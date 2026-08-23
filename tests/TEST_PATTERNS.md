# Reveal Test Patterns and Conventions

**Author**: TIA (The Intelligent Agent)
**Date**: 2026-02-12
**Purpose**: Document test patterns, fixtures, and best practices for reveal test suite

---

## Overview

This document outlines patterns, fixtures, and conventions to maintain test quality and prevent common issues.

**Don't trust a hardcoded count here — it always rots.** Regenerate live:

```bash
# Test count
pytest --collect-only -q | tail -1

# Test file count
find tests -name "test_*.py" | wc -l

# Coverage
pytest --cov=reveal --cov-report=term | tail -5
```

As of 2026-08-21 (BACK-1150): 12,086 tests across 292 files, 165,701 test LOC.
The stale numbers this section previously carried (3,135 tests / 118 files,
dated 2026-02-12) had drifted by ~4x — a live rerun of the commands above is
the only trustworthy source, not this paragraph a session from now.

**Marker taxonomy: `BACK-1149`'s fuller lane taxonomy is registered and
file-level classification is complete.** Beyond `unit`/`integration`/`slow`,
`pyproject.toml` now also registers `component`/`contract`/`cli`/`mcp`/
`conformance`/`compat`/`external_fixture`. As of 2026-08-21, 291 of 293 test
files carry one of these new lane markers (regenerate live: `grep -lE
"pytest\.mark\.(component|contract|cli|mcp|conformance|compat|external_fixture)"
tests/*.py tests/adapters/*.py | wc -l`) — the remaining 2
(`conftest.py`, `corpus_paths.py`) are shared fixtures/helpers, not test
files, and correctly carry no marker. `test_xlsx_adapter.py` is marked at
class granularity rather than file level (`component` vs `external_fixture`
per class) since it genuinely mixes committed-fixture and manually-placed-file
tests — see the file itself for the per-class breakdown. Marker
classification is done, and the fast/PR/full-conformance run lanes are now
documented (see "Run Lanes" under "Available Markers" below) — BACK-1149 is
complete. CI itself still runs the full unfiltered suite on every push/PR by
design (the lane split is for local iteration, not a CI change — see "Run
Lanes" for why). Don't trust this paragraph's numbers past the session that
wrote them; regenerate live via the commands cited above and in "Run Lanes".

---

## Test Organization

### Directory Structure

```
tests/
├── conftest.py              # Shared fixtures and configuration
├── fixtures/                 # Test data and sample files
│   └── conversations/       # Sample conversation JSONL files
├── samples/                 # Sample code files (Java, C, etc.)
├── adapters/                # Adapter-specific tests
│   └── test_claude_adapter.py
└── test_*.py                # Main test files (count drifts -- see Overview)
```

### Test File Naming

- **Pattern**: `test_<component>.py`
- **Examples**:
  - `test_python_analyzer.py` - Python language analyzer
  - `test_git_adapter.py` - Git adapter functionality
  - `test_registry_integrity.py` - Registry validation

---

## Test Isolation and Fixtures

### Common Fixtures (conftest.py)

All tests have access to these fixtures:

#### 1. **temp_dir** - Temporary Directory
```python
def test_file_operations(temp_dir):
    """Test uses isolated temporary directory."""
    test_file = temp_dir / "test.txt"
    test_file.write_text("content")
    assert test_file.exists()
    # Automatic cleanup after test
```

#### 2. **temp_file** - Temporary File
```python
def test_file_reading(temp_file):
    """Test uses temporary file."""
    temp_file.write_text("test content")
    result = process_file(temp_file)
    assert result == "test content"
```

#### 3. **sample_python_code** - Sample Python Code
```python
def test_python_analyzer(sample_python_code):
    """Test uses pre-defined Python code."""
    result = analyze_python(sample_python_code)
    assert "Calculator" in result
```

#### 4. **sample_javascript_code** - Sample JavaScript Code
```python
def test_js_analyzer(sample_javascript_code):
    """Test uses pre-defined JavaScript code."""
    result = analyze_javascript(sample_javascript_code)
    assert "Calculator" in result
```

#### 5. **sample_json_data** - Sample JSON Structure
```python
def test_json_parsing(sample_json_data):
    """Test uses sample JSON data."""
    assert sample_json_data["name"] == "test_project"
    assert "dependencies" in sample_json_data
```

---

## Test Pollution Prevention

### The Problem

**Test pollution** occurs when one test modifies shared state that affects other tests. This causes:
- Tests passing in isolation but failing in full suite
- Flaky tests (intermittent failures)
- Hard-to-debug issues

### Real Example: Registry Pollution

**Issue**: `test_test_adapter.py` imported `TestAdapter`, which executed `@register_adapter('test')`, adding an adapter to the global registry. Later tests (`test_registry_integrity.py`) expected 17 production adapters but saw 18.

**Solution**: Centralized pollution handling via helper method:
```python
class TestAdapterRegistryIntegrity(unittest.TestCase):
    @staticmethod
    def _get_production_adapters():
        """Get registered production adapters, excluding test-only adapters.

        The 'test' adapter is registered during test runs but is not a production
        adapter (not imported in adapters/__init__.py, not documented).
        """
        adapters = set(list_supported_schemes())
        adapters.discard('test')
        return adapters

    def test_all_adapter_files_are_registered(self):
        # ... scan filesystem for adapters ...
        actually_registered = self._get_production_adapters()
        self.assertEqual(registered_in_code, actually_registered)
```

**Benefits**:
- Centralizes pollution handling in one place
- Clear documentation of why 'test' is excluded
- Multiple tests can use the same helper
- Easy to extend if more test-only adapters are added

### Best Practices

1. **Use fixtures** for setup/teardown instead of global state
2. **Isolate state** - save/restore if modifying singletons or registries
3. **Test in isolation** - each test should pass alone AND in full suite
4. **Avoid side effects** - don't modify files outside temp directories
5. **Clean up imports** - be careful with modules that auto-register on import

---

## Test Class Patterns

### unittest.TestCase Style (Legacy)

Many tests use `unittest.TestCase` with `setUp` methods:

```python
class TestPythonAnalyzer(unittest.TestCase):
    def setUp(self):
        """Run before each test."""
        self.analyzer = PythonAnalyzer()

    def test_analyze_function(self):
        """Test function analysis."""
        result = self.analyzer.analyze("def foo(): pass")
        self.assertIsNotNone(result)
```

### pytest Style (Recommended for New Tests)

New tests should use pytest fixtures:

```python
@pytest.fixture
def analyzer():
    """Create analyzer instance."""
    return PythonAnalyzer()

def test_analyze_function(analyzer):
    """Test function analysis."""
    result = analyzer.analyze("def foo(): pass")
    assert result is not None
```

**Why pytest style?**
- More flexible fixtures
- Better dependency injection
- Easier to share fixtures
- More pythonic

---

## Common Test Patterns

### 1. Structure Validation

Testing that output has expected structure:

```python
def test_structure_format(self):
    """Test output structure."""
    result = adapter.get_structure()

    # Validate contract fields
    assert "type" in result
    assert "version" in result
    assert "metadata" in result

    # Validate structure
    self.assertEqual(result["type"], "expected_type")
    self.assertIsInstance(result["metadata"], dict)
```

### 2. Error Handling

Testing graceful error handling:

```python
def test_invalid_input_handling(self):
    """Test error handling for invalid input."""
    with self.assertRaises(ValueError):
        process_invalid_data(None)

    # Or test graceful degradation
    result = process_data_safe(None)
    self.assertEqual(result, {"error": "Invalid input"})
```

### 3. Edge Cases

Testing boundary conditions:

```python
def test_edge_cases(self):
    """Test edge cases."""
    # Empty input
    assert process([]) == []

    # Single item
    assert process([1]) == [1]

    # Large input
    large_input = list(range(10000))
    result = process(large_input)
    assert len(result) == 10000
```

### 4. Subtests (for Multiple Cases)

Using subtests to test multiple scenarios:

```python
def test_multiple_languages(self):
    """Test multiple language analyzers."""
    test_cases = [
        ("python", "def foo(): pass"),
        ("javascript", "function foo() {}"),
        ("ruby", "def foo; end"),
    ]

    for lang, code in test_cases:
        with self.subTest(language=lang):
            result = analyze(lang, code)
            self.assertIsNotNone(result)
```

---

## Test Markers

Use pytest markers to categorize tests:

### Available Markers

```python
@pytest.mark.unit        # Fast unit tests (< 0.1s)
@pytest.mark.integration # Integration tests (slower)
@pytest.mark.slow        # Tests taking > 1s
```

`BACK-1149`'s broader lane taxonomy (applied incrementally, file by file, as
a module-level `pytestmark = pytest.mark.<lane>` rather than per-test):

