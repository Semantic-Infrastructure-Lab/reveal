# Python Adapter Implementation Roadmap

**Related:** [PYTHON_ADAPTER_SPEC.md](./PYTHON_ADAPTER_SPEC.md)
**Status:** Planning
**Target:** v0.17.0 - v0.19.0

---

## Quick Start (Prototype)

### Minimal Viable Implementation

**Goal:** Get `python://version` working in 30 minutes

```python
# reveal/adapters/python.py

import sys
import platform
from typing import Dict, Any, Optional
from .base import ResourceAdapter, register_adapter


@register_adapter('python')
class PythonAdapter(ResourceAdapter):
    """Adapter for Python runtime inspection."""

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get overview of Python environment."""
        return {
            'version': platform.python_version(),
            'implementation': platform.python_implementation(),
            'executable': sys.executable,
            'virtual_env': self._detect_venv(),
            'packages_count': len(list(self._get_packages())),
            'modules_loaded': len(sys.modules)
        }

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get specific element."""
        handlers = {
            'version': self._get_version,
            'env': self._get_env,
            'venv': self._get_venv,
            'packages': self._get_packages_list,
            'imports': self._get_imports,
        }

        # Handle nested paths like 'debug/bytecode'
        parts = element_name.split('/', 1)
        base = parts[0]

        if base in handlers:
            return handlers[base](**kwargs)

        # Handle debug/* namespace
        if base == 'debug' and len(parts) > 1:
            return self._handle_debug(parts[1], **kwargs)

        return None

    def _get_version(self, **kwargs) -> Dict[str, Any]:
        """Get Python version details."""
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

    def _detect_venv(self) -> Dict[str, Any]:
        """Detect if in virtual environment."""
        import os
        venv_path = os.getenv('VIRTUAL_ENV')
        if venv_path:
            return {'active': True, 'path': venv_path}
        if sys.prefix != sys.base_prefix:
            return {'active': True, 'path': sys.prefix}
        return {'active': False}

    def _get_venv(self, **kwargs) -> Dict[str, Any]:
        """Get detailed virtual environment info."""
        venv_info = self._detect_venv()
        if venv_info['active']:
            import os
            venv_info.update({
                'python_version': platform.python_version(),
                'type': 'venv',  # Could detect virtualenv, conda, etc.
                'prompt': os.getenv('VIRTUAL_ENV', '').split('/')[-1]
            })
        return venv_info

    def _get_env(self, **kwargs) -> Dict[str, Any]:
        """Get Python environment details."""
        import os
        return {
            'virtual_env': self._detect_venv(),
            'sys_path': list(sys.path),
            'python_path': os.getenv('PYTHONPATH'),
            'flags': {
                'dont_write_bytecode': sys.dont_write_bytecode,
                'optimize': sys.flags.optimize,
                'verbose': sys.flags.verbose
            }
        }

    def _get_packages(self):
        """Generator for installed packages."""
        try:
            import pkg_resources
            for dist in pkg_resources.working_set:
                yield dist
        except ImportError:
            # Fallback for Python 3.8+
            import importlib.metadata
            for dist in importlib.metadata.distributions():
                yield dist

    def _get_packages_list(self, **kwargs) -> Dict[str, Any]:
        """List all installed packages."""
        packages = []
        for dist in self._get_packages():
            try:
                # pkg_resources API
                packages.append({
                    'name': dist.project_name,
                    'version': dist.version,
                    'location': dist.location
                })
            except AttributeError:
                # importlib.metadata API
                packages.append({
                    'name': dist.name,
                    'version': dist.version,
                    'location': str(dist._path.parent)
                })

        return {
            'count': len(packages),
            'packages': sorted(packages, key=lambda p: p['name'].lower())
        }

    def _get_imports(self, **kwargs) -> Dict[str, Any]:
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

        return {
            'count': len(modules),
            'loaded': sorted(modules, key=lambda m: m['name'])
        }

    def _handle_debug(self, debug_type: str, **kwargs) -> Dict[str, Any]:
        """Handle debug/* endpoints."""
        if debug_type == 'bytecode':
            return self._check_bytecode(**kwargs)

        return {'error': f'Unknown debug type: {debug_type}'}

    def _check_bytecode(self, root_path: str = '.', **kwargs) -> Dict[str, Any]:
        """Check for bytecode issues."""
        from pathlib import Path

        issues = []

        # Find all .pyc files
        root = Path(root_path)
        for pyc_file in root.rglob('**/*.pyc'):
            # Skip if in __pycache__
            if '__pycache__' not in pyc_file.parts:
                issues.append({
                    'type': 'old_style_pyc',
                    'severity': 'info',
                    'file': str(pyc_file),
                    'problem': 'Python 2 style .pyc (should be in __pycache__)'
                })
                continue

            # Get corresponding .py file
            py_file = self._pyc_to_source(pyc_file)

            if not py_file.exists():
                issues.append({
                    'type': 'orphaned_bytecode',
                    'severity': 'info',
                    'pyc_file': str(pyc_file),
                    'problem': 'No matching .py file found',
                    'fix': f'rm {pyc_file}'
                })
            elif pyc_file.stat().st_mtime > py_file.stat().st_mtime:
                issues.append({
                    'type': 'stale_bytecode',
                    'severity': 'warning',
                    'file': str(py_file),
                    'pyc_file': str(pyc_file),
                    'problem': '.pyc is NEWER than source',
                    'fix': f'rm {pyc_file}'
                })

        return {
            'status': 'issues_found' if issues else 'clean',
            'issues': issues,
            'summary': {
                'total': len(issues),
                'warnings': len([i for i in issues if i['severity'] == 'warning']),
                'info': len([i for i in issues if i['severity'] == 'info'])
            }
        }

    @staticmethod
    def _pyc_to_source(pyc_file) -> 'Path':
        """Convert .pyc path to .py path."""
        from pathlib import Path

        # Example: __pycache__/module.cpython-310.pyc -> module.py
        if '__pycache__' in pyc_file.parts:
            parent = pyc_file.parent.parent
            # Remove cpython-XXX suffix
            name = pyc_file.stem.split('.')[0]
            return parent / f"{name}.py"

        # Old style: module.pyc -> module.py
        return pyc_file.with_suffix('.py')

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation."""
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
                    'uri': 'python://version',
                    'description': 'Detailed Python version information'
                },
                {
                    'uri': 'python://venv',
                    'description': 'Virtual environment status'
                },
                {
                    'uri': 'python://packages',
                    'description': 'List all installed packages'
                },
                {
                    'uri': 'python://imports',
                    'description': 'Currently loaded modules'
                },
                {
                    'uri': 'python://debug/bytecode',
                    'description': 'Check for stale .pyc files'
                }
            ],
            'elements': {
                'version': 'Python version and build details',
                'env': 'Python environment (sys.path, flags)',
                'venv': 'Virtual environment status',
                'packages': 'Installed packages',
                'imports': 'Loaded modules',
                'debug/bytecode': 'Bytecode issues'
            },
            'see_also': [
                'reveal env:// - Environment variables',
                'reveal ast:// - Static code analysis'
            ]
        }
```

