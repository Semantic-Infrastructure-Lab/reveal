---
title: "reveal Subcommands"
type: guide
---

# reveal Subcommands

Reference for reveal's top-level subcommands. These are high-level workflow commands distinct from URI adapters.

---

## reveal dev — Developer Tooling

Scaffolding and introspection tools for extending Reveal.

### Commands

```
reveal dev new-adapter NAME [--uri SCHEME]    # Scaffold a new URI adapter
reveal dev new-analyzer NAME [--ext EXT]     # Scaffold a new file analyzer
reveal dev new-rule CODE NAME [--cat CAT]    # Scaffold a new quality rule
reveal dev inspect-config [PATH]             # Show effective .reveal.yaml config
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--uri SCHEME` | URI scheme for new adapter (e.g., `mydb`) |
| `--ext EXT` | File extension for new analyzer (e.g., `.myext`) |
| `--cat CAT` | Rule category (bugs, maintainability, performance, etc.) |

### Examples

```bash
reveal dev new-adapter mydb --uri mydb        # Creates adapters/mydb/ scaffold
reveal dev new-analyzer toml --ext .toml      # Creates analyzers/toml.py scaffold
reveal dev new-rule M999 "Too Long" --cat maintainability
reveal dev inspect-config                     # See config applied to current dir
reveal dev inspect-config /some/project/      # See config for another dir
```

### Scaffold Output

New adapters and analyzers are created in the current reveal source tree.
Rules are added to `reveal/rules/`.

### See Also

- `reveal help://scaffolding` — Full scaffolding guide
- `reveal help://adapter-authoring` — How to write adapters
- `reveal dev --help` — Full flag reference

---

## reveal review — PR Review Workflow

Automated code review orchestrator. Runs quality checks, finds hotspots, and
reports complex functions — all in one pass.

### Usage

```
reveal review PATH                 # Review a directory
reveal review main..feature        # Review a git range (files changed vs main)
reveal review HEAD~3..HEAD         # Review last 3 commits
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--select RULES` | Rule categories (default: B,S,I,C,M) |
| `--format json` | Machine-readable output for CI/CD gating |
| `--verbose` | Show detailed violation messages |

### Output Sections

1. **Structural changes** — files modified (git range mode only)
2. **Violations** — quality rule failures by severity (error / warning / info)
3. **Hotspots** — files with highest complexity or churn, with quality scores
4. **Complex functions** — functions above complexity threshold
5. **Recommendation** — pass/fail summary

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | No errors |
| `1` | Warnings only |
| `2` | Errors found |

### CI/CD Integration

```bash
# Gate on errors only
reveal review . --format json | jq '.sections.violations | map(select(.severity=="error")) | length == 0'

# Gate on any violations
reveal review main..HEAD --format json | jq '.overall_status == "pass"'
```

### Examples

```bash
reveal review .                     # Review current directory
reveal review ./src                 # Review src/ only
reveal review main..feature-branch  # PR review (git range)
reveal review . --verbose           # Show full violation details
reveal review . --format json       # For CI/CD
```

### See Also

- `reveal check` — Run quality rules on specific files
- `reveal health` — Health check for services/paths
- `reveal review --help` — Full flag reference

---

## reveal health — Unified Health Check

Unified health check across all resource types. Routes automatically based on
target type — no need to know which adapter to use.

### Usage

```
reveal health TARGET [TARGET ...]
reveal health --all
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--all` | Check all resources detectable in context (source dir or configured targets) |
| `--select RULES` | Rule categories to check (e.g., `B,S,I,C`) |
| `--format json` | Machine-readable output |
| `--verbose` | Show detailed check results |

### Target Types (Auto-detected)

| Target | What it checks |
|--------|----------------|
| `./path` or `/path` | Directory quality (violations, hotspots) |
| `ssl://example.com` | SSL certificate validity, expiry, chain |
| `mysql://host` | MySQL connectivity, replication health |
| `domain://example.com` | DNS, registrar, HTTPS availability |

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All checks pass |
| `1` | Warnings (non-critical issues) |
| `2` | Failures (action required) |

### Examples

