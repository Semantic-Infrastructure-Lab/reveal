---
title: Why Reveal
category: reference
beth_topics:
  - reveal
  - capabilities
  - architecture
  - power-user
---
# Why Reveal

**What makes it genuinely powerful — and what you can do with it**

---

Reveal is not a linter. Not a code browser. Not a metrics tool.

It's a **semantic query layer** — a unified interface for asking questions about code, infrastructure, documentation, and data using a single consistent syntax. You don't run ten separate tools; you compose one.

---

## The Core Idea: Everything Is a URI

Most tools expose features as subcommands (`git log`, `git blame`). Reveal exposes *resources* as URIs with query parameters:

```bash
reveal ast://src/?complexity>10&sort=-complexity
reveal calls://src/?target=validate_token&depth=3
reveal ssl://api.example.com
reveal mysql://prod/?type=replication
reveal markdown://docs/?aggregate=type
```

Same syntax. Same operators. Same output format. Whether you're querying code, certificates, databases, or docs — the mental model doesn't change. New capabilities don't require new syntax; they drop in as new adapters.

---

## The Top Capabilities

### 1. Cross-File Call Graph Analysis (`calls://`)

Who calls this function? What does it call? What are the most-coupled functions in the project?

```bash
# Who calls validate_token? (anywhere in the project)
reveal 'calls://src/?target=validate_token'

# Callers-of-callers — full impact radius before a refactor
reveal 'calls://src/?target=validate_token&depth=3'

# What does process_payment call?
reveal 'calls://src/?callees=process_payment'

# Architectural coupling: what functions are called the most?
reveal 'calls://src/?rank=callers&top=20'

# Colon shorthand — same as ?target=
reveal 'calls://src/auth.py:validate_token'

# Visual call graph (pipe to graphviz)
reveal 'calls://src/?target=main&format=dot' | dot -Tsvg > callgraph.svg

# Dead code: functions defined but never called anywhere
reveal 'calls://src/?uncalled'

# Filter to functions only (skip methods), show top candidates
reveal 'calls://src/?uncalled&type=function&top=20'
```

**What you get:** Cross-file, language-aware call graph analysis from a CLI — no IDE, no language server, no configuration. The `?rank=callers` metric surfaces architecturally load-bearing functions before you know to look for them. The `?uncalled` query identifies dead code candidates as a pure set-difference between defined functions and the callers index — private functions flagged separately, `__dunder__` and decorated methods excluded. No static analysis plugin, no IDE, no config.

---

### 2. Token-Budgeted Context Snapshots (`reveal pack`)

Giving an AI agent codebase context is usually "read everything" or "let the agent figure it out." Pack makes an opinionated decision: *entry points first, then focus-matched files, then key directories, sized to fit a budget.*

```bash
# Snapshot the whole project — fit in 8000 tokens
reveal pack src/ --budget 8000

# Focus on authentication files specifically
reveal pack src/ --focus "authentication" --budget 6000

# PR review context: changed files first, fill with key dependencies
reveal pack src/ --since main --budget 8000

# Since a specific commit
reveal pack src/ --since HEAD~3 --budget 4000

# JSON for programmatic consumption
reveal pack src/ --budget 8000 --format json
```

**What you get:** The right code in the right order at the right size. Complexity and recency determine priority; token budget determines the ceiling. `--since <ref>` boosts changed files to priority tier 0 — above entry points — so a PR review context leads with what actually changed, not what's biggest. The problem it solves — agents burning their context window on stub `__init__.py` files before reaching actual logic — is constant and real.

---

### 3. Unified Health Checks (`reveal health`)

One command. Code quality + SSL certificates + MySQL replication + domain DNS — all in the same invocation, all exit-code-governed.

```bash
# Full health check: code + infra + certs
reveal health

# Check specific resources (code + SSL + domain in one pass)
reveal health ./src ssl://api.example.com domain://example.com

# CI/CD pipeline: exit 0 clean, exit 1 warnings, exit 2 errors
reveal health ./src && deploy.sh || alert_oncall.sh

# JSON output for monitoring
reveal health ./src --format json | jq '.overall_exit'
```

