---
title: Field Selection & Budget Constraints Guide
category: guide
help_topic: fields
help_description: "Field selection and token-budget constraints"
help_category: feature_guides
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

Field selection applies to a URI adapter's JSON result (`--format json`). In text output
the flag is not applied and a note says so: text renderers need the whole result.

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

### What a field name selects

One rule, the same for every adapter. Each name is looked up at the top level of the
result first, then in the items of the result's lists:

| Name | Selects |
|------|---------|
| `total_results` | that top-level key |
| `summary.total_files` | a nested key (dot notation) |
| `results` | that whole list |
| `results.name` | `name` in each item of `results` |
| `name` (not a top-level key) | `name` in the items of every list whose items have it |

- The Output Contract envelope (`contract_version`, `type`, `source`, `source_type`,
  `meta`) is always kept, so truncation warnings and the result type survive a selection.
- Top-level keys you didn't name are dropped. A list is kept when you name it, or when a
  name selects keys in its items.
- A name that matches nothing is reported: a `fields_unmatched` entry in `meta.warnings`
  and a note on stderr that lists the fields the result does have.
- A failed result (one with a top-level `error`) is left whole.
- `--fields` works on URI adapters. On a plain file (`reveal file.py`) it is not applied,
  and a note says so; use `ast://file.py` instead.

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

A cut list is disclosed the same way for every adapter and every cause (`--max-items`,
`--head`/`--tail`/`--range`, `?limit=`/`?offset=`, an adapter's own `?top=`, an adapter's
default cap): one `meta.warnings` entry per cut list. Text output prints the same message
after the results, as `⚠ Truncated results: showing 50 of 150 — raise --max-items`. One
cut doesn't record it yet: `--head`/`--tail` on a file path (`reveal f.py --head 2`).

```json
{
  "meta": {
    "warnings": [{
      "type": "truncated",
      "field": "results",
      "shown": 50,
      "total": 150,
      "exact": true,
      "cause": "max_items",
      "message": "results: showing 50 of 150 — raise --max-items"
    }]
  }
}
```

`cause` is `limit`, `auto_cap`, `max_items`, `head`, `tail` or `range`. `exact` is false
when the total is only a lower bound: git history is walked newest first and stops one
commit past the page, so it knows more exist but not how many (`total` is then the page plus
one, and the message says `showing 50 of 51+`). When
`--max-items` cut the list, the output also includes its budget block:

```json
{
  "meta": {
    "budget": {
      "truncated": true,
      "reason": "max_items_exceeded",
      "total_available": 150,
      "returned": 50,
      "next_cursor": "offset=50"
    }
  }
}
```

### Metadata Fields

Nested under `meta.budget`:

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
  "contract_version": "1.1",
  "type": "ssl_certificate",
  "source": "ssl://example.com",
  "source_type": "network",
  "host": "example.com",
  "days_until_expiry": 84,
  "health_status": "HEALTHY",
  "common_name": "example.com"
}
```

**Nested field selection**:
```bash
reveal ssl://example.com --fields=host,verification.chain_valid,verification.hostname_match --format=json
```

Output (envelope omitted):
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

**Field selection + budget** (the total, plus three keys of each function):
```bash
reveal 'ast://src?type=function' --fields=total_results,results.name,results.line,results.complexity --max-items=5 --format=json
```

Output (`source`, `source_type` and `meta.budget` omitted):
```json
{
  "contract_version": "1.1",
  "type": "ast_query",
  "meta": {
    "warnings": [
      {"type": "truncated", "field": "results", "shown": 5, "total": 150, "exact": true,
       "cause": "max_items", "message": "results: showing 5 of 150 — raise --max-items"}
    ]
  },
  "total_results": 150,
  "results": [
    {"name": "parse_query", "line": 42, "complexity": 8},
    {"name": "apply_filter", "line": 89, "complexity": 5},
    {"name": "coerce_value", "line": 12, "complexity": 3},
    {"name": "format_output", "line": 156, "complexity": 11},
    {"name": "validate_args", "line": 201, "complexity": 7}
  ]
}
```

`--fields=name,line,complexity` alone returns the same `results` without `total_results`:
those names aren't top-level keys, so they select in the items.

---

### Stats Adapter

**Full output** (~500 lines):
```bash
reveal stats://src --format=json
```

**Selected fields** (each file's name, code lines and quality score):
```bash
reveal stats://src --fields=file,lines.code,quality.score --format=json
```

**Most complex files** (budget mode):
```bash
reveal 'stats://src?sort=-complexity' --max-items=10 --fields=file,complexity --format=json
```

---

### Git Adapter

**Recent commits** (`?limit=` sets how many):
```bash
reveal 'git://.?type=log&limit=20' --format=json
```

**Field selection for the commit list** (the log's `history` items):
```bash
reveal 'git://.?type=log&limit=50' --fields=hash,author,date,message --format=json
```

**One file's history** (its `commits` items):
```bash
reveal 'git://src/app.py?type=history' --fields=hash,date,message --format=json
```

---

### JSON Adapter

**Large dataset filtering**:
```bash
reveal 'json://data.json?status=active' --max-items=100 --format=json
```

**Field projection + filtering** (keys of each object in the array):
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
if data['meta']['budget']['truncated']:
    next_offset = data['meta']['budget']['returned']
    # Make follow-up query with offset
```

---

### 2. Quick Status Checks

**Problem**: Need minimal info for monitoring/dashboards.

**Solution**: Select only status fields:

```bash
# SSL certificate monitoring
reveal ssl://example.com --fields=host,days_until_expiry,health_status --format=json
```

---

