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

reveal 'overview://src'
reveal 'overview://.?no_git=true'
reveal 'overview://.?top=10'
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

## Reading The Output

`stats` carries the summary/hotspots/files data from `stats://`.
`complex_functions` is the `ast://` complexity ranking. `architecture` has
`fan_in`/`entrypoints`/`components`/`circular_count` from `imports://`.
`git_log` is recent commits from `git://`; if the target directory has no
`.git` of its own, `git_foreign_root` names the enclosing repo the history
actually came from.

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
- A directory without its own `.git` inherits the enclosing repo's history
  (disclosed via `git_foreign_root`, not silently hidden).

## See Also

- `reveal help://schemas/overview` - JSON schema
- `reveal 'stats://<dir>?hotspots=true'` - the quality/hotspot data behind this dashboard
- `reveal 'imports://<dir>'` - the fan-in/fan-out/component data behind `architecture`
- `reveal architecture <dir>` - a deeper, standalone architectural brief
