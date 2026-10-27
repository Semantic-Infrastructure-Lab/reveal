---
title: reveal:// Adapter - Reference Implementation
category: guide
help_topic: reveal-guide
help_description: "reveal:// adapter reference"
help_category: feature_guides
---
# reveal:// Adapter - Reference Implementation

**Purpose**: Self-inspection and validation adapter demonstrating reveal's extensibility

**Use Case**: Dogfooding - reveal uses its own tools to validate itself

**Key Insight**: This shows users how to create custom adapters for ANY resource, not just files.

---

## Quick Start

```bash
# Inspect reveal's structure
reveal reveal://

# Validate reveal's completeness
reveal reveal:// --check

# Get help about reveal://
reveal help://reveal

# List all adapters
reveal reveal://adapters

# Debug configuration
reveal reveal://config              # Show active config with sources
reveal reveal://config --format json # JSON output for scripting

# See all validation rules
reveal --rules --all | grep V0
```

`reveal://` and the V-series rules are internal self-inspection, hidden from
`reveal --adapters` / `reveal --rules` unless you pass `--all`.

---

## What This Demonstrates

### 1. **Non-File Adapters**

Adapters aren't limited to file types. They can inspect ANY resource:

| Adapter | Inspects | Example |
|---------|----------|---------|
| `git://` | Git repository | `reveal git://.` |
| `env://` | Environment vars | `reveal env://PATH` |
| `json://` | JSON data | `reveal json://file.json/path` |
| `reveal://` | **Reveal itself** | `reveal reveal://` |
| **YOUR-THING://** | Whatever you want! | `reveal project://` |

**Pattern**: `scheme://[resource][/path]`

### 2. **Validation Rules**

The V-series rules (V001–V042, 41 rules; there is no V010; `reveal --rules --all` lists them) check reveal's internal state:

```python
# reveal/rules/validation/V001.py
class V001(BaseRule):
    """Validate that all supported file types have help documentation."""

    code = "V001"
    message = "File type analyzer missing help documentation"
    category = RulePrefix.V
    severity = Severity.MEDIUM

    def check(self, file_path, structure, content):
        # Check if every analyzer has help docs
        # ...
```

**What Makes This Special**: These rules run on `reveal://` URIs, not files.

### 3. **Complete Working Example**

Look at `reveal/adapters/reveal/` (package) to see:
- How to create an adapter
- How to implement `get_structure()`
- How to format output (text/JSON)
- How to integrate with help system

Then look at `reveal/rules/validation/V*.py` for:
- How to write validation rules
- How to check cross-cutting concerns
- How to provide actionable suggestions

---

## Architecture

### Components

```
reveal/
├── adapters/
│   └── reveal/            # Meta-adapter package (inspects reveal)
│       ├── adapter.py     #   RevealAdapter: get_structure(), check()
│       ├── structure.py, operations.py, renderer.py, ...
├── rules/
│   └── validation/        # V-series rules (validate reveal)
│       ├── V001.py        # Help completeness
│       ├── V002.py        # Analyzer registration
│       ├── V003.py        # Feature matrix
│       ├── V004.py        # Test coverage
│       ├── V005.py        # Help file sync
│       ├── V006.py        # Output format support
│       └── ...            # 35 more, up to V042
└── docs/adapters/
    └── REVEAL_ADAPTER_GUIDE.md  # This file
```

### How It Works

```
User runs: reveal reveal:// --check
           ↓
1. Main CLI recognizes reveal:// URI
           ↓
2. Loads RevealAdapter from registry
           ↓
3. RevealAdapter.get_structure() returns:
   - List of analyzers
   - List of adapters
   - List of rules
           ↓
4. --check flag triggers validation rules
           ↓
5. V-series rules run checks, return Detection objects
           ↓
6. Output formatted and displayed
```

---

## Use Cases for Custom Adapters

### Example 1: Project Structure Validator

