# Python Runtime Adapter Specification

**Status:** Planning
**Version:** v0.1.0
**Target Reveal:** v0.17.0+
**Created:** 2025-12-07

---

## Overview

The `python://` adapter provides runtime inspection and debugging capabilities for Python environments, complementing the existing static analysis tools (`ast://`) and environment inspection (`env://`).

### Design Philosophy

**Separation of Concerns:**
- `env://` - Raw environment variables (cross-language)
- `ast://` - Static source code analysis (cross-language)
- `python://` - Python runtime/tooling inspection (Python-specific)

**Key Principle:** `python://` inspects the **running Python environment**, not source code.

---

## Architecture

### Base Implementation

```python
# reveal/adapters/python.py

from .base import ResourceAdapter, register_adapter

@register_adapter('python')
class PythonAdapter(ResourceAdapter):
    """Adapter for Python runtime inspection via python:// URIs."""

    def __init__(self):
        """Initialize with runtime introspection capabilities."""
        self.runtime = PythonRuntime()

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get overview of Python environment."""
        return {
            'version': self.runtime.version_info(),
            'environment': self.runtime.env_summary(),
            'packages': self.runtime.packages_summary(),
            'imports': self.runtime.imports_summary(),
            'health': self.runtime.health_check()
        }

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get specific Python runtime element.

        Supported elements:
            - version: Python version details
            - env: Environment configuration
            - venv: Virtual environment status
            - packages: Installed packages
            - packages/<name>: Specific package info
            - imports: Loaded modules
            - imports/graph: Import dependency graph
            - debug/bytecode: .pyc issues
            - debug/syntax: Syntax errors in project
            - debug/circular: Circular import detection
        """
        # Route to appropriate handler
        return self._route_element(element_name, **kwargs)
```

---

## URI Structure

### Hierarchical Namespace

```
python://                           # Overview of Python environment
python://version                    # Python version info
python://env                        # Python environment config
python://venv                       # Virtual environment status
python://packages                   # All installed packages
python://packages/<name>            # Specific package details
python://imports                    # Currently loaded modules
python://imports/graph              # Import dependency visualization
python://imports/circular           # Circular import detection
python://debug                      # All debug checks
python://debug/bytecode             # .pyc timestamp issues
python://debug/syntax               # Syntax errors in project
python://debug/imports              # Import problems
```

---

## Endpoint Specifications

### Phase 1: Core Runtime (v0.17.0)

#### `python://version`

**Purpose:** Python version and implementation details

**Output:**
```yaml
version: "3.10.12"
implementation: "CPython"
compiler: "GCC 11.4.0"
build_date: "2024-04-23 14:20:45"
executable: "/usr/bin/python3"
prefix: "/usr"
platform: "linux"
architecture: "x86_64"
```

**Implementation:**
```python
import sys, platform

def version_info():
    return {
        'version': platform.python_version(),
        'implementation': platform.python_implementation(),
        'compiler': platform.python_compiler(),
        'build_date': platform.python_build()[1],
        'executable': sys.executable,
        'prefix': sys.prefix,
        'platform': sys.platform,
        'architecture': platform.machine()
    }
```

---

#### `python://env`

**Purpose:** Python's computed environment (not raw env vars - use `env://` for that)

**Output:**
```yaml
virtual_env:
  active: true
  path: "/home/user/project/.venv"
  prompt: "(venv)"
sys_path:
  - "/home/user/project"
  - "/home/user/project/.venv/lib/python3.10/site-packages"
  - "/usr/lib/python3.10"
  count: 12
python_path:
  from_env: "/custom/path"
  computed: true
flags:
  dont_write_bytecode: false
  optimize: 0
  verbose: 0
  interactive: false
```

**Implementation:**
```python
import sys, os

def env_summary():
    return {
        'virtual_env': detect_venv(),
        'sys_path': list(sys.path),
        'python_path': {
            'from_env': os.getenv('PYTHONPATH'),
            'computed': True
        },
        'flags': {
            'dont_write_bytecode': sys.dont_write_bytecode,
            'optimize': sys.flags.optimize,
            'verbose': sys.flags.verbose,
            'interactive': sys.flags.interactive
        }
    }
```

---

#### `python://venv`

**Purpose:** Virtual environment status and details

**Output:**
```yaml
status: "active"
path: "/home/user/project/.venv"
python_version: "3.10.12"
created: "2024-11-15"
prompt: "(venv)"
type: "venv"  # or "virtualenv", "conda", "pipenv"
packages_installed: 47
pip_version: "24.0"
site_packages: "/home/user/project/.venv/lib/python3.10/site-packages"
```

