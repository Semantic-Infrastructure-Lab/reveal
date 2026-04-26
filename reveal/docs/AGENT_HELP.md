---
title: Reveal - AI Agent Reference (Complete)
category: guide
---
# Reveal - AI Agent Reference (Complete)
**Version:** 0.84.0
**Purpose:** Comprehensive guide for AI code assistants
**Token Cost:** ~12,000 tokens
**Audience:** AI agents (Claude Code, Copilot, Cursor, etc.)

---

## About This Guide

This is the complete offline reference for reveal (~26,500 tokens). Both `--agent-help` and `--agent-help-full` serve this file.

**For interactive usage:** Use `reveal help://topic` for progressive, low-token discovery.
- `reveal help://ast` - AST adapter details
- `reveal help://tricks` - Cool tricks and hidden features

---

## Agent Introspection (v0.56.0+ - Complete Coverage)

**NEW: Auto-discover capabilities programmatically**

AI agents can now query reveal's capabilities via machine-readable schemas:

```bash
# List all available adapter schemas
reveal help://schemas                               # listing: ast, ssl, git, ...

# List all available task recipe categories
reveal help://examples                             # listing: quality, security, ...

# Discover adapter schemas (all 23 adapters support this)
reveal help://schemas/<adapter> --format=json

# File & Analysis Adapters
reveal help://schemas/ast --format=json        # Code structure analysis
reveal help://schemas/stats --format=json      # Code statistics
reveal help://schemas/imports --format=json    # Import graph analysis
reveal help://schemas/calls --format=json      # Cross-file call graph
reveal help://schemas/diff --format=json       # Resource comparison

# Environment & Data Adapters
reveal help://schemas/env --format=json        # Environment variables
reveal help://schemas/json --format=json       # JSON file navigation
reveal help://schemas/markdown --format=json   # Markdown queries
reveal help://schemas/python --format=json     # Python runtime
reveal help://schemas/mysql --format=json      # MySQL databases
reveal help://schemas/sqlite --format=json     # SQLite databases
reveal help://schemas/xlsx --format=json       # Excel/spreadsheet files

# Infrastructure Adapters
reveal help://schemas/ssl --format=json        # SSL certificates
reveal help://schemas/domain --format=json     # Domain DNS/WHOIS
reveal help://schemas/git --format=json        # Git repositories
reveal help://schemas/claude --format=json     # Claude conversations
reveal help://schemas/autossl --format=json    # cPanel AutoSSL run logs
reveal help://schemas/nginx --format=json      # Nginx vhost inspection
reveal help://schemas/cpanel --format=json     # cPanel user environments
reveal help://schemas/letsencrypt --format=json # Let's Encrypt cert inventory

# Meta Adapters
reveal help://schemas/reveal --format=json     # Self-inspection

# Get canonical query recipes for common tasks
reveal help://examples/codebase --format=json        # Codebase exploration recipes
reveal help://examples/debugging --format=json       # Debugging recipes
reveal help://examples/documentation --format=json   # Markdown/doc search recipes
reveal help://examples/infrastructure --format=json  # nginx, SSL, domain recipes
reveal help://examples/quality --format=json         # Code quality recipes
reveal help://examples/security --format=json        # Security analysis recipes
```

**What you get:**
- **Query parameters**: All available filters with types and operators
- **Output schemas**: JSON Schema definitions of adapter outputs
- **Example queries**: Canonical examples for each adapter
- **CLI flags**: Available command-line flags
- **Elements**: Available element-based queries
- **Notes**: Adapter-specific gotchas, behavior details, and usage patterns

**Use case:** Generate valid queries from schema without hardcoding adapter syntax.

**Example schema output:**
```json
{
  "adapter": "ast",
  "uri_syntax": "ast://<path>?<filter1>&<filter2>&...",
  "query_params": {
    "lines": {
      "type": "integer",
      "operators": [">", "<", ">=", "<=", "=="],
      "examples": ["lines>50", "lines<20"]
    },
    "complexity": {
      "type": "integer",
      "operators": [">", "<", ">=", "<=", "=="],
      "examples": ["complexity>10"]
    }
  },
  "example_queries": [
    {
      "uri": "ast://./src?complexity>10",
      "description": "Find complex functions",
      "output_type": "ast_query"
    }
  ],
  "notes": [
    "Quote URIs with > or < operators: 'ast://path?lines>50' (shell interprets > as redirect)",
    "Operators: = (equals), != (not equals), > < (numeric), ~= (regex/glob), .. (range)",
    "Result control: sort=field, sort=-field (descending), limit=N, offset=M"
  ]
}
```

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
# Hierarchical view — file-level (classes with methods)
reveal src/main.py --outline

# Control-flow skeleton — function-level (branches, loops, returns)
reveal src/main.py process_request --outline

# Just function names (fast scan)
reveal src/main.py --format=json | jq '.structure.functions[].name'

# Find complex functions first
reveal src/main.py --format=json | jq '.structure.functions[] | select(.depth > 3)'
```

**Note:** `--outline` has two distinct modes that produce different output:
- `reveal file.py --outline` — file-level class/method hierarchy (structural tree)
- `reveal file.py myfunc --outline` — function-level control-flow skeleton (if/while/for/return branches)

These answer different questions. The element-level mode is the entry point to all nav flags. See the "Navigate inside a function" task below.

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
- `decorator=X` - Has specific decorator (exact match)
- `has_decorator=X` - Has decorator (presence check; use when exact name uncertain)
- `param_type=X` - Filter by parameter annotation (glob supported: `List*`)
- `return_type=X` - Filter by return annotation (glob supported: `Optional*`)
- `has_annotations=true/false` - `false` = fully unannotated; `true` = fully annotated
- `callers>N` - Inbound caller count above N (combine with `complexity>10` for prime refactor targets)
- `reveal_type=VAR` - Show type evidence for a variable without editing source
- `show=dict-heatmap` - Rank bare-dict params by key access; suggests TypedDict names

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

### Task: "Search within a single file" (NEW - v0.47.3)

**Ergonomic convenience flags for within-file operations:**

```bash
# Find functions by name pattern (simple)
reveal file.py --search connection
# Same as: reveal 'ast://file.py?name~=connection'

# Filter by element type
reveal file.py --type function
# Same as: reveal 'ast://file.py?type=function'

# Sort results
reveal file.py --sort complexity          # Ascending
reveal file.py --sort=-complexity         # Descending (note the = sign)

# Combine flags
reveal file.py --search test --type function --sort=-complexity
# Same as: reveal 'ast://file.py?name~=test&type=function&sort=-complexity'
```

**Why use convenience flags?**
- **Ergonomic**: Simpler syntax for common operations (80% use case)
- **Familiar**: Similar to grep/find command patterns
- **Progressive**: Use flags for simple queries, URI syntax for complex ones

**Convenience flags vs URI syntax:**

| Task | Convenience Flags | URI Syntax |
|------|------------------|------------|
| Find by name | `--search pattern` | `?name~=pattern` |
| Filter type | `--type function` | `?type=function` |
| Sort results | `--sort field` | `?sort=field` |
| Complex query | ❌ (use URI) | `?complexity>10&lines>50&sort=-complexity` |

**Example: Replace grep workflow**
```bash
# Old workflow (grep)
grep -n "get_repository" file.py

# New workflow (reveal)
reveal file.py --search get_repository
# Output shows line numbers, complexity, signatures

# With sorting
reveal file.py --search get_repository --sort=-line_count
```

**When to use URI syntax instead:**
- Multiple conditions: `?complexity>10&lines>50`
- Range queries: `?lines=10..50`
- Boolean logic: `?type=function|method`
- Advanced operators: `!=`, `~=`, `..`

---

### Task: "Review code quality"

**Pattern (v0.57.0+: use subcommand form):**
```bash
# Subcommand form (preferred — own --help, clean namespace)
reveal check src/                      # Check directory recursively
reveal check file.py                   # Check single file
reveal check src/ --select B,S         # Bugs & security only
reveal check src/ --format json        # JSON for CI/CD gating

# Legacy flag form (still works)
reveal file.py --check
reveal file.py --check --select B,S    # Bugs & security only
reveal file.py --check --select C,E    # Complexity & errors only

# Specific file types
reveal check nginx.conf                # Nginx validation (N001-N012)
reveal check Dockerfile                # Docker best practices (S701)
```

**Available rule categories:**
- **B** (bugs) - Common code bugs and anti-patterns (B001-B006)
- **C** (complexity) - Code complexity metrics (C901, C902, C905)
- **D** (duplicates) - Duplicate code detection (D001; D002 exists but is disabled by default — enable with `--select D002`)
- **E** (errors) - Line length and formatting (E501)
- **F** (frontmatter) - Markdown front matter validation (F001-F005)
- **I** (imports) - Import analysis and dependencies (I001-I006)
- **L** (links) - Link validation and documentation (L001-L005)
- **M** (maintainability) - Code maintainability checks (M101-M105)
- **N** (nginx) - Nginx configuration validation (N001-N012)
- **R** (refactoring) - Refactoring opportunities (R913)
- **S** (security) - Security vulnerabilities (S701)
- **T** (types) - Type annotation issues (T004)
- **U** (urls) - URL consistency and security (U501, U502)
- **V** (validation) - Internal validation rules (V001-V023)

**List all rules:** `reveal --rules`
**Explain specific rule:** `reveal --explain B001`

**Example output:**
```
File: src/auth.py (234 lines, Python)

Quality Issues (3):

  B003: @property 'headers' is 17 lines (max 15) (line 45)
    @property
    def headers(self): ...  # ❌ Too complex for a property
    Suggestion: Consider converting to a regular method: def get_headers(self)

  C901: High cyclomatic complexity (line 67)
    Function: authenticate_user (complexity: 12)
    Suggestion: Consider breaking into smaller functions

  B006: Broad exception handler with silent pass (line 89)
    except Exception: pass
    Suggestion: Log or re-raise — silent pass hides bugs
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

**Suppressing false positives with `.reveal.yaml`:**

Some rules fire on valid patterns in certain codebases. Use `.reveal.yaml` to suppress selectively rather than disabling globally:

```yaml
# Disable a rule for specific directories (preferred — narrow scope)
overrides:
  - files: "workers/**"
    rules:
      disable: [M102]        # M102: task workers look like dead code but are loaded dynamically
  - files: "plugins/**"
    rules:
      disable: [M102]        # Same: plugin registry loads these at runtime
  - files: "blueprints/**"
    rules:
      disable: [M102]

# Disable a rule globally (use sparingly)
rules:
  disable: [M102]
```

**Common false positive rules and their causes:**

| Rule | False positive trigger | Root cause |
|------|------------------------|------------|
| **M102** | Workers, plugins, blueprints, rule discovery modules | Module loaded dynamically via registry/factory — M102 sees no call sites at analysis time |
| **B005** | `try/except ImportError: …` optional deps | Fixed in v0.67.0+: B005 now skips imports inside `try/except ImportError` blocks |
| **I001** | `__init__.py` re-exports | Fixed in v0.61+: I001 now skips `__all__`-listed names |

**M102 heuristic detail:** M102 (unused module members) scans call sites within the same file and across the project. It cannot follow `getattr(module, name)()` dispatch, `importlib.import_module` loading, or registration patterns like `RULES = {k: v for k, v in globals().items() if isinstance(v, BaseRule)}`. When you see M102 on a file full of small classes with no direct callers, check whether a registry or factory loads them.

---

### Task: "Extract specific code element"

**Extraction syntaxes:**
```bash
# By name
reveal app.py process_request          # Extract function by name
reveal app.py DatabaseHandler          # Extract class by name

# Hierarchical (nested elements)
reveal app.py DatabaseHandler.connect  # Extract method within class
reveal app.py Outer.Inner.method       # Multiple nesting levels

# By line number (from grep, error messages, stack traces)
reveal app.py 73                       # Element at line 73 (or ±10 context window)
reveal app.py :73                      # Same — bare integer and :N are equivalent
reveal app.py :42-80                   # Exact line range

# By position (ordinal)
reveal app.py @1                       # First element (usually function)
reveal app.py @3                       # Third element

# By type + position
reveal app.py function:2               # Second function
reveal app.py class:1                  # First class
```

**When to use each:**
- **Name** - You know what you're looking for
- **Hierarchical** - You see `Class.method` in outline or structure
- **Line number** - Error message says "line 73" or grep found `:73:` — bare integer works too
- **Ordinal** - You ran `reveal file.py` and want "the 3rd one"
- **Type+position** - You want "2nd function" specifically

**Head/tail for exploration:**
```bash
reveal app.py --head 5                 # First 5 functions
reveal app.py --tail 5                 # Last 5 functions (where bugs cluster!)
```

