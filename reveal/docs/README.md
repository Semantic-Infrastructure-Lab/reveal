# Reveal Documentation

Comprehensive guides for users, developers, and AI agents.

## Quick Start by Role

### New Users

1. [QUICK_START.md](QUICK_START.md) - 5-minute introduction
2. [RECIPES.md](RECIPES.md) - Task-based workflows
3. [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md) - Customize behavior

### Developers & Contributors

1. [ADAPTER_AUTHORING_GUIDE.md](ADAPTER_AUTHORING_GUIDE.md) - Create custom adapters
2. [ANALYZER_PATTERNS.md](ANALYZER_PATTERNS.md) - Code analysis patterns
3. [REVEAL_ADAPTER_GUIDE.md](REVEAL_ADAPTER_GUIDE.md) - Reference implementation

### AI Agents

1. [AGENT_HELP.md](AGENT_HELP.md) - Complete reference (~45KB)

**For CLI:** `reveal --agent-help` loads the quick reference directly.

---

## Documentation Index

### Core Guides

| Guide | Purpose |
|-------|---------|
| [QUICK_START.md](QUICK_START.md) | 5-minute introduction |
| [RECIPES.md](RECIPES.md) | Task-based workflows and patterns |
| [QUERY_SYNTAX_GUIDE.md](QUERY_SYNTAX_GUIDE.md) | **Phase 3** - Universal query operators and result control |
| [FIELD_SELECTION_GUIDE.md](FIELD_SELECTION_GUIDE.md) | **Phase 4** - Token reduction with --fields and budget constraints |
| [ELEMENT_DISCOVERY_GUIDE.md](ELEMENT_DISCOVERY_GUIDE.md) | **Phase 5** - Progressive disclosure with available_elements |
| [QUERY_PARAMETER_REFERENCE.md](QUERY_PARAMETER_REFERENCE.md) | Query parameters for all adapters |
| [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md) | Configuration options |
| [CODEBASE_REVIEW.md](CODEBASE_REVIEW.md) | Complete codebase review workflows |

### Adapter Guides

Complete guides for all URI adapters:

| Adapter | Purpose | Lines |
|---------|---------|-------|
| [AST_ADAPTER_GUIDE.md](AST_ADAPTER_GUIDE.md) | AST-based code analysis with complexity/size filtering | 1188 |
| [CLAUDE_ADAPTER_GUIDE.md](CLAUDE_ADAPTER_GUIDE.md) | Claude CLI session analysis and tool usage | 2182 |
| [DIFF_ADAPTER_GUIDE.md](DIFF_ADAPTER_GUIDE.md) | Git diff analysis and structure comparison | 1928 |
| [DOMAIN_ADAPTER_GUIDE.md](DOMAIN_ADAPTER_GUIDE.md) | Domain/DNS/WHOIS analysis | 2293 |
| [ENV_ADAPTER_GUIDE.md](ENV_ADAPTER_GUIDE.md) | Environment variable analysis | 1347 |
| [GIT_ADAPTER_GUIDE.md](GIT_ADAPTER_GUIDE.md) | Git repository analysis (commits, branches, tags) | 1870 |
| [IMPORTS_ADAPTER_GUIDE.md](IMPORTS_ADAPTER_GUIDE.md) | Import dependency analysis | 1630 |
| [JSON_ADAPTER_GUIDE.md](JSON_ADAPTER_GUIDE.md) | JSON/JSONL data analysis with JMESPath | 1323 |
| [MYSQL_ADAPTER_GUIDE.md](MYSQL_ADAPTER_GUIDE.md) | MySQL database introspection | 2107 |
| [PYTHON_ADAPTER_GUIDE.md](PYTHON_ADAPTER_GUIDE.md) | Python runtime introspection | 460 |
| [REVEAL_ADAPTER_GUIDE.md](REVEAL_ADAPTER_GUIDE.md) | Reveal introspection (analyzers, adapters) | 532 |
| [SQLITE_ADAPTER_GUIDE.md](SQLITE_ADAPTER_GUIDE.md) | SQLite database introspection | 1157 |
| [SSL_ADAPTER_GUIDE.md](SSL_ADAPTER_GUIDE.md) | SSL/TLS certificate analysis | 1449 |
| [STATS_ADAPTER_GUIDE.md](STATS_ADAPTER_GUIDE.md) | Codebase statistics and metrics | 1864 |
| [XLSX_ADAPTER_GUIDE.md](XLSX_ADAPTER_GUIDE.md) | Excel/XLSX file analysis | 564 |

