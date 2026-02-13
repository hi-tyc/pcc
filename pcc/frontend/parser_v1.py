"""
Python AST to IR parser for pcc.

This module parses Python source code into the intermediate representation (IR)
used by the pcc compiler.
"""

import ast
from typing import Dict, List, Set

from ..ir import (
    IntConst, StrConst, Var, BinOp, CmpOp, Call, AttributeAccess, MethodCall, ConstructorCall, BuiltinCall, Expr,
    Assign, AttrAssign, MethodCallStmt, Print, If, While, ForRange, Return, Break, Continue, Stmt,
    FunctionDef, ClassDef, ModuleIR
)


class ParseError(Exception):
    """Exception raised for parsing errors."""
    pass


class Parser:
    """Parser for converting Python source to IR.

    This parser handles a subset of Python syntax and converts it to
    the pcc intermediate representation.

    Supported features:
    - Integer and string literals (arbitrary precision integers)
    - Variables and assignment
    - Binary operators: +, -, *, //, %
    - Comparison operators: ==, !=, <, <=, >, >=
    - Function definitions and calls
    - Class definitions with methods and attributes
    - Control flow: if/else, while, for-range, break, continue
    - Print statements

    Example:
        >>> parser = Parser()
        >>> ir = parser.parse("print(1 + 2)")
    """

    def __init__(self):
        """Initialize the parser."""
        self._fn_sigs: Dict[str, int] = {}
        self._class_defs: Dict[str, ClassDef] = {}
        self._current_class: str = ""  # Track current class for method parsing

    def parse(self, source: str, filename: str = "<input>") -> ModuleIR:
        """Parse Python source code into IR.

        Args:
            source: Python source code string
            filename: Source filename for error reporting

        Returns:
            ModuleIR: The intermediate representation of the module

        Raises:
            ParseError: If the source contains unsupported syntax
        """
        try:
            mod = ast.parse(source, filename=filename, mode="exec")
        except SyntaxError as e:
            raise ParseError(f"Python syntax error: {e}") from e

        # First pass: collect function and class signatures
        self._fn_sigs = self._collect_function_signatures(mod)
        self._class_defs = self._collect_class_signatures(mod)

        # Second pass: parse functions, classes, and main body
        functions: List[FunctionDef] = []
        classes: List[ClassDef] = []
        main_stmts: List[Stmt] = []
        defined_main: Set[str] = set()

        for stmt in mod.body:
            if isinstance(stmt, ast.FunctionDef):
                functions.append(self._parse_function_def(stmt))
            elif isinstance(stmt, ast.ClassDef):
                classes.append(self._parse_class_def(stmt))
            else:
                self._validate_module_level_stmt(stmt)
                main_stmts.append(self._parse_stmt(stmt, defined_main, in_loop_depth=0))

        return ModuleIR(functions=functions, classes=classes, main=main_stmts)

    def _collect_function_signatures(self, mod: ast.Module) -> Dict[str, int]:
        """Collect function names and their arities."""
        sigs: Dict[str, int] = {}
        for stmt in mod.body:
            if isinstance(stmt, ast.FunctionDef):
                if stmt.name in sigs:
                    lineno = getattr(stmt, 'lineno', '?')
                    raise ParseError(f"Line {lineno}: duplicate function name: {stmt.name}")
                sigs[stmt.name] = len(stmt.args.args)
        return sigs

    def _collect_class_signatures(self, mod: ast.Module) -> Dict[str, ClassDef]:
        """Collect class names and their definitions."""
        classes: Dict[str, ClassDef] = {}
        for stmt in mod.body:
            if isinstance(stmt, ast.ClassDef):
                if stmt.name in classes:
                    lineno = getattr(stmt, 'lineno', '?')
                    raise ParseError(f"Line {lineno}: duplicate class name: {stmt.name}")
                # Check for unsupported class features
                if stmt.bases:
                    lineno = getattr(stmt, 'lineno', '?')
                    raise ParseError(f"Line {lineno}: class inheritance is not supported")
                if stmt.keywords:
                    lineno = getattr(stmt, 'lineno', '?')
                    raise ParseError(f"Line {lineno}: class keywords are not supported")
                if stmt.decorator_list:
                    lineno = getattr(stmt, 'lineno', '?')
                    raise ParseError(f"Line {lineno}: class decorators are not supported")
                # Store the class name for later lookup
                classes[stmt.name] = None  # Will be populated during full parsing
        return classes

    def _validate_module_level_stmt(self, stmt: ast.stmt) -> None:
        """Validate that a module-level statement is supported."""
        unsupported = (ast.Import, ast.ImportFrom, ast.Lambda,
                      ast.Try, ast.With, ast.Raise)
        if isinstance(stmt, unsupported):
            lineno = getattr(stmt, 'lineno', '?')
            raise ParseError(f"Line {lineno}: unsupported statement: {type(stmt).__name__}")

    def _parse_function_def(self, fn: ast.FunctionDef) -> FunctionDef:
        """Parse a function definition."""
        lineno = getattr(fn, 'lineno', 0)

        if fn.decorator_list:
            raise ParseError(f"Line {lineno}: decorators are not supported")
        if fn.returns is not None:
            raise ParseError(f"Line {lineno}: return annotations are not supported")

        args = fn.args
        if args.vararg or args.kwarg or args.kwonlyargs or args.defaults or args.kw_defaults:
            raise ParseError(f"Line {lineno}: only simple positional parameters are supported")

        params = []
        for a in args.args:
            if a.annotation is not None:
                a_lineno = getattr(a, 'lineno', '?')
                raise ParseError(f"Line {a_lineno}: parameter annotations are not supported")
            params.append(a.arg)

        defined = set(params)
        body: List[Stmt] = []
        for s in fn.body:
            body.append(self._parse_stmt(s, defined, in_loop_depth=0))

        return FunctionDef(name=fn.name, params=params, body=body, lineno=lineno)

    def _parse_class_def(self, node: ast.ClassDef) -> ClassDef:
        """Parse a class definition."""
        lineno = getattr(node, 'lineno', 0)

        self._current_class = node.name  # Set current class context

        methods: List[FunctionDef] = []
        fields: Set[str] = set()

        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                methods.append(self._parse_method_def(item))
            elif isinstance(item, ast.Assign):
                # Class-level field with default value
                if len(item.targets) != 1:
                    raise ParseError(f"Line {lineno}: only single-target assignment is supported in class")
                target = item.targets[0]
                if not isinstance(target, ast.Name):
                    raise ParseError(f"Line {lineno}: class field must be a simple name")
                fields.add(target.id)
            else:
                raise ParseError(f"Line {lineno}: only methods and field assignments allowed in class")

        self._current_class = ""  # Clear current class context

        return ClassDef(name=node.name, methods=methods, fields=list(fields), lineno=lineno)

    def _parse_method_def(self, fn: ast.FunctionDef) -> FunctionDef:
        """Parse a method definition (similar to function but with self)."""
        lineno = getattr(fn, 'lineno', 0)

        if fn.decorator_list:
            raise ParseError(f"Line {lineno}: decorators are not supported")
        if fn.returns is not None:
            raise ParseError(f"Line {lineno}: return annotations are not supported")

        args = fn.args
        if args.vararg or args.kwarg or args.kwonlyargs or args.defaults or args.kw_defaults:
            raise ParseError(f"Line {lineno}: only simple positional parameters are supported")

        # First parameter must be 'self'
        if not args.args or args.args[0].arg != "self":
            raise ParseError(f"Line {lineno}: method first parameter must be 'self'")

        # Skip 'self' parameter for the IR (it's implicit)
        params = []
        for a in args.args[1:]:  # Skip 'self'
            if a.annotation is not None:
                a_lineno = getattr(a, 'lineno', '?')
                raise ParseError(f"Line {a_lineno}: parameter annotations are not supported")
            params.append(a.arg)

        # Add 'self' to defined set for method body parsing
        defined = set(params)
        defined.add("self")  # 'self' is always available in methods
        body: List[Stmt] = []
        for s in fn.body:
            body.append(self._parse_stmt(s, defined, in_loop_depth=0))

        return FunctionDef(name=fn.name, params=params, body=body, lineno=lineno)

    def _parse_stmt(self, stmt: ast.stmt, defined: Set[str], in_loop_depth: int) -> Stmt:
        """Parse a statement."""
        # Assignment: x = <expr>
        if isinstance(stmt, ast.Assign):
            return self._parse_assign(stmt, defined)

        # Print statement
        if isinstance(stmt, ast.Expr):
            return self._parse_expr_stmt(stmt, defined)

        # If statement
        if isinstance(stmt, ast.If):
            return self._parse_if(stmt, defined, in_loop_depth)

        # While loop
        if isinstance(stmt, ast.While):
            return self._parse_while(stmt, defined, in_loop_depth)

        # For loop
        if isinstance(stmt, ast.For):
            return self._parse_for(stmt, defined, in_loop_depth)

        # Return statement
        if isinstance(stmt, ast.Return):
            return self._parse_return(stmt, defined)

        # Break statement
        if isinstance(stmt, ast.Break):
            return self._parse_break(stmt, in_loop_depth)

        # Continue statement
        if isinstance(stmt, ast.Continue):
            return self._parse_continue(stmt, in_loop_depth)

        # Global/Nonlocal
        if isinstance(stmt, (ast.Global, ast.Nonlocal)):
            lineno = getattr(stmt, 'lineno', '?')
            raise ParseError(f"Line {lineno}: global/nonlocal not supported")

        raise ParseError(f"Unsupported statement: {type(stmt).__name__}")

    def _parse_assign(self, stmt: ast.Assign, defined: Set[str]) -> Stmt:
        """Parse an assignment statement."""
        if len(stmt.targets) != 1:
            raise ParseError("Only single-target assignment is supported")

        t0 = stmt.targets[0]

        # Simple variable assignment: x = expr
        if isinstance(t0, ast.Name) and isinstance(t0.ctx, ast.Store):
            name = t0.id
            expr = self._parse_expr(stmt.value, defined)
            defined.add(name)
            return Assign(name=name, expr=expr)

        # Attribute assignment: obj.attr = expr
        if isinstance(t0, ast.Attribute) and isinstance(t0.ctx, ast.Store):
            if not isinstance(t0.value, ast.Name):
                raise ParseError("Only simple variable.attribute assignment is supported")

            obj_name = t0.value.id
            if obj_name not in defined:
                lineno = getattr(stmt, 'lineno', '?')
                raise ParseError(f"Line {lineno}: variable used before assignment: {obj_name}")

            attr_name = t0.attr
            expr = self._parse_expr(stmt.value, defined)
            return AttrAssign(obj=obj_name, attr=attr_name, expr=expr)

        raise ParseError("Assignment target must be a variable name or attribute access")

    def _parse_expr_stmt(self, stmt: ast.Expr, defined: Set[str]) -> Stmt:
        """Parse an expression statement (print or method call)."""
        call = stmt.value
        if not isinstance(call, ast.Call):
            raise ParseError("Only function calls are supported as expression statements")

        # Print statement: print(expr)
        if isinstance(call.func, ast.Name) and call.func.id == "print":
            if len(call.args) != 1 or call.keywords:
                raise ParseError("print(...) must have exactly one positional argument")
            expr = self._parse_expr(call.args[0], defined)
            return Print(expr=expr)

        # Method call statement: obj.method(args)
        if isinstance(call.func, ast.Attribute):
            if not isinstance(call.func.value, ast.Name):
                raise ParseError("Only simple variable.method() calls are supported")

            obj_name = call.func.value.id
            if obj_name not in defined:
                lineno = getattr(call, 'lineno', '?')
                raise ParseError(f"Line {lineno}: variable used before assignment: {obj_name}")

            method_name = call.func.attr

            if call.keywords:
                raise ParseError("Keyword arguments are not supported")

            args = [self._parse_expr(a, defined) for a in call.args]
            return MethodCallStmt(obj=obj_name, method=method_name, args=args)

        raise ParseError("Only print(...) or method calls are supported as expression statements")

    def _parse_if(self, stmt: ast.If, defined: Set[str], in_loop_depth: int) -> If:
        """Parse an if/else statement."""
        test = self._parse_expr(stmt.test, defined)

        defined_for_body = set(defined)
        body: List[Stmt] = []
        for s in stmt.body:
            body.append(self._parse_stmt(s, defined_for_body, in_loop_depth))

        defined_for_else = set(defined)
        orelse: List[Stmt] = []
        for s in stmt.orelse:
            orelse.append(self._parse_stmt(s, defined_for_else, in_loop_depth))

        defined |= (defined_for_body | defined_for_else)
        return If(test=test, body=body, orelse=orelse)

    def _parse_while(self, stmt: ast.While, defined: Set[str], in_loop_depth: int) -> While:
        """Parse a while loop."""
        if stmt.orelse:
            raise ParseError("while-else is not supported")

        test = self._parse_expr(stmt.test, defined)

        defined_for_body = set(defined)
        body: List[Stmt] = []
        for s in stmt.body:
            body.append(self._parse_stmt(s, defined_for_body, in_loop_depth + 1))

        defined |= defined_for_body
        return While(test=test, body=body)

    def _parse_for(self, stmt: ast.For, defined: Set[str], in_loop_depth: int) -> ForRange:
        """Parse a for-range loop."""
        lineno = int(getattr(stmt, 'lineno', 0) or 0)

        if stmt.orelse:
            raise ParseError(f"Line {lineno}: for-else is not supported")

        if not isinstance(stmt.target, ast.Name) or not isinstance(stmt.target.ctx, ast.Store):
            raise ParseError(f"Line {lineno}: for target must be a variable name")
        var = stmt.target.id

        it = stmt.iter
        if not isinstance(it, ast.Call) or it.keywords:
            raise ParseError(f"Line {lineno}: only for-in-range is supported")
        if not isinstance(it.func, ast.Name) or it.func.id != "range":
            raise ParseError(f"Line {lineno}: only for-in-range is supported")

        argc = len(it.args)
        if argc not in (1, 2, 3):
            raise ParseError(f"Line {lineno}: range() expects 1, 2, or 3 arguments, got {argc}")

        # Parse range arguments
        if argc == 1:
            start_e = IntConst(0)
            stop_e = self._parse_expr(it.args[0], defined)
            step_e = IntConst(1)
        elif argc == 2:
            start_e = self._parse_expr(it.args[0], defined)
            stop_e = self._parse_expr(it.args[1], defined)
            step_e = IntConst(1)
        else:
            start_e = self._parse_expr(it.args[0], defined)
            stop_e = self._parse_expr(it.args[1], defined)
            step_e = self._parse_expr(it.args[2], defined)

        if isinstance(step_e, IntConst) and step_e.value == 0:
            raise ParseError(f"Line {lineno}: range() step must not be 0")

        defined_for_body = set(defined)
        defined_for_body.add(var)

        body: List[Stmt] = []
        for s in stmt.body:
            body.append(self._parse_stmt(s, defined_for_body, in_loop_depth + 1))

        defined |= defined_for_body
        return ForRange(var=var, start=start_e, stop=stop_e, step=step_e,
                       body=body, lineno=lineno)

    def _parse_return(self, stmt: ast.Return, defined: Set[str]) -> Return:
        """Parse a return statement."""
        if stmt.value is None:
            return Return(expr=IntConst(0))
        return Return(expr=self._parse_expr(stmt.value, defined))

    def _parse_break(self, stmt: ast.Break, in_loop_depth: int) -> Break:
        """Parse a break statement."""
        lineno = int(getattr(stmt, 'lineno', 0) or 0)
        if in_loop_depth <= 0:
            raise ParseError(f"Line {lineno}: break outside loop")
        return Break(lineno=lineno)

    def _parse_continue(self, stmt: ast.Continue, in_loop_depth: int) -> Continue:
        """Parse a continue statement."""
        lineno = int(getattr(stmt, 'lineno', 0) or 0)
        if in_loop_depth <= 0:
            raise ParseError(f"Line {lineno}: continue outside loop")
        return Continue(lineno=lineno)

    def _parse_expr(self, node: ast.AST, defined: Set[str]) -> Expr:
        """Parse an expression."""
        # Integer constant
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return IntConst(int(node.value))

        # String constant
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return StrConst(str(node.value))

        # Negative numbers: -5 -> BinOp("-", IntConst(0), IntConst(5))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            operand = self._parse_expr(node.operand, defined)
            return BinOp("-", IntConst(0), operand)

        # Variable reference
        if isinstance(node, ast.Name):
            if not isinstance(node.ctx, ast.Load):
                raise ParseError("Only variable reads are supported in expressions")
            if node.id not in defined:
                lineno = getattr(node, 'lineno', '?')
                raise ParseError(f"Line {lineno}: variable used before assignment: {node.id}")
            return Var(node.id)

        # Attribute access (obj.attr)
        if isinstance(node, ast.Attribute):
            return self._parse_attribute(node, defined)

        # Binary operation
        if isinstance(node, ast.BinOp):
            return self._parse_binop(node, defined)

        # Comparison
        if isinstance(node, ast.Compare):
            return self._parse_compare(node, defined)

        # Function call or method call or constructor call
        if isinstance(node, ast.Call):
            return self._parse_call(node, defined)

        raise ParseError(f"Unsupported expression: {type(node).__name__}")

    def _parse_attribute(self, node: ast.Attribute, defined: Set[str]) -> AttributeAccess:
        """Parse an attribute access expression (obj.attr)."""
        if not isinstance(node.value, ast.Name):
            raise ParseError("Only simple variable.attribute access is supported")

        obj_name = node.value.id
        if obj_name not in defined:
            lineno = getattr(node, 'lineno', '?')
            raise ParseError(f"Line {lineno}: variable used before assignment: {obj_name}")

        return AttributeAccess(obj=obj_name, attr=node.attr)

    def _parse_binop(self, node: ast.BinOp, defined: Set[str]) -> BinOp:
        """Parse a binary operation."""
        op_map = {
            ast.Add: "+",
            ast.Sub: "-",
            ast.Mult: "*",
            ast.FloorDiv: "//",
            ast.Mod: "%",
        }

        op_type = type(node.op)
        if op_type not in op_map:
            raise ParseError(f"Unsupported binary operator: {op_type.__name__}")

        op_s = op_map[op_type]
        left = self._parse_expr(node.left, defined)
        right = self._parse_expr(node.right, defined)
        return BinOp(op_s, left, right)

    def _parse_compare(self, node: ast.Compare, defined: Set[str]) -> CmpOp:
        """Parse a comparison operation."""
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise ParseError("Chained comparisons are not supported (e.g., 1 < x < 3)")

        op_map = {
            ast.Eq: "==",
            ast.NotEq: "!=",
            ast.Lt: "<",
            ast.LtE: "<=",
            ast.Gt: ">",
            ast.GtE: ">=",
        }

        op_type = type(node.ops[0])
        if op_type not in op_map:
            raise ParseError(f"Unsupported comparison operator: {op_type.__name__}")

        op_s = op_map[op_type]
        left = self._parse_expr(node.left, defined)
        right = self._parse_expr(node.comparators[0], defined)
        return CmpOp(op_s, left, right)

    # Builtin functions that don't need to be defined
    _BUILTINS = {'len', 'abs', 'min', 'max', 'pow', 'str', 'int'}

    def _parse_call(self, node: ast.Call, defined: Set[str]) -> Expr:
        """Parse a function call, method call, constructor call, or builtin call."""
        # Method call: obj.method(args)
        if isinstance(node.func, ast.Attribute):
            if not isinstance(node.func.value, ast.Name):
                raise ParseError("Only simple variable.method() calls are supported")

            obj_name = node.func.value.id
            if obj_name not in defined:
                lineno = getattr(node, 'lineno', '?')
                raise ParseError(f"Line {lineno}: variable used before assignment: {obj_name}")

            method_name = node.func.attr

            if node.keywords:
                raise ParseError("Keyword arguments are not supported")

            args = [self._parse_expr(a, defined) for a in node.args]
            return MethodCall(obj=obj_name, method=method_name, args=args)

        # Regular function call, constructor call, or builtin call
        if not isinstance(node.func, ast.Name):
            raise ParseError("Only simple function calls by name are supported")

        fname = node.func.id

        if fname == "print":
            raise ParseError("print(...) is only supported as a statement, not as an expression")

        # Check if it's a builtin function
        if fname in self._BUILTINS:
            if node.keywords:
                raise ParseError("Keyword arguments are not supported in builtin calls")
            args = [self._parse_expr(a, defined) for a in node.args]
            return self._parse_builtin(fname, args, node)

        # Check if it's a constructor call (class name)
        if fname in self._class_defs:
            if node.keywords:
                raise ParseError("Keyword arguments are not supported in constructor calls")
            args = [self._parse_expr(a, defined) for a in node.args]
            return ConstructorCall(class_name=fname, args=args)

        # Regular function call
        if fname not in self._fn_sigs:
            lineno = getattr(node, 'lineno', '?')
            raise ParseError(f"Line {lineno}: call to unknown function or class: {fname}")
        if node.keywords:
            raise ParseError("Keyword arguments are not supported")

        expected = self._fn_sigs[fname]
        got = len(node.args)
        if got != expected:
            lineno = getattr(node, 'lineno', '?')
            raise ParseError(f"Line {lineno}: function '{fname}' expects {expected} args, got {got}")

        args = [self._parse_expr(a, defined) for a in node.args]
        return Call(func=fname, args=args)

    def _parse_builtin(self, name: str, args: List[Expr], node: ast.Call) -> BuiltinCall:
        """Parse builtin function call with argument validation."""
        # Validate argument counts for builtins
        builtin_arity = {
            'len': 1,
            'abs': 1,
            'str': 1,
            'int': 1,
            'pow': (2, 3),  # 2 or 3 args
            'min': (1, None),  # 1 or more
            'max': (1, None),  # 1 or more
        }

        arity = builtin_arity.get(name)
        if arity is not None:
            if isinstance(arity, int):
                if len(args) != arity:
                    lineno = getattr(node, 'lineno', '?')
                    raise ParseError(f"Line {lineno}: builtin '{name}' expects {arity} argument(s), got {len(args)}")
            elif isinstance(arity, tuple):
                min_args, max_args = arity
                if len(args) < min_args:
                    lineno = getattr(node, 'lineno', '?')
                    raise ParseError(f"Line {lineno}: builtin '{name}' expects at least {min_args} argument(s), got {len(args)}")
                if max_args is not None and len(args) > max_args:
                    lineno = getattr(node, 'lineno', '?')
                    raise ParseError(f"Line {lineno}: builtin '{name}' expects at most {max_args} argument(s), got {len(args)}")

        return BuiltinCall(name=name, args=args)
