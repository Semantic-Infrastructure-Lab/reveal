---
title: overview:// Adapter Guide
category: guide
---

# overview:// Adapter Guide

`overview://` is a one-glance codebase dashboard: language breakdown,
quality pulse, hotspots, complex functions, an architecture summary (entry
points/core abstractions/components), and recent git activity. It is
composed from `stats://`, `ast://`, `imports://`, and `git://` — not an
independent scan.

## Quick Start

```bash
reveal overview
reveal overview ./src
reveal overview . --no-git
reveal overview . --no-imports
reveal overview . --exclude 'dist/*' --exclude '*.min.js'

reveal 'overview://src'
reveal 'overview://.?no_git=true'
reveal 'overview://.?top=10'
reveal 'overview://.?exclude=dist/*,*.min.js'
```

Use JSON when another tool or agent will consume the result:

```bash
reveal overview . --format json
```

## Query Parameters

| Parameter | Values | Purpose |
|-----------|--------|---------|
| `top` | integer (default `5`) | Number of items shown per section. |
| `no_git` | `true`, `false` (default) | Skip the recent-git-activity section. |
| `no_imports` | `true`, `false` (default) | Skip import graph analysis (architecture section). |
| `exclude` | comma-separated glob patterns | Exclude matching files/directories from the `stats`/hotspots, `scope` and `architecture` sections (an excluded file stays resolvable as an import target). Does not affect `complex_functions`. |
| `respect_gitignore` | `true` (default), `false` | Skip what git ignores, in every section (tracked files are never skipped; `false` or `--no-gitignore` includes ignored files). |

## Reading The Output

`stats` carries the summary/hotspots/files data from `stats://`.
`complex_functions` is the `ast://` complexity ranking. `architecture` has
`fan_in`/`entrypoints`/`components`/`circular_count` from `imports://`.
`git_log` is recent commits from `git://`; if the target directory has no
`.git` of its own, `git_foreign_root` names the enclosing repo the history
actually came from.

`architecture.metadata` retains the Imports owner's `files_failed_count`,
`files_failed`, `files_lost_count`, `files_lost`, and `extraction_diagnostics`
when available. Counts are exact; each path list keeps the existing first 50
paths, with truncation disclosed in parent metadata. Extraction causes are
retained without that path-list cap. Paths and diagnostic keys are relative to
the analysis target, using a resolved Imports build target while preserving the
overview resource spelling. `architecture.unsupported_extensions` stays in its
existing location.

Git discovery happens before requesting history. A target outside any repository
skips that optional section; operational dependency, I/O and repository-open
failures remain attributed diagnostics. `no_git=true` skips discovery and history.
Optional Stats churn warnings reach the overview Caveats section once.

The quality pulse's average describes the analyzed population. Its critical and
warning file counts describe the shown hotspot ranking, which may omit files
outside `top`. No matches in that ranking are not an overall quality verdict.
These evidence repairs preserve the existing overview exit policy; they do not
introduce a findings gate or declared execution binding.

## Good Review Questions

- Does the language breakdown match what you'd expect for this tree?
- Is the quality pulse trending toward more or fewer critical files over
  time?
- Do the entry points and core abstractions match your own mental model?

## Limits

- Composed, not independent: quality is bounded by each underlying
  adapter's own coverage for a given language.
- Static imports only for the architecture section — dynamically loaded
  files (plugins, registries) may appear as spurious entry points.
- `?exclude=` reaches the `stats`/hotspots, `scope` and `architecture`
  sections (BACK-1042, BACK-1495); `complex_functions` (`ast://`) still
  scans the whole tree. `respect_gitignore` applies to
  every section (BACK-1386).
- A directory without its own `.git` inherits the enclosing repo's history
  (disclosed via `git_foreign_root`, not silently hidden).

## See Also

- `reveal help://schemas/overview` - JSON schema
- `reveal 'stats://<dir>?hotspots=true'` - the quality/hotspot data behind this dashboard
- `reveal 'imports://<dir>'` - the fan-in/fan-out/component data behind `architecture`
- `reveal architecture <dir>` - a deeper, standalone architectural brief
