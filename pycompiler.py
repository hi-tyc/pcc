#!/usr/bin/env python3
"""pycompiler - a from-scratch Python -> LLVM -> executable compiler.

Pipeline:
    source.py
      -> [lexer]      tokens
      -> [parser]     AST
      -> [semantic]   validated AST + inferred types
      -> [codegen]    LLVM IR (textual, .ll)
      -> [opt]        optimized LLVM assembly (.opt.ll)
      -> [clang]      link with runtime.c -> native executable

Usage:
    pycompiler.py <source.py> [-o OUTPUT] [--run] [--emit-ir] [--no-opt] [-O LEVEL]
"""

import argparse
import os
import subprocess
import sys
import tempfile

from lexer import Lexer, LexError
from parser import parse, ParseError
from semantic import analyze, SemanticError
from codegen import generate, CodeGenError


COMPILER_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_C = os.path.join(COMPILER_DIR, "runtime.c")


class CompileError(Exception):
    pass


def log(msg):
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def find_tool(names):
    for n in names:
        try:
            subprocess.run([n, "--version"], capture_output=True, check=False)
            return n
        except FileNotFoundError:
            continue
    return None


def run(cmd):
    """Run a command, returning stdout. Raise CompileError on failure."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise CompileError(
            f"command failed: {' '.join(cmd)}\n--- stderr ---\n{proc.stderr}"
        )
    return proc.stdout


def compile_source(source, source_name, out_exec, opt_level=2, emit_ir=False, no_opt=False):
    # Stage 1: lex
    log("[1/5] Lexical analysis...")
    try:
        tokens = Lexer(source).tokenize()
    except LexError as e:
        raise CompileError(str(e))
    log(f"      {len(tokens)} tokens")

    # Stage 2: parse
    log("[2/5] Syntax parsing...")
    try:
        ast = parse(tokens)
    except ParseError as e:
        raise CompileError(str(e))
    log(f"      {len(ast)} top-level statements")

    # Stage 3: semantic analysis
    log("[3/5] Semantic analysis & type inference...")
    try:
        info = analyze(ast)
    except SemanticError as e:
        raise CompileError(str(e))
    log(f"      {len(info['funcs'])} function(s), {len(info['globals'])} global(s)")

    # Stage 4: codegen
    log("[4/5] LLVM IR generation...")
    try:
        ir = generate(info)
    except CodeGenError as e:
        raise CompileError(str(e))

    # Write raw IR.
    ir_path = out_exec + ".ll"
    with open(ir_path, "w") as f:
        f.write(ir)
    log(f"      wrote {ir_path}")

    # Stage 5: optimize + link
    log("[5/5] Optimization & linking...")
    clang = find_tool(["clang"])
    opt = find_tool(["opt"])
    if clang is None:
        raise CompileError("clang not found on PATH (required for final linking)")

    link_input = ir_path
    opt_path = out_exec + ".opt.ll"

    if not no_opt and opt is not None:
        # Run LLVM optimization passes to produce optimized assembly.
        passes = f"default<O{opt_level}>"
        try:
            run([opt, f"-passes={passes}", "-S", ir_path, "-o", opt_path])
            link_input = opt_path
            log(f"      optimized IR -> {opt_path}")
        except CompileError:
            # Fallback: try legacy flag.
            try:
                run([opt, f"-O{opt_level}", "-S", ir_path, "-o", opt_path])
                link_input = opt_path
                log(f"      optimized IR (legacy) -> {opt_path}")
            except CompileError:
                log("      warning: opt failed, linking unoptimized IR")
    elif no_opt:
        log("      optimization disabled (--no-opt)")

    # Link optimized IR + runtime.c -> executable.
    if not os.path.exists(RUNTIME_C):
        raise CompileError(f"runtime library not found: {RUNTIME_C}")
    link_cmd = [clang, f"-O{opt_level}", link_input, RUNTIME_C, "-o", out_exec, "-lm"]
    run(link_cmd)
    log(f"      executable -> {out_exec}")

    # Cleanup intermediate IR unless requested.
    if not emit_ir:
        for p in (ir_path, opt_path):
            if os.path.exists(p):
                os.remove(p)
    return out_exec


def main():
    ap = argparse.ArgumentParser(
        prog="pycompiler",
        description="Compile a subset of Python to a native executable via LLVM.")
    ap.add_argument("source", help="Python source file to compile")
    ap.add_argument("-o", "--output", help="output executable path")
    ap.add_argument("-O", dest="opt_level", type=int, default=2,
                    choices=range(0, 4), help="optimization level (0-3), default 2")
    ap.add_argument("--run", action="store_true", help="run the executable after compiling")
    ap.add_argument("--emit-ir", action="store_true",
                    help="keep the generated .ll / .opt.ll files")
    ap.add_argument("--no-opt", action="store_true", help="skip LLVM optimization passes")
    args = ap.parse_args()

    if not os.path.exists(args.source):
        sys.stderr.write(f"error: source file not found: {args.source}\n")
        return 1

    with open(args.source) as f:
        source = f.read()

    out_exec = args.output
    if out_exec is None:
        base = os.path.splitext(args.source)[0]
        out_exec = base

    try:
        compile_source(source, args.source, out_exec,
                       opt_level=args.opt_level, emit_ir=args.emit_ir, no_opt=args.no_opt)
    except CompileError as e:
        sys.stderr.write(f"\nCompilation failed:\n{e}\n")
        return 1

    log(f"\nBuild succeeded: {out_exec}")
    if args.run:
        log(f"--- running {out_exec} ---")
        proc = subprocess.run([out_exec])
        return proc.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
