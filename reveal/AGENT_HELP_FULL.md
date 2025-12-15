# Reveal: Agent Usage Guide (Complete)

**Version:** 0.23.0
**Last Updated:** 2025-12-14
**For:** AI Agents and LLM-based tools

**Token Cost:** ~12,000 tokens (this complete guide)
**Prefer:** `reveal --agent-help` (~1,500 tokens) + `reveal help://` (progressive discovery)

**Use this guide when:**
- Cannot make multiple reveal calls (API/token constraints)
- Working in restricted environment (no file system access)
- Need complete offline reference

**For interactive usage:** Try `reveal --agent-help` for token-efficient discovery pattern.

---

## Core Purpose

Semantic code exploration optimized for **token efficiency**.

**Key Principle:** Use reveal BEFORE reading files - see structure first, extract what you need.

**Token Impact:** Reading a 500-line file costs ~7,500 tokens. Reveal structure costs ~50 tokens (150x reduction).

---

## Decision Tree

**When exploring code:**

```
Need to understand code?
├─ Unknown directory → reveal src/
├─ Unknown file → reveal file.py (or --outline for hierarchy)
├─ Need specific function → reveal file.py function_name
├─ Multiple files → find/git | reveal --stdin
├─ Code quality checks → reveal file.py --check
├─ Large file (>300 lines) → reveal file.py --head N (explore progressively)
└─ Full content needed → cat/Read tool (after exploring structure)
```

**Key Rule:** Never read full file without checking structure first!

---

## Primary Use Cases

### Use Case 1: Unknown Codebase Exploration

**Pattern:**
```bash
1. reveal src/                              # What directories exist?
2. reveal src/*.py                          # Structure of main files
3. reveal src/main.py --outline             # Hierarchical view
4. reveal src/main.py load_config           # Extract specific function
```

**Use when:** Exploring unfamiliar codebase, onboarding to project

**Token impact:**
- Traditional (read all): ~5,000 tokens
- With reveal: ~200 tokens (25x reduction)

### Use Case 2: Function Location & Extraction

**Pattern:**
```bash
1. reveal file.py                           # See all functions/classes
2. reveal file.py target_function           # Extract specific code
```

**Use when:** Need to understand specific functionality

**Token impact:**
- Grep + read file: ~500 tokens
- Reveal + extract: ~70 tokens (7x reduction)

### Use Case 3: Code Quality Review

**Pattern:**
```bash
1. reveal file.py --check                   # Run all quality checks
2. reveal file.py --check --select B,S      # Focus on bugs & security
3. reveal file.py --outline --check         # Structure + issues
```

**Use when:** PR review, refactoring, security audit

**Token impact:** Adds ~20-50 tokens for issue annotations

### Use Case 4: Large File Progressive Disclosure

**Pattern:**
```bash
1. reveal large_file.py --head 10           # First 10 functions
2. reveal large_file.py --tail 5            # Last 5 functions (bugs cluster here!)
3. reveal large_file.py --range 15-20       # Specific range
4. reveal large_file.py specific_func       # Extract target
```

**Use when:** File is too large to view all at once

**Token impact:** View only what's needed (10x+ reduction)

---

## Workflow Sequences

### Workflow: PR Review
```bash
# Get changed files
git diff --name-only origin/main

# Quick structure check
git diff --name-only | reveal --stdin --outline

# Quality check changed files
git diff --name-only | grep "\.py$" | reveal --stdin --check

# Deep dive on specific file
reveal src/auth.py --check
reveal src/auth.py authenticate_user
```

### Workflow: Bug Investigation
```bash
# Find file structure
reveal src/problematic_file.py --outline

# Check last functions (bugs often at end)
reveal src/problematic_file.py --tail 5

# Extract suspicious function
reveal src/problematic_file.py buggy_function

# Check for quality issues
reveal src/problematic_file.py --check --select B,E
```

### Workflow: New Feature Understanding
```bash
# Explore feature directory
reveal src/features/new_thing/

# See main file structure
reveal src/features/new_thing/main.py

# Check complexity
reveal src/features/new_thing/main.py --check --select C

# Extract key functions
reveal src/features/new_thing/main.py init_feature
```

---

## Anti-patterns

### ❌ Reading Full Files First
```bash
# BAD - Wastes 500 tokens
cat large_file.py

# GOOD - Use 50 tokens to decide
reveal large_file.py
reveal large_file.py target_function  # Then extract (20 tokens)
```

