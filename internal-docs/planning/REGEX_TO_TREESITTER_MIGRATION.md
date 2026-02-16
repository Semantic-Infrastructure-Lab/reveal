---
title: Regex to Tree-Sitter Migration Plan
date: 2026-01-14
status: in-progress
priority: high
beth_topics: [reveal, tree-sitter, code-quality, technical-debt, refactoring]
---

# Regex to Tree-Sitter Migration Plan

**Status**: Phase 1 Complete (1/8 migrations done)
**Next**: Phase 2 - Migrate remaining 6 analyzers + import analyzers

## Executive Summary

Comprehensive audit of Reveal's codebase found **166 regex usages across 86 files**. Analysis shows **30-35% (50-58 uses) should migrate to tree-sitter** for robust AST-based code parsing instead of fragile regex.

**Impact of full migration:**
- **Lines saved**: 200-300+ lines of maintenance code
- **Bugs fixed**: 4-5 known parsing edge cases
- **Maintainability**: Significant improvement (regex → declarative)
- **Architecture**: Consistent tree-sitter usage across all code parsers

---

## Phase 1: Critical Migration ✅ COMPLETE

### Completed (2026-01-14)

#### 1. V021 Validation Rule ✅
- **Created**: `rules/validation/V021.py` (+281 lines)
- **Purpose**: Detect inappropriate regex usage when tree-sitter is available
- **Detects**: 7 files that should migrate (dockerfile, toml, yaml_json, 4x import analyzers)
- **Severity**: HIGH
- **Benefits**:
  - Prevents future regex proliferation
  - Provides migration guidance automatically
  - Estimates effort per file (small/medium/large)
  - Self-documenting codebase architecture

#### 2. GDScript Analyzer Migration ✅
- **File**: `analyzers/gdscript.py`
- **Before**: 197 lines of regex parsing (4 patterns: CLASS, FUNC, SIGNAL, VAR)
- **After**: 21 lines using TreeSitterAnalyzer (15 lines actual code, 6 docstring)
- **Reduction**: -176 lines (-89%)
- **Testing**: Verified with `/tmp/test_gdscript.gd` - functions, classes, signatures extracted correctly
- **Known edge cases fixed**:
  - Nested classes now work correctly
  - Comments inside code blocks don't break parsing
  - Multi-line constructs handled properly
  - Complex signatures with return types work

#### 3. Documentation Updates ✅
- **README.md**: Updated rule count (55 → 56), added V021 to unreleased list
- **This file**: Created comprehensive migration plan

---

## Phase 2: High-Priority Analyzers

**Target**: 6 remaining analyzers flagged by V021
**Estimated effort**: 3-6 hours total
**Estimated savings**: ~500 lines of code

### Files to Migrate

| File | Current Lines | Regex Ops | Effort | Priority | Savings |
|------|--------------|-----------|--------|----------|---------|
| `analyzers/dockerfile.py` | 181 | 1 | Small (30min) | HIGH | ~160 lines |
| `analyzers/toml.py` | 113 | 4 | Medium (1h) | HIGH | ~90 lines |
| `analyzers/yaml_json.py` | 113 | 4 | Medium (1h) | HIGH | ~90 lines |
| `analyzers/imports/go.py` | 171 | 2 | Small (30min) | MEDIUM | ~155 lines |
| `analyzers/imports/rust.py` | 214 | 2 | Small (30min) | MEDIUM | ~200 lines |
| `analyzers/imports/javascript.py` | 270 | 5 | Medium (1.5h) | MEDIUM | ~250 lines |
| `analyzers/imports/python.py` | 410 | 2 | Small (30min)* | LOW | ~390 lines* |

*Note: python.py already uses tree-sitter for main parsing; regex is for legacy string extraction. May be removable.

### Migration Pattern (All Files)

Each migration follows the same simple pattern:

```python
# Before (100-400 lines)
import re
from ..base import FileAnalyzer

class FooAnalyzer(FileAnalyzer):
    PATTERN_1 = re.compile(r'...')
    PATTERN_2 = re.compile(r'...')
    # 50-300 lines of regex parsing logic

# After (10-20 lines)
from ..treesitter import TreeSitterAnalyzer

@register('.foo', name='Foo', icon='')
class FooAnalyzer(TreeSitterAnalyzer):
    language = 'foo'  # That's it! Tree-sitter handles everything
```

