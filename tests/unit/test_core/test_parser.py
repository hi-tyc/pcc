"""
Unit tests for the parser module.

This module tests the Parser class defined in pcc.core.parser.
"""

import pytest
from pcc.core import Parser, ParseError
from pcc.ir import IntConst, StrConst, Var, BinOp, CmpOp, Call


class TestParserBasic:
    """Tests for basic parsing functionality."""

    def test_parse_print_integer(self, parser):
        """Test parsing a simple print statement with integer."""
        ir = parser.parse("print(42)")
        assert len(ir.main) == 1
        stmt = ir.main[0]
        assert stmt.expr.value == 42

    def test_parse_print_string(self, parser):
        """Test parsing a print statement with string."""
        ir = parser.parse('print("hello")')
        assert len(ir.main) == 1
        stmt = ir.main[0]
        assert stmt.expr.value == "hello"

    def test_parse_assignment(self, parser):
        """Test parsing a variable assignment."""
        ir = parser.parse("x = 42")
        assert len(ir.main) == 1
        stmt = ir.main[0]
        assert stmt.name == "x"
        assert stmt.expr.value == 42

    def test_parse_multiple_statements(self, parser):
        """Test parsing multiple statements."""
        ir = parser.parse("x = 1\nprint(x)")
        assert len(ir.main) == 2


class TestParserExpressions:
    """Tests for expression parsing."""

    def test_parse_binary_addition(self, parser):
        """Test parsing addition expression."""
        ir = parser.parse("x = 1 + 2")
        stmt = ir.main[0]
        assert isinstance(stmt.expr, BinOp)
        assert stmt.expr.op == "+"

    def test_parse_binary_subtraction(self, parser):
        """Test parsing subtraction expression."""
        ir = parser.parse("x = 5 - 3")
        stmt = ir.main[0]
        assert isinstance(stmt.expr, BinOp)
        assert stmt.expr.op == "-"

    def test_parse_binary_multiplication(self, parser):
        """Test parsing multiplication expression."""
        ir = parser.parse("x = 4 * 5")
        stmt = ir.main[0]
        assert isinstance(stmt.expr, BinOp)
        assert stmt.expr.op == "*"

    def test_parse_binary_division(self, parser):
        """Test parsing floor division expression."""
        ir = parser.parse("x = 10 // 3")
        stmt = ir.main[0]
        assert isinstance(stmt.expr, BinOp)
        assert stmt.expr.op == "//"

    def test_parse_binary_modulo(self, parser):
        """Test parsing modulo expression."""
        ir = parser.parse("x = 10 % 3")
        stmt = ir.main[0]
        assert isinstance(stmt.expr, BinOp)
        assert stmt.expr.op == "%"

    def test_parse_comparison_equal(self, parser):
        """Test parsing equality comparison."""
        ir = parser.parse("x = 1 == 1")
        stmt = ir.main[0]
        assert isinstance(stmt.expr, CmpOp)
        assert stmt.expr.op == "=="

    def test_parse_comparison_less_than(self, parser):
        """Test parsing less-than comparison."""
        ir = parser.parse("x = 1 < 2")
        stmt = ir.main[0]
        assert isinstance(stmt.expr, CmpOp)
        assert stmt.expr.op == "<"

    def test_parse_negative_number(self, parser):
        """Test parsing negative number."""
        ir = parser.parse("x = -5")
        stmt = ir.main[0]
        assert isinstance(stmt.expr, BinOp)
        assert stmt.expr.op == "-"


