---
date: 2026-02-12
session: neon-light-0212
type: mypy-cleanup-strategy
status: ready-to-execute
---

# MyPy Cleanup Strategy - 66 Remaining Errors

**Current**: 66 errors in 32 files
**Goal**: 0 errors (or close to it)
**Approach**: Bulk fixes by pattern category

---

## Error Distribution by File

**High-Impact Files** (20% of files, 40% of errors):
```
6 errors: cli/introspection.py
5 errors: analyzers/html.py
5 errors: adapters/ssl/certificate.py
5 errors: adapters/mysql/adapter.py
```

**Medium-Impact Files** (3 errors each):
```
3 errors: rules/duplicates/_base_detector.py
3 errors: adapters/reveal.py
3 errors: adapters/imports.py
3 errors: adapters/domain/dns.py
```

**Long-tail** (24 files with 1-2 errors each)

---

## Pattern Categories (Bulk Fix Order)

### 🟢 Category 1: Missing Type Annotations (8 errors) - EASIEST

**Pattern**: `Need type annotation for "X" (hint: "X: List[<type>] = ...")`

**Files**:
- reveal/adapters/reveal.py: analyzers, rules, by_category
- reveal/adapters/imports.py: imports, files
- reveal/adapters/domain/dns.py: current_path
- reveal/cli/introspection.py: by_file

**Bulk Fix Strategy**:
```python
# Before
analyzers = []

# After
analyzers: list[dict[str, Any]] = []
```

**Estimated Time**: 15 minutes (8 fixes)
**Risk**: LOW (just adds type hints)

---

### 🟢 Category 2: Method Redefinitions (5 errors) - EASY

**Pattern**: `Name "_get_X" already defined on line Y`

**File**: reveal/adapters/mysql/adapter.py (all 5 errors)

**Issue**: Duplicate method definitions
- _get_performance (lines 262, 632)
- _get_innodb (lines 266, 704)
- _get_replication (lines 270, 738)
- _get_storage (lines 274, 767)
- _get_database_storage (lines 278, 787)

**Bulk Fix Strategy**: Remove or rename duplicates

**Estimated Time**: 10 minutes
**Risk**: LOW (but check if both versions are used)

---

### 🟡 Category 3: None Checks (7 errors) - MEDIUM

**Pattern**: `Item "None" of "X | None" has no attribute "Y"`

**Files**:
- adapters/domain/dns.py: `.is_dir()`
- adapters/ssl/certificate.py: `.getinfo()`
- Multiple argument type issues

**Bulk Fix Strategy**:
```python
# Before
if path:
    path.is_dir()  # Error: None has no is_dir

# After
if path is not None:
    path.is_dir()  # OK
```

**Estimated Time**: 20 minutes
**Risk**: LOW (defensive programming)

---

### 🟡 Category 4: Union Type Attribute Access (5 errors) - MEDIUM

**Pattern**: `Item "type" of "type | Any | str" has no attribute "lower"`

**Files**: Various

**Bulk Fix Strategy**:
```python
# Before
value.lower()  # value might be type or str

# After
if isinstance(value, str):
    value.lower()
```

**Estimated Time**: 15 minutes
**Risk**: LOW (adds runtime checks)

---

### 🟠 Category 5: Incompatible Assignment (10 errors) - HARDER

**Pattern**: `Incompatible types in assignment (expression has type "X", target has type "Y")`

**Examples**:
- `str` → `bool`
- `dict[str, Any]` → `str`
- `None` → `str`

**Files**: Scattered across codebase

**Strategy**: Case-by-case fixes
- Some are Optional[] missing
- Some are wrong types entirely
- Some need assertion or cast

**Estimated Time**: 30 minutes
**Risk**: MEDIUM (need to understand intent)

---

### 🟠 Category 6: Argument Type Mismatches (15 errors) - HARDER

**Pattern**: `Argument N to "func" has incompatible type "X"; expected "Y"`

**Examples**:
- `str | None` → `str` (needs None check)
- `FunctionDef | AsyncFunctionDef` → `FunctionDef` (union too broad)
- `dict[Any, Any] | None` → `dict[str, Any]` (needs None check + cast)

**Strategy**:
1. Add None checks where needed
2. Use type guards for unions
3. Add casts where type is known but mypy can't infer

**Estimated Time**: 45 minutes
**Risk**: MEDIUM (need context)

---

### 🔴 Category 7: Return Type Mismatches (5 errors) - HARDEST

**Pattern**: `Incompatible return value type (got "X", expected "Y")`

**Examples**:
- `tuple[str, str | None]` → `tuple[str, str] | None`
- `dict[str, int]` → `dict[str, float]`
- `T | None` → `T`

**Strategy**: Fix function signatures or implementation

**Estimated Time**: 20 minutes
**Risk**: MEDIUM (might affect callers)

