---
title: trace:// Adapter Guide
category: guide
---

# trace:// Adapter Guide

`trace://` walks the call graph depth-first from a named entry-point
function, one frame per definition, and builds a depth-indented execution
narrative: each frame shows the function's file/line, parameters,
classified side-effects, and what it calls next.

## Quick Start

```bash
reveal trace src/ --from main
reveal trace src/ --from handle_request --depth 4
reveal trace src/ --from main --format json
reveal trace src/ --from src/jobs/runner.py:run   # one of several run() definitions

reveal 'trace://src?from=main'
reveal 'trace://src?from=handle_request&depth=4'
```

## Query Parameters

| Parameter | Values | Purpose |
|-----------|--------|---------|
| `from` | string (required) | Entry-point function to start the trace from. `<file>:<name>` (e.g. `src/app.py:run`) picks one of several same-named definitions; a bare name with several definitions traces each and adds a warning. |
| `depth` | integer (default `2`, clamped 1-5) | How many call levels to expand. |

## Reading The Output

`frames` are in depth-first call order, so each frame follows its caller
(`depth` gives the nesting). Each frame is one definition, with `file`/`line`,
`params`, `effects` (classified side-effect labels like `db:execute`,
`http:get`), `calls` (callee names), `resolved` and `ambiguous`. `resolved:
false` means the callee is external/unresolved (marked `[external]` in text
output). `ambiguous: true` means the callee name matches several definitions
and neither the caller's own file nor its imports pick one; the frame lists
them in `candidates` (text: `[ambiguous: N definitions -- a.py:3, ...]`) and
is not expanded. `warnings` names ambiguous roots and callees.

## Good Review Questions

- Does the actual call graph from this entry point match your mental model?
- Are there unexpected side-effects (network/db/fs) several levels deep from
  a function that looks pure at the top?
- Are there `[external]` markers where you expected a resolved local call?

## Limits

- Static call-graph only — dynamic dispatch, reflection, and plugin-style
  invocation are not traced.
- Resolution is by name: a callee matches definitions in the caller's language
  family, preferring the caller's own file, then the file it imports the name
  from. A method called on a value (`handler.apply(x)`) resolves to the only
  project definition of that name even when the value is a parameter of
  another type.
- Methods declared inside an anonymous class (Java `new Runnable() {...}`) are
  not definitions of their own, so the walk does not descend into them.

## See Also

- `reveal help://schemas/trace` - JSON schema
- `reveal 'calls://<dir>?target=<fn>'` - the reverse direction (who calls this?)
- MCP tool `reveal_trace(dir, entry_point)` - same narrative, MCP-native
