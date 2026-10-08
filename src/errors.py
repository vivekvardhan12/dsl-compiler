"""
errors.py
---------
Custom error types for every compiler phase.

Why custom errors instead of Python's built-in ones?
  - A Python traceback is scary and useless to someone writing DSL code.
  - Our errors carry the line and column of the problem, so we can print
    a friendly message with a caret (^) pointing at the exact spot:

        Lexer error at line 2, column 14: Unexpected character '@'
            filter marks @ 60
                         ^
"""


class DSLError(Exception):
    """Base class for all errors raised by our compiler.

    Every phase (lexer, parser, semantic checker...) gets its own subclass,
    so main.py can catch *any* compiler error with a single
    `except DSLError`.
    """

    # Subclasses override this so the message says which phase failed.
    phase = "Compiler"

    def __init__(self, message: str, line: int, column: int):
        """Store the error details.

        Args:
            message: human-readable description of what went wrong
            line:    1-based line number where the problem is
            column:  1-based column number where the problem is
        """
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column

    def format(self, source_code: str) -> str:
        """Build a friendly, multi-line error message.

        Args:
            source_code: the full DSL program text, so we can show the
                         offending line with a caret under the problem.

        Returns:
            A string like:
                Lexer error at line 2, column 14: Unexpected character '@'
                    filter marks @ 60
                                 ^
        """
        header = f"{self.phase} error at line {self.line}, column {self.column}: {self.message}"

        lines = source_code.splitlines()
        # Guard: the line number might be past the end (e.g. error at EOF).
        if 1 <= self.line <= len(lines):
            code_line = lines[self.line - 1]
            # Column is 1-based, so we put (column - 1) spaces before the caret.
            caret = " " * (self.column - 1) + "^"
            return f"{header}\n    {code_line}\n    {caret}"
        return header


class LexerError(DSLError):
    """Raised when the lexer finds text it cannot turn into a token."""

    phase = "Lexer"


class ParseError(DSLError):
    """Raised when the tokens don't follow the grammar rules.

    Example: 'filter > 60' - the parser expected a column name after
    'filter' but found '>'.
    """

    phase = "Syntax"
