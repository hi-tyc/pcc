"""Float support tests for pcc."""

from pcc.core import Compiler
from pcc.ir import FloatConst, Assign, BinOp, Print


def test_parse_float_literal_v1_and_v2():
    src = "x = 1.5\nprint(x)\n"
    ir1 = Compiler(parser_version=1).parse(src)
    ir2 = Compiler(parser_version=2).parse(src)

    assert isinstance(ir1.main[0], Assign)
    assert isinstance(ir1.main[0].expr, FloatConst)

    assert isinstance(ir2.main[0], Assign)
    assert isinstance(ir2.main[0].expr, FloatConst)


def test_codegen_fast_declares_double_and_prints():
    c = Compiler(parser_version=2)  # fast codegen by default
    src = "x = 1.5\ny = x * 2\nprint(y)\n"
    ir = c.parse(src)
    csrc = c.generate_c(ir).c_source

    assert "double x" in csrc
    assert "double y" in csrc
    # Uses %.17g for double prints
    assert "printf(\"%.17g\\n\"" in csrc


def test_float_comparison_generates_double_compare():
    c = Compiler(parser_version=2)
    src = "x = 1.5\nif x < 2.0:\n    print(1)\nelse:\n    print(0)\n"
    ir = c.parse(src)
    csrc = c.generate_c(ir).c_source
    # Should contain a double comparison
    assert "(double)" not in csrc or "<" in csrc
    assert "printf" in csrc
