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

- **New users** → [QUICK_START.md](QUICK_START.md) → [RECIPES.md](RECIPES.md)
- **Adapters** → See [Adapter Guides](#adapter-guides-17-files) below
- **nginx / cPanel operator** → [NGINX_GUIDE.md](NGINX_GUIDE.md) | [CPANEL_ADAPTER_GUIDE.md](CPANEL_ADAPTER_GUIDE.md)
- **AI Agents** → [AGENT_HELP.md](AGENT_HELP.md) (2824 lines)
- **Developers** → [Development Guides](#development-guides-4-files)

---

## User Guides (8 files)

| File | Lines | Description |
|------|-------|-------------|
| [README.md](README.md) | 147 | Documentation overview and navigation |
| [WHY_REVEAL.md](WHY_REVEAL.md) | — | What makes Reveal powerful — key capabilities with examples |
| [QUICK_START.md](QUICK_START.md) | 374 | 5-minute introduction for new users |
| [BENCHMARKS.md](BENCHMARKS.md) | — | Measured 3.9–33x token reduction — 5 real scenarios with exact numbers |
| [MCP_SETUP.md](MCP_SETUP.md) | — | MCP server setup for Claude Code, Cursor, Windsurf — 5 tools, stdio/SSE transports |
| [CI_RECIPES.md](CI_RECIPES.md) | — | GitHub Actions and GitLab CI ready-to-paste YAML: PR review, complexity gate, hotspot tracking, SSL checks |
| [RECIPES.md](RECIPES.md) | 1255 | Task-based workflows and common patterns |
| [CODEBASE_REVIEW.md](CODEBASE_REVIEW.md) | 1386 | Complete codebase review workflows |

**Total**: ~4,100 lines

---

## Adapter Guides (17 files)

Complete guides for all URI protocol adapters (~23,300 lines).
`XLSX_POWERBI_EXPANSION.md` is also listed here as a roadmap reference (not a usage guide).

| File | Lines | Purpose |
|------|-------|---------|
| [AST_ADAPTER_GUIDE.md](AST_ADAPTER_GUIDE.md) | 1329 | AST-based code analysis with complexity/size filtering |
| [CALLS_ADAPTER_GUIDE.md](CALLS_ADAPTER_GUIDE.md) | 622 | Cross-file call graph queries (calls://) |
| [CLAUDE_ADAPTER_GUIDE.md](CLAUDE_ADAPTER_GUIDE.md) | 2321 | Claude CLI session analysis and tool usage tracking |
| [CPANEL_ADAPTER_GUIDE.md](CPANEL_ADAPTER_GUIDE.md) | 328 | cPanel user environment: domains, SSL, ACL health |
| [DIFF_ADAPTER_GUIDE.md](DIFF_ADAPTER_GUIDE.md) | 1948 | Git diff analysis and structure comparison |
| [DOMAIN_ADAPTER_GUIDE.md](DOMAIN_ADAPTER_GUIDE.md) | 2297 | Domain/DNS/WHOIS information analysis |
| [ENV_ADAPTER_GUIDE.md](ENV_ADAPTER_GUIDE.md) | 1351 | Environment variable analysis and validation |
| [GIT_ADAPTER_GUIDE.md](GIT_ADAPTER_GUIDE.md) | 1880 | Git repository analysis (commits, branches, tags) |
| [IMPORTS_ADAPTER_GUIDE.md](IMPORTS_ADAPTER_GUIDE.md) | 1639 | Import dependency analysis across languages |
| [JSON_ADAPTER_GUIDE.md](JSON_ADAPTER_GUIDE.md) | 1327 | JSON/JSONL data analysis with JMESPath queries |
| [MYSQL_ADAPTER_GUIDE.md](MYSQL_ADAPTER_GUIDE.md) | 2116 | MySQL database introspection and schema analysis |
| [PYTHON_ADAPTER_GUIDE.md](PYTHON_ADAPTER_GUIDE.md) | 464 | Python runtime introspection (modules, objects) |
| [REVEAL_ADAPTER_GUIDE.md](REVEAL_ADAPTER_GUIDE.md) | 536 | Reveal introspection (analyzers, adapters, config) |
| [SQLITE_ADAPTER_GUIDE.md](SQLITE_ADAPTER_GUIDE.md) | 1161 | SQLite database introspection and schema analysis |
| [SSL_ADAPTER_GUIDE.md](SSL_ADAPTER_GUIDE.md) | 1488 | SSL/TLS certificate analysis and validation |
| [STATS_ADAPTER_GUIDE.md](STATS_ADAPTER_GUIDE.md) | 1874 | Codebase statistics and metrics collection |
| [XLSX_ADAPTER_GUIDE.md](XLSX_ADAPTER_GUIDE.md) | 651 | Excel/XLSX file analysis and data extraction |
| [XLSX_POWERBI_EXPANSION.md](XLSX_POWERBI_EXPANSION.md) | — | Gap analysis and roadmap: Power Query, named ranges, pivot tables, connections, VBA, pbix/pbit/bim |

**Total**: ~23,300 lines

**Adapters without dedicated guides** (covered elsewhere or minimal):
- `autossl://` — see [NGINX_GUIDE.md](NGINX_GUIDE.md) (cPanel AutoSSL logs)
- `markdown://` — see [MARKDOWN_GUIDE.md](MARKDOWN_GUIDE.md) under Analyzer Guides
- `nginx://` — see [NGINX_GUIDE.md](NGINX_GUIDE.md)
- `demo://` — example/testing adapter, no guide needed
- `help://` — meta-adapter for in-tool help; use `reveal help://` to explore

---

## Analyzer Guides (5 files)

Language and infrastructure analyzer guides:

| File | Lines | Description |
|------|-------|-------------|
| [ANALYZER_PATTERNS.md](ANALYZER_PATTERNS.md) | 821 | Code analysis patterns and best practices |
| [ELIXIR_ANALYZER_GUIDE.md](ELIXIR_ANALYZER_GUIDE.md) | 76 | Elixir language analyzer guide |
| [HTML_GUIDE.md](HTML_GUIDE.md) | 401 | HTML analysis and template extraction |
| [MARKDOWN_GUIDE.md](MARKDOWN_GUIDE.md) | 852 | Markdown analysis, headings, and frontmatter |
| [NGINX_GUIDE.md](NGINX_GUIDE.md) | — | nginx:// adapter + config file analyzer (N001–N007 rules, ACME/SSL audits) |

**Total**: ~2,555 lines

---

## Reference Documentation (10 files)

Core reference and technical specifications:

| File | Lines | Description |
|------|-------|-------------|
| [QUERY_SYNTAX_GUIDE.md](QUERY_SYNTAX_GUIDE.md) | 762 | Universal query operators and result control |
| [QUERY_PARAMETER_REFERENCE.md](QUERY_PARAMETER_REFERENCE.md) | 363 | Query parameters for all adapters |
| [FIELD_SELECTION_GUIDE.md](FIELD_SELECTION_GUIDE.md) | 658 | Token reduction with --fields and budgets |
| [ELEMENT_DISCOVERY_GUIDE.md](ELEMENT_DISCOVERY_GUIDE.md) | 701 | Progressive disclosure with available_elements |
| [OUTPUT_CONTRACT.md](OUTPUT_CONTRACT.md) | 678 | JSON output specification |
| [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md) | 662 | Configuration options and .reveal.yaml |
| [CLI_INTEGRATION_GUIDE.md](CLI_INTEGRATION_GUIDE.md) | 281 | CLI integration patterns |
| [HELP_SYSTEM_GUIDE.md](HELP_SYSTEM_GUIDE.md) | 397 | Help system internals (help:// adapter) |
| [DUPLICATE_DETECTION_GUIDE.md](DUPLICATE_DETECTION_GUIDE.md) | 499 | Duplicate detection algorithms |
| [SCHEMA_VALIDATION_HELP.md](SCHEMA_VALIDATION_HELP.md) | 620 | Frontmatter schema validation |

**Total**: ~6,300 lines

---

## Subcommand Guides (1 file)

Reference guides for all reveal subcommands (`check`, `deps`, `dev`, `health`, `hotspots`, `overview`, `pack`, `review`, `scaffold`):

| File | Lines | Description |
|------|-------|-------------|
| [SUBCOMMANDS_GUIDE.md](SUBCOMMANDS_GUIDE.md) | — | All subcommand reference: `check`, `deps`, `dev`, `health`, `hotspots`, `overview`, `pack`, `review`, `scaffold` |

---

## Development Guides (4 files)

For contributors and adapter authors:

| File | Lines | Description |
|------|-------|-------------|
| [../../ARCHITECTURE.md](../../ARCHITECTURE.md) | 312 | **Start here**: URI routing, adapter lifecycle, output contract, query pipeline, help tiers, subcommand model |
| [ADAPTER_AUTHORING_GUIDE.md](ADAPTER_AUTHORING_GUIDE.md) | 454 | Create custom adapters |
| [ADAPTER_CONSISTENCY.md](ADAPTER_CONSISTENCY.md) | 388 | Adapter UX patterns and consistency |
| [SCAFFOLDING_GUIDE.md](SCAFFOLDING_GUIDE.md) | 390 | CLI scaffolding system |

**Total**: ~1,542 lines

---

## AI Agent Reference (1 file)

Complete reference for AI agent integration:

| File | Lines | Description |
|------|-------|-------------|
| [AGENT_HELP.md](AGENT_HELP.md) | 2824 | Complete AI agent reference (~68KB) |

**Total**: 2,824 lines

---

## Documentation Statistics

**By Category**:
- Adapter Guides: 17 guides + 1 roadmap (XLSX_POWERBI_EXPANSION), ~23,300 lines (57%)
- Reference: 10 files, ~5,800 lines (14%)
- User Guides: 8 files, ~4,100 lines (10%)
- AI Agent: 1 file, ~2,824 lines (7%)
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
- "What can Reveal do?" → [RECIPES.md](RECIPES.md)
- "How do I use X adapter?" → [Adapter Guides](#adapter-guides-17-files)
- "How do queries work?" → [QUERY_SYNTAX_GUIDE.md](QUERY_SYNTAX_GUIDE.md)
- "For AI agents?" → [AGENT_HELP.md](AGENT_HELP.md)
- "How does Reveal work internally?" → [ARCHITECTURE.md](../../ARCHITECTURE.md)
- "Create custom adapter?" → [ADAPTER_AUTHORING_GUIDE.md](ADAPTER_AUTHORING_GUIDE.md)

**By Adapter**:
Use `reveal help://` to list all adapters, or see [Adapter Guides](#adapter-guides-17-files) above.

---

## Maintenance Notes

**Internal Documentation**:
Internal maintainer documentation (planning, research, architecture) is maintained separately outside the public repository.

---

**Last Updated**: 2026-03-18 (Session: foggy-flood-0318)
**Navigation**: [README](README.md) | [Project Root](../../README.md)
