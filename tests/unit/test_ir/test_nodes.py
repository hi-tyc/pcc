"""
Unit tests for IR (Intermediate Representation) nodes.

This module tests the IR node classes defined in pcc.ir.nodes.
"""

import pytest
from pcc.ir import (
    IntConst, StrConst, Var, BinOp, CmpOp, Call,
    Assign, Print, If, While, ForRange, Return, Break, Continue,
    FunctionDef, ModuleIR
)


class TestIntConst:
    """Tests for IntConst IR node."""

    def test_basic_value(self):
        """Test creating an integer constant."""
        node = IntConst(value=42)
        assert node.value == 42

    def test_bigint_value(self):
        """Test creating a large integer constant."""
        big = 10**100
        node = IntConst(value=big)
        assert node.value == big

    def test_negative_value(self):
        """Test creating a negative integer constant."""
        node = IntConst(value=-123)
        assert node.value == -123

    def test_zero_value(self):
        """Test creating a zero integer constant."""
        node = IntConst(value=0)
        assert node.value == 0

    def test_immutability(self):
        """Test that IntConst is immutable."""
        node = IntConst(value=42)
        with pytest.raises(AttributeError):
            node.value = 100


class TestStrConst:
    """Tests for StrConst IR node."""

    def test_basic_string(self):
        """Test creating a string constant."""
        node = StrConst(value="hello")
        assert node.value == "hello"

    def test_empty_string(self):
        """Test creating an empty string constant."""
        node = StrConst(value="")
        assert node.value == ""

    def test_unicode_string(self):
        """Test creating a unicode string constant."""
        node = StrConst(value="Hello, 世界")
        assert node.value == "Hello, 世界"

    def test_immutability(self):
        """Test that StrConst is immutable."""
        node = StrConst(value="hello")
        with pytest.raises(AttributeError):
            node.value = "world"


class TestVar:
    """Tests for Var IR node."""

    def test_variable_name(self):
        """Test creating a variable reference."""
        node = Var(name="x")
        assert node.name == "x"

    def test_long_name(self):
        """Test creating a variable with a long name."""
        node = Var(name="very_long_variable_name_123")
        assert node.name == "very_long_variable_name_123"


class TestBinOp:
    """Tests for BinOp IR node."""

    def test_addition(self):
        """Test creating an addition operation."""
        left = IntConst(1)
        right = IntConst(2)
        node = BinOp(op="+", left=left, right=right)
        assert node.op == "+"
        assert node.left.value == 1
        assert node.right.value == 2

    def test_subtraction(self):
        """Test creating a subtraction operation."""
        left = IntConst(5)
        right = IntConst(3)
        node = BinOp(op="-", left=left, right=right)
        assert node.op == "-"

    def test_multiplication(self):
        """Test creating a multiplication operation."""
        left = IntConst(4)
        right = IntConst(5)
        node = BinOp(op="*", left=left, right=right)
        assert node.op == "*"

    def test_floor_division(self):
        """Test creating a floor division operation."""
        left = IntConst(10)
        right = IntConst(3)
        node = BinOp(op="//", left=left, right=right)
        assert node.op == "//"

    def test_modulo(self):
        """Test creating a modulo operation."""
        left = IntConst(10)
        right = IntConst(3)
        node = BinOp(op="%", left=left, right=right)
        assert node.op == "%"


class TestCmpOp:
    """Tests for CmpOp IR node."""

    def test_equality(self):
        """Test creating an equality comparison."""
        left = IntConst(1)
        right = IntConst(1)
        node = CmpOp(op="==", left=left, right=right)
        assert node.op == "=="

    def test_less_than(self):
        """Test creating a less-than comparison."""
        left = IntConst(1)
        right = IntConst(2)
        node = CmpOp(op="<", left=left, right=right)
        assert node.op == "<"

    def test_all_comparison_ops(self):
        """Test all comparison operators."""
        left = IntConst(1)
        right = IntConst(2)
        ops = ["==", "!=", "<", "<=", ">", ">="]
        for op in ops:
            node = CmpOp(op=op, left=left, right=right)
            assert node.op == op


class TestCall:
    """Tests for Call IR node."""

    def test_function_call_no_args(self):
        """Test creating a function call with no arguments."""
        node = Call(func="foo", args=[])
        assert node.func == "foo"
        assert node.args == []

    def test_function_call_with_args(self):
        """Test creating a function call with arguments."""
        args = [IntConst(1), IntConst(2)]
        node = Call(func="add", args=args)
        assert node.func == "add"
        assert len(node.args) == 2


