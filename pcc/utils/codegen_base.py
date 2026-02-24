"""
Base utilities for C code generation in pcc.

This module provides shared functionality used by both the HPF (BigInt)
and Fast (native long long) code generators.
"""

from dataclasses import dataclass
from typing import Dict, List

from ..ir import Expr, StrConst, Var, BinOp


INT64_MIN = -9223372036854775808
INT64_MAX = 9223372036854775807


@dataclass
class CodegenState:
    """Shared state for code generation.
    
    Tracks temporary variable and label counters to generate unique names,
    and tracks the types of temporaries.
    """
    temp_counter: int = 0
    label_counter: int = 0
    temp_types: Dict[str, str] = None
    
    def __post_init__(self):
        if self.temp_types is None:
            self.temp_types = {}
    
    def next_temp(self, type_hint: str = "rt_int") -> str:
        """Generate a unique temporary variable name.
        
        Args:
            type_hint: The type of the temporary (e.g., "rt_int", "rt_str", "long long")
        
        Returns:
            A unique temporary name like "pcc_tmp_1"
        """
        self.temp_counter += 1
        temp_name = f"pcc_tmp_{self.temp_counter}"
        self.temp_types[temp_name] = type_hint
        return temp_name
    
    def get_temp_type(self, temp_name: str) -> str:
        """Get the type of a temporary variable.
        
        Args:
            temp_name: The name of the temporary
        
        Returns:
            The type string
        """
        return self.temp_types.get(temp_name, "rt_int")
    
    def next_label(self, prefix: str) -> str:
        """Generate a unique label name.
        
        Args:
            prefix: Prefix for the label (e.g., "while_start")
        
        Returns:
            A unique label name like "while_start_1"
        """
        self.label_counter += 1
        return f"{prefix}_{self.label_counter}"


def ctype_for_var(name: str, var_types: Dict[str, str], default: str = "rt_int") -> str:
    """Get the C type for a variable.
    
    Args:
        name: Variable name
        var_types: Mapping of variable names to their C types
        default: Default type if not found
    
    Returns:
        The C type string
    """
    return var_types.get(name, default)


def expr_produces_string(expr: Expr, var_types: Dict[str, str]) -> bool:
    """Check if an expression produces a string result.
    
    This is used to determine if a BinOp expression results in a string,
    which happens when both operands are strings and the operator is '+'.
    
    Args:
        expr: The expression to check
        var_types: Mapping of variable names to their C types
    
    Returns:
        True if the expression produces a string
    """
    if isinstance(expr, StrConst):
        return True
    if isinstance(expr, Var):
        return var_types.get(expr.name) == "rt_str"
    if isinstance(expr, BinOp) and expr.op == "+":
        left_is_str = expr_produces_string(expr.left, var_types)
        right_is_str = expr_produces_string(expr.right, var_types)
        return left_is_str and right_is_str
    return False


def fits_in_int64(value: int) -> bool:
    """Check if an integer value fits in a 64-bit signed integer.
    
    Args:
        value: The integer value to check
    
    Returns:
        True if the value fits in int64_t range
    """
    return INT64_MIN <= value <= INT64_MAX


def escape_c_string(s: str) -> str:
    """Escape a string for use in C source code.
    
    Args:
        s: The string to escape
    
    Returns:
        The escaped string safe for use in C string literals
    """
    return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\t', '\\t')


def emit_int_const(
    value: int,
    lines: List[str],
    state: CodegenState,
    use_hpf: bool = False
) -> str:
    """Emit code for an integer constant.
    
    Args:
        value: The integer value
        lines: List to append generated C lines to
        state: Codegen state for generating unique names
        use_hpf: Whether to always use HPF (BigInt) representation
    
    Returns:
        C expression string representing the integer
    """
    if not use_hpf and fits_in_int64(value):
        return f"{value}LL"
    
    temp = state.next_temp(type_hint="rt_int")
    lines.append(f"    rt_int {temp}; rt_int_init(&{temp});")
    
    if fits_in_int64(value):
        lines.append(f"    rt_int_set_si(&{temp}, {value}LL);")
    else:
        lines.append(f'    rt_int_from_dec(&{temp}, "{value}");')
    
    return f"&{temp}"


def emit_str_const(
    value: str,
    lines: List[str],
    state: CodegenState
) -> str:
    """Emit code for a string constant.
    
    Args:
        value: The string value
        lines: List to append generated C lines to
        state: Codegen state for generating unique names
    
    Returns:
        C expression string representing the string
    """
    temp = state.next_temp(type_hint="rt_str")
    escaped = escape_c_string(value)
    lines.append(f'    rt_str {temp} = rt_str_from_cstr("{escaped}");')
    return temp
