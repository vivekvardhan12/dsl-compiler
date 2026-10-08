"""
test_optimizer.py
-----------------
Automated tests for Phase 4 (the optimizer).

Run from the project root with:
    pytest -v

Two kinds of tests:
  1. Rule tests        - each optimization fires when it should, and
                         does NOT fire when it would be unsafe.
  2. Equivalence tests - the most important ones: the optimized program
                         must print EXACTLY the same output as the
                         original. An optimizer that changes results is
                         a bug, however fast it is.
"""

import pytest

from ast_nodes import CombinedFilterNode, SelectNode, SortNode
from codegen import CodeGenerator
from optimizer import Optimizer
from semantic import analyze_source

# Marks and ages are all different, so sort results have no ties and the
# equivalence tests can compare outputs exactly.
DATA_CSV = (
    "name,city,age,marks\n"
    "Aarav,Hyderabad,20,78\n"
    "Diya,Chennai,21,55\n"
    "Rohan,Bengaluru,19,91\n"
    "Sneha,Hyderabad,22,64\n"
    "Karthik,Mumbai,23,47\n"
    "Arjun,Delhi,24,95\n"
)


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Temp folder with data.csv (and other.csv), set as the current directory."""
    (tmp_path / "data.csv").write_text(DATA_CSV, encoding="utf-8")
    (tmp_path / "other.csv").write_text("x,y\n1,2\n3,4\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def optimize(*lines):
    """Helper: check a program (starting with load) and optimize it.

    Returns:
        (original_program, optimized_program, report)
    """
    source = "\n".join(['load "data.csv"', *lines])
    program, _ = analyze_source(source)
    optimizer = Optimizer()
    optimized = optimizer.optimize(program)
    return program, optimized, optimizer.report


def kinds(program):
    """Helper: list of node class names, easy to compare."""
    return [type(node).__name__ for node in program.statements]


# ---------------------------------------------------------------------------
# 1. Dead code elimination
# ---------------------------------------------------------------------------

def test_trailing_transforms_are_dead(workdir):
    _, optimized, report = optimize("show", "filter marks > 60", "sort marks")
    assert kinds(optimized) == ["LoadNode", "ShowNode"]
    assert len(report) == 2
    assert report[0].startswith("Dead code: removed Filter")  # program order, not reversed


def test_unused_load_is_dead(workdir):
    _, optimized, report = optimize('load "other.csv"', "show")
    # The first load (data.csv) is replaced before anything is shown.
    assert kinds(optimized) == ["LoadNode", "ShowNode"]
    assert optimized.statements[0].path == "other.csv"
    assert "its data is never shown" in report[0]


def test_transforms_before_output_are_kept(workdir):
    _, optimized, report = optimize("filter marks > 60", "show")
    assert kinds(optimized) == ["LoadNode", "FilterNode", "ShowNode"]
    assert report == []


def test_program_without_output_becomes_empty(workdir):
    _, optimized, _ = optimize("filter marks > 60")
    assert optimized.statements == []


# ---------------------------------------------------------------------------
# 2 + 3. Filter pushdown and merging
# ---------------------------------------------------------------------------

def test_filter_pushed_before_select_and_sort(workdir):
    _, optimized, report = optimize("select name, marks", "sort marks", "filter marks > 60", "show")
    assert kinds(optimized) == ["LoadNode", "FilterNode", "SelectNode", "SortNode", "ShowNode"]
    assert any(message.startswith("Filter pushdown") for message in report)


def test_two_filters_are_merged(workdir):
    _, optimized, report = optimize("filter marks > 60", 'filter city == "Hyderabad"', "show")
    combined = optimized.statements[1]
    assert isinstance(combined, CombinedFilterNode)
    assert [c.column for c in combined.conditions] == ["marks", "city"]
    assert any(message.startswith("Filter merging") for message in report)


def test_pushdown_brings_separated_filters_together_for_merging(workdir):
    _, optimized, _ = optimize("filter marks > 50", "sort age", "filter age < 24", "show")
    assert kinds(optimized) == ["LoadNode", "CombinedFilterNode", "SortNode", "ShowNode"]


def test_filters_never_move_across_an_output(workdir):
    """'show' sees the table, so the filter after it must stay after it."""
    _, optimized, report = optimize("sort marks", "show", "filter marks > 60", "show")
    assert kinds(optimized) == ["LoadNode", "SortNode", "ShowNode", "FilterNode", "ShowNode"]
    assert report == []


# ---------------------------------------------------------------------------
# 4 + 5. Redundant sort / select
# ---------------------------------------------------------------------------

def test_earlier_sort_is_redundant(workdir):
    _, optimized, report = optimize("sort name", "sort marks desc", "show")
    sorts = [n for n in optimized.statements if isinstance(n, SortNode)]
    assert len(sorts) == 1 and sorts[0].column == "marks"
    assert any(message.startswith("Redundant sort") for message in report)


def test_sort_before_output_is_not_redundant(workdir):
    _, optimized, _ = optimize("sort name", "show", "sort marks", "show")
    assert len([n for n in optimized.statements if isinstance(n, SortNode)]) == 2


def test_earlier_select_is_redundant(workdir):
    _, optimized, report = optimize("select name, city, marks", "sort city", "select name, marks", "show")
    selects = [n for n in optimized.statements if isinstance(n, SelectNode)]
    assert len(selects) == 1 and selects[0].columns == ["name", "marks"]
    # The sort between the selects survives and keeps its place before the select.
    assert kinds(optimized) == ["LoadNode", "SortNode", "SelectNode", "ShowNode"]
    assert any(message.startswith("Redundant select") for message in report)


# ---------------------------------------------------------------------------
# General properties
# ---------------------------------------------------------------------------

def test_original_program_is_not_modified(workdir):
    original, _, _ = optimize("select name, marks", "filter marks > 60", "filter marks < 90", "show")
    assert kinds(original) == ["LoadNode", "SelectNode", "FilterNode", "FilterNode", "ShowNode"]


def test_already_optimal_program_is_unchanged(workdir):
    original, optimized, report = optimize("filter marks > 60", "sort marks", "show", "print avg(marks)")
    assert optimized.statements == original.statements
    assert report == []


def test_combined_filter_codegen(workdir):
    source = 'load "data.csv"\nfilter marks > 60\nfilter city == "Hyderabad"\nshow\n'
    program, _ = analyze_source(source)
    code = CodeGenerator(source, "t.dsl").generate(Optimizer().optimize(program))
    assert "df = df[(df['marks'] > 60) & (df['city'] == 'Hyderabad')]" in code
    assert "# lines 2, 3 (merged by optimizer)" in code


# ---------------------------------------------------------------------------
# Equivalence: optimized output == unoptimized output
# ---------------------------------------------------------------------------

EQUIVALENCE_PROGRAMS = [
    ["select name, marks", "filter marks > 60", "sort marks desc", "show"],
    ["filter marks > 50", "sort age", "filter age < 24", "show", "print avg(marks)"],
    ["sort name", "sort marks", "select name, city, marks", "select name, marks", "show"],
    ["show", "filter marks > 60", "sort marks"],                       # dead code
    ['load "other.csv"', "print sum(x)"],                              # dead load
    ['filter city == "Hyderabad"', "print count(name)", "filter marks > 70", "show"],
    ["sort marks", "show", "sort name desc", "filter age > 19", "show", "print max(marks)"],
]


def run_python(code, capsys):
    """Execute generated code and return its printed output."""
    exec(compile(code, "<generated>", "exec"), {})
    return capsys.readouterr().out


@pytest.mark.parametrize("lines", EQUIVALENCE_PROGRAMS)
def test_optimized_output_matches_original(workdir, capsys, lines):
    source = "\n".join(['load "data.csv"', *lines]) + "\n"
    program, _ = analyze_source(source)
    generator = CodeGenerator(source, "t.dsl")

    original_output = run_python(generator.generate(program), capsys)
    optimized_output = run_python(generator.generate(Optimizer().optimize(program)), capsys)

    assert optimized_output == original_output
