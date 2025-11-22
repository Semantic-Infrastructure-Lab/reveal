# reveal - Progressive File Disclosure for Agentic AI

> **The missing tool for AI code exploration**
>
> A plugin-based CLI that reveals file contents hierarchically, optimized for AI agents to efficiently navigate and understand codebases.

## 🎯 The Problem

AI coding assistants waste tokens reading entire files when they only need metadata, structure, or specific sections. There's no standard way for agents to progressively explore files with breadcrumb navigation.

## 💡 The Solution

`reveal` provides a plugin-based system where any file type can be explored through multiple levels of detail, always showing breadcrumbs to other views. Perfect for agentic workflows.

## ⚡ Quick Start

**One-line install:**
```bash
pip install git+https://github.com/scottsen/reveal.git
```

**Or from source:**
```bash
git clone https://github.com/scottsen/reveal.git
cd reveal
pip install -e .
```

**Usage:**
```bash
reveal app.py                    # Level 0: metadata
reveal app.py --level 1          # Level 1: structure (imports, classes, functions)
reveal app.py --level 2          # Level 2: preview (docstrings, signatures)
reveal app.py --level 3          # Level 3: full content (paged)

# With filtering
reveal app.py -l 2 --grep "class" --context 2
```

## 🔌 Plugin Architecture

Every file type is defined by a YAML plugin that maps to Python analyzers:

```yaml
# plugins/python.yaml
extension: .py
name: Python Source
description: Python source files with AST analysis

levels:
  0: {name: metadata, description: "File stats"}
  1: {name: structure, analyzer: python_structure}
  2: {name: preview, analyzer: python_preview}
  3: {name: full, description: "Complete source"}

features: [grep, context, paging, syntax_highlighting]
```

**Built-in support:** Python, YAML, JSON, Markdown, C/C++ headers, plain text

**Coming soon:** Excel (.xlsx), Jupyter notebooks (.ipynb), TypeScript, Go, Rust

## 🪜 Hierarchical Navigation

Every level shows breadcrumbs to other levels:

```
📄 app.py (Level 1: Structure)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Imports: 5 modules
Classes: 3 (UserManager, DatabaseHandler, APIClient)
Functions: 12 global functions

💡 Navigation:
   reveal app.py           → metadata (size, encoding, lines)
   reveal app.py -l 2      → preview (docstrings, signatures)
   reveal app.py -l 3      → full content
   reveal app.py -l 1 -m "Database"  → grep filter at this level
```

## 🤖 Why This Matters for AI

**Before reveal:**
- AI reads entire 500-line file to find one function
- Wastes tokens on irrelevant content
- No standard navigation pattern

**With reveal:**
- Start with structure (50 tokens)
- Identify target function
- Read only that function (20 tokens)
- 10x token efficiency

## 🎨 Features

- **Progressive Disclosure** - 4 levels: metadata → structure → preview → full
- **Plugin System** - YAML configs map extensions to analyzers
- **Breadcrumb Navigation** - Always show available levels
- **Rich Filtering** - Regex grep with context at any level
- **Composable** - Build complex analyzers from simple components
- **AI-Optimized** - Designed for agentic workflows
- **Extensible** - Add new file types without touching core

## 📚 Documentation

- [Plugin Development Guide](docs/PLUGIN_GUIDE.md)
- [Contributing](CONTRIBUTING.md)
- [Project Status](docs/PROJECT_STATUS.md)
- [Examples](docs/examples/)

## 🔗 Links

- **GitHub:** https://github.com/scottsen/reveal
- **Issues:** https://github.com/scottsen/reveal/issues
- **Discussions:** https://github.com/scottsen/reveal/discussions

## 🏗️ Architecture

```
reveal/
├── reveal/              # Core package
│   ├── cli.py          # Command-line interface
│   ├── core.py         # Reveal engine
│   ├── plugin_loader.py # YAML plugin system
│   ├── breadcrumbs.py  # Navigation hints
│   └── analyzers/      # Built-in analyzers
├── plugins/            # Plugin definitions (YAML)
├── tests/              # Test suite
└── docs/               # Documentation
```

## 🚀 Roadmap

- [x] Core framework with 4-level hierarchy
- [x] Python, YAML, JSON, Markdown analyzers
- [x] Decorator-based plugin system with entry points
- [ ] Breadcrumb navigation
- [ ] C/C++ header support (.h, .hpp)
- [ ] Excel support (.xlsx)
- [ ] Jupyter notebook support (.ipynb)
- [ ] Syntax highlighting
- [ ] Language server protocol integration
- [ ] GitHub Action for repo exploration
- [ ] VSCode extension

## 🤝 Contributing

We welcome contributions! This project is designed to grow through community plugins.

**Ways to contribute:**
- Add new file type plugins
- Improve existing analyzers
- Write documentation
- Share AI integration patterns

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

### 🔌 Creating Plugins

Reveal uses a Pythonic decorator-based plugin system. Creating a new file type analyzer is simple:

**Minimal Plugin (5 lines):**
```python
from reveal import register

@register(['.rs', '.rust'], name='Rust', icon='🦀')
class RustAnalyzer:
    def analyze_structure(self, lines):
        return {'functions': [l for l in lines if 'fn ' in l]}

    def generate_preview(self, lines):
        return [(i, l) for i, l in enumerate(lines[:20], 1)]
```

**Install as Package:**
```python
# setup.py
setup(
    name='reveal-rust',
    entry_points={
        'reveal.analyzers': [
            'rust = reveal_rust:RustAnalyzer',
        ],
    },
)
```

**Usage:**
```bash
pip install reveal-rust
reveal app.rs --level 1  # Works immediately!
```

**Benefits:**
- ✅ No core code changes needed
- ✅ pip-installable plugins
- ✅ Auto-discovery via entry points
- ✅ Type-safe with IDE autocomplete
- ✅ Community-friendly (like Flask routes, pytest fixtures)

## 📜 License

MIT License - See [LICENSE](LICENSE)

## 🎯 Use Cases

**For AI Agents:**
- Explore unknown codebases efficiently
- Read only necessary content
- Navigate with breadcrumbs
- Standard interface for all file types

**For Developers:**
- Quick file overview without full read
- Understand code structure rapidly
- Filter and search at appropriate levels
- Document file navigation patterns

## 🌟 Vision

Make `reveal` the standard way for AI agents and developers to progressively explore files, with a rich ecosystem of community-contributed plugins for every file type imaginable.

---

**Status:** 🚀 Active Development | **Version:** 0.1.0 | **License:** MIT

[![GitHub Stars](https://img.shields.io/github/stars/scottsen/reveal?style=social)](https://github.com/scottsen/reveal)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
