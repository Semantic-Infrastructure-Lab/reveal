# Changelog

All notable changes to reveal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### ✨ NEW: Configurable MySQL Health Thresholds

**Customize health check thresholds** - No more hardcoded limits!

MySQL health check thresholds are now fully configurable via YAML config files. Different environments (dev, staging, prod) can have different tolerance levels.

**Configuration:**

Create `~/.config/reveal/mysql-health-checks.yaml` (user-specific) or `/etc/reveal/mysql-health-checks.yaml` (system-wide):

```yaml
checks:
  - name: "Table Scan Ratio"
    metric: "table_scan_ratio"
    pass_threshold: 5      # Stricter than default (10)
    warn_threshold: 15     # Stricter than default (25)
    severity: high
    operator: "<"

  # ... customize other checks
```

**Features:**
- ✅ Fallback to sensible defaults if no config exists
- ✅ Per-environment customization (dev/staging/prod)
- ✅ Add/remove checks without code changes
- ✅ Version control your thresholds
- ✅ Complete example: `docs/mysql-health-checks.example.yaml`

**Example: Strict production thresholds**
```yaml
# Production: Zero tolerance for issues
checks:
  - name: "Table Scan Ratio"
    pass_threshold: 5   # Default: 10
    warn_threshold: 10  # Default: 25
```

**Example: Permissive development thresholds**
```yaml
# Dev: More lenient
checks:
  - name: "Table Scan Ratio"
    pass_threshold: 25   # Default: 10
    warn_threshold: 50   # Default: 25
```

**Why it matters:**
- Production DBAs can enforce stricter standards
- Development teams can avoid false alarms
- CI/CD can use different thresholds per environment
- No need to fork/modify reveal source code

### ✨ NEW: MySQL DBA Tuning Ratios

**Added 5 critical DBA tuning metrics to MySQL adapter** - now exceeds pt-mysql-summary coverage for most use cases!

The MySQL adapter now includes industry-standard tuning ratios found in every MySQL DBA guide and professional monitoring tool (Percona Toolkit, Datadog, PMM):

**Performance Element Enhancements:**

1. **Full table scan detection** ⭐⭐⭐
   - `select_scan_ratio`: Percentage of queries without indexes
   - `handler_read_rnd_next`: Sequential read counter
   - Status indicators: ✅ <10%, ⚠️ <25%, ❌ ≥25%
   - Note: "High scan ratio (>25%) indicates missing indexes"

2. **Thread cache efficiency** ⭐⭐⭐
   - `miss_rate`: Thread cache miss percentage
   - Threads created vs total connections ratio
   - Status indicators: ✅ <10%, ⚠️ <25%, ❌ ≥25%
   - Note: "Miss rate >10% suggests increasing thread_cache_size"

3. **Temp tables on disk ratio** ⭐⭐⭐
   - `disk_ratio`: Percentage of temp tables created on disk
   - On-disk vs total temp tables created
   - Status indicators: ✅ <25%, ⚠️ <50%, ❌ ≥50%
   - Note: "Ratio >25% suggests increasing tmp_table_size or max_heap_table_size"

**Health Overview Enhancements:**

4. **Max used connections** ⭐⭐
   - `max_used_ever`: Historical peak connection count
   - `max_used_pct`: Peak as percentage of max_connections
   - Status indicator: ⚠️ if ever reached 100% (connections were rejected)
   - Shows if connection limit was ever hit since server start

5. **Open files limit** ⭐⭐
   - `resource_limits.open_files`: Current vs limit tracking
   - Status indicators: ✅ <75%, ⚠️ <90%, ❌ ≥90%
   - Note: "Approaching limit (>75%) can cause 'too many open files' errors"
   - Prevents production outages from file descriptor exhaustion

**Example Output:**

```bash
reveal mysql://localhost/performance
```

```json
{
  "full_table_scans": {
    "select_scan_ratio": "58.25%",
    "status": "❌",
    "note": "High scan ratio (>25%) indicates missing indexes"
  },
  "thread_cache_efficiency": {
    "miss_rate": "0.12%",
    "status": "✅",
    "note": "Miss rate >10% suggests increasing thread_cache_size"
  },
  "temp_tables": {
    "disk_ratio": "1.11%",
    "status": "✅",
    "note": "Ratio >25% suggests increasing tmp_table_size"
  }
}
```

**Industry Comparison:**

With these additions, Reveal's MySQL adapter now:
- ✅ **Exceeds pt-mysql-summary** in tuning ratio coverage
- ✅ **Matches Datadog/PMM** for essential DBA metrics
- ✅ **Maintains advantages**: Progressive disclosure (1,132x token reduction), time context accuracy, integrated index/slow query analysis

**Production Validated:**
- Tested on production database (175GB, 77 days uptime, 51M+ rows)
- Correctly identified: 58% table scan ratio (needs indexes), 0.12% thread cache miss (excellent), 1.1% temp tables on disk (excellent)

### ✨ NEW: MySQL --check Flag with Health Thresholds

**Production-ready health validation** - Automated MySQL health checks with pass/warn/fail thresholds!

The MySQL adapter now supports `reveal mysql://host --check` with 7 industry-standard health checks:

**Health Checks:**
1. **Table Scan Ratio** (high severity) - Pass: <10%, Warn: <25%, Fail: ≥25%
2. **Thread Cache Miss Rate** (medium) - Pass: <10%, Warn: <25%, Fail: ≥25%
3. **Temp Disk Ratio** (medium) - Pass: <25%, Warn: <50%, Fail: ≥50%
4. **Max Used Connections %** (critical) - Pass: <80%, Warn: <100%, Fail: ≥100%
5. **Open Files %** (critical) - Pass: <75%, Warn: <90%, Fail: ≥90%
6. **Current Connection %** (high) - Pass: <80%, Warn: <95%, Fail: ≥95%
7. **Buffer Hit Rate** (high) - Pass: >99%, Warn: >95%, Fail: ≤95%

**Exit Codes:**
- 0: All checks passed ✅
- 1: Some warnings ⚠️
- 2: One or more failures ❌

**Example:**
```bash
reveal mysql://localhost --check

MySQL Health Check: ✅ PASS
Summary: 7/7 passed, 0 warnings, 0 failures

✅ All Checks Passed:
  • Table Scan Ratio: 5.20% (threshold: <10%)
  • Thread Cache Miss Rate: 2.10% (threshold: <10%)
  • Temp Disk Ratio: 10.50% (threshold: <25%)
  • Max Used Connections %: 50.00% (threshold: <80%)
  • Open Files %: 10.00% (threshold: <75%)
  • Current Connection %: 5.00% (threshold: <80%)
  • Buffer Hit Rate: 99.90% (threshold: >99%)

Exit code: 0
```

**JSON Output for CI/CD:**
```bash
reveal mysql://localhost --check --format=json
```

### 🔧 IMPROVED: MySQL Adapter Code Quality

**Complete P0 fixes for production readiness:**

1. **Fixed bare except clauses** - Changed `except:` to `except Exception as e:` with error capture
   - Line 411: Replication detection now includes error in return dict
   - Line 896: Connection cleanup remains silent (standard __del__ pattern)

2. **Comprehensive test suite** - 45 tests with 100% P0 coverage
   - 6 test classes covering initialization, credentials, routing, conversion, errors
   - 6 dedicated check() tests for all threshold scenarios
   - Full mocking strategy - no real MySQL needed

3. **Code excellence metrics:**
   - ✅ No bare except clauses
   - ✅ Error handling with context
   - ✅ Production-validated on 175GB database
   - ✅ Complete test coverage for core functionality

## [0.24.1] - 2025-12-17

### 🐛 Bug Fixes

**Critical: Fixed TypeError when using CLI flags with certain file types**
- Fixed LSP violation where analyzers didn't accept parameters from CLI layer
- All analyzers now properly accept `head`, `tail`, `range`, and `**kwargs`
- Fixes: `reveal file.json --outline` (and similar combinations) no longer crashes

**Affected commands that now work:**
```bash
reveal file.json --outline  # ✅ Previously: TypeError
reveal file.yaml --head 5   # ✅ Previously: TypeError
reveal Dockerfile --tail 3  # ✅ Previously: TypeError
```

### 🔧 Improvements

**Enhanced analyzer architecture:**
- Standardized `get_structure()` signature across all analyzers
- Added V008 validation rule to catch signature violations at dev time
- Updated analyzers: Dockerfile, GDScript, Jupyter, Nginx, TOML, YAML, JSON

**Test coverage:**
- Added integration tests for CLI flags × file type combinations
- Prevents regression of LSP violations in analyzer signatures

### 📚 Documentation

**Why this happened:**
- CLI layer passes universal params (`outline`, `head`, `tail`) to all analyzers
- Some analyzers had narrow signatures that rejected these params
- Unit tests only called analyzers directly (worked), never via CLI (failed)

**The fix:**
- All analyzers now accept: `get_structure(self, head=None, tail=None, range=None, **kwargs)`
- Analyzers implement slicing/outline if meaningful, ignore if not
- V008 check prevents future violations

### ✨ NEW: Stats Adapter - Code Quality Metrics & Hotspot Detection

**Automated code quality analysis and technical debt identification** - find problematic code before it becomes a maintenance burden.

#### New `stats://` Adapter

Analyze codebase metrics and identify quality hotspots automatically:

```bash
# Directory statistics with quality metrics
reveal stats://./src

# Identify quality hotspots (worst files first)
reveal stats://./src --hotspots

# Specific file metrics
reveal stats://./src/app.py

# JSON output for CI/CD integration
reveal stats://./src --format=json | jq '.summary.avg_quality_score'
```

**Metrics Provided:**
- **Lines**: Total, code, comments, empty
- **Elements**: Functions, classes, imports
- **Complexity**: Average, min, max cyclomatic complexity
- **Quality Score**: 0-100 rating based on:
  - Long functions (>100 lines)
  - Deep nesting (>4 levels)
  - High complexity (>10)

**Quality Hotspot Detection (`--hotspots`):**
- Automatically ranks files by quality score (worst first)
- Highlights specific issues (long functions, deep nesting)
- Provides actionable refactoring targets
- CI/CD ready with JSON output

#### Use Cases

**Find Technical Debt:**
```bash
# Identify worst quality files
reveal stats://./src --hotspots

# Set quality baseline in CI/CD
baseline=90.0
current=$(reveal stats://./src --format=json | jq '.summary.avg_quality_score')
if (( $(echo "$current < $baseline" | bc -l) )); then
    echo "Quality dropped: $current < $baseline"
    exit 1
fi
```

**Guided Refactoring:**
```bash
# 1. Find hotspots
reveal stats://./src --hotspots

# 2. Check specific file details
reveal stats://./src/problem.py

# 3. View code structure
reveal ./src/problem.py --outline

# 4. Refactor and verify improvement
# ... make changes ...
reveal stats://./src/problem.py  # Check new score
```

**Codebase Health Dashboard:**
```bash
# Overall statistics
reveal stats://./src

# Example output:
# Files: 42
# Total lines: 12,458
# Code lines: 8,234 (66.1%)
# Functions: 187
# Classes: 34
# Avg complexity: 3.2
# Quality score: 87.5/100
```

#### Files Added
- `reveal/adapters/stats.py` - Stats adapter implementation (570 lines)
- `reveal/tests/test_stats_adapter.py` - Comprehensive tests (23 tests, all passing)

#### Files Modified
- `reveal/cli/parser.py` - Added `--hotspots` flag
- `reveal/adapters/__init__.py` - Registered stats:// adapter
- `reveal/cli/routing.py` - Stats CLI handler

