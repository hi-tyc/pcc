"""
Builtin function utilities for pcc.

This module provides shared validation logic for builtin functions
used by both parser versions.
"""

from typing import Dict, Union, Tuple, Optional, List


BUILTIN_ARITY: Dict[str, Union[int, Tuple[int, Optional[int]]]] = {
    'len': 1,
    'abs': 1,
    'str': 1,
    'int': 1,
    'pow': (2, 3),
    'min': (1, None),
    'max': (1, None),
}

BUILTINS: set = {'len', 'abs', 'min', 'max', 'pow', 'str', 'int'}


def validate_builtin_args(
    name: str,
    arg_count: int,
    lineno: Optional[int] = None,
    col_offset: Optional[int] = None
) -> None:
    """Validate argument count for a builtin function.
    
    Args:
        name: Name of the builtin function
        arg_count: Number of arguments provided
        lineno: Line number for error reporting (optional)
        col_offset: Column offset for error reporting (optional)
    
    Raises:
        ValueError: If argument count is invalid
    """
    from ..frontend.parser_v1 import ParseError
    
    arity = BUILTIN_ARITY.get(name)
    if arity is None:
        return
    
    if isinstance(arity, int):
        if arg_count != arity:
            msg = f"builtin '{name}' expects {arity} argument(s), got {arg_count}"
            if lineno is not None:
                msg = f"Line {lineno}: {msg}"
            raise ValueError(msg)
    elif isinstance(arity, tuple):
        min_args, max_args = arity
        if arg_count < min_args:
            msg = f"builtin '{name}' expects at least {min_args} argument(s), got {arg_count}"
            if lineno is not None:
                msg = f"Line {lineno}: {msg}"
            raise ValueError(msg)
        if max_args is not None and arg_count > max_args:
            msg = f"builtin '{name}' expects at most {max_args} argument(s), got {arg_count}"
            if lineno is not None:
                msg = f"Line {lineno}: {msg}"
            raise ValueError(msg)


def is_builtin(name: str) -> bool:
    """Check if a name is a builtin function.
    
    Args:
        name: Function name to check
    
    Returns:
        True if the name is a builtin function
    """
    return name in BUILTINS


def get_builtin_arity(name: str) -> Optional[Union[int, Tuple[int, Optional[int]]]]:
    """Get the arity specification for a builtin function.
    
    Args:
        name: Name of the builtin function
    
    Returns:
        Arity specification (int for exact, tuple for range, None if not builtin)
    """
    return BUILTIN_ARITY.get(name)
