# reveal - Semantic Code Explorer

**Progressive file disclosure for AI agents and developers**

```bash
pip install reveal-cli
reveal src/                    # directory → tree
reveal app.py                  # file → structure
reveal app.py load_config      # element → code
```

Zero config. 31 languages built-in. 50+ via tree-sitter.

---

## 🤖 For AI Agents

**This README is structured for both humans and AI agents.** Progressive disclosure starts at the top with quick examples.

**Using reveal CLI?** Get usage patterns and optimization techniques:
```bash
reveal --agent-help          # Quick start + discovery patterns (~720 lines)
reveal --agent-help-full     # Complete reference (~1680 lines)
```

**Token efficiency:** Structure view = 50 tokens vs 7,500 for reading full file. Validated 7-150x reduction in production.

**Documentation:** [Installation](INSTALL.md) • [Contributing](CONTRIBUTING.md) • [Changelog](CHANGELOG.md) • [Production Guide](docs/PRODUCTION_TESTING_GUIDE.md)

**Quick Install:**
```bash
pip install reveal-cli              # Full-featured by default (31 languages, 10 adapters)
pip install reveal-cli[database]    # Add MySQL database inspection
```
See [INSTALL.md](INSTALL.md) for details on what's included.

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

**41 built-in rules** across 12 categories: bugs (B001-B005), complexity (C901-C905), duplicates (D001-D002), style (E501), frontmatter (F001-F005), imports (I001-I003), links (L001-L003), maintainability (M101-M103), nginx (N001-N003), refactoring (R913), security (S701), URLs (U501-U502), validation (V001-V011). New in v0.25.0: link validation (L001-L003). New in v0.28.0: import analysis (I001-I003) for unused imports, circular dependencies, and layer violations. New in v0.29.0: schema validation (F001-F005) for markdown front matter.
**Extensible:** Drop custom rules in `~/.reveal/rules/` - auto-discovered

### 📝 Schema Validation (v0.29.0+)

```bash
# Validate markdown front matter against built-in schemas
reveal README.md --validate-schema session    # Session/workflow READMEs
reveal post.md --validate-schema hugo         # Hugo blog posts/pages
reveal post.md --validate-schema jekyll       # Jekyll (GitHub Pages)
reveal docs/api.md --validate-schema mkdocs   # MkDocs documentation
reveal note.md --validate-schema obsidian     # Obsidian notes

# Use custom schema
reveal doc.md --validate-schema /path/to/schema.yaml

# CI/CD integration
reveal README.md --validate-schema session --format json
```

**Built-in schemas:** session (workflow READMEs), hugo (static sites), jekyll (GitHub Pages), mkdocs (Python docs), obsidian (knowledge bases)
**Validation rules (F-series):** F001 (missing front matter), F002 (empty), F003 (required fields), F004 (type mismatches), F005 (custom validation)
**Docs:** [Schema Validation Guide](docs/SCHEMA_VALIDATION_GUIDE.md)

### ⚙️ Configuration System (v0.28.0+)

Control rule behavior via `.reveal.yaml` files and environment variables:

```yaml
# .reveal.yaml (project root)
root: true  # Stop searching upward for parent configs

rules:
  # Adjust complexity thresholds
  C901:
    threshold: 15  # Cyclomatic complexity (default: 10)

  E501:
    max_length: 120  # Line length (default: 100)

  # Disable specific rules
  # disable:
  #   - E501  # Line too long
  #   - C901  # Too complex

# Ignore files/directories
ignore:
  - "*.min.js"
  - "vendor/**"
  - "build/**"
```

**Environment variables** (override file config):

```bash
# Disable rules temporarily
export REVEAL_RULES_DISABLE="C901,E501"
reveal --check src/

# Override thresholds
export REVEAL_C901_THRESHOLD=20
export REVEAL_E501_MAX_LENGTH=120
reveal --check src/

# Use custom config file
export REVEAL_CONFIG=.reveal-strict.yaml
reveal --check src/

# Skip all config files (use defaults only)
export REVEAL_NO_CONFIG=1
reveal --check src/
```

**Configuration precedence** (highest to lowest):
1. CLI flags (`--select`, `--ignore`)
2. Environment variables
3. Custom config file (via `REVEAL_CONFIG`)
4. Project configs (walk up from current directory)
5. User config (`~/.config/reveal/config.yaml`)
6. System config (`/etc/reveal/config.yaml`)
7. Built-in defaults

**Debug configuration:**
```bash
reveal reveal://config              # Show active config with full transparency
reveal reveal://config --format json  # JSON output for scripting
```

**Learn more:**
```bash
reveal help://configuration  # Complete guide with examples
```

### 🔗 Link Validation (v0.25.0+)

```bash
# Validate links in markdown files
reveal docs/README.md --check --select L      # Check all link rules
reveal docs/ --check --select L001            # Only broken internal links
reveal docs/ --check --select L002            # Only broken external links (slow)
reveal docs/ --check --select L003            # Only framework routing mismatches
```

**L-series rules** for documentation workflows:
- **L001:** Broken internal links (filesystem validation, case sensitivity)
- **L002:** Broken external links (HTTP validation with smart suggestions)
- **L003:** Framework routing mismatches (FastHTML, Jekyll, Hugo auto-detection)

