# Extraction System Improvements

**Date**: 2026-01-19
**Session**: immortal-shrine-0119
**Status**: ✅ COMPLETE - All features implemented in v0.39.0 (2026-01-19)
**Implementation Sessions**: yevaxi-0119 (@N syntax), glowing-gleam-0119 (:LINE syntax + mappings), kabawose-0119

---

## Executive Summary

Reveal's extraction system has UX inconsistencies between what's shown in output and what can be extracted. This document captures findings from code analysis and VEINBORN dogfooding feedback.

**Key insight**: If we show `:73` in output, users should be able to extract by `:73`.

---

## Current Extraction Capabilities

### What Works

| Syntax | Example | Result |
|--------|---------|--------|
| By name | `reveal file.py get_structure` | Extracts function |
| By line range | `reveal file.py --range 73-91` | Extracts lines |
| Markdown section name | `reveal doc.md "Installation"` | Extracts section |
| Markdown section ordinal | `reveal doc.md --section 3` | 3rd heading |
| JSONL record number | `reveal log.jsonl 42` | Record #42 |
| Hierarchical | `reveal file.py MyClass.method` | Method within class |

### What Doesn't Work (But Should)

| Syntax | Expected | Actual |
|--------|----------|--------|
| `reveal file.py :73` | Element at line 73 | "Element ':73' not found" |
| `reveal file.py @3` | 3rd function | Falls to grep, random match |
| `reveal file.py #3` | 3rd function | "Element '#3' not found" |
| `reveal file.py function:3` | 3rd function explicitly | Not implemented |

---

## The Line Number Inconsistency

### Output Shows Line Numbers

```
Functions (11):
  :73     get_structure(...) [18 lines, depth:0]
  :33     __init__(...) [4 lines, depth:0]
  :38     _read_file(...) [18 lines, depth:4]
```

### But You Can't Use Them

```bash
reveal file.py :73           # FAILS
reveal file.py --range 73-91 # WORKS (but must know end line)
reveal file.py get_structure # WORKS (but requires remembering name)
```

### Proposal: `:LINE` Extraction

```bash
reveal file.py :73           # Extract element containing/starting at line 73
reveal file.py :73-91        # Explicit range (shorthand for --range)
```

**Implementation**: In `extract_element()`, detect `:N` pattern and find element whose `line_start <= N <= line_end`.

---

## The Ordinal Inconsistency

### Different Behaviors by File Type

| Type | Ordinal Works? | How |
|------|----------------|-----|
| JSONL | Yes | `reveal file.jsonl 2` = record #2 |
| Markdown | Yes | `reveal doc.md --section 3` = 3rd heading |
| Code | No | `reveal file.py 3` falls to grep |

### Proposal: `@N` Ordinal Extraction

```bash
reveal file.py @1            # 1st function (dominant category)
reveal file.py @3            # 3rd function
reveal file.py function:3    # Explicit: 3rd function
reveal file.py class:1       # 1st class
```

**Design decision**: What does bare `@3` mean?
- Option A: 3rd element of dominant category (functions for code, headings for md)
- Option B: 3rd element overall (mixed types)
- **Recommendation**: Option A (matches user mental model)

---

## Unmapped Structure Categories

### Problem: `meta.extractable` Misses Many Types

The `category_to_type` mapping in `structure.py` only covers:

```python
category_to_type = {
    'functions': 'function',
    'classes': 'class',
    'structs': 'struct',
    'headings': 'section',
    'sections': 'section',
    'servers': 'server',
    'locations': 'location',
    'upstreams': 'upstream',
    'keys': 'key',
    'tables': 'section',
}
```

### Missing High-Value Mappings

Many analyzers return categories not in this mapping:

| Analyzer | Categories Returned | Not Mapped |
|----------|---------------------|------------|
| GraphQL | queries, mutations, types, interfaces, enums | All unmapped |
| HCL/Terraform | resources, variables, outputs, modules | All unmapped |
| Protobuf | messages, services, rpcs, enums | All unmapped |
| Zig | functions, tests, enums, unions | tests, enums, unions |
| TreeSitter base | imports, functions, classes, structs | imports |
| Jupyter | cells, kernel | cells |
| Markdown (--code) | code_blocks | code_blocks |

### Proposal: Expand Mappings

