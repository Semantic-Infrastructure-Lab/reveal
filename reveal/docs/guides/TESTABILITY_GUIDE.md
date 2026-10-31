---
title: Testability Pressure Guide
category: guide
help_topic: testability
help_description: "Test patch pressure joined with production boundary fan-out (reveal patches --view pressure)"
help_category: feature_guides
---

# Testability Pressure Guide

Use this workflow when tests need many patches or when a production function
mixes business decisions with runtime boundaries such as network clients,
persistence, sleeps, environment, filesystem state, or global state.

The goal is not to say "mocking is bad." Mocking external boundaries is often
correct. The goal is to find review targets where repeated patching and
boundary fan-out overlap.

## Quick Start

```bash
# Raw patch pressure in tests
reveal patches://tests
reveal 'patches://tests?group=target&limit=20'

# Combined workflow: test patches + production boundaries
reveal patches src --view pressure --tests tests
reveal patches src --view pressure --tests tests --top 20
reveal patches src --view pressure --tests tests --format json

# the same view as a queryable URI (testability:// is its retired spelling)
reveal 'patches://src?view=pressure'
reveal 'patches://src?view=pressure&tests=tests,integration_tests'
reveal 'patches://src?view=pressure&top=10'
```

Read the output as a ranked review queue:

- high repeated patch count means tests often replace the same target
- private target patches can mean tests are reaching through internals
- boundary categories show runtime effects in related production functions
- suggestions are advisory, not automatic refactor instructions

Both spellings return `testability_report`. Explicit test roots are checked before
analysis: every requested path must exist. Paths are relative to the working
directory. An existing empty explicit tests directory is valid. Omitting `tests`
uses one selected project test/support policy over the target (its parent for a
file), conventional sibling candidates for directory targets, and literal declared
additional paths. The raw Patches view stays within its target. Narrowed targets
retain the selected project's file roles. Markerless targets use a disclosed
scan-root fallback.

`test_scope` records policy basis, anchor, candidate suite roots and scanned-file
count. Candidate roots include optional missing declarations, so `tests` and
`suite_roots` do not prove presence or runner collection. Existing sibling suites
outside the selected anchor use conventional names without loading their config.
Explicit `tests=` bypasses default policy selection, trusts all Python files and
retains JS/TS recognized test-name rules. Source boundary profiles remain a separate
population and include test functions when they lie under the source target.

