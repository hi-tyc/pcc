"""Abstract Syntax Tree node definitions.

Each node carries a `line` attribute for error reporting. The AST is
produced by the parser and consumed by the semantic analyzer and the
LLVM IR code generator.
"""


class Node:
    def __init__(self, line=0):
        self.line = line


# ---------- Expressions ----------

class NumberLit(Node):
    def __init__(self, value, line=0):
        super().__init__(line)
        self.value = value


class StringLit(Node):
    def __init__(self, value, line=0):
        super().__init__(line)
        self.value = value


class BoolLit(Node):
    def __init__(self, value, line=0):
        super().__init__(line)
        self.value = value


class NoneLit(Node):
    def __init__(self, line=0):
        super().__init__(line)


class Name(Node):
    def __init__(self, name, line=0):
        super().__init__(line)
        self.name = name


class BinOp(Node):
    def __init__(self, op, left, right, line=0):
        super().__init__(line)
        self.op = op
        self.left = left
        self.right = right


class UnaryOp(Node):
    def __init__(self, op, operand, line=0):
        super().__init__(line)
        self.op = op
        self.operand = operand


class BoolOp(Node):
    """Short-circuit `and` / `or`."""
    def __init__(self, op, left, right, line=0):
        super().__init__(line)
        self.op = op  # 'and' | 'or'
        self.left = left
        self.right = right


class Call(Node):
    def __init__(self, func, args, line=0, kwargs=None):
        super().__init__(line)
        self.func = func
        self.args = args
        self.kwargs = kwargs or {}  # name -> expr (used by print sep/end)


class IfExp(Node):
    """Ternary: a if cond else b."""
    def __init__(self, cond, then, else_, line=0):
        super().__init__(line)
        self.cond = cond
        self.then = then
        self.else_ = else_


class ListLit(Node):
    """List literal: [a, b, c]"""
    def __init__(self, elements, line=0):
        super().__init__(line)
        self.elements = elements


class Subscript(Node):
    """Subscript access: obj[index]"""
    def __init__(self, obj, index, line=0):
        super().__init__(line)
        self.obj = obj
        self.index = index


class MethodCall(Node):
    """Method call: obj.method(args)"""
    def __init__(self, obj, method, args, line=0, kwargs=None):
        super().__init__(line)
        self.obj = obj
        self.method = method
        self.args = args
        self.kwargs = kwargs or {}


class Attribute(Node):
    """Attribute access: obj.attr"""
    def __init__(self, obj, attr, line=0):
        super().__init__(line)
        self.obj = obj
        self.attr = attr


class TupleLit(Node):
    """Tuple literal: (a, b, c)"""
    def __init__(self, elements, line=0):
        super().__init__(line)
        self.elements = elements


class DictLit(Node):
    """Dict literal: {k: v, ...}"""
    def __init__(self, pairs, line=0):
        super().__init__(line)
        self.pairs = pairs  # list of (key_expr, val_expr)


class Slice(Node):
    """Slice expression: a[start:stop:step]"""
    def __init__(self, obj, start, stop, step, line=0):
        super().__init__(line)
        self.obj = obj
        self.start = start
        self.stop = stop
        self.step = step


class FString(Node):
    """f-string: f"..." with interpolation parts"""
    def __init__(self, parts, line=0):
        super().__init__(line)
        self.parts = parts  # list of (str_lit_or_expr, is_expr)


class Compare(Node):
    """Chained comparison: a < b < c"""
    def __init__(self, ops, operands, line=0):
        super().__init__(line)
        self.ops = ops       # list of operators: '<', '>', '==', etc.
        self.operands = operands  # list of expressions


class IsOp(Node):
    """is / is not operator"""
    def __init__(self, left, right, negate, line=0):
        super().__init__(line)
        self.left = left
        self.right = right
        self.negate = negate


class Starred(Node):
    """Starred expression: *expr (used in call argument unpacking)"""
    def __init__(self, value, line=0):
        super().__init__(line)
        self.value = value


class ListComp(Node):
    """List comprehension: [expr for var in iterable (if cond)*]"""
    def __init__(self, element, var, iterable, conditions, line=0):
        super().__init__(line)
        self.element = element       # the expression to produce
        self.var = var               # list of loop variable names
        self.iterable = iterable
        self.conditions = conditions  # list of 'if' expressions (and-ed)


# ---------- Statements ----------

class ExprStmt(Node):
    def __init__(self, expr, line=0):
        super().__init__(line)
        self.expr = expr


class Assign(Node):
    def __init__(self, target, value, line=0):
        super().__init__(line)
        self.target = target
        self.value = value


class AugAssign(Node):
    def __init__(self, target, op, value, line=0):
        super().__init__(line)
        self.target = target
        self.op = op  # e.g. '+'
        self.value = value


class If(Node):
    def __init__(self, branches, orelse, line=0):
        # branches: list of (cond, body) for if/elif
        # orelse: list of statements
        super().__init__(line)
        self.branches = branches
        self.orelse = orelse


class While(Node):
    def __init__(self, cond, body, orelse, line=0):
        super().__init__(line)
        self.cond = cond
        self.body = body
        self.orelse = orelse


class For(Node):
    """for var in range(...): body"""
    def __init__(self, var, iterable, body, orelse, line=0):
        super().__init__(line)
        self.var = var
        self.iterable = iterable
        self.body = body
        self.orelse = orelse


class FuncDef(Node):
    def __init__(self, name, params, body, line=0, defaults=None):
        super().__init__(line)
        self.name = name
        self.params = params  # list of str
        self.body = body
        self.defaults = defaults or {}  # param_name -> default_expr


class ClassDef(Node):
    def __init__(self, name, methods, line=0):
        super().__init__(line)
        self.name = name
        self.methods = methods  # list of FuncDef


class Import(Node):
    def __init__(self, module, alias, line=0):
        super().__init__(line)
        self.module = module
        self.alias = alias


class ImportFrom(Node):
    def __init__(self, module, names, line=0):
        super().__init__(line)
        self.module = module
        self.names = names  # list of str


class Return(Node):
    def __init__(self, value, line=0):
        super().__init__(line)
        self.value = value


class Break(Node):
    def __init__(self, line=0):
        super().__init__(line)


class Continue(Node):
    def __init__(self, line=0):
        super().__init__(line)


class Pass(Node):
    def __init__(self, line=0):
        super().__init__(line)


class Global(Node):
    def __init__(self, names, line=0):
        super().__init__(line)
        self.names = names


class With(Node):
    """with item [as var]: body"""
    def __init__(self, items, body, line=0):
        super().__init__(line)
        # items: list of (expr, var_name_or_None)
        self.items = items
        self.body = body


class Try(Node):
    """try: body except [type [as name]]: handler ..."""
    def __init__(self, body, handlers, line=0):
        super().__init__(line)
        self.body = body
        # handlers: list of (exc_type_or_None, name_or_None, handler_body)
        self.handlers = handlers


class Raise(Node):
    def __init__(self, exc, line=0):
        super().__init__(line)
        self.exc = exc
