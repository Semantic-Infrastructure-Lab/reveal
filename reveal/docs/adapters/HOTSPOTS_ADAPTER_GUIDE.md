---
title: hotspots:// Adapter Guide
category: guide
---

# hotspots:// Adapter Guide

> **Retired (BACK-2149).** `reveal hotspots` and `hotspots://` answer as before until the cut release,
> with one note on stderr and a `retired_spelling` entry in JSON `meta.warnings`. Use two commands
> instead: `reveal metrics <path> --hotspots` for the file ranking and its `--fail-on findings` gate,
> and `reveal 'ast://<path>?complexity>=10&sort=-complexity&limit=10' --format json` for the function
> ranking. `has_test_hint` has no replacement field (see [Reading The Output](#reading-the-output)).

`hotspots://` identifies the files and functions most likely to need
attention: low-quality/high-complexity files (via `metrics://`) and
high-cyclomatic-complexity functions (via `ast://`). It composes those two
existing adapters rather than running an independent scan.

## Quick Start (the replacements)

```bash
reveal metrics ./src --hotspots                    # was: reveal hotspots ./src (files), --files-only
reveal metrics ./src --hotspots --top 20           # was: --top 20 (files)
reveal metrics . --hotspots --fail-on findings     # was: reveal hotspots . --fail-on findings
reveal 'ast://.?complexity>=10&sort=-complexity&limit=10' --format json   # was: --functions-only
reveal 'ast://.?complexity>=15&sort=-complexity&limit=20' --format json   # was: --min-complexity 15 --top 20
```

The file entries are the same (`hotspot_score`, `quality_score`, `issues`, `details`, the path-only
`provenance` tag) and `summary.has_findings` is the same predicate, taken over every analysed file
before any cut, so it no longer depends on `--min-complexity`, `--files-only` or `--functions-only`.
The function entries are `ast://` rows (`name`, `file`, `line`, `complexity`, ...); text output groups
them by file, JSON keeps the ranked order.

The rest of this guide describes the retired answer.

## Query Parameters

| Parameter | Values | Purpose |
|-----------|--------|---------|
| `top` | nonnegative integer (default `10`) | Retained items per ranking in text and JSON; `0` = all. |
| `min_complexity` | signed integer (default `10`) | Minimum cyclomatic complexity for a function to be reported. |
| `functions_only` | `true`, `false` (default) | Skip file-level hotspots. |
| `files_only` | `true`, `false` (default) | Skip function-level hotspots (and the test-index scan below). |

Whole decimal/scientific spellings such as `3.0` and `1e2` are accepted for
both numeric parameters; fractions and booleans reject. Negative `top` now rejects
with usage code 2 rather than expanding the rankings; signed `min_complexity`
thresholds remain valid. The two only-flags are independent strict booleans.

`--verbose` lifts both ranking caps in either transport. URI `--all` lifts caps
when no explicit `top` is present; explicit `top` wins. The subcommand rejects
`--all`. These controls retain their existing acceptance boundaries.

## Reading The Output

`file_hotspots` is a ranked list from `metrics://` (`quality_score`,
`hotspot_score`, `issues`, and `details` with `lines`, `functions`, `complexity`,
`commit_count`). `function_hotspots` is a ranked list from
`ast://`'s complexity filter, each annotated with `has_test_hint`.

**`has_test_hint` is retired** (BACK-2149): it was an unmeasured test-name heuristic
(a test whose name resembles the function, not coverage), and no field replaces it
in `metrics` or `ast`. Use the language's coverage tool (coverage.py,
`go test -cover`, `cargo llvm-cov`, Istanbul/c8, JaCoCo). It answers unchanged until
the hotspots noun is removed. What it was: a name-matching guess (does a test for this name exist,
by the language's own convention: Python `test_<name>`, Go `TestName` in
`_test.go`, Rust `#[test] fn`, `*.test.ts`/`*.spec.ts` files, JUnit
`FooTest`/`testBar`?), not real coverage data. It is `null` (unknown, not
untested) for languages with no known test convention, and the result carries
a `test_convention_unknown` warning.

Text output shows a coverage overlay (✅ = test found, ⚪ = no test found, ❔ = unknown for this language)
next to each complex function, using its existing `has_test_hint` value in both
invocation forms. The symbols themselves are presentation; the hint remains in JSON.

`summary.has_findings` records whether the requested population contains a file
with quality below 70 or a function with complexity above 20. File findings use
all analyzed file scores before the composite ranking is cut; a high-ranked file
can have a better quality score than a lower-ranked critical file. When critical
findings fall outside the displayed rankings, text discloses that fact. Function
ranking is descending by complexity, so its retained maximum preserves this
predicate even when `top` cuts the list. `min_complexity` and the two only-flags
still define the requested population. Both only-flags may coexist, leaving both
rankings empty while retaining the statistics coverage scan.

File quality counts file-local check rules only, the same count `metrics://` prints; `meta.issue_count` and the text footer name the rule set, and cross-file rules run under
`reveal check`. A scan cap on a cross-file rule neither changes a score nor fails the scan
([what the issue count counts](METRICS_ADAPTER_GUIDE.md#what-the-issue-count-counts)).

Empty rankings say that no hotspots were found in the requested analyzed
population. This is a scoped observation rather than an overall quality verdict.
Single-file requests support file ranking and disclose failed check rules just
as directory requests do. Optional churn warnings survive composition without
becoming adverse findings.

Both invocation forms return `hotspots_scan` under the
[declared execution policy](../development/OUTPUT_CONTRACT.md#declared-execution-policy).
The default `--fail-on none` reports completed findings with exit 0 in text and JSON.
Use `--fail-on findings` for exit 1 when `summary.has_findings` is true, including
critical files outside the retained ranking. Invalid requests exit 2; required
analysis or requested output failure exits 3 even with `--fail-on none`. This
replaces the former automatic CLI text findings gate.

Stats coverage is required in every mode, including both only-flags together.
AST coverage/results are required unless `files_only` is enabled. Missing or
malformed child proof and failed parse/check analysis remain failures before
ranking or field projection. `parse_degraded`, `check_rules_failed`,
`analysis_failed` and `parse_recovered` indicate incomplete required work;
optional churn/test conventions, confidence alone and ranking cuts do not.
Surviving observations and attributed diagnostics remain available.

`--fields`, URI `--head` and `--max-items` operate after execution facts are
captured. `--output json=PATH` writes the answer beside human or JSON stdout;
successful JSON mirrors equal stdout. A failed requested write preserves the
primary answer and exits 3.
Mixed URI batches retain their legacy execution policy and reject `--fail-on`.

## Good Review Questions

- Do the lowest-quality files match where bugs or incidents have actually
  clustered?
- Do the highest-complexity functions lacking a test hint match your own
  sense of what's risky to change?

## Limits

- Composed, not independent: results are exactly as good as `metrics://`'s
  quality scoring and `ast://`'s complexity metric for each language.
- `has_test_hint` (retired, see above) is a naming heuristic (does a plausibly-named
  test exist?) — it does not run coverage tooling and can both over- and under-count;
  its precision was never measured.
- The test index covers the scanned path plus the project root's own test
  directories (`tests/`, `test/`, `spec/`, ...), so `reveal hotspots src/pkg`
  in a src layout still sees `<root>/tests`.

## See Also

- `reveal help://schemas/hotspots` - JSON schema
- `reveal 'metrics://<dir>?hotspots=true'` - the file-quality data behind `file_hotspots`
- `reveal 'ast://<dir>?complexity>N'` - the function-complexity data behind `function_hotspots`