### Analyzer Guides

| Guide | Purpose |
|-------|---------|
| [ANALYZER_PATTERNS.md](ANALYZER_PATTERNS.md) | Code analysis patterns and best practices |
| [ELIXIR_ANALYZER_GUIDE.md](ELIXIR_ANALYZER_GUIDE.md) | Elixir language analyzer |
| [HTML_GUIDE.md](HTML_GUIDE.md) | HTML analysis and templates |
| [MARKDOWN_GUIDE.md](MARKDOWN_GUIDE.md) | Markdown analysis and extraction |

### Format & Validation

| Guide | Purpose |
|-------|---------|
| [SCHEMA_VALIDATION_HELP.md](SCHEMA_VALIDATION_HELP.md) | Frontmatter schema validation |
| [OUTPUT_CONTRACT.md](OUTPUT_CONTRACT.md) | JSON output specification |
| [DUPLICATE_DETECTION_GUIDE.md](DUPLICATE_DETECTION_GUIDE.md) | Duplicate detection algorithms |

### Development Guides

| Guide | Purpose |
|-------|---------|
| [ADAPTER_CONSISTENCY.md](ADAPTER_CONSISTENCY.md) | **New** - Adapter UX patterns and consistency |
| [ADAPTER_AUTHORING_GUIDE.md](ADAPTER_AUTHORING_GUIDE.md) | Create custom adapters |
| [ANALYZER_PATTERNS.md](ANALYZER_PATTERNS.md) | Analyzer development patterns |
| [REVEAL_ADAPTER_GUIDE.md](REVEAL_ADAPTER_GUIDE.md) | Reference implementation |
| [PYTHON_ADAPTER_GUIDE.md](PYTHON_ADAPTER_GUIDE.md) | python:// adapter guide |
| [HELP_SYSTEM_GUIDE.md](HELP_SYSTEM_GUIDE.md) | Help system internals |
| [DUPLICATE_DETECTION_GUIDE.md](DUPLICATE_DETECTION_GUIDE.md) | Duplicate detection |

### AI Agent Reference

| Guide | Purpose |
|-------|---------|
| [AGENT_HELP.md](AGENT_HELP.md) | Complete AI agent reference |

---

## Common Tasks

**Analyze a file?**
→ `reveal file.py` for structure, `reveal file.py func` for extraction

**Find complex code?**
→ `reveal 'ast://./src?complexity>10'` - see [RECIPES.md](RECIPES.md)

**Validate frontmatter?**
→ `reveal file.md --validate-schema hugo` - see [SCHEMA_VALIDATION_HELP.md](SCHEMA_VALIDATION_HELP.md)

**Review a codebase?**
→ See [CODEBASE_REVIEW.md](CODEBASE_REVIEW.md) for complete workflows

**Create custom adapter?**
→ See [ADAPTER_AUTHORING_GUIDE.md](ADAPTER_AUTHORING_GUIDE.md)

---

## Getting Help

```bash
reveal --help                    # CLI reference
reveal --agent-help              # AI agent quick reference
reveal help://                   # List all help topics
reveal help://ast                # Adapter-specific help
```

---

## For Contributors

See [CONTRIBUTING.md](../../CONTRIBUTING.md) in the project root for contribution guidelines.

Internal maintainer documentation (planning, research, architecture) is maintained separately outside the public repository.

---

**Last updated:** 2026-02-15

[← Project README](../../README.md)
