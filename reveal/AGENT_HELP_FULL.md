# Reveal - AI Agent Reference (Complete)
**Version:** 0.31.0
**Purpose:** Comprehensive guide for AI code assistants
**Token Cost:** ~12,000 tokens
**Audience:** AI agents (Claude Code, Copilot, Cursor, etc.)

---

## About This Guide

**Use the quick reference instead:** `reveal --agent-help` (~2,200 tokens)

**Use this complete guide when:**
- Cannot make multiple reveal calls (API/token constraints)
- Working in restricted environment (no file system access)
- Need complete offline reference with all features
- Implementing reveal integration in your agent

**For interactive usage:** Use `reveal --agent-help` + `reveal help://topic` for progressive discovery.

---

## Core Rule: Structure Before Content

**Always use reveal instead of cat/grep/find for code files.**

❌ DON'T: `cat file.py` (wastes 7,500 tokens)
✅ DO: `reveal file.py` (uses 100 tokens, shows structure)

**Token savings:** 10-150x reduction

**Why this matters:**
- Reading a 500-line Python file: ~7,500 tokens
- Reveal structure: ~50 tokens (150x reduction)
- Extract specific function: ~20 tokens (375x reduction)

**The progressive disclosure pattern:**
1. **Broad** - `reveal src/` (directory structure)
2. **Medium** - `reveal src/main.py` (file structure)
3. **Focused** - `reveal src/main.py load_config` (specific function)
4. **Deep** - Read tool on extracted function only (last resort)

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

**Why this works:** Progressive disclosure. Don't read entire files - see structure first, then extract what you need.

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
  initialize_app [24 lines, depth:2] (line 67)
  ...
```

**Advanced variations:**
```bash
# Hierarchical view (classes with methods)
reveal src/main.py --outline

# Just function names (fast scan)
reveal src/main.py --format=json | jq '.structure.functions[].name'

# Find complex functions first
reveal src/main.py --format=json | jq '.structure.functions[] | select(.depth > 3)'
```

**Token impact:**
- Traditional approach (read all files): ~5,000 tokens
- With reveal: ~200 tokens (25x reduction)

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

**Why this works:** AST queries search across entire codebase without reading files. Pure metadata search is instant and uses minimal tokens.

**Available filters:**
- `name=pattern` - Wildcard matching (test_*, *helper*, *_internal, etc.)
- `complexity>N` - Cyclomatic complexity threshold
- `complexity<N` - Low complexity (simple functions)
- `lines>N` - Function line count
- `lines<N` - Short functions
- `type=X` - Element type (function, class, method, async_function)
- `depth>N` - Nesting depth (complexity indicator)
- `depth<N` - Shallow nesting
- `decorator=X` - Has specific decorator (@property, @staticmethod, etc.)

**Filter combinations:**
```bash
# Complex AND long (refactor targets)
reveal 'ast://./src?complexity>10&lines>50'

# Short AND simple (good examples)
reveal 'ast://./src?complexity<3&lines<20'

# All async functions
reveal 'ast://./src?type=async_function'

# All properties
reveal 'ast://./src?decorator=property'

# Test functions (by name pattern)
reveal 'ast://./tests?name=test_*'
```

**Pattern matching rules:**
- `*` matches any characters: `*auth*` matches "authenticate", "authorization"
- `test_*` matches functions starting with "test_"
- `*_helper` matches functions ending with "_helper"
- Case-sensitive by default

**Example output:**
```
Found 12 functions matching 'complexity>10':

src/auth/handler.py:
  authenticate_user (line 45, complexity: 12, lines: 67)
  validate_token (line 112, complexity: 14, lines: 89)

src/processor/main.py:
  process_request (line 234, complexity: 15, lines: 103)
```

---

### Task: "Review code quality"

**Pattern:**
```bash
# Check all quality rules
reveal file.py --check

# Check specific categories (faster)
reveal file.py --check --select B,S    # Bugs & security only
reveal file.py --check --select C,E    # Complexity & errors only

# Specific file types
reveal Dockerfile --check              # Docker best practices (S701)
reveal nginx.conf --check              # Nginx validation (N001-N003)
```

**Available rule categories:**
- **B** (bugs) - Common code bugs and anti-patterns (B001-B005)
- **S** (security) - Security vulnerabilities (S001, S701)
- **C** (complexity) - Code complexity metrics (C001-C003)
- **E** (errors) - Syntax errors and issues (E001)
- **D** (duplicates) - Duplicate code detection (D001, D002)
- **N** (nginx) - Nginx configuration issues (N001-N003)
- **V** (validation) - General validation rules (V001-V006)
- **R** (refactoring) - Refactoring opportunities (R001-R003)
- **U** (urls) - URL and link issues (U001-U003)

**List all rules:** `reveal --rules`
**Explain specific rule:** `reveal --explain B001`

**Example output:**
```
File: src/auth.py (234 lines, Python)

