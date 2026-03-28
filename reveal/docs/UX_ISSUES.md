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
  - code-review
  - contracts
---

# Reveal UX Issues & Bugs

Discovered via dogfooding on real codebases (morphogen, tiacad) — session shining-wormhole-0315, 2026-03-15.

> **Status**: 6 open issues (UX-10, UX-11, UX-12, UX-13, FP-01, FP-02). All prior issues resolved as of shining-satellite-0327.

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
| MEM-04 | **High** | `ast/analysis.py` | Same as MEM-02 in `collect_structures()` | ✅ Fixed floating-wormhole-0321 |
| MEM-05 | Medium | `imports.py` | 100+ redundant rglob walks (one per extension) | ✅ Fixed floating-wormhole-0321 |
| MEM-06 | Low-Medium | `calls/index.py` | Unbounded `_INDEX_CACHE`, extra rglob on miss | ✅ Fixed floating-wormhole-0321 |
| MEM-07 | Low | `pack.py` | Full path list before budget scoring | ✅ Fixed floating-wormhole-0321 |
| MEM-08 | Low | `tree_view.py` | Full list before sort+truncate | ✅ Fixed sacred-shrine-0321 |

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

## UX Issues From Session Mining (rose-beam-0327, 2026-03-27)

Discovered by running `reveal 'claude://sessions/?search=...'` across 100 recent sessions and extracting reveal error patterns.

### UX-08: `--lines` ghost flag — unhelpful exit 2 + usage dump

**Severity:** Low
**Confirmed occurrences:** 1 (sunny-mist-0324)
**Problem:** Agent tried `reveal async_send_socialmedia_post.php --lines 1345-1370`, received exit code 2 with the full `usage:` dump. The error `reveal: error: unrecognized arguments: --lines 1345-1370` gives no hint about the correct alternatives.

The correct syntax for the two similar-sounding operations are:
- **Line range extraction** (yields the enclosing code element at those lines): `reveal file.php :1345-1370`
- **Structure-item range** (e.g., records 10–20 from a JSONL file): `reveal file.jsonl --range 1345-1370`

These are genuinely easy to confuse. `--lines` is the natural flag name a user reaching for line-range output would try.

**Fix options (pick one):**
1. Add `--lines` as a hidden alias for `--range` (minimal, handles JSONL/record range case only)
2. Intercept `--lines` in arg parsing before argparse sees it and emit a targeted suggestion:
   ```
   reveal: unknown flag --lines. Did you mean:
     reveal file.php :1345-1370        # extract element at line range
     reveal file.php --range 1345-1370 # show structure items in range
   ```
   Option 2 is preferred — it teaches the real model rather than silently accepting a confusing alias.

**Source:** rose-beam-0327 session mining.

---

### UX-09: `markdown://` relative path — query string appended to "not found" path

**Severity:** Low
**Confirmed occurrences:** Reproduced live (2 patterns affected: `?link-graph`, `?beth_topics~=`)
**Problem:** `reveal 'markdown://docs/?link-graph'` resolves the relative path before separating the query string, producing:
```
Error initializing markdown:// adapter: Directory not found: /path/to/cwd/docs/?link-graph
```
The `?link-graph` is attached to the resolved path in the error message, making it look like the literal filesystem path is `docs/?link-graph` rather than a query parameter issue.

**Root cause:** The URI parser resolves the path component before stripping the query string, so the error message shows the raw combined string.

**Fix:** Parse and separate path from query params *before* emitting the "not found" error. Show:
```
Error: directory not found: docs/ (resolved: /path/to/cwd/docs/)
Hint: reveal requires absolute paths for markdown:// URIs.
Try: reveal 'markdown:///path/to/cwd/docs/?link-graph'
```

**Source:** rose-beam-0327 session mining.

---

## UX Issues From Session Mining (seasonal-sleet-0328, 2026-03-28)

Discovered by parsing 80 recent `conversation.jsonl` files for Exit code 1/2 patterns, `Element not found` errors, agent retry sequences, and tool misuse. Method: Python script extracting Bash tool calls → tool results across all recent sessions; confirmed by reading surrounding context.