### ❌ Using Grep for Function Definitions
```bash
# BAD - Brittle, misses context
grep -n "def.*config" file.py

# GOOD - Semantic, accurate
reveal file.py  # See all functions with line numbers
reveal file.py load_config  # Extract with full context
```

### ❌ Manual Complexity Estimation
```bash
# BAD - Subjective, error-prone
# Read code and guess complexity

# GOOD - Objective metrics
reveal file.py --check --select C  # Actual complexity scores
```

### ❌ Exploring Without Structure
```bash
# BAD - Random file reading
cat src/a.py
cat src/b.py
cat src/c.py

# GOOD - Systematic discovery
reveal src/              # What exists?
reveal src/*.py          # Structure overview
reveal src/main.py func  # Targeted extraction
```

---

## Pipeline Composition

### With Git
```bash
# Changed files in PR
git diff --name-only origin/main | reveal --stdin --outline

# Quality check modified code
git diff --name-only | grep "\.py$" | reveal --stdin --check

# Find complex changes
git diff --name-only | reveal --stdin --check --select C
```

### With Find
```bash
# Explore all Python files
find src/ -name "*.py" | reveal --stdin

# Check all Dockerfiles
find . -name "Dockerfile*" | reveal --stdin --check

# JSON output for further processing
find src/ -name "*.py" | reveal --stdin --format=json
```

### With jq (JSON Processing)
```bash
# Find complex functions (>3 depth, >50 lines)
reveal app.py --format=json | jq '.structure.functions[] | select(.depth > 3 and .line_count > 50)'

# Extract all function signatures
reveal app.py --format=json | jq -r '.structure.functions[] | "\(.name)(\(.line)) - \(.line_count) lines"'

# Find all imports
reveal app.py --format=json | jq '.structure.imports[]'
```

---

## Token Efficiency Analysis

### Scenario: 500-Line Python File

| Approach | Tokens | Time | Use When |
|----------|--------|------|----------|
| Read entire file | ~7,500 | Immediate | Never (unless truly needed) |
| reveal structure | ~50 | <100ms | First step (always) |
| reveal --outline | ~100 | <100ms | Need hierarchy |
| reveal + extract | ~70 | <200ms | Need specific code |
| reveal --check | ~150 | <500ms | Quality review |

**Best Practice:** Start with structure (50 tokens), then extract only what's needed.

### Scenario: Exploring 50-File Codebase

| Approach | Tokens | Result |
|----------|--------|--------|
| Read all files | ~375,000 | Context overflow, expensive |
| reveal all files | ~2,500 | Complete structure map |
| reveal + targeted reads | ~5,000 | Deep understanding where needed |

**Savings:** 75x token reduction with better understanding!

---

## Complementary Tools

**When to use reveal:**
- Need structure overview (functions, classes, imports)
- Finding specific code elements
- Token budget is tight
- First-time file exploration
- Code quality checks

**When to use alternatives:**

| Need | Use Instead | Why |
|------|-------------|-----|
| Full file content | `cat`, `Read` tool | Need complete source |
| Text search | `grep`, `Grep` tool | Finding specific strings |
| File listing | `ls`, `find`, `Glob` tool | Just need file names |
| Diffs | `git diff` | Seeing changes |
| File metadata | `ls -la`, `stat` | Size, dates, permissions |

**Best Pattern:** reveal first (structure), then use complementary tools for specific needs.

---

## Supported File Types

**18 built-in analyzers:**
- **Code:** Python (.py), JavaScript (.js), TypeScript (.ts, .tsx), Rust (.rs), Go (.go), GDScript (.gd)
- **Scripts:** Bash/Shell (.sh, .bash)
- **Config:** YAML (.yaml, .yml), JSON (.json), TOML (.toml), Nginx (nginx.conf)
- **Containers:** Dockerfile
- **Docs:** Markdown (.md)
- **Data:** Jupyter (.ipynb), JSONL (.jsonl)
- **Fallback:** 30+ languages via Tree-sitter (automatic)

**Check support:**
```bash
reveal --list-supported
```

---

## Quick Reference

