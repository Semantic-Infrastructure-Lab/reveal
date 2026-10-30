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

Controls follow the canonical guide: `top` bounds ordinary map rows, while
`all` and `verbose` expand them. `no_imports` requests a scope-only map.
`exclude` supplies comma-separated scope globs; `respect_gitignore` defaults
to true, and false includes ignored candidates subject to other exclusions.
`against` selects comparison and rejects explicit `no_imports`, `all` or
`verbose` controls, even false values. The removed dashboard controls `no_git`
and `tests` reject with guidance toward Git and metrics/AST queries; they do
not select another map mode or alter graph test policy. See the
[overview controls](OVERVIEW_ADAPTER_GUIDE.md#controls) for the full contract.

`pack --architecture` remains a separate context-selection capability.
