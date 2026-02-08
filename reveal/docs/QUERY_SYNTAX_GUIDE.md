---
title: Query Syntax Guide
description: Complete reference for unified query operators and result control
date: 2026-02-08
phase: Phase 3 Complete
---

# Query Syntax Guide

**Status**: Phase 3 Complete (2026-02-08) - Universal query operators standardized across all 5 query-capable adapters.

This guide documents the **unified query syntax** that works consistently across Reveal's query-capable adapters. All operators described here use the same underlying comparison logic (`compare_values()` in `reveal/utils/query.py`), ensuring consistent behavior.

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
reveal 'stats://src/?lines=100..500&sort=-complexity'

# Regex matching
reveal 'git://.?message~=bug.*fix'
```

---

## Query-Capable Adapters

These 5 adapters support the unified query syntax:

| Adapter | Query Fields | Example |
|---------|--------------|---------|
| **json://** | Any JSON field | `json://data.json?age>25&role=admin` |
| **markdown://** | Frontmatter fields | `markdown://docs/?status=draft&tags~=python` |
| **stats://** | File metrics | `stats://src/?complexity>10&lines<100` |
| **ast://** | Code elements | `ast://src/?type=function&lines>50` |
| **git://** | Commit metadata | `git://.?author=John&message~=fix` |

---

## Universal Operators

All 5 adapters support these operators through the unified `compare_values()` function:

### Comparison Operators

| Operator | Description | Example | Matches |
|----------|-------------|---------|---------|
| `=` or `==` | Exact match (case-insensitive) | `status=active` | "active", "Active", "ACTIVE" |
| `!=` | Not equal | `status!=draft` | Anything except "draft" |
| `>` | Greater than | `lines>50` | 51, 100, 200... |
| `<` | Less than | `complexity<10` | 1, 5, 9... |
| `>=` | Greater or equal | `priority>=5` | 5, 6, 10... |
| `<=` | Less or equal | `functions<=20` | 1, 10, 20 |
| `~=` | Regex match (case-insensitive) | `message~=bug.*fix` | "Bug fix", "Fixed bug" |
| `..` | Range (inclusive) | `lines=50..200` | 50, 100, 200 |

### Type Coercion

**Numeric comparison**:
- Strings automatically coerced to numbers: `"50" > 25` → true
- Non-numeric strings fail gracefully (no match)

**String comparison**:
- Case-insensitive by default (configurable per adapter)
- `author=John` matches "john", "John", "JOHN"

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
reveal 'stats://src/?lines=50..100&sort=-complexity'

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
reveal 'json://data.json?name~=john'                # Name contains "john"
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
reveal 'markdown://docs/?tags~=python'              # Tagged with Python
reveal 'markdown://docs/?tags~=api&status=complete' # Python APIs, complete
```

**Date filtering**:
```bash
reveal 'markdown://docs/?created>2026-01-01'        # Created this year
reveal 'markdown://docs/?updated=2026-01..2026-02'  # Range query
```

**Priority and sorting**:
```bash
reveal 'markdown://docs/?priority>=5&sort=-priority&limit=10'
```

**Field existence** (markdown-specific):
```bash
reveal 'markdown://docs/?!published'                # No published date
```

---

### stats:// - File Metrics Filtering

**Complexity filtering**:
```bash
reveal 'stats://src/?complexity>10'                 # Complex files
reveal 'stats://src/?complexity=5..15'              # Medium complexity
```

**Size filtering**:
```bash
reveal 'stats://src/?lines>500'                     # Large files
reveal 'stats://src/?lines<50'                      # Small files
reveal 'stats://src/?lines=100..500'                # Medium files
```

**Quality filtering**:
```bash
reveal 'stats://src/?quality_score<50'              # Low quality
reveal 'stats://src/?functions>20'                  # Many functions
```

**Hotspot analysis**:
```bash
# 20 most complex files
reveal 'stats://src/?sort=-complexity&limit=20'

# Large, complex files (refactoring candidates)
reveal 'stats://src/?lines>200&complexity>10&sort=-complexity'

# Small but complex (needs splitting)
reveal 'stats://src/?lines<100&complexity>15'
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
reveal 'git://.?author=John'                        # Exact name match
reveal 'git://.?author~=john'                       # Contains "john"
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

**String comparison** (fallback):
- Lexicographic comparison
- `name>"m"` matches "python", "ruby", "zebra"

---

### Regex Match (`~=`)

