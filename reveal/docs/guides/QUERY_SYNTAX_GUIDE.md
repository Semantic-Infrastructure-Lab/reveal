---
title: Query Syntax Guide
description: Complete reference for unified query operators and result control
help_topic: query
help_description: "Unified query syntax reference (operators, result control)"
help_category: feature_guides
---

# Query Syntax Guide

Complete reference for the filter expressions (`--where 'FIELD OP VALUE'`) and result controls (`--sort`, `--limit`, `--offset`) that work the same way on every noun that filters rows. All operators use the same underlying comparison logic (`compare_values()` in `reveal/utils/query_eval.py`), ensuring consistent behavior across nouns.

Options are flags: `reveal NOUN TARGET --where ... --sort ...`, and a resource URI takes the same flags (`reveal git://app.py@main --view history --limit 5`). The older query-string spelling (`reveal 'ast://src?complexity>10&sort=-lines'`) still answers until 1.0 with a note naming its flag form, then exits 2; the operators below are the same in both.

---

## Quick Start

```bash
# Filter by field value
reveal json data.json --where 'age>25'

# Multiple filters (AND)
reveal markdown docs/ --where status=draft --where priority=high

# Sort and limit results
reveal git . --view history --where author=John --sort=-date --limit 10

# Range queries
reveal metrics src/ --where lines=100..500 --sort=-complexity

# Regex matching
reveal git . --where 'message~=bug.*fix'
```

---

## File Flags vs the `ast` Noun

**For simple within-file queries, use the file read's own flags; for filters, use `reveal ast`.**

### Ergonomic Flags for Common Operations

```bash
# Search by name pattern
reveal file.py --name connection
# Equivalent to: reveal ast file.py --where 'name~=connection'

# Filter by element type
reveal file.py --type function
# Equivalent to: reveal ast file.py --kind function

# Sort results
reveal file.py --sort complexity    # Ascending
reveal file.py --sort=-complexity   # Descending
# Equivalent to: reveal ast file.py --sort complexity (or --sort=-complexity)

# Combine flags
reveal file.py --name test --type function --sort=-line_count
# Equivalent to: reveal ast file.py --where 'name~=test' --kind function --sort=-line_count
```

### When to Use File Flags

**Use the file read's flags for** (80% of queries):
- ✅ Searching within a single file
- ✅ Simple name pattern matching
- ✅ Basic type filtering
- ✅ Sorting results
- ✅ Quick grep-like workflows
- ✅ File target options (`--links` on markdown, `--diagnose` on nginx files)

**Use a noun (`reveal ast`, `reveal git`, ...) with `--where` for** (20% of queries):
- ✅ Multiple conditions: `--where 'complexity>10' --where 'lines>50'`
- ✅ Range queries: `--where lines=10..50`
- ✅ Either of two kinds: `--kind 'function|method'`
- ✅ Directory-wide queries: `reveal ast ./src --where 'name=*test*'`
- ✅ A noun's own controls: `reveal git . --where author=John --since 2024-01-01`
- ✅ Batch/pipeline workflows: each `--stdin` line is a whole request, flags included (`ast src --where 'complexity>10'`)

> **Architectural note**: options are flags on every noun: `reveal NOUN TARGET --option value`. A URI names a resource (`git://app.py@main`, `claude://session/NAME`, `json://data.json/users`) and takes the same flags, with the same answer and exit code. A query string (`?option=value`) is the retiring spelling: it answers with a note naming the flag form until 1.0, then exits 2. The hosting-ops adapters (`cpanel://`, `ssl://`, `domain://`, ...) are outside this rule: they are moving to a separate package and keep their query options.

### Comparison Table

| Task | File flag | `ast` noun |
|------|-----------|------------|
| Find by name | `reveal file.py --name pattern` | `reveal ast file.py --where 'name~=pattern'` |
| Filter type | `reveal file.py --type function` | `reveal ast file.py --kind function` |
| Sort | `reveal file.py --sort complexity` | `reveal ast file.py --sort complexity` |
| Complex filter | ❌ (not supported) | `reveal ast src/ --where 'complexity>10' --where 'lines>50' --kind function --sort=-complexity` |

