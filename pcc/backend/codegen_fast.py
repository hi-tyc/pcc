"""
Fast C code generation module for pcc.

This version uses native long long integers instead of HPF/BigInt for better performance.
Only uses HPF when explicitly requested or when values exceed 64-bit range.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Set, Tuple

from ..ir import (
    ModuleIR, FunctionDef, ClassDef, Stmt, Expr,
    IntConst, StrConst, ListConst, DictConst, Subscript,
    Var, BinOp, CmpOp, Call, AttributeAccess, MethodCall, ConstructorCall, BuiltinCall,
    Assign, AttrAssign, MethodCallStmt, Print, If, While, ForRange, TryExcept, Raise, Return, Break, Continue
)


@dataclass(frozen=True)
class CSource:
    """Container for generated C source code."""
    c_source: str


class _CodegenState:
    """Internal state for code generation."""

    def __init__(self) -> None:
        self.temp_counter = 0
        self.label_counter = 0
        self.temp_types: Dict[str, str] = {}  # temp_name -> type ("long long" or "rt_str")

    def next_temp(self, type_hint: str = "long long") -> str:
        """Generate a unique temporary variable name."""
        self.temp_counter += 1
        temp_name = f"pcc_tmp_{self.temp_counter}"
        self.temp_types[temp_name] = type_hint
        return temp_name

    def get_temp_type(self, temp_name: str) -> str:
        """Get the type of a temporary variable."""
        return self.temp_types.get(temp_name, "long long")

    def next_label(self, prefix: str) -> str:
        """Generate a unique label name."""
        self.label_counter += 1
        return f"{prefix}_{self.label_counter}"


def _ctype_for_var(name: str, var_types: Dict[str, str]) -> str:
    """Get the C type for a variable."""
    return var_types.get(name, "long long")


def _expr_produces_string(expr: Expr, var_types: Dict[str, str]) -> bool:
    """Check if an expression produces a string result."""
    if isinstance(expr, StrConst):
        return True
    if isinstance(expr, Var):
        return var_types.get(expr.name) == "rt_str"
    if isinstance(expr, BinOp) and expr.op == "+":
        left_is_str = _expr_produces_string(expr.left, var_types)
        right_is_str = _expr_produces_string(expr.right, var_types)
        return left_is_str and right_is_str
    return False


def _expr_is_list(expr: Expr, var_types: Dict[str, str]) -> bool:
    """True if expression is (or evaluates to) a PCC list."""
    if isinstance(expr, ListConst):
        return True
    if isinstance(expr, Var):
        return var_types.get(expr.name) == "rt_list_si"
    return False


def _expr_is_dict(expr: Expr, var_types: Dict[str, str]) -> bool:
    """True if expression is (or evaluates to) a PCC dict."""
    if isinstance(expr, DictConst):
        return True
    if isinstance(expr, Var):
        return var_types.get(expr.name) == "rt_dict_ssi"
    return False


def _needs_hpf(expr: Expr) -> bool:
    """Check if expression needs HPF (value exceeds 64-bit range)."""
    if isinstance(expr, IntConst):
        return not (-9223372036854775808 <= expr.value <= 9223372036854775807)
    return False


def _emit_expr(
    expr: Expr,
    lines: List[str],
    state: _CodegenState,
    var_types: Dict[str, str],
    fn_sigs: Dict[str, int]
) -> str:
    """Emit code for an expression and return the C expression string."""
    
    # Integer constant - use long long by default, HPF only for large values
    if isinstance(expr, IntConst):
        # Check if value fits in int64_t
        if -9223372036854775808 <= expr.value <= 9223372036854775807:
            # Use native long long
            return f"{expr.value}LL"
        else:
            # Use HPF for large integers
            temp = state.next_temp(type_hint="rt_int")
            lines.append(f"    rt_int {temp}; rt_int_init(&{temp});")
            lines.append(f'    rt_int_from_dec(&{temp}, "{expr.value}");')
            return f"&{temp}"

    if isinstance(expr, StrConst):
        temp = state.next_temp(type_hint="rt_str")
        escaped = expr.value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\t', '\\t')
        lines.append(f'    rt_str {temp} = rt_str_from_cstr("{escaped}");')
        return temp

    if isinstance(expr, ListConst):
        temp = state.next_temp(type_hint="rt_list_si")
        lines.append(f"    rt_list_si {temp}; rt_list_si_init(&{temp});")
        for e in expr.elements:
            ev = _emit_expr(e, lines, state, var_types, fn_sigs)
            lines.append(f"    rt_list_si_append(&{temp}, {ev});")
        return temp

    if isinstance(expr, DictConst):
        temp = state.next_temp(type_hint="rt_dict_ssi")
        lines.append(f"    rt_dict_ssi {temp}; rt_dict_ssi_init(&{temp});")
        for k, v in zip(expr.keys, expr.values):
            kv = _emit_expr(k, lines, state, var_types, fn_sigs)
            vv = _emit_expr(v, lines, state, var_types, fn_sigs)
            lines.append(f"    rt_dict_ssi_set(&{temp}, {kv}, {vv});")
        return temp

    if isinstance(expr, Subscript):
        ctype = _ctype_for_var(expr.obj, var_types)
        idx = _emit_expr(expr.index, lines, state, var_types, fn_sigs)
        temp = state.next_temp(type_hint="long long")
        lines.append(f"    long long {temp};")
        if ctype == "rt_list_si":
            lines.append(f"    {temp} = rt_list_si_get(&{expr.obj}, {idx});")
            return temp
        if ctype == "rt_dict_ssi":
            lines.append(f"    {temp} = rt_dict_ssi_get(&{expr.obj}, {idx});")
            return temp
        raise ValueError(f"Subscript on unsupported type for {expr.obj}: {ctype}")

    if isinstance(expr, Var):
        ctype = _ctype_for_var(expr.name, var_types)
        if ctype == "rt_str":
            return expr.name
        elif ctype == "rt_int":
            return f"&{expr.name}"
        elif ctype == "rt_list_si":
            return expr.name
        elif ctype == "rt_dict_ssi":
            return expr.name
        else:
            # long long - return directly
            return expr.name

    if isinstance(expr, BinOp):
        left = _emit_expr(expr.left, lines, state, var_types, fn_sigs)
        right = _emit_expr(expr.right, lines, state, var_types, fn_sigs)
        
        # Check if this is a string concatenation
        left_is_str = isinstance(expr.left, StrConst)
        if isinstance(expr.left, Var) and var_types.get(expr.left.name) == "rt_str":
            left_is_str = True
        if isinstance(expr.left, BinOp):
            left_is_str = _expr_produces_string(expr.left, var_types)

        right_is_str = isinstance(expr.right, StrConst)
        if isinstance(expr.right, Var) and var_types.get(expr.right.name) == "rt_str":
            right_is_str = True
        if isinstance(expr.right, BinOp):
            right_is_str = _expr_produces_string(expr.right, var_types)

        if left_is_str and right_is_str and expr.op == "+":
            # String concatenation
            temp = state.next_temp(type_hint="rt_str")
            lines.append(f"    rt_str {temp} = rt_str_concat({left}, {right});")
            return temp
        else:
            # Integer arithmetic - use native long long operations
            temp = state.next_temp(type_hint="long long")
            lines.append(f"    long long {temp};")
            
            # For division and modulo, ensure right operand is in a variable to avoid compile-time detection
            if expr.op in ("//", "%") and isinstance(expr.right, IntConst):
                right_var = state.next_temp(type_hint="long long")
                lines.append(f"    long long {right_var} = {right};")
                right = right_var
            
            if expr.op == "+":
                lines.append(f"    {temp} = {left} + {right};")
            elif expr.op == "-":
                lines.append(f"    {temp} = {left} - {right};")
            elif expr.op == "*":
                lines.append(f"    {temp} = {left} * {right};")
            elif expr.op == "//":
                # Python floor division: floor(a / b)
                # C truncates toward zero, so we need to adjust for negative results
                # Check for division by zero first - must check BEFORE performing division
                lines.append(f"    if ({right} == 0) RT_RAISE(RT_EXC_ZeroDivisionError, \"division by zero\");")
                lines.append(f"    {temp} = {left} / {right};")
                lines.append(f"    if ({right} != 0 && ({left} < 0) != ({right} < 0) && {left} % {right} != 0) {{")
                lines.append(f"        {temp} -= 1;")
                lines.append(f"    }}")
            elif expr.op == "%":
                # Python modulo: result has same sign as divisor (always non-negative for positive divisor)
                # C's % has same sign as dividend
                # Check for division by zero first - must check BEFORE performing modulo
                lines.append(f"    if ({right} == 0) RT_RAISE(RT_EXC_ZeroDivisionError, \"modulo by zero\");")
                lines.append(f"    {temp} = {left} % {right};")
                lines.append(f"    if ({right} != 0 && ({left} < 0) != ({right} < 0) && {temp} != 0) {{")
                lines.append(f"        {temp} += {right};")
                lines.append(f"    }}")
            else:
                raise ValueError(f"Unsupported binary operator: {expr.op}")
            return temp

    if isinstance(expr, CmpOp):
        left = _emit_expr(expr.left, lines, state, var_types, fn_sigs)
        right = _emit_expr(expr.right, lines, state, var_types, fn_sigs)
        temp = state.next_temp(type_hint="int")
        lines.append(f"    int {temp} = ({left} {expr.op} {right});")
        return f"({temp} != 0)"

    if isinstance(expr, Call):
        arg_exprs = []
        for arg in expr.args:
            # For function calls, arguments need to be passed as pointers
            # So we need to store literals in temporaries
            if isinstance(arg, IntConst):
                # Create a temporary for the literal
                temp_arg = state.next_temp(type_hint="long long")
                lines.append(f"    long long {temp_arg} = {arg.value}LL;")
                arg_exprs.append(f"&{temp_arg}")
            elif isinstance(arg, Var):
                # Variables need address-of operator
                arg_exprs.append(f"&{_emit_expr(arg, lines, state, var_types, fn_sigs)}")
            else:
                # Other expressions - emit and take address
                arg_expr = _emit_expr(arg, lines, state, var_types, fn_sigs)
                arg_exprs.append(f"&{arg_expr}")

        temp = state.next_temp(type_hint="long long")
        lines.append(f"    long long {temp};")

        args_str = ", ".join(arg_exprs)
        lines.append(f"    pcc_fn_{expr.func}(&{temp}, {args_str});")
        return temp

    if isinstance(expr, AttributeAccess):
        temp = state.next_temp(type_hint="long long")
        lines.append(f"    long long {temp};")
        lines.append(f"    pcc_get_attr_{expr.obj}_{expr.attr}(&{temp});")
        return temp

    if isinstance(expr, MethodCall):
        arg_exprs = []
        for arg in expr.args:
            arg_expr = _emit_expr(arg, lines, state, var_types, fn_sigs)
            arg_exprs.append(arg_expr)

        temp = state.next_temp(type_hint="long long")
        lines.append(f"    long long {temp};")

        args_str = ", ".join(arg_exprs)
        lines.append(f"    pcc_method_{expr.obj}_{expr.method}(&{temp}, {args_str});")
        return temp

    if isinstance(expr, ConstructorCall):
        arg_exprs = []
        for arg in expr.args:
            arg_expr = _emit_expr(arg, lines, state, var_types, fn_sigs)
            arg_exprs.append(arg_expr)

        temp = state.next_temp(type_hint="long long")
        lines.append(f"    long long {temp};")

        args_str = ", ".join(arg_exprs)
        lines.append(f"    pcc_new_{expr.class_name}(&{temp}, {args_str});")
        return temp

    if isinstance(expr, BuiltinCall):
        return _emit_builtin_call(expr, lines, state, var_types, fn_sigs)

    raise ValueError(f"Unsupported expression: {type(expr).__name__}")


def _emit_builtin_call(
    expr: BuiltinCall,
    lines: List[str],
    state: _CodegenState,
    var_types: Dict[str, str],
    fn_sigs: Dict[str, int]
) -> str:
    """Emit code for a builtin function call."""
    # Emit arguments
    arg_exprs = []
    for arg in expr.args:
        arg_expr = _emit_expr(arg, lines, state, var_types, fn_sigs)
        arg_exprs.append(arg_expr)
    
    if expr.name == 'len':
        arg_expr = expr.args[0]
        arg = arg_exprs[0]
        temp = state.next_temp(type_hint="long long")
        if _expr_produces_string(arg_expr, var_types):
            lines.append(f"    long long {temp} = (long long)rt_str_len(&{arg});")
            return temp
        if _expr_is_list(arg_expr, var_types):
            lines.append(f"    long long {temp} = (long long)rt_list_si_len(&{arg});")
            return temp
        if _expr_is_dict(arg_expr, var_types):
            lines.append(f"    long long {temp} = (long long)rt_dict_ssi_len(&{arg});")
            return temp
        raise ValueError("len() only supports str/list/dict in this PCC version")
    
    elif expr.name == 'abs':
        # abs() returns absolute value
        arg = arg_exprs[0]
        temp = state.next_temp(type_hint="long long")
        lines.append(f"    long long {temp} = rt_math_abs_si({arg});")
        return temp
    
    elif expr.name == 'min':
        # min() returns minimum of arguments
        if len(arg_exprs) == 1:
            # Single argument should be iterable - not supported yet
            raise ValueError("min() with single iterable argument not supported")
        elif len(arg_exprs) == 2:
            temp = state.next_temp(type_hint="long long")
            lines.append(f"    long long {temp} = rt_math_min_si({arg_exprs[0]}, {arg_exprs[1]});")
            return temp
        else:
            # Multiple arguments - chain min calls
            temp = state.next_temp(type_hint="long long")
            lines.append(f"    long long {temp} = {arg_exprs[0]};")
            for i in range(1, len(arg_exprs)):
                lines.append(f"    {temp} = rt_math_min_si({temp}, {arg_exprs[i]});")
            return temp
    
    elif expr.name == 'max':
        # max() returns maximum of arguments
        if len(arg_exprs) == 1:
            # Single argument should be iterable - not supported yet
            raise ValueError("max() with single iterable argument not supported")
        elif len(arg_exprs) == 2:
            temp = state.next_temp(type_hint="long long")
            lines.append(f"    long long {temp} = rt_math_max_si({arg_exprs[0]}, {arg_exprs[1]});")
            return temp
        else:
            # Multiple arguments - chain max calls
            temp = state.next_temp(type_hint="long long")
            lines.append(f"    long long {temp} = {arg_exprs[0]};")
            for i in range(1, len(arg_exprs)):
                lines.append(f"    {temp} = rt_math_max_si({temp}, {arg_exprs[i]});")
            return temp
    
    elif expr.name == 'pow':
        # pow() returns base^exp
        if len(arg_exprs) == 2:
            temp = state.next_temp(type_hint="long long")
            lines.append(f"    long long {temp} = rt_math_pow_si({arg_exprs[0]}, {arg_exprs[1]});")
            return temp
        elif len(arg_exprs) == 3:
            # Three-argument pow() for modular exponentiation - not supported yet
            raise ValueError("pow() with 3 arguments (modular) not supported")
    
    elif expr.name == 'str':
        # str() converts to string
        arg = arg_exprs[0]
        temp = state.next_temp(type_hint="rt_str")
        lines.append(f"    rt_str {temp} = rt_str_from_si({arg});")
        return temp
    
    elif expr.name == 'int':
        # int() converts to integer
        arg = arg_exprs[0]
        temp = state.next_temp(type_hint="long long")
        lines.append(f"    long long {temp} = {arg};")  # For now, just return as-is
        return temp
    
    raise ValueError(f"Unknown builtin: {expr.name}")


def _emit_stmt(
    stmt: Stmt,
    lines: List[str],
    state: _CodegenState,
    var_types: Dict[str, str],
    fn_sigs: Dict[str, int],
    in_loop: bool = False,
    break_label: Optional[str] = None,
    continue_label: Optional[str] = None
) -> None:
    """Emit code for a statement."""

    def _exc_enum(exc_name: str) -> str:
        mapping = {
            "Exception": "RT_EXC_Exception",
            "ZeroDivisionError": "RT_EXC_ZeroDivisionError",
            "IndexError": "RT_EXC_IndexError",
            "KeyError": "RT_EXC_KeyError",
            "TypeError": "RT_EXC_TypeError",
            "ValueError": "RT_EXC_ValueError",
        }
        return mapping.get(exc_name, "RT_EXC_Exception")
    
    if isinstance(stmt, Assign):
        expr_result = _emit_expr(stmt.expr, lines, state, var_types, fn_sigs)
        
        # Check if variable already exists
        if stmt.name in var_types:
            # Variable already declared, just assign
            ctype = var_types[stmt.name]
            if ctype == "rt_str":
                lines.append(f"    {stmt.name} = {expr_result};")
            elif ctype == "rt_int":
                lines.append(f"    rt_int_assign(&{stmt.name}, {expr_result});")
            else:
                # long long
                lines.append(f"    {stmt.name} = {expr_result};")
        else:
            # New variable - need to declare
            if isinstance(stmt.expr, StrConst):
                var_types[stmt.name] = "rt_str"
                lines.append(f"    rt_str {stmt.name} = {expr_result};")
            elif isinstance(stmt.expr, ListConst):
                var_types[stmt.name] = "rt_list_si"
                lines.append(f"    rt_list_si {stmt.name} = {expr_result};")
            elif isinstance(stmt.expr, DictConst):
                var_types[stmt.name] = "rt_dict_ssi"
                lines.append(f"    rt_dict_ssi {stmt.name} = {expr_result};")
            elif _expr_produces_string(stmt.expr, var_types):
                var_types[stmt.name] = "rt_str"
                lines.append(f"    rt_str {stmt.name} = {expr_result};")
            elif _expr_is_list(stmt.expr, var_types):
                var_types[stmt.name] = "rt_list_si"
                lines.append(f"    rt_list_si {stmt.name} = {expr_result};")
            elif _expr_is_dict(stmt.expr, var_types):
                var_types[stmt.name] = "rt_dict_ssi"
                lines.append(f"    rt_dict_ssi {stmt.name} = {expr_result};")
            elif _needs_hpf(stmt.expr):
                var_types[stmt.name] = "rt_int"
                lines.append(f"    rt_int {stmt.name}; rt_int_init(&{stmt.name});")
                lines.append(f"    rt_int_assign(&{stmt.name}, {expr_result});")
            else:
                # Default to long long
                var_types[stmt.name] = "long long"
                lines.append(f"    long long {stmt.name} = {expr_result};")
        return

    if isinstance(stmt, Print):
        expr_result = _emit_expr(stmt.expr, lines, state, var_types, fn_sigs)
        
        # Determine how to print based on expression type
        if isinstance(stmt.expr, StrConst):
            lines.append(f"    rt_print_str({expr_result});")
        elif isinstance(stmt.expr, Var) and var_types.get(stmt.expr.name) == "rt_str":
            lines.append(f"    rt_print_str({expr_result});")
        elif _expr_produces_string(stmt.expr, var_types):
            lines.append(f"    rt_print_str({expr_result});")
        elif isinstance(stmt.expr, Var) and var_types.get(stmt.expr.name) == "rt_int":
            lines.append(f"    rt_print_int({expr_result});")
        elif _needs_hpf(stmt.expr):
            lines.append(f"    rt_print_int({expr_result});")
        else:
            # Print long long directly
            lines.append(f"    printf(\"%lld\\n\", {expr_result});")
        return

    if isinstance(stmt, If):
        test_result = _emit_expr(stmt.test, lines, state, var_types, fn_sigs)
        lines.append(f"    if ({test_result}) {{")
        for s in stmt.body:
            _emit_stmt(s, lines, state, var_types, fn_sigs, in_loop, break_label, continue_label)
        if stmt.orelse:
            lines.append("    } else {")
            for s in stmt.orelse:
                _emit_stmt(s, lines, state, var_types, fn_sigs, in_loop, break_label, continue_label)
        lines.append("    }")
        return

    if isinstance(stmt, While):
        start_label = state.next_label("while_start")
        end_label = state.next_label("while_end")
        lines.append(f"{start_label}:")
        test_result = _emit_expr(stmt.test, lines, state, var_types, fn_sigs)
        lines.append(f"    if (!({test_result})) goto {end_label};")
        for s in stmt.body:
            _emit_stmt(s, lines, state, var_types, fn_sigs, in_loop=True, break_label=end_label, continue_label=start_label)
        lines.append(f"    goto {start_label};")
        lines.append(f"{end_label}:")
        return

    if isinstance(stmt, ForRange):
        # Emit loop variable initialization
        start_result = _emit_expr(stmt.start, lines, state, var_types, fn_sigs)
        var_types[stmt.var] = "long long"
        lines.append(f"    long long {stmt.var} = {start_result};")
        
        # Get stop and step values
        stop_result = _emit_expr(stmt.stop, lines, state, var_types, fn_sigs)
        step_result = _emit_expr(stmt.step, lines, state, var_types, fn_sigs)
        
        start_label = state.next_label("for_start")
        end_label = state.next_label("for_end")
        continue_label = state.next_label("for_continue")
        
        lines.append(f"{start_label}:")
        # Check step direction for loop condition
        lines.append(f"    if ({step_result} > 0) {{")
        lines.append(f"        if ({stmt.var} >= {stop_result}) goto {end_label};")
        lines.append(f"    }} else {{")
        lines.append(f"        if ({stmt.var} <= {stop_result}) goto {end_label};")
        lines.append(f"    }}")
        for s in stmt.body:
            _emit_stmt(s, lines, state, var_types, fn_sigs, in_loop=True, break_label=end_label, continue_label=continue_label)
        lines.append(f"{continue_label}:")
        lines.append(f"    {stmt.var} += {step_result};")
        lines.append(f"    goto {start_label};")
        lines.append(f"{end_label}:")
        return

    if isinstance(stmt, TryExcept):
        ctx = state.next_temp(type_hint="rt_try_ctx")
        flag = state.next_temp(type_hint="int")
        lines.append(f"    rt_try_ctx {ctx};")
        lines.append(f"    int {flag} = rt_try_push(&{ctx});")
        lines.append(f"    if ({flag} == 0) {{")
        for s in stmt.body:
            _emit_stmt(s, lines, state, var_types, fn_sigs, in_loop=in_loop, break_label=break_label, continue_label=continue_label)
        lines.append(f"        rt_try_pop(&{ctx});")
        lines.append("    } else {")
        if stmt.exc_name is None:
            lines.append("        rt_exc_clear();")
            lines.append(f"        rt_try_pop(&{ctx});")
            for s in stmt.handler:
                _emit_stmt(s, lines, state, var_types, fn_sigs, in_loop=in_loop, break_label=break_label, continue_label=continue_label)
        else:
            enumv = _exc_enum(stmt.exc_name)
            lines.append(f"        if (rt_exc_is({enumv})) {{")
            lines.append("            rt_exc_clear();")
            lines.append(f"            rt_try_pop(&{ctx});")
            for s in stmt.handler:
                _emit_stmt(s, lines, state, var_types, fn_sigs, in_loop=in_loop, break_label=break_label, continue_label=continue_label)
            lines.append("        } else {")
            lines.append(f"            rt_try_pop(&{ctx});")
            lines.append("            rt_reraise();")
            lines.append("        }")
        lines.append("    }")
        return

    if isinstance(stmt, Raise):
        enumv = _exc_enum(stmt.exc_name)
        msg = stmt.message if stmt.message is not None else ""
        msg_c = msg.replace('\\', r'\\').replace('"', r'\\"')
        lines.append(f"    rt_raise({enumv}, \"{msg_c}\", \"<source>\", {stmt.lineno});")
        return

    if isinstance(stmt, Return):
        if stmt.expr:
            expr_result = _emit_expr(stmt.expr, lines, state, var_types, fn_sigs)
            lines.append(f"    *pcc_ret = {expr_result};")
        lines.append("    return;")
        return

    if isinstance(stmt, Break):
        if not in_loop or break_label is None:
            raise ValueError("break outside of loop")
        lines.append(f"    goto {break_label};")
        return

    if isinstance(stmt, Continue):
        if not in_loop or continue_label is None:
            raise ValueError("continue outside of loop")
        lines.append(f"    goto {continue_label};")
        return

    if isinstance(stmt, MethodCallStmt):
        obj_type = var_types.get(stmt.obj, "long long")
        if obj_type == "rt_list_si" and stmt.method == "append":
            if len(stmt.args) != 1:
                raise ValueError("list.append expects 1 argument")
            av = _emit_expr(stmt.args[0], lines, state, var_types, fn_sigs)
            lines.append(f"    rt_list_si_append(&{stmt.obj}, {av});")
            return

        arg_exprs = []
        for arg in stmt.args:
            arg_expr = _emit_expr(arg, lines, state, var_types, fn_sigs)
            arg_exprs.append(arg_expr)

        args_str = ", ".join(arg_exprs)
        lines.append(f"    pcc_method_{stmt.obj}_{stmt.method}({args_str});")
        return

    raise ValueError(f"Unsupported statement: {type(stmt).__name__}")


def _emit_function(
    func: FunctionDef,
    lines: List[str],
    state: _CodegenState,
    fn_sigs: Dict[str, int]
) -> None:
    """Emit code for a function definition."""
    var_types: Dict[str, str] = {}
    
    # Parameters are long long by default - passed by pointer for consistency
    params = [f"long long* pcc_{p}" for p in func.params]
    params_str = ", ".join(params) if params else "void"
    
    lines.append(f"void pcc_fn_{func.name}(long long* pcc_ret, {params_str}) {{")
    
    # Copy parameters to local variables for easier access
    for param in func.params:
        var_types[param] = "long long"
        lines.append(f"    long long {param} = *pcc_{param};")
    
    for stmt in func.body:
        _emit_stmt(stmt, lines, state, var_types, fn_sigs, in_loop=False)
    
    lines.append("}")


def _emit_class(cls: ClassDef, lines: List[str], state: _CodegenState) -> None:
    """Emit code for a class definition."""
    # Emit class struct and methods
    lines.append(f"// Class: {cls.name}")
    lines.append(f"typedef struct {{ long long value; }} pcc_class_{cls.name};")


def generate(module_ir: ModuleIR) -> CSource:
    """Generate C source code from intermediate representation using fast native integers."""
    lines: List[str] = []
    state = _CodegenState()
    
    # Collect function signatures
    fn_sigs: Dict[str, int] = {}
    for func in module_ir.functions:
        fn_sigs[func.name] = len(func.params)
    
    # Include headers - minimal set for fast execution
    lines.append('#include <stdio.h>')
    lines.append('#include <stdlib.h>')
    lines.append('#include <string.h>')
    lines.append('#include <stdint.h>')
    # Include runtime library header
    lines.append('#include "runtime.h"')
    lines.append("")
    
    # Emit class definitions
    for cls in module_ir.classes:
        _emit_class(cls, lines, state)
    
    if module_ir.classes:
        lines.append("")
    
    # Emit forward declarations for all functions first
    for func in module_ir.functions:
        params = [f"long long* pcc_{p}" for p in func.params]
        params_str = ", ".join(params) if params else ""
        lines.append(f"void pcc_fn_{func.name}(long long* pcc_ret, {params_str});")
    
    if module_ir.functions:
        lines.append("")
    
    # Emit function definitions
    for func in module_ir.functions:
        _emit_function(func, lines, state, fn_sigs)
        lines.append("")
    
    # Emit main function
    lines.append("int main(void) {")
    
    var_types: Dict[str, str] = {}
    
    for stmt in module_ir.main:
        _emit_stmt(stmt, lines, state, var_types, fn_sigs, in_loop=False)
    
    lines.append("    return 0;")
    lines.append("}")
    
    return CSource(c_source="\n".join(lines))
