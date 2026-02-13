"""
Unit tests for the Version 2 parser with tokenize-based lexer.
"""

import pytest
from pcc.frontend import ParserV2, ParseError, LexerError
from pcc.ir import (
    IntConst, StrConst, Var, BinOp, CmpOp, Call,
    Assign, Print, If, While, ForRange, Return, Break, Continue,
    FunctionDef, ClassDef, ModuleIR
)


class TestParserV2Basic:
    """Tests for basic parser functionality."""
    
    @pytest.fixture
    def parser(self):
        return ParserV2()
    
    def test_empty_source(self, parser):
        """Test parsing empty source."""
        ir = parser.parse("")
        assert isinstance(ir, ModuleIR)
        assert len(ir.functions) == 0
        assert len(ir.classes) == 0
        assert len(ir.main) == 0
    
    def test_simple_assignment(self, parser):
        """Test parsing simple assignment."""
        ir = parser.parse("x = 42")
        assert len(ir.main) == 1
        stmt = ir.main[0]
        assert isinstance(stmt, Assign)
        assert stmt.name == "x"
        assert isinstance(stmt.expr, IntConst)
        assert stmt.expr.value == 42
    
    def test_string_assignment(self, parser):
        """Test parsing string assignment."""
        ir = parser.parse('x = "hello"')
        assert len(ir.main) == 1
        stmt = ir.main[0]
        assert isinstance(stmt, Assign)
        assert stmt.name == "x"
        assert isinstance(stmt.expr, StrConst)
        assert stmt.expr.value == "hello"
    
    def test_print_statement(self, parser):
        """Test parsing print statement."""
        ir = parser.parse("print(42)")
        assert len(ir.main) == 1
        stmt = ir.main[0]
        assert isinstance(stmt, Print)
        assert isinstance(stmt.expr, IntConst)
        assert stmt.expr.value == 42


class TestParserV2Expressions:
    """Tests for expression parsing."""
    
    @pytest.fixture
    def parser(self):
        return ParserV2()
    
    def test_binary_operations(self, parser):
        """Test parsing binary operations."""
        test_cases = [
            ("x = 1 + 2", "+"),
            ("x = 1 - 2", "-"),
            ("x = 1 * 2", "*"),
            ("x = 1 // 2", "//"),
            ("x = 1 % 2", "%"),
        ]
        
        for source, expected_op in test_cases:
            ir = parser.parse(source)
            stmt = ir.main[0]
            assert isinstance(stmt.expr, BinOp)
            assert stmt.expr.op == expected_op
    
    def test_comparison_operations(self, parser):
        """Test parsing comparison operations."""
        test_cases = [
            ("x = 1 < 2", "<"),
            ("x = 1 > 2", ">"),
            ("x = 1 <= 2", "<="),
            ("x = 1 >= 2", ">="),
            ("x = 1 == 2", "=="),
            ("x = 1 != 2", "!="),
        ]
        
        for source, expected_op in test_cases:
            ir = parser.parse(source)
            stmt = ir.main[0]
            assert isinstance(stmt.expr, CmpOp)
            assert stmt.expr.op == expected_op
    
    def test_variable_reference(self, parser):
        """Test parsing variable reference."""
        ir = parser.parse("""
x = 10
y = x + 5
""")
        assert len(ir.main) == 2
        stmt = ir.main[1]
        assert isinstance(stmt.expr, BinOp)
        # Due to left associativity, x is on the left
        assert isinstance(stmt.expr.left, Var)
        assert stmt.expr.left.name == "x"
    
    def test_negative_number(self, parser):
        """Test parsing negative number."""
        ir = parser.parse("x = -5")
        stmt = ir.main[0]
        assert isinstance(stmt.expr, BinOp)
        assert stmt.expr.op == "-"
        assert isinstance(stmt.expr.left, IntConst)
        assert stmt.expr.left.value == 0
        assert isinstance(stmt.expr.right, IntConst)
        assert stmt.expr.right.value == 5


