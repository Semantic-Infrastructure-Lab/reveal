---
title: "Reveal MCP Server Setup"
type: guide
beth_topics:
  - reveal
  - mcp
  - claude-code
  - agent-integration
help_topic: mcp
help_description: "MCP server setup — 10 tools for Claude Code, Cursor, Windsurf"
help_category: ai_guides
help_token_estimate: "~2,000"
---

# Reveal MCP Server

Reveal ships a first-class MCP (Model Context Protocol) server that exposes reveal's
capabilities as structured tools — no subprocess overhead, no stdout parsing,
native integration with Claude Code, Cursor, Windsurf, and any MCP-compatible agent.

## Installation

```bash
pip install reveal-cli
```

The `reveal-mcp` command is included as an entry point in `reveal-cli` — no separate package needed.

Or if reveal is already installed and `mcp` isn't:
```bash
pip install "mcp>=2.0.0"
```

## Configuration

### Claude Code

Add to your Claude Code settings (`~/.claude/settings.json` or project
`.claude/settings.json`):

```json
{
  "mcpServers": {
    "reveal": {
      "command": "reveal-mcp"
    }
  }
}
```

### Cursor / Windsurf

Add `reveal-mcp` as an MCP server in your IDE's MCP configuration.
Uses stdio transport by default — no port configuration needed.

### HTTP / SSE Transport

For HTTP-based clients:

```bash
reveal-mcp --transport sse --host 127.0.0.1 --port 8000
reveal-mcp --transport streamable-http --port 8080
```

## Available Tools

**Error handling:** an unambiguous call failure (bad path, unresolvable element,
unknown flag, an underlying exception) returns the call with `isError: true` in
the MCP result — check that field rather than string-matching the response text.
A negative *verdict* from the tool itself (e.g. `reveal_health` returning FAIL, or
`reveal_check` finding issues) is not a call failure and always comes back with
`isError: false` — that's real output, not an error.

### `reveal_structure(path, depth=3, ext='', exclude='', files=False)`

Get the semantic structure of a file or directory — the first step of progressive
disclosure. Returns function signatures, imports, and class definitions for files;
file trees for directories. `depth`/`ext`/`exclude`/`files` scope the directory
case only, mirroring the CLI's `--depth`/`--ext`/`--exclude`/`--files`.

```
reveal_structure("src/auth.py")                    → all functions with signatures
reveal_structure("src/")                            → directory tree
reveal_structure("docs/", files=True, ext="md")     → doc-triage: flat, newest-first, *.md only
reveal_structure("src/", depth=1)                   → shallow tree on a large monorepo
reveal_structure("src/", exclude="vendor,*.log")    → tree with noise excluded
```

Token cost: 50–500 tokens (vs thousands for raw file content).

### `reveal_element(path, element)`

Extract the full implementation of a specific function or class. Use after
`reveal_structure` to drill into exactly the code you need.

```
reveal_element("src/auth.py", "validate_token")
```

### `reveal_query(uri)`

Run any reveal URI query across all adapters. Same syntax as the CLI.

```
reveal_query("ast://src/?complexity>10&sort=-complexity")
reveal_query("calls://src/?target=validate_token&depth=3")
reveal_query("calls://src/?uncalled")
reveal_query("ssl://api.example.com")
reveal_query("domain://example.com")
reveal_query("imports://src/?unused")
reveal_query("diff://git://main/.:git://HEAD/.")
reveal_query("xlsx://model.xlsx?powerpivot=tables")
```

CLI-only global flags (`--severity`, `--select`, `--format`, `--provenance`)
don't pass through here — write `?limit=N`, `?sort=field`/`?sort=-field`, and
`?offset=M` directly in the URI instead (every adapter reads these off the
query string the same way regardless of CLI vs. MCP). Everything else is each
adapter's own `?key=value` vocabulary — check `reveal_query('help://schemas/
<adapter>')` for what a given scheme accepts, or use a dedicated typed tool
(`reveal_check` has `severity`/`select`/`ignore`).

### `reveal_pack(path, budget, since, content, focus)`

Token-budgeted context snapshot — ideal for PR review. Selects the most important
files, with changed files first (when `since` is set).

```
reveal_pack("src/", budget=8000, since="main", content=True)
```

With `content=True` (default):
- Changed files → full raw content
- Key files → reveal structure (function signatures, imports)
- Low-priority files → names only

### `reveal_check(path, severity, select, ignore)`

Run quality checks. Detects complexity hotspots, maintainability issues, style
violations, broken links. `select`/`ignore` take comma-separated rule codes or
series (e.g. `"M"`, `"B006,S012"`) — same as the CLI's `--select`/`--ignore`.

```
reveal_check("src/")
reveal_check("src/auth.py", severity="high")
reveal_check("src/", select="M", ignore="N")
```

### `reveal_nav(path, element, flag)`

Navigate inside a function using analysis flags — the final level of progressive
disclosure. Routes all `--flag` options to agents without subprocess overhead.

