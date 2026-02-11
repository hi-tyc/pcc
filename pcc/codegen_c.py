from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Set, Tuple, Optional

from .frontend import (
    ModuleIR, FunctionDef,
    Assign, Print, If, While, Return,
    Break, Continue, ForRange,
    IntConst, StrConst, Var, BinOp, BoolOp, UnaryOp, CmpOp, Call, Expr, Stmt,
)

@dataclass(frozen=True)
class CEmitResult:
    c_source: str

def _c_ident(name: str) -> str:
    return f"pcc_{name}"

def _c_fn_ident(name: str) -> str:
    return f"pcc_fn_{name}"

# ---------------- type system ----------------
Type = str  # "int" | "str" | "bool"

def infer_expr_type(e: Expr, tenv: Dict[str, Type]) -> Type:
    if isinstance(e, IntConst):
        return "int"
    if isinstance(e, StrConst):
        return "str"
    if isinstance(e, Var):
        if e.name not in tenv:
            raise SyntaxError(f"Type error: variable '{e.name}' used before assignment")
        return tenv[e.name]
    if isinstance(e, Call):
        if e.func in ("len", "int", "pow"):
            return "int"
        if e.func == "input":
            return "str"
        # In this compiler, functions return int only (BigInt) for this stage
        return "int"
    if isinstance(e, UnaryOp):
        if e.op != "not":
            raise SyntaxError(f"Unsupported unary op: {e.op}")
        ot = infer_expr_type(e.operand, tenv)
        if ot not in ("bool", "int"):
            raise SyntaxError("Type error: 'not' only supports bool/int in this stage")
        return "bool"
    if isinstance(e, BoolOp):
        lt = infer_expr_type(e.left, tenv)
        rt = infer_expr_type(e.right, tenv)
        if lt not in ("bool", "int") or rt not in ("bool", "int"):
            raise SyntaxError("Type error: 'and/or' only supports bool/int in this stage")
        if e.op not in ("and", "or"):
            raise SyntaxError(f"Unsupported bool op: {e.op}")
        return "bool"
    if isinstance(e, CmpOp):
        lt = infer_expr_type(e.left, tenv)
        rt = infer_expr_type(e.right, tenv)
        if lt == "int" and rt == "int":
            return "bool"
        if lt == "str" and rt == "str":
            return "bool"
        raise SyntaxError("Type error: comparisons only supported on int or str (both operands must be same type)")
    if isinstance(e, BinOp):
        lt = infer_expr_type(e.left, tenv)
        rt = infer_expr_type(e.right, tenv)
        if e.op == "+":
            if lt == "int" and rt == "int":
                return "int"
            if lt == "str" and rt == "str":
                return "str"
            raise SyntaxError("Type error: '+' requires both int or both str")
        if e.op in ("-", "*", "**"):
            if lt == "int" and rt == "int":
                return "int"
            raise SyntaxError(f"Type error: operator '{e.op}' only supports int")
        if e.op in ("//", "%"):
            if lt == "int" and rt == "int":
                return "int"
            raise SyntaxError(f"Type error: operator '{e.op}' only supports int")
        raise SyntaxError(f"Unsupported operator: {e.op}")
    raise TypeError(f"Unknown expr node: {type(e).__name__}")

def merge_tenv(a: Dict[str, Type], b: Dict[str, Type]) -> Dict[str, Type]:
    out = dict(a)
    for k, vt in b.items():
        if k in out and out[k] != vt:
            raise SyntaxError(f"Type error: variable '{k}' assigned incompatible types ({out[k]} vs {vt})")
        out[k] = vt
    return out