---

### 🔴 Category 8: Miscellaneous (11 errors) - CASE-BY-CASE

**Includes**:
- Dict entry type mismatches (3 errors)
- Import issues (tomllib, mccabe) (2 errors)
- "Cannot assign to a type" (1 error)
- DNS Rdata attributes (2 errors)
- Override signature mismatches (2 errors)
- Iterable issues (1 error)

**Strategy**: Individual fixes based on context

**Estimated Time**: 40 minutes
**Risk**: VARIES

---

## Execution Plan

### Phase 1: Quick Wins (30 minutes, ~20 errors)

1. ✅ **Missing type annotations** (8 errors, 15 min)
   - Easiest bulk fix
   - Zero risk

2. ✅ **Method redefinitions** (5 errors, 10 min)
   - MySQL adapter cleanup
   - Check if duplicates are needed

3. ✅ **None checks** (7 errors, 20 min)
   - Add defensive checks
   - Standard pattern

**Expected**: 66 → ~46 errors

---

### Phase 2: Pattern Fixes (45 minutes, ~20 errors)

4. ✅ **Union type attribute access** (5 errors, 15 min)
   - Add isinstance checks

5. ✅ **Incompatible assignments** (10 errors, 30 min)
   - Case-by-case analysis
   - Fix type annotations or logic

**Expected**: 46 → ~26 errors

---

### Phase 3: Deeper Issues (60 minutes, ~20 errors)

6. ✅ **Argument type mismatches** (15 errors, 45 min)
   - Add type guards
   - Narrow union types

7. ✅ **Return type mismatches** (5 errors, 20 min)
   - Fix signatures

**Expected**: 26 → ~6 errors

---

### Phase 4: Cleanup (30 minutes, ~6 errors)

8. ✅ **Miscellaneous** (11 errors, 40 min)
   - Individual fixes
   - Document any suppressions

**Expected**: 6 → 0-2 errors

---

## Total Estimated Time

- **Phase 1**: 30 minutes (quick wins)
- **Phase 2**: 45 minutes (patterns)
- **Phase 3**: 60 minutes (deeper)
- **Phase 4**: 30 minutes (cleanup)

**Total**: ~2.5 hours for complete mypy cleanup

---

## Bulk Fix Patterns

### Pattern A: Missing List Annotation
```python
# Search: ^(\s+)(\w+) = \[\]$
# Context: Check if mypy complains
# Fix: Add type hint

# Before
items = []

# After
items: list[dict[str, Any]] = []
```

### Pattern B: Missing Dict Annotation
```python
# Before
cache = {}

# After
cache: dict[str, Any] = {}
```

### Pattern C: None Check Before Attribute Access
```python
# Before
def process(path: Path | None) -> bool:
    return path.is_dir()  # Error!

# After
def process(path: Path | None) -> bool:
    return path.is_dir() if path is not None else False
```

### Pattern D: Union Type Guard
```python
# Before
def lower(value: str | type) -> str:
    return value.lower()  # Error!

# After
def lower(value: str | type) -> str:
    if isinstance(value, str):
        return value.lower()
    return str(value).lower()
```

### Pattern E: Optional to Required
```python
# Before
def process(data: dict[str, Any] | None):
    keys = data.keys()  # Error!

# After
def process(data: dict[str, Any] | None):
    if data is None:
        return
    keys = data.keys()  # OK
```

---

## Risk Mitigation

### Test After Each Phase
```bash
# Run tests to ensure no regressions
pytest tests/ -x --tb=short

# Check mypy progress
mypy reveal 2>&1 | tail -1
```

### Commit Strategy

**Commit after each phase**:
```bash
git add -A
git commit -m "fix(types): Phase N - Category (X → Y errors)"

# Example:
git commit -m "fix(types): Phase 1 - Missing annotations (66 → 46 errors)"
```

### Rollback Plan

If a phase breaks tests:
```bash
git reset --hard HEAD~1  # Rollback last commit
# Fix specific issue
# Re-run phase
```

---

## Success Metrics

| Metric | Start | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|--------|-------|---------|---------|---------|---------|
| Errors | 66 | ~46 | ~26 | ~6 | 0-2 |
| % Complete | 0% | 30% | 61% | 91% | 97%+ |
| Risk | - | LOW | LOW | MED | MED |

---

## Expected Outcome

**Best Case**: 0 mypy errors (100% type safe)
**Realistic**: 0-5 errors (95%+ type safe, remaining might need suppressions)
**Worst Case**: 10-15 errors (issues needing architecture changes)

**Confidence**: HIGH - Most errors are straightforward fixes

---

## Next Steps

1. Review this strategy
2. Start Phase 1 (quick wins)
3. Run tests after each file
4. Commit after each phase
5. Iterate until complete

**Ready to execute?**
