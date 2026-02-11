import ast
from dataclasses import dataclass
from typing import List, Union, Dict


@dataclass(frozen=True)
class IntConst:
    value: int


@dataclass(frozen=True)
class StrConst:
    value: str


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class BinOp:
    op: str  # "+", "-", "*", "**", "//", "%"
    left: "Expr"
    right: "Expr"

@dataclass(frozen=True)
class BoolOp:
    op: str  # "and", "or"
    left: "Expr"
    right: "Expr"

@dataclass(frozen=True)
class UnaryOp:
    op: str  # "not"
    operand: "Expr"


@dataclass(frozen=True)
class CmpOp:
    op: str  # "==", "!=", "<", "<=", ">", ">="
    left: "Expr"
    right: "Expr"


@dataclass(frozen=True)
class Call:
    func: str
    args: List["Expr"]


Expr = Union[IntConst, StrConst, Var, BinOp, BoolOp, UnaryOp, CmpOp, Call]


@dataclass(frozen=True)
class Assign:
    name: str
    expr: Expr


@dataclass(frozen=True)
class Print:
    expr: Expr


@dataclass(frozen=True)
class If:
    test: Expr
    body: List["Stmt"]
    orelse: List["Stmt"]


@dataclass(frozen=True)
class While:
    test: Expr
    body: List["Stmt"]


@dataclass(frozen=True)
class Return:
    expr: Expr


@dataclass(frozen=True)
class Break:
    lineno: int


@dataclass(frozen=True)
class Continue:
    lineno: int


@dataclass(frozen=True)
class ForRange:
    var: str
    start: Expr
    stop: Expr
    step: Expr
    body: List["Stmt"]
    lineno: int


@dataclass(frozen=True)
class FunctionDef:
    name: str
    params: List[str]
    body: List["Stmt"]
    lineno: int


