"""
Unit tests for the Compiler with ParserV2 integration.
"""

import pytest
from pathlib import Path
from pcc.core import Compiler
from pcc.frontend import ParserV2, LexerError
from pcc.frontend.parser_v1 import ParseError as ParseErrorV1


class TestCompilerV2:
    """Tests for Compiler with ParserV2."""
    
    @pytest.fixture
    def compiler_v2(self):
        return Compiler(parser_version=2)
    
    @pytest.fixture
    def compiler_v1(self):
        return Compiler(parser_version=1)
    
    def test_compiler_v2_initialization(self, compiler_v2):
        """Test that Compiler initializes with ParserV2."""
        assert compiler_v2._parser_version == 2
        assert isinstance(compiler_v2._parser, ParserV2)
    
    def test_compiler_v1_initialization(self, compiler_v1):
        """Test that Compiler initializes with ParserV1."""
        from pcc.frontend.parser_v1 import Parser
        assert compiler_v1._parser_version == 1
        assert isinstance(compiler_v1._parser, Parser)
    
    def test_compiler_invalid_version(self):
        """Test that Compiler raises error for invalid version."""
        with pytest.raises(ValueError, match="Invalid parser version"):
            Compiler(parser_version=3)
    
    def test_parse_simple_program_v2(self, compiler_v2):
        """Test parsing simple program with V2."""
        source = "x = 42\nprint(x)"
        ir = compiler_v2.parse(source)
        assert len(ir.main) == 2
    
    def test_parse_function_v2(self, compiler_v2):
        """Test parsing function with V2."""
        source = """
def add(a, b):
    return a + b

result = add(1, 2)
print(result)
"""
        ir = compiler_v2.parse(source)
        assert len(ir.functions) == 1
        assert len(ir.main) == 2
    
    def test_parse_class_v2(self, compiler_v2):
        """Test parsing class with V2."""
        source = """
class Point:
    x = 0
    y = 0

p = Point()
print(p.x)
"""
        ir = compiler_v2.parse(source)
        assert len(ir.classes) == 1
        assert ir.classes[0].name == "Point"
    
    def test_v1_and_v2_produce_same_ir(self, compiler_v1, compiler_v2):
        """Test that V1 and V2 produce equivalent IR."""
        source = """
x = 10
y = x + 5
print(y)
"""
        ir_v1 = compiler_v1.parse(source)
        ir_v2 = compiler_v2.parse(source)
        
        # Both should have same number of main statements
        assert len(ir_v1.main) == len(ir_v2.main)
        assert len(ir_v1.functions) == len(ir_v2.functions)
        assert len(ir_v1.classes) == len(ir_v2.classes)


class TestCompilerV2ErrorHandling:
    """Tests for Compiler V2 error handling."""
    
    @pytest.fixture
    def compiler_v2(self):
        return Compiler(parser_version=2)
    
    def test_undefined_variable_error(self, compiler_v2):
        """Test error on undefined variable."""
        source = "x = y + 1"  # y is not defined
        with pytest.raises(Exception):  # ParseErrorV2
            compiler_v2.parse(source)
    
    def test_syntax_error_handling(self, compiler_v2):
        """Test handling of syntax errors."""
        # This should be caught by the lexer
        source = "x = @@@"  # Invalid syntax
        with pytest.raises(Exception):
            compiler_v2.parse(source)


class TestCompilerV2CodeGeneration:
    """Tests for Compiler V2 code generation."""
    
    @pytest.fixture
    def compiler_v2(self):
        return Compiler(parser_version=2)
    
    def test_generate_c_simple(self, compiler_v2):
        """Test generating C code from V2 parsed IR."""
        source = "x = 42\nprint(x)"
        ir = compiler_v2.parse(source)
        c_source = compiler_v2.generate_c(ir)
        
        assert c_source.c_source is not None
        assert len(c_source.c_source) > 0
        assert "rt_int" in c_source.c_source or "int" in c_source.c_source
    
    def test_generate_c_with_function(self, compiler_v2):
        """Test generating C code with function."""
        source = """
def greet():
    print(1)

x = greet()
"""
        ir = compiler_v2.parse(source)
        c_source = compiler_v2.generate_c(ir)
        
        assert "greet" in c_source.c_source


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
