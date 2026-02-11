# PCC — Python to C/C++ Transpiler (MVP)

PCC (Python C Compiler) is an experimental project that transpiles a subset of Python into C/C++ code and produces native executables through a system compiler.

This project explores lightweight Python compilation strategies without relying on the full CPython runtime.

---

## Overview

PCC implements a minimal compilation pipeline:

Python Source
    ↓
Parsing / AST
    ↓
Intermediate Representation
    ↓
C Code Generation
    ↓
Native Compilation
    ↓
Executable Output

The current version is an MVP and supports a limited, statically translatable subset of Python.

---

## Features

- Transpile a subset of Python to C
- Generate standalone executables
- Simple runtime support layer
- Command-line interface
- Basic automated test support

---

## Project Structure

pcc/
├── pcc/              Core compiler implementation
├── runtime/          C runtime support layer
├── scripts/          Build and test scripts
├── tests/            Test cases
├── pyproject.toml    Packaging configuration
├── README.md
└── .gitignore

---

## Requirements

- Python >= 3.10
- A C compiler (MSVC / GCC / Clang)
- Windows (currently tested environment)

---

## Installation (Development Mode)

Clone the repository:

git clone https://github.com/<your-username>/pcc.git
cd pcc

Install in editable mode:

pip install -e .

Verify installation:

pcc --help

---

## Usage

Example:

pcc build examples/hello.py

Compilation flow:

1. Parse Python source
2. Generate C source code
3. Invoke system compiler
4. Produce native executable

---

## Running Tests

PowerShell:

./scripts/run_tests.ps1

---

## Design Goals

- Maintain simple and readable compiler structure
- Focus on experimental compilation techniques
- Keep runtime dependency minimal
- Serve as an educational compiler project

PCC is not intended to fully replace CPython.  
It is an experimental exploration of Python-to-native compilation approaches.

---

## Roadmap

- Extend supported Python syntax
- Improve static analysis and type handling
- Add optimization passes
- Investigate LLVM backend integration
- Expand cross-platform support

---

## License

MIT License

---

## Author

@hi-zcy | @hi-tyc
