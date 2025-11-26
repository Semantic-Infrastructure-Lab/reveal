# reveal - Explore Code Semantically

> **The simplest way to understand code**
>
> Point it at a directory, file, or function. Get exactly what you need with zero configuration.

## 🎯 The Problem

Developers and AI agents waste time reading entire files when they only need to understand structure or extract specific functions. There's no standard way to progressively explore code.

## 💡 The Solution

`reveal` provides smart, semantic exploration of codebases:
- **Directories** → See what's inside
- **Files** → See structure (imports, functions, classes)
- **Elements** → See implementation (extract specific function/class)

All with perfect `filename:line` integration for vim, git, grep, and other tools.

## ⚡ Quick Start

**Install:**
```bash
pip install reveal-cli
```

Includes full support for 18 file types out of the box (Python, JavaScript, TypeScript, Rust, Go, and more).

**Use:**
```bash
reveal src/                    # Directory → tree view
reveal app.py                  # File → structure
reveal app.py load_config      # Element → extraction
```

**That's it.** No flags, no configuration, just works.

## 🎨 Clean Design

### Smart Auto-Detection

```bash
# Directories → tree view
$ reveal src/
📁 src/
├── app.py (247 lines, Python)
├── database.py (189 lines, Python)
└── models/
    ├── user.py (156 lines, Python)
    └── post.py (203 lines, Python)

# Files → structure view
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

# Elements → extraction
$ reveal app.py load_config
app.py:15-27 | load_config

   15  def load_config(path: str) -> Dict:
   16      """Load configuration from JSON file."""
   17
   18      if not os.path.exists(path):
   19          raise FileNotFoundError(f"Config not found: {path}")
   20
   21      with open(path) as f:
   22          return json.load(f)
```

### Perfect Unix Integration

Every line is `filename:line` format:

```bash
# Works with vim
$ reveal app.py | grep "Database"
  app.py:95     Database

$ vim app.py:95

# Works with git
$ reveal app.py | grep "load_config"
  app.py:15   load_config(path: str) -> Dict

$ git blame app.py -L 15,27

# Pipe to other tools
$ reveal app.py --format=grep | grep "config"
app.py:15:def load_config(path: str) -> Dict:
app.py:18:    if not os.path.exists(path):
```

## 🔌 Adding New File Types (Stupidly Easy)

### Tree-Sitter Languages (10 lines!)

```python
from reveal import TreeSitterAnalyzer, register

@register('.go', name='Go', icon='🔷')
class GoAnalyzer(TreeSitterAnalyzer):
    language = 'go'
```

**Done!** Full Go support with structure extraction and element access.

Works for: Python, Rust, Go, JavaScript, TypeScript, C#, Java, PHP, Bash, C, C++, Swift, Kotlin, and 40+ more languages!

### Custom Analyzers (20-50 lines)

```python
from reveal import FileAnalyzer, register

@register('.md', name='Markdown', icon='📝')
class MarkdownAnalyzer(FileAnalyzer):
    def get_structure(self):
        """Extract headings."""
        headings = []
        for i, line in enumerate(self.lines, 1):
            if line.startswith('#'):
                headings.append({'line': i, 'name': line.strip('# ')})
        return {'headings': headings}

    def extract_element(self, element_type, name):
        """Extract a section."""
        # Custom extraction logic
        ...
```

That's it! Your file type now works with reveal.

## 🚀 Features

