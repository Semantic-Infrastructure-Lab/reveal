---
title: Claude Adapter Guide (claude://)
category: guide
---
# Claude Adapter Guide (claude://)

**Last Updated**: 2026-07-09
**Version**: 1.1
**Adapter Version**: reveal 0.68.0+

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Core Features](#core-features)
4. [Elements Reference](#elements-reference)
5. [Query Parameters](#query-parameters)
6. [Progressive Disclosure Pattern](#progressive-disclosure-pattern)
7. [Tool Usage Analytics](#tool-usage-analytics)
8. [File Operation Tracking](#file-operation-tracking)
9. [Workflow Visualization](#workflow-visualization)
10. [Error Detection](#error-detection)
11. [Token Analysis](#token-analysis)
12. [Detailed Workflows](#detailed-workflows)
13. [Performance Considerations](#performance-considerations)
14. [Limitations](#limitations)
15. [Error Messages](#error-messages)
16. [Tips & Best Practices](#tips--best-practices)
17. [Integration Examples](#integration-examples)
18. [Install Introspection Resources](#install-introspection-resources)
19. [Related Documentation](#related-documentation)
20. [FAQ](#faq)

---

## Overview

The **claude://** adapter provides two families of resources: **session analysis** for inspecting individual Claude Code conversations, and **install introspection** for exploring your Claude Code installation (history, settings, plans, config, memory, agents, hooks).

**Session Analysis** (`claude://<session-name>[/element][?params]`):
- Post-session review and analysis
- Debugging failed or problematic sessions
- Understanding tool usage patterns and success rates
- Tracking file operations (Read/Write/Edit)
- Identifying errors with full context
- Optimizing token usage
- Analyzing agent workflows
- Extracting thinking blocks for analysis

**Install Introspection** (`claude://<resource>`):
- `claude://info` — diagnostic map of all Claude Code data locations
- `claude://history` — searchable prompt history across all sessions
- `claude://settings` — current user settings (`~/.claude/settings.json`)
- `claude://plans` — list and read saved plans
- `claude://config` — per-install config flags and MCP server registrations
- `claude://memory` — memory files across all projects
- `claude://agents` — registered agent definitions
- `claude://hooks` — hook scripts by event type

**Key Capabilities**:
- Session overview with message counts, tool usage, duration
- Tool usage analytics with success rates (including Agent tool telemetry)
- File operation tracking (Read/Write/Edit/Glob/Grep operations)
- Chronological workflow visualization
- Error detection with full context
- Thinking block extraction and token estimates
- Token breakdown by turn (`?tokens`)
- Agent tool call tracking (`/agents` sub-route)
- Context change tracking (directory, branch changes)
- Composite query support (filter by tool, errors, and tool-result text)

**Design Philosophy**:
- **Progressive disclosure**: Start with overview, drill down as needed
- **Token-efficient**: Avoid loading full conversations unless necessary
- **Composable queries**: Combine filters for precise analysis
- **Actionable facts**: Tool success rates, error context (the failing call's input and the thinking before it), message and token counts

---

## Quick Start

### 1. Session Overview

Get high-level session summary (messages, tools, duration):

```bash
reveal claude://session/infernal-earth-0118
```

> `infernal-earth-0118` is a placeholder session name. Your actual session directories are most likely UUIDs (e.g. `reveal claude://session/2627362f-6f72-45e1-b7bb-d5a61519a388`, or the 8-character short form `reveal claude://session/2627362f`) unless you use a friendly-naming layer. See [Error: "Conversation not found"](#error-conversation-not-found-for-session) for the accepted formats.

**Returns**: Session title, message counts, duration, files touched, tool counts, token totals and cache-hit rate, cwd/branch, last assistant snippet, conversation file path

`message_count` is the number of JSONL records (it includes tool results and metadata records). The role counts are messages: `user_messages` is the typed prompts, `tool_result_messages` the tool-result turns (also role `user` in the file), and `assistant_messages` the API messages (the records of one reply share a `message.id` and count once). `readme_present` appears (as `true`) only when a `README*.md` sits beside the transcript, a layout a stock `~/.claude/projects` install does not have; without one the field is omitted, not reported as absent. The session list and cross-session search follow the same rule.

### 2. Session Summary

Get the overview plus per-tool success rates and message sizes:

```bash
reveal 'claude://session/infernal-earth-0118?summary'
```

**Returns**: Overview plus per-tool success rates, average/max message size and thinking-block count

### 3. Tool Usage Analysis

Get all tool usage with success rates:

```bash
reveal claude://session/infernal-earth-0118/tools
```

**Returns**: Tool usage counts, success rates, common operations

### 4. File Operations

Track all files read, written, or edited:

```bash
reveal claude://session/infernal-earth-0118/files
```

**Returns**: File paths, operation types (Read/Write/Edit), access counts

### 5. Workflow Visualization

See chronological sequence of tool operations:

```bash
reveal claude://session/infernal-earth-0118/workflow
```

**Returns**: Time-ordered tool calls with parameters and results

### 6. Error Detection

Find all errors with context:

```bash
reveal 'claude://session/infernal-earth-0118?errors'
```

**Returns**: Error messages, message IDs, surrounding context

### 7. Thinking Block Analysis

Extract all thinking blocks:

```bash
reveal claude://session/infernal-earth-0118/thinking
```

**Returns**: All thinking blocks with token estimates and analysis

### 8. Filter by Tool

Show only specific tool usage:

```bash
reveal 'claude://session/infernal-earth-0118?tools=Bash'
reveal 'claude://session/infernal-earth-0118?tools=Read'
```

**Returns**: Filtered messages/operations for specified tool

### 9. Read User Prompts (what the human asked)

See only the prompts the human typed — tool-result turns excluded:

```bash
reveal claude://session/infernal-earth-0118/prompts
```

**Returns**: Each human prompt in full, no tool-result noise. (Add `?raw` instead if you need to see tool-result turn boundaries too.)

### 10. Read Assistant Responses (the Findings)

See what the assistant said — narrative text turns only, tool-call-only turns skipped:

```bash
reveal claude://session/infernal-earth-0118/messages
```

**Returns**: Assistant narrative text per turn (add `?raw` for every raw record unfiltered — text, thinking, tool_use, tool_result all included)

To read the two together, one turn at a time, use the prompt/answer pairing or the composed digest:

```bash
reveal claude://session/infernal-earth-0118/exchanges   # each prompt next to the final text answer it got
reveal claude://session/infernal-earth-0118/digest      # overview + prompts + narrative in one call
```

**Returns**: `/exchanges` pairs each human prompt with the assistant's last text answer before the next prompt (thinking-only and tool-only turns skipped; add `?full` to lift the 600-character cut). `/digest` composes whole-session sections instead of joining prompt to answer.

### 11. Search Session Content

Find a term across all text, thinking blocks, tool inputs and tool results:

```bash
reveal 'claude://session/infernal-earth-0118?search=verify'
reveal 'claude://session/infernal-earth-0118?search=path traversal'
```

**Returns**: Matches with message index, role, block type, and excerpt

### 12. Prompt History

Browse recent prompts across all sessions:

```bash
reveal claude://history
reveal 'claude://history?search=deploy&since=2026-03-01'
```

**Returns**: Prompts newest-first (50 by default); consecutive entries are grouped under their project path

### 13. Saved Plans

List or read saved plans from `~/.claude/plans/`:

```bash
reveal claude://plans
reveal claude://plans/my-plan-name
```

**Returns**: Plan list with title/modified/size, or full plan content

### 14. Install Diagnostics

Check all Claude Code data locations in one shot:

```bash
reveal claude://info
```

**Returns**: Paths, item counts, and active environment overrides

---

## Core Features

### 1. Progressive Disclosure

Start with overview, drill down as needed:

```bash
# Level 1: Overview (token-efficient)
reveal claude://session/my-session

# Level 2: Specific analysis
reveal claude://session/my-session/tools      # Tool usage
reveal claude://session/my-session/files      # File operations
reveal claude://session/my-session/workflow   # Chronological flow

# Level 3: Deep analysis
reveal 'claude://session/my-session?errors'     # Error debugging
reveal claude://session/my-session/thinking   # Token analysis
reveal 'claude://session/my-session?tools=Bash' # Tool-specific
```

**Why**: Prevents loading full conversations unnecessarily, saves tokens

---

### 2. Tool Usage Analytics

Track and analyze tool usage patterns:

**Metrics provided**:
- **Tool counts**: How many times each tool was called
- **Success rates**: Percentage of successful tool calls
- **Common operations**: Most frequent operations per tool
- **Tool pairs**: Which tools are commonly used together

**Example output** (actual field names — `tools` is an object keyed by tool name, not an array, and there is no top-level `overall_success_rate`):
```json
{
  "type": "claude_tool_summary",
  "session": "infernal-earth-0118",
  "total_calls": 23,
  "tools": {
    "Read": {
      "count": 15,
      "success_rate": "93.3%",
      "success": 14,
      "failure": 1
    },
    "Bash": {
      "count": 8,
      "success_rate": "87.5%",
      "success": 7,
      "failure": 1
    }
  }
}
```
To get a per-tool success rate below a threshold: `jq '.tools | to_entries[] | select(.value.success_rate | rtrimstr("%") | tonumber < 80)'`.

**Use cases**:
- Identify unreliable tools (low success rates)
- Find frequently used operations (optimization targets)
- Understand agent behavior patterns
- Debug tool failures

---

### 3. File Operation Tracking

Track all file access patterns:

**Operations tracked**:
- **Read**: Files inspected during session
- **Write**: Files created from scratch
- **Edit**: Files modified (existing content changed)

**Metrics provided**:
- File paths and operation types
- Access frequency (how many times each file was touched)
- Operation distribution (Read vs Write vs Edit)

**Example output** (actual shape — `operations` is a flat list of events with `file_path`, and per-file counts live under `by_operation`, not a `files`/`summary` array):
```json
{
  "type": "claude_files",
  "session": "infernal-earth-0118",
  "total_operations": 4,
  "unique_files": 2,
  "by_operation": {
    "Read": {"/home/user/project/src/main.py": 2},
    "Write": {"/home/user/project/tests/test_main.py": 1},
    "Edit": {"/home/user/project/src/main.py": 1},
    "Glob": {},
    "Grep": {}
  },
  "operations": [
    {"message_index": 47, "operation": "Read", "file_path": "/home/user/project/src/main.py", "timestamp": "2026-02-12T11:21:27Z"}
  ]
}
```

**Use cases**:
- Track what files were touched during debugging
- Identify hotspots (frequently modified files)
- Verify expected file operations occurred
- Document changes for review

---

### 4. Workflow Visualization

Chronological sequence of tool operations:

**What it shows**:
- Time-ordered tool calls (first to last)
- Tool names and parameters
- Results (success/failure)
- Execution flow patterns

**Example output**:
```json
{
  "type": "claude_workflow",
  "session": "infernal-earth-0118",
  "total_steps": 40,
  "collapsed_steps": 36,
  "displayed_steps": 36,
  "workflow": [
    {"step": 1, "message_index": 7, "tool": "Bash", "detail": "Run test suite",
     "timestamp": "2026-01-18T10:15:23", "outcome": "success"},
    {"step": 2, "message_index": 9, "tool": "Edit", "detail": "/path/to/file.py",
     "timestamp": "2026-01-18T10:16:45", "outcome": "success"}
  ]
}
```

`detail` is the Bash description or the file path, not the full tool parameters. Consecutive identical steps are collapsed (text output shows `(×2)`).

**Use cases**:
- Understand sequence of operations
- Identify where session went wrong
- Analyze problem-solving patterns
- Document agent workflow for optimization

---

### 5. Error Detection

Find errors with full context:

**How a tool result is classified** (`error_type`, in priority order — the same rules give `/tools` its success rates):
- `return_code`: the client's `returnCodeInterpretation` is `error` (Bash). When it says `success`, the result is not an error.
- `is_error_flag`: the `tool_result` carries `is_error: true`.
- `exit_code`: "exit code N" (N > 0) in the output.
- `pattern_match`: a line starting with `Traceback`, `Error:`, `fatal:`, `panic:` or `exception` — a command that exited 0 but printed an error.

The last two read command output only. They are not applied to tools whose result is file, web or agent text (`Read`, `Edit`, `Write`, `Grep`, `Glob`, `WebFetch`, `WebSearch`, `Agent`/`Task`, ...), where they matched the contents of a file instead.

**Example output**:
```json
{
  "type": "claude_errors",
  "session": "infernal-earth-0118",
  "error_count": 1,
  "errors": [
    {
      "message_index": 67,
      "tool_use_id": "toolu_01...",
      "error_type": "is_error_flag",
      "content_preview": "Exit code 1\nFAILED tests/test_auth.py::test_login",
      "timestamp": "2026-01-18T10:22:31.000Z",
      "context": {"...": "the tool call and surrounding messages"}
    }
  ]
}
```

**Use cases**:
- Debug failed sessions
- Identify recurring errors
- Find root causes of failures
- Optimize error handling patterns

---

### 6. Thinking Block Extraction

Extract and analyze all thinking blocks:

**What it provides**:
- All thinking blocks from session
- Token estimates (chars / 4)
- Counts of blocks and of blocks whose text was not stored

**Example output**:
```json
{
  "type": "claude_thinking",
  "session": "infernal-earth-0118",
  "thinking_block_count": 25,
  "blocks_without_text": 24,
  "total_chars": 187,
  "total_tokens_estimate": 46,
  "blocks": [
    {"message_index": 12, "content": "Let me analyze this error...", "char_count": 624,
     "token_estimate": 156, "timestamp": "2026-01-18T10:15:40"}
  ]
}
```

**Use cases**:
- Understand agent reasoning process
- Spot long thinking blocks by size
- Debug reasoning failures

---

### 7. Context Change Tracking

Track directory and branch changes during session:

**What it tracks**: the `cwd` and `gitBranch` fields Claude Code writes on each record. An entry is emitted whenever either value differs from the previous record (the first record always counts). It does not parse `cd` or `git checkout` commands.

**Example output**:
```json
{
  "type": "claude_context",
  "session": "infernal-earth-0118",
  "total_changes": 2,
  "final_cwd": "/home/user/project/tests",
  "final_branch": "feature/new-api",
  "changes": [
    {"message_index": 5, "type": "cwd", "value": "/home/user/project", "timestamp": "2026-01-18T10:00:01"},
    {"message_index": 45, "type": "branch", "value": "feature/new-api", "timestamp": "2026-01-18T10:30:12"}
  ]
}
```

**Use cases**:
- Track context switches during debugging
- Understand agent navigation patterns
- Identify context confusion issues

---

### 8. Composite Queries

Combine filters for precise analysis:

```bash
# Bash tool usage + errors only
reveal 'claude://session/my-session?tools=Bash&errors'

# Assistant narrative turns containing specific text
reveal 'claude://session/my-session/messages?contains=reveal'

# Error list (the summary already carries per-tool failure counts)
reveal 'claude://session/my-session?errors'
```

**Supported combinations**:
- `?tools=<tool>&errors` - Specific tool failures
- `/messages?contains=<text>` - Narrative-turn text search (see `?search=<term>` below for a whole-session, all-roles equivalent)
- `?tools=<tool>&contains=<text>` - Results of that tool whose output contains the text (tool inputs are not searched; use `?search=` for those)

`?summary&errors` is not a combination: `errors` is ignored and the answer is the plain `?summary`.

---

## Elements Reference

The claude:// adapter supports fifteen elements for progressive disclosure:

### 1. workflow

**Description**: Chronological sequence of tool operations

**Syntax**:
```bash
reveal 'claude://session/<session-name>/workflow'
```

**Example**:
```bash
reveal claude://session/infernal-earth-0118/workflow
```

**Output**: Time-ordered tool calls with parameters, results, and execution flow. Each step's `outcome` is `success`, `error`, or `pending` — `pending` marks a background launch (e.g. an async `Agent` call, `toolUseResult.status: 'async_launched'`) that hasn't reported back yet; its `backgrounded` flag is also set. Renders as `⏳` (pending) or `✗` (error) in text output, `[bg]` appended when backgrounded. Before this was fixed, every successfully-launched background agent showed a permanent `✗` — the completion arrives later as a separate message, never as a re-derivation of this step.

**Use when**: Need to understand sequence of operations, debug workflow issues, check on in-flight background agents

---

### 2. files

**Description**: All files read, written, or edited during session

**Syntax**:
```bash
reveal 'claude://session/<session-name>/files'
```

**Example**:
```bash
reveal claude://session/infernal-earth-0118/files
```

**Output**: File paths, operation types (Read/Write/Edit), access counts, summary metrics

**Use when**: Track file modifications, identify hotspots, verify expected operations

---

### 3. tools

**Description**: Tool usage analytics with success rates

**Syntax**:
```bash
reveal 'claude://session/<session-name>/tools'
```

**Example**:
```bash
reveal claude://session/infernal-earth-0118/tools
```

**Output**: Tool counts, success rates, common operations, overall success rate

**Use when**: Analyze tool usage patterns, identify unreliable tools, optimize operations

---

### 4. thinking

**Description**: All thinking blocks with token estimates

**Syntax**:
```bash
reveal 'claude://session/<session-name>/thinking'
```

**Example**:
```bash
reveal claude://session/infernal-earth-0118/thinking
```

**Output**: Thinking block content and token estimates (chars / 4). Recent models store most thinking blocks with a signature but no text; `blocks_without_text` counts them and the header says how many were not shown.

**Use when**: Understand agent reasoning, identify token waste, optimize thinking patterns

---

### 5. errors

**Description**: All errors and exceptions with full context

**Syntax**:
```bash
reveal 'claude://session/<session-name>/errors'
```

**Example**:
```bash
reveal claude://session/infernal-earth-0118/errors
```

**Output**: Error messages, message IDs, tool names, surrounding context

**Use when**: Debug session failures, identify recurring errors, find root causes

---

### 6. timeline

**Description**: Chronological message timeline

**Syntax**:
```bash
reveal 'claude://session/<session-name>/timeline'
```

**Example**:
```bash
reveal claude://session/infernal-earth-0118/timeline
```

**Output**: Events in order, each with an index and timestamp: `user_message` (typed prompts, as the `/prompts` view defines them, whether stored as a plain string or a block list), `assistant_message`, `thinking`, `tool_call` and `tool_result`, each with a short content preview

**Use when**: Understand conversation flow, identify timing patterns

---

### 7. context

**Description**: Working-directory and git-branch changes over the session (read from the `cwd` and `gitBranch` fields Claude Code writes on each record)

**Syntax**:
```bash
reveal 'claude://session/<session-name>/context'
```

**Example**:
```bash
reveal claude://session/infernal-earth-0118/context
```

**Output**: Each point where the working directory or the git branch differs from the previous record (the first record always counts), with `message_index`, `type` (`cwd` or `branch`), `value` and `timestamp`, plus `final_cwd` and `final_branch`

**Use when**: Track context switches, debug navigation issues, understand agent context management

---

### 8. prompts

**Description**: Human-typed prompts only — messages that contain at least one `text` block. Pure tool-result wrapper messages are excluded.

**Syntax**:
```bash
reveal 'claude://session/<session-name>/prompts'
```

**Example**:
```bash
reveal claude://session/infernal-earth-0118/prompts
```

**Output**: Each human prompt with timestamp and full text (first prompt up to 1200 chars, rest up to 300). No `[N tool result(s)]` noise, and no harness-injected text — synthetic system content (async Agent-tool `<task-notification>` completions, bash-mode `!command` wrappers like `<local-command-caveat>`/`<command-name>`/`<local-command-stdout>`) is excluded, not just tool-result turns.

**Use when**: You want to read *what the human asked* without wading through tool-result turns or harness noise. This is the resource to reach for when reviewing intent. The Claude API encodes tool-result turns as `role: user`, so a naive raw dump mixes them in with real prompts — a session with ~15 prompts can show ~170 raw "user" records. `/prompts` filters those out (see `?raw` below if you need the raw dump anyway).

**`?raw`**: add `?raw` to get every raw role=user record unfiltered instead — prompts, tool-result turns, and harness-injected text all included, normalized to a block list. This is a bulk forensic scan (e.g. skimming every tool-result payload in a session at once), not narrative reading; prefer plain `/prompts` unless you specifically need that. Response includes a `hint` field when tool-result-only turns are present, pointing back at plain `/prompts`.

```bash
reveal 'claude://session/<session-name>/prompts?raw'
```

---

### 9. messages

**Description**: Assistant narrative text turns only — what the assistant *said* (explanations, summaries, decisions), not tool-call records. Skips turns that produced only `tool_use`/`tool_result`/`thinking` blocks with no text.

**Syntax**:
```bash
reveal 'claude://session/<session-name>/messages'
reveal 'claude://session/<session-name>/messages?raw'     # raw, unfiltered role=assistant dump
reveal 'claude://session/<session-name>/messages?raw&full'   # + disable 600-char truncation
```

**Example**:
```bash
reveal claude://session/infernal-earth-0118/messages
```

**Output**: Each narrative turn's text, with `turn`/`message_index`/`timestamp`/`char_count`. Text output cuts each turn at 600 characters (`--verbose` or `--max-snippet-chars N` lifts it; `?full` has no effect on plain `/messages`); JSON always carries the full text. This is the best resource for reading what the assistant concluded — lighter and cleaner than a raw dump because tool-call-only turns are skipped entirely rather than shown as one-line summaries.

**`?raw`**: add `?raw` to get every raw role=assistant record unfiltered instead — text, thinking, tool_use, and tool_result blocks all present for every turn, none skipped. This is a bulk forensic scan (e.g. reading every tool_use's exact arguments across a session at once, or every tool_result's exact output), not narrative reading; prefer plain `/messages` unless you specifically need that. Add `&full` to also disable the 600-char per-message truncation.

**Use when**: Read the actual findings or report, compare outputs between sessions, understand what the agent concluded (plain); inspect exact tool call arguments or tool output in bulk (`?raw`).

---

### 10. message/\<n\>

**Description**: Read a single message by index: text in full, tool_use name and key params (a Write's `content` is shown as a size only), tool_result first 500 chars (`--verbose` for all). Use `--format json` to see exactly what a Write or Edit sent

**Syntax**:
```bash
reveal 'claude://session/<session-name>/message/<index>'
reveal 'claude://session/<session-name>/message/-1'      # last raw record (may be a metadata record; use ?last for the last assistant turn)
```

**Example**:
```bash
reveal claude://session/infernal-earth-0118/message/334
reveal claude://session/infernal-earth-0118/message/-1
```

**Output**: Full message content. For `tool_use` blocks: shows name + key params (`file_path`, `command`, `content` size). For `tool_result` blocks: shows content preview (first 500 chars).

**Notes**:
- Index is 0-indexed over raw JSONL records (see [`/message` (range)](#11-message-range) below for the *other* indexing scheme this resource family uses)
- For `user`/`assistant` messages, the response includes a `turn` field — the 1-indexed conversation-turn number that `/message --range` uses, so you can go from a raw index straight to the range number without a second call

**Use when**: Read a long assistant response in full, inspect what a Write/Edit tool call actually wrote, read agent tool_result output, or find the `turn` number to jump into `/message --range`

---

### 11. message (range)

**Description**: Read a range of messages (both user and assistant, interleaved) using the standard `--range` flag

**Syntax**:
```bash
reveal 'claude://session/<session-name>/message' --range 10-20
reveal 'claude://session/<session-name>/message?full' --range 10-20
reveal 'claude://session/<session-name>/message' --range 300-    # open-ended: 300 to end
```

**Example**:
```bash
reveal claude://session/infernal-earth-0118/message --range 5-15
```

**Output**: Interleaved user + assistant turns with role, timestamp, and content. Default truncation at 600 chars; add `?full` or `--verbose` to disable. Each turn shows its raw `message_index` so you can drill in with `/message/N`. Tool-only assistant turns show one-line summaries (`Read → file.py`, `Bash → git status`).

**Notes**:
- Range is 1-indexed over conversation messages (user + assistant only; metadata records excluded)
- Raw `message_index` shown per turn for cross-reference with `/message/N` (which is 0-indexed over all raw records)
- Open-ended `--range 300-` supported: returns all messages from turn 300 to end
- `?full` and `--verbose` are equivalent — both disable the 600-char truncation

**Use when**: Navigate a specific region of a long conversation, review a troubleshooting exchange, inspect what happened between two known points

---

### 12. agents

**Description**: Agent tool calls made during the session with per-agent telemetry

**Syntax**:
```bash
reveal 'claude://session/<session-name>/agents'
```

**Example**:
```bash
reveal claude://session/infernal-earth-0118/agents
```

**Output**: Per-agent `agent_id`, `agent_type`, `status`, `prompt` (first 200 chars) and `timestamp`. `agent_type` is the result's `agentType`, else the `subagent_type` the call asked for (`unknown` when neither is recorded). Foreground (completed) agents add `duration_ms`, `token_count`, `tool_count` and `usage` (`input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_created_tokens`); background launches (`status: async_launched`) have none of these and do not count toward the session-level totals `total_agent_tokens` and `total_agent_duration_ms`.

**Use when**: Understand subagent cost, identify slow or expensive agent invocations, audit agent behavior within a session

---

### 13. chain

**Description**: Session continuation chain traversal — follows `continuing_from:` links in README frontmatter back through the session history

**Syntax**:
```bash
reveal 'claude://session/<session-name>/chain'
```

**Example**:
```bash
REVEAL_SESSIONS_DIR=~/projects/my-sessions reveal claude://session/revealed-sphinx-0407/chain
```

**Output**: Ordered list of sessions from HEAD back to the root, each showing `session`, `date`, `badge`, `continuing_from`, `tests_start`, `tests_end`, and `commits`. Chain length capped at 50 to prevent cycles.

**Notes**:
- Follows `continuing_from:` frontmatter in `README*.md` files (most recent README wins if multiple exist)
- Cycle detection prevents infinite loops
- Missing README → entry still included with `null` fields; `readme: null` shown in output
- Set `REVEAL_SESSIONS_DIR` so the adapter can locate sibling sessions (`--base-path` locates the transcript but does not feed the chain walk)

**Use when**: Understand a session's development lineage, audit what changed across a multi-session feature, verify test count progression over time

---

### 14. digest

**Description**: Composed readable view — session overview + human prompts + assistant narrative in one call. Exists so getting a clean picture of what happened doesn't take 3 separate calls (`?summary`, `/prompts`, `/messages`).

**Syntax**:
```bash
reveal 'claude://session/<session-name>/digest'
reveal 'claude://session/<session-name>?digest'   # query-param alias, same result
```

**Example**:
```bash
reveal claude://session/infernal-earth-0118/digest
```

**Output**: Title, duration, message/file counts, then every human prompt, then every assistant narrative turn — each with its `message_index` so you can drill in with `/message/N`.

**Use when**: This is the resource to reach for first when picking up a session cold — "what was asked, what happened, what did it find" in one shot. Drill into `/workflow`, `/tools`, `/thinking`, etc. only once the digest points at something specific.

---

### 15. exchanges

**Description**: Each real human prompt paired with the assistant's final text answer to it — skips `thinking`-only and tool-only turns in between, returning the last text block found before the next prompt. Distinct from `/digest`: `/digest` composes whole-session sections; `/exchanges` joins a specific prompt to its specific answer.

**Syntax**:
```bash
reveal 'claude://session/<session-name>/exchanges'
reveal 'claude://session/<session-name>/exchanges?full'   # disable 600-char truncation on answers
```

**Example**:
```bash
reveal claude://session/infernal-earth-0118/exchanges
```

**Output**: One entry per real prompt: `message_index`, `timestamp`, `prompt`, `answer_message_index`, `answer_timestamp`, `answer` (`null` if no assistant text was found before the next prompt or end of session — e.g. a purely tool-driven exchange).

**Notes**:
- Walks the JSONL `parentUuid` chain *backward* from the record the next prompt hangs off (or the session's last record). Every record has exactly one parent, so this follows the branch the conversation actually took; walking forward is ambiguous, since parallel tool calls give each `tool_use` record its own `tool_result` child and `type: progress` records fork side-chains off the same parent.
- A compaction boundary mid-turn re-roots the chain; the answer is then the last text found on the way back to the boundary. Only when that finds nothing does the walk fall back to following first (non-`progress`) children forward.
- A prompt is "real" if it has typed text (bare string, or a text block — e.g. a pasted screenshot with a caption) and is not a synthetic text block riding on a `tool_result` turn, a harness-injected wrapper (`<task-notification>`, `<command-name>`, `<bash-input>`/`<bash-stdout>`, local-command caveats), or a record the harness marks `isMeta` or `isCompactSummary` (matches `/prompts`' definition exactly).

**Use when**: You need "what did I ask, what did it finally say" for a specific turn or set of turns, without eyeballing timestamps between `/prompts` and `/messages` or binary-searching `/message/<n>` by hand.

---

## Query Parameters

### ?summary

**Description**: Overview plus per-tool success rates, message sizes and thinking-block count

**Syntax**:
```bash
reveal 'claude://session/<session-name>?summary'
```

**Example**:
```bash
reveal 'claude://session/infernal-earth-0118?summary'
```

**Output**: The overview fields plus `tool_success_rate` (per tool: success, failure, total, success_rate), `avg_message_size`, `max_message_size` and `thinking_blocks`. There is no timeline, event list or recommendation

**Use when**: Quick session understanding, post-session review

---

### ?digest

**Description**: Query-param alias for [`/digest`](#14-digest) — composed overview + prompts + assistant narrative in one call

**Syntax**:
```bash
reveal 'claude://session/<session-name>?digest'
```

**Example**:
```bash
reveal 'claude://session/infernal-earth-0118?digest'
```

**Output**: Same as `/digest` — see that section for full output shape.

**Use when**: Same as `/digest`; use whichever form (path or query param) fits your URI more naturally.

---

### ?tokens

**Description**: Token usage breakdown by turn — input, output, cache read/write tokens per assistant message

**Syntax**:
```bash
reveal 'claude://session/<session-name>?tokens'
```

**Example**:
```bash
reveal 'claude://session/infernal-earth-0118?tokens'
```

**Output**: One row per API message: `message_index`, `timestamp`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_created_tokens`, `cumulative_input`; `totals` adds `cache_hit_rate`

**Use when**: Audit token cost, identify expensive turns, compare sessions by cost

---

### ?patches

**Description**: JSON only: add each Edit's patch to the files-touched view

**Syntax**:
```bash
reveal 'claude://session/<session-name>/files?patches=true'
```

**Example**:
```bash
reveal 'claude://session/infernal-earth-0118/files?patches=true'
```

**Output**: Each `operations[]` entry gains `patch`, the Edit's structured hunks (`oldStart`, `oldLines`, `newStart`, `newLines`, `lines`); it is `null` for Read, Write and failed edits. The text view is unchanged

**Use when**: Review exactly what changed in a session's edits, not just which files

---

### ?errors

**Description**: Filter for messages containing errors

**Syntax**:
```bash
reveal 'claude://session/<session-name>?errors'
```

**Example**:
```bash
reveal 'claude://session/infernal-earth-0118?errors'
```

**Output**: Only messages with errors, error context, error summary

**Use when**: Debug failed sessions, focus on problems

---

### ?tools=<tool>

**Description**: Filter for specific tool usage

**Syntax**:
```bash
reveal 'claude://session/<session-name>?tools=<ToolName>'
```

**Examples**:
```bash
reveal 'claude://session/infernal-earth-0118?tools=Bash'
reveal 'claude://session/infernal-earth-0118?tools=Read'
reveal 'claude://session/infernal-earth-0118?tools=Edit'
```

**Output**: Only messages/operations involving specified tool

**Use when**: Analyze specific tool behavior, debug tool-specific issues

---

### ?search=\<term\>

**Description**: Case-insensitive search across all session content — text blocks, thinking blocks, tool inputs/descriptions and tool-result output

**Syntax**:
```bash
reveal 'claude://session/<session-name>?search=<term>'
```

**Examples**:
```bash
reveal 'claude://session/infernal-earth-0118?search=verify=False'
reveal 'claude://session/infernal-earth-0118?search=path traversal'
reveal 'claude://session/infernal-earth-0118?search=credential'
```

**Output**: Matching messages with role, block type (`text`, `thinking`, `tool_use:Bash`, `tool_result`), timestamp, and a 120-char excerpt centered on the match

**Use when**: Find where a specific topic was discussed, compare findings across sessions, locate the message containing a key conclusion

---

### ?contains=<text>

**Description**: A modifier, not a stand-alone filter. On `/messages` it filters narrative turns; combined with `tools=` or `errors` it filters tool-result content. On its own at the session root it is ignored (use `?search=<term>` for a whole-session search)

**Syntax**:
```bash
reveal 'claude://session/<session-name>?contains=<text>'
```

**Examples**:
```bash
reveal 'claude://session/infernal-earth-0118/messages?contains=reveal'
reveal 'claude://session/infernal-earth-0118?tools=Bash&contains=error'
reveal 'claude://session/infernal-earth-0118/messages?contains=import pandas'
```

**Output**: Case-insensitive match. On `/messages`, the narrative turns that contain the text; with `tools=`, the results of that tool whose output contains it (tool inputs are not searched)

**Use when**: Find specific topics, track keyword usage, search conversations

---

### ?raw

**Description**: On `/prompts` or `/messages`, return every raw role record unfiltered (text, thinking, tool_use, tool_result blocks all included) instead of the narrative-only extract. Replaces the old standalone `/user` and `/assistant` elements and the `?role=user|assistant` query param (both removed; a request for `/user`, `/assistant` or any other unknown element falls back to the session overview with rc 0 and no warning, and `?role=` is ignored with a warning) — `/prompts?raw` reaches full parity with `/user`'s old scope (every role=user record, tool-result wrapper turns included, not narrowed to real prompts); `/messages?raw` reaches parity with `/assistant`'s old scope.

**Syntax**:
```bash
reveal 'claude://session/<session-name>/prompts?raw'
reveal 'claude://session/<session-name>/messages?raw'
reveal 'claude://session/<session-name>/messages?raw&full'   # + disable 600-char truncation
```

**Examples**:
```bash
reveal 'claude://session/infernal-earth-0118/prompts?raw'
reveal 'claude://session/infernal-earth-0118/messages?raw'
```

**Output**: Every raw record for that role, normalized to a block list — nothing skipped, nothing filtered.

**Use when**: Bulk forensic scanning — e.g. skimming every tool-result payload or every tool_use's exact arguments across a whole session at once. For reading intent or findings, prefer plain `/prompts` and `/messages` — they're lighter and skip harness/tool noise.

---

### ?tail=N

**Description**: Show the last N assistant turns — fast session recovery ("where did it stop?")

**Syntax**:
```bash
reveal 'claude://session/<session-name>?tail=N'
```

**Examples**:
```bash
reveal 'claude://session/infernal-earth-0118?tail=3'
reveal 'claude://session/infernal-earth-0118?tail=1'
```

**Use when**: Resuming a session and only need the most recent turns, not the full history

---

### ?last

**Description**: Show the last assistant turn only — shorthand for `?tail=1`

**Syntax**:
```bash
reveal 'claude://session/<session-name>?last'
```

**Use when**: The fastest way to check "what did the assistant just say/do" — cheaper than a full session read

---

### Composite Queries

Combine multiple query parameters:

```bash
# Bash errors
reveal 'claude://session/my-session?tools=Bash&errors'

# Assistant narrative turns about reveal
reveal 'claude://session/my-session/messages?contains=reveal'

# Read operations with errors
reveal 'claude://session/my-session?tools=Read&errors'
```

---

## Progressive Disclosure Pattern

The claude:// adapter uses **progressive disclosure** to provide exactly the level of detail needed:

### Level 1: Overview (Token-Efficient)

**Command**:
```bash
reveal claude://session/my-session
```

**Token cost**: ~300-500 tokens

**Returns**:
- Session name
- Message count
- Tool call count
- Duration
- Tool summary (top tools with counts)

**Use when**: Initial session assessment, quick status check

---

### Level 2: Specific Analysis (Moderate Detail)

**Commands**:
```bash
reveal claude://session/my-session/tools      # Tool analytics
reveal claude://session/my-session/files      # File operations
reveal claude://session/my-session/workflow   # Operation sequence
```

**Token cost**: ~500-1000 tokens per element

**Returns**: Complete data for requested analysis type

**Use when**: Need specific aspect understanding

---

### Level 3: Filtered Analysis (Targeted Detail)

**Commands**:
```bash
reveal 'claude://session/my-session?errors'           # Only errors
reveal 'claude://session/my-session?tools=Bash'       # Only Bash usage
reveal 'claude://session/my-session?search=reveal'    # Text search (whole session)
```

**Token cost**: ~400-800 tokens (depends on filter match count)

**Returns**: Filtered messages/operations matching criteria

**Use when**: Debugging specific issues, targeted analysis

---

### Level 4: Deep Analysis (Comprehensive)

**Commands**:
```bash
reveal 'claude://session/my-session?summary'          # Full summary
reveal claude://session/my-session/thinking         # All thinking blocks
reveal 'claude://session/my-session?tools=Bash&errors' # Composite filter
```

**Token cost**: ~1000-2000 tokens

**Returns**: The facts each command prints (success rates, thinking blocks, Bash calls and errors); none of them adds insights or recommendations

**Use when**: Deep understanding needed, optimization analysis, comprehensive review

---

### Pattern Summary

```
Overview (300 tokens)
   ↓
Specific analysis (500 tokens)
   ↓
Filtered analysis (600 tokens)
   ↓
Deep analysis (1500 tokens)
```

**Rule**: Start shallow, drill down only when needed

---

## Tool Usage Analytics

### Success Rate Calculation

**Formula**:
```
Success Rate = (Successful Calls / Total Calls) × 100
```

**Determination**:
- **Success**: Tool result returned without error
- **Failure**: Tool result contains error or exception

**Example** (`/tools` JSON, one entry per tool under `tools`):
```json
{
  "Bash": {"count": 10, "success_rate": "80.0%", "success": 8, "failure": 2}
}
```

`success_rate` is a string with a `%` sign here; `?summary` reports `tool_success_rate.<Tool>` with `success`, `failure`, `total` and a numeric `success_rate`.

---

### Common Tool Patterns

reveal does not count repeated operations or pair tools. `/tools` lists each call in order, and its JSON `details.<Tool>[]` entries carry `message_index`, `tool_use_id`, `timestamp`, `detail` (the Bash description or the file path) and `caller_type`. Frequencies and patterns are for the reader or a script to derive from those lists, for example:

```bash
reveal claude://session/my-session/tools --format json | jq -r '.details.Bash[].detail' | sort | uniq -c | sort -rn
```

---

### Tool Success Rate Thresholds

| Success Rate | Status | Action |
|--------------|--------|--------|
| **90-100%** | Excellent | No action needed |
| **75-89%** | Good | Monitor for patterns |
| **50-74%** | Fair | Investigate failures |
| **< 50%** | Poor | Review usage patterns, consider alternatives |

---

### Tool Usage Insights

**High Read tool usage**: Might indicate:
- Heavy file inspection (normal for debugging)
- Repeated file reads (optimization opportunity)
- Missing context (agent re-reading same files)

**High Bash tool failures**: Might indicate:
- Command syntax issues
- Environment problems
- Permission issues

**High Edit tool failures**: Might indicate:
- Pattern matching issues (old_string not found)
- File conflicts (file changed between read and edit)
- Incorrect file paths

---

## File Operation Tracking

### Operation Types

**Read operations**:
- **Purpose**: Inspect file contents
- **Typical count**: High (5-20 reads per session)
- **Pattern**: Often repeated for same files

**Write operations**:
- **Purpose**: Create new files
- **Typical count**: Low (0-3 writes per session)
- **Pattern**: Concentrated during implementation

**Edit operations**:
- **Purpose**: Modify existing files
- **Typical count**: Moderate (2-8 edits per session)
- **Pattern**: Iterative refinement

---

### File Access Patterns

**Hotspot detection**:

`/files` JSON has `total_operations`, `unique_files`, `by_operation` (each operation, including empty `Glob` and `Grep`, mapped to the files it touched and how many times) and `operations[]` (`message_index`, `operation`, `file_path`, `timestamp`). reveal does not rank or flag files; count repeats from `operations[]`:

```bash
reveal claude://session/my-session/files --format json | jq -r '.operations[].file_path' | sort | uniq -c | sort -rn | head
```

**Interpreting repeats** (your judgement, not a reveal field):
- **Many accesses to one file**: Potential hotspot, consider why the file needs repeated access
- **Multiple edits**: Iterative refinement (normal) or indecision (review needed)
- **Read-only with a high count**: Reference file or missing information

---

### File Coverage Analysis

**Metrics**:
```json
{
  "summary": {
    "total_files": 15,
```json
{
  "total_operations": 31,
  "unique_files": 15,
  "by_operation": {"Read": {"a.py": 2, "b.py": 1}, "Edit": {"a.py": 1}, "Write": {"c.py": 1}, "Glob": {}, "Grep": {}}
}
```

There is no `summary` object; derive read-only, modified and created sets from `by_operation`.

**Interpretation**:
- **High read-only count**: Exploratory session, debugging, learning
- **High modified count**: Implementation session, bug fixing
- **High created count**: Feature development, scaffolding

---

## Workflow Visualization

### Operation Sequence Analysis

**Linear workflow** (typical):
```
Read → Edit → Bash (test) → Read (verify) → Edit (fix) → Bash (test) ✓
```

**Iterative workflow** (debugging):
```
Read → Bash (test) ✗ → Read → Edit → Bash (test) ✗ → Read → Edit → Bash (test) ✓
```

**Exploratory workflow** (investigation):
```
Read → Read → Read → Bash (check) → Read → Read → Bash (analyze)
```

---

### Workflow Patterns

**Pattern 1: Test-Driven Development**
```
Write (test) → Write (impl) → Bash (pytest) → Edit (fix) → Bash (pytest) ✓
```

**Pattern 2: Iterative Refinement**
```
Read → Edit → Bash (check) → Edit → Bash (check) → Edit → Bash (check) ✓
```

**Pattern 3: Debugging**
```
Bash (reproduce) → Read (investigate) → Edit (fix) → Bash (verify) ✓
```

**Pattern 4: Exploration**
```
Read → Read → Read → Bash (analyze) → Read → Write (summary)
```

---

### Workflow Insights

**Fast convergence** (3-5 steps):
- Clear understanding of problem
- Effective tool selection
- Minimal trial-and-error

**Slow convergence** (10+ steps):
- Unclear problem definition
- Repeated operations (optimization opportunity)
- Trial-and-error approach (consider planning first)

---

## Error Detection

### Error Types

**Tool call errors**:
- Bash command failures (exit code != 0)
- Edit pattern not found
- Read file not found
- Permission denied

**System errors**:
- Timeout
- Network errors
- Resource exhaustion

**Logic errors**:
- Test failures
- Assertion errors
- Validation failures

---

### Error Context

Each error includes:
- **`message_index`** and **`tool_use_id`**: Where the error occurred
- **`error_type`**: How it was classified (for example `is_error_flag`, `pattern_match`)
- **`content_preview`**: The first 300 characters of the error text
- **`timestamp`**
- **`context`**: The failing call, not surrounding messages: `tool_name`, `tool_input_preview`, `thinking_preview` (the thinking just before it) and `prior_action`

**Example**:
```json
{
  "message_index": 67,
  "tool_use_id": "toolu_01...",
  "error_type": "is_error_flag",
  "content_preview": "Exit code 1 ...",
  "timestamp": "2026-10-27T06:17:26.977Z",
  "context": {
    "tool_name": "Bash",
    "tool_input_preview": "pytest tests/test_main.py",
    "thinking_preview": "Running tests to verify fix...",
    "prior_action": "Edit"
  }
}
```

---

### Error Analysis

**Recurring errors**: Same error multiple times
- **Indicates**: Misunderstanding, environment issue, incorrect approach
- **Action**: Review error pattern, check environment, consider alternative approach

**Cascading errors**: One error triggers others
- **Indicates**: Root cause issue
- **Action**: Focus on first error in sequence

**Isolated errors**: Single error, then recovery
- **Indicates**: Normal trial-and-error, environment glitch
- **Action**: Usually no concern unless recurring

---

## Token Analysis

### API Token Usage

The overview's `token_summary` and the `?tokens` view report the API's own usage figures, not estimates. Claude Code writes one JSONL record per content block of a reply and every record repeats that reply's usage (input and cache figures stay the same, output grows while it streams), so records are grouped by `message.id` and counted once, at their largest value. `?tokens` has one entry per API message.

### Token Estimation

**Formula**: `tokens ≈ characters / 4`

**Accuracy**: ±10% (approximation, actual tokenization varies)

---

### Thinking Block Analysis

`/thinking` JSON reports `thinking_block_count`, `blocks_without_text` (blocks whose text the transcript did not store, common with current models), `total_chars`, `total_tokens_estimate` and `blocks[]` (`message_index`, `content`, `char_count`, `token_estimate`, `timestamp`). It has no averages, largest block or frequency rating.

---

### Token Optimization Insights (reader's guide, not reveal output)

**High thinking token usage** (>30% of session):
- **Potential issue**: Over-analysis, repetitive thinking
- **Action**: Consider more direct approaches, reduce unnecessary reasoning

**Large thinking blocks** (>500 tokens):
- **Potential issue**: Complex reasoning chains
- **Action**: Review if complexity is justified, consider breaking down problem

**Frequent thinking blocks** (>20 blocks):
- **Potential issue**: Excessive internal deliberation
- **Action**: Improve prompt clarity, provide more context upfront

---

## Detailed Workflows

### Workflow 1: Post-Session Review

**Scenario**: Understand what happened in a completed session

**Steps**:

```bash
# Step 1: Quick overview
reveal claude://session/my-session
# Returns: Message count, tool usage, duration, summary

# Step 2: Check for errors
reveal 'claude://session/my-session?errors'
# Returns: Any errors that occurred

# Step 3: Analyze tool usage
reveal claude://session/my-session/tools
# Returns: Tool counts, success rates

# Step 4: Review file operations
reveal claude://session/my-session/files
# Returns: Files modified, created, read

# Step 5: Comprehensive summary
reveal 'claude://session/my-session?summary'
# Returns: Overview plus per-tool success rates and message sizes
```

**Automation**:
```bash
#!/bin/bash
SESSION="$1"
echo "=== Session Overview ==="
reveal claude://session/$SESSION

echo -e "\n=== Errors ==="
reveal "claude://session/$SESSION?errors"

echo -e "\n=== Tool Usage ==="
reveal claude://session/$SESSION/tools

echo -e "\n=== Files Modified ==="
reveal claude://session/$SESSION/files
```

---

### Workflow 2: Debug Failed Session

**Scenario**: Find why a session failed and what went wrong

**Steps**:

```bash
# Step 1: Check for errors
reveal 'claude://session/failed-build?errors'
# Returns: All errors with context

# Step 2: View workflow to find failure point
reveal claude://session/failed-build/workflow
# Returns: Chronological operations, identifies where failure occurred

# Step 3: Check specific tool failures
reveal 'claude://session/failed-build?tools=Bash&errors'
# Returns: Bash command failures specifically

# Step 4: Review error context
reveal claude://session/failed-build/errors
# Returns: Detailed error information with surrounding messages

# Step 5: Analyze tool success rates
reveal claude://session/failed-build/tools
# Returns: Which tools had issues
```

---

### Workflow 3: Token Optimization

**Scenario**: Identify token waste and optimize session efficiency

**Steps**:

```bash
# Step 1: Get summary with token estimates
reveal 'claude://session/my-session?summary'
# Returns: Overview with token usage patterns

# Step 2: Analyze thinking blocks
reveal claude://session/my-session/thinking
# Returns: All thinking blocks with token estimates

# Step 3: Check for repeated Read operations
reveal 'claude://session/my-session?tools=Read'
# Returns: All Read operations (look for duplicates)

# Step 4: Identify file hotspots
reveal claude://session/my-session/files
# Returns: Files touched by operation (count repeats yourself, see File Access Patterns)
```

**Optimization ideas** (the reader's judgement, not reveal output):
- **Repeated reads of same file**: Use context management, pass context explicitly
- **Large thinking blocks**: Simplify prompts, provide clearer direction
- **High file access count**: Consider summarizing or caching file content

---

### Workflow 4: Agent Behavior Analysis

**Scenario**: Understand how agent approached a problem

**Steps**:

```bash
# Step 1: View workflow sequence
reveal claude://session/my-session/workflow
# Returns: Chronological tool operations

# Step 2: Analyze tool selection
reveal claude://session/my-session/tools
# Returns: Which tools were chosen and how often

# Step 3: Track context changes
reveal claude://session/my-session/context
# Returns: Directory and branch changes

# Step 4: Review thinking process
reveal claude://session/my-session/thinking
# Returns: Agent reasoning and decision-making
```

---

### Workflow 5: Session Comparison

**Scenario**: Compare two sessions (e.g., successful vs failed)

**Steps**:

```bash
# Session 1 analysis
reveal claude://session/successful-session/tools > session1-tools.json
reveal claude://session/successful-session/workflow > session1-workflow.json

# Session 2 analysis
reveal claude://session/failed-session/tools > session2-tools.json
reveal claude://session/failed-session/workflow > session2-workflow.json

# Compare with diff
diff -u session1-tools.json session2-tools.json
diff -u session1-workflow.json session2-workflow.json
```

**Analysis**:
- Tool usage differences
- Workflow pattern differences
- Success rate differences

---

### Workflow 6: Continuous Monitoring

**Scenario**: Track session quality over time

**Setup monitoring script**:

```bash
#!/bin/bash
# monitor-sessions.sh

SESSION_DIR="$HOME/.claude/projects/my-project"

for session in $(ls -1t $SESSION_DIR | head -10); do
  echo "=== $session ==="

  # Get success rate
  SUCCESS_RATE=$(reveal claude://session/$session/tools --format json | \
    jq -r '([.tools[] | .success] | add) / ([.tools[] | .count] | add) * 100')

  # Get error count
  ERROR_COUNT=$(reveal "claude://session/$session?errors" --format json | \
    jq -r '.error_count // 0')

  echo "Success Rate: $SUCCESS_RATE%"
  echo "Errors: $ERROR_COUNT"

  # Alert if issues
  if (( $(echo "$SUCCESS_RATE < 80" | bc -l) )) || [ "$ERROR_COUNT" -gt 5 ]; then
    echo "⚠️  Session quality issues detected"
  fi

  echo ""
done
```

---

## Performance Considerations

### Operation Timing

Measured on a 1.6 MB and a 5.5 MB transcript: the overview, `?summary`, `/workflow` and `/tools` each took 0.28-0.32 s. The time is dominated by interpreter start-up and loading the JSONL file, which every view pays, so no view is meaningfully faster than another. Choose a view by the size of its output, not by speed.

---

### Optimization Strategies

#### 1. Progressive Disclosure

Start with overview, drill down only when needed:

```bash
# ❌ Expensive: Jump to comprehensive analysis
reveal 'claude://session/my-session?summary'

# ✅ Efficient: Start with overview
reveal claude://session/my-session
# If issues detected:
reveal 'claude://session/my-session?errors'
# If deeper analysis needed:
reveal 'claude://session/my-session?summary'
```

**Token savings**: 60-70%

---

#### 2. Targeted Filtering

Use filters to reduce output:

```bash
# ❌ Large output: All messages
reveal claude://session/my-session

# ✅ Focused: Only Bash usage
reveal 'claude://session/my-session?tools=Bash'

# ✅ Even more focused: Bash errors only
reveal 'claude://session/my-session?tools=Bash&errors'
```

**Output reduction**: 80-90%

---

#### 3. Element Selection

Choose specific elements instead of full summary:

```bash
# ❌ Heavy: Full summary
reveal 'claude://session/my-session?summary'

# ✅ Light: Just what you need
reveal claude://session/my-session/tools  # Only tool analytics
reveal claude://session/my-session/files  # Only file operations
```

**Note**: Each view takes about the same time (around 0.3 s on a few-MB transcript, dominated by start-up and loading the file); choose by output size, not speed.

---

#### 4. JSON Output for Automation

Use JSON format for programmatic analysis:

```bash
# Parse with jq for efficient filtering
reveal claude://session/my-session/tools --format json | jq '.tools | to_entries[] | select((.value.success_rate | rtrimstr("%") | tonumber) < 80)'
```

**Benefit**: Client-side filtering, reduced output, easier parsing

---

## Limitations

### Current Limitations

1. **Conversation file dependency**
   - **Requirement**: Conversation JSONL file must exist in `~/.claude/projects/`
   - **Impact**: Can't analyze sessions without saved conversations
   - **Workaround**: Ensure conversations are saved

2. **Session name matching**
   - **Limitation**: Session name must match directory name pattern
   - **Impact**: Non-standard session names may not be found
   - **Workaround**: Use exact session name from directory listing
   - **Several transcripts under one name**: a session directory can hold more than one transcript (the session was re-entered). `claude://session/<name>` reads the first started and names the others in a warning; open one of them with `claude://session/<uuid>`.

3. **Token estimation accuracy**
   - **Limitation**: Approximation (chars / 4), not exact tokenization
   - **Accuracy**: ±10%
   - **Impact**: Token counts are estimates, not precise
   - **Workaround**: Use for relative comparison, not absolute values

4. **Live sessions are read as written**
   - Results reflect the transcript up to the last record written, so a running session can be analyzed

5. **No session modification**
   - **Limitation**: Read-only analysis (can't edit conversations)
   - **Design**: Intentional (inspection tool, not editor)

6. **Cross-session search available via `claude://sessions/?search=term`**
   - **Status**: Implemented — scans all session JSONL files, returns one snippet per match
   - **Default**: 20 results; use `--all` for full scan; `?since=DATE` narrows corpus
   - **Examples**: `reveal 'claude://sessions/?search=validate_token'`, `reveal 'claude://sessions/?search=auth&since=2026-03-01'`

---

### Design Limitations (Intentional)

1. **No conversation editing**: Read-only (by design)
2. **Cross-session search available** via `claude://sessions/?search=term`; full multi-session analysis not supported (by design)
3. **No real-time monitoring**: File-based analysis only (by design)

---

## Error Messages

### Common Errors and Solutions

#### Error: "Conversation not found for session"

**Meaning** (exit 1): no transcript matched the name by directory name, full UUID, first 8 hex characters, or any trailing part of the UUID. Invalid names and empty session directories give the same message.

**Solutions**:
```bash
# List available sessions
reveal claude://

# Check the base path
reveal 'claude://session/<name>' --base-path ~/my-sessions
```

A stock Claude Code install stores transcripts at `~/.claude/projects/<project-dir>/<uuid>.jsonl`.

---

#### Cross-session search

Cross-session content search is fully implemented via `claude://sessions/?search=term`:

Search matches decoded message blocks and `toolUseResult` sidecars, so JSON
escaping does not change whether text matches. File tracking likewise matches
decoded paths, including Unicode and Windows backslashes. Record field names
alone are not content hits. Excerpts use original text positions even when
lowercasing expands a character.

Ordinary substring search uses Unicode lowercase matching; `?word` retains
Unicode regex word-boundary matching. Neither adds accent normalization or full
case folding. Session content searches decode eligible records rather than
rejecting them from raw JSON text; use `?since` and `?until` to bound large stores.

```bash
# Find sessions mentioning a term (20 most recent matches by default)
reveal 'claude://sessions/?search=validate_token'

# Scope to recent sessions (much faster on large stores)
reveal 'claude://sessions/?search=auth&since=2026-03-01'

# Path-based alias
reveal 'claude://search/validate_token'

# Show all matches (no 20-result limit)
reveal 'claude://sessions/?search=auth' --all

# Widen the context snippet around each match (default 120, range 60–500)
reveal 'claude://sessions/?search=validate_token&snippet=300'

# Whole-word match (no substring hits: "auth" won't match "authenticate")
reveal 'claude://sessions/?search=auth&word'
```

**Query parameters:**

| Param | Effect |
|-------|--------|
| `?search=TERM` | Term to find (case-insensitive substring by default) |
| `?since=DATE` | ISO date or `today` — narrows the corpus before scanning (faster) |
| `?until=DATE` | ISO 8601 upper bound date — pairs with `?since=` for a date range (`?since=2026-06-10&until=2026-06-12`) |
| `?word` | Whole-word match — prevents substring hits |
| `?snippet=N` | Characters of context around each match. Default `120`, clamped to `60–500`. Use a larger value when the 120-char default doesn't show enough to understand why the term matched. |
| `?filter=SUBSTRING` | Filter the session *list* (not content search) by name substring — alias of `?search=` for list-filtering mode (`?filter=auth-refactor`) |

---

#### Short session IDs

Use the full UUID, its first 8 hex characters (`2627362f`), or any trailing part of it. Shorter prefixes such as 7 characters do not resolve. A friendly name (`infernal-earth-0118`) works where a session-naming layer provides one.

---

#### Malformed transcript lines

Lines that are not valid JSON are skipped silently (exit 0). A file with no valid lines reports `Messages: 0`.

---

## Tips & Best Practices

### 1. Start with Overview, Then Drill Down

```bash
# ❌ Wasteful: Jump to deep analysis
reveal 'claude://session/my-session?summary'

# ✅ Efficient: Progressive disclosure
reveal claude://session/my-session              # Overview
# If issues detected:
reveal 'claude://session/my-session?errors'       # Focus on problems
# If deeper understanding needed:
reveal claude://session/my-session/workflow     # Full sequence
```

**Token savings**: 60-70%

---

### 2. Use Filters for Targeted Analysis

```bash
# ✅ Focus on specific tool
reveal 'claude://session/my-session?tools=Bash'

# ✅ Find errors only
reveal 'claude://session/my-session?errors'

# ✅ Combine filters
reveal 'claude://session/my-session?tools=Bash&errors'
```

**Benefit**: Reduced noise, faster analysis

---

### 3. Analyze Tool Success Rates

```bash
# Check overall tool health
reveal claude://session/my-session/tools

# Tools with <80% success rate need investigation
```

**Action items**:
- <50% success rate: Review usage patterns, consider alternatives
- 50-80%: Investigate common failures
- >80%: Acceptable, monitor for trends

---

### 4. Track File Hotspots

```bash
# Identify frequently accessed files
reveal claude://session/my-session/files
```

**High access count (>5)**:
- **Why**: Complex file, unclear structure, repeated exploration
- **Action**: Consider summarizing, improving documentation, caching content

---

### 5. Review Workflow for Patterns

```bash
# Understand operation sequence
reveal claude://session/my-session/workflow
```

**Look for**:
- Repeated operations (optimization opportunity)
- Failed operation sequences (debugging patterns)
- Inefficient patterns (Read → Edit → Read → Edit instead of Read → Edit)

---

### 6. Use JSON Output for Automation

```bash
# Extract success rates
reveal claude://session/my-session/tools --format json | \
  jq '.tools | to_entries[] | select((.value.success_rate | rtrimstr("%") | tonumber) < 80)'

# Extract error messages
reveal 'claude://session/my-session?errors' --format json | \
  jq '.errors[].content_preview'

# Count specific tool usage
reveal claude://session/my-session/tools --format json | \
  jq '.tools.Bash.count'
```

---

### 7. Compare Sessions for Quality Trends

```bash
#!/bin/bash
# Compare success rates across recent sessions

for session in $(ls -1t ~/.claude/projects/my-project | head -5); do
  RATE=$(reveal claude://session/$session/tools --format json | jq -r '([.tools[] | .success] | add) / ([.tools[] | .count] | add) * 100')
  echo "$session: $RATE%"
done
```

---

### 8. Analyze Thinking Blocks for Token Optimization

```bash
# Find excessive thinking
reveal claude://session/my-session/thinking --format json | \
  jq '.blocks[] | select(.token_estimate > 500)'
```

**If thinking tokens >30% of session**: Consider clearer prompts, more context upfront

---

### 9. Document Session Patterns

```bash
# Generate session report
{
  echo "# Session: my-session"
  echo ""
  echo "## Overview"
  reveal claude://session/my-session
  echo ""
  echo "## Tool Usage"
  reveal claude://session/my-session/tools
  echo ""
  echo "## Files Modified"
  reveal claude://session/my-session/files
} > session-report.md
```

---

### 10. Monitor Error Patterns Over Time

```bash
#!/bin/bash
# Track error trends

ERROR_LOG="error-trends.csv"
echo "Date,Session,Error Count,Success Rate" > $ERROR_LOG

for session in $(ls -1t ~/.claude/projects/my-project | head -20); do
  ERRORS=$(reveal "claude://session/$session?errors" --format json | jq -r '.error_count // 0')
  SUCCESS=$(reveal claude://session/$session/tools --format json | jq -r '(([.tools[] | .success] | add) / ([.tools[] | .count] | add) * 100) // 0')
  DATE=$(stat -c %y ~/.claude/projects/my-project/$session | cut -d' ' -f1)

  echo "$DATE,$session,$ERRORS,$SUCCESS" >> $ERROR_LOG
done

echo "Error trends logged to $ERROR_LOG"
```

---

## Integration Examples

### 1. jq Integration

**Extract tool success rates** (`tools` is an object keyed by tool name, not an array):
```bash
reveal claude://session/my-session/tools --format json | \
  jq '.tools | to_entries[] | {name: .key, success_rate: .value.success_rate}'
```

**Find low-success tools**:
```bash
reveal claude://session/my-session/tools --format json | \
  jq '.tools | to_entries[] | select(.value.success_rate | rtrimstr("%") | tonumber < 80)'
```

**Count errors** (field is `error_count`, not `count`):
```bash
reveal 'claude://session/my-session?errors' --format json | jq '.error_count'
```

**Extract file paths** (field is `operations[].file_path`, not `files[].path`):
```bash
reveal claude://session/my-session/files --format json | jq -r '.operations[].file_path' | sort -u
```

---

### 2. Python Integration

```python
import subprocess
import json

def analyze_session(session_name):
    """Analyze session and return metrics."""
    result = subprocess.run(
        ['reveal', f'claude://session/{session_name}/tools', '--format', 'json'],
        capture_output=True,
        text=True
    )

    data = json.loads(result.stdout)
    tools = data['tools']  # an object keyed by tool name; success_rate is a string like "85.7%"

    return {
        'session': session_name,
        'overall_success_rate': round(100 * sum(v['success'] for v in tools.values())
                                      / max(1, sum(v['count'] for v in tools.values())), 1),
        'tool_count': len(tools),
        'low_success_tools': [
            name for name, v in tools.items()
            if float(v['success_rate'].rstrip('%')) < 80
        ]
    }

# Analyze session
metrics = analyze_session('infernal-earth-0118')
print(f"Session: {metrics['session']}")
print(f"Success Rate: {metrics['overall_success_rate']}%")
if metrics['low_success_tools']:
    print(f"⚠️  Low-success tools: {', '.join(metrics['low_success_tools'])}")
```

---

### 3. Shell Script Integration

**Session quality report**:

```bash
#!/bin/bash
# session-report.sh - Generate session quality report

SESSION="$1"

if [ -z "$SESSION" ]; then
  echo "Usage: $0 <session-name>"
  exit 1
fi

echo "=== Session Quality Report: $SESSION ==="
echo ""

# Overview
echo "## Overview"
reveal claude://session/$SESSION

# Tool success rates
echo -e "\n## Tool Success Rates"
reveal claude://session/$SESSION/tools --format json | \
  jq -r '.tools | to_entries[] | "\(.key): \(.value.success_rate)"'

# Error count
echo -e "\n## Errors"
ERROR_COUNT=$(reveal "claude://session/$SESSION?errors" --format json | jq -r '.error_count // 0')
echo "Total errors: $ERROR_COUNT"

if [ "$ERROR_COUNT" -gt 0 ]; then
  echo "Error details:"
  reveal "claude://session/$SESSION?errors" --format json | \
    jq -r '.errors[] | "  - [\(.context.tool_name)] \(.content_preview)"'
fi

# File operations
echo -e "\n## File Operations"
reveal claude://session/$SESSION/files --format json | \
  jq -r '"Files: \(.unique_files), operations: \(.total_operations), edited: \(.by_operation.Edit | length), written: \(.by_operation.Write | length)"'

echo ""
echo "Report complete."
```

---

### 4. Monitoring Dashboard

**Track session health**:

```bash
#!/bin/bash
# dashboard.sh - Live session quality dashboard

PROJECT="my-project"
SESSION_DIR="$HOME/.claude/projects/$PROJECT"

while true; do
  clear
  echo "=== Session Quality Dashboard ==="
  echo "Project: $PROJECT"
  echo "Last updated: $(date)"
  echo ""

  echo "Recent Sessions:"
  echo "--------------------------------"

  for session in $(ls -1t $SESSION_DIR | head -5); do
    SUCCESS=$(reveal claude://session/$session/tools --format json 2>/dev/null | \
      jq -r '(([.tools[] | .success] | add) / ([.tools[] | .count] | add) * 100) // "N/A"')
    ERRORS=$(reveal "claude://session/$session?errors" --format json 2>/dev/null | \
      jq -r '.error_count // 0')

    printf "%-30s | Success: %5s%% | Errors: %2s\n" "$session" "$SUCCESS" "$ERRORS"
  done

  sleep 60
done
```

---

### 5. GitHub Actions Integration

```yaml
name: Session Quality Check

on:
  workflow_dispatch:
    inputs:
      session_name:
        description: 'Session name to analyze'
        required: true

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - name: Install reveal
        run: pip install reveal-cli

      - name: Analyze session
        id: analyze
        run: |
          SUCCESS_RATE=$(reveal claude://session/${{ inputs.session_name }}/tools --format json | \
            jq -r '([.tools[] | .success] | add) / ([.tools[] | .count] | add) * 100')
          ERROR_COUNT=$(reveal claude://session/${{ inputs.session_name }}?errors --format json | \
            jq -r '.error_count // 0')

          echo "success_rate=$SUCCESS_RATE" >> $GITHUB_OUTPUT
          echo "error_count=$ERROR_COUNT" >> $GITHUB_OUTPUT

      - name: Check quality thresholds
        run: |
          if (( $(echo "${{ steps.analyze.outputs.success_rate }} < 80" | bc -l) )); then
            echo "::warning::Session success rate below 80%"
          fi

          if [ "${{ steps.analyze.outputs.error_count }}" -gt 5 ]; then
            echo "::error::Session has more than 5 errors"
            exit 1
          fi

      - name: Generate report
        run: |
          reveal claude://session/${{ inputs.session_name }}?summary > session-report.txt

      - name: Upload report
        uses: actions/upload-artifact@v3
        with:
          name: session-report
          path: session-report.txt
```

---

### 6. Slack Alerting

```bash
#!/bin/bash
# slack-alert.sh - Alert on low session quality

SESSION="$1"
WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

SUCCESS_RATE=$(reveal claude://session/$SESSION/tools --format json | jq -r '([.tools[] | .success] | add) / ([.tools[] | .count] | add) * 100')
ERROR_COUNT=$(reveal "claude://session/$SESSION?errors" --format json | jq -r '.error_count // 0')

if (( $(echo "$SUCCESS_RATE < 70" | bc -l) )) || [ "$ERROR_COUNT" -gt 10 ]; then
  MESSAGE="{
    \"text\": \"⚠️ Session Quality Alert: $SESSION\",
    \"attachments\": [{
      \"color\": \"warning\",
      \"fields\": [
        {\"title\": \"Success Rate\", \"value\": \"$SUCCESS_RATE%\", \"short\": true},
        {\"title\": \"Error Count\", \"value\": \"$ERROR_COUNT\", \"short\": true}
      ]
    }]
  }"

  curl -X POST -H 'Content-type: application/json' --data "$MESSAGE" $WEBHOOK_URL
fi
```

---

## Install Introspection Resources

These resources inspect your **Claude Code installation** — they are independent of any session. Each maps to a data directory or file under `~/.claude/`.

| Resource | What It Shows | File / Dir |
|----------|--------------|------------|
| `claude://info` | All data locations + env overrides | `~/.claude/` |
| `claude://history` | Prompt history (all sessions) | `~/.claude/history.jsonl` |
| `claude://settings` | User preferences | `~/.claude/settings.json` |
| `claude://plans` | Saved Claude Code plans | `~/.claude/plans/` |
| `claude://config` | Per-install flags + MCP registrations | `~/.claude.json` |
| `claude://memory` | Memory files across all projects | `~/.claude/projects/*/memory/` |
| `claude://agents` | Custom agent definitions | `~/.claude/agents/` |
| `claude://hooks` | Hook scripts by event type | `~/.claude/hooks/` |

> **Pointing at a different install** (SSH, WSL, multi-user): Use `REVEAL_CLAUDE_HOME=/path/to/.claude` — all paths (history, config, plans, hooks, sessions) derive from it automatically. You can also pass `--base-path /path/to/.claude` (the home dir) or `--base-path /path/to/.claude/projects` (the projects subdir) — both forms are accepted. For non-standard `.claude.json` locations, set `REVEAL_CLAUDE_JSON`. Check resolved paths with `claude://info`.

---

### `claude://info` — Path Diagnostics

Diagnostic dump of all resolved Claude Code data paths and active environment overrides. Use this first when troubleshooting missing history, wrong sessions dir, or MCP issues.

```bash
reveal claude://info
```

**Output**:
```
Claude Code data locations:

  home                       /home/user/.claude  [32 items]
  projects (sessions)        /home/user/.claude/projects  [3366 items]
  history                    /home/user/.claude/history.jsonl  [51MB]
  plans                      /home/user/.claude/plans  [39 items]
  settings                   /home/user/.claude/settings.json  [1KB]
  config (~/.claude.json)    /home/user/.claude.json  [41KB]
  agents                     /home/user/.claude/agents  [1 items]
  hooks                      /home/user/.claude/hooks  [1 items]

Environment overrides:
  REVEAL_CLAUDE_HOME         (not set)
  REVEAL_CLAUDE_JSON         (not set)
  REVEAL_CLAUDE_DIR          (not set)
  REVEAL_SESSIONS_DIR        (not set)
```

**Returns**: Paths with existence, kind (`file`/`dir`), size/count. No query parameters.

---

### `claude://history` — Prompt History

Browse your full prompt history from `~/.claude/history.jsonl`. Streams line-by-line — safe for large files (50MB+). Consecutive entries are grouped under their project path, newest first.

```bash
# Recent 50 prompts (default)
reveal claude://history

# Show all matching entries
reveal claude://history --all

# Show N most recent
reveal claude://history --head 20

# Filter by prompt content
reveal 'claude://history?search=deploy'

# Filter by project path
reveal 'claude://history?project=my-webapp'

# Filter by date
reveal 'claude://history?since=2026-03-01'
reveal 'claude://history?since=today'

# Combine filters
reveal 'claude://history?search=migration&since=2026-02-01&project=sdms'
```

**Query Parameters**:

| Parameter | Description |
|-----------|-------------|
| `?search=term` | Case-insensitive substring match on prompt text |
| `?project=path` | Case-insensitive substring match on project path |
| `?since=DATE` | ISO date (`2026-03-01`) or `today`; excludes older entries |

**CLI Flags**:

| Flag | Description |
|------|-------------|
| `--all` | Show all matching entries (default: 50) |
| `--head N` | Show N most recent matching entries |

**Returns**: Entries with `prompt`, `project`, `timestamp`, `session_id`. Header shows total entry count and match count.

---

### `claude://settings` — User Settings

Read `~/.claude/settings.json` — the user preferences file edited via Claude Code settings UI or directly.

```bash
# Full settings
reveal claude://settings

# Extract a specific key (dot-path)
reveal 'claude://settings?key=permissions.additionalDirectories'
reveal 'claude://settings?key=cleanupPeriodDays'
```

**Query Parameters**:

| Parameter | Description |
|-----------|-------------|
| `?key=dotpath` | Extract a nested value using dot notation (e.g. `permissions.additionalDirectories`) |

**Returns**: Full settings JSON, or a single extracted value when `?key=` is used.

**Common keys**: `cleanupPeriodDays`, `includeCoAuthoredBy`, `permissions.additionalDirectories`, `statusLine`, `alwaysThinkingEnabled`, `autoCompactEnabled`.

---

### `claude://plans` — Saved Plans

List or read saved plans from `~/.claude/plans/`. Plans are Markdown files created by Claude Code's built-in plan mode, with random slug names (for example `goofy-churning-island`).

```bash
# List all plans (sorted by most recent)
reveal claude://plans

# Read a specific plan (exact or prefix match)
reveal claude://plans/my-session-name

# Search plan content
reveal 'claude://plans?search=deployment'
```

**Query Parameters**:

| Parameter | Description |
|-----------|-------------|
| `?search=term` | Case-insensitive content filter — only plans containing `term` are listed |

**Sub-resource**:

```bash
reveal 'claude://plans/<name>'      # Exact name or unambiguous prefix
```

Name matching: `.md` extension is optional. If the name is a unique prefix, it resolves automatically. If ambiguous, returns a list of matches.

**Returns (list)**: Name, modified timestamp, size, first-line title — sorted by most recent.

**Returns (single plan)**: Full Markdown content with name and modified timestamp.

---

### `claude://config` — Install Config

Read `~/.claude.json` — the per-install config file storing feature flags, project registrations, and MCP server assignments. Secrets are masked automatically.

```bash
# Summary view (flags + project count)
reveal claude://config

# Extract a specific value (dot-path)
reveal 'claude://config?key=numStartups'
reveal 'claude://config?key=autoUpdates'
```

**Query Parameters**:

| Parameter | Description |
|-----------|-------------|
| `?key=dotpath` | Extract a nested value using dot notation |

**Returns (summary)**:
- **Flags**: `autoUpdates`, `autoCompactEnabled`, `verbose`, `installMethod`, `numStartups`, `autoConnectIde`, `showSpinnerTree`
- **Projects**: Count + per-project MCP server names and allowed tools
- Secrets (API keys, tokens) are masked

**Returns (`?key=`)**: Scalar or object at the specified path.

**Common keys**: `numStartups`, `autoUpdates`, `verbose`, `installMethod`, `autoCompactEnabled`.

---

### `claude://memory` — Memory Files

Walk `~/.claude/projects/*/memory/` and list all memory files across projects. Memory files use YAML frontmatter (`type`, `description`, `name`) parsed and surfaced in the listing.

```bash
# All memory files across all projects
reveal claude://memory

# Filter to one project (substring match on project dir name)
reveal claude://memory/-home-user-src-myproject

# Search memory file content
reveal 'claude://memory?search=deployment'

# Combine: filter project + search content
reveal 'claude://memory/-home-user-src-myproject?search=feedback'
```

**Sub-resource**:

```bash
reveal 'claude://memory/<project-fragment>'    # Substring match on project directory name
```

**Query Parameters**:

| Parameter | Description |
|-----------|-------------|
| `?search=term` | Case-insensitive content filter across all memory files |

**Returns**: Files grouped by project, sorted by most recently modified. Each entry shows: `name`, `type` (from frontmatter), `description` (from frontmatter), `modified`, `size_bytes`, `path`.

**Memory types**: `user`, `feedback`, `project`, `reference` — shown in brackets in the listing.

---

### `claude://agents` — Agent Definitions

List or read custom agent definitions from `~/.claude/agents/`. Agents are Markdown files with YAML frontmatter declaring `description`, `tools`, and `model`.

```bash
# List all agents
reveal claude://agents

# Read a specific agent
reveal claude://agents/my-agent-name

# Search agent content
reveal 'claude://agents?search=codereview'
```

**Query Parameters**:

| Parameter | Description |
|-----------|-------------|
| `?search=term` | Case-insensitive content filter — only agents containing `term` are listed |

**Sub-resource**:

```bash
reveal 'claude://agents/<name>'    # Exact name or unambiguous prefix; .md extension optional
```

**Returns (list)**: Name, modified, size, model, description — sorted by most recently modified.

**Returns (single agent)**: Full Markdown content + parsed frontmatter (`description`, `tools`, `model`).

**Agent frontmatter**:
```yaml
---
description: "What this agent does"
model: sonnet
tools:
  - Bash
  - Read
  - Grep
---
```

---

### `claude://hooks` — Hook Scripts

List or read the files and directories under `~/.claude/hooks/`. Each entry's name is shown in the EVENT column even when it is not an event name (a README or a helper script is listed the same way). Which hooks Claude Code actually runs is set by the `hooks` block in `settings.json`: see `claude://settings?key=hooks`. Executability is shown for each entry.

```bash
# List all hook events
reveal claude://hooks

# Read or list scripts for a specific event
reveal claude://hooks/PostToolUse
reveal claude://hooks/PreToolUse
```

**Sub-resource**:

```bash
reveal 'claude://hooks/<EventName>'
```

Hook storage can be either:
- **File-style**: A single script directly at `~/.claude/hooks/<EventName>` (e.g. `PostToolUse`)
- **Directory-style**: A directory at `~/.claude/hooks/<EventName>/` containing multiple scripts

**Returns (list)**: Event name, kind (`file` or `directory`), modified, size/script count, executability.

**Returns (file event)**: Full script content, path, size, executable flag, modified timestamp.

**Returns (directory event)**: List of scripts within the event directory, each with path, size, executable flag, modified.

**Common event names** (when a file or directory is named after one): `PreToolUse`, `PostToolUse`, `Stop`, `SubagentStop`, `Notification`.

---

## Related Documentation

### Reveal Adapter Guides
Related adapters are shown live via `reveal help://claude` (see its `## Next`
section) — sourced from reveal's adapter-relationship registry, so this
list can't go stale the way a hand-maintained one did.

### Reveal Core Documentation

- **[REVEAL_ADAPTER_GUIDE.md](REVEAL_ADAPTER_GUIDE.md)** - Reveal adapter reference
- **[ADAPTER_AUTHORING_GUIDE.md](../development/ADAPTER_AUTHORING_GUIDE.md)** - How to create adapters
- **[ADAPTER_CONSISTENCY.md](../development/ADAPTER_CONSISTENCY.md)** - Adapter patterns and consistency

---

## FAQ

### General Questions

**Q: What's the difference between claude:// and json://?**

A: **claude://** provides high-level conversation analysis (tool usage, errors, workflow). A session transcript is JSON Lines (one record per line), which `json://` rejects (`conversation.jsonl is a JSON Lines file ... Use 'reveal <path>.jsonl'`). For the raw records use `reveal <file>.jsonl` (for example with `--head N`).

---

**Q: Can I analyze a currently running session?**

A: Yes. claude:// reads whatever has been appended to the transcript so far, so the results reflect the session up to the last record written.

---

**Q: Where are conversation files stored?**

A: `~/.claude/projects/<project-dir>/<uuid>.jsonl` on a stock Claude Code install (with a same-named directory holding `tool-results/`). A `conversation.jsonl` exists only in TIA-style session directories, where it is a link to that file.

---

**Q: How accurate are token estimates?**

A: Approximate (±10%). Formula: `tokens ≈ characters / 4`. Use for relative comparison, not absolute values.

---

**Q: Can I analyze multiple sessions at once?**

A: Some views span sessions: `claude://` (the session list), `claude://sessions/?search=<term>` (cross-session search) and `claude://history`. For per-session analysis across many sessions use shell loops. See [Integration Examples](#integration-examples).

---

### Tool Usage Questions

**Q: What does "success rate" mean?**

A: Percentage of tool calls that returned results without errors. Formula: `(Successful Calls / Total Calls) × 100`

---

**Q: What's a good tool success rate?**

A:
- **90-100%**: Excellent
- **75-89%**: Good
- **50-74%**: Fair (investigate patterns)
- **<50%**: Poor (review usage)

---

**Q: Why is my Bash success rate low?**

A: Common causes:
- Command syntax errors
- Environment issues (missing tools)
- Permission problems
- Incorrect paths

Review: `reveal 'claude://session/my-session?tools=Bash&errors'`

---

**Q: Can I see specific tool parameters?**

A: `/workflow` shows only a `detail` per step (the Bash description or the file path). The parameters are in `?tools=<Name>` (each `calls[].input`, for example `command` and `description`) or in `/message/<n>`.

---

### File Operation Questions

**Q: What's a "hotspot" file?**

A: A file the session touched many times. reveal does not flag hotspots; count repeats in `/files` JSON (`operations[].file_path`). Many repeats can indicate:
- Complex file structure
- Repeated exploration
- Missing information

**Action**: Consider summarizing or improving documentation.

---

**Q: How do I find files that were edited?**

A: `reveal claude://session/my-session/files --format json | jq '.files[] | select(.operations | contains(["Edit"]))'`

---

**Q: Can I see file diffs?**

A: Partly. `reveal 'claude://session/my-session/files?patches=true' --format json` returns each Edit's hunks in `operations[].patch`. For the resulting diff of a file, use git.

---

### Error Analysis Questions

**Q: How do I find why a session failed?**

A:
```bash
# Step 1: Check errors
reveal 'claude://session/failed-session?errors'

# Step 2: View workflow to find failure point
reveal claude://session/failed-session/workflow

# Step 3: Review error context (the failing call's input and the thinking before it)
reveal claude://session/failed-session/errors
```

---

**Q: What's "error context"?**

A: Surrounding messages before/after error (helps understand what led to error).

---

**Q: Can I filter errors by tool?**

A: Yes: `reveal 'claude://session/my-session?tools=Bash&errors'`

---

### Token Optimization Questions

**Q: How do I reduce token usage?**

A: Analyze thinking blocks and file access:
```bash
reveal claude://session/my-session/thinking
reveal claude://session/my-session/files
```

Look for:
- Large thinking blocks (>500 tokens)
- Repeated file reads (same file multiple times)
- Many accesses to the same file (count them from `/files` JSON)

---

**Q: What's excessive thinking token usage?**

A: >30% of total session tokens. Indicates over-analysis or unclear prompts.

---

**Q: How do I find repeated file reads?**

A: `reveal claude://session/my-session/files` - Look for `access_count > 3`

---

### Query Parameter Questions

**Q: Can I combine query parameters?**

A: Yes:
```bash
reveal 'claude://session/my-session?tools=Bash&errors'
reveal 'claude://session/my-session/messages?contains=reveal'
```

---

**Q: What's the difference between ?summary and /workflow?**

A:
- **?summary**: The overview plus per-tool success rates, message sizes and thinking-block count
- **/workflow**: Chronological tool operation sequence only

---

**Q: Can I search across all sessions?**

A: Yes — use `claude://sessions/?search=term`:
```bash
reveal 'claude://sessions/?search=error'
reveal 'claude://sessions/?search=auth&since=2026-03-01'
reveal 'claude://sessions/?search=validate_token' --all
```
See the [Cross-session search](#cross-session-search) section for full syntax and filters.

---

### Integration Questions

**Q: How do I integrate with monitoring tools?**

A: Use JSON output and parse with jq. See [Monitoring Dashboard](#4-monitoring-dashboard) example.

---

**Q: Can I export metrics to Prometheus?**

A: Yes, parse JSON output:
```bash
reveal claude://session/my-session/tools --format json | \
  jq -r '.tools | to_entries[] | "session_tool_success_rate{session=\"my-session\",tool=\"\(.key)\"} \(.value.success_rate | rtrimstr("%"))"'
```

---

**Q: How do I automate session analysis in CI/CD?**

A: See [GitHub Actions Integration](#5-github-actions-integration) example.

---