**Why tail is useful:** Technical debt and bugs often cluster at the end of files. Functions added later tend to be rushed or less reviewed.

**Advanced extraction:**
```bash
# Extract multiple functions (with --format=json)
reveal app.py --format=json | jq '.structure.functions[] | select(.name | test("^handle_"))'

# Extract function with its decorators
reveal app.py decorated_function       # Automatically includes @decorators
```

**Hierarchical view (--outline):**
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

### Task: "Navigate inside a function — outline, scope, variable flow, calls, and more" (v0.72.0+, extended v0.78.0+)

Progressive disclosure flags for navigating inside functions and flat procedural files. Use when a function (or a large flat file like a PHP controller) is too large to read in full.

**`--outline` on an element → control-flow skeleton**
```bash
reveal app.py process_batch --outline

# Output:
# DEF process_batch  L1→L13
#   FOR  item in items  L3→L12
#     IF  item.active  L4→L12
#     ELIF  item.pending  L7→L12
#       TRY  L8→L12
#   RETURN  results  L13
```
Shows the shape of the function without reading every line. Default depth 3; use `--depth N` to go deeper.

**`--scope :LINE` → ancestor context for a line**
```bash
reveal app.py :5 --scope

# Output:
# FOR     L3→L12          FOR  item in items
#   IF      L4→L12          IF  item.active
#
#     ▶ L5 is here
```
Useful when a stack trace or grep result gives you a line number and you need to know what scope it's inside.

**`--varflow VAR` → read/write trace for a variable**
```bash
reveal app.py process_batch --varflow results   # inside a named function
reveal flat_file.php :1-2000 --varflow errormsg  # flat procedural file

# Output:
# WRITE     L2:  results = []
# READ      L6:  results.append(value)
# READ/COND L10:  if not results:
# READ      L13:  return results
```
Shows every place the variable is assigned (WRITE), read (READ), or tested in a condition (READ/COND). Works on both named functions and flat/procedural files without a function wrapper.

**`--varflow VAR --cross-calls` → follow variable across function boundaries (v0.84.0+)**
```bash
reveal app.py process_batch --varflow results --cross-calls

# Output (indented frames show cross-function propagation):
# WRITE     L2:  results = []
# READ      L6:  results.append(value)
# ↳ validate(results)           # 'results' passed as arg
#     READ      L18:  for item in results:  # tracked as param inside callee
```
When the tracked variable appears as an argument in a call, recursion enters the callee and tracks the corresponding parameter. DFS with cycle guard. Reveals end-to-end data flow across module boundaries.

**`--narrow VAR` → type-narrowing path for a variable (v0.84.0+)**
```bash
reveal app.py process_request --narrow response

# Output:
# Optional[Response] → Response  (narrowed by 'if response is not None' at L47)
# Response → None                (narrowed by 'if not response' at L62 → else branch)
```
Parses `Optional[X]`, `Union[X,Y,None]`, `X|Y` annotations and classifies `isinstance`, `not isinstance`, `is None`, `is not None` guards. Shows the type at each branch. Useful before editing code that handles nullable types.

> **PHP support (v0.81.0+)**: All nav flags including `--varflow`, `--deps`, `--mutations`, `--sideeffects`, `--returns`, and `--boundary` work on PHP files. Note: PHP `foreach` loop variables (`$k`, `$v` in `foreach($arr as $k => $v)`) are tracked but show as READ instead of WRITE — a minor limitation with no current workaround. `--boundary` additionally detects PHP superglobals (`$_GET`, `$_POST`, `$_SESSION`, etc.) and surfaces them in a separate ENVIRONMENT section.

**`--calls` → call sites in a line range**
```bash
reveal app.py process_batch --calls 7-12          # scoped to lines 7-12
reveal flat_file.php :477-531 --calls             # flat file, whole element range
reveal app.py process_batch --calls               # all calls in the function

# Output:
# L9:  retry(item)
# L10:  results.append(value)
# L12:  log_error(e)
```
> **Disambiguation**: `--calls` (this flag) lists call sites *within a line range* — it's a sub-element analysis tool. `calls://` (the URI adapter) is a project-level call graph — use `reveal 'calls://file.py?target=myfunc'` to find which functions *across the project* call `myfunc`. Different scope, different question.

**`--around N` → verbatim context centered on a line (v0.78.0+)**
```bash
reveal app.py :123 --around      # ±20 lines (default)
reveal app.py :123 --around 10  # ±10 lines

# Output:
#   118  def helper(x):
#   119      ...
# ▶ 123      critical_call(x)
#   124      ...
```
Eliminates the mental arithmetic of picking a line range when you just know a line number. The `▶` marker points to the target line.

**`--ifmap` → branching skeleton (IF/ELIF/ELSE) (v0.78.0+)**
```bash
reveal flat_file.php :878-2130 --ifmap
reveal app.py process_batch --ifmap

# Output:
# IF  $fb_status == 1  L878→L2130
#   IF  !empty($fb_page_id)  L900→L1050
#   ELSE  L1050→L1200
```
Filtered view of `--outline` showing only conditional branches. Useful before committing to reading a large if/elif/else chain.

**`--catchmap` → exception skeleton (TRY/CATCH/FINALLY) (v0.78.0+)**
```bash
reveal flat_file.php :470-525 --catchmap
reveal app.py process_batch --catchmap

# Output:
# TRY  L400→L592
#   EXCEPT  ValueError  L477→L515
#   EXCEPT  Exception  L516→L554
```

**`--exits` → exit nodes in a range (v0.78.0+)**
```bash
reveal flat_file.php :657-2200 --exits
reveal app.py process_batch --exits

# Output:
# EXIT      L916:  die('quota exceeded')
# RETURN    L1283: return false
```
Lists all return/raise/break/continue/die nodes. Useful for auditing where a large block can exit.

**`--flowto` → exits + reachability verdict (v0.78.0+)**
```bash
reveal flat_file.php :2928-3663 --flowto

# Output:
# BREAK     L3123: break 1
#
# flowto L3663: ~ CONDITIONAL
```
Verdict: `✓ CLEAR` (no exits), `~ CONDITIONAL` (only loop breaks/continues), `⚠ BLOCKED` (hard return/raise).

**`--deps` → variables flowing INTO a range (v0.78.0+)**
```bash
reveal flat_file.php :1136-1463 --deps
reveal app.py process_batch --deps --range 20-80

# Output:
# PARAM  size_bytes                    first read L1136  (never written in range)
# PARAM  file_handle                   first read L1148  (never written in range)
```
Shows which variables the range depends on — what would become function parameters if you extracted this block.

**`--mutations` → variables written in range and read after (v0.78.0+)**
```bash
reveal flat_file.php :1136-1463 --mutations
reveal app.py process_batch --mutations --range 20-80

# Output:
# RETURN chunk_upload_success          written L1455, next read L1466
# RETURN is_rate_limit_error           written L1386, next read L1466
```
Shows which variables the caller would need back — what would become return values if you extracted this block. Together with `--deps`, this is a full refactoring pre-flight.

> `--writes` is an alias for `--mutations` — use whichever reads more naturally. Empty-result message says "No read-after-write hazards" with a `--varflow` hint.

**`--sideeffects` → classified side-effect calls (db/http/cache/log/file/sleep/hard_stop) (v0.81.0+)**
```bash
reveal flat_file.php :477-531 --sideeffects
reveal app.py myfunc --sideeffects

# Output (flat, in line order):
# L3       db         mysql_query("SELECT * FROM orders...")
# L5       log        error_log("DB failed")
# L6       hard_stop  die("fatal error")
# L9       http       curl_exec($ch)
# L11      sleep      sleep(1)
# L12      file       file_put_contents("/tmp/...")
```
Shows what external systems a range touches. Useful for assessing blast radius, spotting unexpected I/O, or understanding retry safety. Works on PHP and Python.

**`--returns` → return/exit paths with gate chains (v0.81.0+)**
```bash
reveal app.py process_order --returns
reveal flat_file.php :120-340 --returns

# Output:
# RETURN    L198:  return false
#           gate: not token (L145)
#
# RETURN    L280:  return result
#           gate: token_valid (L210)
#           gate: api_ok (L251)
#
# RETURN    L340:  return true  [unconditional]
```
For each exit point (return/raise/throw/die), shows the full condition chain that must be true to reach it. `[unconditional]` means the exit is reachable without any guard. Complements `--exits` (which locates exits) with path analysis (which conditions gate each one). Works on PHP and Python.

**`--boundary` → boundary contract: INPUTS / ENVIRONMENT / EFFECTS (v0.81.0+)**
```bash
reveal app.py process_order --boundary
reveal flat_file.php handleRequest --boundary

# Output (PHP example):
# INPUTS (undefined reads):
#   $config                           first read L2
#
# ENVIRONMENT (superglobal reads):
#   $_SESSION                         first read L3
#   $_GET                             first read L4
#
# EFFECTS:
#   db   L5       mysql_query("SELECT * FROM items WHERE user=" . $...)
#   log  L6       error_log("Fetched page " . $page)
```
Composes `--deps` + `--sideeffects` into a single boundary-contract report: what the code receives (INPUTS), what environment state it reads (ENVIRONMENT — PHP superglobals `$_GET`, `$_POST`, `$_SESSION`, etc.), and what it does to the world (EFFECTS). The ENVIRONMENT section is omitted when empty (Python files rarely have superglobals). The highest-value single-flag summary for understanding an unfamiliar code range.

**Most flags work on flat/procedural files (v0.78.0+):**
```bash
# Flat PHP file — no named function required
reveal rr_body.php :878-2130 --ifmap
reveal rr_body.php :657-2200 --exits
reveal rr_body.php :1136-1463 --deps
reveal rr_body.php :477-531 --sideeffects
reveal rr_body.php :120-340 --returns
reveal rr_body.php :477-531 --boundary
```
All flags accept `:LINE-RANGE` or no element (whole-file fallback). Exception: `--scope` and `--around` require a single `:LINE`. All variable-tracking flags (`--varflow`, `--deps`, `--mutations`) now work on PHP as well as Python (fixed in v0.81.0, BACK-203).

**Combining with `--range` to narrow scope:**
```bash
reveal app.py process_batch --outline --range 7-12   # outline of just lines 7-12
reveal app.py process_batch --varflow value --range 7-12  # trace 'value' in lines 7-12
reveal app.py process_batch --deps --range 7-12      # deps of a sub-range
```

**Class.method syntax works with all nav flags:**
```bash
reveal app.py MyClass.process --outline
reveal app.py MyClass.process --varflow result
reveal app.py MyClass.process --exits
```

**Workflow — large function investigation:**
```bash
# 1. Get the skeleton
reveal app.py process_batch --outline

# 2. Identify the suspicious branch (say lines 7-12)
reveal app.py process_batch --calls 7-12      # what does it call?
reveal app.py process_batch --varflow value   # how does 'value' flow through?
reveal app.py :9 --around                    # see ±20 lines around line 9

# 3. Read only what you need
reveal app.py process_batch --range 7-12      # full source of that branch only
```

**Workflow — refactoring pre-flight (extract function):**
```bash
# Planning to extract lines 1136-1463 into a function?
reveal flat_file.php :1136-1463 --deps        # → these become parameters
reveal flat_file.php :1136-1463 --mutations   # → these become return values
reveal flat_file.php :1136-1463 --exits       # → check for unexpected early exits
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

**Pattern (v0.57.0+: use `reveal review` for one-shot PR reviews):**
```bash
# Full PR review: diff + check + hotspots + complexity
reveal review main..feature
reveal review HEAD~3..HEAD      # Last 3 commits
reveal review ./src             # Review a directory

# Manual approach (more control)
git diff --name-only | reveal --stdin --outline   # Structure of changed files
git diff --name-only | grep "\.py$" | reveal --stdin --check  # Quality check
reveal src/changed_file.py --check
reveal src/changed_file.py changed_function
```

**`reveal review` output:** structural diff + quality violations + top hotspots + complex functions, unified in one pass.

**Advanced workflows:**
```bash
# Compare with main branch
git diff main --name-only | reveal --stdin --outline

# Check only modified (not new) files
git diff --name-only --diff-filter=M | reveal --stdin --check

# JSON output for CI/CD gating
reveal review main..feature --format json

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

### Task: "Trace function call graph"