---

## Phase 1 Checklist (v0.17.0)

### Core Implementation

- [ ] Create `reveal/adapters/python.py`
- [ ] Implement basic adapter structure
- [ ] Add `@register_adapter('python')` decorator
- [ ] Implement `get_structure()` method
- [ ] Implement `get_element()` routing

### Endpoints

- [ ] `python://` - Overview
- [ ] `python://version` - Version info
- [ ] `python://env` - Environment details
- [ ] `python://venv` - Virtual environment
- [ ] `python://packages` - Package list
- [ ] `python://imports` - Loaded modules
- [ ] `python://debug/bytecode` - Bytecode check

### Testing

- [ ] Unit tests for each endpoint
- [ ] Test with/without virtual environment
- [ ] Test bytecode detection
- [ ] Test package listing (pkg_resources + importlib.metadata)
- [ ] Cross-platform testing (Linux, macOS, Windows)

### Documentation

- [ ] Add to README.md
- [ ] Update CHANGELOG.md
- [ ] Add examples to help system
- [ ] Update `reveal --agent-help`

### Release

- [ ] Version bump to 0.17.0
- [ ] Tag and publish to PyPI
- [ ] GitHub release notes

---

## Phase 2 Checklist (v0.18.0)

### Advanced Import Analysis

- [ ] `python://imports/graph` - Dependency graph
- [ ] `python://imports/circular` - Circular import detection
- [ ] `python://debug/syntax` - Syntax error detection

### Implementation Notes

