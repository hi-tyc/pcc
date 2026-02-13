"""
Configuration settings for pcc.

This module contains default configuration values and settings used
throughout the compiler.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class Settings:
    """Compiler settings and configuration.

    Attributes:
        default_toolchain: Default toolchain to use
        valid_toolchains: List of valid toolchain choices
        optimization_level: Optimization level (0-3)
        enable_warnings: Whether to enable compiler warnings
        c_standard: C language standard version
    """
    default_toolchain: str = "auto"
    valid_toolchains: List[str] = None
    optimization_level: int = 2
    enable_warnings: bool = True
    c_standard: str = "c11"

    def __post_init__(self):
        if self.valid_toolchains is None:
            self.valid_toolchains = ["auto", "gcc", "msvc", "clang-cl"]

    @property
    def toolchain_choices(self) -> List[str]:
        """Get the list of valid toolchain choices."""
        return self.valid_toolchains


# Global default settings instance
DEFAULT_SETTINGS = Settings()
