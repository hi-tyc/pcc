"""
Lexer module for pcc - Version 2.

This module provides a robust tokenizer using Python's standard library `tokenize` module.
It converts Python source code into a stream of tokens for the parser.
"""

import tokenize
import io
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Iterator, Optional, Tuple


class TokenType(Enum):
    """Token types for the pcc language subset."""
    # Literals
    NUMBER = auto()      # Integer literal
    STRING = auto()      # String literal
    
    # Identifiers and keywords
    NAME = auto()        # Identifier or keyword
    
    # Operators
    PLUS = auto()        # +
    MINUS = auto()       # -
    STAR = auto()        # *
    SLASH = auto()       # /
    PERCENT = auto()     # %
    DOUBLESLASH = auto() # //
    
    # Comparison operators
    LESS = auto()        # <
    GREATER = auto()     # >
    LESSEQUAL = auto()   # <=
    GREATEREQUAL = auto()# >=
    EQEQUAL = auto()     # ==
    NOTEQUAL = auto()    # !=
    
    # Assignment
    EQUAL = auto()       # =
    
    # Delimiters
    LPAR = auto()        # (
    RPAR = auto()        # )
    LBRACE = auto()      # {
    RBRACE = auto()      # }
    LBRACKET = auto()    # [
    RBRACKET = auto()    # ]
    COLON = auto()       # :
    COMMA = auto()       # ,
    DOT = auto()         # .
    NEWLINE = auto()     # End of line
    INDENT = auto()      # Indentation increase
    DEDENT = auto()      # Indentation decrease
    
    # Special
    ENDMARKER = auto()   # End of file
    COMMENT = auto()     # # comment
    NL = auto()          # Non-significant newline (inside brackets)
    ENCODING = auto()    # File encoding
    
    # Keywords (handled as NAME with keyword check)
    # def, class, if, else, elif, while, for, in, return, pass, break, continue, print


@dataclass(frozen=True)
class Token:
    """Represents a token in the source code.
    
    Attributes:
        type: The token type
        value: The string value of the token
        lineno: Line number (1-indexed)
        col_offset: Column offset (0-indexed)
        line: The entire line containing the token
    """
    type: TokenType
    value: str
    lineno: int
    col_offset: int
    line: str
    
    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, line={self.lineno})"


class LexerError(Exception):
    """Exception raised for lexer errors."""
    
    def __init__(self, message: str, lineno: int = 0, col_offset: int = 0, line: str = ""):
        self.message = message
        self.lineno = lineno
        self.col_offset = col_offset
        self.line = line
        super().__init__(self._format_message())
    
    def _format_message(self) -> str:
        if self.lineno > 0:
            return f"Line {self.lineno}, col {self.col_offset}: {self.message}"
        return self.message


