---
title: Duplicate Code Detection in Reveal
category: guide
help_topic: duplicates
help_description: "Duplicate code detection (D001/D002 functions per-file, D005 cross-file literals, workflows)"
help_category: feature_guides
---
# Duplicate Code Detection in Reveal

**Status:** D001 (exact) and D002 (opt-in similarity) compare functions within one file; D005 finds literal clusters across files

---

## Quick Start

```bash
# Find exact duplicate functions in a file
reveal check file.py --select D001

# Find all duplicates (adds opt-in similarity D002 and cross-file literals D005)
reveal check file.py --select D

# Find functions by naming patterns (cross-file)
reveal 'ast://./src?name=*parse*'

# Find duplication-prone code (complex/long functions)
reveal 'ast://./src?complexity>10&lines>50'
```

---

## What's Implemented

### D001: Exact Duplicates (Reliable)

**Status:** ✅ Production-ready
**Scope:** Single file only, and within one scope (see below)
**Method:** Hash-based detection using normalized code

Detects functions whose bodies are identical after removing comments, docstrings and
whitespace. Identifiers are kept as-is: a copy with renamed variables or parameters is
not D001 (D002 alpha-renames locals and can surface it).

Within one file, D001 compares functions only inside the same scope: top-level functions
with each other, and each class's methods with each other. Identical methods in two
different classes, or a method and a module-level function, are not reported.

**Example:**
```bash
$ reveal check app.py --select D001

app.py: Found 1 issue

app.py:23:1 ⚠️  D001 Duplicate function detected: 'process_c' identical to 'process_a' (line 1)
  💡 Refactor to share implementation with process_a
  📝 95 chars, hash ef526a198999adec
```

**How it works:**
1. Extracts function bodies from AST
2. Normalizes code (removes comments, whitespace, docstrings)
3. Creates SHA256 hash of normalized body
4. Reports functions with matching hashes

**Performance:** ~1-5ms per file

### D002: Similar Code (Opt-in)

**Status:** opt-in: runs with `--select D002` or `--select D`, off in a plain `reveal check`
**Scope:** Single file only
**Method:** a cosine pre-filter on body features, then a token-sequence match with local
names alpha-renamed (≥0.5) or a literal-identifier match (≥0.7). Functions under 8 lines
are skipped; at most 5 candidates per file, ranked by similarity × √size.

D002 is a ranked discovery list for review, not a defect report (severity low). The
sequence match is what keeps unrelated functions that merely share a skeleton (loops,
conditionals, similar length) off the list; a copy with renamed variables keeps its token
sequence and still matches.

**Example output:**
```bash
$ reveal check adapters/ast/filtering.py --select D002

adapters/ast/filtering.py: Found 3 issues

adapters/ast/filtering.py:389:1 ℹ️  D002 Potential duplicate candidate: '_matches_return_type' ~99% similar to '_matches_param_type' (line 361)
  💡 Combined 50 lines. Worth investigating if logic can be shared.
  📝 Interestingness: 7.0 (similarity 99% × size 50)
```

---

## Cross-File Detection

### Literal clusters (D005)

**Status:** ✅ Implemented

D005 detects the same hardcoded list/set/tuple literal duplicated across
multiple files — the pattern M104 (per-file) structurally cannot see. On the
first check in a project it scans every `.py` file under the project root,
indexes each qualifying literal by its order-independent value set, and flags
any cluster that spans `MIN_CLUSTER_FILES` (default 3) distinct files.

```bash
# ✅ Flags literals duplicated across ≥3 files
reveal check ./src --select D005
```

Thresholds: `MIN_LITERAL_SIZE = 5` (items in the literal), `MIN_CLUSTER_FILES = 3`
(distinct files). Names matching stable patterns (`__all__`, `*_format`, test
fixtures) are exempt. The cross-file index is cached per project root. Serialized
MCP requests validate healthy indexes against the existing tree fingerprint;
indexes built with directory-discovery failures rebuild on the next request.