def _parse_expr(node: ast.AST, defined: set[str], fn_sigs: Dict[str, int]) -> Expr:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return IntConst(int(node.value))
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return StrConst(str(node.value))

    if isinstance(node, ast.UnaryOp):
        # Handle negative numbers: -5 is UnaryOp(op=USub, operand=Constant(5))
        if isinstance(node.op, ast.USub):
            operand = _parse_expr(node.operand, defined, fn_sigs)
            return BinOp("-", IntConst(0), operand)
        # Handle boolean not
        if isinstance(node.op, ast.Not):
            operand = _parse_expr(node.operand, defined, fn_sigs)
            return UnaryOp("not", operand)
        raise SyntaxError(f"Unsupported unary operator: {type(node.op).__name__}")

    if isinstance(node, ast.Name):
        if not isinstance(node.ctx, ast.Load):
            raise SyntaxError("Only variable reads are supported in expressions")
        if node.id not in defined:
            lineno = getattr(node, "lineno", "?")
            raise SyntaxError(f"Line {lineno}: variable used before assignment: {node.id}")
        return Var(node.id)

    if isinstance(node, ast.BinOp):
        op = node.op
        if isinstance(op, ast.Add):
            op_s = "+"
        elif isinstance(op, ast.Sub):
            op_s = "-"
        elif isinstance(op, ast.Mult):
            op_s = "*"
        elif isinstance(op, ast.Pow):
            op_s = "**"
        elif isinstance(op, ast.FloorDiv):
            op_s = "//"
        elif isinstance(op, ast.Mod):
            op_s = "%"
        else:
            raise SyntaxError(f"Unsupported binary operator: {type(op).__name__}")

        left = _parse_expr(node.left, defined, fn_sigs)
        right = _parse_expr(node.right, defined, fn_sigs)
        return BinOp(op_s, left, right)

    if isinstance(node, ast.BoolOp):
        # Keep MVP simple: only binary and/or, no chaining like a and b and c
        if len(node.values) != 2:
            raise SyntaxError("Only binary boolean ops are supported (e.g., a and b)")
        if isinstance(node.op, ast.And):
            op_s = "and"
        elif isinstance(node.op, ast.Or):
            op_s = "or"
        else:
            raise SyntaxError(f"Unsupported boolean operator: {type(node.op).__name__}")
        left = _parse_expr(node.values[0], defined, fn_sigs)
        right = _parse_expr(node.values[1], defined, fn_sigs)
        return BoolOp(op_s, left, right)

    if isinstance(node, ast.Compare):
        # MVP: only single comparator, no chained compares
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise SyntaxError("Chained comparisons are not supported (e.g., 1 < x < 3)")
        op = node.ops[0]
        if isinstance(op, ast.Eq):
            op_s = "=="
        elif isinstance(op, ast.NotEq):
            op_s = "!="
        elif isinstance(op, ast.Lt):
            op_s = "<"
        elif isinstance(op, ast.LtE):
            op_s = "<="
        elif isinstance(op, ast.Gt):
            op_s = ">"
        elif isinstance(op, ast.GtE):
            op_s = ">="
        else:
            raise SyntaxError(f"Unsupported comparison operator: {type(op).__name__}")
        left = _parse_expr(node.left, defined, fn_sigs)
        right = _parse_expr(node.comparators[0], defined, fn_sigs)
        return CmpOp(op_s, left, right)

    if isinstance(node, ast.Call):
        # allow calling known user-defined funcs (print is statement-only in this MVP)
        if not isinstance(node.func, ast.Name):
            raise SyntaxError("Only simple function calls by name are supported")
        fname = node.func.id
        if fname == "print":
            raise SyntaxError("print(...) is only supported as a statement, not as an expression")
        # builtin: input()
        if fname == "input":
            # Python supports input() and input(prompt)
            if node.keywords or len(node.args) not in (0, 1):
                lineno = getattr(node, "lineno", "?")
                raise SyntaxError(f"Line {lineno}: input() takes 0 or 1 positional arguments")
            args = [_parse_expr(a, defined, fn_sigs) for a in node.args]
            return Call(func="input", args=args)

        # builtin: len(x)
        if fname == "len":
            if node.keywords or len(node.args) != 1:
                lineno = getattr(node, "lineno", "?")
                raise SyntaxError(f"Line {lineno}: len() expects exactly 1 positional argument")
            arg0 = _parse_expr(node.args[0], defined, fn_sigs)
            return Call(func="len", args=[arg0])

        # builtin: int(x)  (only support int(str) for now; keep Python spelling)
        if fname == "int":
            if node.keywords or len(node.args) != 1:
                lineno = getattr(node, "lineno", "?")
                raise SyntaxError(f"Line {lineno}: int() expects exactly 1 positional argument")
            arg0 = _parse_expr(node.args[0], defined, fn_sigs)
            return Call(func="int", args=[arg0])

        # builtin: pow(a, b) and pow(a, b, mod)
        if fname == "pow":
            if node.keywords:
                raise SyntaxError("Keyword arguments are not supported")
            got = len(node.args)
            if got not in (2, 3):
                lineno = getattr(node, "lineno", "?")
                raise SyntaxError(f"Line {lineno}: builtin 'pow' expects 2 or 3 args, got {got}")
            args = [_parse_expr(a, defined, fn_sigs) for a in node.args]
            return Call(func="pow", args=args)
        if fname not in fn_sigs:
            lineno = getattr(node, "lineno", "?")
            raise SyntaxError(f"Line {lineno}: call to unknown function: {fname}")
        if node.keywords:
            raise SyntaxError("Keyword arguments are not supported")
        expected = fn_sigs[fname]
        got = len(node.args)
        if got != expected:
            lineno = getattr(node, "lineno", "?")
            raise SyntaxError(f"Line {lineno}: function '{fname}' expects {expected} args, got {got}")
        args = [_parse_expr(a, defined, fn_sigs) for a in node.args]
        return Call(func=fname, args=args)

    raise SyntaxError(f"Unsupported expression: {type(node).__name__}")


Stmt = Union[Assign, Print, If, While, ForRange, Return, Break, Continue]


@dataclass(frozen=True)
class ModuleIR:
    functions: List[FunctionDef]
    main: List[Stmt]


