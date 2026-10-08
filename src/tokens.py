"""
tokens.py
---------
Defines the vocabulary of our Data Analysis DSL.

A "token" is the smallest meaningful piece of a program, like a word in a
sentence. The lexer (lexer.py) reads raw text and produces a list of these.

Example:
    filter marks > 60
becomes
    [FILTER] [IDENT:marks] [GT] [NUMBER:60]
"""

from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    """Every kind of token our language understands.

    auto() just gives each member a unique number; we never use the numbers,
    only the names.
    """

    # ---- Keywords: commands --------------------------------------------
    LOAD = auto()     # load "file.csv"
    FILTER = auto()   # filter marks > 60
    SELECT = auto()   # select name, marks
    SORT = auto()     # sort marks desc
    SHOW = auto()     # show
    PRINT = auto()    # print avg(marks)
    PLOT = auto()     # plot bar name marks   (optional feature)

    # ---- Keywords: sort direction --------------------------------------
    ASC = auto()
    DESC = auto()

    # ---- Keywords: aggregate functions ---------------------------------
    COUNT = auto()
    SUM = auto()
    AVG = auto()
    MIN = auto()
    MAX = auto()

    # ---- Literals and names --------------------------------------------
    IDENT = auto()    # a column name, e.g. marks, city
    NUMBER = auto()   # 60, 3.5
    STRING = auto()   # "students.csv"

    # ---- Comparison operators ------------------------------------------
    GT = auto()       # >
    LT = auto()       # <
    GE = auto()       # >=
    LE = auto()       # <=
    EQ = auto()       # ==
    NE = auto()       # !=

    # ---- Punctuation ---------------------------------------------------
    COMMA = auto()    # ,
    LPAREN = auto()   # (
    RPAREN = auto()   # )

    # ---- Structure -----------------------------------------------------
    NEWLINE = auto()  # end of a statement
    EOF = auto()      # end of the whole file


# Maps the text of each keyword to its token type.
# The lexer reads a word, then looks it up here: if found, it's a keyword;
# if not, it's an identifier (a column name).
KEYWORDS = {
    "load": TokenType.LOAD,
    "filter": TokenType.FILTER,
    "select": TokenType.SELECT,
    "sort": TokenType.SORT,
    "show": TokenType.SHOW,
    "print": TokenType.PRINT,
    "plot": TokenType.PLOT,
    "asc": TokenType.ASC,
    "desc": TokenType.DESC,
    "count": TokenType.COUNT,
    "sum": TokenType.SUM,
    "avg": TokenType.AVG,
    "min": TokenType.MIN,
    "max": TokenType.MAX,
}


@dataclass
class Token:
    """One token produced by the lexer.

    Attributes:
        type:   what kind of token it is (a TokenType member)
        value:  the actual data - e.g. 60 for a NUMBER, "marks" for an IDENT.
                For keywords and symbols it's just the matched text.
        line:   line number in the source file (starts at 1)
        column: column number in that line (starts at 1)

    line/column let us print helpful errors like "line 3, column 8".
    """

    type: TokenType
    value: object
    line: int
    column: int

    def __str__(self) -> str:
        """Short, readable form used when printing the token list."""
        # Keywords/symbols: just show the type, e.g. [FILTER]
        # Data-carrying tokens: show type and value, e.g. [NUMBER:60]
        if self.type in (TokenType.IDENT, TokenType.NUMBER, TokenType.STRING):
            return f"[{self.type.name}:{self.value}]"
        return f"[{self.type.name}]"
