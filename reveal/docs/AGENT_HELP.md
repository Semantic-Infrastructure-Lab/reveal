# Reveal - AI Agent Reference
**Version:** 0.36.1
**Purpose:** Practical patterns for AI code assistants
**Token Cost:** ~2,400 tokens
**Audience:** AI agents (Claude Code, Copilot, Cursor, etc.)

---

## Core Rule: Structure Before Content

**Always use reveal instead of cat/grep/find for code files.**

❌ DON'T: `cat file.py` (wastes 7,500 tokens)
✅ DO: `reveal file.py` (uses 100 tokens, shows structure)

**Token savings:** 10-150x reduction

---

## Critical Pattern: Codebase Assessment

**Problem:** AI agents waste 80% more commands and 81% more tokens assessing codebases.

**Anti-pattern (8 commands, 1,600 tokens, 90 seconds):**
```bash
find . -name "*.py" | wc -l          # Count Python files
find . -name "*.js" | wc -l          # Count JS files
find . -type f | wc -l               # Total files
du -sh .                              # Size
wc -l $(find . -name "*.py")         # Total lines
# ... more ad-hoc commands
```

**✅ Correct pattern (1 command, 300 tokens, 15 seconds):**
```bash
# Get comprehensive codebase metrics
reveal stats://./

# Focus on code files only (excludes data/config)
reveal stats://./?type=python

# JSON for scripting
reveal stats://. --format=json
```

**What you get from stats://:**
```
📊 Codebase Statistics: /path/to/project

Files by Language:
  Python         43 files    12,458 lines    (82.3%)
  JavaScript     12 files     2,134 lines    (14.1%)
  JSON            8 files       542 lines     (3.6%)

Quality Scores:
  Complexity: 7.2/10 (healthy)
  Maintainability: 8.1/10 (good)

Top Issues:
  C901: 12 functions exceed complexity threshold
  B005: 3 mutable default arguments

Health: 🟢 HEALTHY
```

**Impact measurement (real agent session):**
- **Before:** 8 commands, 1,600 tokens, 90s, incomplete metrics
- **After:** 1 command, 300 tokens, 15s, complete metrics + quality scores
- **Improvement:** 81% fewer tokens, 83% faster

**When to use:**
- First encounter with unfamiliar codebase
- Project health assessment
- Finding complexity hotspots
- Scoping refactoring work
- Reporting codebase status

**URI parameters:**
- `?type=python` - Filter to specific language
- `?min_lines=50` - Only files with 50+ lines
- `?hotspots=true` - Show quality hotspots (most complex files)

**See also:** `reveal help://stats` for full stats:// capabilities

---

## Common Tasks → Reveal Patterns

### Task: "Understand unfamiliar code"

**Pattern:**
```bash
# 1. See directory structure
reveal src/

# 2. Pick interesting file, see its structure
reveal src/main.py

# 3. Extract specific function you need
reveal src/main.py load_config
```

**Why this works:** Progressive disclosure. Don't read entire files.

**Example output:**
```
File: src/main.py (342 lines, Python)

Imports (5):
  import os
  import sys
  from pathlib import Path

Functions (8):
  load_config [12 lines, depth:1] (line 45)
  parse_args [8 lines, depth:1] (line 58)
  ...
```

---

### Task: "Find where X is implemented"

**Pattern:**
```bash
# Find functions by name pattern
reveal 'ast://./src?name=*authenticate*'

# Find complex code (likely buggy)
reveal 'ast://./src?complexity>10'

# Find long functions (refactor candidates)
reveal 'ast://./src?lines>50'

# Combine filters
reveal 'ast://./src?complexity>10&lines>50'
```

**Why this works:** AST queries don't require reading files. Searches across entire codebase instantly.

**Available filters:**
- `name=pattern` - Wildcard matching (test_*, *helper*, etc.)
- `complexity>N` - Cyclomatic complexity threshold
- `lines>N` - Function line count
- `type=X` - Element type (function, class, method)
- `depth>N` - Nesting depth

---

### Task: "Review code quality"

**Pattern:**
```bash
# Check all quality rules
reveal file.py --check

# Check specific categories (faster)
reveal file.py --check --select B,S    # Bugs & security
reveal file.py --check --select C,E    # Complexity & errors

# Specific file types
reveal Dockerfile --check              # Docker best practices
reveal nginx.conf --check              # Nginx validation
```

