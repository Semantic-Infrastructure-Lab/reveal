---
title: "Reveal MCP Server Setup"
type: guide
beth_topics:
  - reveal
  - mcp
  - claude-code
  - agent-integration
---

# Reveal MCP Server

Reveal ships a first-class MCP (Model Context Protocol) server that exposes reveal's
capabilities as structured tools — no subprocess overhead, no stdout parsing,
native integration with Claude Code, Cursor, Windsurf, and any MCP-compatible agent.

## Installation

```bash
pip install "reveal-cli[mcp]"
```

Or if reveal is already installed and `mcp` isn't:
```bash
pip install "mcp>=1.0.0"
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

### `reveal_structure(path)`

Get the semantic structure of a file or directory — the first step of progressive
disclosure. Returns function signatures, imports, and class definitions for files;
file trees for directories.

```
reveal_structure("src/auth.py")          → all functions with signatures
reveal_structure("src/")                  → directory tree
```

Token cost: 50–500 tokens (vs thousands for raw file content).

### `reveal_element(path, element)`

Extract the full implementation of a specific function or class. Use after
`reveal_structure` to drill into exactly the code you need.

```
reveal_element("src/auth.py", "validate_token")
```

### `reveal_query(uri)`

Run any reveal URI query across all 22 adapters. Same syntax as the CLI.

```
reveal_query("ast://src/?complexity>10&sort=-complexity")
reveal_query("calls://src/?target=validate_token&depth=3")
reveal_query("calls://src/?uncalled")
reveal_query("ssl://api.example.com")
reveal_query("domain://example.com")
reveal_query("imports://src/?unused")
reveal_query("diff://git://main/.:git://HEAD/.")
```

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

### `reveal_check(path, severity)`

Run quality checks. Detects complexity hotspots, maintainability issues, style
violations, broken links.

```
reveal_check("src/")
reveal_check("src/auth.py", severity="high")
```

## Recommended Agent Workflow

```
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

## Token Efficiency

| Tool | Typical tokens | vs reading directly |
|------|---------------|---------------------|
| `reveal_structure(dir)` | 50–200 | — |
| `reveal_structure(file)` | 200–500 | 10–50× less than cat |
| `reveal_element(file, fn)` | 100–300 | 20–50× less than cat |
| `reveal_pack(dir, budget=8000)` | ~8,000 | One call instead of N calls |
| `reveal_query("calls://...?uncalled")` | 200–500 | 33× less than manual cross-ref |

## Debugging

```bash
# Verify reveal-mcp is installed
reveal-mcp --help

# Test directly (JSON-RPC over stdin)
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | reveal-mcp
```