**What you get:** A category collapse. No other single tool runs code analysis, certificate expiry checks, DNS validation, and database health under unified exit codes and JSON output. The value isn't any individual check — it's that you stop switching tools.

---

### 4. Composable Pipelines

Reveal outputs structured data that becomes the next query's input. This is Unix philosophy applied to semantic queries.

```bash
# nginx config → extract all domains → check each SSL cert
reveal nginx.conf --extract domains | \
  sed 's/^/ssl:\/\//' | \
  reveal --stdin --check

# Structural diff between two branches
reveal diff://git://main/.:git://HEAD/.

# Find circular imports across a project
reveal 'imports://src/?circular'

# Batch SSL check from a file of domains
reveal @domains.txt --check
```

**What you get:** Adapters compose. The output of `nginx://` feeds `ssl://`. The output of `diff://` feeds `ast://`. Infrastructure becomes queryable data that pipes into the next analysis.

---

### 5. Docs as a Queryable Graph (`markdown://`)

Documentation isn't text files — it's a graph. Reveal treats it that way.

```bash
# What document types exist across the knowledge base?
reveal 'markdown://docs/?aggregate=type'

# Find all docs tagged with a topic
reveal 'markdown://docs/?beth_topics~=authentication'

# Which docs link to auth.md?
reveal 'markdown://docs/?link-graph' | grep 'auth.md'

# Find orphaned docs (nothing links to them)
reveal 'markdown://docs/?link-graph' | grep 'backlinks: 0'

# Full-text search combining with frontmatter filters
reveal 'markdown://docs/?body-contains=retry&type=procedure'
```

**What you get:** Bidirectional link graphs, taxonomy frequency tables, full-text search combined with structured metadata filtering. Knowledge graph functionality in a code tool.

---

### 6. Automated Code Review (`reveal review`)

```bash
# Full PR review: structural diff → violations → hotspots → pass/fail
reveal review main..HEAD

# Fast: security and bug rules only
reveal review main..HEAD --select B,S

# Find functions that got meaningfully more complex in this PR
reveal diff://git://main/.:git://HEAD/. --format json | \
  jq '.diff.functions[] | select(.complexity_delta > 5)'

# JSON for automated processing
reveal review main..HEAD --format json

# Use as a CI gate (exit codes: 0=clean, 1=warnings, 2=errors)
reveal review main..HEAD || exit 1
```

**What you get:** One command that composes structural diff, quality checks, hotspot detection, and complexity analysis with consistent exit codes. Every changed function carries `complexity_before`, `complexity_after`, and `complexity_delta` — enabling the CI gate: "did this PR make anything meaningfully more complex?" Drop it in a PR check; the baseline is the same whether a human or agent runs it.

---

### 7. Session Archaeology (`claude://`)

Reveal can query its own AI session history as structured data.

```bash
# List recent sessions
reveal claude://sessions/

# What files did I touch in a session?
reveal claude://session/my-session-0316/files

# What tools did I use and how often?
reveal claude://session/my-session-0316/tools

# Recover context — last 3 assistant turns
reveal 'claude://session/my-session-0316?tail=3'

# Search a session for a specific topic
reveal 'claude://session/my-session-0316?search=validate_token'

# See errors and exceptions from a session
reveal claude://session/my-session-0316/errors
```

**What you get:** Your AI work history is queryable. "When did I last touch this function? What was the context?" is now answerable from the CLI. The `/files` element shows every file read, written, and edited with operation counts — useful for understanding what a session actually changed.

---

## The Day-to-Day Core

The most-used pattern. Works across 50+ languages with zero configuration.

```bash
# What's in this directory?
reveal src/

# What's in this file? (outline: functions, classes, imports)
reveal src/auth.py

# What does this function do?
reveal src/auth.py validate_token

# What functions are most complex?
reveal 'ast://src/?sort=-complexity&limit=10'

# Find all functions over complexity 10
reveal 'ast://src/?complexity>10'

# Find all cached functions (wildcard decorator matching)
reveal 'ast://.?decorator=*cache*'

# Find large functions for refactoring candidates
reveal 'ast://src/?lines>50&sort=-lines'

# Who wrote this function? (semantic blame)
reveal 'git://src/auth.py?type=blame&element=validate_token'
```

