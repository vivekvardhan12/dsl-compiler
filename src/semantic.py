"""
semantic.py
-----------
PHASE 3 of the compiler: Semantic Analysis.

The parser only checks GRAMMAR (is the sentence well-formed?).
Semantic analysis checks MEANING (does the sentence make sense?).

    filter salary > 50     <- perfect grammar, but students.csv has no 'salary'
    print avg(name)        <- perfect grammar, but you can't average names
    show                   <- perfect grammar, but nothing has been loaded yet

All three pass the parser. All three are caught here.

---------------------------------------------------------------------------
THE KEY IDEA: the Symbol Table
---------------------------------------------------------------------------
In a C compiler, the symbol table records every variable and its type
(int x, float y...). In our language, the "variables" are the COLUMNS of
the current table, so our symbol table records each column and its type:

    after  load "students.csv"     { name: text, age: number, city: text, marks: number }
    after  select name, marks      { name: text, marks: number }

Notice the table CHANGES as the program runs: 'select' removes columns.
So after 'select name, marks', using 'city' is an error even though the
CSV has it. We walk the statements in order and keep the table up to date.

How do we know the column types? At compile time we open the CSV and look:
if every value in a column parses as a number, it's 'number', else 'text'.
This is called type inference - the user never writes types.

---------------------------------------------------------------------------
CHECKS PERFORMED
---------------------------------------------------------------------------
  load    - file exists, is a readable CSV with a header, no duplicate headers
  any     - a 'load' must come before any other command
  filter  - column exists; value type matches column type;
            text columns only allow == and !=
  select  - every column exists; no column listed twice
  sort    - column exists
  print   - column exists; sum/avg need a number column
  plot    - chart kind is bar/line/scatter; y column is a number
            (scatter needs a number x column too)
  warning - program produces no output (no show/print/plot)

Run this file directly to see the symbol table after each statement:
    python src/semantic.py examples/analysis.dsl
"""

import csv
import difflib
import os
import sys

from ast_nodes import (
    FilterNode,
    LoadNode,
    PlotNode,
    PrintNode,
    Program,
    SelectNode,
    ShowNode,
    SortNode,
    describe_node,
)
from errors import DSLError, SemanticError
from parser import parse_source

# Type names used in the symbol table.
NUMBER = "number"
TEXT = "text"

# Aggregates that only make sense on numbers. (count/min/max work on text too:
# min/max of names gives the alphabetically first/last.)
NUMERIC_ONLY_AGGREGATES = {"sum", "avg"}

# Chart types the 'plot' command supports.
PLOT_KINDS = {"bar", "line", "scatter"}


class SymbolTable:
    """Records which columns the current table has and the type of each.

    A plain dict wrapped in a class, so the rest of the code reads like
    English: table.has("marks"), table.type_of("marks").
    The dict keeps insertion order, which matches the CSV column order.
    """

    def __init__(self, columns: dict):
        """Args:
            columns: mapping of column name -> NUMBER or TEXT
        """
        self.columns = dict(columns)

    def has(self, name: str) -> bool:
        """Return True if the column exists."""
        return name in self.columns

    def type_of(self, name: str) -> str:
        """Return NUMBER or TEXT for an existing column."""
        return self.columns[name]

    def names(self) -> list:
        """Return the column names in order."""
        return list(self.columns)

    def keep_only(self, names: list) -> "SymbolTable":
        """Return a NEW table with only the given columns, in the given order.

        Used by 'select'. We return a new object instead of changing this
        one, so each step's table can be printed/inspected independently.
        """
        return SymbolTable({name: self.columns[name] for name in names})

    def __str__(self) -> str:
        """Readable form, e.g. { name: text, marks: number }"""
        inner = ", ".join(f"{name}: {kind}" for name, kind in self.columns.items())
        return "{ " + inner + " }"


