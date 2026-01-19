# Reveal Quick Start (5 Minutes)

**Get productive with reveal in 5 minutes.**

---

## Installation

```bash
pip install reveal-cli
```

**That's it.** Zero configuration required.

---

## Three Core Concepts

Reveal works in three modes based on what you pass it:

| Input | Output | Token Savings |
|-------|--------|---------------|
| **Directory** | Tree view (what files exist) | 10-20x vs `ls -R` |
| **File** | Structure (functions, classes) | 50-100x vs `cat` |
| **File:Element** | Extracted code (specific function) | 20-50x vs `grep` |

---

## Example 1: Explore a Directory (10 seconds)

```bash
reveal src/
```

**Output:**
```
src/
├── app.py (247 lines, Python)
├── database.py (189 lines, Python)
└── models/
    ├── user.py (156 lines, Python)
    └── post.py (203 lines, Python)
```

**What you learned:**
- Which files exist
- Their sizes
- Their languages
- Directory structure

**Next:** Pick a file to explore.

---

## Example 2: Understand a File (30 seconds)

```bash
reveal src/app.py
```

**Output:**
```
File: app.py (7.2KB, 247 lines)

Imports (3):
  :1      import os
  :2      import sys
  :3      from typing import Dict

Functions (5):
  :15     load_config(path: str) -> Dict [12 lines, depth:1]
  :28     setup_logging(level: str) -> None [8 lines, depth:1]
  :37     connect_db() -> Database [15 lines, depth:2]
  :53     handle_request(req: Request) -> Response [32 lines, depth:3]
  :86     main() -> None [9 lines, depth:2]

Classes (2):
  :95     Database
  :145    RequestHandler
```

**What you learned:**
- What functions exist (and their signatures)
- How complex they are (depth = nesting level)
- How big they are (lines)
- What classes exist
- Import dependencies

**Token cost:** ~100 tokens (vs 7,500 for full file)

**Next:** Extract a specific function to understand its logic.

---

## Example 3: Extract Specific Code (15 seconds)

```bash
reveal src/app.py load_config
```

**Output:**
```
app.py:15-27 | load_config

   15  def load_config(path: str) -> Dict:
   16      """Load configuration from JSON file."""
   17      if not os.path.exists(path):
   18          raise FileNotFoundError(f"Config not found: {path}")
   19      with open(path) as f:
   20          return json.load(f)
```

**What you learned:**
- Exact implementation of `load_config`
- Line numbers (works with vim, IDEs, git)
- Only saw what you needed (not 247 lines)

**Token cost:** ~50 tokens (vs 7,500 for full file)

---

## Filtering: See Less

**Problem:** Too many results? Filter them.

```bash
# Show first 5 functions only
reveal src/app.py --head 5

# Show last 3 classes only
reveal src/app.py --tail 3

# Show functions 10-20
reveal src/app.py --range 10:20
```

---

## Progressive Disclosure Workflow

**The reveal way:** Start broad, drill down progressively.

```bash
# Step 1: What files exist?
reveal src/

# Step 2: What's in this file?
reveal src/app.py

# Step 3: Extract what I need
reveal src/app.py handle_request
```

**Why this matters:**
- **Token efficiency:** 100 tokens instead of 7,500
- **Cognitive clarity:** See structure before details
- **Time savings:** Find what you need without reading everything

---

## Real-World Task: Code Review

**Task:** Review a pull request for a feature branch.

**Old way (❌):**
```bash
git diff main..feature | cat
# 15,000 lines of diff
# 500,000 tokens
# 10 minutes to read
```

**Reveal way (✅):**
```bash
# What changed structurally?
reveal diff://git://main/.:git://feature/.

# Output shows:
# - Which functions were added/removed/modified
# - Which files changed
# - No noise from whitespace or comments

# Token cost: ~500 tokens (1000x reduction)
# Time: 30 seconds
```

---

## Real-World Task: Onboard to New Codebase

**Task:** Understand a new project you just cloned.