### Most Common Commands
```bash
# Structure (always start here)
reveal file.py
reveal src/

# Extraction
reveal file.py function_name
reveal file.py ClassName

# Navigation (large files)
reveal file.py --head 10
reveal file.py --tail 5
reveal file.py --range 10-20

# Quality
reveal file.py --check
reveal file.py --check --select B,S

# Hierarchy
reveal file.py --outline

# Output formats
reveal file.py --format=json
reveal file.py --format=grep

# Pipelines
find . -name "*.py" | reveal --stdin
git diff --name-only | reveal --stdin --check
```

### Key Flags

| Flag | Purpose | Token Impact |
|------|---------|--------------|
| (none) | Show structure | Minimal (50-100) |
| `--outline` | Hierarchical view | Low (100-200) |
| `--head N` | First N elements | Minimal (10-50) |
| `--tail N` | Last N elements | Minimal (10-50) |
| `--range M-N` | Specific range | Minimal (20-100) |
| `--check` | Quality checks | Low (100-300) |
| `--format=json` | JSON output | Same (for scripting) |
| `function_name` | Extract element | Low (20-100) |

---

## Integration with Claude Code / TIA

**TIA Pattern (Orient → Navigate → Focus):**
```bash
# Orient: What exists?
tia search all "topic"
tia beth explore "topic"

# Navigate: What's relevant? (Use reveal here!)
reveal path/from/search/result.py

# Focus: Get details
reveal path/from/search/result.py specific_function
```

**Reveal fits perfectly in the Navigate phase** - after finding files, before reading them.

---

## Version-Specific Features

**v0.12.0+** - Semantic navigation
- `--head`, `--tail`, `--range` for progressive disclosure

**v0.13.0+** - Pattern detection
- `--check` for code quality (replaces deprecated `--sloppy`)
- Industry-aligned rule codes (B001, S701, C901, E501, U501)

**v0.11.0+** - URI adapters
- `reveal env://` for environment variables
- `reveal ast://` for AST-based code querying (v0.14.0+)

**v0.17.0** - Python runtime adapter
- `reveal python://` for Python environment inspection
- Bytecode debugging, package management, venv detection
- See "URI Adapters" section below for complete documentation

---

## URI Adapters (Self-Documenting System)

**Discovery:** `reveal help://` lists all available adapters (always current)

**As of v0.17.0:**

### help:// - Help System (Meta-Adapter)

Discover available adapters and their documentation.

```bash
reveal help://                    # List all adapters and guides
reveal help://python              # Learn about python:// adapter
reveal help://ast                 # Learn about ast:// adapter
reveal help://adapters            # Summary of all adapters
reveal help:// --format=json      # Machine-readable adapter registry
```

**Use when:** Need to discover what adapters exist or learn their syntax.

---

### python:// - Python Runtime Inspection (NEW in v0.17.0)

**Purpose:** Inspect Python runtime environment and debug common issues.

**Common use case:** "My code changes aren't working!" → stale .pyc bytecode

**Endpoints:**
```bash
# Overview
reveal python://                  # Python version, venv, package count

# Version details
reveal python://version           # Detailed version (CPython 3.10.12, GCC...)

# Environment
reveal python://env               # sys.path, flags, encoding
reveal python://venv              # Virtual environment status/path/type

# Packages
reveal python://packages          # List all installed packages
reveal python://packages/requests # Details for specific package

# Runtime inspection
reveal python://imports           # Currently loaded modules (sys.modules)

# Debugging (KILLER FEATURE)
reveal python://debug/bytecode    # ⚠️  Detect stale .pyc files
```

**Bytecode debugging example:**
```bash
$ reveal python://debug/bytecode
⚠️  stale_bytecode
   File: lib/mymodule.py
   Problem: .pyc is NEWER than source (stale bytecode)
   Fix: rm __pycache__/mymodule.cpython-310.pyc
```

**Separation of concerns:**
- `env://PYTHONPATH` → Raw environment variable
- `python://env` → Computed sys.path (PYTHONPATH + defaults + site-packages)
- `ast://file.py` → Static source analysis
- `python://imports` → Runtime loaded modules

**Full help:** `reveal help://python`

---

### ast:// - AST Query System (v0.14.0+)

**Purpose:** Query code as a database without reading files.

**Syntax:** `ast://<path>?<filter1>&<filter2>&...`

**Filters:**
- `type=<element>` - Function, class, method, etc.
- `complexity>N` - Cyclomatic complexity threshold
- `lines>N` - Line count threshold
- `depth>N` - Nesting depth threshold

