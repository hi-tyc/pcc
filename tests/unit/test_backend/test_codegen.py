"""
Unit tests for the code generation module.

This module tests the CodeGenerator class defined in pcc.backend.codegen.
"""

import pytest
from pcc.backend import CodeGenerator, CSource
from pcc.ir import (
    IntConst, StrConst, Var, BinOp, CmpOp, Call,
    Assign, Print, If, While, ForRange, Return,
    FunctionDef, ClassDef, ModuleIR
)


class TestCodeGeneratorBasic:
    """Tests for basic code generation."""

    def test_generate_empty_module(self, codegen):
        """Test generating code for an empty module."""
        module = ModuleIR(functions=[], classes=[], main=[])
        result = codegen.generate(module)
        assert isinstance(result, CSource)
        assert "int main(void)" in result.c_source
        assert "return 0;" in result.c_source

    def test_generate_print_integer(self, codegen):
        """Test generating code for printing an integer."""
        module = ModuleIR(
            functions=[],
            classes=[],
            main=[Print(IntConst(42))]
        )
        result = codegen.generate(module)
        assert "rt_print_int" in result.c_source
        assert "42" in result.c_source

    def test_generate_print_string(self, codegen):
        """Test generating code for printing a string."""
        module = ModuleIR(
            functions=[],
            classes=[],
            main=[Print(StrConst("hello"))]
        )
        result = codegen.generate(module)
        assert "rt_print_str" in result.c_source
        assert "hello" in result.c_source

    def test_generate_assignment(self, codegen):
        """Test generating code for variable assignment."""
        module = ModuleIR(
            functions=[],
            classes=[],
            main=[Assign("x", IntConst(42))]
        )
        result = codegen.generate(module)
        assert "rt_int x" in result.c_source
        assert "rt_int_init" in result.c_source


class TestCodeGeneratorExpressions:
    """Tests for expression code generation."""

    def test_generate_addition(self, codegen):
        """Test generating code for addition."""
        module = ModuleIR(
            functions=[],
            classes=[],
            main=[Print(BinOp("+", IntConst(1), IntConst(2)))]
        )
        result = codegen.generate(module)
        assert "rt_int_add" in result.c_source

    def test_generate_subtraction(self, codegen):
        """Test generating code for subtraction."""
        module = ModuleIR(
            functions=[],
            classes=[],
            main=[Print(BinOp("-", IntConst(5), IntConst(3)))]
        )
        result = codegen.generate(module)
        assert "rt_int_sub" in result.c_source

    def test_generate_multiplication(self, codegen):
        """Test generating code for multiplication."""
        module = ModuleIR(
            functions=[],
            classes=[],
            main=[Print(BinOp("*", IntConst(4), IntConst(5)))]
        )
        result = codegen.generate(module)
        assert "rt_int_mul" in result.c_source

    def test_generate_floor_division(self, codegen):
        """Test generating code for floor division."""
        module = ModuleIR(
            functions=[],
            classes=[],
            main=[Print(BinOp("//", IntConst(10), IntConst(3)))]
        )
        result = codegen.generate(module)
        assert "rt_int_floordiv" in result.c_source

    def test_generate_modulo(self, codegen):
        """Test generating code for modulo."""
        module = ModuleIR(
            functions=[],
            classes=[],
            main=[Print(BinOp("%", IntConst(10), IntConst(3)))]
        )
        result = codegen.generate(module)
        assert "rt_int_mod" in result.c_source

    def test_generate_comparison(self, codegen):
        """Test generating code for comparison."""
        module = ModuleIR(
            functions=[],
            classes=[],
            main=[Print(CmpOp("<", IntConst(1), IntConst(2)))]
        )
        result = codegen.generate(module)
        assert "rt_int_cmp" in result.c_source


class TestCodeGeneratorControlFlow:
    """Tests for control flow code generation."""

    def test_generate_if_statement(self, codegen):
        """Test generating code for if statement."""
        module = ModuleIR(
            functions=[],
            classes=[],
            main=[If(
                test=CmpOp(">", IntConst(1), IntConst(0)),
                body=[Print(IntConst(1))],
                orelse=[]
            )]
        )
        result = codegen.generate(module)
        assert "if (" in result.c_source
        assert "{" in result.c_source
        assert "}" in result.c_source

    def test_generate_if_else_statement(self, codegen):
        """Test generating code for if-else statement."""
        module = ModuleIR(
            functions=[],
            classes=[],
            main=[If(
                test=CmpOp(">", IntConst(1), IntConst(0)),
                body=[Print(IntConst(1))],
                orelse=[Print(IntConst(0))]
            )]
        )
        result = codegen.generate(module)
        assert "if (" in result.c_source
        assert "} else {" in result.c_source

    def test_generate_while_loop(self, codegen):
        """Test generating code for while loop."""
        module = ModuleIR(
            functions=[],
            classes=[],
            main=[While(
                test=CmpOp(">", IntConst(1), IntConst(0)),
                body=[Print(IntConst(1))]
            )]
        )
        result = codegen.generate(module)
        assert "while_start_" in result.c_source
        assert "goto" in result.c_source

    def test_generate_for_range(self, codegen):
        """Test generating code for for-range loop."""
        module = ModuleIR(
            functions=[],
            classes=[],
            main=[ForRange(
                var="i",
                start=IntConst(0),
                stop=IntConst(5),
                step=IntConst(1),
                body=[Print(Var("i"))],
                lineno=1
            )]
        )
        result = codegen.generate(module)
        assert "for_start_" in result.c_source
        assert "rt_int_cmp" in result.c_source


