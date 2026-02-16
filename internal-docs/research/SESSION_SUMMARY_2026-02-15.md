# V005 Guide Auto-Discovery Implementation

**Session**: invincible-quarantine-0215  
**Date**: 2026-02-15  
**Badge**: V005: Guide auto-discovery  
**Status**: ✅ COMPLETE - All 40 V005 violations resolved  
**Commit**: cf6e935  

---

## Executive Summary

Successfully implemented hybrid auto-discovery for Reveal guide files, resolving all 40 V005 violations and making 20 previously unregistered guides discoverable via `help://` URIs. The solution combines automatic file discovery with manual registration, providing both convenience and flexibility.

**Impact**: All guide files now automatically discoverable by users and agents, eliminating manual registration burden and preventing future discoverability issues.

---

## Problem Analysis

### Discovery
Found during dogfooding exercise in session `ascending-observatory-0215`:
- **40 V005 violations** (20 unique guides, reported twice each)
- **29 total guide files** in `reveal/docs/`
- **9 registered** in `STATIC_HELP`
- **20 unregistered** and undiscoverable

### Root Cause
Manual registration in `STATIC_HELP` dictionary was error-prone:
1. Developer creates new adapter → writes guide → forgets to register
2. Guide exists but invisible to users via `help://` 
3. No enforcement until running `reveal reveal:// --check`

### Unregistered Guides
```
AST_ADAPTER_GUIDE.md        CLAUDE_ADAPTER_GUIDE.md
CLI_INTEGRATION_GUIDE.md    DEMO_ADAPTER_GUIDE.md
DIFF_ADAPTER_GUIDE.md       DOMAIN_ADAPTER_GUIDE.md
ELEMENT_DISCOVERY_GUIDE.md  ELIXIR_ANALYZER_GUIDE.md
ENV_ADAPTER_GUIDE.md        FIELD_SELECTION_GUIDE.md
GIT_ADAPTER_GUIDE.md        IMPORTS_ADAPTER_GUIDE.md
JSON_ADAPTER_GUIDE.md       MYSQL_ADAPTER_GUIDE.md
QUERY_SYNTAX_GUIDE.md       SQLITE_ADAPTER_GUIDE.md
SSL_ADAPTER_GUIDE.md        STATS_ADAPTER_GUIDE.md
TEST_ADAPTER_GUIDE.md       XLSX_ADAPTER_GUIDE.md
```

---

## Solution Design

### Options Evaluated

1. **Manual Registration** ❌ - Quick fix but recurring problem
2. **Full Auto-Discovery** ❌ - Zero maintenance but lose aliases
3. **Hybrid Auto-Discovery** ✅ - **CHOSEN** (best of both worlds)
4. **Convention-Based** ❌ - Inflexible for general guides
5. **Disable Reverse Check** ❌ - Wrong solution (hides problem)

### Hybrid Auto-Discovery (Selected)

**Approach**:
- Auto-discover `*_GUIDE.md` files at runtime
- Keep `STATIC_HELP` for aliases and special cases
- Merge: `{**discovered, **STATIC_HELP}` (manual takes precedence)

**Benefits**:
✅ Solves immediate problem (all guides discoverable)  
✅ Prevents recurrence (new guides auto-discovered)  
✅ Maintains flexibility (aliases still work)  
✅ Backward compatible (existing URIs work)  
✅ Low maintenance (only update STATIC_HELP for special cases)  

---

## Implementation

### 1. HelpAdapter Changes

**File**: `reveal/adapters/help.py`

**Added**:
```python
def __init__(self, topic: Optional[str] = None):
    self.topic = topic
    # Merge auto-discovered guides with manual STATIC_HELP entries
    self.help_topics = self._discover_and_merge_guides()

def _discover_and_merge_guides(self) -> Dict[str, str]:
    """Auto-discover guide files and merge with STATIC_HELP."""
    discovered = {}
    docs_dir = Path(__file__).parent.parent / 'docs'
    
    if docs_dir.exists():
        # Auto-discover *_GUIDE.md files
        for guide in docs_dir.glob('*_GUIDE.md'):
            # AST_ADAPTER_GUIDE.md -> ast-adapter
            topic = guide.stem.lower().replace('_guide', '').replace('_', '-')
            discovered[topic] = guide.name
    
    # STATIC_HELP takes precedence (allows aliases)
    return {**discovered, **self.STATIC_HELP}
```