def infer_stmt_types(stmts: List[Stmt], tenv_in: Dict[str, Type]) -> Dict[str, Type]:
    tenv = dict(tenv_in)
    for s in stmts:
        if isinstance(s, Assign):
            t = infer_expr_type(s.expr, tenv)
            if s.name in tenv and tenv[s.name] != t:
                raise SyntaxError(f"Type error: variable '{s.name}' reassigned from {tenv[s.name]} to {t}")
            tenv[s.name] = t
        elif isinstance(s, Print):
            infer_expr_type(s.expr, tenv)
        elif isinstance(s, Return):
            rt = infer_expr_type(s.expr, tenv)
            if rt != "int":
                raise SyntaxError("Type error: return value must be int in this stage")
        elif isinstance(s, If):
            ct = infer_expr_type(s.test, tenv)
            if ct not in ("bool", "int"):
                raise SyntaxError("Type error: if condition must be int/bool")
            tenv_body = infer_stmt_types(s.body, tenv)
            tenv_else = infer_stmt_types(s.orelse, tenv)
            tenv = merge_tenv(tenv_body, tenv_else)
        elif isinstance(s, While):
            ct = infer_expr_type(s.test, tenv)
            if ct not in ("bool", "int"):
                raise SyntaxError("Type error: while condition must be int/bool")
            tenv_body = infer_stmt_types(s.body, tenv)
            tenv = merge_tenv(tenv, tenv_body)
        elif isinstance(s, ForRange):
            # range args must be int
            if infer_expr_type(s.start, tenv) != "int" or infer_expr_type(s.stop, tenv) != "int" or infer_expr_type(s.step, tenv) != "int":
                raise SyntaxError("Type error: range(start, stop, step) args must be int")
            tenv2 = dict(tenv)
            tenv2[s.var] = "int"
            tenv_body = infer_stmt_types(s.body, tenv2)
            tenv = merge_tenv(tenv, tenv_body)
        elif isinstance(s, (Break, Continue)):
            pass
        else:
            raise TypeError(f"Unknown stmt: {type(s).__name__}")
    return tenv

# ---------------- utilities ----------------

def c_escape_string(s: str) -> str:
    out = []
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == "\"":
            out.append("\\\"")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        else:
            out.append(ch)
    return "\"" + "".join(out) + "\""

_tmp_counter = 0
def new_tmp(prefix: str) -> str:
    global _tmp_counter
    _tmp_counter += 1
    return f"pcc_tmp_{prefix}_{_tmp_counter}"

def _collect_assigned_vars(stmts: List[Stmt], out: Set[str]) -> None:
    for s in stmts:
        if isinstance(s, Assign):
            out.add(s.name)
        elif isinstance(s, If):
            _collect_assigned_vars(s.body, out)
            _collect_assigned_vars(s.orelse, out)
        elif isinstance(s, While):
            _collect_assigned_vars(s.body, out)
        elif isinstance(s, ForRange):
            out.add(s.var)
            _collect_assigned_vars(s.body, out)
        elif isinstance(s, (Return, Break, Continue, Print)):
            pass