```python
# my_project/validators/project_adapter.py
from reveal.adapters.base import ResourceAdapter, register_adapter

@register_adapter('project')
class ProjectAdapter(ResourceAdapter):
    """Validate project structure."""

    def get_structure(self):
        return {
            'modules': self._get_modules(),
            'tests': self._get_tests(),
            'docs': self._get_docs()
        }

# Then create rules:
# rules/P001.py - Every module has tests
# rules/P002.py - Every feature has docs
# rules/P003.py - No circular dependencies
```

**Usage**: `reveal project:// --check`

### Example 2: API Endpoint Validator

```python
@register_adapter('api')
class ApiAdapter(ResourceAdapter):
    """Inspect and validate API endpoints."""

    def __init__(self, url):
        self.url = url

    def get_structure(self):
        response = requests.get(self.url)
        return {
            'status': response.status_code,
            'headers': dict(response.headers),
            'body': response.json()
        }

# Rules:
# A001: Response time < 200ms
# A002: Returns valid JSON
# A003: Has required fields
```

**Usage**: `reveal api://https://myapi.com/health --check`

### Example 3: Docker Container Inspector

```python
@register_adapter('docker')
class DockerAdapter(ResourceAdapter):
    """Inspect running containers."""

    def __init__(self, container_name):
        self.container = container_name

    def get_structure(self):
        # Use docker SDK to inspect container
        return {
            'image': ...,
            'env_vars': ...,
            'volumes': ...,
            'health': ...
        }

# Rules:
# D001: Image not using :latest
# D002: No secrets in env vars
# D003: Health check configured
```

**Usage**: `reveal docker://my-container --check`

---

## Implementation Guide

### Step 1: Create the Adapter

An adapter needs a renderer: `@register_renderer` stacked under `@register_adapter`.
Without it `reveal mything://` exits 1 with `No renderer registered for scheme 'mything'`.
Text and JSON output both go through the renderer's `render_structure`.

```python
# .reveal/adapters/mything/my_adapter.py
from typing import Optional

from reveal.adapters.base import ResourceAdapter, register_adapter, register_renderer
from reveal.utils import print_json_result


class MyThingRenderer:
    @staticmethod
    def render_structure(result, format='text'):
        if format == 'json':
            print_json_result(result)
            return
        print(f"My Thing: {result['metadata']['count']} item(s)")
        for item in result['items']:
            print(f"  {item}")

    @staticmethod
    def render_check(result, format='text', **kwargs):
        """Only needed if the adapter implements check() (Step 3)."""
        if format == 'json':
            print_json_result({**result, 'detections': [d.to_dict() for d in result['detections']]})
            return
        for d in result['detections']:
            print(f"{d.file_path}:{d.line} {d.rule_code} {d.message}")


@register_adapter('mything')
@register_renderer(MyThingRenderer)
class MyThingAdapter(ResourceAdapter):
    """Inspect my thing."""

    LEGACY_INIT = False  # construct with the canonical signature below

    @staticmethod
    def get_help():
        """Required for help:// integration."""
        return {
            'name': 'mything',
            'description': 'Inspect my thing',
            'syntax': 'mything://[resource]',
            'examples': [
                {'uri': 'mything://', 'description': 'List all things'}
            ]
        }

    def __init__(self, resource: str = '', query: Optional[str] = None):
        super().__init__(resource, query)

    def get_structure(self, **kwargs):
        """Core method - return Dict describing structure."""
        items = self._get_items()
        return {
            'type': 'mything',
            'items': items,
            'metadata': {'count': len(items)},
        }

    def _get_items(self):
        return ['alpha', 'beta']
```

### Step 2: Register the Adapter

reveal discovers plugin adapters in `<cwd>/.reveal/adapters/<name>/` (project-local) and
`~/.reveal/adapters/<name>/` (user-global) and imports each package; the decorators register
the scheme as a side effect. Plugins must import `reveal.adapters.base` absolutely, since they
live outside the reveal package.

```python
# .reveal/adapters/mything/__init__.py
from .my_adapter import MyThingAdapter

__all__ = ['MyThingAdapter']
```