### Progressive Escalation

Start simple (file flags), escalate to the `ast` noun when needed:

```bash
# Step 1: Simple search
reveal file.py --name authenticate

# Step 2: Add type filter
reveal file.py --name authenticate --type function

# Step 3: Add sorting
reveal file.py --name authenticate --type function --sort=-complexity

# Step 4: Need complex conditions? Use the ast noun
# Note: --name PATTERN becomes --where 'name~=PATTERN' (a filter on the name field)
reveal ast file.py --where 'name~=authenticate' --where 'complexity>10' --where 'lines>50' --kind function --sort=-complexity
```

---

## Nouns with Field Filters

These 5 nouns take the filter expressions and result controls below:

| Noun | Filter fields | Example |
|------|---------------|---------|
| **json** | Any JSON field | `reveal json data.json --where 'age>25' --where role=admin` |
| **markdown** | Frontmatter fields | `reveal markdown docs/ --where status=draft --where 'tags~=python'` |
| **metrics** | File metrics | `reveal metrics src/ --where 'complexity>10' --where 'lines<100'` |
| **ast** | Code elements | `reveal ast src/ --kind function --where 'lines>50'` |
| **git** | Commit metadata | `reveal git . --where author=John --where 'message~=fix'` |

---

## Universal Operators

All 5 nouns support these operators in `--where` through the unified `compare_values()` function:

### Comparison Operators

| Operator | Description | Example | Matches |
|----------|-------------|---------|---------|
| `=` or `==` | Exact match (case-insensitive on json and git; case-sensitive on markdown and ast) | `status=active` | "active", "Active", "ACTIVE" (json) |
| `!=` | Not equal | `status!=draft` | Anything except "draft" |
| `>` | Greater than | `lines>50` | 51, 100, 200... |
| `<` | Less than | `complexity<10` | 1, 5, 9... |
| `>=` | Greater or equal | `priority>=5` | 5, 6, 10... |
| `<=` | Less or equal | `functions<=20` | 1, 10, 20 |
| `~=` | Regex match (ignores case; case-sensitive on ast) | `message~=bug.*fix` | "Bug fix", "fixed bug fix" |
| `!~` | Regex does not match | `email!~@company.com` | any email not at company.com |
| `..` | Range (inclusive) | `lines=50..200` | 50, 100, 200 |

`~=` and `!~` ignore case on json, markdown, git and metrics, and are case-sensitive on
ast (code is case-sensitive; start the pattern with `(?i)` there to ignore case). The negated regex is `!~` (not `!~=`, which is mis-parsed and
filters everything out).

### Type Coercion

**Numeric comparison**:
- Strings automatically coerced to numbers: `"50" > 25` → true
- Non-numeric strings fail gracefully (no match)

**String comparison**:
- `=` is case-insensitive on json and git, case-sensitive on markdown and ast
- git: `author=John` matches "john", "John", "JOHN" (the whole author name)

**Boolean coercion**:
- `"true"`, `"yes"`, `"1"` → true
- `"false"`, `"no"`, `"0"` → false

---

## Result Control

Control how results are sorted and paginated:

| Flag | Description | Example |
|------|-------------|---------|
| `--sort FIELD` | Sort ascending | `--sort lines` |
| `--sort=-FIELD` | Sort descending | `--sort=-complexity` |
| `--limit N` | Limit to N results (`0` = no cap) | `--limit 20` |
| `--offset M` | Skip first M results | `--offset 10` (pagination) |

`null` and missing values sort last in both directions on `json`, `ast`, `markdown`,
`metrics` and `git`, in their source order, so `--sort=-age` lists the largest ages first and
the people with no age at the end. A missing value is not sorted as a zero.