**Detection Logic:**
```python
def detect_venv():
    """Detect virtual environment."""
    # Check VIRTUAL_ENV
    venv_path = os.getenv('VIRTUAL_ENV')
    if venv_path:
        return {'active': True, 'path': venv_path, 'type': 'venv'}

    # Check sys.prefix vs sys.base_prefix
    if sys.prefix != sys.base_prefix:
        return {'active': True, 'path': sys.prefix, 'type': 'venv'}

    # Check conda
    if os.getenv('CONDA_DEFAULT_ENV'):
        return {'active': True, 'type': 'conda', ...}

    return {'active': False}
```

---

#### `python://packages`

**Purpose:** List all installed packages (like `pip list`)

**Output:**
```yaml
count: 47
packages:
  - name: "reveal-cli"
    version: "0.16.0"
    location: "/home/user/.local/lib/python3.10/site-packages"
    editable: false
  - name: "click"
    version: "8.1.7"
    location: "/usr/lib/python3/dist-packages"
    editable: false
  - name: "myproject"
    version: "0.1.0"
    location: "/home/user/project"
    editable: true
outdated:
  - name: "requests"
    installed: "2.28.0"
    latest: "2.31.0"
```

**Implementation:**
```python
import pkg_resources

def list_packages():
    """List installed packages."""
    packages = []
    for dist in pkg_resources.working_set:
        packages.append({
            'name': dist.project_name,
            'version': dist.version,
            'location': dist.location,
            'editable': is_editable_install(dist)
        })
    return packages
```

---

#### `python://packages/<name>`

**Purpose:** Detailed information about a specific package

**Example:** `python://packages/reveal-cli`

**Output:**
```yaml
name: "reveal-cli"
version: "0.16.0"
summary: "Semantic code exploration with progressive disclosure"
author: "Progressive Reveal Contributors"
license: "MIT"
location: "/home/user/.local/lib/python3.10/site-packages"
requires_python: ">=3.8"
dependencies:
  - "click>=8.0"
  - "pathspec>=0.11"
installed_files_count: 42
size: "245 KB"
installed_date: "2025-12-04"
editable: false
homepage: "https://github.com/Semantic-Infrastructure-Lab/reveal"
entry_points:
  console_scripts:
    - "reveal = reveal.main:cli"
```

---

#### `python://imports`

**Purpose:** Currently loaded modules in `sys.modules`

**Output:**
```yaml
count: 247
loaded:
  - name: "sys"
    file: null  # built-in
    package: null
  - name: "requests"
    file: "/usr/lib/python3/dist-packages/requests/__init__.py"
    package: "requests"
    size: "47 KB"
  - name: "myapp.models"
    file: "/home/user/project/myapp/models.py"
    package: "myapp"
recent:
  - "requests"
  - "urllib3"
  - "certifi"
memory_estimate: "~45 MB"
```

**Implementation:**
```python
import sys

def list_imports():
    """List currently loaded modules."""
    modules = []
    for name, module in sys.modules.items():
        if module is None:
            continue
        modules.append({
            'name': name,
            'file': getattr(module, '__file__', None),
            'package': getattr(module, '__package__', None)
        })
    return modules
```

---

#### `python://debug/bytecode`

**Purpose:** Detect stale .pyc files and bytecode issues

**Output:**
```yaml
status: "issues_found"
issues:
  - type: "stale_bytecode"
    severity: "warning"
    file: "lib/mymodule.py"
    pyc_file: "__pycache__/mymodule.cpython-310.pyc"
    problem: ".pyc is NEWER than source (stale bytecode)"
    source_mtime: "2025-12-07 09:55:00"
    pyc_mtime: "2025-12-07 10:00:00"
    fix: "rm __pycache__/mymodule.cpython-310.pyc"

  - type: "orphaned_bytecode"
    severity: "info"
    pyc_file: "old_code.pyc"
    problem: "No matching .py file found"
    fix: "find . -name '*.pyc' -delete"

  - type: "version_mismatch"
    severity: "warning"
    directory: "__pycache__/"
    problem: "Mixed Python versions"
    found: ["cpython-310.pyc", "cpython-311.pyc"]
    fix: "python -m compileall -f ."

summary:
  total_issues: 3
  warnings: 2
  info: 1
  errors: 0
```

**Implementation:**
```python
from pathlib import Path

def check_bytecode(root_path='.'):
    """Check for bytecode issues."""
    issues = []

    # Find all .pyc files
    for pyc_file in Path(root_path).rglob('**/*.pyc'):
        # Get corresponding .py file
        py_file = pyc_to_source(pyc_file)

        if not py_file.exists():
            issues.append({
                'type': 'orphaned_bytecode',
                'severity': 'info',
                'pyc_file': str(pyc_file),
                'problem': 'No matching .py file found'
            })
        elif pyc_file.stat().st_mtime > py_file.stat().st_mtime:
            issues.append({
                'type': 'stale_bytecode',
                'severity': 'warning',
                'file': str(py_file),
                'pyc_file': str(pyc_file),
                'problem': '.pyc is NEWER than source (stale bytecode)'
            })

    return issues
```