class TestCodeGeneratorFunctions:
    """Tests for function code generation."""

    def test_generate_function_definition(self, codegen):
        """Test generating code for function definition."""
        module = ModuleIR(
            functions=[FunctionDef(
                name="add",
                params=["a", "b"],
                body=[Return(BinOp("+", Var("a"), Var("b")))],
                lineno=1
            )],
            classes=[],
            main=[]
        )
        result = codegen.generate(module)
        assert "pcc_fn_add" in result.c_source
        assert "rt_int* out" in result.c_source

    def test_generate_function_call(self, codegen):
        """Test generating code for function call."""
        module = ModuleIR(
            functions=[FunctionDef(
                name="add",
                params=["a", "b"],
                body=[Return(BinOp("+", Var("a"), Var("b")))],
                lineno=1
            )],
            classes=[],
            main=[Print(Call("add", [IntConst(1), IntConst(2)]))]
        )
        result = codegen.generate(module)
        assert "pcc_fn_add" in result.c_source


class TestCodeGeneratorClasses:
    """Tests for class code generation."""

    def test_generate_class_struct(self, codegen):
        """Test generating code for class struct definition."""
        module = ModuleIR(
            functions=[],
            classes=[ClassDef(
                name="Point",
                methods=[],
                fields=["x", "y"],
                lineno=1
            )],
            main=[]
        )
        result = codegen.generate(module)
        assert "typedef struct" in result.c_source
        assert "pcc_class_Point" in result.c_source
        assert "rt_int x" in result.c_source
        assert "rt_int y" in result.c_source

    def test_generate_class_constructor(self, codegen):
        """Test generating code for class constructor."""
        module = ModuleIR(
            functions=[],
            classes=[ClassDef(
                name="Point",
                methods=[],
                fields=["x", "y"],
                lineno=1
            )],
            main=[]
        )
        result = codegen.generate(module)
        assert "pcc_new_Point" in result.c_source
        assert "malloc" in result.c_source

    def test_generate_class_method(self, codegen):
        """Test generating code for class method."""
        module = ModuleIR(
            functions=[],
            classes=[ClassDef(
                name="Point",
                methods=[FunctionDef(
                    name="move",
                    params=["dx", "dy"],
                    body=[],
                    lineno=1
                )],
                fields=["x", "y"],
                lineno=1
            )],
            main=[]
        )
        result = codegen.generate(module)
        assert "pcc_method_Point_move" in result.c_source


class TestCodeGeneratorOutput:
    """Tests for verifying generated C code structure."""

    def test_includes_present(self, codegen):
        """Test that required includes are present."""
        module = ModuleIR(functions=[], classes=[], main=[])
        result = codegen.generate(module)
        assert '#include <stdio.h>' in result.c_source
        assert '#include <stdlib.h>' in result.c_source
        assert '#include "runtime.h"' in result.c_source

    def test_main_function_structure(self, codegen):
        """Test that main function has correct structure."""
        module = ModuleIR(functions=[], classes=[], main=[])
        result = codegen.generate(module)
        assert "int main(void) {" in result.c_source
        assert "return 0;" in result.c_source

    def test_runtime_functions_used(self, codegen):
        """Test that runtime functions are properly called."""
        module = ModuleIR(
            functions=[],
            classes=[],
            main=[Assign("x", IntConst(42)), Print(Var("x"))]
        )
        result = codegen.generate(module)
        assert "rt_int_init" in result.c_source
        assert "rt_int_clear" in result.c_source
        assert "rt_print_int" in result.c_source


class TestCodeGeneratorEdgeCases:
    """Tests for edge cases in code generation."""

    def test_nested_expressions(self, codegen):
        """Test generating code for nested expressions."""
        # (1 + 2) * 3
        inner = BinOp("+", IntConst(1), IntConst(2))
        outer = BinOp("*", inner, IntConst(3))
        module = ModuleIR(
            functions=[],
            classes=[],
            main=[Print(outer)]
        )
        result = codegen.generate(module)
        # Should generate multiple temporaries
        assert result.c_source.count("rt_int_init") >= 2

    def test_string_concatenation(self, codegen):
        """Test generating code for string concatenation."""
        module = ModuleIR(
            functions=[],
            classes=[],
            main=[
                Assign("a", StrConst("hello")),
                Assign("b", StrConst(" world")),
                Print(BinOp("+", Var("a"), Var("b")))
            ]
        )
        result = codegen.generate(module)
        assert "rt_str" in result.c_source
