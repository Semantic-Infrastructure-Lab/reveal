# Dogfooding Report: Reveal v0.39.0

**Date**: 2026-01-19
**Methodology**: Start from `reveal://help`, navigate through all adapter documentation, validate each adapter works
**Session**: psychic-shark-0119 (findings), burning-trajectory-0119 (validation)

## Executive Summary

Dogfooding reveal's own help system revealed a **critical architectural bug**: newly added adapters (`claude://`, `git://`, `stats://`) weren't being imported in `routing.py`, causing "No renderer registered" errors.

**Root Cause**: Manual import list in `routing.py:53` fell out of sync with `adapters/__init__.py`
**Fix**: Simplified to single source of truth - `from .. import adapters`
**Prevention**: Added `test_all_adapters_have_renderers` regression test

## Adapters Tested

### Working Correctly (11/14)

| Adapter | Test Command | Result |
|---------|--------------|--------|
| `help://` | `reveal help://` | ✅ Excellent organization |
| `help://adapters` | `reveal help://adapters` | ✅ Lists all adapters |
| `help://workflows` | `reveal help://workflows` | ✅ Practical examples |
| `ast://` | `reveal 'ast://./reveal?complexity>10'` | ✅ Powerful queries |
| `env://` | `reveal env://` | ✅ Clean output |
| `python://` | `reveal python://doctor` | ✅ Genuinely useful diagnostics |
| `json://` | `reveal json://pyproject.toml` | ✅ Good path navigation |
| `imports://` | `reveal imports://reveal` | ✅ Dependency analysis |
| `diff://` | `reveal 'diff://file.py:backup.py'` | ✅ Semantic comparison |
| `markdown://` | `reveal markdown://.` | ✅ Frontmatter queries |
| `reveal://` | `reveal reveal://` | ✅ Self-inspection |

### Were Broken - Now Fixed (3/14)

| Adapter | Original Error | Root Cause |
|---------|----------------|------------|
| `claude://` | "No renderer registered for scheme 'claude'" | Missing from routing.py imports |
| `git://` | "No renderer registered for scheme 'git'" | Missing from routing.py imports |
| `stats://` | "No renderer registered for scheme 'stats'" | Missing from routing.py imports |

### Partial/Needs Improvement (0/14)

All adapters now route correctly after the fix.

## Critical Bug: Adapter Registration Sync

### The Problem

`routing.py` line 53 had a manual import list:
```python
from ..adapters import env, ast, help, python, json_adapter, reveal, mysql, sqlite, imports, diff, markdown
```

This list was missing `claude`, `git`, and `stats`, even though they were properly exported in `adapters/__init__.py`.

### Why It Happened

Two sources of truth:
1. `adapters/__init__.py` - defines `__all__` with all adapter modules
2. `routing.py` - manually listed imports to trigger registration

When new adapters were added, only `__init__.py` was updated.

### The Fix

Single source of truth:
```python
# Import adapters package to trigger all registrations (single source of truth)
from .. import adapters as _adapters
```

### Prevention

Added regression test in `tests/test_adapter_contracts.py`:
```python
def test_all_adapters_have_renderers(self):
    """Prevents 'No renderer registered' errors."""
    for scheme in self.all_schemes:
        renderer_class = get_renderer_class(scheme)
        self.assertIsNotNone(renderer_class, ...)
```

## Documentation Findings

### What Works Well

1. **help:// system** - Progressive disclosure, good organization
2. **AGENT_HELP.md** - Comprehensive quick reference
3. **Adapter-specific guides** - PYTHON_ADAPTER_GUIDE.md, etc.

### Gaps Found & Fixed

1. **Extraction syntaxes undocumented** - `:LINE`, `@N`, `Class.method` were functional but not in AGENT_HELP.md
   - **Fix**: Added extraction syntax section with v0.39.0+ markers

2. **help://adapters/stats missing** - No dedicated help section for stats adapter
   - **Status**: Low priority - adapter works, basic help exists

## Quality Observations

### Strengths

1. **help:// is genuinely useful** - Discovered features I didn't know about
2. **ast:// queries are powerful** - `complexity>10` filter found 47 complex functions
3. **python://doctor** - Excellent for debugging environment issues
4. **stats://hotspots** - Good quality analysis integration

### Opportunities

1. **sqlite:// error handling** - Could provide better messages for non-existent DBs
2. **mysql:// connection errors** - Generic errors, could be more helpful
3. **Adapter help consistency** - Some adapters have detailed help, others minimal

## Test Results

After fixes:
- **2525 tests passed**, 2 skipped
- **10 adapter contract tests pass** including new renderer registration test
- All adapters route correctly

## Files Modified

| File | Change |
|------|--------|
| `reveal/cli/routing.py` | Simplified adapter import |
| `reveal/adapters/claude/adapter.py` | Added input validation |
| `tests/test_adapter_contracts.py` | Added renderer registration test |
| `reveal/docs/AGENT_HELP.md` | Documented extraction syntaxes |

## Recommendations

### Immediate (Done)
- [x] Fix routing.py imports
- [x] Add regression test
- [x] Document extraction syntaxes

### Future
- [ ] Add help sections for all adapters in help://adapters/{adapter}
- [ ] Improve error messages for database adapters
- [ ] Consider adapter self-test capability (`reveal {adapter}://test`)

## Conclusion

Dogfooding from `reveal://help` proved valuable - it found a real bug that would have affected users of the claude://, git://, and stats:// adapters. The fix is simple and the regression test prevents recurrence.

**Time invested**: ~30 minutes
**Bugs found**: 1 (affecting 3 adapters)
**Tests added**: 1
**Docs improved**: 2 files
