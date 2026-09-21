---
title: surface:// Adapter Guide
category: guide
---

# surface:// Adapter Guide

`surface://` maps every external boundary a codebase touches: CLI arguments,
HTTP routes, MCP tool registrations, environment variable reads, network/db/sdk
imports, filesystem writes, and subprocess/shell execution. It answers "what
does this system talk to?" without reading the whole tree by hand.

It is taxonomy-based: a curated list of known libraries and language-specific
syntax patterns per category. Project-specific clients outside that taxonomy
are not detected, and dynamic registrations (e.g. plugin-loaded routes) are
not tracked.

## Quick Start

```bash
reveal surface ./src
reveal surface .
reveal surface . --top 20
reveal surface . --type env
reveal surface . --source-only
reveal surface . --source-only --type sdk
reveal surface . --by dir --depth 2

reveal 'surface://src'
reveal 'surface://.?type=env'
reveal 'surface://.?source_only=true'
reveal 'surface://.?by=dir&depth=2'
```

Use JSON when another tool or agent will rank, filter, or store the result:

```bash
reveal surface . --format json
reveal 'surface://.?type=env' --format json
```

## Query Parameters

| Parameter | Values | Purpose |
|-----------|--------|---------|
| `type` | `cli`, `http`, `mcp`, `env`, `network`, `db`, `sdk`, `fs`, `subprocess` | Filter to one surface category. |
| `source_only` | `true`, `false` (default) | Exclude test files and directories (`test_*.py`, `*_test.py`, `conftest.py`, `tests/`, `__tests__/`, `*.test.ts`, `*.spec.ts`, etc.). |
| `by` | `dir` | Add a per-directory rollup (see below). |
| `depth` | integer >= 0 (default `0`) | With `by=dir`: keep only the first N path segments of each directory, so `depth=2` folds `app/api/util` into `app/api`. `0` keeps the full directory. |

The CLI subcommand form additionally supports `--top N` to cap entries shown
per category in text output (JSON always returns all entries). With `--by dir`,
`--top N` caps directories instead.

## Language Coverage

Python, TypeScript/JavaScript, Java, C#, PHP, Swift, Kotlin, Ruby, Go, Rust,
and C++. A tree that's mostly outside this set triggers a coverage warning
rather than a false-clean "no surfaces" verdict.

Not every language detects every category. A `0` can mean "scanned, found
nothing" or "no detector exists", so the scan reports a `matrix` for the languages
it met: `cells` maps language -> category -> `rules` | `scanner` | `not_applicable`
| `not_implemented`, and `not_implemented` inverts that to category -> languages.
The text report lists those gaps ("mcp: Go, Rust") so they are not read as clean
results. The single source of truth is `reveal/adapters/ast/surface_matrix.py`.

## Reading The Output

`surfaces` groups entries by category (`cli`, `http`, `mcp`, `env`, `network`,
`db`, `sdk`, `fs`, `subprocess`); each entry carries `file`/`line` plus
category-specific fields (`name`, `type`, `methods`, `path`, `target`, ...).

`coverage` and `scope` describe how much of the tree reveal actually
understood — check `coverage.warning` before trusting an empty or
suspiciously small result on a mixed-language repo.

### Per-directory rollup

`--by dir` (or `?by=dir`) answers "which layer owns DB access, shells out, or
reads env" without inferring layering from paths. Text output replaces the
per-category listing with one line per directory, busiest first:

```
By directory (3):
  app/api     4  env 3  subprocess 1
  app/db      2  env 1  db 1
  .           1  env 1
```

JSON keeps `surfaces` unchanged and adds `by_dir`, a list of
`{"dir", "total", "counts": {category: n}}` rows in the same order. The key is
absent unless `by=dir` is requested. It honours `type` and `source_only`, and
its totals sum to the flat `total`.

## Good Review Questions

- Does every network/db/sdk import correspond to a boundary the team actually
  knows about and monitors?
- Are there filesystem writes or subprocess calls outside expected locations?
- Does the CLI/HTTP/MCP surface match what's documented as the public
  interface?
- With `--source-only`, does production code reach further than tests
  exercise?
- With `--by dir`, does each boundary kind sit in the layer that should own it,
  or is it scattered across the tree?

## Limits

- Taxonomy-based — project-specific clients outside known libraries are not
  detected.
- Dynamic surface registrations (plugin-loaded routes, runtime-constructed
  subprocess commands) are not tracked.
- `subprocess` is matched by call shape, not data flow: `subprocess.*`/`os.system`
  (Python, resolved through imports), `exec.Command` (Go), `ProcessBuilder` and
  `Runtime.getRuntime().exec` (Java/Kotlin), `Command::new` (Rust, only when
  imported from a `process` module), `Process.Start`/`ProcessStartInfo` (C#),
  `Process()` (Swift), `system`/backticks/`Open3` (Ruby). A launcher held in a
  variable (`rt.exec(...)`) is not detected. For those eight languages the
  patterns live in one rule table (`reveal/adapters/ast/surface_rules_subprocess.py`);
  TypeScript/JavaScript, PHP and C++ detect it in their own scanners.
- `fs` covers writes only, matched by call shape: `os.WriteFile`/`os.Create` (Go),
  `Files.write`, `new FileWriter()` (Java/Kotlin), `File.WriteAllText`, `new StreamWriter()`
  (C#), `fs::write`/`File::create` (Rust), `File.write`/`FileUtils.mkdir_p` (Ruby),
  `FileManager.default.createFile` (Swift). Swift's `data.write(to:)` is not detected. Those
  languages share one rule table (`reveal/adapters/ast/surface_rules_fs.py`); Python,
  TypeScript/JavaScript, PHP and C++ detect it in their own scanners.
- `env` covers reads with a string-literal key, matched by call shape: `os.Getenv`/`os.LookupEnv`
  (Go), `System.getenv` (Java/Kotlin), `Environment.GetEnvironmentVariable` (C#),
  `env::var`/`env::var_os` (Rust). A key held in a variable or built by interpolation is not
  reported. Those five languages share one rule table (`reveal/adapters/ast/surface_rules_env.py`);
  Python, TypeScript/JavaScript, Ruby, PHP, Swift and C++ detect it in their own scanners
  (subscript and property forms such as `ENV['X']` and `process.env.X` are not table-expressible yet).
- Confidence is `medium` — treat results as a map to review, not a
  compliance-grade inventory.

## See Also

- `reveal help://schemas/surface` - JSON schema
- `reveal 'imports://<dir>'` - full import graph behind the `network`/`db`/`sdk` buckets
- `reveal 'stats://<dir>'` - quality metrics for the same tree