**Pattern:**
```bash
# Cross-file: who calls a function across the entire project? (reverse)
reveal 'calls://src/?target=validate_item'

# Cross-file: what does a function call? (forward, builtins hidden by default)
reveal 'calls://src/?callees=validate_item'

# Include Python builtins — useful to audit for eval/open/exec
reveal 'calls://src/?callees=validate_item&builtins=true'

# Transitive: callers-of-callers (2 levels)
reveal 'calls://src/?target=validate_item&depth=2'

# Within-file: find all functions that call validate_item
reveal 'ast://src/auth.py?calls=validate_item'

# Within-file: find everything called by process_batch
reveal 'ast://src/?callee_of=process_batch'

# Compact call graph view (arrow diagram)
reveal 'ast://src/?show=calls'

# Graphviz: pipe to dot for SVG
reveal 'calls://src/?target=main&format=dot' | dot -Tsvg > callgraph.svg

# Coupling metrics: rank all functions by how many unique callers they have
reveal 'calls://src/?rank=callers'             # Top 10 most-called functions
reveal 'calls://src/?rank=callers&top=20'      # Top 20
reveal 'calls://src/?rank=callers&builtins=true'  # Include Python builtins
```

**Two adapters — different scopes:**

| Adapter | Scope | Use For |
|---------|-------|---------|
| `calls://src/?target=fn` | Cross-file, whole project | "Who calls fn anywhere?" (reverse) |
| `calls://src/?callees=fn` | Cross-file, whole project | "What does fn call?" (forward, builtins hidden; add `&builtins=true` to include) |
| `calls://src/?rank=callers` | Cross-file, whole project | "Which functions are called most?" (coupling metrics) |
| `ast://src/?calls=fn` | Within-file only | "Does this file call fn?" |
| `ast://src/?show=calls` | Within-file only | "Show me the call graph for this file" |

**JSON output — call fields per function:**
```bash
reveal 'ast://src/auth.py?type=function' --format=json | \
  jq '.results[] | {name, calls, called_by, resolved_calls}'
```

Fields:
- `calls` — outgoing calls from this function
- `called_by` — within-file callers
- `resolved_calls` — cross-file resolved entries (file + name, Python only)

**See also:** `CALLS_ADAPTER_GUIDE.md` for full `calls://` documentation.

**Execution narrative — `reveal trace` (v0.86.0+):**

```bash
# Depth-indented execution narrative from an entry point
reveal trace src/ --from main
reveal trace src/ --from main --depth 3    # expand 3 levels (max 5)
reveal trace src/ --from process_request --json   # JSON output
```

Each frame shows:
- Function name + file:line (relative path)
- `params:` — function parameters
- `effects:` — classified side-effects (hard_stop, db, http, cache, file, log, sleep)
- `calls:` — what it calls at the next level

Output is depth-indented so the execution tree is scannable at a glance.  Unresolved
(external/stdlib) callees appear with an `[external]` marker.

---

### Task: "Add a custom analyzer for a new file type" (plugin auto-discovery, v0.87.0+)

Create a file named `*_analyzer.py` in `.reveal/analyzers/` (project-local) or `~/.reveal/plugins/` (user-global):

```python
# .reveal/analyzers/myformat_analyzer.py
from reveal.base import FileAnalyzer
from reveal.registry import register

@register('.myfmt', name='MyFormat', icon='📄')
class MyFormatAnalyzer(FileAnalyzer):
    def get_structure(self, **kwargs):
        content = self.path.read_text()
        return {'type': 'myformat', 'lines': len(content.splitlines())}
```

On the next `reveal` run, `.myfmt` files are handled by `MyFormatAnalyzer` automatically — no source edits, no registration step. Bad plugin files log a warning and are skipped without crashing.

---

### Task: "Find dead code (uncalled functions)"

**Pattern:**
```bash
reveal 'calls://src/?uncalled'                 # All functions with no callers
reveal 'calls://src/?uncalled&type=function'   # Module-level functions only (skip methods)
reveal 'calls://src/?uncalled&type=method'     # Methods only
reveal 'calls://src/?uncalled&top=20'          # Top 20 most-recently-added uncalled
```

**Suppression:** Add `# noqa: uncalled` to a function's definition line (or up to 3 lines after) to exclude it from results — useful for runtime-dispatched functions, plugin entry points, or framework hooks that are called dynamically.

**Limitations:** Static analysis only — functions called via `getattr`, `importlib`, or string dispatch are not tracked and appear as uncalled. Private (`_prefix`) functions are flagged separately. `__dunder__` methods, `@property`, `@classmethod`, and `@staticmethod` are excluded automatically.

---

### Task: "Find what depends on a module (reverse import graph)"

**Pattern:**
```bash
# Codebase-wide fan-in ranking — which files are most central?
reveal 'imports://src?rank=fan-in'
reveal 'imports://src?rank=fan-in&top=10'

# Who imports this specific file?
reveal depends://src/utils.py

# Who imports anything in models/?
reveal depends://src/models/

# Full reverse graph in GraphViz DOT format
reveal 'depends://src?format=dot' | dot -Tsvg > deps.svg
```

**Key use cases:**
- **Architectural orientation** — three complementary views from the import graph:
  - `imports://src?rank=fan-in` — ranks every file by importer count. High fan-in = core abstractions (change carefully); zero = entry points or dead code.
  - `imports://src?entrypoints` — lists only the fan-in=0 files, sorted by fan-out. High fan-out = real CLI/runner; zero = likely dead code.
  - `imports://src?components` — scores each directory as a component: cohesion (how self-contained), coupling (incoming/outgoing), top bridge file. Low cohesion = not a real component.
- **Impact analysis before refactoring** — before changing `utils.py`, run `depends://src/utils.py` to see every direct importer
- **Safe deletion** — verify `count: 0` (via `depends://`) before removing a module

**How the tools relate:**

| Tool | Question | Granularity |
|------|----------|-------------|
| `imports://src?rank=fan-in` | Which files are most central? | Codebase ranking |
| `imports://src?entrypoints` | Where does execution start? | Fan-in=0 subset |
| `imports://src?components` | Which directories are real components? | Per-directory |
| `depends://src/module.py` | What exactly imports this file? | Per-file reverse |
| `imports://src` | What does each file import? | Forward, all files |
| `calls://src/?target=fn` | Who calls this function? | Function level |

Use the three `imports://` views for orientation; `depends://` for targeted impact analysis before a specific change.

**Enforce architectural layers (`?violations`):**
```bash
reveal 'imports://src?violations'
```
Flags any import that crosses a layer boundary in the wrong direction (e.g. domain importing infrastructure). Requires `.reveal.yaml` with a `layers:` + `allowed_deps:` config:
```yaml
layers:
  presentation: [src/api/, src/views/]
  application:  [src/services/]
  domain:       [src/models/]
  infrastructure: [src/db/, src/cache/]
allowed_deps:
  presentation: [application]
  application:  [domain]
  domain:       []
  infrastructure: []
```
Output: one line per violation with file, line, and direction. Clean output = ✅ no violations.

**Scan root tip**: scan from the project root (not a subdirectory) when imports use absolute package paths (e.g. `from myapp.utils import x`). Scanning too deep causes the resolver to miss edges, producing false fan-in=0 entries.

**Limitations:** Dynamic imports (`importlib.import_module`) and `TYPE_CHECKING`-only imports are not tracked (same as `imports://`). Results are conservative — false negatives possible, never false positives.

---

### Task: "Find complexity hotspots"

**Pattern:**
```bash
# Subcommand form (preferred)
reveal hotspots .                  # Worst 10 files + complex functions
reveal hotspots ./src --top 20     # Top 20 files
reveal hotspots . --functions-only # Only complex functions
reveal hotspots . --files-only     # Only file-level hotspots
reveal hotspots . --min-complexity 15  # Raise complexity threshold
reveal hotspots . --format json    # JSON for CI/scripting

# Legacy stats:// form (still works)
reveal stats://. --hotspots
```

**Output:** Files ranked by quality score (worst first) + complex functions with cyclomatic complexity scores.

**Use case:** Identify the 10 worst files in a codebase — start technical debt work here. Output is the same data `reveal review` uses to surface hotspots in PR reviews.

---

### Task: "Get a one-glance codebase dashboard"

**Pattern:**
```bash
reveal overview .                  # Full dashboard: stats, languages, quality, hotspots, git
reveal overview ./src              # Scope to a subdirectory
reveal overview . --top 10         # 10 items per section
reveal overview . --no-git         # Skip git history (useful in CI or non-git dirs)
reveal overview . --format json    # Machine-readable output
```

**Output sections:** codebase stats (files, lines, functions, classes) · language breakdown · quality pulse (avg score, hotspot count) · top hotspots with `→ reveal <file>` hints · top complex functions · architecture (entry points, core abstractions, component cohesion bars, circular count) · recent git commits with age labels. Skip architecture with `--no-imports`.

**Use case:** Fast orientation for an unfamiliar codebase. Combined entry point before deciding which area to investigate with `reveal hotspots`, `reveal deps`, or `ast://`.

---

### Task: "Get an architectural brief before editing a module"

**Pattern:**
```bash
reveal architecture src/           # Entry points, core abstractions, risks, next commands
reveal architecture src/auth/      # Target a specific subdirectory
reveal architecture . --format json  # Machine-readable: {facts, risks[], next_commands[]}
reveal architecture src/ --no-imports  # Skip import analysis (faster, no graph)
```

**Output sections:** entry points (fan-in=0, by fan-out) · core abstractions (most imported) · component cohesion bars · risks (circular groups, high-complexity entry points, load-bearing files) · next commands (dynamically generated from findings).

**Use case:** Pre-edit orientation for a specific module. More targeted than `reveal overview` — works on subdirectories and produces a risks + next_commands structure agents can act on directly. `next_commands` tells the agent exactly what to look at next without further reasoning.

---

### Task: "Build a token-budgeted context snapshot with architecture awareness"

**Pattern:**
```bash
reveal pack ./src --architecture            # Boost core abstractions; prepend architecture brief
reveal pack ./src --architecture --budget 6000
reveal pack ./src --architecture --content  # Architecture brief + structure content per file
reveal pack ./src --since main --architecture --budget 8000  # PR context + arch brief
```

**`--architecture` does two things:**
1. Queries `imports://` fan-in data and boosts widely-imported files in the priority score (fan-in ≥1: +1pt, ≥5: +3pt, ≥15: +5pt)
2. Prepends an **Architecture Brief** before the tier list:
```
── Architecture Brief ──
Entry points:      main.py
Core abstractions: utils/__init__.py(39)  base.py(27)  registry.py(14)
```

**Use case:** When starting work on an unfamiliar codebase — `--architecture` ensures the token budget is spent on structurally important files (widely depended-on abstractions), not just recently modified ones. Combine with `--content` for a single self-contained agent context.

---

### Task: "Check dependency health"

**Pattern:**
```bash
reveal deps .                      # Full dependency dashboard
reveal deps ./src                  # Scope to a subdirectory
reveal deps . --no-unused          # Skip unused imports (focus on structure)
reveal deps . --format json        # Machine-readable for CI
```

**Output:** Third-party package summary · health line (circular deps + unused imports) · top packages by usage · circular dependency cycles · unused imports with file:line · top importers.

**Exit codes:** 0 (clean) · 1 (circular deps or unused imports found — CI-friendly gate).

**Use case:** Before a release or major refactor — confirm no accidental circular imports crept in, surface unused imports to clean up, see dependency surface area at a glance.

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
reveal check nginx.conf                # N001-N012 rules
# - N001: Duplicate backends (upstreams with same server:port)
# - N002: Missing SSL certificates
# - N003: Missing proxy headers
# - N004: ACME challenge path inconsistency (cert renewal failures)
# - N005: Timeout/buffer values outside safe operational ranges
# - N006: send_timeout too short relative to client_max_body_size (HIGH)
# - N007: ssl_stapling on but no OCSP URL in cert (stapling silently ineffective)
# - N008: HTTPS server block missing Strict-Transport-Security (HIGH)
# - N009: server_tokens not disabled (nginx version exposed)
# - N010: Deprecated X-XSS-Protection header present
# - N011: SSL listener missing http2 (certbot strips it on renewal)
# - N012: No rate limiting applied to server block

# Focus on one rule (e.g. ACME paths only) — essential for large cPanel configs
reveal check ea-nginx.conf --select N004     # ACME paths only
reveal check ea-nginx.conf --ignore N011,E501  # suppress certbot/line-length noise

# Tip: large generated configs (e.g. cPanel) collapse repeated rules by default
reveal check ea-nginx.conf             # 2,685 N003s shown as one summary line
reveal check ea-nginx.conf --no-group  # expand all occurrences
# Add '# reveal: generated' to skip a file in recursive sweeps

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

