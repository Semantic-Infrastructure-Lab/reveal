# diff:// Adapter - AI Agent Usage Guide

## Overview

The diff:// adapter provides **semantic structural comparison** for AI agents to analyze code changes. Unlike text-based diff tools, it compares functions, classes, and imports - providing actionable insights for code review and impact assessment.

## Key Features for AI

### 1. **Directory Diff** - Batch Operations
Compare entire modules/projects at once:

```bash
# Compare current vs backup
reveal diff://./src:./backup/src --format=json

# Assess refactoring impact
reveal diff://./old_arch:./new_arch --format=json
```

**JSON Output Structure**:
```json
{
  "summary": {
    "functions": {"added": 10, "removed": 5, "modified": 3}
  },
  "diff": {
    "functions": [
      {
        "type": "modified",
        "name": "process_data",
        "left": {"file": "utils/processor.py", "complexity": 3},
        "right": {"file": "utils/processor.py", "complexity": 7}
      }
    ]
  }
}
```

### 2. **Git Integration** - Historical Analysis

```bash
# Review uncommitted changes (pre-commit validation)
reveal diff://git://HEAD/src/:src/ --format=json

# Compare branches (merge impact assessment)
reveal diff://git://main/app/:git://feature/refactor/app/ --format=json

# Track evolution (what changed since last release)
reveal diff://git://v1.0.0/module.py:git://v2.0.0/module.py --format=json
```

**Git URI Format**: `git://REF/path`
- REF: Any git reference (HEAD, HEAD~1, main, v1.0.0, commit-sha)
- path: File or directory path

### 3. **Cross-Resource Comparison**

```bash
# Working tree vs git
reveal diff://git://HEAD/file.py:file.py

# Local vs production environment
reveal diff://env://local:env://production

# Database schema drift
reveal diff://mysql://localhost/users:mysql://staging/users
```

## AI Workflow Patterns

### Pattern 1: Pre-Commit Validation

```python
# AI checks uncommitted changes for quality issues
result = reveal("diff://git://HEAD/src/:src/", format="json")

issues = []
for func in result['diff']['functions']:
    if func['type'] == 'modified':
        old_complexity = func['left']['complexity']
        new_complexity = func['right']['complexity']
        if new_complexity - old_complexity >= 5:
            issues.append(f"⚠️ {func['name']} complexity increased significantly")

if issues:
    print("Quality issues detected:", issues)
```

### Pattern 2: Migration Validation

```python
# Verify refactoring didn't lose functionality
result = reveal("diff://./old_system:./new_system", format="json")

# Check for removed functions (potential regressions)
removed = [f for f in result['diff']['functions'] if f['type'] == 'removed']
if removed:
    print(f"⚠️ {len(removed)} functions removed - verify intentional")
```

### Pattern 3: Merge Impact Assessment

```python
# Before merging feature branch
result = reveal("diff://git://main/.:git://feature/big-refactor/.", format="json")

summary = result['summary']
total_changes = (
    summary['functions']['added'] + 
    summary['functions']['removed'] + 
    summary['functions']['modified']
)

if total_changes > 50:
    print(f"⚠️ Large merge ({total_changes} function changes) - thorough review needed")
```

### Pattern 4: Code Review Automation

```python
# Identify functions with significant changes
result = reveal("diff://git://HEAD~1/src/:git://HEAD/src/", format="json")

for func in result['diff']['functions']:
    if func['type'] == 'modified':
        changes = func['changes']
        
        # Flag complexity increases
        if 'complexity' in changes:
            old, new = changes['complexity']['old'], changes['complexity']['new']
            if new - old >= 2:
                print(f"📊 {func['name']}: complexity {old}→{new} - review needed")
        
        # Flag signature changes (API breaking)
        if 'signature' in changes:
            print(f"🔧 {func['name']}: signature changed - check callers")
```

## Progressive Disclosure

The diff:// adapter follows reveal's progressive disclosure pattern:

1. **Summary** - Quick overview of aggregate changes
2. **Details** - Per-element changes with old→new values
3. **File Context** - Which file each change is in (for directories)

**Example:**
```json
{
  "summary": {"functions": {"+": 5, "-": 2, "~": 3}},
  "diff": {
    "functions": [
      {
        "type": "modified",
        "name": "validate_input",
        "changes": {"complexity": {"old": 3, "new": 7}},
        "left": {"file": "utils.py", ...},
        "right": {"file": "utils.py", ...}
      }
    ]
  }
}
```

## Semantic vs Text Diff

**diff:// focuses on structure, not lines:**

```python
# Text diff would show:
# - def process(x):
# + def process(x, y):

# diff:// shows:
{
  "type": "modified",
  "name": "process",
  "changes": {
    "signature": {"old": "(x)", "new": "(x, y)"}
  }
}
```

**Benefits for AI**:
- Language-agnostic insights
- Focuses on semantic changes
- Noise reduction (ignore whitespace/formatting)
- Actionable metrics (complexity, signature)

## Performance Considerations

- **Directory diff**: Scans only analyzable files (skips binary, .git, etc.)
- **Git integration**: Creates temp files (cleaned up automatically)
- **Large repos**: Use specific paths instead of root: `diff://git://HEAD/src/core:src/core`

## Integration with Other Adapters

diff:// composes with ALL reveal adapters:

```bash
# Compare Python package versions
reveal diff://python://requests:python://urllib3

# Compare AST queries
reveal diff://ast://src/?type=function:ast://tests/?type=function

# Compare JSON schemas
reveal diff://data/schema_v1.json:data/schema_v2.json
```

## Error Handling

```python
try:
    result = reveal("diff://git://HEAD/file.py:file.py", format="json")
except RevealError as e:
    if "Not in a git repository" in str(e):
        # Fallback to simple file diff
        result = reveal("diff://backup/file.py:file.py", format="json")
```

## Next Steps

- Explore `reveal help://diff` for complete syntax
- Use `--format=json` for programmatic access
- Combine with other reveal features (--check, --outline)

---

**Session**: sacred-sphinx-0104  
**Related**: cooling-hurricane-0104 (diff:// Week 1)
