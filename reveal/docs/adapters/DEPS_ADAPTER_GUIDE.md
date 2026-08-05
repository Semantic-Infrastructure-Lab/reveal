---
title: deps:// Adapter Guide
category: guide
---

# deps:// Adapter Guide

`deps://` is a dependency health dashboard: third-party package usage,
circular dependency cycles, and unused imports for a directory. It is
composed entirely from three `imports://` queries (base, `?circular`,
`?unused`) — not an independent scan.

## Quick Start

```bash
reveal deps
reveal deps ./src
reveal deps . --no-unused
reveal deps . --top 15

reveal 'deps://src'
reveal 'deps://.?top=15'
reveal 'deps://.?no_unused=true'
```

Use JSON when another tool or agent will rank, filter, or store the result:

```bash
reveal deps . --format json
```

## Query Parameters

| Parameter | Values | Purpose |
|-----------|--------|---------|
| `top` | integer (default `10`) | Number of items shown per section in text output (JSON always returns all). |
| `no_unused` | `true`, `false` (default) | Skip the unused-imports section. |
| `no_circular` | `true`, `false` (default) | Skip the circular-dependencies section. |

## Reading The Output

`base` is the raw `imports://` file map. `circular` carries `cycles` and a
`count`. `unused` is a flat list of unused-import entries (`file`, `line`,
`module`, `names`). Text rendering additionally derives third-party/stdlib
package usage counts and a "top importers" ranking from `base`.

## Good Review Questions

- Are any circular dependency cycles new, or in code about to be touched?
- Do the top third-party packages match what's actually documented as a
  dependency?
- Are unused imports concentrated in one area (stale refactor) or scattered?

## Limits

- Stdlib/local-package classification is heuristic (module name matching),
  not a resolved import graph.
- Composed, not independent: results are exactly as good as `imports://`'s
  own detection for each language.

## See Also

- `reveal help://schemas/deps` - JSON schema
- `reveal 'imports://<dir>'` - the full import graph behind this dashboard
- `reveal 'imports://<dir>?circular'` / `?unused` - the underlying queries directly