N004: ACME challenge path inconsistency
  server { server_name a.com; location /.well-known/acme-challenge/ { root /var/www/a; } }
  server { server_name b.com; location /.well-known/acme-challenge/ { root /var/www/b; } }
  # ❌ Inconsistent paths cause cert renewal failures (Let's Encrypt)
```

**Nginx ACL and routing checks:**
```bash
# N1: Check that nobody user can read every docroot (cPanel nginx requirement)
reveal /etc/nginx/conf.d/users/USERNAME.conf --check-acl
# Exit 2 on any path component that blocks nobody (ACME renewal will fail)

# N4: Find ACME root paths + ACL status in one table
reveal /etc/nginx/conf.d/users/USERNAME.conf --extract acme-roots
# domain → acme root path → ACL status

# N2: Detect location block routing surprises
reveal /etc/nginx/conf.d/users/USERNAME.conf --check-conflicts
# prefix_overlap: one non-regex location is a strict prefix of another
# regex_shadows_prefix: regex pattern can match a prefix location's path
# Exit 2 on regex conflicts; prefix overlap is info-only

# N3: Filter output to a specific server block (essential for 1,500-line cPanel configs)
reveal /etc/nginx/conf.d/users/USERNAME.conf --server-name example.com
```

**cPanel nginx audit commands:**
```bash
# The single command that would have caught a Feb 2026 production SSL incident:
reveal /etc/nginx/conf.d/users/USERNAME.conf --validate-nginx-acme
# Per-domain table: ACME root path | nobody ACL status | live SSL cert status
# Exit 2 on any ACL failure or SSL expiry
# On large configs (500+ domains), filter to problems only:
reveal /etc/nginx/conf.d/users/USERNAME.conf --validate-nginx-acme --only-failures

# Machine-readable JSON output (for agents / scripting)
reveal /etc/nginx/conf.d/users/USERNAME.conf --validate-nginx-acme --format=json
# Shape: {type: "nginx_acme_audit", has_failures: bool, only_failures: bool, domains: [...]}
# Each domain: {domain, acme_path, acl_status, ssl_status, ssl_days, has_failure}
# Exit 2 still fires on failures even in JSON mode
# Combine with --only-failures: only domains with has_failure=true in output
reveal /etc/nginx/conf.d/users/USERNAME.conf --validate-nginx-acme --format=json --only-failures
reveal /etc/nginx/conf.d/users/USERNAME.conf --validate-nginx-acme --format=json | jq '.domains[] | select(.has_failure)'

# Check nginx error log for ACME/SSL failures (retroactive diagnosis)
reveal /etc/nginx/conf.d/users/USERNAME.conf --diagnose
# Scans last 5,000 lines of nginx error log for:
# - permission_denied: open() on /.well-known/ returned EACCES (exit 2)
# - ssl_error: SSL_CTX_use_certificate / handshake failures (exit 2)
# - not_found: ENOENT on /.well-known/ (info-only, exit 0)
# Groups by (domain, pattern): count + last seen + sample line
# Override log path: reveal ... --diagnose --log-path /var/log/nginx/error.log

# Check cPanel disk certs vs live certs (detect stale-after-AutoSSL-renewal)
reveal /etc/nginx/conf.d/users/USERNAME.conf --cpanel-certs
# Per-domain table: disk cert expiry | live cert expiry | match status
# ⚠️ STALE (reload nginx) when serial numbers differ
# Exit 2 on stale or expired certs
```

**Fleet consistency matrix (`nginx:// --audit`):**
```bash
reveal nginx:// --audit                    # Cross-site matrix: where does the fleet diverge?
reveal nginx:// --audit --only-failures    # Directives with gaps only
reveal nginx:// --audit --format json      # Machine-readable
```
Reads all enabled site configs + `nginx.conf`, compares each directive against the fleet majority pattern. Surfaces: missing HSTS headers, server_tokens on, deprecated X-XSS-Protection, http2 gaps, rate limiting gaps, snippet inconsistencies. Flags directives present in ≥50% of server blocks but absent from the global `http{}` block as consolidation opportunities.

---

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

### Task: "Check SSL certificates"

**Pattern:**
```bash
# Certificate overview (~150 tokens)
reveal ssl://example.com

# Health check with exit codes (0=pass, 1=warning, 2=critical)
reveal ssl://example.com --check

# Subject Alternative Names (all domains covered)
reveal ssl://example.com/san

# Certificate chain
reveal ssl://example.com/chain

# Non-standard port
reveal ssl://example.com:8443

# Batch check from file (one domain per line, supports comments with #)
reveal @domains.txt --check

# Batch check via stdin
echo -e "ssl://a.com\nssl://b.com" | reveal --stdin --check
```

**Batch output includes inline failure detail and expiry dates:**
```
# Failures show reason inline:
example.com         EXPIRED  3 days ago  (Jan 25, 2026)
api.example.com     DNS FAILURE (NXDOMAIN)
db.example.com      CONNECTION REFUSED
cdn.example.com     TIMEOUT

# Warnings show expiry date:
staging.example.com  WARNING  expires in 12 days  (Mar 11, 2026)

# Healthy domains show expiry:
www.example.com      OK       182 days  (Aug 27, 2026)
```

**On-disk certificate inspection (cPanel / file-based certs):**
```bash
# Inspect a PEM cert on disk without a live connection
reveal ssl://file:///var/cpanel/ssl/apache_tls/example.com/combined
# Same health/expiry/SAN display as live cert
# PEM combined files (leaf + chain) are split; chain count surfaced
# Next step suggested: reveal ssl://example.com --check for disk-vs-live

# Any PEM or DER file
reveal ssl://file:///etc/letsencrypt/live/example.com/fullchain.pem
```

**Local cert validation (no network required):**
```bash
# Validate certs referenced in a nginx config directly on disk
reveal ssl://nginx:///etc/nginx/nginx.conf --check --local-certs
# Reports expiry status per cert file — no live connection needed
# Useful for servers without outbound HTTPS or for pre-deployment checks
```

**Nginx SSL audit (composable pipeline):**
```bash
# See nginx config with SSL status indicators
reveal /etc/nginx/nginx.conf

# Extract SSL domains as ssl:// URIs
reveal /etc/nginx/nginx.conf --extract domains

# Full SSL audit pipeline: extract → check
reveal /etc/nginx/nginx.conf --extract domains | reveal --stdin --check

# Show only failures and warnings
reveal /etc/nginx/nginx.conf --extract domains | reveal --stdin --check --only-failures

# Quick summary (counts only)
reveal /etc/nginx/nginx.conf --extract domains | reveal --stdin --check --summary

# Filter to expiring soon
reveal /etc/nginx/nginx.conf --extract domains | reveal --stdin --check --expiring-within=30
```

**SSL elements:**
- `/san` - Subject Alternative Names (all domains covered by cert)
- `/chain` - Certificate chain information
- `/issuer` - Certificate issuer details
- `/subject` - Certificate subject details
- `/dates` - Validity dates
- `/full` - Full certificate as JSON

**Batch filter flags:**
- `--only-failures` - Hide healthy certs, show only warnings/failures
- `--summary` - Show aggregated counts instead of per-domain details
- `--expiring-within=N` - Filter to certs expiring within N days

**Health check thresholds:**
- Warning: <30 days until expiry (exit code 1)
- Critical: <7 days until expiry (exit code 2)
- Also checks: chain validity, hostname match

**Live TLS + redirect checks:**
```bash
# TLS version + cipher suite (in --advanced)
reveal ssl://example.com --check --advanced
# → tls_version: Using TLSv1.3 / TLS_AES_256_GCM_SHA384 (256-bit) (recommended)

# HTTP→HTTPS redirect verification (standalone)
reveal ssl://example.com --probe-http
# → follows chain from http://, reports hop count, final URL, HSTS/CSP headers

# Full TLS + redirect audit in one pass
reveal ssl://example.com --check --probe-http
# → cert health + redirect check; failing redirect elevates exit code to 2
```

**Workflow: Nginx + SSL integration**
```bash
# 1. Check nginx config for issues (N004 detects ACME path problems)
reveal /etc/nginx/nginx.conf --check --select N

# 2. Check all SSL certificates from nginx
reveal /etc/nginx/nginx.conf --extract domains | reveal --stdin --check --only-failures

# 3. Find certs expiring within 14 days
reveal /etc/nginx/nginx.conf --extract domains | reveal --stdin --check --expiring-within=14
```

---

### Task: "Inspect nginx vhost configuration"

The `nginx://` adapter provides domain-centric nginx vhost inspection — structured view of ports, upstreams, auth, and location blocks. No nginx binary required; reads config files directly.

**Pattern:**
```bash
# Overview: all enabled vhosts on this server
reveal nginx://

# Full vhost summary: ports, upstreams, auth, locations
reveal nginx://example.com

# Specific sub-view
reveal nginx://example.com/ports      # Listening ports (80/443, SSL, redirect)
reveal nginx://example.com/upstream   # proxy_pass targets + TCP reachability
reveal nginx://example.com/auth       # auth_basic / auth_request directives
reveal nginx://example.com/locations  # Location blocks with routing targets
reveal nginx://example.com/config     # Full raw server block(s)

# JSON for programmatic use
reveal nginx://example.com --format=json
```

**nginx:// views:**
- `nginx://` — overview: all enabled sites with config file paths
- `nginx://domain` — full vhost summary for a specific domain
- `nginx://domain/ports` — port listeners (HTTP, HTTPS, redirect rules)
- `nginx://domain/upstream` — backend servers with TCP connectivity check
- `nginx://domain/auth` — auth_basic realm, auth_request paths
- `nginx://domain/locations` — location blocks with proxy/static/return routing
- `nginx://domain/config` — raw server block text from the config file

**When to use which view:**

| Scenario | Command |
|----------|---------|
| "Is this domain configured?" | `reveal nginx://example.com` |
| "What port does it listen on?" | `.../ports` |
| "Where does it proxy to?" | `.../upstream` |
| "Is it password-protected?" | `.../auth` |
| "What's the raw config?" | `.../config` |
| "Show all sites on this server" | `reveal nginx://` |

**Combine with other adapters:**
```bash
# After nginx upstream check, verify the backend service
reveal nginx://example.com/upstream  # shows proxy_pass target
reveal domain://api.example.com      # inspect the upstream domain

# domain:// also supports WHOIS lookup
reveal domain://example.com/whois    # registrar, creation/expiry dates, nameservers
reveal domain://example.com/registrar  # registrar + WHOIS fields (requires: pip install reveal[whois])

# Validate nginx config + SSL in one workflow
reveal nginx://example.com           # check vhost config
reveal ssl://example.com --check     # verify cert health
```

---

### Task: "Inspect domain health — DNS, registration, HTTP"

The `domain://` adapter provides structured domain health checks: DNS records, HTTP response chain, SSL expiry, and WHOIS registration. Combines multiple checks into a single pass.

**Pattern:**
```bash
# Overview: DNS summary, SSL status, nameservers
reveal domain://example.com

# Deep health check: DNS resolution, propagation, SSL expiry, HTTP status
reveal domain://example.com --check

# Show only problems
reveal domain://example.com --check --only-failures

# Specific sub-views
reveal domain://example.com/dns          # All DNS records (A, AAAA, MX, TXT, NS, CNAME, SOA)
reveal domain://example.com/ssl          # SSL certificate status (delegates to ssl://)
reveal domain://example.com/registrar    # Registrar name and key dates from WHOIS
reveal domain://example.com/whois        # WHOIS data (requires: pip install reveal[whois])

# JSON for scripting
reveal domain://example.com --check --format=json
```

**When to use which view:**

| Scenario | Command |
|----------|---------|
| "Is this domain healthy?" | `reveal domain://example.com --check` |
| "What are the DNS records?" | `.../dns` |
| "When does this domain expire?" | `.../registrar` |
| "Is SSL valid?" | `.../ssl` or `reveal ssl://example.com --check` |
| "Is DNS propagated?" | `reveal domain://example.com --check` (includes propagation check) |

**Batch domain checks:**
```bash
# Check multiple domains, show only failures
echo -e "domain://example.com\ndomain://api.example.com" | reveal --stdin --batch --check --only-failures
```

**domain:// vs ssl://:**
- `domain://` — overview + DNS + HTTP + registrar; use for broad health checks
- `ssl://` — deep SSL inspection (cert chain, SANs, cipher suites); use when SSL is the specific concern

---

### Task: "Audit a cPanel user environment"

The `cpanel://` adapter provides a first-class view of a cPanel user's web environment.
All operations are filesystem-based — no WHM API or credentials required.

