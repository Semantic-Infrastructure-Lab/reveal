---
title: Reveal Documentation Index
category: reference
---
# Reveal Documentation Index

**Complete catalog of all user-facing documentation**

**Last Updated**: 2026-03-18
**Total**: 48 markdown files, ~41,000 lines

---

## Quick Navigation

- **New users** → [QUICK_START.md](QUICK_START.md) → [RECIPES.md](guides/RECIPES.md)
- **Adapters** → See [Adapter Guides](#adapter-guides-19-files) below
- **nginx / cPanel operator** → [NGINX_GUIDE.md](adapters/NGINX_GUIDE.md) | [CPANEL_ADAPTER_GUIDE.md](adapters/CPANEL_ADAPTER_GUIDE.md)
- **AI Agents** → [AGENT_HELP.md](AGENT_HELP.md) (3,265 lines)
- **Developers** → [Development Guides](#development-guides-4-files)

---

## User Guides (7 files)

| File | Lines | Description |
|------|-------|-------------|
| [README.md](README.md) | 147 | Documentation overview and navigation |
| [WHY_REVEAL.md](WHY_REVEAL.md) | — | What makes Reveal powerful — key capabilities with examples |
| [QUICK_START.md](QUICK_START.md) | 374 | 5-minute introduction for new users |
| [BENCHMARKS.md](BENCHMARKS.md) | — | Measured 3.9–33x token reduction — 5 real scenarios with exact numbers |
| [MCP_SETUP.md](guides/MCP_SETUP.md) | — | MCP server setup for Claude Code, Cursor, Windsurf — 5 tools, stdio/SSE transports |
| [CI_RECIPES.md](guides/CI_RECIPES.md) | — | GitHub Actions and GitLab CI ready-to-paste YAML: PR review, complexity gate, hotspot tracking, SSL checks |
| [RECIPES.md](guides/RECIPES.md) | — | Task-based workflows, multi-adapter patterns, and real-world scenarios |

---

## Adapter Guides (19 files)

Complete guides for all URI protocol adapters.

| File | Lines | Purpose |
|------|-------|---------|
| [AST_ADAPTER_GUIDE.md](adapters/AST_ADAPTER_GUIDE.md) | 1329 | AST-based code analysis with complexity/size filtering |
| [CALLS_ADAPTER_GUIDE.md](adapters/CALLS_ADAPTER_GUIDE.md) | 622 | Cross-file call graph queries (calls://) |
| [CLAUDE_ADAPTER_GUIDE.md](adapters/CLAUDE_ADAPTER_GUIDE.md) | 2321 | Claude CLI session analysis and tool usage tracking |
| [CPANEL_ADAPTER_GUIDE.md](adapters/CPANEL_ADAPTER_GUIDE.md) | 328 | cPanel user environment: domains, SSL, ACL health |
| [DEPENDS_ADAPTER_GUIDE.md](adapters/DEPENDS_ADAPTER_GUIDE.md) | — | Reverse module dependency graph — who imports this module? |
| [DIFF_ADAPTER_GUIDE.md](adapters/DIFF_ADAPTER_GUIDE.md) | 1948 | Git diff analysis and structure comparison |
| [DOMAIN_ADAPTER_GUIDE.md](adapters/DOMAIN_ADAPTER_GUIDE.md) | 2297 | Domain/DNS/WHOIS information analysis |
| [ENV_ADAPTER_GUIDE.md](adapters/ENV_ADAPTER_GUIDE.md) | 1351 | Environment variable analysis and validation |
| [GIT_ADAPTER_GUIDE.md](adapters/GIT_ADAPTER_GUIDE.md) | 1880 | Git repository analysis (commits, branches, tags) |
| [IMPORTS_ADAPTER_GUIDE.md](adapters/IMPORTS_ADAPTER_GUIDE.md) | 1639 | Import dependency analysis across languages |
| [JSON_ADAPTER_GUIDE.md](adapters/JSON_ADAPTER_GUIDE.md) | 1327 | JSON/JSONL data analysis with JMESPath queries |
| [LETSENCRYPT_ADAPTER_GUIDE.md](adapters/LETSENCRYPT_ADAPTER_GUIDE.md) | — | Let's Encrypt cert inventory — orphan/duplicate detection |
| [MYSQL_ADAPTER_GUIDE.md](adapters/MYSQL_ADAPTER_GUIDE.md) | 2116 | MySQL database introspection and schema analysis |
| [PYTHON_ADAPTER_GUIDE.md](adapters/PYTHON_ADAPTER_GUIDE.md) | 464 | Python runtime introspection (modules, objects) |
| [REVEAL_ADAPTER_GUIDE.md](adapters/REVEAL_ADAPTER_GUIDE.md) | 536 | Reveal introspection (analyzers, adapters, config) |
| [SQLITE_ADAPTER_GUIDE.md](adapters/SQLITE_ADAPTER_GUIDE.md) | 1161 | SQLite database introspection and schema analysis |
| [SSL_ADAPTER_GUIDE.md](adapters/SSL_ADAPTER_GUIDE.md) | 1488 | SSL/TLS certificate analysis and validation |
| [STATS_ADAPTER_GUIDE.md](adapters/STATS_ADAPTER_GUIDE.md) | 1874 | Codebase statistics and metrics collection |
| [XLSX_ADAPTER_GUIDE.md](adapters/XLSX_ADAPTER_GUIDE.md) | 651 | Excel/XLSX file analysis and data extraction |

**Adapters without dedicated guides** (covered elsewhere or minimal):
- `autossl://` — see [NGINX_GUIDE.md](adapters/NGINX_GUIDE.md) (cPanel AutoSSL logs)
- `markdown://` — see [MARKDOWN_GUIDE.md](adapters/MARKDOWN_GUIDE.md) under Analyzer Guides
- `nginx://` — see [NGINX_GUIDE.md](adapters/NGINX_GUIDE.md)
- `demo://` — example/testing adapter, no guide needed
- `help://` — meta-adapter for in-tool help; use `reveal help://` to explore

---

## Analyzer Guides (5 files)

Language and infrastructure analyzer guides:

| File | Lines | Description |
|------|-------|-------------|
| [ANALYZER_PATTERNS.md](development/ANALYZER_PATTERNS.md) | 821 | Code analysis patterns and best practices |
| [ELIXIR_ANALYZER_GUIDE.md](development/ELIXIR_ANALYZER_GUIDE.md) | 76 | Elixir language analyzer guide |
| [HTML_GUIDE.md](adapters/HTML_GUIDE.md) | 401 | HTML analysis and template extraction |
| [MARKDOWN_GUIDE.md](adapters/MARKDOWN_GUIDE.md) | 852 | Markdown analysis, headings, and frontmatter |
| [NGINX_GUIDE.md](adapters/NGINX_GUIDE.md) | — | nginx:// adapter + config file analyzer (N001–N012 rules, ACME/SSL audits) |

**Total**: ~2,555 lines

---

## Reference Documentation (10 files)

Core reference and technical specifications:

| File | Lines | Description |
|------|-------|-------------|
| [QUERY_SYNTAX_GUIDE.md](guides/QUERY_SYNTAX_GUIDE.md) | 762 | Universal query operators and result control |
| [QUERY_PARAMETER_REFERENCE.md](guides/QUERY_PARAMETER_REFERENCE.md) | 363 | Query parameters for all adapters |
| [FIELD_SELECTION_GUIDE.md](guides/FIELD_SELECTION_GUIDE.md) | 658 | Token reduction with --fields and budgets |
| [ELEMENT_DISCOVERY_GUIDE.md](guides/ELEMENT_DISCOVERY_GUIDE.md) | 701 | Progressive disclosure with available_elements |
| [OUTPUT_CONTRACT.md](development/OUTPUT_CONTRACT.md) | 678 | JSON output specification |
| [CONFIGURATION_GUIDE.md](guides/CONFIGURATION_GUIDE.md) | 662 | Configuration options and .reveal.yaml |
| [CLI_INTEGRATION_GUIDE.md](development/CLI_INTEGRATION_GUIDE.md) | 281 | CLI integration patterns |
| [HELP_SYSTEM_GUIDE.md](development/HELP_SYSTEM_GUIDE.md) | 397 | Help system internals (help:// adapter) |
| [DUPLICATE_DETECTION_GUIDE.md](guides/DUPLICATE_DETECTION_GUIDE.md) | 499 | Duplicate detection algorithms |
| [SCHEMA_VALIDATION_HELP.md](guides/SCHEMA_VALIDATION_HELP.md) | 620 | Frontmatter schema validation |

**Total**: ~6,300 lines

---

## Subcommand Guides (1 file)

Reference guides for all reveal subcommands (`check`, `deps`, `dev`, `health`, `hotspots`, `overview`, `pack`, `review`, `scaffold`):

| File | Lines | Description |
|------|-------|-------------|
| [SUBCOMMANDS_GUIDE.md](guides/SUBCOMMANDS_GUIDE.md) | — | All subcommand reference: `check`, `deps`, `dev`, `health`, `hotspots`, `overview`, `pack`, `review`, `scaffold` |

---

## Development Guides (4 files)

For contributors and adapter authors:

| File | Lines | Description |
|------|-------|-------------|
| [../../ARCHITECTURE.md](../../ARCHITECTURE.md) | 312 | **Start here**: URI routing, adapter lifecycle, output contract, query pipeline, help tiers, subcommand model |
| [ADAPTER_AUTHORING_GUIDE.md](development/ADAPTER_AUTHORING_GUIDE.md) | 454 | Create custom adapters |
| [ADAPTER_CONSISTENCY.md](development/ADAPTER_CONSISTENCY.md) | 388 | Adapter UX patterns and consistency |
| [SCAFFOLDING_GUIDE.md](development/SCAFFOLDING_GUIDE.md) | 390 | CLI scaffolding system |

**Total**: ~1,542 lines

---

## AI Agent Reference (1 file)

Complete reference for AI agent integration:

| File | Lines | Description |
|------|-------|-------------|
| [AGENT_HELP.md](AGENT_HELP.md) | 3265 | Complete AI agent reference (~104KB) |

**Total**: 3,265 lines

---

## Documentation Statistics

**By Category**:
- Adapter Guides: 17 guides + 1 roadmap (XLSX_POWERBI_EXPANSION), ~23,300 lines (57%)
- Reference: 10 files, ~5,800 lines (14%)
- User Guides: 8 files, ~4,100 lines (10%)
- AI Agent: 1 file, ~3,265 lines (7%)
- Analyzer Guides: 5 files, ~2,800 lines (7%)
- Development: 4 files, ~1,600 lines (4%)
- Subcommand Guides: 1 file, ~500 lines (1%)
- Internal/WIP: 2 files (UX_ISSUES.md, REVIEW_VALIDATION_AND_IMPROVEMENTS.md — maintainer reference)

**Total**: 49 files (47 user-facing + 2 maintainer reference)

**Last Updated**: 2026-03-18 (Session: violet-brush-0318)

---

## Finding Documentation

**By Task**:
- "How do I start?" → [QUICK_START.md](QUICK_START.md)
- "What makes Reveal different?" → [WHY_REVEAL.md](WHY_REVEAL.md)
- "What can Reveal do?" → [RECIPES.md](guides/RECIPES.md)
- "How do I use X adapter?" → [Adapter Guides](#adapter-guides-19-files)
- "How do queries work?" → [QUERY_SYNTAX_GUIDE.md](guides/QUERY_SYNTAX_GUIDE.md)
- "For AI agents?" → [AGENT_HELP.md](AGENT_HELP.md)
- "How does Reveal work internally?" → [ARCHITECTURE.md](../../ARCHITECTURE.md)
- "Create custom adapter?" → [ADAPTER_AUTHORING_GUIDE.md](development/ADAPTER_AUTHORING_GUIDE.md)

**By Adapter**:
Use `reveal help://` to list all adapters, or see [Adapter Guides](#adapter-guides-19-files) above.

---

## Maintenance Notes

**Internal Documentation**:
Internal maintainer documentation (planning, research, architecture) is maintained separately outside the public repository.

---

**Last Updated**: 2026-03-18 (Session: foggy-flood-0318)
**Navigation**: [README](README.md) | [Project Root](../../README.md)