**Updated References**:
- `self.STATIC_HELP` → `self.help_topics` (4 locations)
- `get_structure()`, `get_element()`, `_load_static_help()`, `_list_topics()`

### 2. V005 Rule Changes

**File**: `reveal/rules/validation/V005.py`

**Updated**: `_check_unregistered_guides()` method
- Added recognition of auto-discovery patterns
- Files matching `*_GUIDE.md` no longer flagged
- Updated docstring noting auto-discovery as of v0.50.0+

**Key Change**:
```python
# Check if this file matches auto-discovery pattern
if guide_file.name.endswith('_GUIDE.md') or guide_file.name.endswith('GUIDE.md'):
    # This guide is auto-discovered, no violation
    continue
```

### 3. Test Updates

**File**: `tests/test_V005_extended.py`

**Updated**:
- `test_unregistered_guide_detected` - now expects 0 detections (correct behavior)
- Added `test_auto_discovered_guides_not_flagged` - validates auto-discovery

**Test Coverage**: 19 tests, all passing

---

## Verification

### V005 Violations

**Before**: 40 violations (20 unique guides)  
**After**: 0 violations ✅

```bash
$ reveal reveal:// --check
reveal://: ✅ No issues found
```

### Guide Accessibility

**Total Static Guides**: 44 (previously 24)

**Newly Accessible** (20 guides):
```
✓ ast-adapter       ✓ claude-adapter    ✓ cli-integration
✓ demo-adapter      ✓ diff-adapter      ✓ domain-adapter
✓ element-discovery ✓ elixir-analyzer   ✓ env-adapter
✓ field-selection   ✓ git-adapter       ✓ imports-adapter
✓ json-adapter      ✓ mysql-adapter     ✓ query-syntax
✓ sqlite-adapter    ✓ ssl-adapter       ✓ stats-adapter
✓ test-adapter      ✓ xlsx-adapter
```

**Aliases Still Work**:
```
✓ help://python     (alias for python-adapter)
✓ help://tricks     (alias for recipes)
✓ help://agent      (special case)
```

### Test Suite

**Result**: All 4244 tests passing ✅

```bash
$ pytest tests/ -x
======================= 4244 passed in 112.09s =======================
```

**Specific Test Results**:
- `tests/test_adapters.py::TestHelpAdapter` - 5/5 passing
- `tests/test_V005_extended.py` - 19/19 passing

---

## Technical Details

### Auto-Discovery Pattern

**Filename**: `*_GUIDE.md`  
**Topic Name**: Lowercase, underscores → hyphens, strip `_guide` suffix

**Examples**:
```
AST_ADAPTER_GUIDE.md     → ast-adapter
GIT_ADAPTER_GUIDE.md     → git-adapter
QUERY_SYNTAX_GUIDE.md    → query-syntax
ELEMENT_DISCOVERY_GUIDE.md → element-discovery
```

### Merge Strategy

```python
{**discovered, **STATIC_HELP}
```

**Precedence**: `STATIC_HELP` takes priority
- Allows aliases: `'python': 'PYTHON_ADAPTER_GUIDE.md'`
- Overrides auto-names: `'tricks': 'RECIPES.md'`
- Special cases: `'agent': 'AGENT_HELP.md'`

### Backward Compatibility

✅ **No Breaking Changes**:
- Existing `help://` URIs work unchanged
- `STATIC_HELP` entries preserved
- Aliases function identically
- API contract maintained

---

## Impact Analysis

### User Benefits

1. **Immediate**: All guides now discoverable
2. **Discoverability**: Users can find help via `help://adapter-name`
3. **Consistency**: All adapters have same help access pattern
4. **Documentation**: Better user experience exploring features

### Developer Benefits

1. **Zero Registration**: Create `*_GUIDE.md`, automatically available
2. **Error Prevention**: Can't forget to register (auto-discovered)
3. **Maintainability**: No manual `STATIC_HELP` updates needed
4. **Flexibility**: Can still add aliases when needed

