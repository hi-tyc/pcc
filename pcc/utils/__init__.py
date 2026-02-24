"""
Utility modules for pcc.

This package contains utility functions and helpers used throughout the compiler.
"""

from .toolchain import Toolchain, ToolchainDetector
from .settings import Settings
from .builtin_utils import (
    BUILTIN_ARITY,
    BUILTINS,
    validate_builtin_args,
    is_builtin,
    get_builtin_arity,
)
from .codegen_base import (
    INT64_MIN,
    INT64_MAX,
    CodegenState,
    ctype_for_var,
    expr_produces_string,
    fits_in_int64,
    escape_c_string,
    emit_int_const,
    emit_str_const,
)

__all__ = [
    "Toolchain",
    "ToolchainDetector",
    "Settings",
    "BUILTIN_ARITY",
    "BUILTINS",
    "validate_builtin_args",
    "is_builtin",
    "get_builtin_arity",
    "INT64_MIN",
    "INT64_MAX",
    "CodegenState",
    "ctype_for_var",
    "expr_produces_string",
    "fits_in_int64",
    "escape_c_string",
    "emit_int_const",
    "emit_str_const",
]
