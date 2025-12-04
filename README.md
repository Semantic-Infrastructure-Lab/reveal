# reveal - Semantic Code Explorer

**Progressive file disclosure for AI agents and developers**

```bash
pip install reveal-cli
reveal src/                    # directory → tree
reveal app.py                  # file → structure
reveal app.py load_config      # element → code
```

Zero config. 18 languages built-in. 50+ via tree-sitter.

---

## Core Modes

**Auto-detects what you need:**

```bash
# Directory → tree view
$ reveal src/
📁 src/
├── app.py (247 lines, Python)
├── database.py (189 lines, Python)
└── models/
    ├── user.py (156 lines, Python)
    └── post.py (203 lines, Python)

# File → structure (imports, functions, classes)
$ reveal app.py
📄 app.py

Imports (3):
  app.py:1    import os, sys
  app.py:2    from typing import Dict

Functions (5):
  app.py:15   load_config(path: str) -> Dict
  app.py:28   setup_logging(level: str) -> None

Classes (2):
  app.py:95   Database
  app.py:145  RequestHandler

# Element → extract function/class
$ reveal app.py load_config
app.py:15-27 | load_config

   15  def load_config(path: str) -> Dict:
   16      """Load configuration from JSON file."""
   17      if not os.path.exists(path):
   18          raise FileNotFoundError(f"Config not found: {path}")
   19      with open(path) as f:
   20          return json.load(f)
```

**All output is `filename:line` format** - works with vim, git, grep.

---

## Key Features

### 🤖 AI Agent Workflows

```bash
# Get comprehensive agent guide
reveal --agent-help              # Decision trees, workflows, anti-patterns

# Typical exploration pattern
reveal src/                      # Orient: what exists?
reveal src/app.py                # Navigate: see structure
reveal src/app.py Database       # Focus: get implementation
```

**Token efficiency:** Structure view = 50 tokens vs 7,500 for full file read.

### 🔍 Code Quality Checks (v0.13.0+)

```bash
reveal app.py --check            # Find issues (bugs, security, complexity)
reveal app.py --check --select B,S  # Only bugs + security
reveal --rules                   # List all rules
reveal --explain B001            # Explain specific rule
```

**Built-in rules:** Bare except (B001), :latest tags (S701), complexity (C901), line length (E501), HTTP URLs (U501)
**Extensible:** Drop custom rules in `~/.reveal/rules/` - auto-discovered

### 🌲 Outline Mode (v0.9.0+)

```bash
reveal app.py --outline
UserManager (app.py:1)
  ├─ create_user(self, username) [3 lines, depth:0] (line 4)
  ├─ delete_user(self, user_id) [3 lines, depth:0] (line 8)
  └─ UserValidator (nested class, line 12)
     └─ validate_email(self, email) [2 lines, depth:0] (line 15)
```

### 🔌 Unix Pipelines

```bash
# Changed files in git
git diff --name-only | reveal --stdin --outline

# Find complex functions
find src/ -name "*.py" | reveal --stdin --format=json | jq '.functions[] | select(.line_count > 100)'

# CI/CD quality gate
git diff --name-only origin/main | grep "\.py$" | reveal --stdin --check --format=grep
```

### 🌐 URI Adapters (v0.11.0+)

Explore ANY resource - files, environment, code queries:

```bash
# Discover what's available
reveal help://                              # List all help topics
reveal help://ast                           # Learn about ast:// queries

# Environment variables
reveal env://                               # All environment variables
reveal env://DATABASE_URL                   # Specific variable

# Query code as a database (v0.15.0+)
reveal 'ast://./src?complexity>10'          # Find complex functions
reveal 'ast://app.py?lines>50'              # Find long functions
reveal 'ast://.?lines>30&complexity<5'      # Long but simple
reveal 'ast://src?type=function' --format=json  # JSON output
```

**Self-documenting:** Every adapter exposes help via `reveal help://<scheme>`

---

## Quick Reference

### Output Formats

```bash
reveal app.py                    # text (default)
reveal app.py --format=json      # structured data
reveal app.py --format=grep      # grep-compatible
reveal app.py --meta             # metadata only
```

### Supported Languages

**Built-in (18):** Python, Rust, Go, JavaScript, TypeScript, GDScript, Bash, Jupyter, Markdown, JSON, YAML, TOML, Nginx, Dockerfile, + more

**Via tree-sitter (50+):** C, C++, C#, Java, PHP, Swift, Kotlin, Ruby, etc.

**Shebang detection:** Extensionless scripts auto-detected (`#!/usr/bin/env python3`)

### Common Flags

| Flag | Purpose |
|------|---------|
| `--outline` | Hierarchical structure view |
| `--check` | Code quality analysis |
| `--stdin` | Read file paths from stdin |
| `--depth N` | Directory tree depth |
| `--max-entries N` | Limit directory entries (default: 200, 0=unlimited) |
| `--fast` | Fast mode: skip line counting (~6x faster) |
| `--agent-help` | AI agent usage guide |
| `--list-supported` | Show all file types |

---

## Extending reveal

### Tree-Sitter Languages (10 lines)

```python
from reveal import TreeSitterAnalyzer, register

@register('.go', name='Go', icon='🔷')
class GoAnalyzer(TreeSitterAnalyzer):
    language = 'go'
```

Done. Full Go support with structure + extraction.

### Custom Analyzers (20-50 lines)

```python
from reveal import FileAnalyzer, register

@register('.md', name='Markdown', icon='📝')
class MarkdownAnalyzer(FileAnalyzer):
    def get_structure(self):
        headings = []
        for i, line in enumerate(self.lines, 1):
            if line.startswith('#'):
                headings.append({'line': i, 'name': line.strip('# ')})
        return {'headings': headings}
```

**Custom rules:** Drop in `~/.reveal/rules/` - zero config.

---

## Architecture

```
reveal/
├── base.py          # Core (~380 lines)
├── main.py          # CLI (~920 lines)
├── treesitter.py    # 50+ languages (~345 lines)
├── analyzers/       # 18 file types (10-300 lines each)
└── adapters/        # URI support (help://, env://, ast://)
```

**Total:** ~3,400 lines. Most analyzers < 25 lines.

**Deep dive:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## Contributing

Add new languages in 10-50 lines. See `analyzers/` for examples.

**Most wanted:** TypeScript, Java, Swift, better extraction logic, bug reports.

---

## Part of Semantic Infrastructure Lab

**reveal** is production infrastructure from [SIL](https://github.com/semantic-infrastructure-lab/sil) - building the semantic substrate for intelligent systems.

**Role:** Layer 5 (Human Interfaces) - progressive disclosure of structure
**Principles:** Clarity, Simplicity, Composability, Correctness, Verifiability

[SIL Manifesto](https://github.com/semantic-infrastructure-lab/sil/blob/main/docs/canonical/MANIFESTO.md) • [Architecture](https://github.com/semantic-infrastructure-lab/sil/blob/main/docs/architecture/UNIFIED_ARCHITECTURE_GUIDE.md) • [Projects](https://github.com/semantic-infrastructure-lab/sil/blob/main/projects/PROJECT_INDEX.md)

---

**Status:** v0.13.3 | **License:** MIT | [Roadmap](ROADMAP.md) | [Issues](https://github.com/scottsen/reveal/issues)

[![Stars](https://img.shields.io/github/stars/scottsen/reveal?style=social)](https://github.com/scottsen/reveal)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