```bash
reveal health .                         # Local directory health
reveal health ssl://example.com         # SSL cert health
reveal health domain://example.com      # Domain + DNS health
reveal health --all                     # Auto-detect: source dir + configured targets

# Composable: check multiple targets
reveal health ./src ssl://api.example.com mysql://localhost

# Configure targets in .reveal.yaml for `--all`:
# health:
#   targets: [src/, ssl://api.example.com]

# CI/CD: fail on warnings or failures
reveal health . --format json | jq '.exit_code == 0'
```

### See Also

- `reveal review` — Code review workflow
- `reveal check` — Quality rules only
- `reveal health --help` — Full flag reference

---

## reveal pack — Token-Budgeted Context Snapshot

Creates a curated context snapshot that fits within a token budget. With `--content`,
emits the reveal structure of each selected file — making pack directly agent-consumable
without a second round-trip of `Read` calls.

### Usage

```
reveal pack PATH [--budget N] [--focus TOPIC] [--since REF] [--content] [--verbose]
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--budget N` | Token budget (e.g., `--budget 4000`). Default: 2000 |
| `--budget N-lines` | Line budget instead of tokens (e.g., `--budget 500-lines`) |
| `--since REF` | Boost files changed since `REF` (branch, commit, or `HEAD~N`) to top priority |
| `--focus TOPIC` | Emphasize files matching this name pattern (e.g., `--focus auth`) |
| `--content` | Emit reveal structure output for each selected file (agent-ready context) |
| `--architecture` | Boost high fan-in (core abstraction) files; prepend architecture brief |
| `--verbose` | Show per-file token/line counts |
| `--format json` | Machine-readable output |

### Priority Algorithm

Files are scored and selected in this order:

1. **Changed files** (when `--since` is used) — files in `git diff --name-only <ref>...HEAD`, boosted above all else
2. **Entry points** — `main.py`, `app.py`, `index.js`, config files, etc.
3. **High-complexity files** — ranked by complexity score
4. **Recently modified files** — ranked by mtime
5. **Other files** — fills remaining budget

Near-empty files (e.g., stub `__init__.py`) are excluded automatically.

### Examples

```bash
reveal pack .                              # Default 2000-token budget
reveal pack . --budget 4000              # Larger budget
reveal pack . --budget 500-lines          # Line-based budget
reveal pack . --focus auth                # Emphasize auth module
reveal pack ./src --budget 8000 --verbose # Show per-file token counts
reveal pack . --content                   # Structure content, not just file list
reveal pack src/ --since main --content --budget 8000  # Full agent context: changed + structure
reveal pack src/ --since main --budget 8000    # PR context: changed files first (manifest only)
reveal pack src/ --since HEAD~3 --budget 4000  # Since 3 commits ago
reveal pack . --architecture              # Boost core abstractions; show architecture brief
reveal pack . --format json               # For agent consumption
```

### Agent-Ready Output with --content

Without `--content`, pack outputs a file manifest — which files are most important. Agents still have to read those files themselves.

With `--content`, pack emits the reveal structure of each selected file after the manifest:

```
Pack: src/  [~8000 tokens budget]  [since main]
Changed files: 3 (boosted to top priority)
Selected 12 of 47 files (~7340 tokens, 892 lines)

── Changed files (since main) ──
  auth.py
  ...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTENT  (reveal structure for each selected file)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

── auth.py  ◀ CHANGED ──
File: auth.py (3.2KB, 94 lines)
Imports (3): ...
Functions (4): authenticate_user, refresh_token, ...
```

### JSON Output for Agents

```bash
# File list only (for targeted Read calls):
reveal pack . --budget 8000 --format json | jq '.files[].relative'

# Structure content in JSON (agent-consumable):
reveal pack . --budget 8000 --content --format json
```

Without `--content`: top-level JSON keys: `path`, `budget`, `since`, `meta`, `files`.
With `--content`: also includes `content` — a list of `{file, changed, structure}` dicts.

### See Also

- `reveal review` — Code quality review
- `reveal pack --help` — Full flag reference

---

## reveal trace — Execution Narrative

Walk the call graph forward from a named entry point and print a depth-indented execution narrative. Each frame shows the function's location, parameters, classified side-effects, and what it calls next.

### Usage

```
reveal trace [PATH] --from FUNC [--depth N] [--format {text,json}]
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--from FUNC` | Entry-point function to start the trace from (required) |
| `--depth N` | Call levels to expand, 1–5 (default: 2) |
| `--format` | Output format: `text` (default) or `json` |

