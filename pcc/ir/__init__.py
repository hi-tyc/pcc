"""
Intermediate Representation (IR) module for pcc.

This module defines the IR data structures used throughout the compiler.
The IR is a simplified AST that represents the Python subset supported by pcc.
"""

from .nodes import (
    # Expressions
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
    Expr,
    # Statements
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
    Stmt,
    # Module-level
    FunctionDef,
    ClassDef,
    ModuleIR,
)

__all__ = [
    # Expressions
    "IntConst",
    "StrConst",
    "ListConst",
    "DictConst",
    "Subscript",
    "Var",
    "BinOp",
    "CmpOp",
    "Call",
    "AttributeAccess",
    "MethodCall",
    "ConstructorCall",
    "BuiltinCall",
    "Expr",
    # Statements
    "Assign",
    "AttrAssign",
    "MethodCallStmt",
    "Print",
    "If",
    "While",
    "ForRange",
    "TryExcept",
    "Raise",
    "Return",
    "Break",
    "Continue",
    "Stmt",
    # Module-level
    "FunctionDef",
    "ClassDef",
    "ModuleIR",
]
