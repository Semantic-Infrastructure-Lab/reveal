# Duplicate Code Detection in Reveal

**Version:** 0.29.0
**Status:** Partial implementation (single-file only)
**Last Updated:** 2026-01-03

---

## Quick Start

```bash
# Find exact duplicate functions in a file
reveal file.py --check --select D001

# Find all duplicates (includes experimental similarity detection)
reveal file.py --check --select D

# Find functions by naming patterns (cross-file)
reveal 'ast://./src?name=*parse*'

# Find duplication-prone code (complex/long functions)
reveal 'ast://./src?complexity>10&lines>50'
```

---

## What's Implemented

### D001: Exact Duplicates (Reliable)

**Status:** ✅ Production-ready
**Scope:** Single file only
**Method:** Hash-based detection using normalized code

Detects functions with identical implementations, even if:
- Variable names differ (signature normalization)
- Whitespace differs
- Comments differ

**Example:**
```bash
$ reveal app.py --check --select D001

app.py: Found 1 issue

app.py:45:1 ⚠️  D001 Duplicate function detected: 'process_b' identical to 'process_a' (line 12)
  💡 Refactor to share implementation with process_a
  📝 287 chars, hash a3f2c1b4
```

**How it works:**
1. Extracts function bodies from AST
2. Normalizes code (removes comments, whitespace, docstrings)
3. Creates SHA256 hash of normalized body
4. Reports functions with matching hashes

**Performance:** ~1-5ms per file

### D002: Similar Code (Experimental)

**Status:** ⚠️ High false positive rate
**Scope:** Single file only
**Method:** TF-weighted feature vectors + cosine similarity

**Known Issues:**
- Reports unrelated functions as 95%+ similar
- Feature extraction needs tuning
- Not recommended for production use

**Example output (with false positives):**
```bash
$ reveal app.py --check --select D002

app.py: Found 5 issues

app.py:430:1 ℹ️  D002 Potential duplicate candidate: 'extract_markdown_section' ~82% similar to '_register_custom_tools' (line 281)
  💡 Combined 524 lines. Worth investigating if logic can be shared.
  📝 Interestingness: 18.8 (similarity 82% × size 524)
```

**Reality:** These functions are often completely different. Use D001 only until D002 is improved.

---

## What's NOT Implemented (Yet)

### Cross-File Detection

**Status:** 🚧 Planned, not implemented
**Architecture:** Fully designed (see `internal-docs/planning/DUPLICATE_DETECTION_DESIGN.md`)

**Current limitation:**
```bash
# ❌ This only checks WITHIN each file, not ACROSS files
find src/ -name "*.py" | xargs -I {} reveal {} --check --select D001

# Each file is analyzed independently
# Duplicates between file_a.py and file_b.py are NOT detected
```

**Future capability:**
```bash
# 🚧 Not yet available
reveal ./src --check --select D001  # Would scan all files, find cross-file duplicates
```

**Why not implemented:** Requires caching layer to store function hashes across file scans.

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

Since cross-file detection isn't implemented, combine reveal with standard tools:

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

**Output shows files and line numbers:**
```
AST Query: ./src
Filter: name=*parse*
Files scanned: 45
Results: 18

File: src/schemas.py
  src/schemas.py:989   parse_file_annotations [22 lines, complexity: 4]
  src/schemas.py:1013  _parse_source_info [20 lines, complexity: 8]
  src/schemas.py:1056  parse_phase1_output [22 lines, complexity: 6]

File: src/handlers.py
  src/handlers.py:145  parse_request [18 lines, complexity: 3]
  src/handlers.py:203  parse_response [19 lines, complexity: 3]
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
reveal 'stats://./src' --hotspots

# Output:
Hotspots (Top 10 worst files):
1. src/processor.py      Quality: 45/100  (complexity: 18.3, 1243 lines)
2. src/handlers.py       Quality: 52/100  (complexity: 15.7, 987 lines)
3. src/validators.py     Quality: 58/100  (complexity: 12.4, 756 lines)
```

