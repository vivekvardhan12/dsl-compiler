"""
parser.py
---------
PHASE 2 of the compiler: Syntax Analysis (Parsing).

The parser takes the token list from the lexer and checks that the tokens
appear in an order allowed by the GRAMMAR. If they do, it builds the AST.
If they don't, it raises a ParseError pointing at the bad token.

    tokens: [FILTER] [IDENT:marks] [GT] [NUMBER:60] [NEWLINE]
    AST:    FilterNode(column="marks", operator=">", value=60)

    tokens: [FILTER] [GT] [NUMBER:60] [NEWLINE]
    error:  Syntax error at line 1, column 8: Expected a column name
            after 'filter', but found '>'

---------------------------------------------------------------------------
THE GRAMMAR (written in EBNF - Extended Backus-Naur Form)
---------------------------------------------------------------------------
How to read it:
    UPPERCASE  = a token from the lexer
    lowercase  = another grammar rule
    |          = "or"
    ( ... )*   = repeat zero or more times
    [ ... ]    = optional

    program     ::= statement* EOF
    statement   ::= ( load | filter | select | sort | show | print | plot ) NEWLINE

    load        ::= LOAD STRING
    filter      ::= FILTER IDENT comparison value
    select      ::= SELECT IDENT ( COMMA IDENT )*
    sort        ::= SORT IDENT [ ASC | DESC ]
    show        ::= SHOW
    print       ::= PRINT aggregate LPAREN IDENT RPAREN
    plot        ::= PLOT IDENT IDENT IDENT

    comparison  ::= GT | LT | GE | LE | EQ | NE
    value       ::= NUMBER | STRING
    aggregate   ::= COUNT | SUM | AVG | MIN | MAX

---------------------------------------------------------------------------
THE TECHNIQUE: Recursive Descent Parsing
---------------------------------------------------------------------------
Each grammar rule becomes one method:  `filter` rule -> _parse_filter().
A method reads tokens left to right and calls `_expect(...)` for every
token the rule requires. That's it.

The first token of a statement decides which rule to use (FILTER ->
_parse_filter). Because one token of lookahead is always enough to choose,
our grammar is LL(1):
    L = reads input Left to right
    L = builds a Leftmost derivation (top-down)
    1 = needs 1 token of lookahead
This is the classic top-down parser from the Compiler Design syllabus.

Run this file directly to see the AST of any .dsl file:
    python src/parser.py examples/analysis.dsl
"""

import sys

from ast_nodes import (
    FilterNode,
    LoadNode,
    PlotNode,
    PrintNode,
    Program,
    SelectNode,
    ShowNode,
    SortNode,
    print_tree,
)
from errors import DSLError, ParseError
from lexer import Lexer
from tokens import Token, TokenType

# Token types that can appear as a comparison operator in 'filter'.
COMPARISON_TYPES = {
    TokenType.GT,
    TokenType.LT,
    TokenType.GE,
    TokenType.LE,
    TokenType.EQ,
    TokenType.NE,
}

# Token types that are aggregate functions in 'print'.
AGGREGATE_TYPES = {
    TokenType.COUNT,
    TokenType.SUM,
    TokenType.AVG,
    TokenType.MIN,
    TokenType.MAX,
}


def describe_token(token: Token) -> str:
    """Turn a token into words for error messages.

    We want "found '>'" or "found number 60", not "found TokenType.GT".
    """
    if token.type == TokenType.EOF:
        return "end of file"
    if token.type == TokenType.NEWLINE:
        return "end of line"
    if token.type == TokenType.IDENT:
        return f"name '{token.value}'"
    if token.type == TokenType.NUMBER:
        return f"number {token.value}"
    if token.type == TokenType.STRING:
        return f'text "{token.value}"'
    # Keywords and symbols: show the text the user wrote.
    return f"'{token.value}'"


