import argparse
from pathlib import Path

from .build_driver import build_command


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="pcc", description="pcc MVP: .py -> C -> .exe (Windows)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Build an input .py into a Windows .exe")
    b.add_argument("input", type=str, help="Input .py file")
    b.add_argument("-o", "--output", required=True, type=str, help="Output .exe path")
    b.add_argument(
        "--toolchain",
        choices=["auto", "msvc", "clang-cl"],
        default="auto",
        help="Select toolchain (default: auto)",
    )
    b.add_argument(
        "--emit-c-only",
        action="store_true",
        help="Only emit generated C (main.c) and do not compile/link",
    )

    args = parser.parse_args(argv)

    if args.cmd == "build":
        return build_command(
            input_py=Path(args.input),
            out_exe=Path(args.output),
            toolchain=args.toolchain,
            emit_c_only=args.emit_c_only,
        )

    return 2