**Available rule categories:**
- **B** (bugs) - Common code bugs and anti-patterns
- **S** (security) - Security vulnerabilities
- **C** (complexity) - Code complexity metrics
- **E** (errors) - Syntax errors and issues
- **D** (duplicates) - Duplicate code detection
- **N** (nginx) - Nginx configuration issues
- **V** (validation) - General validation rules

**List all rules:** `reveal --rules`
**Explain rule:** `reveal --explain B001`

---

### Task: "Validate Markdown front matter"

**Pattern:**
```bash
# Validate session README
reveal README.md --validate-schema session

# Validate Hugo blog post or static page
reveal content/posts/article.md --validate-schema hugo

# Validate Jekyll post (GitHub Pages)
reveal _posts/2026-01-03-my-post.md --validate-schema jekyll

# Validate MkDocs documentation
reveal docs/api/reference.md --validate-schema mkdocs

# Validate Obsidian note
reveal vault/notes/project.md --validate-schema obsidian

# Use custom schema
reveal document.md --validate-schema /path/to/custom-schema.yaml

# JSON output for CI/CD
reveal README.md --validate-schema session --format json

# Select specific validation rules
reveal README.md --validate-schema session --select F003,F004
```

**Why this works:** Schema validation ensures consistent front matter across markdown files. Essential for documentation sites (Hugo, MkDocs), GitHub Pages (Jekyll), and knowledge bases (Obsidian).

**Built-in schemas:**
- **session** - Session/workflow READMEs (requires `session_id`, `topics`)
- **hugo** - Hugo static sites (requires `title`)
- **jekyll** - Jekyll sites / GitHub Pages (requires `layout`)
- **mkdocs** - MkDocs documentation (all fields optional)
- **obsidian** - Obsidian vaults (all fields optional)

**Validation rules (F-series):**
- **F001** - Missing front matter
- **F002** - Empty front matter
- **F003** - Required field missing
- **F004** - Field type mismatch
- **F005** - Custom validation failed

**Exit codes:**
- `0` - Validation passed
- `1` - Validation failed (use in CI/CD)

**See also:** [Schema Validation Help](SCHEMA_VALIDATION_HELP.md)

---

### Task: "Find markdown files by metadata"

**Pattern:**
```bash
# List all markdown files in docs/
reveal markdown://docs/

# Find files by specific field value
reveal 'markdown://sessions/?topics=reveal'

# Find files with specific tag
reveal 'markdown://docs/?tags=python'

# Find files missing required metadata
reveal 'markdown://?!topics'

# Wildcard pattern matching
reveal 'markdown://?type=*guide*'

# Multiple filters (AND logic)
reveal 'markdown://docs/?status=active&type=guide'

# Get paths for piping (grep format)
reveal 'markdown://docs/?topics=reveal' --format=grep

# JSON output for scripting
reveal 'markdown://docs/?status=draft' --format=json
```

**Why this works:** Queries markdown files by front matter fields. Essential for finding related documentation, identifying files missing metadata, or filtering by topic.

**Query syntax:**
- `field=value` - Exact match (or contains for list fields)
- `field=*pattern*` - Glob-style wildcard matching
- `!field` - Files missing this field
- `field1=val1&field2=val2` - Multiple filters (AND)

**Use cases:**
- Find all docs related to a topic: `markdown://?topics=authentication`
- Find draft content: `markdown://?status=draft`
- Quality check - find missing metadata: `markdown://?!title`
- Combine with `--related`: Find docs, then traverse their links

---

### Task: "Extract specific code element"

**Pattern:**
```bash
# Extract function
reveal app.py process_request

# Extract class
reveal app.py DatabaseHandler

# Extract specific lines
reveal app.py --range 42-80

# Get first/last functions (bugs cluster at end!)
reveal app.py --head 5
reveal app.py --tail 5
```

**Why tail is useful:** Bugs and technical debt often cluster at the end of files. `--tail 5` shows the last 5 functions added.

---

### Task: "Debug Python environment issues"

**Pattern:**
```bash
# Quick environment check
reveal python://

# Check for stale .pyc bytecode (common issue!)
reveal python://debug/bytecode

# Check virtual environment
reveal python://venv

# List installed packages
reveal python://packages

# Get details on specific package
reveal python://packages/requests
```

**Common scenario:** "My code changes aren't working!"
**Solution:** `reveal python://debug/bytecode` detects stale .pyc files

