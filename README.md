# Reveal

**Progressive disclosure for codebases, databases, and infrastructure.**

Reveal is a command-line tool that provides structured, token-efficient inspection of:
- **Code**: AST queries, imports, structure analysis
- **Databases**: MySQL, PostgreSQL health monitoring
- **Infrastructure**: SSL certificates, domains, git repos
- **Data**: JSON, CSV, YAML, XML analysis

## Installation

```bash
pip install reveal-cli
```

## Quick Start

```bash
# Inspect code structure
reveal file.py

# Database health check
reveal mysql://localhost

# SSL certificate check
reveal ssl://example.com

# AST queries
reveal 'ast://src?complexity>30'
```

## Documentation

- **Quick Start**: `reveal help://quick-start`
- **Full Guide**: `reveal help://`
- **Agent Help**: `reveal --agent-help`

## Subcommands

```bash
reveal check src/             # Quality check (complexity, maintainability, links)
reveal review main..feature   # PR review: diff + check + hotspots in one pass
reveal health ssl://site.com  # Health check with exit codes 0/1/2
reveal pack src/ --budget 8k  # Token-budgeted snapshot for LLM context
reveal dev new-adapter        # Scaffold new adapters/rules
```

## Features

- 🎯 **Progressive Disclosure**: Structure → Element → Detail
- 🔍 **Unified Query Syntax**: Filter and sort across all adapters
- 🤖 **AI-Optimized**: Token-efficient output for LLM consumption
- 📊 **Quality Metrics**: Complexity, maintainability, test coverage
- 🔌 **Extensible**: 19 built-in adapters, 42+ languages, easy to add custom ones

## License

See [LICENSE](LICENSE) for details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