def _parse_stmt(
    stmt: ast.stmt,
    defined: set[str],
    fn_sigs: Dict[str, int],
    in_loop_depth: int,
) -> Stmt:
    # x = <expr>
    if isinstance(stmt, ast.Assign):
        if len(stmt.targets) != 1:
            raise SyntaxError("Only single-target assignment is supported")
        t0 = stmt.targets[0]
        if not isinstance(t0, ast.Name) or not isinstance(t0.ctx, ast.Store):
            raise SyntaxError("Assignment target must be a variable name")
        name = t0.id
        expr = _parse_expr(stmt.value, defined, fn_sigs)
        defined.add(name)  # visible to subsequent statements (including inside future ifs)
        return Assign(name=name, expr=expr)

    # print(<expr>)
    if isinstance(stmt, ast.Expr):
        call = stmt.value
        if not isinstance(call, ast.Call):
            raise SyntaxError("Only function calls are supported as expression statements")
        if not isinstance(call.func, ast.Name) or call.func.id != "print":
            raise SyntaxError("Only print(...) is supported as expression statement")
        if len(call.args) != 1 or call.keywords:
            raise SyntaxError("print(...) must have exactly one positional argument and no keywords")
        expr = _parse_expr(call.args[0], defined, fn_sigs)
        return Print(expr=expr)

    # if <test>: ...
    if isinstance(stmt, ast.If):
        test = _parse_expr(stmt.test, defined, fn_sigs)

        # For MVP, treat assignments in either branch as "defined after the if"
        # (no real scope/definite assignment analysis).
        defined_for_body = set(defined)
        body_ir: List[Stmt] = []
        for s in stmt.body:
            body_ir.append(_parse_stmt(s, defined_for_body, fn_sigs, in_loop_depth))

        # elif is represented as nested If in orelse by Python AST
        # We keep it as-is to preserve elif semantics
        defined_for_else = set(defined)
        else_ir: List[Stmt] = []
        for s in stmt.orelse:
            else_ir.append(_parse_stmt(s, defined_for_else, fn_sigs, in_loop_depth))

        defined |= (defined_for_body | defined_for_else)
        return If(test=test, body=body_ir, orelse=else_ir)

    # while <test>: ...
    if isinstance(stmt, ast.While):
        if stmt.orelse:
            raise SyntaxError("while-else is not supported in this MVP")
        test = _parse_expr(stmt.test, defined, fn_sigs)

        # Similar to If: treat assignments in the loop body as "defined after the loop"
        defined_for_body = set(defined)
        body_ir: List[Stmt] = []
        for s in stmt.body:
            body_ir.append(_parse_stmt(s, defined_for_body, fn_sigs, in_loop_depth + 1))
        defined |= defined_for_body
        return While(test=test, body=body_ir)

    # for var in range(...): ...
    if isinstance(stmt, ast.For):
        lineno = int(getattr(stmt, "lineno", 0) or 0)
        if stmt.orelse:
            raise SyntaxError(f"Line {lineno}: for-else is not supported in this MVP")
        # target: Name only
        if not isinstance(stmt.target, ast.Name) or not isinstance(stmt.target.ctx, ast.Store):
            raise SyntaxError(f"Line {lineno}: for target must be a variable name (Name)")
        var = stmt.target.id

        # iter: range(...)
        it = stmt.iter
        if not isinstance(it, ast.Call) or it.keywords:
            raise SyntaxError(f"Line {lineno}: only for-in-range is supported")
        if not isinstance(it.func, ast.Name) or it.func.id != "range":
            raise SyntaxError(f"Line {lineno}: only for-in-range is supported")

        argc = len(it.args)
        if argc not in (1, 2, 3):
            raise SyntaxError(f"Line {lineno}: range() expects 1, 2, or 3 arguments, got {argc}")

        # Parse args as expressions
        if argc == 1:
            start_e = IntConst(0)
            stop_e = _parse_expr(it.args[0], defined, fn_sigs)
            step_e = IntConst(1)
        elif argc == 2:
            start_e = _parse_expr(it.args[0], defined, fn_sigs)
            stop_e = _parse_expr(it.args[1], defined, fn_sigs)
            step_e = IntConst(1)
        else:
            start_e = _parse_expr(it.args[0], defined, fn_sigs)
            stop_e = _parse_expr(it.args[1], defined, fn_sigs)
            step_e = _parse_expr(it.args[2], defined, fn_sigs)

        # step == 0 compile-time check if literal
        if isinstance(step_e, IntConst) and step_e.value == 0:
            raise SyntaxError(f"Line {lineno}: range() step must not be 0")

        # Loop variable is defined inside loop and after loop (simple scope model)
        defined_for_body = set(defined)
        defined_for_body.add(var)

        body_ir: List[Stmt] = []
        for s in stmt.body:
            body_ir.append(_parse_stmt(s, defined_for_body, fn_sigs, in_loop_depth + 1))

        defined |= defined_for_body
        return ForRange(var=var, start=start_e, stop=stop_e, step=step_e, body=body_ir, lineno=lineno)

    if isinstance(stmt, ast.Return):
        if stmt.value is None:
            # MVP: return without value -> return 0
            return Return(expr=IntConst(0))
        return Return(expr=_parse_expr(stmt.value, defined, fn_sigs))

    if isinstance(stmt, ast.Break):
        lineno = int(getattr(stmt, "lineno", 0) or 0)
        if in_loop_depth <= 0:
            raise SyntaxError(f"Line {lineno}: Break outside while (node=Break)")
        return Break(lineno=lineno)

    if isinstance(stmt, ast.Continue):
        lineno = int(getattr(stmt, "lineno", 0) or 0)
        if in_loop_depth <= 0:
            raise SyntaxError(f"Line {lineno}: Continue outside while (node=Continue)")
        return Continue(lineno=lineno)

    if isinstance(stmt, (ast.Global, ast.Nonlocal)):
        raise SyntaxError(f"Line {getattr(stmt, 'lineno', '?')}: global/nonlocal not supported")

    raise SyntaxError(f"Unsupported top-level statement: {type(stmt).__name__}")