### Expected Results

**After Phase 2:**
- 7 files migrated (GDScript + 6 remaining)
- ~1,500 lines of regex code removed
- ~140 lines of tree-sitter code added
- Net: -1,360 lines (-90% reduction)
- All V021 detections resolved
- Consistent architecture across all analyzers

---

## Phase 3: Import Analyzer Deep Review

**Target**: Understand why import analyzers use regex despite main analyzers using tree-sitter
**Estimated effort**: 2-3 hours analysis + 2-4 hours refactoring

### Questions to Answer

1. **Why separate import analyzers?**
   - Main analyzers (python.py, go.py, etc.) are 13 lines using tree-sitter
   - Import analyzers (analyzers/imports/*.py) are 171-410 lines using regex
   - Are import analyzers doing specialized analysis beyond structure extraction?

2. **Can import analysis use tree-sitter?**
   - Tree-sitter already extracts `imports` category in base class
   - Do import analyzers need additional detail (unused imports, circular deps, etc.)?
   - Could this be a tree-sitter query instead of regex?

3. **Architecture decision:**
   - Keep separate import analyzers but use tree-sitter?
   - Merge into main analyzers with specialized methods?
   - Create tree-sitter-based import extractors?

### Files to Review

- `analyzers/imports/base.py` (195 lines) - Base class for import analysis
- `analyzers/imports/python.py` (410 lines) - Python import analysis
- `analyzers/imports/go.py` (171 lines) - Go import analysis
- `analyzers/imports/rust.py` (214 lines) - Rust import analysis
- `analyzers/imports/javascript.py` (270 lines) - JavaScript import analysis
- `analyzers/imports/layers.py` (246 lines) - Layer violation detection
- `analyzers/imports/resolver.py` (142 lines) - Import path resolution

**Total**: 1,648 lines of import-specific code

---

## Phase 4: Validation Rules - Use Python AST

**Target**: Validation rules that parse Python code with regex
**Estimated effort**: 1-2 hours

### Files to Migrate

| File | Current Approach | Better Approach | Benefit |
|------|-----------------|-----------------|---------|
| `rules/validation/V002.py` | `re.findall(r'^class\s+\w+')` | `ast.parse()` + `ast.walk()` | Accurate class detection |
| `rules/validation/V003.py` | `re.match(r'^class\s+\w+')` | `ast.parse()` | Handles edge cases |

**Why AST instead of tree-sitter?**
- Python's `ast` module is stdlib (no dependencies)
- Purpose-built for Python code analysis
- Rules run on reveal's own Python code
- Tree-sitter would be overkill for simple validation

### Migration Example

```python
# Before (V002.py)
class_count = len(re.findall(r'^class\s+\w+', content, re.MULTILINE))

# After
import ast
tree = ast.parse(content)
classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
class_count = len(classes)
```

**Benefits:**
- Accurate (doesn't match `# class Foo` in comments)
- Robust (handles decorators, nested classes, etc.)
- Pythonic (uses stdlib tools)

---

## Legitimate Regex Uses (Keep As-Is)

**40-45% of regex usage (~65-75 instances) is appropriate:**

### Text Pattern Matching
- Version extraction from documentation (V007, V011, V014)
- Link/URL validation (L001, L002, L003, U501, U502)
- Markdown heading extraction (markdown.py)
- String normalization for slugs (markdown.py `_heading_to_slug`)

### String Manipulation
- Comment/docstring stripping for duplicate detection (D001, D002)
- Whitespace normalization
- Escape character handling

### Configuration Parsing
- Simple key-value extraction (where appropriate)
- Pattern-based file ignoring

**These should remain regex-based** - tree-sitter would be overkill.

---

## Quick Wins: Use String Methods

**15-20% of regex (~25-33 instances) should use simpler string methods:**

### Replace with str methods

| Current | Better | File Examples |
|---------|--------|---------------|
| `re.split(r',')` | `str.split(',')` | config.py, cli/*.py |
| `re.match(r'^foo')` | `str.startswith('foo')` | Various |
| `re.search(r'bar')` | `'bar' in string` | Various |

**Effort**: 1-2 hours to audit and replace
**Benefit**: Clearer code, better performance

---

## Migration Checklist Template

For each analyzer migration:

- [ ] Read current implementation to understand structure extracted
- [ ] Create test file for the language (e.g., `/tmp/test_X.ext`)
- [ ] Write new tree-sitter-based analyzer (3-5 lines)
- [ ] Test structure extraction: `reveal /tmp/test_X.ext`
- [ ] Test element extraction: `reveal /tmp/test_X.ext function_name`
- [ ] Verify output matches expected structure
- [ ] Update documentation if structure categories changed
- [ ] Commit with message: `refactor(analyzers): Migrate X to tree-sitter`
- [ ] Run V021 to verify file no longer flagged

---

## Success Metrics

### Phase 1 (Complete)
- ✅ V021 validation rule created and working
- ✅ GDScript migrated (197 → 21 lines)
- ✅ All tests passing
- ✅ Documentation updated

### Phase 2 (Target)
- [ ] 6 remaining analyzers migrated
- [ ] ~1,360 lines removed
- [ ] All V021 detections resolved
- [ ] Consistent tree-sitter architecture

### Full Migration (Vision)
- [ ] All appropriate regex replaced with tree-sitter or AST
- [ ] 200-300+ lines of code removed
- [ ] 4-5 parsing bugs fixed
- [ ] Validation rule enforces tree-sitter usage going forward
- [ ] Clear architectural guidelines documented

---

## Tree-Sitter Language Support

**Available in tree-sitter-language-pack:**

| Language | Status | Analyzer Status | Notes |
|----------|--------|----------------|-------|
| GDScript | ✅ Available | ✅ Migrated | Phase 1 complete |
| Dockerfile | ✅ Available | ⏳ Pending | Phase 2 |
| TOML | ✅ Available | ⏳ Pending | Phase 2 |
| YAML | ✅ Available | ⏳ Pending | Phase 2 |
| Nginx | ✅ Available | ❌ Not flagged | Not currently using regex (or whitelisted) |
| Python | ✅ Available | ✅ Using | Already migrated |
| Go | ✅ Available | ✅ Using | Main analyzer done, imports pending |
| Rust | ✅ Available | ✅ Using | Main analyzer done, imports pending |
| JavaScript | ✅ Available | ✅ Using | Main analyzer done, imports pending |
| TypeScript | ✅ Available | ✅ Using | Already migrated |
| C/C++ | ✅ Available | ✅ Using | Already migrated |
| Java | ✅ Available | ✅ Using | Already migrated |
| Ruby | ✅ Available | ✅ Using | Already migrated |
| ... | 40+ total | ... | See tree-sitter-language-pack docs |

---

## References

- **V021 Source**: `reveal/rules/validation/V021.py`
- **Tree-sitter Base**: `reveal/treesitter.py` (650 lines)
- **Example Migrated**: `reveal/analyzers/python.py` (15 lines)
- **Audit Report**: Agent task a139330 output (comprehensive 166-usage analysis)
- **Prior Session**: stellar-cosmos-0114 (V019/V020 validation work)

---

## Next Actions

**Immediate (Phase 2):**
1. Migrate dockerfile.py (30 minutes)
2. Migrate toml.py (1 hour)
3. Migrate yaml_json.py (1 hour)
4. Test all three with reveal --check
5. Commit as batch or individually

**Follow-up (Phase 3):**
1. Analyze import analyzers architecture
2. Decide: refactor with tree-sitter or keep specialized?
3. Migrate if beneficial

**Polish (Phase 4):**
1. Migrate V002/V003 to use Python ast module
2. Review remaining regex for str method replacements
3. Update architecture documentation

---

**Last Updated**: 2026-01-14 (Phase 1 complete)
**Next Review**: After Phase 2 completion
**Owner**: TIA + Scott (maintainer)
