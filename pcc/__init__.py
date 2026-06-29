"""pcc - Python-to-native compiler.

A from-scratch Python -> LLVM IR -> native executable compiler.
Supports two modes:

  * **Route B (pure AOT)** — compiles your Python directly to LLVM IR and
    links with a small built-in runtime. Smaller, faster binaries. Works
    for our supported subset (see SUPPORTED.md).

  * **Route A (embed libpython)** — links against the system's libpython
    and falls back to the CPython interpreter for unsupported features
    (numpy, requests, C extensions, etc.). 100% Python compatibility.

The compiler auto-detects the right route based on which modules the
program imports: local .py files are inlined, pip-installed C extensions
trigger embed mode.

Quick start:

    pip install pcc
    pcc hello.py -o hello
    ./hello
"""

__version__ = "0.3.0"
__all__ = ["__version__"]
