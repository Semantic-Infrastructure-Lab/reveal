---
title: surface:// Adapter Guide
category: guide
---

# surface:// Adapter Guide

`surface://` maps every external boundary a codebase touches: CLI arguments,
HTTP routes, MCP tool registrations, environment variable reads, network/db/sdk
imports, filesystem writes, and subprocess/shell execution. It answers "what
does this system talk to?" without reading the whole tree by hand.

It is taxonomy-based: a curated list of known libraries and language-specific
syntax patterns per category. Project-specific clients outside that taxonomy
are not detected, and dynamic registrations (e.g. plugin-loaded routes) are
not tracked.

## Quick Start

```bash
reveal surface ./src
reveal surface .
reveal surface . --top 20
reveal surface . --type env
reveal surface . --source-only
reveal surface . --source-only --type sdk

reveal 'surface://src'
reveal 'surface://.?type=env'
reveal 'surface://.?source_only=true'
```

Use JSON when another tool or agent will rank, filter, or store the result:

```bash
reveal surface . --format json
reveal 'surface://.?type=env' --format json
```

## Query Parameters

| Parameter | Values | Purpose |
|-----------|--------|---------|
| `type` | `cli`, `http`, `mcp`, `env`, `network`, `db`, `sdk`, `fs`, `subprocess` | Filter to one surface category. |
| `source_only` | `true`, `false` (default) | Exclude test files and directories (`test_*.py`, `*_test.py`, `conftest.py`, `tests/`, `__tests__/`, `*.test.ts`, `*.spec.ts`, etc.). |

The CLI subcommand form additionally supports `--top N` to cap entries shown
per category in text output (JSON always returns all entries).

## Language Coverage

Python, TypeScript/JavaScript, Java, C#, PHP, Swift, Kotlin, Ruby, Go, Rust,
and C++. A tree that's mostly outside this set triggers a coverage warning
rather than a false-clean "no surfaces" verdict.

## Reading The Output

`surfaces` groups entries by category (`cli`, `http`, `mcp`, `env`, `network`,
`db`, `sdk`, `fs`, `subprocess`); each entry carries `file`/`line` plus
category-specific fields (`name`, `type`, `methods`, `path`, `target`, ...).

`coverage` and `scope` describe how much of the tree reveal actually
understood — check `coverage.warning` before trusting an empty or
suspiciously small result on a mixed-language repo.

## Good Review Questions

- Does every network/db/sdk import correspond to a boundary the team actually
  knows about and monitors?
- Are there filesystem writes or subprocess calls outside expected locations?
- Does the CLI/HTTP/MCP surface match what's documented as the public
  interface?
- With `--source-only`, does production code reach further than tests
  exercise?

## Limits

- Taxonomy-based — project-specific clients outside known libraries are not
  detected.
- Dynamic surface registrations (plugin-loaded routes, runtime-constructed
  subprocess commands) are not tracked.
- Confidence is `medium` — treat results as a map to review, not a
  compliance-grade inventory.

## See Also

- `reveal help://schemas/surface` - JSON schema
- `reveal 'imports://<dir>'` - full import graph behind the `network`/`db`/`sdk` buckets
- `reveal 'stats://<dir>'` - quality metrics for the same tree
