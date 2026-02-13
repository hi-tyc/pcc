"""
Toolchain detection and management for pcc.

This module provides utilities for detecting and working with different
C compilers (MSVC, clang-cl, GCC).
"""

import shutil
from enum import Enum
from typing import Optional


class Toolchain(Enum):
    """Supported C compiler toolchains."""
    MSVC = "msvc"
    CLANG_CL = "clang-cl"
    GCC = "gcc"


class ToolchainDetector:
    """Detects available C compilers on the system.

    This class provides methods to detect which C compilers are available
    on the current system and select the most appropriate one.

    Example:
        >>> detector = ToolchainDetector()
        >>> toolchain = detector.detect()
        >>> if toolchain:
        ...     print(f"Found: {toolchain.value}")
    """

    # Priority order for toolchain selection
    DEFAULT_PRIORITY = [Toolchain.GCC, Toolchain.MSVC, Toolchain.CLANG_CL]

    def __init__(self, priority: Optional[list] = None):
        """Initialize the detector.

        Args:
            priority: Optional custom priority order for toolchain selection
        """
        self.priority = priority or self.DEFAULT_PRIORITY

    def detect(self) -> Optional[Toolchain]:
        """Detect the best available toolchain.

        Returns:
            Toolchain: The first available toolchain in priority order,
                      or None if no toolchain is found
        """
        for tc in self.priority:
            if self.is_available(tc):
                return tc
        return None

    def is_available(self, toolchain: Toolchain) -> bool:
        """Check if a specific toolchain is available.

        Args:
            toolchain: The toolchain to check

        Returns:
            bool: True if the toolchain is available
        """
        if toolchain == Toolchain.MSVC:
            return shutil.which("cl.exe") is not None
        elif toolchain == Toolchain.CLANG_CL:
            return (shutil.which("clang-cl.exe") is not None or
                    shutil.which("clang-cl") is not None)
        elif toolchain == Toolchain.GCC:
            return (shutil.which("gcc") is not None or
                    shutil.which("gcc.exe") is not None)
        return False

    def get_compiler_path(self, toolchain: Toolchain) -> Optional[str]:
        """Get the path to the compiler executable.

        Args:
            toolchain: The toolchain to look up

        Returns:
            str: Path to the compiler, or None if not found
        """
        if toolchain == Toolchain.MSVC:
            return shutil.which("cl.exe")
        elif toolchain == Toolchain.CLANG_CL:
            return shutil.which("clang-cl.exe") or shutil.which("clang-cl")
        elif toolchain == Toolchain.GCC:
            return shutil.which("gcc") or shutil.which("gcc.exe")
        return None

    def list_available(self) -> list:
        """List all available toolchains.

        Returns:
            list: List of available Toolchain enums
        """
        return [tc for tc in Toolchain if self.is_available(tc)]
