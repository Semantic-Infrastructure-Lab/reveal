# reveal - Progressive File Disclosure for AI Agents

[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/scottsen/reveal?style=social)](https://github.com/scottsen/reveal)

> **Token-efficient file exploration for AI coding assistants**
>
> Explore codebases hierarchically with 4 levels of detail: metadata → structure → preview → full content

## 📖 TL;DR for LLMs

**What:** CLI tool for progressive file disclosure (explore files in stages instead of reading everything)
**Why:** Save tokens - read structure first (50 tokens), then only the parts you need
**Install:** `pip install reveal-cli`
**Use:** `reveal file.py -l 1` (structure) → `reveal file.py -l 2` (preview) → targeted reading
**Supports:** Python, GDScript, YAML, JSON, TOML, Markdown, SQL, C headers, plain text

---

## 🚀 Installation (Copy-Paste Ready)

**Recommended: Install from PyPI**
```bash
pip install reveal-cli
```

**Alternative: Install from GitHub (latest development version)**
```bash
pip install git+https://github.com/scottsen/reveal.git
```

**For development:**
```bash
git clone https://github.com/scottsen/reveal.git
cd reveal
pip install -e .
```

**Verify installation:**
```bash
reveal --help
```

That's it! No configuration needed.

---

## ⚡ Quick Start Examples

### Basic Usage (4 Levels)

```bash
# Level 0: File metadata (size, lines, encoding)
reveal app.py

# Level 1: Code structure (imports, classes, functions)
reveal app.py --level 1
# Alias: reveal app.py -l 1

# Level 2: Preview (signatures, docstrings, no implementations)
reveal app.py --level 2

# Level 3: Full content (with paging)
reveal app.py --level 3
```

### Real-World Workflow

```bash
# 1. Check file structure (50 tokens)
reveal game_manager.py -l 1
# Output shows: 3 classes, 12 functions at specific line numbers

# 2. Preview specific class (20 tokens)
reveal game_manager.py -l 2 --grep "GameManager"

# 3. Read full implementation (200 tokens)
reveal game_manager.py -l 3 --grep "class GameManager" -C 50
```

**Token savings: 270 tokens vs 500+ tokens reading full file**

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

**Built-in support:**
- **Python** (`.py`) - AST-based parsing, classes, functions, imports
- **GDScript** (`.gd`) - Godot Engine files, signals, exports, lifecycle methods
- **YAML** (`.yaml`, `.yml`) - Structured config files
- **JSON** (`.json`) - Data files
- **TOML** (`.toml`) - Config files
- **Markdown** (`.md`) - Documentation
- **SQL** (`.sql`) - Database schemas and queries
- **C Headers** (`.h`) - Function declarations
- **Plain Text** (`.txt`) - Generic files

**Coming soon:** Excel (.xlsx), Jupyter notebooks (.ipynb), TypeScript, Go, Rust, Shell scripts

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

## 🔗 Composable with Unix Tools

All analyzers return `filename:line` references, making reveal output work seamlessly with standard CLI tools:

```bash
# Find a function
$ reveal app.py --level 1 | grep "process_data"
app.py:42  process_data

# Jump to it in vim
$ vim app.py:42

# Or check git history
$ git blame app.py -L 42,50

# Use in scripts
$ reveal config.yaml --level 1 | awk '{print $1}' | xargs -I {} vim {}
```

**Universal pattern:** Every structure element shows its source location, making reveal a perfect bridge between exploration and editing.

## 🤖 For AI Agents: Usage Patterns

### Pattern 1: Unknown Codebase Exploration
```bash
# Step 1: Get file structure (cheap)
reveal src/main.py -l 1

# Step 2: Preview interesting parts (targeted)
reveal src/main.py -l 2 --grep "UserManager"

# Step 3: Read specific implementation (precise)
reveal src/main.py -l 3 --grep "def login" -C 10
```

### Pattern 2: Finding Specific Code
```bash
# Search structure first
reveal app.py -l 1 | grep "database"
# Output: app.py:42  DatabaseManager

# Then read that specific section
reveal app.py -l 3 --grep "class DatabaseManager" -C 20
```

### Pattern 3: Quick File Overview
```bash
# Check what's in this file without reading it all
reveal config.py -l 1
# Shows: 5 variables, 3 functions, 0 classes

# Decision: Not what I need, move on
# Saved: 300+ tokens
```

### Pattern 4: Godot Game Development
```bash
# Structure: See signals, exports, lifecycle functions
reveal player.gd -l 1

# Preview: Function signatures without implementations
reveal player.gd -l 2

# Targeted read: Specific function only
reveal player.gd -l 3 --grep "func take_damage" -C 5
```

### Why This Matters

**Before reveal:**
- Read entire 500-line file to find one function (500 tokens)
- Waste tokens on irrelevant content
- No standard navigation pattern

**With reveal:**
- Start with structure (50 tokens)
- Identify target at `app.py:42`
- Read only that section (20 tokens)
- **10x token efficiency**

### Best Practices for LLMs

1. **Always start with level 1** - Structure view shows what's in the file
2. **Use grep at level 1** - Find line numbers before reading content
3. **Use -C (context)** - Add surrounding lines when reading specific sections
4. **Compose with other tools** - `reveal file.py -l 1 | grep "class"`
5. **Don't read full files** - Only use level 3 when you know exactly what you need

## 🎨 Features

- **Progressive Disclosure** - 4 levels: metadata → structure → preview → full
- **Universal Line Numbers** - All analyzers show `filename:line` format for seamless tool integration
- **Composable Output** - Works with vim, grep, git blame, sed, and all CLI tools
- **Plugin System** - Decorator-based registration, auto-discovery via entry points
- **Breadcrumb Navigation** - Always show available levels
- **Rich Filtering** - Regex grep with context at any level
- **Directory Support** - Recursive analysis with progressive disclosure
- **AI-Optimized** - Designed for agentic workflows
- **Extensible** - Add new file types without touching core

## 🔧 Troubleshooting

### Installation Issues

**Problem:** `pip install git+https://...` fails
```bash
# Solution: Update pip first
python3 -m pip install --upgrade pip
pip install git+https://github.com/scottsen/reveal.git
```

**Problem:** `reveal: command not found`
```bash
# Solution: Ensure Python scripts are in PATH
# Add to ~/.bashrc or ~/.zshrc:
export PATH="$HOME/.local/bin:$PATH"

# Then reload:
source ~/.bashrc
```

**Problem:** `ModuleNotFoundError: No module named 'reveal'`
```bash
# Solution: Install in the correct Python environment
python3 -m pip install git+https://github.com/scottsen/reveal.git
```

### Usage Issues

**Problem:** File not recognized / shows as "text"
```bash
# Check supported file types:
reveal --help

# If your file type isn't supported, it falls back to text mode
# (Still works, just no structure parsing)
```

**Problem:** No output or empty structure
```bash
# Some files may not have parseable structure
# Try level 2 (preview) or level 3 (full content)
reveal file.py -l 2
```

### Getting Help

- Check `reveal --help` for all options
- Report issues: https://github.com/scottsen/reveal/issues
- Discussions: https://github.com/scottsen/reveal/discussions

---

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
- [x] Python, YAML, JSON, TOML, Markdown, SQL analyzers
- [x] GDScript support for Godot Engine
- [x] Decorator-based plugin system with entry points
- [x] Universal line number support (composable with CLI tools)
- [x] Directory analysis with recursive traversal
- [x] Breadcrumb navigation
- [x] C/C++ header support (.h, .hpp)
- [ ] Plugin-specific arguments (--table, --section, etc.)
- [ ] Shell script support (.sh, .bash)
- [ ] Excel support (.xlsx)
- [ ] Jupyter notebook support (.ipynb)
- [ ] TypeScript/JavaScript support
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

## 📋 Quick Command Reference

```bash
# Installation
pip install reveal-cli

# Basic usage
reveal file.py              # Level 0: metadata
reveal file.py -l 1         # Level 1: structure
reveal file.py -l 2         # Level 2: preview
reveal file.py -l 3         # Level 3: full content

# With filtering
reveal file.py -l 1 --grep "class"           # Filter output
reveal file.py -l 3 --grep "def login" -C 5  # Show with context

# Composable
reveal file.py -l 1 | grep "User"            # Pipe to grep
vim $(reveal file.py -l 1 | grep "login" | awk '{print $1}')  # Jump to function

# Get help
reveal --help
```

### Common Flags

- `-l, --level <0-3>` - Disclosure level (default: 0)
- `--grep PATTERN` - Filter output by regex pattern
- `-C, --context N` - Show N lines around matches
- `-h, --help` - Show help message

---

**Status:** 🚀 Active Development | **Version:** 0.1.0 | **License:** MIT

[![GitHub Stars](https://img.shields.io/github/stars/scottsen/reveal?style=social)](https://github.com/scottsen/reveal)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