# ---------------- expression emission ----------------
# For BigInt, expressions are evaluated into rt_int temporaries.
# Return tuple:
#   kind: "int"/"str"/"bool"
#   code: for int/str -> name of var/temp (rt_int or rt_str); for bool -> C expression string
#   pre: list of statements (decl/init/ops)
#   post: list of statements (cleanup temps to free)
#   owns: for int/str, whether caller must clear/free the returned object (temp)
#   is_ptr: for int, whether the code is already a pointer (i.e., function param)
def emit_expr(e: Expr, sym: Dict[str, str], fn_sym: Dict[str, str], tenv: Dict[str, Type], is_ptr_param: Dict[str, bool] = None) -> Tuple[Type, str, List[str], List[str], bool, bool]:
    if is_ptr_param is None:
        is_ptr_param = {}
    # int constant -> temp rt_int
    if isinstance(e, IntConst):
        t = new_tmp("int")
        pre = [f"rt_int {t}; rt_int_init(&{t});"]
        # choose set_si vs from_dec
        v = int(e.value)
        # check 64-bit range
        if -2**63 <= v <= 2**63 - 1:
            pre.append(f"rt_int_set_si(&{t}, {v}LL);")
        else:
            pre.append(f"rt_int_from_dec(&{t}, {c_escape_string(str(v))});")
        post = [f"rt_int_clear(&{t});"]
        return ("int", t, pre, post, True, False)

    if isinstance(e, StrConst):
        t = new_tmp("str")
        lit = c_escape_string(e.value)
        pre = [f"rt_str {t} = rt_str_from_cstr({lit});"]
        post = [f"rt_str_free(&{t});"]
        return ("str", t, pre, post, True, False)

    if isinstance(e, Var):
        is_ptr = is_ptr_param.get(e.name, False)
        return (tenv[e.name], sym[e.name], [], [], False, is_ptr)

    if isinstance(e, Call):
        if e.func == "input":
            t = new_tmp("str")
            tmp_raw = f"raw_{t}"
            pre: List[str] = []
            post: List[str] = []

            if len(e.args) == 0:
                pre.append(f"char* {tmp_raw} = rt_input();")
            elif len(e.args) == 1:
                pt, pc, ppre, ppost, powns, p_is_ptr = emit_expr(e.args[0], sym, fn_sym, tenv, is_ptr_param)
                if pt != "str":
                    raise SyntaxError("Type error: input(prompt) expects a str")
                pre.extend(ppre)
                pre.append(f"char* {tmp_raw} = rt_input_prompt({pc});")
                if powns:
                    post += ppost
            else:
                raise SyntaxError("input() takes 0 or 1 positional arguments")

            pre.append(f"rt_str {t} = rt_str_from_cstr({tmp_raw});")
            pre.append(f"free({tmp_raw});")
            post.append(f"rt_str_free(&{t});")
            return ("str", t, pre, post, True, False)

        # len(str) -> int
        if e.func == "len":
            if len(e.args) != 1:
                raise SyntaxError("len() expects exactly 1 argument")
            at, ac, apre, apost, aowns, a_is_ptr = emit_expr(e.args[0], sym, fn_sym, tenv, is_ptr_param)
            if at != "str":
                raise SyntaxError("TypeError: object of type is not supported for len() yet")
            t = new_tmp("int")
            pre: List[str] = []
            pre.extend(apre)
            pre.append(f"rt_int {t};")
            pre.append(f"rt_int_init(&{t});")
            pre.append(f"rt_str_len(&{t}, &{ac});")
            post: List[str] = []
            if aowns:
                post += apost
            post.append(f"rt_int_clear(&{t});")
            return ("int", t, pre, post, True, False)

        # int(str) -> int (BigInt), raise ValueError on bad literal
        if e.func == "int":
            if len(e.args) != 1:
                raise SyntaxError("int() expects exactly 1 argument")
            at, ac, apre, apost, aowns, a_is_ptr = emit_expr(e.args[0], sym, fn_sym, tenv, is_ptr_param)
            if at != "str":
                raise SyntaxError("TypeError: int() currently only supports int(str)")
            t = new_tmp("int")
            pre: List[str] = []
            pre.extend(apre)
            pre.append(f"rt_int {t};")
            pre.append(f"rt_int_init(&{t});")
            pre.append(f"rt_int_from_dec_or_raise(&{t}, {ac}.data);")
            post: List[str] = []
            if aowns:
                post += apost
            post.append(f"rt_int_clear(&{t});")
            return ("int", t, pre, post, True, False)
            if len(e.args) != 1:
                raise SyntaxError("len() expects exactly 1 argument")
            at, ac, apre, apost, aowns, a_is_ptr = emit_expr(e.args[0], sym, fn_sym, tenv, is_ptr_param)
            if at != "str":
                raise SyntaxError("Type error: len() currently only supports str")

            t = new_tmp("int")
            pre: List[str] = []
            pre.extend(apre)
            pre.append(f"rt_int {t}; rt_int_init(&{t});")
            pre.append(f"rt_str_len(&{t}, &{ac});")

            post: List[str] = []
            if aowns:
                post += apost
            post.append(f"rt_int_clear(&{t});")
            return ("int", t, pre, post, True, False)

        # Functions return int (rt_int via out param) in this stage
        t = new_tmp("int")
        pre = [f"rt_int {t}; rt_int_init(&{t});"]
        post: List[str] = [f"rt_int_clear(&{t});"]

        arg_refs: List[str] = []
        for a in e.args:
            at, ac, apre, apost, aowns, a_is_ptr = emit_expr(a, sym, fn_sym, tenv, is_ptr_param)
            if at != "int":
                raise SyntaxError("Type error: function arguments must be int in this stage")
            pre.extend(apre)
            # pass rt_int* (if already pointer, pass directly; otherwise take address)
            arg_refs.append(f"{ac}" if a_is_ptr else f"&{ac}")
            # cleanup arg temps after call
            post = apost + post if aowns else post  # ensure args cleared before result
        if e.func == "pow":
            if len(arg_refs) == 2:
                pre.append(f"rt_int_pow(&{t}, {arg_refs[0]}, {arg_refs[1]});")
            else:
                pre.append(f"rt_int_powmod(&{t}, {arg_refs[0]}, {arg_refs[1]}, {arg_refs[2]});")
            return ("int", t, pre, post, True, False)
        cfn = fn_sym[e.func]
        pre.append(f"{cfn}(&{t}, {', '.join(arg_refs)});")
        return ("int", t, pre, post, True, False)

    if isinstance(e, UnaryOp):
        # Only: not <expr>
        ot, oc, opre, opost, oowns, o_is_ptr = emit_expr(e.operand, sym, fn_sym, tenv, is_ptr_param)
        pre = list(opre)
        post = []
        if oowns:
            post += opost
        if ot == "bool":
            return ("bool", f"(!({oc}))", pre, post, False, False)
        if ot == "int":
            oc_ref = oc if o_is_ptr else f"&{oc}"
            return ("bool", f"(!rt_int_truthy({oc_ref}))", pre, post, False, False)
        raise SyntaxError("Type error: 'not' only supports bool/int in this stage")

    if isinstance(e, BoolOp):
        # Short-circuit semantics with a temp C int
        lt, lc, lpre, lpost, lowns, l_is_ptr = emit_expr(e.left, sym, fn_sym, tenv, is_ptr_param)
        rt, rc, rpre, rpost, rowns, r_is_ptr = emit_expr(e.right, sym, fn_sym, tenv, is_ptr_param)
        tmp = new_tmp("bool")
        bvar = f"__b_{tmp}"
        pre: List[str] = []
        post: List[str] = []
        pre.append(f"int {bvar} = 0;")

        # Evaluate left
        pre.extend(lpre)
        if lt == "bool":
            pre.append(f"{bvar} = ({lc}) ? 1 : 0;")
        elif lt == "int":
            lc_ref = lc if l_is_ptr else f"&{lc}"
            pre.append(f"{bvar} = rt_int_truthy({lc_ref});")
        else:
            raise SyntaxError("Type error: 'and/or' only supports bool/int in this stage")
        if lowns:
            pre.extend(lpost)

        if e.op == "and":
            pre.append(f"if ({bvar}) {{")
        elif e.op == "or":
            pre.append(f"if (!{bvar}) {{")
        else:
            raise SyntaxError(f"Unsupported bool op: {e.op}")

        # Evaluate right only if needed
        for ln in rpre:
            pre.append(f"    {ln}")
        if rt == "bool":
            pre.append(f"    {bvar} = ({rc}) ? 1 : 0;")
        elif rt == "int":
            rc_ref = rc if r_is_ptr else f"&{rc}"
            pre.append(f"    {bvar} = rt_int_truthy({rc_ref});")
        else:
            raise SyntaxError("Type error: 'and/or' only supports bool/int in this stage")
        if rowns:
            for ln in rpost:
                pre.append(f"    {ln}")
        pre.append("}")

        return ("bool", bvar, pre, post, False, False)

    if isinstance(e, CmpOp):
        # bool: produce C int expression
        lt, lc, lpre, lpost, lowns, l_is_ptr = emit_expr(e.left, sym, fn_sym, tenv, is_ptr_param)
        rt, rc, rpre, rpost, rowns, r_is_ptr = emit_expr(e.right, sym, fn_sym, tenv, is_ptr_param)

        pre = lpre + rpre
        post = []
        # clear temps after use
        if lowns: post += lpost
        if rowns: post += rpost

        op = e.op

        # string comparison
        if lt == "str" and rt == "str":
            if op == "==":
                expr = f"(rt_str_eq({lc}, {rc}) == 0)"
            elif op == "!=":
                expr = f"(rt_str_eq({lc}, {rc}) != 0)"
            else:
                raise SyntaxError(f"Unsupported compare op for strings: {op}")
            return ("bool", expr, pre, post, False, False)

        # int comparison
        if lt == "int" and rt == "int":
            lc_ref = lc if l_is_ptr else f"&{lc}"
            rc_ref = rc if r_is_ptr else f"&{rc}"
            if op == "==":
                expr = f"(rt_int_cmp({lc_ref}, {rc_ref}) == 0)"
            elif op == "!=":
                expr = f"(rt_int_cmp({lc_ref}, {rc_ref}) != 0)"
            elif op == "<":
                expr = f"(rt_int_cmp({lc_ref}, {rc_ref}) < 0)"
            elif op == "<=":
                expr = f"(rt_int_cmp({lc_ref}, {rc_ref}) <= 0)"
            elif op == ">":
                expr = f"(rt_int_cmp({lc_ref}, {rc_ref}) > 0)"
            elif op == ">=":
                expr = f"(rt_int_cmp({lc_ref}, {rc_ref}) >= 0)"
            else:
                raise SyntaxError(f"Unsupported compare op: {op}")
            return ("bool", expr, pre, post, False, False)

        raise SyntaxError("Type error: comparisons only supported on int or str (both operands must be same type)")

    if isinstance(e, BinOp):
        # BigInt supports + - * // % (Python floor semantics for // and %)

        lt, lc, lpre, lpost, lowns, l_is_ptr = emit_expr(e.left, sym, fn_sym, tenv, is_ptr_param)
        rt, rc, rpre, rpost, rowns, r_is_ptr = emit_expr(e.right, sym, fn_sym, tenv, is_ptr_param)

        # string concat
        if e.op == "+" and lt == "str" and rt == "str":
            t = new_tmp("str")
            pre = lpre + rpre + [f"rt_str {t} = rt_str_concat({lc}, {rc});"]
            post = []
            if lowns: post += lpost
            if rowns: post += rpost
            post += [f"rt_str_free(&{t});"]
            return ("str", t, pre, post, True, False)

        # bigint + - *
        if lt == "int" and rt == "int":
            t = new_tmp("int")
            pre = lpre + rpre + [f"rt_int {t}; rt_int_init(&{t});"]
            lc_ref = lc if l_is_ptr else f"&{lc}"
            rc_ref = rc if r_is_ptr else f"&{rc}"
            if e.op == "+":
                pre.append(f"rt_int_add(&{t}, {lc_ref}, {rc_ref});")
            elif e.op == "-":
                pre.append(f"rt_int_sub(&{t}, {lc_ref}, {rc_ref});")
            elif e.op == "*":
                pre.append(f"rt_int_mul(&{t}, {lc_ref}, {rc_ref});")
            elif e.op == "**":
                pre.append(f"rt_int_pow(&{t}, {lc_ref}, {rc_ref});")
            elif e.op == "//":
                # compile-time div-by-zero if RHS is constant 0
                if isinstance(e.right, IntConst) and int(e.right.value) == 0:
                    raise SyntaxError(f"Division by zero in '//' at line {getattr(e, 'lineno', '?')}")
                pre.append(f"rt_int_floordiv(&{t}, {lc_ref}, {rc_ref});")
            elif e.op == "%":
                if isinstance(e.right, IntConst) and int(e.right.value) == 0:
                    raise SyntaxError(f"Division by zero in '%' at line {getattr(e, 'lineno', '?')}")
                pre.append(f"rt_int_mod(&{t}, {lc_ref}, {rc_ref});")
            else:
                raise SyntaxError(f"Unsupported op: {e.op}")

            post = []
            if lowns: post += lpost
            if rowns: post += rpost
            post += [f"rt_int_clear(&{t});"]
            return ("int", t, pre, post, True, False)

        # mixed
        if e.op == "+":
            raise SyntaxError("Type error: '+' requires both int or both str")
        raise SyntaxError(f"Type error: operator '{e.op}' only supports int (or str+str for '+')")

    raise TypeError(f"Unknown expr node: {type(e).__name__}")

