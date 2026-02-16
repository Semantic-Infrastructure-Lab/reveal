# GitHub Issues to Create from Testing

**Source:** Popular repositories testing session (howling-flood-0104)
**Date:** 2026-01-04
**Reference:** `research/POPULAR_REPOS_TESTING_ISSUES.md`

---

## Issue #1: C Language Support Broken

**Title:** C language analyzer returns "No structure available"

**Labels:** `bug`, `language-support`, `high-priority`

**Description:**

C files show "No structure available for this file type (fallback: c)" even though C is listed as a supported language.

**Steps to Reproduce:**
```bash
git clone --depth=1 https://github.com/tree-sitter/tree-sitter.git
reveal tree-sitter/lib/src/parser.c
```

**Expected Behavior:**
Should extract functions, structs, typedefs, and other C language elements, similar to Python analyzer.

**Actual Behavior:**
```
File: parser.c (76.0KB, 2,262 lines) (fallback: c)

No structure available for this file type
```

**Environment:**
- Reveal version: 0.29.0
- Test file: `tree-sitter/lib/src/parser.c` (2,262 lines)
- Impact: Cannot analyze any C codebases

**Additional Context:**
- tree-sitter itself is written in C - this is a dogfooding opportunity
- tree-sitter has 31 C files + 43 headers available for testing
- Help output lists C as supported: `--list-supported` includes C

**Possible Root Cause:**
- Tree-sitter C grammar not loaded/configured
- C analyzer not properly registered
- Fallback mode kicking in incorrectly

**Priority:** High
**Reason:** C is a fundamental language; Reveal uses tree-sitter which is written in C

---

## Issue #2: JSON Output Format Invalid (Breaks jq Parsing)

**Title:** `--format=json` produces invalid JSON that jq cannot parse

**Labels:** `bug`, `output-format`, `high-priority`, `ci-cd`

**Description:**

JSON output from `--format=json` is malformed and cannot be parsed by jq or other JSON processors.

**Steps to Reproduce:**
```bash
git clone --depth=1 https://github.com/tiangolo/fastapi.git
reveal fastapi/fastapi/applications.py --format=json | jq '.structure.functions[]'
```

**Expected Behavior:**
Valid JSON that can be piped to jq for filtering and processing.

**Actual Behavior:**
```
parse error: Invalid numeric literal at line 1, column 6
```

**Environment:**
- Reveal version: 0.29.0
- Test file: FastAPI applications.py (4,669 lines)
- jq version: (standard)

**Impact:**
- Breaks documented use case in `--help` examples
- Prevents programmatic consumption of Reveal output
- Blocks CI/CD integration workflows
- Makes pipeline mode unusable for JSON consumers

**Additional Context:**
- Issue may be specific to large files or complex nested structures
- Could be invalid escape sequences in function signatures (e.g., `\*\*kwargs`)
- Possibly related to numeric formatting in metrics

**Debug Suggestion:**
1. Capture raw JSON to file: `reveal file.py --format=json > output.json`
2. Validate with: `jq . output.json` to see exact error
3. Check for trailing commas, invalid escapes, or malformed numbers

**Priority:** High
**Reason:** Documented feature, critical for CI/CD, breaks programmatic workflows

---

## Issue #3: Element Search Matches First Occurrence Instead of Definition

**Title:** Element extraction matches references instead of definitions

**Labels:** `enhancement`, `element-extraction`, `medium-priority`

**Description:**

When extracting elements by name (e.g., `reveal file.py ClassName`), Reveal matches the first text occurrence rather than the actual definition, leading to wrong extractions.

**Steps to Reproduce:**
```bash
git clone --depth=1 https://github.com/pallets/flask.git
reveal flask/src/flask/app.py Flask
```

**Expected Behavior:**
Extract the Flask class definition at line 108:
```python
class Flask(App):
    """The flask object implements a WSGI application..."""
```

**Actual Behavior:**
Extracts type variable context around line 59-79 because "Flask" appears in import comments.

**Impact:**
- Common scenario: many class/function names appear in imports, comments, docstrings
- User must know exact line number or use workarounds
- Confusing when element exists but wrong one is extracted

**Workarounds:**
1. Use more specific search: `reveal app.py "class Flask"`
2. Use `--outline` first to find correct line
3. Specify line number (if syntax supported)

**Suggested Improvements:**
1. **Prioritize definitions:** Class/function definitions should rank higher than references
2. **Multiple matches:** Show list if multiple matches found, let user choose
3. **Line number syntax:** Support `reveal file.py:108` for line-specific extraction
4. **Semantic search:** Use AST to find definitions, not text search

**Priority:** Medium
**Reason:** Common pain point, but workarounds exist

---

## Issue #4: `--hotspots` Flag Requires URI Adapter Syntax

**Title:** `--hotspots` flag doesn't work directly on directories

**Labels:** `usability`, `enhancement`, `medium-priority`

**Description:**

The `--hotspots` flag exists but errors when used on directories, forcing users to learn `stats://` URI adapter syntax.

**Steps to Reproduce:**
```bash
reveal src/ --hotspots
```

**Expected Behavior:**
Show quality hotspots for all files in directory.

**Actual Behavior:**
```
❌ Error: --hotspots only works with stats:// adapter

Examples:
  reveal stats://src/?hotspots=true    # URI param (preferred)
  reveal stats://src/ --hotspots        # Flag (legacy)
```

**Impact:**
- Confusing UX: flag exists but doesn't work
- Forces users to learn URI adapter syntax
- Inconsistent with other flags that work directly

**Current Required Syntax:**
```bash
reveal 'stats://fastapi/fastapi/?hotspots=true'
```

