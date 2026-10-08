"""
test_cli.py
-----------
Tests for the small command-line demos built into each phase:

    python src/lexer.py     file.dsl   -> prints tokens
    python src/parser.py    file.dsl   -> prints the AST
    python src/semantic.py  file.dsl   -> prints the symbol table
    python src/optimizer.py file.dsl   -> prints the AST before/after
    python src/codegen.py   file.dsl   -> writes and prints output/<name>.py

Each demo's main() reads sys.argv, so the tests replace sys.argv with
monkeypatch (restored automatically afterwards) and capture what's printed.
Every demo is checked for: success, a DSL error, a missing file, and
being called with the wrong number of arguments.
"""

import sys

import pytest

import codegen
import lexer
import optimizer
import parser
import semantic

DATA_CSV = "name,marks\nAarav,78\nDiya,55\n"
VALID_PROGRAM = 'load "data.csv"\nsort name\nfilter marks > 60\nshow\n'

# (module, text that must appear in its successful output)
DEMOS = [
    (lexer, "[FILTER] [IDENT:marks] [GT] [NUMBER:60]"),
    (parser, "Parsed 4 statements successfully."),
    (semantic, "Semantic check passed."),
    (optimizer, "AFTER optimization:"),
    (codegen, "Generated:"),
]


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Temp folder with data.csv and prog.dsl, set as the current directory."""
    (tmp_path / "data.csv").write_text(DATA_CSV, encoding="utf-8")
    (tmp_path / "prog.dsl").write_text(VALID_PROGRAM, encoding="utf-8")
    (tmp_path / "bad.dsl").write_text("filter marks @ 60\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run_demo(module, monkeypatch, *args):
    """Call module.main() as if run with the given command-line arguments.

    Returns:
        The exit code: 0 if main() returned normally, else the sys.exit code.
    """
    monkeypatch.setattr(sys, "argv", [f"{module.__name__}.py", *args])
    try:
        module.main()
    except SystemExit as exit_signal:
        return exit_signal.code
    return 0


@pytest.mark.parametrize("module, expected", DEMOS, ids=[m.__name__ for m, _ in DEMOS])
def test_demo_success(workdir, monkeypatch, capsys, module, expected):
    assert run_demo(module, monkeypatch, "prog.dsl") == 0
    assert expected in capsys.readouterr().out


@pytest.mark.parametrize("module", [m for m, _ in DEMOS], ids=[m.__name__ for m, _ in DEMOS])
def test_demo_reports_dsl_error(workdir, monkeypatch, capsys, module):
    assert run_demo(module, monkeypatch, "bad.dsl") == 1
    assert "Lexer error at line 1, column 14" in capsys.readouterr().out


@pytest.mark.parametrize("module", [m for m, _ in DEMOS], ids=[m.__name__ for m, _ in DEMOS])
def test_demo_missing_file(workdir, monkeypatch, capsys, module):
    assert run_demo(module, monkeypatch, "nope.dsl") == 1
    assert "file not found" in capsys.readouterr().out


@pytest.mark.parametrize("module", [m for m, _ in DEMOS], ids=[m.__name__ for m, _ in DEMOS])
def test_demo_usage_message(workdir, monkeypatch, capsys, module):
    assert run_demo(module, monkeypatch) == 1  # no file argument
    assert "Usage:" in capsys.readouterr().out


def test_codegen_demo_writes_file(workdir, monkeypatch, capsys):
    run_demo(codegen, monkeypatch, "prog.dsl")
    assert (workdir / "output" / "prog.py").exists()


def test_codegen_demo_prints_warnings(workdir, monkeypatch, capsys):
    (workdir / "quiet.dsl").write_text('load "data.csv"\nfilter marks > 60\n', encoding="utf-8")
    run_demo(codegen, monkeypatch, "quiet.dsl")
    assert "Warning:" in capsys.readouterr().out


def test_semantic_demo_prints_warnings(workdir, monkeypatch, capsys):
    (workdir / "quiet.dsl").write_text('load "data.csv"\nfilter marks > 60\n', encoding="utf-8")
    run_demo(semantic, monkeypatch, "quiet.dsl")
    assert "Warning:" in capsys.readouterr().out


def test_optimizer_demo_already_optimal(workdir, monkeypatch, capsys):
    (workdir / "tidy.dsl").write_text('load "data.csv"\nshow\n', encoding="utf-8")
    run_demo(optimizer, monkeypatch, "tidy.dsl")
    assert "already optimal" in capsys.readouterr().out