#### Dogfooding Success

**Real-world validation:** Used stats adapter on reveal's own codebase:
- Identified `nginx.py` analyzer as worst hotspot (32.2/100 quality score)
- Guided refactoring: extracted 6 helper methods, reduced complexity
- Result: Improved from 32.2/100 → 93.8/100 (+192%)
- Added 16 comprehensive tests with 97% coverage
- Overall reveal quality improved: 95.2/100 → 95.7/100

### ✨ NEW: Link Validation Rules (Track 4 Phase 1)

**Native link validation for documentation workflows** - detect broken links in Markdown files.

#### New Quality Rules (L-series)

**L001: Broken Internal Links**
- Detects broken relative filesystem links in Markdown
- Validates `./file.md`, `../path/file.md` patterns
- Provides helpful fix suggestions (case mismatches, missing extensions)
- Handles anchor links `#heading` gracefully
- Example: `reveal docs/README.md --check --select L`

**L002: Broken External Links**
- Validates external HTTP/HTTPS URLs
- Uses HTTP HEAD requests (5s timeout)
- Handles various HTTP errors (404, 403, 500, etc.)
- Suggests common fixes (http→https, add www, etc.)
- Lower severity (external links can be transient)
- Example: `reveal docs/ --recursive --check --select L002`

**L003: Framework Routing Mismatches**
- Validates framework-specific routing conventions
- Auto-detects framework (FastHTML, Jekyll, Hugo, static)
- FastHTML: `/path/FILE` → `docs/path/FILE.md` (case-insensitive)
- Jekyll: Checks `_posts/` directory and permalinks
- Hugo: Validates `content/` directory and `index.md` files
- Example: `reveal docs/foundations/ --check --select L003`

#### New Feature: Recursive Directory Checking

**`--recursive` / `-r` flag**
- Process all files in directory tree
- Respects `.gitignore` patterns
- Skips common directories (`.git`, `node_modules`, `__pycache__`)
- Aggregated output with summary
- Exit code 0 (success) or 1 (issues found)
- Example: `reveal docs/ --recursive --check --select L`

**Output format:**
```
foundations/SIL_GLOSSARY.md: Found 2 issues

foundations/SIL_GLOSSARY.md:88:1 ⚠️  L001 Broken internal link: ./missing.md
  💡 File not found - verify path is correct
  📝 [Guide](./missing.md)

============================================================
Checked 8 files
Found 2 issues in 1 file
```

#### Use Cases

**CI/CD Integration:**
```bash
# Validate all docs before deploy
reveal docs/ --recursive --check --select L
```

**Link Quality Checks:**
```bash
# Check only internal links
reveal docs/ -r --check --select L001

# Check everything including external URLs
reveal docs/ -r --check --select L
```

**Framework-Aware Validation:**
```bash
# FastHTML project - validates web routes
reveal docs/ -r --check --select L003
```

#### Files Added
- `reveal/rules/links/L001.py` - Internal link validation (182 lines)
- `reveal/rules/links/L002.py` - External link validation (204 lines)
- `reveal/rules/links/L003.py` - Framework routing validation (312 lines)
- `reveal/rules/base.py` - Added `L` prefix for link rules

#### Files Modified
- `reveal/cli/parser.py` - Added `--recursive` flag
- `reveal/cli/routing.py` - Added recursive directory checking

### 🎯 REDESIGNED: Help System (AI Agent Focused)

**Major improvements to reveal's help system** - designed for realistic AI agent usage patterns.

#### What Changed

**`--agent-help` (AI Agent Reference)**
- **Task-oriented**: "When you need to do X, use Y" patterns (not exploration hints)
- **Example-heavy**: Concrete, working commands for every task
- **Realistic**: Written for how AI agents actually behave (like Claude Code)
- **Real-world scenarios**: Bug investigation, PR review, environment debugging, etc.
- **No exploration prompts**: Direct patterns instead of "discover with help://"
- **Token cost**: ~2,200 tokens (updated estimate)

**`help://` (Progressive Discovery)**
- **Source attribution**: All topics show where content comes from
  - Dynamic: "ast.py adapter (dynamic)"
  - Static: "File: AGENT_HELP.md | Token cost: ~2,200"
- **Categorized index**: Organized by source type (Dynamic/Static/Special)
- **Token costs**: Estimates shown for AI agents
- **Clear organization**: AI Agents, Feature Guides, Best Practices, Development
- **Navigation tips**: Better discoverability

**New: `help://help`**
- Meta-documentation explaining the three-tier help system
- Design principles and architecture
- How to add new help content
- Troubleshooting guide

#### Files Modified

- `reveal/AGENT_HELP.md` - Completely redesigned with task-based patterns
- `reveal/rendering/adapters/help.py` - Enhanced with source attribution
- `reveal/adapters/help.py` - Added HELP_SYSTEM_GUIDE.md mapping
- `reveal/HELP_SYSTEM_GUIDE.md` - **New** meta-documentation

#### Design Philosophy

**Three-tier system with clear separation:**
1. `--help` - CLI reference (humans typing commands)
2. `--agent-help` - Task patterns (AI agents, llms.txt standard)
3. `help://` - Progressive discovery (both humans and agents)

**Key insight**: AI agents don't "explore" help systems - they need direct, actionable patterns.

#### Examples

**Before (exploration-based):**
```markdown
## Progressive Discovery Pattern
1. Discover what's available: reveal help://
2. Learn about specific capability: reveal help://ast
3. Use it
```

**After (task-based):**
```markdown
### Task: "Find where X is implemented"

**Pattern:**
```bash
reveal 'ast://./src?name=*authenticate*'
```

**Why this works:** AST queries don't require reading files.
```

### Benefits

- **For AI agents**: Get working patterns immediately (no discovery needed)
- **For humans**: Clear source attribution (know where help comes from)
- **For developers**: Easy to add new help (auto-discovery + clear docs)
- **Token efficiency**: Estimate costs shown for all guides

## [0.23.1] - 2025-12-14