**Examples:**
```bash
# Find complex functions
reveal 'ast://./src?complexity>10'

# Find long functions
reveal 'ast://app.py?lines>50'

# Find all functions
reveal 'ast://.?type=function' --format=json

# Query specific file
reveal 'ast://main.py?type=class'

# Combined filters
reveal 'ast://./src?type=function&complexity>5&lines>30'
```

**Use when:** Need to find code patterns across many files without reading them.

**Full help:** `reveal help://ast`

---

### env:// - Environment Variables

**Purpose:** Explore environment variables (cross-language, raw values).

**Examples:**
```bash
# List all environment variables
reveal env://

# Get specific variable
reveal env://PATH
reveal env://PYTHONPATH
reveal env://HOME

# JSON output
reveal env://PATH --format=json
```

**Use when:** Need to check environment configuration.

**Full help:** `reveal help://env`

---

### URI Adapter Workflow Example

```bash
# 1. Discover what adapters exist
reveal help://                    # See all: python, ast, env, help

# 2. Learn about Python adapter
reveal help://python              # Get documentation (~200 tokens)

# 3. Use it
reveal python://                  # Environment overview
reveal python://debug/bytecode    # Check for stale .pyc

# 4. Switch to AST queries
reveal 'ast://./src?complexity>10'  # Find complex code

# 5. Check environment
reveal env://VIRTUAL_ENV          # Verify venv path
```

**Key advantage:** URI adapters are self-documenting via `get_help()` methods.
New adapters automatically appear in `reveal help://` output.

---

## Performance Notes

- **Speed:** <100ms for most files, <500ms for complex files
- **Memory:** Minimal (~10-50MB for large files)
- **Scalability:** Works with files up to 100K+ lines
- **Batch:** Process 100s of files via stdin efficiently

---

## Common Mistakes & Solutions

### Mistake: Reading before exploring
```bash
❌ cat huge_file.py  # 10,000 tokens wasted
✅ reveal huge_file.py --head 10  # 50 tokens, see what's there
```

### Mistake: Using wrong tool for the job
```bash
❌ grep -A 20 "def function" file.py  # Brittle, manual counting
✅ reveal file.py function  # Semantic, accurate, with context
```

### Mistake: Not using pipelines
```bash
❌ reveal file1.py; reveal file2.py; ...  # Manual, tedious
✅ git diff --name-only | reveal --stdin  # Automatic, composable
```

### Mistake: Ignoring structure flags
```bash
❌ reveal 1000_line_file.py  # Overwhelming output
✅ reveal 1000_line_file.py --head 10  # Start small, expand as needed
```

---

## Support & Resources

- **Repo:** https://github.com/Semantic-Infrastructure-Lab/reveal
- **PyPI:** https://pypi.org/project/reveal-cli/
- **Install:** `pip install reveal-cli`
- **Help:** `reveal --help` (syntax reference)
- **Agent Help:** `reveal --agent-help` (this guide)
- **Issues:** https://github.com/Semantic-Infrastructure-Lab/reveal/issues

---

## Summary

**Core Workflow for Agents:**
1. 🔍 **Explore** - `reveal file.py` (structure overview)
2. 🎯 **Navigate** - `--head`, `--tail`, `--outline` (progressive)
3. 🔬 **Focus** - `reveal file.py func` (extract specific)
4. ✅ **Validate** - `--check` (quality checks)

**Remember:** Reveal is about **seeing structure without reading content**. Use it first, read later, save tokens everywhere.

---

## Extended Examples

### Example 1: Multi-File PR Review (Complete Flow)
```bash
# Step 1: Identify changed files
git diff --name-only origin/main
# Output: src/auth.py, src/utils.py, tests/test_auth.py

# Step 2: Quick overview of all changes
git diff --name-only origin/main | reveal --stdin --outline

# Step 3: Deep dive on critical file
reveal src/auth.py --check --select S,B
# See security and bug patterns

# Step 4: Extract specific new function
git diff origin/main src/auth.py | grep "^+def" | head -1
# Find: +def validate_token(token):
reveal src/auth.py validate_token

# Step 5: Check test coverage
reveal tests/test_auth.py --outline
# See if test_validate_token exists

# Step 6: Summary - JSON export for CI
git diff --name-only origin/main | reveal --stdin --check --format=json > pr_analysis.json
```

---