### Side-Effect Classification

Each frame is labelled with detected side-effects:

| Tag | Meaning |
|-----|---------|
| `db` | Database call |
| `http` | Outbound HTTP |
| `cache` | Cache read/write |
| `file` | Filesystem I/O |
| `log` | Logging call |
| `sleep` | Blocking sleep |
| `hard_stop` | `sys.exit` / raise without catch |

Unresolved (external/stdlib) callees appear with an `[external]` marker.

### Examples

```bash
reveal trace src/ --from main               # Trace from main(), depth 2
reveal trace src/ --from process_order --depth 3
reveal trace . --from handle_request --format json  # Machine-readable output
```

### Known Limitations

- **Silent miss on unknown function name (BACK-254):** If `--from <name>` does not match any function in the project, trace reports `Resolved: 0` and shows the name as `[external]` with no warning. Verify the function name with `reveal <path>` before tracing.

### See Also

- `calls://` adapter — raw cross-file call graph queries
- `reveal trace --help` — Full flag reference

---

## reveal contracts — Contract & Seam Inventory

Find all architectural contracts in a codebase: ABCs, Protocols, TypedDicts, `@dataclass` classes, Pydantic BaseModels, and path-heuristic base classes. Lists abstract methods per contract and which classes implement each one.

### Usage

```
reveal contracts [PATH] [--abstract-only] [--no-implementations] [--format FORMAT]
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--abstract-only` | Show only ABCs and Protocols; skip TypedDicts, dataclasses, path-heuristic |
| `--no-implementations` | Skip showing which classes implement each contract |
| `--format` | `text` (default), `json`, `typed`, `grep` |

### Examples

```bash
reveal contracts ./src               # All contracts in src/
reveal contracts .                   # Entire project
reveal contracts . --abstract-only   # Only ABCs and Protocols
reveal contracts . --format json     # Machine-readable output
```

### See Also

- `reveal surface` — External boundary map (HTTP routes, env vars, etc.)
- `reveal contracts --help` — Full flag reference

---

## reveal surface — External Boundary Map

Map every external surface the system touches: CLI arguments, HTTP routes, MCP tool registrations, environment variables, network I/O, database/SDK imports, and filesystem writes. Answers "what does this system touch outside itself?"

### Usage

```
reveal surface [PATH] [--type TYPE] [--format FORMAT]
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--type TYPE` | Filter to one surface type (see table below) |
| `--format` | `text` (default), `json`, `typed`, `grep` |

### Surface Types

| Type | What it finds |
|------|--------------|
| `cli` | CLI arguments (`argparse`, `click`) |
| `http` | HTTP route handlers (Flask/FastAPI decorators) |
| `mcp` | MCP tool registrations |
| `env` | Environment variable reads (`os.getenv`, `os.environ.get`) |
| `network` | Outbound network imports (`requests`, `httpx`, etc.) |
| `fs` | Filesystem writes (`open(…,'w')`, `Path.write_text`) |
| `db` | Database/ORM imports |
| `sdk` | Third-party SDK imports |

### Examples

```bash
reveal surface ./src                 # All surfaces in src/
reveal surface .                     # Entire project
reveal surface . --type env          # Only env var reads
reveal surface . --type http         # Only HTTP route handlers
reveal surface . --format json       # Machine-readable output
```

### Known Limitations

- **`env` type false positives (BACK-250):** Any dict `.get()` call (`trade.get("key")`, `config.get("val")`) is currently misclassified as an environment variable read. Until fixed, `--type env` output will be noisy on codebases that use dict `.get()` heavily. Cross-check with `grep -r 'os.getenv\|os.environ' <path>` to identify true env var reads.
- **Python-only** — surface scans `.py` files only.

### See Also

- `reveal contracts` — Architectural contracts (ABCs, Protocols, TypedDicts)
- `reveal surface --help` — Full flag reference

---

## reveal hotspots — Complexity Hotspot Finder

Identifies high-complexity files and functions that need the most attention.
Surfaces the worst 10 (or N) files by cyclomatic complexity.

### Usage

