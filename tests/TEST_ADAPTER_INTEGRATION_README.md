# Adapter Integration Tests

**File:** `tests/test_adapter_integration.py`
**Created:** 2026-01-16
**Purpose:** End-to-end integration testing of reveal's URI adapter system

## Overview

This test suite validates that reveal's adapter system works correctly through the CLI interface. It drives `reveal.main`'s CLI entry point via `conftest.py`'s `_run_reveal_direct` helper (in-process, not a real `subprocess` -- 10-20x faster, same code path) to ensure adapters work as users will experience them.

## Test Coverage

**Counts below drift -- regenerate instead of trusting a hardcoded number**
(BACK-1150; this doc previously said "20 tests, 6 of 13 adapters" from its
2026-01-16 creation and was already off by 2x within the same file):

```bash
pytest tests/test_adapter_integration.py --collect-only -q | tail -1
grep -c '^class Test' tests/test_adapter_integration.py
python -c "from reveal.adapters import list_supported_schemes as s; print(len(s()))"
```

As of 2026-08-21: **40 tests** across **13 test classes**, covering
**11 of 34** registered adapter schemes (`help`, `env`, `ast`, `git`, `json`,
`markdown`, `python`, `stats`, `imports`, `diff`, `reveal`). The other 23
schemes (`mysql`, `sqlite`, `xlsx`, `ssl`, `nginx`, `domain`, `cpanel`,
`autossl`, `letsencrypt`, `calls`, `contracts`, `depends`, `deps`,
`architecture`, `hotspots`, `overview`, `surface`, `testability`, `trace`,
`patches`, `pack`, `claude`, `codex`) have no CLI-subprocess integration test
here -- some are covered by other test files (see the file's own imports/
adjacent `test_*.py` for adapter-specific unit coverage), this file is not
the single source of truth for adapter coverage overall.

### ✅ Adapters covered by this file

#### help:// - Help System Adapter (4 tests)
- ✅ Lists available help topics
- ✅ Shows specific topics (tricks, adapters)
- ✅ Handles invalid topics gracefully
- **Usage:** `reveal help://`, `reveal help://tricks`

#### env:// - Environment Variables Adapter (4 tests)
- ✅ Lists all environment variables
- ✅ Shows specific variable (e.g., PATH)
- ✅ Organizes variables by category
- ✅ Handles nonexistent variables gracefully
- **Usage:** `reveal env://`, `reveal env://PATH`

#### ast:// - AST Query Adapter (3 tests)
- ✅ Shows Python code structure
- ✅ Queries with filters (e.g., `?type=function`)
- ✅ Handles invalid Python gracefully
- **Usage:** `reveal ast://./src`, `reveal ast://.?complexity>10`

#### git:// - Git Repository Adapter (4 tests)
- ✅ Shows repository overview (branches, tags, commits)
- ✅ Shows branch commit history
- ✅ Shows detailed commit history for refs
- ✅ Handles non-git directories gracefully
- **Usage:** `reveal git://.`, `reveal git://.@master`

#### json:// - JSON Adapter (4 tests)
- ✅ Shows JSON file structure
- ✅ Queries specific paths (e.g., `/user/name`)
- ✅ Handles invalid JSON with error code
- ✅ Handles invalid paths gracefully
- **Usage:** `reveal json://data.json`, `reveal json://data.json/user/name`

#### markdown:// - Markdown Query Adapter (1 test)
- ✅ Searches directories for markdown files
- **Usage:** `reveal markdown://./docs`

#### python:// - Python Runtime Adapter (5 tests)
- ✅ Shows Python environment information
- ✅ Shows version details
- ✅ Lists installed packages
- ✅ Shows virtual environment status
- ✅ Handles invalid elements gracefully
- **Usage:** `reveal python://`, `reveal python://version`, `reveal python://packages`

#### stats:// - Codebase Statistics Adapter (2 tests)
- ✅ Shows codebase metrics (files, lines, functions, complexity)
- ✅ Handles nonexistent paths gracefully
- **Usage:** `reveal stats://./src`

