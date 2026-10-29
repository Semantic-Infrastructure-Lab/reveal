---
title: trace:// Adapter Guide (retired)
category: guide
---

# trace:// Adapter Guide (retired)

`trace://` and `reveal trace` are retired: trace merged into `calls://`, whose callee walk they
already answered from. The walk, its resolution rule, `--detail` params and side effects, and
its limits are documented once, in [CALLS_ADAPTER_GUIDE.md](CALLS_ADAPTER_GUIDE.md#callees).

| Retired | Use instead |
|---------|-------------|
| `reveal 'trace://src?from=main&depth=2'` | `reveal 'calls://src?callees=main&depth=2&detail'` |
| `reveal trace src/ --from main --depth 2` | `reveal calls src/ --callees main --depth 2 --detail` |
| `from=src/app.py:run` / `--from src/app.py:run` | `callees=src/app.py:run` / `--callees src/app.py:run` |
| `trace://src?from=script.py:<module>` | `calls://src?callees=script.py:<module>` |
| MCP `reveal_trace(dir, entry_point)` | `reveal_query('calls://<dir>?callees=FUNC&depth=2&detail')`; the tool keeps its name for now |

Trace's default depth was 2; `callees` defaults to 1.

## Until the cut release

Both spellings still answer exactly as before, with one
`note: ... is deprecated; use ...` line on stderr and a `retired_spelling` entry in JSON
`meta.warnings` (see [Retired spellings](CALLS_ADAPTER_GUIDE.md#retired-spellings)). At the cut
the same text becomes an exit-2 error.

- **Output:** the `trace` result type and its `frames`, in pre-order under the call that first
  reaches each definition. A frame is one definition with `file`/`line`, `params`, `effects`,
  `calls` (callee labels), `depth`, `resolved`, `ambiguous` (`candidates` when ambiguous) and
  `relationship` for JSX references. `[external]` and `[ambiguous: N definitions -- ...]` mark
  unresolved and ambiguous callees in text.
- **Parameters:** `from` (required; `FILE:NAME` picks one definition) and `depth` (signed whole
  integer, default 2, clamped 1-5; booleans and fractions exit 2).
- **Exits:** 0 complete; 2 invalid input or a proven absent entry point; 3 incomplete analysis
  or a required output failure. Only `--fail-on none` is supported. The MCP tool keeps its
  historical nonerror answer for a proven absent entry point.

### Python API compatibility

While Trace remains available, `api.query` applies declared typed `from` and `depth`
overrides. For example:

```python
from reveal import api

report = api.query("trace://src?from=main&depth=1", **{"from": "other", "depth": 3})
```

The original URI validates first: a missing or invalid required `from` still rejects
before overrides. Explicit values replace valid URI controls; omission keeps them.
`depth=None` selects default 2, and zero clamps to 1. Invalid typed values raise
`ValueError`; unsupported API keywords, including `root` and `from_`, raise `TypeError`.
Typed selectors remain literal rather than being URI-encoded or decoded again.

Direct adapter calls bind controls in constructor `params=` and then call
`get_structure()`. Plain constructor mappings keep the CLI destination name:
`TraceAdapter(path, params={"root": "main", "depth": 3})`. Method keywords now raise
`TypeError`; previously they were ignored. The retirement and execution policies
above remain in effect.

## See Also

- `reveal help://schemas/trace` - the retired result type's JSON schema
- [CALLS_ADAPTER_GUIDE.md](CALLS_ADAPTER_GUIDE.md) - `?callees=&depth=&detail`, the replacement
