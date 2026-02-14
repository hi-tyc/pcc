"""
IR node definitions for pcc.

This module contains all the data classes that represent the intermediate
representation of Python code in the pcc compiler.
"""

from dataclasses import dataclass
from typing import List, Union, Optional


# ==================== Expressions ====================

@dataclass(frozen=True)
class IntConst:
    """Integer constant expression.

    Attributes:
        value: The integer value (arbitrary precision)
    """
    value: int


@dataclass(frozen=True)
class FloatConst:
    """Float constant expression.

    Attributes:
        value: The float value (C double precision)
    """
    value: float


@dataclass(frozen=True)
class StrConst:
    """String constant expression.

    Attributes:
        value: The string value
    """
    value: str


@dataclass(frozen=True)
class ListConst:
    """List literal expression (restricted subset).

    Current PCC list support is intentionally minimal: lists are homogeneous
    sequences of signed 64-bit integers.

    Attributes:
        elements: List element expressions (must evaluate to int)
    """
    elements: List["Expr"]


@dataclass(frozen=True)
class DictConst:
    """Dict literal expression (restricted subset).

    Current PCC dict support is intentionally minimal: keys are strings and
    values are signed 64-bit integers.

    Attributes:
        keys: Key expressions (must be string literals or string vars)
        values: Value expressions (must evaluate to int)
    """
    keys: List["Expr"]
    values: List["Expr"]


@dataclass(frozen=True)
class Subscript:
    """Subscript expression (obj[index]).

    For M2 this is restricted to variable subscripting for list/dict.

    Attributes:
        obj: Variable name of the container
        index: Index / key expression
    """
    obj: str
    index: "Expr"


@dataclass(frozen=True)
class Var:
    """Variable reference expression.

    Attributes:
        name: The variable name
    """
    name: str


@dataclass(frozen=True)
class BinOp:
    """Binary operation expression.

    Attributes:
        op: The operator ("+", "-", "*", "//", "%")
        left: Left operand expression
        right: Right operand expression
    """
    op: str
    left: "Expr"
    right: "Expr"


@dataclass(frozen=True)
class CmpOp:
    """Comparison operation expression.

    Attributes:
        op: The operator ("==", "!=", "<", "<=", ">", ">=")
        left: Left operand expression
        right: Right operand expression
    """
    op: str
    left: "Expr"
    right: "Expr"


@dataclass(frozen=True)
class Call:
    """Function call expression.

    Attributes:
        func: Function name
        args: List of argument expressions
    """
    func: str
    args: List["Expr"]


@dataclass(frozen=True)
class AttributeAccess:
    """Attribute access expression (obj.attr).

    Attributes:
        obj: Variable name of the object
        attr: Attribute name
    """
    obj: str
    attr: str


@dataclass(frozen=True)
class MethodCall:
    """Method call expression (obj.method(args)).

    Attributes:
        obj: Variable name of the object
        method: Method name
        args: List of argument expressions
    """
    obj: str
    method: str
    args: List["Expr"]


@dataclass(frozen=True)
class ConstructorCall:
    """Class constructor call (ClassName(args)).

    Attributes:
        class_name: Class name
        args: List of argument expressions
    """
    class_name: str
    args: List["Expr"]


@dataclass(frozen=True)
class BuiltinCall:
    """Builtin function call (e.g., len(), abs(), min(), max()).

    Attributes:
        name: Builtin function name
        args: List of argument expressions
    """
    name: str
    args: List["Expr"]


# Union type for all expressions
Expr = Union[
    IntConst,
    StrConst,
    ListConst,
    DictConst,
    Subscript,
    Var,
    BinOp,
    CmpOp,
    Call,
    AttributeAccess,
    MethodCall,
    ConstructorCall,
    BuiltinCall,
]


# ==================== Statements ====================

@dataclass(frozen=True)
class Assign:
    """Assignment statement.

    Attributes:
        name: Variable name to assign to
        expr: Expression to evaluate and assign
    """
    name: str
    expr: Expr


