---
title: Query Syntax Guide
description: Complete reference for unified query operators and result control
help_topic: query
help_description: "Unified query syntax reference (operators, result control)"
help_category: feature_guides
---

# Query Syntax Guide

Complete reference for the unified query syntax that works consistently across all of Reveal's query-capable adapters. All operators use the same underlying comparison logic (`compare_values()` in `reveal/utils/query_eval.py`), ensuring consistent behavior across adapters.

---

## Quick Start

```bash
# Filter by field value
reveal 'json://data.json?age>25'

# Multiple filters (AND)
reveal 'markdown://docs/?status=draft&priority=high'

# Sort and limit results
reveal 'git://.?type=history&author=John&sort=-date&limit=10'

# Range queries
reveal 'metrics://src/?lines=100..500&sort=-complexity'

# Regex matching
reveal 'git://.?message~=bug.*fix'
```

---

## Convenience Flags vs URI Syntax (NEW - v0.47.3)

**For simple within-file queries, use convenience flags instead of URI syntax.**

### Ergonomic Flags for Common Operations

```bash
# Search by name pattern
reveal file.py --name connection
# Equivalent to: reveal 'ast://file.py?name~=connection'

# Filter by element type
reveal file.py --type function
# Equivalent to: reveal 'ast://file.py?type=function'

# Sort results
reveal file.py --sort complexity          # Ascending
reveal file.py --sort=-complexity         # Descending
# Equivalent to: reveal 'ast://file.py?sort=complexity' or 'ast://file.py?sort=-complexity'

# Combine flags
reveal file.py --name test --type function --sort=-line_count
# Equivalent to: reveal 'ast://file.py?name~=test&type=function&sort=-line_count'
```

### When to Use Convenience Flags

**Use flags for** (80% of queries):
- ✅ Searching within a single file
- ✅ Simple name pattern matching
- ✅ Basic type filtering
- ✅ Sorting results
- ✅ Quick grep-like workflows
- ✅ File target options (`--links` on markdown, `--diagnose` on nginx files)

**Use URI syntax for** (20% of queries):
- ✅ Multiple conditions: `?complexity>10&lines>50`
- ✅ Range queries: `?lines=10..50`
- ✅ Boolean logic: `?type=function|method`
- ✅ Cross-directory queries: `ast://./src?name=*test*`
- ✅ Adapter-specific params: `git://.?author=John&since=2024-01-01`
- ✅ Batch/pipeline workflows where options must travel with the URI