**4. Check each file individually:**
```bash
# Check high-priority files for exact duplicates
reveal src/processor.py --check --select D001
reveal src/handlers.py --check --select D001
reveal src/validators.py --check --select D001
```

**5. Pipeline approach (batch checking):**
```bash
# Check all Python files (within-file duplicates only)
find src/ -name "*.py" -type f | while read file; do
    echo "=== $file ==="
    reveal "$file" --check --select D001
done

# Or with git-tracked files only
git ls-files "*.py" | while read file; do
    reveal "$file" --check --select D001 2>/dev/null
done
```

### Finding Similar File Structures

Use stats:// to find files with similar characteristics (may indicate copy-paste):

```bash
# Find files with 200-300 lines
reveal 'stats://./src?min_lines=200&max_lines=300'

# Find files with similar complexity
reveal 'stats://./src?min_complexity=10&max_complexity=15'

# Find files with many functions (>20)
reveal 'stats://./src?min_functions=20'
```

---

## Understanding the Output

### D001 Output Format

```
file.py:45:1 ⚠️  D001 Duplicate function detected: 'process_b' identical to 'process_a' (line 12)
  💡 Refactor to share implementation with process_a
  📝 287 chars, hash a3f2c1b4
```

**Breakdown:**
- `file.py:45:1` - Duplicate function location (line 45, column 1)
- `'process_b'` - Name of duplicate function
- `'process_a' (line 12)` - Original function (first occurrence)
- `287 chars` - Size of normalized function body
- `hash a3f2c1b4` - First 16 chars of SHA256 hash (for debugging)

**What counts as "identical":**
- Same control flow
- Same operations
- Comments/whitespace ignored
- Function signature ignored (different param names OK)

### AST Query Output

```
AST Query: ./src
Filter: name=*parse*
Files scanned: 45
Results: 18

File: src/schemas.py
  src/schemas.py:989   parse_file_annotations [22 lines, complexity: 4]
  src/schemas.py:1013  _parse_source_info [20 lines, complexity: 8]
```

**Use this to:**
- Find functions with similar names across files
- Manually inspect for duplication patterns
- Identify naming conventions that suggest copy-paste

---

## Best Practices

### ✅ DO

1. **Use D001 only** (D002 has too many false positives)
```bash
reveal file.py --check --select D001
```

2. **Use AST queries for cross-file analysis**
```bash
reveal 'ast://./src?name=*pattern*'
```

3. **Find complex code first** (duplication hotspots)
```bash
reveal 'ast://./src?complexity>10&lines>50'
```

4. **Batch check with scripts**
```bash
find src/ -name "*.py" | xargs -I {} reveal {} --check --select D001
```

5. **Combine with stats for context**
```bash
reveal 'stats://./src' --hotspots
```

### ❌ DON'T

1. **Don't use D002 yet** (false positive rate ~90%)
```bash
# ❌ Avoid this
reveal file.py --check --select D002
```

2. **Don't expect cross-file detection**
```bash
# ❌ This won't find duplicates BETWEEN files
reveal ./src --check --select D
```

3. **Don't use `--check` without `--select D`**
```bash
# ❌ Runs ALL rules (slow, noisy)
reveal file.py --check

# ✅ Only duplicate detection
reveal file.py --check --select D001
```

---

## Limitations

### Current Limitations

1. **Single-file only**
   - D001 and D002 only detect duplicates within one file
   - No cross-file duplicate detection
   - Must check each file separately

2. **D002 unusable**
   - High false positive rate (85-95%)
   - Reports unrelated functions as similar
   - Feature extraction needs fundamental redesign

3. **No configuration**
   - Can't tune thresholds
   - Can't customize normalization
   - Can't set per-language rules

4. **No statistical feedback**
   - No similarity distribution analysis
   - No quality metrics
   - No threshold recommendations

### Architecture Exists, Implementation Missing

The good news: **Complete architecture designed** in `internal-docs/planning/`:
- ✅ `DUPLICATE_DETECTION_DESIGN.md` - Full system architecture
- ✅ `DUPLICATE_DETECTION_GUIDE.md` - Implementation plan
- ✅ `DUPLICATE_DETECTION_OPTIMIZATION.md` - D002 fixes
- ✅ `DUPLICATE_DETECTION_OVERVIEW.md` - Complete vision

