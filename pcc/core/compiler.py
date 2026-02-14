"""
Main compiler orchestration module for pcc.

This module provides the high-level Compiler class that coordinates
parsing, code generation, and build processes.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Union

from ..frontend.parser_v1 import Parser as ParserV1, ParseError as ParseErrorV1
from ..frontend.parser_v2 import ParserV2, ParseError as ParseErrorV2
from ..backend.codegen import CodeGenerator as CodeGeneratorHPF, CSource
from ..backend.codegen_fast import generate as generate_fast
from ..utils.toolchain import Toolchain, ToolchainDetector


@dataclass
class BuildResult:
    """Result of a build operation.

    Attributes:
        success: Whether the build succeeded
        c_source_path: Path to the generated C source file (if applicable)
        executable_path: Path to the compiled executable (if applicable)
        error_message: Error message if the build failed
    """
    success: bool
    c_source_path: Optional[Path] = None
    executable_path: Optional[Path] = None
    error_message: Optional[str] = None


class Compiler:
    """Main compiler class for pcc.

    This class orchestrates the entire compilation process from Python
    source code to executable.

    Supports two parser versions:
    - Version 1: Uses Python's ast module (default)
    - Version 2: Uses tokenize-based lexer with recursive descent parser

    Example:
        >>> compiler = Compiler(parser_version=2)
        >>> result = compiler.build(
        ...     input_py=Path("example.py"),
        ...     out_exe=Path("example.exe"),
        ...     toolchain="auto"
        ... )
    """

    def __init__(self, parser_version: int = 2, use_hpf: bool = False):
        """Initialize the compiler.

        Args:
            parser_version: Which parser to use (1 or 2). Default is 2.
            use_hpf: Whether to use HPF (Heavy Precision Float) for integers.
                     Default is False (uses fast native long long).
        """
        if parser_version == 1:
            self._parser = ParserV1()
            self._parser_version = 1
        elif parser_version == 2:
            self._parser = ParserV2()
            self._parser_version = 2
        else:
            raise ValueError(f"Invalid parser version: {parser_version}. Use 1 or 2.")

        self._use_hpf = use_hpf
        self._codegen_hpf = CodeGeneratorHPF()
        self._toolchain_detector = ToolchainDetector()

    def parse(self, source: str, filename: str = "<input>"):
        """Parse Python source code into IR.

        Args:
            source: Python source code string
            filename: Source filename for error reporting

        Returns:
            ModuleIR: The intermediate representation

        Raises:
            ParseError: If parsing fails
        """
        return self._parser.parse(source, filename)

    def generate_c(self, module_ir) -> CSource:
        """Generate C code from IR.

        Args:
            module_ir: The intermediate representation

        Returns:
            CSource: The generated C source code
        """
        if self._use_hpf:
            return self._codegen_hpf.generate(module_ir)
        else:
            return generate_fast(module_ir)

    def build(
        self,
        input_py: Path,
        out_exe: Path,
        toolchain: str = "auto",
        emit_c_only: bool = False
    ) -> BuildResult:
        """Build a Python file into an executable.

        Args:
            input_py: Path to the input Python file
            out_exe: Path for the output executable
            toolchain: Toolchain to use ("auto", "msvc", "clang-cl", "gcc")
            emit_c_only: If True, only generate C code without compiling

        Returns:
            BuildResult: The result of the build operation
        """
        # Validate input
        if not input_py.exists():
            return BuildResult(
                success=False,
                error_message=f"Input file not found: {input_py}"
            )

        if input_py.suffix.lower() != ".py":
            return BuildResult(
                success=False,
                error_message=f"Input must be a .py file: {input_py}"
            )

        # Parse Python source
        try:
            source = input_py.read_text(encoding="utf-8")
            module_ir = self._parser.parse(source, filename=str(input_py))
        except (ParseErrorV1, ParseErrorV2) as e:
            return BuildResult(
                success=False,
                error_message=f"Parse error: {e}"
            )
        except Exception as e:
            return BuildResult(
                success=False,
                error_message=f"Unexpected error during parsing: {e}"
            )

        # Generate C code
        try:
            c_source = self.generate_c(module_ir)
        except Exception as e:
            return BuildResult(
                success=False,
                error_message=f"Code generation error: {e}"
            )

        # Write C source to file
        root = self._repo_root()
        build_dir = root / "build" / f"pcc_{input_py.stem}"
        build_dir.mkdir(parents=True, exist_ok=True)

        main_c = build_dir / "main.c"
        main_c.write_text(c_source.c_source, encoding="utf-8")

        if emit_c_only:
            return BuildResult(
                success=True,
                c_source_path=main_c,
                error_message=None
            )

        # Compile to executable
        out_exe = out_exe.resolve()
        out_exe.parent.mkdir(parents=True, exist_ok=True)

        # Detect toolchain
        if toolchain == "auto":
            detected = self._toolchain_detector.detect()
            if detected is None:
                return BuildResult(
                    success=False,
                    c_source_path=main_c,
                    error_message="No supported compiler found in PATH"
                )
            toolchain = detected.value

        # Run build
        result = self._compile(main_c, out_exe, toolchain, root)
        if result != 0:
            return BuildResult(
                success=False,
                c_source_path=main_c,
                error_message=f"Compilation failed with exit code {result}"
            )

        return BuildResult(
            success=True,
            c_source_path=main_c,
            executable_path=out_exe
        )

    def _compile(
        self,
        main_c: Path,
        out_exe: Path,
        toolchain: str,
        root: Path
    ) -> int:
        """Compile C source to executable.

        Args:
            main_c: Path to the main C source file
            out_exe: Path for the output executable
            toolchain: Toolchain to use
            root: Repository root path

        Returns:
            int: Exit code from the compiler
        """
        runtime_dir = root / "runtime"
        runtime_inc = runtime_dir

        # Modular runtime source files
        runtime_sources = [
            runtime_dir / "rt_bigint.c",
            runtime_dir / "rt_string.c",
            runtime_dir / "rt_error.c",
            runtime_dir / "rt_exc.c",
            runtime_dir / "rt_math.c",
            runtime_dir / "rt_string_ex.c",
            runtime_dir / "rt_list.c",
            runtime_dir / "rt_dict.c",
        ]

        if toolchain in ("msvc", "clang-cl"):
            return self._compile_msvc_style(main_c, out_exe, toolchain, runtime_sources, runtime_inc)
        elif toolchain == "gcc":
            return self._compile_gcc(main_c, out_exe, runtime_sources, runtime_inc)
        else:
            raise ValueError(f"Unknown toolchain: {toolchain}")

    def _compile_msvc_style(
        self,
        main_c: Path,
        out_exe: Path,
        toolchain: str,
        runtime_sources: list[Path],
        runtime_inc: Path
    ) -> int:
        """Compile using MSVC-style command line (cl.exe or clang-cl)."""
        if toolchain == "msvc":
            compiler = "cl.exe"
            if not shutil.which(compiler):
                raise RuntimeError("cl.exe not found. Install Visual Studio Build Tools.")
        else:
            compiler = shutil.which("clang-cl.exe") or shutil.which("clang-cl")
            if not compiler:
                raise RuntimeError("clang-cl not found. Install LLVM.")

        cmd = [
            compiler,
            "/nologo",
            "/O2",
            "/W3",
            "/TC",
            "/I", str(runtime_inc),
            str(main_c),
        ]
        # Add modular runtime sources
        cmd.extend(str(src) for src in runtime_sources)
        # Add linker options
        cmd.extend(["/link", f"/OUT:{str(out_exe)}"])

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr)
        return result.returncode

    def _compile_gcc(
        self,
        main_c: Path,
        out_exe: Path,
        runtime_sources: list[Path],
        runtime_inc: Path
    ) -> int:
        """Compile using GCC."""
        gcc = shutil.which("gcc") or shutil.which("gcc.exe")
        if not gcc:
            raise RuntimeError("gcc not found. Install GCC or MinGW-w64.")

        cmd = [
            gcc,
            "-O2",
            "-Wall",
            "-std=c11",
            "-I", str(runtime_inc),
            str(main_c),
        ]
        # Add modular runtime sources
        cmd.extend(str(src) for src in runtime_sources)
        # Add output option
        cmd.extend(["-o", str(out_exe)])

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr)
        return result.returncode

    @staticmethod
    def _repo_root() -> Path:
        """Get the repository root directory."""
        return Path(__file__).resolve().parent.parent.parent
