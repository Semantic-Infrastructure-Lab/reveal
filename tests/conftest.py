"""Shared pytest fixtures and configuration for reveal test suite.

This module provides common fixtures for test isolation, temporary files,
and adapter registry management to prevent test pollution and reduce duplication.
"""

import os
import pytest
import sys
import tempfile
import shutil
from pathlib import Path
from typing import Generator
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr


def _run_reveal_direct(*args):
    """Run reveal in-process to avoid subprocess startup overhead.

    Equivalent to subprocess.run([sys.executable, '-m', 'reveal.main'] + list(args))
    but 10-20x faster: no interpreter startup, warm tree-sitter cache across calls.

    Returns an object with .returncode, .stdout, .stderr attributes.
    Safe for use within a single xdist worker (tests in a worker run serially).
    """
    from reveal.main import main

    old_argv = sys.argv
    sys.argv = ['reveal'] + [str(a) for a in args]
    buf_out = StringIO()
    buf_err = StringIO()
    rc = 0
    try:
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            try:
                main()
            except SystemExit as e:
                rc = e.code if isinstance(e.code, int) else 0
    finally:
        sys.argv = old_argv

    class _Result:
        __slots__ = ('returncode', 'stdout', 'stderr')

        def __init__(self, returncode, stdout, stderr):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    return _Result(rc, buf_out.getvalue(), buf_err.getvalue())


def native(posix_path: str) -> str:
    """Convert a POSIX path string to the platform-native string form.

    Use this in assertions that compare path strings from production code,
    which stores paths using ``str(Path(...))``.  On Linux the result is
    identical to the input; on Windows forward slashes become backslashes.

    Example::

        assert result['file'] == native('/fake/x.py')
        assert native('src/main.py') in structure['path']
    """
    return str(Path(posix_path))


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


_PROBE_COMPLEX = '''
def complex_{i}(x, y=0):
    total = 0
    if x > 0:
        if x > 10:
            if x > 100:
                return "huge"
            return "big"
        for k in range(x):
            if k % 2 == 0:
                total += k
            elif k % 3 == 0:
                total -= k
            else:
                while total > 50:
                    total //= 2
    elif x < 0:
        while x < 0:
            x += 1
    try:
        total += int(os.getenv("N{i}", "0"))
    except ValueError:
        pass
    return total + y
'''


@pytest.fixture(scope="session")
def flag_probe_corpus(tmp_path_factory) -> Path:
    """A small Python project that overflows every default cap the flag-matrix probes lift.

    Replaces probing reveal's own reveal/ and reveal/adapters trees (BACK-1451): those
    cost 6-59s per probe and ran baseline + changed. Sized past each cap a probe relies
    on: 30 complex modules (hotspot/overview/stats/ast top-N), 8 subpackages
    (architecture's top=5 components), a pyproject.toml so depends:// resolves the
    chained imports, and 3 patches per production function (testability's
    min_patches=3, top=20 groups; patches:// cap). Layout: <root>/pkg, <root>/tests.
    """
    root = tmp_path_factory.mktemp("flag_probe_corpus")
    pkg, tests, subpackages = root / "pkg", root / "tests", 8
    tests.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname = "pkg"\nversion = "0"\n', encoding="utf-8")
    for s in range(subpackages):
        (pkg / f"sub{s}").mkdir(parents=True)
        (pkg / f"sub{s}" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    for i in range(30):
        sub = f"sub{i % subpackages}"
        src = "import os\nimport json\n"
        if i:
            src += f"from pkg.sub{(i - 1) % subpackages} import mod{i - 1}\n"
        src += _PROBE_COMPLEX.format(i=i)
        src += f"\n\ndef helper_{i}():\n"
        src += (f"    return complex_{i}(1) + mod{i - 1}.helper_{i - 1}()\n" if i
                else f"    return complex_{i}(1)\n")
        src += (f"\n\nclass Thing{i}:\n    def run(self):\n        return helper_{i}()\n\n"
                f"    def dump(self):\n        return json.dumps({{'i': {i}}})\n")
        (pkg / sub / f"mod{i}.py").write_text(src, encoding="utf-8")
        test = f"from unittest.mock import patch\nfrom pkg.{sub} import mod{i}\n"
        for t in range(3):
            test += (f"\n\n@patch('pkg.{sub}.mod{i}.complex_{i}', return_value={t})\n"
                     f"def test_complex_{i}_{t}(complex_fn):\n"
                     f"    assert mod{i}.complex_{i}({t}) == {t}\n")
        (tests / f"test_mod{i}.py").write_text(test, encoding="utf-8")
    return root


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
    config.addinivalue_line("markers", "real_worker_pool: needs reveal's own ProcessPoolExecutor "
                            "(clears the suite-wide REVEAL_MAX_WORKERS=1)")
    # xdist already saturates the cores; reveal's internal pools on top only add contention
    # (flag-matrix tests: 178s -> 103s). Explicit developer overrides win.
    os.environ.setdefault("REVEAL_MAX_WORKERS", "1")


@pytest.fixture(autouse=True)
def _serial_workers_unless_pool_test(request, monkeypatch):
    if request.node.get_closest_marker("real_worker_pool"):
        monkeypatch.delenv("REVEAL_MAX_WORKERS", raising=False)
