# AST Query Patterns for Reveal

**Date:** 2025-12-08
**Status:** Living Document - add patterns as discovered

---

## Quick Reference

```bash
reveal 'ast://<path>?<filter1>&<filter2>'
```

**Operators:** `>`, `<`, `>=`, `<=`, `==`
**Wildcards:** `*` (any), `?` (single char)

---

## Scoping Queries

### Directory Targeting
```bash
# Whole project
reveal 'ast://.'

# Specific directory
reveal 'ast://./src'
reveal 'ast://./src/auth'

# Absolute paths work too
reveal 'ast:///home/user/project/lib'
```

### File Targeting
```bash
# Single file
reveal 'ast://./src/main.py?lines>30'
```

---

## Code Discovery Patterns

### Find Entry Points
```bash
# All main() functions in a codebase
reveal 'ast://./src?name=main'

# CLI entry points (commands directory)
reveal 'ast://./commands?name=main'
```

### Find Long Functions (Refactoring Candidates)
```bash
# Functions over 50 lines
reveal 'ast://./src?lines>50'

# Really long functions (100+ lines) - definitely need attention
reveal 'ast://./src?lines>100'
```

### Find Complex Functions
```bash
# High complexity (cyclomatic complexity > 7)
reveal 'ast://./src?complexity>7'

# Danger zone (complexity 10+)
reveal 'ast://./src?complexity>=10'
```

### Find by Naming Convention
```bash
# Private/internal functions
reveal 'ast://./src?name=_*'

# Getters
reveal 'ast://./src?name=get_*'

# Test functions
reveal 'ast://./src?name=test_*'

# Error handlers
reveal 'ast://./src?name=*error*'

# Async functions (by naming convention)
reveal 'ast://./src?name=async_*'
```

---

## Code Quality Patterns

### Long But Simple (Extract to Module?)
```bash
# Long functions with low complexity - might be procedural code
# Good candidate for extraction to separate module
reveal 'ast://./src?lines>50&complexity<5'
```

### Short But Complex (Simplify?)
```bash
# Short functions with high complexity - dense logic
# Might need refactoring for readability
reveal 'ast://./src?lines<20&complexity>7'
```

### Monster Functions (Priority Refactoring)
```bash
# Both long AND complex - highest priority for refactoring
reveal 'ast://./src?lines>100&complexity>7'
```

---

## API Surface Patterns

### Public API Discovery
```bash
# All public functions (not starting with _)
# Note: Requires excluding _ prefix - use inverse thinking
reveal 'ast://./src?name=get_*'      # Getters are usually public
reveal 'ast://./src?name=create_*'   # Factory functions
reveal 'ast://./src?name=run_*'      # Entry points
```

### Interface Methods
```bash
# Common interface method names
reveal 'ast://./src?name=get_structure'
reveal 'ast://./src?name=get_element'
reveal 'ast://./src?name=get_help'
```

---

## Testing Patterns

### Test Coverage Discovery
```bash
# Count test functions
reveal 'ast://./tests?name=test_*' | wc -l

# Find test files with few tests (might need more coverage)
reveal 'ast://./tests?name=test_*' --format=json | jq 'group_by(.file)'
```

### Find Untested Areas
```bash
# Complex functions that might need tests
reveal 'ast://./src?complexity>7'
# Then check if corresponding test_* functions exist
```

---

## Combined Queries (Real Examples)

### Reveal Codebase Analysis
```bash
# Long getter methods (might be doing too much)
reveal 'ast://reveal?lines>50&name=get_*'
# Found: get_help (68 lines), get_structure (74-107 lines)

# All analyzers with large get_structure methods
reveal 'ast://reveal/analyzers?lines>50&name=get_structure'
# Found: dockerfile, gdscript, jsonl, jupyter, markdown, nginx
```

### TIA Codebase Analysis
```bash
# All command entry points
reveal 'ast:///home/scottsen/src/tia/commands?name=main'
# Found: 395 main() functions

# Error handling functions
reveal 'ast:///home/scottsen/src/tia/lib?name=*error*'
# Found: 39 error-related functions

# Most complex functions in lib
reveal 'ast:///home/scottsen/src/tia/lib?complexity>=10'
```

---

## Output Formats

### Human-Readable (Default)
```bash
reveal 'ast://./src?lines>50'
```

### JSON (For Scripting)
```bash
# Pipe to jq for filtering
reveal 'ast://./src?lines>50' --format=json | jq '.[] | select(.complexity > 7)'

# Get just file names
reveal 'ast://./src?lines>50' --format=json | jq -r '.[].file' | sort -u
```

### Grep Format (For Further Processing)
```bash
reveal 'ast://./src?lines>50' --format=grep
```

---

## Type Filter

### Singular and Plural Both Work
```bash
# Both forms work (normalized automatically)
reveal 'ast://./src?type=function'   # ✅ Works
reveal 'ast://./src?type=functions'  # ✅ Works

reveal 'ast://./src?type=class'      # ✅ Works
reveal 'ast://./src?type=classes'    # ✅ Works

# Supported types: function(s), class(es), method(s), struct(s), import(s)
```

---

## Anti-Patterns to Avoid

### Quote URIs with Operators
```bash
# Shell interprets > as redirect without quotes
reveal ast://./src?lines>50    # ❌ Creates file named "50"
reveal 'ast://./src?lines>50'  # ✅ Correct
```

---

## Workflow Examples

### Code Review Prep
```bash
# 1. Find what changed (git)
git diff --name-only main

# 2. Check complexity of changed files
reveal 'ast://./src/changed_file.py?complexity>5'

# 3. Review long functions
reveal 'ast://./src/changed_file.py?lines>30'
```

### Onboarding to New Codebase
```bash
# 1. Find entry points
reveal 'ast://./src?name=main'

# 2. Find public API
reveal 'ast://./src?name=get_*'
reveal 'ast://./src?name=create_*'

# 3. Find the complex parts
reveal 'ast://./src?complexity>7'
```

### Technical Debt Assessment
```bash
# 1. Monster functions (long + complex)
reveal 'ast://./src?lines>100&complexity>7'

# 2. Count by severity
reveal 'ast://./src?lines>100' | grep -c "Results:"
reveal 'ast://./src?lines>50' | grep -c "Results:"
reveal 'ast://./src?complexity>7' | grep -c "Results:"
```

---

## Future Patterns (When Implemented)

> **Status**: These are post-v1.0 features. See [PRIORITIES.md](PRIORITIES.md) for current roadmap.
> - `semantic://` — Explicitly killed (unclear value)
> - Call graph / `calls=` — Deferred post-v1.0 (requires full static analysis)

```bash
# Call graph (post-v1.0)
reveal 'ast://./src#authenticate --call-graph'

# Cross-reference (post-v1.0)
reveal 'ast://./src?calls=authenticate'
reveal 'calls://src/api.py:handle_request'  # Proposed syntax
```

**Why deferred**: Call graph analysis requires tracking function invocations across files—significantly more complex than structure extraction. The tree-sitter infrastructure is ready, but the cross-file resolution isn't trivial.

---

## Notes

- Complexity is currently line-count heuristic; tree-sitter-based calculation planned
- Scans recursively through all code files
- Supports 50+ languages via tree-sitter
- Results sorted by file, then by line number