Quality Issues (3):

  B003: Mutable default argument (line 45)
    def process_items(items=[]):  # ❌ Mutable default
    Suggestion: Use None and initialize inside function

  C002: High cyclomatic complexity (line 67)
    Function: authenticate_user (complexity: 12)
    Suggestion: Consider breaking into smaller functions

  S001: Potential SQL injection (line 89)
    query = f"SELECT * FROM users WHERE id={user_id}"
    Suggestion: Use parameterized queries
```

**Pipeline usage:**
```bash
# Check all Python files in directory
find src/ -name "*.py" | reveal --stdin --check

# Check only changed files in PR
git diff --name-only | grep "\.py$" | reveal --stdin --check

# Focus on security issues only
git diff --name-only | reveal --stdin --check --select S
```

---

### Task: "Extract specific code element"

**Pattern:**
```bash
# Extract function
reveal app.py process_request

# Extract class
reveal app.py DatabaseHandler

# Extract method
reveal app.py DatabaseHandler.connect

# Extract specific lines
reveal app.py --range 42-80

# Get first/last functions (bugs cluster at end!)
reveal app.py --head 5
reveal app.py --tail 5
```

**Why tail is useful:** Technical debt and bugs often cluster at the end of files. Functions added later tend to be rushed or less reviewed. Always check `--tail 5` when investigating issues.

**Advanced extraction:**
```bash
# Extract multiple functions (with --format=json)
reveal app.py --format=json | jq '.structure.functions[] | select(.name | test("^handle_"))'

# Extract function with its decorators
reveal app.py decorated_function  # Automatically includes @decorators

# Extract with context (surrounding functions)
reveal app.py target_function --range $((line-10))-$((line+10))
```

**Hierarchical extraction (--outline):**
```bash
reveal models.py --outline

# Output:
# class User:
#   __init__ [5 lines] (line 10)
#   authenticate [12 lines] (line 16)
#   update_profile [8 lines] (line 29)
# class Admin(User):
#   delete_user [6 lines] (line 40)
```

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

# Check sys.path
reveal python://sys/path

# Check environment variables
reveal python://env
```

**Common scenario:** "My code changes aren't working!"
**Solution:** `reveal python://debug/bytecode` detects stale .pyc files

**python:// adapter provides:**
- Python version and interpreter path
- Virtual environment detection (venv, virtualenv, conda)
- Package inventory (pip list equivalent)
- sys.path inspection
- Stale bytecode detection
- Environment variables (PYTHONPATH, VIRTUAL_ENV, etc.)
- Import system debugging

**Example output:**
```
Python Environment

Version: 3.11.6
Interpreter: /home/user/.venv/bin/python3
Virtual Environment: /home/user/.venv (active)

Packages (45 installed):
  fastapi==0.104.1
  uvicorn==0.24.0
  pydantic==2.5.0
  ...

Stale Bytecode: 3 files
  src/__pycache__/main.cpython-311.pyc (older than src/main.py)
  Fix: python -m compileall src/ or delete __pycache__
```

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
reveal json://data.json/users[0:5]     # First 5 items
reveal json://data.json/users[-3:]     # Last 3 items

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

**JSONL is different:** Each line is a separate JSON object (common for logs, LLM conversations, datasets). Use `--head`, `--tail`, `--range` to navigate records without loading entire file.

**json:// query parameters:**
- `?schema` - Show JSON structure (types, keys)
- `?flatten` - Gron-style output (greppable)
- `?pretty` - Pretty-print JSON
- `?keys` - List all keys at current path

**Example outputs:**
```bash
# reveal json://config.json/database
{
  "host": "localhost",
  "port": 5432,
  "name": "mydb",
  "credentials": {
    "user": "admin",
    "password": "***"
  }
}

# reveal json://config.json?flatten
json.database.host = "localhost"
json.database.port = 5432
json.database.name = "mydb"
json.database.credentials.user = "admin"
```

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

**--stdin mode:** Feed file paths via stdin. Works with `git diff`, `find`, `ls`, any line-delimited output.

**Advanced PR review workflows:**
```bash
# Compare with main branch
git diff main --name-only | reveal --stdin --outline

# Check only modified (not new) files
git diff --name-only --diff-filter=M | reveal --stdin --check

# Get complexity of changed functions
git diff main --name-only | grep "\.py$" | reveal --stdin --format=json | \
  jq '.structure.functions[] | {name, complexity: .depth}'

# Check security on new files only
git diff --name-only --diff-filter=A | reveal --stdin --check --select S
```

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