# ---------------- statement emission ----------------

def _emit_block(

    stmts: List[Stmt],

    sym: Dict[str, str],

    fn_sym: Dict[str, str],

    tenv: Dict[str, Type],

    indent: int,

    loop_depth: int,

    is_ptr_param: Dict[str, bool] = None,

    locals: Set[str] = None,

) -> List[str]:

    if is_ptr_param is None:

        is_ptr_param = {}

    if locals is None:

        locals = set()

    pad = " " * indent

    lines: List[str] = []



    for s in stmts:

        if isinstance(s, Assign):

            t = tenv[s.name]

            et, ec, pre, post, owns, e_is_ptr = emit_expr(s.expr, sym, fn_sym, tenv, is_ptr_param)

            if et != t:

                raise SyntaxError(f"Type error: assigning {et} to {t} variable '{s.name}'")



            for ln in pre:

                lines.append(pad + ln)



            dst = sym[s.name]

            if t == "int":

                # copy bigint into existing initialized variable

                ec_ref = ec if e_is_ptr else f"&{ec}"

                lines.append(f"{pad}rt_int_copy(&{dst}, {ec_ref});")

            else:

                # str: free old then assign/copy

                lines.append(f"{pad}rt_str_free(&{dst});")

                lines.append(f"{pad}{dst} = {ec};")

                # if ec is temp, ownership moved; avoid double-free by skipping its post free

                if owns:

                    # remove the last free if it exists; safer: just don't emit post for this assignment

                    post = []



            for ln in post:

                lines.append(pad + ln)



        elif isinstance(s, Print):

            et, ec, pre, post, owns, e_is_ptr = emit_expr(s.expr, sym, fn_sym, tenv, is_ptr_param)

            for ln in pre:

                lines.append(pad + ln)



            if et == "int":

                ec_ref = ec if e_is_ptr else f"&{ec}"

                lines.append(f"{pad}rt_print_int({ec_ref});")

            elif et == "str":

                lines.append(f"{pad}rt_print_str({ec});")

            elif et == "bool":

                            # bool prints as True/False to match Python semantics

                            lines.append(f"{pad}printf(\"%s\\n\", ({ec}) ? \"True\" : \"False\");")

            else:

                raise SyntaxError(f"Unsupported print type: {et}")



            for ln in post:

                lines.append(pad + ln)



            # if str temp, its post already frees; ok



        elif isinstance(s, If):

                    tt, tc, pre, post, _, t_is_ptr = emit_expr(s.test, sym, fn_sym, tenv, is_ptr_param)

                    if tt != "bool":

                        raise SyntaxError("Type error: if condition must be bool")

                    for ln in pre:

                        lines.append(pad + ln)

                    if tt == "bool":
                        cond = f"({tc})"
                    else:
                        tc_ref = tc if t_is_ptr else f"&{tc}"
                        cond = f"(rt_int_truthy({tc_ref}))"

                    lines.append(f"{pad}if {cond} {{")



                    lines.extend(_emit_block(s.body, sym, fn_sym, tenv, indent + 4, loop_depth, is_ptr_param, locals))



                    lines.append(f"{pad}}}")



                    if s.orelse:



                        lines.append(f"{pad}else {{")



                        lines.extend(_emit_block(s.orelse, sym, fn_sym, tenv, indent + 4, loop_depth, is_ptr_param, locals))



                        lines.append(f"{pad}}}")



        



                    for ln in post:



                        lines.append(pad + ln)



        elif isinstance(s, While):

                    tt, tc, pre, post, _, t_is_ptr = emit_expr(s.test, sym, fn_sym, tenv, is_ptr_param)

                    if tt != "bool":

                        raise SyntaxError("Type error: while condition must be bool")

                    if tt == "bool":
                        cond_expr = f"({tc})"
                    else:
                        tc_ref = tc if t_is_ptr else f"&{tc}"
                        cond_expr = f"(rt_int_truthy({tc_ref}))"

                    # Evaluate condition each iter; free temps immediately so 'continue' can't skip cleanup.
                    # while (1) { <pre>; int cond = <tc>; <post>; if (!cond) break; <body>; }



                    cond_tmp = new_tmp("whilecond")



                    cond_var = f"__cond_{cond_tmp}"



        



                    lines.append(f"{pad}while (1) {{")



                    for ln in pre:



                        lines.append(f"{pad}    {ln}")



                    lines.append(f"{pad}    int {cond_var} = {cond_expr};")



                    for ln in post:



                        lines.append(f"{pad}    {ln}")



                    lines.append(f"{pad}    if (!{cond_var}) {{")



                    lines.append(f"{pad}        break;")



                    lines.append(f"{pad}    }}")



                    lines.extend(_emit_block(s.body, sym, fn_sym, tenv, indent + 4, loop_depth + 1, is_ptr_param, locals))



                    lines.append(f"{pad}}}")



        elif isinstance(s, ForRange):

            # Evaluate start/stop/step BigInt -> long long checked, then for-loop over long long.

            ivar = sym[s.var]

            st, sc, spre, spost, _, s_is_ptr = emit_expr(s.start, sym, fn_sym, tenv, is_ptr_param)

            et, ec, epre, epost, _, e_is_ptr = emit_expr(s.stop, sym, fn_sym, tenv, is_ptr_param)

            pt, pc, ppre, ppost, _, p_is_ptr = emit_expr(s.step, sym, fn_sym, tenv, is_ptr_param)

            if st != "int" or et != "int" or pt != "int":

                raise SyntaxError("Type error: range args must be int")



            tmp = new_tmp("rng")

            tstart_ll = f"{tmp}_start_ll"

            tstop_ll = f"{tmp}_stop_ll"

            tstep_ll = f"{tmp}_step_ll"



            lines.append(f"{pad}{{")

            # pre compute bigint args

            for ln in (spre + epre + ppre):

                lines.append(f"{pad}    {ln}")

            lines.append(f"{pad}    long long {tstart_ll};")

            lines.append(f"{pad}    long long {tstop_ll};")

            lines.append(f"{pad}    long long {tstep_ll};")

            sc_ref = sc if s_is_ptr else f"&{sc}"

            ec_ref = ec if e_is_ptr else f"&{ec}"

            pc_ref = pc if p_is_ptr else f"&{pc}"

            lines.append(f"{pad}    if (!rt_int_to_si_checked({sc_ref}, &{tstart_ll}) || !rt_int_to_si_checked({ec_ref}, &{tstop_ll}) || !rt_int_to_si_checked({pc_ref}, &{tstep_ll})) {{")

            lines.append(f'{pad}        puts("pcc runtime error: range() arguments too large for this stage");')

            lines.append(f"{pad}        exit(1);")

            lines.append(f"{pad}    }}")

            # free bigint temps

            for ln in (spost + epost + ppost):

                lines.append(f"{pad}    {ln}")

            # runtime check for step==0

            lines.append(f"{pad}    if ({tstep_ll} == 0) {{")

            lines.append(f'{pad}        puts("pcc runtime error: range() step must not be 0");')

            lines.append(f"{pad}        exit(1);")

            lines.append(f"{pad}    }}")

            # use long long loop
            lines.append(f"{pad}    if ({tstep_ll} > 0) {{")
            lines.append(f"{pad}        for (long long __i = {tstart_ll}; __i < {tstop_ll}; __i += {tstep_ll}) {{")
            lines.append(f"{pad}            rt_int_set_si(&{ivar}, __i);")
            lines.extend(_emit_block(s.body, sym, fn_sym, tenv, indent + 16, loop_depth + 1, is_ptr_param, locals))
            lines.append(f"{pad}        }}")
            lines.append(f"{pad}    }} else {{")
            lines.append(f"{pad}        for (long long __i = {tstart_ll}; __i > {tstop_ll}; __i += {tstep_ll}) {{")
            lines.append(f"{pad}            rt_int_set_si(&{ivar}, __i);")
            lines.extend(_emit_block(s.body, sym, fn_sym, tenv, indent + 16, loop_depth + 1, is_ptr_param, locals))
            lines.append(f"{pad}        }}")
            lines.append(f"{pad}    }}")
            lines.append(f"{pad}}}")



        elif isinstance(s, Return):



                    et, ec, pre, post, owns, e_is_ptr = emit_expr(s.expr, sym, fn_sym, tenv, is_ptr_param)



                    if et != "int":



                        raise SyntaxError("Type error: return value must be int in this stage")



                    for ln in pre:



                        lines.append(pad + ln)



                    # For BigInt return, we use out param: return rt_int_copy(out, &expr)



                    # In this stage, functions take out param as first arg



                    ec_ref = ec if e_is_ptr else f"&{ec}"



                    lines.append(f"{pad}rt_int_copy(__pcc_out, {ec_ref});")



                    # Clear expression temps



                    for ln in post:



                        lines.append(pad + ln)



                    # Clear all local variables before return to avoid leaks



                    for v in sorted(locals):



                        if tenv.get(v, "int") == "int":



                            lines.append(f"{pad}rt_int_clear(&{sym[v]});")



                        else:



                            lines.append(f"{pad}rt_str_free(&{sym[v]});")



                    lines.append(f"{pad}return;")



        elif isinstance(s, Break):

            if loop_depth <= 0:

                raise SyntaxError(f"break used outside loop (line {s.lineno})")

            lines.append(f"{pad}break;")



        elif isinstance(s, Continue):

            if loop_depth <= 0:

                raise SyntaxError(f"continue used outside loop (line {s.lineno})")

            lines.append(f"{pad}continue;")



        else:

            raise TypeError(f"Unknown stmt node: {type(s).__name__}")



    return lines

