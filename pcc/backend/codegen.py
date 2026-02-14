"""
C code generation module for pcc.

Converts the intermediate representation (IR) from the frontend into
C source code that uses the runtime library for BigInt and string operations.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Set, Tuple

from ..ir import (
    ModuleIR, FunctionDef, ClassDef, Stmt, Expr,
    IntConst, StrConst, Var, BinOp, CmpOp, Call, AttributeAccess, MethodCall, ConstructorCall, BuiltinCall,
    Assign, AttrAssign, MethodCallStmt, Print, If, While, ForRange, TryExcept, Raise, Return, Break, Continue
)


@dataclass(frozen=True)
class CSource:
    """Container for generated C source code.

    Attributes:
        c_source: The generated C source code as a string
    """
    c_source: str


class _CodegenState:
    """Internal state for code generation.

    Tracks temporary variable and label counters to generate unique names,
    and tracks the types of temporaries.
    """

    def __init__(self) -> None:
        self.temp_counter = 0
        self.label_counter = 0
        self.temp_types: Dict[str, str] = {}  # temp_name -> type ("rt_int" or "rt_str")

    def next_temp(self, type_hint: str = "rt_int") -> str:
        """Generate a unique temporary variable name.

        Args:
            type_hint: The type of the temporary ("rt_int" or "rt_str")

        Returns:
            str: A unique temporary name like "pcc_tmp_1"
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
            str: The type ("rt_int" or "rt_str")
        """
        return self.temp_types.get(temp_name, "rt_int")

    def next_label(self, prefix: str) -> str:
        """Generate a unique label name.

        Args:
            prefix: Prefix for the label (e.g., "while_start")

        Returns:
            str: A unique label name like "while_start_1"
        """
        self.label_counter += 1
        return f"{prefix}_{self.label_counter}"


def _ctype_for_var(name: str, var_types: Dict[str, str]) -> str:
    """Get the C type for a variable.

    Args:
        name: Variable name
        var_types: Mapping of variable names to their C types

    Returns:
        str: The C type ("rt_int" or "rt_str")
    """
    return var_types.get(name, "rt_int")


def _expr_produces_string(expr: Expr, var_types: Dict[str, str]) -> bool:
    """Check if an expression produces a string result.

    This is used to determine if a BinOp expression results in a string,
    which happens when both operands are strings and the operator is '+'.

    Args:
        expr: The expression to check
        var_types: Mapping of variable names to their C types

    Returns:
        bool: True if the expression produces a string
    """
    if isinstance(expr, StrConst):
        return True
    if isinstance(expr, Var):
        return var_types.get(expr.name) == "rt_str"
    if isinstance(expr, BinOp) and expr.op == "+":
        # String concatenation: both operands must be strings
        left_is_str = _expr_produces_string(expr.left, var_types)
        right_is_str = _expr_produces_string(expr.right, var_types)
        return left_is_str and right_is_str
    return False


def _emit_expr(
    expr: Expr,
    lines: List[str],
    state: _CodegenState,
    var_types: Dict[str, str],
    fn_sigs: Dict[str, int]
) -> str:
    """Emit code for an expression and return the C expression string.

    Args:
        expr: The IR expression to emit
        lines: List to append generated C lines to
        state: Codegen state for generating unique names
        var_types: Mapping of variable names to their C types
        fn_sigs: Mapping of function names to their arities

    Returns:
        str: C expression string representing the result
    """
    if isinstance(expr, IntConst):
        temp = state.next_temp()
        lines.append(f"    rt_int {temp}; rt_int_init(&{temp});")
        # Check if value fits in int64_t
        if -9223372036854775808 <= expr.value <= 9223372036854775807:
            lines.append(f"    rt_int_set_si(&{temp}, {expr.value}LL);")
        else:
            # Use decimal string for large integers
            lines.append(f'    rt_int_from_dec(&{temp}, "{expr.value}");')
        return f"&{temp}"

    if isinstance(expr, StrConst):
        temp = state.next_temp()
        # Escape the string for C (handle backslashes, quotes, newlines, etc.)
        escaped = expr.value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\t', '\\t')
        lines.append(f'    rt_str {temp} = rt_str_from_cstr("{escaped}");')
        return temp

    if isinstance(expr, Var):
        ctype = _ctype_for_var(expr.name, var_types)
        if ctype == "rt_str":
            return expr.name
        return f"&{expr.name}"

    if isinstance(expr, BinOp):
        left = _emit_expr(expr.left, lines, state, var_types, fn_sigs)
        right = _emit_expr(expr.right, lines, state, var_types, fn_sigs)
        temp = state.next_temp()

        # Check if this is a string concatenation
        # Left operand is a string if it's a StrConst, a string Var, or a string temp
        left_is_str = isinstance(expr.left, StrConst)
        if isinstance(expr.left, Var) and var_types.get(expr.left.name) == "rt_str":
            left_is_str = True
        if isinstance(expr.left, BinOp):
            # Recursively check if left sub-expression produces a string
            left_is_str = _expr_produces_string(expr.left, var_types)

        # Right operand is a string if it's a StrConst, a string Var, or a string temp
        right_is_str = isinstance(expr.right, StrConst)
        if isinstance(expr.right, Var) and var_types.get(expr.right.name) == "rt_str":
            right_is_str = True
        if isinstance(expr.right, BinOp):
            # Recursively check if right sub-expression produces a string
            right_is_str = _expr_produces_string(expr.right, var_types)

        if left_is_str and right_is_str and expr.op == "+":
            # String concatenation
            temp = state.next_temp(type_hint="rt_str")
            lines.append(f"    rt_str {temp} = rt_str_concat({left}, {right});")
            return temp
        else:
            # Integer arithmetic
            lines.append(f"    rt_int {temp}; rt_int_init(&{temp});")
            if expr.op == "+":
                lines.append(f"    rt_int_add(&{temp}, {left}, {right});")
            elif expr.op == "-":
                lines.append(f"    rt_int_sub(&{temp}, {left}, {right});")
            elif expr.op == "*":
                lines.append(f"    rt_int_mul(&{temp}, {left}, {right});")
            elif expr.op == "//":
                lines.append(f"    rt_int_floordiv(&{temp}, {left}, {right});")
            elif expr.op == "%":
                lines.append(f"    rt_int_mod(&{temp}, {left}, {right});")
            else:
                raise ValueError(f"Unsupported binary operator: {expr.op}")
            return f"&{temp}"

    if isinstance(expr, CmpOp):
        left = _emit_expr(expr.left, lines, state, var_types, fn_sigs)
        right = _emit_expr(expr.right, lines, state, var_types, fn_sigs)
        temp = state.next_temp()
        lines.append(f"    int {temp} = rt_int_cmp({left}, {right});")

        op_map = {
            "==": f"({temp} == 0)",
            "!=": f"({temp} != 0)",
            "<": f"({temp} < 0)",
            "<=": f"({temp} <= 0)",
            ">": f"({temp} > 0)",
            ">=": f"({temp} >= 0)",
        }
        return op_map.get(expr.op, f"({temp} == 0)")

    if isinstance(expr, Call):
        arg_exprs = []
        for arg in expr.args:
            arg_expr = _emit_expr(arg, lines, state, var_types, fn_sigs)
            arg_exprs.append(arg_expr)

        temp = state.next_temp()
        lines.append(f"    rt_int {temp}; rt_int_init(&{temp});")

        args_str = ", ".join(arg_exprs)
        lines.append(f"    pcc_fn_{expr.func}(&{temp}, {args_str});")
        return f"&{temp}"

    if isinstance(expr, AttributeAccess):
        # Access object field: obj.attr
        # The object variable holds a pointer to the struct
        obj_type = var_types.get(expr.obj, "rt_int")
        if obj_type.startswith("pcc_class_"):
            # Return address of the field for int types
            return f"&{expr.obj}->{expr.attr}"
        raise ValueError(f"Attribute access on non-object type: {obj_type}")

    if isinstance(expr, MethodCall):
        # Method call: obj.method(args)
        arg_exprs = []
        for arg in expr.args:
            arg_expr = _emit_expr(arg, lines, state, var_types, fn_sigs)
            arg_exprs.append(arg_expr)

        temp = state.next_temp()
        lines.append(f"    rt_int {temp}; rt_int_init(&{temp});")

        args_str = ", ".join(arg_exprs)
        lines.append(f"    pcc_method_{expr.obj}_{expr.method}({expr.obj}, &{temp}, {args_str});")
        return f"&{temp}"

    if isinstance(expr, ConstructorCall):
        # Constructor call: ClassName(args)
        temp = state.next_temp(type_hint=f"pcc_class_{expr.class_name}")

        # Allocate and initialize the object
        lines.append(f"    pcc_class_{expr.class_name}* {temp} = pcc_new_{expr.class_name}();")

        # Store the object pointer in var_types
        var_types[temp] = f"pcc_class_{expr.class_name}"

        return temp

    if isinstance(expr, BuiltinCall):
        return _emit_builtin_call(expr, lines, state, var_types)

    raise ValueError(f"Unsupported expression type: {type(expr).__name__}")


def _emit_builtin_call(
    expr: BuiltinCall,
    lines: List[str],
    state: _CodegenState,
    var_types: Dict[str, str]
) -> str:
    """Emit code for a builtin function call."""
    # Emit arguments
    arg_exprs = []
    for arg in expr.args:
        arg_expr = _emit_expr(arg, lines, state, var_types)
        arg_exprs.append(arg_expr)

    if expr.name == 'len':
        # len() returns the length of a string
        arg = arg_exprs[0]
        temp = state.next_temp(type_hint="rt_int")
        lines.append(f"    rt_int {temp}; rt_int_init(&{temp});")
        lines.append(f"    rt_int_set_si(&{temp}, rt_str_len({arg}));")
        return f"&{temp}"

    elif expr.name == 'abs':
        # abs() returns absolute value
        arg = arg_exprs[0]
        temp = state.next_temp(type_hint="rt_int")
        lines.append(f"    rt_int {temp}; rt_int_init(&{temp});")
        lines.append(f"    rt_math_abs(&{temp}, {arg});")
        return f"&{temp}"

    elif expr.name == 'min':
        # min() returns minimum of arguments
        if len(arg_exprs) == 2:
            temp = state.next_temp(type_hint="rt_int")
            lines.append(f"    rt_int {temp}; rt_int_init(&{temp});")
            lines.append(f"    rt_math_min(&{temp}, {arg_exprs[0]}, {arg_exprs[1]});")
            return f"&{temp}"
        else:
            raise ValueError("min() with more than 2 arguments not supported in HPF mode")

    elif expr.name == 'max':
        # max() returns maximum of arguments
        if len(arg_exprs) == 2:
            temp = state.next_temp(type_hint="rt_int")
            lines.append(f"    rt_int {temp}; rt_int_init(&{temp});")
            lines.append(f"    rt_math_max(&{temp}, {arg_exprs[0]}, {arg_exprs[1]});")
            return f"&{temp}"
        else:
            raise ValueError("max() with more than 2 arguments not supported in HPF mode")

    elif expr.name == 'pow':
        # pow() returns base^exp
        if len(arg_exprs) == 2:
            temp = state.next_temp(type_hint="rt_int")
            lines.append(f"    rt_int {temp}; rt_int_init(&{temp});")
            # Get exponent as int64
            lines.append(f"    int64_t exp; rt_int_to_si_checked({arg_exprs[1]}, &exp);")
            lines.append(f"    rt_math_pow(&{temp}, {arg_exprs[0]}, exp);")
            return f"&{temp}"
        else:
            raise ValueError("pow() with 3 arguments not supported")

    elif expr.name == 'str':
        # str() converts to string
        arg = arg_exprs[0]
        temp = state.next_temp(type_hint="rt_str")
        lines.append(f"    rt_str {temp} = rt_str_from_int({arg});")
        return temp

    elif expr.name == 'int':
        # int() converts to integer
        arg = arg_exprs[0]
        temp = state.next_temp(type_hint="rt_int")
        lines.append(f"    rt_int {temp}; rt_int_init(&{temp});")
        lines.append(f"    rt_int_copy(&{temp}, {arg});")
        return f"&{temp}"

    raise ValueError(f"Unknown builtin: {expr.name}")


def _collect_locals_in_stmt(stmt: Stmt) -> Set[Tuple[str, str]]:
    """Collect all local variables declared in a statement (for cleanup).

    Args:
        stmt: The statement to analyze

    Returns:
        Set of (name, type) tuples
    """
    locals_set: Set[Tuple[str, str]] = set()

    if isinstance(stmt, Assign):
        if isinstance(stmt.expr, StrConst):
            locals_set.add((stmt.name, "rt_str"))
        else:
            locals_set.add((stmt.name, "rt_int"))

    elif isinstance(stmt, (If, While)):
        for s in stmt.body:
            locals_set.update(_collect_locals_in_stmt(s))
        if isinstance(stmt, If):
            for s in stmt.orelse:
                locals_set.update(_collect_locals_in_stmt(s))

    elif isinstance(stmt, ForRange):
        locals_set.add((stmt.var, "rt_int"))
        for s in stmt.body:
            locals_set.update(_collect_locals_in_stmt(s))

    return locals_set


def _emit_block(
    stmts: List[Stmt],
    lines: List[str],
    state: _CodegenState,
    var_types: Dict[str, str],
    fn_sigs: Dict[str, int],
    in_loop: bool = False,
    break_label: str = "",
    continue_label: str = "",
    declared_vars: Optional[Set[str]] = None
) -> None:
    """Emit code for a block of statements.

    Args:
        stmts: List of statements to emit
        lines: List to append generated C lines to
        state: Codegen state
        var_types: Variable type mappings
        fn_sigs: Function signatures
        in_loop: Whether we're inside a loop
        break_label: Label to jump to for break statements
        continue_label: Label to jump to for continue statements
        declared_vars: Set of variables already declared in current scope
    """
    if declared_vars is None:
        declared_vars = set()

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

    for stmt in stmts:
        if isinstance(stmt, Assign):
            expr_result = _emit_expr(stmt.expr, lines, state, var_types, fn_sigs)

            if isinstance(stmt.expr, StrConst):
                var_types[stmt.name] = "rt_str"
                if stmt.name not in declared_vars:
                    declared_vars.add(stmt.name)
                    lines.append(f"    rt_str {stmt.name} = {expr_result};")
                else:
                    lines.append(f"    {stmt.name} = {expr_result};")
            elif isinstance(stmt.expr, ConstructorCall):
                # Object assignment
                class_name = stmt.expr.class_name
                var_types[stmt.name] = f"pcc_class_{class_name}"
                if stmt.name not in declared_vars:
                    declared_vars.add(stmt.name)
                    lines.append(f"    pcc_class_{class_name}* {stmt.name} = {expr_result};")
                else:
                    # Clean up old object before assigning new one
                    lines.append(f"    pcc_delete_{class_name}({stmt.name});")
                    lines.append(f"    {stmt.name} = {expr_result};")
            else:
                var_types[stmt.name] = "rt_int"
                if stmt.name not in declared_vars:
                    declared_vars.add(stmt.name)
                    lines.append(f"    rt_int {stmt.name}; rt_int_init(&{stmt.name});")
                    if isinstance(stmt.expr, Var) and var_types.get(stmt.expr.name) == "rt_str":
                        pass  # Type mismatch caught in frontend
                    else:
                        lines.append(f"    rt_int_copy(&{stmt.name}, {expr_result});")
                else:
                    # Variable already declared, just copy the new value
                    if isinstance(stmt.expr, Var) and var_types.get(stmt.expr.name) == "rt_str":
                        pass  # Type mismatch caught in frontend
                    else:
                        lines.append(f"    rt_int_copy(&{stmt.name}, {expr_result});")

        elif isinstance(stmt, AttrAssign):
            # Attribute assignment: obj.attr = expr
            expr_result = _emit_expr(stmt.expr, lines, state, var_types, fn_sigs)
            lines.append(f"    rt_int_copy(&{stmt.obj}->{stmt.attr}, {expr_result});")

        elif isinstance(stmt, MethodCallStmt):
            # Method call as statement: obj.method(args)
            arg_exprs = []
            for arg in stmt.args:
                arg_expr = _emit_expr(arg, lines, state, var_types, fn_sigs)
                arg_exprs.append(arg_expr)

            temp = state.next_temp()
            lines.append(f"    rt_int {temp}; rt_int_init(&{temp});")

            # Get the class name from the object variable type
            obj_type = var_types.get(stmt.obj, "")
            if obj_type.startswith("pcc_class_"):
                class_name = obj_type[10:]  # Remove "pcc_class_" prefix
            else:
                # Fallback - this shouldn't happen if parsing is correct
                class_name = stmt.obj

            args_str = ", ".join(arg_exprs)
            if args_str:
                lines.append(f"    pcc_method_{class_name}_{stmt.method}({stmt.obj}, &{temp}, {args_str});")
            else:
                lines.append(f"    pcc_method_{class_name}_{stmt.method}({stmt.obj}, &{temp});")

        elif isinstance(stmt, Print):
            expr_result = _emit_expr(stmt.expr, lines, state, var_types, fn_sigs)
            # Check if it's a string expression
            is_str = False
            if isinstance(stmt.expr, StrConst):
                is_str = True
            elif isinstance(stmt.expr, Var) and var_types.get(stmt.expr.name) == "rt_str":
                is_str = True
            elif expr_result.startswith("pcc_tmp_") and state.get_temp_type(expr_result) == "rt_str":
                is_str = True

            if is_str:
                lines.append(f"    rt_print_str({expr_result});")
            else:
                lines.append(f"    rt_print_int({expr_result});")

        elif isinstance(stmt, If):
            test_result = _emit_expr(stmt.test, lines, state, var_types, fn_sigs)
            lines.append(f"    if ({test_result}) {{")

            body_var_types = dict(var_types)
            body_declared = set(declared_vars)
            _emit_block(stmt.body, lines, state, body_var_types, fn_sigs,
                       in_loop, break_label, continue_label, body_declared)

            if stmt.orelse:
                lines.append("    } else {")
                else_var_types = dict(var_types)
                else_declared = set(declared_vars)
                _emit_block(stmt.orelse, lines, state, else_var_types, fn_sigs,
                           in_loop, break_label, continue_label, else_declared)

            lines.append("    }")

        elif isinstance(stmt, While):
            start_label = state.next_label("while_start")
            end_label = state.next_label("while_end")

            lines.append(f"    {start_label}:")
            test_result = _emit_expr(stmt.test, lines, state, var_types, fn_sigs)
            lines.append(f"    if (!({test_result})) goto {end_label};")

            body_var_types = dict(var_types)
            body_declared = set(declared_vars)
            _emit_block(stmt.body, lines, state, body_var_types, fn_sigs,
                       True, end_label, start_label, body_declared)

            lines.append(f"    goto {start_label};")
            lines.append(f"    {end_label}:")

        elif isinstance(stmt, ForRange):
            start_label = state.next_label("for_start")
            end_label = state.next_label("for_end")
            continue_label_for = state.next_label("for_continue")

            # Initialize loop variable
            start_result = _emit_expr(stmt.start, lines, state, var_types, fn_sigs)
            var_types[stmt.var] = "rt_int"
            lines.append(f"    rt_int {stmt.var}; rt_int_init(&{stmt.var});")
            lines.append(f"    rt_int_copy(&{stmt.var}, {start_result});")

            # Initialize stop value
            stop_temp = state.next_temp()
            stop_result = _emit_expr(stmt.stop, lines, state, var_types, fn_sigs)
            lines.append(f"    rt_int {stop_temp}; rt_int_init(&{stop_temp});")
            lines.append(f"    rt_int_copy(&{stop_temp}, {stop_result});")

            # Initialize step value
            step_temp = state.next_temp()
            step_result = _emit_expr(stmt.step, lines, state, var_types, fn_sigs)
            lines.append(f"    rt_int {step_temp}; rt_int_init(&{step_temp});")
            lines.append(f"    rt_int_copy(&{step_temp}, {step_result});")

            # Check step direction
            lines.append(f"    int {stop_temp}_cmp = rt_int_cmp(&{step_temp}, &(rt_int){{0}});")

            lines.append(f"    {start_label}:")

            # Loop condition based on step direction
            lines.append(f"    if ({stop_temp}_cmp > 0) {{")
            lines.append(f"        if (rt_int_cmp(&{stmt.var}, &{stop_temp}) >= 0) goto {end_label};")
            lines.append("    } else {")
            lines.append(f"        if (rt_int_cmp(&{stmt.var}, &{stop_temp}) <= 0) goto {end_label};")
            lines.append("    }")

            body_var_types = dict(var_types)
            body_declared = set(declared_vars)
            _emit_block(stmt.body, lines, state, body_var_types, fn_sigs,
                       True, end_label, continue_label_for, body_declared)

            lines.append(f"    {continue_label_for}:")
            lines.append(f"    rt_int_add(&{stmt.var}, &{stmt.var}, &{step_temp});")
            lines.append(f"    goto {start_label};")
            lines.append(f"    {end_label}:")

            lines.append(f"    rt_int_clear(&{stop_temp});")
            lines.append(f"    rt_int_clear(&{step_temp});")

        elif isinstance(stmt, TryExcept):
            ctx = state.next_temp(type_hint="rt_try_ctx")
            flag = state.next_temp(type_hint="int")
            lines.append(f"    rt_try_ctx {ctx};")
            lines.append(f"    rt_try_push(&{ctx});")
            lines.append(f"    int {flag} = setjmp({ctx}.env);")
            lines.append(f"    if ({flag} == 0) {{")
            body_var_types = dict(var_types)
            body_declared = set(declared_vars)
            _emit_block(stmt.body, lines, state, body_var_types, fn_sigs,
                       in_loop, break_label, continue_label, body_declared)
            lines.append(f"        rt_try_pop(&{ctx});")
            lines.append("    } else {")
            if stmt.exc_name is None:
                lines.append("        rt_exc_clear();")
                lines.append(f"        rt_try_pop(&{ctx});")
                handler_var_types = dict(var_types)
                handler_declared = set(declared_vars)
                _emit_block(stmt.handler, lines, state, handler_var_types, fn_sigs,
                           in_loop, break_label, continue_label, handler_declared)
            else:
                enumv = _exc_enum(stmt.exc_name)
                lines.append(f"        if (rt_exc_is({enumv})) {{")
                lines.append("            rt_exc_clear();")
                lines.append(f"            rt_try_pop(&{ctx});")
                handler_var_types = dict(var_types)
                handler_declared = set(declared_vars)
                _emit_block(stmt.handler, lines, state, handler_var_types, fn_sigs,
                           in_loop, break_label, continue_label, handler_declared)
                lines.append("        } else {")
                lines.append(f"            rt_try_pop(&{ctx});")
                lines.append("            rt_reraise();")
                lines.append("        }")
            lines.append("    }")

        elif isinstance(stmt, Raise):
            enumv = _exc_enum(stmt.exc_name)
            msg = stmt.message if stmt.message is not None else ""
            msg_c = msg.replace('\\', r'\\').replace('"', r'\\"')
            lines.append(f"    rt_raise({enumv}, \"{msg_c}\", \"<source>\", {stmt.lineno});")

        elif isinstance(stmt, Return):
            expr_result = _emit_expr(stmt.expr, lines, state, var_types, fn_sigs)
            lines.append(f"    rt_int_copy(out, {expr_result});")

        elif isinstance(stmt, Break):
            if not in_loop or not break_label:
                raise ValueError("Break outside of loop")
            lines.append(f"    goto {break_label};")

        elif isinstance(stmt, Continue):
            if not in_loop or not continue_label:
                raise ValueError("Continue outside of loop")
            lines.append(f"    goto {continue_label};")


def _emit_class_struct(class_def: ClassDef) -> List[str]:
    """Emit C struct definition for a class.

    Args:
        class_def: Class definition IR

    Returns:
        List of C code lines
    """
    lines = []
    lines.append(f"typedef struct {{")
    # All fields are rt_int for now
    for field in class_def.fields:
        lines.append(f"    rt_int {field};")
    lines.append(f"}} pcc_class_{class_def.name};")
    lines.append("")
    return lines


def _emit_class_constructor(class_def: ClassDef) -> List[str]:
    """Emit C constructor function for a class.

    Args:
        class_def: Class definition IR

    Returns:
        List of C code lines
    """
    lines = []
    lines.append(f"static pcc_class_{class_def.name}* pcc_new_{class_def.name}(void) {{")
    lines.append(f"    pcc_class_{class_def.name}* obj = malloc(sizeof(pcc_class_{class_def.name}));")
    lines.append("    if (!obj) return NULL;")

    # Initialize all fields
    for field in class_def.fields:
        lines.append(f"    rt_int_init(&obj->{field});")

    lines.append("    return obj;")
    lines.append("}")
    lines.append("")
    return lines


def _emit_class_destructor(class_def: ClassDef) -> List[str]:
    """Emit C destructor function for a class.

    Args:
        class_def: Class definition IR

    Returns:
        List of C code lines
    """
    lines = []
    lines.append(f"static void pcc_delete_{class_def.name}(pcc_class_{class_def.name}* obj) {{")
    lines.append("    if (!obj) return;")

    # Clear all fields
    for field in class_def.fields:
        lines.append(f"    rt_int_clear(&obj->{field});")

    lines.append("    free(obj);")
    lines.append("}")
    lines.append("")
    return lines


def _emit_method(class_def: ClassDef, fn: FunctionDef, fn_sigs: Dict[str, int]) -> List[str]:
    """Emit C code for a method definition.

    Args:
        class_def: Class definition IR
        fn: Method definition IR
        fn_sigs: Function signatures map

    Returns:
        List of C code lines
    """
    lines = []
    params = ", ".join([f"rt_int* pcc_p_{p}" for p in fn.params])
    if params:
        params = ", " + params
    lines.append(f"static void pcc_method_{class_def.name}_{fn.name}(pcc_class_{class_def.name}* self, rt_int* out{params}) {{")

    state = _CodegenState()
    var_types: Dict[str, str] = {}

    # 'self' is available in the method
    var_types["self"] = f"pcc_class_{class_def.name}"

    # Initialize parameters
    for p in fn.params:
        var_types[p] = "rt_int"
        lines.append(f"    rt_int {p}; rt_int_init(&{p});")
        lines.append(f"    rt_int_copy(&{p}, pcc_p_{p});")

    fn_declared: Set[str] = set()
    _emit_block(fn.body, lines, state, var_types, fn_sigs, declared_vars=fn_declared)

    # Cleanup locals (excluding 'self' and parameters)
    for name, ctype in var_types.items():
        if name == "self" or name in fn.params:
            continue
        if ctype == "rt_str":
            lines.append(f"    rt_str_clear(&{name});")
        elif ctype == "rt_int":
            lines.append(f"    rt_int_clear(&{name});")

    lines.append("}")
    lines.append("")
    return lines


def _emit_function(fn: FunctionDef, fn_sigs: Dict[str, int]) -> List[str]:
    """Emit C code for a function definition.

    Args:
        fn: Function definition IR
        fn_sigs: Function signatures map

    Returns:
        List of C code lines
    """
    lines = []
    params = ", ".join([f"rt_int* pcc_p_{p}" for p in fn.params])
    lines.append(f"static void pcc_fn_{fn.name}(rt_int* out, {params}) {{")

    state = _CodegenState()
    var_types: Dict[str, str] = {}

    # Initialize parameters
    for p in fn.params:
        var_types[p] = "rt_int"
        lines.append(f"    rt_int {p}; rt_int_init(&{p});")
        lines.append(f"    rt_int_copy(&{p}, pcc_p_{p});")

    fn_declared: Set[str] = set()
    _emit_block(fn.body, lines, state, var_types, fn_sigs, declared_vars=fn_declared)

    # Cleanup locals
    for name, ctype in var_types.items():
        if ctype == "rt_str":
            lines.append(f"    rt_str_clear(&{name});")
        else:
            lines.append(f"    rt_int_clear(&{name});")

    lines.append("}")
    lines.append("")
    return lines


class CodeGenerator:
    """C code generator for pcc.

    Converts the intermediate representation (IR) into C source code
    that can be compiled with the pcc runtime library.

    Example:
        >>> from pcc.core import Compiler
        >>> compiler = Compiler()
        >>> ir = compiler.parse("print(1 + 2)")
        >>> codegen = CodeGenerator()
        >>> c_source = codegen.generate(ir)
        >>> print(c_source.c_source)
    """

    def generate(self, module: ModuleIR) -> CSource:
        """Convert the IR module to C source code.

        Args:
            module: The IR module containing functions and main statements

        Returns:
            CSource object containing the generated C code
        """
        lines = []
        lines.append("// Generated by pcc MVP with BigInt support")
        lines.append("#include <stdio.h>")
        lines.append("#include <stdlib.h>")
        lines.append("#include <setjmp.h>")
        lines.append("#include \"runtime.h\"")
        lines.append("")

        # Build function signatures map
        fn_sigs: Dict[str, int] = {}
        for fn in module.functions:
            fn_sigs[fn.name] = len(fn.params)

        # Emit class struct definitions
        for class_def in module.classes:
            lines.extend(_emit_class_struct(class_def))

        # Emit function forward declarations (prototypes)
        for fn in module.functions:
            params = ", ".join([f"rt_int* pcc_p_{p}" for p in fn.params])
            lines.append(f"static void pcc_fn_{fn.name}(rt_int* out, {params});")

        # Emit method forward declarations
        for class_def in module.classes:
            for method in class_def.methods:
                params = ", ".join([f"rt_int* pcc_p_{p}" for p in method.params])
                if params:
                    params = ", " + params
                lines.append(f"static void pcc_method_{class_def.name}_{method.name}(pcc_class_{class_def.name}* self, rt_int* out{params});")
        lines.append("")

        # Emit class constructors and destructors
        for class_def in module.classes:
            lines.extend(_emit_class_constructor(class_def))
            lines.extend(_emit_class_destructor(class_def))

        # Emit function definitions
        for fn in module.functions:
            lines.extend(_emit_function(fn, fn_sigs))

        # Emit method definitions
        for class_def in module.classes:
            for method in class_def.methods:
                lines.extend(_emit_method(class_def, method, fn_sigs))

        # Emit main function
        lines.append("int main(void) {")

        state = _CodegenState()
        var_types: Dict[str, str] = {}

        main_declared: Set[str] = set()
        _emit_block(module.main, lines, state, var_types, fn_sigs, declared_vars=main_declared)

        # Cleanup main locals
        for name, ctype in var_types.items():
            if ctype == "rt_str":
                lines.append(f"    rt_str_clear(&{name});")
            elif ctype.startswith("pcc_class_"):
                # Object pointers are not cleaned up here to avoid double-free
                # They will be cleaned up when the program exits
                pass
            else:
                lines.append(f"    rt_int_clear(&{name});")

        lines.append("    return 0;")
        lines.append("}")

        return CSource(c_source="\n".join(lines))