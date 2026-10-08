"""
test_main.py
------------
End-to-end (integration) tests for the compiler driver, main.py.

Run from the project root with:
    pytest -v

Unit tests (test_lexer.py etc.) check one phase at a time. These tests
check that ALL phases work together, exactly as a user runs the compiler.

We call main([...]) with an argument list instead of starting a new
process, and use pytest's `capfd` fixture to capture everything printed -
including output from the generated script, which runs as a child process.
"""

import pytest

from main import main

DATA_CSV = "name,marks\nAarav,78\nDiya,55\nRohan,91\n"


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Temp folder with data.csv, set as the current directory.

    MPLBACKEND=Agg stops any chart from opening a window during tests;
    child processes inherit this environment variable.
    """
    (tmp_path / "data.csv").write_text(DATA_CSV, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MPLBACKEND", "Agg")
    return tmp_path


def write_program(folder, text, name="prog.dsl"):
    """Helper: save a .dsl file and return its path as a string."""
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return str(path)


VALID_PROGRAM = 'load "data.csv"\nfilter marks > 60\nsort marks desc\nshow\nprint avg(marks)\n'


def test_compile_and_run(workdir, capfd):
    exit_code = main([write_program(workdir, VALID_PROGRAM)])
    output = capfd.readouterr().out
    assert exit_code == 0
    assert "Compiled successfully" in output
    assert "avg(marks) = 84.5" in output          # (78 + 91) / 2
    assert output.index("Rohan") < output.index("Aarav")  # sorted descending
    assert (workdir / "output" / "prog.py").exists()


def test_no_run_only_compiles(workdir, capfd):
    exit_code = main([write_program(workdir, VALID_PROGRAM), "--no-run"])
    output = capfd.readouterr().out
    assert exit_code == 0
    assert "Not running (--no-run)" in output
    assert "avg(marks) =" not in output           # script was not executed
    assert (workdir / "output" / "prog.py").exists()


def test_custom_output_dir(workdir, capfd):
    main([write_program(workdir, VALID_PROGRAM), "--no-run", "-o", "build"])
    assert (workdir / "build" / "prog.py").exists()


def test_all_flag_prints_every_phase(workdir, capfd):
    main([write_program(workdir, VALID_PROGRAM), "--all", "--no-run"])
    output = capfd.readouterr().out
    assert "Phase 1: Tokens" in output and "[FILTER]" in output
    assert "Phase 2: Abstract Syntax Tree" in output and "Filter(marks > 60)" in output
    assert "Phase 3: Symbol table" in output and "marks: number" in output
    assert "Phase 5: Generated Python code" in output and "pd.read_csv" in output


def test_individual_flag_prints_only_that_phase(workdir, capfd):
    main([write_program(workdir, VALID_PROGRAM), "--tokens", "--no-run"])
    output = capfd.readouterr().out
    assert "Phase 1: Tokens" in output
    assert "Phase 2" not in output


@pytest.mark.parametrize(
    "program_text, expected",
    [
        ("filter marks @ 60\n", "Lexer error at line 1"),
        ('load "data.csv"\nfilter > 60\n', "Syntax error at line 2"),
        ('load "data.csv"\nprint avg(mark)\n', "Semantic error at line 2"),
    ],
)
def test_each_phase_error_returns_1(workdir, capfd, program_text, expected):
    exit_code = main([write_program(workdir, program_text)])
    output = capfd.readouterr().out
    assert exit_code == 1
    assert expected in output
    assert "Compiled successfully" not in output
    assert not (workdir / "output" / "prog.py").exists()  # nothing written on error


def test_warning_is_printed_but_still_compiles(workdir, capfd):
    exit_code = main([write_program(workdir, 'load "data.csv"\nfilter marks > 60\n'), "--no-run"])
    output = capfd.readouterr().out
    assert exit_code == 0
    assert "Warning:" in output


def test_missing_source_file(workdir, capfd):
    assert main(["does_not_exist.dsl"]) == 1
    assert "file not found" in capfd.readouterr().out


def test_runtime_failure_returns_script_exit_code(workdir, capfd):
    """If the CSV is deleted between compiling and running, the script fails
    at runtime; main must report that instead of pretending all is well."""
    path = write_program(workdir, VALID_PROGRAM)
    main([path, "--no-run"])
    (workdir / "data.csv").unlink()
    from main import CompilerDriver
    exit_code = CompilerDriver.run("output/prog.py")
    assert exit_code != 0


def test_plot_program_end_to_end(workdir, capfd):
    program = 'load "data.csv"\nplot bar name marks\n'
    assert main([write_program(workdir, program)]) == 0
    assert (workdir / "output" / "prog_plot_line2.png").exists()
