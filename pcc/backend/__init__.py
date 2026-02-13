"""
Backend code generation module for pcc.

This module handles the conversion of IR to target code (C code).
"""

from .codegen import CodeGenerator, CSource

__all__ = [
    "CodeGenerator",
    "CSource",
]
