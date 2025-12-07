"""Python runtime adapter (python://)."""

import sys
import platform
import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Iterator
from .base import ResourceAdapter, register_adapter


@register_adapter('python')
class PythonAdapter(ResourceAdapter):
    """Adapter for Python runtime inspection via python:// URIs."""

    def __init__(self):
        """Initialize with runtime introspection capabilities."""
        self._packages_cache = None
        self._imports_cache = None

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get overview of Python environment.

        Returns:
            Dict containing Python environment overview
        """
        venv_info = self._detect_venv()
        return {
            'version': platform.python_version(),
            'implementation': platform.python_implementation(),
            'executable': sys.executable,
            'virtual_env': venv_info,
            'packages_count': len(list(self._get_packages())),
            'modules_loaded': len(sys.modules),
            'platform': sys.platform,
            'architecture': platform.machine()
        }

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get specific element within the Python runtime.

        Args:
            element_name: Element path (e.g., 'version', 'packages', 'debug/bytecode')

        Supported elements:
            - version: Python version details
            - env: Python environment configuration
            - venv: Virtual environment status
            - packages: All installed packages
            - packages/<name>: Specific package details
            - imports: Currently loaded modules
            - debug/bytecode: Bytecode issues
            - debug/syntax: Syntax errors (future)

        Returns:
            Dict containing element details, or None if not found
        """
        # Handle nested paths
        parts = element_name.split('/', 1)
        base = parts[0]

        # Route to handlers
        if base == 'version':
            return self._get_version(**kwargs)
        elif base == 'env':
            return self._get_env(**kwargs)
        elif base == 'venv':
            return self._get_venv(**kwargs)
        elif base == 'packages':
            if len(parts) > 1:
                return self._get_package_details(parts[1], **kwargs)
            return self._get_packages_list(**kwargs)
        elif base == 'imports':
            if len(parts) > 1 and parts[1] == 'graph':
                return {'error': 'Import graph analysis coming in v0.18.0'}
            elif len(parts) > 1 and parts[1] == 'circular':
                return {'error': 'Circular import detection coming in v0.18.0'}
            return self._get_imports(**kwargs)
        elif base == 'debug':
            if len(parts) > 1:
                return self._handle_debug(parts[1], **kwargs)
            return {'error': 'Specify debug type: bytecode, syntax'}

        return None

    def _get_version(self, **kwargs) -> Dict[str, Any]:
        """Get detailed Python version information.

        Returns:
            Dict with version, implementation, build info, etc.
        """
        return {
            'version': platform.python_version(),
            'implementation': platform.python_implementation(),
            'compiler': platform.python_compiler(),
            'build_date': platform.python_build()[1],
            'build_number': platform.python_build()[0],
            'executable': sys.executable,
            'prefix': sys.prefix,
            'base_prefix': sys.base_prefix,
            'platform': sys.platform,
            'architecture': platform.machine(),
            'version_info': {
                'major': sys.version_info.major,
                'minor': sys.version_info.minor,
                'micro': sys.version_info.micro,
                'releaselevel': sys.version_info.releaselevel,
                'serial': sys.version_info.serial
            }
        }

    def _detect_venv(self) -> Dict[str, Any]:
        """Detect if running in a virtual environment.

        Returns:
            Dict with virtual environment status and details
        """
        venv_path = os.getenv('VIRTUAL_ENV')
        if venv_path:
            return {
                'active': True,
                'path': venv_path,
                'type': 'venv'
            }

        # Check if sys.prefix differs from sys.base_prefix
        if sys.prefix != sys.base_prefix:
            return {
                'active': True,
                'path': sys.prefix,
                'type': 'venv'
            }

        # Check for conda
        conda_env = os.getenv('CONDA_DEFAULT_ENV')
        if conda_env:
            return {
                'active': True,
                'path': os.getenv('CONDA_PREFIX', ''),
                'type': 'conda',
                'name': conda_env
            }

        return {'active': False}

    def _get_venv(self, **kwargs) -> Dict[str, Any]:
        """Get detailed virtual environment information.

        Returns:
            Dict with virtual environment details
        """
        venv_info = self._detect_venv()

        if venv_info['active']:
            venv_info.update({
                'python_version': platform.python_version(),
                'prompt': os.path.basename(venv_info.get('path', ''))
            })

        return venv_info

    def _get_env(self, **kwargs) -> Dict[str, Any]:
        """Get Python environment configuration.

        Returns:
            Dict with sys.path, flags, and environment details
        """
        return {
            'virtual_env': self._detect_venv(),
            'sys_path': list(sys.path),
            'sys_path_count': len(sys.path),
            'python_path': os.getenv('PYTHONPATH'),
            'flags': {
                'dont_write_bytecode': sys.dont_write_bytecode,
                'optimize': sys.flags.optimize,
                'verbose': sys.flags.verbose,
                'interactive': sys.flags.interactive,
                'debug': sys.flags.debug
            },
            'encoding': {
                'filesystem': sys.getfilesystemencoding(),
                'default': sys.getdefaultencoding()
            }
        }

    def _get_packages(self) -> Iterator:
        """Generator for installed packages.

        Yields:
            Package distribution objects
        """
        try:
            # Try pkg_resources first (older but more compatible)
            import pkg_resources
            for dist in pkg_resources.working_set:
                yield dist
        except ImportError:
            # Fallback to importlib.metadata (Python 3.8+)
            try:
                import importlib.metadata
                for dist in importlib.metadata.distributions():
                    yield dist
            except ImportError:
                # No package metadata available
                pass

    def _get_packages_list(self, **kwargs) -> Dict[str, Any]:
        """List all installed packages.

        Returns:
            Dict with package count and list of packages
        """
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
                try:
                    packages.append({
                        'name': dist.name,
                        'version': dist.version,
                        'location': str(dist._path.parent) if hasattr(dist, '_path') else 'unknown'
                    })
                except Exception:
                    continue

        return {
            'count': len(packages),
            'packages': sorted(packages, key=lambda p: p['name'].lower())
        }

    def _get_package_details(self, package_name: str, **kwargs) -> Dict[str, Any]:
        """Get detailed information about a specific package.

        Args:
            package_name: Name of the package

        Returns:
            Dict with package details or error
        """
        try:
            # Try pkg_resources first
            import pkg_resources
            dist = pkg_resources.get_distribution(package_name)

            details = {
                'name': dist.project_name,
                'version': dist.version,
                'location': dist.location,
                'requires_python': None,
                'dependencies': []
            }

            # Get requirements
            try:
                details['dependencies'] = [str(req) for req in dist.requires()]
            except Exception:
                pass

            # Check if editable install
            try:
                details['editable'] = dist.has_metadata('direct_url.json')
            except Exception:
                details['editable'] = False

            return details

        except Exception:
            # Try importlib.metadata
            try:
                import importlib.metadata
                dist = importlib.metadata.distribution(package_name)

                metadata = dist.metadata

                return {
                    'name': metadata.get('Name'),
                    'version': metadata.get('Version'),
                    'summary': metadata.get('Summary'),
                    'author': metadata.get('Author'),
                    'license': metadata.get('License'),
                    'location': str(dist._path.parent) if hasattr(dist, '_path') else 'unknown',
                    'requires_python': metadata.get('Requires-Python'),
                    'homepage': metadata.get('Home-page'),
                    'dependencies': dist.requires or []
                }
            except Exception as e:
                return {
                    'error': f'Package not found: {package_name}',
                    'details': str(e)
                }

    def _get_imports(self, **kwargs) -> Dict[str, Any]:
        """List currently loaded modules.

        Returns:
            Dict with loaded module information
        """
        modules = []

        for name, module in sys.modules.items():
            if module is None:
                continue

            module_info = {
                'name': name,
                'file': getattr(module, '__file__', None),
                'package': getattr(module, '__package__', None)
            }

            modules.append(module_info)

        return {
            'count': len(modules),
            'loaded': sorted(modules, key=lambda m: m['name'])
        }

    def _handle_debug(self, debug_type: str, **kwargs) -> Dict[str, Any]:
        """Handle debug/* endpoints.

        Args:
            debug_type: Type of debug check (bytecode, syntax, etc.)

        Returns:
            Dict with debug results
        """
        if debug_type == 'bytecode':
            root_path = kwargs.get('root_path', '.')
            return self._check_bytecode(root_path)
        elif debug_type == 'syntax':
            return {'error': 'Syntax checking coming in v0.18.0'}

        return {'error': f'Unknown debug type: {debug_type}'}

    def _check_bytecode(self, root_path: str = '.') -> Dict[str, Any]:
        """Check for bytecode issues (stale .pyc files, orphaned bytecode, etc.).

        Args:
            root_path: Root directory to scan

        Returns:
            Dict with issues found
        """
        issues = []
        root = Path(root_path)

        try:
            # Find all .pyc files
            for pyc_file in root.rglob('**/*.pyc'):
                # Skip if not in __pycache__ (old Python 2 style)
                if '__pycache__' not in pyc_file.parts:
                    issues.append({
                        'type': 'old_style_pyc',
                        'severity': 'info',
                        'file': str(pyc_file),
                        'problem': 'Python 2 style .pyc file (should be in __pycache__)',
                        'fix': f'rm {pyc_file}'
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
                        'problem': '.pyc file is NEWER than source (stale bytecode)',
                        'source_mtime': py_file.stat().st_mtime,
                        'pyc_mtime': pyc_file.stat().st_mtime,
                        'fix': f'rm {pyc_file}'
                    })

        except Exception as e:
            return {
                'error': f'Failed to scan for bytecode issues: {str(e)}',
                'status': 'error'
            }

        return {
            'status': 'issues_found' if issues else 'clean',
            'issues': issues,
            'summary': {
                'total': len(issues),
                'warnings': len([i for i in issues if i['severity'] == 'warning']),
                'info': len([i for i in issues if i['severity'] == 'info']),
                'errors': len([i for i in issues if i['severity'] == 'error'])
            }
        }

    @staticmethod
    def _pyc_to_source(pyc_file: Path) -> Path:
        """Convert .pyc file path to corresponding .py file path.

        Args:
            pyc_file: Path to .pyc file

        Returns:
            Path to corresponding .py file
        """
        # Example: __pycache__/module.cpython-310.pyc -> module.py
        if '__pycache__' in pyc_file.parts:
            parent = pyc_file.parent.parent
            # Remove cpython-XXX suffix and .pyc extension
            name = pyc_file.stem.split('.')[0]
            return parent / f"{name}.py"

        # Old style: module.pyc -> module.py
        return pyc_file.with_suffix('.py')

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for python:// adapter.

        Returns:
            Dict containing help information
        """
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
                    'uri': 'python://env',
                    'description': "Python's computed environment (sys.path, flags)"
                },
                {
                    'uri': 'python://venv',
                    'description': 'Virtual environment status and details'
                },
                {
                    'uri': 'python://packages',
                    'description': 'List all installed packages'
                },
                {
                    'uri': 'python://packages/reveal-cli',
                    'description': 'Details about a specific package'
                },
                {
                    'uri': 'python://imports',
                    'description': 'Currently loaded modules in sys.modules'
                },
                {
                    'uri': 'python://debug/bytecode',
                    'description': 'Check for stale .pyc files and bytecode issues'
                },
                {
                    'uri': 'python:// --format=json',
                    'description': 'JSON output for scripting'
                }
            ],
            'elements': {
                'version': 'Python version, implementation, and build details',
                'env': 'Python environment configuration (sys.path, flags, encoding)',
                'venv': 'Virtual environment detection and status',
                'packages': 'List all installed packages (like pip list)',
                'packages/<name>': 'Detailed information about a specific package',
                'imports': 'Currently loaded modules from sys.modules',
                'debug/bytecode': 'Detect stale .pyc files and bytecode issues'
            },
            'features': [
                'Runtime environment inspection',
                'Virtual environment detection (venv, virtualenv, conda)',
                'Package listing and details',
                'Import tracking and analysis',
                'Bytecode debugging (stale .pyc detection)',
                'Cross-platform support (Linux, macOS, Windows)'
            ],
            'use_cases': [
                'Debug "my changes aren\'t working" (stale bytecode)',
                'Verify virtual environment activation',
                'Check installed package versions',
                'Inspect sys.path and import configuration',
                'Find what modules are currently loaded',
                'Pre-debug environment sanity check'
            ],
            'separation_of_concerns': {
                'env://': 'Raw environment variables (cross-language)',
                'ast://': 'Static source code analysis (cross-language)',
                'python://': 'Python runtime inspection (Python-specific)'
            },
            'notes': [
                'This adapter inspects the RUNTIME environment, not source code',
                'Use ast:// for static code analysis',
                'Use env:// for raw environment variables',
                'Bytecode checking requires filesystem access',
                'Package details require pkg_resources or importlib.metadata'
            ],
            'coming_soon': [
                'python://imports/graph - Import dependency visualization (v0.18.0)',
                'python://imports/circular - Circular import detection (v0.18.0)',
                'python://debug/syntax - Syntax error detection (v0.18.0)',
                'python://project - Project type detection (v0.19.0)',
                'python://tests - Test discovery (v0.19.0)'
            ],
            'see_also': [
                'reveal env:// - Environment variables',
                'reveal ast:// - Static code analysis',
                'reveal help://python - This help'
            ]
        }