```python
# Add to category_to_type:
'queries': 'query',        # GraphQL
'mutations': 'mutation',   # GraphQL
'types': 'type',           # GraphQL, TypeScript
'interfaces': 'interface', # GraphQL, Java, TS, Go
'enums': 'enum',           # GraphQL, Protobuf, Zig, Rust
'messages': 'message',     # Protobuf
'services': 'service',     # Protobuf, gRPC
'rpcs': 'rpc',             # Protobuf
'resources': 'resource',   # Terraform/HCL
'variables': 'variable',   # HCL
'outputs': 'output',       # HCL
'modules': 'module',       # HCL, Ruby, Python
'imports': 'import',       # All tree-sitter languages
'tests': 'test',           # Zig, pytest markers
'unions': 'union',         # Zig, Rust
'cells': 'cell',           # Jupyter notebooks
'records': 'record',       # JSONL
```

---

## `--capabilities` vs Actual Discrepancy

### Problem

`_get_extractable_types()` in `introspection.py` is hardcoded by extension and doesn't match actual analyzer output.

| Extension | Claims | Actual Structure |
|-----------|--------|------------------|
| .py | function, class, method | functions, classes (no separate methods) |
| .md | section, heading, code_block | headings only (code_blocks require --code) |
| .js | function, class, method | functions only |

### Proposal: Data-Driven Capabilities

Instead of hardcoded extension mappings, derive capabilities from:
1. Analyzer's actual `get_structure()` output
2. Or: Each analyzer declares its extractable types

```python
class PythonAnalyzer(TreeSitterAnalyzer):
    extractable_types = ['function', 'class', 'import']
    # Used by both --capabilities and meta.extractable
```

---

## Related: VEINBORN Feedback Integration

From `VEINBORN_FEEDBACK.md` (neon-abyss-0119):

### Relevant to Extraction

1. **No aggregate summary** - Running `--check` on multiple files lacks summary
2. **No ordinal extraction mentioned** - Case study uses name extraction only

### General Gaps (Not Extraction)

1. `--check` doesn't recurse on directories
2. `imports://` path resolution issues
3. `markdown://` query used wrong directory
4. No baseline/ignore file for --check
5. No severity filtering

### Wishlist Items

- Recursive directory checks
- Aggregate reporting (`--format=summary`)
- CI/CD output formats (github, junit)

---

## Implementation Priority

### Phase 1: Quick Wins (Low Effort, High Value)

1. **`:LINE` extraction** - Detect `:N` pattern, find containing element
2. **Expand category_to_type** - Add 15+ mappings for GraphQL, HCL, Protobuf, etc.
3. **Fix `--capabilities` claims** - Remove types that don't actually work

### Phase 2: Medium Effort

4. **`@N` ordinal extraction** - Support `@3` for 3rd element
5. **`type:N` explicit ordinal** - Support `function:3` syntax
6. **Data-driven capabilities** - Analyzers declare their extractable types

### Phase 3: Architecture

7. **Unified extraction registry** - Single source of truth for what's extractable
8. **Extraction flags** - `--function`, `--class` per heroic-giant-0119

---

## Testing Requirements

Each extraction improvement needs:

1. **Positive tests**: Valid extraction works
2. **Edge cases**: First/last element, single element, no elements
3. **Error messages**: Clear errors for invalid positions/lines
4. **JSON output**: `meta.extractable` reflects actual capabilities

---

## Files to Modify

| File | Changes |
|------|---------|
| `reveal/display/element.py` | Add `:LINE` and `@N` parsing in `extract_element()` |
| `reveal/display/structure.py` | Expand `category_to_type` mapping |
| `reveal/cli/introspection.py` | Fix `_get_extractable_types()` claims |
| `reveal/docs/AGENT_HELP.md` | Document new extraction syntax |
| `tests/test_element_extraction.py` | Add tests for new syntax |

---

## Open Questions

1. Should `:73` extract the element AT line 73, or the element CONTAINING line 73?
   - **Recommendation**: Containing (more useful for jumping into middle of function)

2. Should `@3` be 0-indexed or 1-indexed?
   - **Recommendation**: 1-indexed (matches JSONL, markdown --section)

3. What if `:LINE` is between elements (in whitespace)?
   - **Recommendation**: Return next element, or error with "no element at line N"

---

*Research session: immortal-shrine-0119*
*Context: eternal-god-0119 (hierarchical extraction), heroic-giant-0119 (meta.extractable)*