### Example 2: Debugging Production Issue (Complete Flow)
```bash
# Context: API endpoint returning 500 errors
# Step 1: Find the endpoint handler
reveal src/api/endpoints.py | grep "handle_request"
# Output: handle_request:127 (60 lines, complexity: 8)

# Step 2: Extract the function
reveal src/api/endpoints.py handle_request

# Step 3: Check for known issues
reveal src/api/endpoints.py --check --select B,E,C
# Output: C901: Cyclomatic complexity too high (8 > 5)

# Step 4: Look at related utility functions
reveal src/api/endpoints.py --tail 3
# Often helper functions at end have bugs

# Step 5: Check error handling patterns
reveal src/api/endpoints.py --format=json | jq '.structure.functions[] | select(.name | contains("error"))'

# Step 6: Compare with tests
reveal tests/api/test_endpoints.py | grep "test_handle_request"
```

---

### Example 3: Onboarding to New Codebase (Complete Flow)
```bash
# Day 1: Understanding project structure
reveal src/                           # Directory tree
find src/ -name "*.py" | wc -l       # 87 files

# Identify main entry points
reveal src/main.py --outline
reveal src/app.py --outline
reveal src/cli.py --outline

# Day 2: Understanding core modules
find src/core -name "*.py" | reveal --stdin --outline

# Focus on key abstractions
reveal src/core/base.py --outline    # Base classes
reveal src/core/engine.py            # Core logic

# Day 3: Understanding patterns
# Find all database-related code
find src/ -name "*db*.py" | reveal --stdin

# Extract a typical CRUD function
reveal src/models/user.py create_user

# Check code quality baseline
find src/ -name "*.py" | reveal --stdin --check --select C | grep "C901" | wc -l
# Output: 12 files with high complexity
```

---

## Complete Anti-Patterns Guide

### Anti-Pattern 1: Token Wastage
**❌ Bad:**
```bash
# Read entire 1000-line file
cat src/large_module.py
# Cost: 15,000 tokens
# Problem: Context overflow, expensive, slow to process
```

**✅ Good:**
```bash
# Explore structure first
reveal src/large_module.py --head 10
# Cost: 100 tokens
# Extract only what's needed
reveal src/large_module.py target_function
# Cost: 50 tokens
# Total: 150 tokens (100x reduction!)
```

---

### Anti-Pattern 2: Manual Code Extraction
**❌ Bad:**
```bash
# Use grep with manual line counting
grep -n "def process_data" file.py
# Output: 145:def process_data(items):
grep -A 50 "def process_data" file.py
# Problem: Might cut off mid-function, brittle
```

**✅ Good:**
```bash
# Semantic extraction
reveal file.py process_data
# Output: Complete function with correct boundaries
# Includes: decorators, docstrings, nested functions
```

---

### Anti-Pattern 3: Ignoring Code Quality Early
**❌ Bad:**
```bash
# Write code → commit → PR → CI fails → fix → repeat
git add src/new_feature.py
git commit -m "Add feature"
# Later: CI reports complexity issues, security problems
```

**✅ Good:**
```bash
# Check quality BEFORE committing
reveal src/new_feature.py --check
# Fix issues immediately
git add src/new_feature.py
git commit -m "Add feature"
```

---

### Anti-Pattern 4: One-Size-Fits-All Approach
**❌ Bad:**
```bash
# Always use same command for everything
reveal file1.py
reveal file2.py
reveal file3.py
# Problem: Not using right tool for context
```

**✅ Good:**
```bash
# Match tool to need
reveal small_file.py               # Full structure
reveal large_file.py --head 10     # Progressive
reveal config.yaml                 # Key-value overview
reveal Dockerfile                  # Stage-by-stage
```

---

## Complete Rules Reference

### Bug Detection (B)

**B001: Assert used in production code**
```python
# ❌ Bad: Asserts can be disabled with -O
def validate_user(user):
    assert user.is_active  # Disabled in production!

# ✅ Good: Explicit checks
def validate_user(user):
    if not user.is_active:
        raise ValueError("User not active")
```

**Detection:**
```bash
reveal file.py --check --select B
```

---

### Security Issues (S)

**S701: Hardcoded credentials**
```python
# ❌ Bad: Credentials in code
API_KEY = "sk_live_abc123xyz"
DATABASE_PASSWORD = "admin123"

# ✅ Good: Environment variables
import os
API_KEY = os.getenv("API_KEY")
DATABASE_PASSWORD = os.getenv("DATABASE_PASSWORD")
```

