"""Token definitions for the Python compiler."""

from enum import Enum, auto


class TokenType(Enum):
    # Literals
    INTEGER = auto()
    FLOAT = auto()
    STRING = auto()
    IDENTIFIER = auto()

    # Keywords
    KEYWORD = auto()

    # Operators
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    DOUBLE_SLASH = auto()
    PERCENT = auto()
    DOUBLE_STAR = auto()

    # Comparison
    EQ = auto()
    NEQ = auto()
    LT = auto()
    GT = auto()
    LE = auto()
    GE = auto()

    # Assignment
    ASSIGN = auto()
    PLUS_ASSIGN = auto()
    MINUS_ASSIGN = auto()
    STAR_ASSIGN = auto()
    SLASH_ASSIGN = auto()

    # Logical
    AND = auto()
    OR = auto()
    NOT = auto()

    # Punctuation
    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    LBRACE = auto()
    RBRACE = auto()
    COLON = auto()
    COMMA = auto()
    DOT = auto()
    AT = auto()
    SEMI = auto()

    # Structure
    NEWLINE = auto()
    INDENT = auto()
    DEDENT = auto()
    EOF = auto()


KEYWORDS = {
    "if", "elif", "else", "while", "for", "in", "def", "return",
    "break", "continue", "pass", "True", "False", "None",
    "and", "or", "not", "import", "from", "as", "global", "nonlocal",
    "class", "is", "lambda", "try", "except", "finally", "raise",
    "with", "yield", "del", "assert",
}


class Token:
    __slots__ = ("type", "value", "line", "col")

    def __init__(self, type_, value, line, col):
        self.type = type_
        self.value = value
        self.line = line
        self.col = col

    def __repr__(self):
        return f"Token({self.type.name}, {self.value!r}, line={self.line})"