@dataclass(frozen=True)
class AttrAssign:
    """Attribute assignment statement (obj.attr = expr).

    Attributes:
        obj: Variable name of the object
        attr: Attribute name
        expr: Expression to evaluate and assign
    """
    obj: str
    attr: str
    expr: Expr


@dataclass(frozen=True)
class MethodCallStmt:
    """Method call as a statement (discards return value).

    Attributes:
        obj: Variable name of the object
        method: Method name
        args: List of argument expressions
    """
    obj: str
    method: str
    args: List["Expr"]


@dataclass(frozen=True)
class Print:
    """Print statement.

    Attributes:
        expr: Expression to print
    """
    expr: Expr


@dataclass(frozen=True)
class If:
    """If/else statement.

    Attributes:
        test: Condition expression
        body: List of statements in the if branch
        orelse: List of statements in the else branch
    """
    test: Expr
    body: List["Stmt"]
    orelse: List["Stmt"]


@dataclass(frozen=True)
class While:
    """While loop statement.

    Attributes:
        test: Loop condition expression
        body: List of statements in the loop body
    """
    test: Expr
    body: List["Stmt"]


@dataclass(frozen=True)
class ForRange:
    """For loop over range statement.

    Attributes:
        var: Loop variable name
        start: Start expression (inclusive)
        stop: Stop expression (exclusive)
        step: Step expression
        body: List of statements in the loop body
        lineno: Source line number for error reporting
    """
    var: str
    start: Expr
    stop: Expr
    step: Expr
    body: List["Stmt"]
    lineno: int


@dataclass(frozen=True)
class Return:
    """Return statement.

    Attributes:
        expr: Expression to return
    """
    expr: Expr


@dataclass(frozen=True)
class Break:
    """Break statement.

    Attributes:
        lineno: Source line number for error reporting
    """
    lineno: int


@dataclass(frozen=True)
class Continue:
    """Continue statement.

    Attributes:
        lineno: Source line number for error reporting
    """
    lineno: int


@dataclass(frozen=True)
class Raise:
    """Raise an exception.

    Minimal subset for M3:
      - raise <Name>("message")
      - raise <Name>()
      - raise <Name>

    Attributes:
        exc_name: Exception class name (e.g., ValueError, ZeroDivisionError)
        message: Optional message string
        lineno: Source line number for diagnostics
    """
    exc_name: str
    message: Optional[str]
    lineno: int


@dataclass(frozen=True)
class TryExcept:
    """Try/except block.

    Minimal subset for M3:
      - try: <body> except <Name>: <handler>
      - try: <body> except: <handler>   (catch-all)

    Attributes:
        body: Statements in the try block
        exc_name: Optional exception class name to match (None = catch-all)
        handler: Statements in the except handler
        lineno: Source line number of the try statement
    """
    body: List["Stmt"]
    exc_name: Optional[str]
    handler: List["Stmt"]
    lineno: int


# Union type for all statements
Stmt = Union[
    Assign,
    AttrAssign,
    MethodCallStmt,
    Print,
    If,
    While,
    ForRange,
    TryExcept,
    Raise,
    Return,
    Break,
    Continue,
]


# ==================== Module-level Constructs ====================

@dataclass(frozen=True)
class FunctionDef:
    """Function definition.

    Attributes:
        name: Function name
        params: List of parameter names
        body: List of statements in the function body
        lineno: Source line number for error reporting
    """
    name: str
    params: List[str]
    body: List[Stmt]
    lineno: int


@dataclass(frozen=True)
class ClassDef:
    """Class definition.

    Attributes:
        name: Class name
        methods: List of method definitions
        fields: List of field names (for struct layout)
        lineno: Source line number for error reporting
    """
    name: str
    methods: List[FunctionDef]
    fields: List[str]
    lineno: int


@dataclass(frozen=True)
class ModuleIR:
    """Module intermediate representation.

    This is the top-level IR structure that contains all functions
    and the main script body.

    Attributes:
        functions: List of function definitions
        classes: List of class definitions
        main: List of statements in the main script body
    """
    functions: List[FunctionDef]
    classes: List[ClassDef]
    main: List[Stmt]
