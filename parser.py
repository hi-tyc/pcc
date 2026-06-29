"""Recursive-descent parser: token stream -> AST.

Grammar handled (subset):
  program     := (NEWLINE | statement)* EOF
  statement   := compound_stmt | simple_stmt NEWLINE
  simple_stmt := (return | break | continue | pass | global | assignment | expr)
  compound    := if | while | for | def
  suite       := simple_stmt | NEWLINE INDENT (statement)+ DEDENT
Expressions follow standard precedence (ternary > or > and > not >
comparison > add/sub > mul/div/floordiv/mod > unary > power > call/atom).
"""

from tokens import TokenType as T
from lexer import LexError
import ast_nodes as A


class ParseError(Exception):
    def __init__(self, msg, line=0):
        super().__init__(f"ParseError at line {line}: {msg}")
        self.line = line


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.i = 0
        self._lambda_counter = 0
        self._lambdas = []

    # --- helpers ---
    def peek(self, off=0):
        return self.tokens[self.i + off]

    def cur(self):
        return self.tokens[self.i]

    def at(self, ttype):
        return self.cur().type == ttype

    def at_kw(self, kw):
        t = self.cur()
        return t.type == T.KEYWORD and t.value == kw

    def advance(self):
        t = self.tokens[self.i]
        self.i += 1
        return t

    def expect(self, ttype, what=None):
        if self.cur().type != ttype:
            what = what or ttype.name
            raise ParseError(f"expected {what}, got {self.cur().type.name} ({self.cur().value!r})", self.cur().line)
        return self.advance()

    def expect_kw(self, kw):
        if not self.at_kw(kw):
            raise ParseError(f"expected '{kw}', got {self.cur().value!r}", self.cur().line)
        return self.advance()

    def skip_newlines(self):
        while self.at(T.NEWLINE):
            self.advance()

    # --- entry ---
    def parse_program(self):
        stmts = []
        self.skip_newlines()
        while not self.at(T.EOF):
            stmts.extend(self.parse_statement())
            self.skip_newlines()
        # Add collected lambda functions at the top level
        stmts = self._lambdas + stmts
        return stmts

    # --- statements ---
    def parse_statement(self):
        """Returns a list of statements (at least one).

        Compound statements return a single-element list.
        Simple statements may return multiple elements when separated by ';'.
        """
        if self.at_kw("if"):
            return [self.parse_if()]
        if self.at_kw("while"):
            return [self.parse_while()]
        if self.at_kw("for"):
            return [self.parse_for()]
        if self.at_kw("def"):
            return [self.parse_funcdef()]
        if self.at_kw("class"):
            return [self.parse_classdef()]
        if self.at_kw("import"):
            return [self.parse_import()]
        if self.at_kw("from"):
            return [self.parse_import_from()]
        if self.at_kw("with"):
            return [self.parse_with()]
        if self.at_kw("try"):
            return [self.parse_try()]
        if self.at_kw("raise"):
            return [self.parse_raise()]
        # one or more simple statements separated by ';'
        stmts = self.parse_simple_stmt_list()
        self.expect(T.NEWLINE, "newline")
        return stmts

    def parse_simple_stmt_list(self):
        """Parse small_stmt (';' small_stmt)* [';'] without consuming NEWLINE."""
        stmts = [self.parse_simple_stmt()]
        while self.at(T.SEMI):
            self.advance()
            if self.at(T.NEWLINE) or self.at(T.EOF) or self.at(T.DEDENT):
                break  # trailing semicolon
            stmts.append(self.parse_simple_stmt())
        return stmts

    def parse_simple_stmt(self):
        t = self.cur()
        if self.at_kw("return"):
            self.advance()
            if self.at(T.NEWLINE) or self.at(T.EOF):
                return A.Return(None, t.line)
            val = self.parse_expr()
            # Support tuple return: return a, b
            if self.at(T.COMMA):
                elems = [val]
                while self.at(T.COMMA):
                    self.advance()
                    if self.at(T.NEWLINE) or self.at(T.SEMI) or self.at(T.EOF):
                        break
                    elems.append(self.parse_expr())
                val = A.TupleLit(elems, t.line)
            return A.Return(val, t.line)
        if self.at_kw("break"):
            self.advance()
            return A.Break(t.line)
        if self.at_kw("continue"):
            self.advance()
            return A.Continue(t.line)
        if self.at_kw("pass"):
            self.advance()
            return A.Pass(t.line)
        if self.at_kw("global"):
            self.advance()
            names = [self.expect(T.IDENTIFIER).value]
            while self.at(T.COMMA):
                self.advance()
                names.append(self.expect(T.IDENTIFIER).value)
            return A.Global(names, t.line)
        # assignment or expression statement
        expr = self.parse_expr()
        # Support tuple unpacking on LHS: a, b = ...
        if self.at(T.COMMA):
            left_elements = [expr]
            while self.at(T.COMMA):
                self.advance()
                if self.at(T.ASSIGN) or self.at(T.NEWLINE) or self.at(T.SEMI):
                    break  # trailing comma
                left_elements.append(self.parse_expr())
            expr = A.TupleLit(left_elements, t.line)
        if self.at(T.ASSIGN):
            self.advance()
            value = self.parse_expr()
            # Support tuple on RHS: a, b = c, d
            if self.at(T.COMMA):
                right_elements = [value]
                while self.at(T.COMMA):
                    self.advance()
                    if self.at(T.NEWLINE) or self.at(T.SEMI) or self.at(T.EOF):
                        break
                    right_elements.append(self.parse_expr())
                value = A.TupleLit(right_elements, t.line)
            if not isinstance(expr, (A.Name, A.Subscript, A.Attribute, A.TupleLit)):
                raise ParseError("invalid assignment target", t.line)
            return A.Assign(expr, value, t.line)
        if self.cur().type in (T.PLUS_ASSIGN, T.MINUS_ASSIGN, T.STAR_ASSIGN, T.SLASH_ASSIGN):
            op = self.advance().value[0]  # '+', '-', '*', '/'
            value = self.parse_expr()
            if not isinstance(expr, (A.Name, A.Subscript, A.Attribute)):
                raise ParseError("invalid augmented assignment target", t.line)
            return A.AugAssign(expr, op, value, t.line)
        return A.ExprStmt(expr, t.line)

    def parse_suite(self):
        self.expect(T.COLON, "':'")
        if self.at(T.NEWLINE):
            self.advance()
            self.skip_newlines()
            self.expect(T.INDENT, "INDENT")
            stmts = []
            self.skip_newlines()
            while not self.at(T.DEDENT) and not self.at(T.EOF):
                stmts.extend(self.parse_statement())
                self.skip_newlines()
            if self.at(T.DEDENT):
                self.advance()
            return stmts
        # single-line suite: simple_stmt (';' simple_stmt)*
        stmts = self.parse_simple_stmt_list()
        # Consume trailing NEWLINE so subsequent elif/else checks work.
        if self.at(T.NEWLINE):
            self.advance()
        return stmts

    def parse_if(self):
        t = self.advance()  # 'if'
        cond = self.parse_expr()
        body = self.parse_suite()
        branches = [(cond, body)]
        orelse = []
        while self.at_kw("elif"):
            self.advance()
            ec = self.parse_expr()
            eb = self.parse_suite()
            branches.append((ec, eb))
        if self.at_kw("else"):
            self.advance()
            orelse = self.parse_suite()
        return A.If(branches, orelse, t.line)

    def parse_while(self):
        t = self.advance()
        cond = self.parse_expr()
        body = self.parse_suite()
        orelse = []
        if self.at_kw("else"):
            self.advance()
            orelse = self.parse_suite()
        return A.While(cond, body, orelse, t.line)

    def parse_for(self):
        t = self.advance()
        # Support tuple unpacking: for a, b in ... or for (a, b) in ...
        var = self._parse_for_target()
        self.expect_kw("in")
        iterable = self.parse_expr()
        body = self.parse_suite()
        orelse = []
        if self.at_kw("else"):
            self.advance()
            orelse = self.parse_suite()
        return A.For(var, iterable, body, orelse, t.line)

    def _parse_for_target(self):
        """Parse a for-loop target. Returns a list of (str | list).
        Examples:
          x            -> ["x"]
          a, b         -> ["a", "b"]
          (a, b)       -> ["a", "b"]
          rank, (w, c) -> ["rank", ["w", "c"]]
        """
        first = self._parse_single_target()
        targets = [first]
        while self.at(T.COMMA):
            self.advance()
            if self.at_kw("in"):
                break
            targets.append(self._parse_single_target())
        return targets

    def _parse_single_target(self):
        if self.at(T.LPAREN):
            self.advance()
            inner = [self._parse_single_target()]
            while self.at(T.COMMA):
                self.advance()
                if self.at(T.RPAREN):
                    break
                inner.append(self._parse_single_target())
            self.expect(T.RPAREN, "')'")
            return inner
        return self.expect(T.IDENTIFIER).value

    def parse_funcdef(self):
        t = self.advance()  # 'def'
        name = self.expect(T.IDENTIFIER).value
        self.expect(T.LPAREN, "'('")
        params = []
        defaults = {}
        if not self.at(T.RPAREN):
            self._parse_param(params, defaults)
            while self.at(T.COMMA):
                self.advance()
                if self.at(T.RPAREN):
                    break
                self._parse_param(params, defaults)
        self.expect(T.RPAREN, "')'")
        body = self.parse_suite()
        return A.FuncDef(name, params, body, t.line, defaults=defaults)

    def _parse_param(self, params, defaults):
        pname = self.expect(T.IDENTIFIER).value
        params.append(pname)
        if self.at(T.ASSIGN):
            self.advance()
            defaults[pname] = self.parse_expr()

    def parse_classdef(self):
        t = self.advance()  # 'class'
        name = self.expect(T.IDENTIFIER).value
        # optional base class (ignored for now)
        if self.at(T.LPAREN):
            self.advance()
            while not self.at(T.RPAREN):
                self.advance()
            self.advance()
        body = self.parse_suite()
        # body should be a list of FuncDef (methods) and pass
        methods = []
        for s in body:
            if isinstance(s, A.FuncDef):
                methods.append(s)
            elif isinstance(s, A.Pass):
                pass
            # ignore other statements
        return A.ClassDef(name, methods, t.line)

    def parse_import(self):
        t = self.advance()  # 'import'
        module = self.expect(T.IDENTIFIER).value
        alias = None
        if self.at_kw("as"):
            self.advance()
            alias = self.expect(T.IDENTIFIER).value
        self.expect(T.NEWLINE, "newline")
        return A.Import(module, alias, t.line)

    def parse_import_from(self):
        t = self.advance()  # 'from'
        module = self.expect(T.IDENTIFIER).value
        while self.at(T.DOT):
            self.advance()
            module += "." + self.expect(T.IDENTIFIER).value
        self.expect_kw("import")
        names = [self.expect(T.IDENTIFIER).value]
        while self.at(T.COMMA):
            self.advance()
            names.append(self.expect(T.IDENTIFIER).value)
        self.expect(T.NEWLINE, "newline")
        return A.ImportFrom(module, names, t.line)

    def parse_with(self):
        t = self.advance()  # 'with'
        items = []
        while True:
            ctx = self.parse_expr()
            var = None
            if self.at_kw("as"):
                self.advance()
                var = self.expect(T.IDENTIFIER).value
            items.append((ctx, var))
            if not self.at(T.COMMA):
                break
            self.advance()
        body = self.parse_suite()
        return A.With(items, body, t.line)

    def parse_try(self):
        t = self.advance()  # 'try'
        body = self.parse_suite()
        handlers = []
        while self.at_kw("except"):
            self.advance()
            exc_type = None
            exc_name = None
            if not self.at(T.COLON):
                exc_type = self.parse_expr()
                if self.at_kw("as"):
                    self.advance()
                    exc_name = self.expect(T.IDENTIFIER).value
            handler_body = self.parse_suite()
            handlers.append((exc_type, exc_name, handler_body))
        return A.Try(body, handlers, t.line)

    def parse_raise(self):
        t = self.advance()  # 'raise'
        exc = None
        if not self.at(T.NEWLINE) and not self.at(T.SEMI):
            exc = self.parse_expr()
        self.expect(T.NEWLINE, "newline")
        return A.Raise(exc, t.line)

    # --- expressions ---
    def parse_expr(self):
        return self.parse_ternary()

    def parse_ternary(self):
        expr = self.parse_or()
        if self.at_kw("if"):
            self.advance()
            cond = self.parse_or()
            self.expect_kw("else")
            else_ = self.parse_ternary()
            return A.IfExp(cond, expr, else_, expr.line)
        return expr

    def parse_or(self):
        left = self.parse_and()
        while self.at(T.OR):
            t = self.advance()
            right = self.parse_and()
            left = A.BoolOp("or", left, right, t.line)
        return left

    def parse_and(self):
        left = self.parse_not()
        while self.at(T.AND):
            t = self.advance()
            right = self.parse_not()
            left = A.BoolOp("and", left, right, t.line)
        return left

    def parse_not(self):
        if self.at(T.NOT):
            t = self.advance()
            operand = self.parse_not()
            return A.UnaryOp("not", operand, t.line)
        return self.parse_comparison()

    def parse_comparison(self):
        left = self.parse_additive()
        # Handle is / is not
        if self.at_kw("is"):
            t = self.advance()
            negate = False
            if self.at(T.NOT):  # 'not' is tokenized as NOT, not KEYWORD
                self.advance()
                negate = True
            right = self.parse_additive()
            return A.IsOp(left, right, negate, t.line)
        # Handle comparison operators (including chained: a < b < c, 'in', 'not in')
        ops = []
        operands = [left]
        while True:
            op = None
            if self.cur().type in (T.EQ, T.NEQ, T.LT, T.GT, T.LE, T.GE):
                t = self.advance()
                op_map = {T.EQ: "==", T.NEQ: "!=", T.LT: "<", T.GT: ">", T.LE: "<=", T.GE: ">="}
                op = op_map[t.type]
            elif self.at_kw("in"):
                t = self.advance()
                op = "in"
            elif self.at(T.NOT):
                t = self.advance()
                if self.at_kw("in"):
                    self.advance()
                    op = "not in"
                else:
                    # 'not' as unary not at this level: bail out
                    # The 'not' token was consumed; we need to handle it as unary.
                    # Wrap 'left' in UnaryOp("not", left) and continue parsing.
                    operand = self.parse_comparison()
                    return A.UnaryOp("not", operand, t.line)
            if op is None:
                break
            ops.append(op)
            operands.append(self.parse_additive())
        if len(ops) == 0:
            return left
        if len(ops) == 1:
            return A.BinOp(ops[0], operands[0], operands[1], left.line)
        return A.Compare(ops, operands, left.line)

    def parse_additive(self):
        left = self.parse_multiplicative()
        while self.cur().type in (T.PLUS, T.MINUS):
            t = self.advance()
            op = t.value
            right = self.parse_multiplicative()
            left = A.BinOp(op, left, right, t.line)
        return left

    def parse_multiplicative(self):
        left = self.parse_unary()
        while self.cur().type in (T.STAR, T.SLASH, T.DOUBLE_SLASH, T.PERCENT):
            t = self.advance()
            op_map = {T.STAR: "*", T.SLASH: "/", T.DOUBLE_SLASH: "//", T.PERCENT: "%"}
            op = op_map[t.type]
            right = self.parse_unary()
            left = A.BinOp(op, left, right, t.line)
        return left

    def parse_unary(self):
        if self.cur().type in (T.PLUS, T.MINUS):
            t = self.advance()
            op = t.value
            operand = self.parse_unary()
            return A.UnaryOp(op, operand, t.line)
        return self.parse_power()

    def parse_power(self):
        base = self.parse_postfix()
        if self.at(T.DOUBLE_STAR):
            t = self.advance()
            exp = self.parse_unary()  # right associative
            return A.BinOp("**", base, exp, t.line)
        return base

    def parse_postfix(self):
        expr = self.parse_atom()
        while True:
            if self.at(T.LPAREN):
                t = self.advance()
                args = []
                kwargs = {}
                if not self.at(T.RPAREN):
                    self._parse_one_arg(args, kwargs)
                    while self.at(T.COMMA):
                        self.advance()
                        if self.at(T.RPAREN):
                            break
                        self._parse_one_arg(args, kwargs)
                self.expect(T.RPAREN, "')'")
                expr = A.Call(expr, args, t.line, kwargs=kwargs)
            elif self.at(T.LBRACKET):
                t = self.advance()
                # Check for slice: a[start:stop] or a[:stop] or a[start:] or a[::step]
                start = None
                stop = None
                step = None
                is_slice = False
                if self.at(T.COLON):
                    is_slice = True
                else:
                    start = self.parse_expr()
                    if self.at(T.COLON):
                        is_slice = True
                if is_slice:
                    self.advance()  # consume first ':'
                    if not self.at(T.COLON) and not self.at(T.RBRACKET):
                        stop = self.parse_expr()
                    if self.at(T.COLON):
                        self.advance()  # consume second ':'
                        if not self.at(T.RBRACKET):
                            step = self.parse_expr()
                    self.expect(T.RBRACKET, "']'")
                    expr = A.Slice(expr, start, stop, step, t.line)
                else:
                    # start already holds the index expression
                    self.expect(T.RBRACKET, "']'")
                    expr = A.Subscript(expr, start, t.line)
            elif self.at(T.DOT):
                t = self.advance()
                attr = self.expect(T.IDENTIFIER, "attribute name").value
                if self.at(T.LPAREN):
                    self.advance()
                    args = []
                    kwargs = {}
                    if not self.at(T.RPAREN):
                        self._parse_one_arg(args, kwargs)
                        while self.at(T.COMMA):
                            self.advance()
                            if self.at(T.RPAREN):
                                break
                            self._parse_one_arg(args, kwargs)
                    self.expect(T.RPAREN, "')'")
                    expr = A.MethodCall(expr, attr, args, t.line, kwargs=kwargs)
                else:
                    expr = A.Attribute(expr, attr, t.line)
            else:
                break
        return expr

    def _parse_one_arg(self, args, kwargs):
        # Support *expr argument unpacking
        if self.at(T.STAR):
            t = self.advance()
            args.append(A.Starred(self.parse_expr(), t.line))
            return
        # Support keyword arguments: name = expr (used by print sep/end).
        if self.cur().type == T.IDENTIFIER and self.peek(1).type == T.ASSIGN:
            name = self.advance().value
            self.advance()  # '='
            value = self.parse_expr()
            kwargs[name] = value
        else:
            args.append(self.parse_expr())

    def parse_atom(self):
        t = self.cur()
        if t.type == T.INTEGER:
            self.advance()
            return A.NumberLit(t.value, t.line)
        if t.type == T.FLOAT:
            self.advance()
            return A.NumberLit(t.value, t.line)
        if t.type == T.STRING:
            self.advance()
            # Check for f-string (value is a tuple ("FSTRING", content))
            if isinstance(t.value, tuple) and t.value[0] == "FSTRING":
                return self._parse_fstring(t.value[1], t.line)
            return A.StringLit(t.value, t.line)
        if t.type == T.IDENTIFIER:
            self.advance()
            return A.Name(t.value, t.line)
        if t.type == T.KEYWORD:
            if t.value == "True":
                self.advance()
                return A.BoolLit(True, t.line)
            if t.value == "False":
                self.advance()
                return A.BoolLit(False, t.line)
            if t.value == "None":
                self.advance()
                return A.NoneLit(t.line)
            if t.value == "lambda":
                return self._parse_lambda(t)
        if t.type == T.LPAREN:
            self.advance()
            if self.at(T.RPAREN):
                self.advance()
                return A.TupleLit([], t.line)
            expr = self.parse_expr()
            if self.at(T.COMMA):
                # tuple
                elements = [expr]
                while self.at(T.COMMA):
                    self.advance()
                    if self.at(T.RPAREN):
                        break
                    elements.append(self.parse_expr())
                self.expect(T.RPAREN, "')'")
                return A.TupleLit(elements, t.line)
            self.expect(T.RPAREN, "')'")
            return expr
        if t.type == T.LBRACKET:
            self.advance()
            if self.at(T.RBRACKET):
                self.advance()
                return A.ListLit([], t.line)
            first = self.parse_expr()
            # Check for list comprehension: [expr for var in iter (if cond)*]
            if self.at_kw("for"):
                return self._parse_list_comp(first, t.line)
            elements = [first]
            while self.at(T.COMMA):
                self.advance()
                if self.at(T.RBRACKET):
                    break
                elements.append(self.parse_expr())
            self.expect(T.RBRACKET, "']'")
            return A.ListLit(elements, t.line)
        if t.type == T.LBRACE:
            self.advance()
            pairs = []
            if not self.at(T.RBRACE):
                key = self.parse_expr()
                self.expect(T.COLON, "':'")
                val = self.parse_expr()
                # Dict comprehension: {k: v for var in iter (if cond)*}
                if self.at_kw("for"):
                    var, iterable, conds = self._parse_comp_for_clauses(T.RBRACE)
                    return A.DictComp(key, val, var, iterable, conds, t.line)
                pairs.append((key, val))
                while self.at(T.COMMA):
                    self.advance()
                    if self.at(T.RBRACE):
                        break
                    key = self.parse_expr()
                    self.expect(T.COLON, "':'")
                    val = self.parse_expr()
                    pairs.append((key, val))
            self.expect(T.RBRACE, "'}'")
            return A.DictLit(pairs, t.line)
        raise ParseError(f"unexpected token {t.type.name} ({t.value!r})", t.line)

    def _parse_lambda(self, t):
        self.advance()  # 'lambda'
        params = []
        if not self.at(T.COLON):
            params.append(self.expect(T.IDENTIFIER).value)
            while self.at(T.COMMA):
                self.advance()
                params.append(self.expect(T.IDENTIFIER).value)
        self.expect(T.COLON, "':'")
        body = self.parse_expr()
        # Create a hidden function for the lambda
        name = f"__lambda_{self._lambda_counter}"
        self._lambda_counter += 1
        func_def = A.FuncDef(name, params, [A.Return(body, t.line)], t.line)
        self._lambdas.append(func_def)
        # Return a reference to the function
        return A.Name(name, t.line)

    def _parse_list_comp(self, element, line):
        """Parse the 'for var in iter (if cond)*' part of a list comprehension."""
        var, iterable, conditions = self._parse_comp_for_clauses(T.RBRACKET)
        return A.ListComp(element, var, iterable, conditions, line)

    def _parse_comp_for_clauses(self, end_tok):
        """Parse 'for var[, var2] in iterable (if cond)*' followed by end_tok.
        Returns (var_list, iterable, conditions)."""
        self.expect_kw("for")
        first = self.expect(T.IDENTIFIER).value
        var = [first]
        while self.at(T.COMMA):
            self.advance()
            var.append(self.expect(T.IDENTIFIER).value)
        self.expect_kw("in")
        iterable = self.parse_or()
        conditions = []
        while self.at_kw("if"):
            self.advance()
            conditions.append(self.parse_or())
        end_name = "']'" if end_tok == T.RBRACKET else "'}'"
        self.expect(end_tok, end_name)
        return var, iterable, conditions

    def _parse_fstring(self, content, line):
        """Parse f-string content into parts (literal strings and expressions)."""
        parts = []
        i = 0
        n = len(content)
        literal = ""
        while i < n:
            c = content[i]
            if c == "{" and i + 1 < n and content[i + 1] == "{":
                literal += "{"
                i += 2
                continue
            if c == "}" and i + 1 < n and content[i + 1] == "}":
                literal += "}"
                i += 2
                continue
            if c == "{":
                if literal:
                    parts.append((A.StringLit(literal, line), False))
                    literal = ""
                i += 1
                # Read expression until matching } (handle format spec after :)
                expr_str = ""
                depth = 0
                while i < n and (content[i] != "}" or depth > 0):
                    if content[i] == "{":
                        depth += 1
                    elif content[i] == "}":
                        depth -= 1
                    if content[i] == ":" and depth == 0:
                        break
                    expr_str += content[i]
                    i += 1
                # Check for format spec
                spec = ""
                if i < n and content[i] == ":":
                    i += 1
                    while i < n and content[i] != "}":
                        spec += content[i]
                        i += 1
                if i < n and content[i] == "}":
                    i += 1
                # Parse the expression string
                from lexer import Lexer
                expr_tokens = Lexer(expr_str).tokenize()
                expr_ast = Parser(expr_tokens).parse_expr()
                if spec:
                    # Attach format spec to the expression
                    parts.append((expr_ast, spec))
                else:
                    parts.append((expr_ast, True))
                continue
            literal += c
            i += 1
        if literal:
            parts.append((A.StringLit(literal, line), False))
        return A.FString(parts, line)


def parse(tokens):
    return Parser(tokens).parse_program()