**python:// adapter provides:**
- Python version and interpreter path
- Virtual environment detection
- Package inventory (pip list equivalent)
- sys.path inspection
- Stale bytecode detection
- Environment variables (PYTHONPATH, etc.)

---

### Task: "Navigate JSON/JSONL files"

**Pattern:**
```bash
# Access nested keys
reveal json://config.json/database/host

# Array access
reveal json://data.json/users/0
reveal json://data.json/users[-1]      # Last item

# Array slicing
reveal json://data.json/users[0:5]

# Get structure overview
reveal json://config.json?schema

# Make grep-able (gron-style)
reveal json://config.json?flatten

# JSONL: Get specific records
reveal conversation.jsonl --head 10    # First 10 records
reveal conversation.jsonl --tail 5     # Last 5 records
reveal conversation.jsonl --range 48-52 # Records 48-52
reveal conversation.jsonl 42           # Specific record
```

**JSONL is different:** Each line is a separate JSON object. Use `--head`, `--tail`, `--range` to navigate records without loading entire file.

---

### Task: "Review pull request / git changes"

**Pattern:**
```bash
# See structure of changed files
git diff --name-only | reveal --stdin --outline

# Check quality on changed Python files
git diff --name-only | grep "\.py$" | reveal --stdin --check

# Deep dive on specific changed file
reveal src/changed_file.py --check
reveal src/changed_file.py changed_function
```

**--stdin mode:** Feed file paths via stdin. Works with `git diff`, `find`, `ls`, etc.

---

### Task: "Understand file relationships"

**Pattern:**
```bash
# See imports
reveal app.py --format=json | jq '.structure.imports[]'

# See class hierarchy
reveal app.py --outline

# Find what imports a module
grep -r "import database" src/

# See all functions in directory
find src/ -name "*.py" | reveal --stdin --format=json | \
  jq '.structure.functions[] | {file, name, lines: .line_count}'
```

**--outline flag:** Shows hierarchical structure (classes with their methods, nested functions, etc.)

---

### Task: "Find duplicate code"

**Pattern:**
```bash
# Within a single file (only what's implemented)
reveal file.py --check --select D001

# D001: Exact duplicates (hash-based, reliable) ✅
# D002: Similar code (experimental, ~90% false positives) ⚠️
```

**Cross-file detection (workaround using AST):**
```bash
# Find functions with similar names
reveal 'ast://./src?name=*parse*'
reveal 'ast://./src?name=*validate*'
reveal 'ast://./src?name=*process*'

# Find duplication-prone code
reveal 'ast://./src?complexity>10&lines>50'

# Check hotspot files (URI param - preferred)
reveal 'stats://./src?hotspots=true'
```

**Note:** Cross-file duplicate detection not yet implemented. D001/D002 only work within single files. See `reveal/DUPLICATE_DETECTION_GUIDE.md` for comprehensive workflows.

---

### Task: "Validate configuration files"

**Pattern:**
```bash
# Nginx configuration
reveal nginx.conf --check              # N001-N003 rules
# - N001: Duplicate backends (upstreams with same server:port)
# - N002: Missing SSL certificates
# - N003: Missing proxy headers

# Dockerfile
reveal Dockerfile --check              # S701 rule
# - S701: Security best practices

# YAML/TOML
reveal config.yaml                     # Structure view
reveal pyproject.toml                  # Structure view
```

---

### Task: "Debug reveal configuration"

**Pattern:**
```bash
# See active configuration with sources
reveal reveal://config

# Check if environment variable is set
REVEAL_C901_THRESHOLD=30 reveal reveal://config

# Export config as JSON for scripting
reveal reveal://config --format json
```

**Why this works:** Shows exactly what configuration is active and where it comes from (environment variables, config files, CLI flags, defaults). Displays 7-level precedence hierarchy for debugging.

**Use cases:**
- Troubleshoot why a rule isn't being applied
- Verify environment variables are being picked up
- See which config file is being used (project vs user vs system)
- Debug precedence issues (which config source wins)

---

## Output Formats

**Choose format based on use case:**

```bash
# Human-readable (default)
reveal file.py

# JSON for scripting
reveal file.py --format=json

# Grep-friendly (name:line format)
reveal file.py --format=grep

# Typed JSON (with relationships)
reveal file.py --format=typed

# Copy to clipboard
reveal file.py --copy
```

**JSON + jq filtering:**
```bash
# Find complex functions
reveal app.py --format=json | jq '.structure.functions[] | select(.depth > 3)'

# Find functions > 50 lines
reveal app.py --format=json | jq '.structure.functions[] | select(.line_count > 50)'

# List all classes
reveal app.py --format=json | jq '.structure.classes[].name'
```

