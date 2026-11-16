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
| `reveal 'stats://src?view=hotspots'` | `reveal 'metrics://src?view=hotspots'` |

## Until the cut release

`stats://` still answers exactly as `metrics://` does, with one
`note: stats:// is deprecated; use ...` line on stderr and a `retired_spelling` entry in JSON
`meta.warnings` (see [Retired spellings](METRICS_ADAPTER_GUIDE.md#retired-spellings)). At the
cut the same text becomes an exit-2 error. Its parameters are metrics' own: `?view=`, `?where=`
(and the bare operator-filter keys), `?code-only=` (alias `?code_only=`), `?churn=`, `?merges=`,
`?since=`, `?tests=`, `?detail=`, `?sort=`, `?limit=`, `?offset=`, `?exclude=`, `?respect_gitignore=`,
and the spellings metrics replaced (`?hotspots=`, `?top=`, `?min_lines=`, `?max_lines=`,
`?min_complexity=`, `?max_complexity=`, `?min_functions=`, `?no_churn=`, `?no_merges=`,
`?summary_only=`; see [Replaced spellings](METRICS_ADAPTER_GUIDE.md#replaced-spellings)).

## See Also

- `reveal help://metrics` - the replacement
- [METRICS_ADAPTER_GUIDE.md](METRICS_ADAPTER_GUIDE.md)
