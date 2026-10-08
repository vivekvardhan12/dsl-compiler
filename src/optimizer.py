"""
optimizer.py
------------
PHASE 4 of the compiler: Optimization.

The optimizer rewrites the checked AST into an EQUIVALENT but cheaper AST,
before code generation. "Equivalent" is the golden rule: the optimized
program must print exactly the same results as the original.

Five optimizations, all classic ones from compiler and database textbooks:

  1. Dead code elimination   - remove commands whose result is never output
  2. Filter pushdown         - move filters earlier, so later steps
                               (sort, select) work on fewer rows
  3. Filter merging          - combine consecutive filters into one,
                               so the table is scanned once, not N times
  4. Redundant sort removal  - an earlier sort is pointless if a later sort
                               re-orders the table before anything is shown
  5. Redundant select removal- only the last select before an output matters

---------------------------------------------------------------------------
KEY IDEA 1: barriers and blocks
---------------------------------------------------------------------------
Some statements OBSERVE the table (show, print, plot) and 'load' REPLACES
it. We may never move code across these, or the output would change.
We call them BARRIERS. Between two barriers there's a BLOCK of pure
transformations (filter, select, sort) that nobody can see individually -
only the final table at the end of the block matters. So inside a block we
are free to reorder and combine, as long as the final table is the same.

    load "s.csv"        <- barrier
    select name, marks  |
    filter marks > 60   | block 1: free to rearrange
    sort marks desc     |
    show                <- barrier
    sort name           | block 2
    show                <- barrier

---------------------------------------------------------------------------
KEY IDEA 2: liveness (for dead code elimination)
---------------------------------------------------------------------------
A transformation is LIVE if some output statement later sees its effect
(before the next 'load' replaces the table). We find this by walking the
program BACKWARDS, which is how real compilers do liveness analysis.

---------------------------------------------------------------------------
A NOTE ON SORT ORDER
---------------------------------------------------------------------------
Like SQL's ORDER BY, our 'sort' only promises to order rows by the given
column; rows with EQUAL values may come out in any order. That rule is
what makes optimizations 2 and 4 valid.

Run this file directly to see the AST before and after optimization:
    python src/optimizer.py examples/optimize_demo.dsl
"""

import sys

from ast_nodes import (
    CombinedFilterNode,
    FilterNode,
    LoadNode,
    PlotNode,
    PrintNode,
    Program,
    SelectNode,
    ShowNode,
    SortNode,
    describe_node,
    print_tree,
)
from errors import DSLError
from semantic import analyze_source

# Statements that look at the current table and produce output.
OUTPUT_TYPES = (ShowNode, PrintNode, PlotNode)

# Statements that transform the table without producing output.
TRANSFORM_TYPES = (FilterNode, SelectNode, SortNode, CombinedFilterNode)


def source_text(node) -> str:
    """Short label for reports, e.g. "'filter marks > 60' (line 5)"."""
    return f"{describe_node(node)} (line {node.line})"


