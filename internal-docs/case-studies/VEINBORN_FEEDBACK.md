# Reveal Feedback: Veinborn Dogfooding Session

**Session**: neon-abyss-0119
**Date**: 2026-01-19
**Context**: First-time user experience exploring Veinborn codebase
**Reveal Version**: 0.39.0

---

## UX Issues Encountered

### 1. `--check` Doesn't Recurse on Directories

**What happened**:
```bash
reveal /home/scottsen/src/projects/veinborn/src/core/actions/ --check --select B006
```
**Expected**: Run B006 check on all .py files in actions/
**Actual**: Just showed directory structure, no checks run

**Workaround**: Manual loop
```bash
for f in src/core/*.py; do reveal "$f" --check; done
```

**Suggestion**: `--check` on a directory should recurse and aggregate results. Maybe `--check --recursive` or just make it the default.

---

### 2. `imports://` Scanner Shows 0 Files

**What happened**:
```bash
reveal 'imports:///home/scottsen/src/projects/veinborn/src?circular'
```
**Output**:
```
Total Files:   0
Total Imports: 0
Cycles Found:  ✅ No
```

**Expected**: Should have scanned 79 Python files

**Possible cause**: Path resolution issue? Works differently than other adapters?

---

### 3. `markdown://` Query Used Wrong Directory

**What happened**:
```bash
reveal 'markdown:///home/scottsen/src/projects/veinborn/docs?category=*'
```
**Output**: Searched current directory instead of specified path
```
Markdown Query: /home/scottsen/src/tia/sessions/neon-abyss-0119/
Matched: 1 of 1 files
  CLAUDE.md
```

**Expected**: Should query Veinborn's docs directory

---

### 4. No Aggregate Summary for Multi-File Checks

When running `--check` on multiple files (via loop), there's no summary like:
```
Total: 55 issues across 15 files
  - 20 unused imports (I001)
  - 15 complexity warnings (C901/C902)
  - etc.
```

**Suggestion**: `reveal src/ --check --summary` or automatic aggregation

---

### 5. help:// Index Is Dense

`reveal help://` returns ~200 lines. For quick orientation, a shorter version would help:
```bash
reveal help://quick  # Just the 5 most useful commands
```

---

## Functionality Gaps

### From TIA's Brogue Scanners (Not in Reveal)

| Gap | TIA Scanner | Use Case |
|-----|-------------|----------|
| Magic number detection | `brogue_magic_number_scanner` | Find hardcoded balance values like `damage * 1.5` |
| Type hint coverage | `brogue_standards_scanner` | Enforce typing on public APIs |
| Docstring enforcement | `brogue_standards_scanner` | Require docstrings on public functions |
| Print statement detection | `brogue_standards_scanner` | Find debug prints left in code |
| Exception handling audit | `brogue_standards_scanner` | Find bare `except:` clauses |

### General Gaps

1. **No baseline/ignore file** - Can't mark known issues as "accepted"
2. **No fix suggestions with patches** - Could offer `--fix` for simple issues like unused imports
3. **No severity filtering** - `--check --severity=high` would be useful
4. **No rule configuration** - Can't adjust thresholds (e.g., complexity max 15 instead of 10)

---

## Wishlist

### High Priority

1. **Recursive directory checks**
   ```bash
   reveal src/ --check  # Should just work
   ```

2. **Aggregate reporting**
   ```bash
   reveal src/ --check --format=summary
   # Output: 55 issues (20 I001, 15 C901, ...)
   ```

3. **Severity filtering**
   ```bash
   reveal src/ --check --severity=warning,error  # Skip info
   ```

4. **Baseline file support**
   ```bash
   reveal src/ --check --baseline=.reveal-baseline.json
   # Only show NEW issues since baseline
   ```

### Medium Priority

5. **Auto-fix for simple issues**
   ```bash
   reveal src/ --check --fix --select=I001  # Remove unused imports
   ```

6. **Rule configuration file**
   ```yaml
   # .reveal.yaml
   rules:
     C901:
       max_complexity: 15  # Override default 10
     C902:
       max_lines: 80       # Override default 100
     I001:
       ignore_patterns:
         - "from typing import *"  # Allow star imports from typing
   ```

7. **Watch mode**
   ```bash
   reveal src/ --check --watch
   # Re-runs on file changes
   ```

8. **CI/CD output formats**
   ```bash
   reveal src/ --check --format=github  # GitHub Actions annotations
   reveal src/ --check --format=gitlab  # GitLab CI format
   reveal src/ --check --format=junit   # JUnit XML for CI systems
   ```

### Nice to Have

9. **Pre-commit hook integration**
   ```yaml
   # .pre-commit-config.yaml
   - repo: local
     hooks:
       - id: reveal-check
         name: Reveal Code Quality
         entry: reveal --check --select=C901,I001
         types: [python]
   ```

