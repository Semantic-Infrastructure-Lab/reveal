---
title: Python Adapter (python://) - Complete Guide
category: guide
---
# Python Adapter (python://) - Complete Guide

## Overview

The Python adapter provides runtime inspection and diagnostics for Python environments. It's designed to help debug common Python environment issues, especially those that plague AI coding assistants and developers alike.

**Core Philosophy**: Make invisible Python runtime issues visible through structured queries.

## Quick Start

```bash
# Basic environment overview
reveal python://

# Check for issues
reveal python://doctor

# Analyze a specific module
reveal python://module/reveal

# Inspect sys.path
reveal python://syspath
```

## Features at a Glance

| Feature | URI | Use Case |
|---------|-----|----------|
| Environment Overview | `python://` | Quick health check |
| Version Info | `python://version` | Verify Python version |
| Virtual Env Detection | `python://venv` | Confirm venv activation |
| Package Listing | `python://packages` | See all installed packages |
| Package Details | `python://packages/pkg` | Deep dive into specific package |
| **Module Conflict Detection** | `python://module/pkg` | **Debug "wrong version loading"** |
| **sys.path Analysis** | `python://syspath` | **Understand import precedence** |
| **Auto Diagnostics** | `python://doctor` | **One-command health check** |
| Loaded Modules | `python://imports` | See what's currently imported |
| Bytecode Issues | `python://debug/bytecode` | Find stale .pyc files |

## The Problem This Solves

### Classic Scenario

```
Developer: "I just upgraded package X but it's still showing the old version!"
```

**What's Actually Happening**: CWD shadowing, editable installs, or stale imports.

**Before Python Adapter**:
```bash
python -c "import X; print(X.__file__)"  # Find location
pip show X  # Check pip metadata
ls -la /path/to/X  # Manual investigation
# ... 15 minutes later ...
```

**With Python Adapter**:
```bash
reveal python://module/X
```

Output shows:
- ✅ Import location
- ✅ Pip package metadata
- ⚠️  **CONFLICT DETECTED**: CWD shadowing installed package
- 💡 **RECOMMENDATION**: Run from different directory

## New Features (v0.17.0)

### 1. Module Conflict Detection (`python://module/<name>`)

**Problem Solved**: "Why is Python importing the wrong version of my package?"

#### Examples

**Example 1: Detecting CWD Shadowing**

```bash
$ cd /home/user/myproject
$ reveal python://module/myproject

{
  "module": "myproject",
  "status": "importable",
  "import_location": "/home/user/myproject/myproject/__init__.py",
  "import_path": "/home/user/myproject/myproject",
  "pip_package": {
    "name": "myproject",
    "version": "1.0.0",
    "location": "/usr/local/lib/python3.10/site-packages",
    "install_type": "normal"
  },
  "conflicts": [
    {
      "type": "cwd_shadowing",
      "severity": "warning",
      "message": "Current working directory is shadowing installed package",
      "cwd": "/home/user/myproject"
    }
  ],
  "recommendations": [
    {
      "action": "change_directory",
      "message": "Run from a different directory to use the installed package",
      "command": "cd /tmp && python ..."
    }
  ]
}
```

**Example 2: Pip vs Import Location Mismatch**

```bash
$ reveal python://module/reveal-cli

{
  "module": "reveal",
  "status": "importable",
  "import_location": "/home/user/src/reveal/reveal/__init__.py",
  "pip_package": {
    "name": "reveal-cli",
    "version": "0.17.0",
    "location": "/home/user/.local/lib/python3.10/site-packages",
    "install_type": "editable"
  },
  "conflicts": [
    {
      "type": "location_mismatch",
      "severity": "warning",
      "message": "Import location differs from pip package location"
    }
  ]
}
```

**Example 3: Module Not Found**

```bash
$ reveal python://module/nonexistent

{
  "module": "nonexistent",
  "status": "not_found",
  "import_location": null,
  "pip_package": null,
  "conflicts": [],
  "recommendations": []
}
```

### 2. sys.path Analysis (`python://syspath`)

**Problem Solved**: "Why isn't Python finding my module?" or "Which version will Python import?"

#### Examples

**Example: Understanding Import Precedence**

```bash
$ reveal python://syspath

{
  "count": 12,
  "cwd": "/home/user/projects/myapp",
  "paths": [
    {
      "index": 0,
      "path": "(CWD: /home/user/projects/myapp)",
      "is_cwd": true,
      "exists": true,
      "type": "cwd",
      "priority": "highest"
    },
    {
      "index": 1,
      "path": "/home/user/.local/lib/python3.10/site-packages",
      "is_cwd": false,
      "exists": true,
      "type": "site-packages",
      "priority": "normal"
    },
    {
      "index": 2,
      "path": "/usr/lib/python3.10",
      "is_cwd": false,
      "exists": true,
      "type": "python_stdlib",
      "priority": "high"
    }
  ],
  "conflicts": [
    {
      "type": "cwd_precedence",
      "severity": "info",
      "message": "Current working directory takes precedence over site-packages",
      "note": "Local modules will shadow installed packages"
    }
  ],
  "summary": {
    "cwd_entries": 1,
    "site_packages": 2,
    "stdlib": 3,
    "pythonpath": 1,
    "other": 5
  }
}
```

**Key Insight**: `sys.path[0]` (CWD) has highest priority. If you have local code matching an installed package name, the local code wins.

### 3. Automated Diagnostics (`python://doctor`)

**Problem Solved**: "Is my Python environment healthy?" - one command to rule them all.

#### Examples

**Example 1: Healthy Environment**

```bash
$ reveal python://doctor

{
  "status": "healthy",
  "health_score": 100,
  "issues": [],
  "warnings": [],
  "info": [],
  "recommendations": []
}
```

**Example 2: Common Issues Detected**

```bash
$ reveal python://doctor

{
  "status": "warning",
  "health_score": 70,
  "issues": [
    {
      "category": "bytecode",
      "message": "Found 5 stale .pyc files",
      "impact": "Code changes may not take effect",
      "severity": "high"
    }
  ],
  "warnings": [
    {
      "category": "environment",
      "message": "No virtual environment detected",
      "impact": "Packages install globally, may cause conflicts"
    },
    {
      "category": "import_shadowing",
      "message": "CWD is sys.path[0] and contains 12 .py files",
      "impact": "Local modules may shadow installed packages"
    }
  ],
  "recommendations": [
    {
      "action": "clean_bytecode",
      "message": "Remove stale bytecode files",
      "commands": [
        "find . -type d -name __pycache__ -exec rm -rf {} +",
        "find . -name \"*.pyc\" -delete"
      ]
    },
    {
      "action": "create_venv",
      "message": "Consider using a virtual environment",
      "commands": [
        "python3 -m venv venv",
        "source venv/bin/activate",
        "pip install -r requirements.txt"
      ]
    }
  ]
}
```

**Checks Performed**:
1. ✅ Virtual environment activation
2. ✅ CWD shadowing (local code vs installed packages)
3. ✅ Stale bytecode (.pyc files newer than .py)
4. ✅ Python version compatibility
5. ✅ Editable installs (dev vs production)

## Complete API Reference

### Core Endpoints

| Endpoint | Returns | Example Use Case |
|----------|---------|------------------|
| `python://` | Environment overview | Quick health check |
| `python://version` | Detailed version info | Verify Python build |
| `python://env` | Environment config | Inspect sys.path, flags |
| `python://venv` | Virtual env status | Confirm venv activation |

### Package Management

| Endpoint | Returns | Example Use Case |
|----------|---------|------------------|
| `python://packages` | All installed packages | Audit dependencies |
| `python://packages/<name>` | Package details | Check version, location |
| `python://module/<name>` | Module analysis + conflicts | Debug import issues |

### Diagnostics

| Endpoint | Returns | Example Use Case |
|----------|---------|------------------|
| `python://doctor` | Automated health check | Pre-deployment validation |
| `python://syspath` | sys.path analysis | Understand import order |
| `python://debug/bytecode` | Stale .pyc detection | Fix "changes not working" |
| `python://imports` | Loaded modules | Memory/import debugging |

## Real-World Workflows

### Workflow 1: Debugging Package Version Issues

```bash
# 1. Check what Python sees
reveal python://module/problematic-package

# If conflict detected:
# 2. Understand sys.path
reveal python://syspath

# 3. Check pip installation
reveal python://packages/problematic-package

# 4. Run comprehensive check
reveal python://doctor
```

### Workflow 2: Pre-Deployment Health Check

```bash
# Single command validation
reveal python://doctor

# Should return:
# - status: "healthy"
# - health_score: >= 90
# - No stale bytecode
# - Proper venv activation (if expected)
```

### Workflow 3: Understanding Import Behavior

```bash
# Where will Python import from?
reveal python://syspath

# What's currently loaded?
reveal python://imports

# Check specific module
reveal python://module/mymodule
```

## Integration Patterns

### With CI/CD

```bash
#!/bin/bash
# pre-deploy-check.sh

# Run doctor check
result=$(reveal python://doctor --format=json)
health=$(echo "$result" | jq -r '.health_score')

if [ "$health" -lt 90 ]; then
  echo "❌ Environment health check failed (score: $health)"
  reveal python://doctor  # Show details
  exit 1
fi

echo "✅ Environment health check passed (score: $health)"
```

### With LLM Agents

When an LLM agent encounters Python environment issues:

```python
# Agent prompt enhancement
f"""
Debugging Python environment issue.

Step 1: Check module import
```bash
reveal python://module/{package_name}
```

Step 2: Run health check
```bash
reveal python://doctor
```

Analyze the output and provide fix.
"""
```

## Multi-Shot Prompting Examples (for LLMs)

The examples above demonstrate the **multi-shot prompting pattern** - by showing concrete input/output examples, LLMs can better understand how to use the tool.

### Pattern Template

```
Problem: [Specific issue]
Command: reveal python://[endpoint]
Output: [Actual JSON/text output]
Interpretation: [What this means]
Action: [What to do next]
```

## Troubleshooting

### Common Issues

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| "Wrong package version loading" | `python://module/pkg` | Check for CWD shadowing |
| "Changes not taking effect" | `python://debug/bytecode` | Clear stale .pyc files |
| "Module not found" | `python://syspath` | Verify module in sys.path |
| "Import errors" | `python://doctor` | Run full diagnostics |

## Performance Notes

- **Fast**: All operations complete in < 100ms
- **Safe**: Read-only, no filesystem modifications
- **Cacheable**: Results can be cached for repeated checks

## Related Adapters

For advanced import analysis, use the dedicated **imports://** adapter:
- `imports://path/to/file.py` - Import analysis with dependency tracking
- `imports://path/to/file.py?circular` - Circular import detection
- `imports://path/to/dir` - Multi-file import graph

See [ADAPTER_AUTHORING_GUIDE.md](ADAPTER_AUTHORING_GUIDE.md) for the full adapter list.

## Contributing

Found a bug or have a feature request? See the main Reveal repository.

## See Also

- [ADAPTER_AUTHORING_GUIDE.md](ADAPTER_AUTHORING_GUIDE.md) - Create custom adapters
- [ANALYZER_PATTERNS.md](ANALYZER_PATTERNS.md) - Code analysis patterns
- [RECIPES.md](RECIPES.md) - Practical Python examples
- [README.md](README.md) - Documentation hub

## License

MIT - Part of the Reveal project