```
reveal_nav("src/auth.py", "validate_token", "boundary")     → inputs + environment + effects
reveal_nav("src/auth.py", "validate_token", "sideeffects")  → classified outbound calls (db/http/cache/log/file)
reveal_nav("src/auth.py", "validate_token", "returns")      → exit paths with gate conditions
reveal_nav("src/auth.py", "validate_token", "ifmap")        → conditional branch map
reveal_nav("src/auth.py", "validate_token", "varflow")      → variable data-flow
```

Answers "what does this function touch outside itself?" without ever reading source.

### `reveal_grep(path, pattern, ignore_case)`

Cross-file text/identifier search grouped by enclosing function — use instead of
shell grep when you want matches tied to the function/class they're in.

```
reveal_grep("src/", "API_TIMEOUT")
reveal_grep("src/auth.py", "validate_.*token", ignore_case=True)
```

### `reveal_trace(path, entry_point, depth)`

Depth-indented call-graph narrative from one entry point — each frame shows
location, parameters, classified side effects, and what it calls next.
Complements `reveal_query("calls://...")`, which answers structural
caller/callee queries rather than rendering a readable walk-through.

```
reveal_trace("src/", "process_order", depth=2)
```

### `reveal_health(target, select)`

Unified PASS/WARN/FAIL health check for a path (code quality) or a URI
resource (`ssl://`, `mysql://`, `domain://`) — a quicker go/no-go read than
`reveal_check`/`reveal_query` when you just need a verdict per target.

```
reveal_health("src/")
reveal_health("ssl://api.example.com")
reveal_health("mysql://prod/mydb")
```

### `reveal_review(target, select)`

PR-merge quality assessment: violations, hotspots, and complexity spikes in
one report. A git range (`"main..feature"`) scopes analysis to only the
changed files; a directory reviews the whole tree.

```
reveal_review("main..feature")
reveal_review("src/", select="B,S")
```

## Recommended Agent Workflow

```
# 0. Orient in an unfamiliar codebase first
reveal_query("overview://src/")             # quality score, hotspots, git activity, one screen

# 1. Understand the shape of a codebase area
reveal_structure("src/")                    # 50-200 tokens: what files exist

# 2. Understand a specific file
reveal_structure("src/auth.py")             # 200-500 tokens: all functions

# 3. Read only what you need
reveal_element("src/auth.py", "validate_token")  # 100-300 tokens: one function

# 4. PR review context in one call
reveal_pack("src/", since="main", budget=8000, content=True)

# 5. Find dead code before a refactor
reveal_query("calls://src/?uncalled")

# 6. Impact analysis before changing a function
reveal_query("calls://src/?target=validate_token&depth=3")
```

## Cross-Resource Workflows

Reveal adapters cover more than source code. Use `reveal_query` for any URI adapter:

```
# Search prior Claude sessions for a topic
reveal_query("claude://sessions/?search=validate_token")
reveal_query("claude://sessions/?search=auth&since=2026-03-01")

# Search OpenAI Codex CLI sessions
reveal_query("codex://sessions/?filter=validate_token")
reveal_query("codex://sessions/?search=authentication")

# Git history — commits mentioning a keyword
reveal_query("git://.?message~=fix")

# Markdown docs — full-text + metadata filter
reveal_query("markdown://docs/?body-contains=retry&type=procedure")

# SQLite database introspection
reveal_query("sqlite:///path/to/app.db")

# Discover all available adapters (including project-local plugins)
reveal_query("help://adapters")

# Get machine-readable schema for any adapter
reveal_query("help://schemas/claude")
reveal_query("help://schemas/git")
```

When you're uncertain what adapter to use, start with:
```
reveal_query("help://quick")   # compact intent router, ~750 tokens
```

## Token Efficiency

| Tool | Typical tokens | vs reading directly |
|------|---------------|---------------------|
| `reveal_structure(dir)` | 50–200 | — |
| `reveal_structure(file)` | 200–500 | 10–50× less than cat |
| `reveal_element(file, fn)` | 100–300 | 20–50× less than cat |
| `reveal_pack(dir, budget=8000)` | ~8,000 | One call instead of N calls |
| `reveal_query("calls://...?uncalled")` | 200–500 | 33× less than manual cross-ref |
| `reveal_grep(dir, pattern)` | 100–500 | grouped by function vs raw grep output |
| `reveal_trace(dir, entry_point)` | 300–1000 | one call vs manual multi-file call chasing |

## Debugging

```bash
# Verify reveal-mcp is installed
reveal-mcp --help

# Test directly (JSON-RPC over stdin)
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | reveal-mcp
```

---

## See Also

- [../QUICK_START.md](../QUICK_START.md) — Ground yourself on the CLI before exposing reveal as MCP tools.
- [RECIPES.md](RECIPES.md) — Task patterns that map directly onto the `reveal_*` MCP tools.
- [../adapters/CLAUDE_ADAPTER_GUIDE.md](../adapters/CLAUDE_ADAPTER_GUIDE.md) — `claude://` adapter for inspecting Claude Code session transcripts.
