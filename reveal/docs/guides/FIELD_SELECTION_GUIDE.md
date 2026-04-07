---
title: Field Selection & Budget Constraints Guide
category: guide
---
# Field Selection & Budget Constraints Guide

**Phase 4 Feature**: Token reduction through field selection and explicit budget constraints.

**Status**: ✅ Complete (v0.47.2+)

---

## Quick Start

```bash
# Select specific fields only (5-10x token reduction)
reveal ssl://example.com --fields=host,days_until_expiry,health_status --format=json

# Stop after N results (budget mode)
reveal 'ast://src?type=function' --max-items=10 --format=json

# Truncate long string values
reveal 'json://logs.json?level=error' --max-snippet-chars=200 --format=json

# Combine field selection + budget
reveal 'ast://src?type=function' --fields=name,line,complexity --max-items=20 --format=json
```

---

## Table of Contents

1. [Field Selection](#field-selection)
2. [Budget Constraints](#budget-constraints)
3. [Adapter Examples](#adapter-examples)
4. [Common Patterns](#common-patterns)
5. [Best Practices](#best-practices)
6. [Advanced Patterns](#advanced-patterns)

---

## Field Selection

### Overview

The `--fields` flag allows you to select specific fields from adapter output, dramatically reducing token usage. This is especially valuable for AI agents operating in loops where full structure is unnecessary.

### Syntax

```bash
reveal <uri> --fields=field1,field2,field3 --format=json
```

### Features

- **Flat fields**: `--fields=name,type,status`
- **Nested fields**: `--fields=certificate.expiry,meta.confidence`
- **Comma-separated**: Multiple fields in single flag
- **JSON output**: Works with `--format=json` (field selection on text output has limited benefit)

### Token Reduction

| Adapter | Full Output | Selected Fields | Reduction |
|---------|-------------|-----------------|-----------|
| SSL | ~400 lines | ~10 lines | 40x |
| AST | ~500 lines | ~50 lines | 10x |
| Stats | ~500 lines | ~50 lines | 10x |
| Git | ~200 lines | ~30 lines | 7x |
| JSON | Variable | Variable | 5-10x |

---

## Budget Constraints

### Overview

Budget-aware flags enable explicit token budget control for AI agent loops. When a budget is exceeded, output is truncated and metadata indicates truncation.

### Flags

| Flag | Description | Use Case |
|------|-------------|----------|
| `--max-items=N` | Stop after N results | List result limiting |
| `--max-snippet-chars=N` | Truncate long string values | Log lines, large content fields |

### Truncation Metadata

When budget is exceeded, output includes metadata:

```json
{
  "meta": {
    "truncated": true,
    "reason": "max_items_exceeded",
    "total_available": 150,
    "returned": 50,
    "next_cursor": "offset=50"
  }
}
```

### Metadata Fields

- `truncated`: Boolean indicating truncation
- `reason`: Why truncation occurred (`max_items_exceeded`)
- `total_available`: Total results available
- `returned`: Number of results returned
- `next_cursor`: Pagination hint for next request

---

## Adapter Examples

### SSL Adapter

**Full output** (~400 lines):
```bash
reveal ssl://example.com --format=json
```

**Selected fields** (~10 lines, 40x reduction):
```bash
reveal ssl://example.com --fields=host,days_until_expiry,health_status,common_name --format=json
```

Output:
```json
{
  "host": "example.com",
  "days_until_expiry": 35,
  "health_status": "HEALTHY",
  "common_name": "example.com"
}
```

**Nested field selection**:
```bash
reveal ssl://example.com --fields=host,verification.chain_valid,verification.hostname_match --format=json
```

Output:
```json
{
  "host": "example.com",
  "verification": {
    "chain_valid": true,
    "hostname_match": true
  }
}
```

---

### AST Adapter

**Budget-limited query** (stop after 10 results):
```bash
reveal 'ast://src?type=function' --max-items=10 --format=json
```

**Field selection + budget**:
```bash
reveal 'ast://src?type=function' --fields=type,total_results,results --max-items=5 --format=json
```

Output:
```json
{
  "type": "ast_query",
  "total_results": 150,
  "results": [
    {"name": "parse_query", "line": 42, "complexity": 8},
    {"name": "apply_filter", "line": 89, "complexity": 5},
    {"name": "coerce_value", "line": 12, "complexity": 3},
    {"name": "format_output", "line": 156, "complexity": 11},
    {"name": "validate_args", "line": 201, "complexity": 7}
  ],
  "meta": {
    "truncated": true,
    "reason": "max_items_exceeded",
    "total_available": 150,
    "returned": 5,
    "next_cursor": "offset=5"
  }
}
```

---

### Stats Adapter

**Full output** (~500 lines):
```bash
reveal stats://src --format=json
```

**Selected fields** (~50 lines, 10x reduction):
```bash
reveal stats://src --fields=path,quality_score,hotspot_score,lines --format=json
```

**Top-N hotspots** (budget mode):
```bash
reveal 'stats://src?sort=-hotspot_score' --max-items=10 --format=json
```

---

### Git Adapter

**Recent commits** (budget limited):
```bash
reveal 'git://repo?sort=-date' --max-items=20 --format=json
```

**Field selection for commit list**:
```bash
reveal 'git://repo?sort=-date' --fields=hash,author,date,message --max-items=50 --format=json
```

---

### JSON Adapter

**Large dataset filtering**:
```bash
reveal 'json://data.json?status=active' --max-items=100 --format=json
```

**Field projection + filtering**:
```bash
reveal 'json://users.json?role=admin' --fields=id,name,email --format=json
```

---

## Common Patterns

### 1. AI Agent Budget Loops

**Problem**: AI agent needs to query repeatedly without hitting token limits.

**Solution**: Use `--max-items` with `--fields` to control output size:

```bash
# Limit to 20 results with only needed fields
reveal 'ast://src?type=function&lines>50' --max-items=20 --fields=name,line,complexity --format=json

# Check truncation in response
if data['meta']['truncated']:
    next_offset = data['meta']['returned']
    # Make follow-up query with offset
```

---

### 2. Quick Status Checks

**Problem**: Need minimal info for monitoring/dashboards.

**Solution**: Select only status fields:

```bash
# SSL certificate monitoring
reveal ssl://example.com --fields=host,days_until_expiry,health_status --format=json

# Database health check
reveal 'mysql://localhost/mydb' --fields=status,replication_lag,connections --format=json
```

---

### 3. Large Result Set Pagination

**Problem**: Query returns hundreds of results, too large for single response.

**Solution**: Use `--max-items` with offset pagination:

```bash
# First page
reveal 'ast://src?type=function' --max-items=50 --format=json > page1.json

# Check truncation
if data['meta']['truncated']:
    # Second page
    reveal 'ast://src?type=function&offset=50' --max-items=50 --format=json > page2.json
```

---

### 4. Exploring Unknown Structure

**Problem**: New adapter or data source, want to see structure before committing to fields.

**Solution**: Start with full output, then refine:

```bash
# Step 1: See full structure
reveal ssl://example.com --format=json | jq 'keys'
# Output: ["common_name", "days_until_expiry", "health_status", "host", ...]

# Step 2: Select interesting fields
reveal ssl://example.com --fields=host,days_until_expiry --format=json
```

---

### 5. String Truncation for Large Content

**Problem**: Some fields contain very long strings (logs, content, descriptions).

**Solution**: Use `--max-snippet-chars` to truncate:

```bash
# Truncate long string values to 200 chars
reveal 'json://logs.json?level=error' --max-snippet-chars=200 --format=json
```

---

## Best Practices

### 1. **Always use --format=json with field selection**

Field selection is designed for JSON output. Text rendering may not benefit as much:

```bash
# ✅ Good: JSON output with field selection
reveal ssl://example.com --fields=host,days_until_expiry --format=json

# ❌ Limited benefit: text output with field selection
reveal ssl://example.com --fields=host,days_until_expiry --format=text
```

---

### 2. **Combine --max-items with --fields for tight token budgets**

Both flags together give precise control:

```bash
# Limit results AND select only needed fields
reveal 'ast://src?type=function' --max-items=10 --fields=name,line,complexity --format=json
```

---

### 3. **Combine with query operators for precision**

Phase 3 query operators + Phase 4 field selection = powerful combination:

```bash
# Filter, sort, limit, then select fields
reveal 'stats://src?lines>100&sort=-complexity' --max-items=20 --fields=path,complexity,lines --format=json
```

---

### 4. **Check truncation metadata in AI loops**

Always check `meta.truncated` to know if you got partial results:

```python
import json
import subprocess

result = subprocess.run(
    ['reveal', 'ast://src?type=function', '--max-items=50', '--format=json'],
    capture_output=True, text=True
)

data = json.loads(result.stdout)

if data.get('meta', {}).get('truncated'):
    print(f"Got {data['meta']['returned']} of {data['meta']['total_available']} results")
    print(f"Next: offset={data['meta']['returned']}")
else:
    print("Got all results")
```

---

### 5. **Use nested field selection for deep structures**

Access nested fields with dot notation:

```bash
# Access nested certificate data
reveal ssl://example.com --fields=host,verification.chain_valid,verification.hostname_match --format=json

# Access nested meta information
reveal 'ast://src?type=function' --fields=type,results,meta.confidence --format=json
```

---

## Advanced Patterns

### Pattern 1: Progressive Detail Loading

**Scenario**: AI agent explores codebase progressively, starting with minimal info, then drilling down.

```bash
# Level 1: Overview (minimal fields)
reveal 'stats://src' --fields=path,quality_score --max-items=100 --format=json

# Level 2: Identify hotspots
reveal 'stats://src?quality_score<60&sort=-hotspot_score' --max-items=20 --format=json

# Level 3: Deep dive on specific file
reveal 'ast://src/problematic_file.py' --format=json
```

---

### Pattern 2: Multi-Source Aggregation

**Scenario**: Collect minimal data from multiple sources, aggregate centrally.

```bash
# Collect SSL status from multiple domains
cat domains.txt | while read domain; do
    reveal "ssl://$domain" --fields=host,days_until_expiry,health_status --format=json
done | jq -s '.'
```

---

### Pattern 3: Budget-Aware Search

**Scenario**: Search large codebase, limiting results per file.

```bash
# Search for functions matching pattern, limit per file
for file in $(find src -name "*.py"); do
    reveal "ast://$file?type=function&name~=.*handler.*" \
        --max-items=20 \
        --fields=name,line,complexity \
        --format=json
done
```

---

### Pattern 4: Incremental Result Fetching

**Scenario**: Fetch large result set incrementally with pagination.

```bash
#!/bin/bash
offset=0
page_size=50
total=0

while true; do
    result=$(reveal "ast://src?type=function&offset=$offset" \
        --max-items=$page_size \
        --fields=name,line \
        --format=json)

    # Check if truncated
    truncated=$(echo "$result" | jq -r '.meta.truncated // false')
    returned=$(echo "$result" | jq -r '.meta.returned // 0')

    total=$((total + returned))
    echo "Fetched $returned results (total: $total)"

    # Stop if not truncated
    if [ "$truncated" != "true" ]; then
        break
    fi

    offset=$((offset + page_size))
done
```

---

## Field Selection by Adapter

### Available Fields Reference

#### SSL Adapter

Common fields:
- `host`, `port`
- `common_name`, `issuer`
- `days_until_expiry`, `health_status`, `health_icon`
- `valid_from`, `valid_until`
- `san_count`
- `verification.chain_valid`, `verification.hostname_match`

#### AST Adapter

Common fields (top-level):
- `type`, `source`, `source_type`
- `total_files`, `total_results`, `displayed_results`
- `results` (list)
- `meta.parse_mode`, `meta.confidence`

Common fields (result items):
- `file`, `category`, `name`, `line`, `line_count`
- `signature`, `complexity`, `depth`
- `decorators`, `class_name`

#### Stats Adapter

Common fields:
- `path`, `lines`, `code_lines`, `comment_lines`
- `quality_score`, `hotspot_score`
- `functions`, `classes`, `complexity`
- `todo_count`, `fixme_count`

#### Git Adapter

Common fields (commits):
- `hash`, `short_hash`
- `author`, `author_email`, `date`
- `message`, `subject`, `body`
- `files_changed`, `insertions`, `deletions`

#### JSON Adapter

Fields depend on your data structure. Use `jq 'keys'` to explore.

---

## Token Budget Guidelines

### Budget Recommendations by Use Case

**Monitoring/Status Checks** (minimal output):
- Use `--fields` to select only status fields
- Use `--max-items=1` for single-object checks

**Interactive Exploration** (moderate output):
- Allow medium result sets with `--max-items=50-100`
- Add `--fields` to drop verbose columns

**Batch Processing** (larger chunks):
- Use `--max-items=200-500` per iteration
- Use `--max-snippet-chars=500` if fields contain long text

**One-Time Analysis** (no limit):
- Omit budget flags — get full results

---

## Comparison with Phase 3

### Phase 3: Query Operators

**Purpose**: Filter and sort results at data layer

**Operators**: `=`, `!=`, `>`, `<`, `>=`, `<=`, `~=`, `..`

**Example**:
```bash
reveal 'stats://src?quality_score<60&sort=-hotspot_score&limit=20'
```

### Phase 4: Field Selection + Budget

**Purpose**: Reduce output size and enforce token budgets

**Flags**: `--fields`, `--max-items`, `--max-snippet-chars`

**Example**:
```bash
reveal 'stats://src?quality_score<60&sort=-hotspot_score' --max-items=20 --fields=path,quality_score --format=json
```

### Combining Both

```bash
# Phase 3: Filter and sort
# Phase 4: Limit results and select fields
reveal 'ast://src?type=function&complexity>10&sort=-complexity' \
    --max-items=10 \
    --fields=name,line,complexity \
    --format=json
```

**Result**: Precise, budget-aware queries with minimal token usage.

---

## Troubleshooting

### Field not found

**Problem**: Selected field doesn't exist in output

**Solution**: Check available fields first:

```bash
# See all fields
reveal <uri> --format=json | jq 'keys'

# Then select existing fields
reveal <uri> --fields=<existing-field> --format=json
```

---

### Budget constraints not working

**Problem**: `--max-items` doesn't limit output

**Cause**: Adapter returns single object, not a list

**Solution**: Budget constraints work on list results (`items`, `results`, `checks`, `commits`, `files`). For single objects, use `--fields` instead.

---

### Truncation metadata missing

**Problem**: Expected `meta.truncated` but not present

**Cause**: Results fit within budget (no truncation occurred)

**Solution**: This is expected. Only truncated results include budget metadata.

---

## See Also

- [Query Syntax Guide](QUERY_SYNTAX_GUIDE.md) - Phase 3 query operators
- [Output Contract](../development/OUTPUT_CONTRACT.md) - JSON output specification
- [Adapter Consistency](../development/ADAPTER_CONSISTENCY.md) - Universal adapter behavior
- [Agent Help](../AGENT_HELP.md) - AI agent integration guide

---