class TestAssign:
    """Tests for Assign IR node."""

    def test_integer_assignment(self):
        """Test creating an integer assignment."""
        expr = IntConst(42)
        node = Assign(name="x", expr=expr)
        assert node.name == "x"
        assert node.expr.value == 42

    def test_string_assignment(self):
        """Test creating a string assignment."""
        expr = StrConst("hello")
        node = Assign(name="s", expr=expr)
        assert node.name == "s"
        assert node.expr.value == "hello"


class TestPrint:
    """Tests for Print IR node."""

    def test_print_integer(self):
        """Test creating a print statement for integer."""
        expr = IntConst(42)
        node = Print(expr=expr)
        assert node.expr.value == 42

    def test_print_string(self):
        """Test creating a print statement for string."""
        expr = StrConst("hello")
        node = Print(expr=expr)
        assert node.expr.value == "hello"


class TestIf:
    """Tests for If IR node."""

    def test_simple_if(self):
        """Test creating a simple if statement."""
        test = CmpOp("==", IntConst(1), IntConst(1))
        body = [Print(IntConst(1))]
        orelse = []
        node = If(test=test, body=body, orelse=orelse)
        assert len(node.body) == 1
        assert len(node.orelse) == 0

    def test_if_else(self):
        """Test creating an if-else statement."""
        test = CmpOp(">", Var("x"), IntConst(0))
        body = [Print(StrConst("positive"))]
        orelse = [Print(StrConst("non-positive"))]
        node = If(test=test, body=body, orelse=orelse)
        assert len(node.body) == 1
        assert len(node.orelse) == 1


class TestWhile:
    """Tests for While IR node."""

    def test_simple_while(self):
        """Test creating a simple while loop."""
        test = CmpOp(">", Var("x"), IntConst(0))
        body = [Print(Var("x"))]
        node = While(test=test, body=body)
        assert len(node.body) == 1


class TestForRange:
    """Tests for ForRange IR node."""

    def test_simple_for(self):
        """Test creating a simple for-range loop."""
        node = ForRange(
            var="i",
            start=IntConst(0),
            stop=IntConst(10),
            step=IntConst(1),
            body=[Print(Var("i"))],
            lineno=1
        )
        assert node.var == "i"
        assert node.start.value == 0
        assert node.stop.value == 10
        assert node.step.value == 1


class TestReturn:
    """Tests for Return IR node."""

    def test_return_value(self):
        """Test creating a return statement with value."""
        expr = IntConst(42)
        node = Return(expr=expr)
        assert node.expr.value == 42


class TestBreak:
    """Tests for Break IR node."""

    def test_break(self):
        """Test creating a break statement."""
        node = Break(lineno=10)
        assert node.lineno == 10


class TestContinue:
    """Tests for Continue IR node."""

    def test_continue(self):
        """Test creating a continue statement."""
        node = Continue(lineno=20)
        assert node.lineno == 20


class TestFunctionDef:
    """Tests for FunctionDef IR node."""

    def test_simple_function(self):
        """Test creating a simple function definition."""
        node = FunctionDef(
            name="add",
            params=["a", "b"],
            body=[Return(BinOp("+", Var("a"), Var("b")))],
            lineno=1
        )
        assert node.name == "add"
        assert node.params == ["a", "b"]
        assert len(node.body) == 1

    def test_function_no_params(self):
        """Test creating a function with no parameters."""
        node = FunctionDef(
            name="get_zero",
            params=[],
            body=[Return(IntConst(0))],
            lineno=1
        )
        assert node.params == []


class TestModuleIR:
    """Tests for ModuleIR IR node."""

    def test_empty_module(self):
        """Test creating an empty module."""
        node = ModuleIR(functions=[], classes=[], main=[])
        assert node.functions == []
        assert node.classes == []
        assert node.main == []

    def test_module_with_functions(self):
        """Test creating a module with functions."""
        func = FunctionDef(
            name="add",
            params=["a", "b"],
            body=[Return(BinOp("+", Var("a"), Var("b")))],
            lineno=1
        )
        node = ModuleIR(functions=[func], classes=[], main=[Print(Call("add", [IntConst(1), IntConst(2)]))])
        assert len(node.functions) == 1
        assert len(node.main) == 1

    def test_module_main_only(self):
        """Test creating a module with only main statements."""
        node = ModuleIR(
            functions=[],
            classes=[],
            main=[Print(IntConst(1)), Print(IntConst(2))]
        )
        assert len(node.main) == 2

    def test_module_with_classes(self):
        """Test creating a module with classes."""
        from pcc.ir import ClassDef
        cls = ClassDef(
            name="Point",
            methods=[],
            fields=["x", "y"],
            lineno=1
        )
        node = ModuleIR(functions=[], classes=[cls], main=[])
        assert len(node.classes) == 1
        assert node.classes[0].name == "Point"