**Fastest path for agents — one command does everything:**
```bash
# ssl + acl-check + nginx ACME in one pass; exits 2 if any component has failures
reveal cpanel://USERNAME/full-audit

# Machine-readable composite audit
reveal cpanel://USERNAME/full-audit --format=json
# Output shape: {type, username, has_failures, ssl: {...}, acl: {...}, nginx: {...}|null}

# Filter to failures only across all three components
reveal cpanel://USERNAME/full-audit --only-failures
```

**Individual components (when you need targeted output):**
```bash
# Overview: domain count + SSL summary + nginx config path
reveal cpanel://USERNAME

# List all domains with docroots and type (addon/subdomain/main_domain/parked)
reveal cpanel://USERNAME/domains

# Disk cert health for every domain — sorted failures first
reveal cpanel://USERNAME/ssl

# Show only failing certs
reveal cpanel://USERNAME/ssl --only-failures

# Filter to main domain only (URI query param)
reveal cpanel://USERNAME/ssl?domain_type=main_domain
# domain_type values: main_domain, addon, subdomain, parked

# DNS-verified: exclude NXDOMAIN and elsewhere-pointing domains from counts
# Use when large accounts have inactive/migrated domains with expiring certs
reveal cpanel://USERNAME/ssl --dns-verified
# Summary: "1 critical  (2 nxdomain-excluded: 2 critical)  (1 elsewhere-excluded: 1 critical)"
# Table annotations: [nxdomain] = NXDOMAIN; [→ elsewhere] = resolves but to a different server
# Combine: --dns-verified --only-failures shows only failures on domains served by THIS server

# JSON output for jq pipelines
reveal cpanel://USERNAME/ssl --format=json
reveal cpanel://USERNAME/ssl --dns-verified --format=json | jq '.certs[] | select(.dns_points_here == false)'
reveal cpanel://USERNAME/ssl --format=json | jq '.certs[] | select(.status != "ok")'

# Nobody ACL check on every domain docroot — required for ACME renewal
reveal cpanel://USERNAME/acl-check
reveal cpanel://USERNAME/acl-check --only-failures  # show only denied docroots
```

**Full per-user audit workflow (when NOT using full-audit):**
```bash
# 1. Overview
reveal cpanel://USERNAME

# 2. Check nobody ACL on all docroots (required for nginx ACME renewal)
reveal cpanel://USERNAME/acl-check --only-failures

# 3. Check on-disk cert health for every SSL domain
reveal cpanel://USERNAME/ssl --only-failures

# 4. Composed audit: ACME paths + ACL + live SSL in one nginx table
reveal /etc/nginx/conf.d/users/USERNAME.conf --validate-nginx-acme --only-failures

# 5. Disk cert vs live cert comparison (detect AutoSSL renewed but nginx not reloaded)
reveal /etc/nginx/conf.d/users/USERNAME.conf --cpanel-certs

# 6. nginx ACME audit as JSON (for agents that want structured output)
reveal /etc/nginx/conf.d/users/USERNAME.conf --validate-nginx-acme --format=json
# Shape: {type: "nginx_acme_audit", has_failures, only_failures, domains: [...]}

# 7. Retroactive error log diagnosis (what has already failed)
reveal /etc/nginx/conf.d/users/USERNAME.conf --diagnose
```

**cpanel:// views:**
- `cpanel://USERNAME/full-audit` — **recommended start**: ssl + acl-check + nginx ACME; exits 2 on failure
- `cpanel://USERNAME` — overview: domain count, SSL summary, nginx config path
- `cpanel://USERNAME/domains` — all domains with docroots and type (main_domain/addon/subdomain/parked)
- `cpanel://USERNAME/ssl` — disk cert health per domain; supports `--only-failures`, `--dns-verified`, `?domain_type=`
- `cpanel://USERNAME/acl-check` — nobody ACL status on every domain docroot; supports `--only-failures`

**When to use which command:**
| Scenario | Command |
|----------|---------|
| Full health check (preferred) | `reveal cpanel://USERNAME/full-audit` |
| Full health check, machine-readable | `reveal cpanel://USERNAME/full-audit --format=json` |
| "Why is ACME renewal failing?" | `reveal /etc/nginx/conf.d/users/USERNAME.conf --validate-nginx-acme` then `--diagnose` |
| "Did AutoSSL run but nginx not reload?" | `reveal /etc/nginx/conf.d/users/USERNAME.conf --cpanel-certs` |
| "Which docroots block nobody?" | `reveal cpanel://USERNAME/acl-check --only-failures` |
| "What domains does this user have?" | `reveal cpanel://USERNAME/domains` |
| Show only cert problems | `reveal cpanel://USERNAME/ssl --only-failures` |
| "Former-customer domains inflating critical count" | `reveal cpanel://USERNAME/ssl --dns-verified` |
| "Which domains point to a different server?" | `reveal cpanel://USERNAME/ssl --dns-verified --format=json \| jq '.certs[] \| select(.dns_points_here == false)'` |
| Scope to main domain only | `reveal cpanel://USERNAME/ssl?domain_type=main_domain` |

**DNS verification details (--dns-verified):**
- `dns_resolves: false` → domain is NXDOMAIN (DNS gone); shown with `[nxdomain]` tag, excluded from summary
- `dns_points_here: false` → domain resolves but IPs don't match any local interface; shown with `[→ elsewhere]` tag, excluded from summary
- `dns_points_here: null` → domain resolves but local IPs couldn't be determined
- Both NXDOMAIN and elsewhere-pointing domains are excluded from counts — summary reflects only domains this server actually serves

**ACL check methods:**
- `reveal cpanel://USERNAME/acl-check` — filesystem walk (authoritative); finds denied docroots directly
- `reveal /etc/nginx/.../USERNAME.conf --validate-nginx-acme` — parses nginx config + checks ACME paths + live SSL; also verifies routing
- `reveal cpanel://USERNAME/full-audit` — runs both plus ssl in one pass

---

### Task: "Audit Let's Encrypt certificate inventory"

The `letsencrypt://` adapter walks `/etc/letsencrypt/live/` and reports all certbot-managed certs with expiry, SANs, and coverage gaps.

```bash
# Full cert inventory — all certs with expiry and SANs
reveal letsencrypt://

# Find certs not referenced by any nginx ssl_certificate directive (orphans)
reveal letsencrypt:// --check-orphans

# Find certs sharing identical SANs (duplicates — usually from re-issued certs)
reveal letsencrypt:// --check-duplicates

# Machine-readable output
reveal letsencrypt:// --format=json
```

**letsencrypt:// output includes:**
- Common name, SANs, expiry date, `days_until_expiry` (int) — sorted expiry-first
- `--check-orphans`: certs not referenced in nginx `sites-enabled`/`conf.d`
- `--check-duplicates`: certs with identical SAN sets (clean state shows only `✅ No duplicate-SAN certs found`)

**JSON field names** (for `--format=json | jq`): `name`, `cert_path`, `common_name`, `san` (array), `days_until_expiry` (int), `not_after` (ISO string), `is_expired` (bool), `issuer`.

**`--check-orphans` on cPanel servers:** nginx `ssl_certificate` directives point to `/var/cpanel/ssl/apache_tls/`, not `/etc/letsencrypt/`. All LE certs will appear orphaned even when active. Use `reveal cpanel://USER/ssl` instead.

**When to use vs ssl://:**
- `letsencrypt://` — inventory of managed certs on disk (no network, server-side only)
- `ssl://domain` — live TLS handshake from a client perspective (works remotely)
- `ssl://file:///etc/letsencrypt/live/.../cert.pem` — details on a specific cert file

---

### Task: "Inspect cPanel AutoSSL run logs"

The `autossl://` adapter reads `/var/cpanel/logs/autossl/` NDJSON logs — per-domain TLS renewal outcomes without WHM API access.

```bash
# List available AutoSSL run timestamps
reveal autossl://

# Parse most recent run — per-user/domain TLS summary
reveal autossl://latest

# Parse a specific run by timestamp
reveal autossl://2026-03-03T23:26:01Z

# Extract all defective domains as JSON
reveal autossl://latest --format=json | jq '[.users[].domains[] | select(.tls_status=="defective")]'

# Domain history — is this domain always failing?
reveal autossl://app.example.com          # 20 most recent runs; shows ✅ 0 ok + Failing since: date
reveal autossl://app.example.com --all    # full history (300+ runs)
```

**TLS outcome codes:**
- `ok` — cert issued/renewed successfully
- `incomplete` — DCV not completed
- `defective` — renewal failed; defect codes: `SELF_SIGNED_CERT`, `CERT_HAS_EXPIRED`, `TOTAL_DCV_FAILURE`, `NO_UNSECURED_DOMAIN_PASSED_DCV`

**Domain history output:** summary always shows `✅ N ok` even when zero (key signal for chronic failures). When ok==0, prints "Failing since: YYYY-MM-DD" at top. Default cap: 20 most recent rows; use `--all` to see full history.

