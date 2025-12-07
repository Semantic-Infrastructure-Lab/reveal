# Reveal - Agent Quick Start

**Version:** 0.17.0
**Token Cost:** ~1,500 tokens (this guide)
**Alternative:** Use `reveal help://` for progressive discovery (~50-500 tokens)

---

## Token-Efficient Help System ⭐

Reveal has a **discoverable help system** via `help://` URIs - always up-to-date, self-documenting.

**Best Practice:** Use `help://` to explore capabilities progressively instead of loading full guides.

---

## Progressive Discovery Pattern

```bash
# 1. Discover what's available
reveal help://                    # List all adapters (~50 tokens)

# 2. Learn about specific capability
reveal help://python              # Python runtime inspection (~200 tokens)
reveal help://ast                 # AST query system (~250 tokens)

# 3. Use it
reveal python://                  # Python environment overview
reveal python://debug/bytecode    # Check for stale .pyc files
reveal 'ast://./src?complexity>10' # Find complex functions
```

**Token efficiency:**
- Progressive exploration: ~50-500 tokens (as needed)
- This quick start: ~1,500 tokens
- Full guide (--agent-help-full): ~12,000 tokens

---

## Available Help Topics

**Discover current list:** `reveal help://`

**As of v0.17.0:**

### URI Adapters (Self-Documenting)
- `help://python` - Python runtime inspection (NEW: bytecode debugging, package info)
- `help://ast` - Query code as AST database (find functions by complexity/size)
- `help://env` - Environment variables explorer
- `help://help` - Help system itself (meta!)

### Guides
- `help://agent` - Same as this file
- `help://agent-full` - Complete comprehensive guide (~12K tokens)

**New adapters auto-appear** - `help://` queries the live adapter registry.

---

## Core Reveal Usage (Quick Reference)

### Structure-First Philosophy

**DO THIS:**
```bash
reveal file.py                    # Structure first (~100 tokens)
reveal file.py target_function    # Then extract what you need (~50 tokens)
```

**NOT THIS:**
```bash
cat file.py                       # Read entire file (~7,500 tokens) ❌
```

**Token savings:** 10-150x reduction

---

### Essential Commands

```bash
# File exploration
reveal src/                       # Directory tree
reveal file.py                    # File structure (functions, classes, imports)
reveal file.py --outline          # Hierarchical view (classes with methods)
reveal file.py function_name      # Extract specific function

# Code quality
reveal file.py --check            # Run all quality checks
reveal file.py --check --select B,S  # Bugs & security only

# Large files (progressive disclosure)
reveal large.py --head 10         # First 10 functions
reveal large.py --tail 5          # Last 5 functions
reveal large.py --range 15-20     # Specific range

# Pipeline workflows
git diff --name-only | reveal --stdin --outline
find src/ -name "*.py" | reveal --stdin --check

# Output formats
reveal file.py --format=json      # JSON (for scripting)
reveal file.py --format=grep      # Pipeable format
```

---

## Python Runtime Inspection (NEW in v0.17.0)

**Common use case:** "My code changes aren't working!" (stale .pyc bytecode)

```bash
# Quick environment check
reveal python://                  # Python version, venv status, package count

# Debug bytecode issues
reveal python://debug/bytecode    # ⚠️  Detects stale .pyc files

# Package management
reveal python://packages          # List all installed packages
reveal python://packages/requests # Details for specific package

# Environment details
reveal python://venv              # Virtual environment status
reveal python://env               # sys.path, flags, encoding
reveal python://imports           # Currently loaded modules
```

**Full documentation:** `reveal help://python`

---

## AST Query System

Find code patterns without reading files:

```bash
# Find complex functions
reveal 'ast://./src?complexity>10'

# Find long functions
reveal 'ast://app.py?lines>50'

# Find all functions (JSON output)
reveal 'ast://.?type=function' --format=json

# Query specific file
reveal 'ast://main.py?type=class'
```

**Full syntax:** `reveal help://ast`

---

## Essential Workflows

### Unknown Codebase
```bash
reveal help://                    # What adapters exist?
reveal src/                       # What's the structure?
reveal src/main.py                # What's in this file?
reveal src/main.py load_config    # Extract specific function
```

### PR Review
```bash
git diff --name-only | reveal --stdin --outline
git diff --name-only | grep "\.py$" | reveal --stdin --check
reveal src/changed_file.py --check
```

