---
title: AST Adapter Guide
category: guide
---
# AST Adapter Guide

**Version**: 1.0 (reveal 0.49.2+)
**Status**: 🟢 Stable - Production Ready
**Adapter**: `ast://`

---

## Table of Contents

- [Quick Start](#quick-start)
- [Overview](#overview)
- [Features](#features)
- [Query Parameters](#query-parameters)
- [Operators](#operators)
- [Output Formats](#output-formats)
- [Common Workflows](#common-workflows)
- [Result Control](#result-control)
- [Performance](#performance)
- [Limitations](#limitations)
- [Error Messages](#error-messages)
- [Tips & Best Practices](#tips-best-practices)
- [Integration with Other Tools](#integration-with-other-tools)
- [Related Documentation](#related-documentation)
- [Version History](#version-history)

---

## Quick Start

The AST adapter lets you query code as a database - find functions, classes, and methods by their properties like complexity, size, name patterns, and decorators.

**Common examples:**

```bash
# 1. Find all code structure in a directory
reveal 'ast://./src'

# 2. Find functions with more than 50 lines (refactor candidates)
reveal 'ast://./src?lines>50'

# 3. Find complex functions (industry threshold: >10 needs refactoring)
reveal 'ast://./src?complexity>10'

# 4. Find functions by name pattern
reveal 'ast://./src?name=*authenticate*'

# 5. Find all @property decorated methods
reveal 'ast://.?decorator=property'

# 6. Combine filters: complex AND long functions
reveal 'ast://./src?complexity>10&lines>50'

# 7. Top 10 most complex functions (NEW: sort + limit)
reveal 'ast://./src?complexity>5&sort=-complexity&limit=10'

# 8. Get JSON output for scripting
reveal 'ast://./src?complexity>10' --format=json
```

**Note**: Quote URIs containing `>` or `<` to prevent shell redirection.

---

## Overview

### What is the AST Adapter?

The `ast://` adapter provides **semantic code search** - it parses source code into an Abstract Syntax Tree (AST) and lets you query code elements by their structural properties, not just text matching.

**Why use ast:// instead of grep?**

| Task | grep | ast:// |
|------|------|--------|
| Find function by name | ❌ Matches comments, strings | ✅ Only actual functions |
| Find complex code | ❌ Can't measure complexity | ✅ McCabe complexity built-in |
| Find long functions | ❌ Manual counting | ✅ `lines>50` filter |
| Find decorated functions | ❌ Text matching only | ✅ `decorator=property` filter |
| Structured output | ❌ Plain text | ✅ JSON with metadata |

**Key capabilities:**

- 🔍 **Query by properties**: Find functions by complexity, size, type, decorators
- 🎯 **Pattern matching**: Wildcards (`*`, `?`) and regex (`~=`) for name searches
- 📊 **Complexity analysis**: McCabe cyclomatic complexity calculation
- 🔗 **Multi-language**: Supports 50+ languages via tree-sitter
- 📈 **Result control**: Sort, limit, offset for efficient queries
- 🤖 **AI-friendly**: JSON schema for agent integration

---

## Features

### 1. **AST Structure Queries**

Extract complete code structure from files or directories:

```bash
# All functions, classes, methods in a file
reveal ast://app.py

# All code in a directory (recursive)
reveal 'ast://./src'
```

**Output includes:**
- Function/class/method names
- Line numbers
- Line counts
- Complexity metrics
- Decorator lists
- Type information

### 2. **Complexity Filtering**

Find code that needs refactoring using McCabe cyclomatic complexity:

```bash
# Industry threshold: >10 needs attention
reveal 'ast://./src?complexity>10'

# Danger zone: >20 is high risk
reveal 'ast://./src?complexity>20'

# Prime refactoring targets: complex AND long
reveal 'ast://./src?complexity>15&lines>100'
```

**Complexity thresholds:**
- **1-5**: Simple, easy to test
- **6-10**: Moderate complexity
- **11-20**: Needs refactoring
- **21+**: High risk, difficult to maintain

### 3. **Size Filtering**

Find oversized functions that violate single-responsibility principle:

```bash
# Functions with >50 lines
reveal 'ast://./src?lines>50'

# Functions with >100 lines (likely doing too much)
reveal 'ast://./src?lines>100'

# Range queries: functions between 50-200 lines
reveal 'ast://./src?lines=50..200'

# Simple but long (splitting candidates)
reveal 'ast://./src?complexity<5&lines>50'
```

### 4. **Name Pattern Matching**

Find code elements by name using wildcards or regex:

```bash
# Wildcard matching (glob-style)
reveal 'ast://./src?name=test_*'           # Starts with test_
reveal 'ast://./src?name=*helper*'         # Contains "helper"
reveal 'ast://./src?name=get_?'            # get_ + one char

# Regex matching (NEW: ~= operator)
reveal 'ast://./src?name~=^test_'          # Regex: starts with test_
reveal 'ast://./src?name~=.*Manager$'      # Regex: ends with Manager
```

### 5. **Type Filtering**

Filter by code element type:

```bash
# Only functions (not classes or methods)
reveal 'ast://./src?type=function'

# Only classes
reveal 'ast://./src?type=class'

# Multiple types (OR logic)
reveal 'ast://./src?type=class|function'
reveal 'ast://./src?type=class,function'   # Comma also works

# Everything except functions (NEW: != operator)
reveal 'ast://./src?type!=function'
```

**Valid types:**
- `function` - Top-level functions
- `class` - Class definitions
- `method` - Class methods

### 6. **Decorator Filtering**

Find functions/classes by their decorators:

```bash
# Find all @property methods
reveal 'ast://.?decorator=property'

# Find all cached functions (wildcard matching)
reveal 'ast://.?decorator=*cache*'
# Matches: @lru_cache, @cached_property, @cache, etc.

# Find static methods
reveal 'ast://.?decorator=staticmethod'

# Find abstract methods
reveal 'ast://.?decorator=abstractmethod'

# Find complex properties (code smell - properties should be simple)
reveal 'ast://.?decorator=property&lines>10'

# Exclude specific decorators (NEW: != operator)
reveal 'ast://.?decorator!=property'
```

### 7. **Combined Filters**

Stack multiple filters with AND logic:

```bash
# Complex AND long functions
reveal 'ast://./src?complexity>10&lines>50'

# Long but simple (good splitting candidates)
reveal 'ast://./src?complexity<5&lines>50'

# Complex properties (code smell)
reveal 'ast://.?decorator=property&lines>10'

# Test functions that are too long
reveal 'ast://./tests?name=test_*&lines>100'

# Entry points that are complex
reveal 'ast://./src?name=main*&complexity>10'
```

---

## Query Parameters

Complete reference of all supported query parameters:

| Parameter | Type | Description | Examples |
|-----------|------|-------------|----------|
| `lines` | integer | Number of lines in function/class | `lines>50`, `lines=10..100` |
| `complexity` | integer | McCabe cyclomatic complexity (>10 needs refactoring, >20 high risk) | `complexity>10`, `complexity<5` |
| `type` | string | Element type: `function`, `class`, `method`. Supports OR with `\|` or `,` | `type=function`, `type=class\|function` |
| `name` | string | Element name with wildcards (`*` = any chars, `?` = one char) or regex | `name=test_*`, `name~=^test_` |
| `decorator` | string | Decorator pattern with wildcards or regex | `decorator=property`, `decorator=*cache*` |

**Parameter capabilities:**

- **Numeric parameters** (`lines`, `complexity`): Support all comparison operators
- **String parameters** (`name`, `decorator`): Support wildcards, regex, negation
- **Type parameter**: Supports OR logic for multiple types
- **All parameters**: Can be combined with AND logic using `&`

---

## Operators

### Comparison Operators

Used with numeric parameters (`lines`, `complexity`):

| Operator | Meaning | Example |
|----------|---------|---------|
| `>` | Greater than | `lines>50` |
| `<` | Less than | `complexity<5` |
| `>=` | Greater than or equal | `lines>=100` |
| `<=` | Less than or equal | `complexity<=10` |
| `==` | Equal to | `lines==50` |
| `!=` | Not equal to (NEW) | `complexity!=0` |
| `..` | Range (inclusive) (NEW) | `lines=50..200` |

### String Operators

Used with string parameters (`name`, `decorator`, `type`):

| Operator | Meaning | Example |
|----------|---------|---------|
| `=` | Exact match or wildcard | `name=main`, `name=test_*` |
| `~=` | Regex match (NEW) | `name~=^test_` |
| `!=` | Not equal to (NEW) | `type!=function` |

### Wildcards

Used in string values for pattern matching:

| Wildcard | Meaning | Example |
|----------|---------|---------|
| `*` | Zero or more chars | `name=test_*` → `test_user`, `test_data` |
| `?` | Exactly one char | `name=get_?` → `get_a`, `get_b` |

### Logic Operators

Combine multiple conditions:

| Operator | Meaning | Example |
|----------|---------|---------|
| `&` | AND - all conditions must match | `lines>50&complexity>10` |
| `\|` or `,` | OR - any condition matches (type only) | `type=class\|function` |

---

## Output Formats

The AST adapter supports three output formats:

### 1. Text Format (Default)

Human-readable output with color coding:

```bash
reveal 'ast://./src?complexity>10'
```

**Output:**
```
src/auth.py:
  authenticate (line 45, 67 lines, complexity 15)
  validate_token (line 120, 89 lines, complexity 12)

src/api.py:
  process_request (line 78, 134 lines, complexity 18)
```

### 2. JSON Format

Structured data for programmatic processing:

```bash
reveal 'ast://./src?complexity>10' --format=json
```

**Output structure:**
```json
{
  "contract_version": "1.1",
  "type": "ast_query",
  "source": "./src",
  "source_type": "directory",
  "path": "./src",
  "query": "complexity>10",
  "total_files": 15,
  "total_results": 8,
  "displayed_results": 8,
  "results": [
    {
      "file": "src/auth.py",
      "symbol": "authenticate",
      "type": "function",
      "line": 45,
      "lines": 67,
      "complexity": 15,
      "decorators": []
    }
  ],
  "meta": {
    "parse_mode": "tree_sitter_full",
    "confidence": 1.0
  }
}
```

**JSON fields:**
- `contract_version`: Output contract version (currently 1.1)
- `type`: Always `"ast_query"`
- `query`: Formatted query string
- `total_files`: Number of files scanned
- `total_results`: Number of matches before limit/offset
- `displayed_results`: Number of results in output
- `results`: Array of matched code elements
- `meta`: Trust metadata (parse mode, confidence)

### 3. Grep Format

Machine-readable format for piping to other tools:

```bash
reveal 'ast://./src?complexity>10' --format=grep
```

**Output:**
```
src/auth.py:45:authenticate
src/auth.py:120:validate_token
src/api.py:78:process_request
```

**Format**: `<file>:<line>:<symbol>`

---

## Common Workflows

### Workflow 1: Find Refactoring Targets

**Scenario**: Codebase feels messy, need to prioritize cleanup.

```bash
# Step 1: Find complex functions (industry threshold: >10)
reveal 'ast://./src?complexity>10'

# Step 2: Find oversized functions (>100 lines)
reveal 'ast://./src?lines>100'

# Step 3: Find the worst offenders (complex AND long)
reveal 'ast://./src?complexity>15&lines>100'

# Step 4: Sort by complexity to prioritize
reveal 'ast://./src?complexity>10&sort=-complexity&limit=10'

# Step 5: Drill into a specific problem file
reveal src/problem_file.py --outline

# Step 6: Extract a specific function for analysis
reveal src/problem_file.py big_function
```

**Expected outcome**: Prioritized list of refactoring targets, worst offenders first.

### Workflow 2: Explore Unknown Codebase

**Scenario**: New project, need to understand structure and entry points.

```bash
# Step 1: Find entry points
reveal 'ast://.?name=main*'
reveal 'ast://.?name=*main*'

# Step 2: Find CLI handlers
reveal 'ast://.?name=*cli*|*command*'

# Step 3: Survey class hierarchy
reveal 'ast://.?type=class'

# Step 4: Find configuration loading
reveal 'ast://.?name=*config*'

# Step 5: Drill into a key file
reveal src/core.py --outline
```

**Expected outcome**: Mental map of codebase architecture and key components.

### Workflow 3: Pre-Commit Quality Check

**Scenario**: About to commit, want to ensure code quality.

```bash
# Check complexity of changed files
git diff --name-only | grep '\.py$' | \
  xargs -I{} reveal 'ast://{}?complexity>10'

# Find long functions in changed files
git diff --name-only | grep '\.py$' | \
  xargs -I{} reveal 'ast://{}?lines>50'

# Run full quality checks on changed files
git diff --name-only | xargs -I{} reveal {} --check
```

**Expected outcome**: Catch quality issues before they enter the codebase.

### Workflow 4: Analyze Decorator Patterns

**Scenario**: Understand caching strategy, API surface, code patterns.

```bash
# Step 1: Find all properties
reveal 'ast://.?decorator=property'

# Step 2: Find all cached/memoized functions
reveal 'ast://.?decorator=*cache*'
# Matches: @lru_cache, @cached_property, @cache

# Step 3: Find static methods (might not need class)
reveal 'ast://.?decorator=staticmethod'

# Step 4: Find abstract interface
reveal 'ast://.?decorator=abstractmethod'

# Step 5: Find code smells (complex properties)
reveal 'ast://.?decorator=property&lines>10'

# Step 6: Get JSON for analysis
reveal 'ast://.?decorator=*cache*' --format=json | \
  jq -r '.results[] | "\(.file):\(.line) \(.symbol)"'
```

**Expected outcome**: Understanding of caching patterns and potential issues.

### Workflow 5: Test Suite Analysis

**Scenario**: Understand test coverage and identify problem tests.

```bash
# Step 1: Find all test functions
reveal 'ast://./tests?name=test_*'

# Step 2: Find long tests (>100 lines = potential issues)
reveal 'ast://./tests?name=test_*&lines>100'

# Step 3: Find complex tests (hard to maintain)
reveal 'ast://./tests?name=test_*&complexity>10'

# Step 4: Count tests per file
reveal 'ast://./tests?name=test_*' --format=json | \
  jq -r '.results[].file' | sort | uniq -c | sort -rn
```

**Expected outcome**: Test quality assessment and problem test identification.

### Workflow 6: API Surface Documentation

**Scenario**: Generate API documentation from code structure.

```bash
# Step 1: Find all public classes
reveal 'ast://./src?type=class' --format=json

# Step 2: Find all public functions (not starting with _)
reveal 'ast://./src?type=function' --format=json | \
  jq '.results[] | select(.symbol | startswith("_") | not)'

# Step 3: Find all @property methods (getters/setters)
reveal 'ast://./src?decorator=property' --format=json

# Step 4: Create API index
reveal 'ast://./src?type=class|function' --format=json | \
  jq -r '.results[] | "\(.file):\(.line) [\(.type)] \(.symbol)"' | \
  sort > api_index.txt
```

**Expected outcome**: Complete API surface documentation.

---

## Result Control

**NEW in v0.49.0**: Result control parameters for efficient queries.

### Sort Results

Sort output by any field:

```bash
# Sort by complexity (ascending)
reveal 'ast://./src?complexity>5&sort=complexity'

# Sort by complexity (descending - most complex first)
reveal 'ast://./src?complexity>5&sort=-complexity'

# Sort by lines (shortest first)
reveal 'ast://./src?sort=lines'

# Sort by lines (longest first)
reveal 'ast://./src?sort=-lines'

# Sort by name (alphabetical)
reveal 'ast://./src?sort=name'
```

**Sortable fields:**
- `complexity` - McCabe complexity
- `lines` - Line count
- `name` - Function/class name
- `line` - Line number in file

### Limit Results

Restrict output to first N results:

```bash
# Top 10 most complex functions
reveal 'ast://./src?sort=-complexity&limit=10'

# Top 5 longest functions
reveal 'ast://./src?sort=-lines&limit=5'

# First 20 results
reveal 'ast://./src?limit=20'
```

### Offset Results

Skip first N results (pagination):

```bash
# Skip first 10 results
reveal 'ast://./src?offset=10'

# Pagination: skip 10, take 10 (results 11-20)
reveal 'ast://./src?offset=10&limit=10'

# Next page (results 21-30)
reveal 'ast://./src?offset=20&limit=10'
```

### Combined Result Control

All three can be combined:

```bash
# Most complex functions, paginated
reveal 'ast://./src?complexity>5&sort=-complexity&limit=20&offset=10'

# Longest functions, top 10
reveal 'ast://./src?type=function&sort=-lines&limit=10'
```

**Performance note**: Result control happens **after** filtering, so:
1. All files are scanned
2. Filters are applied (e.g., `complexity>10`)
3. Results are sorted/limited/offset
4. Output is generated

This means `limit=10` still scans all files but only returns 10 results.

---

## Performance

### Query Speed

AST queries require parsing source code, so they're slower than text search but much more accurate:

| Operation | Typical Speed | Notes |
|-----------|---------------|-------|
| Single file | 10-50ms | Tree-sitter parsing |
| Small project (<100 files) | 100-500ms | Parallel processing |
| Medium project (100-1000 files) | 1-5s | Scales linearly |
| Large project (1000+ files) | 5-30s | Consider narrowing path |

**Optimization tips:**

1. **Narrow the path**: Query specific directories instead of entire codebase
   ```bash
   # ❌ Slow: scans entire codebase
   reveal 'ast://.?complexity>10'

   # ✅ Fast: only scans src/
   reveal 'ast://./src?complexity>10'
   ```

2. **Use result control**: Limit output for large codebases
   ```bash
   reveal 'ast://./src?complexity>10&limit=20'
   ```

3. **Cache results**: For repeated queries, save JSON output
   ```bash
   reveal 'ast://./src' --format=json > structure_cache.json
   jq '.results[] | select(.complexity > 10)' structure_cache.json
   ```

### Large Codebase Strategies

For projects with 1000+ files:

**Strategy 1: Divide and conquer**
```bash
# Query subdirectories separately
for dir in src/*; do
  reveal "ast://$dir?complexity>10"
done
```

**Strategy 2: Progressive filtering**
```bash
# First pass: find problem files
reveal 'ast://./src?complexity>15' --format=json | \
  jq -r '.results[].file' | sort -u

# Second pass: deep dive into problem files
reveal ast://src/problem_file.py
```

**Strategy 3: Use CI/CD for incremental analysis**
```bash
# Only analyze changed files
git diff --name-only origin/main | grep '\.py$' | \
  xargs -I{} reveal 'ast://{}?complexity>10'
```

### Caching and Pre-computation

For very large codebases, consider pre-computing structure:

```bash
# Generate structure cache (run nightly)
reveal 'ast://./src' --format=json > structure_cache.json

# Query cache with jq (instant)
jq '.results[] | select(.complexity > 10)' structure_cache.json
jq '.results[] | select(.lines > 100)' structure_cache.json
```

**Cache invalidation**: Regenerate when files change.

---

## Limitations

### What AST Queries CAN'T Do

**1. Cross-file analysis**

AST queries operate on individual code elements, not relationships between files:

❌ "Find all callers of function X"
❌ "Find all classes that inherit from Y"
✅ Use `imports://` adapter for dependency analysis

**2. Runtime behavior**

AST is static analysis only:

❌ "Find functions that throw exceptions"
❌ "Find functions that call external APIs"
✅ Use dynamic analysis or runtime inspection

**3. Comment/docstring content**

AST doesn't parse documentation:

❌ "Find functions with TODO comments"
❌ "Find functions with missing docstrings"
✅ Use grep or markdown adapter for documentation analysis

**4. Variable/data flow**

AST doesn't track data flow:

❌ "Find functions that modify global state"
❌ "Find unused variables"
✅ Use linters (pylint, ruff) for data flow analysis

**5. Semantic equivalence**

AST can't understand code meaning:

❌ "Find functions that do authentication"
✅ Use name patterns: `name=*auth*` (approximation)

### Current Implementation Limitations

**Complexity calculation**: Currently heuristic-based (line count proxy). Tree-sitter-based McCabe calculation coming soon.

**Language support**: Tree-sitter parsers available for 50+ languages, but complexity/decorator extraction may be Python-specific. Check language support:

```bash
reveal --languages
```

**Decorator matching**: Python-specific. Other languages may not support decorator filtering.

---

## Error Messages

### Common errors and solutions:

**1. Invalid operator**

```
Error: Invalid operator '!=' for parameter 'lines'
```

**Cause**: Used unsupported operator for parameter type.
**Solution**: Check [Operators](#operators) table for valid operators per parameter type.

**2. Path not found**

```
Error: Path './src' does not exist
```

**Cause**: Specified path doesn't exist.
**Solution**: Check path spelling, use `ls` to verify directory exists.

**3. Syntax error in query**

```
Error: Failed to parse query string: lines>>50
```

**Cause**: Double operator or invalid syntax.
**Solution**: Use single operators: `lines>50` not `lines>>50`.

**4. No results**

```
No results found matching query: complexity>10
```

**Cause**: No code elements match filters.
**Solution**: Relax filters or verify you're querying the right path.

**5. Tree-sitter parsing error**

```
Warning: Failed to parse file.py (tree-sitter error)
```

**Cause**: File contains syntax errors or unsupported language features.
**Solution**: Fix syntax errors or exclude file from query.

---

## Tips & Best Practices

### Progressive Disclosure

Start broad, then narrow:

```bash
# 1. Survey entire codebase
reveal 'ast://./src'

# 2. Filter by complexity
reveal 'ast://./src?complexity>10'

# 3. Sort and limit to top offenders
reveal 'ast://./src?complexity>10&sort=-complexity&limit=10'

# 4. Drill into specific file
reveal src/problem_file.py --outline

# 5. Extract specific function
reveal src/problem_file.py problematic_function
```

### Wildcard Best Practices

**Use wildcards for exploration:**

```bash
# Find authentication-related code
reveal 'ast://./src?name=*auth*'

# Find all test setup functions
reveal 'ast://./tests?name=setup_*'

# Find all getter methods
reveal 'ast://./src?name=get_*'
```

**Use regex for precision:**

```bash
# Only functions starting with test_ (not contains)
reveal 'ast://./tests?name~=^test_'

# Only Manager classes (not ManagerFactory)
reveal 'ast://./src?name~=.*Manager$&type=class'
```

### Filter Combination Strategies

**AND logic** (all conditions must match):

```bash
# Complex AND long
reveal 'ast://./src?complexity>10&lines>100'

# Properties that are too complex
reveal 'ast://.?decorator=property&lines>10'
```

**OR logic** (only for type parameter):

```bash
# Classes OR functions (not methods)
reveal 'ast://./src?type=class|function'
```

**Negation** (exclude matching):

```bash
# Everything except functions
reveal 'ast://./src?type!=function'

# All non-property decorators
reveal 'ast://.?decorator!=property'
```

### Quote Consistently

**Always quote URIs** to prevent shell interpretation:

```bash
# ✅ GOOD: Quoted
reveal 'ast://./src?complexity>10'

# ❌ BAD: Unquoted (shell redirects > to file)
reveal ast://./src?complexity>10

# ✅ GOOD: Quoted with wildcards
reveal 'ast://./src?name=test_*'

# ❌ BAD: Unquoted (shell expands * to files)
reveal ast://./src?name=test_*
```

### Use JSON for Scripting

When piping to other tools, use JSON output:

```bash
# Count functions per file
reveal 'ast://./src?type=function' --format=json | \
  jq -r '.results[].file' | sort | uniq -c | sort -rn

# Find top 10 most complex functions
reveal 'ast://./src' --format=json | \
  jq -r '[.results[] | {name: .symbol, file, complexity, lines}] |
         sort_by(.complexity) | reverse | .[0:10][]'

# Generate CSV report
reveal 'ast://./src' --format=json | \
  jq -r '.results[] | [.file, .symbol, .complexity, .lines] | @csv' \
  > code_metrics.csv
```

### Complexity Thresholds

Use industry-standard thresholds:

```bash
# Low complexity (1-5): good examples
reveal 'ast://./src?complexity<=5'

# Moderate (6-10): acceptable
reveal 'ast://./src?complexity>5&complexity<=10'

# Needs attention (11-20): refactor soon
reveal 'ast://./src?complexity>10&complexity<=20'

# High risk (21+): refactor now
reveal 'ast://./src?complexity>20'
```

### Don't Query What You Don't Need

**Bad: Query everything, filter later**
```bash
# ❌ Slow: scans all files, returns everything
reveal 'ast://.' --format=json | jq '.results[] | select(.complexity > 10)'
```

**Good: Filter at query time**
```bash
# ✅ Fast: only returns complex functions
reveal 'ast://.?complexity>10' --format=json
```

---

## Integration with Other Tools

### With jq (JSON processing)

```bash
# Top 10 most complex functions
reveal 'ast://./src' --format=json | \
  jq '[.results[] | {name: .symbol, complexity}] |
      sort_by(.complexity) | reverse | .[0:10]'

# Functions by file with complexity
reveal 'ast://./src?complexity>10' --format=json | \
  jq -r 'group_by(.file) |
         .[] | "\(.[0].file): \(length) complex functions"'

# Generate HTML report
reveal 'ast://./src' --format=json | \
  jq -r '.results[] |
         "<tr><td>\(.symbol)</td><td>\(.complexity)</td></tr>"' \
  > report.html
```

### With CI/CD Pipelines

**GitHub Actions example:**

```yaml
- name: Check code complexity
  run: |
    # Fail if any function has complexity >20
    if reveal 'ast://./src?complexity>20' --format=json | \
       jq -e '.total_results > 0' > /dev/null; then
      echo "::error::Found functions with complexity >20"
      exit 1
    fi
```

**GitLab CI example:**

```yaml
code_quality:
  script:
    - reveal 'ast://./src?complexity>15' --format=json > complexity.json
    - |
      if [ $(jq '.total_results' complexity.json) -gt 0 ]; then
        echo "Warning: Found complex functions"
        jq '.results[]' complexity.json
      fi
```

### With pre-commit hooks

**`.pre-commit-config.yaml`:**

```yaml
- repo: local
  hooks:
    - id: complexity-check
      name: Check code complexity
      entry: bash -c 'reveal "ast://." --format=json |
                      jq -e ".total_results == 0 or
                             all(.results[]; .complexity <= 15)"'
      language: system
      types: [python]
```

### With Python scripts

```python
import subprocess
import json

# Run ast query
result = subprocess.run(
    ["reveal", "ast://./src?complexity>10", "--format=json"],
    capture_output=True,
    text=True
)

# Parse JSON output
data = json.loads(result.stdout)

# Process results
for item in data["results"]:
    print(f"{item['file']}:{item['line']} - "
          f"{item['symbol']} (complexity: {item['complexity']})")
```

### With pandas (data analysis)

```python
import subprocess
import json
import pandas as pd

# Get all code structure
result = subprocess.run(
    ["reveal", "ast://./src", "--format=json"],
    capture_output=True,
    text=True
)

data = json.loads(result.stdout)
df = pd.DataFrame(data["results"])

# Analyze
print(df.describe())
print(df.groupby("type")["complexity"].mean())
print(df.nlargest(10, "complexity"))
```

### With SQLite (code database)

```bash
# Export to CSV
reveal 'ast://./src' --format=json | \
  jq -r '.results[] | [.file, .symbol, .type, .line, .lines, .complexity] | @csv' \
  > code_structure.csv

# Import to SQLite
sqlite3 code.db <<EOF
CREATE TABLE code (
  file TEXT,
  symbol TEXT,
  type TEXT,
  line INTEGER,
  lines INTEGER,
  complexity INTEGER
);
.mode csv
.import code_structure.csv code
EOF

# Query with SQL
sqlite3 code.db "SELECT file, symbol, complexity
                 FROM code
                 WHERE complexity > 10
                 ORDER BY complexity DESC
                 LIMIT 10"
```

---

## Related Documentation

**Core reveal documentation:**
- [QUICK_START.md](QUICK_START.md) - Getting started with reveal
- [QUERY_SYNTAX_GUIDE.md](QUERY_SYNTAX_GUIDE.md) - Query parameter reference
- [AGENT_HELP.md](AGENT_HELP.md) - Complete agent help

**Related adapters:**
- [PYTHON_ADAPTER_GUIDE.md](PYTHON_ADAPTER_GUIDE.md) - Python runtime inspection
- [imports:// adapter](IMPORTS_ADAPTER_GUIDE.md) - Dependency analysis
- [stats:// adapter](STATS_ADAPTER_GUIDE.md) - Codebase statistics

**Workflow guides:**
- [RECIPES.md](RECIPES.md) - Reveal recipes and patterns
- [CODEBASE_REVIEW.md](CODEBASE_REVIEW.md) - Code review workflows

**Language support:**
- Run `reveal --languages` for complete list of supported languages

---

## Version History

### v1.0 (reveal 0.49.0+)

**Features:**
- ✅ Query by complexity, lines, type, name, decorators
- ✅ Wildcard and regex pattern matching
- ✅ Result control (sort, limit, offset)
- ✅ Multiple output formats (text, JSON, grep)
- ✅ 50+ language support via tree-sitter
- ✅ Combined filters with AND logic
- ✅ OR logic for type parameter

**Operators added:**
- `!=` - Not equal to (negation)
- `~=` - Regex pattern matching
- `..` - Range operator

**Known limitations:**
- Complexity calculation is heuristic-based (tree-sitter implementation planned)
- Decorator filtering is Python-specific
- No cross-file analysis (use imports:// adapter)

---

## FAQ

**Q: What's the difference between `name=test_*` and `name~=^test_`?**

A: `name=test_*` uses glob-style wildcards (simpler), `name~=^test_` uses regex (more powerful). For most cases, glob is sufficient and clearer.

**Q: Why are my results slow?**

A: AST queries parse all source files. Narrow your path (`ast://./src` instead of `ast://.`) or use result control (`limit=20`).

**Q: Can I query across multiple languages?**

A: Yes! reveal supports 50+ languages. However, some features (decorator filtering) may be language-specific.

**Q: How accurate is complexity measurement?**

A: Currently heuristic-based. Tree-sitter-based McCabe calculation is planned for improved accuracy.

**Q: Can I find all callers of a function?**

A: No, AST adapter only analyzes code structure, not relationships. Use `imports://` for dependency analysis or IDE tools for call graphs.

**Q: How do I exclude test files?**

A: Query a specific directory: `ast://./src` (not `ast://.`), or filter results with `jq`.

**Q: Can I save queries as shortcuts?**

A: Yes! Create shell aliases:
```bash
alias reveal-complex="reveal 'ast://./src?complexity>10&sort=-complexity&limit=20'"
```

---

**End of AST Adapter Guide**

*This guide covers reveal v0.49.2+. For updates, see CHANGELOG.md.*
