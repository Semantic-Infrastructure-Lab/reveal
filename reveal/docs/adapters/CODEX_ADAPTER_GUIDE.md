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
- Session listing and metadata filtering via SQLite (fast — no JSONL scanning)
- Full-text content search across all session JSONL files, scoped by `?since`/`?until`
- Composed digest view (overview + prompts + agent narrative) and prompt/reply exchange pairs
- Single raw-record access by index (`/message/<n>`, negative indexing supported)
- Chronological workflow view — tool calls + shell commands interleaved by timestamp
- Full event timeline — every JSONL event type in session order
- Per-turn token breakdown (input/output/cached/reasoning split)
- Shell command tracking with exit codes, output, and duration
- Tool call pairing (`function_call` + `function_call_output`)
- Thread goal tracking (`goals_1.sqlite`) — objective, status, token budget
- Memory pipeline status — Stage1/Stage2 consolidation from `stage1_outputs`
- Install introspection (config with `?key=` drill-down, history, memories, rules, skills, plugins)

---

## Quick Start

```bash
# List recent sessions
reveal 'codex://'

# Find sessions by title/first-message (SQLite metadata, fast)
reveal 'codex://sessions/?filter=auth-refactor'

# Full-text search across all session content
reveal 'codex://sessions/?search=authentication'

# Full-text search scoped to a date range
reveal 'codex://sessions/?search=authentication&since=2026-07-01'

# Session overview (turns, tools, tokens, duration)
reveal 'codex://019e5cc5'

# Composed readable view: overview + prompts + agent narrative in one call
reveal 'codex://019e5cc5/digest'

# Each user prompt paired with the agent's next reply
reveal 'codex://019e5cc5/exchanges'

# Last agent message — fastest session recovery
reveal 'codex://019e5cc5?last'

# Single raw JSONL record by index (negative indexing supported)
reveal 'codex://019e5cc5/message/-1'

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

# Config value by dot-path (applied after secret masking)
reveal 'codex://config?key=model'

# Installed skills and plugins
reveal 'codex://skills'
reveal 'codex://plugins'

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
| `codex://sessions/?filter=<term>` | Filter by title or first message (SQLite metadata, fast, no JSONL scan) |
| `codex://sessions/?search=<term>` | Full-text JSONL search across all sessions |
| `codex://sessions/?search=<term>&since=<date>` | Full-text search scoped to sessions updated on/after `<date>` (ISO 8601 or `today`) |
| `codex://sessions/?search=<term>&since=<date>&until=<date>` | Full-text search scoped to a date range |
| `codex://sessions/?search=<term>&matches=<n>` | Snippets kept per session (default 3, `0` keeps all); a cut is reported as a truncation naming `?matches=N` |
| `codex://sessions/?filter=<term>&since=<date>&until=<date>` | Metadata filter, same date scoping |

> **Renamed**: `?search=` used to mean the SQLite metadata match and `?content=` the full-text scan. They're now `?filter=` (metadata) and `?search=` (content) — matching `claude://`'s established meaning, where `?search=` always means "search the content." The old names are not aliased; using them surfaces via reveal's unknown-query-param warning.

### Session Analysis

| URI | What it returns |
|-----|----------------|
| `codex://<UUID>` | Overview: turns, tool calls, tokens, duration, git state |
| `codex://<UUID>?last` | Last agent message only — fast recovery pattern |
| `codex://<UUID>?tokens` | Per-turn token breakdown (input/output/cached/reasoning) |
| `codex://<UUID>?goal` | Thread goal from `goals_1.sqlite` (objective, status, token budget) |
| `codex://<UUID>/messages` | All user and agent turns in order |
| `codex://<UUID>/digest` | Composed readable view: overview + prompts + agent narrative in one call |
| `codex://<UUID>/exchanges` | Each user prompt paired with the agent's final reply before the next prompt |
| `codex://<UUID>/message/<n>` | Single raw JSONL record by 0-based index (negative indexing supported, e.g. `-1` = last) |
| `codex://<UUID>/tools` | Paired `function_call` + `function_call_output` events |
| `codex://<UUID>/shell` | `exec_command_end` events: command, exit code, output |
| `codex://<UUID>/errors` | Error, warning, and guardian_warning events |
| `codex://<UUID>/workflow` | Tool calls + shell commands interleaved chronologically |
| `codex://<UUID>/timeline` | All events in session order with brief summaries |

**UUID prefix**: A unique prefix of 7+ hex characters works instead of the full UUID: `reveal 'codex://019e5cc5'` resolves to the matching session. A prefix several sessions share exits 1 with `Ambiguous session prefix ...: matches <ids>; use more characters`; the first UUID group (8 characters) is usually enough.