### UX-10: `errors.py` suggests `--analyzer text` — a flag that doesn't exist ❌

**Severity:** High
**File:** `reveal/errors.py:78`
**Confirmed occurrences:** 2 (copper-beam-0328, amber-spark-0328)

Every time reveal can't handle a file type (`.txt`, `.yml`, `.env`, compose files, etc.) the error suggestions include:
```
- Use generic text analyzer: reveal /path/to/file.txt --analyzer text
```
`--analyzer` is not a valid CLI argument. Following this suggestion produces Exit code 2 with the full `usage:` dump — a second failure on top of the first.

**Confirmed chain in copper-beam-0328:**
```bash
# Step 1: agent runs
reveal docker/compose.staging.yml
# → Error: No analyzer found ... Suggestions: ... --analyzer text

# Step 2: agent follows suggestion
reveal docker/compose.staging.yml --analyzer text
# → Exit code 2: usage: reveal [-h] ... error: unrecognized arguments: --analyzer text
```

There is no text analyzer. There is no `--analyzer` flag. The suggestion is dead wrong.

**Fix:** Remove the false suggestion from `errors.py:78`. Replace with something accurate, e.g.:
```
- View raw file content with: cat /path/to/file.txt
- View all supported file types: reveal --list-supported
- Request .txt support: https://github.com/...
```

---

### UX-11: `Element not found` for code files gives no alternatives

**Severity:** Medium
**File:** `reveal/display/element.py:252`
**Confirmed occurrences:** 3+ (amber-spark-0328, pulsing-gravity-0327, multiple others)

When element extraction fails for code files, reveal emits:
```
Error: Element 'deploy_staging' not found in deploy.sh
```
No hint about what IS available. The agent in amber-spark-0328 requested `deploy_staging`; the actual function name was `deploy_code_staging` (visible in the structure output, but not echoed in the error). The agent fell back to `reveal deploy.sh` (full file) — a wasteful round trip when a one-liner hint would have resolved it.

Compare to the file-not-found case, which shows a `Hint:` and a `Try:`. The element-not-found case has nothing.

**Fix:** On extraction failure, print available element names from the structure:
```
Error: Element 'deploy_staging' not found in deploy.sh
Available functions: red, green, yellow, bold, die, step, usage, wait_healthy, preflight_data,
                    sync_data, run_compose, build_base, deploy_code_staging, deploy_code_prod,
                    deploy_data_staging, deploy_data_prod
```
This is cheap — the structure is already parsed at this point.

---

### UX-12: Code element extraction is exact-match; markdown is substring — asymmetry causes silent failures

**Severity:** Low
**Confirmed occurrences:** Several (amber-spark-0328, multiple sessions)

Markdown section extraction uses case-insensitive substring matching — `reveal doc.md "staging"` finds `## Staging Environment`. Code element extraction is exact-match only — `reveal deploy.sh "staging"` returns `Element 'staging' not found`.

The asymmetry isn't documented at the point of failure. Agents trained on markdown behavior naturally carry it to code files and get silent not-found errors with no indication why.

**Observed pattern:** Agent uses `reveal script.sh "keyword"`, fails, falls back to `reveal script.sh` (full file dump).

The design rationale for exact-only is sound (`base.py:158`: substring matching on identifiers hits comments and variable references). But the *error message* should communicate the difference:
```
Error: Element 'staging' not found in deploy.sh
Hint: Code extraction uses exact function/class names. Available functions: ..., deploy_code_staging, ...
      For content search across the file, use: reveal deploy.sh --search staging
```

---

### UX-13: OR-pattern and table-row IDs — agents expect `reveal backlog.md "BACK-107|BACK-108"` to work

**Severity:** Low
**File:** `reveal/analyzers/markdown.py` — OR-pattern operates on headings only
**Confirmed occurrences:** 2 (shining-satellite-0327, pulsing-gravity-0327)