class TestParserControlFlow:
    """Tests for control flow parsing."""

    def test_parse_if_statement(self, parser):
        """Test parsing if statement."""
        ir = parser.parse("""
x = 1
if x > 0:
    print(1)
""")
        assert len(ir.main) == 2
        stmt = ir.main[1]
        assert len(stmt.body) == 1
        assert len(stmt.orelse) == 0

    def test_parse_if_else_statement(self, parser):
        """Test parsing if-else statement."""
        ir = parser.parse("""
x = 1
if x > 0:
    print(1)
else:
    print(0)
""")
        stmt = ir.main[1]
        assert len(stmt.body) == 1
        assert len(stmt.orelse) == 1

    def test_parse_while_loop(self, parser):
        """Test parsing while loop."""
        ir = parser.parse("""
x = 5
while x > 0:
    print(x)
    x = x - 1
""")
        assert len(ir.main) == 2
        stmt = ir.main[1]
        assert len(stmt.body) == 2

    def test_parse_for_range(self, parser):
        """Test parsing for-range loop."""
        ir = parser.parse("""
for i in range(5):
    print(i)
""")
        assert len(ir.main) == 1
        stmt = ir.main[0]
        assert stmt.var == "i"

    def test_parse_for_range_with_start_stop(self, parser):
        """Test parsing for-range with start and stop."""
        ir = parser.parse("""
for i in range(1, 5):
    print(i)
""")
        stmt = ir.main[0]
        assert stmt.start.value == 1
        assert stmt.stop.value == 5

    def test_parse_for_range_with_step(self, parser):
        """Test parsing for-range with step."""
        ir = parser.parse("""
for i in range(0, 10, 2):
    print(i)
""")
        stmt = ir.main[0]
        assert stmt.step.value == 2


class TestParserFunctions:
    """Tests for function parsing."""

    def test_parse_function_definition(self, parser):
        """Test parsing function definition."""
        ir = parser.parse("""
def add(a, b):
    return a + b
""")
        assert len(ir.functions) == 1
        func = ir.functions[0]
        assert func.name == "add"
        assert func.params == ["a", "b"]

    def test_parse_function_no_params(self, parser):
        """Test parsing function with no parameters."""
        ir = parser.parse("""
def get_zero():
    return 0
""")
        func = ir.functions[0]
        assert func.params == []

    def test_parse_function_call(self, parser):
        """Test parsing function call."""
        ir = parser.parse("""
def add(a, b):
    return a + b

print(add(1, 2))
""")
        assert len(ir.functions) == 1
        # The call is in the print statement
        print_stmt = ir.main[0]
        assert isinstance(print_stmt.expr, Call)
        assert print_stmt.expr.func == "add"


class TestParserErrors:
    """Tests for parser error handling."""

    def test_undefined_variable(self, parser):
        """Test that undefined variables raise an error."""
        with pytest.raises(ParseError) as exc_info:
            parser.parse("print(undefined_var)")
        assert "variable used before assignment" in str(exc_info.value)

    def test_unknown_function(self, parser):
        """Test that unknown functions raise an error."""
        with pytest.raises(ParseError) as exc_info:
            parser.parse("print(unknown_func())")
        assert "unknown function" in str(exc_info.value)

    def test_break_outside_loop(self, parser):
        """Test that break outside loop raises an error."""
        with pytest.raises(ParseError) as exc_info:
            parser.parse("break")
        assert "break outside loop" in str(exc_info.value)

    def test_continue_outside_loop(self, parser):
        """Test that continue outside loop raises an error."""
        with pytest.raises(ParseError) as exc_info:
            parser.parse("continue")
        assert "continue outside loop" in str(exc_info.value)

    def test_import_not_supported(self, parser):
        """Test that import statements are not supported."""
        with pytest.raises(ParseError) as exc_info:
            parser.parse("import os")
        assert "unsupported statement" in str(exc_info.value)

    def test_class_empty_not_supported(self, parser):
        """Test that empty class definitions are not supported."""
        with pytest.raises(ParseError) as exc_info:
            parser.parse("class MyClass: pass")
        assert "only methods and field assignments allowed in class" in str(exc_info.value)


class TestParserBigInt:
    """Tests for BigInt parsing."""

    def test_parse_large_integer(self, parser):
        """Test parsing a very large integer."""
        big_num = "123456789012345678901234567890"
        ir = parser.parse(f"x = {big_num}")
        stmt = ir.main[0]
        assert str(stmt.expr.value) == big_num

    def test_parse_bigint_arithmetic(self, parser):
        """Test parsing arithmetic with large integers."""
        ir = parser.parse("x = 1000000000000000000 + 1")
        stmt = ir.main[0]
        assert isinstance(stmt.expr, BinOp)
        assert stmt.expr.left.value == 1000000000000000000
