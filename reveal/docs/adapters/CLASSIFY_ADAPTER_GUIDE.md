---
title: classify:// Adapter Guide (retired)
category: guide
---

# classify:// Adapter Guide (retired)

`classify://` is retired: `metrics://` absorbed it as `?view=provenance` (BACK-2069), the same
report from the same owner. The view, its heuristics and its exclusion counts are documented
once, in [METRICS_ADAPTER_GUIDE.md](METRICS_ADAPTER_GUIDE.md#provenance-view).

| Retired | Use instead |
|---------|-------------|
| `reveal 'classify://src'` | `reveal 'metrics://src?view=provenance'` |
| `reveal 'classify://src?respect_gitignore=false'` | `reveal 'metrics://src?view=provenance&respect_gitignore=false'` |

## Until the cut release

`classify://` still answers exactly as before: every analyzable file with its provenance tag,
`summary.total`, `summary.by_provenance`, `summary.excluded` and
`summary.excluded_by_extension`, with one `note: classify:// is deprecated; use ...` line on
stderr and a `retired_spelling` entry in JSON `meta.warnings`. At the cut the same text becomes
an exit-2 error. Its one parameter is `respect_gitignore` (boolean, default `true`).

## See Also

- `reveal help://metrics` - the replacement
- [METRICS_ADAPTER_GUIDE.md](METRICS_ADAPTER_GUIDE.md#provenance-view)
