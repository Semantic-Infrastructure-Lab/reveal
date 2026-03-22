---
title: "Reveal UX Issues & Bugs"
type: reference
beth_topics:
  - reveal
  - bugs
  - ux
  - quality
  - memory
  - performance
---

# Reveal UX Issues & Bugs

Discovered via dogfooding on real codebases (morphogen, tiacad) — session shining-wormhole-0315, 2026-03-15.

> **Status**: All 9 original issues resolved in awakened-pegasus-0315 (v0.63.x). Memory issues below discovered in vortex-isotope-0321, 2026-03-21 — partially fixed, remainder documented here.

---

## Memory / Performance Issues

Discovered via OOM kill post-mortem — `reveal stats://.` and `reveal overview .` on the reveal codebase (554 Python files) consumed 28GB+ and killed the machine twice (Mar 18, Mar 21). Root cause was unbounded parse tree caching + file content retained across the entire directory scan.

### MEM-01: `_parse_cache` unbounded growth during directory scans ✅ Fixed vortex-isotope-0321

**Severity:** Critical
**File:** `reveal/treesitter.py`
**Problem:** Module-level `_parse_cache` dict accumulated parse trees + node caches for every file analyzed. During `stats://.` on a 554-file project it grew to hold all 554 trees indefinitely, contributing to 28GB memory use.
**Fix:** Replaced plain dict with `OrderedDict` LRU capped at 128 entries. Cache-hit rate during directory scans is ~0% (each file visited once), so eviction costs nothing.

---

### MEM-02: Analyzer content not freed after `analyze_file()` in stats scan ✅ Fixed vortex-isotope-0321

**Severity:** High
**File:** `reveal/adapters/stats/analysis.py`
**Problem:** After `calculate_file_stats_func()` returned, `analyzer.lines`, `.content`, and `._content_bytes` were retained until Python's GC decided to collect. During sequential scans of hundreds of files, multiple files' full content coexisted in memory at peak.
**Fix:** Explicitly clear `analyzer.lines = []`, `.content = ''`, `._content_bytes = None` immediately after stats are computed.

---

### MEM-03: `find_analyzable_files()` materializes full path list before analysis ✅ Fixed vortex-isotope-0321

**Severity:** Low
**Files:** `reveal/adapters/stats/analysis.py`, `reveal/adapters/diff/resolution.py`
**Problem:** Returned `List[Path]`, building the complete file list in memory before any analysis began.
**Fix:** Converted to `Iterator[Path]` generator. One diff caller that used `len(files)` now counts during iteration.

---

### MEM-04: `ast/analysis.py collect_structures()` — FIXED

**Severity:** High → **Resolved**
**File:** `reveal/adapters/ast/analysis.py`
**Fix:** Added explicit content cleanup in `analyze_file()` after the structure loop: `analyzer.lines = []`, `.content = ''`, `._content_bytes = None`. Peak memory now proportional to one file, not all files analyzed.

---

### MEM-05: `imports.py` performs one `rglob()` per file extension (~100 walks) — FIXED

**Severity:** Medium → **Resolved**
**File:** `reveal/adapters/imports.py`
**Fix:** Replaced `for ext in get_all_extensions(): rglob(pattern)` loop with a single `rglob('*')` walk filtered by `frozenset` of supported extensions.

---

### MEM-06: `calls/index.py _INDEX_CACHE` — unbounded, no LRU — FIXED

**Severity:** Low-Medium → **Resolved**
**File:** `reveal/adapters/calls/index.py`
**Fix:** Replaced plain `dict` with `OrderedDict` LRU capped at 8 entries. Cache hits call `move_to_end()`; inserts evict oldest with `popitem(last=False)` when over limit.

---

### MEM-07: `pack.py _walk_files()` materializes full file list before budget scoring — FIXED

**Severity:** Low → **Resolved**
**File:** `reveal/cli/commands/pack.py`
**Fix:** Converted `_walk_files()` from `List[Path]` to `Generator[Path, None, None]`; caller (`_collect_candidates`) already iterated, so no other changes needed.

---

### MEM-08: `tree_view.py _collect_matching_files()` builds full list before sort+truncate

**Severity:** Low
**File:** `reveal/tree_view.py` line 28
**Problem:** Collects all `(Path, stat)` tuples before sorting and applying `max_entries=200` cap. On a 50k-file directory this builds 50k tuples then discards 49,800 of them.
**Fix needed:** Bounded max-heap (e.g., `heapq.nlargest(max_entries, ...)`) to keep only the top N entries during traversal.

---

## Memory Issues Summary

| ID | Severity | File | Issue | Status |
|----|----------|------|-------|--------|
| MEM-01 | **Critical** | `treesitter.py` | Unbounded `_parse_cache` — 28GB OOM kill | ✅ Fixed vortex-isotope-0321 |
| MEM-02 | **High** | `stats/analysis.py` | Analyzer content not freed after per-file stats | ✅ Fixed vortex-isotope-0321 |
| MEM-03 | Low | `stats/analysis.py`, `diff/resolution.py` | Full path list before analysis | ✅ Fixed vortex-isotope-0321 |
| MEM-04 | **High** | `ast/analysis.py` | Same as MEM-02 in `collect_structures()` | ⬜ Not yet fixed |
| MEM-05 | Medium | `imports.py` | 100+ redundant rglob walks (one per extension) | ⬜ Not yet fixed |
| MEM-06 | Low-Medium | `calls/index.py` | Unbounded `_INDEX_CACHE`, extra rglob on miss | ⬜ Not yet fixed |
| MEM-07 | Low | `pack.py` | Full path list before budget scoring | ⬜ Not yet fixed |
| MEM-08 | Low | `tree_view.py` | Full list before sort+truncate | ⬜ Not yet fixed |

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