---

### Phase 2: Advanced Features (v0.18.0)

#### `python://imports/graph`

**Purpose:** Visualize import dependencies

**Output:**
```yaml
format: "tree"
root: "myapp"
dependencies:
  myapp:
    - myapp.utils
    - myapp.models
    - requests
  myapp.utils:
    - myapp.config
    - os
    - sys
  myapp.models:
    - myapp.schemas
    - sqlalchemy
  myapp.schemas:
    - myapp.models  # ⚠️ Circular!
```

---

#### `python://imports/circular`

**Purpose:** Detect circular imports

**Output:**
```yaml
circular_imports_found: true
cycles:
  - modules: ["myapp.models", "myapp.schemas"]
    path:
      - "myapp.models imports myapp.schemas (line 12)"
      - "myapp.schemas imports myapp.models (line 8)"
    severity: "warning"
    suggestion: "Use TYPE_CHECKING or move imports to functions"
```

---

#### `python://debug/syntax`

**Purpose:** Find Python files with syntax errors

**Output:**
```yaml
syntax_errors:
  - file: "broken.py"
    line: 45
    error: "SyntaxError: invalid syntax"
    code: "def foo()"  # Missing colon

  - file: "old.py"
    line: 12
    error: "IndentationError: unexpected indent"
```

---

### Phase 3: Project Intelligence (v0.19.0)

#### `python://project`

**Purpose:** Auto-detect project type and structure

**Output:**
```yaml
type: "django"
detected_patterns:
  - "manage.py found"
  - "settings.py with INSTALLED_APPS"
details:
  settings: "myproject/settings.py"
  apps:
    - "users"
    - "blog"
    - "api"
  database: "PostgreSQL"
  entry_point: "manage.py"
```

---

#### `python://tests`

**Purpose:** Discover and analyze tests

**Output:**
```yaml
framework: "pytest"
test_files: 15
test_count: 143
results:
  passed: 124
  failed: 0
  skipped: 19
coverage: "67%"
coverage_file: ".coverage"
```

---

## Integration with Existing Adapters

### Clear Boundaries