> **Architectural note**: For URI adapters (`cpanel://`, `ssl://`, `domain://`, etc.), adapter-specific options belong in the URI query string — not as CLI flags. File target options (`--diagnose`, `--links`, `--frontmatter`) stay as CLI flags. See [ADAPTER_CONSISTENCY.md](../development/ADAPTER_CONSISTENCY.md#adapter-specific-flags-vs-query-parameters).

### Comparison Table

| Task | Convenience Flag | URI Syntax |
|------|-----------------|------------|
| Find by name | `reveal file.py --name pattern` | `reveal 'ast://file.py?name~=pattern'` |
| Filter type | `reveal file.py --type function` | `reveal 'ast://file.py?type=function'` |
| Sort | `reveal file.py --sort complexity` | `reveal 'ast://file.py?sort=complexity'` |
| Complex filter | ❌ (not supported) | `reveal 'ast://src/?complexity>10&lines>50&type=function&sort=-complexity'` |

### Progressive Escalation

Start simple (flags), escalate to URI syntax when needed:

```bash
# Step 1: Simple search
reveal file.py --name authenticate

# Step 2: Add type filter
reveal file.py --name authenticate --type function

# Step 3: Add sorting
reveal file.py --name authenticate --type function --sort=-complexity

# Step 4: Need complex conditions? Use URI syntax
# Note: --name <pattern> becomes ?name~=<pattern> in URI form (intentional rename)
reveal 'ast://file.py?name~=authenticate&type=function&complexity>10&lines>50&sort=-complexity'
```

---

## Query-Capable Adapters

These 5 adapters support the unified query syntax:

| Adapter | Query Fields | Example |
|---------|--------------|---------|
| **json://** | Any JSON field | `json://data.json?age>25&role=admin` |
| **markdown://** | Frontmatter fields | `markdown://docs/?status=draft&tags~=python` |
| **metrics://** | File metrics | `metrics://src/?complexity>10&lines<100` |
| **ast://** | Code elements | `ast://src/?type=function&lines>50` |
| **git://** | Commit metadata | `git://.?author=John&message~=fix` |

---

## Universal Operators

All 5 adapters support these operators through the unified `compare_values()` function:

### Comparison Operators

| Operator | Description | Example | Matches |
|----------|-------------|---------|---------|
| `=` or `==` | Exact match (case-insensitive on json:// and git://; case-sensitive on markdown:// and ast://) | `status=active` | "active", "Active", "ACTIVE" (json://) |
| `!=` | Not equal | `status!=draft` | Anything except "draft" |
| `>` | Greater than | `lines>50` | 51, 100, 200... |
| `<` | Less than | `complexity<10` | 1, 5, 9... |
| `>=` | Greater or equal | `priority>=5` | 5, 6, 10... |
| `<=` | Less or equal | `functions<=20` | 1, 10, 20 |
| `~=` | Regex match (case-sensitive; prefix `(?i)` to ignore case) | `message~=(?i)bug.*fix` | "Bug fix", "fixed bug fix" |
| `!~` | Regex does not match | `email!~@company.com` | any email not at company.com |
| `..` | Range (inclusive) | `lines=50..200` | 50, 100, 200 |

`~=` is case-sensitive on every adapter; git's `author` and `email` filters are the exception
and match case-insensitively. The negated regex is `!~` (not `!~=`, which is mis-parsed and
filters everything out).

### Type Coercion

**Numeric comparison**:
- Strings automatically coerced to numbers: `"50" > 25` → true
- Non-numeric strings fail gracefully (no match)

**String comparison**:
- `=` is case-insensitive on json:// and git://, case-sensitive on markdown:// and ast://
- git: `author=John` matches "john", "John", "JOHN" (the whole author name)

**Boolean coercion**:
- `"true"`, `"yes"`, `"1"` → true
- `"false"`, `"no"`, `"0"` → false

---

## Result Control

Control how results are sorted and paginated:

| Parameter | Description | Example |
|-----------|-------------|---------|
| `sort=field` | Sort ascending | `sort=lines` |
| `sort=-field` | Sort descending | `sort=-complexity` |
| `limit=N` | Limit to N results | `limit=20` |
| `offset=M` | Skip first M results | `offset=10` (pagination) |

### Examples

```bash
# Top 10 most complex functions
reveal 'ast://src/?type=function&sort=-complexity&limit=10'

# Files 50-100 lines, by complexity
reveal 'metrics://src/?lines=50..100&sort=-complexity'

# Recent commits by John, newest first
reveal 'git://.?author=John&sort=-date&limit=20'

# Paginated results (page 2, 10 items per page)
reveal 'json://data.json?status=active&sort=name&offset=10&limit=10'
```

---

## Adapter-by-Adapter Examples

### json:// - JSON Data Filtering

**Numeric filters**:
```bash
reveal 'json://data.json?age>25'                    # Age over 25
reveal 'json://data.json?count>=100'                # Count 100+
reveal 'json://data.json?score=80..95'              # Score range
```

**String filters**:
```bash
reveal 'json://data.json?status=active'             # Exact match
reveal 'json://data.json?status!=draft'             # Not draft
reveal 'json://data.json?name~=john'                # Name contains "john" (case-sensitive; (?i)john to ignore case)
```

**Combined filters**:
```bash
reveal 'json://data.json?role=admin&age>30&status=active'
```

**Sorting**:
```bash
reveal 'json://data.json?status=active&sort=name'
reveal 'json://data.json?role=admin&sort=-age&limit=10'
```

---

### markdown:// - Frontmatter Queries

**Status filtering**:
```bash
reveal 'markdown://docs/?status=draft'              # Draft documents
reveal 'markdown://docs/?status!=archived'          # Not archived
```

**Tag filtering**:
```bash
reveal 'markdown://docs/?tags~=python'              # Tagged "python" (case-sensitive)
reveal 'markdown://docs/?tags~=api&status=complete' # Python APIs, complete
```

**Date filtering**:
```bash
reveal 'markdown://docs/?created=2026-01-01..2026-12-31'   # Created in 2026
reveal 'markdown://docs/?updated=2026-01-01..2026-02-28'   # January-February 2026
```

Frontmatter dates: use a range with full `YYYY-MM-DD` bounds. `>`/`<` on a frontmatter date
match nothing (no error), and a short bound such as `2026-02` excludes every February date
(`"2026-02-01" > "2026-02"`).

**Priority and sorting**:
```bash
reveal 'markdown://docs/?priority>=5&limit=10'
```

markdown:// filters on any frontmatter key but sorts only on the fields it puts in each result
(`path`, `relative_path`, `modified`, `mtime`, `status`, `has_frontmatter`); `sort=-priority`
leaves the results unsorted with a warning.

**Body text search** (markdown-specific):
```bash
reveal 'markdown://docs/?body-contains=nginx'                     # Body mentions "nginx"
reveal 'markdown://docs/?body-contains=nginx&body-contains=ssl'   # Body mentions both (AND)
reveal 'markdown://docs/?type=guide&body-contains=nginx&limit=5'  # Combine with frontmatter + limit
```

**Field existence** (markdown-specific):
```bash
reveal 'markdown://docs/?!published'                # No published date
```

---

### metrics:// - File Metrics Filtering

**Complexity filtering**:
```bash
reveal 'metrics://src/?complexity>10'                 # Complex files
reveal 'metrics://src/?complexity=5..15'              # Medium complexity
```

A metrics:// range (`field=a..b`) currently prints `⚠ Unknown query param '<field>' for
metrics:// — ignored` on stderr. Ignore that warning: the range is applied (same files as
`field>=a&field<=b`).

**Size filtering**:
```bash
reveal 'metrics://src/?lines>500'                     # Large files
reveal 'metrics://src/?lines<50'                      # Small files
reveal 'metrics://src/?lines=100..500'                # Medium files
```

**Quality filtering**:
```bash
reveal 'metrics://src/?quality<50'                    # Low quality
reveal 'metrics://src/?functions>20'                  # Many functions
```

**Hotspot analysis**:
```bash
# 20 most complex files
reveal 'metrics://src/?sort=-complexity&limit=20'

# Large, complex files (refactoring candidates)
reveal 'metrics://src/?lines>200&complexity>10&sort=-complexity'

# Small but complex (needs splitting)
reveal 'metrics://src/?lines<100&complexity>15'
```

---

### ast:// - Code Element Filtering

**Type filtering** (AST-specific `in` operator):
```bash
reveal 'ast://src/?type=function'                   # Functions only
reveal 'ast://src/?type=class'                      # Classes only
```

**Complexity filtering**:
```bash
reveal 'ast://src/?complexity>10'                   # Complex elements
reveal 'ast://src/?complexity<=5'                   # Simple elements
```

**Size filtering**:
```bash
reveal 'ast://src/?lines>50'                        # Long functions
reveal 'ast://src/?lines=20..50'                    # Medium functions
```

**Name filtering** (glob support):
```bash
reveal 'ast://src/?name=test_*'                     # Test functions
reveal 'ast://src/?name~=^get_'                     # Getters (regex)
```

**Quality queries**:
```bash
# Top 10 most complex functions
reveal 'ast://src/?type=function&sort=-complexity&limit=10'

# Long but simple functions (candidates for refactoring)
reveal 'ast://src/?lines>100&complexity<5'

# Small, complex functions (needs simplification)
reveal 'ast://src/?lines<30&complexity>10'
```

---

### git:// - Commit Filtering

**Author filtering**:
```bash
reveal 'git://.?author=John'                        # Exact full-name match (use author~= for part of a name)
reveal 'git://.?author~=john'                       # Contains "john" (any case)
reveal 'git://.?email~=@example.com'                # Company emails
```

**Message filtering**:
```bash
reveal 'git://.?message~=bug'                       # Bug fixes
reveal 'git://.?message~=^feat:'                    # Features (conventional commits)
reveal 'git://.?message~=(fix|bug)'                 # Fixes or bugs
```

**Combined filters**:
```bash
# John's bug fixes
reveal 'git://.?author=John&message~=bug'

# Recent work by email domain
reveal 'git://.?email~=@company.com&sort=-date&limit=20'

# Features by specific author
reveal 'git://.?author~=jane&message~=^feat:&sort=-date'
```

**Hash filtering**:
```bash
reveal 'git://.?hash=a1b2c3'                        # Commit by prefix
```

**File history**:
```bash
reveal 'git://app.py?type=history&author=John&sort=-date&limit=10'
```

---

## Operator Behavior Details

### Equality (`=` or `==`)

**String comparison**:
- Case-insensitive by default (adapter-specific)
- Exact match: `author=John` matches "John", "john", "JOHN"

**Numeric comparison**:
- Type coercion: `"50"` equals `50`
- Example: `priority=5` matches `5` and `"5"`

**List fields** (JSON, Markdown):
- Matches if ANY element equals value
- `tags=python` matches `["python", "code"]`

---

### Inequality (`!=`)

**String comparison**:
- `status!=draft` matches anything except "draft"
- Case-insensitive (adapter-specific)

**Numeric comparison**:
- Type coercion enabled
- `age!=25` matches 24, 26, but not 25 or "25"

**None/null handling**:
- Behavior varies by adapter (see configuration)
- JSON/Markdown/Git: `null != "value"` → true
- Stats/AST: `null != "value"` → false

---

### Numeric Comparisons (`>`, `<`, `>=`, `<=`)

**Number comparison**:
- Type coercion attempts numeric conversion
- `lines>50` matches 51, 100, 200
- Fails gracefully if not numeric (no match)

**No string fallback**: `>`, `<`, `>=`, `<=` compare numbers. A value that is not a number
matches nothing (no lexicographic fallback): `name>m` returns no rows. Use a range
(`name=a..n`) for string ordering; ranges compare strings when the bounds are not numbers.

---

### Regex Match (`~=`)

**Pattern matching**:
- Uses Python `re` module (a search, not a full match)
- Case-sensitive; prefix `(?i)` to ignore case (git `author`/`email` are matched case-insensitively)
- `message~=(?i)bug.*fix` matches "Bug fix for login"

**Common patterns**:
```bash
~=^test_          # Starts with "test_"
~=.*util.*        # Contains "util"
~=login$          # Ends with "login"
~=(foo|bar)       # Matches "foo" or "bar"
~=\d{4}-\d{2}     # Date pattern YYYY-MM
```

**Error handling**:
- Invalid patterns fail gracefully (no match)
- Logged for debugging

---

### Range (`..`)

**Numeric ranges**:
- Inclusive on both ends
- `lines=50..200` matches 50, 150, 200
- Type coercion enabled

**String ranges**:
- Lexicographic comparison
- `name=a..n` matches "alice", "bob", "mike" (`a..m` would drop "mike", since "mike" > "m")

**Syntax**:
- Use with `=` operator: `field=min..max`
- Example: `age=25..35`, `lines=100..500`

---

## Multiple Filters (AND Logic)

Combine filters with `&` - all must match:

```bash
# JSON: Admin users over 30
reveal 'json://data.json?role=admin&age>30'

# Markdown: High-priority Python docs
reveal 'markdown://docs/?tags~=python&priority>=5&status=draft'

# Stats: Large, complex files
reveal 'metrics://src/?lines>200&complexity>10'

# Git: John's bug fixes this year
reveal 'git://.?author=John&message~=bug&date>2026-01-01'

# AST: Long, complex functions
reveal 'ast://src/?type=function&lines>100&complexity>15'
```

**Behavior**:
- Filters are ANDed together
- Each filter narrows results
- No general OR operator: ast:// accepts `type=a|b`; elsewhere use a regex `~=(foo|bar)`

---

## Advanced Patterns

### Progressive Filtering

Start broad, narrow down:

```bash
# 1. See all files
reveal 'metrics://src/'

# 2. Filter to large files
reveal 'metrics://src/?lines>100'

# 3. Add complexity filter
reveal 'metrics://src/?lines>100&complexity>10'

# 4. Sort and limit
reveal 'metrics://src/?lines>100&complexity>10&sort=-complexity&limit=10'
```

---

### Top-N Queries

Find worst/best items:

```bash
# Top 10 most complex functions
reveal 'ast://src/?type=function&sort=-complexity&limit=10'

# 20 largest files
reveal 'metrics://src/?sort=-lines&limit=20'

# Most active committers (recent)
reveal 'git://.?type=log&limit=50' --format json | jq '.history | group_by(.author) | map({author: .[0].author, count: length}) | sort_by(-.count)'

# Worst quality files
reveal 'metrics://src/?sort=quality&limit=10'
```

---

### Range + Sort Queries

Filter by range, sort within range:

```bash
# Medium-sized files by complexity
reveal 'metrics://src/?lines=100..500&sort=-complexity'

# Functions 20-50 lines, most complex first
reveal 'ast://src/?lines=20..50&sort=-complexity'

# Commits from January, newest first
reveal 'git://.?date=2026-01..2026-02&sort=-date'
```

---

### Pagination

Paginate large result sets:

```bash
# Page 1 (first 10)
reveal 'json://data.json?status=active&sort=name&limit=10'

# Page 2 (next 10)
reveal 'json://data.json?status=active&sort=name&offset=10&limit=10'

# Page 3 (next 10)
reveal 'json://data.json?status=active&sort=name&offset=20&limit=10'
```

---

### Regex OR Queries

Use regex for OR logic:

```bash
# Bug fixes or features
reveal 'git://.?message~=(bug|feat)'

# Python or JavaScript files
reveal 'metrics://src/?file~=\.(py|js)$'

# Test or spec files
reveal 'ast://src/?name~=(test_|spec_)'

# Admin or moderator roles
reveal 'json://users.json?role~=(admin|moderator)'
```

---

## Configuration Options

The `compare_values()` function accepts options to configure behavior per adapter:

| Adapter | List Matching | Case Sensitive (`=`) | Numeric Coercion | Null != |
|---------|---------------|----------------|------------------|---------|
| **json://** | ✅ Any | ❌ No | ✅ Yes | ✅ Yes |
| **markdown://** | ✅ Any | ✅ Yes | ✅ Yes | ✅ Yes |
| **metrics://** | ❌ No | ❌ No | ✅ Yes | ❌ No |
| **ast://** | ❌ No | ✅ Yes | ✅ Yes | ❌ No |
| **git://** | ❌ No | ❌ No | ✅ Yes | ✅ Yes |

The column is about `=` and wildcards. `~=` ignores it: a regex is case-sensitive on every
adapter (add `(?i)`), except git's `author`/`email` filters, which ignore case.

**Rationale**:
- **JSON/Markdown**: Have list fields (tags, topics)
- **Metrics**: Numeric-focused, no lists
- **AST**: Code is case-sensitive
- **Git**: Commit metadata, case-insensitive author/email search

---

## Common Patterns

### Code Quality Analysis

```bash
# Refactoring candidates (large + complex)
reveal 'metrics://src/?lines>200&complexity>10&sort=-complexity'

# Technical debt hotspots
reveal 'metrics://src/?quality<50&sort=quality&limit=20'

# Overly complex small functions
reveal 'ast://src/?type=function&lines<50&complexity>10'

# Long functions needing splitting
reveal 'ast://src/?type=function&lines>100&sort=-lines'
```

---

### Documentation Management

```bash
# Unfinished high-priority docs
reveal 'markdown://docs/?status=draft&priority>=5'

# Stale documentation (dates: use a range; > and < on dates match nothing)
reveal 'markdown://docs/?updated=0000-01-01..2024-12-31'

# Python API documentation
reveal 'markdown://docs/?tags~=python&tags~=api&status=complete'

# Missing publication dates
reveal 'markdown://docs/?!published&status=complete'
```

---

### Git Analysis

```bash
# Bug fix commits this month
reveal 'git://.?message~=bug&date>2026-02-01&sort=-date'

# Feature commits by author
reveal 'git://.?message~=^feat:&author=John&sort=-date'

# Commits from external contributors
reveal 'git://.?type=log&email!~@company.com&sort=-date'

# Recent work by file
reveal 'git://app.py?type=history&limit=10&sort=-date'
```

---

### Data Analysis

```bash
# Active admin users
reveal 'json://users.json?role=admin&status=active&sort=last_login'

# High-value customers
reveal 'json://customers.json?lifetime_value>10000&sort=-lifetime_value'

# Recent orders over $100
reveal 'json://orders.json?total>100&date>2026-01-01&sort=-date'

# Age demographics
reveal 'json://users.json?age=25..35&status=active'
```

---

## Best Practices

### 1. Use Quotes

Shell may interpret `?` and `&`:

```bash
reveal 'json://data.json?age>25'     # ✅ Correct
reveal json://data.json?age>25        # ❌ Shell may break this
```

---

### 2. Start Broad, Then Filter

```bash
# 1. See structure
reveal 'metrics://src/'

# 2. Filter
reveal 'metrics://src/?complexity>10'

# 3. Sort and limit
reveal 'metrics://src/?complexity>10&sort=-complexity&limit=10'
```

---

### 3. Combine Complementary Filters

```bash
# Good: Specific, actionable query
reveal 'metrics://src/?lines>200&complexity>10&sort=-complexity&limit=20'

# Less useful: Too broad
reveal 'metrics://src/?lines>100'
```

---

### 4. Use Result Control

Always sort and limit large result sets:

```bash
# Good: Top 10 results
reveal 'json://data.json?status=active&sort=name&limit=10'

# Overwhelming: All results
reveal 'json://data.json?status=active'
```

---

### 5. Test Incrementally

Build complex queries step by step:

```bash
# Step 1: Basic filter
reveal 'git://.?author=John'

# Step 2: Add message filter
reveal 'git://.?author=John&message~=bug'

# Step 3: Sort and limit
reveal 'git://.?author=John&message~=bug&sort=-date&limit=10'
```

---

## See Also

- [Query Parameter Reference](QUERY_PARAMETER_REFERENCE.md) - Adapter-specific parameters
- [Adapter Authoring Guide](../development/ADAPTER_AUTHORING_GUIDE.md) - Add query support to custom adapters
- [Agent Help](../AGENT_HELP.md) - AI agent integration guide
- [Output Contract](../development/OUTPUT_CONTRACT.md) - Adapter output specification

---

## Implementation Details

**Phase 3 Completion** (2026-02-08):
- Unified query parser in `reveal/utils/query_parser.py`, operators in `reveal/utils/query_eval.py` (`reveal/utils/query.py` re-exports both)
- Single `compare_values()` function powers all operators
- 299 lines of duplicate code eliminated
- All 5 adapters migrated: json, markdown, stats, ast, git
- Backward compatible with existing queries
- Result control (sort/limit/offset) standardized

**Key Functions**:
- `parse_query_filters()` - Parse query string into filter objects
- `compare_values()` - Universal comparison logic
- `parse_result_control()` - Parse sort/limit/offset
- `apply_result_control()` - Apply sorting and pagination
