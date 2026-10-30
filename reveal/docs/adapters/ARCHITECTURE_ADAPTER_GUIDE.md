---
title: architecture:// Adapter Guide (retired)
category: guide
---

# architecture:// Adapter Guide (retired)

`architecture` and `architecture://` are retired spellings of `overview` and
`overview://`. Use the [overview guide](OVERVIEW_ADAPTER_GUIDE.md) for the compact
project map, controls, counting rules and comparison evidence.

| Retired | Use instead |
|---------|-------------|
| `reveal architecture src/` | `reveal overview src/` |
| `reveal 'architecture://src?top=10'` | `reveal 'overview://src?top=10'` |
| `reveal architecture src/ --against HEAD` | `reveal overview src/ --against HEAD` |

Until the cut, each retired spelling emits a replaced-by note and returns the
canonical `overview` or `overview_diff` answer. The former `facts`, `risks` and
`next_commands` report is removed. Ordinary overview is a bounded map; deeper
import views, metrics, AST complexity, checks and history are separate queries.
Comparisons retain required per-side evidence and unavailable deltas when a
snapshot is incomplete.

`pack --architecture` remains a separate context-selection capability.