## Test Structure

Each adapter test class follows this pattern:

```python
class TestAdapterIntegration(unittest.TestCase):
    """Integration tests for adapter:// adapter."""

    def run_reveal_command(self, *args):
        """Run reveal command via _run_reveal_direct (in-process, not subprocess)."""
        # Drives reveal.main.main() directly with a patched sys.argv
        # Returns an object with .returncode/.stdout/.stderr

    def test_adapter_basic_functionality(self):
        """Test adapter works for basic use case."""
        result = self.run_reveal_command("adapter://resource")
        self.assertEqual(result.returncode, 0)
        self.assertIn('expected_content', result.stdout)

    def test_adapter_error_handling(self):
        """Test adapter handles errors gracefully."""
        result = self.run_reveal_command("adapter://invalid")
        # Verify no crashes, appropriate error messages
```

## Benefits

1. **Real-world validation** - Tests actual CLI usage, not just function calls
2. **User experience** - Catches issues users would encounter
3. **Integration coverage** - Tests CLI → routing → adapter → renderer flow
4. **Documentation** - Tests serve as usage examples
5. **Regression prevention** - Catches breaking changes in adapter interfaces

## Running Tests

```bash
# Run all adapter integration tests
python -m pytest tests/test_adapter_integration.py -v

# Run specific adapter tests
python -m pytest tests/test_adapter_integration.py::TestHelpAdapterIntegration -v
python -m pytest tests/test_adapter_integration.py::TestEnvAdapterIntegration -v
python -m pytest tests/test_adapter_integration.py::TestAstAdapterIntegration -v

# Run with coverage
python -m pytest tests/test_adapter_integration.py --cov=reveal --cov-report=term
```

## Coverage Impact

See the regenerate commands under "Test Coverage" above -- this section
previously carried point-in-time counts from 2026-01-16 (20 tests, 6/13
adapters) that had already drifted (actual: 40 tests, 11/34 adapters) by the
time anyone next read it. Don't hardcode a snapshot here again.

## Future Improvements

Already done since this doc's original "High Priority" list was written:
git:// CLI routing fixed, python:// tests added, imports:// tests added
(`TestImportsAdapterIntegration`), diff:// tests added
(`TestDiffAdapterIntegration`), stats:// tests added
(`TestStatsAdapterIntegration`). Still open:

### High Priority
1. **Add mysql:// / sqlite:// adapter tests** - Database inspection (requires mock/fixture DB)
2. **Add xlsx:// adapter tests** - Spreadsheet inspection

### Medium Priority
3. **Test error scenarios** - Invalid inputs, edge cases
4. **Test query parameters** - Complex query strings
5. **Test element extraction** - Specific element queries
6. **Add coverage for the remaining untested schemes** listed under "Test
   Coverage" above (ssl/nginx/domain/cpanel/autossl/letsencrypt/calls/
   contracts/depends/deps/architecture/hotspots/overview/surface/
   testability/trace/patches/pack/claude/codex) -- audit which already have
   adapter-specific unit coverage elsewhere before assuming a gap here means
   a gap overall.

### Low Priority
11. **Performance tests** - Adapter response times
12. **Stress tests** - Large files, many results
13. **Concurrent tests** - Multiple adapter calls
14. **Mock external dependencies** - Git repos, databases

## Related Files

- `tests/test_cli_commands_integration.py` - CLI flag integration tests
- `tests/test_cli_flags_integration.py` - CLI flag parsing tests
- `tests/test_rendering_json_env_ast_reveal.py` - Rendering unit tests
- `reveal/cli/routing.py` - URI routing logic
- `reveal/adapters/` - Adapter implementations

## Maintenance

- **Update frequency:** When new adapters added or adapter interfaces change
- **Breaking changes:** Tests will fail if adapter syntax changes
- **Documentation:** Keep usage examples in sync with actual adapter behavior

## Contributors

- TIA (The Intelligent Agent) - Initial test suite creation (2026-01-16)
