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
Rules are added to `reveal/quality/rules/`.

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

Creates a curated file list that fits within a token budget. Designed for
providing AI agents with the right files to understand a codebase — without
exceeding context limits.

### Usage

```
reveal pack PATH [--budget N] [--focus TOPIC] [--verbose]
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--budget N` | Token budget (e.g., `--budget 4000`). Default: 2000 |
| `--budget N-lines` | Line budget instead of tokens (e.g., `--budget 500-lines`) |
| `--focus TOPIC` | Emphasize files matching this name pattern (e.g., `--focus auth`) |
| `--verbose` | Show per-file token/line counts |
| `--format json` | Machine-readable output |

### Priority Algorithm

Files are scored and selected in this order:

1. **Entry points** — `main.py`, `app.py`, `index.js`, config files, etc.
2. **High-complexity files** — ranked by complexity score
3. **Recently modified files** — ranked by mtime
4. **Other files** — fills remaining budget

Near-empty files (e.g., stub `__init__.py`) are excluded automatically.

### Examples

```bash
reveal pack .                              # Default 2000-token budget
reveal pack . --budget 4000              # Larger budget
reveal pack . --budget 500-lines          # Line-based budget
reveal pack . --focus auth                # Emphasize auth module
reveal pack ./src --budget 8000 --verbose # Show per-file token counts
reveal pack . --format json               # For agent consumption
```

### JSON Output for Agents

```bash
reveal pack . --budget 8000 --format json | jq '.files[].relative'
```

Returns the relative paths of selected files, ready for agent `Read` calls.

Top-level JSON keys: `path`, `budget`, `meta`, `files`. Each `files[]` entry has: `path`, `relative`, `priority`, `tokens_approx`, `lines`, `mtime`, `size`.

### See Also

- `reveal review` — Code quality review
- `reveal pack --help` — Full flag reference

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
