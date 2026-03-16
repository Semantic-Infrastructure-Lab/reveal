---
title: "Reveal UX Issues & Bugs"
type: reference
beth_topics:
  - reveal
  - bugs
  - ux
  - quality
---

# Reveal UX Issues & Bugs

Discovered via dogfooding on real codebases (morphogen, tiacad) — session shining-wormhole-0315, 2026-03-15.

> **Status**: All 9 issues resolved in awakened-pegasus-0315 (v0.63.x). This doc is kept for historical reference.

---

## Bugs (Crashes / Wrong Output)

### BUG-01: `git:// blame&element=` crashes

**Severity:** High
**Adapter:** `git://`
**Repro:**
```bash
reveal 'git://path/to/file.py?type=blame&element=function_name'
```
**Error:**
```
Error (git://): GitAdapter.get_structure.<locals>.<lambda>() takes 1 positional argument but 3 were given
```
**Confirmed on:** morphogen (`circuit.py`), tiacad (`spatial_resolver.py`)
**Expected:** Blame output scoped to the named function
**Notes:** `?type=blame` without `element=` works correctly. The element dispatch in `get_structure` passes wrong arity to the lambda.

---

### BUG-02: `ast://` multi-file colon path silently returns 0 results

**Severity:** Medium
**Adapter:** `ast://`
**Repro:**
```bash
reveal 'ast://path/file1.py:path/file2.py?complexity>10'
```
**Output:**
```
Files scanned: 0
Results: 0
```
**Expected:** Either scan both files, or fail with a clear error explaining the syntax is unsupported.
**Notes:** The colon is the `diff://` separator, which creates ambiguity. Multi-file ast queries should be explicitly documented as unsupported or handled.

---

## UX Issues (Confusing / Misleading Output)

### UX-01: `diff://` with absolute paths fails cryptically

**Severity:** Medium
**Adapter:** `diff://`
**Repro:**
```bash
reveal 'diff:///abs/path/to/file1.py::/abs/path/to/file2.py'
# or
reveal 'diff:///abs/path/to/file1.py:/abs/path/to/file2.py'
```
**Error:**
```
Error (diff://): [Errno 2] No such file or directory: ':/abs/path/to/file2.py'
```
**Root cause:** The `:` separator in `diff://left:right` conflicts with absolute paths. The parser splits on the first `:` after the scheme, mangling the second path.
**Workaround:** Run from the project root and use relative paths.
**Expected:** Either support absolute paths (escape the separator), or emit a clear error: *"diff:// requires relative paths — run from your project root, or use: diff://./rel/path:./rel/path2"*

---

### UX-02: `imports:// violations` reports "0 violations" when config is missing

**Severity:** Medium
**Adapter:** `imports://`
**Repro:**
```bash
reveal 'imports:///path/to/project?violations'
```
**Output:**
```
Layer Violations: 0
✅ Layer violation detection requires .reveal.yaml configuration (coming in Phase 4)
```
**Problem:** The header says "0 violations" which looks like a clean pass. The explanation is in the body, but a user skimming output will conclude the project is clean.
**Expected:** When config is missing, lead with the config-missing message, not a count. E.g.:
```
Layer Violations: NOT CONFIGURED
ℹ️  Add layer rules to .reveal.yaml to enable this check.
    See: reveal help://configuration
```

---

### UX-03: `ast://` whole-project default dumps too many results

**Severity:** Medium
**Adapter:** `ast://`
**Repro:**
```bash
reveal ast:///path/to/large/project          # no filter
reveal 'ast://tiacad_core?type=class'        # broad filter on large codebase
```
**Problem:** Returns hundreds/thousands of results (morphogen: 6,895 unfiltered; tiacad class listing: 313) with no warning, no truncation, no result count shown before the dump.
**Expected:**
- Show result count before listing: `Results: 313 (showing all — use --limit N to cap)`
- Default cap at ~100 results with a "... and N more" message
- Suggest narrowing filters in the footer when results are large