class Optimizer:
    """Applies all optimization passes to a Program and records what changed.

    Usage:
        optimizer = Optimizer()
        optimized_program = optimizer.optimize(program)
        for message in optimizer.report:
            print(message)

    The input Program is never modified; a new Program is returned.
    That makes before/after comparisons (and testing) easy.
    """

    def __init__(self):
        """Start with an empty report."""
        self.report = []  # human-readable description of each change made

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def optimize(self, program: Program) -> Program:
        """Run every pass in order and return the optimized Program.

        Order matters: dead code goes first (less to work on), and
        pushdown runs before merging because pushing filters to the front
        of a block is what puts them next to each other.
        """
        statements = list(program.statements)
        statements = self._eliminate_dead_code(statements)
        statements = self._optimize_blocks(statements)
        return Program(statements=statements)

    # ------------------------------------------------------------------
    # Pass 1: dead code elimination (backward liveness analysis)
    # ------------------------------------------------------------------

    def _eliminate_dead_code(self, statements: list) -> list:
        """Remove transforms and loads whose effect is never output.

        Walk backwards with a flag `table_needed`:
          - output statement   -> always kept; the table IS needed above it
          - transform          -> kept only if the table is needed
          - load               -> kept only if needed; above a load the old
                                  table is NOT needed any more (load replaces it)
        """
        kept_reversed = []
        removed_messages = []   # collected backwards, reversed at the end
        table_needed = False

        for node in reversed(statements):
            if isinstance(node, OUTPUT_TYPES):
                kept_reversed.append(node)
                table_needed = True
            elif isinstance(node, LoadNode):
                if table_needed:
                    kept_reversed.append(node)
                else:
                    removed_messages.append(f"Dead code: removed {source_text(node)} - its data is never shown")
                table_needed = False
            else:  # a transform
                if table_needed:
                    kept_reversed.append(node)
                else:
                    removed_messages.append(f"Dead code: removed {source_text(node)} - nothing is shown after it")

        # We walked backwards, so reverse both lists back into program order.
        self.report.extend(reversed(removed_messages))
        return list(reversed(kept_reversed))

    # ------------------------------------------------------------------
    # Passes 2-5: work on one block of transforms at a time
    # ------------------------------------------------------------------

    def _optimize_blocks(self, statements: list) -> list:
        """Split the program into blocks between barriers; optimize each block."""
        result = []
        block = []
        for node in statements:
            if isinstance(node, TRANSFORM_TYPES):
                block.append(node)
            else:
                # A barrier: finish the current block, then keep the barrier as-is.
                result.extend(self._optimize_block(block))
                block = []
                result.append(node)
        result.extend(self._optimize_block(block))  # a trailing block, if any
        return result

    def _optimize_block(self, block: list) -> list:
        """Optimize a list of consecutive transforms (no barriers inside)."""
        if len(block) < 2:
            return block  # nothing to rearrange or combine
        filters = [node for node in block if isinstance(node, FilterNode)]
        others = [node for node in block if not isinstance(node, FilterNode)]

        others = self._remove_redundant(others, SortNode, "sort", "a later sort re-orders the rows anyway")
        others = self._remove_redundant(others, SelectNode, "select", "a later select chooses the final columns")
        # Report pushdown only past statements that are still there after
        # redundant ones were removed - otherwise the report would mention
        # moving a filter "before" something that no longer exists.
        surviving = [node for node in block if isinstance(node, FilterNode) or any(node is o for o in others)]
        self._report_pushdown(surviving)
        merged_filters = self._merge_filters(filters)
        return merged_filters + others

    def _report_pushdown(self, block: list):
        """Pass 2: filter pushdown. Filters go to the FRONT of the block.

        Why it's safe:
          - before a 'select', the table has the same or MORE columns, so
            the filter's column still exists there;
          - filtering doesn't depend on row order, and sorting fewer rows
            gives the same order for the rows that remain.
        Why it's faster: sort is O(n log n) and select copies data, so
        doing them on fewer rows saves work.

        The actual move happens in _optimize_block (filters + others);
        this method only reports the filters that really moved.
        """
        for position, node in enumerate(block):
            if isinstance(node, FilterNode):
                earlier_non_filters = [n for n in block[:position] if not isinstance(n, FilterNode)]
                if earlier_non_filters:
                    jumped = ", ".join(describe_node(n) for n in earlier_non_filters)
                    self.report.append(f"Filter pushdown: moved {source_text(node)} before {jumped}")

    def _remove_redundant(self, nodes: list, node_type, keyword: str, reason: str) -> list:
        """Passes 4 and 5: keep only the LAST node of `node_type` in a block.

        Inside a block nobody sees the table between steps, so:
          - sort A ... sort B   -> only B decides the final order
          - select A ... select B -> only B decides the final columns
            (B's columns are a subset of A's, which semantic analysis
            already guaranteed)
        """
        last_index = max((i for i, n in enumerate(nodes) if isinstance(n, node_type)), default=None)
        kept = []
        for index, node in enumerate(nodes):
            if isinstance(node, node_type) and index != last_index:
                self.report.append(f"Redundant {keyword}: removed {source_text(node)} - {reason}")
            else:
                kept.append(node)
        return kept

    def _merge_filters(self, filters: list) -> list:
        """Pass 3: merge 2+ filters into one CombinedFilterNode.

        filter a > 1 + filter b < 2  ->  ONE pass with (a > 1) & (b < 2).
        Rows must satisfy every filter either way, so the result is the same.
        """
        if len(filters) < 2:
            return filters
        lines = ", ".join(str(node.line) for node in filters)
        self.report.append(f"Filter merging: combined {len(filters)} filters (lines {lines}) into one")
        first = filters[0]
        return [CombinedFilterNode(conditions=filters, line=first.line, col=first.col)]


def main():
    """Command-line entry point: python src/optimizer.py <file.dsl>"""
    if len(sys.argv) != 2:
        print("Usage: python src/optimizer.py <file.dsl>")
        sys.exit(1)

    file_path = sys.argv[1]
    try:
        with open(file_path, encoding="utf-8") as file:
            source_code = file.read()
    except FileNotFoundError:
        print(f"Error: file not found: {file_path}")
        sys.exit(1)

    try:
        program, _ = analyze_source(source_code)
    except DSLError as error:
        print(error.format(source_code))
        sys.exit(1)

    optimizer = Optimizer()
    optimized = optimizer.optimize(program)

    print("BEFORE optimization:")
    print_tree(program)
    print("\nAFTER optimization:")
    print_tree(optimized)
    print("\nChanges:")
    for message in optimizer.report or ["(none - the program is already optimal)"]:
        print(f"  - {message}")
    print(f"\nStatements: {len(program.statements)} -> {len(optimized.statements)}")


if __name__ == "__main__":
    main()
