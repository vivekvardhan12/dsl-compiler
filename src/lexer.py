"""
lexer.py
--------
PHASE 1 of the compiler: Lexical Analysis.

The lexer (also called a "scanner" or "tokenizer") reads the raw program
text one character at a time and groups characters into tokens.

    Input : 'filter marks > 60\n'
    Output: [FILTER] [IDENT:marks] [GT] [NUMBER:60] [NEWLINE] [EOF]

It does NOT check whether the tokens make sense together. For example,
"filter > > 60" lexes fine - spotting that mistake is the parser's job
(Step 2). The lexer only answers: "Is every piece of text a valid word?"

How it works (the core idea):
    We keep a pointer `pos` into the source string. In a loop we look at
    the current character and decide what kind of token *starts* there:
        letter        -> read a whole word   -> keyword or IDENT
        digit         -> read a whole number -> NUMBER
        "             -> read until next "   -> STRING
        > < = !       -> operator (maybe 2 chars, like >=)
        , ( )         -> punctuation
        #             -> comment, skip to end of line
        space/tab     -> skip
        newline       -> NEWLINE token
        anything else -> LexerError

Run this file directly to see the tokens of any .dsl file:
    python src/lexer.py examples/analysis.dsl
"""

import sys

from errors import LexerError
from tokens import KEYWORDS, Token, TokenType

# Single-character symbols that map directly to a token type.
SINGLE_CHAR_TOKENS = {
    ",": TokenType.COMMA,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
}