### Maintenance Benefits

1. **Self-Healing**: New guides automatically integrated
2. **No Tech Debt**: Problem solved permanently
3. **Quality Enforcement**: V005 rule still validates file existence
4. **Documentation Sync**: Guides and access stay synchronized

---

## Statistics

### Code Changes

```
reveal/adapters/help.py      | +58 -7   (50 net lines)
reveal/rules/validation/V005.py | +29 -6   (23 net lines)
tests/test_V005_extended.py  | +57 -7   (50 net lines)
```

**Total**: +144 -20 (123 net lines)

### Files Changed

- **Created**: 0
- **Modified**: 3
- **Deleted**: 0

### Tests

- **Added**: 1 new test (auto-discovery validation)
- **Updated**: 1 test (new expected behavior)
- **Passing**: 4244/4244 (100%)

---

## Session Metrics

**Duration**: ~2 hours  
**Mode**: Adult (autonomous execution)  
**Efficiency**: High (focused, systematic)

**Workflow**:
1. Research (30 min): Analyzed problem, read code, evaluated options
2. Implementation (45 min): Updated HelpAdapter, V005 rule, tests
3. Validation (30 min): Tested guides, ran test suite, verified fix
4. Documentation (15 min): Commit message, session summary

---

## Patterns & Lessons

### What Worked Well

1. **Hybrid Approach**: Combined auto-discovery with manual control
2. **Backward Compatibility**: No breaking changes, smooth transition
3. **Test-Driven Validation**: Updated tests before verifying fix
4. **Comprehensive Testing**: Verified guides, aliases, edge cases
5. **Thorough Investigation**: Evaluated multiple solutions before implementing

### Key Success Factors

- **Clear Problem Definition**: Understood root cause (manual registration)
- **Solution Evaluation**: Compared 5 options, chose best fit
- **Implementation Focus**: Changed only what was necessary
- **Comprehensive Testing**: Verified all 20 guides + aliases + test suite
- **Documentation**: Clear commit message and session summary

### Lessons for Future

1. **Dogfooding Value**: Self-analysis finds real bugs (V005 discovered this way)
2. **Auto-Discovery Patterns**: Reduces maintenance burden significantly
3. **Hybrid Solutions**: Often better than pure approaches
4. **Test Updates**: Remember to update tests for new behavior
5. **Backward Compatibility**: Critical for production systems

---

## Follow-Up Opportunities

### Potential Enhancements

1. **Auto-Aliases**: Generate common aliases automatically (e.g., `ast` → `ast-adapter`)
2. **Guide Templates**: Standardize guide structure for consistency
3. **Coverage Validation**: Ensure all adapters have guides (new rule?)
4. **Multi-Pattern Discovery**: Support additional help file patterns
5. **Version Tracking**: Track when guides were last updated

### Related Work

- **V005 Rule Enhancement**: Could check guide completeness/quality
- **Help System Documentation**: Update HELP_SYSTEM_GUIDE.md with auto-discovery
- **Developer Guide**: Document guide creation best practices
- **CI/CD Integration**: Validate guides in pre-commit hooks

---

## Related Sessions

**Immediate Context**:
- `ascending-observatory-0215`: Phase 10 test coverage + dogfooding (discovered issue)

**V005 History**:
- `valley-whirlwind-0215`: Phase 8 (V005 rule improvements to 96% coverage)

---

## Conclusion

Successfully implemented hybrid auto-discovery for Reveal guide files, resolving all 40 V005 violations and making 20 previously unregistered guides discoverable. The solution balances automatic convenience with manual control, providing a maintainable foundation that prevents future registration issues.

**Key Achievement**: Zero manual registration required for standard guides, while preserving flexibility for aliases and special cases.

**Proof of Success**:
- ✅ 0 V005 violations (down from 40)
- ✅ 20/20 guides now discoverable
- ✅ 4244/4244 tests passing
- ✅ Backward compatible (aliases work)
- ✅ Future-proof (auto-discovery ongoing)

---

**Session**: invincible-quarantine-0215  
**Status**: ✅ COMPLETE  
**Commit**: cf6e935  
**Next Session**: TBD (options: Phase 11 test coverage, new features, different project)
