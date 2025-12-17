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

## 🤖 For AI Agents

**This README is structured for both humans and AI agents.** Progressive disclosure starts at the top with quick examples.

**Using reveal CLI?** Get usage patterns and optimization techniques:
```bash
reveal --agent-help          # Quick start + discovery patterns (~382 lines)
reveal --agent-help-full     # Complete reference (~1215 lines)
```

**Token efficiency:** Structure view = 50 tokens vs 7,500 for reading full file. Validated 7-150x reduction in production.

**Documentation:** [Installation](INSTALL.md) • [Contributing](CONTRIBUTING.md) • [Changelog](CHANGELOG.md)

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

### 🔍 Code Quality Checks (v0.13.0+)

```bash
reveal app.py --check            # Find issues (bugs, security, complexity)
reveal app.py --check --select B,S  # Only bugs + security
reveal --rules                   # List all rules
reveal --explain B001            # Explain specific rule
```

**28 built-in rules** across 10 categories: bugs (B001-B005), complexity (C901-C905), duplicates (D001-D002), style (E501), maintainability (M101-M103), nginx (N001-N003), refactoring (R913), security (S701), URLs (U501-U502), validation (V001-V007). New in v0.23.0: decorator-aware bug detection (B002-B005).
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

Explore ANY resource - files, environment, code queries, Python runtime:

```bash
# Discover what's available
reveal help://                              # List all help topics
reveal help://ast                           # Learn about ast:// queries
reveal help://python                        # Python runtime adapter help

# Comprehensive guides (v0.18.0+)
reveal help://python-guide                  # Multi-shot examples for LLMs
reveal help://anti-patterns                 # Stop using grep/find!
reveal help://adapter-authoring             # Create custom adapters
reveal help://tricks                        # Cool tricks and hidden features 🆕

# Environment variables
reveal env://                               # All environment variables
reveal env://DATABASE_URL                   # Specific variable

# Python runtime inspection (v0.17.0+)
reveal python://                            # Python environment overview
reveal python://version                     # Version details
reveal python://venv                        # Virtual environment status
reveal python://packages                    # Installed packages
reveal python://packages/requests           # Specific package info
reveal python://module/mypackage            # Module conflict detection 🆕
reveal python://syspath                     # sys.path analysis 🆕
reveal python://doctor                      # Automated diagnostics 🆕
reveal python://imports                     # Loaded modules
reveal python://debug/bytecode              # Find stale .pyc files

# Query code as a database (v0.15.0+)
reveal 'ast://./src?complexity>10'          # Find complex functions
reveal 'ast://app.py?lines>50'              # Find long functions
reveal 'ast://.?name=test_*'                # Wildcard patterns 🆕
reveal 'ast://src/?name=*helper*'           # Find helpers 🆕
reveal 'ast://.?lines>30&complexity<5'      # Long but simple
reveal 'ast://src?type=function' --format=json  # JSON output

# Self-inspection and validation (v0.22.0+) 🆕
reveal reveal://                            # Inspect reveal's structure
reveal reveal:// --check                    # Validate completeness (V-series rules)
reveal help://reveal                        # Learn about reveal:// adapter
```

**Extensibility Example:**
The `reveal://` adapter demonstrates that reveal can inspect **any resource**, not just files. Use it as a reference for creating custom adapters for your own projects (APIs, databases, containers, etc.). See `reveal help://reveal` for the complete guide.

**6 Built-in Adapters:**
- `help://` - Self-documenting help system (discover all adapters)
- `env://` - Environment variables (cross-language)
- `ast://` - Static code analysis & queries (cross-language)
- `json://` - JSON navigation with path access & schema (v0.20.0+)
- `python://` - Python runtime inspection & diagnostics (v0.17.0+)
- `reveal://` - Self-inspection & validation (v0.22.0+)

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

**Built-in (25):** Python, Rust, Go, JavaScript, TypeScript, GDScript, Bash, Jupyter, Markdown, JSON, JSONL, YAML, TOML, Nginx, Dockerfile, Word/Excel/PowerPoint (.docx/.xlsx/.pptx), LibreOffice (.odt/.ods/.odp)

**Via tree-sitter (50+):** C, C++, C#, Java, PHP, Swift, Kotlin, Ruby, etc.

**Shebang detection:** Extensionless scripts auto-detected (`#!/usr/bin/env python3`)

### Common Flags

| Flag | Purpose |
|------|---------|
| `--outline` | Hierarchical structure view |
| `--check` | Code quality analysis |
| `--copy` / `-c` | Copy output to clipboard 🆕 |
| `--frontmatter` | Extract YAML front matter (markdown) 🆕 |
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
├── cli/          # Argument parsing, routing, handlers
├── display/      # Terminal output formatting
├── rendering/    # Adapter-specific renderers
├── rules/        # 24 quality rules (B, C, D, E, M, N, R, S, U, V)
├── analyzers/    # 25 file types (Python, Rust, Markdown, etc.)
├── adapters/     # URI support (help://, env://, ast://, python://)
├── schemas/      # Type definitions (renamed from types/ in v0.23.0)
└── treesitter.py # Universal language support (50+ langs)
```

**Clean architecture:** Most analyzers < 50 lines. Modular packages since v0.22.0.

**Power users:** [COOL_TRICKS.md](reveal/COOL_TRICKS.md) - Hidden features and advanced workflows

---

## Contributing

Add new languages in 10-50 lines. See `analyzers/` for examples.

**Most wanted:** TypeScript, Java, Swift, better extraction logic, bug reports.

---

## Part of Semantic Infrastructure Lab

**reveal** is production infrastructure from [SIL](https://github.com/semantic-infrastructure-lab) - building semantic tools for intelligent systems.

**Core principles:** Progressive disclosure, composability, semantic clarity.

---

**License:** MIT | [Roadmap](ROADMAP.md) | [Cool Tricks](reveal/COOL_TRICKS.md) | [Issues](https://github.com/Semantic-Infrastructure-Lab/reveal/issues)

[![Stars](https://img.shields.io/github/stars/scottsen/reveal?style=social)](https://github.com/Semantic-Infrastructure-Lab/reveal)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