The OR-pattern (`|`) added in v0.67.0 works for heading-based extraction. Agents that know about OR-pattern naturally try it for table content — e.g., `reveal BACKLOG.md "BACK-107|BACK-108"`. Backlog IDs live in table rows, not headings, so it fails with:
```
Error: Element 'BACK-107|BACK-108' not found in BACKLOG.md
```

This is the same error as a plain not-found — nothing indicates that OR-pattern only applies to headings, or that `--search` exists.

**Fix:** When an OR-pattern extraction fails, add a hint:
```
Error: Element 'BACK-107|BACK-108' not found in BACKLOG.md
Hint: OR-pattern (|) matches section headings, not table content.
      To search file content: reveal BACKLOG.md --search BACK-107
```

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
| UX-08 | Low | CLI | `--lines N-M` produces unhelpful exit 2; should suggest `:N-M` or `--range` | ✅ Fixed shining-satellite-0327 |
| UX-09 | Low | `markdown://` | Relative path error appends query string to path in "not found" message | ✅ Fixed shining-satellite-0327 |
| UX-10 | **High** | CLI / errors | `errors.py` suggests `--analyzer text` — flag doesn't exist; causes 2nd failure | Open |
| UX-11 | **Medium** | file extraction | `Element not found` for code files lists no alternatives (available names) | Open |
| UX-12 | Low | file extraction | Code extraction is exact-only; markdown is substring — asymmetry undocumented at failure | Open |
| UX-13 | Low | `markdown` | OR-pattern failure on table IDs gives no hint about `--search` fallback | Open |
| FP-01 | **High** | B005 | Fires on `try/except ImportError` optional-dep pattern — flags working code as broken | Open |
| FP-02 | Medium | M102 | Fires on plugin/worker/blueprint modules loaded dynamically — no hint about suppress pattern | Open |

---

## Rule False Positives (session mining, seasonal-sleet-0328, 2026-03-28)

Confirmed by reading `reveal check` output in real user-project sessions (Stickerize My Dog, Cutliner). These are rules that fire correctly by their current logic but produce wrong conclusions for legitimate code patterns.

### FP-01: B005 fires on `try/except ImportError` optional-dependency pattern ❌

**Severity:** High
**Rule:** B005 ("Import references non-existent module")
**Confirmed occurrences:** 2 user projects (sevepa-0328: SMD `pillow_heif`; rose-ember-0328: Cutliner `vtracer`)

**Pattern that triggers it:**
```python
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    _HEIF_AVAILABLE = True
except ImportError:
    _HEIF_AVAILABLE = False
```

B005 flags `pillow_heif` as "references non-existent module — remove unused import or install missing package." The module IS in `pyproject.toml` and IS installed in the Docker image. The import is intentional graceful degradation for an optional dependency.

**What happened in practice (sevepa-0328):** The agent saw B005 and created a task to "fix broken import" and began investigating whether `pillow_heif` should be removed. After reading the code it discovered the `try/except` and correctly identified it as a false positive. But this costs a full investigation cycle, and an agent less careful about reading surrounding code could delete working code.

**Root cause:** B005 checks whether the package can be imported at rule evaluation time (or is in a known package list), without considering that the import is already guarded by `try/except ImportError` — which by definition means "this might not be installed, and that's OK."

**Fix:** B005 should not fire when the import statement is directly inside a `try/except ImportError` block. The `try/except ImportError` pattern is the canonical Python idiom for optional dependencies.

**Suppression (workaround until fixed):** `# noqa: B005` on the import line, or add to `.reveal.yaml`:
```yaml
rules:
  B005:
    ignore_optional_imports: true
```

---

### FP-02: M102 fires on plugin, worker, and dynamically-loaded modules ❌

**Severity:** Medium
**Rule:** M102 ("Module is not imported anywhere in the package — may be dead code")
**Confirmed occurrences:** sevepa-0328 (`mailer.py`), noble-earth-0322 (reveal rule discovery modules, template scaffolding)

**Pattern that triggers it:**
Any `.py` file that is not statically imported anywhere in the package. This correctly catches some dead code, but also flags:

- **Background workers/tasks** — loaded by a task queue (Celery, RQ) by module path, never imported
- **Flask/FastAPI blueprints** — registered via `app.register_blueprint()` or similar
- **CLI entry points** — invoked via `pyproject.toml [scripts]` or `__main__.py`
- **Plugin/extension files** — discovered at runtime via `importlib`, `pkgutil.iter_modules`, or file-system scan
- **Template/scaffolding files** — intentionally not imported, used as copy targets

**What happened in practice (sevepa-0328):** `mailer.py` flagged as dead code. Agent noted it and moved on, but the warning is actively misleading — the module is used, just not via a static import.

**What happened in reveal's own codebase (noble-earth-0322):** Rule discovery modules are loaded via `importlib` at runtime, never statically imported → M102 fires on every rule file. The fix was `.reveal.yaml` suppression with comments explaining why.

**Root cause:** M102 performs pure static analysis (import graph traversal) and cannot detect runtime-dynamic loading patterns.

**Fix options:**
1. Suppress when the module is registered in `pyproject.toml [scripts]` or `[entry-points]`
2. Suppress when the module contains `if __name__ == '__main__':`
3. Suppress when the directory is named `tasks/`, `workers/`, `commands/`, `plugins/`, `templates/`
4. Document the suppression patterns clearly in `--agent-help` output so agents find them before investigating

**Suppression (workaround):** Add to `.reveal.yaml`:
```yaml
- files: "src/myapp/workers/**/*.py"
  rules:
    disable:
      - M102  # Workers loaded dynamically by task queue, not statically imported
```

---

## Summary Table

Discovered via full codebase review (static analysis + manual audit) — session floating-wormhole-0321, 2026-03-21.

### BUG-03: Duplicate method `render_element` in `calls/adapter.py` (D001)

**Severity:** Medium
**File:** `reveal/adapters/calls/adapter.py` lines 220–227
**Problem:** `render_element` (line 225) and `render_structure` (line 220) are byte-for-byte identical — both delegate to `render_calls_structure()` with the same logic. One is dead code.
```python
def render_structure(result, format='text'):
    effective_format = result.get('_query_format') or format
    render_calls_structure(result, effective_format)

def render_element(result, format='text'):   # identical
    effective_format = result.get('_query_format') or format
    render_calls_structure(result, effective_format)
```
**Fix needed:** Remove `render_element`; route any callers to `render_structure`.

---

### BUG-04: `letsencrypt/adapter.py` missing required contract fields `source` and `source_type` (V023)

**Severity:** High
**File:** `reveal/adapters/letsencrypt/adapter.py` lines ~195–223
**Problem:** `get_structure()` returns a result dict without `source` or `source_type` — both required by the adapter output contract (see `adapters/base.py`). Every other adapter includes them. Downstream tools that consume the contract (V023 validator, structured output consumers) will fail or silently skip fields.
**Fix needed:** Add to the returned dict in `get_structure()`:
```python
'source': self.live_dir,
'source_type': 'letsencrypt_directory',
```

---

### CFG-01: Rule config key allowlist rejects legitimate rule-specific keys (hundreds of warnings)

**Severity:** Medium
**File:** `reveal/rules/__init__.py` line 430
**Problem:** `_ALLOWED_RULE_CONFIG_KEYS` is defined as:
```python
frozenset({'enabled', 'severity', 'threshold', 'message', 'description'})
```
Rules C905, E501, and R913 each register their own threshold keys (`MAX_DEPTH`, `max_length`, `max_args`), but these are not in the allowlist. Result: every file checked emits multiple "Unknown rule config key … ignored" warnings to stderr, drowning out real output.
**Fix needed:** Expand the frozenset to include the keys actually used by built-in rules:
```python
_ALLOWED_RULE_CONFIG_KEYS = frozenset({
    'enabled', 'severity', 'threshold', 'message', 'description',
    'max_length', 'max_depth', 'MAX_DEPTH', 'max_args',
})
```
**Longer-term:** Let each rule class declare `allowed_config_keys: Set[str]` so the registry can validate per-rule rather than via a central list.

---

### PERF-01: `_dir_cache_key` walks entire directory tree on every cache miss