### Fixed
- **stdlib collision**: Renamed `reveal/types/` to `reveal/schemas/` to avoid conflict with Python's `types` module
- **--check flag for reveal://**: V-series validation rules now execute correctly (were dead code)
- **--check warnings**: URI adapters (python://, json://, ast://, env://, help://) now warn when --check is unsupported instead of silently ignoring
- **Stale tests**: Removed 22 failing tests that tested removed API surface in Python adapter

### Changed
- Updated README architecture diagram to reflect `schemas/` rename

## [0.23.0] - 2025-12-14

### 🏗️ NEW: Type-First Architecture with `--typed` Flag

**Reveal now supports typed, navigable code structures with containment relationships!**

```bash
reveal app.py --typed            # See hierarchical structure with containment
reveal app.py --typed --format=json   # Full typed structure as JSON
```

**What's Included:**
- ✅ `--typed` flag for type-aware output showing parent/child relationships
- ✅ `TypedStructure.from_analyzer_output()` factory for programmatic use
- ✅ `TypedElement` base class with `.parent`, `.children`, `.walk()` navigation
- ✅ `PythonElement` specialized class with `.decorators`, `.is_property`, `.is_staticmethod`, etc.
- ✅ **Decorator extraction** from Python functions and classes via TreeSitter
- ✅ Containment computed from line ranges + EntityDef rules
- ✅ Path navigation: `structure / 'MyClass' / 'method'`
- ✅ Query methods: `structure.find(category='function')`, `find_by_line(42)`

**Example Output:**
```bash
reveal mymodule.py --typed

File: mymodule.py (5.2KB, 150 lines)
Type: python
Elements: 15 (3 roots)

@dataclass Config (class) [1-5]
MyClass (class) [10-80]
  __init__(self, name) (method) [15-25]
  @property name() (property) [28-31]
  @staticmethod helper() (staticmethod) [33-40]
  process(data) → Result (method) [45-60]
    _inner_helper() (function) [50-55]   # Nested function visible!
standalone_func(x, y) → int (function) [85-100]
```

**Rich Output Features:**
- ✅ **Decorator extraction**: Shows `@property`, `@staticmethod`, `@classmethod`, `@dataclass`, etc.
- ✅ **Function signatures**: Parameters and return types displayed
- ✅ **Semantic categories**: Methods, properties, staticmethods distinguished from plain functions
- ✅ **Line counts**: Shows line count for longer elements (e.g., `94 lines`)

**Programmatic Usage:**
```python
from reveal.structure import TypedStructure

# Convert raw analyzer output to typed structure
typed = TypedStructure.from_analyzer_output(raw_dict, 'app.py')

# Navigate
my_class = typed / 'MyClass'
for method in my_class.children:
    print(f"{method.name} at line {method.line}")

# Query
nested = list(typed.find(lambda el: el.depth > 1))
```

### 🎯 IMPROVED: Size Disclosure & LLM-Friendly Quality Checks

**Reveal now shows file size and line count in headers, preventing surprise large reads!**

```bash
reveal main.py
# Output: File: main.py (42.3KB, 1,247 lines)
```

**New --check Rules for Size-Based Quality:**
- ✅ **C902**: Function too long (warns >50 lines, errors >100 lines)
- ✅ **C905**: Nesting depth too high (errors >4 levels)
- ✅ **M101**: File too large (warns >500 lines, errors >1000 lines)

**Benefits:**
- **Size Awareness**: See file dimensions before loading content (prevents LLM token bloat)
- **God Function Detection**: Catch unmaintainable functions early
- **Deep Nesting Alerts**: Identify complex control flow (callback hell, nested conditionals)
- **Token Cost Estimates**: M101 shows estimated LLM token cost for large files

**Example --check Output:**
```bash
reveal massive.py --check

massive.py: Found 2 issues

massive.py:1:1 ❌ M101 File is too large (1,247 lines, 42.3KB)
  💡 LLM cost: ~18,500 tokens to load entire file.
      Use 'reveal massive.py' (structure view) instead.

massive.py:45:1 ❌ C902 Function is too long: process_everything (342 lines)
  💡 Break into smaller functions. Single function costs ~5,100 tokens.
```

### 📝 NEW: YAML Front Matter Extraction for Markdown

**Reveal can now extract and display YAML front matter from markdown files!** This feature integrates seamlessly with Beth and TIA's semantic infrastructure.

```bash
reveal README.md --frontmatter                    # Extract front matter metadata
reveal README.md --frontmatter --format=json      # Full metadata as JSON
```

**What's Supported:**
- ✅ YAML front matter parsing (---delimited blocks)
- ✅ Beth-specific fields (`beth_topics`, `session_id`, `tags`, `related_docs`)
- ✅ Nested structures and complex YAML
- ✅ Text and JSON output formats
- ✅ Graceful error handling for malformed YAML
- ✅ Line range tracking (shows which lines contain front matter)

**Use Cases:**
- **Metadata Validation**: Audit front matter consistency and completeness across documentation
- **Static Site Generation**: Extract metadata for navigation, indexes, and bibliographies
- **Documentation Analysis**: Aggregate metadata from project documentation
- **CI/CD Validation**: Ensure required metadata fields are present in pull requests
- **Semantic Search Integration**: Extract topic metadata for knowledge graph indexing

**Example Output (Text):**
```
Frontmatter (6):
  Lines 1-12:
    title: Feature Implementation Report
    author: Development Team
    date: 2025-12-13
    tags:
      - feature
      - testing
      - documentation
    category: development
    version: 1.0
```

**Example Output (JSON):**
```json
{
  "frontmatter": {
    "data": {
      "title": "Feature Implementation Report",
      "author": "Development Team",
      "date": "2025-12-13",
      "tags": ["feature", "testing", "documentation"]
    },
    "line_start": 1,
    "line_end": 12,
    "raw": "title: Feature Implementation Report\nauthor: ..."
  }
}
```

**Implementation:**
- `reveal/analyzers/markdown.py`: Added `_extract_frontmatter()` method and `extract_frontmatter` parameter
- `reveal/main.py`: Added `--frontmatter` CLI flag, text/JSON formatters, help text
- `tests/test_markdown_analyzer.py`: 9 comprehensive tests covering nested structures, error handling, edge cases
- All tests passing (28/28 markdown analyzer tests)

**Real-World Example:**
The Semantic Infrastructure Lab uses reveal's front matter extraction for their Beth knowledge graph system. [Learn more about the integration](https://semanticinfrastructurelab.org/docs/canonical/REVEAL_BETH_PROGRESSIVE_KNOWLEDGE_SYSTEM).

**Impact**: Enables metadata extraction from markdown documentation for validation, aggregation, and semantic indexing use cases.

### 🐛 FIXED: JSON Serialization for Date Objects

**Fixed a bug where JSON output failed when YAML front matter contained date fields.**

**Problem:**
- YAML auto-parses date fields (e.g., `date: 2025-12-13`) into Python `datetime.date` objects
- Python's standard `json.dumps()` cannot serialize date/datetime objects
- This caused `TypeError: Object of type date is not JSON serializable` when using `--frontmatter --format=json`

**Solution:**
- Added custom `DateTimeEncoder` class that serializes dates as ISO format strings
- Created `safe_json_dumps()` helper function used throughout reveal
- All JSON output now handles date/datetime objects gracefully

**Example:**
```bash
# Previously failed with TypeError
reveal README.md --frontmatter --format=json

# Now works - dates serialize as ISO strings
{
  "frontmatter": {
    "data": {
      "date": "2025-12-13",           # ✅ Serialized as string
      "created": "2025-12-10",         # ✅ ISO format
      "session_id": "stormy-gust-1213"
    }
  }
}
```

**Files modified:**
- `reveal/main.py`: Added `DateTimeEncoder` class and `safe_json_dumps()` helper (20 lines)
- Replaced 13 instances of `json.dumps()` with `safe_json_dumps()`

**Testing:**
- ✅ Tested on TIA session READMEs with date fields
- ✅ Tested on SIL documentation with created/updated dates
- ✅ All 372 tests passing
- ✅ No regressions

### 🔍 NEW: reveal:// Meta-Adapter - Self-Inspection System

**Reveal can now inspect itself!** The new `reveal://` adapter demonstrates that reveal can explore **any resource**, not just files.

```bash
reveal reveal://                    # Inspect reveal's structure
reveal reveal:// --check            # Self-validation (V001-V007 rules)
reveal help://reveal                # Learn about reveal:// adapter
```

**Why this matters:**
- **Proves extensibility**: Reference implementation for custom adapters (APIs, databases, containers)
- **Marketing value**: "Reveal validates itself using its own tools" (dogfooding in action)
- **Quality forcing function**: Self-validation catches real issues before users see them

**New files:**
- `reveal/adapters/reveal.py` (291 lines) - Meta-adapter implementation
- `reveal/REVEAL_ADAPTER_GUIDE.md` (521 lines) - Complete guide with examples (project://, api://, docker://)
- `reveal/MARKDOWN_GUIDE.md` (654 lines) - Comprehensive markdown analysis guide
- `docs/REVEAL_SELF_AUDIT_2025-12-11.md` (333 lines) - Full self-audit report

**Total**: 20 files modified/created, 3,719 lines added

### 📋 NEW: V-Series Validation Rules (V001-V007)

**7 new validation rules** for reveal's internal quality assurance:

| Rule | Severity | Description |
|------|----------|-------------|
| **V001** | MEDIUM | Help documentation completeness for all adapters |
| **V002** | HIGH | Analyzer registration validation (prevents silent failures) |
| **V003** | MEDIUM | Feature matrix coverage (outline, element extraction) |
| **V004** | LOW | Test coverage gaps for analyzers |
| **V005** | HIGH | Static help file sync with STATIC_HELP registry |
| **V006** | MEDIUM | Output format support (text, JSON, grep, typed) |
| **V007** | HIGH | Version consistency (pyproject.toml vs CHANGELOG/docs) |

**Impact**: V001-V007 all passing (0 issues) after dogfooding fixes

**New files:**
- `reveal/rules/validation/V001.py` through `V007.py` (~1,000 lines total)
- Integrated with `reveal reveal:// --check` command

### 🔍 NEW: Duplicate Detection Rules (D001-D002)

**Detect code duplication** with exact and structural similarity matching:

```bash
reveal src/ --check --select D       # Find duplicates
reveal app.py --check --select D001  # Exact duplicates only
reveal app.py --check --select D002  # Structural similarity
```

**D001 - Exact Duplicate Detection:**
- Identifies identical function/class implementations
- Ignores whitespace and comments
- Reports all duplicate groups with locations

**D002 - Structural Similarity Detection:**
- AST-based similarity matching (adjustable threshold)
- Mathematical similarity algorithms
- Detects refactoring opportunities

**New files:**
- `reveal/rules/duplicates/D001.py` (184 lines)
- `reveal/rules/duplicates/D002.py` (217 lines)
- `reveal/rules/duplicates/base_detector.py` (414 lines) - Universal framework
- `scripts/analyze_duplicate_detection.py` (307 lines) - Statistical analysis tool

**Documentation** (105KB across 4 files):
- `internal-docs/planning/DUPLICATE_DETECTION_DESIGN.md` (606 lines) - Architecture
- `internal-docs/planning/DUPLICATE_DETECTION_GUIDE.md` (542 lines) - User guide
- `internal-docs/planning/DUPLICATE_DETECTION_OPTIMIZATION.md` (510 lines) - Mathematical framework
- `internal-docs/planning/DUPLICATE_DETECTION_OVERVIEW.md` (437 lines) - Visual overview

### 🌲 IMPROVED: TOML Outline Support

**TOML files now support hierarchical outline mode!**

```bash
reveal config.toml --outline
```

**Features:**
- Level-based hierarchy from dot-notation (`database.connection.pool`)
- Tree structure display (like markdown headings)
- Proper nesting for complex configurations

**Modified files:**
- `reveal/analyzers/toml.py` - Added `outline` parameter to `get_structure()`
- `reveal/main.py` - Added `build_heading_hierarchy()` for TOML sections

### 🔧 IMPROVED: Main Module Refactoring

**Reduced `reveal/main.py` complexity** through systematic extraction:

**Phase 1:** Extract `_main_impl` into smaller functions (246→40 lines)
- `_create_argument_parser()` - Argument parsing
- `_handle_list_supported()`, `_handle_agent_help()` - Special mode handlers
- `_handle_stdin_mode()` - Stdin processing
- `_handle_file_or_directory()` - File/directory handling
- **Complexity**: Depth 5 → Depth 2

**Phase 2:** Extract rendering functions
- `render_help()` - Help text rendering (212 lines → extracted)
- `render_python_element()` - Python element rendering (173 lines → extracted)

**Phase 4-5:** Extract Python adapter helpers
- `_get_module_analysis()` - Module conflict detection
- `_run_doctor()` - Diagnostic execution
- Added comprehensive test coverage for extracted functions

**Impact**: Improved testability, readability, and maintainability

**Modified files:**
- `reveal/main.py` (460 lines changed across 3 commits)

### 📚 NEW: Documentation Infrastructure

**Comprehensive planning and structure documentation:**

**Core Guides:**
- `internal-docs/DOCUMENTATION_STRUCTURE_GUIDE.md` (569 lines) - Two-tier doc organization
- `internal-docs/planning/PENDING_WORK.md` (389 lines) - Master index of pending work
- `internal-docs/planning/README.md` (135 lines) - Active/shipped/archived plans index

**Planning Documents:**
- `internal-docs/planning/PYTHON_ADAPTER_ROADMAP.md` (726 lines)
- `internal-docs/planning/PYTHON_ADAPTER_SPEC.md` (845 lines)
- `internal-docs/planning/NGINX_ADAPTER_ENHANCEMENTS.md` (424 lines)
- `internal-docs/planning/CODE_QUALITY_ARCHITECTURE.md` (439 lines)
- `internal-docs/planning/CODE_QUALITY_REFACTORING.md` (381 lines)

**Engineering Review:**
- `docs/REVEAL_ENGINEERING_REVIEW_2025-12-12.md` (425 lines) - Comprehensive audit
  - Quality score: 22/100 (intentional technical debt)
  - Architecture: 9/10, Documentation: 10/10, SIL Alignment: 10/10
  - Verdict: Ship-ready for SIL showcase

**Total**: 13 documentation files added (105.6KB)

### ✅ Test Coverage Complete (V004 → Zero Issues)

**Added comprehensive test suites for 4 previously untested analyzers:**

- `tests/test_rust_analyzer.py` - Rust analyzer with functions, structs, impls, traits (6 tests)
- `tests/test_go_analyzer.py` - Go analyzer with functions, structs, interfaces, methods (6 tests)
- `tests/test_gdscript_analyzer.py` - GDScript analyzer with Godot patterns (7 tests)
- `tests/test_yaml_json_analyzer.py` - YAML/JSON analyzers with UTF-8 support (8 tests)

**Total**: 27 new test cases, 363 tests passing (100% pass rate)

**Impact**: V004 validation issue count: 4 → 0 (complete test coverage for all TreeSitter analyzers)

### 🚀 CI Enhancement: Self-Validation in GitHub Actions

**Added `reveal reveal://` self-validation step to CI workflow:**

```yaml
- name: Reveal self-validation (dogfooding)
  run: python validation script  # Runs V001-V007 checks
```

**Impact**: Every push now validates reveal's internal quality (analyzers, tests, docs, version consistency)

### 🔧 Fixes

- Updated `AGENT_HELP.md` version reference: 0.19.0 → 0.22.0
- Updated `AGENT_HELP_FULL.md` version reference: 0.17.0 → 0.22.0
- Fixed `.gitignore` patterns to allow `internal-docs/` while excluding session artifacts
- Fixed TOML analyzer to support outline mode
- Fixed markdown analyzer bugs (documented in `docs/ROOT_CAUSE_ANALYSIS_MARKDOWN_BUGS.md`)

### 📊 Quality Metrics

- **Test suite**: 363 tests passing (+27 new tests)
- **Coverage**: 63% overall
- **Quality rules**: 18 total (10 new: V001-V007, D001-D002)
- **URI adapters**: 6 (1 new: reveal://)
- **Validation issues**: 0 (V001-V007 all passing)
- **CI checks**: Self-validation now runs on every push
- **Code complexity**: main.py depth 5 → 2
- **Documentation**: 105.6KB planning docs added
- **Lines changed**: 11,575+ across 8 commits

### 🎯 NEW: Decorator-Aware Code Intelligence

**Reveal now understands decorators semantically — query by decorator, detect decorator-related bugs, and analyze decorator usage across your codebase.**

#### New Bug Detection Rules (B002-B004)

Three new rules catch common decorator-related bugs:

```bash
reveal app.py --check --select B

# B002: @staticmethod 'process' has 'self' parameter
#       Either remove @staticmethod or remove 'self'

# B003: @property 'config' is 15 lines (max 8)
#       Properties should be simple getters

# B004: @property 'value' has no return statement (will return None)
#       Add a return statement or convert to a method
```

| Rule | Description | Severity |
|------|-------------|----------|
| B002 | `@staticmethod` with `self` parameter | HIGH |
| B003 | `@property` too complex (>8 lines) | MEDIUM |
| B004 | `@property` without return statement | HIGH |

#### AST Decorator Query

Query code by decorator pattern using the `ast://` adapter:

```bash
# Find all properties
reveal 'ast://.?decorator=property'

# Find all cached functions (wildcard matching)
reveal 'ast://.?decorator=*cache*'

# Find all abstract methods
reveal 'ast://.?decorator=abstractmethod'

# Combine with other filters - find complex properties (code smell)
reveal 'ast://.?decorator=property&lines>10'
```

#### Category Filtering (`--filter`)

Filter `--typed` output by semantic category:

```bash
reveal app.py --typed --filter=property       # Only properties
reveal app.py --typed --filter=staticmethod   # Only static methods
reveal app.py --typed --filter=class          # Only classes
```

#### Decorator Statistics (`--decorator-stats`)

Analyze decorator usage across your codebase:

```bash
reveal src/ --decorator-stats

# Standard Library Decorators:
#   @property                        13 occurrences (2 files)
#   @staticmethod                    11 occurrences (8 files)
#   @lru_cache                        5 occurrences (3 files)
#
# Custom/Third-Party Decorators:
#   @register                        23 occurrences (16 files)
#   @validate                         8 occurrences (4 files)
#
# Summary:
#   Total decorators: 94
#   Files with decorators: 30/98 (30%)
```

### 📊 Quality Metrics

- **Tests**: 401 passing (up from 363)
- **New rules**: B002, B003, B004
- **New CLI flags**: `--typed`, `--filter`, `--decorator-stats`
- **AST adapter**: Extended with `decorator=` filter

## [0.22.0] - 2025-12-11

### 🔍 NEW: Editable Install Conflict Detection

**`reveal python://doctor` now detects editable install conflicts that can cause version confusion.**

This was added after a real debugging session where `pip install reveal-cli==0.21.0` kept loading v0.20.0 due to stale `.pth` files.

```bash
reveal python://doctor

# New detections:
⚠️  [editable_conflict] Multiple editable .pth files for 'mypackage'
    Impact: Version conflicts - imports may load unexpected version

⚠️  [editable_shadow] Editable 'mypackage' may shadow PyPI install
    Impact: pip install from PyPI won't take effect
```

**New checks:**
- **Duplicate .pth files**: Detects when multiple `__editable__.<pkg>-<version>.pth` files exist for the same package
- **Editable shadowing PyPI**: Warns when an editable install exists alongside a PyPI dist-info

**Recommendations provided:**
```bash
rm ~/.local/lib/python*/site-packages/__editable__.*mypackage*
pip install mypackage --force-reinstall
```

## [0.21.0] - 2025-12-11

### 📄 NEW: Office Document Support (6 Formats)

**Analyze Word, Excel, PowerPoint, and LibreOffice documents with reveal!**

```bash
reveal document.docx           # Word: sections, tables, word count
reveal spreadsheet.xlsx        # Excel: sheets with dimensions, formulas
reveal presentation.pptx       # PowerPoint: slides with titles

reveal document.odt            # LibreOffice Writer
reveal spreadsheet.ods         # LibreOffice Calc
reveal presentation.odp        # LibreOffice Impress
```

**Features:**
- **Zero new dependencies** - pure Python stdlib (`zipfile` + `xml.etree`)
- **Semantic extraction** - extract sections by heading, sheets by name, slides by number
- **Progressive disclosure** - overview first, then drill into details
- **Both format families** - Microsoft OpenXML (.docx/.xlsx/.pptx) and ODF (.odt/.ods/.odp)

**New analyzers:**
| Format | Extension | Analyzer |
|--------|-----------|----------|
| Word | `.docx` | DocxAnalyzer |
| Excel | `.xlsx` | XlsxAnalyzer |
| PowerPoint | `.pptx` | PptxAnalyzer |
| Writer (ODF) | `.odt` | OdtAnalyzer |
| Calc (ODF) | `.ods` | OdsAnalyzer |
| Impress (ODF) | `.odp` | OdpAnalyzer |

**Architecture:** Shared `ZipXMLAnalyzer` base class handles ZIP archive operations and XML parsing. Format-specific subclasses know the XML schemas for each format family.

```bash
reveal document.docx "Introduction"    # Extract section by heading
reveal spreadsheet.xlsx Sheet1         # Extract sheet with data preview
reveal presentation.pptx 3             # Extract slide by number
```

### 🧪 Test Coverage Improvements

**Coverage increased from 56% to 65%** with 95 new tests across 5 test files.

| Module | Before | After |
|--------|--------|-------|
| `jupyter_analyzer.py` | 7% | 78% |
| `markdown.py` | 12% | 96% |
| `jsonl.py` | 12% | 89% |
| `tree_view.py` | 10% | 87% |
| Rules (B001, C901, R913, S701) | 35-47% | 92-100% |

**New test files:**
- `test_jupyter_analyzer.py` - 14 tests
- `test_markdown_analyzer.py` - 22 tests
- `test_jsonl_analyzer.py` - 18 tests
- `test_tree_view.py` - 14 tests
- `test_rules.py` - 27 tests
- `test_office_analyzers.py` - 26 tests (office document support)

### 🐛 Bug Fixes

- Fixed broken internal links in README.md pointing to `COOL_TRICKS.md`

## [0.20.0] - 2025-12-11

### 📚 NEW: Enhanced Help System with Workflows, Examples & Anti-Patterns

**The help system now teaches reveal methodology, not just syntax!**

Each adapter's help now includes three new sections:

```bash
reveal help://ast              # Full help with new sections
reveal help://ast/workflows    # Extract just workflows
reveal help://ast/try-now      # Extract just executable examples
reveal help://ast/anti-patterns # Extract just do/don't comparisons
```

**New sections in adapter help:**

| Section | Purpose | Example |
|---------|---------|---------|
| `Try Now` | Executable examples for your cwd | `reveal 'ast://.?complexity>5'` |
| `Workflows` | Scenario-based patterns | "Find Refactoring Targets" with step-by-step |
| `Don't Do This` | Bad/good/why comparisons | `grep -r` vs `reveal ast://` |

**Adapters enhanced:**
- `ast://` - Find Refactoring Targets, Explore Unknown Codebase, Pre-PR Review
- `python://` - Debug 'My Changes Aren't Working', Wrong Package Version, Environment Health Check
- `json://` - Explore Unknown JSON, Schema Discovery, Extract Nested Data
- `env://` - Debug Missing Variables, Compare Environments

**Section extraction for token efficiency:**

```bash
reveal help://ast/workflows       # ~30 lines (just workflows)
reveal help://ast                 # ~100 lines (full help)
```

Each extracted section includes a "See Full Help" breadcrumb pointing back to the complete documentation.

**Impact:** Progressive disclosure now applies to the help system itself - learn what you need, when you need it.

## [0.19.0] - 2025-12-09

### 📋 NEW: Clipboard Integration (`--copy` / `-c`)

**Copy reveal output directly to clipboard!** Cross-platform support with zero dependencies.

```bash
reveal app.py --copy              # Copy structure to clipboard
reveal app.py load_config -c      # Copy extracted function
reveal nginx.conf --check --copy  # Copy check results
```

**Features:**
- Tee behavior: Output displays AND copies to clipboard
- Cross-platform: Linux (xclip/xsel/wl-copy), macOS (pbcopy), Windows (clip)
- No new dependencies (uses native clipboard utilities)
- Feedback on stderr: "📋 Copied N chars to clipboard"

### 🔧 NEW: Nginx Configuration Rules (N001-N003)

**Catch nginx misconfigurations before they cause production incidents!**

```bash
reveal nginx.conf --check              # Run all nginx checks
reveal nginx.conf --check --select N   # Only nginx rules
```

**New rules:**
- **N001** (HIGH): Duplicate backend detection - catches when multiple upstreams share the same server:port
- **N002** (CRITICAL): Missing SSL certificate - catches `listen 443 ssl` without certificate directives
- **N003** (MEDIUM): Missing proxy headers - catches `proxy_pass` without `X-Real-IP`, `X-Forwarded-For`

**Background:** These rules were inspired by a production incident where two nginx upstreams pointed to the same port, causing an $8,619/month revenue site to serve wrong content. N001 catches this exact class of bug.

### 📚 NEW: `help://tricks` Guide

**Cool tricks and hidden features now discoverable!**

```bash
reveal help://tricks    # 560+ lines of advanced workflows
```

Includes: Self-diagnostic superpowers, AST query wizardry, pipeline magic, token efficiency mastery, and more.

### 🎯 NEW: Wildcard Name Patterns in AST Queries

**Find code by pattern!** The `ast://` adapter now supports wildcard patterns in name filters.

```bash
reveal 'ast://.?name=test_*'        # All functions starting with test_
reveal 'ast://src/?name=*helper*'   # Functions containing "helper"
reveal 'ast://.?name=get_?'         # Single character wildcard
```

**Patterns supported:**
- `*` - Match zero or more characters
- `?` - Match exactly one character
- Combine with other filters: `name=test_*&lines>50`

**Impact:** Replaces grep/find workflows with semantic code search (30-60x token reduction)

### 📚 NEW: Comprehensive Help Guides for LLMs and Extension Authors

**Three new discoverable guides (v0.18.0):**

1. **`help://python-guide`** - Python adapter comprehensive guide (links v0.17.0 features)
   - Multi-shot prompting examples (input → output → interpretation)
   - Real-world workflows (debugging, deployment checks)
   - LLM integration patterns
   - 450+ lines of examples

2. **`help://anti-patterns`** - Stop using grep/find!
   - grep/find/cat → reveal equivalents
   - Token savings table (10-150x reduction)
   - 10 common anti-patterns with solutions
   - Decision trees for when to use reveal vs traditional tools

3. **`help://adapter-authoring`** - Create custom adapters
   - Complete schema documentation
   - Best practices for LLM-friendly help
   - Multi-shot prompting patterns
   - Checklist for good help
   - Reference implementations

**Enhanced for extension authors:**
- `base.py` get_help() docstring now 40+ lines with complete schema
- Required/recommended/optional fields clearly marked
- Automatic help discovery - just implement `get_help()`
- Reference to `help://adapter-authoring` guide

### 🔗 NEW: Breadcrumb Improvements

All adapters now include breadcrumbs to related guides:
- AST adapter → `help://anti-patterns` (stop using grep!)
- Python adapter → `help://python-guide` (comprehensive examples)
- ENV adapter → `help://anti-patterns`

**Progressive discovery:** Each help topic guides you to the next resource

### 🗂️ NEW: JSON Adapter (`json://`)

**Navigate and query JSON files with path access, schema discovery, and gron-style output!**

```bash
reveal json://config.json                    # Pretty-print JSON
reveal json://config.json/users/0/name       # Navigate to path
reveal json://config.json/items[-1]          # Negative index
reveal json://config.json/items[0:3]         # Array slicing
reveal json://config.json?schema             # Infer type structure
reveal json://config.json?flatten            # Gron-style output (grep-able)
reveal json://config.json?gron               # Alias for flatten
reveal json://config.json?keys               # List keys/indices
reveal json://config.json?length             # Get length
```

**Features:**
- **Path Navigation**: `/key/subkey/0/field` with array indices and slicing
- **Schema Discovery**: `?schema` infers type structure for large JSON files
- **Gron-Style Output**: `?flatten` or `?gron` produces grep-able assignment syntax
- **Query Operations**: `?type`, `?keys`, `?length` for inspection

### 🔀 NEW: OR Logic for AST Type Filters

**Query multiple types at once!** The `ast://` adapter now supports OR logic in type filters.

```bash
reveal 'ast://.?type=class|function'         # Both classes AND functions
reveal 'ast://.?type=class,function'         # Same, comma separator
reveal 'ast://.?type=class|function&lines>50' # Combined with other filters
```

### 🐛 Fixed: Class Line Count Bug

**Classes now show accurate line counts!** Previously `reveal 'ast://.?type=class'` showed `[0 lines]` for all classes.

**Before:** `AstAdapter [0 lines]`
**After:** `AstAdapter [413 lines]`

**Root cause:** Classes provide `line_end` but not `line_count`, while functions provide both. Now calculated from `line_end - line + 1` when missing.

### 🐛 Fixed: Tilde Expansion in URI Adapters

**Both `ast://` and `json://` now expand `~` to home directory!**

```bash
# Before: "Files scanned: 0" or FileNotFoundError
reveal 'ast://~/src/project?type=class'
reveal 'json://~/config/settings.json'

# After: Works correctly
reveal 'ast://~/src/project?type=class'   # ✓ Expands to /home/user/src/project
reveal 'json://~/config/settings.json'    # ✓ Expands to /home/user/config/settings.json
```

### 🐛 Fixed: `python://doctor` Text Output

**Doctor now shows full diagnostic output in text mode!** Previously only showed "Bytecode Check: HEALTHY" instead of the complete health report.

```bash
reveal python://doctor
# Now shows:
# Python Environment Health: ✓ HEALTHY
# Health Score: 90/100
#
# Warnings (1):
#   ⚠️  [environment] No virtual environment detected
# ...
```

### 🐛 Fixed: Bytecode Checker Smart Defaults

**Bytecode checking now excludes non-user directories by default!** Skips `.cache/`, `.venv/`, `venv/`, `site-packages/`, `node_modules/`, `.git/`, `.tox/`, `.nox/`, `.pytest_cache/`, `.mypy_cache/`, and `*.egg-info/`.

**Before:** 47,457 issues (mostly in cached/vendored code)
**After:** 71 issues (actual stale bytecode in user code)

### 🐍 NEW: Python Runtime Adapter (`python://`)

**Inspect Python runtime environment and debug common issues!** The new `python://` adapter provides runtime inspection capabilities for Python environments, complementing the existing static analysis tools.

**Key Features:**
- **Runtime Environment Inspection** - Python version, implementation, executable path
- **Virtual Environment Detection** - Auto-detect venv, virtualenv, conda
- **Package Management** - List installed packages, get package details
- **Import Tracking** - See currently loaded modules from sys.modules
- **Bytecode Debugging** - Detect stale .pyc files that cause "my changes aren't working" issues
- **Cross-Platform Support** - Works on Linux, macOS, Windows

**Separation of Concerns:**
- `env://` - Raw environment variables (cross-language)
- `ast://` - Static source code analysis (cross-language)
- `python://` - **Python runtime inspection** (Python-specific) ← NEW

**Usage Examples:**
```bash
# Quick environment overview
reveal python://

# Check Python version details
reveal python://version

# Verify virtual environment
reveal python://venv

# List installed packages
reveal python://packages

# Get specific package info
reveal python://packages/requests

# See loaded modules
reveal python://imports

# Debug stale bytecode (fixes "my changes aren't working!")
reveal python://debug/bytecode
```

**Output Example:**
```yaml
version: "3.10.12"
implementation: "CPython"
executable: "/usr/bin/python3"
virtual_env:
  active: true
  path: "/home/user/project/.venv"
packages_count: 47
modules_loaded: 247
platform: "linux"
architecture: "x86_64"
```

**Supported Endpoints:**
- `python://` - Environment overview
- `python://version` - Detailed version information
- `python://env` - Python environment (sys.path, flags, encoding)
- `python://venv` - Virtual environment status
- `python://packages` - List all packages (like `pip list`)
- `python://packages/<name>` - Package details
- **`python://module/<name>`** - 🆕 Module conflict detection (CWD shadowing, pip vs import)
- `python://imports` - Currently loaded modules
- **`python://syspath`** - 🆕 sys.path analysis with conflict detection
- **`python://doctor`** - 🆕 Automated environment diagnostics
- `python://debug/bytecode` - Bytecode issues (stale .pyc files)

**🎯 Enhanced Diagnostic Features:**

**1. Module Conflict Detection (`python://module/<name>`)**
```bash
reveal python://module/mypackage
```
Detects and diagnoses:
- **CWD Shadowing**: Local directory masking installed packages
- **Pip vs Import Mismatch**: Package installed one place, importing from another
- **Editable Installs**: Development installs vs production packages
- **Actionable Recommendations**: Commands to fix detected issues

**2. sys.path Analysis (`python://syspath`)**
```bash
reveal python://syspath
```
Shows:
- Complete sys.path with priority classification (cwd, site-packages, stdlib, etc.)
- CWD highlighting (sys.path[0] = highest priority)
- Conflict detection (when CWD shadows packages)
- Summary statistics by path type

**3. Automated Environment Diagnostics (`python://doctor`)**
```bash
reveal python://doctor
```
One-command health check performing 5 automated checks:
- ✅ Virtual environment activation status
- ✅ CWD shadowing detection
- ✅ Stale bytecode (.pyc newer than .py)
- ✅ Python version compatibility
- ✅ Editable install detection

Returns health score (0-100) + actionable fix commands.

**Coming Soon (v0.18.0+):**
- `python://imports/graph` - Import dependency visualization
- `python://imports/circular` - Circular import detection
- `python://debug/syntax` - Syntax error detection
- `python://project` - Auto-detect project type (Django, Flask, etc.)
- `python://tests` - Test discovery and status

**Use Cases:**
- Pre-debug environment sanity check
- Fix "my changes aren't working" (stale bytecode detection)
- Verify virtual environment activation
- Check installed package versions
- Inspect sys.path and import configuration
- AI agents debugging Python environments

**New Files:**
- `reveal/adapters/python.py` (750+ lines) - Python runtime adapter with enhanced diagnostics
- `reveal/adapters/PYTHON_ADAPTER_GUIDE.md` (250+ lines) - Comprehensive guide with examples

**Tests:**
- `tests/test_adapters.py` - 19 comprehensive tests for Python adapter (51% coverage)
  - Module conflict detection tests
  - sys.path analysis tests
  - Doctor diagnostics tests

**Documentation:**
- Self-documenting via `reveal help://python`
- Integrated with existing help system
- Complete guide: `reveal/adapters/PYTHON_ADAPTER_GUIDE.md`
  - Real-world workflows
  - Multi-shot prompting examples (for LLMs)
  - Integration patterns (CI/CD, agents)
  - Troubleshooting guide

---

### 📚 IMPROVED: Help System Redesign (Token-Efficient Discovery)

**Agent help system redesigned for progressive discovery!** The help system now promotes the `help://` URI adapter as the primary discovery mechanism, with --agent-help teaching the discovery pattern instead of dumping full documentation.

**New Architecture:**
- `--agent-help` - Brief quick start (~1,500 tokens) + teaches `help://` pattern
- `help://` - Progressive discovery (~50-500 tokens as needed)
- `--agent-help-full` - Complete offline reference (~12,000 tokens)

**Key Changes:**

**1. `--agent-help` (Now Brief & Educational)**
```bash
reveal --agent-help              # Quick start + discovery pattern
```

**New content focuses on:**
- Teaching the `help://` progressive discovery pattern
- Essential workflows (codebase exploration, PR review, Python debugging)
- When to use `--agent-help-full` (offline fallback)
- Token efficiency comparison table

**Token cost:** ~1,500 tokens (was ~11,000 tokens)
**Reduction:** 85% smaller, teaches better patterns

**2. `help://` Promotion (Primary Discovery Method)**
```bash
# Progressive discovery workflow
reveal help://                    # List all adapters (~50 tokens)
reveal help://python              # Learn specific adapter (~200 tokens)
reveal python://                  # Use it
```

**Benefits:**
- Always up-to-date (queries live adapter registry)
- Self-documenting (adapters implement `get_help()`)
- Token-efficient (progressive, not all-at-once)
- Machine-readable (`--format=json` support)

**3. `--agent-help-full` (Offline Fallback)**
```bash
reveal --agent-help-full          # Complete guide when needed
```

**Updated with:**
- Token cost warning at top (~12,000 tokens)
- Complete python:// adapter documentation
- URI adapter section (help://, python://, ast://, env://)
- Guidance on when to prefer `help://` vs full guide

**Impact:**
- Prevents documentation drift (python:// was missing from old guide)
- Encourages token-efficient discovery patterns
- Provides fallback for constrained environments

**Modified Files:**
- `reveal/AGENT_HELP.md` - Complete rewrite (~85% reduction, teaches `help://`)
- `reveal/AGENT_HELP_FULL.md` - Added python:// docs, token cost warning

---

### 🐛 FIXED: BrokenPipeError When Piping Output

**Fixed crash when piping reveal output to head/tail/grep.**

**Problem:**
```bash
reveal python://packages | head -30
# Traceback: BrokenPipeError: [Errno 32] Broken pipe
```

**Solution:**
Added standard Python CLI pattern to handle broken pipe gracefully:
```python
try:
    _main_impl()
except BrokenPipeError:
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, sys.stdout.fileno())
    sys.exit(0)  # Exit cleanly
```

**Now works:**
```bash
reveal python://packages | head -30  # ✅ No error
reveal python://imports | tail -20   # ✅ Works
reveal python:// | grep "3.10"       # ✅ Works
```

**Modified Files:**
- `reveal/main.py` - Added BrokenPipeError handler in `main()`

---

## [0.16.0] - 2025-12-04

### 🎯 NEW: Type System & Semantic Analysis (`--format=typed`)

**Reveal now understands code relationships!** Analyzers can define types and relationships, enabling type-aware queries, call graphs, and dependency tracking.

**New `--format=typed` output:**
```bash
reveal app.py --format=typed
```

**Output includes:**
- **Entities with explicit types** - Each element tagged (function, method, class, etc.)
- **Relationships** - Call graphs, inheritance, decorators, imports
- **Bidirectional edges** - Automatic reverse relationships (calls ↔ called_by)
- **Type counts** - Summary statistics
- **Metadata** - Total entities and relationships

**Example output:**
```json
{
  "entities": [
    {"type": "function", "name": "process", "line": 10, "signature": "..."},
    {"type": "method", "name": "handle", "line": 50, "parent_class": "Handler"}
  ],
  "relationships": {
    "calls": [{"from": {"type": "method", "name": "handle"}, "to": {"type": "function", "name": "process"}}],
    "called_by": [{"from": {"type": "function", "name": "process"}, "to": {"type": "method", "name": "handle"}}]
  },
  "type_counts": {"function": 10, "method": 5, "class": 3}
}
```

**For Analyzer Authors:**
Analyzers can now optionally define:
- **Types** - Entity definitions with property validation and inheritance
- **Relationships** - Relationship definitions (bidirectional, transitive)
- **Extraction** - `_extract_relationships()` method to build relationship graphs

**Backward Compatible:** Existing analyzers work unchanged. Type system only activates if types are defined. Falls back to standard JSON if no types available.

**New Files:**
- `reveal/types.py` (617 lines) - Type system core (Entity, RelationshipDef, TypeRegistry, RelationshipRegistry)

**Modified Files:**
- `reveal/base.py` - Type system integration in FileAnalyzer
- `reveal/main.py` - `--format=typed` output renderer

---

### 📚 IMPROVED: AI-Friendly Documentation

**README optimized for AI agents:**
- Progressive disclosure structure (examples first)
- "For AI Agents" section with usage guide
- Clear pointers to `--agent-help` and `--agent-help-full`

**Philosophy:** README is already concise and AI-readable - no need for separate llms.txt when documentation is already well-structured.

---

### 🧹 Cleanup: Removed "enhanced" naming debt

**Improved clarity by removing vague "enhanced" terminology:**

- **Documentation:** Replaced "enhanced format" with "typed format" throughout
- **Code comments:** Updated all references to use "typed" instead of "enhanced"
- **File cleanup:** Removed unused POC analyzer that registered for fake `.pyenhanced` extension

**Changes:**
- `reveal/AGENT_HELP.md`: "Typed Format" section now clearer
- `reveal/main.py`: Updated docstrings and help text for `--format=typed`
- Deleted: `reveal/analyzers/python_enhanced.py` (unused POC, fake `.pyenhanced` extension)

**Philosophy:** If we need examples later, we'll create real, runnable ones based on actual use cases. Better nothing than fake examples.

**No breaking changes:** All functionality preserved, just clearer naming.

## [0.15.0] - 2025-12-03

### 🔍 NEW: Code Query System - Query your codebase like a database!

**ast:// adapter** - Find functions by complexity, size, and type across your entire codebase.

```bash
reveal 'ast://./src?complexity>10'          # Find complex functions
reveal 'ast://app.py?lines>50'              # Find long functions
reveal 'ast://.?lines>30&complexity<5'      # Long but simple functions
reveal 'ast://src?type=function' --format=json  # All functions as JSON
```

**Features:**
- **Query operators:** `>`, `<`, `>=`, `<=`, `==`
- **Filters:** `lines` (line count), `complexity` (cyclomatic), `type` (function/class/method)
- **Recursive scanning:** Analyzes entire directories
- **50+ languages:** Works with all tree-sitter supported languages
- **Output formats:** text, JSON, grep

**Use cases:**
- Find technical debt: `ast://src?complexity>10`
- Find refactor candidates: `ast://src?lines>100`
- Find good examples: `ast://src?complexity<3&lines<20`
- Export for analysis: `ast://src --format=json | jq`

### 🆘 NEW: help:// - Self-Documenting Adapter System

**Discover everything reveal can do:**

```bash
reveal help://                    # List all available help topics
reveal help://ast                 # Learn about ast:// queries
reveal help://env                 # Learn about env:// adapter
reveal help://adapters            # Summary of all adapters
```

**Features:**
- **Auto-discovery:** New adapters automatically appear in help://
- **Extensible:** Every adapter self-documents via `get_help()` method
- **Consistent:** Same pattern for all adapters (env://, ast://, future adapters)
- **Integration:** Works with existing `--agent-help` and `--agent-help-full` flags

### 🧹 Cleanup: Removed redundant --recommend-prompt flag

The `--recommend-prompt` flag duplicated content from `--agent-help`. Use `--agent-help` or `reveal help://agent` instead.

**Migration:**
- ❌ `reveal --recommend-prompt`
- ✅ `reveal --agent-help` (llms.txt convention)
- ✅ `reveal help://agent` (URI-based)

### 🏗️ Architecture: Pluggable Adapter System

**Zero main.py edits needed for new adapters:**

```python
@register_adapter('postgres')  # Auto-registers
class PostgresAdapter(ResourceAdapter):
    @staticmethod
    def get_help():  # Auto-discovered by help://
        return {...}
```

Adding new URI schemes (postgres://, diff://, etc.) requires zero changes to core code - just drop in a new adapter file!

## [0.14.0] - 2025-12-03

### ⚡ Performance: Graceful handling of large directories (#10)

**NEW: Smart truncation and fast mode for large directory trees!**

reveal now handles large directories gracefully with automatic warnings and performance optimizations.

**What's New:**
- **`--max-entries N`**: Limit directory tree output (default: 200, use 0 for unlimited)
- **`--fast`**: Skip expensive line counting, show file sizes instead (~5-6x faster)
- **Auto-detection**: Warns when directory has >500 entries, suggests optimizations

**Performance Impact:**
- **50x token reduction**: 200 entries vs 2,000+ entries
- **6x faster**: 66ms vs 374ms on 606-entry directory with `--fast`
- **Smart defaults**: 200-entry limit balances utility and performance

**Example:**
```bash
# Large directory (606 entries) - automatic warning
reveal /large/project
⚠️  Large directory detected (606 entries)
   Showing first 200 entries (use --max-entries 0 for unlimited)
   Consider using --fast to skip line counting

# Fast mode - show sizes instead of line counts
reveal /large/project --fast

# Show all entries
reveal /large/project --max-entries 0
```

**Technical Details:**
- Fast entry counting before tree walk (no analysis overhead)
- Truncation with clear messaging ("... 47 more entries")
- Fast mode skips analyzer instantiation and metadata calls
- Backward compatible: All existing behavior unchanged without flags

Fixes #10

### 🐛 Bug Fix: Missing file field in JSON structure elements (#11)

**Fixed:** `--stdin` with `--format=json` now includes file path in all structure elements.

**Problem:** When processing multiple files through stdin, nested structure elements (functions, classes, etc.) lacked a `file` field, making it impossible to identify which source file each element belonged to.

**Before (broken):**
```bash
ls *.py | reveal --stdin --format=json | jq '.structure.functions[]'
{
  "line": 1,
  "name": "foo",
  # ❌ No file field - can't tell which file this is from!
}
```

**After (fixed):**
```bash
ls *.py | reveal --stdin --format=json | jq '.structure.functions[]'
{
  "line": 1,
  "name": "foo",
  "file": "/path/to/app.py"  # ✅ File field present!
}
```

**Example use case:**
```bash
# Find all long functions across multiple files
find src/ -name "*.py" | reveal --stdin --format=json | \
  jq -r '.structure.functions[] | select(.line_count > 50) | "\(.file):\(.line) \(.name)"'
```

**Impact:** Enables proper pipeline workflows with multiple files. All structure elements (functions, classes, imports, etc.) now include the file path for reliable file attribution.

Fixes #11

## [0.13.3] - 2025-12-01

### 🪟 Windows Compatibility Improvements

**NEW: Native Windows support with platform-appropriate conventions!**

reveal now properly handles Windows platform conventions, making it a first-class citizen on all operating systems.

**What's Fixed:**
- **Cache directory**: Now uses `%LOCALAPPDATA%\reveal` on Windows (instead of Unix `~/.config/reveal`)
- **Environment variables**: Added 16 Windows system variables (USERPROFILE, USERNAME, COMSPEC, etc.) to `reveal env://`
- **PyPI metadata**: Updated classifiers to explicitly declare Windows, Linux, and macOS support

**Testing:**
- Added comprehensive Windows compatibility test suite (7 new tests)
- CI now validates on Windows, Linux, and macOS before every release
- All 85 tests passing on all platforms

**Impact:**
- Windows users get native platform experience
- `reveal env://` properly categorizes Windows system variables
- Update checks store cache in correct Windows location
- Cross-platform testing prevents regressions

**Technical Details:**
- Platform detection: Uses `sys.platform == 'win32'` for Windows-specific paths
- Fallback behavior: Gracefully handles missing LOCALAPPDATA environment variable
- Backward compatible: Unix/macOS paths unchanged

## [0.13.2] - 2025-12-01

### 🐛 Critical Bug Fix: AGENT_HELP Packaging

**Fixed:** v0.13.1 failed to include AGENT_HELP.md files in PyPI packages, causing `--agent-help` flag to fail with "file not found" errors.

**Root cause:** AGENT_HELP.md files were at repository root but not properly included in the Python package structure.

**Solution:**
- Moved AGENT_HELP.md and AGENT_HELP_FULL.md into `reveal/` package directory
- Updated package-data configuration in pyproject.toml to include `*.md` files
- Updated MANIFEST.in with correct paths
- Updated main.py path resolution from `parent.parent` to `parent`

**Verification:** Tested successfully in clean Podman container with fresh pip install.

**Impact:** `--agent-help` and `--agent-help-full` flags now work correctly in all installations.

## [0.13.1] - 2025-12-01

### ✨ Enhancement: Agent-Friendly Navigation Breadcrumbs

**NEW: Context-aware navigation hints optimized for AI agents!**

reveal now provides intelligent breadcrumb suggestions after every operation, helping AI agents discover the next logical steps without reading documentation.

**Features:**
- **File-type-aware suggestions**: Python files suggest `--check` and `--outline`, Markdown suggests `--links` and `--code`, etc.
- **Progressive disclosure**: Shows relevant next steps based on what you're viewing
- **15+ file types supported**: Custom breadcrumbs for Python, JS, TS, Rust, Go, Bash, GDScript, Markdown, YAML, JSON, JSONL, TOML, Dockerfile, Nginx, Jupyter

**Examples:**
```bash
# Python file shows code-specific breadcrumbs
$ reveal app.py
Next: reveal app.py <function>   # Extract specific element
      reveal app.py --check      # Check code quality
      reveal app.py --outline    # Nested structure

# Markdown shows content-specific breadcrumbs
$ reveal README.md
Next: reveal README.md <heading>   # Extract specific element
      reveal README.md --links      # Extract links
      reveal README.md --code       # Extract code blocks

# After extracting an element
$ reveal app.py main
Extracted main (180 lines)
  → Back: reveal app.py          # See full structure
  → Check: reveal app.py --check # Quality analysis
```

### 🐛 Bug Fixes
- Fixed: AGENT_HELP.md and AGENT_HELP_FULL.md now properly included in pip packages via MANIFEST.in

### 📝 Documentation
- Updated all `--god` flag references to `--check` (flag was renamed in v0.13.0)
- Updated README status line to v0.13.1

## [0.13.0] - 2025-11-30

### 🎯 Major Feature: Pattern Detection System

**NEW: Industry-aligned code quality checks with pluggable rules!**

reveal now includes a built-in pattern detection system that checks code quality, security, and best practices across all supported file types.

```bash
# Run all quality checks
reveal app.py --check

# Select specific categories (B=bugs, S=security, C=complexity, E=errors)
reveal app.py --check --select B,S

# Ignore specific rules
reveal app.py --check --ignore E501

# List all available rules
reveal --rules

# Explain a specific rule
reveal --explain B001
```

**Built-in Rules (6 rules):**
- **B001**: Bare except clause catches all exceptions including SystemExit (Python)
- **C901**: Function is too complex (Universal)
- **E501**: Line too long (Universal)
- **R913**: Too many arguments to function (Python)
- **S701**: Docker image uses :latest tag (Dockerfile)
- **U501**: GitHub URL uses insecure http:// protocol (Universal)

**Extensible:** Drop custom rules in `~/.reveal/rules/` - auto-discovered, zero configuration!

### 🤖 Major Feature: AI Agent Help System

**NEW: Comprehensive built-in guidance for AI agents and LLMs!**

Following the `llms.txt` pattern, reveal now provides structured usage guides directly from the CLI.

```bash
# Get brief agent usage guide (llms.txt-style)
reveal --agent-help

# Get comprehensive agent guide with examples
reveal --agent-help-full

# Get strategic best practices (from v0.12.0)
reveal --recommend-prompt
```

**Includes:**
- Decision trees for when to use reveal vs alternatives
- Workflow sequences for common tasks (PR review, bug investigation)
- Token efficiency analysis and cost comparisons
- Anti-patterns and what NOT to do
- Pipeline composition with git, find, jq, etc.

### Added
- **Pattern detection system** (`--check` flag)
  - Pluggable rule architecture in `reveal/rules/`
  - Rule categories: bugs, security, complexity, errors, refactoring, urls
  - `RuleRegistry` for automatic rule discovery
  - Support for file pattern and URI pattern matching
  - Multiple output formats: text (default), json, grep
  - `--select` and `--ignore` for fine-grained control

- **AI agent help flags**
  - `--agent-help`: Brief llms.txt-style usage guide
  - `--agent-help-full`: Comprehensive guide with examples
  - Embedded in CLI, no external dependencies

- **Rule management commands**
  - `--rules`: List all available pattern detection rules
  - `--explain <CODE>`: Get detailed explanation of specific rule

- **Documentation**
  - `AGENT_HELP.md`: Brief agent usage guide
  - `AGENT_HELP_FULL.md`: Comprehensive agent guide
  - `docs/AGENT_HELP_STANDARD.md`: Standard for agent help in CLI tools
  - `docs/SLOPPY_DETECTORS_DESIGN.md`: Pattern detector design documentation

### Changed
- **README updated** - New sections for pattern detection and AI agent support
- **Help text** - Updated examples to reference `--check` instead of deprecated `--show-sloppy`
- **Test suite** - Removed 3 obsolete test files from old refactoring
  - Kept 23 passing tests for semantic navigation
  - All core functionality tested and working

### Breaking Changes
- ⚠️ `--show-sloppy` flag renamed to `--check` (from v0.12.0)
  - Rationale: "check" is more industry-standard and clearer than "sloppy"
  - Pattern detection system replaces the previous sloppy code detection
  - Use `--check` instead of `--show-sloppy` or `--sloppy`

### Notes
- This release skips v0.12.0 to consolidate features
- v0.12.0 introduced semantic navigation and `--show-sloppy`
- v0.13.0 renames `--show-sloppy` to `--check` and adds full pattern detection
- See v0.12.0 notes in git history for semantic navigation features

## [0.11.1] - 2025-11-27

### Fixed
- **Test suite** - Fixed all failing tests for 100% pass rate (78/78 tests)
  - Removed 6 obsolete test files testing non-existent modules from old codebase
  - Fixed nginx analyzer tests to use temp files instead of passing line lists
  - Updated CLI help text test expectations to match current output format
  - All test modules now passing: Dockerfile, CLI, Analyzers, Nginx, Shebang, TOML, TreeSitter UTF-8

### Changed
- **pytest configuration** - Disabled postgresql and redis plugins to prevent import errors

## [0.11.0] - 2025-11-26

### 🌐 Major Feature: URI Adapters

**NEW: Explore ANY resource, not just files!**

reveal now supports URI-based exploration of structured resources. This release includes the first adapter (`env://`) with more coming soon.

```bash
# Environment variables
reveal env://                    # Show all environment variables
reveal env://DATABASE_URL        # Get specific variable
reveal env:// --format=json      # JSON output for scripting
```

**Why URI adapters?**
- **Consistent interface** - Same reveal UX for any resource
- **Progressive disclosure** - Overview → specific element → details
- **Multiple formats** - text, json, grep (just like files)
- **Composable** - Works with jq, grep, and other Unix tools

### Added
- **URI adapter architecture** - Extensible system for exploring non-file resources
  - Base adapter interface in `reveal/adapters/base.py`
  - Adapter registry and URI routing in `main.py`
  - Consistent output formats (text, json, grep)

- **`env://` adapter** - Environment variable exploration
  - `reveal env://` - List all environment variables, grouped by category
  - `reveal env://VAR_NAME` - Get specific variable details
  - Automatic sensitive data detection (passwords, tokens, keys)
  - Redacts sensitive values by default (show with `--show-secrets`)
  - Categories: System, Python, Node, Application, Custom
  - Example: `reveal env:// --format=json | jq '.categories.Python'`

- **Enhanced help text** - URI adapter examples with jq integration
  - Shows env:// usage patterns
  - Demonstrates JSON filtering with jq
  - Clear documentation of adapter system

### Changed
- **README updated** - New "URI Adapters" section with examples
- **Features list** - URI adapters now listed as key feature

### Coming Soon
- `https://` - REST API exploration
- `git://` - Git repository inspection
- `docker://` - Container inspection
- And more! See ARCHITECTURE_URI_ADAPTERS.md for roadmap

## [0.10.1] - 2025-11-26

### Fixed
- **jq examples corrected** - All jq examples in help now use correct `.structure.functions[]` path
  - Previous examples used `.functions[]` which caused "Cannot iterate over null" errors
  - Affects all jq filtering examples in `--help` output
  - Examples now work as documented

### Changed
- **--god flag help clarified** - Now explicitly shows thresholds: ">50 lines OR depth >4"
  - Previous description was vague: "high complexity or length"
  - Users can now understand exactly what qualifies as a "god function"

### Added
- **Markdown-specific examples** - Added help examples for markdown features
  - `reveal doc.md --links` - Extract all links
  - `reveal doc.md --links --link-type external` - Filter by link type
  - `reveal doc.md --code --language python` - Extract Python code blocks
- **File-type specific features section** - New help section explaining file-type capabilities
  - Markdown: --links, --code with filtering options
  - Code files: --god, --outline for complexity analysis
  - Improves discoverability of file-specific features

## [0.10.0] - 2025-11-26

### Added
- **`--stdin` flag** - Unix pipeline workflows! Read file paths from stdin (one per line)
  - Enables composability with find, git, ls, and other Unix tools
  - Works with all existing flags: `--god`, `--outline`, `--format`, etc.
  - Graceful error handling: skips missing files and directories with warnings
  - Perfect for dynamic file selection and CI/CD workflows
  - Examples:
    - `find src/ -name "*.py" | reveal --stdin --god` - Find complex code in Python files
    - `git diff --name-only | reveal --stdin --outline` - Analyze changed files
    - `git ls-files "*.ts" | reveal --stdin --format=json` - Export TypeScript structure
    - `find . -name "*.py" | reveal --stdin --format=json | jq '.functions[] | select(.line_count > 100)'` - Complex filtering pipeline

- **Enhanced help text** - Pipeline examples with jq integration
  - Dynamic help: shows jq examples only if jq is installed
  - Clear documentation of stdin workflows
  - Real-world pipeline examples combining find/git/grep with reveal

- **README documentation** - Added "Unix Pipeline Workflows" section
  - Comprehensive stdin examples with find, git, jq
  - CI/CD integration patterns
  - Clear explanation of composability benefits

### Changed
- **Analyzer icons removed** - Completed LLM optimization started in v0.9.0
  - All emoji icons removed from file type registrations
  - Consistent with token optimization strategy (30-40% token savings)
  - Applies to all 18 built-in analyzers

### Fixed
- **Suppressed tree-sitter deprecation warnings** - Clean output for end users
  - No more FutureWarning messages from tree-sitter library
  - Applied globally across all TreeSitter usage

## [0.9.0] - 2025-11-26

### 🌟 Major Feature: Hierarchical Outline Mode

**NEW: `--outline` flag** - See code structure as a beautiful tree!

Transform flat lists into hierarchical views that show relationships at a glance:

```bash
# Before: Flat list
Functions (5):
  app.py:4    create_user(self, username)
  app.py:8    delete_user(self, user_id)
  ...

# After: Hierarchical tree
UserManager (app.py:1)
  ├─ create_user(self, username) [3 lines, depth:0] (line 4)
  ├─ delete_user(self, user_id) [3 lines, depth:0] (line 8)
  └─ UserValidator (nested class, line 12)
     └─ validate_email(self, email) [2 lines, depth:0] (line 15)
```

**Key Benefits:**
- **Instant understanding** - See which methods belong to which classes
- **Nested structure visibility** - Detect nested classes, functions within functions
- **Perfect for AI agents** - Hierarchical context improves code comprehension
- **Combines with other flags** - Use with `--god` for complexity-focused outlines

**Works across languages:**
- Python: Classes with methods, nested classes
- JavaScript/TypeScript: Classes with methods (via TreeSitter)
- Markdown: Heading hierarchy (# → ## → ###)
- Any language with TreeSitter support

### Added
- **`--outline` flag** - Hierarchical tree view of code structure
  - Automatically builds parent-child relationships from line ranges
  - Uses tree characters (├─, └─, │) for visual clarity
  - Shows line numbers for vim/git integration
  - Preserves complexity metrics ([X lines, depth:Y])
  - Example: `reveal app.py --outline`
  - Example: `reveal app.py --outline --god` (outline of only complex code)

- **Enhanced TreeSitter analyzers** - Now track `line_end` for proper hierarchy
  - Classes, structs, and all code elements now have line ranges
  - Enables accurate parent-child relationship detection
  - Fixes: Classes can now contain their methods in outline view

- **God function detection** (`--god` flag) - Find high-complexity code (>50 lines or >4 depth)
  - Quickly identify functions that need refactoring
  - JSON format includes metrics: `line_count`, `depth` for filtering with jq
  - Combines beautifully with `--outline` for focused views
  - Example: `reveal app.py --god` shows only complex functions

- **TreeSitter fallback system** - Automatic support for 35+ additional languages
  - C, C++, C#, Java, PHP, Ruby, Swift, Kotlin, and 27 more languages
  - Graceful fallback when explicit analyzer doesn't exist
  - Transparency: Shows `(fallback: cpp)` indicator in output
  - Metadata included in JSON

- **--no-fallback flag** - Disable automatic fallback for strict workflows

### Changed
- **LLM optimization** - Removed emojis from all output formats (30-40% token savings)
  - Clean, parseable format optimized for AI agents
  - Hierarchical outline adds even more AI-friendly structure

- **Code quality** - Refactored `show_structure()` function (54% complexity reduction)
  - Extracted helper functions: `_format_links()`, `_format_code_blocks()`, `_format_standard_items()`
  - Added `build_hierarchy()` and `render_outline()` for tree rendering
  - Reduced from 208 lines → 95 lines (main function)
  - Improved maintainability with proper type hints

### Improved
- **Help text** - Added clear examples for `--outline` flag
- **Visual clarity** - Tree characters make structure instantly recognizable
- **AI agent workflows** - Hierarchical context improves code understanding
- **Developer experience** - See code organization at a glance

## [0.8.0] - 2025-11-25

### Changed
- **tree-sitter is now a required dependency** (previously optional via `[treesitter]` extra)
  - JavaScript, TypeScript, Rust, Go, and all tree-sitter languages now work out of the box
  - No more silent failures when analyzing JS/TS files without extras installed
  - Simplified installation: just `pip install reveal-cli` (no `[treesitter]` needed)
  - Package size increased from ~50KB to ~15MB (comparable to numpy, black, pytest)

### Improved
- **Better user experience**: Code exploration features work by default
- **Simpler documentation**: One install command instead of two options
- **Cleaner codebase**: Removed optional import logic and conditional checks
- **Aligned with tool identity**: "Semantic code exploration" now works for all languages immediately

### Added
- **Update notifications**: reveal now checks PyPI once per day for newer versions
  - Shows: "⚠️ Update available: reveal 0.8.1 (you have 0.8.0)"
  - Includes install hint: "💡 Update: pip install --upgrade reveal-cli"
  - Non-blocking: 1-second timeout, fails silently on errors
  - Cached: Only checks once per day (~/.config/reveal/last_update_check)
  - Opt-out: Set `REVEAL_NO_UPDATE_CHECK=1` environment variable

### Technical
- Moved `tree-sitter==0.21.3` and `tree-sitter-languages>=1.10.0` from optional to required dependencies
- Simplified `reveal/treesitter.py` by removing `TREE_SITTER_AVAILABLE` conditionals
- Updated README.md to show single installation command
- Kept `[treesitter]` extra as empty for backward compatibility
- Added update checking using urllib (no new dependencies)

### Migration Notes
- **Existing users**: No action required - upgrade works seamlessly
- **New users**: Just `pip install reveal-cli` and everything works
- **Scripts using `[treesitter]`**: Still work (now redundant but harmless)

## [0.7.0] - 2025-11-23

### Added
- **TOML Analyzer** (`.toml`) - Extract sections and top-level keys from TOML configuration files
  - Perfect for exploring `pyproject.toml`, Hugo configs, Cargo.toml
  - Shows `[section]` headers and `[[array]]` sections with line numbers
  - Supports section extraction via `reveal file.toml <section>`
- **Dockerfile Analyzer** (filename: `Dockerfile`) - Extract Docker directives and build stages
  - Shows FROM images, RUN commands, COPY/ADD operations, ENV variables, EXPOSE ports
  - Detects multi-stage builds and displays all directives with line numbers
  - Works with any Dockerfile regardless of case (Dockerfile, dockerfile, DOCKERFILE)
- **Shebang Detection** - Automatically detect file type from shebang for extensionless scripts
  - Python scripts (`#!/usr/bin/env python3`) now work without `.py` extension
  - Bash/Shell scripts (`#!/bin/bash`, `#!/bin/sh`, `#!/bin/zsh`) work without `.sh` extension
  - Enables reveal to analyze TIA's `bin/` directory and other extensionless script collections
  - File extension still takes precedence when present

### Technical Improvements
- Enhanced `get_analyzer()` with fallback chain: extension → filename → shebang
- Case-insensitive filename matching for special files (Dockerfile, Makefile)
- Cross-platform shebang detection with robust error handling
- 32 new comprehensive unit tests (TOML: 7, Dockerfile: 13, Shebang: 12)

### Impact
- File types supported: **16 → 18** (+12.5%)
- TIA ecosystem coverage: ~90% of file types now supported
- Token efficiency: 6-10x improvement for config files and Dockerfiles

## [0.6.0] - 2025-11-23

### Added
- **Nginx configuration analyzer** (.conf) - Web server config analysis
  - Extracts server blocks with ports and server names
  - Identifies location blocks with routing targets (proxy_pass, static roots)
  - Detects upstream blocks for load balancing
  - Captures header comments with deployment status
  - Line-accurate navigation to config sections
  - Supports HTTP→HTTPS redirect patterns
  - Cross-platform compatible

## [0.5.0] - 2025-11-23

### Added
- **JavaScript analyzer** (.js) - Full ES6+ support via tree-sitter
  - Extracts function declarations, arrow functions, classes
  - Supports import/export statements
  - Handles async functions and object methods
  - Cross-platform compatible (Windows/Linux/macOS)

- **TypeScript analyzer** (.ts, .tsx) - Full TypeScript support via tree-sitter
  - Extracts functions with type annotations
  - Supports class definitions and interfaces
  - React/TSX component support (.tsx files)
  - Type definitions and return types
  - Cross-platform compatible (Windows/Linux/macOS)

- **Bash/Shell script analyzer** (.sh, .bash) - DevOps script support via tree-sitter
  - Extracts function definitions (both `function name()` and `name()` syntax)
  - Cross-platform analysis (parses bash syntax on any OS)
  - Does NOT execute scripts, only analyzes syntax
  - Works with WSL, Git Bash, and native Unix shells
  - Custom `_get_function_name()` implementation for bash 'word' node types

- **12 comprehensive tests** in `test_new_analyzers.py`:
  - JavaScript: functions, classes, imports, UTF-8 handling
  - TypeScript: typed functions, classes, interfaces, TSX/React components
  - Bash: function extraction, complex scripts, cross-platform compatibility
  - Cross-platform UTF-8 validation for all three analyzers

### Changed
- **File type count: 10 → 15** supported file types
  - JavaScript (.js)
  - TypeScript (.ts, .tsx) - 2 extensions
  - Bash (.sh, .bash) - 2 extensions

- **Updated analyzers/__init__.py** to register new analyzers
- **Fixed test_main_cli.py** version assertion to use regex pattern instead of hardcoded version

### Technical Details

**JavaScript Support:**
- Tree-sitter language: `javascript`
- Node types: function_declaration, class_declaration, import_statement
- Handles modern ES6+ syntax (arrow functions, classes, modules)

**TypeScript Support:**
- Tree-sitter language: `typescript`
- Supports both .ts and .tsx (React) files
- Extracts type annotations and interfaces
- Handles generic types and complex TypeScript features

**Bash Support:**
- Tree-sitter language: `bash`
- Custom implementation: Bash uses `word` for function names, not `identifier`
- Overrides `_get_function_name()` to handle bash-specific AST structure
- Supports both `function deploy() {}` and `deploy() {}` syntaxes

**Cross-Platform Strategy:**
- JavaScript/TypeScript: Universal web languages, native cross-platform support
- Bash: Analyzes syntax only (doesn't execute), works on Windows via WSL/Git Bash
- All analyzers tested on UTF-8 content with emoji and multi-byte characters

**Real-World Validation:**
- Tested on SDMS platform codebase
- JavaScript: Extracted classes from pack-builder.js files
- Bash: Extracted 5+ functions from deploy-container.sh
- All UTF-8 characters (emoji, special symbols) handled correctly

### Windows Compatibility
All new analyzers are fully Windows-compatible:
- **JavaScript/TypeScript:** Native cross-platform support
- **Bash:** Syntax analysis works on Windows (common in Git Bash, WSL, Docker workflows)
- No execution required, only parsing

**Future Windows Support:**
- PowerShell (.ps1) - Not yet available in tree-sitter-languages
- Batch files (.bat, .cmd) - Not yet available in tree-sitter-languages

## [0.4.1] - 2025-11-23

### Fixed
- **CRITICAL: TreeSitter UTF-8 byte offset handling** - Fixed function/class/import name truncation bug
  - GitHub Issues #6, #7, #8: Function names, class names, and import statements were truncated or corrupted
  - Root cause: Tree-sitter uses byte offsets but we were slicing Unicode strings
  - Multi-byte UTF-8 characters (emoji, non-Latin scripts) caused byte/character offset mismatch
  - Solution: Convert to bytes for slicing, then decode back to string
  - Affected all tree-sitter languages (Python, Rust, Go, GDScript, etc.)
  - Fixed in `reveal/treesitter.py:_get_node_text()`
- **Test assertion:** Updated version test to expect 0.4.0 (was incorrectly testing for 0.3.0)

### Added
- **4 comprehensive UTF-8 regression tests** in `test_treesitter_utf8.py`:
  - Test function names with emoji in docstrings
  - Test class names with multi-byte characters
  - Test imports with Unicode strings
  - Test complex Unicode throughout file (multiple languages, extensive emoji)
- Extensive code comments explaining UTF-8 byte offset handling

### Technical Details
**Bug reproduction:**
- Files with multi-byte UTF-8 characters before function/class/import definitions
- Tree-sitter returns byte offset 100, but string character offset is 97 (if 3-byte emoji present)
- Slicing `string[100:]` starts too far, losing first few characters

**Examples of bugs fixed:**
- ❌ Before: `test_function_name` → `st_function_name` (missing "te")
- ✅ After: `test_function_name` (complete)
- ❌ Before: `import numpy as np` → `rt numpy as np\nimp` (garbled)
- ✅ After: `import numpy as np` (clean)
- ❌ Before: `TestClassName` → `tClassName` (truncated)
- ✅ After: `TestClassName` (complete)

**Impact:**
- All tree-sitter-based analyzers now handle Unicode correctly
- Python, Rust, Go, GDScript all benefit from this fix
- Particularly important for codebases with emoji in docstrings or non-Latin comments

## [0.4.0] - 2025-11-23

### Added
- **`--version` flag** to show current version
- **`--list-supported` flag** (`-l` shorthand) to display all supported file types with icons
- **Cross-platform compatibility checker** (`check_cross_platform.sh`) - automated audit tool
- **Comprehensive documentation:**
  - `CHANGELOG.md` - Complete version history
  - `CROSS_PLATFORM.md` - Windows/Linux/macOS compatibility guide
  - `IMPROVEMENTS_SUMMARY.md` - Detailed improvement tracking
- **Enhanced help text** with organized examples (Directory, File, Element, Formats, Discovery)
- **11 new tests** in `test_main_cli.py` covering all new features
- **Validation script** `validate_v0.4.0.sh` (updated from v0.3.0)

### Changed
- **Better error messages** with actionable hints:
  - Shows full path and extension for unsupported files
  - Suggests `--list-supported` to see supported types
  - Links to GitHub for feature requests
- **Improved help output:**
  - GDScript examples included
  - Better organized examples by category
  - Clear explanations of all flags
  - Professional tagline about filename:line integration
- **Updated README:**
  - Version badge: v0.3.0 (was v0.2.0)
  - Added GDScript to features and examples
  - Added new flags to Optional Flags section
- **Updated INSTALL.md:**
  - PyPI installation shown first
  - New verification commands (--version, --list-supported)
  - Removed outdated --level references
  - Updated CI/CD examples

### Fixed
- Documentation consistency (removed all outdated --level references)
- README version accuracy

## [0.3.0] - 2025-11-23

### Added
- **GDScript analyzer** for Godot game engine files (.gd)
  - Extracts classes, functions, signals, and variables
  - Supports type hints and return types
  - Handles export variables and onready modifiers
  - Inner class support
- **Windows UTF-8/emoji support** - fixes console encoding issues on Windows
- Comprehensive validation samples for all 10 file types
- Validation samples: `calculator.rs` (Rust), `server.go` (Go), `analysis.ipynb` (Jupyter), `player.gd` (GDScript)

### Changed
- Modernized Jupyter analyzer for v0.2.0+ architecture
- Updated validation samples to be Windows-compatible
- Removed archived v0.1 code (4,689 lines cleaned up)

### Fixed
- Windows console encoding crash with emoji/unicode characters
- Jupyter analyzer compatibility with new architecture
- Hardcoded Unix paths in validation samples

### Contributors
- @Huzza27 - Windows UTF-8 encoding fix (PR #5)
- @scottsen - GDScript support and test coverage

## [0.2.0] - 2025-11-23

### Added
- Clean redesign with simplified architecture
- TreeSitter-based analyzers for Rust, Go
- Markdown, JSON, YAML analyzers
- Comprehensive validation suite (15 automated tests)
- `--format=grep` option for pipeable output
- `--format=json` option for programmatic access
- `--meta` flag for metadata-only view
- `--depth` flag for directory tree depth control

### Changed
- Complete architecture redesign (500 lines core, 10-50 lines per analyzer)
- Simplified CLI interface - removed 4-level progressive disclosure
- New element extraction model (positional argument instead of --level)
- Improved filename:line format throughout

### Removed
- Old 4-level `--level` system (replaced with simpler model)
- Legacy plugin YAML configs (moved to decorator-based registration)

## [0.1.0] - 2025-11-22

### Added
- Initial release
- Basic file exploration
- Python analyzer
- Plugin architecture
- Progressive disclosure (4 levels)
- Basic CLI interface

---

## Version History Summary

- **0.3.0** - GDScript + Windows Support
- **0.2.0** - Clean Redesign
- **0.1.0** - Initial Release

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on adding new features and file types.

## Links

- **GitHub**: https://github.com/Semantic-Infrastructure-Lab/reveal
- **PyPI**: https://pypi.org/project/reveal-cli/
- **Issues**: https://github.com/Semantic-Infrastructure-Lab/reveal/issues
