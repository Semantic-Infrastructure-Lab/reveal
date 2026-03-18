# Reveal

**Reveal is how AI agents understand codebases without wasting tokens.**

A local-first, adapter-driven semantic inspection layer — progressive disclosure enforced by design. One CLI, 22 URI adapters, 190+ languages. Structure before content, always. Engineers and AI systems use the same tool, the same syntax, the same progressive drill-down.

```bash
reveal src/auth.py validate_token           # What does this function do?
reveal 'calls://src/?target=validate_token' # Who calls it? (cross-file)
reveal 'calls://src/?uncalled'              # What's dead code?
reveal 'ast://src/?complexity>10'           # What's too complex?
reveal health ssl://api.example.com domain://example.com ./src  # One-shot health check
reveal pack src/ --since main --budget 8000 # PR context snapshot for AI agents
```

## Installation

```bash
pip install reveal-cli
```

## What Makes It Different

**Progressive disclosure — the only way in.** `dir → file → element` isn't optional; it's the architecture. You cannot accidentally dump 7,000 tokens of raw code.

```bash
reveal src/                          # tree structure (~50-200 tokens)
reveal src/auth.py                   # imports, functions, classes (~200-500 tokens)
reveal src/auth.py validate_token    # exact code (~100-300 tokens)
```

**Local-first.** No backend, no API keys, no data leaving the machine. Runs in CI/CD pipelines, air-gapped environments, and anywhere you'd use a Unix tool.

**Everything is a URI.** `ast://`, `calls://`, `ssl://`, `mysql://`, `markdown://`, `claude://` — same query operators, same output format, same piping model across all of them.

**Dead code detection from the CLI:**
```bash
reveal 'calls://src/?uncalled'             # functions defined but never called
reveal 'calls://src/?rank=callers&top=20'  # most architecturally coupled functions
reveal 'calls://src/?target=fn&depth=3'    # full impact radius before a refactor
```

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

**AI session history as structured data:**
```bash
reveal claude://sessions/                          # list all sessions
reveal claude://session/my-session-0316/files     # what files were touched
reveal 'claude://sessions/?search=validate_token' # cross-session search
reveal 'claude://session/my-session-0316?tail=3'  # recover last 3 turns
```

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
reveal hotspots src/           # top complexity hotspots
reveal overview .              # one-glance dashboard: stats, quality, git activity
reveal deps .                  # dependency health: circular imports, unused, packages
reveal dev new-adapter <name>  # scaffold new adapters/rules
```

## Adapters (22 built-in)

| Adapter | What it queries |
|---------|-----------------|
| `ast://` | Functions, classes, complexity, decorators — 190+ languages |
| `calls://` | Cross-file call graph: callers, callees, coupling metrics, dead code |
| `diff://` | Structural diff between branches or commits (with per-function complexity delta) |
| `imports://` | Dependency graph, circular imports, unused imports |
| `stats://` | Codebase quality scores, hotspots, duplication |
| `git://` | Commits, blame, branches, tags, function-level history |
| `ssl://` | Certificate expiry, chain validation, hostname match |
| `autossl://` | cPanel AutoSSL run logs — per-domain TLS outcomes, DCV failures |
| `domain://` | DNS, WHOIS, registrar, HTTP redirect chain, email DNS |
| `nginx://` | Config parsing, ACL rules, upstream routing, ACME validation |
| `cpanel://` | User environment, domains, SSL health, ACL audit |
| `mysql://` | Schema, replication status, table analysis |
| `sqlite://` | Schema, query analysis |
| `markdown://` | Frontmatter, headings, link graphs, full-text search |
| `json://` | JMESPath queries, nested navigation, flatten |
| `env://` | Environment variable analysis, `.env` validation |
| `python://` | Runtime introspection of live Python modules |
| `xlsx://` | Excel data extraction and analysis |
| `claude://` | AI session history, tool usage, file access patterns |
| `reveal://` | Reveal introspects itself: adapters, rules, config |
| `help://` | Built-in documentation, searchable from the CLI |

## Documentation

- **[Why Reveal](reveal/docs/WHY_REVEAL.md)** — what makes it powerful
- **[Quick Start](reveal/docs/QUICK_START.md)** — 5-minute introduction
- **[MCP Server](reveal/docs/MCP_SETUP.md)** — native integration with Claude Code, Cursor, Windsurf
- **[CI/CD Recipes](reveal/docs/CI_RECIPES.md)** — GitHub Actions and GitLab CI ready-to-paste YAML
- **[Benchmarks](reveal/docs/BENCHMARKS.md)** — measured 3.9–33x token reduction on real scenarios
- **[Recipes](reveal/docs/RECIPES.md)** — task-based workflows
- **[All Docs](reveal/docs/INDEX.md)** — complete documentation index
- **AI Agents**: `reveal --agent-help`

## License

See [LICENSE](LICENSE) for details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
