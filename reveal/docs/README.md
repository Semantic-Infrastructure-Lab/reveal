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
| [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md) | Configuration options |
| [CODEBASE_REVIEW.md](CODEBASE_REVIEW.md) | Complete codebase review workflows |

### Format-Specific Guides

| Guide | Purpose |
|-------|---------|
| [MARKDOWN_GUIDE.md](MARKDOWN_GUIDE.md) | Markdown analysis and extraction |
| [HTML_GUIDE.md](HTML_GUIDE.md) | HTML analysis and templates |
| [SCHEMA_VALIDATION_HELP.md](SCHEMA_VALIDATION_HELP.md) | Frontmatter schema validation |
| [OUTPUT_CONTRACT.md](OUTPUT_CONTRACT.md) | JSON output specification |

### Development Guides

| Guide | Purpose |
|-------|---------|
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

**Last updated:** 2026-01-20

[← Project README](../../README.md)
