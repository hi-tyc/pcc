"""
pcc - Python-to-C-to-Executable Compiler

A compiler that translates a subset of Python to C code and then to native executables.
Supports BigInt arithmetic, strings, control flow, and functions.

Example:
    >>> from pcc import Compiler
    >>> compiler = Compiler()
    >>> result = compiler.build(Path("example.py"), Path("example.exe"))
    >>> if result.success:
    ...     print("Build successful!")

Version: 0.2.0
"""

__version__ = "0.2.0"
__author__ = "pcc Team"

from .core import Compiler, Parser, ParseError

__all__ = [
    "__version__",
    "__author__",
    "Compiler",
    "Parser",
    "ParseError",
]
