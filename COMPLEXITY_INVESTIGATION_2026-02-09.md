# Complexity Calculation Investigation

**Date**: 2026-02-09
**Session**: xodayepo-0209
**Investigator**: TIA (continuation from mijecoga-0209)

## Executive Summary

Investigated reported complexity calculation discrepancy where `_has_noqa_comment` function reported complexity 32 vs actual McCabe complexity of 6 (5.3x inflation). Found and partially fixed systematic over-reporting bug affecting ALL functions with boolean logic.

**Status**: 🟡 Partial fix applied, deeper investigation needed
**Impact**: Medium-High (affects all complexity metrics across codebase)
**Root Cause**: Tree-sitter complexity calculation differs significantly from standard McCabe

---

## The Problem

Previous session (mijecoga-0209) noted: `_has_noqa_comment` reports complexity 32 but manual calculation suggests ~13. Investigation reveals the true McCabe complexity is even lower: **6**.

### Comparative Analysis

Tested across multiple functions in `reveal/rules/imports/I001.py`:

| Function | McCabe (Correct) | Reveal (Original) | Inflation | Status |
|----------|------------------|-------------------|-----------|---------|
| `_has_noqa_comment` | **6** | **32** → 25 | 5.3x → 4.2x | 🟡 Improved |
| `_check_from_import` | 4 | 12 | 3.0x | ⚠️ |
| `_check_regular_import` | 3 | 11 | 3.7x | ⚠️ |
| `_should_skip_import` | 4 | 7 | 1.8x | ⚠️ |
| `check` | 9 | 14 | 1.6x | ⚠️ |

**Pattern**: Reveal consistently over-reports complexity by 2-5x compared to authoritative McCabe implementation (used by flake8, pylint).

---

## Bugs Found & Fixes Applied

### Bug #1: Double-Counting Boolean Operators ✅ FIXED

**Location**: `reveal/treesitter.py:688-693`

**The Problem**:
```python
# Line 685-686: Count boolean_operator nodes
if child.type in decision_types:  # decision_types includes 'boolean_operator'
    count += 1

# Line 690-693: Count AGAIN if it contains 'and'/'or'
if child.type in ('binary_operator', 'boolean_operator'):
    text = self._get_node_text(child)
    if text and any(op in text for op in [' and ', ' or ', '&&', '||']):
        count += 1  # ❌ DOUBLE COUNT!
```

**The Fix**: Removed lines 688-693 entirely. Boolean operators already counted at line 686.

**Impact**: Reduced some over-reporting but didn't solve the full issue.

---

### Bug #2: Over-Broad Binary Operator Matching ✅ FIXED

**Location**: `reveal/treesitter.py:665`

**The Problem**:
```python
decision_types = {
    # ...
    'boolean_operator', 'binary_operator',  # ❌ 'binary_operator' is TOO BROAD
    # ...
}
```

`'binary_operator'` includes:
- ✅ Boolean operators: `and`, `or` (ARE decision points)
- ❌ Comparison operators: `in`, `==`, `!=`, `>`, `<` (NOT decision points)
- ❌ Arithmetic operators: `+`, `-`, `*`, `/` (NOT decision points)
- ❌ Bitwise operators: `&`, `|`, `^` (NOT decision points)

**The Fix**: Removed `'binary_operator'` from decision_types, keeping only:
- `'boolean_operator'` (generic)
- `'and'`, `'or'` (Python-specific)
- `'logical_and'`, `'logical_or'` (C-family)

**Impact**: Should reduce over-counting of comparison-heavy code.

---

### Bug #3: Tree-Sitter Nested Boolean Nodes 🟡 NEEDS INVESTIGATION

**Status**: Hypothesis, not yet confirmed

After applying both fixes, `_has_noqa_comment` still reports complexity 25 (should be 6).

**Hypothesis**: Tree-sitter may create nested `boolean_operator` nodes for chained operations:

```python
# Code: A or B or C
# Possible tree-sitter structure:
boolean_operator            # Count: +1
├─ A
├─ or
└─ boolean_operator         # Count: +1 (nested!)
   ├─ B
   ├─ or
   └─ C
```

If tree-sitter nests these, recursive counting would count both the outer and inner nodes.

**Evidence**:
- In `_has_noqa_comment`, there are 4 `or` operators and 3 `and` operators
- If each creates nested nodes, that could explain the excess counts
- Line 59 alone has 2 chained `or` operators: `':' not in line_lower or 'f401' in line_lower or 'i001' in line_lower`

**Next Steps**:
1. Examine actual tree-sitter AST for `_has_noqa_comment` to confirm nesting hypothesis
2. If confirmed, modify counting logic to skip nested boolean_operator nodes
3. Alternative: Only count leaf boolean operators, or count based on operator keywords not nodes

---

## Test Function: _has_noqa_comment

For reference, here's the function being analyzed:

```python
def _has_noqa_comment(self, source_line: str) -> bool:
    """Check if source line has a suppression comment."""
    if not source_line:                              # Decision point 1: if
        return False

    line_lower = source_line.lower()

    # Python: # noqa
    if '# noqa' in line_lower:                       # Decision point 2: if
        # Generic noqa (no colon) or specific F401/I001
        return ':' not in line_lower or 'f401' in line_lower or 'i001' in line_lower  # DP 3-4: or, or

    # JavaScript: // eslint-disable
    if '// eslint-disable' in line_lower and ('no-unused-vars' in line_lower or 'unused' in line_lower):  # DP 5-7: if, and, or
        return True

    # Go: // nolint
    if '// nolint' in line_lower and ('unused' in line_lower or ':' not in line_lower):  # DP 8-10: if, and, or
        return True

    # Rust: #[allow(unused)]
    if '#[allow' in line_lower and 'unused' in line_lower:  # DP 11-12: if, and
        return True

    return False
```