**Pattern matching**:
- Uses Python `re` module
- Case-insensitive by default
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
- `name=a..m` matches "alice", "bob", "mike"

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
reveal 'stats://src/?lines>200&complexity>10'

# Git: John's bug fixes this year
reveal 'git://.?author=John&message~=bug&date>2026-01-01'

# AST: Long, complex functions
reveal 'ast://src/?type=function&lines>100&complexity>15'
```

**Behavior**:
- Filters are ANDed together
- Each filter narrows results
- No OR operator (use regex for OR: `~=(foo|bar)`)

---

## Advanced Patterns

### Progressive Filtering

Start broad, narrow down:

```bash
# 1. See all files
reveal 'stats://src/'

# 2. Filter to large files
reveal 'stats://src/?lines>100'

# 3. Add complexity filter
reveal 'stats://src/?lines>100&complexity>10'

# 4. Sort and limit
reveal 'stats://src/?lines>100&complexity>10&sort=-complexity&limit=10'
```

---

### Top-N Queries

Find worst/best items:

```bash
# Top 10 most complex functions
reveal 'ast://src/?type=function&sort=-complexity&limit=10'

# 20 largest files
reveal 'stats://src/?sort=-lines&limit=20'

# Most active committers (recent)
reveal 'git://.?sort=-date&limit=50' | jq '.items | group_by(.author) | map({author: .[0].author, count: length}) | sort_by(-.count)'

# Worst quality files
reveal 'stats://src/?sort=quality_score&limit=10'
```

---

### Range + Sort Queries

Filter by range, sort within range:

```bash
# Medium-sized files by complexity
reveal 'stats://src/?lines=100..500&sort=-complexity'

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
reveal 'stats://src/?path~=\.(py|js)$'

# Test or spec files
reveal 'ast://src/?name~=(test_|spec_)'

# Admin or moderator roles
reveal 'json://users.json?role~=(admin|moderator)'
```

---

## Configuration Options

The `compare_values()` function accepts options to configure behavior per adapter:

| Adapter | List Matching | Case Sensitive | Numeric Coercion | Null != |
|---------|---------------|----------------|------------------|---------|
| **json://** | ✅ Any | ❌ No | ✅ Yes | ✅ Yes |
| **markdown://** | ✅ Any | ❌ No | ✅ Yes | ✅ Yes |
| **stats://** | ❌ No | ❌ No | ✅ Yes | ❌ No |
| **ast://** | ❌ No | ✅ Yes | ✅ Yes | ❌ No |
| **git://** | ❌ No | ❌ No | ✅ Yes | ✅ Yes |

**Rationale**:
- **JSON/Markdown**: Have list fields (tags, topics), need case-insensitive search
- **Stats**: Numeric-focused, no lists
- **AST**: Code is case-sensitive
- **Git**: Commit metadata, case-insensitive search

---

## Common Patterns

### Code Quality Analysis

```bash
# Refactoring candidates (large + complex)
reveal 'stats://src/?lines>200&complexity>10&sort=-complexity'

# Technical debt hotspots
reveal 'stats://src/?quality_score<50&sort=quality_score&limit=20'

# Overly complex small functions
reveal 'ast://src/?type=function&lines<50&complexity>10'

# Long functions needing splitting
reveal 'ast://src/?type=function&lines>100&sort=-lines'
```

---

### Documentation Management

```bash
# Unfinished high-priority docs
reveal 'markdown://docs/?status=draft&priority>=5&sort=-priority'

# Stale documentation
reveal 'markdown://docs/?updated<2025-01-01&sort=updated'

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
reveal 'git://.?email!~=@company.com&sort=-date'

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
reveal 'stats://src/'

# 2. Filter
reveal 'stats://src/?complexity>10'

# 3. Sort and limit
reveal 'stats://src/?complexity>10&sort=-complexity&limit=10'
```

---

### 3. Combine Complementary Filters

```bash
# Good: Specific, actionable query
reveal 'stats://src/?lines>200&complexity>10&sort=-complexity&limit=20'

# Less useful: Too broad
reveal 'stats://src/?lines>100'
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
- [Adapter Authoring Guide](ADAPTER_AUTHORING_GUIDE.md) - Add query support to custom adapters
- [Agent Help](AGENT_HELP.md) - AI agent integration guide
- [Output Contract](OUTPUT_CONTRACT.md) - Adapter output specification

---

## Implementation Details

**Phase 3 Completion** (2026-02-08):
- Unified query parser in `reveal/utils/query.py`
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

**Session**: hosuki-0208 (Phase 3 completion)
