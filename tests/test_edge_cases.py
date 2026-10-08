"""
test_edge_cases.py
------------------
Small, unusual situations that the main test files don't reach.

These were found with the coverage report (pytest --cov): every line it
listed as "Missing" is either tested here or is a deliberate exclusion
(like `if __name__ == "__main__":`, see .coveragerc).

Run from the project root with:
    pytest -v
"""

import pytest

from ast_nodes import (
    CombinedFilterNode,
    FilterNode,
    PlotNode,
    Program,
    ShowNode,
    describe_node,
    print_tree,
)
from codegen import CodeGenerator
from errors import LexerError, ParseError
from lexer import Lexer
from main import CompilerDriver, main
from parser import describe_token
from tokens import Token, TokenType

# ---------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------

def test_number_followed_by_dot_without_digits():
    """'3.' is the number 3 followed by an unexpected '.'"""
    with pytest.raises(LexerError, match="Unexpected character '.'"):
        Lexer("filter marks > 3.").tokenize()


def test_single_exclamation_gives_hint():
    with pytest.raises(LexerError, match="Did you mean '!='"):
        Lexer("filter city ! 5").tokenize()


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "token, expected",
    [
        (Token(TokenType.EOF, None, 1, 1), "end of file"),
        (Token(TokenType.NEWLINE, "\\n", 1, 1), "end of line"),
        (Token(TokenType.IDENT, "marks", 1, 1), "name 'marks'"),
        (Token(TokenType.NUMBER, 60, 1, 1), "number 60"),
        (Token(TokenType.STRING, "a.csv", 1, 1), 'text "a.csv"'),
        (Token(TokenType.GT, ">", 1, 1), "'>'"),
    ],
)
def test_describe_token(token, expected):
    assert describe_token(token) == expected


def test_string_where_column_expected():
    from parser import parse_source
    with pytest.raises(ParseError, match='found text "marks"'):
        parse_source('sort "marks"')


# ---------------------------------------------------------------------------
# AST pretty printer
# ---------------------------------------------------------------------------

def test_describe_plot_and_combined_filter():
    assert describe_node(PlotNode("bar", "name", "marks")) == "Plot(kind=bar, x=name, y=marks)"
    combined = CombinedFilterNode([FilterNode("marks", ">", 60), FilterNode("city", "==", "Pune")])
    assert describe_node(combined) == 'Filter(marks > 60 AND city == "Pune")'


def test_describe_unknown_node_falls_back_to_repr():
    assert describe_node(Program()) == repr(Program())


def test_print_tree_marks_last_child(capsys):
    print_tree(Program([ShowNode(line=1), ShowNode(line=2)]))
    lines = capsys.readouterr().out.splitlines()
    assert lines[1].startswith("├── ") and lines[2].startswith("└── ")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

def test_error_format_when_line_is_past_end_of_source():
    error = ParseError("Something went wrong", line=99, column=1)
    assert error.format("show") == "Syntax error at line 99, column 1: Something went wrong"


# ---------------------------------------------------------------------------
# Code generator
# ---------------------------------------------------------------------------

def test_codegen_without_source_text_still_comments_lines():
    """If no source text is given, comments fall back to the line number."""
    code = CodeGenerator().generate(Program([ShowNode(line=7)]))
    assert "# line 7\n" in code


# ---------------------------------------------------------------------------
# Compiler driver (main.py)
# ---------------------------------------------------------------------------

@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Temp folder with data.csv, set as the current directory."""
    (tmp_path / "data.csv").write_text("name,marks\nAarav,78\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_no_optimize_with_opt_flag_says_skipped(workdir, capfd):
    (workdir / "p.dsl").write_text('load "data.csv"\nshow\n', encoding="utf-8")
    main(["p.dsl", "--opt", "--no-optimize", "--no-run"])
    assert "Skipped (--no-optimize)." in capfd.readouterr().out


def test_source_file_that_is_not_utf8(workdir, capfd):
    (workdir / "binary.dsl").write_bytes(b"\xff\xfe\x00show")
    assert main(["binary.dsl"]) == 1
    assert "cannot read binary.dsl" in capfd.readouterr().out


def test_runtime_failure_message_from_main(workdir, capfd, monkeypatch):
    """If the generated script fails, main() returns its exit code and says so."""
    (workdir / "p.dsl").write_text('load "data.csv"\nshow\n', encoding="utf-8")
    monkeypatch.setattr(CompilerDriver, "run", staticmethod(lambda output_path: 3))
    assert main(["p.dsl"]) == 3
    assert "stopped with exit code 3" in capfd.readouterr().out