**Manual Count**:
- `if` statements: 5
- `or` operators: 4
- `and` operators: 3
- **Total**: 12 decision points + 1 = **13 complexity** (manual tree-sitter logic)
- **McCabe**: **6** (authoritative)
- **Reveal reports**: **25** (after fixes)

**Discrepancy**: Still ~4x too high after fixes.

---

## Consolidation Opportunities Found

### Opportunity #1: Imports Adapter _format_* Methods

**Location**: `reveal/adapters/imports.py`

**Pattern**: Four format methods share identical structure:

1. `_format_all()` (lines 519-537, 19 lines)
2. `_format_unused()` (lines 539-554, 16 lines)
3. `_format_circular()` (lines 556-574, 19 lines)
4. `_format_violations()` (lines 576-591, 16 lines)

**Common Structure** (repeated 4 times):
```python
return {
    'contract_version': '1.0',
    'type': '<type_name>',
    'source': str(self._target_path),
    'source_type': 'directory' if self._target_path.is_dir() else 'file',
    '<data_field>': <data>,
    'count': <count>,  # sometimes
    'metadata': self.get_metadata()
}
```

**Consolidation Plan**:
Extract common structure into helper method:

```python
def _build_response(self, response_type: str, data_field: str, data: Any, count: int = None) -> Dict[str, Any]:
    """Build standardized adapter response."""
    response = {
        'contract_version': '1.0',
        'type': response_type,
        'source': str(self._target_path),
        'source_type': 'directory' if self._target_path.is_dir() else 'file',
        data_field: data,
        'metadata': self.get_metadata()
    }
    if count is not None:
        response['count'] = count
    return response

def _format_all(self) -> Dict[str, Any]:
    if not self._graph:
        return {'imports': []}
    imports_by_file = {
        str(path): [self._format_import(stmt) for stmt in imports]
        for path, imports in self._graph.files.items()
    }
    return self._build_response('imports', 'files', imports_by_file)

# Similar simplification for _format_unused, _format_circular, _format_violations
```

**Impact**:
- Lines reduced: ~70 → ~30 (57% reduction)
- Duplication eliminated: 4 copies of structure → 1 implementation
- Maintenance: Changes to response format only need 1 update

**Effort**: Low (30 minutes)
**Risk**: Low (tests validate behavior)

---

## Recommendations

### Immediate (This Session)

1. ✅ **Document findings** (this document)
2. ⚠️ **Keep complexity fixes** but mark as experimental
3. 🔄 **Run full test suite** to verify no regressions
4. 📝 **Create GitHub issue** for deeper tree-sitter investigation

### Short Term (Next Session)

1. **Investigate tree-sitter AST structure**:
   - Add debug logging to see actual nodes created
   - Test hypothesis about nested boolean_operator nodes
   - Consider using `mccabe` library directly instead of tree-sitter calculation

2. **Implement imports adapter consolidation**:
   - Extract `_build_response()` helper
   - Refactor four `_format_*` methods
   - Run tests to verify behavior unchanged

### Long Term

1. **Consider switching to mccabe library**:
   - It's the authoritative implementation
   - Used by flake8, pylint (industry standard)
   - Current tree-sitter approach has fundamental issues

2. **Document trade-offs**:
   - Tree-sitter: Cross-language support
   - mccabe: Python-only but accurate
   - Potential: Use mccabe for Python, tree-sitter for other languages

---

## Impact Assessment

### Current State

- **Quality Score Impact**: Complexity metrics are unreliable
- **Developer Experience**: Functions flagged as "complex" may be simpler than reported
- **False Positives**: Functions with many comparisons over-counted
- **Trust**: Metrics don't match industry-standard tools

### After Full Fix

- **Accuracy**: Complexity matches McCabe standard
- **Reliability**: Developers can trust the metrics
- **Prioritization**: Focus refactoring on truly complex code
- **Industry Standard**: Align with flake8/pylint expectations

---

## Files Modified

1. `reveal/treesitter.py`:
   - Removed lines 688-693 (double-counting fix)
   - Removed `'binary_operator'` from decision_types (line 665)

2. *(This document created)*:
   - `COMPLEXITY_INVESTIGATION_2026-02-09.md`

---

## Test Results

**Status**: Tests need to be run after fixes

**Command**: `pytest tests/ -xvs`

**Expected**: All tests should pass (fixes only reduce over-counting, shouldn't break functionality)

---

## References

- **McCabe Complexity**: Standard cyclomatic complexity metric
- **mccabe library**: Python implementation used by flake8, pylint
- **Tree-sitter**: Multi-language parser used by Reveal
- **Previous session**: mijecoga-0209 (code duplication consolidation)

---

## Conclusion

Identified systematic over-reporting in Reveal's complexity calculation caused by:
1. ✅ Double-counting boolean operators (fixed)
2. ✅ Counting non-decision binary operators (fixed)
3. 🟡 Possible nested tree-sitter nodes (needs investigation)

Partial fix applied reduces inflation but doesn't solve it completely. Full resolution requires deeper investigation into tree-sitter AST structure or switching to mccabe library for Python code.

Additionally found consolidation opportunity in imports adapter `_format_*` methods that can reduce duplication by 57%.

**Recommendation**: Keep fixes, mark as experimental, investigate deeper before considering complete solution (mccabe library adoption or tree-sitter node filtering).
