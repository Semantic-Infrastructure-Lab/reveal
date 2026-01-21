---
title: Reveal - Progressive Code Exploration
type: documentation
category: main
date: 2026-01-20
---

# reveal - Progressive Code Exploration

**Structure before content. Understand code by navigating it, not reading it.**

```bash
pip install reveal-cli
reveal src/                    # directory → tree
reveal app.py                  # file → structure
reveal app.py load_config      # element → code
```

Zero config. 40+ languages built-in. 165+ via tree-sitter.

**Token efficiency:** Structure view = 50 tokens vs 7,500 for full file. Measured 10-150x reduction in production use.

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

## Common Workflows

**Code review:**
```bash
reveal diff://git://main/.:git://feature/.   # What changed structurally?
reveal src/auth.py --check --select B,S      # Security issues?
```

**Onboarding:**
```bash
reveal .                   # Map the repo
reveal src/main.py          # Understand entry point
reveal src/main.py handler  # Drill into specifics
```

**Filtering noise:**
```bash
reveal . --exclude "node_modules" --exclude "*.pyc"  # Skip build artifacts
reveal . --exclude "__pycache__" --exclude "dist"    # Multiple patterns
```

**Finding hotspots:**
```bash
reveal 'ast://./src?complexity>10'    # Find complex functions
reveal stats://./src --hotspots       # Technical debt map
```

**Debugging:**
```bash
reveal python://doctor           # Environment health check
reveal python://module/requests  # Detect import shadowing
```

---

## 🤖 For AI Agents

**This README is structured for both humans and AI agents.** Progressive disclosure starts at the top with quick examples.

**Using reveal CLI?** Get usage patterns and optimization techniques:
```bash
reveal --agent-help          # Quick start + discovery patterns (~720 lines)
reveal --agent-help-full     # Complete reference (~1680 lines)
```

**Documentation:** [Installation](INSTALL.md) • [Contributing](CONTRIBUTING.md) • [Changelog](CHANGELOG.md) • [Guides](reveal/docs/README.md)

**Quick Install:**
```bash
pip install reveal-cli              # Full-featured by default (40+ languages, 15 adapters)
pip install reveal-cli[database]    # Add MySQL database inspection
```
See [INSTALL.md](INSTALL.md) for details on what's included.

---

## Key Features

### 🔍 Code Quality Checks (v0.13.0+)

```bash
reveal app.py --check            # Find issues (bugs, security, complexity)
reveal app.py --check --select B,S  # Only bugs + security
reveal --rules                   # List all rules
reveal --explain B001            # Explain specific rule
```

**55+ built-in rules** across 12 categories: bugs (B), complexity (C), duplicates (D), style (E), frontmatter (F), imports (I), links (L), maintainability (M), nginx (N), refactoring (R), security (S), URLs (U), validation (V). See CHANGELOG.md for recent additions.
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
**Docs:** [Schema Validation Guide](reveal/docs/SCHEMA_VALIDATION_HELP.md)

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

# SQLite database inspection 🆕
# No dependencies - uses Python's built-in sqlite3 module
reveal sqlite:///path/to/app.db             # Database overview & schema
reveal sqlite:///path/to/app.db/users       # Table structure with columns, indexes, FKs
reveal sqlite://./relative.db               # Relative paths supported
reveal sqlite:///data/prod.db --format=json # JSON output for scripting

# SSL certificate inspection 🆕
# No dependencies - uses Python's built-in ssl module
reveal ssl://example.com                    # Certificate overview & health status
reveal ssl://example.com:8443               # Non-standard port
reveal ssl://example.com/san                # Subject Alternative Names (all domains)
reveal ssl://example.com/chain              # Certificate chain details
reveal ssl://example.com --check            # Health checks (expiry, chain, hostname)

# Import graph analysis (v0.28.0+) 🆕
reveal imports://src                        # List all imports in directory
reveal 'imports://src?unused'               # Find unused imports (I001 rule)
reveal 'imports://src?circular'             # Detect circular dependencies (I002 rule)
reveal 'imports://src?violations'           # Check layer violations (I003 rule)
reveal imports://src/app.py                 # Imports for specific file

# Structural diff (v0.30.0+)
reveal diff://app.py:backup/app.py          # Compare files (shows function/class changes)
reveal diff://src/:backup/src/              # Compare directories (aggregates all changes)
reveal diff://git://HEAD~1/app.py:git://HEAD/app.py    # Compare across commits
reveal diff://git://HEAD/src/:src/          # Compare git vs working tree (pre-commit check)
reveal diff://git://main/.:git://feature/.  # Compare branches
reveal diff://app.py:new.py/handle_request  # Element-specific diff
reveal diff://env://:env://production        # Environment drift detection
reveal help://diff                           # Complete diff guide
```

**15 Built-in Adapters (Organized by Purpose):**

🟢 **Universal Tools** (core functionality, everyone benefits):
- `help://` - Self-documenting help system (discover all features)
- `env://` - Environment variable inspection (cross-platform debugging)
- `ast://` - Code structure queries (find functions by complexity, size, type)
- `python://` - Python runtime diagnostics (venv, packages, conflicts)

🟡 **Development Workflows** (code review, refactoring, quality analysis):
- `diff://` - Semantic structural comparison (files, directories, git refs)
- `stats://` - Codebase metrics and hotspot detection (technical debt)
- `imports://` - Import graph analysis (unused, circular, layer violations)
- `git://` - Repository archaeology (blame, history, time-travel)

