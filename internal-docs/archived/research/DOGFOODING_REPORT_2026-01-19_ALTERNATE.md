# Reveal Dogfooding Report - 2026-01-19

**Session**: psychic-shark-0119
**Methodology**: Systematic validation starting from `reveal://help`, testing all features, reviewing docs
**Version**: 0.39.0 (unreleased)

---

## Executive Summary

**Overall Health**: Mixed - core features work well, but 3 adapters broken + documentation drift

### Critical Issues (Blocking Release)
1. **claude:// adapter completely broken** - "No renderer registered for scheme 'claude'"
2. **diff:// adapter crashes** - Traceback on any query
3. **sqlite:// works** but error handling poor (traceback on file not found)

### High-Priority Issues
4. **Extraction syntax undocumented** - `:LINE` and `@N` work but not in user-facing docs
5. **Internal-docs README stale** - Documents 20 files, 34 exist (40% drift)
6. **4 redundant index docs** - README, DOCS_SUMMARY, DOC_NAVIGATION, DOCUMENTATION_HEALTH_REPORT

### Medium-Priority Issues
7. **TIA reference in code** - `schemas/frontmatter/__init__.py` has `'beth': 'session'` comment
8. **help:// counts outdated** - Shows "14 adapters" but only 11 actually work

---

## Adapter Validation Results

| Adapter | Status | Notes |
|---------|--------|-------|
| ast:// | ✅ Works | Excellent - complexity queries functional |
| claude:// | ❌ **BROKEN** | No renderer registered - full failure |
| diff:// | ❌ **CRASHES** | Traceback on any comparison |
| env:// | ✅ Works | Good - categories, redaction |
| git:// | ✅ Works | Good - generic fallback rendering |
| help:// | ✅ Works | Excellent - well organized |
| imports:// | ✅ Works | Good - circular detection |
| json:// | ✅ Works | Good - path navigation |
| markdown:// | ✅ Works | Good - query by frontmatter |
| mysql:// | ⚠️ Untested | No MySQL running (expected behavior) |
| python:// | ✅ Works | Excellent - doctor diagnostics |
| reveal:// | ✅ Works | Good - self-inspection |
| sqlite:// | ⚠️ Partial | Works but poor error handling |
| stats:// | ✅ Works | Good - hotspots functional |

**Summary**: 11/14 work, 2 broken, 1 partial

---

## Recommendations

### 1. Tests/Rules/Scanners Needed

**Add integration test for all adapters**:
```python
# tests/test_adapter_smoke.py
@pytest.mark.parametrize("scheme", ["ast", "env", "git", "help", ...])
def test_adapter_renders_without_error(scheme):
    """Every registered adapter should render without traceback."""
    # This would have caught claude:// and diff:// issues
```

**Add V-rule for renderer coverage**:
```
V020: Check all adapters have registered renderers
```

**Add CI smoke test**:
```bash
# Run basic query on each adapter in CI
reveal ast://. | head -5
reveal env:// | head -5
reveal git://. | head -5
# etc.
```

### 2. UX/UI Updates for Consistency

**Error message standardization**:
```
Current: "Error: No renderer registered for scheme 'claude'"
Better:  "Error: claude:// adapter unavailable (missing renderer)"
         "Hint: This adapter may be incomplete - see reveal help://claude"
```

**File not found handling**:
```
Current: Python traceback (FileNotFoundError)
Better:  "Error: Database not found: /path/to/file.db"
         "Hint: Use reveal sqlite:///path/to/existing.db"
```

**Help status indicators**:
```
Current: 🟢 Stable | 🟡 Beta | 🔴 Experimental
Add:     ⛔ Broken (for adapters that don't work at all)
```

### 3. Documentation Consolidation

**Archive these to `research/archived/`**:
- `DOCUMENTATION_HEALTH_REPORT.md` (one-time audit, extract action items)
- `DOGFOODING_REPORT_2026-01-15.md` (superseded by this report)
- `CLAUDE_ADAPTER_POSTMORTEM.md` (extract learnings, archive)

**Consolidate these**:
- Merge `DOCS_SUMMARY.md` + `DOC_NAVIGATION.md` → single navigation doc
- Update `README.md` to reflect actual 34 files, not 20

**Update README.md to document**:
- `case-studies/` directory
- `PRACTICAL_UTILITY_ANALYSIS.md`
- `REGEX_TO_TREESITTER_MIGRATION.md`
- `planning/EXTRACTION_IMPROVEMENTS.md`
- `research/OUTPUT_CONTRACT_ANALYSIS.md`
- All recent planning docs

### 4. Document the Extraction Syntaxes

Add to AGENT_HELP.md and QUICK_START.md:
```markdown
## Element Extraction

reveal file.py function_name     # By name
reveal file.py ':50'             # By line number (line 50)
reveal file.py ':50-60'          # By line range
reveal file.py '@3'              # 3rd element (ordinal)
reveal file.py 'class:2'         # 2nd class specifically
reveal file.py 'Class.method'    # Hierarchical (nested)
```

### 5. Fix TIA Reference

In `schemas/frontmatter/__init__.py`:
```python
# Change this:
'beth': 'session',  # beth renamed to session for open source

# To this:
'beth': 'session',  # Historical alias for session schema
```

---

## What's Working Well

1. **help:// system** - Excellent organization, token costs, navigation tips
2. **ast:// queries** - Powerful, well-documented, works as expected
3. **stats:// hotspots** - Useful quality analysis
4. **python://doctor** - Genuinely helpful diagnostics
5. **Progressive disclosure** - The core philosophy works
6. **--agent-help** - Good quick reference for AI agents

---

## Recommended Next Actions

### Before 0.39.0 Release
1. [ ] Fix claude:// renderer (or mark as experimental/broken in help)
2. [ ] Fix diff:// crash
3. [ ] Improve sqlite:// error handling

### Post-Release (0.40.0)
1. [ ] Add adapter smoke tests
2. [ ] Document extraction syntaxes
3. [ ] Consolidate internal-docs
4. [ ] Add V020 rule for renderer coverage

---

## Files Reviewed

- `reveal://help` (internal structure)
- `help://` (13 topics)
- `help://<adapter>` for all 14 adapters
- `internal-docs/README.md`
- `internal-docs/DOCS_SUMMARY.md`
- `internal-docs/DOC_NAVIGATION.md`
- `internal-docs/DOCUMENTATION_HEALTH_REPORT.md`
- `external-git/reveal/rendering/adapters/`
- `external-git/reveal/display/element.py`

**Session**: psychic-shark-0119
**Date**: 2026-01-19
