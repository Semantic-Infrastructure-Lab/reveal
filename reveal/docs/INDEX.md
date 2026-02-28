---
title: Reveal Documentation Index
category: reference
---
# Reveal Documentation Index

**Complete catalog of all user-facing documentation**

**Last Updated**: 2026-02-27
**Total**: 40 markdown files, ~38,500 lines

---

## Quick Navigation

- **New users** → [QUICK_START.md](QUICK_START.md) → [RECIPES.md](RECIPES.md)
- **Adapters** → See [Adapter Guides](#adapter-guides-18-files) below
- **nginx / cPanel operator** → [NGINX_ANALYZER_GUIDE.md](NGINX_ANALYZER_GUIDE.md) | [CPANEL_ADAPTER_GUIDE.md](CPANEL_ADAPTER_GUIDE.md)
- **AI Agents** → [AGENT_HELP.md](AGENT_HELP.md) (2289 lines)
- **Developers** → [Development Guides](#development-guides-3-files)

---

## User Guides (4 files)

| File | Lines | Description |
|------|-------|-------------|
| [README.md](README.md) | 111 | Documentation overview and navigation |
| [QUICK_START.md](QUICK_START.md) | 339 | 5-minute introduction for new users |
| [RECIPES.md](RECIPES.md) | 913 | Task-based workflows and common patterns |
| [CODEBASE_REVIEW.md](CODEBASE_REVIEW.md) | 1360 | Complete codebase review workflows |

**Total**: 2,723 lines

---

## Adapter Guides (18 files)

Complete guides for all URI protocol adapters and infrastructure analyzers (~23,450 lines):

| File | Lines | Purpose |
|------|-------|---------|
| [AST_ADAPTER_GUIDE.md](AST_ADAPTER_GUIDE.md) | 1188 | AST-based code analysis with complexity/size filtering |
| [CLAUDE_ADAPTER_GUIDE.md](CLAUDE_ADAPTER_GUIDE.md) | 2182 | Claude CLI session analysis and tool usage tracking |
| [CPANEL_ADAPTER_GUIDE.md](CPANEL_ADAPTER_GUIDE.md) | 328 | cPanel user environment: domains, SSL, ACL health |
| [DIFF_ADAPTER_GUIDE.md](DIFF_ADAPTER_GUIDE.md) | 1928 | Git diff analysis and structure comparison |
| [DOMAIN_ADAPTER_GUIDE.md](DOMAIN_ADAPTER_GUIDE.md) | 2293 | Domain/DNS/WHOIS information analysis |
| [ENV_ADAPTER_GUIDE.md](ENV_ADAPTER_GUIDE.md) | 1347 | Environment variable analysis and validation |
| [GIT_ADAPTER_GUIDE.md](GIT_ADAPTER_GUIDE.md) | 1870 | Git repository analysis (commits, branches, tags) |
| [IMPORTS_ADAPTER_GUIDE.md](IMPORTS_ADAPTER_GUIDE.md) | 1630 | Import dependency analysis across languages |
| [JSON_ADAPTER_GUIDE.md](JSON_ADAPTER_GUIDE.md) | 1323 | JSON/JSONL data analysis with JMESPath queries |
| [MYSQL_ADAPTER_GUIDE.md](MYSQL_ADAPTER_GUIDE.md) | 2107 | MySQL database introspection and schema analysis |
| [PYTHON_ADAPTER_GUIDE.md](PYTHON_ADAPTER_GUIDE.md) | 460 | Python runtime introspection (modules, objects) |
| [REVEAL_ADAPTER_GUIDE.md](REVEAL_ADAPTER_GUIDE.md) | 532 | Reveal introspection (analyzers, adapters, config) |
| [SQLITE_ADAPTER_GUIDE.md](SQLITE_ADAPTER_GUIDE.md) | 1157 | SQLite database introspection and schema analysis |
| [SSL_ADAPTER_GUIDE.md](SSL_ADAPTER_GUIDE.md) | 1449 | SSL/TLS certificate analysis and validation |
| [STATS_ADAPTER_GUIDE.md](STATS_ADAPTER_GUIDE.md) | 1864 | Codebase statistics and metrics collection |
| [XLSX_ADAPTER_GUIDE.md](XLSX_ADAPTER_GUIDE.md) | 564 | Excel/XLSX file analysis and data extraction |

**Total**: ~23,050 lines

---

## Analyzer Guides (5 files)

Language and infrastructure analyzer guides:

| File | Lines | Description |
|------|-------|-------------|
| [ANALYZER_PATTERNS.md](ANALYZER_PATTERNS.md) | 817 | Code analysis patterns and best practices |
| [ELIXIR_ANALYZER_GUIDE.md](ELIXIR_ANALYZER_GUIDE.md) | 67 | Elixir language analyzer guide |
| [HTML_GUIDE.md](HTML_GUIDE.md) | 397 | HTML analysis and template extraction |
| [MARKDOWN_GUIDE.md](MARKDOWN_GUIDE.md) | 827 | Markdown analysis, headings, and frontmatter |
| [NGINX_ANALYZER_GUIDE.md](NGINX_ANALYZER_GUIDE.md) | 405 | nginx config analysis: rules, operator commands, cPanel workflows |

**Total**: ~2,513 lines

---

## Reference Documentation (11 files)

Core reference and technical specifications:

| File | Lines | Description |
|------|-------|-------------|
| [QUERY_SYNTAX_GUIDE.md](QUERY_SYNTAX_GUIDE.md) | 762 | Universal query operators and result control |
| [QUERY_PARAMETER_REFERENCE.md](QUERY_PARAMETER_REFERENCE.md) | 363 | Query parameters for all adapters |
| [UNIFIED_OPERATOR_REFERENCE.md](UNIFIED_OPERATOR_REFERENCE.md) | 670 | Operator support matrix across all 5 core adapters |
| [FIELD_SELECTION_GUIDE.md](FIELD_SELECTION_GUIDE.md) | 654 | Token reduction with --fields and budgets |
| [ELEMENT_DISCOVERY_GUIDE.md](ELEMENT_DISCOVERY_GUIDE.md) | 697 | Progressive disclosure with available_elements |
| [OUTPUT_CONTRACT.md](OUTPUT_CONTRACT.md) | 669 | JSON output specification |
| [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md) | 658 | Configuration options and .reveal.yaml |
| [CLI_INTEGRATION_GUIDE.md](CLI_INTEGRATION_GUIDE.md) | 275 | CLI integration patterns |
| [HELP_SYSTEM_GUIDE.md](HELP_SYSTEM_GUIDE.md) | 393 | Help system internals (help:// adapter) |
| [DUPLICATE_DETECTION_GUIDE.md](DUPLICATE_DETECTION_GUIDE.md) | 495 | Duplicate detection algorithms |
| [SCHEMA_VALIDATION_HELP.md](SCHEMA_VALIDATION_HELP.md) | 611 | Frontmatter schema validation |

**Total**: ~6,250 lines

---

## Development Guides (3 files)

For contributors and adapter authors:

| File | Lines | Description |
|------|-------|-------------|
| [ADAPTER_AUTHORING_GUIDE.md](ADAPTER_AUTHORING_GUIDE.md) | 450 | Create custom adapters |
| [ADAPTER_CONSISTENCY.md](ADAPTER_CONSISTENCY.md) | 385 | Adapter UX patterns and consistency |
| [SCAFFOLDING_GUIDE.md](SCAFFOLDING_GUIDE.md) | 381 | CLI scaffolding system |

**Total**: 1,216 lines

---

## AI Agent Reference (1 file)

Complete reference for AI agent integration:

| File | Lines | Description |
|------|-------|-------------|
| [AGENT_HELP.md](AGENT_HELP.md) | 2289 | Complete AI agent reference (~48KB) |

**Total**: 2,289 lines

---

## Documentation Statistics

**By Category**:
- Adapter Guides: 16 files, ~23,050 lines (60%)
- Reference: 11 files, ~6,250 lines (16%)
- Analyzer Guides: 5 files, ~2,513 lines (7%)
- User Guides: 4 files, ~2,700 lines (7%)
- AI Agent: 1 file, ~2,289 lines (6%)
- Development: 3 files, ~1,200 lines (3%)

**Total**: 40 files, ~38,500 lines

**Last Updated**: 2026-02-27 (Session: ninja-force-0227)

---

## Finding Documentation

**By Task**:
- "How do I start?" → [QUICK_START.md](QUICK_START.md)
- "What can Reveal do?" → [RECIPES.md](RECIPES.md)
- "How do I use X adapter?" → [Adapter Guides](#adapter-guides-18-files)
- "How do queries work?" → [QUERY_SYNTAX_GUIDE.md](QUERY_SYNTAX_GUIDE.md)
- "For AI agents?" → [AGENT_HELP.md](AGENT_HELP.md)
- "Create custom adapter?" → [ADAPTER_AUTHORING_GUIDE.md](ADAPTER_AUTHORING_GUIDE.md)

**By Adapter**:
Use `reveal help://` to list all adapters, or see [Adapter Guides](#adapter-guides-18-files) above.

---

## Maintenance Notes

**Internal Documentation**:
Internal maintainer documentation (planning, research, architecture) is maintained separately outside the public repository.

---

**Last Updated**: 2026-02-27 (Session: ninja-force-0227)
**Navigation**: [README](README.md) | [Project Root](../../README.md)