**Performance:** L001+L003 are fast (~50ms/file), L002 is slow (network I/O). Run L002 pre-commit or weekly.
**Guide:** See [LINK_VALIDATION_GUIDE.md](docs/LINK_VALIDATION_GUIDE.md) for batch validation, CI/CD integration, and examples.

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
reveal help://html                          # HTML analysis guide (templates, metadata, semantic)
reveal help://markdown                      # Markdown analysis guide

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
reveal reveal://analyzers/markdown.py MarkdownAnalyzer  # Extract class from reveal source
reveal reveal://rules/links/L001.py _extract_anchors_from_markdown  # Extract function from reveal source
reveal help://reveal                        # Learn about reveal:// adapter

# Code quality metrics & hotspot detection 🆕
reveal stats://./src                        # Codebase statistics and quality score
reveal stats://./src --hotspots             # Find worst quality files (technical debt)
reveal stats://./src/app.py                 # Specific file metrics
reveal stats://./src --format=json          # JSON output for CI/CD pipelines

# MySQL database inspection 🆕
# Requires: pip install reveal-cli[database]
reveal mysql://localhost                    # Database health overview
reveal mysql://localhost/performance        # Query performance + DBA tuning ratios
reveal mysql://localhost/indexes            # Index usage analysis
reveal mysql://localhost/slow-queries       # Slow query analysis (last 24h)
reveal mysql://localhost/innodb             # InnoDB buffer pool & locks

# Import graph analysis (v0.28.0+) 🆕
reveal imports://src                        # List all imports in directory
reveal 'imports://src?unused'               # Find unused imports (I001 rule)
reveal 'imports://src?circular'             # Detect circular dependencies (I002 rule)
reveal 'imports://src?violations'           # Check layer violations (I003 rule)
reveal imports://src/app.py                 # Imports for specific file

# Semantic diff - compare structures, not text (v0.30.0+) 🆕
reveal diff://app.py:backup/app.py          # Compare files (shows function/class changes)
reveal diff://src/:backup/src/              # Compare directories (aggregates all changes)
reveal diff://git://HEAD~1/app.py:git://HEAD/app.py    # Compare across commits
reveal diff://git://HEAD/src/:src/          # Compare git vs working tree (pre-commit check)
reveal diff://git://main/.:git://feature/.:  # Compare branches
reveal diff://app.py:new.py/handle_request  # Element-specific diff
reveal diff://env://:env://production        # Environment drift detection
reveal help://diff                           # Complete diff guide
```

**Extensibility Example:**
The `reveal://` adapter demonstrates that reveal can inspect **any resource**, not just files. Use it as a reference for creating custom adapters for your own projects (APIs, databases, containers, etc.). See `reveal help://reveal` for the complete guide.

**10 Built-in Adapters:**
- `help://` - Self-documenting help system (discover all adapters)
- `env://` - Environment variables (cross-language)
- `ast://` - Static code analysis & queries (cross-language)
- `json://` - JSON navigation with path access & schema (v0.20.0+)
- `python://` - Python runtime inspection & diagnostics (v0.17.0+)
- `reveal://` - Self-inspection & validation (v0.22.0+)
- `stats://` - Code quality metrics & hotspot detection
- `mysql://` - MySQL database inspection with DBA tuning ratios (requires `[database]` extra)
- `imports://` - Import graph analysis with unused/circular detection (v0.28.0+)
- `diff://` - Semantic structural diff (files, directories, git refs) (v0.30.0+) 🆕

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

**Built-in (31):** Python, Rust, Go, **C, C++**, **C#, Scala**, Java, PHP, **Ruby, Lua**, JavaScript, TypeScript, GDScript, Bash, **SQL**, Jupyter, HTML, Markdown, JSON, JSONL, YAML, TOML, Nginx, Dockerfile, Word/Excel/PowerPoint (.docx/.xlsx/.pptx), LibreOffice (.odt/.ods/.odp)

**Via tree-sitter (50+):** Kotlin, Perl, R, Haskell, and more. Add new languages in 3 lines of code.

**Shebang detection:** Extensionless scripts auto-detected (`#!/usr/bin/env python3`)

### Common Flags

| Flag | Purpose |
|------|---------|
| `--outline` | Hierarchical structure view |
| `--check` | Code quality analysis |
| `--copy` / `-c` | Copy output to clipboard 🆕 |
| `--frontmatter` | Extract YAML front matter (markdown) 🆕 |
| `--metadata` | Extract HTML head metadata (SEO, OpenGraph, Twitter cards) 🆕 |
| `--semantic TYPE` | Extract HTML semantic elements (navigation, content, forms, media) 🆕 |
| `--scripts TYPE` | Extract script tags from HTML (inline, external, all) 🆕 |
| `--styles TYPE` | Extract stylesheets from HTML (inline, external, all) 🆕 |
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
├── rules/        # 41 quality rules (B, C, D, E, F, I, L, M, N, R, S, U, V)
├── analyzers/    # 26 file types (Python, Rust, HTML, Markdown, etc.)
├── adapters/     # URI support (help://, env://, ast://, python://)
├── schemas/      # Type definitions (renamed from types/ in v0.23.0)
└── treesitter.py # Universal language support (50+ langs)
```

**Clean architecture:** Most analyzers < 50 lines. Modular packages since v0.22.0.

**Power users:** [COOL_TRICKS.md](reveal/COOL_TRICKS.md) - Hidden features and advanced workflows
**Production workflows:** [PRODUCTION_TESTING_GUIDE.md](docs/PRODUCTION_TESTING_GUIDE.md) - Real-world testing, CI/CD integration, performance at scale

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

[![Stars](https://img.shields.io/github/stars/Semantic-Infrastructure-Lab/reveal?style=social)](https://github.com/Semantic-Infrastructure-Lab/reveal)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
