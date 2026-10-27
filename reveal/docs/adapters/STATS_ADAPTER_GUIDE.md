---
title: stats:// Adapter Guide (retired)
category: guide
---

# stats:// Adapter Guide (retired)

`stats://` is retired: it was renamed `metrics://`, the same adapter with the same
answers. Everything it does is documented once, in
[METRICS_ADAPTER_GUIDE.md](METRICS_ADAPTER_GUIDE.md).

| Retired | Use instead |
|---------|-------------|
| `reveal stats://src` | `reveal metrics://src` |
| `reveal 'stats://src?hotspots=true'` | `reveal 'metrics://src?hotspots=true'` |
| `reveal stats://src --hotspots` | `reveal metrics://src --hotspots` |

## Until the cut release

`stats://` still answers exactly as `metrics://` does, with one
`note: stats:// is deprecated; use ...` line on stderr and a `retired_spelling` entry in JSON
`meta.warnings` (see [Retired spellings](METRICS_ADAPTER_GUIDE.md#retired-spellings)). At the
cut the same text becomes an exit-2 error. Its parameters are metrics' own: `?view=`,
`?hotspots=`, `?top=`, `?code_only=`, `?min_lines=`, `?max_lines=`, `?min_complexity=`,
`?max_complexity=`, `?min_functions=`, `?churn=`, `?since=`, `?no_merges=`, `?tests=`, `?summary_only=`,
`?sort=`, `?limit=`, `?offset=`, plus the operator-filter syntax.

## See Also

- `reveal help://metrics` - the replacement
- [METRICS_ADAPTER_GUIDE.md](METRICS_ADAPTER_GUIDE.md)
