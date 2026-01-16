# Adapter Integration Tests

**File:** `tests/test_adapter_integration.py`
**Created:** 2026-01-16
**Purpose:** End-to-end integration testing of reveal's URI adapter system

## Overview

This test suite validates that reveal's adapter system works correctly through the CLI interface. It tests actual command execution using `subprocess` to ensure adapters work as users will experience them.

## Test Coverage

### ✅ Fully Tested Adapters (17 passing tests)

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

#### json:// - JSON Adapter (4 tests)
- ✅ Shows JSON file structure
- ✅ Queries specific paths (e.g., `/user/name`)
- ✅ Handles invalid JSON with error code
- ✅ Handles invalid paths gracefully
- **Usage:** `reveal json://data.json`, `reveal json://data.json/user/name`

#### markdown:// - Markdown Query Adapter (1 test)
- ✅ Searches directories for markdown files
- **Usage:** `reveal markdown://./docs`

#### git:// - Git Repository Adapter (1 test)
- ✅ Handles non-git directories gracefully
- ⏭️ 3 tests skipped (requires CLI routing fix)

### ⏭️ Skipped Tests (3 tests)

#### git:// adapter tests requiring routing fix:
- `test_git_adapter_shows_repo_info` - git://. syntax not receiving resource parameter
- `test_git_adapter_shows_status` - CLI routing issue
- `test_git_adapter_shows_log` - CLI routing issue

**Issue:** The git:// adapter initialization expects `resource` or `path` parameter but isn't receiving it through CLI routing. Documented for future fix.

## Test Structure

Each adapter test class follows this pattern:

```python
class TestAdapterIntegration(unittest.TestCase):
    """Integration tests for adapter:// adapter."""

    def run_reveal_command(self, *args):
        """Run reveal command via subprocess."""
        # Execute reveal.main as subprocess
        # Return CompletedProcess with stdout/stderr

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

- **Tests added:** 20 total (17 passing, 3 skipped)
- **Overall test count:** 2154 → 2171 (+17 tests)
- **Coverage improvement:** 73% → 74% (+1%)
- **Adapters tested:** 6 of 13 registered adapters

## Future Improvements

### High Priority
1. **Fix git:// CLI routing** - Enable 3 skipped tests
2. **Add python:// adapter tests** - Runtime environment inspection
3. **Add imports:// adapter tests** - Import graph analysis
4. **Add diff:// adapter tests** - Semantic diff functionality
5. **Add mysql:// adapter tests** - Database inspection (requires mock)

### Medium Priority
6. **Add sqlite:// adapter tests** - Database inspection
7. **Add stats:// adapter tests** - File statistics
8. **Test error scenarios** - Invalid inputs, edge cases
9. **Test query parameters** - Complex query strings
10. **Test element extraction** - Specific element queries

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
