# PCC - Python-to-C-to-Executable Compiler

[![Version](https://img.shields.io/badge/version-0.2.0-blue.svg)](https://github.com/yourusername/pcc)
[![Python](https://img.shields.io/badge/python-3.10+-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

PCC is a Python-to-C-to-Executable compiler that translates a subset of Python into C code and compiles it to native executables. It features arbitrary-precision integer arithmetic (BigInt), string operations, control flow, and function support.

## Table of Contents

- [Features](#features)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Usage](#usage)
- [Supported Python Subset](#supported-python-subset)
- [Examples](#examples)
- [Architecture](#architecture)
- [Development](#development)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Features

- **Arbitrary-Precision Integers**: Support for integers of any size with no overflow
- **String Operations**: String literals, variables, and concatenation
- **Control Flow**: if/else, while loops, for-range loops, break, continue
- **Functions**: Define and call functions with support for recursion
- **Type Safety**: Compile-time type checking
- **Cross-Platform**: Supports Windows (MSVC, clang-cl) and Linux/macOS (GCC)
- **Clean C Output**: Generates readable, structured C code

## Project Structure

```
pcc/
├── pcc/                      # Main Python package
│   ├── __init__.py          # Package initialization
│   ├── __main__.py          # Entry point for `python -m pcc`
│   ├── cli.py               # Command-line interface
│   ├── ir/                  # Intermediate Representation
│   │   ├── __init__.py
│   │   └── nodes.py         # IR node definitions
│   ├── core/                # Core compiler components
│   │   ├── __init__.py
│   │   ├── parser.py        # Python AST to IR parser
│   │   └── compiler.py      # Main compiler orchestration
│   ├── backend/             # Code generation
│   │   ├── __init__.py
│   │   └── codegen.py       # C code generator
│   └── utils/               # Utility modules
│       ├── __init__.py
│       ├── toolchain.py     # Toolchain detection
│       └── settings.py      # Configuration settings
├── runtime/                 # C runtime library
│   ├── runtime.h            # Main runtime header
│   ├── rt_config.h          # Configuration and platform detection
│   ├── rt_error.h/.c        # Error handling
│   ├── rt_string.h/.c       # String operations
│   └── rt_bigint.h/.c       # BigInt operations
├── tests/                   # Test suite
│   ├── unit/                # Unit tests
│   ├── integration/         # Integration tests
│   ├── e2e/                 # End-to-end tests
│   └── fixtures/            # Test fixtures
├── scripts/                 # Build scripts
│   ├── build.ps1           # PowerShell build script
│   └── run_tests.ps1       # Test runner script
├── README.md               # This file
└── .gitignore
```

## Installation

### Prerequisites

- Python 3.10 or higher
- A C compiler:
  - **Windows**: Visual Studio Build Tools (cl.exe) or LLVM (clang-cl)
  - **Linux/macOS**: GCC or Clang

### Install Python Dependencies

```bash
pip install pytest  # For running tests
```

### Install C Compilers

#### Windows - MSVC (Recommended)

```powershell
winget install -e --id Microsoft.VisualStudio.2022.BuildTools
```

After installation, use "Developer PowerShell for VS 2022" or ensure `cl.exe` is in your PATH.

#### Windows - LLVM (Alternative)

```powershell
winget install -e --id LLVM.LLVM
winget install -e --id Microsoft.WindowsSDK.11
```

#### Linux

```bash
sudo apt-get install gcc
```

#### macOS

```bash
xcode-select --install
```

## Usage

### Command Line

Build a Python file to an executable:

```bash
python -m pcc build input.py -o output.exe
```

Options:
- `-o, --output`: Output executable path (required)
- `--toolchain`: Compiler to use (`auto`, `msvc`, `clang-cl`, `gcc`)
- `--emit-c-only`: Only generate C code, skip compilation
- `-v, --verbose`: Enable verbose output

### Examples

```bash
# Basic build
python -m pcc build example.py -o example.exe

# Specify toolchain
python -m pcc build example.py -o example.exe --toolchain msvc

# Only generate C code
python -m pcc build example.py -o example.exe --emit-c-only

# Show version
python -m pcc version
```

### Python API

```python
from pcc import Compiler

compiler = Compiler()

# Build to executable
result = compiler.build(
    input_py=Path("input.py"),
    out_exe=Path("output.exe"),
    toolchain="auto"
)

if result.success:
    print(f"Built: {result.executable_path}")
else:
    print(f"Error: {result.error_message}")

# Or use individual steps
ir = compiler.parse("print(1 + 2)")
c_source = compiler.generate_c(ir)
print(c_source.c_source)
```

## Supported Python Subset

### Data Types

- **Integers**: Arbitrary precision (BigInt)
  - Operations: `+`, `-`, `*`, `//`, `%`
  - Comparisons: `==`, `!=`, `<`, `<=`, `>`, `>=`
- **Strings**: Literals, variables, concatenation (`+`)
- **Booleans**: Result of comparisons (0/1 integers)

### Statements

- `x = expr` - Variable assignment
- `print(expr)` - Print expression
- `return expr` - Return from function
- Expression statements (function calls)

### Control Flow

- `if condition:` / `else:` - Conditional execution
- `while condition:` - While loop
- `for i in range(start, stop, step):` - For-range loop
- `break` - Exit loop
- `continue` - Skip to next iteration

### Functions

```python
def function_name(param1, param2):
    # function body
    return expression
```

### Limitations

- No `//` or `%` in expressions (only in statements)
- No `int + str` or `str + int` mixing
- No string comparison
- No classes, lists, dictionaries, tuples
- No exception handling, imports, or decorators
- No keyword arguments

## Examples

### Basic Arithmetic

```python
# BigInt arithmetic
a = 100000000000000000000
b = 99999999999999999999
print(a + b)  # 199999999999999999999
```

### String Operations

```python
s = "hello"
t = "world"
print(s + " " + t)  # hello world
```

### Control Flow

```python
x = 10
if x > 5:
    print("big")
else:
    print("small")

for i in range(5):
    print(i)

n = 5
while n > 0:
    print(n)
    n = n - 1
```

### Functions and Recursion

```python
def factorial(n):
    if n <= 1:
        return 1
    else:
        return n * factorial(n - 1)

print(factorial(5))  # 120
```

## Architecture

PCC follows a traditional compiler architecture:

1. **Parsing**: Python source → AST → IR (Intermediate Representation)
2. **Code Generation**: IR → C source code
3. **Compilation**: C source → Native executable

### Intermediate Representation (IR)

The IR is a simplified AST that represents the supported Python subset:

- **Expressions**: `IntConst`, `StrConst`, `Var`, `BinOp`, `CmpOp`, `Call`
- **Statements**: `Assign`, `Print`, `If`, `While`, `ForRange`, `Return`, `Break`, `Continue`
- **Module-level**: `FunctionDef`, `ModuleIR`

### Runtime Library

The C runtime provides:

- **BigInt (`rt_int`)**: Arbitrary-precision integer arithmetic
- **String (`rt_str`)**: String operations with proper memory management
- **Error Handling**: Structured error codes and messages

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=pcc --cov-report=html

# Run specific test file
pytest tests/unit/test_parser.py

# Run with verbose output
pytest -v
```

### Project Setup for Development

```bash
# Clone the repository
git clone https://github.com/yourusername/pcc.git
cd pcc

# Install development dependencies
pip install pytest pytest-cov

# Run tests to verify setup
pytest
```

### Code Style

- Python: Follow PEP 8
- C: Follow Linux kernel style (tabs, 80-column limit)
- All code should have docstrings/comments

## Testing

The test suite includes:

- **Unit Tests** (`tests/unit/`): Test individual components
  - `test_ir.py`: IR node tests
  - `test_parser.py`: Parser tests
  - `test_codegen.py`: Code generator tests

- **Integration Tests** (`tests/integration/`): Test component interactions

- **End-to-End Tests** (`tests/e2e/`): Test full compilation pipeline

- **Test Fixtures** (`tests/fixtures/`): Sample Python files for testing

### Test Coverage

Target: 85%+ code coverage

Current coverage can be checked with:
```bash
pytest --cov=pcc --cov-report=term-missing
```

## Troubleshooting

### "cl.exe not found" (Windows)

Open "Developer PowerShell for VS 2022" or run:
```powershell
& "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
```

### "No supported compiler found"

Install a C compiler:
- Windows: Visual Studio Build Tools or LLVM
- Linux: `sudo apt-get install gcc`
- macOS: `xcode-select --install`

### Generated C code won't compile

Check that the runtime library is in the include path:
```bash
# Runtime should be at runtime/runtime.h
ls runtime/runtime.h
```

### Parse errors

Ensure your Python code uses only the supported subset. See [Supported Python Subset](#supported-python-subset).

## Contributing

Contributions are welcome! Please follow these guidelines:

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

### Coding Standards

- Write tests for new features
- Maintain 85%+ test coverage
- Update documentation for API changes
- Follow existing code style

### Reporting Issues

Please include:
- Python version
- Operating system
- Compiler version
- Minimal code to reproduce the issue
- Error messages

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Authors: @hi_tyc, @hi_zcy
- Inspired by Python's simplicity and C's performance
- BigInt implementation based on base-10^9 limb representation

## Roadmap

- [ ] Float support
- [ ] List/dict support
- [ ] Exception handling
- [ ] Module imports
- [ ] Optimization passes
- [ ] LLVM backend option
- [ ] WebAssembly target

---

**Note**: This is an MVP (Minimum Viable Product) implementation. The supported Python subset is intentionally limited for simplicity and performance.