class Parser:
    """Recursive descent parser: tokens in, AST out.

    Usage:
        tokens = Lexer(source).tokenize()
        program = Parser(tokens).parse()
    """

    def __init__(self, tokens: list):
        """Store the tokens and start at the first one.

        Args:
            tokens: the full list from Lexer.tokenize(), ending with EOF
        """
        self.tokens = tokens
        self.pos = 0  # index of the current token

    # ------------------------------------------------------------------
    # Helper methods - the parser's basic "moves"
    # ------------------------------------------------------------------

    def _current(self) -> Token:
        """Return the token we're looking at right now (the lookahead)."""
        return self.tokens[self.pos]

    def _advance(self) -> Token:
        """Consume the current token and move to the next one.

        We never move past EOF, so _current() is always safe to call.

        Returns:
            The token that was consumed.
        """
        token = self.tokens[self.pos]
        if token.type != TokenType.EOF:
            self.pos += 1
        return token

    def _check(self, *token_types) -> bool:
        """Return True if the current token is one of the given types."""
        return self._current().type in token_types

    def _expect(self, token_type: TokenType, what_we_wanted: str) -> Token:
        """Consume a token of the required type, or raise a ParseError.

        This is the heart of a recursive descent parser: each rule just
        lists what it expects, in order.

        Args:
            token_type:     the type the grammar requires here
            what_we_wanted: plain-English description for the error message,
                            e.g. "a column name after 'filter'"

        Returns:
            The consumed token (so the caller can read its value).
        """
        if self._check(token_type):
            return self._advance()
        self._error(f"Expected {what_we_wanted}, but found {describe_token(self._current())}")

    def _error(self, message: str):
        """Raise a ParseError located at the current token."""
        token = self._current()
        raise ParseError(message, token.line, token.column)

    # ------------------------------------------------------------------
    # Top-level rules
    # ------------------------------------------------------------------

    def parse(self) -> Program:
        """program ::= statement* EOF

        Parse the whole token list and return the root Program node.

        Raises:
            ParseError: at the first grammar mistake found.
        """
        program = Program()
        while not self._check(TokenType.EOF):
            statement = self._parse_statement()
            program.statements.append(statement)
        return program

    def _parse_statement(self):
        """statement ::= ( load | filter | ... ) NEWLINE

        Look at the first token (one token of lookahead) to decide which
        rule applies. Then make sure the line ends after the statement.
        """
        # A dispatch table: first token type -> method that parses that rule.
        # Cleaner than a long if/elif chain, and easy to extend (Open/Closed).
        rules = {
            TokenType.LOAD: self._parse_load,
            TokenType.FILTER: self._parse_filter,
            TokenType.SELECT: self._parse_select,
            TokenType.SORT: self._parse_sort,
            TokenType.SHOW: self._parse_show,
            TokenType.PRINT: self._parse_print,
            TokenType.PLOT: self._parse_plot,
        }

        parse_rule = rules.get(self._current().type)
        if parse_rule is None:
            self._error(
                "Expected a command (load, filter, select, sort, show, print, plot), "
                f"but found {describe_token(self._current())}"
            )

        node = parse_rule()

        # Every statement must end here. This catches extra junk such as
        # 'show marks' or 'sort marks desc asc'.
        self._expect(TokenType.NEWLINE, "end of line after the command")
        return node

    # ------------------------------------------------------------------
    # One method per statement rule
    # ------------------------------------------------------------------

    def _parse_load(self) -> LoadNode:
        """load ::= LOAD STRING"""
        keyword = self._advance()  # consume 'load'
        path = self._expect(TokenType.STRING, 'a file name in quotes after \'load\', like "data.csv"')
        return LoadNode(path=path.value, line=keyword.line, col=keyword.column)

    def _parse_filter(self) -> FilterNode:
        """filter ::= FILTER IDENT comparison value"""
        keyword = self._advance()  # consume 'filter'
        column = self._expect(TokenType.IDENT, "a column name after 'filter'")

        if not self._check(*COMPARISON_TYPES):
            self._error(
                f"Expected a comparison (>, <, >=, <=, ==, !=) after '{column.value}', "
                f"but found {describe_token(self._current())}"
            )
        operator = self._advance()

        if not self._check(TokenType.NUMBER, TokenType.STRING):
            self._error(
                f"Expected a number or quoted text after '{operator.value}', "
                f"but found {describe_token(self._current())}"
            )
        value = self._advance()

        return FilterNode(
            column=column.value,
            operator=operator.value,
            value=value.value,
            line=keyword.line,
            col=keyword.column,
        )

    def _parse_select(self) -> SelectNode:
        """select ::= SELECT IDENT ( COMMA IDENT )*"""
        keyword = self._advance()  # consume 'select'
        columns = [self._expect(TokenType.IDENT, "a column name after 'select'").value]

        # Keep reading ", column" pairs as long as we see a comma.
        while self._check(TokenType.COMMA):
            self._advance()  # consume ','
            columns.append(self._expect(TokenType.IDENT, "a column name after ','").value)

        return SelectNode(columns=columns, line=keyword.line, col=keyword.column)

    def _parse_sort(self) -> SortNode:
        """sort ::= SORT IDENT [ ASC | DESC ]"""
        keyword = self._advance()  # consume 'sort'
        column = self._expect(TokenType.IDENT, "a column name after 'sort'")

        ascending = True  # default direction when none is written
        if self._check(TokenType.ASC):
            self._advance()
        elif self._check(TokenType.DESC):
            self._advance()
            ascending = False

        return SortNode(column=column.value, ascending=ascending, line=keyword.line, col=keyword.column)

    def _parse_show(self) -> ShowNode:
        """show ::= SHOW"""
        keyword = self._advance()  # consume 'show'
        return ShowNode(line=keyword.line, col=keyword.column)

    def _parse_print(self) -> PrintNode:
        """print ::= PRINT aggregate LPAREN IDENT RPAREN"""
        keyword = self._advance()  # consume 'print'

        if not self._check(*AGGREGATE_TYPES):
            self._error(
                "Expected count, sum, avg, min or max after 'print', "
                f"but found {describe_token(self._current())}"
            )
        function = self._advance()

        self._expect(TokenType.LPAREN, f"'(' after '{function.value}'")
        column = self._expect(TokenType.IDENT, "a column name inside the brackets")
        self._expect(TokenType.RPAREN, "')' to close the bracket")

        return PrintNode(function=function.value, column=column.value, line=keyword.line, col=keyword.column)

    def _parse_plot(self) -> PlotNode:
        """plot ::= PLOT IDENT IDENT IDENT   (chart kind, x column, y column)"""
        keyword = self._advance()  # consume 'plot'
        kind = self._expect(TokenType.IDENT, "a chart type after 'plot' (bar, line or scatter)")
        x_column = self._expect(TokenType.IDENT, "the x-axis column name")
        y_column = self._expect(TokenType.IDENT, "the y-axis column name")
        return PlotNode(
            kind=kind.value,
            x_column=x_column.value,
            y_column=y_column.value,
            line=keyword.line,
            col=keyword.column,
        )


def parse_source(source_code: str) -> Program:
    """Convenience function: run Phase 1 + Phase 2 on raw text.

    Raises:
        LexerError or ParseError (both are DSLError subclasses).
    """
    tokens = Lexer(source_code).tokenize()
    return Parser(tokens).parse()


def main():
    """Command-line entry point: python src/parser.py <file.dsl>"""
    if len(sys.argv) != 2:
        print("Usage: python src/parser.py <file.dsl>")
        sys.exit(1)

    file_path = sys.argv[1]
    try:
        with open(file_path, encoding="utf-8") as file:
            source_code = file.read()
    except FileNotFoundError:
        print(f"Error: file not found: {file_path}")
        sys.exit(1)

    try:
        program = parse_source(source_code)
    except DSLError as error:
        # Catches both lexer and parser errors with one except.
        print(error.format(source_code))
        sys.exit(1)

    print_tree(program)
    print(f"\nParsed {len(program.statements)} statements successfully.")


if __name__ == "__main__":
    main()