| Task | Correct Adapter | Wrong Adapter |
|------|----------------|---------------|
| Get PATH environment variable | `env://PATH` | ~~`python://env/PATH`~~ |
| Get sys.path (Python's import paths) | `python://env` | ~~`env://PYTHONPATH`~~ |
| Analyze function complexity (static) | `ast://file.py --check` | ~~`python://complexity`~~ |
| Find loaded modules (runtime) | `python://imports` | ~~`ast://file.py`~~ |
| Detect circular imports (runtime) | `python://imports/circular` | ~~`ast://`~~ |

---

## Output Formats

Support all standard Reveal formats:

```bash
# Default text output
reveal python://packages

# JSON for scripting
reveal python://packages --format=json

# Typed output (with type annotations)
reveal python://imports --format=typed

# Grep-friendly output
reveal python://debug/bytecode --format=grep
```

---

## Usage Examples

### Common Developer Workflows

```bash
# Quick environment check
reveal python://

# Debug "my changes aren't working"
reveal python://debug/bytecode

# Check virtual environment
reveal python://venv

# Find what's imported
reveal python://imports | grep myapp

# Package audit
reveal python://packages --format=json | jq '.outdated'

# Find circular imports
reveal python://imports/circular

# Get package details
reveal python://packages/reveal-cli
```

### AI Agent Workflows

```bash
# Agent debugging import errors
reveal python://imports/circular --format=json

# Agent checking environment before running code
reveal python://env --format=typed

# Agent verifying package installation
reveal python://packages/requests

# Agent scanning for issues
reveal python://debug --format=json
```

---

## Implementation Plan

### Phase 1: Core Runtime (v0.17.0) - ~300 LOC

**Priority:** High
**Complexity:** Low
**Value:** High

**Endpoints:**
- `python://version` ✓
- `python://env` ✓
- `python://venv` ✓
- `python://packages` ✓
- `python://packages/<name>` ✓
- `python://imports` ✓
- `python://debug/bytecode` ✓

**Implementation Time:** 4-6 hours

---

### Phase 2: Advanced Debugging (v0.18.0) - ~200 LOC

**Priority:** Medium
**Complexity:** Medium
**Value:** High

**Endpoints:**
- `python://imports/graph` ✓
- `python://imports/circular` ✓
- `python://debug/syntax` ✓

**Implementation Time:** 3-4 hours

---

### Phase 3: Project Intelligence (v0.19.0) - ~400 LOC

**Priority:** Low
**Complexity:** High
**Value:** Medium

**Endpoints:**
- `python://project` ✓
- `python://tests` ✓
- `python://quality` ✓
- `python://security` ✓

**Implementation Time:** 8-10 hours

---

## Testing Strategy

### Unit Tests

```python
# tests/adapters/test_python.py

def test_python_version():
    adapter = PythonAdapter()
    result = adapter.get_element('version')
    assert 'version' in result
    assert 'implementation' in result

def test_bytecode_detection():
    # Create test files with stale .pyc
    adapter = PythonAdapter()
    result = adapter.get_element('debug/bytecode')
    assert result['status'] in ['clean', 'issues_found']

def test_imports_listing():
    adapter = PythonAdapter()
    result = adapter.get_element('imports')
    assert 'sys' in [m['name'] for m in result['loaded']]
```

### Integration Tests

```bash
# Test full workflow
reveal python:// --format=json | jq '.health'
reveal python://debug/bytecode
reveal python://packages/reveal-cli --format=typed
```

---

## Security Considerations

### Sensitive Data

**DO NOT expose:**
- API keys in environment variables (already handled by `env://` redaction)
- Database passwords in package configs
- Private package sources/credentials

**Pattern:**
```python
SENSITIVE_PATTERNS = [
    'PASSWORD', 'SECRET', 'TOKEN', 'KEY', 'CREDENTIAL',
    'API_KEY', 'AUTH', 'PRIVATE'
]

def redact_if_sensitive(key, value):
    if any(pattern in key.upper() for pattern in SENSITIVE_PATTERNS):
        return '***REDACTED***'
    return value
```

---

## Performance Considerations

### Lazy Loading

```python
class PythonAdapter(ResourceAdapter):
    def __init__(self):
        self._packages_cache = None
        self._imports_cache = None

    @property
    def packages(self):
        if self._packages_cache is None:
            self._packages_cache = self._load_packages()
        return self._packages_cache
```

### Caching Strategy

- Cache expensive operations (package listing)
- TTL: 60 seconds for imports, 5 minutes for packages
- Invalidate on environment changes

---

## Error Handling

### Graceful Degradation

```python
def get_element(self, element_name: str, **kwargs):
    try:
        return self._route_element(element_name, **kwargs)
    except ImportError as e:
        return {
            'error': f'Required module not available: {e}',
            'suggestion': 'pip install required dependencies'
        }
    except PermissionError:
        return {
            'error': 'Permission denied',
            'suggestion': 'Check file permissions or run with appropriate privileges'
        }
```

---

## Documentation

### Self-Documenting Help

```python
@staticmethod
def get_help() -> Dict[str, Any]:
    """Get help documentation for python:// adapter."""
    return {
        'name': 'python',
        'description': 'Inspect Python runtime environment and debug common issues',
        'syntax': 'python://[element]',
        'examples': [
            {
                'uri': 'python://',
                'description': 'Overview of Python environment'
            },
            {
                'uri': 'python://debug/bytecode',
                'description': 'Check for stale .pyc files'
            },
            {
                'uri': 'python://packages/requests',
                'description': 'Details about requests package'
            }
        ],
        'elements': {
            'version': 'Python version and implementation details',
            'env': "Python's computed environment (sys.path, flags)",
            'venv': 'Virtual environment status',
            'packages': 'Installed packages (pip list)',
            'imports': 'Currently loaded modules',
            'debug/bytecode': 'Detect stale .pyc files',
        },
        'see_also': [
            'reveal env:// - Environment variables',
            'reveal ast:// - Static code analysis',
            'reveal help://python - This help'
        ]
    }
```

---

## Future Extensions

### Potential Additions

```bash
python://profile              # cProfile integration
python://memory               # Memory profiling
python://security             # Vulnerability scanning
python://notebooks            # Jupyter notebook detection
python://migrations           # Django/Alembic migrations
python://coverage             # Code coverage analysis
python://types                # Type hint coverage
python://quality              # Aggregate code quality
```

---

## References

- **Base Adapter:** `reveal/adapters/base.py`
- **Example Adapter:** `reveal/adapters/env.py`
- **Adapter Registration:** `@register_adapter()` decorator
- **URI Routing:** `reveal/main.py:handle_uri()`

---

## Changelog

### v0.1.0 (2025-12-07)
- Initial specification
- Phase 1-3 endpoint definitions
- Implementation plan
- Integration with existing adapters

---

## Approvals

- [ ] Design reviewed
- [ ] Separation of concerns validated
- [ ] Security considerations addressed
- [ ] Performance implications assessed
- [ ] Documentation complete
- [ ] Ready for implementation