**What you get:** The `reveal file.py → reveal file.py function` loop trains a better workflow reflex than `cat`. The breadcrumbs mean you never have to remember syntax. Wildcard decorator matching (`*cache*` → matches `@lru_cache`, `@cached_property`, `@cache`) finds patterns without knowing exact names.

---

## The Architecture Point

| Design choice | What it enables |
|---|---|
| URI-as-language | Same query syntax across all resources — code, infra, data, docs |
| Universal operators (`=`, `~=`, `>`, `!`, `..`, `*`) | Filter expressions transfer across adapters without learning new syntax |
| `--stdin` piping | Output of one adapter is input to the next |
| Structured JSON output | Every query is composable with `jq`, scripts, and AI agents |
| Exit code discipline (0/1/2) | Every check is a valid CI gate with no configuration |
| Token budgeting | First-class LLM context constraint, not a workaround |
| `reveal://` self-reference | The tool introspects itself using its own syntax |

---

## Things Nobody Else Does

1. **`calls://src/?uncalled`** — dead code detection from the CLI. Pure set-difference: defined functions minus everything in the callers index. No IDE, no plugin, no config. Private functions flagged separately; decorators like `@property` excluded.

2. **`?rank=callers`** — coupling metrics from the CLI. Not "who calls this" but "what is most called across the project." Graph analysis, not search.

3. **`reveal health` spanning code + certs + DB + DNS** — a category collapse. One command, one JSON blob, one exit code.

4. **`reveal pack --since <branch> --budget N`** — PR-aware codebase snapshots. Changed files boosted to priority tier 0; remaining budget fills with entry points and complexity leaders. Built for agents, not retrofitted.

5. **`markdown://docs/?link-graph`** — bidirectional doc link analysis with orphan detection. Rare in any tool category.

6. **`?depth=N` transitive call graphs** — callers-of-callers up to 5 levels. Impact radius before a refactor, not just immediate callers.

7. **`complexity_delta` on every changed function** — `diff://` carries before/after complexity for each modified function. "Did this PR make anything harder to maintain?" is now a scriptable CI check.

8. **`?decorator=*cache*` wildcard matching** — surfaces patterns across a codebase without knowing exact names.

9. **`claude://sessions/` session archaeology** — your AI work history as queryable structured data.

10. **Native MCP server (`reveal-mcp`)** — exposes all reveal capabilities as MCP tools for Claude Code, Cursor, and Windsurf. One install, five tools: `reveal_structure`, `reveal_element`, `reveal_query`, `reveal_pack`, `reveal_check`. Agents get progressive disclosure and call-graph analysis without subprocess overhead.

---

## Adapters at a Glance

| Adapter | What it queries |
|---|---|
| `ast://` | Functions, classes, complexity, decorators — 190+ languages |
| `calls://` | Cross-file call graph with coupling metrics |
| `stats://` | Codebase quality scores, hotspots, duplication |
| `imports://` | Dependency graph, circular imports, unused imports |
| `diff://` | Structural diff between branches, commits, or files |
| `git://` | Commits, blame, branches, tags, function-level history |
| `autossl://` | cPanel AutoSSL run logs — per-domain TLS outcomes, DCV failures |
| `ssl://` | Certificate expiry, chain validation, hostname match |
| `mysql://` | Schema, replication status, table analysis |
| `sqlite://` | Schema, query analysis |
| `domain://` | DNS, WHOIS, registrar, HTTPS availability |
| `nginx://` | Config parsing, ACL rules, upstream routing, ACME |
| `cpanel://` | User environment, domains, SSL, ACL health |
| `markdown://` | Frontmatter, headings, link graphs, body search |
| `json://` | JMESPath queries, nested navigation |
| `env://` | Environment variable analysis, `.env` validation |
| `python://` | Runtime introspection of live Python modules |
| `xlsx://` | Excel data extraction and analysis |
| `claude://` | AI session history, tool usage, file access patterns |
| `reveal://` | Reveal introspects itself: adapters, rules, config |
| `help://` | Built-in documentation, searchable from the CLI |

---

**Navigation**: [INDEX.md](INDEX.md) | [QUICK_START.md](QUICK_START.md) | [RECIPES.md](RECIPES.md) | [AGENT_HELP.md](AGENT_HELP.md)