**`/digest` vs `/exchanges` vs `/messages`**: `/digest` composes a whole-session readable summary in one call (start here for "what happened in this session"); `/exchanges` pairs each prompt with its final answer (for "what did I ask, what did it finally say," one pair at a time); `/messages` is the flat chronological list of every user/agent turn with no pairing or composition.

### Install Introspection

| URI | What it returns |
|-----|----------------|
| `codex://info` | Resolved paths, DB exists/size, session count |
| `codex://history` | `~/.codex/history.jsonl` prompt history |
| `codex://config` | `~/.codex/config.toml` with secrets masked |
| `codex://config?key=<dotpath>` | A single config value by dot-path, e.g. `?key=model` — applied *after* secret masking, so a masked value can never be un-redacted this way |
| `codex://memories` | `~/.codex/memories/` MEMORY.md and summaries |
| `codex://memories/pipeline` | Stage1/Stage2 memory consolidation pipeline status |
| `codex://rules` | `~/.codex/rules/*.rules` Starlark permission rules |
| `codex://skills` | `~/.codex/skills/**/SKILL.md` — list of installed skill definitions |
| `codex://skills/<name>` | A single skill's frontmatter + full content |
| `codex://plugins` | Installed plugin manifests under `~/.codex/plugins/cache/**/.codex-plugin/plugin.json` |
| `codex://plugins/<name>` | A single plugin's manifest |

---

## Workflow

`/workflow` interleaves tool calls and shell commands in chronological order — the same sequence the agent executed them. Use this when you want to understand what the session actually did and in what order.

```bash
reveal 'codex://01a161bb/workflow'
# Codex Workflow: 216 action(s)
#
#   ...
#
#   [✓] tool  exec(text(await tools.exec_command({cmd:"git status --short")  [2026-10-22T03:51:31]
#       → Script completed Wall time 6.4 seconds Output: {"chunk_id":"fec210","wall_time_seconds":6.163628376,
#
#   [✓] shell $ git status --short  [2026-10-22T03:51:37]
#       → exit=0 6163ms
```

Two event kinds appear (JSON `kind`: `tool_call`, `shell`; text: `tool`, `shell`):
- **tool** — a `function_call`/`function_call_output` pair; `[✓]` if an output was paired, `[✗]` if not. The arguments and the output preview are each cut to one line.
- **shell** — an `exec_command_end` event; `[✓]` if `exit_code == 0`. The second line is `→ exit=N <ms>ms` (the duration is left out when the rollout records none).

Current Codex rollouts record both: the `exec`/`exec_command` tool call and an `exec_command_end` event for each command it ran, so one command usually shows as a `tool` row followed by a `shell` row. Rollouts without `exec_command_end` show only the tool row.

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
- `session_meta` — session ID, cwd, CLI version, model provider, git state (no model, so its summary reads `model=?`; the model is in `turn_context`)
- `turn_context` — model, sandbox policy, approval mode (per-turn)
- `event_msg/user_message` / `event_msg/agent_message` — conversation turns
- `response_item/function_call` / `response_item/function_call_output` — tool execution
- `event_msg/exec_command_end` — native shell execution (sandbox mode)
- `event_msg/token_count` — running token totals after each API call
- `event_msg/task_complete` — turn duration and token summary
- `response_item/reasoning` — reasoning steps (content encrypted — count only)
- `event_msg/item_completed` — a completed conversation item (often the commonest payload type in current rollouts)
- `event_msg/task_started` / `event_msg/thread_settings_applied` — turn start and per-thread settings
- `world_state` — the session environment (instructions, environments, skills) as `state`; `full` is true for a complete snapshot, false for a partial update

Current rollouts can also carry `token_usage_record`, `inter_agent_communication_metadata` and `response_item/agent_message` records; the timeline lists every record whatever its type.

---

## Token Analysis

Codex emits `token_count` events after each API request with a delta (`last_token_usage`) and running total (`total_token_usage`). The `?tokens` route gives the per-request breakdown: one row per `token_count` event (one model API call), so its "turn" count is far higher than the overview's user/agent turn count:

```bash
reveal 'codex://01a161bb?tokens'
# Codex Token Usage: 131 turn(s)  |  running total: 19,055,254
#
#   TURN  TIMESTAMP               INPUT   CACHED   OUTPUT   REASON    TOTAL
#   ----- -------------------- -------- -------- -------- -------- --------
#   1     2026-10-22 03:51:16    17,698   12,032       81        0   17,779
#   2     2026-10-22 03:51:23    17,837   17,664       40        0   17,877
#   ...
```