Healthy default discovery with no scannable tests returns not-applicable. Directory
or root-stat loss retains analysis diagnostics instead; useful source profiles
survive with an incomplete outcome. Configured selectors follow the
[shared declaration contract](CONFIGURATION_GUIDE.md#project-test-and-support-paths).

CLI path arguments stay literal. In a URI list, percent-encode each path before
joining with commas: `tests=tests%2Cextra,integration_tests` names two roots, the
first of which contains a comma. Whole decimal controls such as `3.0` are accepted;
fractions, booleans, exponent spellings and nonfinite values are usage errors.
`top=0` remains unlimited; negative top clamps to zero and thresholds clamp to one.

## What It Finds

Both the default `patches://` scan and `?view=pressure` scan Python tests with AST parsing and detect:

- `@patch("pkg.mod.name")`
- `patch("pkg.mod.name")`
- `mock.patch("pkg.mod.name")`
- `patch.object(obj, "attr")`
- `patch.dict(...)`
- `patch.multiple(target, **kwargs)` — one target per patched attribute
- `monkeypatch.setattr("pkg.mod.name", value)`
- `monkeypatch.setattr(obj, "attr", value)`
- `monkeypatch.setitem(mapping, key, value)` / `delitem(mapping, key)`
- `monkeypatch.delattr(obj, "attr")`
- `monkeypatch.setenv(name, value)` / `delenv(name)`

TypeScript/JavaScript files selected by the default project test/support policy,
or recognized test files (`.test.ts`/`.spec.ts`/`__tests__/`) in explicit suites,
are scanned with tree-sitter and detect `jest.mock`/`vi.mock`,
`jest.spyOn`/`vi.spyOn`, `jest.fn`/`vi.fn`, and
`jest.replaceProperty`/`vi.replaceProperty`.

All of the above are measured against an independent ground-truth oracle
(100% recall on both languages) — see
[VALIDATION.md](../../../VALIDATION.md).

`reveal patches --view pressure` joins those patch groups to production function profiles.
Each production function's categories come from its own calls, classified by the
same per-language taxonomy as `--sideeffects`:

- `network_client` -- HTTP calls
- `persistence` -- database, cache and session calls
- `filesystem` -- file I/O
- `event_telemetry` -- logging calls
- `clock_sleep` -- sleeps (not clock reads)
- `env_config` -- environment reads
- `process_global` -- process exits (`sys.exit`, PHP `exit`/`die`)
- `mutation` -- in-place collection writes (`append`, `update`, `pop`, ...)

## Good Interpretations

Good:

```text
This target is patched 25 times because it is a genuine external certificate
boundary. A fake checker might reduce repeated setup, but patching is normal.
```

Good:

```text
This private helper is patched repeatedly and the related function touches
persistence, clock_sleep, and mutation boundaries. Extracting the pure
decision step may make tests simpler.
```

Bad:

```text
There are mocks, therefore the design is wrong.
```

## Useful Follow-Up Commands

```bash
# Inspect a patch-heavy production function
reveal src/module.py function_name --boundary
reveal src/module.py function_name --sideeffects

# Find other complex production functions
reveal 'ast://src?complexity>10&sort=-complexity&limit=20'

# See cross-file calls for a function
reveal 'calls://src?callees=function_name'
reveal 'calls://src?callers=function_name'

# Map external surfaces in the codebase
reveal surface src
```

## JSON Output

Use JSON for agents, dashboards, and CI experiments:

```bash
reveal 'patches://tests?group=target' --format json
reveal patches src --view pressure --tests tests --format json
```

The JSON output includes confidence metadata because static target resolution is
best-effort. Do not treat the report as a precise runtime call graph.

The raw scan (`patches://tests`, type `patches_scan`) reports `total_uses`, `total_targets`
and `displayed_groups` at the top level. The pressure view (type `testability_report`)
carries the `summary` object below.

In the pressure view, `summary.total_patch_uses` and `summary.total_boundary_profiles` count observations
before grouping thresholds and display cuts. A pure function with no boundary
categories still contributes a profile. Empty hotspot arrays therefore do not
establish that no observations were collected. `--max-items` cuts both hotspot
lists; JSON `--fields` projects the primary answer. Text `--output json=PATH` saves the
full answer after cuts, including its summary and diagnostics.

## Execution Outcomes

Direct CLI and URI requests use these exits:

| Exit | Meaning |
|------|---------|
| `0` | Complete analysis, including genuine zero observations, or omitted-tests not-applicable |
| `2` | Invalid request, including an empty `tests=` value or a test root that does not exist |
| `3` | Required evidence loss, malformed analysis, operational failure, or requested output failure |

Known required loss with a surviving patch use or function profile is incomplete;
without either it is failed. This deliberately treats constant-only source plus
an entirely failed test scan as failed analysis. Clean-file availability is not
inferred from an empty ranking. Advisory warnings alone do not cause failure.
Only `--fail-on none` is supported; it does not suppress analysis or output failure.
Legacy stdin batches retain their existing policy.

Generic MCP queries use the same direct-request evidence: useful partial answers
remain ordinary results with an incomplete-analysis note, while failed analysis
is a tool error. No dedicated Testability tool is required.

## Limits

- Patch detection supports Python and recognized JavaScript/TypeScript test files.
  Production profiles use the existing per-language structure analysis and boundary taxonomy.
- Local test-file read/parse failures and unavailable JS/TS grammars appear as
  `analysis_failed` warnings. Recovered tree-sitter syntax appears as
  `parse_recovered` warnings; surviving observations remain in the report.
  Production boundary-profile failures and recovered syntax are disclosed separately.
  Diagnostic counts cover all recorded files; displayed path samples stop at five.
- Actual source and test directory enumeration failures are retained separately from
  file failures, including events with no identified directory. The missing file
  population is unknown; diagnostic path samples do not count unseen files.
- Dynamic patch targets are preserved but may have lower confidence.
- Static target resolution is best-effort.
- Project-specific boundary words may need future config.
- Findings remain advisory; analysis and output failures use the execution policy above.
