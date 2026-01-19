---
title: Reveal Workflow Recipes
type: documentation
category: workflows
date: 2026-01-15
---

# Reveal Workflow Recipes

**Task-based patterns for getting work done**

This guide organizes reveal commands by workflow, not by feature. Find your task, get the commands.

---

## Table of Contents

- [Code Review](#code-review)
- [Onboarding & Exploration](#onboarding--exploration)
- [Debugging & Troubleshooting](#debugging--troubleshooting)
- [Refactoring & Quality](#refactoring--quality)
- [Documentation Maintenance](#documentation-maintenance)
- [AI Agent Integration](#ai-agent-integration)
- [Database Operations](#database-operations)
- [Pipeline Integration](#pipeline-integration)

---

## Code Review

### See what changed structurally

```bash
# Compare branches
reveal diff://git://main/.:git://feature/.

# Pre-commit check (what did I actually change?)
reveal diff://git://HEAD/src/:src/

# Compare specific files
reveal diff://app.py:backup/app.py

# See commit impact
reveal diff://git://HEAD~1/src/:git://HEAD/src/
```

**What you get:** Functions/classes added, removed, modified. Complexity changes. Import changes.

### Check quality before merge

```bash
# Run all checks
reveal src/ --check

# Security + bugs only (fast)
reveal src/ --check --select B,S

# Specific file
reveal src/auth.py --check --select B,S
```

### Review specific changes

```bash
# See what's in a file
reveal src/app.py

# Extract specific function
reveal src/app.py handle_request

# Check complexity of changed functions
reveal 'ast://src/?complexity>10'
```

---

## Onboarding & Exploration

### Map a new codebase

```bash
# 1. See high-level structure
reveal .

# 2. Explore main directories
reveal src/
reveal tests/

# 3. Find entry points
reveal src/main.py
reveal src/__init__.py

# 4. Drill into key functions
reveal src/main.py main
reveal src/app.py create_app
```

### Find patterns

```bash
# Find all authentication-related code
reveal 'ast://./src?name=*auth*'

# Find complex functions (likely important or buggy)
reveal 'ast://./src?complexity>10'

# Find long functions (refactor candidates)
reveal 'ast://./src?lines>50'

# Combine filters (complex AND long)
reveal 'ast://./src?complexity>10&lines>50'
```

### Understand architecture

```bash
# See all imports
reveal imports://src/

# Find circular dependencies
reveal 'imports://src?circular'

# Check layer violations
reveal 'imports://src?violations'

# Get statistics
reveal stats://./src
```

---

## Debugging & Troubleshooting

### Python environment issues

```bash
# Full health check
reveal python://doctor

# Check specific module (import shadowing?)
reveal python://module/requests

# Analyze sys.path conflicts
reveal python://syspath

# Find stale bytecode
reveal python://debug/bytecode

# See virtual environment status
reveal python://venv

# Check installed packages
reveal python://packages
```

### Find the code behind the error

```bash
# Locate error handling
reveal 'ast://src?name=*error*'
reveal 'ast://src?name=*exception*'

# Find specific handler
reveal src/handlers.py error_handler

# Check environment configuration
reveal env://
reveal env://DATABASE_URL
```

### Trace execution paths

```bash
# Find entry points
reveal src/main.py

# Locate middleware/handlers
reveal 'ast://src?name=*handler*'
reveal 'ast://src?name=*middleware*'

# Check complex code paths
reveal 'ast://src?complexity>15'
```

---

## Refactoring & Quality

### Find technical debt

```bash
# Quality hotspots (worst files first)
reveal stats://./src --hotspots

# Complex functions across codebase
reveal 'ast://./src?complexity>10'

# Long functions
reveal 'ast://./src?lines>100'

# Code golf (complex but short - suspicious)
reveal 'ast://./src?complexity>10&lines<50'
```

### Before refactoring

```bash
# Capture current state
reveal src/module.py function_name

# Check current complexity
reveal src/module.py --check --select C

# See current structure
reveal src/module.py --outline
```

### After refactoring

```bash
# Verify structural changes
reveal diff://git://HEAD/src/module.py:src/module.py

# Check quality didn't degrade
reveal src/module.py --check

# Ensure no circular imports introduced
reveal 'imports://src?circular'
```

### Find duplication

```bash
# Check for duplicate code
reveal src/ --check --select D

# Specific duplication check
reveal src/module.py --check --select D001,D002
```

---

## Documentation Maintenance

### Validate markdown frontmatter

```bash
# Session READMEs
reveal sessions/*/README.md --validate-schema session

# Hugo blog posts
reveal content/posts/*.md --validate-schema hugo

# Jekyll/GitHub Pages
reveal _posts/*.md --validate-schema jekyll

# MkDocs
reveal docs/**/*.md --validate-schema mkdocs
```

### Find docs by metadata

```bash
# Find all docs on a topic
reveal 'markdown://docs/?topics=authentication'

# Find incomplete docs
reveal 'markdown://docs/?status=draft'

# Find docs with specific tag
reveal 'markdown://?tags=python'

# Find docs missing metadata
reveal 'markdown://?!topics'
```

### Validate links

```bash
# Check all link rules
reveal docs/ --check --select L

# Fast check (internal links + routing only)
reveal docs/ --check --select L001,L003

# Full check including external links (slow)
reveal docs/ --check --select L
```

### Extract frontmatter

```bash
# See frontmatter structure
reveal docs/page.md --frontmatter

# Get as JSON for scripting
reveal docs/page.md --frontmatter --format=json
```

---

## AI Agent Integration

### Progressive disclosure pattern

```bash
# 1. Orient - Get directory structure (50 tokens)
reveal src/

# 2. Navigate - See file structure (200 tokens)
reveal src/app.py

# 3. Focus - Extract specific code (100 tokens)
reveal src/app.py Database

# Total: 350 tokens vs 7,500 for reading full files
```

### Query before reading

```bash
# Find relevant code without reading everything
reveal 'ast://./src?name=*config*'

# Filter by complexity
reveal 'ast://./src?complexity>5'

# Get structured output for parsing
reveal 'ast://./src?name=*auth*' --format=json
```

### Validation workflow

```bash
# Check code quality
reveal src/ --check --format=json

# Validate markdown metadata
reveal README.md --validate-schema session --format=json

# Get diff summary
reveal diff://git://HEAD/src/:src/ --format=json
```

### Self-referential (meta usage)

```bash
# Extract reveal's own implementation
reveal reveal://analyzers/markdown.py MarkdownAnalyzer

# Learn adapter patterns
reveal reveal://adapters/base.py ResourceAdapter

# Study rule implementation
reveal reveal://rules/complexity/C901.py
```

---

## Database Operations

### SQLite inspection

```bash
# Database overview
reveal sqlite:///path/to/app.db

# Table structure
reveal sqlite:///path/to/app.db/users

# Get as JSON
reveal sqlite:///app.db --format=json
```

### MySQL inspection (requires [database] extra)

```bash
# Database health
reveal mysql://localhost

# Performance metrics
reveal mysql://localhost/performance

# Index analysis
reveal mysql://localhost/indexes

# Slow queries
reveal mysql://localhost/slow-queries

# InnoDB status
reveal mysql://localhost/innodb
```

### Schema drift detection

```bash
# Compare database schemas
reveal diff://mysql://localhost/users:mysql://staging/users

# Compare SQLite schemas
reveal diff://sqlite://./dev.db:sqlite://./prod.db
```

---

## Pipeline Integration

### Unix pipelines

```bash
# Process changed files
git diff --name-only | reveal --stdin --outline

# Find complex functions in changed files
git diff --name-only origin/main | grep "\.py$" | reveal --stdin --format=json

# CI/CD quality gate
git diff --name-only origin/main | reveal --stdin --check --format=grep
```

### JSON processing

```bash
# Extract function info
reveal src/app.py --format=json | jq '.functions'

# Find large functions
reveal src/ --format=json | jq '.functions[] | select(.line_count > 100)'

# Get complexity metrics
reveal stats://src/ --format=json | jq '.quality_score'
```

### Batch operations

```bash
# Check multiple files
find src/ -name "*.py" -print0 | xargs -0 -I {} reveal {} --check

# Process all markdown
fd -e md | reveal --stdin --validate-schema hugo

# Get structure of all files
fd -e py | reveal --stdin --format=json > structure.json
```

### Clipboard integration

```bash
# Copy function to clipboard
reveal src/app.py handle_request --copy

# Copy structure as JSON
reveal src/app.py --format=json --copy
```

---

## Quick Reference

### Discovery commands (find before you read)

```bash
reveal .                                 # Map directory structure
reveal src/                              # Explore subdirectory
reveal 'ast://./src?name=*pattern*'      # Find by name
reveal 'ast://./src?complexity>10'       # Find by complexity
reveal 'imports://src?circular'          # Find circular imports
reveal stats://./src --hotspots          # Find technical debt
```

### Inspection commands (understand structure)

```bash
reveal file.py                           # File structure
reveal file.py --outline                 # Hierarchical view
reveal file.py function_name             # Extract specific code
reveal file.py --format=json             # Structured output
```

### Validation commands (check quality)

```bash
reveal file.py --check                   # All rules
reveal file.py --check --select B,S     # Specific categories
reveal --rules                           # List all rules
reveal --explain B001                    # Explain specific rule
```

### Comparison commands (see changes)

```bash
reveal diff://file1.py:file2.py         # Compare files
reveal diff://git://HEAD/.:src/         # Pre-commit check
reveal diff://git://main/.:git://feat/. # Branch comparison
```

### Configuration commands

```bash
reveal reveal://config                   # Show active config
reveal env://                            # Environment variables
reveal python://doctor                   # Python health check
```

---

## Tips & Tricks

### Performance optimization

```bash
# Fast mode (skip line counting, ~6x faster)
reveal src/ --fast

# Limit directory entries
reveal node_modules/ --max-entries 50

# Control tree depth
reveal . --depth 2
```

### Format selection

- **text** (default): Human-readable, colorized
- **json**: Machine-readable, parseable
- **grep**: Pipeline-friendly (path:line format)
- **--meta**: Metadata only (no code)

### Rule categories

- **B** - Bugs and anti-patterns
- **S** - Security vulnerabilities
- **C** - Complexity metrics
- **E** - Errors and syntax issues
- **D** - Duplicate code detection
- **F** - Frontmatter validation
- **I** - Import analysis
- **L** - Link validation
- **M** - Maintainability issues
- **N** - Nginx configuration
- **V** - Validation rules (self-check)

### AST query operators

- `name=pattern` - Wildcard matching (`*auth*`, `test_*`)
- `complexity>N` - Cyclomatic complexity threshold
- `lines>N` - Function line count
- `type=X` - Element type (function, class, method)
- `depth>N` - Nesting depth
- `&` - Combine filters (AND logic)

---

## Getting Help

```bash
# List all adapters
reveal help://

# Adapter-specific help
reveal help://ast
reveal help://python
reveal help://diff

# Comprehensive guides
reveal help://tricks                # Hidden features
reveal help://anti-patterns         # Common mistakes
reveal help://adapter-authoring     # Create custom adapters

# Agent documentation
reveal --agent-help                 # Quick reference
reveal --agent-help-full            # Complete guide
```

---

**See also:**
- [AGENT_HELP.md](reveal/docs/AGENT_HELP.md) - AI agent reference
- [COOL_TRICKS.md](reveal/docs/COOL_TRICKS.md) - Advanced features
- [README.md](README.md) - Feature overview