### 3. Large Result Set Pagination

**Problem**: Query returns hundreds of results, too large for single response.

**Solution**: Use `--max-items` with offset pagination:

```bash
# First page
reveal 'ast://src?type=function' --max-items=50 --format=json > page1.json

# Check truncation
if data['meta']['budget']['truncated']:
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

A name that isn't there gets a note listing the fields that are, so a wrong guess
tells you what to ask for:

```
Note: --fields: expiry matched no field of this ssl:// result. Fields: common_name, issuer, ...
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

Field selection applies to the JSON result. In text output it is not applied, and a note
says so:

```bash
# ✅ Selects the fields
reveal ssl://example.com --fields=host,days_until_expiry --format=json

# ❌ Prints the whole text view, plus "Note: --fields selects fields of the JSON result"
reveal ssl://example.com --fields=host,days_until_expiry
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
reveal 'stats://src?lines>100&sort=-complexity' --max-items=20 --fields=file,complexity,lines --format=json
```

---

### 4. **Check truncation metadata in AI loops**

Always check `meta.budget.truncated` to know if you got partial results:

```python
import json
import subprocess

result = subprocess.run(
    ['reveal', 'ast://src?type=function', '--max-items=50', '--format=json'],
    capture_output=True, text=True
)

data = json.loads(result.stdout)

if data.get('meta', {}).get('budget', {}).get('truncated'):
    print(f"Got {data['meta']['budget']['returned']} of {data['meta']['budget']['total_available']} results")
    print(f"Next: offset={data['meta']['budget']['returned']}")
else:
    print("Got all results")
```

---

### 5. **Use nested field selection for deep structures**

Access nested fields with dot notation:

```bash
# Access nested certificate data
reveal ssl://example.com --fields=host,verification.chain_valid,verification.hostname_match --format=json

# Access nested keys of each list item
reveal stats://src --fields=file,quality.score,complexity.max --format=json
```

---

## Advanced Patterns

### Pattern 1: Progressive Detail Loading

**Scenario**: AI agent explores codebase progressively, starting with minimal info, then drilling down.

```bash
# Level 1: Overview (minimal fields)
reveal 'stats://src' --fields=file,quality.score --max-items=100 --format=json

# Level 2: Identify hotspots
reveal 'stats://src?hotspots=true' --fields=summary,hotspots --format=json

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
    truncated=$(echo "$result" | jq -r '.meta.budget.truncated // false')
    returned=$(echo "$result" | jq -r '.meta.budget.returned // 0')

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
- `total_files`, `total_results`, `displayed_results`, `query`
- `results` (list)
- the envelope (`type`, `source`, `source_type`, `meta`) is always kept

Common fields (result items):
- `file`, `category`, `name`, `line`, `line_count`
- `signature`, `complexity`, `depth`
- `decorators`, `bases`, `calls`, `called_by`

#### Stats Adapter

Top-level (directory): `summary` (`summary.total_files`, `summary.avg_quality_score`, ...),
`files` (list), and `hotspots` with `?hotspots=true`.

Items of `files`:
- `file`
- `lines.total`, `lines.code`, `lines.empty`, `lines.comments`
- `elements.functions`, `elements.classes`, `elements.imports`
- `complexity.average`, `complexity.max`, `complexity.min`
- `quality.score`, `quality.long_functions`, `quality.deep_nesting`
- `issues`

#### Git Adapter

Items of `history` (`git://.?type=log`) and `commits` (`git://file?type=history`):
- `hash`, `author`, `email`, `date`, `timestamp`, `message`

The log view's top-level `commit` holds the ref's own commit, with `full_hash`,
`full_message`, `parents` and `committer` as well.

#### JSON Adapter

Fields depend on your data structure. For an array of objects, a name selects that key
of each object (the result's `value` list). Use `jq 'keys'` to explore.

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
reveal 'stats://src?lines>100&sort=-complexity'
```

### Phase 4: Field Selection + Budget

**Purpose**: Reduce output size and enforce token budgets

**Flags**: `--fields`, `--max-items`, `--max-snippet-chars`

**Example**:
```bash
reveal 'stats://src?lines>100&sort=-complexity' --max-items=20 --fields=file,quality.score --format=json
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

**What you see**: a note on stderr naming the field and listing the fields the result
has (top level, and the keys of each list's items), and a `fields_unmatched` entry in
`meta.warnings`. Pick a name from that list:

```bash
reveal <uri> --fields=<existing-field> --format=json
```

---

### Budget constraints not working

**Problem**: `--max-items` doesn't limit output

**Cause**: Adapter returns single object, not a list

**Solution**: Budget constraints work on the lists an adapter declares (ast:// `results`,
stats:// `files`, git:// `commits`, ...); when there is nothing to cut, a note says the
flag had no effect. For single objects, use `--fields` instead.

---

### Truncation metadata missing

**Problem**: Expected `meta.budget.truncated` but not present

**Cause**: Results fit within budget (no truncation occurred), or something other than
`--max-items` cut the list (`?limit=`, `--head`, an adapter's default cap).

**Solution**: Check `meta.warnings` for an entry with `"type": "truncated"`. It is present
for every cut, whatever caused it; `meta.budget` is present only for `--max-items`.

---

## See Also

- [Query Syntax Guide](QUERY_SYNTAX_GUIDE.md) - Phase 3 query operators
- [Output Contract](../development/OUTPUT_CONTRACT.md) - JSON output specification
- [Adapter Consistency](../development/ADAPTER_CONSISTENCY.md) - Universal adapter behavior
- [Agent Help](../AGENT_HELP.md) - AI agent integration guide

---