class Lexer:
    """Lexer for tokenizing Python source code.
    
    Uses Python's standard library `tokenize` module for robust tokenization.
    Converts Python source code into a stream of Token objects.
    
    Example:
        >>> lexer = Lexer()
        >>> tokens = lexer.tokenize("x = 42")
        >>> for token in tokens:
        ...     print(token)
    """
    
    # Mapping from tokenize module types to our TokenType
    _TOKEN_TYPE_MAP = {
        tokenize.NUMBER: TokenType.NUMBER,
        tokenize.STRING: TokenType.STRING,
        tokenize.NAME: TokenType.NAME,
        tokenize.OP: None,  # Handled separately
        tokenize.NEWLINE: TokenType.NEWLINE,
        tokenize.NL: TokenType.NL,
        tokenize.COMMENT: TokenType.COMMENT,
        tokenize.ENCODING: TokenType.ENCODING,
        tokenize.ENDMARKER: TokenType.ENDMARKER,
        tokenize.INDENT: TokenType.INDENT,
        tokenize.DEDENT: TokenType.DEDENT,
        tokenize.ERRORTOKEN: None,  # Handled separately
    }
    
    # Operator mapping
    _OP_MAP = {
        '+': TokenType.PLUS,
        '-': TokenType.MINUS,
        '*': TokenType.STAR,
        '/': TokenType.SLASH,
        '%': TokenType.PERCENT,
        '//': TokenType.DOUBLESLASH,
        '<': TokenType.LESS,
        '>': TokenType.GREATER,
        '<=': TokenType.LESSEQUAL,
        '>=': TokenType.GREATEREQUAL,
        '==': TokenType.EQEQUAL,
        '!=': TokenType.NOTEQUAL,
        '=': TokenType.EQUAL,
        '(': TokenType.LPAR,
        ')': TokenType.RPAR,
        '{': TokenType.LBRACE,
        '}': TokenType.RBRACE,
        '[': TokenType.LBRACKET,
        ']': TokenType.RBRACKET,
        ':': TokenType.COLON,
        ',': TokenType.COMMA,
        '.': TokenType.DOT,
    }
    
    # Python keywords that are valid in pcc
    _KEYWORDS = {
        'def', 'class', 'if', 'else', 'elif', 'while', 'for', 'in',
        'return', 'pass', 'break', 'continue', 'print', 'range',
        'True', 'False', 'None', 'and', 'or', 'not', 'is',
    }
    
    # Boolean literals
    _BOOLEAN_LITERALS = {'True', 'False'}
    
    def __init__(self):
        """Initialize the lexer."""
        self._filename: str = "<input>"
    
    def tokenize(self, source: str, filename: str = "<input>") -> List[Token]:
        """Tokenize Python source code.
        
        Args:
            source: Python source code string
            filename: Source filename for error reporting
            
        Returns:
            List of Token objects
            
        Raises:
            LexerError: If tokenization fails
        """
        self._filename = filename
        
        try:
            # Use StringIO for string-based tokenization
            readline = io.StringIO(source).readline
            
            tokens = []
            for tok_type, tok_value, (lineno, col_offset), _, line in tokenize.generate_tokens(readline):
                token = self._convert_token(tok_type, tok_value, lineno, col_offset, line)
                if token is not None:
                    tokens.append(token)
            
            return tokens
            
        except tokenize.TokenError as e:
            # Extract line number from error message if available
            msg = str(e)
            lineno = 0
            if '(' in msg and ')' in msg:
                try:
                    lineno_str = msg.split('(')[1].split(',')[0]
                    lineno = int(lineno_str)
                except (ValueError, IndexError):
                    pass
            raise LexerError(f"Tokenization error: {msg}", lineno, 0, "")
        except SyntaxError as e:
            raise LexerError(f"Syntax error: {e}", e.lineno or 0, e.offset or 0, e.text or "")
    
    def tokenize_iter(self, source: str, filename: str = "<input>") -> Iterator[Token]:
        """Tokenize Python source code lazily.
        
        Args:
            source: Python source code string
            filename: Source filename for error reporting
            
        Yields:
            Token objects one at a time
            
        Raises:
            LexerError: If tokenization fails
        """
        self._filename = filename
        
        try:
            readline = io.StringIO(source).readline
            
            for tok_type, tok_value, (lineno, col_offset), _, line in tokenize.generate_tokens(readline):
                token = self._convert_token(tok_type, tok_value, lineno, col_offset, line)
                if token is not None:
                    yield token
                    
        except tokenize.TokenError as e:
            raise LexerError(f"Tokenization error: {e}")
        except SyntaxError as e:
            raise LexerError(f"Syntax error: {e}", e.lineno or 0, e.offset or 0, e.text or "")
    
    def _convert_token(self, tok_type: int, tok_value: str, lineno: int, 
                       col_offset: int, line: str) -> Optional[Token]:
        """Convert a tokenize module token to our Token format.
        
        Args:
            tok_type: Token type from tokenize module
            tok_value: Token string value
            lineno: Line number
            col_offset: Column offset
            line: Full line containing the token
            
        Returns:
            Token object or None if token should be skipped
        """
        # Handle ERRORTOKEN
        if tok_type == tokenize.ERRORTOKEN:
            if tok_value.strip():
                raise LexerError(f"Invalid character: {tok_value!r}", lineno, col_offset, line)
            return None
        
        # Handle operators
        if tok_type == tokenize.OP:
            if tok_value in self._OP_MAP:
                return Token(
                    type=self._OP_MAP[tok_value],
                    value=tok_value,
                    lineno=lineno,
                    col_offset=col_offset,
                    line=line
                )
            else:
                raise LexerError(f"Unsupported operator: {tok_value!r}", lineno, col_offset, line)
        
        # Handle other token types
        if tok_type in self._TOKEN_TYPE_MAP:
            our_type = self._TOKEN_TYPE_MAP[tok_type]
            if our_type is None:
                return None  # Skip this token type
            
            return Token(
                type=our_type,
                value=tok_value,
                lineno=lineno,
                col_offset=col_offset,
                line=line
            )
        
        # Unknown token type
        raise LexerError(f"Unknown token type: {tok_type}", lineno, col_offset, line)
    
    def is_keyword(self, name: str) -> bool:
        """Check if a name is a keyword.
        
        Args:
            name: Identifier to check
            
        Returns:
            True if name is a keyword
        """
        return name in self._KEYWORDS
    
    def get_keyword_tokens(self) -> List[str]:
        """Get list of valid keywords.
        
        Returns:
            List of keyword strings
        """
        return sorted(self._KEYWORDS)


def tokenize_source(source: str, filename: str = "<input>") -> List[Token]:
    """Convenience function to tokenize source code.
    
    Args:
        source: Python source code string
        filename: Source filename for error reporting
        
    Returns:
        List of Token objects
    """
    lexer = Lexer()
    return lexer.tokenize(source, filename)


# Example usage and testing
if __name__ == "__main__":
    # Test the lexer
    test_code = '''
class Point:
    x = 0
    y = 0
    
    def move(self, dx, dy):
        self.x = self.x + dx
        self.y = self.y + dy

p = Point()
p.move(3, 4)
print(p.x)
'''
    
    print("Testing lexer with sample code:")
    print("-" * 50)
    print(test_code)
    print("-" * 50)
    
    lexer = Lexer()
    try:
        tokens = lexer.tokenize(test_code)
        print(f"\nGenerated {len(tokens)} tokens:")
        for token in tokens[:20]:  # Show first 20 tokens
            print(f"  {token}")
        if len(tokens) > 20:
            print(f"  ... and {len(tokens) - 20} more tokens")
    except LexerError as e:
        print(f"Lexer error: {e}")
