---
title: Reveal Documentation
category: reference
---
# Reveal Documentation

Guides for users, developers, and AI agents. The full catalog is [INDEX.md](INDEX.md); the
same material is browsable from the CLI with `reveal help://`.

## Start by role

### New users

1. [QUICK_START.md](QUICK_START.md) - 5-minute introduction
2. [RECIPES.md](guides/RECIPES.md) - Task-based workflows
3. [CONFIGURATION_GUIDE.md](guides/CONFIGURATION_GUIDE.md) - Customize behavior

### Developers and contributors

1. [ARCHITECTURE.md](../../ARCHITECTURE.md) - How reveal is put together
2. [ADAPTER_AUTHORING_GUIDE.md](development/ADAPTER_AUTHORING_GUIDE.md) - Create custom adapters
3. [ANALYZER_PATTERNS.md](development/ANALYZER_PATTERNS.md) - Code analysis patterns
4. [REVEAL_ADAPTER_GUIDE.md](adapters/REVEAL_ADAPTER_GUIDE.md) - Reference implementation

### AI agents

[AGENT_HELP.md](AGENT_HELP.md) is the complete reference. From the CLI:

```bash
reveal help://quick              # compact intent router (~1,600 tokens)
reveal --agent-help              # orientation section (~1,500 tokens)
reveal help://agent/full         # the complete reference
```

## Common tasks

**Analyze a file?** `reveal file.py` for structure, `reveal file.py func` for extraction.

**Find complex code?** `reveal 'ast://./src?complexity>10'` - see [RECIPES.md](guides/RECIPES.md).

**Validate frontmatter?** `reveal file.md --validate-schema hugo` - see [SCHEMA_VALIDATION_HELP.md](guides/SCHEMA_VALIDATION_HELP.md).

**What is Reveal best at?** See [WHAT_IS_REVEAL_GOOD_FOR.md](guides/WHAT_IS_REVEAL_GOOD_FOR.md).

**Use one adapter?** Each URI adapter has a guide under `adapters/`; `reveal 'help://<adapter>'` prints it.

**Create a custom adapter?** See [ADAPTER_AUTHORING_GUIDE.md](development/ADAPTER_AUTHORING_GUIDE.md).

## Getting help

```bash
reveal --help                    # CLI reference
reveal help://                   # List all help topics and adapters
reveal help://ast                # Adapter-specific help
```

## For contributors

See [CONTRIBUTING.md](../../CONTRIBUTING.md) in the project root.

---

[← Project README](../../README.md) | [Full index →](INDEX.md)
