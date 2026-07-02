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
- Chronological workflow view — tool calls + shell commands interleaved by timestamp
- Full event timeline — every JSONL event type in session order
- Per-turn token breakdown (input/output/cached/reasoning split)
- Shell command tracking with exit codes, output, and duration
- Tool call pairing (`function_call` + `function_call_output`)
- Thread goal tracking (`goals_1.sqlite`) — objective, status, token budget
- Memory pipeline status — Stage1/Stage2 consolidation from `stage1_outputs`
- Install introspection (config, history, memories, rules)

---

## Quick Start

```bash
# List recent sessions
reveal 'codex://'

# Find sessions by title/first-message
reveal 'codex://sessions/?search=auth-refactor'

# Full-text search across all session content
reveal 'codex://sessions/?content=authentication'

# Session overview (turns, tools, tokens, duration)
reveal 'codex://019e5cc5'

# Last agent message — fastest session recovery
reveal 'codex://019e5cc5?last'

# Per-turn token breakdown
reveal 'codex://019e5cc5?tokens'

# Thread goal (objective + token budget)
reveal 'codex://019e5cc5?goal'

# Conversation turns (user + agent messages)
reveal 'codex://019e5cc5/messages'

# Tool calls with paired outputs
reveal 'codex://019e5cc5/tools'

# Shell commands with exit codes and output
reveal 'codex://019e5cc5/shell'

# Errors and warnings from the session
reveal 'codex://019e5cc5/errors'

# Tools + shell interleaved chronologically
reveal 'codex://019e5cc5/workflow'

# Full event stream in session order
reveal 'codex://019e5cc5/timeline'

# Install info and DB stats
reveal 'codex://info'

# Memory pipeline status
reveal 'codex://memories/pipeline'
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
| `codex://<UUID>?goal` | Thread goal from `goals_1.sqlite` (objective, status, token budget) |
| `codex://<UUID>/messages` | All user and agent turns in order |
| `codex://<UUID>/tools` | Paired `function_call` + `function_call_output` events |
| `codex://<UUID>/shell` | `exec_command_end` events: command, exit code, output |
| `codex://<UUID>/errors` | Error, warning, and guardian_warning events |
| `codex://<UUID>/workflow` | Tool calls + shell commands interleaved chronologically |
| `codex://<UUID>/timeline` | All events in session order with brief summaries |

**UUID prefix**: You can use the first 7+ hex characters instead of the full UUID. `reveal 'codex://019e5cc5'` resolves to the matching session.

### Install Introspection

| URI | What it returns |
|-----|----------------|
| `codex://info` | Resolved paths, DB exists/size, session count |
| `codex://history` | `~/.codex/history.jsonl` prompt history |
| `codex://config` | `~/.codex/config.toml` with secrets masked |
| `codex://memories` | `~/.codex/memories/` MEMORY.md and summaries |
| `codex://memories/pipeline` | Stage1/Stage2 memory consolidation pipeline status |
| `codex://rules` | `~/.codex/rules/*.rules` Starlark permission rules |

---

## Workflow

`/workflow` interleaves tool calls and shell commands in chronological order — the same sequence the agent executed them. Use this when you want to understand what the session actually did and in what order.

```bash
reveal 'codex://019d9da3/workflow'
# Codex Workflow: 299 action(s)
#
#   [✓] tool  exec_command({"cmd":"find /home/user/projects -maxdepth 2...)  [2026-04-17T22:51:18]
#       → Chunk ID: f1427c
#
#   [✓] shell $ find /home/user/projects -maxdepth 2 -type d -iname '*reveal*'  [2026-04-17T22:51:18]
#       → exit=0
#
#   [✓] tool  exec_command({"cmd":"ls -la /home/user/projects/reveal"...})  [2026-04-17T22:51:24]
#       → Chunk ID: 9e60cd
```

Two event kinds appear:
- **tool** — a `function_call`/`function_call_output` pair; `[✓]` if an output was paired, `[✗]` if not
- **shell** — a native `exec_command_end` event (only in sessions using the sandbox shell); `[✓]` if `exit_code == 0`

Note: in most recent Codex sessions, shell execution goes through the `exec_command` function_call tool (appears as `tool` kind). Native `exec_command_end` events appear in older or sandbox-mode sessions.

---

## Timeline

`/timeline` shows every JSONL event in the session — the raw event stream with brief summaries. Use this for full forensic analysis of what happened and when.