def infer_column_types(csv_path: str) -> dict:
    """Open a CSV file and work out each column's type.

    Rule: a column is NUMBER if every non-empty value can be read as a
    number; otherwise it is TEXT. Empty cells are ignored (missing data).
    A column with no values at all is treated as TEXT.

    Args:
        csv_path: path to the CSV file

    Returns:
        dict of column name -> NUMBER or TEXT, in file order.

    Raises:
        ValueError: if the file has no header row or duplicate column names.
        OSError: if the file can't be opened (caller turns this into a nice error).
    """
    # newline="" is what the csv module documentation recommends,
    # so quoted fields containing line breaks are read correctly.
    with open(csv_path, newline="", encoding="utf-8") as file:
        reader = csv.reader(file)
        header = next(reader, None)
        if not header:
            raise ValueError("the CSV file is empty (no header row)")

        header = [name.strip() for name in header]
        duplicates = sorted({name for name in header if header.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate column name(s) in header: {', '.join(duplicates)}")

        # Start by assuming every column is numeric, and that we've seen no values.
        is_numeric = [True] * len(header)
        has_value = [False] * len(header)

        for row in reader:
            for index, raw_value in enumerate(row[: len(header)]):
                value = raw_value.strip()
                if value == "":
                    continue  # missing value: tells us nothing about the type
                has_value[index] = True
                if is_numeric[index]:
                    try:
                        float(value)
                    except ValueError:
                        is_numeric[index] = False  # one non-number is enough

    return {
        name: NUMBER if (is_numeric[i] and has_value[i]) else TEXT
        for i, name in enumerate(header)
    }


class SemanticAnalyzer:
    """Walks the AST in order, tracking the symbol table and checking meaning.

    Usage:
        warnings = SemanticAnalyzer().analyze(program)
    Raises SemanticError on the first real problem; returns a list of
    warning strings for things that are allowed but probably mistakes.
    """

    def __init__(self, verbose: bool = False):
        """Args:
            verbose: if True, print the symbol table after every statement
                     (used by the command-line demo).
        """
        self.verbose = verbose
        self.table = None     # SymbolTable; None means "nothing loaded yet"
        self.warnings = []

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def analyze(self, program: Program) -> list:
        """Check every statement in order. Returns the list of warnings."""
        # Dispatch table: node class -> checking method (same idea as the parser).
        checkers = {
            LoadNode: self._check_load,
            FilterNode: self._check_filter,
            SelectNode: self._check_select,
            SortNode: self._check_sort,
            ShowNode: self._check_show,
            PrintNode: self._check_print,
            PlotNode: self._check_plot,
        }

        for node in program.statements:
            # Every command except 'load' needs data to work on.
            if not isinstance(node, LoadNode) and self.table is None:
                raise SemanticError(
                    "No data loaded yet. Add a 'load \"file.csv\"' line before this command",
                    node.line,
                    node.col,
                )

            checkers[type(node)](node)

            if self.verbose:
                print(f"{describe_node(node):<42} -> {self.table}")

        produces_output = any(
            isinstance(node, (ShowNode, PrintNode, PlotNode)) for node in program.statements
        )
        if program.statements and not produces_output:
            self.warnings.append(
                "The program has no show, print or plot command, so it will produce no output"
            )

        return self.warnings

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _require_column(self, name: str, node, purpose: str):
        """Raise a SemanticError if `name` is not in the current table.

        Adds a "did you mean ...?" hint when a column with a similar name
        exists - e.g. 'mark' -> 'marks'. difflib is in Python's standard
        library and measures how similar two strings are.

        Args:
            name:    the column the user wrote
            node:    the AST node (for line/column in the error)
            purpose: short text for the message, e.g. "in 'filter'"
        """
        if self.table.has(name):
            return

        message = f"Unknown column '{name}' {purpose}."
        suggestions = difflib.get_close_matches(name, self.table.names(), n=1)
        if suggestions:
            message += f" Did you mean '{suggestions[0]}'?"
        message += f" Available columns: {', '.join(self.table.names())}"
        raise SemanticError(message, node.line, node.col)

    # ------------------------------------------------------------------
    # One checker per statement type
    # ------------------------------------------------------------------

    def _check_load(self, node: LoadNode):
        """The file must exist and be a valid CSV. Builds a fresh symbol table.

        Paths are relative to the folder you run the compiler from
        (the project root), same as the generated Python script will use.
        """
        if not node.path.lower().endswith(".csv"):
            raise SemanticError(f"'load' only supports .csv files, got \"{node.path}\"", node.line, node.col)

        if not os.path.isfile(node.path):
            raise SemanticError(
                f"File not found: \"{node.path}\" (paths are relative to the folder "
                f"you run the compiler from: {os.getcwd()})",
                node.line,
                node.col,
            )

        try:
            column_types = infer_column_types(node.path)
        except (ValueError, OSError, UnicodeDecodeError, csv.Error) as problem:
            raise SemanticError(f"Cannot read \"{node.path}\": {problem}", node.line, node.col)

        # A second 'load' simply replaces the current table.
        self.table = SymbolTable(column_types)

    def _check_filter(self, node: FilterNode):
        """Column exists, value type matches, operator suits the type."""
        self._require_column(node.column, node, "in 'filter'")
        column_type = self.table.type_of(node.column)
        value_type = TEXT if isinstance(node.value, str) else NUMBER

        if column_type == NUMBER and value_type == TEXT:
            raise SemanticError(
                f"Column '{node.column}' holds numbers, so compare it with a number, "
                f"not text \"{node.value}\"",
                node.line,
                node.col,
            )
        if column_type == TEXT and value_type == NUMBER:
            raise SemanticError(
                f"Column '{node.column}' holds text, so compare it with quoted text, "
                f"e.g. {node.column} == \"{node.value}\"",
                node.line,
                node.col,
            )
        if column_type == TEXT and node.operator not in ("==", "!="):
            raise SemanticError(
                f"Text column '{node.column}' can only be compared with == or !=, "
                f"not '{node.operator}'",
                node.line,
                node.col,
            )

    def _check_select(self, node: SelectNode):
        """Every column exists and none is repeated. Shrinks the symbol table."""
        seen = set()
        for name in node.columns:
            if name in seen:
                raise SemanticError(f"Column '{name}' is listed twice in 'select'", node.line, node.col)
            seen.add(name)
            self._require_column(name, node, "in 'select'")

        # From now on, only these columns exist.
        self.table = self.table.keep_only(node.columns)

    def _check_sort(self, node: SortNode):
        """The sort column must exist (numbers and text can both be sorted)."""
        self._require_column(node.column, node, "in 'sort'")

    def _check_show(self, node: ShowNode):
        """Nothing extra to check - the 'data loaded' check already ran."""

    def _check_print(self, node: PrintNode):
        """Column exists; sum and avg need numbers."""
        self._require_column(node.column, node, f"in '{node.function}'")
        if node.function in NUMERIC_ONLY_AGGREGATES and self.table.type_of(node.column) != NUMBER:
            raise SemanticError(
                f"Cannot calculate {node.function}() of text column '{node.column}'. "
                f"Use count, min or max for text",
                node.line,
                node.col,
            )

    def _check_plot(self, node: PlotNode):
        """Chart kind is supported; axis columns exist and have suitable types."""
        if node.kind not in PLOT_KINDS:
            raise SemanticError(
                f"Unknown chart type '{node.kind}'. Use one of: {', '.join(sorted(PLOT_KINDS))}",
                node.line,
                node.col,
            )
        self._require_column(node.x_column, node, "for the plot x-axis")
        self._require_column(node.y_column, node, "for the plot y-axis")

        if self.table.type_of(node.y_column) != NUMBER:
            raise SemanticError(
                f"The y-axis column '{node.y_column}' must hold numbers", node.line, node.col
            )
        if node.kind == "scatter" and self.table.type_of(node.x_column) != NUMBER:
            raise SemanticError(
                f"A scatter plot needs numbers on both axes, but '{node.x_column}' holds text",
                node.line,
                node.col,
            )


def analyze_source(source_code: str, verbose: bool = False):
    """Convenience function: run Phases 1-3 on raw text.

    Returns:
        (program, warnings) - the checked AST and any warning messages.
    Raises:
        LexerError, ParseError or SemanticError (all DSLError subclasses).
    """
    program = parse_source(source_code)
    warnings = SemanticAnalyzer(verbose=verbose).analyze(program)
    return program, warnings


def main():
    """Command-line entry point: python src/semantic.py <file.dsl>"""
    if len(sys.argv) != 2:
        print("Usage: python src/semantic.py <file.dsl>")
        sys.exit(1)

    file_path = sys.argv[1]
    try:
        with open(file_path, encoding="utf-8") as file:
            source_code = file.read()
    except FileNotFoundError:
        print(f"Error: file not found: {file_path}")
        sys.exit(1)

    print("Symbol table after each statement:\n")
    try:
        _, warnings = analyze_source(source_code, verbose=True)
    except DSLError as error:
        print()
        print(error.format(source_code))
        sys.exit(1)

    for warning in warnings:
        print(f"\nWarning: {warning}")
    print("\nSemantic check passed.")


if __name__ == "__main__":
    main()
