---
title: Reveal Documentation Index
category: reference
---
# Reveal Documentation Index

**Complete catalog of all user-facing documentation**

**Last Updated**: 2026-03-03
**Total**: 44 markdown files, ~38,600 lines

---

## Quick Navigation

- **New users** → [QUICK_START.md](QUICK_START.md) → [RECIPES.md](RECIPES.md)
- **Adapters** → See [Adapter Guides](#adapter-guides-16-files) below
- **nginx / cPanel operator** → [NGINX_ANALYZER_GUIDE.md](NGINX_ANALYZER_GUIDE.md) | [CPANEL_ADAPTER_GUIDE.md](CPANEL_ADAPTER_GUIDE.md)
- **AI Agents** → [AGENT_HELP.md](AGENT_HELP.md) (2391 lines)
- **Developers** → [Development Guides](#development-guides-3-files)

---

## User Guides (4 files)

| File | Lines | Description |
|------|-------|-------------|
| [README.md](README.md) | 147 | Documentation overview and navigation |
| [QUICK_START.md](QUICK_START.md) | 374 | 5-minute introduction for new users |
| [RECIPES.md](RECIPES.md) | 1023 | Task-based workflows and common patterns |
| [CODEBASE_REVIEW.md](CODEBASE_REVIEW.md) | 1386 | Complete codebase review workflows |

**Total**: ~3,140 lines

---

## Adapter Guides (16 files)

Complete guides for all URI protocol adapters (~24,500 lines):

| File | Lines | Purpose |
|------|-------|---------|
| [AST_ADAPTER_GUIDE.md](AST_ADAPTER_GUIDE.md) | 1192 | AST-based code analysis with complexity/size filtering |
| [CALLS_ADAPTER_GUIDE.md](CALLS_ADAPTER_GUIDE.md) | — | Cross-file call graph queries (calls://) |
| [CLAUDE_ADAPTER_GUIDE.md](CLAUDE_ADAPTER_GUIDE.md) | 2316 | Claude CLI session analysis and tool usage tracking |
| [CPANEL_ADAPTER_GUIDE.md](CPANEL_ADAPTER_GUIDE.md) | 328 | cPanel user environment: domains, SSL, ACL health |
| [DIFF_ADAPTER_GUIDE.md](DIFF_ADAPTER_GUIDE.md) | 1932 | Git diff analysis and structure comparison |
| [DOMAIN_ADAPTER_GUIDE.md](DOMAIN_ADAPTER_GUIDE.md) | 2297 | Domain/DNS/WHOIS information analysis |
| [ENV_ADAPTER_GUIDE.md](ENV_ADAPTER_GUIDE.md) | 1351 | Environment variable analysis and validation |
| [GIT_ADAPTER_GUIDE.md](GIT_ADAPTER_GUIDE.md) | 1879 | Git repository analysis (commits, branches, tags) |
| [IMPORTS_ADAPTER_GUIDE.md](IMPORTS_ADAPTER_GUIDE.md) | 1639 | Import dependency analysis across languages |
| [JSON_ADAPTER_GUIDE.md](JSON_ADAPTER_GUIDE.md) | 1327 | JSON/JSONL data analysis with JMESPath queries |
| [MYSQL_ADAPTER_GUIDE.md](MYSQL_ADAPTER_GUIDE.md) | 2116 | MySQL database introspection and schema analysis |
| [PYTHON_ADAPTER_GUIDE.md](PYTHON_ADAPTER_GUIDE.md) | 464 | Python runtime introspection (modules, objects) |
| [REVEAL_ADAPTER_GUIDE.md](REVEAL_ADAPTER_GUIDE.md) | 536 | Reveal introspection (analyzers, adapters, config) |
| [SQLITE_ADAPTER_GUIDE.md](SQLITE_ADAPTER_GUIDE.md) | 1161 | SQLite database introspection and schema analysis |
| [SSL_ADAPTER_GUIDE.md](SSL_ADAPTER_GUIDE.md) | 1484 | SSL/TLS certificate analysis and validation |
| [STATS_ADAPTER_GUIDE.md](STATS_ADAPTER_GUIDE.md) | 1868 | Codebase statistics and metrics collection |
| [XLSX_ADAPTER_GUIDE.md](XLSX_ADAPTER_GUIDE.md) | 568 | Excel/XLSX file analysis and data extraction |

**Total**: ~24,500 lines

---

## Analyzer Guides (5 files)

Language and infrastructure analyzer guides:

| File | Lines | Description |
|------|-------|-------------|
| [ANALYZER_PATTERNS.md](ANALYZER_PATTERNS.md) | 821 | Code analysis patterns and best practices |
| [ELIXIR_ANALYZER_GUIDE.md](ELIXIR_ANALYZER_GUIDE.md) | 76 | Elixir language analyzer guide |
| [HTML_GUIDE.md](HTML_GUIDE.md) | 401 | HTML analysis and template extraction |
| [MARKDOWN_GUIDE.md](MARKDOWN_GUIDE.md) | 852 | Markdown analysis, headings, and frontmatter |
| [NGINX_ANALYZER_GUIDE.md](NGINX_ANALYZER_GUIDE.md) | 405 | nginx config analysis: rules, operator commands, cPanel workflows |

**Total**: ~2,555 lines

---

## Reference Documentation (11 files)

Core reference and technical specifications:

| File | Lines | Description |
|------|-------|-------------|
| [QUERY_SYNTAX_GUIDE.md](QUERY_SYNTAX_GUIDE.md) | 762 | Universal query operators and result control |
| [QUERY_PARAMETER_REFERENCE.md](QUERY_PARAMETER_REFERENCE.md) | 363 | Query parameters for all adapters |
| [UNIFIED_OPERATOR_REFERENCE.md](UNIFIED_OPERATOR_REFERENCE.md) | 670 | Operator support matrix across all 5 core adapters |
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

## Subcommand Guides (4 files)

Reference guides for `reveal check`, `review`, `health`, `pack`, and `dev` subcommands:

| File | Lines | Description |
|------|-------|-------------|
| [DEV_GUIDE.md](DEV_GUIDE.md) | 46 | `reveal dev` — scaffold adapters, rules, inspect config |
| [HEALTH_GUIDE.md](HEALTH_GUIDE.md) | 66 | `reveal health` — unified health check with exit codes |
| [PACK_GUIDE.md](PACK_GUIDE.md) | 61 | `reveal pack` — token-budgeted context snapshot |
| [REVIEW_GUIDE.md](REVIEW_GUIDE.md) | 66 | `reveal review` — PR review workflow |

**Total**: ~239 lines

---

## Development Guides (3 files)

For contributors and adapter authors:

| File | Lines | Description |
|------|-------|-------------|
| [ADAPTER_AUTHORING_GUIDE.md](ADAPTER_AUTHORING_GUIDE.md) | 454 | Create custom adapters |
| [ADAPTER_CONSISTENCY.md](ADAPTER_CONSISTENCY.md) | 388 | Adapter UX patterns and consistency |
| [SCAFFOLDING_GUIDE.md](SCAFFOLDING_GUIDE.md) | 390 | CLI scaffolding system |

**Total**: ~1,230 lines

---

## AI Agent Reference (1 file)

Complete reference for AI agent integration:

| File | Lines | Description |
|------|-------|-------------|
| [AGENT_HELP.md](AGENT_HELP.md) | 2391 | Complete AI agent reference (~62KB) |

**Total**: 2,391 lines

---

## Documentation Statistics

**By Category**:
- Adapter Guides: 16 files, ~24,500 lines (63%)
- Reference: 11 files, ~6,300 lines (16%)
- Analyzer Guides: 5 files, ~2,555 lines (7%)
- User Guides: 4 files, ~3,140 lines (8%)
- Subcommand Guides: 4 files, ~239 lines (1%)
- AI Agent: 1 file, ~2,391 lines (6%)
- Development: 3 files, ~1,230 lines (3%)

**Total**: 44 files, ~40,355 lines

**Last Updated**: 2026-03-03 (Session: gapozi-0303)

---

## Finding Documentation

**By Task**:
- "How do I start?" → [QUICK_START.md](QUICK_START.md)
- "What can Reveal do?" → [RECIPES.md](RECIPES.md)
- "How do I use X adapter?" → [Adapter Guides](#adapter-guides-16-files)
- "How do queries work?" → [QUERY_SYNTAX_GUIDE.md](QUERY_SYNTAX_GUIDE.md)
- "For AI agents?" → [AGENT_HELP.md](AGENT_HELP.md)
- "Create custom adapter?" → [ADAPTER_AUTHORING_GUIDE.md](ADAPTER_AUTHORING_GUIDE.md)

**By Adapter**:
Use `reveal help://` to list all adapters, or see [Adapter Guides](#adapter-guides-16-files) above.

---

## Maintenance Notes

**Internal Documentation**:
Internal maintainer documentation (planning, research, architecture) is maintained separately outside the public repository.

---

**Last Updated**: 2026-03-03 (Session: gapozi-0303)
**Navigation**: [README](README.md) | [Project Root](../../README.md)