**--outline flag:** Shows hierarchical structure (classes with their methods, nested functions, decorators).

**Relationship analysis patterns:**
```bash
# Find all classes that inherit from Base
grep -r "class.*Base" src/ | reveal --stdin --outline

# Find files with many imports (coupling indicator)
find src/ -name "*.py" | reveal --stdin --format=json | \
  jq 'select(.structure.imports | length > 20) | .file_path'

# Find circular import candidates
find src/ -name "*.py" | reveal --stdin --format=json | \
  jq '.structure.imports[] | select(. | contains("src/"))'
```

---

### Task: "Find duplicate code"

**Pattern:**
```bash
# Run duplicate detection (within single file only)
reveal file.py --check --select D001

# D001: Exact duplicates (hash-based, reliable) ✅
# D002: Similar code (experimental, high false positives) ⚠️
```

**IMPORTANT:** Cross-file duplicate detection is not yet implemented. D001 and D002 only find duplicates within a single file.

**Example output:**
```
File: src/handler.py (456 lines, Python)

Quality Issues (2):

  D001: Exact duplicate code (line 45)
    Identical to 'process_request' (line 123)
    Suggestion: Refactor to share implementation

  D001: Exact duplicate code (line 234)
    Identical to 'validate_input' (line 456)
    Suggestion: Extract to shared function
```

**Finding duplicates across files (workaround):**
```bash
# 1. Find functions with similar names across files
reveal 'ast://./src?name=*parse*'
reveal 'ast://./src?name=*validate*'

# 2. Find complex functions (duplication candidates)
reveal 'ast://./src?complexity>10&lines>50'

# 3. Check each file individually
find src/ -name "*.py" | while read f; do
    reveal "$f" --check --select D001
done
```

**See also:** `reveal/DUPLICATE_DETECTION_GUIDE.md` for comprehensive workflows and limitations.

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
# - S701: Security best practices (USER directive, etc.)

# YAML/TOML
reveal config.yaml                     # Structure view
reveal pyproject.toml                  # Structure view
```

**Nginx-specific checks:**
```
N001: Duplicate upstream servers
  upstream backend {
    server localhost:8000;
    server localhost:8000;  # ❌ Duplicate
  }

N002: SSL certificate file not found
  ssl_certificate /etc/nginx/ssl/cert.pem;  # ❌ File doesn't exist

N003: Missing proxy headers
  location / {
    proxy_pass http://backend;
    # ❌ Missing: proxy_set_header Host $host;
  }
```

**Docker security checks (S701):**
```
S701: Running as root
  FROM python:3.11
  COPY . /app
  # ❌ No USER directive - running as root
  CMD ["python", "app.py"]

  # ✅ Should include:
  USER appuser
```

---

### Task: "Work with Markdown documentation"

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
```