- ✅ **Smart defaults** - No flags needed for 99% of use cases
- ✅ **Directory trees** - See what's in a folder
- ✅ **Structure extraction** - Imports, functions, classes, signals (GDScript)
- ✅ **Element extraction** - Get specific function/class
- ✅ **18 file types built-in** - Python, Rust, Go, JavaScript, TypeScript, GDScript, Bash, Jupyter, Markdown, JSON, YAML, TOML, Nginx, Dockerfile, and more
- ✅ **Shebang detection** - Extensionless scripts work automatically (detects `#!/usr/bin/env python3`, `#!/bin/bash`)
- ✅ **50+ languages available** - Via optional tree-sitter (JS, TS, C#, Java, PHP, etc.)
- ✅ **Perfect line numbers** - `filename:line` format everywhere
- ✅ **Unix composable** - Works with vim, git, grep, sed, awk
- ✅ **Multiple output formats** - text (default), json, grep
- ✅ **Easy to extend** - Add new file type in 10-50 lines
- ✅ **AI-optimized** - Designed for agentic workflows
- ✅ **Windows compatible** - Full UTF-8/emoji support

## 📚 Real-World Examples

### AI Agent Workflow
```bash
# Start broad
$ reveal src/
# Pick interesting file
$ reveal src/app.py
# Deep dive
$ reveal src/app.py Database
```

### Developer Quick Lookup
```bash
# See function implementation
$ reveal app.py load_config

# Jump to edit
$ vim app.py:15
```

### Game Development (GDScript)
```bash
# Explore Godot scripts
$ reveal player.gd
📄 player.gd

Functions (4):
  player.gd:11    _ready() -> void
  player.gd:16    take_damage(amount: int) -> void
  player.gd:24    die() -> void

Signals (2):
  player.gd:3     health_changed(new_health)
  player.gd:4     died()

# Extract specific function
$ reveal player.gd take_damage
player.gd:16-23 | take_damage

   16  func take_damage(amount: int) -> void:
   17      """Reduce health by amount."""
   18      current_health -= amount
   19      emit_signal("health_changed", current_health)
```

### Integration with Tools
```bash
# Find all TODO comments
$ reveal src/*.py | grep -i "todo"

# Count functions per file
$ for f in src/*.py; do echo "$f: $(reveal $f | grep -c 'Functions')"; done

# Extract all function names
$ reveal app.py | awk '/Functions/,/^$/ {if ($2 ~ /:/) print $3}'
```

## 🎯 Use Cases

**For AI Agents:**
- Explore unknown codebases efficiently
- Get structure without reading full files
- Extract specific elements on demand
- Standard interface across all file types

**For Developers:**
- Quick reference without opening editor
- Understand file structure rapidly
- Find specific functions/classes
- Perfect for terminal workflows

**For Scripts:**
- JSON output for programmatic access
- Grep-compatible format
- Composable with Unix tools
- Reliable filename:line references

## 🏗️ Architecture

```
reveal/
├── base.py              # FileAnalyzer base class
├── treesitter.py        # TreeSitterAnalyzer (50+ languages!)
├── tree_view.py         # Directory tree view
├── new_cli.py           # Simple CLI (200 lines)
└── analyzers_new/
    ├── python.py        # 15 lines
    ├── rust.py          # 13 lines
    ├── go.py            # 13 lines
    ├── markdown.py      # 79 lines
    ├── yaml_json.py     # 110 lines
    └── ...              # Easy to add more!
```

**Total core:** ~500 lines
**Per analyzer:** 10-50 lines

## 📖 Optional Flags

```bash
# Discovery
reveal --version              # Show version
reveal --list-supported       # List all supported file types

# Metadata only
reveal app.py --meta

# JSON output
reveal app.py --format=json

# Grep-compatible output
reveal app.py --format=grep

# Directory depth
reveal src/ --depth=5
```

## 🤝 Contributing

We welcome contributions! Adding a new file type takes 10-50 lines of code.

**Most wanted:**
- New language analyzers (TypeScript, Java, Swift, Kotlin)
- Better extraction logic for existing analyzers
- Documentation improvements
- Bug reports and feature requests

## 📜 License

MIT License - See [LICENSE](LICENSE)

## 🔗 Links

- **GitHub:** https://github.com/scottsen/reveal
- **Issues:** https://github.com/scottsen/reveal/issues
- **Discussions:** https://github.com/scottsen/reveal/discussions

## 🌟 Vision

Make `reveal` the standard way to explore code - for humans and AI agents alike. Clean, simple, powerful.

---

**Status:** 🚀 v0.4.0 - Enhanced CLI + Cross-Platform | **License:** MIT

[![GitHub Stars](https://img.shields.io/github/stars/scottsen/reveal?style=social)](https://github.com/scottsen/reveal)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