**Detection:**
```bash
reveal file.py --check --select S
```

---

### Complexity (C)

**C901: Cyclomatic complexity too high**
```python
# ❌ Bad: 10+ decision points
def process(data, flag1, flag2, flag3):
    if flag1:
        if flag2:
            if flag3:
                # ... nested logic
    elif flag2:
        # ... more branching
    # Complexity: 12

# ✅ Good: Break into smaller functions
def process(data, flags):
    if flags.should_validate():
        validate(data)
    if flags.should_transform():
        transform(data)
    # Complexity: 2
```

**Detection:**
```bash
reveal file.py --check --select C
```

---

### Error Handling (E)

**E501: Line too long (>120 chars)**
```python
# ❌ Bad: Long lines reduce readability
result = some_function_call(param1, param2, param3, param4, param5, param6, param7, param8, param9, param10, param11)

# ✅ Good: Break into multiple lines
result = some_function_call(
    param1, param2, param3, param4,
    param5, param6, param7, param8,
    param9, param10, param11
)
```

**Detection:**
```bash
reveal file.py --check --select E
```

---

### Refactoring Opportunities (R)

**R913: Too many arguments (>5)**
```python
# ❌ Bad: Hard to maintain
def create_user(name, email, age, address, phone, role, dept, manager):
    pass

# ✅ Good: Use dataclass or dict
from dataclasses import dataclass

@dataclass
class UserData:
    name: str
    email: str
    age: int
    # ...

def create_user(user_data: UserData):
    pass
```

**Detection:**
```bash
reveal file.py --check --select R
```

---

### URL Issues (U)

**U501: Unsafe URL pattern**
```python
# ❌ Bad: Unvalidated URL construction
url = f"https://api.example.com/{user_input}"

# ✅ Good: Use urllib
from urllib.parse import urljoin, quote
url = urljoin("https://api.example.com/", quote(user_input))
```

**Detection:**
```bash
reveal file.py --check --select U
```

---

## Advanced Pipeline Patterns

### Pattern 1: Finding All High-Complexity Functions
```bash
# Find all Python files with complexity issues
find src/ -name "*.py" | \
  reveal --stdin --check --select C --format=json | \
  jq -r '.[] | select(.issues | length > 0) | .path' | \
  sort | uniq

# Deep dive on worst offenders
reveal src/worst_file.py --check --select C
```

---

### Pattern 2: Security Audit Across Entire Project
```bash
# Generate security report
find . -name "*.py" | \
  reveal --stdin --check --select S --format=json > security_audit.json

# Count issues by type
jq '[.[] | .issues[] | .code] | group_by(.) | map({code: .[0], count: length})' security_audit.json

# Extract files needing immediate attention
jq -r '.[] | select(.issues | length > 0) | "\(.path): \(.issues | length) issues"' security_audit.json
```

---

### Pattern 3: Tracking Code Quality Over Time
```bash
# Baseline: Current complexity
git tag -a quality-baseline -m "Quality baseline"
find src/ -name "*.py" | reveal --stdin --check --select C --format=json > baseline.json

# After refactoring: Compare
find src/ -name "*.py" | reveal --stdin --check --select C --format=json > current.json

# Diff report
diff <(jq -S . baseline.json) <(jq -S . current.json)
```

---

### Pattern 4: Pre-commit Hook Integration
```bash
# .git/hooks/pre-commit
#!/bin/bash
# Get staged Python files
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep "\.py$")

if [ -n "$STAGED_FILES" ]; then
    echo "$STAGED_FILES" | reveal --stdin --check --select B,S,C

    # Fail commit if critical issues found
    ISSUES=$(echo "$STAGED_FILES" | reveal --stdin --check --select S --format=json | jq '[.[] | .issues | length] | add')

    if [ "$ISSUES" -gt 0 ]; then
        echo "❌ Security issues detected. Fix before committing."
        exit 1
    fi
fi
```

---

## Troubleshooting Guide

### Issue: "No structure found"

**Symptom:**
```bash
reveal file.py
# Output: (empty)
```

**Causes:**
1. File type not supported
2. File has only comments/docstrings
3. Syntax errors in file

**Solutions:**
```bash
# Check if file type supported
reveal --list-supported

# Try fallback parser
reveal file.py --format=json

# Check for syntax errors
python -m py_compile file.py
```

---

### Issue: "Element not found"

**Symptom:**
```bash
reveal file.py my_function
# Error: Element 'my_function' not found
```

