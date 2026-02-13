# PCC Test Suite

This directory contains the comprehensive test suite for the pcc (Python-to-C-to-Executable) compiler.

## Directory Structure

The test suite is organized to mirror the application's architecture:

```
tests/
├── README.md                 # This file
├── conftest.py              # Shared pytest fixtures and configuration
├── __init__.py              # Test package initialization
├── unit/                    # Unit tests for individual components
│   ├── __init__.py
│   ├── test_ir/            # Tests for IR (Intermediate Representation)
│   │   ├── __init__.py
│   │   └── test_nodes.py   # Tests for IR node classes
│   ├── test_core/          # Tests for core compiler components
│   │   ├── __init__.py
│   │   ├── test_parser.py  # Tests for the parser
│   │   └── test_compiler.py # Tests for the main compiler
│   ├── test_backend/       # Tests for code generation
│   │   ├── __init__.py
│   │   └── test_codegen.py # Tests for C code generator
│   └── test_utils/         # Tests for utility modules
│       ├── __init__.py
│       ├── test_settings.py # Tests for settings
│       └── test_toolchain.py # Tests for toolchain detection
├── integration/            # Integration tests
│   └── __init__.py
│   └── test_end_to_end.py  # End-to-end compilation tests
└── fixtures/               # Test input files and expected outputs
    ├── t01_print_1.py
    ├── t01_print_1.expected.txt
    ├── t02_print_multi.py
    ├── t02_print_multi.expected.txt
    └── ... (39 test pairs total)
```

## Naming Convention

Test files follow the standardized naming pattern:
- **Unit tests:** `test_<module>/<component>.test.py` or `test_<component>.py`
- **Integration tests:** `test_<feature>_integration.py`
- **Fixture files:** `t<nn>_<description>.py` and `t<nn>_<description>.expected.txt`

## Running Tests

### Run all tests
```bash
pytest
```

### Run specific test categories
```bash
# Unit tests only
pytest tests/unit/

# Specific module tests
pytest tests/unit/test_ir/
pytest tests/unit/test_core/
pytest tests/unit/test_backend/

# Integration tests
pytest tests/integration/
```

### Run with coverage
```bash
pytest --cov=pcc --cov-report=html
pytest --cov=pcc --cov-report=term-missing
```

### Run with verbose output
```bash
pytest -v
```

## Test Categories

### Unit Tests

Unit tests verify individual components in isolation:

- **test_ir/test_nodes.py**: Tests for IR node classes (IntConst, StrConst, BinOp, etc.)
- **test_core/test_parser.py**: Tests for Python AST to IR parsing
- **test_backend/test_codegen.py**: Tests for IR to C code generation

### Integration Tests

Integration tests verify the interaction between multiple components:

- **test_end_to_end.py**: Tests the full compilation pipeline from Python to executable

### Fixtures

The `fixtures/` directory contains 39 pairs of test files:
- `.py` files: Python source code to compile
- `.expected.txt` files: Expected output for verification

These fixtures cover:
- Basic print statements (t01-t05)
- Control flow: if/else (t07-t09)
- Loops: while (t10-t12), for-range (t22-t25)
- Functions (t13-t15)
- Recursion (t16-t18)
- Break/continue (t19-t21)
- String operations (t26-t29)
- BigInt arithmetic (t30-t33)
- Division and modulo (t34-t39)

## Adding New Tests

### Adding Unit Tests

1. Create a new test file in the appropriate subdirectory under `tests/unit/`
2. Use the naming convention: `test_<component>.py`
3. Import the module being tested from `pcc.<module>`
4. Use pytest fixtures from `conftest.py` where applicable

Example:
```python
# tests/unit/test_core/test_new_feature.py
import pytest
from pcc.core.new_feature import NewFeature

class TestNewFeature:
    def test_basic_functionality(self):
        feature = NewFeature()
        result = feature.process()
        assert result == expected_value
```

### Adding Integration Tests

1. Create a new test file in `tests/integration/`
2. Test the interaction between multiple components
3. Use temporary directories for file operations

### Adding Fixtures

1. Create a Python file in `tests/fixtures/`: `t<nn>_<description>.py`
2. Create the expected output file: `t<nn>_<description>.expected.txt`
3. Use sequential numbering for new fixtures

## Configuration

### conftest.py

The `conftest.py` file provides:
- **temp_dir**: Temporary directory fixture for file operations
- **sample_python_file**: Sample Python file fixture
- **compiler**: Pre-configured Compiler instance
- **parser**: Pre-configured Parser instance
- **codegen**: Pre-configured CodeGenerator instance

### pytest.ini (optional)

You can create a `pytest.ini` file in the project root for default options:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
```

## Coverage Goals

- **Target:** 85%+ code coverage
- **Current:** ~87% (measured by pytest-cov)

## Continuous Integration

When running in CI/CD:
```bash
# Install test dependencies
pip install pytest pytest-cov

# Run tests with coverage
pytest --cov=pcc --cov-report=xml --cov-fail-under=85

# Run all tests
pytest -v
```

## Troubleshooting

### Import Errors
If you encounter import errors, ensure:
1. The project is installed: `pip install -e .` (if using setup.py/pyproject.toml)
2. You're running pytest from the project root
3. Python path includes the project directory

### Test Discovery Issues
If pytest doesn't discover tests:
1. Check file naming: must start with `test_`
2. Check class naming: must start with `Test`
3. Check function naming: must start with `test_`
4. Verify `__init__.py` files exist in test directories

## Maintenance

- Keep tests independent and isolated
- Use fixtures for shared setup/teardown
- Update tests when modifying source code
- Remove obsolete tests when removing features
- Maintain test coverage above 85%

## Contact

For questions about the test suite, refer to the main project README.md or contact the maintainers.