def _has_return(stmts: List[Stmt]) -> bool:
    for s in stmts:
        if isinstance(s, Return):
            return True
        if isinstance(s, If):
            if _has_return(s.body) or _has_return(s.orelse):
                return True
        if isinstance(s, While):
            if _has_return(s.body):
                return True
    return False

def emit_c(module: ModuleIR) -> CEmitResult:
    """
    Backend: IR -> C main.c
    Uses BigInt (rt_int) for int type, rt_str for str type
    """
    # Function table: Python name -> C name
    fn_sym: Dict[str, str] = {f.name: _c_fn_ident(f.name) for f in module.functions}

    lines: list[str] = []
    lines.append("// Generated by pcc MVP with BigInt support")
    lines.append("#include <stdio.h>")
    lines.append("#include <stdlib.h>")
    lines.append('#include "runtime.h"')
    lines.append("")

    # Forward declarations (functions take out param as first arg)
    for f in module.functions:
        cfn = fn_sym[f.name]
        params = ", ".join(f"rt_int* {_c_ident(p)}" for p in f.params)
        lines.append(f"static void {cfn}(rt_int* __pcc_out, {params});")
    if module.functions:
        lines.append("")

    # Function bodies
    for f in module.functions:
        cfn = fn_sym[f.name]
        # locals: params + assigned vars
        locals_seen: Set[str] = set(f.params)
        _collect_assigned_vars(f.body, locals_seen)
        sym: Dict[str, str] = {v: _c_ident(v) for v in sorted(locals_seen)}

        # type inference for this function
        tenv: Dict[str, Type] = {p: "int" for p in f.params}
        tenv = infer_stmt_types(f.body, tenv)

        # mark function params as pointers
        is_ptr_param = {p: True for p in f.params}

        params = ", ".join(f"rt_int* {sym[p]}" for p in f.params)
        lines.append(f"static void {cfn}(rt_int* __pcc_out, {params}) {{")

        # declare locals (excluding params)
        local_only = [v for v in sorted(locals_seen) if v not in set(f.params)]
        for v in local_only:
            if tenv.get(v, "int") == "int":
                lines.append(f"    rt_int {sym[v]}; rt_int_init(&{sym[v]});")
            else:
                lines.append(f"    rt_str {sym[v]} = rt_str_null();")
        if local_only:
            lines.append("")

        lines.extend(_emit_block(f.body, sym, fn_sym, tenv, indent=4, loop_depth=0, is_ptr_param=is_ptr_param, locals=set(local_only)))

        # free any int/str locals before function ends
        for v in local_only:
            if tenv.get(v, "int") == "int":
                lines.append(f"    rt_int_clear(&{sym[v]});")
            else:
                lines.append(f"    rt_str_free(&{sym[v]});")
        lines.append("}")
        lines.append("")

    lines.append("int main(void) {")

    # main locals: assigned vars in module.main
    main_vars: Set[str] = set()
    _collect_assigned_vars(module.main, main_vars)
    main_sym: Dict[str, str] = {v: _c_ident(v) for v in sorted(main_vars)}

    # type inference for main
    main_tenv: Dict[str, Type] = {}
    main_tenv = infer_stmt_types(module.main, main_tenv)

    for v in sorted(main_vars):
        if main_tenv.get(v, "int") == "int":
            lines.append(f"    rt_int {main_sym[v]}; rt_int_init(&{main_sym[v]});")
        else:
            lines.append(f"    rt_str {main_sym[v]} = rt_str_null();")
    if main_vars:
        lines.append("")

    lines.extend(_emit_block(module.main, main_sym, fn_sym, main_tenv, indent=4, loop_depth=0, is_ptr_param={}, locals=set(main_vars)))

    # free int/str vars at end of main
    for v in sorted(main_vars):
        if main_tenv.get(v, "int") == "int":
            lines.append(f"    rt_int_clear(&{main_sym[v]});")
        else:
            lines.append(f"    rt_str_free(&{main_sym[v]});")

    lines.append("    return 0;")
    lines.append("}")
    lines.append("")
    return CEmitResult(c_source="\n".join(lines))