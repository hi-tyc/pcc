#!/usr/bin/env python3
"""
Build script for precompiling the PCC runtime library.

This script compiles the runtime C sources into a static library
that can be linked with compiled programs for faster build times.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def get_compiler():
    """Detect the available C compiler."""
    compilers = ['gcc', 'clang', 'cc']
    for compiler in compilers:
        if shutil.which(compiler):
            return compiler
    return None


def get_compiler_flags(optimize: bool = True) -> list:
    """Get compiler flags based on platform and optimization level."""
    flags = ['-Wall', '-Wextra', '-std=c11']
    
    if optimize:
        flags.extend([
            '-O3',
            '-fPIC',
            '-fomit-frame-pointer',
        ])
        if platform.system() != 'Windows':
            flags.append('-march=native')
    
    return flags


def build_static_library(runtime_dir: Path, output_dir: Path, optimize: bool = True) -> bool:
    """Build the runtime library as a static library.
    
    Args:
        runtime_dir: Path to the runtime source directory
        output_dir: Path to output directory for the library
        optimize: Whether to use optimization flags
        
    Returns:
        True if successful, False otherwise
    """
    compiler = get_compiler()
    if not compiler:
        print("Error: No C compiler found. Please install gcc or clang.")
        return False
    
    sources = [
        'rt_bigint.c',
        'rt_string.c',
        'rt_error.c',
        'rt_math.c',
        'rt_string_ex.c',
    ]
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    flags = get_compiler_flags(optimize)
    obj_files = []
    
    print(f"Using compiler: {compiler}")
    print(f"Compiler flags: {' '.join(flags)}")
    print()
    
    for src in sources:
        src_path = runtime_dir / src
        if not src_path.exists():
            print(f"Warning: Source file not found: {src_path}")
            continue
        
        obj_path = output_dir / f"{src}.o"
        obj_files.append(obj_path)
        
        cmd = [compiler] + flags + ['-c', '-I', str(runtime_dir), '-o', str(obj_path), str(src_path)]
        print(f"Compiling: {src}")
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"Error compiling {src}:")
            print(e.stderr.decode())
            return False
    
    lib_name = 'libpcc_runtime.a'
    lib_path = output_dir / lib_name
    
    print(f"\nCreating static library: {lib_path}")
    cmd = ['ar', 'rcs', str(lib_path)] + [str(f) for f in obj_files]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"Error creating library:")
        print(e.stderr.decode())
        return False
    
    for obj in obj_files:
        obj.unlink()
    
    print(f"\nStatic library created successfully: {lib_path}")
    print(f"Library size: {lib_path.stat().st_size / 1024:.1f} KB")
    
    return True


def build_shared_library(runtime_dir: Path, output_dir: Path, optimize: bool = True) -> bool:
    """Build the runtime library as a shared library.
    
    Args:
        runtime_dir: Path to the runtime source directory
        output_dir: Path to output directory for the library
        optimize: Whether to use optimization flags
        
    Returns:
        True if successful, False otherwise
    """
    compiler = get_compiler()
    if not compiler:
        print("Error: No C compiler found. Please install gcc or clang.")
        return False
    
    sources = [
        'rt_bigint.c',
        'rt_string.c',
        'rt_error.c',
        'rt_math.c',
        'rt_string_ex.c',
    ]
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    flags = get_compiler_flags(optimize)
    flags.append('-shared')
    
    system = platform.system()
    if system == 'Darwin':
        lib_name = 'libpcc_runtime.dylib'
    elif system == 'Windows':
        lib_name = 'pcc_runtime.dll'
    else:
        lib_name = 'libpcc_runtime.so'
    
    lib_path = output_dir / lib_name
    
    source_paths = [str(runtime_dir / src) for src in sources if (runtime_dir / src).exists()]
    
    cmd = [compiler] + flags + ['-I', str(runtime_dir), '-o', str(lib_path)] + source_paths
    
    print(f"Building shared library: {lib_path}")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"Error creating shared library:")
        print(e.stderr.decode())
        return False
    
    print(f"\nShared library created successfully: {lib_path}")
    print(f"Library size: {lib_path.stat().st_size / 1024:.1f} KB")
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Build the PCC runtime library',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python build_runtime.py                    # Build static library
  python build_runtime.py --shared           # Build shared library
  python build_runtime.py --output ./lib     # Specify output directory
  python build_runtime.py --no-optimize      # Build without optimization
'''
    )
    
    parser.add_argument(
        '--output', '-o',
        type=Path,
        default=None,
        help='Output directory for the library (default: runtime/lib)'
    )
    
    parser.add_argument(
        '--shared',
        action='store_true',
        help='Build as shared library instead of static library'
    )
    
    parser.add_argument(
        '--no-optimize',
        action='store_true',
        help='Build without optimization flags'
    )
    
    args = parser.parse_args()
    
    script_dir = Path(__file__).parent
    runtime_dir = script_dir
    
    if args.output:
        output_dir = args.output
    else:
        output_dir = runtime_dir / 'lib'
    
    optimize = not args.no_optimize
    
    print("=" * 60)
    print("PCC Runtime Library Builder")
    print("=" * 60)
    print(f"Runtime source: {runtime_dir}")
    print(f"Output directory: {output_dir}")
    print(f"Optimization: {'enabled' if optimize else 'disabled'}")
    print(f"Library type: {'shared' if args.shared else 'static'}")
    print("=" * 60)
    print()
    
    if args.shared:
        success = build_shared_library(runtime_dir, output_dir, optimize)
    else:
        success = build_static_library(runtime_dir, output_dir, optimize)
    
    if success:
        print("\nBuild completed successfully!")
        return 0
    else:
        print("\nBuild failed!")
        return 1


if __name__ == '__main__':
    sys.exit(main())
