from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .frontend import parse_source_to_ir
from .codegen_c import emit_c


def _repo_root_from_here() -> Path:
    # pcc/ is at <root>/pcc/
    return Path(__file__).resolve().parent.parent


def _which(cmd: str) -> str | None:
    return shutil.which(cmd)


def build_command(input_py: Path, out_exe: Path, toolchain: str, emit_c_only: bool) -> int:
    if not input_py.exists():
        print(f"[pcc] error: input not found: {input_py}")
        return 1
    if input_py.suffix.lower() != ".py":
        print(f"[pcc] error: input must be a .py file: {input_py}")
        return 1

    src = input_py.read_text(encoding="utf-8")
    mod_ir = parse_source_to_ir(src, filename=str(input_py))
    c = emit_c(mod_ir).c_source

    root = _repo_root_from_here()
    build_dir = root / "build" / f"pcc_{input_py.stem}"
    build_dir.mkdir(parents=True, exist_ok=True)

    main_c = build_dir / "main.c"
    main_c.write_text(c, encoding="utf-8")

    print(f"[pcc] emitted: {main_c}")

    if emit_c_only:
        print("[pcc] --emit-c-only specified; skipping compilation.")
        return 0

    # Ensure output directory exists
    out_exe = out_exe.resolve()
    out_exe.parent.mkdir(parents=True, exist_ok=True)

    # Choose toolchain
    if toolchain == "auto":
        if _which("cl.exe"):
            toolchain = "msvc"
        elif _which("clang-cl.exe") or _which("clang-cl"):
            toolchain = "clang-cl"
        else:
            print("[pcc] error: neither cl.exe nor clang-cl found in PATH.")
            print("[pcc]        open 'Developer PowerShell for VS' or install LLVM.")
            return 1

    script = root / "scripts" / "build.ps1"
    if not script.exists():
        print(f"[pcc] error: build script not found: {script}")
        return 1

    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-MainC",
        str(main_c),
        "-OutExe",
        str(out_exe),
        "-Toolchain",
        toolchain,
    ]

    print(f"[pcc] building with {toolchain} -> {out_exe}")
    try:
        r = subprocess.run(cmd, cwd=str(root), check=False)
    except FileNotFoundError as e:
        print(f"[pcc] error: failed to run PowerShell: {e}")
        return 1

    return r.returncode