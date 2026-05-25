---
title: Codex Adapter Guide (codex://)
category: guide
---
# Codex Adapter Guide (codex://)

**Adapter Version**: reveal 0.97.0+

---

## Overview

The **codex://** adapter navigates and analyzes [OpenAI Codex CLI](https://github.com/openai/codex) sessions. Codex stores sessions in a SQLite index (`~/.codex/state_5.sqlite`) with per-session JSONL event files — a different storage model from Claude Code, so this is a dedicated adapter rather than a fork of `claude://`.

**Key capabilities:**
- Session listing and metadata search via SQLite (fast — no JSONL scanning)
- Full-text content search across all session JSONL files
- Per-turn token breakdown (input/output/cached/reasoning split)
- Shell command tracking with exit codes and output
- Tool call pairing (`function_call` + `function_call_output`)
- Install introspection (config, history, memories, rules)

---

## Quick Start

```bash
# List recent sessions
reveal 'codex://'

# Find sessions by title/first-message
reveal 'codex://sessions/?search=peyton'

# Full-text search across all session content
reveal 'codex://sessions/?content=authentication'

# Session overview (turns, tools, tokens, duration)
reveal 'codex://019e5cc5'

# Last agent message — fastest session recovery
reveal 'codex://019e5cc5?last'

# Per-turn token breakdown
reveal 'codex://019e5cc5?tokens'

# Conversation turns (user + agent messages)
reveal 'codex://019e5cc5/messages'

# Tool calls with paired outputs
reveal 'codex://019e5cc5/tools'

# Shell commands with exit codes and output
reveal 'codex://019e5cc5/shell'

# Errors and warnings from the session
reveal 'codex://019e5cc5/errors'

# Install info and DB stats
reveal 'codex://info'
```

---

## URI Reference

### Session List

| URI | What it returns |
|-----|----------------|
| `codex://` | All user sessions from SQLite, newest first |
| `codex://sessions/` | Same as bare `codex://` |
| `codex://sessions/?search=<term>` | Filter by title or first message (SQLite) |
| `codex://sessions/?content=<term>` | Full-text JSONL search across all sessions |

### Session Analysis

| URI | What it returns |
|-----|----------------|
| `codex://<UUID>` | Overview: turns, tool calls, tokens, duration, git state |
| `codex://<UUID>?last` | Last agent message only — fast recovery pattern |
| `codex://<UUID>?tokens` | Per-turn token breakdown (input/output/cached/reasoning) |
| `codex://<UUID>/messages` | All user and agent turns in order |
| `codex://<UUID>/tools` | Paired `function_call` + `function_call_output` events |
| `codex://<UUID>/shell` | `exec_command_end` events: command, exit code, output |
| `codex://<UUID>/errors` | Error, warning, and guardian_warning events |

**UUID prefix**: You can use the first 7+ hex characters instead of the full UUID. `reveal 'codex://019e5cc5'` resolves to the matching session.

### Install Introspection

| URI | What it returns |
|-----|----------------|
| `codex://info` | Resolved paths, DB exists/size, session count |
| `codex://history` | `~/.codex/history.jsonl` prompt history |
| `codex://config` | `~/.codex/config.toml` with secrets masked |
| `codex://memories` | `~/.codex/memories/` MEMORY.md and summaries |
| `codex://rules` | `~/.codex/rules/*.rules` Starlark permission rules |

---

## Token Analysis

Codex emits `token_count` events after each API request with a delta (`last_token_usage`) and running total (`total_token_usage`). The `?tokens` route surfaces the per-turn breakdown:

```bash
reveal 'codex://019e5cc5?tokens'
# Codex Token Usage: 12 turn(s)  |  running total: 3,790,050
#
#   TURN  TIMESTAMP              INPUT    CACHED   OUTPUT   REASON    TOTAL
#   ----- -------------------- -------- -------- -------- -------- --------
#   1     2026-05-25 01:35:58   16,343    3,456      205        0   16,548
#   2     2026-05-25 01:36:19   28,100    8,200      310        0   28,410
#   ...
```

Fields:
- **INPUT**: prompt tokens (includes context)
- **CACHED**: prompt tokens served from the API cache (no cost)
- **OUTPUT**: completion tokens generated
- **REASON**: reasoning tokens (gpt-5.5 reasoning steps)
- **TOTAL**: INPUT + OUTPUT (not INPUT + CACHED + OUTPUT)

---

## Shell Commands

Codex tracks shell execution via `exec_command_end` events (no separate begin event — the end event contains everything):

```bash
reveal 'codex://019e5cc5/shell'
# Codex Shell Calls: 4
#
#   $ pwd  [2026-05-25T01:36:01]
#     → exit=0  8ms
#     /home/scottsen/src/projects/...
#
#   $ rg --files -g 'README.md'  [2026-05-25T01:36:05]
#     → exit=0  45ms
#     docs/README.md
#     src/README.md
```

---

## Content Search

`?content=<term>` scans all session JSONL files for a term in `user_message` and `agent_message` payloads:

```bash
reveal 'codex://sessions/?content=authentication'
# Codex Content Search: 3 session(s) matching 'authentication'
#
#   019e5cc5  2026-05-25  [gpt-5.5]  lets find all past sessions...
#     [USER] 2026-05-25 01:35:58  help me understand the authentication flow...
#     [AGENT] 2026-05-25 01:36:01  I'll look at the auth middleware first...
```

This is a full-file scan — use `?search=` first for fast SQLite metadata filtering.

---

## Storage Layout

```
~/.codex/
├── state_5.sqlite        ← session index (SQLite) — primary lookup
├── sessions/
│   └── 2026/05/25/
│       └── rollout-*.jsonl   ← per-session event stream
├── history.jsonl         ← prompt history
├── config.toml           ← user config
├── memories/             ← MEMORY.md + session summaries
├── rules/                ← Starlark permission rules
└── goals_1.sqlite        ← per-thread objectives + token budgets
```

---

## Differences from claude://

| Dimension | codex:// | claude:// |
|-----------|----------|-----------|
| Session ID | UUID (7+ hex prefix works) | Named slug (`amber-fire-0425`) |
| Primary index | SQLite `threads` table | Filesystem scan |
| Tool calls | `function_call`/`function_call_output` (JSONL events) | `tool_use`/`tool_result` (message blocks) |
| Shell execution | Dedicated `exec_command_end` events | Bash tool call in tool_use |
| Reasoning | `encrypted_content` — count only | `thinking` blocks — readable |
| Token data | Per-request via `token_count` events | Estimated from char count |
| Config | TOML | JSON |

---

## Environment Overrides

| Variable | Default | Purpose |
|----------|---------|---------|
| `REVEAL_CODEX_HOME` | `~/.codex` | Override Codex home directory |
| `REVEAL_CODEX_DB` | `~/.codex/state_5.sqlite` | Override SQLite DB path |

---

## Related Documentation

- `reveal help://adapters` — All adapters
- [Claude Adapter Guide](CLAUDE_ADAPTER_GUIDE.md) — Sister adapter for Claude Code sessions
- [CODEX_ADAPTER_DESIGN_2026-05-24.md](../../internal-docs/design/CODEX_ADAPTER_DESIGN_2026-05-24.md) — Design doc with JSONL format details