**Old way (❌):**
```bash
find . -name "*.py" | xargs cat
# Read everything
# 100,000+ lines
# 2,500,000+ tokens
# Hours of work
```

**Reveal way (✅):**
```bash
# Step 1: Map the repo (30 seconds)
reveal .

# Step 2: Find the entry point (30 seconds)
reveal src/main.py

# Step 3: Understand the main flow (1 minute)
reveal src/main.py main
reveal src/app.py handle_request
reveal src/database.py connect

# Total: 2 minutes, <1000 tokens
```

---

## Real-World Task: Find Complex Code

**Task:** Find technical debt hotspots.

```bash
# Find all functions with complexity > 10
reveal 'ast://./src?complexity>10'

# Output:
# src/app.py:53   handle_request [32 lines, complexity: 15]
# src/auth.py:87  validate_token [45 lines, complexity: 12]
# src/db.py:123   migrate_schema [78 lines, complexity: 18]
```

**What you learned:**
- Where complexity lives
- Which functions to refactor first
- Prioritized by actual metrics (not guesses)

---

## Advanced: URI Adapters

Reveal has **13 URI adapters** for specialized queries:

```bash
# Query code structure
reveal 'ast://./src?complexity>10&lines<50'

# Git blame a specific function
reveal 'git://src/app.py?type=blame&element=handle_request'

# Analyze imports and dependencies
reveal 'imports://./src'

# Compare two files structurally
reveal 'diff://file1.py:file2.py'

# Get codebase statistics
reveal 'stats://.'

# Query markdown by front matter
reveal 'markdown://?category=guide'
```

**Learn more:**
```bash
reveal help://           # List all adapters
reveal help://ast        # Learn about ast:// queries
reveal help://git        # Learn about git:// adapter
```

---

## Help System

**Built-in documentation:**
```bash
reveal --help                    # CLI help
reveal --agent-help              # AI agent quick reference
reveal help://                   # List all help topics
reveal help://markdown-guide     # Specific guide
reveal help://cool-tricks        # Power user workflows
reveal help://anti-patterns      # What NOT to do
```

---

## Key Takeaways

1. **Structure before content** - See what exists before reading code
2. **Progressive disclosure** - Directory → File → Element
3. **Token efficiency** - 10-150x fewer tokens than cat/grep
4. **Line numbers** - All output is `file:line` format (vim compatible)
5. **Zero config** - Works out of the box on 41 languages

---

## Next Steps

**New users:**
1. [MARKDOWN_GUIDE.md](MARKDOWN_GUIDE.md) - Complete feature reference
2. [COOL_TRICKS.md](COOL_TRICKS.md) - Power user workflows
3. [ANTI_PATTERNS.md](ANTI_PATTERNS.md) - What NOT to do

**AI agents:**
1. [AGENT_HELP.md](AGENT_HELP.md) - Quick reference for AI
2. [AGENT_HELP_FULL.md](AGENT_HELP_FULL.md) - Comprehensive guide

**Developers:**
1. [ADAPTER_AUTHORING_GUIDE.md](ADAPTER_AUTHORING_GUIDE.md) - Extend reveal
2. [ANALYZER_PATTERNS.md](ANALYZER_PATTERNS.md) - Code analysis patterns

---

**Got 5 more minutes?** Read [COOL_TRICKS.md](COOL_TRICKS.md) for practical workflows.

**Still confused?** Check [ANTI_PATTERNS.md](ANTI_PATTERNS.md) for common mistakes.

**Ready to go deep?** Read [MARKDOWN_GUIDE.md](MARKDOWN_GUIDE.md) for complete reference.

---

**Document metadata:**
- **Last updated:** 2026-01-19
- **Reveal version:** 0.38.0+
- **Reading time:** 5 minutes
- **Target audience:** New users, onboarding

---

**Navigation:** [← Documentation Index](README.md) | [Full Guide →](MARKDOWN_GUIDE.md) | [Power Tricks →](COOL_TRICKS.md)
