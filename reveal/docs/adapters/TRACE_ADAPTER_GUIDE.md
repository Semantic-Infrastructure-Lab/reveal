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

JSON also retains typed `meta.warnings` for `analysis_failed` and
`parse_recovered`, including exact counts and up to five affected paths. Surviving
frames describe the evidence that was available. Malformed collection rows carry
attributed `E_COMPOSE` entries in `meta.errors`; valid sibling rows remain usable.
Text prints mirrored legacy and typed diagnostics once. External/ambiguous calls
and requested depth limits are separate observations, not failed input evidence.

These evidence disclosures preserve the current exit policy: a surviving root
can still return 0 with partial input, while an unknown root is rejected by the
subcommand and remains an unresolved frame through URI invocation. Inspect the
diagnostics before treating a trace as complete; declared execution binding is
not part of this producer change.

JSX component-reference frames carry `relationship: jsx_reference` (or
`call_and_jsx_reference` when the symbol is also called) and text labels them
`[JSX reference]`. Their parent retains source reference lines. Following these
frames explores source dependencies; it does not establish runtime render order.
Imported component aliases use the same resolver as ordinary calls.

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


Top-level Python, JS/TS, PHP and Ruby script/block calls can be traced from a
file-qualified synthetic root, for example
`reveal 'trace://src?from=script.py:<module>&depth=2'`. The module root begins at
line 1; `calls://?target=` retains the actual call-site lines. This static scope
excludes deferred function bodies, class-body initializers, extensionless Ruby DSL
files and other languages' top-level code.
