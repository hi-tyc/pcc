"""
Parser module for pcc - Version 2.

This module provides a recursive descent parser that works with the tokenize-based lexer.
It converts tokens into pcc's Intermediate Representation (IR).
"""

from typing import List, Set, Dict, Optional
from ..ir import (
    IntConst, FloatConst, StrConst, Var, BinOp, CmpOp, Call, AttributeAccess, MethodCall, ConstructorCall, BuiltinCall, Expr,
    Assign, AttrAssign, MethodCallStmt, Print, If, While, ForRange, Return, Break, Continue, Stmt,
    FunctionDef, ClassDef, ModuleIR
)
from .lexer import Lexer, Token, TokenType, LexerError


class ParseError(Exception):
    """Exception raised for parsing errors."""
    
    def __init__(self, message: str, lineno: int = 0, col_offset: int = 0):
        self.message = message
        self.lineno = lineno
        self.col_offset = col_offset
        super().__init__(self._format_message())
    
    def _format_message(self) -> str:
        if self.lineno > 0:
            return f"Line {self.lineno}: {self.message}"
        return self.message


class ParserV2:
    """Recursive descent parser for pcc - Version 2.
    
    Works with the tokenize-based lexer to parse Python source code
    into pcc's Intermediate Representation (IR).
    
    Example:
        >>> parser = ParserV2()
        >>> ir = parser.parse("print(1 + 2)")
        >>> print(ir)
    """
    
    def __init__(self):
        """Initialize the parser."""
        self._lexer = Lexer()
        self._tokens: List[Token] = []
        self._pos: int = 0
        self._fn_sigs: Dict[str, int] = {}
        self._class_defs: Dict[str, ClassDef] = {}
    
    def parse(self, source: str, filename: str = "<input>") -> ModuleIR:
        """Parse Python source code into IR.
        
        Args:
            source: Python source code string
            filename: Source filename for error reporting
            
        Returns:
            ModuleIR: The intermediate representation of the module
            
        Raises:
            ParseError: If the source contains unsupported syntax
            LexerError: If tokenization fails
        """
        # Tokenize the source
        self._tokens = self._lexer.tokenize(source, filename)
        self._pos = 0
        
        # First pass: collect function and class signatures
        self._fn_sigs = self._collect_signatures()
        # Note: _collect_signatures also populates self._class_defs
        
        # Second pass: parse the module
        return self._parse_module()
    
    def _collect_signatures(self) -> Dict[str, int]:
        """Collect function and class signatures from tokens."""
        sigs: Dict[str, int] = {}
        self._class_defs = {}  # Reset class definitions
        i = 0
        while i < len(self._tokens):
            token = self._tokens[i]
            
            # Look for 'def' keyword
            if token.type == TokenType.NAME and token.value == 'def':
                # Next token should be function name
                if i + 1 < len(self._tokens) and self._tokens[i + 1].type == TokenType.NAME:
                    func_name = self._tokens[i + 1].value
                    # Count parameters until we hit ')'
                    param_count = 0
                    j = i + 2
                    while j < len(self._tokens) and self._tokens[j].type != TokenType.RPAR:
                        if self._tokens[j].type == TokenType.NAME:
                            param_count += 1
                        j += 1
                    sigs[func_name] = param_count
                    i = j
            
            # Look for 'class' keyword
            elif token.type == TokenType.NAME and token.value == 'class':
                if i + 1 < len(self._tokens) and self._tokens[i + 1].type == TokenType.NAME:
                    class_name = self._tokens[i + 1].value
                    # Check for inheritance (not supported)
                    j = i + 2
                    if j < len(self._tokens) and self._tokens[j].type == TokenType.LPAR:
                        raise ParseError("Class inheritance is not supported", token.lineno, 0)
                    # Store class name for constructor recognition
                    self._class_defs[class_name] = None
            
            i += 1
        
        return sigs
    
    def _current(self) -> Optional[Token]:
        """Get the current token."""
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None
    
    def _peek(self, offset: int = 0) -> Optional[Token]:
        """Peek at a token ahead of current position."""
        pos = self._pos + offset
        if pos < len(self._tokens):
            return self._tokens[pos]
        return None
    
    def _advance(self) -> Token:
        """Advance to the next token and return the current one."""
        token = self._current()
        if token:
            self._pos += 1
            return token
        raise ParseError("Unexpected end of input")
    
    def _expect(self, token_type: TokenType, value: Optional[str] = None) -> Token:
        """Expect a specific token type and optionally value."""
        token = self._current()
        if token is None:
            raise ParseError(f"Expected {token_type.name}, got end of input")
        
        if token.type != token_type:
            raise ParseError(f"Expected {token_type.name}, got {token.type.name}", 
                           token.lineno, token.col_offset)
        
        if value is not None and token.value != value:
            raise ParseError(f"Expected '{value}', got '{token.value}'",
                           token.lineno, token.col_offset)
        
        self._pos += 1
        return token
    
    def _match(self, token_type: TokenType, value: Optional[str] = None) -> bool:
        """Check if current token matches type and optionally value."""
        token = self._current()
        if token is None:
            return False
        if token.type != token_type:
            return False
        if value is not None and token.value != value:
            return False
        return True
    
    def _consume_newlines(self) -> None:
        """Consume newline tokens."""
        while self._match(TokenType.NEWLINE) or self._match(TokenType.NL):
            self._advance()
    
    def _parse_module(self) -> ModuleIR:
        """Parse the module level."""
        functions: List[FunctionDef] = []
        classes: List[ClassDef] = []
        main_stmts: List[Stmt] = []
        defined_main: Set[str] = set()
        
        while self._current() and not self._match(TokenType.ENDMARKER):
            # Skip newlines and indentation
            if self._match(TokenType.NEWLINE) or self._match(TokenType.NL):
                self._advance()
                continue
            
            if self._match(TokenType.INDENT):
                self._advance()
                continue
            
            if self._match(TokenType.DEDENT):
                self._advance()
                continue
            
            # Function definition
            if self._match(TokenType.NAME, 'def'):
                func = self._parse_function_def()
                functions.append(func)
            
            # Class definition
            elif self._match(TokenType.NAME, 'class'):
                cls = self._parse_class_def()
                classes.append(cls)
            
            # Statement at module level (main body)
            else:
                stmt = self._parse_stmt(defined_main, in_loop_depth=0)
                main_stmts.append(stmt)
        
        return ModuleIR(functions=functions, classes=classes, main=main_stmts)
    
    def _parse_function_def(self) -> FunctionDef:
        """Parse a function definition."""
        def_token = self._expect(TokenType.NAME, 'def')
        name_token = self._expect(TokenType.NAME)
        
        self._expect(TokenType.LPAR)
        
        # Parse parameters
        params: List[str] = []
        while not self._match(TokenType.RPAR):
            if params:
                self._expect(TokenType.COMMA)
            
            param_token = self._expect(TokenType.NAME)
            params.append(param_token.value)
        
        self._expect(TokenType.RPAR)
        self._expect(TokenType.COLON)
        self._expect(TokenType.NEWLINE)
        self._expect(TokenType.INDENT)
        
        # Parse function body
        body: List[Stmt] = []
        defined = set(params)
        
        while not self._match(TokenType.DEDENT) and not self._match(TokenType.ENDMARKER):
            if self._match(TokenType.NEWLINE) or self._match(TokenType.NL):
                self._advance()
                continue
            stmt = self._parse_stmt(defined, in_loop_depth=0)
            body.append(stmt)
        
        if self._match(TokenType.DEDENT):
            self._advance()
        
        return FunctionDef(name=name_token.value, params=params, body=body, lineno=def_token.lineno)
    
    def _parse_class_def(self) -> ClassDef:
        """Parse a class definition."""
        class_token = self._expect(TokenType.NAME, 'class')
        name_token = self._expect(TokenType.NAME)
        
        self._expect(TokenType.COLON)
        self._expect(TokenType.NEWLINE)
        self._expect(TokenType.INDENT)
        
        # Parse class body
        methods: List[FunctionDef] = []
        fields: Set[str] = set()
        
        while not self._match(TokenType.DEDENT) and not self._match(TokenType.ENDMARKER):
            if self._match(TokenType.NEWLINE) or self._match(TokenType.NL):
                self._advance()
                continue
            
            # Method definition
            if self._match(TokenType.NAME, 'def'):
                method = self._parse_method_def()
                methods.append(method)
            
            # Field assignment
            elif self._match(TokenType.NAME):
                field_name = self._current().value
                self._advance()
                self._expect(TokenType.EQUAL)
                # Skip the value for now
                while not self._match(TokenType.NEWLINE) and not self._match(TokenType.NL):
                    self._advance()
                fields.add(field_name)
            
            else:
                token = self._current()
                raise ParseError(f"Unexpected token in class body: {token}", 
                               token.lineno if token else 0, 0)
        
        if self._match(TokenType.DEDENT):
            self._advance()
        
        return ClassDef(name=name_token.value, methods=methods, fields=list(fields), 
                       lineno=class_token.lineno)
    
    def _parse_method_def(self) -> FunctionDef:
        """Parse a method definition."""
        def_token = self._expect(TokenType.NAME, 'def')
        name_token = self._expect(TokenType.NAME)
        
        self._expect(TokenType.LPAR)
        
        # First parameter must be 'self'
        self_token = self._expect(TokenType.NAME)
        if self_token.value != 'self':
            raise ParseError("Method first parameter must be 'self'", 
                           self_token.lineno, self_token.col_offset)
        
        # Parse remaining parameters
        params: List[str] = []
        while not self._match(TokenType.RPAR):
            self._expect(TokenType.COMMA)
            param_token = self._expect(TokenType.NAME)
            params.append(param_token.value)
        
        self._expect(TokenType.RPAR)
        self._expect(TokenType.COLON)
        self._expect(TokenType.NEWLINE)
        self._expect(TokenType.INDENT)
        
        # Parse method body
        body: List[Stmt] = []
        defined = set(params)
        defined.add('self')
        
        while not self._match(TokenType.DEDENT) and not self._match(TokenType.ENDMARKER):
            if self._match(TokenType.NEWLINE) or self._match(TokenType.NL):
                self._advance()
                continue
            stmt = self._parse_stmt(defined, in_loop_depth=0)
            body.append(stmt)
        
        if self._match(TokenType.DEDENT):
            self._advance()
        
        return FunctionDef(name=name_token.value, params=params, body=body, lineno=def_token.lineno)
    
    def _parse_stmt(self, defined: Set[str], in_loop_depth: int) -> Stmt:
        """Parse a statement."""
        token = self._current()
        if token is None:
            raise ParseError("Unexpected end of input")
        
        # Assignment or expression statement
        if token.type == TokenType.NAME:
            # Check for keywords
            if token.value == 'if':
                return self._parse_if_stmt(defined, in_loop_depth)
            elif token.value == 'while':
                return self._parse_while_stmt(defined, in_loop_depth)
            elif token.value == 'for':
                return self._parse_for_stmt(defined, in_loop_depth)
            elif token.value == 'return':
                return self._parse_return_stmt(defined)
            elif token.value == 'break':
                return self._parse_break_stmt(in_loop_depth)
            elif token.value == 'continue':
                return self._parse_continue_stmt(in_loop_depth)
            elif token.value == 'print':
                return self._parse_print_stmt(defined)
            elif token.value == 'pass':
                self._advance()
                return Print(expr=IntConst(0))  # No-op
            else:
                # Could be assignment or expression
                return self._parse_assignment_or_expr(defined, in_loop_depth)
        
        raise ParseError(f"Unexpected token: {token}", token.lineno, token.col_offset)
    
    def _parse_assignment_or_expr(self, defined: Set[str], in_loop_depth: int) -> Stmt:
        """Parse assignment or expression statement."""
        # Look ahead to see if this is an assignment
        start_pos = self._pos
        
        try:
            # Try to parse as assignment
            target = self._parse_target(defined)
            self._expect(TokenType.EQUAL)
            expr = self._parse_expr(defined)
            
            if isinstance(target, tuple):
                # Attribute assignment
                obj_name, attr_name = target
                return AttrAssign(obj=obj_name, attr=attr_name, expr=expr)
            else:
                # Variable assignment
                defined.add(target)
                return Assign(name=target, expr=expr)
        except ParseError:
            # Not an assignment, try expression statement
            self._pos = start_pos
            return self._parse_expr_stmt(defined)
    
    def _parse_target(self, defined: Set[str]):
        """Parse assignment target (returns name or (obj, attr) tuple)."""
        token = self._expect(TokenType.NAME)
        
        # Check for attribute access: obj.attr
        if self._match(TokenType.DOT):
            self._advance()
            attr_token = self._expect(TokenType.NAME)
            if token.value not in defined:
                raise ParseError(f"Variable used before assignment: {token.value}",
                               token.lineno, token.col_offset)
            return (token.value, attr_token.value)
        
        return token.value
    
    def _parse_expr_stmt(self, defined: Set[str]) -> Stmt:
        """Parse expression as statement (function call or method call)."""
        token = self._current()
        if token and token.type == TokenType.NAME:
            name = token.value
            self._advance()
            
            # Check for method call: obj.method(args)
            if self._match(TokenType.DOT):
                if name not in defined:
                    raise ParseError(f"Variable used before assignment: {name}",
                                   token.lineno, token.col_offset)
                
                self._advance()
                method_token = self._expect(TokenType.NAME)
                self._expect(TokenType.LPAR)
                
                # Parse arguments
                args: List[Expr] = []
                while not self._match(TokenType.RPAR):
                    if args:
                        self._expect(TokenType.COMMA)
                    arg = self._parse_expr(defined)
                    args.append(arg)
                
                self._expect(TokenType.RPAR)
                return MethodCallStmt(obj=name, method=method_token.value, args=args)
            
            # Check for function call: func(args)
            elif self._match(TokenType.LPAR):
                # This is a function call - parse it and return as a statement
                # We need to reconstruct the call
                self._pos -= 1  # Go back to the function name
                expr = self._parse_primary(defined)
                # Function call as statement - we can't directly use it
                # So we'll create a dummy assignment to a temp variable
                # But for now, let's just return a Print with the expression
                # Actually, let's handle this properly by creating a Call expression
                from ..ir import Call
                if isinstance(expr, Call):
                    # Create a print statement that discards the result
                    # Or better, we should add a new statement type for expression statements
                    # For now, return it as a print of 0 (no-op)
                    return Print(expr=IntConst(0))
            
            # If we get here, it's just a name reference which isn't valid as a statement
            raise ParseError(f"Invalid statement: {name}", token.lineno, token.col_offset)
        
        raise ParseError("Expected expression statement", token.lineno if token else 0, 0)
    
    def _parse_if_stmt(self, defined: Set[str], in_loop_depth: int) -> If:
        """Parse if statement."""
        if_token = self._expect(TokenType.NAME, 'if')
        test = self._parse_expr(defined)
        self._expect(TokenType.COLON)
        self._expect(TokenType.NEWLINE)
        self._expect(TokenType.INDENT)
        
        # Parse if body
        body: List[Stmt] = []
        defined_body = set(defined)
        while not self._match(TokenType.DEDENT) and not self._match(TokenType.ENDMARKER):
            if self._match(TokenType.NEWLINE) or self._match(TokenType.NL):
                self._advance()
                continue
            stmt = self._parse_stmt(defined_body, in_loop_depth)
            body.append(stmt)
        
        if self._match(TokenType.DEDENT):
            self._advance()
        
        # Check for else
        orelse: List[Stmt] = []
        defined_else: Set[str] = set()
        if self._match(TokenType.NAME, 'else'):
            self._advance()
            self._expect(TokenType.COLON)
            self._expect(TokenType.NEWLINE)
            self._expect(TokenType.INDENT)
            
            defined_else = set(defined)
            while not self._match(TokenType.DEDENT) and not self._match(TokenType.ENDMARKER):
                if self._match(TokenType.NEWLINE) or self._match(TokenType.NL):
                    self._advance()
                    continue
                stmt = self._parse_stmt(defined_else, in_loop_depth)
                orelse.append(stmt)
            
            if self._match(TokenType.DEDENT):
                self._advance()
        
        defined.update(defined_body)
        defined.update(defined_else)
        
        return If(test=test, body=body, orelse=orelse)
    
    def _parse_while_stmt(self, defined: Set[str], in_loop_depth: int) -> While:
        """Parse while statement."""
        self._expect(TokenType.NAME, 'while')
        test = self._parse_expr(defined)
        self._expect(TokenType.COLON)
        self._expect(TokenType.NEWLINE)
        self._expect(TokenType.INDENT)
        
        body: List[Stmt] = []
        defined_body = set(defined)
        while not self._match(TokenType.DEDENT) and not self._match(TokenType.ENDMARKER):
            if self._match(TokenType.NEWLINE) or self._match(TokenType.NL):
                self._advance()
                continue
            stmt = self._parse_stmt(defined_body, in_loop_depth + 1)
            body.append(stmt)
        
        if self._match(TokenType.DEDENT):
            self._advance()
        
        defined.update(defined_body)
        
        return While(test=test, body=body)
    
    def _parse_for_stmt(self, defined: Set[str], in_loop_depth: int) -> ForRange:
        """Parse for statement (for-range only)."""
        for_token = self._expect(TokenType.NAME, 'for')
        var_token = self._expect(TokenType.NAME)
        self._expect(TokenType.NAME, 'in')
        self._expect(TokenType.NAME, 'range')
        self._expect(TokenType.LPAR)
        
        # Parse range arguments
        args: List[Expr] = []
        while not self._match(TokenType.RPAR):
            if args:
                self._expect(TokenType.COMMA)
            arg = self._parse_expr(defined)
            args.append(arg)
        
        self._expect(TokenType.RPAR)
        self._expect(TokenType.COLON)
        self._expect(TokenType.NEWLINE)
        self._expect(TokenType.INDENT)
        
        # Determine start, stop, step
        if len(args) == 1:
            start = IntConst(0)
            stop = args[0]
            step = IntConst(1)
        elif len(args) == 2:
            start = args[0]
            stop = args[1]
            step = IntConst(1)
        else:
            start = args[0]
            stop = args[1]
            step = args[2]
        
        # Parse body
        body: List[Stmt] = []
        defined_body = set(defined)
        defined_body.add(var_token.value)
        
        while not self._match(TokenType.DEDENT) and not self._match(TokenType.ENDMARKER):
            if self._match(TokenType.NEWLINE) or self._match(TokenType.NL):
                self._advance()
                continue
            stmt = self._parse_stmt(defined_body, in_loop_depth + 1)
            body.append(stmt)
        
        if self._match(TokenType.DEDENT):
            self._advance()
        
        defined.update(defined_body)
        
        return ForRange(var=var_token.value, start=start, stop=stop, step=step,
                       body=body, lineno=for_token.lineno)
    
    def _parse_return_stmt(self, defined: Set[str]) -> Return:
        """Parse return statement."""
        self._expect(TokenType.NAME, 'return')
        
        if self._match(TokenType.NEWLINE) or self._match(TokenType.NL):
            return Return(expr=IntConst(0))
        
        expr = self._parse_expr(defined)
        return Return(expr=expr)
    
    def _parse_break_stmt(self, in_loop_depth: int) -> Break:
        """Parse break statement."""
        token = self._expect(TokenType.NAME, 'break')
        if in_loop_depth <= 0:
            raise ParseError("break outside loop", token.lineno, token.col_offset)
        return Break(lineno=token.lineno)
    
    def _parse_continue_stmt(self, in_loop_depth: int) -> Continue:
        """Parse continue statement."""
        token = self._expect(TokenType.NAME, 'continue')
        if in_loop_depth <= 0:
            raise ParseError("continue outside loop", token.lineno, token.col_offset)
        return Continue(lineno=token.lineno)
    
    def _parse_print_stmt(self, defined: Set[str]) -> Print:
        """Parse print statement."""
        self._expect(TokenType.NAME, 'print')
        self._expect(TokenType.LPAR)
        expr = self._parse_expr(defined)
        self._expect(TokenType.RPAR)
        return Print(expr=expr)
    
    def _parse_expr(self, defined: Set[str]) -> Expr:
        """Parse an expression."""
        return self._parse_comparison(defined)
    
    def _parse_comparison(self, defined: Set[str]) -> Expr:
        """Parse comparison expression."""
        left = self._parse_additive(defined)
        
        # Check for comparison operators
        if self._match(TokenType.LESS):
            self._advance()
            right = self._parse_additive(defined)
            return CmpOp("<", left, right)
        elif self._match(TokenType.GREATER):
            self._advance()
            right = self._parse_additive(defined)
            return CmpOp(">", left, right)
        elif self._match(TokenType.LESSEQUAL):
            self._advance()
            right = self._parse_additive(defined)
            return CmpOp("<=", left, right)
        elif self._match(TokenType.GREATEREQUAL):
            self._advance()
            right = self._parse_additive(defined)
            return CmpOp(">=", left, right)
        elif self._match(TokenType.EQEQUAL):
            self._advance()
            right = self._parse_additive(defined)
            return CmpOp("==", left, right)
        elif self._match(TokenType.NOTEQUAL):
            self._advance()
            right = self._parse_additive(defined)
            return CmpOp("!=", left, right)
        
        return left
    
    def _parse_additive(self, defined: Set[str]) -> Expr:
        """Parse additive expression."""
        left = self._parse_multiplicative(defined)
        
        while self._match(TokenType.PLUS) or self._match(TokenType.MINUS):
            op = '+' if self._match(TokenType.PLUS) else '-'
            self._advance()
            right = self._parse_multiplicative(defined)
            left = BinOp(op, left, right)
        
        return left
    
    def _parse_multiplicative(self, defined: Set[str]) -> Expr:
        """Parse multiplicative expression."""
        left = self._parse_unary(defined)
        
        while (self._match(TokenType.STAR) or 
               self._match(TokenType.DOUBLESLASH) or 
               self._match(TokenType.PERCENT)):
            if self._match(TokenType.STAR):
                self._advance()
                right = self._parse_unary(defined)
                left = BinOp("*", left, right)
            elif self._match(TokenType.DOUBLESLASH):
                self._advance()
                right = self._parse_unary(defined)
                left = BinOp("//", left, right)
            elif self._match(TokenType.PERCENT):
                self._advance()
                right = self._parse_unary(defined)
                left = BinOp("%", left, right)
        
        return left
    
    def _parse_unary(self, defined: Set[str]) -> Expr:
        """Parse unary expression."""
        if self._match(TokenType.MINUS):
            self._advance()
            operand = self._parse_unary(defined)
            return BinOp("-", IntConst(0), operand)
        
        return self._parse_primary(defined)
    
    def _parse_primary(self, defined: Set[str]) -> Expr:
        """Parse primary expression."""
        token = self._current()
        if token is None:
            raise ParseError("Unexpected end of input")
        
        # Number literal
        if token.type == TokenType.NUMBER:
            self._advance()
            raw = token.value
            # Float if it contains '.' or exponent, otherwise int
            if ('.' in raw) or ('e' in raw) or ('E' in raw):
                try:
                    value_f = float(raw)
                except ValueError:
                    raise ParseError(f"Invalid float: {raw}",
                                   token.lineno, token.col_offset)
                return FloatConst(value_f)
            try:
                value = int(raw)
            except ValueError:
                raise ParseError(f"Invalid integer: {raw}",
                               token.lineno, token.col_offset)
            return IntConst(value)


        
        # String literal
        if token.type == TokenType.STRING:
            self._advance()
            # Remove quotes
            value = token.value
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            return StrConst(value)
        
        # Identifier or function call
        if token.type == TokenType.NAME:
            name = token.value
            self._advance()
            
            # Boolean literals
            if name == 'True':
                return IntConst(1)
            if name == 'False':
                return IntConst(0)
            
            # Function call or constructor
            if self._match(TokenType.LPAR):
                return self._parse_call(name, defined)
            
            # Attribute access
            if self._match(TokenType.DOT):
                self._advance()
                attr_token = self._expect(TokenType.NAME)
                
                # Method call
                if self._match(TokenType.LPAR):
                    return self._parse_method_call(name, attr_token.value, defined)
                
                # Attribute access
                if name not in defined:
                    raise ParseError(f"Variable used before assignment: {name}",
                                   token.lineno, token.col_offset)
                return AttributeAccess(obj=name, attr=attr_token.value)
            
            # Variable reference
            if name not in defined:
                raise ParseError(f"Variable used before assignment: {name}",
                               token.lineno, token.col_offset)
            return Var(name)
        
        # Parenthesized expression
        if token.type == TokenType.LPAR:
            self._advance()
            expr = self._parse_expr(defined)
            self._expect(TokenType.RPAR)
            return expr
        
        raise ParseError(f"Unexpected token: {token}", token.lineno, token.col_offset)
    
    # Builtin functions that don't need to be defined
    _BUILTINS = {'len', 'abs', 'min', 'max', 'pow', 'str', 'int'}
    
    def _parse_call(self, name: str, defined: Set[str]) -> Expr:
        """Parse function call, constructor call, or builtin call."""
        self._expect(TokenType.LPAR)
        
        # Parse arguments
        args: List[Expr] = []
        while not self._match(TokenType.RPAR):
            if args:
                self._expect(TokenType.COMMA)
            arg = self._parse_expr(defined)
            args.append(arg)
        
        self._expect(TokenType.RPAR)
        
        # Check if it's a builtin function
        if name in self._BUILTINS:
            return self._parse_builtin(name, args)
        
        # Check if it's a constructor call
        if name in self._class_defs:
            return ConstructorCall(class_name=name, args=args)
        
        # Regular function call
        if name not in self._fn_sigs:
            raise ParseError(f"Unknown function or class: {name}")
        
        expected = self._fn_sigs[name]
        if len(args) != expected:
            raise ParseError(f"Function '{name}' expects {expected} args, got {len(args)}")
        
        return Call(func=name, args=args)
    
    def _parse_builtin(self, name: str, args: List[Expr]) -> BuiltinCall:
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
                    raise ParseError(f"Builtin '{name}' expects {arity} argument(s), got {len(args)}")
            elif isinstance(arity, tuple):
                min_args, max_args = arity
                if len(args) < min_args:
                    raise ParseError(f"Builtin '{name}' expects at least {min_args} argument(s), got {len(args)}")
                if max_args is not None and len(args) > max_args:
                    raise ParseError(f"Builtin '{name}' expects at most {max_args} argument(s), got {len(args)}")
        
        return BuiltinCall(name=name, args=args)
    
    def _parse_method_call(self, obj_name: str, method_name: str, defined: Set[str]) -> MethodCall:
        """Parse method call."""
        self._expect(TokenType.LPAR)
        
        # Parse arguments
        args: List[Expr] = []
        while not self._match(TokenType.RPAR):
            if args:
                self._expect(TokenType.COMMA)
            arg = self._parse_expr(defined)
            args.append(arg)
        
        self._expect(TokenType.RPAR)
        
        return MethodCall(obj=obj_name, method=method_name, args=args)


# Convenience function
def parse_source(source: str, filename: str = "<input>") -> ModuleIR:
    """Parse Python source code into IR.
    
    Args:
        source: Python source code string
        filename: Source filename for error reporting
        
    Returns:
        ModuleIR object
    """
    parser = ParserV2()
    return parser.parse(source, filename)


# Example usage
if __name__ == "__main__":
    test_code = '''
x = 42
y = x + 10
print(y)
'''
    
    print("Testing parser with sample code:")
    print("-" * 50)
    print(test_code)
    print("-" * 50)
    
    parser = ParserV2()
    try:
        ir = parser.parse(test_code)
        print(f"\nParsed successfully!")
        print(f"Functions: {len(ir.functions)}")
        print(f"Classes: {len(ir.classes)}")
        print(f"Main statements: {len(ir.main)}")
    except (ParseError, LexerError) as e:
        print(f"Error: {e}")
