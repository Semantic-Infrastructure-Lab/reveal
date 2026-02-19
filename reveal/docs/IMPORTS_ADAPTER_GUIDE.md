---
title: Imports Adapter Guide (imports://)
category: guide
---
# Imports Adapter Guide (imports://)

**Adapter**: `imports://`
**Purpose**: Import graph analysis for detecting unused imports, circular dependencies, and layer violations
**Type**: Analysis adapter
**Output Formats**: text, json, grep

## Table of Contents

1. [Quick Start](#quick-start)
2. [URI Syntax](#uri-syntax)
3. [Import Graph Overview](#import-graph-overview)
4. [Unused Import Detection](#unused-import-detection)
5. [Circular Dependency Detection](#circular-dependency-detection)
6. [Layer Violation Checking](#layer-violation-checking)
7. [Multi-Language Support](#multi-language-support)
8. [Query Parameters](#query-parameters)
9. [CLI Flags](#cli-flags)
10. [Output Types](#output-types)
11. [Workflows](#workflows)
12. [Integration Examples](#integration-examples)
13. [Performance & Best Practices](#performance-best-practices)
14. [Troubleshooting](#troubleshooting)
15. [Limitations](#limitations)
16. [Tips & Best Practices](#tips-best-practices)
17. [Related Documentation](#related-documentation)
18. [FAQ](#faq)

---

## Quick Start

```bash
# 1. Import graph overview (all imports)
reveal imports://src

# 2. Find unused imports (dead code)
reveal 'imports://src?unused'

# 3. Detect circular dependencies
reveal 'imports://src?circular'

# 4. Check layer violations (requires .reveal.yaml)
reveal 'imports://src?violations'

# 5. Single file import inspection
reveal imports://src/main.py

# 6. Verbose output (detailed information)
reveal imports://src --verbose

# 7. JSON output for CI/CD
reveal 'imports://src?unused' --format=json

# 8. Grep-friendly output
reveal 'imports://src?circular' --format=grep
```

**Why use imports://?**
- **Clean codebase**: Find and remove unused imports (dead code)
- **Architecture health**: Detect circular dependencies (refactoring opportunities)
- **Layer enforcement**: Check architectural boundaries (clean architecture)
- **Multi-language**: Python, JavaScript/TypeScript, Go, Rust, Java, C++, and more
- **CI/CD integration**: JSON output for automated quality checks

---

## URI Syntax

```
imports://<path>[?<query>]
```

### Components

| Component | Required | Default | Description |
|-----------|----------|---------|-------------|
| `path` | No | `.` (current directory) | Directory or file to analyze |
| `query` | No | (none) | Query flag (?unused, ?circular, ?violations) |

### Examples

```bash
# Directory analysis
reveal imports://src
reveal imports://lib/utils
reveal imports://.  # Current directory

# File analysis
reveal imports://src/main.py
reveal imports://app/__init__.py

# Quality checks
reveal 'imports://src?unused'
reveal 'imports://src?circular'
reveal 'imports://src?violations'

# Absolute paths
reveal imports:///absolute/path/to/project

# Current directory
reveal imports://
reveal imports://.
```

---

## Import Graph Overview

The default view builds a complete import graph:

```bash
reveal imports://src
```

**Returns** (~300 tokens):

```
============================================================
Import Analysis: src
============================================================

  Total Files:   45
  Total Imports: 238
  Cycles Found:  ❌ Yes

Query options:
  reveal 'imports://src?unused'    - Find unused imports
  reveal 'imports://src?circular'  - Detect circular deps
  reveal 'imports://src?violations' - Check layer violations
```

**What you get**:
- **Total files**: Number of source files analyzed
- **Total imports**: Count of import statements
- **Cycles found**: Quick indicator if circular dependencies exist
- **Query options**: Suggested follow-up commands

**Use cases**:
- Quick health check
- Understand import complexity
- Determine next steps (unused vs circular vs violations)

---

## Unused Import Detection

Find imports that are declared but never used in code:

```bash
reveal 'imports://src?unused'
```

**Returns** (~500 tokens):

```
============================================================
Unused Imports: 12
============================================================

  src/api/routes.py:3 - typing.Dict
  src/api/routes.py:5 - datetime
  src/models/user.py:8 - typing.Optional
  src/utils/helpers.py:2 - sys
  src/db/session.py:4 - sqlalchemy.orm
  src/config.py:7 - pathlib.Path
  src/services/auth.py:12 - jwt.exceptions
  src/handlers/errors.py:5 - traceback
  src/middleware/logging.py:3 - json
  src/tests/test_api.py:15 - pytest.fixture

  ... and 2 more unused imports
  Run with --verbose to see all 12 unused imports
```

### Verbose Output

```bash
reveal 'imports://src?unused' --verbose
```

**Returns**: Full list of all unused imports with file paths and line numbers

### JSON Output

```bash
reveal 'imports://src?unused' --format=json
```

**Returns**:
```json
{
  "contract_version": "1.0",
  "type": "unused_imports",
  "source": "/home/user/projects/myproject/src",
  "source_type": "directory",
  "count": 12,
  "unused": [
    {
      "file": "src/api/routes.py",
      "line": 3,
      "module": "typing.Dict",
      "names": ["Dict"],
      "type": "from_import",
      "is_relative": false,
      "alias": null
    },
    {
      "file": "src/api/routes.py",
      "line": 5,
      "module": "datetime",
      "names": [],
      "type": "import",
      "is_relative": false,
      "alias": null
    }
  ],
  "metadata": {
    "total_imports": 238,
    "total_files": 45,
    "has_cycles": true,
    "analyzer": "imports",
    "version": "0.30.0"
  }
}
```

### How It Works

1. **Extract imports**: Parse all import statements in files
2. **Extract symbols**: Find all identifier references in code
3. **Cross-reference**: Match imports against symbol usage
4. **Flag unused**: Report imports with zero references

**Detection logic**:
- ✅ Detects: `import os` (never used)
- ✅ Detects: `from typing import Dict` (never used)
- ❌ Ignores: `from module import *` (can't verify usage)
- ❌ Ignores: Imports in `__all__` (re-exports)
- ❌ Ignores: `TYPE_CHECKING` imports (type hints only)

**Use cases**:
- Clean up dead code
- Reduce import overhead
- Improve code clarity
- Speed up module loading

---

## Circular Dependency Detection

Find import cycles (A imports B, B imports A):

```bash
reveal 'imports://src?circular'
```

**Returns** (~400 tokens):

```
============================================================
Circular Dependencies: 3
============================================================

  1. src/models/user.py -> src/services/auth.py -> src/models/user.py

  2. src/api/routes.py -> src/handlers/users.py -> src/api/routes.py

  3. src/db/models.py -> src/db/session.py -> src/db/base.py -> src/db/models.py

  ... and 0 more circular dependencies
  Run with --verbose to see all 3 cycles
```

### Verbose Output

```bash
reveal 'imports://src?circular' --verbose
```

**Returns**: Full list of all circular dependency chains

### JSON Output

```bash
reveal 'imports://src?circular' --format=json
```

**Returns**:
```json
{
  "contract_version": "1.0",
  "type": "circular_dependencies",
  "source": "/home/user/projects/myproject/src",
  "source_type": "directory",
  "count": 3,
  "cycles": [
    [
      "src/models/user.py",
      "src/services/auth.py",
      "src/models/user.py"
    ],
    [
      "src/api/routes.py",
      "src/handlers/users.py",
      "src/api/routes.py"
    ],
    [
      "src/db/models.py",
      "src/db/session.py",
      "src/db/base.py",
      "src/db/models.py"
    ]
  ],
  "metadata": {
    "total_imports": 238,
    "total_files": 45,
    "has_cycles": true,
    "analyzer": "imports",
    "version": "0.30.0"
  }
}
```

### How It Works

1. **Build graph**: Create directed graph of import relationships
2. **Detect cycles**: Use depth-first search to find strongly connected components
3. **Report chains**: Show complete path from A → B → ... → A

**Detection notes**:
- ✅ Detects: Direct cycles (A → B → A)
- ✅ Detects: Indirect cycles (A → B → C → A)
- ❌ Ignores: `TYPE_CHECKING` imports (not runtime cycles)
- ✅ Reports: Complete chain showing all modules in cycle

**Why circular dependencies are bad**:
- **Testing difficulty**: Can't test modules in isolation
- **Load order issues**: Module initialization becomes fragile
- **Tight coupling**: Changes cascade across modules
- **Refactoring obstacles**: Hard to restructure architecture

**How to fix**:
1. **Extract interface**: Move shared types to separate module
2. **Dependency injection**: Pass dependencies as parameters
3. **Inversion**: Make one module depend on abstraction
4. **Merge**: If modules are tightly coupled, merge them

---

## Layer Violation Checking

Enforce architectural boundaries (requires .reveal.yaml configuration):

```bash
reveal 'imports://src?violations'
```

### Configuration (.reveal.yaml)

```yaml
architecture:
  layers:
    # Layer definitions (higher layers can import lower, not vice versa)
    - name: presentation
      paths:
        - src/api
        - src/cli

    - name: application
      paths:
        - src/services
        - src/handlers

    - name: domain
      paths:
        - src/models
        - src/entities

    - name: infrastructure
      paths:
        - src/db
        - src/external

  rules:
    # Presentation layer can import application and domain
    - layer: presentation
      can_import:
        - application
        - domain

    # Application layer can import domain only
    - layer: application
      can_import:
        - domain

    # Domain layer has no dependencies (pure business logic)
    - layer: domain
      can_import: []

    # Infrastructure layer can import domain
    - layer: infrastructure
      can_import:
        - domain
```

### Example Output

**Returns** (~400 tokens):

```
============================================================
Layer Violations: 5
============================================================

  src/models/user.py:3 - Layer violation: domain importing infrastructure (src.db.session)
  src/handlers/users.py:8 - Layer violation: application importing infrastructure (src.db.models)
  src/api/routes.py:12 - Layer violation: presentation importing infrastructure (src.db.connection)
  src/services/auth.py:15 - Layer violation: application importing presentation (src.api.schemas)
  src/models/product.py:5 - Layer violation: domain importing application (src.services.pricing)

  ... and 0 more violations
  Run with --verbose to see all 5 violations
```

### Without Configuration

If `.reveal.yaml` is not configured:

```bash
reveal 'imports://src?violations'
```

**Returns**:
```
============================================================
Layer Violations: 0
============================================================

  ✅ Layer violation detection requires .reveal.yaml configuration (coming in Phase 4)
```

**Use cases**:
- Enforce clean architecture
- Prevent presentation → database direct access
- Ensure domain layer purity
- Maintain layer boundaries in large codebases

---

## Multi-Language Support

imports:// supports multiple programming languages:

### Supported Languages

| Language | Extensions | Status | Features |
|----------|-----------|--------|----------|
| Python | `.py` | ✅ Full | Imports, symbols, exports, TYPE_CHECKING |
| JavaScript | `.js`, `.mjs` | ✅ Full | require, import/export |
| TypeScript | `.ts`, `.tsx` | ✅ Full | import/export, type imports |
| Go | `.go` | ✅ Full | import statements |
| Rust | `.rs` | ✅ Full | use statements |
| Java | `.java` | ✅ Full | import statements |
| C++ | `.cpp`, `.cc`, `.h`, `.hpp` | ✅ Full | #include directives |
| C# | `.cs` | ✅ Full | using statements |
| Ruby | `.rb` | ✅ Full | require statements |
| PHP | `.php` | ✅ Full | use, require, include |

### Language-Specific Examples

#### Python

```bash
# Find unused imports
reveal 'imports://src?unused'

# Detect circular imports (common in Python)
reveal 'imports://src?circular'

# Example unused:
# from typing import Dict  # Never used
# import os  # Never used
```

#### JavaScript/TypeScript

```bash
# Find unused ES6 imports
reveal 'imports://src?unused'

# Example unused:
# import { useState } from 'react';  // Never used
# const _ = require('lodash');  // Never used
```

#### Go

```bash
# Find unused imports (Go compiler catches most)
reveal 'imports://cmd?unused'

# Example circular:
# package a imports package b
# package b imports package a
```

#### Rust

```bash
# Find unused use statements
reveal 'imports://src?unused'

# Example unused:
# use std::collections::HashMap;  // Never used
```

---

## Query Parameters

### Query Flags

Use `?flag` syntax for operations:

| Flag | Description | Example |
|------|-------------|---------|
| `unused` | Find unused imports | `imports://src?unused` |
| `circular` | Detect circular dependencies | `imports://src?circular` |
| `violations` | Check layer violations | `imports://src?violations` |

**Note**: Query parameters are flags (no `=value` needed)

```bash
# Correct
reveal 'imports://src?unused'

# Also works (but unnecessary)
reveal 'imports://src?unused=true'
```

---

## CLI Flags

### Standard Flags

| Flag | Description | Example |
|------|-------------|---------|
| `--format=<type>` | Output format (text, json, grep) | `reveal imports://src --format=json` |
| `--verbose` | Show detailed results | `reveal imports://src --verbose` |

### Examples

```bash
# Verbose unused imports
reveal 'imports://src?unused' --verbose

# JSON output for CI/CD
reveal 'imports://src?circular' --format=json

# Grep-friendly output
reveal 'imports://src?unused' --format=grep | grep "api/"
```

---

## Output Types

### 1. import_summary

**Use case**: Repository import overview

**Schema**:
```json
{
  "contract_version": "1.0",
  "type": "import_summary",
  "source": "/home/user/projects/myproject/src",
  "source_type": "directory",
  "metadata": {
    "total_files": 45,
    "total_imports": 238,
    "has_cycles": true,
    "analyzer": "imports",
    "version": "0.30.0"
  }
}
```

### 2. unused_imports

**Use case**: Find dead code

**Schema**:
```json
{
  "contract_version": "1.0",
  "type": "unused_imports",
  "source": "/home/user/projects/myproject/src",
  "source_type": "directory",
  "count": 12,
  "unused": [
    {
      "file": "src/api/routes.py",
      "line": 3,
      "module": "typing.Dict",
      "names": ["Dict"],
      "type": "from_import",
      "is_relative": false,
      "alias": null
    }
  ],
  "metadata": {
    "total_imports": 238,
    "total_files": 45,
    "has_cycles": true
  }
}
```

### 3. circular_dependencies

**Use case**: Architecture health check

**Schema**:
```json
{
  "contract_version": "1.0",
  "type": "circular_dependencies",
  "source": "/home/user/projects/myproject/src",
  "source_type": "directory",
  "count": 3,
  "cycles": [
    [
      "src/models/user.py",
      "src/services/auth.py",
      "src/models/user.py"
    ]
  ],
  "metadata": {
    "total_imports": 238,
    "total_files": 45,
    "has_cycles": true
  }
}
```

### 4. layer_violations

**Use case**: Clean architecture enforcement

**Schema**:
```json
{
  "contract_version": "1.0",
  "type": "layer_violations",
  "source": "/home/user/projects/myproject/src",
  "source_type": "directory",
  "count": 5,
  "violations": [
    {
      "file": "src/models/user.py",
      "line": 3,
      "message": "Layer violation: domain importing infrastructure (src.db.session)"
    }
  ],
  "metadata": {
    "total_imports": 238,
    "total_files": 45,
    "has_cycles": true
  }
}
```

---

## Workflows

### Workflow 1: Clean Up Unused Imports

**Scenario**: Remove dead code and improve maintainability

```bash
# 1. Find unused imports
reveal 'imports://src?unused'

# 2. Review list (check for false positives)
reveal 'imports://src?unused' --verbose

# 3. Remove unused imports
# (manually or with automated tools)

# 4. Verify cleanup
reveal 'imports://src?unused'
# Should show: "✅ No unused imports found!"

# 5. Commit changes
git add -u
git commit -m "refactor: Remove unused imports"
```

**Expected result**: Zero unused imports

---

### Workflow 2: Detect and Fix Circular Dependencies

**Scenario**: Find and break circular import cycles

```bash
# 1. Detect circular dependencies
reveal 'imports://src?circular'

# Example output:
# 1. src/models/user.py -> src/services/auth.py -> src/models/user.py

# 2. Analyze the cycle
reveal imports://src/models/user.py
reveal imports://src/services/auth.py

# 3. Identify the problematic imports
# - user.py imports auth.py for token generation
# - auth.py imports user.py for User model

# 4. Refactor to break cycle
# Option A: Extract interface
#   Create src/interfaces/user.py with User protocol
#   auth.py imports interface, not concrete model

# Option B: Dependency injection
#   Pass User model to auth functions as parameter

# Option C: Inversion
#   Move token generation from auth.py to user.py

# 5. Verify fix
reveal 'imports://src?circular'
# Should show: "✅ No circular dependencies found!"

# 6. Commit refactoring
git add -A
git commit -m "refactor: Break circular dependency between user and auth"
```

**Expected result**: Zero circular dependencies

---

### Workflow 3: Enforce Architecture Layers

**Scenario**: Ensure clean architecture with layer boundaries

```bash
# 1. Create .reveal.yaml with layer rules
cat > .reveal.yaml <<EOF
architecture:
  layers:
    - name: presentation
      paths: [src/api, src/cli]
    - name: application
      paths: [src/services]
    - name: domain
      paths: [src/models]
    - name: infrastructure
      paths: [src/db]

  rules:
    - layer: presentation
      can_import: [application, domain]
    - layer: application
      can_import: [domain]
    - layer: domain
      can_import: []
    - layer: infrastructure
      can_import: [domain]
EOF

# 2. Check for violations
reveal 'imports://src?violations'

# Example output:
# src/models/user.py:3 - domain importing infrastructure (src.db.session)

# 3. Fix violations
# - Move database logic from domain to infrastructure
# - Use dependency injection for database access
# - Refactor models to be pure business logic

# 4. Verify compliance
reveal 'imports://src?violations'
# Should show: "✅ No violations found"

# 5. Add to CI/CD
cat >> .github/workflows/ci.yml <<EOF
  - name: Check architecture layers
    run: reveal 'imports://src?violations' --format json
EOF

# 6. Commit layer config
git add .reveal.yaml .github/workflows/ci.yml
git commit -m "feat: Add architecture layer enforcement"
```

**Expected result**: Zero layer violations

---

### Workflow 4: Codebase Health Check

**Scenario**: Comprehensive import analysis

```bash
# 1. Import overview
reveal imports://src

# 2. Check for unused imports
reveal 'imports://src?unused'

# 3. Check for circular dependencies
reveal 'imports://src?circular'

# 4. Generate health report
cat > import_health_report.md <<EOF
# Import Health Report - $(date +%Y-%m-%d)

## Overview
$(reveal imports://src --format=json | jq '.metadata')

## Unused Imports
$(reveal 'imports://src?unused' --format=json | jq '.count')

## Circular Dependencies
$(reveal 'imports://src?circular' --format=json | jq '.count')

## Status
$(reveal imports://src)
EOF

# 5. Address issues
# - Remove unused imports
# - Break circular dependencies
# - Fix layer violations

# 6. Track progress over time
# Save reports: import_health_report_YYYY-MM-DD.md
```

**Expected result**: Health report with metrics

---

### Workflow 5: CI/CD Integration

**Scenario**: Automated import quality checks

```bash
# .github/workflows/import-quality.yml
name: Import Quality

on: [push, pull_request]

jobs:
  import-quality:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Install reveal
        run: pip install reveal-cli

      - name: Check for unused imports
        run: |
          UNUSED=$(reveal 'imports://src?unused' --format=json | jq '.count')
          if [ "$UNUSED" -gt 0 ]; then
            echo "❌ Found $UNUSED unused imports"
            reveal 'imports://src?unused'
            exit 1
          fi
          echo "✅ No unused imports"

      - name: Check for circular dependencies
        run: |
          CYCLES=$(reveal 'imports://src?circular' --format=json | jq '.count')
          if [ "$CYCLES" -gt 0 ]; then
            echo "❌ Found $CYCLES circular dependencies"
            reveal 'imports://src?circular'
            exit 1
          fi
          echo "✅ No circular dependencies"

      - name: Check layer violations
        run: |
          if [ -f .reveal.yaml ]; then
            VIOLATIONS=$(reveal 'imports://src?violations' --format=json | jq '.count')
            if [ "$VIOLATIONS" -gt 0 ]; then
              echo "❌ Found $VIOLATIONS layer violations"
              reveal 'imports://src?violations'
              exit 1
            fi
            echo "✅ No layer violations"
          fi
```

**Expected result**: CI fails on import quality issues

---

### Workflow 6: Refactoring Safety Check

**Scenario**: Ensure refactoring doesn't introduce cycles

```bash
# Before refactoring
reveal 'imports://src?circular' > before_refactor.txt

# Perform refactoring
# - Move functions between modules
# - Reorganize imports
# - Rename modules

# After refactoring
reveal 'imports://src?circular' > after_refactor.txt

# Compare
diff before_refactor.txt after_refactor.txt

# If new cycles introduced:
if [ "$(cat after_refactor.txt | grep 'Circular Dependencies:' | awk '{print $3}')" -gt \
     "$(cat before_refactor.txt | grep 'Circular Dependencies:' | awk '{print $3}')" ]; then
  echo "❌ Refactoring introduced new circular dependencies!"
  reveal 'imports://src?circular'
  exit 1
fi

echo "✅ Refactoring did not introduce new cycles"
```

**Expected result**: No new circular dependencies

---

## Integration Examples

### Integration 1: Combine with jq

```bash
# Count unused imports by directory
reveal 'imports://src?unused' --format=json | \
  jq -r '.unused[] | .file | split("/")[0]' | \
  sort | uniq -c

# Find files with most unused imports
reveal 'imports://src?unused' --format=json | \
  jq -r '.unused[] | .file' | \
  sort | uniq -c | sort -rn | head -10

# List unused imports from specific module
reveal 'imports://src?unused' --format=json | \
  jq -r '.unused[] | select(.file | startswith("src/api")) | "\(.file):\(.line) - \(.module)"'

# Extract circular dependency chains
reveal 'imports://src?circular' --format=json | \
  jq -r '.cycles[] | join(" -> ")'
```

### Integration 2: Automated Cleanup Script

```bash
#!/bin/bash
# cleanup-unused-imports.sh - Remove unused imports (Python)

set -e

echo "Finding unused imports..."
UNUSED=$(reveal 'imports://src?unused' --format=json)
COUNT=$(echo "$UNUSED" | jq '.count')

if [ "$COUNT" -eq 0 ]; then
  echo "✅ No unused imports found"
  exit 0
fi

echo "Found $COUNT unused imports"

# Group by file
FILES=$(echo "$UNUSED" | jq -r '.unused[] | .file' | sort -u)

for file in $FILES; do
  echo "Cleaning $file..."

  # Get unused lines for this file
  LINES=$(echo "$UNUSED" | jq -r ".unused[] | select(.file == \"$file\") | .line")

  # Remove lines (in reverse order to preserve line numbers)
  for line in $(echo "$LINES" | sort -rn); do
    sed -i "${line}d" "$file"
  done
done

echo "✅ Removed $COUNT unused imports"
echo "Run tests to ensure nothing broke!"
```

### Integration 3: Pre-commit Hook

```bash
#!/bin/bash
# .git/hooks/pre-commit - Prevent commits with unused imports

echo "Checking for unused imports..."

UNUSED=$(reveal 'imports://src?unused' --format=json | jq '.count')

if [ "$UNUSED" -gt 0 ]; then
  echo "❌ Cannot commit: Found $UNUSED unused imports"
  reveal 'imports://src?unused'
  echo ""
  echo "Remove unused imports before committing:"
  echo "  reveal 'imports://src?unused'"
  exit 1
fi

echo "✅ No unused imports"
```

### Integration 4: Python Integration

```python
#!/usr/bin/env python3
import subprocess
import json
from pathlib import Path

def get_import_health(path='src'):
    """Get import health metrics using reveal."""
    result = subprocess.run(
        ['reveal', 'imports://' + path, '--format=json'],
        capture_output=True,
        text=True
    )
    return json.loads(result.stdout)

def get_unused_imports(path='src'):
    """Get unused imports."""
    result = subprocess.run(
        ['reveal', f'imports://{path}?unused', '--format=json'],
        capture_output=True,
        text=True
    )
    return json.loads(result.stdout)

def get_circular_dependencies(path='src'):
    """Get circular dependencies."""
    result = subprocess.run(
        ['reveal', f'imports://{path}?circular', '--format=json'],
        capture_output=True,
        text=True
    )
    return json.loads(result.stdout)

def generate_report(path='src'):
    """Generate import health report."""
    health = get_import_health(path)
    unused = get_unused_imports(path)
    circular = get_circular_dependencies(path)

    report = {
        'summary': health['metadata'],
        'issues': {
            'unused_count': unused['count'],
            'circular_count': circular['count']
        },
        'health_score': calculate_health_score(health, unused, circular)
    }

    return report

def calculate_health_score(health, unused, circular):
    """Calculate health score (0-100)."""
    total_imports = health['metadata']['total_imports']
    unused_count = unused['count']
    circular_count = circular['count']

    # Deduct points for issues
    score = 100
    score -= (unused_count / total_imports * 100) * 0.3  # 30% weight
    score -= min(circular_count * 10, 50)  # Max 50 points deduction
    return max(0, int(score))

if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else 'src'

    print(f"Analyzing {path}...")
    report = generate_report(path)

    print(f"\n{'='*60}")
    print(f"Import Health Report")
    print(f"{'='*60}\n")
    print(f"  Total Files:   {report['summary']['total_files']}")
    print(f"  Total Imports: {report['summary']['total_imports']}")
    print(f"  Unused:        {report['issues']['unused_count']}")
    print(f"  Circular:      {report['issues']['circular_count']}")
    print(f"  Health Score:  {report['health_score']}/100")
    print()

    if report['health_score'] < 70:
        print("⚠️ Import health needs attention")
        sys.exit(1)
    else:
        print("✅ Import health is good")
```

### Integration 5: Dependency Graph Visualization

```bash
#!/bin/bash
# visualize-imports.sh - Create import graph visualization

set -e

echo "Building import graph..."

# Get circular dependencies
reveal 'imports://src?circular' --format=json > cycles.json

# Generate GraphViz dot file
cat > imports.dot <<EOF
digraph imports {
  rankdir=LR;
  node [shape=box];

  // Nodes (files)
EOF

# Add nodes from cycles
jq -r '.cycles[][] | unique' cycles.json | sort -u | while read node; do
  echo "  \"$node\";" >> imports.dot
done

echo "" >> imports.dot
echo "  // Edges (imports)" >> imports.dot

# Add edges from cycles
jq -r '.cycles[] | . as $cycle | range(0; length-1) | "\($cycle[.]) -> \($cycle[.+1])"' cycles.json | while read edge; do
  echo "  $edge [color=red];" >> imports.dot
done

echo "}" >> imports.dot

# Render to PNG
dot -Tpng imports.dot -o import_graph.png

echo "✅ Graph saved to import_graph.png"
```

### Integration 6: Multi-Language Analysis

```bash
#!/bin/bash
# analyze-multilang.sh - Analyze imports across languages

echo "Analyzing Python..."
reveal 'imports://src?unused' --format=json > python_unused.json

echo "Analyzing JavaScript..."
reveal 'imports://frontend/src?unused' --format=json > js_unused.json

echo "Analyzing Go..."
reveal 'imports://cmd?unused' --format=json > go_unused.json

# Aggregate results
cat python_unused.json js_unused.json go_unused.json | \
  jq -s '{
    total_unused: map(.count) | add,
    by_language: [
      {language: "Python", count: (.[0].count // 0)},
      {language: "JavaScript", count: (.[1].count // 0)},
      {language: "Go", count: (.[2].count // 0)}
    ]
  }'
```

---

## Performance & Best Practices

### Performance Characteristics

| Operation | Speed | Scalability |
|-----------|-------|-------------|
| Import extraction | Fast | Linear O(n) files |
| Graph construction | Fast | O(n) imports |
| Unused detection | Medium | O(n*m) cross-reference |
| Circular detection | Medium | O(n+e) graph traversal |
| Layer validation | Fast | O(n) imports |

### Performance Tips

1. **Scope analysis**
   ```bash
   # Good: Analyze specific directory
   reveal 'imports://src?unused'

   # Bad: Analyze entire project including tests, docs, etc.
   reveal 'imports://.?unused'
   ```

2. **Use JSON for large results**
   ```bash
   # Fast: JSON output, pipe to jq
   reveal 'imports://src?unused' --format=json | jq '.count'

   # Slow: Text output for 1000s of results
   reveal 'imports://src?unused'
   ```

3. **Cache results**
   ```python
   # Cache import graph (expensive to build)
   @cache(ttl=300)  # 5 minutes
   def get_import_health():
       return get_imports('src')
   ```

4. **Progressive checks**
   ```bash
   # Check overview first (fast)
   reveal imports://src

   # Then specific checks if needed
   if has_cycles; then
     reveal 'imports://src?circular'
   fi
   ```

### Best Practices

1. **Regular cleanup**
   - Run `?unused` weekly in development
   - Add to PR review checklist
   - Automate in CI/CD

2. **Monitor cycles**
   - Check `?circular` during refactoring
   - Track cycle count over time
   - Break cycles before they multiply

3. **Layer enforcement**
   - Define layers in `.reveal.yaml`
   - Add `?violations` to CI
   - Review violations during design

4. **Multi-language projects**
   - Analyze each language separately
   - Aggregate results for reporting
   - Use consistent tooling

---

## Troubleshooting

### Issue: "Path not found: src"

**Problem**: Directory doesn't exist or wrong path

**Solution**:
```bash
# Check path exists
ls -la src

# Use correct relative path
reveal imports://./src

# Or absolute path
reveal imports:///absolute/path/to/src
```

### Issue: No unused imports detected (but there are some)

**Problem**: Symbol extraction missed references

**Solution**:
```bash
# Check file is being analyzed
reveal imports://src --format=json | jq '.metadata.total_files'

# Verify import is actually unused (not in __all__)
grep -n "from module import unused" src/file.py
grep -r "unused" src/

# Report false negatives on GitHub
```

### Issue: Circular dependency not detected

**Problem**: TYPE_CHECKING imports are ignored (by design)

**Solution**:
```python
# These are NOT runtime cycles (ignored)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from module import Class

# This IS a runtime cycle (detected)
from module import Class
```

### Issue: Layer violations not working

**Problem**: No `.reveal.yaml` configuration

**Solution**:
```bash
# Create .reveal.yaml with layer rules
cat > .reveal.yaml <<EOF
architecture:
  layers:
    - name: presentation
      paths: [src/api]
    - name: domain
      paths: [src/models]
  rules:
    - layer: presentation
      can_import: [domain]
    - layer: domain
      can_import: []
EOF

# Then run check
reveal 'imports://src?violations'
```

---

## Limitations

1. **Language support**
   - ✅ Fully supported: Python, JS/TS, Go, Rust, Java, C++
   - ⚠️ Partial: Dynamic imports (`__import__`, `require()`)
   - ❌ Not supported: Custom import mechanisms

2. **Dynamic imports**
   - Cannot detect usage in dynamically loaded modules
   - String-based imports are not tracked
   - Reflection-based imports are not detected

3. **Type-only imports**
   - `TYPE_CHECKING` imports are not counted as cycles
   - Type-only imports may be flagged as unused (false positive)
   - Workaround: Use `# noqa` comments

4. **Layer violations**
   - Requires `.reveal.yaml` configuration
   - Phase 4 feature (not fully implemented yet)
   - Manual rule definition required

5. **Performance**
   - Large codebases (10k+ files) can be slow
   - Unused detection is O(n*m) complexity
   - Consider scoping analysis to specific directories

6. **Re-exports**
   - `__all__` exports are correctly handled
   - `*` imports cannot be fully validated
   - May have false positives for barrel files

---

## Tips & Best Practices

### 1. Start with Overview

```bash
# Always check overall health first
reveal imports://src

# Then drill into specific issues
reveal 'imports://src?unused'
reveal 'imports://src?circular'
```

### 2. Use Verbose for Details

```bash
# Summary (first 10 results)
reveal 'imports://src?unused'

# Full list
reveal 'imports://src?unused' --verbose
```

### 3. Automate in CI/CD

```bash
# Add to .github/workflows/ci.yml
- name: Check import quality
  run: |
    reveal 'imports://src?unused' --format=json | jq -e '.count == 0'
    reveal 'imports://src?circular' --format=json | jq -e '.count == 0'
```

### 4. Track Metrics Over Time

```bash
# Daily import health snapshot
reveal imports://src --format=json | \
  jq '{date: now, files: .metadata.total_files, imports: .metadata.total_imports, cycles: .metadata.has_cycles}' \
  >> import_metrics.jsonl
```

### 5. Fix Cycles Immediately

```bash
# Don't let cycles accumulate
# Fix them as soon as they appear
reveal 'imports://src?circular'

# If found, refactor immediately:
# - Extract interface
# - Dependency injection
# - Inversion of control
```

### 6. Review Unused Before Removal

```bash
# Not all "unused" imports are truly unused
# Check for:
# - Re-exports (__all__)
# - Type hints (TYPE_CHECKING)
# - Side-effect imports

reveal 'imports://src?unused' --verbose | \
  grep -v "__all__" | \
  grep -v "TYPE_CHECKING"
```

### 7. Combine with Other Adapters

```bash
# Find complex files with circular dependencies
reveal ast://src/**/*.py?complexity>10 --format=json | \
  jq -r '.matches[].path' | while read file; do
    reveal imports://$file
  done
```

---

## Related Documentation

- **AST Adapter**: `docs/AST_ADAPTER_GUIDE.md` - Code structure analysis (find complex code)
- **Stats Adapter**: `docs/STATS_ADAPTER_GUIDE.md` - Codebase metrics and hotspots
- **Python Adapter**: `docs/PYTHON_ADAPTER_GUIDE.md` - Runtime inspection
- **Reveal Overview**: `README.md` - Full reveal documentation

---

## FAQ

### Q: How accurate is unused import detection?

**A**: Very accurate for most cases:
- ✅ Detects: `import os` (never used)
- ✅ Detects: `from typing import Dict` (never used)
- ❌ False positive: Type-only imports (use `# noqa`)
- ❌ False positive: Re-exports in `__all__` (handled correctly)
- ❌ False negative: Dynamic imports (`__import__("module")`)

### Q: Can I ignore specific unused imports?

**A**: Yes, use comments:

```python
# Python
from module import unused  # noqa: F401

# JavaScript
import unused from 'module';  // eslint-disable-line no-unused-vars
```

### Q: Why are TYPE_CHECKING imports not flagged as unused?

**A**: `TYPE_CHECKING` imports are type hints only, not runtime dependencies. They don't cause circular dependencies and are intentionally ignored.

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from module import TypeOnly  # Not flagged as unused (correct)
```

### Q: How do I fix circular dependencies?

**A**: Three main approaches:

1. **Extract interface**: Move shared types to separate module
2. **Dependency injection**: Pass dependencies as parameters
3. **Inversion**: Make one module depend on abstraction

See [Workflow 2](#workflow-2-detect-and-fix-circular-dependencies) for detailed examples.

### Q: Can I use this on projects with multiple languages?

**A**: Yes! Analyze each language separately:

```bash
# Python
reveal 'imports://backend/src?unused'

# JavaScript
reveal 'imports://frontend/src?unused'

# Go
reveal 'imports://services/cmd?unused'
```

### Q: What about dynamic imports?

**A**: Dynamic imports are not tracked:

```python
# Not detected
module_name = "os"
__import__(module_name)

# Detected
import os
```

Use static imports when possible for better tooling support.

### Q: How often should I check import health?

**A**: Recommended schedule:
- **Weekly**: Manual check during development
- **Per PR**: Automated check in CI/CD
- **Monthly**: Comprehensive audit with reports

### Q: Can I configure layer rules per team/project?

**A**: Yes, use `.reveal.yaml` in each project root:

```yaml
# Project A (microservice)
architecture:
  layers:
    - name: api
      paths: [src/api]
    - name: domain
      paths: [src/models]

# Project B (monolith)
architecture:
  layers:
    - name: presentation
      paths: [src/web, src/cli]
    - name: application
      paths: [src/services]
    - name: domain
      paths: [src/entities]
```

### Q: What if analysis is slow?

**A**: Optimize scope:

```bash
# Good: Specific directory
reveal 'imports://src?unused'

# Bad: Entire project
reveal 'imports://.?unused'

# Good: Exclude tests
reveal 'imports://src?unused'

# Bad: Include tests (often have many unused test fixtures)
reveal 'imports://src?unused' && reveal 'imports://tests?unused'
```

### Q: Can I get diffs between branches?

**A**: Yes, compare JSON outputs:

```bash
# Main branch
git checkout main
reveal 'imports://src?circular' --format=json > main_cycles.json

# Feature branch
git checkout feature/new-code
reveal 'imports://src?circular' --format=json > feature_cycles.json

# Compare
diff <(jq '.count' main_cycles.json) <(jq '.count' feature_cycles.json)
```

### Q: How do I integrate with pre-commit?

**A**: Add to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: check-imports
        name: Check import quality
        entry: bash -c 'reveal "imports://src?unused" --format=json | jq -e ".count == 0"'
        language: system
        pass_filenames: false
```

---

## Version History

- **v1.0** (2025-02-14): Initial comprehensive guide
  - All 4 output types documented
  - Multi-language support (Python, JS/TS, Go, Rust, Java, C++, etc.)
  - Unused import detection
  - Circular dependency detection
  - Layer violation checking
  - 6 complete workflows
  - Integration examples (jq, Python, CI/CD, pre-commit)
  - Performance optimization tips
  - 52 references consolidated

## See Also

- [GIT_ADAPTER_GUIDE.md](GIT_ADAPTER_GUIDE.md) - Git repository analysis
- [QUICK_START.md](QUICK_START.md) - General reveal usage reference
