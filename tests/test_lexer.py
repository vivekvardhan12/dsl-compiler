"""
test_lexer.py
-------------
Automated tests for Phase 1 (the lexer).

Run from the project root with:
    pytest -v

Each test feeds a small piece of DSL text to the lexer and checks the
tokens that come out. If someone later breaks the lexer, these tests fail
immediately and tell you exactly what broke.
"""

import pytest

from errors import LexerError
from lexer import Lexer
from tokens import TokenType as T


def types_of(source):
    """Helper: lex the source and return just the token types (easy to compare)."""
    return [token.type for token in Lexer(source).tokenize()]


def values_of(source):
    """Helper: lex the source and return just the token values."""
    return [token.value for token in Lexer(source).tokenize()]


# ---------------------------------------------------------------------------
# Happy-path tests: valid input produces the right tokens
# ---------------------------------------------------------------------------

def test_filter_statement():
    """The example from the plan: filter marks > 60"""
    assert types_of("filter marks > 60") == [
        T.FILTER, T.IDENT, T.GT, T.NUMBER, T.NEWLINE, T.EOF
    ]


def test_load_statement_strips_quotes():
    """The string value must not include the quote characters."""
    tokens = Lexer('load "students.csv"').tokenize()
    assert tokens[0].type == T.LOAD
    assert tokens[1].type == T.STRING
    assert tokens[1].value == "students.csv"


def test_select_with_commas():
    assert types_of("select name, city, marks") == [
        T.SELECT, T.IDENT, T.COMMA, T.IDENT, T.COMMA, T.IDENT, T.NEWLINE, T.EOF
    ]


def test_print_aggregate_function():
    assert types_of("print avg(marks)") == [
        T.PRINT, T.AVG, T.LPAREN, T.IDENT, T.RPAREN, T.NEWLINE, T.EOF
    ]


@pytest.mark.parametrize(
    "operator, expected_type",
    [(">", T.GT), ("<", T.LT), (">=", T.GE), ("<=", T.LE), ("==", T.EQ), ("!=", T.NE)],
)
def test_all_comparison_operators(operator, expected_type):
    """Every operator, including two-character ones (maximal munch)."""
    assert types_of(f"filter age {operator} 18")[2] == expected_type


def test_numbers_int_and_float():
    """60 stays an int, 3.5 becomes a float."""
    assert values_of("filter a > 60")[3] == 60
    assert isinstance(values_of("filter a > 60")[3], int)
    assert values_of("filter a > 3.5")[3] == 3.5


def test_keywords_are_case_insensitive():
    assert types_of("FILTER Marks > 60")[0] == T.FILTER
    assert types_of("Sort marks DESC")[2] == T.DESC


def test_identifiers_keep_original_case():
    """Column names are case-sensitive in CSV files, so we keep them as-is."""
    assert values_of("select Marks")[1] == "Marks"


def test_identifier_with_underscore_and_digits():
    assert values_of("select total_marks2")[1] == "total_marks2"


def test_comments_and_blank_lines_are_ignored():
    source = "# a comment\n\n\nshow   # trailing comment\n\n"
    assert types_of(source) == [T.SHOW, T.NEWLINE, T.EOF]


def test_windows_line_endings():
    """Files saved on Windows use \\r\\n; the \\r must be ignored."""
    assert types_of("show\r\nshow\r\n") == [T.SHOW, T.NEWLINE, T.SHOW, T.NEWLINE, T.EOF]


def test_empty_program():
    assert types_of("") == [T.EOF]


def test_line_and_column_numbers():
    tokens = Lexer("show\nfilter marks > 60").tokenize()
    gt_token = [t for t in tokens if t.type == T.GT][0]
    assert gt_token.line == 2
    assert gt_token.column == 14


# ---------------------------------------------------------------------------
# Error tests: invalid input raises LexerError at the right place
# ---------------------------------------------------------------------------

def test_unexpected_character():
    with pytest.raises(LexerError) as error_info:
        Lexer("filter marks @ 60").tokenize()
    assert error_info.value.line == 1
    assert error_info.value.column == 14


def test_unterminated_string():
    with pytest.raises(LexerError, match="Unterminated string"):
        Lexer('load "students.csv').tokenize()


def test_single_equals_gives_hint():
    with pytest.raises(LexerError, match="Did you mean '=='"):
        Lexer("filter city = 5").tokenize()


def test_error_format_shows_caret():
    source = "filter marks @ 60"
    with pytest.raises(LexerError) as error_info:
        Lexer(source).tokenize()
    message = error_info.value.format(source)
    assert "line 1, column 14" in message
    assert "             ^" in message
