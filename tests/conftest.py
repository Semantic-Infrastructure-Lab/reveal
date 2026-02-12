"""Shared pytest fixtures and configuration for reveal test suite.

This module provides common fixtures for test isolation, temporary files,
and adapter registry management to prevent test pollution and reduce duplication.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from typing import Generator


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files.

    Automatically cleaned up after test completes.

    Example:
        def test_file_creation(temp_dir):
            test_file = temp_dir / "test.txt"
            test_file.write_text("content")
            assert test_file.exists()
    """
    tmp = tempfile.mkdtemp()
    try:
        yield Path(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def temp_file(temp_dir: Path) -> Generator[Path, None, None]:
    """Create a temporary file in a temporary directory.

    File is empty by default. Test can write content as needed.
    Automatically cleaned up after test completes.

    Example:
        def test_file_reading(temp_file):
            temp_file.write_text("test content")
            result = process_file(temp_file)
            assert result == "test content"
    """
    file_path = temp_dir / "test_file.txt"
    file_path.touch()
    yield file_path


@pytest.fixture
def sample_python_code() -> str:
    """Provide sample Python code for testing analyzers.

    Returns well-formed Python code with functions, classes, and imports.
    Useful for analyzer and parser tests.
    """
    return '''"""Sample module for testing."""

import os
from typing import List


class Calculator:
    """A simple calculator class."""

    def __init__(self):
        self.result = 0

    def add(self, x: int, y: int) -> int:
        """Add two numbers."""
        return x + y

    def multiply(self, x: int, y: int) -> int:
        """Multiply two numbers."""
        return x * y


def process_data(items: List[str]) -> List[str]:
    """Process a list of items."""
    return [item.upper() for item in items]


if __name__ == "__main__":
    calc = Calculator()
    print(calc.add(2, 3))
'''


@pytest.fixture
def sample_javascript_code() -> str:
    """Provide sample JavaScript code for testing analyzers."""
    return '''/**
 * Sample JavaScript module for testing
 */

class Calculator {
  constructor() {
    this.result = 0;
  }

  add(x, y) {
    return x + y;
  }

  multiply(x, y) {
    return x * y;
  }
}

function processData(items) {
  return items.map(item => item.toUpperCase());
}

module.exports = { Calculator, processData };
'''


@pytest.fixture
def sample_json_data() -> dict:
    """Provide sample JSON data structure for testing."""
    return {
        "name": "test_project",
        "version": "1.0.0",
        "dependencies": {
            "requests": "^2.28.0",
            "pytest": "^7.0.0"
        },
        "config": {
            "debug": False,
            "timeout": 30,
            "retries": 3
        }
    }


# Registry isolation fixtures
# These would require understanding reveal's adapter registry internals
# Placeholder for future implementation:
#
# @pytest.fixture
# def isolated_adapter_registry():
#     """Isolate adapter registry for tests that modify it.
#
#     Saves registry state before test, restores after.
#     Prevents pollution from tests that register adapters.
#     """
#     # TODO: Implement registry save/restore
#     # from reveal.adapters.base import _adapter_registry
#     # original_state = _adapter_registry.copy()
#     # yield
#     # _adapter_registry.clear()
#     # _adapter_registry.update(original_state)
#     pass


# Test markers (also defined in pyproject.toml)
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: fast unit tests (< 0.1s each)")
    config.addinivalue_line("markers", "integration: integration tests (subprocess-based, slower)")
    config.addinivalue_line("markers", "slow: tests taking > 1s each")