**What needs implementation:**
1. Cross-file detection (caching layer)
2. Configuration system (YAML config files)
3. D002 feature extraction improvements
4. Self-reflection feedback system

---

## Roadmap

### Phase 1: Fix D002 (Reduce False Positives)
**Priority:** High
**Status:** Planned

**Changes needed:**
- Better feature extraction (current TF weighting is too coarse)
- Adaptive thresholds per language
- Structural features weighted higher
- Token features weighted lower

### Phase 2: Cross-File Detection
**Priority:** High
**Status:** Architecture complete

**Implementation:**
- Add function hash cache (SQLite or JSON)
- Scan multiple files in one pass
- Report duplicates across file boundaries
- Performance target: <100ms for 1000 files

### Phase 3: Configuration System
**Priority:** Medium
**Status:** Design complete

**Features:**
- `~/.reveal/duplicate_config.yaml`
- Per-language thresholds
- Feature toggles
- Normalization options

### Phase 4: Self-Reflection
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
A: Not yet. D001 and D002 only work within single files. Use AST queries (`ast://`) to find similar function names across files, then manually inspect.

**Q: Should I use D002?**
A: No, not in production. D002 has a ~90% false positive rate. Use D001 only for exact duplicates.

**Q: How do I find copy-pasted code between files?**
A: Currently requires manual workflow:
1. Use `reveal 'ast://./src?name=*pattern*'` to find similar names
2. Use `reveal 'ast://./src?complexity>10'` to find complex functions
3. Manually inspect candidate files
4. Check each file with `reveal file.py --check --select D001`

**Q: Why is D002 so bad?**
A: The TF-weighted feature vectors are too coarse. Functions with similar structural patterns (loops, conditionals) score as 95%+ similar even when logic is completely different. See `DUPLICATE_DETECTION_OPTIMIZATION.md` for planned fixes.

**Q: Can I configure the similarity threshold?**
A: Not yet. Configuration system is designed but not implemented. Thresholds are hardcoded.

**Q: Will cross-file detection be implemented?**
A: Architecture is complete, implementation is planned. It's the highest-priority enhancement for duplicate detection.

---

## Related Documentation

**User Guides:**
- `reveal help://agent` - AI agent quick reference (includes duplicate detection patterns)
- `reveal --agent-help-full` - Complete AI agent guide

**Planning Documents (Internal):**
- `internal-docs/planning/DUPLICATE_DETECTION_DESIGN.md` - Full architecture
- `internal-docs/planning/DUPLICATE_DETECTION_GUIDE.md` - Implementation guide
- `internal-docs/planning/DUPLICATE_DETECTION_OPTIMIZATION.md` - D002 improvements
- `internal-docs/planning/DUPLICATE_DETECTION_OVERVIEW.md` - System overview

**Implementation:**
- `reveal/rules/duplicates/D001.py` - Exact duplicate detection (186 lines)
- `reveal/rules/duplicates/D002.py` - Similar code detection (239 lines)
- `reveal/rules/duplicates/_base_detector.py` - Base framework (414 lines)

---

## Contributing

Want to help implement these features? See:
1. `internal-docs/planning/DUPLICATE_DETECTION_DESIGN.md` for architecture
2. `reveal/rules/duplicates/_base_detector.py` for base classes
3. GitHub Issues for "duplicate detection" label

**High-impact contributions:**
- Implement cross-file caching layer
- Fix D002 feature extraction
- Add configuration system
- Write tests for edge cases

---

**Status Summary:**
- ✅ D001 (exact, single-file) - Production ready
- ⚠️ D002 (similar, single-file) - Experimental, high false positives
- 🚧 Cross-file detection - Designed, not implemented
- 🚧 Configuration system - Designed, not implemented
- 🚧 Self-reflection - Designed, not implemented

Last updated: 2026-01-03 | Version: 0.29.0
