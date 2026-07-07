# Reveal

**Reveal is how AI agents understand codebases without wasting tokens.**

A local-first, adapter-driven semantic inspection layer — progressive disclosure enforced by design. One CLI, 25 URI adapters, 85 languages. Structure before content, always. Engineers and AI systems use the same tool, the same syntax, the same progressive drill-down.

```bash
reveal src/auth.py validate_token           # What does this function do?
reveal 'calls://src/?target=validate_token' # Who calls it? (cross-file)
reveal overview .                           # one-glance dashboard: quality, activity, deps
reveal 'ast://src/?complexity>10'           # What's too complex?
reveal health ssl://api.example.com domain://example.com ./src  # One-shot health check
reveal pack src/ --since main --budget 8000 # PR context snapshot for AI agents
```

## Installation

```bash
pip install reveal-cli
```

**Windows on a managed/locked-down machine?** If Application Control Policy blocks the pip-generated `reveal.exe` launcher, run `python -m reveal` instead — it uses the same install, just skips the blocked wrapper.

## What Makes It Different

**Progressive disclosure — the only way in.** `dir → file → element` isn't optional; it's the architecture. You cannot accidentally dump 7,000 tokens of raw code.

```bash
reveal src/                          # tree structure (~50-200 tokens)
reveal src/auth.py                   # imports, functions, classes (~200-500 tokens)
reveal src/auth.py validate_token    # exact code (~100-300 tokens)
```

**Local-first.** No backend, no API keys, no data leaving the machine. Runs in CI/CD pipelines, air-gapped environments, and anywhere you'd use a Unix tool.

**Everything is a URI.** `ast://`, `calls://`, `ssl://`, `mysql://`, `markdown://`, `claude://` — same query operators, same output format, same piping model across all of them.

**Cross-file call graph analysis:**
```bash
reveal 'calls://src/?target=fn&depth=3'    # full impact radius before a refactor
reveal 'calls://src/?rank=callers&top=20'  # most architecturally coupled functions
reveal 'calls://src/?uncalled'             # functions with no callers — rough check, verify results
```

**Deep-dive code navigation (works on Python, PHP, and 80+ other tree-sitter languages):**
```bash
reveal app.py process_batch --boundary       # inputs read, outputs/effects produced
reveal app.py process_batch --sideeffects    # DB / HTTP / FS / logging calls, classified
reveal app.py process_batch --deps           # what this range depends on (params, externals)
reveal app.py process_batch --mutations      # values written here, where they're next read
reveal app.py :123 --around                  # nearby context from a line number / stack trace
reveal app.py process_batch --ifmap          # control-flow skeleton (branches + early exits)
reveal legacy.php :120-340 --boundary        # same flags work on flat PHP, not just OO
```
Pinpoint inspection inside a single function or line range — built for triaging giant handlers, legacy files, and stack traces without reading top-to-bottom. See [`AGENT_HELP.md`](reveal/docs/AGENT_HELP.md) for the full nav-flag family.

**PR-aware context snapshots for AI agents:**
```bash
reveal pack src/ --since main --budget 8000   # changed files first, then key dependencies
reveal pack src/ --focus "auth" --budget 6000 # topic-focused snapshot
```

**Composable pipelines:**
```bash
# nginx config → extract all domains → check each SSL cert
reveal nginx.conf --extract domains | sed 's/^/ssl:\/\//' | reveal --stdin --check

# Find functions that got more complex in this PR
reveal diff://git://main/.:git://HEAD/. --format json | \
  jq '.diff.functions[] | select(.complexity_delta > 5)'

# Batch SSL check from a file of domains
reveal @domains.txt --check
```

**Native MCP server (`reveal-mcp`) for AI agent integration:**
```bash
# Install once, works in Claude Code, Cursor, Windsurf, any MCP-compatible agent
pip install reveal-cli
reveal-mcp  # starts the server
# Six tools: reveal_structure, reveal_element, reveal_nav, reveal_query, reveal_pack, reveal_check
# Agents get progressive disclosure, deep-dive nav, and call-graph analysis — no subprocess overhead
```

**Unified health checks across categories:**
```bash
reveal health ./src ssl://api.example.com domain://example.com mysql://prod
# → code quality + cert expiry + DNS health + DB replication, one exit code
```

**Documentation as a queryable graph:**
```bash
reveal 'markdown://docs/?aggregate=type'         # taxonomy frequency table
reveal 'markdown://docs/?link-graph'             # bidirectional link analysis + orphan detection
reveal 'markdown://docs/?body-contains=retry&type=procedure'  # full-text + metadata
```

**AI session history as structured data** *(useful for workflows built on Claude Code)*:
```bash
reveal claude://sessions/                          # list all sessions
reveal 'claude://sessions/?search=validate_token' # cross-session search
```

## Using Reveal with AI Agents

Add to your `CLAUDE.md` or `AGENTS.md` so agents discover all adapters at setup time, not mid-task:

```md
## Reveal Usage

Reveal is a structured resource explorer. Before broad discovery searches over
a supported resource, check whether Reveal has an adapter — not just for source
code, but for sessions, git history, documents, data stores, and runtime state.

| Need | Adapter | Example |
|------|---------|---------|
| Code structure / functions | `ast://` | `reveal ast://src/?type=function` |
| Call relationships | `calls://` | `reveal 'calls://src/?target=my_fn'` |
| Imports / change impact | `imports://` `depends://` | `reveal imports://src/` |
| Git history / diffs | `git://` `diff://` | `reveal 'git://.?message~=fix'` |
| Claude sessions / prompts | `claude://` | `reveal 'claude://sessions/?search=auth-refactor'` |
| Codex CLI sessions | `codex://` | `reveal 'codex://sessions/?search=auth-refactor'` |
| Markdown / docs | `markdown://` | `reveal docs/ --grep 'decision'` |
| Databases / workbooks | `sqlite://` `mysql://` `xlsx://` | `reveal sqlite:///app.db` |
| Environment / runtime | `env://` `python://` | `reveal env://` |
| Project-specific tools | live plugins | `reveal help://adapters` |

When adapter syntax is uncertain:
1. `reveal help://quick` — compact intent router (~300 tokens)
2. `reveal help://schemas/<adapter> --format=json` — exact query params
3. Prefer scoped, bounded queries first; drill down as needed.
4. Confirm consequential findings by reading source or running targeted checks.
```

---

## What Reveal Does (and Doesn't)

| Reveal does | Reveal does not |
|-------------|-----------------|
| Inspect / read | Modify / write |
| Evaluate quality | Auto-fix issues |
| Package for LLMs | Run LLM inference |
| Compose workflows | Orchestrate pipelines |
| Describe itself | Require external config |

## Subcommands

```bash
reveal check src/              # quality check (complexity, maintainability, links)
reveal review main..HEAD       # PR review: diff + check + hotspots, one pass
reveal health ssl://site.com   # health check with exit codes 0/1/2
reveal pack src/ --budget 8000 # token-budgeted snapshot for LLM context
reveal pack src/ --architecture # pack + entry points + core abstractions brief
reveal hotspots src/           # top complexity hotspots (✅/⚪ test-coverage per fn)
reveal overview .              # one-glance dashboard: stats, quality, git activity
reveal deps .                  # dependency health: circular imports, unused, packages
reveal architecture src/       # architectural brief: entry points, abstractions, risks
reveal trace src/ --from main  # execution narrative from an entry point
reveal contracts src/          # ABC/Protocol/TypedDict/Pydantic inventory
reveal surface src/            # external boundary map: CLI args, routes, env vars, I/O
reveal dev new-adapter <name>  # scaffold new adapters/rules
```

## Adapters (25 built-in)

| Adapter | What it queries |
|---------|-----------------|
| `ast://` | Functions, classes, complexity, decorators — 85 languages |
| `calls://` | Cross-file call graph: callers, callees, coupling metrics, dead code |
| `depends://` | Inverse module dependency graph: who imports this module |
| `diff://` | Structural diff between branches or commits (with per-function complexity delta) |
| `imports://` | Dependency graph, circular imports, unused imports |
| `stats://` | Codebase quality scores, hotspots, duplication |
| `git://` | Commits, blame, branches, tags, function-level history |
| `ssl://` | Certificate expiry, chain validation, hostname match |
| `autossl://` | cPanel AutoSSL run logs — per-domain TLS outcomes, DCV failures |
| `letsencrypt://` | Let's Encrypt certbot live certificates — expiry, multi-domain, renewal status |
| `domain://` | DNS, WHOIS, registrar, HTTP redirect chain, email DNS |
| `nginx://` | Config parsing, ACL rules, upstream routing, ACME validation |
| `cpanel://` | User environment, domains, SSL health, ACL audit |
| `mysql://` | Schema, replication status, table analysis |
| `sqlite://` | Schema, query analysis |
| `markdown://` | Frontmatter, headings, link graphs, full-text search |
| `json://` | JMESPath queries, nested navigation, flatten |
| `env://` | Environment variable analysis, `.env` validation |
| `python://` | Runtime introspection of live Python modules |
| `patches://` | Test patch pressure: repeated mocks, private patches, patch-heavy tests |
| `xlsx://` | Excel data extraction and analysis |
| `claude://` | AI session history, tool usage, file access patterns |
| `codex://` | OpenAI Codex CLI session history, tool usage, per-session analysis |
| `reveal://` | Reveal introspects itself: adapters, rules, config |
| `help://` | Built-in documentation, searchable from the CLI |

## Documentation

- **[Why Reveal](reveal/docs/WHY_REVEAL.md)** — what makes it powerful
- **[Quick Start](reveal/docs/QUICK_START.md)** — 5-minute introduction
- **[What Reveal Is Good For](reveal/docs/guides/WHAT_IS_REVEAL_GOOD_FOR.md)** — organized use cases and best-fit workflows
- **[MCP Server](reveal/docs/guides/MCP_SETUP.md)** — native integration with Claude Code, Cursor, Windsurf
- **[CI/CD Recipes](reveal/docs/guides/CI_RECIPES.md)** — GitHub Actions and GitLab CI ready-to-paste YAML
- **[Benchmarks](reveal/docs/BENCHMARKS.md)** — measured 3.9–15x token reduction on real scenarios
- **[Recipes](reveal/docs/guides/RECIPES.md)** — task-based workflows
- **[All Docs](reveal/docs/INDEX.md)** — complete documentation index
- **AI Agents**: `reveal --agent-help`

## License

See [LICENSE](LICENSE) for details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
