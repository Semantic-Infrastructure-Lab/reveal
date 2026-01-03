# Post-v0.29.0 Code Quality Improvements

**Created:** 2026-01-03
**Purpose:** Document code quality issues for post-release refactoring
**Status:** Deferred (not blocking v0.29.0 release)

---

## Overview

Reveal v0.29.0 has been released with excellent quality metrics:
- ✅ 1,320/1,320 tests passing (100%)
- ✅ 76% code coverage
- ✅ 96.8/100 quality score (from `reveal stats://./reveal`)
- ✅ All documentation coherent and up-to-date

However, analysis identified opportunities for refactoring that should be addressed in future releases.

---

## High-Complexity Functions (158 total with complexity > 15)

### Top 5 Hotspots (complexity > 40)

#### 1. `reveal/rendering/adapters/help.py:285` - `_render_help_adapter_specific`
- **Complexity:** 55
- **Lines:** 96
- **Issue:** Highly conditional rendering logic
- **Impact:** Maintainability
- **Recommendation:** Extract adapter-specific rendering into strategy pattern
- **Priority:** Medium (not user-facing, but hard to maintain)

#### 2. `reveal/analyzers/gdscript.py:15` - `get_structure`
- **Complexity:** 44
- **Lines:** 79
- **Issue:** GDScript parser complexity
- **Impact:** Language-specific complexity, acceptable
- **Recommendation:** Consider breaking into smaller parser functions
- **Priority:** Low (inherently complex domain)

#### 3. `reveal/adapters/python/modules.py:176` - `get_syspath_analysis`
- **Complexity:** 43
- **Lines:** 68
- **Issue:** Complex edge case handling for Python sys.path
- **Impact:** Maintainability
- **Recommendation:** Extract edge case handlers into separate functions
- **Priority:** Low (works correctly, well-tested)

#### 4. `reveal/rendering/adapters/reveal.py:111` - `render_reveal_structure`
- **Complexity:** 43
- **Lines:** 71
- **Issue:** Deep nesting in structure rendering
- **Impact:** Maintainability
- **Recommendation:** Use composition over large conditionals
- **Priority:** Medium

#### 5. `reveal/rendering/adapters/reveal.py:7` - `_render_config_structure`
- **Complexity:** 42
- **Lines:** 102
- **Issue:** Deep nesting, multiple concerns
- **Impact:** Maintainability
- **Recommendation:** Split into focused renderers
- **Priority:** Medium

---

## Unused Imports (86 total)

### Analysis

Many "unused" imports are intentional:
- `__init__.py` imports for public API exposure
- `pytest` imports used by fixtures (not directly visible)
- Cross-module imports for type checking

### Action Items

1. **Manual review required** - Don't bulk-remove without analysis
2. **Focus on obvious cases** - Test files importing unused modules
3. **Low priority** - Not affecting functionality or performance

### Examples to investigate:
```python
reveal/base.py:216 - registry
reveal/registry.py:20 - base
reveal/structure.py:215 - pathlib
```

---

## Circular Dependencies (16 found in omega-element session)

### Known Cycles

From `reveal 'imports://./reveal?circular'`:
- `base.py → registry.py → base.py`
- `base.py → registry.py → treesitter.py → base.py`
- `utils/__init__.py → utils/updates.py → utils/__init__.py`
- `type_system.py → elements.py → type_system.py`

### Impact

Not breaking functionality, but indicates architectural coupling.

### Recommendation

Consider dependency inversion or restructuring:
1. Extract shared interfaces to separate module
2. Use dependency injection where appropriate
3. Restructure `__init__.py` imports

**Priority:** Low (post-v1.0 refactoring candidate)

---

## Documentation File Permissions

### Issue

Inconsistent file permissions on documentation:
- Most files: `600` (owner-only read-write)
- Some files: `644` or `664` (group/world readable)

### Example

```bash
-rw------- reveal/AGENT_HELP.md
-rw-rw-r-- reveal/MARKDOWN_GUIDE.md  # Inconsistent
```

### Fixed

`MARKDOWN_GUIDE.md` permissions normalized to `600` in this session.

### Action

Verify all documentation files have consistent permissions before next release.

---

## Recommendations by Priority

### High Priority (v0.30.0)
- None (v0.29.0 is production-ready)

### Medium Priority (v0.31.0-v0.32.0)
1. Refactor `_render_help_adapter_specific` (complexity 55)
2. Refactor `render_reveal_structure` and `_render_config_structure` (complexity 42-43)
3. Review and clean up obvious unused imports

### Low Priority (Post-v1.0)
1. Address circular dependencies through architectural refactoring
2. Break down GDScript parser complexity
3. Extract edge case handlers in `get_syspath_analysis`

---

## Testing Strategy for Refactoring

When addressing these issues:

1. **Run full test suite** before and after each refactoring
   ```bash
   pytest -q  # Verify all 1,320 tests still pass
   ```

2. **Verify coverage doesn't drop** (currently 76%)
   ```bash
   pytest --cov=reveal --cov-report=term-missing
   ```

3. **Check complexity improvements**
   ```bash
   reveal 'ast://./reveal?complexity>40'  # Should decrease
   ```

4. **Dogfood the changes**
   ```bash
   reveal reveal/ --check  # Quality should improve or maintain
   ```

---

## References

- **Session:** xivebila-0103 (this session)
- **Related sessions:** omega-element-0103 (dogfooding), scarlet-twilight-0103 (duplicate detection docs)
- **Quality metrics:** `reveal stats://./reveal` - 96.8/100
- **Complexity analysis:** `reveal 'ast://./reveal?complexity>15'` - 158 functions
- **Import analysis:** `reveal 'imports://./reveal?unused'` - 86 imports
- **Circular deps:** `reveal 'imports://./reveal?circular'` - 16 cycles

---

**Next Action:** File tracking issues on GitHub for medium-priority refactorings

**Notes:**
- Don't refactor before major releases
- Each refactoring should be a separate PR with full test coverage
- Use reveal's own tools to validate improvements
