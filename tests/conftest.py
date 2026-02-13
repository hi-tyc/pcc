"""
Pytest configuration and fixtures for pcc tests.
"""

import pytest
import tempfile
from pathlib import Path


@pytest.fixture
def temp_dir():
    """Provide a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def sample_python_file(temp_dir):
    """Create a sample Python file for testing."""
    py_file = temp_dir / "test_input.py"
    py_file.write_text("print(1 + 2)\n")
    return py_file


@pytest.fixture
def compiler():
    """Provide a Compiler instance."""
    from pcc import Compiler
    return Compiler()


@pytest.fixture
def parser():
    """Provide a Parser instance."""
    from pcc.core import Parser
    return Parser()


@pytest.fixture
def codegen():
    """Provide a CodeGenerator instance."""
    from pcc.backend import CodeGenerator
    return CodeGenerator()
