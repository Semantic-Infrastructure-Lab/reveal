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

## Features

- 🎯 **Progressive Disclosure**: Structure → Element → Detail
- 🔍 **Unified Query Syntax**: Filter and sort across all adapters
- 🤖 **AI-Optimized**: Token-efficient output for LLM consumption
- 📊 **Quality Metrics**: Complexity, maintainability, test coverage
- 🔌 **Extensible**: 16+ built-in adapters, easy to add custom ones

## License

See [LICENSE](LICENSE) for details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
