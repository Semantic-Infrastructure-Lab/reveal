---
title: trace:// Adapter Guide
category: guide
---

# trace:// Adapter Guide

`trace://` walks the call graph from a named entry-point function (BFS, via
the same machinery as `calls://`) and builds a depth-indented execution
narrative: each frame shows the function's file/line, parameters,
classified side-effects, and what it calls next.

## Quick Start

```bash
reveal trace src/ --from main
reveal trace src/ --from handle_request --depth 4
reveal trace src/ --from main --format json

reveal 'trace://src?from=main'
reveal 'trace://src?from=handle_request&depth=4'
```

## Query Parameters

| Parameter | Values | Purpose |
|-----------|--------|---------|
| `from` | string (required) | Entry-point function to start the trace from. |
| `depth` | integer (default `2`, clamped 1-5) | How many call levels to expand. |

## Reading The Output

`frames` is BFS-ordered (root first, then level 1, level 2, ...). Each frame
has `file`/`line`, `params`, `effects` (classified side-effect labels like
`db:execute`, `http:get`), `calls` (callee names), and `resolved` — `false`
means the callee is external/unresolved (marked `[external]` in text
output) or its definition couldn't be disambiguated from a same-named
definition in a different language.

## Good Review Questions

- Does the actual call graph from this entry point match your mental model?
- Are there unexpected side-effects (network/db/fs) several levels deep from
  a function that looks pure at the top?
- Are there `[external]` markers where you expected a resolved local call?

## Limits

- Static call-graph only — dynamic dispatch, reflection, and plugin-style
  invocation are not traced.
- A same-named definition across languages is only disambiguated when the
  BFS resolved it through one language family; ambiguous cases render
  unresolved rather than guessing.

## See Also

- `reveal help://schemas/trace` - JSON schema
- `reveal 'calls://<dir>?target=<fn>'` - the reverse direction (who calls this?)
- MCP tool `reveal_trace(dir, entry_point)` - same narrative, MCP-native