```python
@pytest.mark.component        # single-module behavior, no subprocess/CLI involved
@pytest.mark.contract         # schema/shape/key-existence checks -- smoke alarms, not proof of correctness (BACK-1153)
@pytest.mark.cli              # exercises reveal.main's CLI entry point (in-process or subprocess)
@pytest.mark.mcp              # exercises the MCP server tool surface (reveal.mcp_server)
@pytest.mark.conformance      # cross-adapter or cross-language agreement/ratchet tests
@pytest.mark.compat           # dependency-version compatibility tests (e.g. tree-sitter-language-pack pinning)
@pytest.mark.external_fixture # depends on real external state (a live repo, network, or another host) beyond tmp_path fixtures
```

A file's marker was verified before applying it, not inferred from its
name — several `test_cli_*.py` files turned out to call `reveal.cli.*`
handler functions directly rather than going through `reveal.main`, so they
carry `component`, not `cli` (see git history for `BACK-1149` around
2026-08-21 for the reasoning).

### Run Lanes

`BACK-1149`'s three target lanes, layered on the markers above via
`pytest -m`. CI (`.github/workflows/test.yml`) still runs the full
unfiltered suite on every push/PR (~180s, not a real bottleneck given the
current test count) — these are for local iteration, not a CI change.
Counts below are a snapshot (2026-08-22); regenerate with
`pytest tests/ -m "<expr>" --collect-only -q | tail -1`.