`examples/plugin-adapters/tasks-adapter/` in the reveal repository is a complete working
plugin with this layout.

### Step 3: Create Validation Rules (Optional)

Rules are discovered from a category directory under `<project>/.reveal/rules/` (project-local)
or `~/.local/share/reveal/rules/` (user-global). `--check` runs them against a custom URI only
when the adapter implements `check()`; otherwise reveal prints
`Note: --check has no effect on mything:// queries -- not supported by this adapter.`

```python
# .reveal/rules/custom/C001.py
from reveal.rules.base import BaseRule, Detection, RulePrefix, Severity

class C001(BaseRule):
    """Check for specific issue in my thing."""

    code = "C001"
    message = "Issue found in my thing"
    category = RulePrefix.M  # Or create custom prefix
    severity = Severity.HIGH
    file_patterns = ['*']

    def check(self, file_path, structure, content):
        detections = []

        # Only run for mything:// URIs
        if not file_path.startswith('mything://'):
            return detections

        # Your validation logic here
        if something_wrong:
            detections.append(self.create_detection(
                file_path=file_path,
                line=1,
                message="Specific issue found",
                suggestion="How to fix it",
                context="Why this matters"
            ))

        return detections
```

And on the adapter, a `check()` that hands the URI and its structure to the rule registry:

```python
    def check(self, select=None, ignore=None):
        """Makes `reveal mything:// --check` run rules against this URI."""
        from reveal.rules import RuleRegistry
        detections = RuleRegistry.check_file('mything://', self.get_structure(), '',
                                             select=select, ignore=ignore)
        return {'type': 'mything_check', 'detections': detections, 'total': len(detections),
                'exit_code': 1 if detections else 0}
```

### Step 4: Test It

```bash
# Basic usage (from the directory that holds .reveal/)
reveal mything://

# With validation (exits 1 when a rule reports a detection)
reveal mything:// --check

# Get help
reveal help://mything

# JSON output
reveal mything:// --format=json
```

---

## Best Practices

### 1. **Progressive Disclosure**

Show overview first, details on demand:

```python
def get_structure(self):
    if self.resource:
        # Specific resource requested
        return self._get_detailed_view(self.resource)
    else:
        # Overview
        return self._get_summary()
```

### 2. **Clear Error Messages**

```python
detections.append(self.create_detection(
    file_path=path,
    line=line_num,
    message="What is wrong (concise)",
    suggestion="How to fix it (actionable)",
    context="Why this matters (educational)"
))
```

### 3. **Support Multiple Formats**

Always support JSON output for scripting, in the renderer's `render_structure`:

```python
@staticmethod
def render_structure(result, format='text'):
    if format == 'json':
        print_json_result(result)  # from reveal.utils
        return

    # Text format for humans
    print(format_text(result))
```

### 4. **Good Help Documentation**

Follow the help schema (see ADAPTER_AUTHORING_GUIDE.md):

```python
@staticmethod
def get_help():
    return {
        'name': 'adapter-name',
        'description': 'One-line description',
        'syntax': 'scheme://[resource]',
        'examples': [...],  # Required
        'workflows': [...], # Recommended
        'try_now': [...],   # Executable examples
    }
```

---

## Real-World Applications

### CI/CD Integration

```yaml
# .github/workflows/validate.yml
- name: Validate Project Structure
  run: |
    reveal project:// --check
    reveal api://http://localhost:8080 --check
    reveal docker://test-container --check
```

### Development Workflow

```bash
# Pre-commit hook
#!/bin/bash
reveal project:// --check --select P001,P002
if [ $? -ne 0 ]; then
    echo "Project validation failed"
    exit 1