**Causes:**
1. Typo in function name
2. Function is nested or private
3. Function is in different file

**Solutions:**
```bash
# List all available elements
reveal file.py

# Search with grep for the name
reveal file.py --format=grep | grep -i "my_function"

# Check if it's nested
reveal file.py --outline
```

---

### Issue: "Output too large"

**Symptom:**
```bash
reveal huge_file.py
# Output: (thousands of lines)
```

**Solutions:**
```bash
# Use progressive disclosure
reveal huge_file.py --head 20

# Use outline for hierarchy
reveal huge_file.py --outline

# Extract specific element
reveal huge_file.py --format=grep | grep "target"
reveal huge_file.py target_function
```

---

### Issue: "Performance slow"

**Symptom:**
```bash
reveal file.py
# Takes >5 seconds
```

**Causes:**
1. Very large file (>50K lines)
2. Complex Tree-sitter parsing
3. Many nested structures

**Solutions:**
```bash
# Use --meta for quick info
reveal file.py --meta

# Skip quality checks if not needed
# (--check adds overhead)

# Use JSON format for faster processing
reveal file.py --format=json
```

---

## Contributing: Adding New Analyzers

Want to add support for a new language? Here's the pattern:

### Step 1: Create Analyzer Module
```python
# reveal/analyzers/mylang.py
from reveal.base import AnalyzerBase

class MyLangAnalyzer(AnalyzerBase):
    def analyze(self, source: str) -> dict:
        # Parse source code
        # Return structure dict
        return {
            "functions": [...],
            "classes": [...],
            "imports": [...]
        }
```

### Step 2: Register in __init__.py
```python
# reveal/analyzers/__init__.py
from .mylang import MyLangAnalyzer

ANALYZERS = {
    # ...
    '.mylang': MyLangAnalyzer,
}
```

### Step 3: Add Tests
```python
# tests/test_mylang.py
def test_mylang_analyzer():
    result = reveal("sample.mylang")
    assert len(result['functions']) > 0
```

See `CONTRIBUTING.md` for full details.

---

## Version History

### v0.13.0 (2025-11)
- ✨ Pattern detection (`--check`)
- ✨ Industry-aligned rule codes (B, S, C, E, R, U)
- 🔧 Deprecated `--sloppy` (use `--check` instead)
- 📚 Agent help guide

### v0.12.0 (2025-10)
- ✨ Semantic navigation (`--head`, `--tail`, `--range`)
- ✨ JSONL support
- 🔧 Improved TypeScript/TSX parsing

### v0.11.0 (2025-09)
- ✨ URI adapters (`env://`)
- ✨ Nginx config support
- 🐛 Fixed Windows path handling

### v0.10.0 (2025-08)
- ✨ Outline mode (`--outline`)
- ✨ GDScript support (Godot)
- 🔧 Better error messages

---

## Performance Benchmarks

**Test System:** M1 Mac, 16GB RAM

| File Size | Lines | Elements | Parse Time | Memory |
|-----------|-------|----------|------------|--------|
| Small | 100 | 10 funcs | 20ms | 5MB |
| Medium | 500 | 50 funcs | 50ms | 10MB |
| Large | 2,000 | 200 funcs | 150ms | 25MB |
| Huge | 10,000 | 1,000 funcs | 800ms | 80MB |

**Pipeline Performance:**
```bash
# 100 Python files, ~50K total lines
find src/ -name "*.py" | reveal --stdin
# Time: 5.2 seconds
# Throughput: ~19 files/sec
```

---

## Summary (Extended)

**For AI Agents:**
- ⚡ **Token Efficiency:** 10-150x reduction vs reading files
- 🎯 **Precision:** Semantic extraction, not text search
- 🔍 **Progressive:** Start broad, drill down as needed
- ✅ **Quality:** Built-in pattern detection
- 🔗 **Composable:** Pipelines with git, find, jq
- 📊 **Structured:** JSON output for automation

**Core Principle:** **Never read code blindly. Explore structure first, extract what you need, validate quality, save tokens everywhere.**

**When in doubt:** `reveal file.py` → see what's there → `reveal file.py element` → get what you need.

---

**End of Comprehensive Agent Guide**

For quick reference, use: `reveal --agent-help`

**Token Efficiency Mantra:** Structure costs 50 tokens, reading costs 5,000 tokens. Choose wisely.
