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
`module`, `names`). An empty `unused` covers only languages with unused-import
detection (Python, JS/TS, Go, Rust); the rest are listed in
`base.metadata.unused_not_checked_extensions` and the text Health line says
"Unused imports not checked" for them. `skipped` lists the checks turned off
with `no_circular`/`no_unused` (`["circular"]`, `["unused"]`), so an empty
`circular`/`unused` there means "not checked", not "clean"; the text Health line
says "not checked" for them instead of ✅. Text rendering additionally derives
third-party/stdlib package usage counts and a "top importers" ranking from `base`.

`analysis.complete` states whether all requested components completed. Its
`components` records retain each component's `completeness` (`complete`,
`incomplete`, or `failed`), exact `files_failed_count`/`files_lost_count`, and
attributed diagnostics. Lost inputs are included in the failed count. Missing or
malformed count evidence is `null`, with the component marked failed. A recovered
parse or lost input makes required analysis incomplete while preserving surviving
imports and findings. Text reports incomplete or unavailable base, circular and
unused analysis from these same component records. Circular text avoids claiming
there were no cycles when its required evidence is missing.

`analysis.findings` retains full circular-group and unused-import counts before
text caps or JSON summary projection; a missing or malformed findings array has
an unknown (`null`) count rather than a measured zero. Explicitly skipped checks are omitted from
these required components and counts. Diagnostic path lists can be capped at 50;
their exact counts and cut notes remain available. Unsupported languages,
unused-detection limitations, unknown warnings and confidence alone do not make
the analysis incomplete. This evidence does not change the current exit policy.

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
