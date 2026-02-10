# Reveal Dogfooding Issues - 2026-02-07

**Session**: obsidian-gem-0207
**Version Tested**: v0.47.0 (development)
**Date**: 2026-02-07

## Critical Issues

### ~~Issue #6: Schema Queries Fail in Batch Execution~~ ✓ RESOLVED

**Severity**: ~~High~~ **FALSE ALARM**
**Component**: ~~Help adapter / CLI state management~~ **User error**

**Description**:
~~When multiple `help://schemas/<adapter>` queries are executed in the same shell session~~
This was caused by testing with v0.33.0 instead of v0.47.0 due to incorrect pip installation.

**Root Cause**:
Old version (v0.33.0) was still installed in site-packages and taking precedence over development install (v0.47.0). Schema support wasn't added until v0.47.0.

**Resolution**:
Force reinstall with `pip install -e . --force-reinstall --no-deps` ensured correct version.

**Status**: RESOLVED - No actual bug, schemas work correctly in v0.47.0

---

## High Priority Issues

### Issue #2: Stats Adapter Silent Failure on Single Files

**Severity**: Medium
**Component**: Stats adapter

**Description**:
The stats adapter produces no output when given a single file, but works on directories. No error message is shown.

**Reproduction**:
```bash
# Silent failure - no output:
reveal 'stats://path/to/file.py'

# Works fine:
reveal 'stats://path/to/directory/'
```

**Expected Behavior**:
Either:
1. Show stats for the single file
2. Show clear error: "Stats adapter requires a directory, not a single file"

**Impact**: Confusing UX - users don't know if command failed or there's no data

**Fix**: Add proper error message or support single files

---

## Documentation Issues

### Issue #1: Version Mismatch in AGENT_HELP.md

**Severity**: Low
**Component**: Documentation

**Description**:
AGENT_HELP.md claims schemas are available in "v0.46.0+" but the feature is actually in v0.47.0 (unreleased).

**Location**: `external-git/reveal/docs/AGENT_HELP.md:23`

**Current Text**:
```markdown
## Agent Introspection (v0.46.0+ → v0.47.0 Complete Coverage)
```

**Fix**: Change to:
```markdown
## Agent Introspection (v0.47.0 - Full Coverage)
```

**Impact**: Users on v0.46.x will try to use schemas and get errors

---

## Test Script Issues (Not Bugs)

### Git Adapter Test

**Issue**: Test script path was incorrect
**Resolution**: Git adapter works correctly, test needed to run from within git repo
**Status**: Not a bug

### Domain Adapter Test

**Issue**: Test script showed confusing error but adapter worked
**Resolution**: stderr error was misleading but functionality is correct
**Status**: Not a bug

---

## Testing Summary

### Adapters Tested Successfully ✓

All 15 adapters tested and working:

1. ✓ AST - Code structure queries
2. ✓ Stats - Codebase statistics (directories only)
3. ✓ SSL - Certificate inspection
4. ✓ Env - Environment variables
5. ✓ JSON - JSON file navigation
6. ✓ Markdown - Markdown queries
7. ✓ Reveal - Self-introspection
8. ✓ Diff - Resource comparison
9. ✓ Imports - Import graph analysis
10. ✓ Python - Runtime inspection
11. ✓ Git - File history
12. ✓ Domain - DNS/WHOIS/SSL
13. ⊘ Claude - Requires conversation export (not tested)
14. ⊘ MySQL - Requires MySQL connection (not tested)
15. ✓ SQLite - Database inspection

### Schema Coverage

**Expected**: 15/15 adapters with schemas
**Tested**: All schemas exist and work individually
**Issue**: Batch testing fails due to Issue #6

---

## Recommendations

### Immediate Actions

1. **Fix Issue #6** (Critical) - Investigate and fix batch schema query failures
   - Check for module-level state in help adapter
   - Verify adapter registry cleanup between invocations
   - Add tests for multiple schema queries in same process

2. **Fix Issue #2** (High) - Add proper error message to stats adapter for single files

3. **Fix Issue #1** (Low) - Update AGENT_HELP.md version reference

### Testing Improvements Needed

1. **Add integration tests** for batch schema queries
2. **Add edge case tests** for single file vs directory handling
3. **Add version validation** to catch doc/code mismatches

### Documentation Improvements

1. Clarify which adapters require specific resources (MySQL, Claude, etc.)
2. Add "Troubleshooting Batch Queries" section
3. Document single file vs directory behavior for all adapters

---

## Fixes Applied ✓

### 1. Test Registry Updates (FIXED)
- Added 'domain' to expected_adapters in `tests/test_registry_integrity.py`
- Updated README.md adapter count from 15 to 16
- All registry integrity tests now pass (10/10)

### 2. Documentation Corrections (FIXED)
- README.md now correctly states "16 adapters" (was: 15)
- Three occurrences updated across README

## Test Coverage Analysis

**Overall Coverage**: 10% (17,311 untested out of 19,300 lines)

**Well-Tested Components** (>70%):
- Core analyzers: Python, Ruby, JavaScript (>90%)
- Quality rules: D001, D002, C901, C902 (>85%)
- Base infrastructure: registry.py (85%)

**Under-Tested Components** (<20%):
- Adapters: Most adapters have minimal test coverage
- Validation rules (V-series): 0% coverage
- CLI routing and introspection: ~15%
- Tree-sitter base: 15%
- Breadcrumbs system: 12%

**Recommendations for Coverage Improvement**:
1. Add adapter integration tests (currently sparse)
2. Add validation rule tests (V-series completely untested)
3. Test CLI routing edge cases
4. Test breadcrumb generation across languages

## Remaining Issues

### Issue #2: Stats Adapter Silent Failure on Single Files (UNFIXED)
**Status**: Documented but not fixed
**Recommendation**: Add proper error message or support single-file stats

### Issue #1: Version Mismatch in AGENT_HELP.md (UNFIXED)
**Status**: Documented but not fixed
**Recommendation**: Update AGENT_HELP.md line 23 from "v0.46.0+" to "v0.47.0"

## Installation Issues Discovered

### Issue #7: Editable Install Metadata Not Always Updated
**Severity**: Medium
**Component**: pip editable install

**Description**:
When doing `pip install -e .`, the package metadata doesn't always update correctly, leading to version mismatches where `reveal --version` shows one version but `importlib.metadata.version()` shows another.

**Solution**:
```bash
pip uninstall -y reveal-cli
pip install -e . --force-reinstall
```

**Recommendation**: Add installation troubleshooting section to README.md

## Next Steps

1. ~~Fix test registry updates~~ ✓ DONE
2. ~~Update adapter count in README~~ ✓ DONE
3. Fix Issue #2 (stats adapter error handling)
4. Fix Issue #1 (AGENT_HELP.md version reference)
5. Add adapter integration tests to improve coverage
6. Add V-series validation rule tests
7. Consider adding installation troubleshooting to docs