class TestParserV2ControlFlow:
    """Tests for control flow parsing."""
    
    @pytest.fixture
    def parser(self):
        return ParserV2()
    
    def test_if_statement(self, parser):
        """Test parsing if statement."""
        ir = parser.parse("""
x = 1
if x > 0:
    print(x)
""")
        assert len(ir.main) == 2
        stmt = ir.main[1]
        assert isinstance(stmt, If)
        assert isinstance(stmt.test, CmpOp)
        assert len(stmt.body) == 1
        assert len(stmt.orelse) == 0
    
    def test_if_else_statement(self, parser):
        """Test parsing if-else statement."""
        ir = parser.parse("""
x = 1
if x > 0:
    print(1)
else:
    print(0)
""")
        stmt = ir.main[1]
        assert isinstance(stmt, If)
        assert len(stmt.body) == 1
        assert len(stmt.orelse) == 1
    
    def test_while_loop(self, parser):
        """Test parsing while loop."""
        ir = parser.parse("""
x = 1
while x < 10:
    x = x + 1
""")
        assert len(ir.main) == 2
        stmt = ir.main[1]
        assert isinstance(stmt, While)
        assert isinstance(stmt.test, CmpOp)
        assert len(stmt.body) == 1
    
    def test_for_range(self, parser):
        """Test parsing for-range loop."""
        ir = parser.parse("""
for i in range(5):
    print(i)
""")
        assert len(ir.main) == 1
        stmt = ir.main[0]
        assert isinstance(stmt, ForRange)
        assert stmt.var == "i"
        assert isinstance(stmt.start, IntConst)
        assert stmt.start.value == 0
        assert isinstance(stmt.stop, IntConst)
        assert stmt.stop.value == 5
    
    def test_break_statement(self, parser):
        """Test parsing break statement."""
        ir = parser.parse("""
while True:
    break
""")
        stmt = ir.main[0].body[0]
        assert isinstance(stmt, Break)
    
    def test_continue_statement(self, parser):
        """Test parsing continue statement."""
        ir = parser.parse("""
while True:
    continue
""")
        stmt = ir.main[0].body[0]
        assert isinstance(stmt, Continue)


class TestParserV2Functions:
    """Tests for function parsing."""
    
    @pytest.fixture
    def parser(self):
        return ParserV2()
    
    def test_function_definition(self, parser):
        """Test parsing function definition."""
        ir = parser.parse("""
def add(a, b):
    return a + b
""")
        assert len(ir.functions) == 1
        func = ir.functions[0]
        assert isinstance(func, FunctionDef)
        assert func.name == "add"
        assert func.params == ["a", "b"]
        assert len(func.body) == 1
    
    def test_function_call(self, parser):
        """Test parsing function call."""
        ir = parser.parse("""
def add(a, b):
    return a + b

x = add(1, 2)
""")
        assert len(ir.functions) == 1
        assert len(ir.main) == 1
        stmt = ir.main[0]
        assert isinstance(stmt.expr, Call)
        assert stmt.expr.func == "add"
        assert len(stmt.expr.args) == 2


class TestParserV2Classes:
    """Tests for class parsing."""
    
    @pytest.fixture
    def parser(self):
        return ParserV2()
    
    def test_class_definition(self, parser):
        """Test parsing class definition."""
        ir = parser.parse("""
class Point:
    x = 0
    y = 0
""")
        assert len(ir.classes) == 1
        cls = ir.classes[0]
        assert isinstance(cls, ClassDef)
        assert cls.name == "Point"
        assert "x" in cls.fields
        assert "y" in cls.fields
    
    def test_class_with_method(self, parser):
        """Test parsing class with method."""
        ir = parser.parse("""
class Point:
    x = 0
    
    def move(self, dx):
        self.x = self.x + dx
""")
        assert len(ir.classes) == 1
        cls = ir.classes[0]
        assert len(cls.methods) == 1
        method = cls.methods[0]
        assert method.name == "move"
        assert method.params == ["dx"]


class TestParserV2Errors:
    """Tests for parser error handling."""
    
    @pytest.fixture
    def parser(self):
        return ParserV2()
    
    def test_undefined_variable(self, parser):
        """Test error on undefined variable."""
        with pytest.raises(ParseError):
            parser.parse("x = y + 1")
    
    def test_break_outside_loop(self, parser):
        """Test error on break outside loop."""
        with pytest.raises(ParseError):
            parser.parse("break")
    
    def test_continue_outside_loop(self, parser):
        """Test error on continue outside loop."""
        with pytest.raises(ParseError):
            parser.parse("continue")
    
    def test_unknown_function(self, parser):
        """Test error on unknown function."""
        with pytest.raises(ParseError):
            parser.parse("x = unknown_func()")


class TestParserV2Integration:
    """Integration tests for the parser."""
    
    @pytest.fixture
    def parser(self):
        return ParserV2()
    
    def test_complex_program(self, parser):
        """Test parsing a complex program."""
        source = """
class Counter:
    value = 0
    
    def increment(self):
        self.value = self.value + 1

def main():
    c = Counter()
    c.increment()
    c.increment()
    return c.value

result = main()
print(result)
"""
        ir = parser.parse(source)
        
        assert len(ir.classes) == 1
        assert len(ir.functions) == 1
        assert len(ir.main) == 2
        
        # Check class
        cls = ir.classes[0]
        assert cls.name == "Counter"
        assert len(cls.methods) == 1
        
        # Check function
        func = ir.functions[0]
        assert func.name == "main"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