---

## Markdown-Specific Features

**Pattern:**
```bash
# Extract all links
reveal doc.md --links

# Only external links
reveal doc.md --links --link-type external

# Only internal links (broken link detection)
reveal doc.md --links --link-type internal

# Extract code blocks
reveal doc.md --code

# Only Python code blocks
reveal doc.md --code --language python

# Get YAML frontmatter
reveal doc.md --frontmatter

# Navigate related documents (from front matter)
reveal doc.md --related

# Follow related links recursively (depth 3)
reveal doc.md --related --related-depth 3

# Follow ALL related links (unlimited depth)
reveal doc.md --related-all

# Get flat list of paths for piping
reveal doc.md --related-all --related-flat | xargs reveal

# Limit traversal to 50 files
reveal doc.md --related-all --related-limit 50
```

**Link types:**
- `internal` - Relative links (./file.md, ../other.md)
- `external` - HTTP/HTTPS links
- `email` - mailto: links
- `all` - All link types

---

## When reveal Won't Help

**Don't use reveal for:**
- Binary files (use file-specific tools)
- Very large files >10MB (performance degrades)
- Real-time log tailing (use `tail -f`)
- Text search across many files (use `ripgrep`/`grep`)
- Compiled binaries (use `objdump`, etc.)

**Use reveal for:**
- Understanding code structure
- Extracting specific functions/classes
- Quality checks
- Progressive file exploration
- Python environment debugging
- Config file validation

---

## File Type Support

**reveal auto-detects and provides structure for:**

**Languages:** Python, JavaScript, TypeScript, Rust, Go, Java, C, C++, C#, Scala, GDScript, Bash, SQL, PHP, Ruby, Lua (16 languages)

**Configs:** Nginx, Dockerfile, TOML, YAML, JSON, JSONL

**Documents:** Markdown, HTML, Jupyter notebooks

**Office:** Excel (.xlsx), Word (.docx), PowerPoint (.pptx), LibreOffice (.odt/.ods/.odp)

**Check supported types:** `reveal --list-supported`

---

## Advanced: Pipeline Workflows

**reveal works in Unix pipelines:**

```bash
# Check all Python files
find src/ -name "*.py" | reveal --stdin --check

# Get outline of modified files
git diff --name-only | reveal --stdin --outline

# Find complex functions across codebase
find . -name "*.py" | reveal --stdin --format=json | \
  jq '.structure.functions[] | select(.depth > 3)'

# Quality check on recent commits
git diff HEAD~5 --name-only | reveal --stdin --check
```

---

## Real-World Examples

### Example 1: "User reports auth bug"

```bash
# Find auth-related code
reveal 'ast://./src?name=*auth*'

# Found: src/auth/handler.py authenticate_user()
# Check structure
reveal src/auth/handler.py

# Extract suspect function
reveal src/auth/handler.py authenticate_user

# Quality check
reveal src/auth/handler.py --check --select B,S
```

### Example 2: "Need to refactor complex code"

```bash
# Find complex functions
reveal 'ast://./src?complexity>10&lines>50'

# Found: src/processor.py process_request (complexity: 15, 87 lines)
# See structure
reveal src/processor.py --outline

# Extract function
reveal src/processor.py process_request

# Check for issues
reveal src/processor.py --check
```

### Example 3: "Setup not working in new environment"

```bash
# Check Python environment
reveal python://

# Check for stale bytecode
reveal python://debug/bytecode

# Check virtual environment
reveal python://venv

# Verify package installed
reveal python://packages/fastapi
```

### Example 4: "Review PR changes"

```bash
# See what changed
git diff --name-only

# Get structure of changed files
git diff --name-only | reveal --stdin --outline

# Quality check Python files
git diff --name-only | grep "\.py$" | reveal --stdin --check

# Deep dive on specific file
reveal src/modified.py --check
reveal src/modified.py new_function
```

---

## Troubleshooting

**If reveal doesn't work on a file:**
```bash
# Check file type detection
reveal file.py --meta

# Try without fallback (see if TreeSitter parser exists)
reveal file.py --no-fallback
```

**If structure is incomplete:**
- Tree-sitter parser may not support that syntax
- File may have syntax errors
- Try `--outline` for hierarchical view