**Import Graph:**
```python
def _build_import_graph(self, module_name: str) -> Dict:
    """Build import dependency graph."""
    import importlib
    import ast

    graph = {}
    visited = set()

    def analyze_module(name):
        if name in visited:
            return
        visited.add(name)

        try:
            spec = importlib.util.find_spec(name)
            if not spec or not spec.origin:
                return

            with open(spec.origin) as f:
                tree = ast.parse(f.read())

            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)

            graph[name] = imports

            for imp in imports:
                analyze_module(imp)

        except Exception:
            pass

    analyze_module(module_name)
    return graph
```

---

## Phase 3 Checklist (v0.19.0)

### Project Intelligence

- [ ] `python://project` - Auto-detect project type
- [ ] `python://tests` - Test discovery
- [ ] `python://quality` - Code quality metrics
- [ ] `python://security` - Vulnerability scan

### Project Type Detection

```python
def detect_project_type(self, root_path: str = '.') -> Dict:
    """Detect project type."""
    from pathlib import Path

    root = Path(root_path)

    # Django
    if (root / 'manage.py').exists():
        return self._analyze_django_project(root)

    # Flask
    if self._has_flask_patterns(root):
        return self._analyze_flask_project(root)

    # FastAPI
    if self._has_fastapi_patterns(root):
        return self._analyze_fastapi_project(root)

    return {'type': 'generic', 'structure': 'unknown'}
```

---

## Testing Strategy

### Unit Tests

```python
# tests/adapters/test_python.py

import pytest
from reveal.adapters.python import PythonAdapter


def test_adapter_registration():
    """Test that python adapter is registered."""
    from reveal.adapters.base import get_adapter_class
    adapter_class = get_adapter_class('python')
    assert adapter_class is not None
    assert adapter_class == PythonAdapter


def test_get_structure():
    """Test basic structure overview."""
    adapter = PythonAdapter()
    result = adapter.get_structure()

    assert 'version' in result
    assert 'implementation' in result
    assert 'virtual_env' in result
    assert isinstance(result['modules_loaded'], int)


def test_version_element():
    """Test version endpoint."""
    adapter = PythonAdapter()
    result = adapter.get_element('version')

    assert result is not None
    assert 'version' in result
    assert 'executable' in result
    assert 'platform' in result


def test_venv_detection():
    """Test virtual environment detection."""
    adapter = PythonAdapter()
    result = adapter.get_element('venv')

    assert result is not None
    assert 'active' in result
    assert isinstance(result['active'], bool)


def test_packages_listing():
    """Test package listing."""
    adapter = PythonAdapter()
    result = adapter.get_element('packages')

    assert result is not None
    assert 'count' in result
    assert 'packages' in result
    assert isinstance(result['packages'], list)


def test_imports_listing():
    """Test imports listing."""
    adapter = PythonAdapter()
    result = adapter.get_element('imports')

    assert result is not None
    assert 'count' in result
    assert 'loaded' in result
    # sys should always be loaded
    assert any(m['name'] == 'sys' for m in result['loaded'])


def test_bytecode_check(tmp_path):
    """Test bytecode checking."""
    # Create test structure
    py_file = tmp_path / "test.py"
    py_file.write_text("print('hello')")

    pycache = tmp_path / "__pycache__"
    pycache.mkdir()

    pyc_file = pycache / "test.cpython-310.pyc"
    pyc_file.write_bytes(b'fake pyc')

    # Make .pyc newer than .py
    import time
    time.sleep(0.1)
    pyc_file.touch()

    adapter = PythonAdapter()
    result = adapter.get_element('debug/bytecode', root_path=str(tmp_path))

    assert result is not None
    assert result['status'] == 'issues_found'
    assert len(result['issues']) > 0


def test_help_documentation():
    """Test help documentation."""
    help_doc = PythonAdapter.get_help()

    assert help_doc is not None
    assert 'name' in help_doc
    assert help_doc['name'] == 'python'
    assert 'examples' in help_doc
    assert len(help_doc['examples']) > 0
```

### Integration Tests

```bash
#!/bin/bash
# tests/integration/test_python_adapter.sh

set -e

echo "Testing python:// adapter integration"

# Test basic invocation
reveal python:// --format=json > /tmp/python_overview.json
jq -e '.version' /tmp/python_overview.json

# Test version
reveal python://version --format=json > /tmp/python_version.json
jq -e '.executable' /tmp/python_version.json

# Test packages
reveal python://packages --format=json > /tmp/python_packages.json
jq -e '.count' /tmp/python_packages.json

# Test imports
reveal python://imports --format=json > /tmp/python_imports.json
jq -e '.loaded[] | select(.name == "sys")' /tmp/python_imports.json

# Test bytecode check
reveal python://debug/bytecode --format=json > /tmp/python_bytecode.json
jq -e '.status' /tmp/python_bytecode.json

echo "✅ All integration tests passed"
```