```bash
# Fast local loop -- skip subprocess/CLI/MCP + cross-language/dependency/
# external-fixture lanes. ~10,849 tests, ~100s. Use this while iterating.
pytest tests/ -m "not (cli or mcp or conformance or compat or external_fixture)"

# PR lane -- everything except the lanes that need a controlled environment
# or are meant as periodic ratchets rather than per-change checks.
# ~11,707 tests.
pytest tests/ -m "not (conformance or compat or external_fixture)"

# Full/release lane -- the whole suite, no filter. What CI runs today.
# ~12,098 tests, ~180s.
pytest tests/
```

`conformance`, `compat`, and `external_fixture` are the three lanes worth
running deliberately rather than every loop: `conformance` cross-checks
adapters/languages against each other (only moves when adapter behavior
changes), `compat` pins against specific dependency versions (only moves on
a dependency bump), and `external_fixture` needs real external state that
usually isn't present locally anyway (skipif handles that gracefully). Run
the full/release lane before a release or after touching any of those three
areas; the fast lane is the everyday default.

### Usage

```python
@pytest.mark.unit
def test_fast_function():
    """Fast unit test."""
    assert add(2, 3) == 5

@pytest.mark.slow
def test_large_file_processing():
    """Slow integration test."""
    result = process_large_file("big.txt")
    assert result is not None
```

### Running Specific Markers

```bash
# Run only fast unit tests
pytest -m unit

# Skip slow tests
pytest -m "not slow"

# Run integration tests
pytest -m integration
```

---

## Test Naming Conventions

### Test Methods

- **Pattern**: `test_<what>_<scenario>`
- **Examples**:
  - `test_analyze_function_success`
  - `test_invalid_input_raises_error`
  - `test_empty_file_returns_none`

### Test Classes

- **Pattern**: `Test<Component><Aspect>`
- **Examples**:
  - `TestPythonAnalyzerBasic` - Basic functionality
  - `TestGitAdapterErrors` - Error handling
  - `TestAdapterRegistryIntegrity` - Registry validation

---

## Avoiding Common Pitfalls

### 1. Test Adapter Name Collision

**Problem**: pytest sees `TestAdapter` class in `reveal/adapters/test.py` and thinks it's a test class.

**Solution**: Suppress the warning in `pyproject.toml`:
```toml
filterwarnings = [
    "ignore:cannot collect test class 'TestAdapter':pytest.PytestCollectionWarning",
]
```

### 2. Registry Pollution

**Problem**: Tests that import adapters modify global registry.

**Solution**: Use helper method to get production adapters:
```python
# Use the centralized helper from TestAdapterRegistryIntegrity
production_adapters = TestAdapterRegistryIntegrity._get_production_adapters()
```

See "Test Pollution Prevention" section above for full example.

### 3. Hardcoded Paths

**Problem**: Tests fail on different systems due to absolute paths.

**Solution**: Use fixtures and Path objects:
```python
def test_file_reading(temp_dir):
    test_file = temp_dir / "test.txt"  # Relative to temp dir
    assert test_file.exists()
```

### 4. Test Order Dependencies

**Problem**: Tests pass when run alone but fail in suite due to order.

**Solution**: Each test should be independent:
```python
# BAD - depends on previous test
def test_step_1():
    global result
    result = setup()

def test_step_2():
    assert result is not None  # Fails if test_step_1 doesn't run first

# GOOD - independent
def test_step_1():
    result = setup()
    assert result is not None

def test_step_2():
    result = setup()  # Own setup
    assert result is not None
```

---

## Test Coverage

### Running Coverage

```bash
# Generate coverage report
pytest --cov=reveal --cov-report=html

# View report
open htmlcov/index.html
```

### Coverage Exclusions

These components are excluded from coverage (see `pyproject.toml`):
- Test files (`*/tests/*`, `*/test_*.py`)
- Database adapters requiring external connections (`reveal/adapters/mysql/*`, `reveal/adapters/sqlite/*`)

### Improving Coverage

