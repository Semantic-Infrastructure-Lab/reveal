# Reveal Cool Tricks

> The hidden powers of reveal that will make you a 10x developer

---

## Table of Contents

- [Self-Diagnostic Superpowers](#self-diagnostic-superpowers)
- [AST Query Wizardry](#ast-query-wizardry)
- [Pipeline Magic](#pipeline-magic)
- [Markdown Surgery](#markdown-surgery)
- [Token Efficiency Mastery](#token-efficiency-mastery)
- [Quality Gatekeeping](#quality-gatekeeping)
- [Discovery Patterns](#discovery-patterns)
- [Format Transformations](#format-transformations)
- [Multi-Language Exploration](#multi-language-exploration)

---

## Self-Diagnostic Superpowers

### Reveal Diagnosing Reveal (The Meta Example)

```bash
# Run from reveal's source directory - watch Python explode
cd ~/src/projects/reveal/external-git/reveal/adapters
reveal env://
# CRASH! types.py shadows Python's stdlib types module

# Now diagnose the problem
cd /tmp
reveal python://module/types
# Output: No conflicts - imports from /usr/lib/python3.10/types.py

reveal python://module/ast
# If you were in reveal's directory, this would detect the conflict
```

**Why this matters:** Reveal's `python://` adapter can detect when YOU'RE running it from a bad location.

### Python Environment Doctor

```bash
# Run automated diagnostics
reveal python://doctor

# Output:
# {
#   "status": "healthy",
#   "health_score": 100,
#   "issues": [],
#   "warnings": [],
#   "recommendations": [],
#   "checks_performed": [
#     "virtual_environment",
#     "cwd_shadowing",
#     "stale_bytecode",
#     "python_version",
#     "editable_installs"
#   ]
# }
```

### Find Stale Bytecode (The Silent Killer)

```bash
# "My code changes aren't working!"
reveal python://debug/bytecode

# Finds .pyc files newer than source = stale bytecode
# Gives you exact cleanup commands:
#   find . -type d -name __pycache__ -exec rm -rf {} +
#   find . -name "*.pyc" -delete
```

### Detect Import Shadowing

```bash
# Is your local module hiding a pip package?
reveal python://module/requests

# Output shows:
# - import_location: Where Python actually imports from
# - pip_package: Where pip thinks it is
# - conflicts: [] or [{ type: "cwd_shadowing", ... }]
# - recommendations: Exact fix if there's a problem
```

### Analyze sys.path Conflicts

```bash
reveal python://syspath

# Shows each path entry with:
# - Priority number (0 = highest)
# - Type: cwd, site-packages, stdlib, pythonpath
# - Warning if CWD shadows packages
```

---

## AST Query Wizardry

### Find Complex Functions

```bash
# Quote the URI! Shell interprets > as redirect
reveal 'ast://./src?complexity>10'

# Find functions that are complex AND long
reveal 'ast://./src?complexity>8&lines>50'
```

### Wildcard Name Search

```bash
# All test functions
reveal 'ast://.?name=test_*'

# All helper functions
reveal 'ast://src/?name=*helper*'

# Single character wildcard
reveal 'ast://.?name=get_?'

# Combine with type filter
reveal 'ast://.?name=*Manager&type=class'
```

### Find Refactoring Candidates

```bash
# Long but simple functions (copy-paste territory)
reveal 'ast://./src?lines>50&complexity<5'

# Functions with too many parameters
reveal 'ast://./src?type=function' --format=json | \
  jq '.results[] | select(.signature | split(",") | length > 5)'
```

### Cross-Codebase Analysis

```bash
# Find all get_* methods across entire project
reveal 'ast://.?name=get_*' --format=json | \
  jq -r '.results[] | "\(.file):\(.line) \(.name)"'

# Count functions per file
reveal 'ast://./src?type=function' --format=json | \
  jq -r '.results[].file' | sort | uniq -c | sort -rn
```

---

## Pipeline Magic

### Changed Files Analysis

```bash
# What changed in git? Show structure
git diff --name-only | reveal --stdin --outline

# Check quality of changed Python files
git diff --name-only | grep '\.py$' | reveal --stdin --check

# Find complex functions in changed files
git diff --name-only | grep '\.py$' | \
  while read f; do reveal "ast://$f?complexity>8"; done
```

### Batch Processing with JSON

```bash
# All functions > 100 lines across project
find . -name "*.py" | reveal --stdin --format=json | \
  jq -r '.structure.functions[] | select(.line_count > 100) |
         "\(.file):\(.line) \(.name) [\(.line_count) lines]"'

# Extract all imports
find . -name "*.py" | reveal --stdin --format=json | \
  jq -r '.structure.imports[].content' | sort -u
```

### PR Review Workflow

```bash
# 1. See what changed
git diff --name-only origin/main | reveal --stdin

# 2. Check quality issues
git diff --name-only origin/main | grep '\.py$' | reveal --stdin --check

# 3. Find new complex functions
git diff --name-only origin/main | grep '\.py$' | \
  xargs -I{} reveal 'ast://{}?complexity>10'
```

---

## Markdown Surgery

### Extract All Links

```bash
reveal README.md --links

# Filter by type
reveal README.md --links --link-type=external  # GitHub, APIs
reveal README.md --links --link-type=internal  # Local files
reveal README.md --links --link-type=email     # mailto:

# Filter by domain
reveal README.md --links --domain=github.com
```

### Find Broken Links

```bash
# reveal automatically marks broken internal links with [BROKEN]
reveal docs/*.md --links 2>/dev/null | grep BROKEN
```

### Extract Code Examples

```bash
# All code blocks
reveal README.md --code

# Only Python examples
reveal README.md --code --language=python

# Include inline code too
reveal README.md --code --inline
```

### Navigate Documentation

```bash
# Get structure of a doc
reveal docs/ARCHITECTURE.md --outline

# Extract specific section
reveal docs/ARCHITECTURE.md "Installation"

# Find all headings
reveal docs/*.md --format=json | jq '.structure.headings[].content'
```

---

## Token Efficiency Mastery

### Progressive Disclosure Pattern

```bash
# Level 1: Structure (~100 tokens)
reveal app.py

# Level 2: Hierarchy (~150 tokens)
reveal app.py --outline

# Level 3: Specific extraction (~50 tokens)
reveal app.py process_data

# Compare: cat app.py (~7,500 tokens for 300 lines)
# Savings: 50-150x
```

### Semantic Slicing

```bash
# First 5 functions only
reveal large_module.py --head 5

# Last 3 functions (bugs cluster at the bottom!)
reveal large_module.py --tail 3

# Specific range
reveal conversation.jsonl --range 48-52
```

### URI Progressive Disclosure

```bash
# Python environment
reveal python://              # Overview (~20 tokens)
reveal python://packages      # Package list (~200 tokens)
reveal python://packages/numpy  # Specific package (~50 tokens)

# AST queries
reveal ast://./src            # All structure (~500 tokens)
reveal 'ast://./src?complexity>10'  # Just complex ones (~100 tokens)
```

---

## Quality Gatekeeping

### Comprehensive Checks

```bash
# Run all checks
reveal app.py --check

# Just bugs and security
reveal app.py --check --select B,S

# Everything except line length
reveal app.py --check --ignore E501
```

### Available Rules

```bash
# List all rules
reveal --rules

# Explain a specific rule
reveal --explain B001

# Rules by category:
# B - Bugs (bare except, etc.)
# C - Complexity (cyclomatic complexity)
# E - Errors (line length, etc.)
# N - Nginx (duplicate backends, SSL, proxy headers) [NEW v0.19.0]
# R - Refactoring (too many args)
# S - Security (Docker :latest tag)
# U - URLs (insecure http://)
```

### Combine with Outline

```bash
# See structure AND issues together
reveal app.py --outline --check
```

### Docker Security

```bash
# Check Dockerfile best practices
reveal Dockerfile --check

# S701: Warns about :latest tags
# Recommends pinning to specific versions
```

### Nginx Configuration Validation (NEW v0.19.0)

```bash
# Check nginx config for common issues
reveal /etc/nginx/nginx.conf --check
reveal /etc/nginx/sites-available/*.conf --check

# N001: Duplicate backends (multiple upstreams → same server:port)
# N002: SSL servers missing certificate directives
# N003: Proxy locations missing X-Real-IP, X-Forwarded-For

# Example: Catch the $8K incident class
reveal /etc/nginx/conf.d/upstreams.conf --check --select N001
# ❌ N001 Upstream 'app2' shares backend 127.0.0.1:8000 with 'app1'
```

**Why this matters:** A production incident where two nginx upstreams pointed to the same port caused a $8,619/month revenue site to serve the wrong content. N001 catches this exact class of bug.

---

## Discovery Patterns

### Self-Documenting Help System

```bash
# Level 1: What adapters exist? (~50 tokens)
reveal help://

# Level 2: How do I use this adapter? (~200 tokens)
reveal help://ast
reveal help://python
reveal help://env

# Level 3: Deep dive (~2000 tokens)
reveal help://python-guide
reveal help://anti-patterns
reveal help://adapter-authoring
```

### Explore Unknown Codebase

```bash
# 1. Directory structure
reveal src/

# 2. Find entry points
reveal 'ast://./src?name=main*'
reveal 'ast://./src?name=*cli*'

# 3. Find the big modules
reveal 'ast://./src?lines>100'

# 4. Understand one file
reveal src/important_module.py --outline
```

### Find What You're Looking For

```bash
# Instead of: grep -r "class UserManager"
reveal 'ast://.?name=UserManager&type=class'

# Instead of: find . -name "*.py" -exec grep -l "def process"
reveal 'ast://.?name=process*&type=function'
```

---

## Format Transformations

### JSON for Scripting

```bash
# Structure as JSON
reveal app.py --format=json

# Query with jq
reveal app.py --format=json | jq '.structure.functions | length'
reveal app.py --format=json | jq '.structure.imports[].content'
```

### Typed JSON (with Relationships)

```bash
# Get typed output with metadata
reveal app.py --format=typed

# Includes:
# - Entity types (function, class, import)
# - Relationships (calls, inherits)
# - Line ranges
```

### Grep-Compatible Output

```bash
# Pipeable format
reveal app.py --format=grep

# Output: file:line:content
# Perfect for: reveal ... | grep pattern | cut -d: -f1-2
```

---

## Multi-Language Exploration

### Built-in Analyzers (Full Support)

```bash
# Python, JS, TS, Rust, Go, Dockerfile, YAML, JSON, TOML, Markdown
reveal app.py            # Python
reveal config.yaml       # YAML
reveal Dockerfile        # Dockerfile with quality checks
reveal package.json      # JSON structure
reveal main.go           # Go
reveal lib.rs            # Rust
```

### Tree-Sitter Fallback (37+ Languages)

```bash
# C, C++, Java, Ruby, PHP, Kotlin, Scala, Haskell, OCaml, Lua...
reveal Main.java         # Works!
reveal app.rb            # Works!
reveal script.lua        # Works!

# Check what's supported
reveal --list-supported
```

### Nginx Config Analysis

```bash
# See all server blocks
reveal nginx.conf

# Extract specific server
reveal nginx.conf server_myapp

# Find all upstreams
reveal nginx.conf --format=json | jq '.structure.upstreams'
```

### Jupyter Notebooks

```bash
# See notebook structure
reveal analysis.ipynb

# All cells with outputs
reveal analysis.ipynb --format=json
```

---

## Power User Combos

### The Full Investigation

```bash
# Something's broken. Find it.
reveal python://doctor                           # Environment OK?
reveal python://debug/bytecode                   # Stale cache?
reveal python://module/broken_module             # Import conflict?
reveal 'ast://./src?complexity>10'               # Spaghetti code?
reveal ./src --check --select B,S                # Bugs? Security?
```

### The Code Review

```bash
# PR review speedrun
git diff --name-only origin/main > /tmp/changed
cat /tmp/changed | reveal --stdin --outline      # What changed?
cat /tmp/changed | grep '\.py$' | reveal --stdin --check  # Quality?
git diff --name-only origin/main | xargs -I{} reveal 'ast://{}?complexity>10'  # Complex?
```

### The Documentation Audit

```bash
# Docs healthy?
reveal docs/ --links | grep BROKEN               # Broken links?
reveal docs/*.md --code --language=bash          # All CLI examples
reveal 'ast://docs?type=heading'                 # Document structure
```

### The Performance Hunt

```bash
# Find optimization targets
reveal 'ast://./src?lines>100'                   # Big functions
reveal 'ast://./src?complexity>15'               # Complex functions
reveal 'ast://./src?lines>50&complexity<3'       # Long but simple (inline?)
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Structure | `reveal file.py` |
| Hierarchy | `reveal file.py --outline` |
| Extract | `reveal file.py function_name` |
| Complex | `reveal 'ast://.?complexity>10'` |
| Long | `reveal 'ast://.?lines>50'` |
| Named | `reveal 'ast://.?name=test_*'` |
| Check | `reveal file.py --check` |
| Links | `reveal doc.md --links` |
| Code | `reveal doc.md --code` |
| Pipeline | `git diff --name-only \| reveal --stdin` |
| Python env | `reveal python://doctor` |
| Imports | `reveal python://module/name` |
| JSON | `reveal file.py --format=json` |
| Slice | `reveal file.py --head 5` |
| Help | `reveal help://` |

---

## See Also

- `reveal --agent-help` - Quick reference for AI agents
- `reveal help://anti-patterns` - What NOT to do
- `reveal help://python-guide` - Deep dive on Python adapter
- [ROADMAP.md](ROADMAP.md) - Future features

---

*Part of [Semantic Infrastructure Lab](https://github.com/semantic-infrastructure-lab/sil)*
