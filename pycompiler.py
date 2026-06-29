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

import ast_nodes as A


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


# Standard library modules we have built-in support for
KNOWN_STDLIB = {
    "random", "time", "re", "threading", "queue", "collections",
    "concurrent", "concurrent.futures", "math", "os", "sys", "json",
    "itertools", "functools", "string", "datetime", "struct",
    "io", "pathlib", "copy", "textwrap", "bisect", "heapq",
    "operator", "enum", "abc", "contextlib", "csv", "base64",
    "pprint", "unicodedata", "codecs", "hashlib", "hmac",
    "secrets", "decimal", "fractions", "statistics", "array",
    "weakref", "dataclasses", "typing", "argparse", "configparser",
    "shutil", "tempfile", "glob", "fnmatch", "subprocess", "signal",
    "mmap", "ctypes", "platform", "errno", "stat", "socket",
    "ssl", "http", "urllib", "email", "xml", "html",
    "logging", "warnings", "traceback", "inspect", "types",
    "dis", "cProfile", "profile", "pstats", "timeit", "trace",
}

def find_module(module_name, source_dir):
    """Find a .py file for a user module."""
    parts = module_name.replace(".", "/")
    for base in [source_dir, COMPILER_DIR]:
        candidates = [
            os.path.join(base, parts + ".py"),
            os.path.join(base, parts, "__init__.py"),
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
    return None

def _rewrite_module_attr(node, user_modules, depth=0):
    """Recursively rewrite Module.x -> x and Module.x(args) -> x(args).

    For Attribute(Name('mod'), 'attr') where 'mod' is a user module,
    returns Name('attr').
    For MethodCall(Name('mod'), 'method', args) where 'mod' is a user
    module, returns Call(Name('method'), args).
    """
    if isinstance(node, A.Attribute):
        if isinstance(node.obj, A.Name) and node.obj.name in user_modules:
            return A.Name(node.attr, node.line)
        # Recurse into obj to handle nested cases
        node.obj = _rewrite_module_attr(node.obj, user_modules, depth + 1)
        return node
    if isinstance(node, A.MethodCall):
        if isinstance(node.obj, A.Name) and node.obj.name in user_modules:
            # Convert MethodCall(module, method, args) -> Call(Name(method), args)
            return A.Call(
                A.Name(node.method, node.line),
                node.args,
                node.line,
                kwargs=node.kwargs,
            )
        # Recurse into obj
        node.obj = _rewrite_module_attr(node.obj, user_modules, depth + 1)
        return node
    if isinstance(node, A.Subscript):
        node.obj = _rewrite_module_attr(node.obj, user_modules, depth + 1)
        return node
    if isinstance(node, A.Call):
        node.func = _rewrite_module_attr(node.func, user_modules, depth + 1)
        node.args = [_rewrite_module_attr(a, user_modules, depth + 1) for a in node.args]
        node.kwargs = {k: _rewrite_module_attr(v, user_modules, depth + 1) for k, v in node.kwargs.items()}
        return node
    if isinstance(node, (A.BinOp,)):
        node.left = _rewrite_module_attr(node.left, user_modules, depth + 1)
        node.right = _rewrite_module_attr(node.right, user_modules, depth + 1)
        return node
    if isinstance(node, A.UnaryOp):
        node.operand = _rewrite_module_attr(node.operand, user_modules, depth + 1)
        return node
    if isinstance(node, A.BoolOp):
        node.left = _rewrite_module_attr(node.left, user_modules, depth + 1)
        node.right = _rewrite_module_attr(node.right, user_modules, depth + 1)
        return node
    if isinstance(node, A.Compare):
        node.operands = [_rewrite_module_attr(o, user_modules, depth + 1) for o in node.operands]
        return node
    if isinstance(node, A.IfExp):
        node.cond = _rewrite_module_attr(node.cond, user_modules, depth + 1)
        node.then = _rewrite_module_attr(node.then, user_modules, depth + 1)
        node.else_ = _rewrite_module_attr(node.else_, user_modules, depth + 1)
        return node
    if isinstance(node, A.ListLit):
        node.elements = [_rewrite_module_attr(e, user_modules, depth + 1) for e in node.elements]
        return node
    if isinstance(node, A.TupleLit):
        node.elements = [_rewrite_module_attr(e, user_modules, depth + 1) for e in node.elements]
        return node
    if isinstance(node, A.DictLit):
        node.pairs = [
            (_rewrite_module_attr(k, user_modules, depth + 1),
             _rewrite_module_attr(v, user_modules, depth + 1))
            for k, v in node.pairs
        ]
        return node
    if isinstance(node, (A.ListComp, A.DictComp)):
        node.iterable = _rewrite_module_attr(node.iterable, user_modules, depth + 1)
        if isinstance(node, A.ListComp):
            node.element = _rewrite_module_attr(node.element, user_modules, depth + 1)
        else:
            node.key_expr = _rewrite_module_attr(node.key_expr, user_modules, depth + 1)
            node.val_expr = _rewrite_module_attr(node.val_expr, user_modules, depth + 1)
        node.conditions = [_rewrite_module_attr(c, user_modules, depth + 1) for c in node.conditions]
        return node
    if isinstance(node, A.FString):
        new_parts = []
        for part, info in node.parts:
            if info is False:
                new_parts.append((part, False))
            else:
                # info is True (no spec) or a spec string; preserve it.
                new_part = _rewrite_module_attr(part, user_modules, depth + 1)
                new_parts.append((new_part, info))
        node.parts = new_parts
        return node
    if isinstance(node, A.Slice):
        node.obj = _rewrite_module_attr(node.obj, user_modules, depth + 1)
        if node.start is not None:
            node.start = _rewrite_module_attr(node.start, user_modules, depth + 1)
        if node.stop is not None:
            node.stop = _rewrite_module_attr(node.stop, user_modules, depth + 1)
        if node.step is not None:
            node.step = _rewrite_module_attr(node.step, user_modules, depth + 1)
        return node
    if isinstance(node, A.Starred):
        node.value = _rewrite_module_attr(node.value, user_modules, depth + 1)
        return node
    if isinstance(node, A.IsOp):
        node.left = _rewrite_module_attr(node.left, user_modules, depth + 1)
        node.right = _rewrite_module_attr(node.right, user_modules, depth + 1)
        return node
    return node


def _rewrite_stmt(s, user_modules):
    """Recursively rewrite module attribute references in a statement."""
    if isinstance(s, A.Assign):
        s.value = _rewrite_module_attr(s.value, user_modules)
        # If target is Attribute(Name(mod), attr), rewrite to Name(attr)
        if isinstance(s.target, A.Attribute):
            if isinstance(s.target.obj, A.Name) and s.target.obj.name in user_modules:
                s.target = A.Name(s.target.attr, s.target.line)
        return s
    if isinstance(s, A.AugAssign):
        s.value = _rewrite_module_attr(s.value, user_modules)
        if isinstance(s.target, A.Attribute):
            if isinstance(s.target.obj, A.Name) and s.target.obj.name in user_modules:
                s.target = A.Name(s.target.attr, s.target.line)
        return s
    if isinstance(s, A.ExprStmt):
        s.expr = _rewrite_module_attr(s.expr, user_modules)
        return s
    if isinstance(s, A.If):
        s.branches = [
            (_rewrite_module_attr(c, user_modules),
             [_rewrite_stmt(x, user_modules) for x in b])
            for c, b in s.branches
        ]
        s.orelse = [_rewrite_stmt(x, user_modules) for x in s.orelse]
        return s
    if isinstance(s, A.While):
        s.cond = _rewrite_module_attr(s.cond, user_modules)
        s.body = [_rewrite_stmt(x, user_modules) for x in s.body]
        s.orelse = [_rewrite_stmt(x, user_modules) for x in s.orelse]
        return s
    if isinstance(s, A.For):
        s.iterable = _rewrite_module_attr(s.iterable, user_modules)
        s.body = [_rewrite_stmt(x, user_modules) for x in s.body]
        s.orelse = [_rewrite_stmt(x, user_modules) for x in s.orelse]
        return s
    if isinstance(s, A.Return):
        if s.value is not None:
            s.value = _rewrite_module_attr(s.value, user_modules)
        return s
    if isinstance(s, A.With):
        new_items = []
        for ctx, var in s.items:
            new_items.append((_rewrite_module_attr(ctx, user_modules), var))
        s.items = new_items
        s.body = [_rewrite_stmt(x, user_modules) for x in s.body]
        return s
    if isinstance(s, A.Try):
        s.body = [_rewrite_stmt(x, user_modules) for x in s.body]
        new_handlers = []
        for exc_type, name, hb in s.handlers:
            if exc_type is not None:
                exc_type = _rewrite_module_attr(exc_type, user_modules)
            new_handlers.append((exc_type, name, [_rewrite_stmt(x, user_modules) for x in hb]))
        s.handlers = new_handlers
        return s
    if isinstance(s, A.Raise):
        if s.exc is not None:
            s.exc = _rewrite_module_attr(s.exc, user_modules)
        return s
    if isinstance(s, A.FuncDef):
        s.body = [_rewrite_stmt(x, user_modules) for x in s.body]
        return s
    if isinstance(s, A.ClassDef):
        s.methods = [_rewrite_stmt(m, user_modules) for m in s.methods]
        return s
    return s


def resolve_imports(source, source_dir, visited=None):
    """Parse source, find user module imports, inline their definitions.

    For user modules (not in KNOWN_STDLIB), we:
    1. Find and parse the .py file
    2. Recursively resolve its imports
    3. Collect all top-level FuncDef, ClassDef, and global assignments
    4. Rewrite `modname.x` references in the original source to just `x`
       (so that the inlined definitions are visible)
    5. Return the merged AST with user module imports removed

    For stdlib modules, keep imports as-is (handled by semantic analyzer).
    """
    if visited is None:
        visited = set()

    tokens = Lexer(source).tokenize()
    ast = parse(tokens)

    extra_defs = []  # Definitions from user modules
    new_stmts = []   # Statements to keep

    # Track names brought into scope by from-imports (so we don't need to
    # rewrite Attribute refs for these).
    imported_names = set()  # names that are now in scope due to from-imports

    def rewrite_attr_refs(stmts):
        """Walk a statement list and rewrite Module.x -> x for user modules."""
        user_modules = {n for n, k in module_kinds.items() if k == "user"}
        for s in stmts:
            _rewrite_stmt(s, user_modules)

    # First pass: collect user module import names
    module_kinds = {}
    for stmt in ast:
        if isinstance(stmt, A.Import):
            top = stmt.module.split(".")[0]
            if top not in KNOWN_STDLIB:
                module_kinds[top] = "user"
            else:
                module_kinds[top] = "stdlib"
        elif isinstance(stmt, A.ImportFrom):
            top = stmt.module.split(".")[0]
            if top not in KNOWN_STDLIB:
                module_kinds[top] = "user"
            else:
                module_kinds[top] = "stdlib"

    for stmt in ast:
        if isinstance(stmt, A.Import):
            top = stmt.module.split(".")[0]
            if top in KNOWN_STDLIB:
                new_stmts.append(stmt)
            else:
                # User module - try to resolve
                module_path = find_module(stmt.module, source_dir)
                if module_path and module_path not in visited:
                    visited.add(module_path)
                    try:
                        with open(module_path) as f:
                            mod_source = f.read()
                        mod_ast = resolve_imports(mod_source, os.path.dirname(module_path), visited)
                        for s in mod_ast:
                            if isinstance(s, (A.FuncDef, A.ClassDef)):
                                extra_defs.append(s)
                            elif isinstance(s, (A.Import, A.ImportFrom)):
                                # Stdlib imports from the module - keep them
                                top2 = s.module.split(".")[0] if isinstance(s, A.Import) else s.module.split(".")[0]
                                if top2 in KNOWN_STDLIB:
                                    new_stmts.append(s)
                            elif isinstance(s, (A.Assign, A.AugAssign)):
                                # Global variables from the module
                                extra_defs.append(s)
                            else:
                                # Other top-level statements (function calls, etc.)
                                extra_defs.append(s)
                    except Exception:
                        # If we can't parse the module, keep the import
                        new_stmts.append(stmt)
                else:
                    new_stmts.append(stmt)
        elif isinstance(stmt, A.ImportFrom):
            top = stmt.module.split(".")[0]
            if top in KNOWN_STDLIB:
                new_stmts.append(stmt)
            else:
                module_path = find_module(stmt.module, source_dir)
                if module_path and module_path not in visited:
                    visited.add(module_path)
                    try:
                        with open(module_path) as f:
                            mod_source = f.read()
                        mod_ast = resolve_imports(mod_source, os.path.dirname(module_path), visited)
                        # Add all definitions from the module
                        for s in mod_ast:
                            if isinstance(s, (A.FuncDef, A.ClassDef)):
                                # For "from foo import bar as baz", rename
                                if stmt.names and len(stmt.names) == 1 and " as " in stmt.names[0]:
                                    # Handle "from foo import bar as baz"
                                    parts = stmt.names[0].split(" as ")
                                    old_name = parts[0].strip()
                                    new_name = parts[1].strip()
                                    if s.name == old_name:
                                        s.name = new_name
                                extra_defs.append(s)
                                # Track the imported name (for from X import y)
                                if stmt.names:
                                    for nm in stmt.names:
                                        if " as " in nm:
                                            imported_names.add(nm.split(" as ")[1].strip())
                                        else:
                                            imported_names.add(nm.strip())
                            elif isinstance(s, (A.Import, A.ImportFrom)):
                                top2 = s.module.split(".")[0]
                                if top2 in KNOWN_STDLIB:
                                    new_stmts.append(s)
                            elif isinstance(s, (A.Assign, A.AugAssign)):
                                extra_defs.append(s)
                            else:
                                extra_defs.append(s)
                        # ImportFrom is removed (names are now in scope)
                    except Exception:
                        new_stmts.append(stmt)
                else:
                    new_stmts.append(stmt)
        else:
            new_stmts.append(stmt)

    # Rewrite module.x -> x for user modules in the kept statements.
    rewrite_attr_refs(new_stmts)

    return extra_defs + new_stmts


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

    # Stage 2.5: resolve user module imports
    source_dir = os.path.dirname(os.path.abspath(source_name))
    log("[2.5/5] Resolving imports...")
    try:
        ast = resolve_imports(source, source_dir)
    except (LexError, ParseError) as e:
        raise CompileError(str(e))
    log(f"      {len(ast)} statements after import resolution")

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
