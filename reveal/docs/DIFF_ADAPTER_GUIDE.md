# Diff Adapter Guide (diff://)

**Last Updated**: 2026-02-14
**Version**: 1.0
**Adapter Version**: reveal 0.1.0+

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Core Features](#core-features)
4. [URI Syntax](#uri-syntax)
5. [Comparison Types](#comparison-types)
6. [Git Integration](#git-integration)
7. [Element-Specific Diffs](#element-specific-diffs)
8. [Directory Comparison](#directory-comparison)
9. [Output Format](#output-format)
10. [Detailed Workflows](#detailed-workflows)
11. [Performance Considerations](#performance-considerations)
12. [Limitations](#limitations)
13. [Error Messages](#error-messages)
14. [Tips & Best Practices](#tips--best-practices)
15. [Integration Examples](#integration-examples)
16. [Related Documentation](#related-documentation)
17. [FAQ](#faq)

---

## Overview

The **diff://** adapter provides semantic structural comparison between two reveal-compatible resources. Unlike traditional line-level diff tools (like `diff` or `git diff`), it compares structure and semantics, making it ideal for understanding functional changes, schema drift, and configuration differences.

**Primary Use Cases**:
- Pre-commit validation (check uncommitted changes)
- Code review workflow (compare branches, commits)
- Refactoring validation (verify complexity improvements)
- Schema drift detection (database changes)
- Configuration comparison (environment variables, files)
- Migration validation (ensure no functionality lost)
- Merge impact assessment (compare branches before merge)

**Key Capabilities**:
- Semantic diff (compares structure, not just text)
- File-to-file comparison
- Directory comparison (aggregates all files)
- Git integration (compare commits, branches, working tree)
- Environment variable comparison
- Database schema drift detection
- Element-specific diff (functions, classes, methods)
- Complexity delta tracking (detect complexity changes)
- Line count delta tracking

**Design Philosophy**:
- **Semantic over textual**: Understands code structure, not just text
- **Adapter-agnostic**: Works with any reveal-compatible resource
- **Progressive disclosure**: Summary first, then details
- **Two-level output**: Counts (summary) + changes (details)
- **Actionable insights**: Shows what changed functionally, not just textually

---

## Quick Start

### 1. Compare Two Files

```bash
reveal diff://app.py:backup/app.py
```

**Returns**: Structural differences (functions added/removed/modified, complexity changes)

### 2. Compare Current File to Git Version

```bash
reveal diff://git://HEAD~1/app.py:app.py
```

**Returns**: Changes since last commit (pre-commit validation)

### 3. Compare Two Git Branches

```bash
reveal diff://git://main/app.py:git://feature/app.py
```

**Returns**: Changes between branches (code review)

### 4. Compare Directories

```bash
reveal diff://src/:backup/src/
```

**Returns**: Aggregated changes across all files in both directories

### 5. Compare Specific Function

```bash
reveal diff://app.py:old.py/handle_request
```

**Returns**: Changes to specific function across versions

### 6. Compare Environment Variables

```bash
reveal diff://env://:env://production
```

**Returns**: Environment variable differences (local vs production)

### 7. Detect Database Schema Drift

```bash
reveal diff://mysql://localhost/mydb:mysql://staging/mydb
```

**Returns**: Schema differences (tables, columns, indexes)

### 8. Compare Git Branches (Full)

```bash
reveal diff://git://main/.:git://feature/.
```

**Returns**: All changes between branches (merge impact assessment)

---

## Core Features

### 1. Semantic Structural Diff

**Traditional diff** (line-level):
```diff
- def foo():
-   x = 1
-   y = 2
-   return x + y
+ def foo(): return 1 + 2
```

**Semantic diff** (structure-level):
```
function: foo
  complexity: 3 → 1 ✓ (simplified)
  lines: 4 → 1 ✓ (reduced)
  signature: unchanged
  body: modified (refactored)
```

**Why semantic matters**:
- **Focus on functional changes**: What changed semantically, not just textually
- **Ignore formatting**: Refactoring doesn't show as large diff
- **Complexity tracking**: Detect if code got more/less complex
- **Structure awareness**: Understands functions, classes, modules

---

### 2. Adapter-Agnostic Comparison

Works with any reveal-compatible resource:

| Left Resource | Right Resource | Use Case |
|---------------|----------------|----------|
| `app.py` | `backup/app.py` | File comparison |
| `src/` | `backup/src/` | Directory comparison |
| `git://HEAD~1/app.py` | `app.py` | Pre-commit validation |
| `git://main/.` | `git://feature/.` | Branch comparison |
| `env://` | `env://production` | Config comparison |
| `mysql://local/db` | `mysql://prod/db` | Schema drift |

**Pattern**: `diff://<left-resource>:<right-resource>`

---

### 3. Git Integration

Compare across git commits, branches, working tree:

**Git URI format**: `git://<ref>/<path>`

**Examples**:
```bash
# Current file vs last commit
reveal diff://git://HEAD~1/app.py:app.py

# Current file vs HEAD (uncommitted changes)
reveal diff://git://HEAD/app.py:app.py

# Branch comparison
reveal diff://git://main/app.py:git://feature/app.py

# Full directory across branches
reveal diff://git://main/.:git://develop/.

# File 3 commits ago vs current
reveal diff://git://HEAD~3/app.py:app.py
```

**Note**: Git URIs use `path@ref` format internally but are written as `git://ref/path` in diff:// adapter

---

### 4. Two-Level Output

**Level 1: Summary** (counts):
```
Summary:
  Added: 3 functions
  Removed: 1 function
  Modified: 4 functions
  Unchanged: 12 functions
```

**Level 2: Details** (changes):
```
+ function: new_feature
    lines: 0 → 15
    complexity: 0 → 3

- function: deprecated_method
    lines: 20 → 0
    complexity: 5 → 0

~ function: handle_request
    complexity: 8 → 4 ✓ (improved)
    lines: 45 → 32 ✓ (reduced)
```

**Symbols**:
- `+` = Added
- `-` = Removed
- `~` = Modified
- `✓` = Improvement (complexity/lines reduced)
- `⚠` = Concern (complexity/lines increased)

---

### 5. Element-Specific Diff

Compare individual functions, classes, or methods:

```bash
# Compare specific function
reveal diff://app.py:old.py/handle_request

# Compare specific class
reveal diff://models.py:backup/models.py/UserModel

# Compare method in class
reveal diff://api.py:old_api.py/APIHandler.process_request
```

**Use when**:
- Focus on specific functionality
- Ignore unrelated changes
- Verify refactoring didn't change behavior
- Compare specific implementation across versions

---

### 6. Complexity Delta Tracking

Detect if code got more or less complex:

**Output**:
```
function: process_data
  complexity: 12 → 6 ✓ (improved)
  lines: 85 → 45 ✓ (reduced)
```

**Interpretation**:
- **Complexity reduced**: Good (refactoring worked)
- **Complexity increased**: Review (might indicate added functionality or over-complication)
- **Lines reduced**: Often good (more concise)
- **Lines increased**: Neutral (might be documentation, error handling)

**Thresholds**:
- **Complexity >10**: High complexity, consider refactoring
- **Complexity reduced by >50%**: Significant improvement
- **Complexity increased by >50%**: Significant increase, review carefully

---

### 7. Directory Aggregation

Compare entire directories, aggregates all changes:

```bash
reveal diff://src/:backup/src/
```

**How it works**:
1. Recursively finds all analyzable files in both directories
2. Compares each matching file pair
3. Aggregates all changes into single summary
4. Shows per-file breakdown

**Skips**:
- Binary files
- Hidden files/directories (`.git`, `.env`)
- Build artifacts (`node_modules`, `__pycache__`, `target`)
- Non-analyzable files (images, videos, etc.)

**Example output**:
```
Summary:
  Files changed: 8
  Added: 12 functions, 3 classes
  Removed: 4 functions, 1 class
  Modified: 18 functions, 5 classes

Details by file:
  src/main.py: +2 -1 ~3
  src/utils.py: +1 -0 ~2
  src/models.py: +3 -2 ~4
  ...
```

---

## URI Syntax

### Basic Syntax

```
diff://<left-uri>:<right-uri>[/element]
```

**Components**:
- **left-uri**: First resource to compare
- **right-uri**: Second resource to compare
- **element** (optional): Specific element to compare (function, class, method)

---

### URI Types

#### File Paths

```bash
# Relative paths
reveal diff://app.py:backup/app.py

# Absolute paths
reveal diff:///home/user/app.py:/home/user/backup/app.py

# Mixed paths
reveal diff://./src/main.py:/opt/legacy/main.py
```

---

#### Directory Paths

```bash
# Relative directories
reveal diff://src/:backup/src/

# Absolute directories
reveal diff:///home/user/project/src/:/home/user/backup/src/

# Current directory
reveal diff://./:backup/.
```

**Note**: Trailing slashes optional but recommended for clarity

---

#### Git URIs

```bash
# Current file vs git ref
reveal diff://git://HEAD~1/app.py:app.py

# Two git refs
reveal diff://git://main/app.py:git://feature/app.py

# Full directory
reveal diff://git://HEAD/.:git://main/.

# Specific commit
reveal diff://git://abc123/file.py:file.py
```

**Git ref syntax**:
- `HEAD`: Current commit
- `HEAD~1`: 1 commit ago
- `HEAD~3`: 3 commits ago
- `main`: Branch name
- `abc123`: Commit SHA

---

#### Adapter URIs

```bash
# Environment variables
reveal diff://env://:env://production

# Database schemas
reveal diff://mysql://localhost/mydb:mysql://staging/mydb

# SQLite databases
reveal diff://sqlite://local.db:sqlite://backup.db
```

---

### Element Paths

```bash
# Function in file
reveal diff://app.py:old.py/handle_request

# Class in file
reveal diff://models.py:backup/models.py/UserModel

# Method in class
reveal diff://api.py:old_api.py/APIHandler.process_request
```

**Element path syntax**: `<file-uri>/<element-path>`

**Element path components**:
- Function name: `function_name`
- Class name: `ClassName`
- Method: `ClassName.method_name`

---

## Comparison Types

### 1. File to File

**Syntax**:
```bash
reveal diff://file1.py:file2.py
```

**Use cases**:
- Compare working file to backup
- Compare current version to previous version
- Verify manual edits didn't break structure

**Example**:
```bash
echo 'def foo(): return 42' > v1.py
echo 'def foo(): return 42\ndef bar(): return 99' > v2.py
reveal diff://v1.py:v2.py
```

**Output**:
```
Summary: +1 -0 ~0

+ function: bar
    lines: 2
    complexity: 1
```

---

### 2. Directory to Directory

**Syntax**:
```bash
reveal diff://dir1/:dir2/
```

**Use cases**:
- Compare project versions
- Verify migration completeness
- Compare production vs staging code

**Example**:
```bash
reveal diff://src/:backup/src/
```

**Output**: Aggregated changes across all files

---

### 3. Git Commit Comparison

**Syntax**:
```bash
reveal diff://git://ref1/path:git://ref2/path
```

**Use cases**:
- Code review (compare feature branch to main)
- Release validation (compare releases)
- Regression check (compare versions)

**Example**:
```bash
# Compare file across commits
reveal diff://git://HEAD~1/app.py:git://HEAD/app.py

# Compare branches
reveal diff://git://main/src/:git://feature/src/
```

---

### 4. Working Tree Validation

**Syntax**:
```bash
reveal diff://git://HEAD/path:path
```

**Use cases**:
- Pre-commit validation
- Check uncommitted changes
- Verify refactoring before commit

**Example**:
```bash
# Check uncommitted changes
reveal diff://git://HEAD/app.py:app.py

# Full project check
reveal diff://git://HEAD/.:./
```

---

### 5. Environment Comparison

**Syntax**:
```bash
reveal diff://env://[name]:env://[name]
```

**Use cases**:
- Compare local vs production config
- Validate environment setup
- Detect config drift

**Example**:
```bash
# Local vs production
reveal diff://env://:env://production

# Staging vs production
reveal diff://env://staging:env://production
```

---

### 6. Database Schema Drift

**Syntax**:
```bash
reveal diff://mysql://host1/db:mysql://host2/db
reveal diff://sqlite://db1.db:sqlite://db2.db
```

**Use cases**:
- Detect schema drift
- Validate migrations
- Compare staging vs production schemas

**Example**:
```bash
# MySQL schema drift
reveal diff://mysql://localhost/mydb:mysql://staging/mydb

# SQLite comparison
reveal diff://sqlite://local.db:sqlite://backup.db
```

---

## Git Integration

### Git URI Format

**Format**: `git://<ref>/<path>`

**Components**:
- **ref**: Git reference (HEAD, branch name, commit SHA)
- **path**: Path to file/directory within git tree

**Examples**:
```bash
git://HEAD/app.py          # app.py at HEAD
git://HEAD~1/src/          # src/ directory 1 commit ago
git://main/README.md       # README.md on main branch
git://abc123/config.yaml   # config.yaml at commit abc123
git://feature/refactor/.   # All files on feature/refactor branch
```

---

### Git Reference Types

| Reference | Example | Description |
|-----------|---------|-------------|
| **HEAD** | `git://HEAD/file.py` | Current commit |
| **HEAD~N** | `git://HEAD~3/file.py` | N commits ago |
| **Branch** | `git://main/file.py` | Branch name |
| **Tag** | `git://v1.0.0/file.py` | Tag name |
| **Commit SHA** | `git://abc123/file.py` | Specific commit |

---

### Common Git Workflows

#### Pre-Commit Validation

Check what will be committed:

```bash
# Single file
reveal diff://git://HEAD/app.py:app.py

# Full project
reveal diff://git://HEAD/.:./

# Specific directory
reveal diff://git://HEAD/src/:src/
```

**Use in pre-commit hook**:
```bash
#!/bin/bash
# .git/hooks/pre-commit

reveal diff://git://HEAD/.:. --format json | jq -e '.summary.modified < 50'
if [ $? -ne 0 ]; then
  echo "Too many files modified (>50), breaking into smaller commits"
  exit 1
fi
```

---

#### Code Review (Branch Comparison)

Compare feature branch to main:

```bash
# Full comparison
reveal diff://git://main/.:git://feature/.

# Specific file
reveal diff://git://main/app.py:git://feature/app.py

# Specific directory
reveal diff://git://main/src/:git://feature/src/
```

---

#### Release Validation

Compare releases to verify changes:

```bash
# Compare release tags
reveal diff://git://v1.0.0/.:git://v1.1.0/.

# Compare release to main
reveal diff://git://v1.0.0/src/:git://main/src/
```

---

#### Regression Check

Compare current version to older version:

```bash
# Compare to 10 commits ago
reveal diff://git://HEAD~10/.:./

# Compare to specific old commit
reveal diff://git://abc123/app.py:app.py
```

---

### Git URI Best Practices

1. **Use relative paths when possible**:
   ```bash
   # ✅ Good
   reveal diff://git://HEAD/app.py:app.py

   # ❌ Verbose
   reveal diff://git://HEAD/app.py:./app.py
   ```

2. **Compare same path across refs**:
   ```bash
   # ✅ Clear
   reveal diff://git://main/app.py:git://feature/app.py

   # ❌ Confusing (different files)
   reveal diff://git://main/app.py:git://feature/utils.py
   ```

3. **Use meaningful refs**:
   ```bash
   # ✅ Clear intent
   reveal diff://git://main/.:git://feature/.

   # ❌ Unclear
   reveal diff://git://abc123/.:git://def456/.
   ```

---

## Element-Specific Diffs

### What Are Elements?

**Elements**: Individual code units (functions, classes, methods)

**Why element-specific diffs**:
- Focus on specific functionality
- Ignore unrelated file changes
- Verify refactoring didn't change behavior
- Compare implementations across versions

---

### Element Types

| Element Type | Syntax | Example |
|--------------|--------|---------|
| **Function** | `file/function_name` | `app.py/handle_request` |
| **Class** | `file/ClassName` | `models.py/User` |
| **Method** | `file/Class.method` | `api.py/API.process` |

---

### Function Comparison

```bash
# Compare function across files
reveal diff://app.py:old.py/handle_request

# Compare function across git versions
reveal diff://git://main/app.py:git://feature/app.py/handle_request

# Compare function in working tree vs HEAD
reveal diff://git://HEAD/app.py:app.py/process_data
```

**Example output**:
```
function: handle_request

  complexity: 8 → 4 ✓ (improved)
  lines: 45 → 32 ✓ (reduced)
  parameters: (request) → (request, options) (added parameter)

  Body changes:
    - Removed nested if statements
    - Added early returns
    - Simplified error handling
```

---

### Class Comparison

```bash
# Compare class across files
reveal diff://models.py:backup/models.py/UserModel

# Compare class across git versions
reveal diff://git://HEAD~1/models.py:models.py/UserModel
```

**Example output**:
```
class: UserModel

  methods:
    + validate_email (new)
    ~ save (modified)
    - deprecated_method (removed)

  complexity: 15 → 12 ✓ (improved)
  lines: 120 → 105 ✓ (reduced)
```

---

### Method Comparison

```bash
# Compare method across files
reveal diff://api.py:old_api.py/APIHandler.process_request

# Compare method across branches
reveal diff://git://main/api.py:git://refactor/api.py/API.handle
```

**Example output**:
```
method: APIHandler.process_request

  complexity: 6 → 3 ✓ (improved)
  lines: 28 → 18 ✓ (reduced)
  signature: (self, request) → (self, request, context) (added parameter)

  Changes:
    - Extracted validation logic to separate method
    - Simplified error handling
    - Added context support
```

---

### Element Path Resolution

**How reveal finds elements**:
1. Parse file structure (functions, classes, methods)
2. Match element path to structure
3. Extract element from both resources
4. Compare structures

**Path matching**:
- Case-sensitive
- Exact match required
- Nested elements use dot notation (`Class.method`)

---

## Directory Comparison

### How Directory Diffs Work

1. **File discovery**: Recursively find all analyzable files
2. **Pairing**: Match files by relative paths
3. **Comparison**: Compare each matched file pair
4. **Aggregation**: Combine all changes into single summary
5. **Per-file breakdown**: Show which files changed

---

### What Gets Compared

**Included**:
- Python files (`.py`)
- JavaScript files (`.js`, `.jsx`, `.ts`, `.tsx`)
- Source files in supported languages
- Configuration files (when structured)

**Excluded**:
- Binary files (images, videos, executables)
- Hidden files/directories (`.git`, `.env`, `.vscode`)
- Build artifacts (`node_modules`, `__pycache__`, `dist`, `target`)
- Lock files (`package-lock.json`, `poetry.lock`)
- Logs (`.log` files)

---

### Example Directory Diff

```bash
reveal diff://src/:backup/src/
```

**Output**:
```
Summary:
  Files changed: 8 / 12
  Added: 15 functions, 4 classes
  Removed: 6 functions, 2 classes
  Modified: 22 functions, 7 classes

Details by file:

  src/main.py: +2 -1 ~4
    + function: new_feature (15 lines, complexity: 3)
    - function: old_handler (20 lines, complexity: 5)
    ~ function: process (complexity: 8 → 4 ✓)

  src/utils.py: +1 -0 ~2
    + function: format_output (8 lines, complexity: 2)
    ~ function: validate (complexity: 5 → 3 ✓)

  src/models.py: +3 -2 ~5
    + class: NewModel (45 lines, 3 methods)
    - class: LegacyModel (80 lines, 5 methods)
    ~ class: User (modified: 2 methods)

  src/api.py: +0 -1 ~3
    - function: deprecated_endpoint (15 lines)
    ~ function: handle_request (refactored)
```

---

### Directory Diff Metrics

**Summary metrics**:
- **Files changed**: How many files have differences
- **Total files**: How many files were compared
- **Added elements**: New functions/classes across all files
- **Removed elements**: Deleted functions/classes across all files
- **Modified elements**: Changed functions/classes across all files

**Per-file metrics**:
- **+N**: N elements added
- **-M**: M elements removed
- **~K**: K elements modified

---

## Output Format

### Summary Format

**Counts**:
```
Summary:
  Added: N
  Removed: M
  Modified: K
  Unchanged: U
```

**Symbols**:
```
+N -M ~K (N added, M removed, K modified)
```

---

### Detail Format

**Added elements**:
```
+ function: new_feature
    lines: 15
    complexity: 3
    description: New functionality added
```

**Removed elements**:
```
- function: deprecated_method
    lines: 20
    complexity: 5
    reason: Functionality removed or renamed
```

**Modified elements**:
```
~ function: handle_request
    complexity: 8 → 4 ✓ (improved)
    lines: 45 → 32 ✓ (reduced)
    signature: (request) → (request, options)
    changes:
      - Refactored logic
      - Added parameter
      - Reduced complexity
```

---

### JSON Output Format

```bash
reveal diff://app.py:old.py --format json
```

**Structure**:
```json
{
  "contract_version": "1.0",
  "type": "diff",
  "source": "diff://app.py:old.py",
  "left": {"uri": "app.py", "type": "file"},
  "right": {"uri": "old.py", "type": "file"},
  "summary": {
    "added": 3,
    "removed": 1,
    "modified": 4,
    "unchanged": 12
  },
  "changes": [
    {
      "type": "added",
      "element": "new_feature",
      "element_type": "function",
      "lines": 15,
      "complexity": 3
    },
    {
      "type": "removed",
      "element": "old_handler",
      "element_type": "function",
      "lines": 20,
      "complexity": 5
    },
    {
      "type": "modified",
      "element": "process",
      "element_type": "function",
      "old": {"complexity": 8, "lines": 45},
      "new": {"complexity": 4, "lines": 32},
      "delta": {"complexity": -4, "lines": -13},
      "improvement": true
    }
  ]
}
```

---

## Detailed Workflows

### Workflow 1: Pre-Commit Validation

**Scenario**: Check uncommitted changes before committing

**Steps**:

```bash
# Step 1: Check what changed
reveal diff://git://HEAD/src/:src/

# Step 2: Review complexity changes
reveal diff://git://HEAD/src/:src/ --format json | \
  jq '.changes[] | select(.delta.complexity > 5)'

# Step 3: Verify specific files
reveal diff://git://HEAD/app.py:app.py

# Step 4: Commit if acceptable
git add .
git commit -m "Refactored app logic"
```

**Automation** (pre-commit hook):
```bash
#!/bin/bash
# .git/hooks/pre-commit

# Check if complexity increased significantly
RESULT=$(reveal diff://git://HEAD/.:. --format json)
COMPLEXITY_INCREASE=$(echo "$RESULT" | jq '[.changes[] | select(.delta.complexity > 5)] | length')

if [ "$COMPLEXITY_INCREASE" -gt 0 ]; then
  echo "⚠️  Warning: $COMPLEXITY_INCREASE functions with significant complexity increase"
  echo "$RESULT" | jq -r '.changes[] | select(.delta.complexity > 5) | "  - \(.element): complexity +\(.delta.complexity)"'

  read -p "Continue anyway? (y/n) " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
  fi
fi
```

---

### Workflow 2: Code Review (Branch Comparison)

**Scenario**: Review what changed in a feature branch before merging

**Steps**:

```bash
# Step 1: Full branch comparison
reveal diff://git://main/.:git://feature/.

# Step 2: Check specific critical files
reveal diff://git://main/src/core/:git://feature/src/core/

# Step 3: Review specific function changes
reveal diff://git://main/app.py:git://feature/app.py/process_data

# Step 4: Verify complexity improvements
reveal diff://git://main/.:git://feature/. --format json | \
  jq '.changes[] | select(.improvement == true)'

# Step 5: Generate review report
{
  echo "# Code Review: feature → main"
  echo ""
  echo "## Summary"
  reveal diff://git://main/.:git://feature/.
  echo ""
  echo "## Complexity Improvements"
  reveal diff://git://main/.:git://feature/. --format json | \
    jq -r '.changes[] | select(.improvement == true) | "- \(.element): complexity \(.old.complexity) → \(.new.complexity)"'
} > review-report.md
```

---

### Workflow 3: Refactoring Validation

**Scenario**: Verify refactoring improved code without changing behavior

**Steps**:

```bash
# Step 1: Create backup before refactoring
cp -r src/ src.backup/

# Step 2: Perform refactoring
# ... make changes ...

# Step 3: Compare complexity
reveal diff://src.backup/:src/ --format json | \
  jq '.changes[] | {element: .element, complexity_delta: .delta.complexity}'

# Step 4: Verify expected improvements
reveal diff://src.backup/main.py:src/main.py/complex_function

# Step 5: Validate specific functions unchanged semantically
reveal diff://src.backup/api.py:src/api.py/critical_handler
```

**Success criteria**:
- Complexity reduced (negative delta)
- Lines reduced (more concise)
- No new functions added (pure refactoring)
- Critical functions unchanged

---

### Workflow 4: Migration Validation

**Scenario**: Ensure no functionality lost during migration

**Steps**:

```bash
# Step 1: Compare directory structures
reveal diff://legacy_system/:new_system/

# Step 2: Verify all functions migrated
reveal diff://legacy_system/:new_system/ --format json | \
  jq '.changes[] | select(.type == "removed")'

# Expected: Empty (no removed functions)

# Step 3: Compare specific modules
reveal diff://legacy_system/auth.py:new_system/auth.py

# Step 4: Verify critical functions
reveal diff://legacy_system/core.py:new_system/core.py/initialize

# Step 5: Generate migration report
{
  echo "# Migration Validation Report"
  echo ""
  echo "## Summary"
  reveal diff://legacy_system/:new_system/
  echo ""
  echo "## Missing Functions (CRITICAL)"
  reveal diff://legacy_system/:new_system/ --format json | \
    jq -r '.changes[] | select(.type == "removed") | "⚠️  \(.element)"'
} > migration-report.md
```

---

### Workflow 5: Release Validation

**Scenario**: Verify changes between releases before deployment

**Steps**:

```bash
# Step 1: Compare release tags
reveal diff://git://v1.0.0/.:git://v1.1.0/.

# Step 2: Review breaking changes
reveal diff://git://v1.0.0/src/api/:git://v1.1.0/src/api/

# Step 3: Check complexity trends
reveal diff://git://v1.0.0/.:git://v1.1.0/. --format json | \
  jq '.changes[] | select(.delta.complexity > 0)'

# Step 4: Verify expected features added
reveal diff://git://v1.0.0/.:git://v1.1.0/. --format json | \
  jq '.changes[] | select(.type == "added")'

# Step 5: Generate release notes
{
  echo "# Release Notes: v1.1.0"
  echo ""
  echo "## New Features"
  reveal diff://git://v1.0.0/.:git://v1.1.0/. --format json | \
    jq -r '.changes[] | select(.type == "added") | "- \(.element)"'
  echo ""
  echo "## Improvements"
  reveal diff://git://v1.0.0/.:git://v1.1.0/. --format json | \
    jq -r '.changes[] | select(.improvement == true) | "- \(.element): complexity reduced by \(-1 * .delta.complexity)"'
} > RELEASE_NOTES.md
```

---

### Workflow 6: Schema Drift Detection

**Scenario**: Detect database schema differences between environments

**Steps**:

```bash
# Step 1: Compare staging to production
reveal diff://mysql://staging/mydb:mysql://production/mydb

# Step 2: Check specific tables
reveal diff://mysql://staging/mydb:mysql://production/mydb/users

# Step 3: Generate drift report
{
  echo "# Schema Drift Report"
  echo "## Staging vs Production"
  reveal diff://mysql://staging/mydb:mysql://production/mydb
} > schema-drift.md

# Step 4: Alert if drift detected
DRIFT=$(reveal diff://mysql://staging/mydb:mysql://production/mydb --format json | \
  jq '.summary | .added + .removed + .modified')

if [ "$DRIFT" -gt 0 ]; then
  echo "⚠️  Schema drift detected: $DRIFT changes"
  # Send alert to monitoring system
fi
```

---

## Performance Considerations

### Operation Timing

| Operation | Typical Duration | Notes |
|-----------|-----------------|-------|
| File-to-file | 0.1-0.5s | Fast (single file parse) |
| Element-specific | 0.1-0.3s | Fast (element extraction) |
| Directory (small) | 0.5-2s | Moderate (10-20 files) |
| Directory (large) | 2-10s | Slower (50-100 files) |
| Git comparison | 0.5-3s | Moderate (git checkout overhead) |
| Database schema | 1-5s | Moderate (schema query overhead) |

---

### Optimization Strategies

#### 1. Use Element-Specific Diffs When Possible

```bash
# ❌ Expensive: Compare full files
reveal diff://app.py:old.py

# ✅ Fast: Compare specific function
reveal diff://app.py:old.py/handle_request
```

**Performance gain**: 3-5x faster

---

#### 2. Filter Files in Directory Comparisons

```bash
# ❌ Slow: Compare all files
reveal diff://src/:backup/src/

# ✅ Faster: Compare specific subdirectory
reveal diff://src/core/:backup/src/core/
```

**Performance gain**: Proportional to directory size reduction

---

#### 3. Use JSON Output for Programmatic Processing

```bash
# ✅ Efficient: JSON for automation
reveal diff://app.py:old.py --format json | jq '.summary'
```

**Benefit**: Client-side filtering, reduced output processing

---

#### 4. Cache Git Comparisons

```bash
#!/bin/bash
# Cache git diff results for dashboards

CACHE_FILE="/tmp/git-diff-cache.json"
CACHE_TTL=3600  # 1 hour

if [ ! -f "$CACHE_FILE" ] || [ $(($(date +%s) - $(stat -c %Y "$CACHE_FILE"))) -gt $CACHE_TTL ]; then
  reveal diff://git://main/.:git://develop/. --format json > "$CACHE_FILE"
fi

cat "$CACHE_FILE"
```

---

## Limitations

### Current Limitations

1. **Language support**
   - **Supported**: Python, JavaScript (basic)
   - **Partial**: Other languages (text-level diff fallback)
   - **Workaround**: Contribute language parsers

2. **Git integration dependency**
   - **Requirement**: Git must be installed and accessible
   - **Impact**: Git URI comparisons won't work without git CLI
   - **Workaround**: Ensure git is in PATH

3. **Binary file comparison**
   - **Limitation**: Binary files not compared (skipped)
   - **Impact**: Can't detect changes in images, executables
   - **Workaround**: Use traditional diff tools for binary files

4. **Large file performance**
   - **Issue**: Files >10,000 lines may be slow to parse
   - **Impact**: Directory diffs with many large files can take >10s
   - **Workaround**: Use element-specific diffs or filter to smaller directories

5. **No inline diff visualization**
   - **Limitation**: Shows structural changes, not line-by-line diff
   - **Impact**: Can't see exact line changes
   - **Workaround**: Use `git diff` or `diff` for line-level diffs

6. **Database adapter dependency**
   - **Limitation**: Database schema diffs require adapter support
   - **Currently supported**: MySQL, SQLite
   - **Not supported**: PostgreSQL, MongoDB (yet)

---

### Design Limitations (Intentional)

1. **Semantic over textual**: Intentionally ignores formatting, comments
2. **Structure-focused**: Not a replacement for line-level diff tools
3. **No modification**: Read-only (doesn't apply changes)

---

## Error Messages

### Common Errors and Solutions

#### Error: "Failed to resolve URI: file not found"

**Meaning**: One or both resources don't exist

**Solutions**:
```bash
# Verify file paths
ls -la app.py backup/app.py

# Check absolute paths
reveal diff:///home/user/app.py:/home/user/backup/app.py

# Verify git ref
git rev-parse HEAD~1
```

---

#### Error: "Git ref not found"

**Meaning**: Git reference doesn't exist (branch, commit, tag)

**Solutions**:
```bash
# List available branches
git branch -a

# List tags
git tag

# Verify commit exists
git log --oneline -10
```

---

#### Error: "Element not found in resource"

**Meaning**: Specified element doesn't exist in one or both files

**Solutions**:
```bash
# List available elements
reveal app.py

# Check element name spelling
# (case-sensitive, exact match required)

# Verify element exists in both files
reveal app.py/handle_request
reveal old.py/handle_request
```

---

#### Error: "Unsupported resource type for comparison"

**Meaning**: Resource type doesn't support structural comparison

**Solutions**:
- Use supported resource types (files, git, env, mysql, sqlite)
- For unsupported types, use traditional diff tools
- Check adapter documentation for comparison support

---

## Tips & Best Practices

### 1. Use Semantic Diff for Refactoring Validation

```bash
# ✅ Before committing refactored code
reveal diff://git://HEAD/app.py:app.py

# Verify complexity improved
reveal diff://git://HEAD/app.py:app.py --format json | \
  jq '.changes[] | select(.delta.complexity < 0)'
```

**Why**: Semantic diff shows if refactoring actually improved code

---

### 2. Compare Directories for Migration Validation

```bash
# ✅ Ensure all functions migrated
reveal diff://old_system/:new_system/ --format json | \
  jq '.changes[] | select(.type == "removed")'

# Expected: Empty (no removed functions)
```

**Why**: Aggregated view catches missing migrations

---

### 3. Use Element-Specific Diffs for Code Review

```bash
# ✅ Focus on specific function
reveal diff://git://main/app.py:git://feature/app.py/critical_handler

# Review only changed logic
```

**Why**: Filters out noise, focuses on relevant changes

---

### 4. Pre-Commit Hook for Complexity Checks

```bash
#!/bin/bash
# .git/hooks/pre-commit

# Alert if complexity increased significantly
reveal diff://git://HEAD/.:. --format json | \
  jq -e '.changes[] | select(.delta.complexity > 10) | length' > /dev/null

if [ $? -eq 0 ]; then
  echo "⚠️  Warning: Significant complexity increase detected"
  exit 1
fi
```

**Why**: Prevents accidental complexity increases

---

### 5. Use JSON Output for Automation

```bash
# ✅ Programmatic analysis
reveal diff://app.py:old.py --format json | \
  jq '.summary | {added, removed, modified}'
```

**Why**: Easy parsing, integration with monitoring tools

---

### 6. Compare Branches Before Merging

```bash
# ✅ Pre-merge validation
reveal diff://git://main/.:git://feature/.

# Check impact scope
```

**Why**: Understand merge impact before committing

---

### 7. Schema Drift Monitoring

```bash
# ✅ Continuous monitoring
reveal diff://mysql://staging/db:mysql://prod/db --format json | \
  jq -e '.summary | .added + .removed + .modified > 0'

if [ $? -eq 0 ]; then
  echo "⚠️  Schema drift detected"
fi
```

**Why**: Catch schema divergence early

---

### 8. Generate Release Notes from Diffs

```bash
# ✅ Automated release notes
reveal diff://git://v1.0.0/.:git://v1.1.0/. --format json | \
  jq -r '.changes[] | select(.type == "added") | "- \(.element)"' > RELEASE_NOTES.md
```

**Why**: Accurate, automated documentation

---

### 9. Verify Refactoring Didn't Change Behavior

```bash
# ✅ Check specific critical functions unchanged
reveal diff://before.py:after.py/critical_function

# Should show: complexity reduced, but signature/behavior unchanged
```

**Why**: Ensure refactoring maintains functionality

---

### 10. Compare Environment Configs

```bash
# ✅ Detect config drift
reveal diff://env://:env://production

# Flag if critical vars missing
```

**Why**: Prevent deployment issues from config mismatches

---

## Integration Examples

### 1. jq Integration

**Extract added functions**:
```bash
reveal diff://app.py:old.py --format json | \
  jq '.changes[] | select(.type == "added")'
```

**Count complexity improvements**:
```bash
reveal diff://app.py:old.py --format json | \
  jq '[.changes[] | select(.improvement == true)] | length'
```

**Find functions with high complexity increase**:
```bash
reveal diff://app.py:old.py --format json | \
  jq '.changes[] | select(.delta.complexity > 5)'
```

---

### 2. Python Integration

```python
import subprocess
import json

def compare_files(left, right):
    """Compare two files and return structured diff."""
    result = subprocess.run(
        ['reveal', f'diff://{left}:{right}', '--format', 'json'],
        capture_output=True,
        text=True
    )

    data = json.loads(result.stdout)

    return {
        'summary': data['summary'],
        'added': [c for c in data['changes'] if c['type'] == 'added'],
        'removed': [c for c in data['changes'] if c['type'] == 'removed'],
        'modified': [c for c in data['changes'] if c['type'] == 'modified'],
        'improvements': [c for c in data['changes'] if c.get('improvement')]
    }

# Compare files
diff = compare_files('app.py', 'old.py')
print(f"Summary: +{diff['summary']['added']} -{diff['summary']['removed']} ~{diff['summary']['modified']}")
print(f"Improvements: {len(diff['improvements'])}")
```

---

### 3. Pre-Commit Hook

```bash
#!/bin/bash
# .git/hooks/pre-commit - Validate complexity before committing

echo "Checking code complexity..."

RESULT=$(reveal diff://git://HEAD/.:. --format json)
COMPLEXITY_INCREASE=$(echo "$RESULT" | jq '[.changes[] | select(.delta.complexity > 10)] | length')

if [ "$COMPLEXITY_INCREASE" -gt 0 ]; then
  echo "⚠️  Error: $COMPLEXITY_INCREASE functions with significant complexity increase (>10)"
  echo "$RESULT" | jq -r '.changes[] | select(.delta.complexity > 10) | "  ❌ \(.element): complexity +\(.delta.complexity)"'
  echo ""
  echo "Please refactor or justify complexity increase."
  exit 1
fi

echo "✅ Complexity check passed"
```

---

### 4. GitHub Actions Integration

```yaml
name: Code Quality Check

on:
  pull_request:
    branches: [ main ]

jobs:
  complexity-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 0

      - name: Install reveal
        run: pip install reveal-tool

      - name: Compare branches
        run: |
          reveal diff://git://origin/main/.:. --format json > diff-result.json

      - name: Check complexity increases
        run: |
          INCREASES=$(jq '[.changes[] | select(.delta.complexity > 5)] | length' diff-result.json)
          if [ "$INCREASES" -gt 0 ]; then
            echo "⚠️ Warning: $INCREASES functions with significant complexity increase"
            jq -r '.changes[] | select(.delta.complexity > 5) | "- \(.element): +\(.delta.complexity)"' diff-result.json
          fi

      - name: Generate summary
        run: |
          jq '.summary' diff-result.json > summary.json

      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: diff-analysis
          path: diff-result.json
```

---

### 5. Release Notes Generation

```bash
#!/bin/bash
# generate-release-notes.sh - Generate release notes from diff

FROM_TAG="$1"
TO_TAG="$2"

if [ -z "$FROM_TAG" ] || [ -z "$TO_TAG" ]; then
  echo "Usage: $0 <from-tag> <to-tag>"
  exit 1
fi

{
  echo "# Release Notes: $TO_TAG"
  echo ""
  echo "## Summary"
  reveal diff://git://$FROM_TAG/.:git://$TO_TAG/.
  echo ""
  echo "## New Features"
  reveal diff://git://$FROM_TAG/.:git://$TO_TAG/. --format json | \
    jq -r '.changes[] | select(.type == "added") | "- **\(.element)**: \(.lines) lines, complexity \(.complexity)"'
  echo ""
  echo "## Improvements"
  reveal diff://git://$FROM_TAG/.:git://$TO_TAG/. --format json | \
    jq -r '.changes[] | select(.improvement == true) | "- **\(.element)**: complexity reduced by \(-1 * .delta.complexity)"'
  echo ""
  echo "## Breaking Changes"
  reveal diff://git://$FROM_TAG/.:git://$TO_TAG/. --format json | \
    jq -r '.changes[] | select(.type == "removed") | "- ⚠️ **\(.element)** removed"'
} > RELEASE_NOTES_$TO_TAG.md

echo "Release notes saved: RELEASE_NOTES_$TO_TAG.md"
```

---

## Related Documentation

### Reveal Adapter Guides

- **[Git Adapter Guide](GIT_ADAPTER_GUIDE.md)** - Git repository inspection (complements diff:// git integration)
- **[Domain Adapter Guide](DOMAIN_ADAPTER_GUIDE.md)** - Domain DNS/SSL inspection
- **[MySQL Adapter Guide](MYSQL_ADAPTER_GUIDE.md)** - Database schema inspection (used in schema drift detection)

### Reveal Core Documentation

- **[REVEAL_GUIDE.md](REVEAL_GUIDE.md)** - Complete reveal system guide
- **[ADAPTER_OVERVIEW.md](ADAPTER_OVERVIEW.md)** - All adapters reference

---

## FAQ

### General Questions

**Q: What's the difference between diff:// and git diff?**

A: **diff://** provides semantic structural comparison (functions, classes, complexity). **git diff** provides line-level text comparison. Use diff:// for understanding functional changes, git diff for seeing exact line changes.

---

**Q: Can I compare binary files?**

A: No. diff:// only compares structured text files (code, config). Binary files are skipped. Use traditional tools like `cmp` or `diff` for binary comparison.

---

**Q: Does diff:// work with all programming languages?**

A: Currently supports Python and JavaScript well. Other languages fall back to text-level diff. Language support is extensible (contributions welcome).

---

**Q: Can I compare more than 2 resources?**

A: No. diff:// compares exactly 2 resources. For multi-way comparison, use multiple diff commands.

---

### Git Integration Questions

**Q: What's the Git URI format?**

A: `git://<ref>/<path>` where `<ref>` is HEAD, branch name, tag, or commit SHA, and `<path>` is the file/directory path.

Example: `git://HEAD~1/app.py`, `git://main/src/`, `git://abc123/file.py`

---

**Q: How do I compare my working tree to HEAD?**

A: `reveal diff://git://HEAD/file.py:file.py`

This shows uncommitted changes (pre-commit validation).

---

**Q: Can I compare two different branches?**

A: Yes: `reveal diff://git://main/.:git://feature/.`

---

**Q: Why does Git comparison fail with "ref not found"?**

A: Git reference doesn't exist. Verify with `git branch -a` or `git tag`.

---

### Element-Specific Questions

**Q: How do I compare a specific function?**

A: `reveal diff://app.py:old.py/function_name`

Element path: `<file-uri>/<element-name>`

---

**Q: Can I compare a method inside a class?**

A: Yes: `reveal diff://api.py:old_api.py/ClassName.method_name`

Use dot notation for nested elements.

---

**Q: What if the element doesn't exist in one file?**

A: diff:// will show it as added (if only in right) or removed (if only in left).

---

### Directory Comparison Questions

**Q: How does directory comparison work?**

A: Recursively finds all analyzable files in both directories, compares each matching pair, aggregates results.

---

**Q: What files are excluded from directory diffs?**

A: Binary files, hidden files (`.git`, `.env`), build artifacts (`node_modules`, `__pycache__`), lock files.

---

**Q: Can I compare specific subdirectories?**

A: Yes: `reveal diff://src/core/:backup/src/core/`

Faster than full directory comparison.

---

### Output Format Questions

**Q: What does "complexity: 8 → 4 ✓" mean?**

A: Complexity reduced from 8 to 4 (improvement indicated by ✓).

Complexity measures cyclomatic complexity (branching, loops).

---

**Q: What do the symbols mean (+, -, ~, ✓, ⚠)?**

A:
- `+` = Added
- `-` = Removed
- `~` = Modified
- `✓` = Improvement (complexity/lines reduced)
- `⚠` = Concern (complexity/lines increased)

---

**Q: How do I get JSON output?**

A: `reveal diff://app.py:old.py --format json`

JSON is easier to parse programmatically.

---

### Performance Questions

**Q: Why is directory comparison slow?**

A: Must parse all files in both directories. Large codebases (>100 files) can take 5-10s.

Optimize by comparing specific subdirectories or using element-specific diffs.

---

**Q: Can I speed up git comparisons?**

A: Git comparisons require git checkout (overhead). Cache results if running repeatedly (dashboards, monitoring).

---

### Integration Questions

**Q: How do I use diff:// in pre-commit hooks?**

A: See [Pre-Commit Hook](#3-pre-commit-hook) example. Use `reveal diff://git://HEAD/.:./` to check uncommitted changes.

---

**Q: Can I integrate with CI/CD?**

A: Yes. See [GitHub Actions Integration](#4-github-actions-integration). Use JSON output for programmatic analysis.

---

**Q: How do I generate release notes?**

A: See [Release Notes Generation](#5-release-notes-generation). Compare release tags and extract added/removed functions.

---

---

**Last Updated**: 2026-02-14
**Adapter Version**: reveal 0.1.0+
**Documentation Version**: 1.0
