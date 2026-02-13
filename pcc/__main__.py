"""
Entry point for running pcc as a module.

Usage:
    python -m pcc build input.py -o output.exe
"""

import sys
from .cli import main

if __name__ == "__main__":
    sys.exit(main())
