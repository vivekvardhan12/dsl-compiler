"""
main.py
-------
The COMPILER DRIVER: one command that runs every phase in order.

    python src/main.py examples/analysis.dsl

    analysis.dsl --> [1 Lexer] --> tokens
                 --> [2 Parser] --> AST
                 --> [3 Semantic analysis] --> checked AST + warnings
                 --> [4 Optimizer]  (added in Step 6)
                 --> [5 Code generator] --> output/analysis.py
                 --> run output/analysis.py with Python

Real compilers have a driver too: when you type `gcc hello.c`, the `gcc`
program itself doesn't do the work - it calls the preprocessor, compiler,
assembler and linker one after another. This file plays that role.

Options (great for showing each phase during a demo or viva):
    --tokens     print the token list            (Phase 1 output)
    --ast        print the syntax tree           (Phase 2 output)
    --symbols    print the symbol table per line (Phase 3 output)
    --code       print the generated Python      (Phase 5 output)
    --all        all four of the above
    --no-run     only compile; don't run the generated script
    -o DIR       folder for generated files (default: output)

Exit codes (useful for scripts and CI):
    0  success
    1  compile error, or the input file could not be read
    2  wrong command-line arguments (argparse's standard code)
    other  the generated script's own exit code, if it failed while running
"""

import argparse
import os
import subprocess
import sys
import time

from ast_nodes import print_tree
from codegen import CodeGenerator
from errors import DSLError
from lexer import Lexer, print_tokens
from parser import Parser
from semantic import SemanticAnalyzer


def build_argument_parser() -> argparse.ArgumentParser:
    """Describe the command-line options.

    argparse (standard library) reads sys.argv, validates it, and creates
    the --help text for free.
    """
    arg_parser = argparse.ArgumentParser(
        prog="python src/main.py",
        description="Data Analysis DSL Compiler - compiles .dsl files to Python/pandas and runs them.",
    )
    arg_parser.add_argument("source", help="path to the .dsl program, e.g. examples/analysis.dsl")
    arg_parser.add_argument("--tokens", action="store_true", help="print the tokens (lexer output)")
    arg_parser.add_argument("--ast", action="store_true", help="print the syntax tree (parser output)")
    arg_parser.add_argument("--symbols", action="store_true", help="print the symbol table after each statement")
    arg_parser.add_argument("--code", action="store_true", help="print the generated Python code")
    arg_parser.add_argument("--all", action="store_true", help="same as --tokens --ast --symbols --code")
    arg_parser.add_argument("--no-run", action="store_true", help="compile only; do not run the generated script")
    arg_parser.add_argument("-o", "--output-dir", default="output", help="folder for generated files (default: output)")
    return arg_parser


def print_heading(title: str) -> None:
    """Print a section heading like  ==== Phase 1: Tokens ====  ."""
    print(f"\n==== {title} " + "=" * max(4, 60 - len(title)))


