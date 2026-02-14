"""
Command-line interface for pcc.

Provides the main entry point for the pcc compiler with subcommands
for building Python files to executables.
"""

import argparse
import sys
from pathlib import Path

from .core import Compiler


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI.

    Returns:
        argparse.ArgumentParser: The configured argument parser
    """
    parser = argparse.ArgumentParser(
        prog="pcc",
        description="pcc: Python-to-C-to-Executable Compiler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m pcc build input.py -o output.exe
  python -m pcc build input.py -o output.exe --toolchain msvc
  python -m pcc build input.py -o output --emit-c-only
        """
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Build command
    build_parser = subparsers.add_parser(
        "build",
        help="Build a Python file into an executable"
    )
    build_parser.add_argument(
        "input",
        type=str,
        help="Input Python file to compile"
    )
    build_parser.add_argument(
        "-o", "--output",
        required=True,
        type=str,
        help="Output executable path"
    )
    build_parser.add_argument(
        "--toolchain",
        choices=["auto", "msvc", "clang-cl", "gcc"],
        default="auto",
        help="Compiler toolchain to use (default: auto)"
    )
    build_parser.add_argument(
        "--emit-c-only",
        action="store_true",
        help="Only generate C code, skip compilation"
    )
    build_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    build_parser.add_argument(
        "--parser-version",
        type=int,
        choices=[1, 2],
        default=2,
        help="Parser version to use: 1=AST-based, 2=tokenize-based (default)"
    )
    build_parser.add_argument(
        "--use-hpf",
        action="store_true",
        help="Use High Precision Float (BigInt) support for arbitrary precision arithmetic"
    )

    # Version command
    version_parser = subparsers.add_parser(
        "version",
        help="Show version information"
    )

    return parser


def handle_build(args: argparse.Namespace) -> int:
    """Handle the build command.

    Args:
        args: Parsed command-line arguments

    Returns:
        int: Exit code (0 for success, non-zero for failure)
    """
    input_path = Path(args.input)
    output_path = Path(args.output)

    compiler = Compiler(parser_version=args.parser_version, use_hpf=args.use_hpf)

    if args.verbose:
        print(f"[pcc] Building: {input_path}")
        print(f"[pcc] Output: {output_path}")
        print(f"[pcc] Toolchain: {args.toolchain}")
        print(f"[pcc] Parser version: {args.parser_version}")
        print(f"[pcc] Use HPF: {args.use_hpf}")

    result = compiler.build(
        input_py=input_path,
        out_exe=output_path,
        toolchain=args.toolchain,
        emit_c_only=args.emit_c_only
    )

    if result.success:
        if args.emit_c_only:
            print(f"[pcc] Generated C code: {result.c_source_path}")
        else:
            print(f"[pcc] Build successful: {result.executable_path}")
        return 0
    else:
        print(f"[pcc] Error: {result.error_message}", file=sys.stderr)
        if result.c_source_path:
            print(f"[pcc] C source was generated at: {result.c_source_path}")
        return 1


def handle_version(args: argparse.Namespace) -> int:
    """Handle the version command.

    Args:
        args: Parsed command-line arguments

    Returns:
        int: Exit code (always 0 for version)
    """
    from . import __version__, __author__
    print(f"pcc version {__version__}")
    print(f"Author: {__author__}")
    return 0


def main(argv: list = None) -> int:
    """Main entry point for the CLI.

    Args:
        argv: Optional command-line arguments (defaults to sys.argv)

    Returns:
        int: Exit code
    """
    parser = create_parser()
    args = parser.parse_args(argv)

    if args.command == "build":
        return handle_build(args)
    elif args.command == "version":
        return handle_version(args)
    else:
        parser.print_help()
        return 2


if __name__ == "__main__":
    sys.exit(main())
