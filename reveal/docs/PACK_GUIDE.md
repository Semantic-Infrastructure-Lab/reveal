---
title: "reveal pack — Token-Budgeted Context Snapshot"
type: guide
---

# reveal pack — Token-Budgeted Context Snapshot

Creates a curated file list that fits within a token budget. Designed for
providing AI agents with the right files to understand a codebase — without
exceeding context limits.

## Usage

```
reveal pack PATH [--budget N] [--focus TOPIC] [--verbose]
```

## CLI Flags

| Flag | Description |
|------|-------------|
| `--budget N` | Token budget (e.g., `--budget 10000`). Default: 4000 |
| `--budget N-lines` | Line budget instead of tokens (e.g., `--budget 500-lines`) |
| `--focus TOPIC` | Boost files matching this topic (e.g., `--focus authentication`) |
| `--verbose` | Show per-file token/line counts |
| `--format json` | Machine-readable output |

## Priority Algorithm

Files are scored and selected in this order:

1. **Entry points** — `main.py`, `app.py`, `cli.py`, config files, etc.
2. **Focus matches** — files whose path contains the `--focus` topic
3. **Key directories** — `core/`, `api/`, `models/`, `auth/`, etc.
4. **Recency** — recently modified files ranked higher

Near-empty files (e.g., stub `__init__.py`) are excluded automatically.

## Examples

```bash
reveal pack .                              # Default 4000-token budget
reveal pack . --budget 10000              # Larger budget
reveal pack . --budget 500-lines          # Line-based budget
reveal pack . --focus authentication      # Boost auth-related files
reveal pack ./src --budget 8000 --verbose # Show per-file token counts
reveal pack . --format json               # For agent consumption
```

## JSON Output for Agents

```bash
reveal pack . --budget 8000 --format json | jq '.selected[].relative'
```

Returns the relative paths of selected files, ready for agent `Read` calls.

## See Also

- `reveal review` — Code quality review
- `reveal pack --help` — Full flag reference
