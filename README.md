# pcc — Python-to-Native Compiler

[![Version](https://img.shields.io/badge/version-0.3.0-blue.svg)](https://github.com/hi-tyc/pcc)
[![Python](https://img.shields.io/badge/python-3.8+-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

`pcc` (Python Compiler Collection) is a from-scratch Python → LLVM IR → native
executable compiler. It translates Python source code into optimized LLVM IR,
runs the standard LLVM optimization pipeline, and links it with a small
built-in runtime library (and `libpython` for hybrid mode) to produce a
**standalone native executable**.

It implements the **A+B hybrid strategy** for maximum space-time efficiency
and 100% Python compatibility:

- **Route B (pure AOT)** — compiles your Python directly to LLVM IR and
  links with a small built-in runtime. Produces the smallest, fastest
  binaries. Works for our supported subset.

- **Route A (embed libpython)** — links against the system's `libpython`
  and falls back to the CPython interpreter for unsupported features
  (`numpy`, `requests`, C extensions, anything pip-installed, …). Gives
  **100% Python compatibility**.

The compiler **auto-detects** the right route per program: known-stdlib-only
code goes through native mode; pip-installed C extensions and other unknown
modules trigger embed mode automatically. You can also force a route with
`--native` or `--embed`.

## Quick Start

### Install from PyPI (or local checkout)

```bash
# from a local clone
pip install .

# or directly from the source dir
PYTHONPATH=. python -m pcc ...
```

### Compile your first program

Create `hello.py`:

```python
import json
data = {"hello": "world", "n": 42}
print(json.dumps(data))
```

Then compile and run it:

```bash
$ pcc hello.py -o hello
[1/5] Lexical analysis...
[2/5] Syntax parsing...
[2.5/5] Resolving imports...
[3/5] Semantic analysis & type inference...
[4/5] LLVM IR generation...
[5/5] Optimization & linking...
Build succeeded: hello

$ ./hello
{"hello": "world", "n": 42}
```

The output `hello` is a single self-contained executable. No Python
interpreter required at runtime — except for embed-mode programs, which
use `libpython3` for parts the native compiler doesn't know about.

## Usage

```
pcc <source.py> [-o OUTPUT] [-O LEVEL] [--run] [--emit-ir] [--no-opt]
    [--embed | --native | --auto (default)]
```

| Flag | Meaning |
|---|---|
| `-o OUTPUT` | Output executable path (default: source basename) |
| `-O {0,1,2,3}` | LLVM optimization level (default: 2) |
| `--run` | Run the executable after building |
| `--emit-ir` | Keep the generated `.ll` / `.opt.ll` files for inspection |
| `--no-opt` | Skip the LLVM optimization pipeline |
| `--embed` | Force embed mode (route A) — link with `libpython` for 100% Python compatibility |
| `--native` | Force native mode (route B) — small/fast, but only works for our supported subset |
| `--auto` | **Default.** Auto-pick the right mode based on imports; if native mode fails, automatically fall back to embed mode |

Equivalent invocation as a module:

```bash
python -m pcc <source.py> ...
```

## Examples

### Native mode (small, fast)

```python
# fact.py
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

print(factorial(20))
```

```bash
$ pcc fact.py -o fact --run
[auto] no non-stdlib imports -> native mode (route B)
2432902008176640000
```

### Embed mode (any Python)

```python
# numpy_demo.py
import numpy as np
a = np.array([[1, 2], [3, 4]])
b = np.array([[5, 6], [7, 8]])
print(a.dot(b))
print(np.sum(a))
```

```bash
$ pcc numpy_demo.py -o numpy_demo --run
[auto] non-stdlib imports detected -> embed mode (route A+B)
[[19 22]
 [43 50]]
10
```

### Mixed: native + embed auto-fallback

```python
# mixed.py
import json              # stdlib - native handling
import numpy as np       # pip C extension - falls back to embed

data = json.loads('{"numbers": [1, 2, 3, 4, 5]}')
arr = np.array(data["numbers"])
print("sum:", int(arr.sum()))
print("mean:", float(arr.mean()))
```

```bash
$ pcc mixed.py -o mixed --run
[auto] non-stdlib imports detected -> embed mode (route A+B)
sum: 15
mean: 3.0
```

### Local file imports (auto-inlined)

```
project/
├── main.py
└── math_utils.py
```

```python
# math_utils.py
def add(a, b): return a + b
def mul(a, b): return a * b
PI = 3.14159
```

```python
# main.py
from math_utils import add, mul, PI
print("PI =", PI)
print("3 + 4 =", add(3, 4))
print("5 * 6 =", mul(5, 6))
```

```bash
$ pcc main.py -o main --run
[auto] no non-stdlib imports -> native mode (route B)
PI = 3.14159
3 + 4 = 7
5 * 6 = 30
```

The compiler automatically inlines `math_utils.py` into the final binary —
no runtime import needed.

## Architecture

```
            ┌────────────────────────────┐
source.py ─►│  1. Lexer    (lexer.py)    │ tokens
            │  2. Parser   (parser.py)   │ AST
            │  3. Semantic (semantic.py) │ typed AST + import resolution
            │  4. Codegen  (codegen.py)  │ LLVM IR (.ll)
            │  5. opt + clang            │ native executable
            └────────────────────────────┘
```

### Mode A — embed libpython (100% Python compatible)

The `glue.c` file provides a thin bridge between native LLVM IR and the
CPython interpreter:

- `py_embed_init(argc, argv)` — initialise the embedded interpreter
- `py_fallback_import("numpy")` — load a module
- `py_fallback_getattr(obj, "sum")` — read an attribute
- `py_call_method(obj, "sum", args, nargs)` — call a method
- `py_object_to_int / _float / _str` — unbox a Python value
- `py_int_to_pyobject / _float / _str` — box a native value

This lets native IR call into libpython at the precise points where
otherwise unknown features are needed. The result is **one process, one
binary**, with native code on the hot paths and libpython as the safety
net for the rest.

### Mode B — pure AOT (smallest, fastest)

Linked with `runtime.c` (a small self-contained C runtime that supplies
PyList, PyStr, PyDict, and basic operations) plus the LLVM optimizer
(`opt -passes=default<O2>`). The resulting binary has no Python
interpreter dependency and is typically a few hundred KB.

## Supported Python Features (Native mode)

### Data types
- `int`, `float`, `bool`, `str`, `None`
- `list[T]`, `tuple`, `dict[str, V]`, `set`
- F-strings with format spec

### Statements
- `if / elif / else`
- `while`, `for ... in range / list / str / enumerate / zip / dict`
- `break`, `continue`
- `try / except / finally / raise`
- `with`
- `def` (with closures, default args, `*args`, `**kwargs`)
- `class` (single inheritance, methods, `__init__`)

### Expressions
- All arithmetic and comparison operators
- Chained comparisons (`a < b < c`)
- Ternary `x if cond else y`
- List / dict / set comprehensions
- Generator expressions
- Lambda
- Slicing
- `and / or / not` short-circuit
- Walrus `:=`

### Stdlib (native, inlined)
- `random`, `math`, `re`, `time`, `datetime`, `os`, `sys`, `json`
- `itertools`, `functools`, `collections` (deque, Counter)
- `queue`, `threading`, `concurrent.futures`
- `string`, `struct`, `heapq`, `bisect`, `operator`
- `pathlib`, `shutil`, `glob`, `subprocess`
- `csv`, `base64`, `hashlib`, `secrets`
- `textwrap`, `pprint`, `unicodedata`, `codecs`
- `argparse`, `logging`, `warnings`, `traceback`
- And more — see [KNOWN_STDLIB](pcc/__main__.py)

### Anything else
- Pip-installed C extensions (`numpy`, `pandas`, `requests`, …)
- User modules not in our stdlib whitelist
- …automatically fall back to embed mode.

## Installation Details

### Prerequisites

- **Python 3.8+**
- **LLVM** (`opt` and `clang` in `$PATH`; LLVM 14+ recommended)
- **libpython** development headers (only required for embed mode)
  - Debian/Ubuntu: `sudo apt install libpython3-dev`
  - Fedora: `sudo dnf install python3-devel`
  - macOS: included with the python.org installer

### Build from source

```bash
git clone https://github.com/hi-tyc/pcc.git
cd pcc
pip install .
```

This installs the `pcc` command-line tool.

### Verify the install

```bash
$ pcc --help
usage: pcc [-h] [-o OUTPUT] [-O {0,1,2,3}] [--run] [--emit-ir] [--no-opt]
           [--embed] [--native] [--auto]
           source
```

## Python API

```python
import pcc
from pathlib import Path

from pcc.__main__ import compile_source

# Equivalent to `pcc myscript.py -o myexe`
out = compile_source(
    source=Path("myscript.py").read_text(),
    source_name="myscript.py",
    out_exec="myexe",
    opt_level=2,
    embed_mode=False,  # set True to force embed mode
)
print("Built:", out)
```

## Limitations

- Native mode is monomorphic: a function must be called with consistent
  argument types throughout the program. Use embed mode for polymorphic
  code (most real-world Python).
- Embed mode binaries need `libpython3` available at runtime; on most
  systems it's preinstalled, and the binary's RPATH points to it.

## Project Layout

```
pcc/
├── pcc/                       # Python package
│   ├── __init__.py            # version
│   ├── __main__.py            # `python -m pcc` entry point + compiler logic
│   ├── cli.py                 # `pcc` console script entry
│   ├── lexer.py               # tokenizer
│   ├── tokens.py              # token types
│   ├── parser.py              # parser -> AST
│   ├── ast_nodes.py           # AST node definitions
│   ├── semantic.py            # type inference + import resolution
│   ├── codegen.py             # AST -> LLVM IR
│   ├── runtime.c              # native AOT runtime (Route B)
│   └── glue.c                 # libpython bridge (Route A)
├── samples/                   # example programs
│   ├── basic.py               # simple native example
│   ├── test_features.py       # exhaustive native feature coverage
│   ├── hybrid_test.py         # numpy + native mixing
│   └── hybrid_complex.py      # larger numpy example
├── setup.py                   # legacy setup
├── pyproject.toml             # modern build config (PEP 517)
├── MANIFEST.in                # include C sources in sdist
├── LICENSE                    # MIT
└── README.md                  # you are here
```

## License

MIT — see [LICENSE](LICENSE).
