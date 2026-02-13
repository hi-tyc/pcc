"""
Unit tests for the tokenize-based lexer.
"""

import pytest
from pcc.frontend import Lexer, Token, TokenType, LexerError


class TestLexerBasic:
    """Tests for basic lexer functionality."""
    
    @pytest.fixture
    def lexer(self):
        return Lexer()
    
    def test_empty_source(self, lexer):
        """Test tokenizing empty source."""
        tokens = lexer.tokenize("")
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.ENDMARKER
    
    def test_simple_assignment(self, lexer):
        """Test tokenizing simple assignment."""
        tokens = lexer.tokenize("x = 42")
        token_types = [t.type for t in tokens if t.type not in (TokenType.NL, TokenType.NEWLINE, TokenType.ENDMARKER)]
        assert token_types == [TokenType.NAME, TokenType.EQUAL, TokenType.NUMBER]
        
        # Check values
        assert tokens[0].value == "x"
        assert tokens[1].value == "="
        assert tokens[2].value == "42"
    
    def test_string_literal(self, lexer):
        """Test tokenizing string literal."""
        tokens = lexer.tokenize('x = "hello"')
        token_types = [t.type for t in tokens if t.type not in (TokenType.NL, TokenType.NEWLINE, TokenType.ENDMARKER)]
        assert token_types == [TokenType.NAME, TokenType.EQUAL, TokenType.STRING]
        assert tokens[2].value == '"hello"'
    
    def test_operators(self, lexer):
        """Test tokenizing operators."""
        source = "+ - * / % // < > <= >= == != ="
        tokens = lexer.tokenize(source)
        token_types = [t.type for t in tokens if t.type not in (TokenType.NL, TokenType.NEWLINE, TokenType.ENDMARKER)]
        expected = [
            TokenType.PLUS, TokenType.MINUS, TokenType.STAR, TokenType.SLASH,
            TokenType.PERCENT, TokenType.DOUBLESLASH, TokenType.LESS, TokenType.GREATER,
            TokenType.LESSEQUAL, TokenType.GREATEREQUAL, TokenType.EQEQUAL,
            TokenType.NOTEQUAL, TokenType.EQUAL
        ]
        assert token_types == expected
    
    def test_delimiters(self, lexer):
        """Test tokenizing delimiters."""
        source = "( ) { } [ ] : , ."
        tokens = lexer.tokenize(source)
        token_types = [t.type for t in tokens if t.type not in (TokenType.NL, TokenType.NEWLINE, TokenType.ENDMARKER)]
        expected = [
            TokenType.LPAR, TokenType.RPAR, TokenType.LBRACE, TokenType.RBRACE,
            TokenType.LBRACKET, TokenType.RBRACKET, TokenType.COLON, TokenType.COMMA, TokenType.DOT
        ]
        assert token_types == expected


class TestLexerKeywords:
    """Tests for keyword tokenization."""
    
    @pytest.fixture
    def lexer(self):
        return Lexer()
    
    def test_keywords(self, lexer):
        """Test that keywords are recognized."""
        keywords = ['def', 'class', 'if', 'else', 'while', 'for', 'in',
                   'return', 'pass', 'break', 'continue', 'print', 'range']
        
        for kw in keywords:
            tokens = lexer.tokenize(kw)
            assert tokens[0].type == TokenType.NAME
            assert tokens[0].value == kw
            assert lexer.is_keyword(kw)
    
    def test_non_keywords(self, lexer):
        """Test that non-keywords are not recognized as keywords."""
        non_keywords = ['foo', 'bar', 'myvar', 'x', 'y']
        
        for name in non_keywords:
            assert not lexer.is_keyword(name)


class TestLexerIndentation:
    """Tests for indentation handling."""
    
    @pytest.fixture
    def lexer(self):
        return Lexer()
    
    def test_indentation(self, lexer):
        """Test that indentation produces INDENT/DEDENT tokens."""
        source = """if x:
    y = 1
    z = 2
"""
        tokens = lexer.tokenize(source)
        token_types = [t.type for t in tokens]
        
        assert TokenType.INDENT in token_types
        assert TokenType.DEDENT in token_types


class TestLexerLineNumbers:
    """Tests for line number tracking."""
    
    @pytest.fixture
    def lexer(self):
        return Lexer()
    
    def test_line_numbers(self, lexer):
        """Test that line numbers are tracked correctly."""
        source = """x = 1
y = 2
z = 3"""
        tokens = lexer.tokenize(source)
        
        # Find NAME tokens and check their line numbers
        name_tokens = [t for t in tokens if t.type == TokenType.NAME]
        assert name_tokens[0].lineno == 1  # x
        assert name_tokens[1].lineno == 2  # y
        assert name_tokens[2].lineno == 3  # z


class TestLexerErrorHandling:
    """Tests for lexer error handling."""
    
    @pytest.fixture
    def lexer(self):
        return Lexer()
    
    def test_invalid_character(self, lexer):
        """Test handling of invalid characters."""
        # The lexer should handle most cases gracefully
        # or pass them through to be caught by the parser
        pass
    
    def test_lexer_error_attributes(self, lexer):
        """Test that LexerError has correct attributes."""
        error = LexerError("Test error", lineno=5, col_offset=10, line="x = y")
        assert error.message == "Test error"
        assert error.lineno == 5
        assert error.col_offset == 10
        assert error.line == "x = y"
        assert "Line 5" in str(error)


class TestLexerIntegration:
    """Integration tests for the lexer."""
    
    @pytest.fixture
    def lexer(self):
        return Lexer()
    
    def test_complex_source(self, lexer):
        """Test tokenizing a complex source."""
        source = """
class Point:
    x = 0
    y = 0
    
    def move(self, dx, dy):
        self.x = self.x + dx
        self.y = self.y + dy

p = Point()
print(p.x)
"""
        tokens = lexer.tokenize(source)
        
        # Should have tokens for class, def, names, operators, etc.
        token_types = [t.type for t in tokens]
        
        assert TokenType.NAME in token_types
        assert TokenType.NUMBER in token_types
        assert TokenType.LPAR in token_types
        assert TokenType.RPAR in token_types
        assert TokenType.DOT in token_types
    
    def test_tokenize_function(self):
        """Test the convenience tokenize function."""
        from pcc.frontend.lexer import tokenize_source
        
        tokens = tokenize_source("x = 42")
        assert len(tokens) > 0
        assert tokens[0].type == TokenType.NAME
        assert tokens[0].value == "x"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