### Examples

```bash
# Top 10 most complex functions
reveal ast src/ --kind function --sort=-complexity --limit 10

# Files 50-100 lines, by complexity
reveal metrics src/ --where lines=50..100 --sort=-complexity

# Recent commits by John, newest first
reveal git . --where author=John --sort=-date --limit 20

# Paginated results (page 2, 10 items per page)
reveal json data.json --where status=active --sort name --limit 10 --offset 10
```

---

## Adapter-by-Adapter Examples

### json - JSON Data Filtering

**Numeric filters**:
```bash
reveal json data.json --where 'age>25'       # Age over 25
reveal json data.json --where 'count>=100'   # Count 100+
reveal json data.json --where score=80..95   # Score range
```

**String filters**:
```bash
reveal json data.json --where status=active     # Exact match
reveal json data.json --where 'status!=draft'   # Not draft
reveal json data.json --where 'name~=john'      # Name contains "john" (any case)
```

**Combined filters**:
```bash
reveal json data.json --where role=admin --where 'age>30' --where status=active
```

**Sorting**:
```bash
reveal json data.json --where status=active --sort name
reveal json data.json --where role=admin --sort=-age --limit 10
```

---

### markdown - Frontmatter Queries

**Status filtering**:
```bash
reveal markdown docs/ --where status=draft         # Draft documents
reveal markdown docs/ --where 'status!=archived'   # Not archived
```

**Tag filtering**:
```bash
reveal markdown docs/ --where 'tags~=python'                        # Tagged "python" (any case)
reveal markdown docs/ --where 'tags~=api' --where status=complete   # Tagged "api" and complete
```

**Date filtering**:
```bash
reveal markdown docs/ --where created=2026-01-01..2026-12-31   # Created in 2026
reveal markdown docs/ --where updated=2026-01-01..2026-02-28   # January-February 2026
```

Frontmatter dates compare as ISO strings: `created>2026-01-01` and a range with full `YYYY-MM-DD`
bounds both work. A short bound such as `2026-02` excludes every February date
(`"2026-02-01" > "2026-02"`).

**Priority and sorting**:
```bash
reveal markdown docs/ --where 'priority>=5' --limit 10
```

markdown filters on any frontmatter key but sorts only on the fields it puts in each result
(`path`, `relative_path`, `modified`, `mtime`, `status`, `has_frontmatter`); `--sort=-priority`
leaves the results unsorted with a warning.

**Body text search** (markdown-specific):
```bash
reveal markdown docs/ --match nginx                                # Body mentions "nginx"
reveal markdown docs/ --match nginx --match ssl                    # Body mentions both (AND)
reveal markdown docs/ --where type=guide --match nginx --limit 5   # Combine with frontmatter + limit
```

**Field existence** (markdown-specific):
```bash
reveal markdown docs/ --where '!published'                # No published date
```

---

### metrics - File Metrics Filtering

**Complexity filtering**:
```bash
reveal metrics src/ --where 'complexity>10'    # Complex files
reveal metrics src/ --where complexity=5..15   # Medium complexity
```

A metrics range (`--where field=a..b`) is inclusive and returns the same files as
`--where 'field>=a' --where 'field<=b'`.

**Size filtering**:
```bash
reveal metrics src/ --where 'lines>500'      # Large files
reveal metrics src/ --where 'lines<50'       # Small files
reveal metrics src/ --where lines=100..500   # Medium files
```

**Quality filtering**:
```bash
reveal metrics src/ --where 'quality<50'     # Low quality
reveal metrics src/ --where 'functions>20'   # Many functions
```

**Hotspot analysis**:
```bash
# 20 most complex files
reveal metrics src/ --sort=-complexity --limit 20

# Large, complex files (refactoring candidates)
reveal metrics src/ --where 'lines>200' --where 'complexity>10' --sort=-complexity

# Small but complex (needs splitting)
reveal metrics src/ --where 'lines<100' --where 'complexity>15'
```