Directory-discovery failures retain surviving findings and disclose that duplicate
clusters or participating files may be missing. Recursive Check marks D005's source
accounting `exact: false` while keeping observed file counts; it does not estimate
unseen files or count them as failed analyses. This uses Check's existing incomplete
exit 3 (`--exit-zero` retains the warning with exit 0) and ordinary MCP notes.
A failure to analyze an enumerated file remains separate: enumeration can still be
exact even when `failed_files` is positive. Existing scan-ceiling accounting and
healthy cache reuse keep their policies.

**Scope and ceiling:** the project root is resolved like I002's: a `.reveal.yaml`
with `root: true`, else the nearest package marker (`pyproject.toml`, `setup.py`,
`setup.cfg`, `package.json`, `go.mod`, `Cargo.toml`, `pom.xml`, `composer.json`, …),
else the git root, else the file's own directory (no index is built when that
directory is the temp dir, `$HOME` or `/`). To widen or narrow the scope, put
`root: true` in a `.reveal.yaml`. A tree exceeding **5,000 `.py` files** is skipped
with a logged warning rather than stalling an interactive `--check` — raise the bar
with `REVEAL_D005_MAX_FILES=N` for large monorepos.

### Function-body duplication (D001/D002)

**Status:** 🚧 Per-file only

D001 (exact) and D002 (similar) function detection still analyze each file
independently — duplicates between `file_a.py` and `file_b.py` are not detected.

```bash
# Checks every file under src/ in one call, but each file on its own:
# cross-file function duplicates are not detected
reveal check src/ --select D001
```

**Why not implemented:** Requires a caching layer to store function-body hashes
across file scans. D005's index pattern is the template if/when this lands.

### Configuration System

**Status:** 🚧 Fully designed, not implemented

**Planned features:**
- Per-language thresholds (`~/.reveal/duplicate_config.yaml`)
- Feature toggles (syntax, structural, semantic)
- Adaptive threshold tuning
- Normalization options (identifiers, literals)

**Current workaround:** Rules are hardcoded, no user configuration.

### Self-Reflection Feedback

**Status:** 🚧 Designed, not implemented

**Planned output:**
```
Similarity Distribution:
  Mean:   0.523  ✅ Good discrimination
  StdDev: 0.214
  Quality: 0.78/1.0

Suggested threshold: 0.75 (Current is optimal)
```

**Current output:** Just the rule violations, no statistical analysis.

---

## Practical Workflows

### Finding Duplicates Across a Codebase

D005 covers cross-file *literal* duplication directly. For cross-file *function*
duplicates (not yet automated), combine reveal with standard tools:

**1. Find candidate functions by naming patterns:**
```bash
# Find all 'parse' functions across codebase
reveal 'ast://./src?name=*parse*'

# Find all 'validate' functions
reveal 'ast://./src?name=*validate*'

# Find 'process' or 'handle' patterns
reveal 'ast://./src?name=*process*'
reveal 'ast://./src?name=*handle*'
```