**JSON field names** (for `--format=json | jq`): per-domain objects have `domain`, `tls_status` (`ok`/`incomplete`/`defective`), `cert_expiry_days` (float, negative=expired, **null for `incomplete` domains** — AutoSSL didn't process the cert), `defect_codes` (array), `impediments` (array). Top-level: `users[].domains[]`.

**Combined workflow (AutoSSL failure investigation):**
```bash
# 1. Check most recent run for failures
reveal autossl://latest | grep -i defect

# 2. Check if a problem domain is a chronic failure or new
reveal autossl://app.example.com

# 3. Confirm nginx ACME paths are routable for affected user
reveal cpanel://USERNAME/acl-check --only-failures

# 4. Validate ACME challenge routing in nginx config
reveal /etc/nginx/conf.d/users/USERNAME.conf --validate-nginx-acme
```

---

### Task: "Work with Markdown documentation"

**Pattern:**
```bash
# View document structure (headings)
reveal doc.md

# Extract a specific section by heading name (case-insensitive, substring OK)
reveal doc.md "Installation"
reveal doc.md "install"          # substring match → "## Installation"
reveal doc.md --section "Installation"   # flag form (same behavior, useful in scripts)

# OR-alternation: extract multiple named sections in one call
reveal doc.md "Open Issues|Action Items"
reveal doc.md "Bug 11\|social_repost_log\|Action Items"   # grep-style \| also works
reveal doc.md "Breaking Changes|Migration Guide|Upgrade"  # 3-way OR

# Extract all links
reveal doc.md --links

# Only external links
reveal doc.md --links --link-type external

# Only internal links (broken link detection)
reveal doc.md --links --link-type internal

# Only show broken links (✗ entries — skip the passing ones)
reveal doc.md --broken-only

# Extract code blocks
reveal doc.md --code

# Only Python code blocks
reveal doc.md --code --language python

# Include inline code spans (backtick snippets in text, not just fenced blocks)
reveal doc.md --code --inline

# Get YAML frontmatter
reveal doc.md --frontmatter

# Search file body text (text after frontmatter)
reveal 'markdown://docs/?body-contains=nginx'

# Combine body search with frontmatter filter and sort
reveal 'markdown://docs/?type=guide&body-contains=nginx&sort=-modified'

# Multiple body-contains terms are AND'd (all must appear)
reveal 'markdown://docs/?body-contains=auth&body-contains=token'

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

**Section matching rules** (single term or each OR term):
1. Exact match (case-insensitive) — returns that section only
2. Substring match — returns all headings containing the term, concatenated in document order
3. OR (`|`) — resolves each term independently; deduplicates; returns all in document order

**OR-pattern tips for agents:**
- Use `|` to fetch multiple unrelated sections in one round-trip
- Each term follows the same exact → substring priority as single-term queries
- `\|` (grep-style escape) is normalised to `|` automatically
- Spaces around `|` are trimmed: `"A | B"` == `"A|B"`
- If a term matches nothing it is silently skipped; result is `None` only when *all* terms fail

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

### Task: "Analyze Claude Code sessions (claude://)"

The `claude://` adapter provides session-level analysis of Claude Code conversations AND introspection of your Claude Code install (agents, hooks, memory, config, plans). Designed for post-session review, debugging, token optimization, and auditing your Claude setup.

**Session analysis:**
```bash
# List recent sessions (most recent first)
reveal claude://
reveal claude://sessions          # alias

# Session overview: messages, tools, duration
reveal claude://session/my-session-0302

# Chronological tool sequence
reveal claude://session/my-session-0302/workflow

# Files read/written/edited
reveal claude://session/my-session-0302/files

# Tool usage with success rates
reveal claude://session/my-session-0302/tools

# Errors with full context
reveal claude://session/my-session-0302?errors

# Thinking blocks with token estimates
reveal claude://session/my-session-0302/thinking

# Filter to specific tool
reveal 'claude://session/my-session-0302?tools=Bash'

# User messages (prompts only)
reveal claude://session/my-session-0302/user

# Assistant text responses (no thinking/tools)
reveal claude://session/my-session-0302/assistant

# Fast session recovery — last assistant turn
reveal 'claude://session/my-session-0302?last'

# Cross-session content search
reveal 'claude://sessions/?search=validate_token'

# Prompt history across all projects
reveal claude://history
reveal 'claude://history?search=validate_token'
```

**Claude install introspection:**
```bash
# Diagnostic: all data paths and env overrides
reveal claude://info

# Settings (~/.claude/settings.json)
reveal claude://settings
reveal 'claude://settings?key=model'

# Per-install config (~/.claude.json): MCP servers, flags
reveal claude://config
reveal 'claude://config?key=installMethod'

# Saved plans (~/.claude/plans/)
reveal claude://plans
reveal 'claude://plans?search=token'
reveal claude://plans/my-plan-name

# Memory files across all projects
reveal claude://memory
reveal 'claude://memory?search=feedback'
reveal claude://memory/my-project

# Agent definitions (~/.claude/agents/)
reveal claude://agents
reveal claude://agents/reveal-codereview

# Hooks (~/.claude/hooks/)
reveal claude://hooks
reveal claude://hooks/PostToolUse
```

**claude:// session views:**
- `claude://` / `claude://sessions` — listing of all sessions (sorted by recency)
- `claude://session/<name>` — overview: message counts, tools used, duration, title
- `claude://session/<name>/workflow` — numbered chronological tool sequence with descriptions
- `claude://session/<name>/files` — Read/Write/Edit operations grouped by type, with repeat counts
- `claude://session/<name>/tools` — all tools with call counts and success rates
- `claude://session/<name>/thinking` — thinking blocks with character counts and token estimates
- `claude://session/<name>/errors` — tool errors with full input/output context
- `claude://session/<name>/context` — directory and branch changes during session
- `claude://session/<name>/user` — user turns (initial prompt + tool result messages)
- `claude://session/<name>/assistant` — assistant text responses only
- `claude://session/<name>/chain` — session continuation chain (continuing_from: links)

**claude:// install views:**
- `claude://info` — diagnostic path dump (all resolved dirs, env vars)
- `claude://settings` — `~/.claude/settings.json` with `?key=` extraction
- `claude://config` — `~/.claude.json` (MCP servers, feature flags) with `?key=` extraction
- `claude://history` — prompt history; `?search=`, `?project=`, `?since=` filters
- `claude://plans[/<name>]` — list or read `~/.claude/plans/`; `?search=`
- `claude://memory[/<project>]` — memory files from `~/.claude/projects/*/memory/`; `?search=`
- `claude://agents[/<name>]` — list or read `~/.claude/agents/`
- `claude://hooks[/<event>]` — list hook events or read a specific script

**When to use which view:**

| Scenario | Command |
|----------|---------|
| "What did this session do?" | `reveal claude://session/<name>` |
| "What order did things happen?" | `.../workflow` |
| "Which files were changed?" | `.../files` |
| "Why did a tool keep failing?" | `?errors` |
| "How many tokens did thinking use?" | `.../thinking` |
| "What was the original prompt?" | `.../user` |
| "What did Claude output?" | `.../assistant` |
| "Where did the session stop?" | `?last` |
| "Find sessions about X" | `claude://sessions/?search=X` |
| "What MCP servers are configured?" | `claude://config` |
| "What memory does this project have?" | `claude://memory/<project>` |

**Progressive analysis workflow:**
```bash
# 1. Start with overview (cheapest)
reveal claude://session/my-session-0302

# 2. Check for errors if something went wrong
reveal 'claude://session/my-session-0302?errors'

# 3. See the workflow if the sequence matters
reveal claude://session/my-session-0302/workflow

# 4. Drill into files if you need to know what was touched
reveal claude://session/my-session-0302/files
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

# Suppress breadcrumb hints (clean output for scripts / agents)
reveal file.py -q                    # -q / --no-breadcrumbs
```

**Token budget flags (URI adapters — limits list fields like items/results/checks/commits):**
```bash
# Stop after N results (text and JSON both respect this)
reveal 'ast://./src?complexity>5' --max-items 20

# Truncate long string values to N chars (useful for calls:// call lists, git messages, etc.)
reveal 'calls://./src' --max-snippet-chars 80

# Combine: first 50 items, strings max 80 chars
reveal 'calls://./src' --max-items 50 --max-snippet-chars 80
```
When truncated, reveal adds a `meta.budget` field to the JSON output with cursor for pagination. Note: the header/count line in text output may show the pre-budget total; the actual listed results are limited.

### JSON Format Details

**Standard JSON output (v0.40.0+):**
```json
{
  "file": "src/main.py",
  "type": "python",
  "analyzer": {
    "type": "explicit",
    "name": "PythonAnalyzer"
  },
  "meta": {
    "extractable": {
      "types": ["function", "class"],
      "elements": {
        "function": ["load_config", "process_data", "main"],
        "class": ["Config", "DataProcessor"]
      },
      "examples": ["reveal src/main.py load_config"]
    }
  },
  "structure": {
    "imports": [{"line": 1, "name": "os"}, {"line": 2, "name": "sys"}],
    "functions": [
      {
        "name": "load_config",
        "line": 45,
        "line_end": 56,
        "line_count": 12,
        "depth": 1,
        "complexity": 3
      }
    ],
    "classes": []
  }
}
```

**Key fields for agents:**
- `meta.extractable.types` - What element types can be extracted (function, class, section, etc.)
- `meta.extractable.elements` - Map of type → list of extractable names
- `meta.extractable.examples` - Ready-to-use extraction commands

**Using meta.extractable:**
```bash
# Discover what's extractable
reveal app.py --format=json | jq '.meta.extractable'

# Get list of functions
reveal app.py --format=json | jq '.meta.extractable.elements.function'

# Get example command
reveal app.py --format=json | jq -r '.meta.extractable.examples[0]'
```
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

### Pattern 0: Extract-then-Batch Pipeline

**Goal:** Use structured extraction to feed a batch check — no grep/awk needed

```bash
# Extract domains from nginx config, then SSL-check all of them
reveal /etc/nginx/conf.d/app.conf --extract domains | \
  sed 's/^/ssl:\/\//' | reveal --stdin --check

# Show only failures (fast triage for large configs)
reveal /etc/nginx/sites-enabled/ --extract domains | \
  sed 's/^/ssl:\/\//' | reveal --stdin --check --only-failures

# cPanel: check disk SSL for one user, live-probe each non-ok cert
reveal cpanel://USERNAME/ssl --only-failures --check-live

# Pattern detection with minimum severity filter
reveal src/ --check --severity high
```

### Pattern 1: Finding All High-Complexity Functions

**Goal:** Identify refactoring targets across entire codebase

```bash
# Method 1: AST query (fastest)
reveal 'ast://./src?complexity>10'

# Method 2: Pipeline with jq (more control)
find src/ -name "*.py" | reveal --stdin --format=json | \
  jq -r '.structure.functions[] |
         select(.complexity > 10) |
         "\(.file):\(.line) - \(.name) (complexity: \(.complexity))"' | \
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

### Programming Languages (20+)
Python, JavaScript, TypeScript, Rust, Go, Java, C, C++, C#, Scala, Swift, Kotlin, Dart, Elixir, Zig, GDScript, Bash, PowerShell, SQL, PHP, Ruby, Lua

**Structure provided:** Functions, classes, methods, imports, decorators, complexity

**Bash/Shell scripts (`.sh`, `.bash`):** Also extracts top-level variable assignments (config vars, paths, defaults). Only top-level vars — assignments inside functions, loops, and `if` blocks are excluded. Example:
```
File: platform-loop.sh (134 lines)

Variables (7):
  :22     PHP = /usr/local/bin/php
  :25     SERVICE = platform-worker
  :28     FB_LOCK_SHARDS = ${FB_LOCK_SHARDS:-5}
```

### Configuration & Data Formats (15+)
Nginx, Dockerfile, TOML, YAML, JSON, JSONL, CSV, XML, INI, HCL (Terraform), GraphQL, Protocol Buffers, Batch scripts

**Validation:** Format-specific rules (N-series for Nginx, S701 for Docker)

### Document Formats
Markdown, Jupyter notebooks (.ipynb)

**Features:** Link extraction, code block extraction, frontmatter parsing

### Office Documents
Excel (.xlsx), Word (.docx), PowerPoint (.pptx)

**Features:** Structure view, metadata, content extraction, cross-sheet search

**xlsx:// cross-sheet search:**
```bash
# Search all sheets in a workbook (case-insensitive)
reveal 'xlsx://file.xlsx?search=pattern'

# Cap results
reveal 'xlsx://file.xlsx?search=error&limit=20'

# JSON output for scripting
reveal 'xlsx://file.xlsx?search=pattern' --format=json
```

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
# B003: @property 'options' is 18 lines (max 15) (line 52)
#   @property
#   def options(self): ...  # ❌ Too complex for a property
```

**Result:** Found overly complex @property causing hard-to-trace side effects.

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
# C901: High cyclomatic complexity (complexity: 15)
# B001: Bare except clause catches all exceptions
# C902: Function too long (78 lines)
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
# B003: @property too complex (>15 lines)
# B006: Broad exception handler with silent pass
# C901: High cyclomatic complexity

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

**Problem:** You're using the old `--hotspots` flag form instead of the `reveal hotspots` subcommand.

**Old (still works, but deprecated):**
```bash
reveal stats://. --hotspots
reveal stats://.?hotspots=true
```

**Correct — use the subcommand:**
```bash
reveal hotspots .                  # Hotspots in current directory
reveal hotspots ./src              # Hotspots in src/
reveal hotspots . --top 20         # Show top 20 instead of default 10
reveal hotspots . --functions-only # Only complex functions, skip file-level
reveal hotspots . --format json    # JSON output for CI/scripting
```

**`reveal hotspots --help`** — full options including `--min-complexity`, `--files-only`.

---

### Issue: "No structure found"

**Symptoms:**
```
File: script.sh (134 lines)
No structure available for this file type (134 lines)
```

The message now includes line count — use it to decide whether `Read` is worth the tokens.

**Automatic fallbacks (no action needed):**
- **≤50 lines with no structure** — reveal renders the full file inline with line numbers. No `Read` needed.
- **Bash/shell scripts** — top-level variable assignments are extracted even if there are no functions. Flat worker scripts show their config vars automatically.

**Causes & Solutions for genuine "no structure":**

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
# Error: Element 'missing_function' not found in app.py
# Available: validate_token, refresh_token, create_session, ... (and 3 more)
```

**v0.67.0+:** The error message itself lists available names — use one directly and skip the full-file roundtrip.

**Causes & Solutions:**

1. **Typo in element name** — check the `Available:` line in the error, or:
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
   # Global limit: stop after 100 total entries
   reveal huge_dir/ --max-entries 100

   # Per-directory limit: 50 per dir, then snip (default)
   reveal project/ --dir-limit 50

   # Unlimited per-directory (but global limit still applies)
   reveal project/ --dir-limit 0
   ```

   **When to use which:**
   - `--max-entries` - Hard cap on total output (token budget)
   - `--dir-limit` - Control per-directory verbosity (stops node_modules from consuming budget)

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

### Issue: "Exit code 2 is breaking my pipeline / parallel tool calls"

**Exit code contract:**
- `0` — pass (no findings, or informational output only)
- `1` — warnings (expiring certs, non-critical issues)
- `2` — failures found (expired certs, rule violations, ACL failures)

Exit code 2 means **reveal found something** — it is not a tool crash. The output is still valid and useful; the exit code is the machine-readable summary.

**The right fix is `|| true` at the call site:**
```bash
# In a shell pipeline — don't stop on findings
reveal ssl://example.com --check || true

# In a script that should continue regardless
reveal /etc/nginx/conf.d/users/myuser.conf --validate-nginx-acme --only-failures || true

# In a Makefile
check-ssl:
    reveal ssl://example.com --check || true
```

**Why there is no `--no-fail` / `--exit-zero` flag:**
`|| true` is the idiomatic Unix pattern for "run this but don't stop on non-zero exit." Adding `--no-fail` would push caller concerns into the tool, conflate "checking" with "what to do about findings," and need to be added to every checking command. Most Unix tools (`grep`, `diff`, `test`) follow the same convention.

**For AI agents running parallel tool calls:**
If your agent framework treats any non-zero exit as a tool failure, use `|| true`. The output (text or JSON) is produced regardless of exit code — the exit code is purely a machine-readable summary of the result.

```bash
# These both produce output — exit code just summarizes the result
reveal ssl://example.com --check           # exits 2 if expired
reveal ssl://example.com --check || true   # always exits 0; output identical
```

---

## Complete Rules Reference

### Bug Detection (B)

**B001: Bare except clause catches all exceptions**
```python
# ❌ Bad
try:
    risky_operation()
except:  # Catches everything, even KeyboardInterrupt and SystemExit
    pass

# ✅ Good
try:
    risky_operation()
except ValueError:
    pass
```

**B002: @staticmethod should not have 'self' parameter**
```python
# ❌ Bad - 'self' is meaningless on a staticmethod
class MyClass:
    @staticmethod
    def helper(self, value):
        return value * 2

# ✅ Good
class MyClass:
    @staticmethod
    def helper(value):
        return value * 2
```

**B003: @property with complex body**
Properties should be simple getters. Threshold: 15 lines (configurable via `.reveal.yaml`).
```python
# ❌ Bad - 20-line property with logic
@property
def headers(self):
    result = {}
    if self._override:
        result = self._override.copy()
    for k, v in self._base.items():
        if k not in result:
            result[k] = v
    # ... more logic ...
    return result

# ✅ Good - simple getter
@property
def headers(self) -> dict:
    return self._headers  # trivial accessor

# ✅ Also good - logic moved to a regular method
def get_headers(self) -> dict:
    # complex logic lives here instead
    ...
```

**B004: @property has no return statement**
```python
# ❌ Bad - property that never returns a value
class MyClass:
    @property
    def value(self):
        self._compute()  # forgot to return!

# ✅ Good
class MyClass:
    @property
    def value(self):
        return self._value
```

**B005: Import references non-existent or unresolvable module**
```python
# ❌ Bad
from nonexistent_module import SomeClass  # B005 - module not found
import typo_in_name                       # B005 - module not found

# ✅ Good
from actual_module import SomeClass
```

**B006: Broad exception handler with silent pass**
```python
# ❌ Bad - swallows all errors silently
try:
    process_data()
except Exception:
    pass  # B006 - bugs hide here

# ✅ Good - at minimum, log it
try:
    process_data()
except Exception as e:
    logger.warning("process_data failed: %s", e)
```

---

### Security Issues (S)

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

**C901: High cyclomatic complexity**
- Complexity > 10 suggests function is too complex
- Consider breaking into smaller functions
- Use `reveal --explain C901` for thresholds

**C902: Function too long**
- Function exceeds maximum line count
- Consider breaking into smaller, focused functions

**C905: Nesting depth too high**
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

> **Note**: Too-many-arguments is rule **R913**, not a C rule.

---

### Error Handling (E)

**E501: Line too long**
- Line exceeds maximum length (default: 88 characters, configurable via `.reveal.yaml`)
- Applies to all file types (`*`)
- Use `reveal --explain E501` for the threshold and configuration options

---

### Duplicates (D)

**D001: Exact duplicate code (hash-based)**
- Identical code blocks (hash match)
- High confidence - should be deduplicated

**D002: Similar code (structural similarity)**
- Similar but not identical code
- **Disabled by default** (high false positive rate) — enable explicitly with `--select D002`
- Use D001 for reliable duplicate detection

---

### Imports (I)

**I001: Unused import**
- Import is never referenced in the file
- Applies to Python, JS/TS, Rust, Go (multi-language)

**I002: Circular dependency**
- Module A imports B which imports A (directly or transitively)
- Can cause `ImportError` or subtle initialization bugs

**I003: Architectural layer violation**
- Import crosses a forbidden layer boundary (e.g., data layer importing presentation)
- Requires layer configuration in `.reveal.yaml`

**I004: Local file shadows standard library module**
```python
# ❌ Bad - local json.py shadows stdlib json
import json  # Which one? stdlib or local json.py?
```

**I005: Duplicate import statement**
```python
# ❌ Bad
from module import Class  # first import
from other import Thing
from module import Class  # I005 - duplicate
```
- Detects duplicate top-level imports across languages

**I006: Import inside function body** *(Python only)*
```python
# ❌ Bad - import belongs at module top
def process():
    import json  # I006
    return json.dumps({})

# OK - intentional lazy load (name contains 'lazy' or 'import')
def _lazy_import_heavy():
    from .heavy_module import Widget  # skipped
    return Widget()
```
- Suppressed by `# noqa: I006` or `# noqa` on the import line
- Suppressed when function name contains `lazy` or `import`
- Suppressed for `TYPE_CHECKING` guards

---

### Links (L)

*Applies to `.md` / `.markdown` files only.*

**L001: Broken internal link**
- A `[text](path)` link points to a file or anchor that doesn't exist on disk
- Absolute paths checked relative to repo root; relative paths resolved from the source file
- Suppressed on lines matching `<!-- noqa -->` or inside fenced code blocks

**L002: Broken external link** *(opt-in — disabled by default)*
- An `http://` or `https://` URL returns a non-2xx response
- **Disabled by default** — network I/O is slow and flaky in CI. Enable via `.reveal.yaml`:
  ```yaml
  rules:
    select: [L002]
  ```
- Timeout: 5 seconds per request

**L003: Framework routing mismatch**
- A Markdown link uses a path that exists on disk but doesn't match the web framework's routing rules (e.g., a Next.js `pages/` route vs. a `/app/` link)
- Requires framework configuration in `.reveal.yaml` to be meaningful

**L004: Documentation directory missing index**
- A `docs/` subdirectory has no `index.md` or `README.md`
- Severity: LOW — useful for large doc trees

**L005: Low cross-reference density**
- A Markdown file has fewer than 2 outgoing links to other docs
- Signals isolated documentation that hasn't been linked into the broader knowledge graph
- Threshold configurable via `.reveal.yaml` `rules.L005.min_cross_refs`

---

### Maintainability (M)

**M101: File is too large**
- MEDIUM: >500 lines (getting large)
- HIGH: >1000 lines (should be split)
- Applies to all file types
- Suggestion includes estimated LLM token cost to load the file

**M102: Orphaned module** *(Python only)*
- A `.py` file is never imported anywhere in the package
- Skips entry points (`main.py`, `__init__.py`, `cli.py`), test files, and scripts

**M103: Version mismatch** *(Python projects)*
- `pyproject.toml` version doesn't match `__version__` in the package's `__init__.py`
- Catches the common mistake of bumping one but not the other during release prep

**M104: Hardcoded list** *(Python only)*
- A module-level list assignment contains 5+ string/number literals
- Flags lists that are likely to become stale (e.g., `SUPPORTED_FORMATS = ["png", "jpg", ...]`)
- Suggestion: derive from a registry, config file, or enum

**M105: CLI handler not wired** *(Python only)*
- A `handle_*` function exists in a handler module but isn't referenced in `main.py`
- Catches handler functions that were written but never connected to the CLI dispatcher

**M501: Unresolved comment marker**
- Detects `# TODO`, `# FIXME`, `# HACK`, `# XXX` in any file type (case-insensitive)
- Severity: LOW — one detection per matching line
- Skips `reveal/templates/` and `reveal/adapters/demo.py` (intentional scaffolds)
- Suppression via `.reveal.yaml`:
  ```yaml
  rules:
    M501:
      ignore_patterns: ["remove in v", "intentional"]
  ```

---

### Frontmatter (F)

*Applies to `.md` / `.markdown` files only.*

**F001: Missing front matter**
- File has no YAML front matter block (`---` … `---`)
- Only fires when a front matter schema is configured in `.reveal.yaml`

**F002: Empty front matter**
- File has a front matter block (`---\n---`) with no fields inside

**F003: Required field missing**
- A field listed in `.reveal.yaml` `frontmatter.required_fields` is absent from the document's front matter

**F004: Field type mismatch**
- A front matter field is present but has the wrong type (e.g., `date:` is a string instead of a date)

**F005: Custom validation failed**
- A custom validator defined in `.reveal.yaml` rejected the field value

---

### Type Annotations (T)

*Python only.*

**T004: Implicit Optional (PEP 484 violation)**
```python
# ❌ Bad — parameter has a None default but no Optional[] in the type hint
def process(data: str = None): ...

# ✅ Good — explicit Optional makes the intent clear
from typing import Optional
def process(data: Optional[str] = None): ...
```
- PEP 484 requires `Optional[X]` when a parameter can be `None`
- Modern alternative: `str | None` (Python 3.10+)

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

**N004: ACME challenge path inconsistency**
```nginx
# ❌ Bad - inconsistent paths cause Let's Encrypt renewal failures
server {
    server_name a.com;
    location /.well-known/acme-challenge/ { root /var/www/a; }
}
server {
    server_name b.com;
    location /.well-known/acme-challenge/ { root /var/www/b; }  # Different path!
}

# ✅ Good - consistent paths across all servers
server {
    server_name a.com;
    location /.well-known/acme-challenge/ { root /var/www/letsencrypt; }
}
server {
    server_name b.com;
    location /.well-known/acme-challenge/ { root /var/www/letsencrypt; }
}
```

**N005: Timeout/buffer values outside safe operational ranges**
```nginx
# ❌ Bad - values that cause silent failures or resource exhaustion
http {
    send_timeout 3s;           # N005 – below minimum of 10s
    proxy_read_timeout 600s;   # N005 – above maximum of 300s
    client_body_buffer_size 512m;  # N005 – above maximum of 64m
}

# ✅ Good
http {
    send_timeout 30s;
    proxy_read_timeout 60s;
    client_body_buffer_size 16m;
}
```

**N006: send_timeout too short for client_max_body_size** *(HIGH severity)*
```nginx
# ❌ Bad - large uploads will be silently killed mid-transfer
http {
    send_timeout 30s;          # N006 – too short for 200m body size
    client_max_body_size 200m;
}
# Real-world incident: Feb 2026 - media uploads silently dropped due to timeout mismatch

# ✅ Good
http {
    send_timeout 300s;
    client_max_body_size 200m;
}
```
*Fires when any of `send_timeout`, `proxy_read_timeout`, `proxy_send_timeout` is < 60s
and `client_max_body_size` exceeds 10m.*

**N007: ssl_stapling enabled but no OCSP responder URL** *(INFO)*
```nginx
# ❌ Ineffective - self-signed/internal CA cert has no OCSP URL
ssl_stapling on;
ssl_certificate /etc/nginx/ssl/internal.crt;  # no AIA OCSP entry
# nginx silently skips stapling — no error logged
```
*Typically affects self-signed or internal CA certs. Let's Encrypt certs are unaffected.*

---

### Validation (V)

**V001-V006:** Internal validation rules for reveal's own codebase
- Used by `reveal reveal://` self-inspection
- Ensure adapter completeness, documentation, testing

---

### Refactoring Opportunities (R)

**R913: Too many arguments**
- Function has too many parameters — consider a config object or dataclass
- Use `reveal --explain R913` for the threshold

---

### URL Issues (U)

**U501: GitHub URL uses insecure http:// protocol**
- Use `https://` for all GitHub URLs

**U502: URL doesn't match canonical project URL**
- URL references a non-canonical host or path for this project

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
| Function skeleton | `reveal file.py func_name --outline` |
| Scope at a line | `reveal file.py :123 --scope` |
| Lines around a line | `reveal file.py :123 --around` |
| Trace a variable | `reveal file.py func_name --varflow result` |
| Trace var in flat file | `reveal file.php :1-2000 --varflow errormsg` |
| Trace var across calls | `reveal file.py func_name --varflow result --cross-calls` |
| Type-narrowing path | `reveal file.py func_name --narrow response` |
| Calls in a range | `reveal file.py func_name --calls 89-120` |
| Calls in flat file range | `reveal file.php :477-531 --calls` |
| Branching skeleton | `reveal file.py func_name --ifmap` |
| Exception skeleton | `reveal file.py func_name --catchmap` |
| Exit nodes in range | `reveal file.php :657-2200 --exits` |
| Reachability verdict | `reveal file.php :2928-3663 --flowto` |
| Refactor deps | `reveal file.php :1136-1463 --deps` |
| Refactor mutations | `reveal file.php :1136-1463 --mutations` |
| Extract by name | `reveal file.py func_name` |
| Extract class method | `reveal file.py Class.method` |
| Extract at line | `reveal file.py 73` or `reveal file.py :73` |
| Extract Nth element | `reveal file.py @3` |
| Extract 2nd function | `reveal file.py function:2` |
| Quality check | `reveal file.py --check` |
| Security check only | `reveal file.py --check --select S` |
| Find hotspots | `reveal hotspots .` |
| Find by name | `reveal 'ast://./src?name=*pattern*'` |
| Find complex code | `reveal 'ast://./src?complexity>10'` |
| Find long functions | `reveal 'ast://./src?lines>50'` |
| Unannotated functions | `reveal 'ast://./src?has_annotations=false'` |
| Heavily-called functions | `reveal 'ast://./src?callers>5'` |
| Type evidence for var | `reveal 'ast://file.py?reveal_type=result'` |
| Debug Python env | `reveal python://` |
| Check stale bytecode | `reveal python://debug/bytecode` |
| Navigate JSON | `reveal json://file.json/path/to/key` |
| JSONL records | `reveal file.jsonl --head 10` |
| Check changes | `git diff --name-only \| reveal --stdin --check` |
| Check SSL cert | `reveal ssl://example.com` |
| SSL health check | `reveal ssl://example.com --check` |
| Batch SSL from file | `reveal @domains.txt --check` |
| On-disk cert inspection | `reveal ssl://file:///path/to/cert.pem` |
| Nginx SSL domains | `reveal nginx.conf --extract domains` |
| Nginx SSL check | `... --extract domains \| reveal --stdin --check` |
| SSL failures only | `--check --only-failures` |
| SSL expiring soon | `--check --expiring-within=30` |
| Nginx config check | `reveal nginx.conf --check --select N` |
| Nginx nobody ACL check | `reveal /path/user.conf --check-acl` |
| Nginx ACME roots table | `reveal /path/user.conf --extract acme-roots` |
| Nginx location conflicts | `reveal /path/user.conf --check-conflicts` |
| Filter to one server block | `reveal /path/user.conf --server-name example.com` |
| Full ACME+ACL+SSL audit | `reveal /path/user.conf --validate-nginx-acme` |
| ACME audit, failures only | `reveal /path/user.conf --validate-nginx-acme --only-failures` |
| Disk vs live cert compare | `reveal /path/user.conf --cpanel-certs` |
| Error log ACME diagnosis | `reveal /path/user.conf --diagnose` |
| cPanel user overview | `reveal cpanel://USERNAME` |
| cPanel SSL health | `reveal cpanel://USERNAME/ssl` |
| cPanel ACL check | `reveal cpanel://USERNAME/acl-check` |
| Get JSON output | `reveal file.py --format=json` |
| Copy to clipboard | `reveal file.py --copy` |
| Extract links | `reveal doc.md --links` |
| Broken links only | `reveal doc.md --broken-only` |
| Extract code blocks | `reveal doc.md --code` |
| Include inline snippets | `reveal doc.md --code --inline` |
| First/last N functions | `reveal file.py --head 5` / `--tail 5` |
| List all rules | `reveal --rules` |
| Explain rule | `reveal --explain B001` |
| Check file type | `reveal file.py --meta` |
| Suppress breadcrumbs | `reveal file.py -q` |
| Budget: first N items | `reveal uri:// --max-items 50` |

---

## Help System Overview

**For AI agents (you):**
- **Complete guide** (`reveal --agent-help` or `reveal --agent-help-full`) - This file (~12,000 tokens)
- **Progressive help** (`reveal help://topic`) - Low-token per-topic exploration

**For humans:**
- **CLI reference** (`reveal --help`) - All flags and options
- **Progressive help** (`reveal help://`) - Explorable documentation
  - `reveal help://ast` - AST adapter details
  - `reveal help://python-guide` - Python adapter deep dive
  - `reveal help://tricks` - Cool tricks and hidden features

**You don't need to explore help://** - this guide has everything you need. The examples above cover 95% of use cases.

---

**Last updated:** 2026-03-15
**Source:** https://github.com/Semantic-Infrastructure-Lab/reveal
**PyPI:** https://pypi.org/project/reveal-cli/

---

## When to Use grep/find (Rare Cases)

**Use grep when:**
- Searching for exact text strings in logs
- Looking for specific error messages
- Searching non-code files (binaries, data files)

**Use find when:**
- Finding files by modification time
- Complex file permission searches
- Piping to non-reveal tools (xargs, etc.)

**Use cat when:**
- You genuinely need the entire file (rare!)
- Binary file inspection (with `cat -v`)
- Concatenating multiple files

---

## Decision Tree

```
Need to inspect code?
├─ Unknown file? → reveal file.py
├─ Know function name? → reveal file.py "function_name"
├─ Find by pattern? → reveal 'ast://path?name=pattern*'
├─ Find complex code? → reveal 'ast://path?complexity>8'
├─ Check quality? → reveal file.py --check
└─ Read everything? → (Are you sure? Try reveal first!)

Need to search text?
├─ In code (functions/classes)? → reveal 'ast://?name=*pattern*'
├─ In markdown (sections)? → reveal file.md "section name"
├─ Across multiple files? → reveal 'ast://path?name=*pattern*'
└─ Non-code text/logs? → Use grep (OK!)
```

---

## Common Mistakes

### Mistake 1: Reading files too early
```bash
❌ cat file.py                 # 7,500 tokens
✅ reveal file.py              # 100 tokens, shows structure
✅ reveal file.py "func"       # 50 tokens, extract what you need
```

### Mistake 2: Using grep for structured data
```bash
❌ grep -n "class" *.py        # Text matching, false positives
✅ reveal 'ast://.?type=class' # Semantic search, accurate
```

### Mistake 3: Not using wildcards
```bash
❌ grep -r "test_login\|test_logout\|test_signup"
✅ reveal 'ast://tests/?name=test_*'
```

### Mistake 4: Ignoring breadcrumbs
After running `reveal file.py`, reveal shows: "Next: reveal file.py <function_name>"
Use that guidance - it tells you exactly what to do next!

---

## What Changed in This Guide

This is the redesigned complete AI agent reference (Dec 2025). Changes:

- **Task-oriented** - "When you need to do X, use Y" structure
- **Example-heavy** - Concrete commands that actually work
- **Real-world scenarios** - Actual situations you'll encounter
- **Complete coverage** - All adapters, all rules, all features
- **v0.73.0** - `depends://` adapter (23rd adapter) — inverse module dependency graph; `depends://file.py` shows who imports it, `depends://dir/?top=N` ranks most-imported modules, `?format=dot` for GraphViz; scans from project root for full cross-directory visibility. `stats://` quality score now incorporates check rule detections by severity (CRITICAL=10 pts, HIGH=5 pts, MEDIUM=2 pts, LOW=0.5 pts, cap -40); `quality.check_issues` count exposed in per-file output. PHP fixes: anonymous class detection (`anonymous_class` node type), function call tracking (`function_call_expression`), `stats://` complexity no longer stuck at 1.00
- **v0.84.0** - `reveal pack --architecture` (fan-in boost + architecture brief); `--varflow --cross-calls` (follow variable across function boundaries); `--narrow VAR` (type-narrowing path); `ast://` new filters: `param_type=`, `return_type=`, `has_decorator=`, `has_annotations=`, `callers>N`, `reveal_type=`, `show=dict-heatmap`, `depth>N`, `callers>N`; `imports://?circular&verbose` (cycle edge paths); T005 (annotation coverage), T006 (TypedDict suggestion) rules; `--writes` alias for `--mutations`; `reveal/types.py` Output Contract TypedDicts; `_NAV_DISPATCH` dispatch table refactor; `VarFlowWalker` dataclass.
- **v0.87.0** - Plugin auto-discovery: drop a `*_analyzer.py` with a `@register`-decorated `FileAnalyzer` subclass into `.reveal/analyzers/` (project-local) or `~/.reveal/plugins/` (user-global) — it loads automatically on the next `reveal` run. Zero registration boilerplate.
- **v0.86.0** - `reveal trace` subcommand: depth-indented execution narrative from a named entry point. Combines `calls://` recursive callees walk with per-function params and classified side-effects (hard_stop, db, http, cache, file, log, sleep). `--depth N` (1–5, default 2), `--json` output. Prunes builtins and external callees by default.
- **v0.85.0** - 5 new features: `reveal hotspots` test-coverage heuristic (✅/⚪ per function, scans `tests/`/`test/`/`spec/`); `calls://?root=fn&depth=N` recursive callees walk (BFS, cap 5, resolved vs external); `reveal contracts src/` (ABCs, Protocols, TypedDicts, @dataclass, Pydantic BaseModels, `--abstract-only`); `reveal surface src/` (CLI args, HTTP routes, MCP tools, env vars, network/DB/SDK imports, filesystem writes, `--type` filter); `calls://?modules=true` module dependency graph (191 nodes / 248 edges on reveal's own codebase, `?external=true`, dot format).
- **v0.79.0** - documented PHP limitation: `--varflow`, `--deps`, `--mutations` silently return empty on PHP files (BACK-203 — `variable_name` node type vs `identifier`); PHP-safe nav flags: `--calls`, `--exits`, `--flowto`, `--ifmap`, `--catchmap`, `--around`, `--scope`; added `--calls` / `calls://` disambiguation; clarified `--outline` dual-mode behavior
- **v0.78.0** - probe-inspired nav flags: `--around N` (verbatim context ±N lines around a target), `--ifmap` (branching skeleton), `--catchmap` (exception skeleton), `--exits` (exit-node list), `--flowto` (exit list + CLEAR/CONDITIONAL/BLOCKED verdict), `--deps` (refactoring pre-flight: variables flowing in), `--mutations` (variables written in range and read after); flat-file support for `--varflow` and `--calls` (no named function required — use with `:LINE-RANGE` syntax or no element for whole-file)
- **v0.72.1** - M501 rule (TODO/FIXME/HACK/XXX marker detection, LOW severity, all file types); `--max-bytes` and `--max-depth` removed (were misleading/unimplemented); Complete Rules Reference now covers L, M, F, T categories (18 previously undocumented rules); adapter count corrected to 22
- **v0.72.0** - nav flags released: `--outline` (element mode → control-flow skeleton), `--scope` (ancestor scope at a line), `--varflow` (read/write trace), `--calls` (call sites in a range); `--broken-only` and `--inline` documented; `--section NAME` flag; budget flags (`--max-items`, `--max-snippet-chars`) for token management
- **v0.67.0** - B005 skip `try/except ImportError` optional-dep pattern; element-not-found lists available names; `--analyzer text` false suggestion removed; M102 suppress patterns + dynamic-load heuristics in agent-help; OR-pattern failure hints `--search`
- **v0.64.0** - `reveal overview` + `reveal deps` subcommands; `reveal-mcp` MCP server (5 tools); `pack --content` tiered emission; `xlsx://` Power Pivot extraction (`?powerpivot=tables/schema/measures/dax/relationships`); `calls://?uncalled` dead code candidates; `diff://` per-function complexity delta; `claude://sessions/?search=`; Output contract compliance tests; ARCHITECTURE.md; `--discover` flag
- **v0.63.0** - `calls://` complete: `?callees=`, `?rank=callers`, `?builtins=` filtering; I005 + I006 import rules; `reveal hotspots` subcommand; B006 false-positive fixes; cpanel `full-audit`, `?domain_type=`
- **v0.61.0** - markdown cross-file link graph; claude:// cross-session file tracking + content search; json:// `?flatten` fix; domain:// task section; cpanel `--only-failures` for acl-check; I001 `__init__.py` re-export fix; B006 multi-attempt fallback fix; M102 dynamic dispatch fix
- **v0.60.0** - `nginx://` URI adapter (21st adapter); nginx vhost inspection by domain name; nginx bug fixes (glob + nesting); N007 rule
- **v0.59.0** - `--help` argument groups (12 named sections, no more flag wall); 20 adapters support `help://schemas/`; CLI flag taxonomy documented
- **v0.58.0** - `autossl://` adapter (20th URI adapter); cPanel AutoSSL run log inspection
- **v0.57.0** - `reveal dev/review/health/pack` subcommands; error-with-hint guards; claude:// workflow filtering, /messages route, truncation fix
- **v0.56.0** - `reveal check` subcommand; parser foundation with shared global opts
- **v0.55.0** - `--files`, `--ext`, `--sort`/`--desc`/`--asc`, `--meta` on directories
- **v0.54.7** - Added claude:// task section (session analysis, workflow, files, thinking, errors)
- **Pipeline workflows** - Advanced composition patterns
- **Troubleshooting** - Common issues and solutions
- **Performance data** - Benchmarks and optimization tips

The old version organized by "Use Cases" and "Workflows" - this version organizes by tasks with progressive complexity.

---

## See Also

- [RECIPES.md](guides/RECIPES.md) - Task-based workflows and patterns
- [CONFIGURATION_GUIDE.md](guides/CONFIGURATION_GUIDE.md) - Configuration options
- [RECIPES.md](guides/RECIPES.md) - Complete review workflows and patterns
- [README.md](README.md) - Documentation hub