### Python Environment Debugging
```bash
reveal python://                  # Environment overview
reveal python://debug/bytecode    # Check for stale .pyc (common issue!)
reveal python://venv              # Virtual environment status
```

### Bug Investigation
```bash
reveal file.py --outline          # See structure
reveal file.py --tail 5           # Last functions (bugs cluster here!)
reveal file.py suspicious_func    # Extract suspect code
reveal file.py --check --select B,E  # Check for bugs & errors
```

---

## Output Formats

```bash
reveal file.py                    # Text (human-readable)
reveal file.py --format=json      # JSON (standard structure)
reveal file.py --format=typed     # JSON with types & relationships
reveal file.py --format=grep      # Pipeable (name:line format)
```

**JSON + jq** (powerful filtering):
```bash
# Find complex functions
reveal app.py --format=json | jq '.structure.functions[] | select(.depth > 3)'

# List all imports
reveal app.py --format=json | jq '.structure.imports[]'
```

---

## When to Use --agent-help-full

**Use the full guide when:**
- Cannot make multiple reveal calls (API/token constraints)
- Working in restricted environment (no file system access)
- Need complete offline reference

**Cost:** ~12,000 tokens (vs. ~500 for progressive `help://` exploration)

```bash
reveal --agent-help-full          # Complete guide (all workflows, examples, patterns)
```

---

## Decision Tree

```
Need help with reveal?
├─ What adapters exist? → reveal help://
├─ How does python:// work? → reveal help://python
├─ How does ast:// work? → reveal help://ast
├─ Need complete offline guide? → reveal --agent-help-full
├─ Traditional CLI help? → reveal --help
└─ Supported file types? → reveal --list-supported

Exploring code?
├─ Unknown directory → reveal src/
├─ Unknown file → reveal file.py
├─ Need specific function → reveal file.py function_name
├─ Multiple files → find/git | reveal --stdin
├─ Large file (>300 lines) → reveal file.py --head 10
└─ Full content needed → Read tool (after structure exploration)
```

---

## Common Patterns

### ✅ DO: Progressive exploration
```bash
reveal file.py                    # Structure first
reveal file.py --outline          # Hierarchy if needed
reveal file.py target_func        # Extract what you need
```

### ❌ DON'T: Read everything
```bash
cat huge_file.py                  # 10,000 tokens wasted
```

---

### ✅ DO: Use pipelines
```bash
git diff --name-only | reveal --stdin --outline
```

### ❌ DON'T: Manual iteration
```bash
reveal file1.py; reveal file2.py; ...  # Use --stdin instead
```

---

### ✅ DO: Use help:// for discovery
```bash
reveal help://                    # See all adapters
reveal help://python              # Learn specific adapter
```

### ❌ DON'T: Load full guide unnecessarily
```bash
reveal --agent-help-full          # 12K tokens when help:// costs 50
```

---

## Integration Patterns

### With TIA
```bash
tia search all "auth"             # Orient: Find files
reveal path/to/auth.py            # Navigate: Structure (Use reveal here!)
reveal path/to/auth.py auth_func  # Focus: Extract specific code
```

### With Claude Code
```bash
# Before using Read tool, explore structure
reveal unknown_file.py            # What's in here? (~100 tokens)
# Then use Read tool on specific functions only
```

---

## Key Resources

- **Progressive Help:** `reveal help://` (always current, ~50 tokens)
- **Complete Guide:** `reveal --agent-help-full` (~12K tokens, offline fallback)
- **Traditional Help:** `reveal --help` (CLI flags and options)
- **Supported Types:** `reveal --list-supported`
- **Version:** `reveal --version`
- **GitHub:** https://github.com/scottsen/reveal
- **PyPI:** https://pypi.org/project/reveal-cli/

---

## Quick Comparison

| Approach | Tokens | When to Use |
|----------|--------|-------------|
| `reveal help://` | ~50 | Discover available adapters |
| `reveal help://python` | ~200 | Learn specific adapter |
| `reveal --agent-help` | ~1,500 | Quick start + discovery pattern |
| `reveal --agent-help-full` | ~12,000 | Complete offline reference |

**Best Practice:** Start with `help://` for progressive discovery. Fall back to `--agent-help-full` only when needed.

---

## Remember

**Key Principle:** Explore structure before reading files (10-150x token reduction)

**Discovery Pattern:** `help://` → learn → use (most token-efficient)

**When stuck:** `reveal help://` shows you what's possible!
