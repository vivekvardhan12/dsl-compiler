"""
test_semantic.py
----------------
Automated tests for Phase 3 (semantic analysis).

Run from the project root with:
    pytest -v

Each test writes its own small CSV into a temporary folder (pytest's
`tmp_path` fixture) and switches into that folder (`monkeypatch.chdir`).
That way the tests never depend on files outside the test, and they
clean up after themselves automatically.
"""

import pytest

from errors import SemanticError
from semantic import NUMBER, TEXT, SymbolTable, analyze_source, infer_column_types

STUDENTS_CSV = (
    "name,age,city,marks\n"
    "Aarav,20,Hyderabad,78\n"
    "Diya,21,Chennai,55.5\n"
    "Rohan,,Bengaluru,91\n"     # missing age: must not break type inference
)


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Create data.csv in a temp folder and make that the current directory."""
    (tmp_path / "data.csv").write_text(STUDENTS_CSV, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def program(*lines):
    """Helper: build a program that starts by loading data.csv."""
    return "\n".join(['load "data.csv"', *lines])


def assert_semantic_error(source, message_part, line=None):
    """Helper: analysing `source` must fail with a message containing `message_part`."""
    with pytest.raises(SemanticError) as error_info:
        analyze_source(source)
    assert message_part in error_info.value.message
    if line is not None:
        assert error_info.value.line == line


# ---------------------------------------------------------------------------
# Type inference and the symbol table
# ---------------------------------------------------------------------------

def test_infer_column_types(workdir):
    assert infer_column_types("data.csv") == {
        "name": TEXT, "age": NUMBER, "city": TEXT, "marks": NUMBER
    }


def test_empty_column_is_text(workdir):
    (workdir / "blank.csv").write_text("a,b\n1,\n2,\n", encoding="utf-8")
    assert infer_column_types("blank.csv") == {"a": NUMBER, "b": TEXT}


def test_symbol_table_keep_only_reorders_and_is_new_object():
    table = SymbolTable({"a": NUMBER, "b": TEXT, "c": NUMBER})
    smaller = table.keep_only(["c", "a"])
    assert smaller.names() == ["c", "a"]
    assert table.names() == ["a", "b", "c"]  # original unchanged


# ---------------------------------------------------------------------------
# Valid programs
# ---------------------------------------------------------------------------

def test_valid_full_program(workdir):
    source = program(
        "filter marks > 60",
        'filter city != "Chennai"',
        "select name, marks",
        "sort marks desc",
        "show",
        "print avg(marks)",
        "print count(name)",
        "print max(name)",
        "plot bar name marks",
    )
    _, warnings = analyze_source(source)
    assert warnings == []


def test_number_filter_accepts_float(workdir):
    analyze_source(program("filter marks >= 55.5", "show"))


def test_second_load_resets_columns(workdir):
    (workdir / "other.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    source = program("select name", 'load "other.csv"', "print sum(x)")
    analyze_source(source)  # 'x' exists after the second load


def test_warning_when_no_output(workdir):
    _, warnings = analyze_source(program("filter marks > 60"))
    assert len(warnings) == 1
    assert "no show, print or plot" in warnings[0]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

def test_command_before_load(workdir):
    assert_semantic_error("show", "No data loaded", line=1)


def test_file_not_found(workdir):
    assert_semantic_error('load "missing.csv"', "File not found")


def test_only_csv_files(workdir):
    assert_semantic_error('load "data.txt"', "only supports .csv")


def test_empty_csv(workdir):
    (workdir / "empty.csv").write_text("", encoding="utf-8")
    assert_semantic_error('load "empty.csv"', "empty")


def test_duplicate_headers(workdir):
    (workdir / "dup.csv").write_text("a,a\n1,2\n", encoding="utf-8")
    assert_semantic_error('load "dup.csv"', "duplicate column")


def test_unknown_column_with_suggestion(workdir):
    assert_semantic_error(program("filter mark > 60"), "Did you mean 'marks'?", line=2)


def test_unknown_column_lists_available(workdir):
    assert_semantic_error(program("sort salary"), "Available columns: name, age, city, marks")


def test_number_column_compared_with_text(workdir):
    assert_semantic_error(program('filter marks > "high"'), "holds numbers")


def test_text_column_compared_with_number(workdir):
    assert_semantic_error(program("filter city == 5"), "holds text")


def test_text_column_with_greater_than(workdir):
    assert_semantic_error(program('filter city > "A"'), "only be compared with == or !=")


def test_column_removed_by_select(workdir):
    """After 'select name, marks', the 'city' column no longer exists."""
    assert_semantic_error(program("select name, marks", "sort city"), "Unknown column 'city'", line=3)


def test_select_duplicate_column(workdir):
    assert_semantic_error(program("select name, name"), "listed twice")


@pytest.mark.parametrize("function", ["sum", "avg"])
def test_numeric_aggregate_on_text(workdir, function):
    assert_semantic_error(program(f"print {function}(city)"), "of text column 'city'")


def test_unknown_plot_kind(workdir):
    assert_semantic_error(program("plot pie name marks"), "Unknown chart type 'pie'")


def test_plot_y_must_be_number(workdir):
    assert_semantic_error(program("plot bar marks name"), "must hold numbers")


def test_scatter_x_must_be_number(workdir):
    assert_semantic_error(program("plot scatter name marks"), "numbers on both axes")