🟡 **Domain Tools** (technology-specific inspection):
- `mysql://` - MySQL database inspection (requires `[database]` extra)
- `sqlite://` - SQLite database exploration (zero dependencies)
- `ssl://` - SSL certificate inspection (zero dependencies)
- `json://` - JSON navigation with path access and schema
- `markdown://` - Frontmatter queries for knowledge graphs

🎓 **Project Adapters** (extensibility examples - adapt to YOUR project):
- `reveal://` - **Dogfooding example** - reveal inspects itself
- `claude://` - **AI tool integration** - inspect Claude Code session logs

**Build Your Own Adapters:**
Reveal adapts to YOUR project's unique resources. Study `reveal://` (self-inspection) and `claude://` (session analysis) to learn patterns, then build adapters for:
- `k8s://` - Inspect your Kubernetes clusters
- `terraform://` - Validate your infrastructure
- `logs://` - Navigate your application logs
- `YOUR-PROJECT://` - Inspect YOUR unique resources

**Learn more:** `reveal help://adapter-authoring` - Complete guide with examples

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

**Built-in (40+ analyzers):** Python, Rust, Go, **C, C++**, **C#, Scala**, Java, PHP, **Ruby, Lua**, JavaScript, TypeScript, **Kotlin, Swift, Dart**, **HCL/Terraform, GraphQL, Protobuf, Zig**, GDScript, Bash, **SQL**, Jupyter, HTML, Markdown, JSON, JSONL, YAML, TOML, **CSV, INI, XML, PowerShell, Windows Batch**, Dockerfile, **Office formats** (Excel, Word, PowerPoint, Calc, Writer, Impress)

**Via tree-sitter (165+):** Perl, R, Haskell, Elixir, Zig, and more. Add new languages in 3 lines of code.

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
| `--stdin` | Read paths/URIs from stdin (files and any URI scheme) |
| `--depth N` | Directory tree depth |
| `--max-entries N` | Limit total directory entries (default: 200, 0=unlimited) |
| `--dir-limit N` | Limit entries per directory (default: 50, 0=unlimited) |
| `--fast` | Fast mode: skip line counting (~6x faster) |
| `--adapters` | List all URI adapters |
| `--languages` | List all supported languages |
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
├── rules/        # 55+ quality rules (B, C, D, E, F, I, L, M, N, R, S, U, V)
├── analyzers/    # 53 file types (Python, Rust, HTML, Markdown, etc.)
├── adapters/     # URI support (15 adapters: help://, env://, ast://, stats://, etc.)
├── schemas/      # Type definitions (renamed from types/ in v0.23.0)
└── treesitter.py # Universal language support (50+ langs)
```

**Clean architecture:** Most analyzers < 50 lines. Modular packages since v0.22.0.

**Quality metrics:** 2,500+ tests, continuous integration on every commit.

**Documentation:** [reveal/docs/README.md](reveal/docs/README.md) - Comprehensive guides for users, developers, and AI agents
**Power users:** [RECIPES.md](reveal/docs/RECIPES.md) - Task-based workflows and advanced patterns

---

## Stability Guarantees

**Status:** Beta - On path to v1.0 (see [ROADMAP.md](ROADMAP.md))

### 🟢 Stable (Safe to depend on)
- **Core modes:** directory → file → element
- **Basic adapters:** `help://`, `env://`, `ast://`, `python://`, `reveal://`
- **Output format:** `filename:line` (compatible with vim, git, grep)
- **Languages (Tier 1):** Python, JavaScript, TypeScript, Rust, Go, Java, C, C++

### 🟡 Beta (Feature-complete, API may evolve)
- **Advanced adapters:** `diff://`, `imports://`, `sqlite://`, `mysql://`, `stats://`, `json://`, `markdown://`, `git://`
- **Quality rules:** 50+ rules across 12 categories (may be refined)
- **Languages (Tier 2):** 23 additional languages (C#, Scala, PHP, Ruby, Lua, GDScript, Bash, SQL, Kotlin, Swift, Dart, Zig, HCL/Terraform, GraphQL, Protobuf, + config formats)
- **JSON output:** Output Contract v1.0 shipped (2026-01-17) - all adapters have predictable schemas

### 🔴 Experimental (No guarantees)
- **Tree-sitter languages:** 165+ languages (basic structure only)
- **Undocumented features:** Use at your own risk

**For AI agents:** Text output (`filename:line` format) and JSON output (`--format json`) are both production-ready. All 15 adapters follow Output Contract v1.0.

**For CI/CD:** Pin reveal version (`pip install reveal-cli==0.40.0`) and upgrade explicitly after testing.

**Full policy:** See [STABILITY.md](STABILITY.md) for detailed guarantees, breaking change policy, and v1.0 roadmap.

---

## Contributing

Add new languages in 10-50 lines. See `analyzers/` for examples.

**Most wanted:** Better extraction logic, bug reports, documentation improvements.

---

## Part of Semantic Infrastructure Lab

**reveal** is production infrastructure from [SIL](https://github.com/semantic-infrastructure-lab) - building semantic tools for intelligent systems.

**Core principles:** Progressive disclosure, composability, semantic clarity.

---

**License:** MIT | [Documentation](reveal/docs/README.md) | [Recipes](reveal/docs/RECIPES.md) | [Issues](https://github.com/Semantic-Infrastructure-Lab/reveal/issues)

[![Stars](https://img.shields.io/github/stars/Semantic-Infrastructure-Lab/reveal?style=social)](https://github.com/Semantic-Infrastructure-Lab/reveal)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