```bash
reveal 'codex://019e5cc8/timeline'
# Codex Timeline: 640 event(s)
#
#   2026-05-25T01:38:35  [session_meta                  ]  session  model=?
#   2026-05-25T01:38:35  [event_msg/task_started        ]  task started
#   2026-05-25T01:38:35  [response_item/message         ]  <permissions instructions>
#   2026-05-25T01:38:35  [turn_context                  ]  cwd=/home/user/projects/acme-app
#   2026-05-25T01:38:35  [event_msg/user_message        ]  which/where !deploy.sh  ? read that script
#   2026-05-25T01:38:40  [event_msg/agent_message       ]  I'll locate `deploy.sh` on the active PATH...
#   2026-05-25T01:38:40  [response_item/function_call   ]  exec_command({"cmd":"command -V deploy.sh"...})
#   2026-05-25T01:38:40  [response_item/function_call_output]  → Chunk ID: 9f6153
#   2026-05-25T01:38:40  [event_msg/token_count         ]  tokens total=16548
```

Event types in the stream:
- `session_meta` — session ID, cwd, model, git state
- `turn_context` — model, sandbox policy, approval mode (per-turn)
- `event_msg/user_message` / `event_msg/agent_message` — conversation turns
- `response_item/function_call` / `response_item/function_call_output` — tool execution
- `event_msg/exec_command_end` — native shell execution (sandbox mode)
- `event_msg/token_count` — running token totals after each API call
- `event_msg/task_complete` — turn duration and token summary
- `response_item/reasoning` — reasoning steps (content encrypted — count only)

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

Codex tracks native shell execution via `exec_command_end` events (no separate begin event — the end event contains everything: command list, exit code, output, duration):

```bash
reveal 'codex://019d9da3/shell'
# Codex Shell Calls: 143
#
#   $ find /home/user/projects -maxdepth 2 -type d -iname '*reveal*'  [2026-04-17T22:51:18]
#     → exit=0
#     /home/user/projects/reveal
#
#   $ rg --files /home/user/projects | rg '/(package.json|Cargo.toml|...)'  [2026-04-17T22:51:18]
#     → exit=0
#     /home/user/projects/billing-service/README.md
```

See also: `exec_command` tool calls appear in `/tools` and `/workflow`. In recent Codex sessions most shell execution goes through the `exec_command` function_call tool rather than native `exec_command_end` events.

---

## Thread Goals

Codex supports `/goal` slash commands that set a per-thread objective and optional token budget in `~/.codex/goals_1.sqlite`. Most sessions have no goal set.

```bash
reveal 'codex://019e5cc5?goal'
# Codex Goal: 019e5cc5
#
#   Objective:  Refactor the authentication module
#   Status:     active
#   Tokens:     12,500 / 50,000 (25%)
#   Time used:  300s
```

Status values: `active`, `paused`, `blocked`, `usage_limited`, `budget_limited`, `complete`.

When no goal is set: `Codex Goal: (none set for 019e5cc5)`.

---

## Memory Pipeline

Codex runs a background memory consolidation process. Stage 1 extracts memory-relevant items from eligible sessions; Stage 2 consolidates them into `~/.codex/memories/MEMORY.md`. The `memories/pipeline` route shows the current status:

```bash
reveal 'codex://memories/pipeline'
# Codex Memory Pipeline
#
#   Stage 1 outputs:      47
#   Selected for Stage 2:  8
#
#   Recent Stage 1 outputs (up to 20):
#     [✓] 019d9da3  my-session-slug       uses=3
#     [ ] 019d9dd4  other-session-slug    uses=0
```

`[✓]` marks entries selected for Stage 2 consolidation. `uses` counts how many times the memory was cited in a session. `memories/pipeline` reads from `state_5.sqlite`'s `stage1_outputs` table — the same DB as the session index.

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
├── state_5.sqlite        ← session index + stage1_outputs (primary lookup)
├── goals_1.sqlite        ← per-thread objectives + token budgets
├── sessions/
│   └── 2026/05/25/
│       └── rollout-*.jsonl   ← per-session event stream
├── history.jsonl         ← prompt history
├── config.toml           ← user config (secrets masked by reveal)
├── memories/             ← MEMORY.md + session summaries (Stage 2 output)
└── rules/                ← Starlark permission rules
```

---

## Differences from claude://

| Dimension | codex:// | claude:// |
|-----------|----------|-----------|
| Session ID | UUID (7+ hex prefix works) | Named slug (`amber-fire-0425`) |
| Primary index | SQLite `threads` table | Filesystem scan |
| Tool calls | `function_call`/`function_call_output` (JSONL events) | `tool_use`/`tool_result` (message blocks) |
| Shell execution | Dedicated `exec_command_end` events OR `exec_command` tool | Bash tool call in tool_use |
| Reasoning | `encrypted_content` — count only | `thinking` blocks — readable |
| Token data | Per-request via `token_count` events | Estimated from char count |
| Goals | `goals_1.sqlite` thread_goals | None |
| Memory pipeline | `stage1_outputs` → `memories/` | None |
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