def _parse_function_def(fn: ast.FunctionDef, fn_sigs: Dict[str, int]) -> FunctionDef:
    if fn.decorator_list:
        raise SyntaxError(f"Line {getattr(fn,'lineno','?')}: decorators are not supported")
    if fn.returns is not None:
        # ignore annotation but disallow complex typing? keep simple: reject any return annotation for now
        raise SyntaxError(f"Line {getattr(fn,'lineno','?')}: return annotations are not supported")
    if fn.args.vararg or fn.args.kwarg or fn.args.kwonlyargs or fn.args.defaults or fn.args.kw_defaults:
        raise SyntaxError(f"Line {getattr(fn,'lineno','?')}: only simple positional parameters are supported")

    params = []
    for a in fn.args.args:
        if a.annotation is not None:
            raise SyntaxError(f"Line {getattr(a,'lineno','?')}: parameter annotations are not supported")
        params.append(a.arg)

    defined = set(params)
    body_ir: List[Stmt] = []
    for s in fn.body:
        body_ir.append(_parse_stmt(s, defined, fn_sigs, in_loop_depth=0))
    return FunctionDef(name=fn.name, params=params, body=body_ir, lineno=getattr(fn, "lineno", 0))


def parse_source_to_ir(source: str, filename: str = "<input>") -> ModuleIR:
    """
    Frontend: Python AST -> tiny IR

    Supported:
      - x = <expr>
      - print(<expr>)
      - if <test>: ... else: ...
      - while <test>: ...
      - def f(a,b): ... return expr
      - function calls: f(1,2), f(x,y)

    Expr supported:
      - int literal
      - variable name
      - + - * // %
      - == != < <= > >=
      - function call
    """
    mod = ast.parse(source, filename=filename, mode="exec")

    # First pass: collect all module-level function signatures (name -> arity)
    fn_sigs: Dict[str, int] = {}
    for stmt in mod.body:
        if isinstance(stmt, ast.FunctionDef):
            if stmt.name in fn_sigs:
                raise SyntaxError(f"Line {getattr(stmt,'lineno','?')}: duplicate function name: {stmt.name}")
            # We only support simple positional args; full validation happens in _parse_function_def
            fn_sigs[stmt.name] = len(stmt.args.args)

    functions: List[FunctionDef] = []
    main_stmts: List[Stmt] = []

    defined_main: set[str] = set()
    for stmt in mod.body:
        if isinstance(stmt, ast.FunctionDef):
            functions.append(_parse_function_def(stmt, fn_sigs))
            continue

        # Explicitly reject unsupported module-level nodes early
        if isinstance(stmt, (ast.Import, ast.ImportFrom, ast.ClassDef, ast.Lambda, ast.Try, ast.With, ast.Raise)):
            raise SyntaxError(f"Line {getattr(stmt,'lineno','?')}: unsupported statement: {type(stmt).__name__}")

        main_stmts.append(_parse_stmt(stmt, defined_main, fn_sigs, in_loop_depth=0))

    return ModuleIR(functions=functions, main=main_stmts)