fi
```

### Monitoring

```bash
# Health check script
#!/bin/bash
OUTPUT=$(reveal api://https://api.example.com --check --format=json)
ISSUES=$(echo $OUTPUT | jq '.detections | length')

if [ $ISSUES -gt 0 ]; then
    # Send alert
    echo "API health check failed: $ISSUES issues"
fi
```

---

## Why reveal:// Exists

### The Meta-Point

**reveal:// proves that reveal is a platform, not just a tool.**

By using reveal to validate itself, we demonstrate:

1. **Extensibility**: Adapters work for ANY resource
2. **Consistency**: Same patterns for files, URIs, and meta-resources
3. **Dogfooding**: We use our own tools (quality forcing function)
4. **Teaching**: Complete working example users can study and copy

### The Practical Point

reveal:// catches real issues:

- ✓ Missing help documentation
- ✓ Analyzers without tests
- ✓ Inconsistent feature support
- ✓ Broken help file references

Running `reveal reveal:// --check` in CI ensures reveal stays well-maintained.

---

## Comparison: Tests vs. Validation Rules

| Aspect | pytest Tests | Validation Rules |
|--------|--------------|------------------|
| **Purpose** | Verify code works | Verify completeness |
| **Scope** | Unit/integration | Cross-cutting concerns |
| **When Run** | CI, local testing | Anytime via CLI |
| **Output** | Pass/fail | Detections with suggestions |
| **Discoverability** | Need to know filename | `reveal --rules --all`, `reveal help://` |
| **Example** | `test_markdown_works()` | V001: Every analyzer has help |

**Both are valuable** - tests verify correctness, validation rules verify structure.

---

## Learning Path

1. **Study reveal://** - Read the `reveal/adapters/reveal/` package (adapter.py, renderer.py, operations.py, etc.)
2. **Study V-series rules** - Read `reveal/rules/validation/V*.py` (V001-V042)
3. **Run it yourself** - `reveal reveal:// --check`
4. **Adapt the pattern** - Create your own `project://` or `api://` adapter
5. **Share it** - Contribute back if useful to others!

---

## Resources

**Code**:
- Adapter: `reveal/adapters/reveal/` (package)
- Rules: `reveal/rules/validation/V*.py`
- Base classes: `reveal/adapters/base.py`, `reveal/rules/base.py`

**Documentation**:
- Adapter authoring: `reveal/docs/development/ADAPTER_AUTHORING_GUIDE.md`

**Help**:
```bash
reveal help://reveal        # This adapter's help
reveal help://adapters      # All adapters
reveal --rules --all        # All rules, including the V-series self-checks
reveal help://adapter-authoring  # How to create adapters
```

---

## Questions?

1. **Why not just use pytest?**
   - Validation rules check structural properties (completeness, consistency)
   - Tests check behavioral properties (correctness, functionality)
   - Both are valuable, serve different purposes

2. **Can I use this pattern in my project?**
   - Yes! That's why it exists - as a reference implementation
   - Copy the pattern, adapt to your needs
   - Consider contributing back if generally useful

3. **Do I need to create rules for my adapter?**
   - No - adapters can be pure inspection tools
   - Rules are optional, for validation use cases
   - Start simple (just the adapter), add rules if needed

4. **Where do custom adapters go?**
   - Project-local: `<project>/.reveal/adapters/<name>/`; user-global: `~/.reveal/adapters/<name>/`
   - Each needs an `__init__.py` that imports the adapter module, and absolute imports
     from `reveal.adapters.base`; reveal imports these packages itself, so nothing else
     needs to import them
   - Custom rules go in a category directory under `<project>/.reveal/rules/` or
     `~/.local/share/reveal/rules/` (for example `.reveal/rules/custom/C001.py`)
   - Or contribute to reveal if generally useful!

---

**Remember**: reveal:// isn't just a self-check tool - it's a **demonstration that reveal is extensible for ANY inspection or validation task**.

Your imagination is the limit. What will you inspect?

## See Also

- [ADAPTER_AUTHORING_GUIDE.md](../development/ADAPTER_AUTHORING_GUIDE.md) - Create custom adapters
- [ANALYZER_PATTERNS.md](../development/ANALYZER_PATTERNS.md) - Analysis patterns for meta-inspection
- [HELP_SYSTEM_GUIDE.md](../development/HELP_SYSTEM_GUIDE.md) - Integrate with help system
- [README.md](../README.md) - Documentation hub