class CompilerDriver:
    """Runs the phases in order and reports what happened.

    Kept as a class so each phase is a small method, and the options
    (which outputs to show) are stored once instead of passed everywhere.
    """

    def __init__(self, options: argparse.Namespace):
        """Args:
            options: parsed command-line options from build_argument_parser()
        """
        self.options = options
        show_all = options.all
        self.show_tokens = options.tokens or show_all
        self.show_ast = options.ast or show_all
        self.show_symbols = options.symbols or show_all
        self.show_code = options.code or show_all
        self.timings = []  # (phase name, milliseconds) for the summary

    def _timed(self, phase_name: str, function, *args):
        """Call function(*args), record how long it took, return its result.

        time.perf_counter() is the most precise clock Python offers for
        measuring short durations.
        """
        start = time.perf_counter()
        result = function(*args)
        elapsed_ms = (time.perf_counter() - start) * 1000
        self.timings.append((phase_name, elapsed_ms))
        return result

    def compile(self, source_code: str, source_path: str) -> str:
        """Run Phases 1-5 and return the path of the generated .py file.

        Raises:
            DSLError: from whichever phase finds a problem first.
        """
        # ---- Phase 1: Lexical analysis --------------------------------
        tokens = self._timed("Lexer", Lexer(source_code).tokenize)
        if self.show_tokens:
            print_heading("Phase 1: Tokens")
            print_tokens(tokens)

        # ---- Phase 2: Syntax analysis ---------------------------------
        program = self._timed("Parser", Parser(tokens).parse)
        if self.show_ast:
            print_heading("Phase 2: Abstract Syntax Tree")
            print_tree(program)

        # ---- Phase 3: Semantic analysis -------------------------------
        if self.show_symbols:
            print_heading("Phase 3: Symbol table after each statement")
        analyzer = SemanticAnalyzer(verbose=self.show_symbols)
        warnings = self._timed("Semantic", analyzer.analyze, program)
        for warning in warnings:
            print(f"Warning: {warning}")

        # ---- Phase 4: Optimization ------------------------------------
        # (Added in Step 6.)

        # ---- Phase 5: Code generation ---------------------------------
        generator = CodeGenerator(source_code, source_path, self.options.output_dir)
        python_code = self._timed("Codegen", generator.generate, program)
        if self.show_code:
            print_heading("Phase 5: Generated Python code")
            print(python_code.rstrip())

        output_path = self._write_output(python_code, source_path)

        total_ms = sum(ms for _, ms in self.timings)
        phase_summary = ", ".join(f"{name} {ms:.1f}ms" for name, ms in self.timings)
        print_heading("Compiled successfully")
        print(f"{len(tokens)} tokens, {len(program.statements)} statements -> {output_path}")
        print(f"Time: {total_ms:.1f} ms ({phase_summary})")
        return output_path

    def _write_output(self, python_code: str, source_path: str) -> str:
        """Save the generated code as <output_dir>/<source name>.py."""
        os.makedirs(self.options.output_dir, exist_ok=True)
        base_name = os.path.splitext(os.path.basename(source_path))[0]
        output_path = os.path.join(self.options.output_dir, base_name + ".py")
        with open(output_path, "w", encoding="utf-8") as file:
            file.write(python_code)
        return output_path

    @staticmethod
    def run(output_path: str) -> int:
        """Run the generated script with the SAME Python interpreter we're using.

        sys.executable is the full path of the current Python (your conda
        'dslc' env), so the script finds pandas exactly as the compiler did.
        We pass a list of arguments (not one string) and no shell, so file
        names with spaces or special characters can't be misread as commands.

        Returns:
            The script's exit code (0 means it ran without errors).
        """
        print_heading(f"Running {output_path}")
        sys.stdout.flush()  # make sure our output appears before the child's
        completed = subprocess.run([sys.executable, output_path], check=False)
        return completed.returncode


def main(argv=None) -> int:
    """Program entry point. Returns the process exit code.

    Args:
        argv: list of arguments (without the program name). None means
              "use the real command line" - tests pass their own list.
    """
    # Windows consoles sometimes can't print characters like the tree
    # branches. Replace anything unprintable instead of crashing.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    options = build_argument_parser().parse_args(argv)

    try:
        with open(options.source, encoding="utf-8") as file:
            source_code = file.read()
    except FileNotFoundError:
        print(f"Error: file not found: {options.source}")
        return 1
    except (OSError, UnicodeDecodeError) as problem:
        print(f"Error: cannot read {options.source}: {problem}")
        return 1

    driver = CompilerDriver(options)
    try:
        output_path = driver.compile(source_code, options.source)
    except DSLError as error:
        # One except clause handles Lexer, Syntax and Semantic errors alike.
        print()
        print(error.format(source_code))
        return 1

    if options.no_run:
        print(f"\nNot running (--no-run). Run it later with: python {output_path}")
        return 0

    return_code = driver.run(output_path)
    if return_code != 0:
        print(f"\nThe generated script stopped with exit code {return_code}.")
    return return_code


if __name__ == "__main__":
    sys.exit(main())