```
reveal hotspots [PATH] [--top N] [--min-complexity N]
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--top N` | Number of hotspot files to show (default: 10) |
| `--min-complexity N` | Minimum cyclomatic complexity to report (default: 10) |
| `--functions-only` | Show only complex functions, skip file-level hotspots |
| `--files-only` | Show only file-level hotspots, skip function analysis |
| `--format json` | Machine-readable output |

### Test Coverage Heuristic

Complex functions in hotspot output include a test-coverage indicator:

- **✅** — a corresponding test exists (scanned from `tests/`, `test/`, `spec/` directories)
- **⚪** — no test found for this function name

> **Limitation (BACK-253):** The heuristic looks for `def test_<function_name>` in test files. Projects using `test_<module>_<scenario>` naming (e.g. `test_bearish_sweep_of_session_high` in `test_liquidity_sweep.py`) will show ⚪ even when a full test suite exists. A ⚪ means the heuristic didn't find a match — not that the function is definitely untested.

JSON output (`--format json`) includes `has_test_hint: true/false` per function, enabling scripted filtering:

```bash
reveal hotspots . --format json | jq '.function_hotspots[] | select(.has_test_hint == false and .complexity > 15)'
```

### Examples

```bash
reveal hotspots ./src              # Hotspots in a directory
reveal hotspots .                  # Entire project
reveal hotspots ./src --top 20     # Show top 20 files
reveal hotspots . --format json    # Machine-readable output
reveal hotspots . --functions-only # Only show complex functions
reveal hotspots . --files-only     # Only file-level view
```

### See Also

- `reveal check` — Full quality rules (not just complexity)
- `reveal review` — Combined review with hotspots + violations
- `reveal hotspots --help` — Full flag reference

---

## reveal overview — Codebase Dashboard

One-glance dashboard synthesising stats, language breakdown, quality pulse, top
hotspots, complex functions, architecture overview (entry points, core
abstractions, component cohesion, circular count), and recent git activity into
a single view.

### Usage

```
reveal overview [PATH] [--top N] [--no-git]
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--top N` | Items to show per section (default: 5) |
| `--no-git` | Skip the recent git activity section |
| `--no-imports` | Skip the Architecture section (import graph analysis) |
| `--format json` | Machine-readable output |

### Examples

```bash
reveal overview                      # Current directory
reveal overview ./src                # Specific directory
reveal overview . --top 10           # 10 items per section
reveal overview . --no-git           # Skip git history
reveal overview . --format json      # Machine-readable output
```

### See Also

- `reveal hotspots` — Deep dive into complexity hotspots
- `reveal deps` — Dependency health details
- `reveal overview --help` — Full flag reference

---

## reveal architecture — Architectural Brief

Targeted architectural briefing for a directory. Answers "what do I need to
know before editing this code?" Composes entry points, core abstractions,
component cohesion, circular dependency groups, and derived risks into one
output. Designed for agent consumption and subdirectory targeting.

### Usage

```
reveal architecture [PATH] [--top N] [--no-imports] [--format json]
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--top N` | Items to show per section (default: 5) |
| `--no-imports` | Skip import graph analysis |
| `--format json` | Machine-readable output: `{path, facts, risks[], next_commands[]}` |

### Output Sections

- **Entry Points** — files with fan-in=0, sorted by fan-out (active callers of other code)
- **Core Abstractions** — files most imported by others (high fan-in)
- **Components** — directory cohesion bars
- **Risks** — derived from findings: circular groups, high-complexity entry points, load-bearing files
- **Next Commands** — specific `reveal` follow-up commands generated from what was found

### Examples

```bash
reveal architecture src/            # Brief for a specific directory
reveal architecture .               # Whole project
reveal architecture src/ --format json  # Machine-readable for agents
reveal architecture src/ --no-imports   # Skip import analysis (faster)
```

### Notes

Static imports only — dynamically loaded files (plugins, registries) may appear
as entry points. High entry point counts often indicate dynamic loading patterns.

### See Also

- `reveal overview` — Full codebase health dashboard (stats, quality, git)
- `reveal deps` — Dependency health: circular, unused, external packages
- `reveal architecture --help` — Full flag reference

---

## reveal deps — Dependency Health Dashboard

Wraps `imports://` to give a one-pass dependency health summary: external
package count, circular dependency detection, unused imports, top importers.