**Link types:**
- `internal` - Relative links (./file.md, ../other.md, #heading)
- `external` - HTTP/HTTPS links
- `email` - mailto: links
- `all` - All link types (default)

**Markdown analysis workflows:**
```bash
# Find all broken internal links in docs
find docs/ -name "*.md" | while read f; do
  reveal "$f" --links --link-type internal | grep -v "✓"
done

# Extract all code examples for testing
find docs/ -name "*.md" | reveal --stdin --code --language bash > examples.sh

# Get frontmatter from all docs
find docs/ -name "*.md" | while read f; do
  echo "=== $f ==="
  reveal "$f" --frontmatter
done
```

**Link validation:**
```bash
# Check internal links exist
reveal doc.md --links --link-type internal
# Output shows ✓ (exists) or ✗ (broken)

# Example output:
# ./setup.md ✓
# ./api/reference.md ✗ (file not found)
# #installation ✓
# #nonexistent-heading ✗ (heading not found)
```

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

# Typed JSON (with containment relationships)
reveal file.py --format=typed

# Copy to clipboard
reveal file.py --copy
reveal file.py process_request --copy
```

### JSON Format Details

**Standard JSON output:**
```json
{
  "file_path": "src/main.py",
  "file_size": 12456,
  "line_count": 342,
  "language": "Python",
  "structure": {
    "imports": ["os", "sys", "pathlib.Path"],
    "functions": [
      {
        "name": "load_config",
        "line_number": 45,
        "line_count": 12,
        "depth": 1,
        "type": "function"
      }
    ],
    "classes": []
  }
}
```

**Typed JSON output** (--format=typed):
```json
{
  "file_path": "src/models.py",
  "typed_structure": {
    "elements": [
      {
        "name": "User",
        "type": "class",
        "line_number": 10,
        "children": [
          {
            "name": "__init__",
            "type": "method",
            "line_number": 11,
            "parent": "User"
          }
        ]
      }
    ]
  }
}
```

### JSON + jq Filtering Patterns

```bash
# Find complex functions
reveal app.py --format=json | jq '.structure.functions[] | select(.depth > 3)'

# Find functions > 50 lines
reveal app.py --format=json | jq '.structure.functions[] | select(.line_count > 50)'

# List all classes
reveal app.py --format=json | jq '.structure.classes[].name'

# Count functions per file
find src/ -name "*.py" | reveal --stdin --format=json | \
  jq '{file: .file_path, count: .structure.functions | length}'

# Find files with no docstrings (empty imports)
find src/ -name "*.py" | reveal --stdin --format=json | \
  jq 'select(.structure.imports | length == 0)'
```

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

### Pattern 1: Finding All High-Complexity Functions

**Goal:** Identify refactoring targets across entire codebase

```bash
# Method 1: AST query (fastest)
reveal 'ast://./src?complexity>10'

# Method 2: Pipeline with jq (more control)
find src/ -name "*.py" | reveal --stdin --format=json | \
  jq -r '.structure.functions[] |
         select(.depth > 10) |
         "\(.file_path):\(.line_number) - \(.name) (complexity: \(.depth))"' | \
  sort -t: -k3 -nr

# Output:
# src/processor.py:234 - process_request (complexity: 15)
# src/auth.py:67 - authenticate (complexity: 12)
```

### Pattern 2: Security Audit Across Entire Project

**Goal:** Find all security issues in one scan

```bash
# Quick scan (B, S rules only)
find . -name "*.py" | reveal --stdin --check --select B,S > security_audit.txt

# With context (show function names)
find . -name "*.py" | while read f; do
  issues=$(reveal "$f" --check --select S 2>/dev/null | grep -c "^  S")
  if [ "$issues" -gt 0 ]; then
    echo "=== $f ($issues issues) ==="
    reveal "$f" --check --select S
  fi
done

# JSON output for automation
find . -name "*.py" | reveal --stdin --check --select S --format=json | \
  jq 'select(.quality_issues | length > 0)'
```

### Pattern 3: Tracking Code Quality Over Time

**Goal:** Monitor quality metrics across commits

```bash
# Create quality baseline
find src/ -name "*.py" | reveal --stdin --check > baseline.txt

# After changes, compare
find src/ -name "*.py" | reveal --stdin --check > current.txt
diff baseline.txt current.txt

# Track complexity over time
git log --oneline | head -10 | while read commit _; do
  git checkout $commit 2>/dev/null
  complexity=$(find src/ -name "*.py" | reveal --stdin --format=json | \
    jq '[.structure.functions[].depth] | add / length')
  echo "$commit: avg complexity $complexity"
done
```

### Pattern 4: Pre-commit Hook Integration

**Goal:** Block commits with quality issues

```bash
# .git/hooks/pre-commit
#!/bin/bash

# Get staged Python files
staged_files=$(git diff --cached --name-only --diff-filter=ACM | grep "\.py$")

if [ -z "$staged_files" ]; then
  exit 0
fi

# Check quality
echo "$staged_files" | reveal --stdin --check --select B,S > /tmp/quality_check.txt

if grep -q "Quality Issues" /tmp/quality_check.txt; then
  echo "❌ Quality issues found:"
  cat /tmp/quality_check.txt
  echo ""
  echo "Fix issues or use 'git commit --no-verify' to skip"
  exit 1
fi

echo "✅ Quality checks passed"
exit 0
```

---

## When reveal Won't Help

**Don't use reveal for:**
- Binary files (use file-specific tools like `objdump`, `hexdump`)
- Very large files >10MB (performance degrades, use `head`/`tail`)
- Real-time log tailing (use `tail -f`)
- Text search across many files (use `ripgrep`/`grep` - much faster)
- Compiled binaries (use language-specific tools)
- Media files (images, videos, audio)

**Use reveal for:**
- Understanding code structure
- Extracting specific functions/classes
- Quality checks and code analysis
- Progressive file exploration
- Python environment debugging
- Config file validation
- JSON/JSONL navigation
- Markdown documentation analysis

---

## File Type Support

**reveal auto-detects and provides structure for:**

### Programming Languages (16)
Python, JavaScript, TypeScript, Rust, Go, Java, C, C++, C#, Scala, GDScript, Bash, SQL, PHP, Ruby, Lua

**Structure provided:** Functions, classes, methods, imports, decorators, complexity

### Configuration Formats
Nginx, Dockerfile, TOML, YAML, JSON

**Validation:** Format-specific rules (N-series for Nginx, S701 for Docker)

### Document Formats
Markdown, Jupyter notebooks (.ipynb)

**Features:** Link extraction, code block extraction, frontmatter parsing

### Office Documents
Excel (.xlsx), Word (.docx), PowerPoint (.pptx)

**Features:** Structure view, metadata, content extraction

**Check supported types:** `reveal --list-supported`

**File type detection:**
```bash
# See how reveal interprets a file
reveal file.unknown --meta

# Force specific analyzer (if detection fails)
reveal file.txt --language python
```

---

## Real-World Examples

### Example 1: "User reports auth bug"

**Scenario:** User can't log in, investigate authentication system

```bash
# 1. Find auth-related code
reveal 'ast://./src?name=*auth*'

# Output:
# Found 8 functions:
# src/auth/handler.py: authenticate_user (line 45)
# src/auth/handler.py: validate_token (line 112)
# src/auth/middleware.py: check_auth (line 23)

# 2. Check structure of main auth file
reveal src/auth/handler.py

# 3. Extract suspect function
reveal src/auth/handler.py authenticate_user

# 4. Quality check (look for bugs)
reveal src/auth/handler.py --check --select B,S

# Output:
# B003: Mutable default argument (line 52)
#   def authenticate(user, options={}):  # ❌
```

**Result:** Found mutable default argument causing shared state bug.

### Example 2: "Need to refactor complex code"

**Scenario:** Code review identified complex functions, prioritize refactoring

```bash
# 1. Find complex functions across codebase
reveal 'ast://./src?complexity>10&lines>50'

# Output:
# Found 5 functions:
# src/processor.py: process_request (complexity: 15, 87 lines)
# src/validator.py: validate_data (complexity: 12, 76 lines)

# 2. See structure of worst offender
reveal src/processor.py --outline

# 3. Extract function to understand it
reveal src/processor.py process_request

# 4. Check for other issues
reveal src/processor.py --check

# Output:
# C002: High complexity (complexity: 15)
# B001: Except block catches all exceptions
# E001: Unreachable code detected
```

**Result:** Complex function has multiple issues, good refactoring candidate.

### Example 3: "Setup not working in new environment"

**Scenario:** Dependencies installed but imports fail

```bash
# 1. Check Python environment
reveal python://

# Output shows wrong Python version (3.8 vs 3.11 expected)

# 2. Check for stale bytecode
reveal python://debug/bytecode

# Output:
# Stale Bytecode: 12 files
# src/__pycache__/main.cpython-38.pyc (older than src/main.py)

# 3. Check virtual environment
reveal python://venv

# Output:
# Virtual Environment: NONE
# ❌ Not in a virtual environment

# 4. Verify package installed
reveal python://packages/fastapi

# Output:
# Package not found: fastapi
```

**Result:** Not in virtual environment, packages not installed, stale bytecode.

### Example 4: "Review PR changes"

**Scenario:** Reviewing 15-file pull request

```bash
# 1. See what changed
git diff --name-only main

# Output:
# src/auth.py
# src/models.py
# tests/test_auth.py
# ... (12 more files)

# 2. Get structure overview
git diff --name-only main | reveal --stdin --outline

# 3. Quality check Python files
git diff --name-only main | grep "\.py$" | reveal --stdin --check

# Output shows 3 files with issues

# 4. Deep dive on specific file
reveal src/auth.py --check

# Output:
# B003: Mutable default argument
# S001: Potential SQL injection
# C002: High complexity

# 5. Extract problematic function
reveal src/auth.py authenticate_user
```

**Result:** Found security issue and complexity problem before merge.

### Example 5: "Documentation link cleanup"

**Scenario:** Refactored docs, need to find broken links

```bash
# 1. Find all broken internal links
find docs/ -name "*.md" | while read f; do
  broken=$(reveal "$f" --links --link-type internal | grep "✗" | wc -l)
  if [ "$broken" -gt 0 ]; then
    echo "=== $f ($broken broken) ==="
    reveal "$f" --links --link-type internal | grep "✗"
  fi
done

# Output:
# === docs/setup.md (2 broken) ===
# ./old_api.md ✗ (file not found)
# #configuration ✗ (heading not found)

# 2. Fix links and verify
reveal docs/setup.md --links --link-type internal

# Output: All ✓
```

**Result:** Found and fixed 12 broken links across documentation.

---

## Troubleshooting

### Issue: "Nothing happens when I use --hotspots"

**Problem:** `--hotspots` flag only works with the `stats://` adapter.

**Wrong:**
```bash
reveal . --hotspots              # Error: --hotspots only works with stats://
reveal file.py --hotspots        # Error: --hotspots only works with stats://
```

**Correct:**
```bash
# URI parameter (preferred):
reveal stats://.?hotspots=true

# Flag (legacy - shows migration hint):
reveal stats://. --hotspots
```

**Why:** Adapter-specific features should use URI parameters, not global flags. This keeps the CLI consistent and prevents confusion about which flags work where.

---

### Issue: "No structure found"

**Symptoms:**
```
File: script.py (145 lines)
No structure found
```

**Causes & Solutions:**

1. **Syntax errors in file**
   ```bash
   # Check for syntax errors
   python -m py_compile script.py

   # Reveal will show errors
   reveal script.py --check --select E
   ```

2. **Unsupported language/extension**
   ```bash
   # Check file type detection
   reveal file.unknown --meta

   # Force language if detection fails
   reveal file.txt --language python
   ```

3. **TreeSitter parser missing**
   ```bash
   # Try without TreeSitter (uses fallback)
   reveal script.py --no-fallback

   # Check which parsers are available
   reveal reveal://adapters
   ```

4. **File is binary/compiled**
   ```bash
   # Check file type
   file script.py

   # Don't use reveal on binary files
   ```

---

### Issue: "Element not found"

**Symptoms:**
```bash
reveal app.py missing_function
# Error: Element 'missing_function' not found
```

**Causes & Solutions:**

1. **Typo in element name**
   ```bash
   # See all available elements
   reveal app.py

   # Use grep-friendly format
   reveal app.py --format=grep | grep -i "function"
   ```

2. **Element is nested (method in class)**
   ```bash
   # Wrong: reveal app.py method_name
   # Right: reveal app.py ClassName.method_name

   # See class hierarchy
   reveal app.py --outline
   ```

3. **Element in different file**
   ```bash
   # Search across codebase
   reveal 'ast://./src?name=*missing_function*'
   ```

4. **Element is private/internal**
   ```bash
   # Private functions (starting with _) are included
   reveal app.py _private_function  # Works

   # Check if it exists
   reveal app.py --format=json | jq '.structure.functions[].name'
   ```

---

### Issue: "Output too large"

**Symptoms:**
```bash
reveal huge_file.py
# Output: 15,000 lines (too much)
```

**Solutions:**

1. **Use progressive disclosure**
   ```bash
   # See structure only (not content)
   reveal huge_file.py --outline

   # First 10 functions
   reveal huge_file.py --head 10

   # Last 5 functions
   reveal huge_file.py --tail 5

   # Specific range
   reveal huge_file.py --range 100-150
   ```

2. **Extract specific element**
   ```bash
   # Don't dump entire file
   reveal huge_file.py target_function
   ```

3. **Use JSON + jq filtering**
   ```bash
   # Find what you need
   reveal huge_file.py --format=json | jq '.structure.functions[] | select(.name | contains("target"))'
   ```

4. **Limit output**
   ```bash
   # Show only complex functions
   reveal huge_file.py --format=json | jq '.structure.functions[] | select(.depth > 5)'
   ```

---

### Issue: "Performance slow"

**Symptoms:**
```bash
reveal deep_dir/
# Takes 30+ seconds
```

**Solutions:**

1. **Use --fast mode**
   ```bash
   # Skip line counting (major speedup)
   reveal large_dir/ --fast
   ```

2. **Limit tree depth**
   ```bash
   # Only show 2 levels deep
   reveal deep_dir/ --depth 2
   ```

3. **Limit entries shown**
   ```bash
   # Show max 100 entries
   reveal huge_dir/ --max-entries 100
   ```

4. **Use AST queries instead**
   ```bash
   # Don't traverse directory
   # Instead, query directly
   reveal 'ast://./deep_dir?name=target*'
   ```

5. **Exclude large subdirectories**
   ```bash
   # Skip node_modules, .git, etc.
   reveal project/ --exclude node_modules,venv,.git
   ```

---

## Complete Rules Reference

### Bug Detection (B)

**B001: Except block catches all exceptions**
```python
# ❌ Bad
try:
    risky_operation()
except:  # Catches everything, even KeyboardInterrupt
    pass

# ✅ Good
try:
    risky_operation()
except ValueError:
    pass
```

**B002: __init__.py missing in package**
- Detects directories with .py files but no __init__.py
- Important for proper Python package structure

**B003: Mutable default argument**
```python
# ❌ Bad - Shared across calls!
def append_to(item, list=[]):
    list.append(item)
    return list

# ✅ Good
def append_to(item, list=None):
    if list is None:
        list = []
    list.append(item)
    return list
```

**B004: @property decorator on class method**
```python
# ❌ Bad
class MyClass:
    @classmethod
    @property  # Properties can't be class methods
    def value(cls):
        return cls._value

# ✅ Good
class MyClass:
    @classmethod
    def get_value(cls):
        return cls._value
```

**B005: @staticmethod on __init__ or __new__**
```python
# ❌ Bad - Makes no sense
class MyClass:
    @staticmethod
    def __init__(self):
        pass
```

---

### Security Issues (S)

**S001: Potential SQL injection**
```python
# ❌ Bad
query = f"SELECT * FROM users WHERE id={user_id}"
db.execute(query)

# ✅ Good
query = "SELECT * FROM users WHERE id=?"
db.execute(query, (user_id,))
```

**S701: Docker security best practices**
```dockerfile
# ❌ Bad - Running as root
FROM python:3.11
COPY . /app
CMD ["python", "app.py"]

# ✅ Good
FROM python:3.11
RUN useradd -m appuser
COPY --chown=appuser:appuser . /app
USER appuser
CMD ["python", "app.py"]
```

---

### Complexity (C)

**C001: Too many arguments**
```python
# ❌ Bad - 8 arguments
def process(a, b, c, d, e, f, g, h):
    pass

# ✅ Good - Use dataclass or dict
from dataclasses import dataclass

@dataclass
class ProcessConfig:
    a: str
    b: int
    # ...

def process(config: ProcessConfig):
    pass
```

**C002: High cyclomatic complexity**
- Complexity > 10 suggests function is too complex
- Consider breaking into smaller functions

**C003: Deep nesting**
```python
# ❌ Bad - Depth 5
def process():
    if x:
        if y:
            if z:
                if a:
                    if b:
                        return result

# ✅ Good - Early returns
def process():
    if not x:
        return
    if not y:
        return
    # ...
```

---

### Error Handling (E)

**E001: Syntax errors**
- Python syntax errors detected by parser
- File won't execute until fixed

---

### Duplicates (D)

**D001: Exact duplicate code (hash-based)**
- Identical code blocks (hash match)
- High confidence - should be deduplicated

**D002: Similar code (structural similarity)**
- Similar but not identical code
- Experimental - high false positive rate currently
- Being improved in future versions

---

### Nginx Configuration (N)

**N001: Duplicate upstream servers**
```nginx
# ❌ Bad
upstream backend {
    server localhost:8000;
    server localhost:8000;  # Duplicate
}
```

**N002: Missing SSL certificate**
```nginx
# ❌ Bad
ssl_certificate /path/to/missing.pem;  # File doesn't exist
```

**N003: Missing proxy headers**
```nginx
# ❌ Bad
location / {
    proxy_pass http://backend;
    # Missing important headers
}

# ✅ Good
location / {
    proxy_pass http://backend;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

---

### Validation (V)

**V001-V006:** Internal validation rules for reveal's own codebase
- Used by `reveal reveal://` self-inspection
- Ensure adapter completeness, documentation, testing

---

### Refactoring Opportunities (R)

**R001: Long function (>50 lines)**
- Consider breaking into smaller functions
- Each function should do one thing

**R002: Many local variables (>10)**
- Suggests function is doing too much
- Consider extracting helper functions

**R003: God object (>20 methods)**
- Class has too many responsibilities
- Consider breaking into multiple classes

---

### URL Issues (U)

**U001: Broken URL (HTTP 404)**
**U002: Invalid URL format**
**U003: Unreachable URL (connection timeout)**

---

## Performance Benchmarks

**Directory traversal:**
- 100 files: ~50ms
- 1,000 files: ~200ms
- 10,000 files: ~2s

**File structure parsing:**
- Small file (<100 lines): ~5ms
- Medium file (500 lines): ~15ms
- Large file (2,000 lines): ~50ms

**AST queries:**
- Query across 1,000 files: ~100ms
- Complex filter: ~150ms

**Quality checks:**
- Single file: +10-20ms
- Batch (10 files): +100ms

**Token costs (approximate):**
- Directory structure (100 files): ~500 tokens
- File structure (500 lines): ~50 tokens
- Function extraction: ~20 tokens
- JSON output: +30% tokens vs default

---

## Integration with Other Tools

### With Claude Code workflow
```bash
# 1. Structure first (what you should do!)
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

# Extract matching functions
rg -l "authenticate" src/ | while read f; do
  reveal "$f" --format=json | jq '.structure.functions[] | select(.name | contains("authenticate"))'
done
```

### With git
```bash
# See structure of changed files
git diff --name-only | reveal --stdin --outline

# Quality check changes
git diff --name-only | grep "\.py$" | reveal --stdin --check

# Track complexity over time
git log --oneline | head -10 | while read commit _; do
  git checkout $commit
  reveal 'ast://./src?complexity>10' | wc -l
done
```

### With jq (JSON processing)
```bash
# Complex queries
reveal app.py --format=json | jq '.structure.functions[] | select(.depth > 3 and .line_count > 50)'

# Aggregation
find src/ -name "*.py" | reveal --stdin --format=json | \
  jq -s 'map(.structure.functions | length) | add'

# Custom reports
reveal app.py --format=json | jq -r '.structure.functions[] | "\(.name) (\(.line_count) lines)"'
```

---

## Key Principles for AI Agents

1. **Structure before content** - Always `reveal` before `Read`
   - See what exists before reading
   - Extract only what you need
   - 10-150x token savings

2. **Progressive disclosure** - Start broad, drill down as needed
   - Directory → File → Function
   - Don't jump to deep reads
   - Use --head/--tail for large files

3. **Use AST queries** - Don't grep when you can query
   - `reveal 'ast://./src?name=*auth*'` vs `grep -r "def.*auth"`
   - Semantic search vs text search
   - No false positives

4. **Quality checks built-in** - Use `--check` proactively
   - Find bugs before they reach production
   - Security scanning in PR reviews
   - Complexity analysis for refactoring

5. **Pipeline friendly** - Combine with git, find, grep via `--stdin`
   - Unix philosophy
   - Composable workflows
   - Automation-ready

6. **Format for context** - JSON for machines, default for humans
   - Use --format=json for scripting
   - Use jq for complex filtering
   - Use --copy for quick extraction

7. **Know the limits** - When reveal won't help
   - Binary files → use specialized tools
   - Text search → use ripgrep
   - Large files → use progressive disclosure

---

## Quick Reference Card

| Task | Command |
|------|---------|
| See directory structure | `reveal src/` |
| See file structure | `reveal file.py` |
| Hierarchical view | `reveal file.py --outline` |
| Extract function | `reveal file.py func_name` |
| Extract class method | `reveal file.py Class.method` |
| Quality check | `reveal file.py --check` |
| Security check only | `reveal file.py --check --select S` |
| Find by name | `reveal 'ast://./src?name=*pattern*'` |
| Find complex code | `reveal 'ast://./src?complexity>10'` |
| Find long functions | `reveal 'ast://./src?lines>50'` |
| Debug Python env | `reveal python://` |
| Check stale bytecode | `reveal python://debug/bytecode` |
| Navigate JSON | `reveal json://file.json/path/to/key` |
| JSONL records | `reveal file.jsonl --head 10` |
| Check changes | `git diff --name-only \| reveal --stdin --check` |
| Get JSON output | `reveal file.py --format=json` |
| Copy to clipboard | `reveal file.py --copy` |
| Extract links | `reveal doc.md --links` |
| Extract code blocks | `reveal doc.md --code` |
| First/last N functions | `reveal file.py --head 5` / `--tail 5` |
| Specific line range | `reveal file.py --range 42-80` |
| List all rules | `reveal --rules` |
| Explain rule | `reveal --explain B001` |
| Check file type | `reveal file.py --meta` |

---

## Help System Overview

**For AI agents (you):**
- **Quick reference** (`reveal --agent-help`) - Task-based patterns (~2,200 tokens)
- **This complete guide** (`reveal --agent-help-full`) - Comprehensive reference (~12,000 tokens)

**For humans:**
- **CLI reference** (`reveal --help`) - All flags and options
- **Progressive help** (`reveal help://`) - Explorable documentation
  - `reveal help://ast` - AST adapter details
  - `reveal help://python-guide` - Python adapter deep dive
  - `reveal help://tricks` - Cool tricks and hidden features

**You don't need to explore help://** - this guide has everything you need. The examples above cover 95% of use cases.

---

**Version:** 0.31.0
**Last updated:** 2026-01-05
**Source:** https://github.com/Semantic-Infrastructure-Lab/reveal
**PyPI:** https://pypi.org/project/reveal-cli/

---

## What Changed in This Guide

This is the redesigned complete AI agent reference (Dec 2025). Changes:

- **Task-oriented** - "When you need to do X, use Y" structure
- **Example-heavy** - Concrete commands that actually work
- **Real-world scenarios** - Actual situations you'll encounter
- **Complete coverage** - All adapters, all rules, all features
- **Pipeline workflows** - Advanced composition patterns
- **Troubleshooting** - Common issues and solutions
- **Performance data** - Benchmarks and optimization tips

The old version organized by "Use Cases" and "Workflows" - this version organizes by tasks with progressive complexity.