---

### UX-04: `markdown://` type filter opaque when most files lack front matter

**Severity:** Low
**Adapter:** `markdown://`
**Repro:**
```bash
reveal 'markdown:///path/to/project/docs?type=architecture'
# Returns: Matched: 1 of 108 files
```
**Problem:** 107 files silently excluded. A user expects the `architecture/` subdirectory files to match `type=architecture` but they don't (only files with explicit `type: architecture` front matter match).
**Expected:** When match rate is very low (<5%), add a hint: *"Only files with `type: architecture` in YAML front matter are matched. Missing front matter? See reveal help://markdown."*

---

### UX-05: `reveal file.py function` fails with relative paths outside project root

**Severity:** Low
**Feature:** File/function extraction
**Repro:** Running `reveal path/to/file.py function_name` from a directory where `path/to/file.py` doesn't exist relative to cwd.
**Error:**
```
Error: path/to/file.py not found
```
**Problem:** Error gives no hint that the issue is cwd-relative path resolution.
**Expected:** Error message should suggest checking cwd: *"'path/to/file.py' not found. Running from: /current/dir — try an absolute path or cd to your project root."*

---

### UX-06: `git://` `?message~=` regex matches not documented

**Severity:** Low
**Adapter:** `git://`
**Observation:** `?message~=feat` matches commits containing "feature" (substring regex). This is correct behavior but:
1. Not documented in `reveal help://git`
2. Can surprise users expecting exact word match (`~=fix` matches "fixes", "prefix-fix", etc.)

**Expected:** `reveal help://git` should note: *"`~=` uses substring regex match. Use `~=\bfeat\b` for word-boundary match."*

---

### UX-07: `git://` file-scoped history not discoverable via `--log` flag

**Severity:** Low
**Adapter:** `git://`
**Observation:** Attempting `reveal git:///path/to/repo --log path/to/file` shows full repo log (flag silently ignored). The correct syntax is `reveal 'git://path/to/file?type=history'` but this is not obvious.
**Expected:** Either support `--log <file>` as an alias for `?type=history`, or emit: *"Unknown flag --log. For file history use: reveal 'git://path/to/file?type=history'"*

---

## Summary Table

| ID | Severity | Adapter | Issue | Status |
|----|----------|---------|-------|--------|
| BUG-01 | **High** | `git://` | `blame&element=` crashes with lambda arity error | ✅ Fixed awakened-pegasus-0315 |
| BUG-02 | **Medium** | `ast://` | Multi-file colon path silently scans 0 files | ✅ Fixed awakened-pegasus-0315 |
| UX-01 | **Medium** | `diff://` | Absolute paths fail cryptically due to `:` separator conflict | ✅ Fixed awakened-pegasus-0315 |
| UX-02 | **Medium** | `imports://` | Missing config shows "0 violations" instead of "not configured" | ✅ Fixed awakened-pegasus-0315 |
| UX-03 | **Medium** | `ast://` | No result cap or count warning on large unfiltered queries | ✅ Fixed awakened-pegasus-0315 |
| UX-04 | Low | `markdown://` | Silent exclusion when files lack front matter | ✅ Fixed awakened-pegasus-0315 |
| UX-05 | Low | file extraction | "Not found" error doesn't mention cwd context | ✅ Fixed awakened-pegasus-0315 |
| UX-06 | Low | `git://` | `~=` regex substring behavior undocumented | ✅ Fixed awakened-pegasus-0315 |
| UX-07 | Low | `git://` | `--log` flag silently ignored; correct syntax not suggested | ✅ Fixed awakened-pegasus-0315 |

---

## Test Codebases Used

- **morphogen** — `~/src/projects/morphogen` — 300 Python files, MLIR compiler, 39 domains
- **tiacad** — `~/src/projects/tiacad` — 136 Python files, declarative CAD, 1,125 tests
