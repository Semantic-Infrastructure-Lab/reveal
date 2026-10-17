---
title: architecture:// Adapter Guide
category: guide
---

# architecture:// Adapter Guide

`architecture://` answers "what do I need to know before editing this
code?" for a directory: entry points, core abstractions, circular
dependency groups, and risks — composed from `imports://` (fan-in/fan-out/
cycles) and `ast://` (complexity), plus a suggested next commands list.

## Quick Start

```bash
reveal architecture src/
reveal architecture .
reveal architecture src/ --no-imports

reveal 'architecture://src'
reveal 'architecture://.?top=10'
reveal 'architecture://.?no_imports=true'
```

Use JSON when another tool or agent will consume the result:

```bash
reveal architecture . --format json
```

For a git-ref diff (what changed architecturally since a branch/tag/commit),
use the CLI subcommand form — this is not part of the URI:

```bash
reveal architecture src/ --against main
```

## Query Parameters

| Parameter | Values | Purpose |
|-----------|--------|---------|
| `top` | integer (default `5`) | Section display cap; also bounds the complexity candidate population used by the analysis. |
| `no_imports` | `true`, `false` (default) | Skip import graph analysis (entry points/core abstractions/cycles all come back empty; complexity-based risks still run). |

## Reading The Output

`facts.entry_points` are live (non-test, non-`__init__.py`, fan-out > 0)
files nothing else imports. `facts.core_abstractions` are files many others
import (fan-in > 0). `facts.circular_groups` are import cycles. `risks`
flags circular groups, high-complexity entry points (complexity ≥ 20), and
load-bearing files (fan-in ≥ 8). `next_commands` suggests the next reveal
invocation for each risk found.

The ordinary report retains AST warnings, errors, confidence and ranking cuts in
`meta`, including when imports and complexity share one walk. A display cut or
an informational complexity caveat does not establish missing input.

A git-ref comparison applies the same explicit exclusions and current project
ignore policy to both snapshots. The base contains tracked files; the live head
honors the selected gitignore policy. Use `--no-gitignore` to include ignored
untracked head files.

Diff JSON records in `analysis` whether it analyzed both snapshots or proved the
trees identical. Snapshot comparisons disclose imports and complexity completeness
for each side. If either required component fails or has missing
input, the result retains attributed diagnostics and returns an `error` with
`deltas: null`. Text says the comparison is unavailable. Empty deltas on a
successful complete result mean no observed architectural change; unavailable
deltas do not. Confidence remains a separate descriptive field.

## Good Review Questions

- Are the entry points what you'd expect, or is something surprising being
  treated as one (a script that should be a library import)?
- Do the core abstractions match your own mental model of "the important
  files" here?
- Is any circular group new, or does it touch code you're about to change?

## Limits

- Static imports only — dynamically loaded files (plugins, registries) may
  appear as spurious entry points.
- Composed, not independent: quality is bounded by `imports://`'s and
  `ast://`'s own per-language coverage (`scope`/`unsupported_extensions`
  disclose this).

## See Also

- `reveal help://schemas/architecture` - JSON schema
- `reveal 'imports://<dir>'` - the fan-in/fan-out/circular data behind `facts`
- `reveal 'ast://<dir>?complexity>20'` - the complexity data behind high-complexity-entry risks
- `reveal architecture <path> --against <ref>` - git-ref diff mode (CLI-only)