**Suggested Fix:**
Make `--hotspots` flag auto-wrap path in stats:// adapter:
```bash
reveal src/ --hotspots  # Internally: reveal 'stats://src/?hotspots=true'
```

**Priority:** Medium
**Reason:** UX improvement, reduces learning curve, makes feature more discoverable

---

## Issue #5: AST Query Filters Undocumented

**Title:** `ast://` adapter filters not documented anywhere

**Labels:** `documentation`, `ast-queries`, `medium-priority`

**Description:**

AST queries work (`ast://path?complexity>20`) but available filters are undocumented. Users must guess or read source code.

**Current State:**
- `reveal help://ast` doesn't list available filters
- `--help` has minimal AST examples
- No reference in AGENT_HELP.md

**Discovered Filters (via testing):**
- `complexity>N` - cyclomatic complexity threshold
- `lines>N` - function length threshold
- `depth>N` - nesting depth threshold
- `type=function|class|method` - element type filter

**Missing Documentation Locations:**
1. `reveal help://ast` - should list all filters with examples
2. `reveal --help` - should have AST query section
3. `reveal/AGENT_HELP.md` - should document for AI agents
4. Public docs - should have AST query cookbook

**Suggested Additional Filters:**
- `imports~pattern` - filter by import statements
- `decorators~pattern` - filter by decorator usage
- `calls~function` - filter by function calls
- Combined: `ast://src?complexity>20&lines>50`

**Impact:**
- Feature exists but is invisible to users
- Reduces value of powerful query system
- Forces users to explore source code

**Priority:** Medium
**Reason:** Major discoverability issue for advanced feature

---

## Issue #6: Recursive Check Performance Could Be Parallelized

**Title:** `--recursive --check` processes files sequentially (parallelization opportunity)

**Labels:** `performance`, `enhancement`, `low-priority`

**Description:**

Recursive quality checks process files sequentially without utilizing multiple CPU cores.

**Current Performance:**
- ~2 seconds per 100 files (single-threaded)
- Django (2,888 files) = ~58 seconds

**Observation:**
```bash
reveal django/django/ --recursive --check
```
- Processes one file at a time
- CPU not maxed out (single core usage)
- No progress indicator

**Suggested Improvements:**
1. **Parallelize:** Use multiprocessing to check multiple files simultaneously
2. **Progress indicator:** `[342/2888] Checking forms/models.py... (12 issues found)`
3. **Early exit:** `--max-issues N` to stop after finding N issues

**Expected Impact:**
- 4-8x speedup on multi-core systems (depending on core count)
- Better user experience for large codebases
- Faster CI/CD pipelines

**Priority:** Low
**Reason:** Already fast enough for most use cases; optimization not critical for v1.0

---

## Issue #7: Quality Rules Flag Functions with Large Docstrings

**Title:** C902 "function too long" rule creates false positives for docstring-heavy code

**Labels:** `quality-rules`, `false-positive`, `low-priority`

**Description:**

Functions with extensive documentation are flagged as "too long" even when actual code is minimal.

**Example from FastAPI:**
```
applications.py:1541  get [372 lines, complexity: 1]
applications.py:1914  put [377 lines, complexity: 1]
applications.py:2292  post [377 lines, complexity: 1]
```

**Issue:**
- Functions flagged as too long (>100 lines)
- Actually 90%+ docstrings (complexity: 1 confirms minimal logic)
- Creates noise in quality reports

**Suggested Fix:**
Adjust M101/C902 rules to account for docstring ratio:
```python
effective_lines = total_lines - docstring_lines
if effective_lines > threshold:
    report_issue()
```

**Alternative:**
Modify message to indicate docstrings:
```
⚠️  C902 Function is long: get (372 lines, mostly docstrings)
💡 Consider extracting documentation to separate file if it impacts readability
```

**Impact:**
- Minor annoyance for well-documented code
- May train users to ignore warnings
- Not a blocker for v1.0

**Priority:** Low
**Reason:** Edge case, doesn't break functionality, workaround is to ignore warnings

---

## Summary Table

| # | Title | Priority | Impact | Effort |
|---|-------|----------|--------|--------|
| 1 | C language support broken | High | Can't analyze C code | Medium |
| 2 | JSON output invalid | High | Breaks CI/CD | Low |
| 3 | Element search too greedy | Medium | Wrong extractions | Medium |
| 4 | --hotspots flag UX | Medium | Discoverability | Low |
| 5 | AST filters undocumented | Medium | Feature invisible | Low |
| 6 | Recursive check parallelization | Low | Performance | Medium |
| 7 | Quality rule false positives | Low | Noise | Low |

**Recommended for v1.0:**
- Issue #1 (C support) - High priority, medium effort
- Issue #2 (JSON output) - High priority, low effort
- Issue #5 (AST docs) - Medium priority, low effort

**Defer to v1.1+:**
- Issue #3, #4 (UX improvements)
- Issue #6, #7 (optimizations)

---

## Testing Evidence

Full testing documentation:
- `/home/scottsen/src/tia/sessions/howling-flood-0104/REVEAL_TESTING_RESULTS.md`
- `/home/scottsen/src/tia/sessions/howling-flood-0104/REVEAL_ADVANCED_FEATURES.md`
- `reveal/internal-docs/research/POPULAR_REPOS_TESTING_ISSUES.md`

Test repos available for reproduction:
```bash
git clone --depth=1 https://github.com/psf/requests.git
git clone --depth=1 https://github.com/pallets/flask.git
git clone --depth=1 https://github.com/tiangolo/fastapi.git
git clone --depth=1 https://github.com/django/django.git
git clone --depth=1 https://github.com/tree-sitter/tree-sitter.git
```