---

### ast - Code Element Filtering

**Type filtering** (AST-specific `in` operator):
```bash
reveal ast src/ --kind function   # Functions only
reveal ast src/ --kind class      # Classes only
```

**Complexity filtering**:
```bash
reveal ast src/ --where 'complexity>10'   # Complex elements
reveal ast src/ --where 'complexity<=5'   # Simple elements
```

**Size filtering**:
```bash
reveal ast src/ --where 'lines>50'     # Long functions
reveal ast src/ --where lines=20..50   # Medium functions
```

**Name filtering** (glob support):
```bash
reveal ast src/ --where 'name=test_*'   # Test functions
reveal ast src/ --where 'name~=^get_'   # Getters (regex)
```

**Quality queries**:
```bash
# Top 10 most complex functions
reveal ast src/ --kind function --sort=-complexity --limit 10

# Long but simple functions (candidates for refactoring)
reveal ast src/ --where 'lines>100' --where 'complexity<5'

# Small, complex functions (needs simplification)
reveal ast src/ --where 'lines<30' --where 'complexity>10'
```

---

### git - Commit Filtering

**Author filtering**:
```bash
reveal git . --where author=John             # Exact full-name match (use author~= for part of a name)
reveal git . --where 'author~=john'          # Contains "john" (any case)
reveal git . --where 'email~=@example.com'   # Company emails
```

**Message filtering**:
```bash
reveal git . --where 'message~=bug'         # Bug fixes
reveal git . --where 'message~=^feat:'      # Features (conventional commits)
reveal git . --where 'message~=(fix|bug)'   # Fixes or bugs
```

**Combined filters**:
```bash
# John's bug fixes
reveal git . --where author=John --where 'message~=bug'

# Recent work by email domain
reveal git . --where 'email~=@company.com' --sort=-date --limit 20

# Features by specific author
reveal git . --where 'author~=jane' --where 'message~=^feat:' --sort=-date
```

**Hash filtering**:
```bash
reveal git . --where hash=a1b2c3                        # Commit by prefix
```

**Date filtering**:
```bash
reveal git . --where 'date>2026-02-01'               # After 1 Feb (1 Feb itself excluded)
reveal git . --where 'date>=2026-02-01'              # From 1 Feb on (1 Feb included)
reveal git . --since 2026-01-01 --until 2026-01-31   # All of January
reveal git . --where date=2026-02-06                 # Any commit on 6 Feb
reveal git . --where 'date>2026-10-27T22:00:00Z'     # After 22:00 UTC (zone converted)
```

A year, month or day bound names the whole period: `date=P` is any time in P, `date!=P` any time
outside it, `date>P` is after the end of P, `date<P` before its start, and `date>=P`, `date<=P`
and a range `date=P1..P2` include all of P, so `date>2026-01` starts in February,
`until=2026-01` includes January and `date<=2025` includes all of 2025. A full timestamp bound
(`date>2026-02-01 12:00:00`, or `2026-02-01T12:00:00`) compares the timestamp. Commit dates are
written in the local time of the machine running reveal with its UTC offset (`2026-02-01 04:00:00 -0800`),
and a bound compares the clock part; a bound with a zone
(`Z`, `+02:00`) is converted to that local time first, and `+` is written as itself.

A filter on a field no commit has (`reveal git . --where 'authr~=Scott'`) is an invalid request: exit 2,
naming the supported controls and the commit fields (`hash`, `author`, `email`, `date`, `timestamp`, `message` and
`content`), as on metrics. Git and Metrics have a fixed field list; json and markdown, whose fields come from
the data, answer instead with an `unknown_filter_field` warning (exit 0).

**File history**:
```bash
reveal git app.py --view history --where author=John --sort=-date --limit 10
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
- Ignores case except on ast (prefix `(?i)` there to ignore case)
- `message~=bug.*fix` matches "Bug fix for login"

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

Repeat `--where` - every filter must match:

```bash
# JSON: Admin users over 30
reveal json data.json --where role=admin --where 'age>30'