Focus on:
1. **Error paths** - test exception handling
2. **Edge cases** - empty input, None values, large data
3. **Integration** - test component interactions
4. **Adapters** - ensure all adapters have test coverage

---

## Performance Tips

### Parallel Execution

`addopts` in `pyproject.toml` already runs `-n auto` by default (see BACK-1152's
note on `test_mcp_server.py` for a case where a single test still dominated
wall time despite parallelism -- xdist parallelizes across files/classes, it
doesn't make one pathological test fast):

```bash
pytest -n auto  # Auto-detect CPU cores (already the default)
pytest -n 0     # Serial -- needed for --pdb / -s under xdist
```

### Skipping Slow Tests

```bash
# Skip slow tests for quick validation
pytest -m "not slow"

# Run only fast unit tests
pytest -m unit
```

### Test Profiling

```bash
# Show slowest 10 tests
pytest --durations=10
```

---

## Contributing New Tests

### Checklist

- [ ] Test file named `test_<component>.py`
- [ ] Tests use fixtures from `conftest.py` where applicable
- [ ] Tests are independent (pass alone and in suite)
- [ ] Tests clean up after themselves (no side effects)
- [ ] Tests have descriptive docstrings
- [ ] Edge cases and error paths tested
- [ ] Appropriate markers applied (`@pytest.mark.unit`, etc.)
- [ ] Tests run quickly (< 0.1s for unit tests)

### Example Template

```python
"""Tests for <component>."""

import pytest
from reveal.<module> import <Component>


class TestComponentBasic:
    """Test basic <component> functionality."""

    def test_basic_usage(self):
        """Test <component> basic usage."""
        component = Component()
        result = component.process("input")
        assert result is not None

    def test_empty_input(self):
        """Test <component> with empty input."""
        component = Component()
        result = component.process("")
        assert result == ""


class TestComponentErrors:
    """Test <component> error handling."""

    def test_invalid_input_raises_error(self):
        """Test <component> raises error for invalid input."""
        component = Component()
        with pytest.raises(ValueError):
            component.process(None)
```

---

## Debugging Test Failures

### Verbose Output

```bash
pytest -v  # Verbose test names
pytest -vv # Extra verbose with diffs
```

### Show Full Tracebacks

```bash
pytest --tb=long  # Full tracebacks
pytest --tb=short # Short tracebacks
pytest --tb=line  # One line per failure
```

### Stop on First Failure

```bash
pytest -x  # Stop on first failure
pytest --maxfail=3  # Stop after 3 failures
```

### Run Specific Test

```bash
# By file
pytest tests/test_python_analyzer.py

# By class
pytest tests/test_python_analyzer.py::TestPythonAnalyzer

# By method
pytest tests/test_python_analyzer.py::TestPythonAnalyzer::test_analyze_function
```

### Debug with pdb

```bash
pytest --pdb  # Drop into debugger on failure
pytest --trace # Drop into debugger at start of each test
```

---

## Test Quality Metrics

### Current Stats

Regenerate, don't read a number off this page (see Overview) -- the
2026-02-12 figures this section carried for six months (3,135 tests/118
files) were off by ~4x by the time anyone next checked.

### Quality Goals

- **Pass rate**: 100% (all tests pass)
- **Coverage**: Target 80%+ for critical paths
- **Speed**: Unit tests < 0.1s, integration tests < 1s
- **Isolation**: Tests pass both alone and in suite
- **Clarity**: Descriptive names and docstrings

---

## References

- **pytest documentation**: https://docs.pytest.org/
- **unittest documentation**: https://docs.python.org/3/library/unittest.html
- **Project configuration**: `pyproject.toml`
- **Fixtures**: `tests/conftest.py`
- **Test patterns**: This document

---

## Revision History

- **2026-08-22** (BACK-1148, all children done): Test suite architecture
  effort complete — BACK-1149 (marker taxonomy + run lanes, documented
  above), BACK-1150, BACK-1151 (`test_ast_nav_probe_features.py` monolith
  split into 6 files by feature area), BACK-1152 (MCP lane perf fix), and
  BACK-1153 (theater-test audit of all 3 named candidate files — found and
  fixed exactly one overclaiming test, `test_die_exit_call_detected`;
  everything else audited was solid-semantic, not theater). See `tt show
  BACK-1148` for the full history across sessions.
- **2026-08-21** (BACK-1150): Replaced hardcoded test/file/coverage counts
  (stale by ~4x) with regenerate-live commands throughout; noted the actual
  marker taxonomy is still unit/integration/slow pending BACK-1149.
- **2026-02-12**: Initial documentation (cursed-prophet-0212 session)
  - Documented test pollution issue and fix
  - Created conftest.py with common fixtures
  - Suppressed TestAdapter warning
  - Fixed 3 registry integrity test failures
