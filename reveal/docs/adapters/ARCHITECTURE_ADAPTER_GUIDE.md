---
title: architecture:// Adapter Guide
category: guide
---

# architecture:// Adapter Guide

`architecture://` answers "what do I need to know before editing this
code?" for a directory or file: entry points, core abstractions, circular
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
use either spelling:

```bash
reveal architecture src/ --against main
reveal 'architecture://src?against=main'
```

## Query Parameters

| Parameter | Values | Purpose |
|-----------|--------|---------|
| `top` | integer (default `5`) | Section display cap; also bounds the complexity candidate population used by the analysis. |
| `no_imports` | `true`, `false` (default) | Skip import graph analysis. Entry points, core abstractions, components, cycles and all risks come back empty, since every risk type is defined over import facts; only the fallback next commands remain. |
| `against` | Nonempty Git ref | Select `architecture_diff`, comparing that ref with the live working tree. |
| `verbose` | `true`, `false` (default) | Expand ordinary complexity analysis and text sections. Also available as `--verbose` on both spellings. |

`top` must be a nonnegative integer. Ordinary analysis requests `top*4`
complexity candidates; zero requests no ranked complexity. Diff preserves its
existing population of `max(top,1)*4`, including a population of four at zero.
Diff rejects explicitly supplied `no_imports` or `verbose`, even false values.
URI `--all` remains a text-only cap override; the subcommand continues to reject
`--all`. Exact parity applies to supported equivalent requests. Ordinary URI `--verbose` now
expands analysis too, matching the subcommand; previously it expanded text only.

The new URI `against` scalar decodes percent escapes once and preserves `+`.
Encode a literal percent as `%25`, ampersand as `%26` and equals as `%3D`.
Existing numeric/boolean parameters retain their raw codec with strict validation.
For resource paths, an existing literal percent path wins; otherwise an encoded
existing path is decoded once. Both empty resources default to the current directory.

Both spellings return the same operation identity and support human output plus
`--output json=PATH`. With primary `--format json`, `--output json=PATH` retains its
existing no-op behavior. Execution exits are 0 for complete answers, 2 for invalid
requests, and 3 for required analysis or requested-output failure/incompleteness.
Only `--fail-on none` is supported; risks do not establish a findings exit gate.
It never suppresses missing required evidence. Scope census errors, import input
loss and recovered/failed parses remain incomplete; harmless warnings, ranking
cuts and documented unsupported-language scope remain successful.

## Reading The Output

`facts.entry_points` are the *active* entry points: of the files nothing but
tests imports ("fan-in 0", the list `imports://<dir>?entrypoints` prints), the
ones with fan-out > 0 that are not test files and not `__init__.py`. The report
states both numbers and the rule: `entry_point_filter` in JSON
(`fan_in_zero`, `active`, `rule`) and the `Entry Points  (N active of M fan-in=0
files)` heading plus an `active = ...` line in text. `facts.core_abstractions` are files many others
import (fan-in > 0); text leaves re-export modules (an `__init__.py`, `index.ts`, `mod.rs` or
`doc.go`) out of that section while JSON keeps them, so its `... and N more` count is lower
than the JSON length. `facts.components` groups files by directory: `files`,
`internal`/`incoming`/`outgoing` edge counts, `cohesion` (internal / (internal + outgoing), 0-1;
`null` with a `cohesion_reason` for a component mostly in a same-package-visibility language)
and `top_bridge` (the file with the most outgoing cross-component edges). `facts.circular_groups`
are import cycles. `scope` and `unsupported_extensions` state what was scanned. `risks`
flags circular groups, high-complexity entry points (complexity ≥ 20), and
load-bearing files (fan-in ≥ 8). `next_commands` gives at most one follow-up per
risk type (the cycle list, `--boundary` on the worst high-complexity entry, a
complexity query when there are core abstractions, and the top load-bearing file),
or `reveal overview <path>` / `reveal <path>` when none apply. File fields are
relative to the target and commands spell paths as the target was given.

Every count states its rule: a `Rule:` line per counting view in text, `edge_rule` (plus `edge_rule_sections` for entry points and cycles) in JSON, built by the same function as `imports://`'s. Fan-in, entry points and components count every static import edge except `TYPE_CHECKING` ones, function-level imports included (entry points ignore importers under a test path); cycles use the load-time view. `architecture://` takes no `&lazy`; `imports://<dir>?rank=fan-in&lazy=exclude` is the load-time view. A git-ref comparison states the same rule once
(`edge_rule` beside `deltas`; both snapshots are counted by it).

The ordinary report retains AST warnings, errors, confidence and ranking cuts in
`meta`, including when imports and complexity share one walk. A display cut or
an informational complexity caveat does not establish missing input.

For required directory loss, the ordinary report needs surviving positive
relationships or requested AST observations to provide useful partial analysis.
Component filenames and zero-edge rows alone do not establish that availability.
With no usable observations, or malformed required child evidence, analysis is
failed and MCP reports an error; useful partial analysis retains its warnings.
A clean zero remains complete. AST availability uses its validated uncapped
`total_results` before ranking limits, including when `top=0` hides all rows.

A git-ref comparison applies the same explicit exclusions and current project
ignore policy to both snapshots. The base contains tracked files; the live head
honors the selected gitignore policy. Use `--no-gitignore` to include ignored
untracked head files.

Diff JSON records in `analysis` whether it analyzed both snapshots or proved the
trees identical; for identical trees `analysis.basis` is `identical_tree` and the
deltas show no change, with unmeasured centroid `base`/`head` values `null`, proved
`change: 0.0`, and the selected `top_n` population (text says `No architectural change: the working tree under <path> is
identical to <ref>, so neither snapshot was analyzed.`). The header and JSON `path` name
the target as you typed it. Snapshot comparisons disclose imports and complexity completeness
for each side. If either required component fails or has missing
input, including required source or resolution-target directory enumeration loss,
the result retains attributed diagnostics and returns an `error` with
`deltas: null`. Text says the comparison is unavailable. Empty deltas on a
successful complete result mean no observed architectural change; unavailable
deltas do not. Directory warnings retain snapshot attribution and unknown missing-file
population; base-side causes use relative display rather than temporary materialization
paths. Confidence remains a separate descriptive field.

## Good Review Questions

- Are the entry points what you'd expect, or is something surprising being
  treated as one (a script that should be a library import)?
- Do the core abstractions match your own mental model of "the important
  files" here?
- Is any circular group new, or does it touch code you're about to change?

## Limits

The independent `scope` census is an optional composed section. If directory
enumeration fails, it follows the existing optional-section failure behavior:
`scope` is empty, one `E_COMPOSE` diagnostic is retained, confidence is `0.0`,
and the analysis is incomplete (direct CLI exit 3), including an otherwise empty
result. Directory warnings identify the scope census; they do not establish lost
imports, AST rows or physical file statistics. Required-analysis failures retain
their own failure outcome.

- Static imports only — dynamically loaded files (plugins, registries) may
  appear as spurious entry points.
- Composed, not independent: quality is bounded by `imports://`'s and
  `ast://`'s own per-language coverage (`scope`/`unsupported_extensions`
  disclose this).

## See Also

- `reveal help://schemas/architecture` - JSON schema
- `reveal 'imports://<dir>'` - the fan-in/fan-out/circular data behind `facts`
- `reveal 'ast://<dir>?complexity>20'` - the complexity data behind high-complexity-entry risks
- `reveal architecture <path> --against <ref>` - git-ref diff mode
