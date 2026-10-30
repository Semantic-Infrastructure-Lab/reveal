---
title: overview:// Adapter Guide
category: guide
---

# overview:// Adapter Guide

Start with `overview` to learn a project's shape: recognized code files and
languages, major components, import relationships, entrypoint candidates and
cycles. Text and JSON present the same compact map, with coverage and visible
cuts. Follow its drill-down commands to investigate a specific question.

## Quick Start

```bash
reveal overview
reveal overview ./src
reveal overview . --top 10
reveal overview . --top 0
reveal overview . --no-imports
reveal overview . --exclude 'dist/*' --exclude '*.min.js'
reveal overview . --format json
reveal 'overview://src?top=10'
```

## Controls

These controls describe the ordinary map; comparison controls are listed below.

| Parameter | Purpose |
|-----------|---------|
| `top` | Nonnegative whole-number presentation limit, default 5. Bounds each graph section and each cycle's member and witness lists. Zero shows totals without graph rows. Whole-valued `3.0` and `3e0` normalize; fractions, booleans and negatives reject. |
| `no_imports` | Explicit scope-only map, with graph analysis marked not requested. Strict boolean spellings are accepted. |
| `exclude` | Comma-separated globs narrowing the configured census and graph scope. An excluded file can remain resolvable as an import target. |
| `respect_gitignore` | True by default. False or `--no-gitignore` includes ignored candidates subject to other scope exclusions; tracked files remain eligible. |
| `--all`, `--verbose` | Expand map rows, overriding top. They do not request quality or history analysis. |

`no_git` and `tests` were dashboard controls and now reject with a correction.
Use Git queries for history and metrics/AST queries for assessment rankings.
They do not change the map's import counting rules.

## Reading the Map

`scope` counts recognized code files retained by the configured scope, with
language counts and capabilities. This is not an inventory of every repository
file: unknown extensions, documentation and data are outside that census.
Exclusion disclosures count hidden **entries**; a pruned directory is one entry,
not a measured count of its descendants. Traversal failures leave the missing
population unknown. Unmeasured skipped-file counters are not reported as zero.

`map` contains bounded `fan_in`, `entrypoints`, `components` and `cycles` records.
Each has `rows`, `total`, `returned` and `omitted`; cycle member and witness lists
carry their own bounds. Components rank by covered file count, then path.
Selected rows retain coupling and bridge facts. Declined cohesion stays null
with its reason, rather than becoming a numeric score.

Entrypoints use the shared static predicate: fan-in zero ignoring test importers,
positive fan-out, excluding test files and Python package initializers. The predicate uses producer
paths before shortening them for display. These
are candidates for investigation; static imports do not establish runtime entry.
`entry_point_filter` reports the raw candidate population and active subset.

Counting rules accompany the facts. Fan-in and components count static imports
including function-level imports; entrypoint fan-in ignores test importers.
Cycles use the load-time view. TYPE_CHECKING imports are excluded. The rules
state the scope and test policy; use imports queries for other views.

`map_status` distinguishes `complete`, `incomplete`, `failed` and `not_requested` graph
work. `map=null` with `not_requested` status is an intentional scope-only answer.
Scan accounting describes the observed graph: a capped or inexact scan is not
proof of an exhaustive project inventory. Unsupported extensions, hidden inputs,
parse, traversal and worker losses remain visible.

Diagnostic details are bounded separately from graph rows: a small sample is
retained even at top zero, with counts and truncation disclosures. Expanding a
map does not make missing analysis complete. Required evidence is captured before
field selection and presentation cuts, so `--fields` cannot erase a failure.

## Investigate the Next Question

```bash
reveal imports . --rank fan-in
reveal imports . --components
reveal imports . --entrypoints
reveal imports . --circular
reveal metrics . --hotspots
reveal 'ast://.?type=function&sort=-complexity&limit=20'
reveal check .
reveal 'git://.?type=history&limit=10'
```

The raw imports entrypoint query includes static fan-in-zero candidates that the
map's active predicate leaves out. Metrics, complexity, checks and history are
separate investigations; ordinary overview does not run those assessments.
For due diligence, use the map to choose scope, gather deeper evidence, then make
a judgment. Absence of a relationship in a bounded map is not proof of absence.

## Output and Outcomes

Ordinary CLI and URI requests use answer type `overview` and the same declared operation.
Completed work exits 0; invalid resources or parameters exit 2; required analysis
or requested output failure exits 3. `--fail-on none` is the sole supported gate.
A map has no adverse-findings verdict.

Human-primary `--output json=PATH` writes the same bounded map as a JSON artifact;
a failed artifact write exits 3. Primary JSON retains its existing JSON-file-sink
no-op. `--max-items` and URI `--head` have no sliceable outer list: they disclose
no effect. Use top to expand or reduce the map's graph sections.

## Compare Against a Git Ref

```bash
reveal overview . --against HEAD
reveal overview ./src --against HEAD --format json
reveal 'overview://.?against=HEAD&top=5'
```

Against selects a separate `overview_diff` operation before ordinary map work.
It compares the tracked base at the ref with the live working tree, including
uncommitted changes. The head label is `working tree`. It uses the existing
architecture comparison engine; it does not compare the former quality dashboard.
The Git extra is required: `pip install "reveal-cli[git]"`.

Comparison preserves fan-in/out, cycle, coupling, active-entrypoint and complexity
centroid deltas. Its centroid population is `max(top, 1) * 4`: default top five
means twenty functions, and top zero means four. This is different from ordinary
map presentation, where top zero shows no graph rows.

`analysis` states completeness, basis and per-side imports/complexity evidence.
An `identical_tree` proof has no measured snapshots: centroid base/head values
are null, with proved change zero. Analyzed snapshots may legitimately measure
zero. Missing required snapshot evidence, including capped import discovery, gives
unavailable deltas and exit 3;
invalid refs/resources give exit 2. Existing exclusions and gitignore policy
remain symmetric across the base and live head.

Top, scope exclusions, gitignore, output, provenance and the none-only failure
gate remain supported. Omit ordinary-only no_imports, all and verbose controls
in comparisons, even if explicitly false; no_git/tests remain obsolete.
Explicit field selection may omit payload sections while validated execution
facts and failure diagnostics still determine exits and MCP error state.

## Retired Architecture Spelling

`architecture` and `architecture://` are retired aliases. Until the cut they emit
a replaced-by note and return the same canonical `overview` or `overview_diff`
answer. The old risks and next-commands report is removed. `pack --architecture`
retains its separate context-selection behavior.

## See Also

- `reveal help://schemas/overview` — declared controls and output schema
- [Imports guide](IMPORTS_ADAPTER_GUIDE.md) — graph views and counting rules
- [Metrics guide](METRICS_ADAPTER_GUIDE.md) — metrics and quality assessment
