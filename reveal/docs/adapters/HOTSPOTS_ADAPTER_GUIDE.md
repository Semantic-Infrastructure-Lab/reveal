---
title: hotspots:// Adapter Guide
category: guide
---

# hotspots:// Adapter Guide

`hotspots://` identifies the files and functions most likely to need
attention: low-quality/high-complexity files (via `stats://`) and
high-cyclomatic-complexity functions (via `ast://`). It composes those two
existing adapters rather than running an independent scan.

## Quick Start

```bash
reveal hotspots ./src
reveal hotspots .
reveal hotspots ./src --top 20
reveal hotspots . --functions-only
reveal hotspots . --files-only

reveal 'hotspots://src'
reveal 'hotspots://.?top=20'
reveal 'hotspots://.?functions_only=true'
```

Use JSON when another tool or agent will rank, filter, or store the result:

```bash
reveal hotspots . --format json
reveal 'hotspots://.?top=20' --format json
```

## Query Parameters

| Parameter | Values | Purpose |
|-----------|--------|---------|
| `top` | integer (default `10`) | Number of hotspots to show per list; `0` = all (as `--limit 0` and `--all`). |
| `min_complexity` | integer (default `10`) | Minimum cyclomatic complexity for a function to be reported. |
| `functions_only` | `true`, `false` (default) | Skip file-level hotspots. |
| `files_only` | `true`, `false` (default) | Skip function-level hotspots (and the test-index scan below). |

## Reading The Output

`file_hotspots` is a ranked list from `stats://` (quality score, hotspot
score, issues, line count). `function_hotspots` is a ranked list from
`ast://`'s complexity filter, each annotated with a heuristic
`has_test_hint` — a name-matching guess (does a test for this name exist,
by the language's own convention: Python `test_<name>`, Go `TestName` in
`_test.go`, Rust `#[test] fn`, `*.test.ts`/`*.spec.ts` files, JUnit
`FooTest`/`testBar`?), not real coverage data. It is `null` (unknown, not
untested) for languages with no known test convention, and the result carries
a `test_convention_unknown` warning.

Text output shows a coverage overlay (✅ = test found, ⚪ = no test found, ❔ = unknown for this language)
next to each complex function; this is recomputed from the same heuristic
at render time and is not part of the JSON contract.

## Good Review Questions

- Do the lowest-quality files match where bugs or incidents have actually
  clustered?
- Do the highest-complexity functions lacking a test hint match your own
  sense of what's risky to change?

## Limits

- Composed, not independent: results are exactly as good as `stats://`'s
  quality scoring and `ast://`'s complexity metric for each language.
- `has_test_hint` is a naming heuristic (does a plausibly-named test exist?)
  — it does not run coverage tooling and can both over- and under-count.

## See Also

- `reveal help://schemas/hotspots` - JSON schema
- `reveal 'stats://<dir>?hotspots=true'` - the file-quality data behind `file_hotspots`
- `reveal 'ast://<dir>?complexity>N'` - the function-complexity data behind `function_hotspots`
