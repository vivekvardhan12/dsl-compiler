"""
test_parser.py
--------------
Automated tests for Phase 2 (the parser).

Run from the project root with:
    pytest -v

Valid programs must produce the expected AST nodes; invalid programs must
raise ParseError at the right line and column.
"""

import pytest

from ast_nodes import (
    FilterNode,
    LoadNode,
    PlotNode,
    PrintNode,
    SelectNode,
    ShowNode,
    SortNode,
)
from errors import LexerError, ParseError
from parser import parse_source


def single_statement(source):
    """Helper: parse a one-line program and return its only statement."""
    program = parse_source(source)
    assert len(program.statements) == 1
    return program.statements[0]


# ---------------------------------------------------------------------------
# Happy path: each statement type builds the right node
# ---------------------------------------------------------------------------

def test_load():
    node = single_statement('load "students.csv"')
    assert node == LoadNode(path="students.csv", line=1, col=1)


def test_filter_with_number():
    node = single_statement("filter marks > 60")
    assert isinstance(node, FilterNode)
    assert (node.column, node.operator, node.value) == ("marks", ">", 60)


def test_filter_with_string():
    node = single_statement('filter city == "Hyderabad"')
    assert (node.column, node.operator, node.value) == ("city", "==", "Hyderabad")


def test_select_one_column():
    assert single_statement("select name").columns == ["name"]


def test_select_many_columns_keeps_order():
    assert single_statement("select name, city, marks").columns == ["name", "city", "marks"]


def test_sort_default_is_ascending():
    node = single_statement("sort marks")
    assert node == SortNode(column="marks", ascending=True, line=1, col=1)


def test_sort_asc_and_desc():
    assert single_statement("sort marks asc").ascending is True
    assert single_statement("sort marks desc").ascending is False


def test_show():
    assert isinstance(single_statement("show"), ShowNode)


@pytest.mark.parametrize("function", ["count", "sum", "avg", "min", "max"])
def test_print_every_aggregate(function):
    node = single_statement(f"print {function}(marks)")
    assert node == PrintNode(function=function, column="marks", line=1, col=1)


def test_plot():
    node = single_statement("plot bar name marks")
    assert node == PlotNode(kind="bar", x_column="name", y_column="marks", line=1, col=1)


def test_full_program_order_and_lines():
    source = (
        '# comment\n'
        'load "students.csv"\n'
        '\n'
        'filter marks > 60\n'
        'show\n'
    )
    program = parse_source(source)
    types = [type(node) for node in program.statements]
    assert types == [LoadNode, FilterNode, ShowNode]
    assert [node.line for node in program.statements] == [2, 4, 5]


def test_empty_program_has_no_statements():
    assert parse_source("").statements == []
    assert parse_source("# only a comment\n\n").statements == []


# ---------------------------------------------------------------------------
# Error tests: grammar mistakes give a ParseError at the right place
# ---------------------------------------------------------------------------

def assert_parse_error(source, line, column, message_part):
    """Helper: parsing `source` must fail at (line, column) with a message
    containing `message_part`."""
    with pytest.raises(ParseError) as error_info:
        parse_source(source)
    error = error_info.value
    assert (error.line, error.column) == (line, column)
    assert message_part in error.message


def test_line_must_start_with_command():
    assert_parse_error("marks > 60", 1, 1, "Expected a command")


def test_load_needs_quoted_file():
    # (We use 'students' not 'students.csv' here: an unquoted '.' would be
    # caught even earlier, by the lexer, as an unexpected character.)
    assert_parse_error("load students", 1, 6, "file name in quotes")


def test_filter_missing_column():
    assert_parse_error("filter > 60", 1, 8, "column name after 'filter'")


def test_filter_missing_operator():
    assert_parse_error("filter marks 60", 1, 14, "Expected a comparison")


def test_filter_missing_value():
    assert_parse_error("filter marks >", 1, 15, "number or quoted text")


def test_select_trailing_comma():
    assert_parse_error("select name,", 1, 13, "column name after ','")


def test_print_needs_aggregate():
    assert_parse_error("print marks", 1, 7, "count, sum, avg, min or max")


def test_print_missing_bracket():
    assert_parse_error("print avg(marks", 1, 16, "')'")


def test_extra_tokens_after_statement():
    assert_parse_error("show marks", 1, 6, "end of line")


def test_error_on_later_line_reports_that_line():
    assert_parse_error('load "a.csv"\nshow\nsort', 3, 5, "column name after 'sort'")


def test_lexer_errors_still_come_through():
    """parse_source runs the lexer first, so lexer errors appear unchanged."""
    with pytest.raises(LexerError):
        parse_source("filter marks @ 60")