# Markdown: High-priority Python docs
reveal markdown docs/ --where 'tags~=python' --where 'priority>=5' --where status=draft

# Metrics: Large, complex files
reveal metrics src/ --where 'lines>200' --where 'complexity>10'

# Git: John's bug fixes this year
reveal git . --where author=John --where 'message~=bug' --where 'date>2026-01-01'

# AST: Long, complex functions
reveal ast src/ --where 'lines>100' --where 'complexity>15' --kind function
```

**Behavior**:
- Filters are ANDed together
- Each filter narrows results
- A field may repeat and every condition applies: `reveal ast src/ --kind function --where 'kind!=method'`,
  `reveal json data.json --where 'age>30' --where 'age<40'`
- No general OR operator: ast's `--kind` accepts `'function|method'`; elsewhere use a regex `~=(foo|bar)`

---

## Advanced Patterns

### Progressive Filtering

Start broad, narrow down:

```bash
# 1. See all files
reveal metrics src/

# 2. Filter to large files
reveal metrics src/ --where 'lines>100'

# 3. Add complexity filter
reveal metrics src/ --where 'lines>100' --where 'complexity>10'

# 4. Sort and limit
reveal metrics src/ --where 'lines>100' --where 'complexity>10' --sort=-complexity --limit 10
```

---

### Top-N Queries

Find worst/best items:

```bash
# Top 10 most complex functions
reveal ast src/ --kind function --sort=-complexity --limit 10

# 20 largest files
reveal metrics src/ --sort=-lines --limit 20

# Most active committers (recent)
reveal git . --view history --limit 50 --format json | jq '.history | group_by(.author) | map({author: .[0].author, count: length}) | sort_by(-.count)'

# Worst quality files
reveal metrics src/ --sort quality --limit 10
```

---

### Range + Sort Queries

Filter by range, sort within range:

```bash
# Medium-sized files by complexity
reveal metrics src/ --where lines=100..500 --sort=-complexity

# Functions 20-50 lines, most complex first
reveal ast src/ --where lines=20..50 --sort=-complexity

# Commits from January, newest first
reveal git . --where date=2026-01..2026-02 --sort=-date
```

---

### Pagination

Paginate large result sets:

```bash
# Page 1 (first 10)
reveal json data.json --where status=active --sort name --limit 10

# Page 2 (next 10)
reveal json data.json --where status=active --sort name --limit 10 --offset 10

# Page 3 (next 10)
reveal json data.json --where status=active --sort name --limit 10 --offset 20
```

---

### Regex OR Queries

Use regex for OR logic:

```bash
# Bug fixes or features
reveal git . --where 'message~=(bug|feat)'

# Python or JavaScript files
reveal metrics src/ --where 'file~=\.(py|js)$'

# Test or spec files
reveal ast src/ --where 'name~=(test_|spec_)'

# Admin or moderator roles
reveal json users.json --where 'role~=(admin|moderator)'
```

---

## Configuration Options

The `compare_values()` function accepts options to configure behavior per adapter:

| Adapter | List Matching | Case Sensitive (`=`) | Numeric Coercion | Null != |
|---------|---------------|----------------|------------------|---------|
| **json** | ✅ Any | ❌ No | ✅ Yes | ✅ Yes |
| **markdown** | ✅ Any | ✅ Yes | ✅ Yes | ✅ Yes |
| **metrics** | ❌ No | ❌ No | ✅ Yes | ❌ No |
| **ast** | ❌ No | ✅ Yes | ✅ Yes | ❌ No |
| **git** | ❌ No | ❌ No | ✅ Yes | ✅ Yes |

The column is about `=` and wildcards. `~=` and `!~` follow the same setting, except on markdown:
there `=` and wildcards are case-sensitive (a plain `field=value` filter) but `~=`/`!~` ignore case.

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
reveal metrics src/ --where 'lines>200' --where 'complexity>10' --sort=-complexity

# Technical debt hotspots
reveal metrics src/ --where 'quality<50' --sort quality --limit 20

# Overly complex small functions
reveal ast src/ --where 'lines<50' --where 'complexity>10' --kind function

# Long functions needing splitting
reveal ast src/ --where 'lines>100' --kind function --sort=-lines
```

