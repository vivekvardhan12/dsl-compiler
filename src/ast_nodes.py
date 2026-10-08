"""
ast_nodes.py
------------
The building blocks of the Abstract Syntax Tree (AST).

What is an AST?
    After parsing, we don't want to keep working with a flat list of
    tokens. We want a structure that says *what the program means*:

        tokens: [FILTER] [IDENT:marks] [GT] [NUMBER:60] [NEWLINE]
        AST:    FilterNode(column="marks", operator=">", value=60)

    Notice what disappeared: the NEWLINE, and the fact that '>' was a GT
    token. Only the meaning is kept. That's why it's called "abstract" -
    punctuation and formatting details are thrown away.

Our language is a simple list of commands, so the tree is shallow:

    Program
     ├── LoadNode
     ├── FilterNode
     ├── SelectNode
     └── ...

Every node remembers its source line and col(umn) so later phases (semantic
analysis, Step 3) can report errors at the exact spot.

We use @dataclass so Python writes __init__, __repr__ and __eq__ for us.
__eq__ is especially handy in tests: we can compare two nodes with ==.
"""

from dataclasses import dataclass, field


@dataclass
class Node:
    """Base class for every AST node.

    Every concrete node ends with two position fields:
        line: source line where the statement starts (1-based)
        col:  source column where the statement starts (1-based)
    They're named 'col' (not 'column') so they never clash with fields
    that hold a *data* column name, like FilterNode.column.
    """


@dataclass
class LoadNode(Node):
    """load "file.csv"  ->  read a CSV file into the working table."""

    path: str
    line: int = 0
    col: int = 0


@dataclass
class FilterNode(Node):
    """filter marks > 60  ->  keep only rows where the condition is true.

    Attributes:
        column:   the column being compared, e.g. "marks"
        operator: one of  >  <  >=  <=  ==  !=
        value:    a number (60, 3.5) or a string ("Hyderabad")
    """

    column: str
    operator: str
    value: object
    line: int = 0
    col: int = 0


@dataclass
class SelectNode(Node):
    """select name, marks  ->  keep only these columns, in this order."""

    columns: list
    line: int = 0
    col: int = 0


@dataclass
class SortNode(Node):
    """sort marks desc  ->  order the rows by a column.

    ascending is True for 'asc' or when no direction is written
    (ascending is the usual default, same as in SQL).
    """

    column: str
    ascending: bool = True
    line: int = 0
    col: int = 0


@dataclass
class ShowNode(Node):
    """show  ->  print the current table."""

    line: int = 0
    col: int = 0


@dataclass
class PrintNode(Node):
    """print avg(marks)  ->  print one aggregate value.

    function is one of: count, sum, avg, min, max
    """

    function: str
    column: str
    line: int = 0
    col: int = 0


@dataclass
class PlotNode(Node):
    """plot bar name marks  ->  draw a chart (optional feature).

    Attributes:
        kind:     chart type written by the user, e.g. "bar" or "line".
                  Whether the kind is valid is checked in Step 3 (semantic
                  analysis), because it's about meaning, not grammar.
        x_column: column for the x-axis
        y_column: column for the y-axis
    """

    kind: str
    x_column: str
    y_column: str
    line: int = 0
    col: int = 0


@dataclass
class CombinedFilterNode(Node):
    """Several filters merged into one by the optimizer (Step 6).

    The user never writes this directly. When the optimizer sees
        filter marks > 60
        filter city == "Hyderabad"
    it replaces both with ONE CombinedFilterNode, so the generated code
    scans the table once instead of twice:
        df = df[(df['marks'] > 60) & (df['city'] == 'Hyderabad')]

    Attributes:
        conditions: the original FilterNodes, in order (all must be true)
    """

    conditions: list
    line: int = 0
    col: int = 0


@dataclass
class Program(Node):
    """The root of the tree: the whole program is a list of statements."""

    statements: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pretty printer
# ---------------------------------------------------------------------------

def describe_node(node) -> str:
    """Return a one-line, human-friendly description of a statement node."""
    if isinstance(node, LoadNode):
        return f'Load(path="{node.path}")'
    if isinstance(node, FilterNode):
        value = f'"{node.value}"' if isinstance(node.value, str) else node.value
        return f"Filter({node.column} {node.operator} {value})"
    if isinstance(node, SelectNode):
        return f"Select(columns=[{', '.join(node.columns)}])"
    if isinstance(node, SortNode):
        direction = "asc" if node.ascending else "desc"
        return f"Sort(column={node.column}, {direction})"
    if isinstance(node, ShowNode):
        return "Show()"
    if isinstance(node, PrintNode):
        return f"Print({node.function}({node.column}))"
    if isinstance(node, PlotNode):
        return f"Plot(kind={node.kind}, x={node.x_column}, y={node.y_column})"
    if isinstance(node, CombinedFilterNode):
        # Reuse the Filter description for each condition, joined with AND.
        parts = [describe_node(condition)[len("Filter("):-1] for condition in node.conditions]
        return f"Filter({' AND '.join(parts)})"
    return repr(node)


def print_tree(program: Program) -> None:
    """Print the AST as a tree, like the 'tree' command shows folders.

    Example output:
        Program
        ├── Load(path="examples/students.csv")      [line 4]
        ├── Filter(marks > 60)                      [line 5]
        └── Show()                                  [line 8]
    """
    print("Program")
    count = len(program.statements)
    for index, statement in enumerate(program.statements):
        # The last child gets └── , all others get ├──
        branch = "└── " if index == count - 1 else "├── "
        text = describe_node(statement)
        print(f"{branch}{text:<45} [line {statement.line}]")