**If quality checks seem wrong:**
```bash
# See which rules triggered
reveal file.py --check

# Explain specific rule
reveal --explain B001

# List all available rules
reveal --rules
```

**If performance is slow:**
```bash
# Use --fast mode (skips line counting)
reveal large_dir/ --fast

# Limit tree depth
reveal deep_dir/ --depth 2

# Limit entries shown
reveal huge_dir/ --max-entries 100
```

---

## Quick Reference Card

| Task | Command |
|------|---------|
| See directory structure | `reveal src/` |
| See file structure | `reveal file.py` |
| Extract function | `reveal file.py func_name` |
| Quality check | `reveal file.py --check` |
| Find complex code | `reveal 'ast://./src?complexity>10'` |
| Debug Python env | `reveal python://debug/bytecode` |
| Navigate JSON | `reveal json://file.json/path/to/key` |
| JSONL records | `reveal file.jsonl --head 10` |
| Check changes | `git diff --name-only \| reveal --stdin --check` |
| Get JSON output | `reveal file.py --format=json` |
| Hierarchical view | `reveal file.py --outline` |
| Copy to clipboard | `reveal file.py --copy` |
| Extract links | `reveal doc.md --links` |
| Extract code blocks | `reveal doc.md --code` |

---

## URI Parameters vs Flags

**Rule of thumb:** Adapter-specific features use URI parameters, global features use flags.

**Global flags** (work everywhere):
```bash
--format=json         # Output format
--outline             # Hierarchical view
--check               # Run quality checks
--head/--tail         # Slice output
```

**URI parameters** (adapter-specific):
```bash
stats://src?hotspots=true       # Show quality hotspots
ast://src?complexity>10         # Filter by complexity
stats://src?min_lines=50        # Filter files
```

**Why this matters:**
- `reveal . --hotspots` → ❌ Error (--hotspots only works with stats://)
- `reveal stats://.?hotspots=true` → ✅ Works (URI param)
- `reveal stats://. --hotspots` → ✅ Works but shows migration hint

**Common mistake:**
Using adapter-specific flags on regular paths fails with a clear error message pointing you to the correct syntax.

---

## Help System Overview

**For AI agents (you):**
- **This guide** (`reveal --agent-help`) - Task-based patterns, concrete examples
- **Complete guide** (`reveal --agent-help-full`) - Comprehensive reference (~12K tokens)

**For humans:**
- **CLI reference** (`reveal --help`) - All flags and options
- **Progressive help** (`reveal help://`) - Explorable documentation

**You don't need to explore help://** - this guide has the patterns you need. The examples above cover 95% of use cases.

---

## Integration with Other Tools

### With Claude Code workflow
```bash
# 1. Structure first (this is what you should do!)
reveal unknown_file.py            # What's in here? (~100 tokens)

# 2. Then use Read tool on specific functions only
# Don't use Read on entire large files
```

### With grep/ripgrep
```bash
# Find files with keyword
rg -l "authenticate" src/

# Check structure of matches
rg -l "authenticate" src/ | reveal --stdin --outline
```

---

## Key Principles for AI Agents

1. **Structure before content** - Always `reveal` before `Read`
2. **Progressive disclosure** - Start broad, drill down as needed
3. **Use AST queries** - Don't grep when you can query
4. **Quality checks built-in** - Use `--check` proactively
5. **Pipeline friendly** - Combine with git, find, grep via `--stdin`

---

**Version:** 0.36.1
**Last updated:** 2026-01-05
**Source:** https://github.com/Semantic-Infrastructure-Lab/reveal
**PyPI:** https://pypi.org/project/reveal-cli/

---

## What Changed in This Guide

This is a redesigned AI agent reference (Dec 2025). Changes:

- **Task-oriented** - "When you need to do X, use Y"
- **Example-heavy** - Concrete commands that work
- **Realistic** - Written for how AI agents actually behave
- **No exploration prompts** - Direct patterns, not discovery hints
- **Real-world examples** - Actual scenarios you'll encounter

The old version told you to "explore with help://" - this version gives you the patterns directly.

---

## See Also

- [AGENT_HELP_FULL.md](AGENT_HELP_FULL.md) - Comprehensive AI agent reference (41KB)
- [COOL_TRICKS.md](COOL_TRICKS.md) - Practical workflows and token-efficient patterns
- [MARKDOWN_GUIDE.md](MARKDOWN_GUIDE.md) - Core Reveal functionality and examples
- [README.md](README.md) - Documentation hub and navigation