class Lexer:
    """Turns DSL source code into a list of Token objects.

    Usage:
        tokens = Lexer('filter marks > 60').tokenize()
    """

    def __init__(self, source_code: str):
        """Prepare to scan the given program text.

        Args:
            source_code: the full text of the DSL program
        """
        self.source = source_code
        self.pos = 0        # index of the current character in self.source
        self.line = 1       # current line number (1-based, for error messages)
        self.column = 1     # current column number (1-based)
        self.tokens = []    # tokens collected so far

    # ------------------------------------------------------------------
    # Small helper methods
    # ------------------------------------------------------------------

    def _current_char(self):
        """Return the character at the current position, or None at end of input."""
        if self.pos < len(self.source):
            return self.source[self.pos]
        return None

    def _peek_next_char(self):
        """Return the character AFTER the current one, without moving.

        Needed for two-character operators: when we see '>', we peek to
        check whether the next char is '=' (making '>=').
        """
        next_pos = self.pos + 1
        if next_pos < len(self.source):
            return self.source[next_pos]
        return None

    def _advance(self):
        """Move forward one character, keeping line/column numbers correct.

        Returns:
            The character we just moved past.
        """
        char = self.source[self.pos]
        self.pos += 1
        if char == "\n":
            # A newline means the next character is at the start of a new line.
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return char

    def _add_token(self, token_type, value, line, column):
        """Create a Token and append it to the result list."""
        self.tokens.append(Token(token_type, value, line, column))

    def _add_newline_token(self, line, column):
        """Add a NEWLINE token, but avoid useless duplicates.

        Blank lines and comment-only lines would otherwise produce several
        NEWLINE tokens in a row (or one at the very start). The parser only
        cares that a statement ended, so we keep at most one in a row.
        """
        if self.tokens and self.tokens[-1].type != TokenType.NEWLINE:
            self._add_token(TokenType.NEWLINE, "\\n", line, column)

    # ------------------------------------------------------------------
    # Readers for multi-character tokens
    # ------------------------------------------------------------------

    def _read_word(self):
        """Read a keyword or identifier, e.g. 'filter' or 'marks'.

        Rule: starts with a letter or '_', then letters, digits or '_'.
        Keywords are matched case-insensitively ('FILTER' == 'filter'),
        but column names keep their original spelling because CSV headers
        are case-sensitive ('Marks' != 'marks' in pandas).
        """
        start_line, start_column = self.line, self.column
        start_pos = self.pos

        while self._current_char() is not None and (
            self._current_char().isalnum() or self._current_char() == "_"
        ):
            self._advance()

        word = self.source[start_pos:self.pos]
        keyword_type = KEYWORDS.get(word.lower())

        if keyword_type is not None:
            self._add_token(keyword_type, word.lower(), start_line, start_column)
        else:
            self._add_token(TokenType.IDENT, word, start_line, start_column)

    def _read_number(self):
        """Read an integer or decimal number, e.g. 60 or 3.75.

        We store the value as int when there's no decimal point, otherwise
        float, so the generated code looks natural (60, not 60.0).
        """
        start_line, start_column = self.line, self.column
        start_pos = self.pos
        seen_dot = False

        while self._current_char() is not None:
            char = self._current_char()
            if char.isdigit():
                self._advance()
            elif char == "." and not seen_dot:
                # Only accept the dot if a digit follows it ("3." is not a number).
                next_char = self._peek_next_char()
                if next_char is None or not next_char.isdigit():
                    break
                seen_dot = True
                self._advance()
            else:
                break

        text = self.source[start_pos:self.pos]
        value = float(text) if seen_dot else int(text)
        self._add_token(TokenType.NUMBER, value, start_line, start_column)

    def _read_string(self):
        """Read a double-quoted string, e.g. "students.csv" or "Hyderabad".

        The quotes themselves are not part of the token's value.
        A string must close on the same line; otherwise it's an error,
        because a missing quote is a very common typo and we want to
        report it at the place it started.
        """
        start_line, start_column = self.line, self.column
        self._advance()  # skip the opening quote
        start_pos = self.pos

        while True:
            char = self._current_char()
            if char is None or char == "\n":
                raise LexerError(
                    "Unterminated string - missing closing quote (\")",
                    start_line,
                    start_column,
                )
            if char == '"':
                break
            self._advance()

        value = self.source[start_pos:self.pos]
        self._advance()  # skip the closing quote
        self._add_token(TokenType.STRING, value, start_line, start_column)

    def _read_operator(self):
        """Read a comparison operator: > >= < <= == !=

        We try the 2-character version first. This is called "maximal munch":
        always take the longest valid token, so '>=' is one token, not '>'
        followed by '='.
        """
        start_line, start_column = self.line, self.column
        char = self._current_char()
        next_char = self._peek_next_char()

        two_char = char + (next_char or "")
        two_char_ops = {
            ">=": TokenType.GE,
            "<=": TokenType.LE,
            "==": TokenType.EQ,
            "!=": TokenType.NE,
        }
        if two_char in two_char_ops:
            self._advance()
            self._advance()
            self._add_token(two_char_ops[two_char], two_char, start_line, start_column)
            return

        if char == ">":
            self._advance()
            self._add_token(TokenType.GT, ">", start_line, start_column)
        elif char == "<":
            self._advance()
            self._add_token(TokenType.LT, "<", start_line, start_column)
        elif char == "=":
            # A lone '=' is a classic mistake; give a helpful hint.
            raise LexerError("Single '=' is not allowed. Did you mean '=='?", start_line, start_column)
        else:  # char == "!"
            raise LexerError("Single '!' is not allowed. Did you mean '!='?", start_line, start_column)

    def _skip_comment(self):
        """Skip everything from '#' up to (but not including) the newline."""
        while self._current_char() is not None and self._current_char() != "\n":
            self._advance()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def tokenize(self):
        """Scan the whole program and return the list of tokens.

        The list always ends with NEWLINE (if there was any statement)
        followed by EOF, which makes the parser simpler: every statement
        is guaranteed to end with NEWLINE.

        Raises:
            LexerError: if an invalid character or unterminated string is found.
        """
        while self._current_char() is not None:
            char = self._current_char()

            if char in " \t\r":
                # Whitespace separates tokens but is not a token itself.
                # (\r appears in Windows line endings "\r\n".)
                self._advance()
            elif char == "\n":
                line, column = self.line, self.column
                self._advance()
                self._add_newline_token(line, column)
            elif char == "#":
                self._skip_comment()
            elif char.isalpha() or char == "_":
                self._read_word()
            elif char.isdigit():
                self._read_number()
            elif char == '"':
                self._read_string()
            elif char in "><=!":
                self._read_operator()
            elif char in SINGLE_CHAR_TOKENS:
                line, column = self.line, self.column
                self._advance()
                self._add_token(SINGLE_CHAR_TOKENS[char], char, line, column)
            else:
                raise LexerError(f"Unexpected character '{char}'", self.line, self.column)

        # Make sure the last statement ends with NEWLINE even if the file
        # doesn't end with an empty line.
        self._add_newline_token(self.line, self.column)
        self._add_token(TokenType.EOF, None, self.line, self.column)
        return self.tokens


def print_tokens(tokens):
    """Print tokens grouped by source line, which is easy to read.

    Example output:
        line 1: [LOAD] [STRING:students.csv] [NEWLINE]
        line 2: [FILTER] [IDENT:marks] [GT] [NUMBER:60] [NEWLINE]
    """
    current_line = None
    parts = []
    for token in tokens:
        if token.line != current_line and parts:
            print(f"line {current_line}: {' '.join(parts)}")
            parts = []
        current_line = token.line
        parts.append(str(token))
    if parts:
        print(f"line {current_line}: {' '.join(parts)}")


def main():
    """Command-line entry point: python src/lexer.py <file.dsl>"""
    if len(sys.argv) != 2:
        print("Usage: python src/lexer.py <file.dsl>")
        sys.exit(1)

    file_path = sys.argv[1]
    try:
        with open(file_path, encoding="utf-8") as file:
            source_code = file.read()
    except FileNotFoundError:
        print(f"Error: file not found: {file_path}")
        sys.exit(1)

    try:
        tokens = Lexer(source_code).tokenize()
    except LexerError as error:
        print(error.format(source_code))
        sys.exit(1)

    print_tokens(tokens)
    print(f"\nTotal tokens: {len(tokens)}")


# This block runs only when the file is executed directly,
# not when another file does `from lexer import Lexer`.
if __name__ == "__main__":
    main()