10. **Diff-only mode**
    ```bash
    reveal --check --diff=main  # Only check changed files
    ```

---

## veinborn:// Project Adapter Ideas

A project-specific adapter could provide Veinborn-aware inspections:

### 1. Action Class Validation (`veinborn://actions`)

```bash
reveal 'veinborn://actions'
```

**What it would check**:
- All action classes inherit from `BaseAction`
- `execute()` method exists and returns `ActionOutcome`
- `from_dict()` classmethod exists for serialization
- Required attributes (`name`, `description`) present

**Output**:
```
Action Classes (11):
  ✅ AttackAction - valid (execute, from_dict, outcome)
  ✅ MoveAction - valid
  ⚠️  CustomAction - missing from_dict classmethod
  ❌ BrokenAction - execute doesn't return ActionOutcome
```

### 2. Entity Type Audit (`veinborn://entities`)

```bash
reveal 'veinborn://entities?type=monster'
```

**What it would show**:
- All monster definitions from YAML
- Which ones have Lua AI behaviors
- Stats validation (HP > 0, attack > 0, etc.)
- Missing required fields

### 3. Lua Script Validation (`veinborn://lua`)

```bash
reveal 'veinborn://lua/ai'
```

**What it would check**:
- All AI scripts have `update(monster, config)` function
- Required veinborn API calls used correctly
- Event handlers registered properly
- No undefined global access

### 4. Game Balance Audit (`veinborn://balance`)

```bash
reveal 'veinborn://balance?check'
```

**What it would find**:
- Magic numbers in Python code that should be in YAML
- Balance values that seem outliers (damage: 9999)
- Inconsistencies between YAML configs and code defaults

### 5. Event System Consistency (`veinborn://events`)

```bash
reveal 'veinborn://events'
```

**What it would show**:
- All registered event types
- Which handlers subscribe to each
- Orphan events (defined but never emitted)
- Missing handlers for critical events

### 6. Cross-Reference Validation (`veinborn://xref`)

```bash
reveal 'veinborn://xref?entity=goblin'
```

**What it would show**:
- Where "goblin" is defined (YAML)
- Where it's referenced (Python, Lua)
- Spawning rules that create it
- Loot tables that drop its items

---

## Feature Ideas for Reveal Core

### 1. Project Adapter Framework

Make it easy to create project-specific adapters:

```python
# ~/.config/reveal/adapters/veinborn.py
from reveal.adapters.base import ProjectAdapter

class VeinbornAdapter(ProjectAdapter):
    name = "veinborn"
    project_root = "/home/scottsen/src/projects/veinborn"

    def handle_actions(self, query):
        """Handle veinborn://actions queries"""
        # Custom logic here

    def handle_balance(self, query):
        """Handle veinborn://balance queries"""
        # Custom logic here
```

### 2. Semantic Diff for Refactoring

```bash
reveal 'diff://old_file.py:new_file.py?semantic=true'
```

Show structural changes, not just line-by-line:
- Function `foo` renamed to `bar`
- Class `Widget` moved to new module
- Method `process` complexity increased from 5 to 12

### 3. Code Pattern Search

```bash
reveal 'pattern://./src?match=try:*except Exception:pass'
```

Find specific code patterns across codebase (like semgrep but integrated).

### 4. Dependency Graph Visualization

```bash
reveal 'imports://./src?graph=true' > deps.dot
dot -Tpng deps.dot -o deps.png
```

### 5. Historical Complexity Tracking

```bash
reveal 'stats://./src?history=30d'
```

Show how complexity/coverage/issues changed over time.

### 6. Interactive TUI Mode

```bash
reveal --interactive ./src
```

Browse codebase with keyboard navigation:
- Arrow keys to navigate structure
- Enter to drill down
- `c` to run checks on current file
- `b` to show blame
- `h` for history

---

## Quick Wins (Low Effort, High Value)

1. **`--check` recursive by default** - Most common use case
2. **Exit code for CI** - `reveal --check` returns 1 if issues found
3. **`--quiet` mode** - Only show issues, no structure
4. **Issue count in output** - "Found 4 issues" at the end
5. **`--select` accepts wildcards** - `--select='C*'` for all complexity rules

---

## Summary

**What's Already Great**:
- Progressive disclosure (10-75x token savings)
- Semantic git blame on functions
- AST queries with filters
- Multi-language support
- Self-documenting help system

**Biggest Gaps**:
- Directory-level --check doesn't recurse
- No aggregate reporting
- No baseline/ignore file
- imports:// and markdown:// path issues

**Most Exciting Possibilities**:
- Project-specific adapters (veinborn://)
- Auto-fix for simple issues
- CI/CD integration formats
- Semantic diff for refactoring

---

*Feedback from neon-abyss-0119 session, dogfooding Reveal on Veinborn*