### Usage

```
reveal deps [PATH] [--top N] [--no-unused] [--no-circular]
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--top N` | Top packages/importers to show (default: 10) |
| `--no-unused` | Skip unused imports section |
| `--no-circular` | Skip circular dependency section |
| `--format json` | Machine-readable output |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | No issues |
| 1 | Circular deps or unused imports found |

### Examples

```bash
reveal deps                          # Current directory
reveal deps ./src                    # Specific directory
reveal deps . --no-unused            # Skip unused imports
reveal deps . --format json          # Machine-readable for CI
```

### See Also

- `imports://` — Full import graph queries
- `reveal overview` — Includes dependency summary
- `reveal deps --help` — Full flag reference

---

## reveal check — Quality Rule Engine

Run 69 built-in quality rules against a file or directory. Covers bugs, complexity, imports, maintainability, security, types, and more. Exit code 1 = issues found.

### Usage

```
reveal check [path] [flags]
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--select RULES` | Run only specific rules or categories: `B,S` or `B001,I002` |
| `--ignore RULES` | Skip rules or categories |
| `--only-failures` | Hide passing checks; show violations only |
| `--recursive, -r` | Recurse into directories (default: on) |
| `--advanced` | Enable deeper validation checks |
| `--severity LEVEL` | Minimum level: `low`, `medium`, `high`, `critical` |
| `--format` | `text` (default), `json`, `typed`, `grep` |
| `--rules` | List all available rules with descriptions |
| `--explain CODE` | Explain a specific rule (e.g., `--explain B001`) |

### Rule Categories

| Category | Code | What it checks |
|----------|------|----------------|
| Bugs | B | Bare excepts, bad decorators, unresolvable imports |
| Complexity | C | Cyclomatic complexity, function length, nesting depth |
| Duplicates | D | Duplicate function detection |
| Errors | E | Line length and style errors |
| Frontmatter | F | Markdown frontmatter presence, required fields, type validity |
| Imports | I | Unused imports, circular dependencies, layer violations |
| Links | L | Broken internal links, missing index files, low cross-reference density |
| Maintainability | M | File size, orphaned files, version mismatches, hardcoded lists |
| Infrastructure | N | nginx config: SSL, ACME, proxy headers, timeout mismatches |
| Refactoring | R | Too many function arguments |
| Security | S | Docker `:latest` tags and security anti-patterns |
| Types | T | Type annotation gaps: `Optional[]` on nullable params (T001–T004), annotation coverage (T005), TypedDict suggestions for bare-dict params (T006) |
| URLs | U | Insecure `http://` GitHub URLs, URL/canonical mismatches |
| Validation | V | Reveal self-checks: version consistency, adapter contracts, doc accuracy |

### Examples

```bash
reveal check src/                          # check all files recursively
reveal check file.py                       # single file
reveal check src/ --select B,S            # bugs and security only
reveal check src/ --only-failures         # show violations only
reveal check src/ --format json           # machine-readable
reveal check src/ --severity high         # high/critical issues only
reveal check --rules                      # list all 69 rules
reveal check --explain C901              # explain the complexity rule
git diff --name-only | reveal --stdin --check  # check only changed files
```

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | No violations found |
| `1` | One or more violations found |

Exit code 1 is set consistently across all invocation forms: single file, directory, and `--stdin --check` piped file lists.

### See Also

- `reveal review` — Full PR review orchestrator (runs check + hotspots + summary)
- `reveal hotspots` — Complexity-focused view
- `reveal check --help` — Full flag reference

---

## reveal scaffold — Component Generator

Scaffold new reveal components (adapters, analyzers, rules) with correct structure and boilerplate.

### Usage

```
reveal scaffold {adapter,analyzer,rule} [options]
```

### Examples

```bash
reveal scaffold adapter mydb --uri mydb://    # new URI adapter skeleton
reveal scaffold analyzer toml --ext .toml     # new file type analyzer
reveal scaffold rule B007                     # new quality rule stub
```

### See Also

- `reveal dev` — Developer tooling (includes scaffold wrappers)
- `ADAPTER_AUTHORING_GUIDE.md` — Full adapter authoring guide
- `reveal help://scaffolding` — In-tool scaffolding reference