JSON: `token_turns[]` (`turn`, `timestamp`, `input_tokens`, `cached_input_tokens`, `cache_write_input_tokens`, `output_tokens`, `reasoning_output_tokens`, `total_tokens`), `total_turns` and `grand_total`.

Fields:
- **INPUT**: prompt tokens (includes context)
- **CACHED**: prompt tokens served from the API cache (no cost)
- **OUTPUT**: completion tokens generated
- **REASON**: reasoning tokens, a subset of OUTPUT
- **TOTAL**: INPUT + OUTPUT (not INPUT + CACHED + OUTPUT)

---

## Shell Commands

`/shell` lists every shell command a session ran, with exit code, duration and output. Codex records them in one of three ways, and `/shell` (and the overview's "shell commands run") reads whichever the rollout has: `exec_command_end` events, `CommandExecution` items in current rollouts, or, in rollouts with neither, the `exec_command` tool calls themselves — the exit code and wall time are parsed from each call's output (`Process exited with code N`), and a command still running when the call returned takes the exit code of its later `write_stdin` poll. A command that never reported one shows "no exit code reported" or "aborted, no exit code".

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

An `exec` tool call is a script that can run several commands. Rollouts without per-command records don't list those one by one, so the result says how many `exec` scripts it could not break down (`unrecorded_commands` warning) and the shell count is a floor; the scripts and their combined output are in `/tools`.

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

Without a budget the line reads `Tokens: N (no budget)`. When no goal is set: `Codex Goal: (none set for 019e5cc5)`.

---

## Memory Pipeline

Codex runs a background memory consolidation process. Stage 1 extracts memory-relevant items from eligible sessions; Stage 2 consolidates them into `~/.codex/memories/MEMORY.md`. The `memories/pipeline` route shows the current status:

```bash
reveal 'codex://memories/pipeline'
# Codex Memory Pipeline
#
#   Stage 1 outputs:     3
#   Selected for Stage 2: 1
#
#   Recent Stage 1 outputs (up to 20):
#     [✓] 019d9da3  my-session-slug  uses=3
#     [ ] 019d9dd4  other-session-slug  uses=0
#     [ ] 019d9e10  third-session-slug  uses=1
```

The sample is rendered by the real adapter from a hand-built `memories_1.sqlite` holding the columns the adapter reads (`thread_id`, `rollout_slug`, `generated_at`, `selected_for_phase2`, `usage_count`, `last_usage`, `source_updated_at`); the ids and slugs are invented.

`[✓]` marks entries selected for Stage 2 consolidation. `uses` counts how many times the memory was cited in a session. `memories/pipeline` reads the `stage1_outputs` table from `memories_1.sqlite`, where current Codex keeps it, or from `state_5.sqlite` (the session index) on installs that predate that file.

---

## Content Search

`?search=<term>` scans all session JSONL files for a term in `user_message` and `agent_message` payloads:

```bash
reveal 'codex://sessions/?search=authentication'
# Codex Content Search: 3 session(s) matching 'authentication'
#
#   019e5cc5  2026-05-25  [gpt-5.5]  lets find all past sessions...
#     [USER] 2026-05-25 01:35:58  help me understand the authentication flow...
#     [AGENT] 2026-05-25 01:36:01  I'll look at the auth middleware first...
```

This is a full-file scan — use `?filter=` first for fast SQLite metadata filtering, or add `&since=<date>` (optionally `&until=<date>`) to narrow the corpus before scanning:

```bash
reveal 'codex://sessions/?search=authentication&since=2026-07-01'
```

---

## Storage Layout

```
~/.codex/
├── state_5.sqlite        ← session index (threads; primary lookup)
├── memories_1.sqlite     ← stage1_outputs (memory pipeline; older installs kept it in state_5.sqlite)
├── goals_1.sqlite        ← per-thread objectives + token budgets
├── sessions/
│   └── 2026/05/25/
│       └── rollout-*.jsonl   ← per-session event stream
├── history.jsonl         ← prompt history
├── config.toml           ← user config (secrets masked by reveal)
├── memories/             ← MEMORY.md + session summaries (Stage 2 output)
├── rules/                ← Starlark permission rules
├── skills/               ← SKILL.md per skill, recursive (e.g. skills/.system/<name>/SKILL.md)
└── plugins/cache/        ← installed plugin manifests (**/.codex-plugin/plugin.json)
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
| Token data | Per-request via `token_count` events | Per-message API usage records (thinking tokens estimated) |
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