**Output shows files and line numbers** (here run on reveal's own `adapters/`):
```
AST Query: ./adapters
Filter: name=*parse* (glob)
Files scanned: 214
Results: 59

File: adapters/ast/analysis.py
  :  43  parse_recovered_warning [16 lines, complexity: 6]
           calls:     s.get, to_posix (→ path_utils.py::to_posix), ', '.join
  : 516  _parser_failure [5 lines, complexity: 3]
           called by: _complete_structure, _analyzer_outcome

File: adapters/ast/nav_narrow.py
  : 120  _parse_type_node [35 lines, complexity: 15]
```

**2. Identify duplication-prone code:**
```bash
# Find long functions (>50 lines)
reveal 'ast://./src?lines>50'

# Find complex functions (cyclomatic complexity > 10)
reveal 'ast://./src?complexity>10'

# Combine filters
reveal 'ast://./src?complexity>10&lines>50'
```

**These are likely to contain duplicated logic or need refactoring.**

**3. Find hotspot files:**
```bash
# Identify files with quality issues
reveal 'metrics://./src' --hotspots

# Output (after the "Codebase Statistics" block):
Top Hotspots (10):

1. help.py
   Quality: 59.2/100 | Score: 35.3
   Issues: Quality: 59.2/100, 1 function(s) >100 lines, Touched 166 times in scope

2. imports.py
   Quality: 60.0/100 | Score: 26.4
   Issues: Quality: 60.0/100, Touched 147 times in scope
```

**4. Check each file individually:**
```bash
# Check high-priority files for exact duplicates
reveal check src/processor.py --select D001
reveal check src/handlers.py --select D001
reveal check src/validators.py --select D001
```

**5. Batch checking (within-file duplicates only):**
```bash
# Every Python file under src/, in one call
reveal check src/ --select D001

# Or git-tracked files only
git ls-files '*.py' | reveal --stdin --check --select D001
```

### Finding Similar File Structures

Use metrics:// to find files with similar characteristics (may indicate copy-paste):

```bash
# Find files with 200-300 lines
reveal 'metrics://./src?min_lines=200&max_lines=300'

# Find files with similar complexity
reveal 'metrics://./src?min_complexity=10&max_complexity=15'

# Find files with many functions (>20)
reveal 'metrics://./src?min_functions=20'
```

---

## Understanding the Output

### D001 Output Format

```
app.py:23:1 ⚠️  D001 Duplicate function detected: 'process_c' identical to 'process_a' (line 1)
  💡 Refactor to share implementation with process_a
  📝 95 chars, hash ef526a198999adec
```

**Breakdown:**
- `app.py:23:1` - Duplicate function location (line 23, column 1)
- `'process_c'` - Name of duplicate function
- `'process_a' (line 1)` - Original function (first occurrence)
- `95 chars` - Size of the function body (raw, before normalization)
- `hash ef526a198999adec` - First 16 hex chars of the SHA256 hash (for debugging)

**What counts as "identical":**
- Same control flow
- Same operations, with the same identifiers
- Comments, docstrings and whitespace ignored
- Only the `def` line is skipped; parameter names that appear in the body still count

### AST Query Output

```
AST Query: ./adapters
Filter: name=*parse* (glob)
Files scanned: 214
Results: 59

File: adapters/ast/analysis.py
  :  43  parse_recovered_warning [16 lines, complexity: 6]
           calls:     s.get, to_posix (→ path_utils.py::to_posix), ', '.join
  : 516  _parser_failure [5 lines, complexity: 3]
           called by: _complete_structure, _analyzer_outcome
```

Each row is `:LINE  name [size, complexity]` under its `File:` header, with optional
`calls:` / `called by:` lines.

**Use this to:**
- Find functions with similar names across files
- Manually inspect for duplication patterns
- Identify naming conventions that suggest copy-paste

---

## Best Practices

### ✅ DO

1. **Start with D001** (exact copies); read D002 as a ranked review list
```bash
reveal check file.py --select D001
```

2. **Use AST queries for cross-file analysis**
```bash
reveal 'ast://./src?name=*pattern*'
```

3. **Find complex code first** (duplication hotspots)
```bash
reveal 'ast://./src?complexity>10&lines>50'
```

4. **Batch check a directory in one call**
```bash
reveal check src/ --select D001
```

5. **Combine with stats for context**
```bash
reveal 'metrics://./src' --hotspots
```

### ❌ DON'T

1. **Don't gate CI on D002**: it is a ranked candidate list for a human to read, not a
   defect report
```bash
# ❌ Not a gate
reveal check src/ --select D002
```

2. **Don't expect cross-file function detection**
```bash
# ❌ Won't find duplicated FUNCTIONS between files
#    (D005 does catch duplicated list/set/tuple literals across files)
reveal check ./src --select D
```

3. **Don't use `--check` without `--select D`**
```bash
# ❌ Runs ALL rules (slow, noisy)
reveal check file.py

# ✅ Only duplicate detection
reveal check file.py --select D001
```

---

## Limitations

### Current Limitations

1. **Function detection is single-file only**
   - D001 and D002 only detect duplicates within one file
   - D001 compares only within one scope: top-level functions with each other, and each
     class's methods with each other
   - No cross-file function detection (D005 covers cross-file literals)

2. **D002 is a review list, not a verdict**
   - Opt-in, low severity, at most 5 candidates per file
   - Functions under 8 lines are skipped

3. **No configuration**
   - Can't tune thresholds
   - Can't customize normalization
   - Can't set per-language rules

4. **No statistical feedback**
   - No similarity distribution analysis
   - No quality metrics
   - No threshold recommendations

### Architecture Exists, Implementation Missing

The good news: **Complete architecture designed** (see base framework in `reveal/rules/duplicates/`).

**What needs implementation:**
1. Cross-file function detection (caching layer; D005's index is the template)
2. Configuration system (YAML config files)
3. Self-reflection feedback system

---

## Roadmap

### Phase 1: Cross-File Function Detection
**Priority:** High
**Status:** Architecture complete

**Implementation:**
- Add function hash cache (SQLite or JSON)
- Scan multiple files in one pass
- Report duplicates across file boundaries
- Performance target: <100ms for 1000 files

### Phase 2: Configuration System
**Priority:** Medium
**Status:** Design complete

**Features:**
- `~/.reveal/duplicate_config.yaml`
- Per-language thresholds
- Feature toggles
- Normalization options

### Phase 3: Self-Reflection
**Priority:** Medium
**Status:** Design complete

**Features:**
- Similarity distribution statistics
- Quality scoring (0-1)
- Threshold recommendations
- Feature effectiveness analysis

---

## FAQ

**Q: Can reveal find duplicates across multiple files?**
A: Not for functions. D005 finds duplicated list/set/tuple literals across files; for functions use the `ast://` workflow below.

**Q: Should I use D002?**
A: As a review list, yes: it is opt-in and ranks candidates for a human to read. Do not gate CI on it. Use D001 for exact duplicates.

**Q: How do I find copy-pasted code between files?**
A: Currently requires manual workflow:
1. Use `reveal 'ast://./src?name=*pattern*'` to find similar names
2. Use `reveal 'ast://./src?complexity>10'` to find complex functions
3. Manually inspect candidate files
4. Check each file with `reveal check file.py --select D001`

**Q: Why does D002 need a sequence match on top of the similarity score?**
A: The cosine score is dominated by shape features (line count, control-flow density), so unrelated functions with the same skeleton score 95%+. Requiring a token-sequence match (locals alpha-renamed) or a literal-identifier match removes those pairs and keeps real copies, renamed variables included.

**Q: Can I configure the similarity threshold?**
A: Not yet. Configuration system is designed but not implemented. Thresholds are hardcoded.

**Q: Will cross-file function detection be implemented?**
A: Architecture is complete, implementation is planned. It's the highest-priority enhancement for duplicate detection.

---

## Related Documentation

**User Guides:**
- `reveal help://duplicates` - this guide
- `reveal help://agent` - AI agent reference
- `reveal --agent-help` - AI agent orientation (~1,200 tokens; `help://agent/full` for the complete guide)

**Implementation:**
- `reveal/rules/duplicates/D001.py` - Exact duplicate detection
- `reveal/rules/duplicates/D002.py` - Similar code detection
- `reveal/rules/duplicates/D005.py` - Cross-file literal clusters
- `reveal/rules/base.py` - Shared `BaseRule` framework

---

## Contributing

Want to help implement these features? See:
1. `reveal/rules/base.py` for base classes
2. GitHub Issues for "duplicate detection" label

**High-impact contributions:**
- Implement cross-file function detection
- Add configuration system
- Write tests for edge cases

---

**Status Summary:**
- ✅ D001 (exact, single-file) - Production ready
- ℹ️ D002 (similar, single-file) - Opt-in ranked review list
- ✅ D005 (cross-file literal clusters) - Implemented
- 🚧 Cross-file FUNCTION detection - not implemented
- 🚧 Configuration system - Designed, not implemented
- 🚧 Self-reflection - Designed, not implemented

## See Also

- [ANALYZER_PATTERNS.md](../development/ANALYZER_PATTERNS.md) - Code analysis patterns
- [AGENT_HELP.md](../AGENT_HELP.md) - What NOT to do
- [PYTHON_ADAPTER_GUIDE.md](../adapters/PYTHON_ADAPTER_GUIDE.md) - Python-specific analysis
- [README.md](../README.md) - Documentation hub
