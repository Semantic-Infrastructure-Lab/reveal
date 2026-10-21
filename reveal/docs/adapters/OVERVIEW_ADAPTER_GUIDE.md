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
| `top` | nonnegative whole number (default `5`) | Analysis and presentation cap; `3.0` and `3e0` normalize to 3. Fractions, booleans and negative values reject. |
| `no_git` | `true`, `false` (default) | Skip the recent-git-activity section. |
| `no_imports` | `true`, `false` (default) | Skip import graph analysis (architecture section). |
| `exclude` | comma-separated glob patterns | Exclude matching files/directories from the `stats`/hotspots, `scope` and `architecture` sections (an excluded file stays resolvable as an import target). Does not affect `complex_functions`. |
| `respect_gitignore` | `true` (default), `false` | Skip what git ignores, in every section (tracked files are never skipped; `false` or `--no-gitignore` includes ignored files). |

`no_git` and `no_imports` accept strict boolean spellings: `true`/`yes`/`1` and
`false`/`no`/`0`; bare presence is true and unrecognized values reject.
`--all` or `--verbose` expands analysis and text rankings in both spellings,
including when an explicit `top` was supplied. This corrects the URI form's
previous analysis-only cap under those flags. Without either flag, `top=0`
retains all Stats hotspots, zero complex functions and zero Git history entries;
top-controlled text rankings show no entries. Core abstractions keep their
existing fixed five-entry text cap. The complete Stats `files` inventory remains
available, as do the complete Imports rankings in JSON.

Both spellings use fixed answer type `overview` and the same declared execution
path. `--fail-on none` is the default and sole supported policy: a nonempty
dashboard has no adverse-findings gate. Completed work exits 0, invalid parameters
or missing resources exit 2, and required analysis or output failure exits 3.
Unsupported `--fail-on findings` rejects with usage 2. Legacy stdin/mixed batches
retain their separate policy and reject `--fail-on`.

## Reading The Output

`stats` carries the summary/hotspots/files data from `stats://`.
`complex_functions` is the `ast://` complexity ranking. `architecture` has
`fan_in`/`entrypoints`/`components`/`circular_count` from `imports://`.
`architecture.entrypoints` lists every fan-in-0 file; the text view shows only
the active ones (fan_out > 0, not a test file, not `__init__.py`).
`architecture.entry_point_filter` carries the counts and the rule
(`fan_in_zero`, `active`, `rule`), and the text prints the same as
`Entry points  (M fan-in=0, N active)` plus an `active = ...` line.
Every count states its rule: a `Rule:` line per counting view in text, `edge_rule` (plus `edge_rule_sections` for entry points and cycles) in JSON (inside `architecture`), built by the same function as `imports://`'s. Fan-in, entry points and components count every static import edge except `TYPE_CHECKING` ones, function-level imports included (entry points ignore importers under a test path); cycles use the load-time view. `overview://` takes no `&lazy`; `imports://<dir>?rank=fan-in&lazy=exclude` is the load-time view.
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

Quality counts file-local check rules only, the same count `stats://` and `hotspots` print
(`stats.files[].quality.local_check_issues`); `meta.issue_count` and the text footer name the
rule set, and cross-file rules run under `reveal check`. A cross-file scan cap therefore
neither changes a score nor fails the overview
([what the issue count counts](METRICS_ADAPTER_GUIDE.md#what-the-issue-count-counts)).

The quality pulse's average describes the analyzed population. Its critical and
warning file counts describe the shown hotspot ranking, which may omit files
outside `top`. No matches in that ranking are not an overall quality verdict.
Stats, AST and scope evidence are required; Imports is required unless
`no_imports=true`. Missing or malformed required child payloads, failed check
rules, failed/recovered parses and failed/lost Imports inputs make execution
incomplete. Optional Git absence, churn notices, low confidence, unsupported
extensions and ranking cuts do not independently make completed work fail.
Operational Git failures remain failures when Git was requested. Child populations
can differ legitimately, including on unsupported-language and excluded trees.

After required directory loss, surviving measured Stats, requested AST observations
or positive relationships support useful partial analysis. Physical-line measurements
can survive a degraded parse. Filenames, census totals and zero-edge membership
alone do not prove availability. With no useful observations, or malformed required
child evidence, analysis is failed and MCP reports an error. A clean zero remains
complete. The validated uncapped AST count preserves availability before `top=0`
or other ranking limits; projections cannot manufacture observations or erase failure.

Execution facts are retained before `--fields` projection and postprocessing.
Human-primary `--output json=PATH` retains complete arrays; a failed artifact write
exits 3. Primary JSON keeps its established `--output json=PATH` no-op. Closed stdout
alone retains exit 0 but cannot erase an independent analysis or output failure.
Overview has no sliceable outer list: URI `--head` and `--max-items` disclose no
effect, and generated CLI `--max-items` likewise leaves these arrays unchanged.

## Good Review Questions

- Does the language breakdown match what you'd expect for this tree?
- Is the quality pulse trending toward more or fewer critical files over
  time?
- Do the entry points and core abstractions match your own mental model?

## Limits

The independent `scope` census is an optional composed section. If directory
enumeration fails, it follows the existing optional-section failure behavior:
`scope` is empty, one `E_COMPOSE` diagnostic is retained, confidence is `0.0`,
and the analysis is incomplete (direct CLI exit 3), including an otherwise empty
result. Directory warnings identify the scope census; they do not establish lost
imports, AST rows or physical file statistics. Required-analysis failures retain
their own failure outcome.

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