---

## Performance Benchmarks

### Target Performance

| Endpoint | Target Time | Notes |
|----------|-------------|-------|
| `python://` | < 100ms | Overview should be fast |
| `python://version` | < 10ms | Just sys calls |
| `python://packages` | < 500ms | Package discovery is expensive |
| `python://imports` | < 50ms | Read sys.modules |
| `python://debug/bytecode` | < 200ms | File system scan |

### Optimization Strategies

1. **Lazy Loading:** Don't load packages until requested
2. **Caching:** Cache expensive operations with TTL
3. **Parallel Processing:** Scan file system in parallel for bytecode check
4. **Progressive Loading:** Stream results for large datasets

---

## Migration Guide

### For Reveal Users

**No breaking changes** - This is a new adapter.

**New capabilities:**
```bash
# Old way: Manual checks
pip list
python --version
env | grep PYTHON

# New way: Unified inspection
reveal python://
reveal python://packages
reveal python://env
```

### For AI Agents

**New debugging workflow:**
```python
# Agent investigating "imports not working"

# 1. Check Python environment
result = run_reveal("python://env")
if not result['virtual_env']['active']:
    suggest("Activate virtual environment")

# 2. Check for bytecode issues
result = run_reveal("python://debug/bytecode")
if result['status'] == 'issues_found':
    suggest("Clean bytecode: find . -name '*.pyc' -delete")

# 3. Check imports
result = run_reveal("python://imports/circular")
if result['circular_imports_found']:
    suggest("Fix circular imports")
```

---

## Success Criteria

### v0.17.0 Launch

- [ ] All Phase 1 endpoints working
- [ ] 90%+ test coverage
- [ ] Documentation complete
- [ ] Performance targets met
- [ ] Zero regressions in existing adapters
- [ ] Positive user feedback

### Metrics

- **Adoption:** 50+ uses in first week
- **Bug Reports:** < 5 in first month
- **Performance:** All endpoints meet targets
- **Documentation:** < 3 "how do I" questions

---

## Risk Assessment

### Low Risk

- Well-defined scope
- Clear separation from existing adapters
- No breaking changes
- Incremental rollout (3 phases)

### Potential Issues

1. **Cross-platform compatibility**
   - Mitigation: Test on Linux, macOS, Windows
   - Fallbacks for platform-specific features

2. **Package discovery performance**
   - Mitigation: Caching, lazy loading
   - Progress indicators for slow operations

3. **Permission errors**
   - Mitigation: Graceful error handling
   - Clear error messages

---

## Timeline

### Optimistic

- Phase 1: 1 day (8 hours)
- Testing: 0.5 days
- Documentation: 0.5 days
- **Total: 2 days**

### Realistic

- Phase 1: 2 days (16 hours)
- Testing: 1 day
- Documentation: 1 day
- Review/polish: 0.5 days
- **Total: 4.5 days**

### With All Phases

- Phase 1: 2 days
- Phase 2: 1.5 days
- Phase 3: 3 days
- Testing/docs: 2 days
- **Total: 8.5 days**

---

## Next Steps

1. **Review specification** - Get feedback on design
2. **Prototype Phase 1** - Build minimal working version
3. **User testing** - Get early feedback
4. **Iterate** - Refine based on feedback
5. **Ship** - Release v0.17.0 with Phase 1

---

## Questions to Resolve

- [ ] Should `python://packages/<name>` work for packages not installed?
- [ ] How deep should import graph analysis go?
- [ ] Should we integrate with `safety` for security scanning?
- [ ] Cache strategy: In-memory vs file-based?
- [ ] Should we support `python://requirements` to compare with requirements.txt?

---

## Resources

- **Specification:** [PYTHON_ADAPTER_SPEC.md](./PYTHON_ADAPTER_SPEC.md)
- **Base Adapter:** `reveal/adapters/base.py`
- **Reference Implementation:** `reveal/adapters/env.py`
- **Python Docs:** https://docs.python.org/3/library/sys.html
- **pkg_resources:** https://setuptools.pypa.io/en/latest/pkg_resources.html