**Severity:** Medium
**File:** `reveal/adapters/calls/index.py` lines 113–122
**Problem:** The cache key function calls `directory.rglob('*')` and `os.stat()` on every file to build a mtime fingerprint. On a 5,000-file codebase this is ~500ms just for the key computation, on every cache miss. The LRU cap (MEM-06) bounds how many entries accumulate, but each miss is still slow.
**Fix needed:** Use `os.stat(directory).st_mtime_ns` as the primary key (O(1), reliable on ext4/APFS/NTFS). Keep the full rglob as an OSError fallback only:
```python
def _dir_cache_key(directory: Path) -> Any:
    try:
        return ('dir_mtime', os.stat(directory).st_mtime_ns)
    except OSError:
        entries = []
        for fp in sorted(directory.rglob('*')):
            if fp.is_file() and is_code_file(fp):
                try:
                    entries.append((str(fp), os.stat(fp).st_mtime_ns))
                except OSError:
                    pass
        return ('file_mtimes', tuple(entries))
```
**Trade-off:** Directory mtime is not updated on metadata-only changes (permissions). Acceptable for code analysis; edge case on NFS/FAT32.

---

## Test Coverage Gaps

Discovered during full codebase review — session floating-wormhole-0321, 2026-03-21.

### TEST-01: `AstAdapter` class has no unit tests

**Severity:** Medium
**File:** `reveal/adapters/ast/adapter.py`
**Problem:** Only the call graph submodule (`test_ast_call_graph.py`, 38 tests) is unit tested. The main `AstAdapter` class — query parsing (lines 61–95), decorator filtering (lines 104–118), result sorting/limiting/offset, and the full `get_structure()` method — has no dedicated unit tests. Integration tests provide some coverage but don't exercise parameter combinations.
**Fix needed:** Add `tests/adapters/test_ast_adapter.py` covering:
- Query param parsing (`?type=`, `?complexity>N`, `?sort=`, `?limit=`, `?offset=`)
- Decorator filtering (`?decorator=property`)
- Builtins filtering (`?show=builtins`)
- Edge cases: empty file, file with no functions, binary file

---

### TEST-02: Python adapter undertested (9 tests)

**Severity:** Low
**File:** `reveal/adapters/python/` (or equivalent)
**Test file:** `tests/test_python_adapter.py`
**Problem:** Only 9 tests cover what appears to be a substantial adapter implementation. Missing coverage for Python-specific features (runtime introspection, sys.path, installed packages, virtual environment detection).
**Fix needed:** Expand to cover the adapter's core functionality surface.

---

## Code Quality Issues Summary

Discovered: floating-wormhole-0321, 2026-03-21.

| ID | Severity | File | Issue | Status |
|----|----------|------|-------|--------|
| BUG-03 | Medium | `adapters/calls/adapter.py:220` | `render_element` identical to `render_structure` — dead code | ✅ Fixed sacred-shrine-0321 |
| BUG-04 | **High** | `adapters/letsencrypt/adapter.py:195` | Missing `source` + `source_type` contract fields | ✅ Fixed sacred-shrine-0321 |
| CFG-01 | Medium | `rules/__init__.py:430` | Config key allowlist too narrow — floods stderr with warnings | ✅ Fixed sacred-shrine-0321 |
| PERF-01 | Medium | `adapters/calls/index.py:113` | Cache key does full `rglob` on every miss (~500ms on large repos) | ✅ Fixed sacred-shrine-0321 |
| TEST-01 | Medium | `adapters/ast/adapter.py` | `AstAdapter` class has no unit tests | ✅ Fixed sacred-shrine-0321 |
| TEST-02 | Low | `adapters/python/` | Python adapter has only 9 tests | ✅ Fixed sacred-shrine-0321 |

---

## Test Codebases Used

- **morphogen** — `~/src/projects/morphogen` — 300 Python files, MLIR compiler, 39 domains
- **tiacad** — `~/src/projects/tiacad` — 136 Python files, declarative CAD, 1,125 tests
- **reveal itself** — `~/src/projects/reveal/external-git/reveal/` — 414 Python files, 124K lines (floating-wormhole-0321)