---

### Documentation Management

```bash
# Unfinished high-priority docs
reveal markdown docs/ --where status=draft --where 'priority>=5'

# Stale documentation
reveal markdown docs/ --where 'updated<2025-01-01'

# Python API documentation
reveal markdown docs/ --where 'tags~=python' --where 'tags~=api' --where status=complete

# Missing publication dates
reveal markdown docs/ --where '!published' --where status=complete
```

---

### Git Analysis

```bash
# Bug fix commits this month
reveal git . --where 'message~=bug' --where 'date>2026-02-01' --sort=-date

# Feature commits by author
reveal git . --where 'message~=^feat:' --where author=John --sort=-date

# Commits from external contributors
reveal git . --view history --where 'email!~@company.com' --sort=-date

# Recent work by file
reveal git app.py --view history --sort=-date --limit 10
```

---

### Data Analysis

```bash
# Active admin users
reveal json users.json --where role=admin --where status=active --sort last_login

# High-value customers
reveal json customers.json --where 'lifetime_value>10000' --sort=-lifetime_value

# Recent orders over $100
reveal json orders.json --where 'total>100' --where 'date>2026-01-01' --sort=-date

# Age demographics
reveal json users.json --where age=25..35 --where status=active
```

---

## Best Practices

### 1. Use Quotes

Quote a filter whose value holds a shell character (`>`, `<`, `|`, `&`, `*`, `$`, `!`, `(`):

```bash
reveal json data.json --where 'age>25'   # ✅ Correct: the quotes keep > in the value
reveal json data.json --where age>25     # ❌ Unquoted, the shell reads >25 as a redirect to a file named 25
```

---

### 2. Start Broad, Then Filter

```bash
# 1. See structure
reveal metrics src/

# 2. Filter
reveal metrics src/ --where 'complexity>10'

# 3. Sort and limit
reveal metrics src/ --where 'complexity>10' --sort=-complexity --limit 10
```

---

### 3. Combine Complementary Filters

```bash
# Good: Specific, actionable query
reveal metrics src/ --where 'lines>200' --where 'complexity>10' --sort=-complexity --limit 20

# Less useful: Too broad
reveal metrics src/ --where 'lines>100'
```

---

### 4. Use Result Control

Always sort and limit large result sets:

```bash
# Good: Top 10 results
reveal json data.json --where status=active --sort name --limit 10

# Overwhelming: All results
reveal json data.json --where status=active
```

---

### 5. Test Incrementally

Build complex queries step by step:

```bash
# Step 1: Basic filter
reveal git . --where author=John

# Step 2: Add message filter
reveal git . --where author=John --where 'message~=bug'

# Step 3: Sort and limit
reveal git . --where author=John --where 'message~=bug' --sort=-date --limit 10
```

---

## See Also

- [Query Parameter Reference](QUERY_PARAMETER_REFERENCE.md) - Each noun's own options
- [Adapter Authoring Guide](../development/ADAPTER_AUTHORING_GUIDE.md) - Add query support to custom adapters
- [Agent Help](../AGENT_HELP.md) - AI agent integration guide
- [Output Contract](../development/OUTPUT_CONTRACT.md) - Adapter output specification

---

## Implementation Details

**Phase 3 Completion** (2026-02-08):
- Unified query parser in `reveal/utils/query_parser.py`, operators in `reveal/utils/query_eval.py`, sort/limit/offset in `reveal/utils/query_control.py` (`reveal/utils/query.py` re-exports all three)
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
