"""Tests for Python rendering adapter."""

import unittest
import sys
import io
from pathlib import Path
from contextlib import redirect_stdout

# Add parent directory to path to import reveal
sys.path.insert(0, str(Path(__file__).parent.parent))

from reveal.rendering.adapters.python import (
    render_python_structure,
    _render_python_packages,
    _render_python_modules,
    _render_python_doctor,
    _render_python_bytecode,
    _render_python_env_config,
    _render_python_version,
    _render_python_venv_status,
    _render_python_package_details,
    render_python_element,
)


def capture_stdout(func, *args, **kwargs):
    """Capture stdout from a function call."""
    output = io.StringIO()
    with redirect_stdout(output):
        func(*args, **kwargs)
    return output.getvalue()


class TestRenderPythonStructure(unittest.TestCase):
    """Test Python environment overview rendering."""

    def test_json_output(self):
        """Should render JSON when requested."""
        data = {
            'version': '3.10.0',
            'implementation': 'CPython',
            'executable': '/usr/bin/python3',
            'platform': 'linux',
            'architecture': 'x86_64',
            'virtual_env': {'active': False},
            'packages_count': 100,
            'modules_loaded': 50
        }
        output = capture_stdout(render_python_structure, data, 'json')
        self.assertIn('"version"', output)
        self.assertIn('3.10.0', output)

    def test_text_output_no_venv(self):
        """Should render text format without virtual environment."""
        data = {
            'version': '3.10.0',
            'implementation': 'CPython',
            'executable': '/usr/bin/python3',
            'platform': 'linux',
            'architecture': 'x86_64',
            'virtual_env': {'active': False},
            'packages_count': 100,
            'modules_loaded': 50
        }
        output = capture_stdout(render_python_structure, data, 'text')
        self.assertIn('Python Environment', output)
        self.assertIn('Version:        3.10.0 (CPython)', output)
        self.assertIn('Executable:     /usr/bin/python3', output)
        self.assertIn('Platform:       linux (x86_64)', output)
        self.assertIn('Virtual Env:    X Not active', output)
        self.assertIn('Packages:       100 installed', output)
        self.assertIn('Modules:        50 loaded', output)

    def test_text_output_with_venv(self):
        """Should render text format with active virtual environment."""
        data = {
            'version': '3.10.0',
            'implementation': 'CPython',
            'executable': '/home/user/venv/bin/python',
            'platform': 'linux',
            'architecture': 'x86_64',
            'virtual_env': {
                'active': True,
                'path': '/home/user/venv',
                'type': 'venv'
            },
            'packages_count': 50,
            'modules_loaded': 30
        }
        output = capture_stdout(render_python_structure, data, 'text')
        self.assertIn('Virtual Env:    * Active', output)
        self.assertIn('Path:         /home/user/venv', output)
        self.assertIn('Type:         venv', output)


class TestRenderPythonPackages(unittest.TestCase):
    """Test package list rendering."""

    def test_renders_package_list(self):
        """Should render list of installed packages."""
        data = {
            'count': 2,
            'packages': [
                {'name': 'requests', 'version': '2.28.0', 'location': '/usr/lib/python3/site-packages'},
                {'name': 'numpy', 'version': '1.23.0', 'location': '/home/user/venv/lib/python3/site-packages'}
            ]
        }
        output = capture_stdout(_render_python_packages, data)
        self.assertIn('Installed Packages (2)', output)
        self.assertIn('requests', output)
        self.assertIn('2.28.0', output)
        self.assertIn('numpy', output)
        self.assertIn('1.23.0', output)

    def test_empty_package_list(self):
        """Should handle empty package list."""
        data = {
            'count': 0,
            'packages': []
        }
        output = capture_stdout(_render_python_packages, data)
        self.assertIn('Installed Packages (0)', output)


class TestRenderPythonModules(unittest.TestCase):
    """Test loaded modules rendering."""

    def test_renders_module_list(self):
        """Should render list of loaded modules."""
        data = {
            'count': 3,
            'loaded': [
                {'name': 'os', 'file': '/usr/lib/python3.10/os.py'},
                {'name': 'sys', 'file': None},
                {'name': 'json', 'file': '/usr/lib/python3.10/json/__init__.py'}
            ]
        }
        output = capture_stdout(_render_python_modules, data)
        self.assertIn('Loaded Modules (3)', output)
        self.assertIn('os (/usr/lib/python3.10/os.py)', output)
        self.assertIn('sys (built-in)', output)
        self.assertIn('json', output)

    def test_truncates_long_module_list(self):
        """Should truncate and show count for lists > 50 modules."""
        modules = [{'name': f'module{i}', 'file': f'/path/to/module{i}.py'} for i in range(75)]
        data = {
            'count': 75,
            'loaded': modules
        }
        output = capture_stdout(_render_python_modules, data)
        self.assertIn('Loaded Modules (75)', output)
        self.assertIn('... and 25 more modules', output)


class TestRenderPythonDoctor(unittest.TestCase):
    """Test Python environment health diagnostics rendering."""

    def test_healthy_status(self):
        """Should render healthy status."""
        data = {
            'status': 'healthy',
            'health_score': 100,
            'checks_performed': ['venv', 'packages', 'bytecode']
        }
        output = capture_stdout(_render_python_doctor, data)
        self.assertIn('Python Environment Health: * HEALTHY', output)
        self.assertIn('Health Score: 100/100', output)
        self.assertIn('Checks performed: venv, packages, bytecode', output)

    def test_unhealthy_with_issues(self):
        """Should render issues."""
        data = {
            'status': 'degraded',
            'health_score': 60,
            'issues': [
                {'category': 'bytecode', 'message': 'Stale .pyc files found', 'impact': 'Performance degradation'}
            ],
            'checks_performed': ['venv', 'packages', 'bytecode']
        }
        output = capture_stdout(_render_python_doctor, data)
        self.assertIn('Python Environment Health: ! DEGRADED', output)
        self.assertIn('Health Score: 60/100', output)
        self.assertIn('Issues (1):', output)
        self.assertIn('X [bytecode] Stale .pyc files found', output)
        self.assertIn('Impact: Performance degradation', output)

    def test_with_warnings(self):
        """Should render warnings."""
        data = {
            'status': 'healthy',
            'health_score': 90,
            'warnings': [
                {'category': 'packages', 'message': 'Some packages outdated', 'impact': 'Security risk'}
            ],
            'checks_performed': ['packages']
        }
        output = capture_stdout(_render_python_doctor, data)
        self.assertIn('Warnings (1):', output)
        self.assertIn('! [packages] Some packages outdated', output)
        self.assertIn('Impact: Security risk', output)

    def test_with_info(self):
        """Should render info messages."""
        data = {
            'status': 'healthy',
            'health_score': 100,
            'info': [
                {'category': 'venv', 'message': 'Virtual environment active'}
            ],
            'checks_performed': ['venv']
        }
        output = capture_stdout(_render_python_doctor, data)
        self.assertIn('Info (1):', output)
        self.assertIn('i [venv] Virtual environment active', output)

    def test_with_recommendations(self):
        """Should render recommendations."""
        data = {
            'status': 'degraded',
            'health_score': 70,
            'recommendations': [
                {
                    'message': 'Update outdated packages',
                    'commands': ['pip install --upgrade pip', 'pip list --outdated']
                }
            ],
            'checks_performed': ['packages']
        }
        output = capture_stdout(_render_python_doctor, data)
        self.assertIn('Recommendations (1):', output)
        self.assertIn('> Update outdated packages', output)
        self.assertIn('$ pip install --upgrade pip', output)
        self.assertIn('$ pip list --outdated', output)


class TestRenderPythonBytecode(unittest.TestCase):
    """Test bytecode debugging information rendering."""

    def test_no_issues(self):
        """Should render clean status when no issues."""
        data = {
            'status': 'clean',
            'issues': []
        }
        output = capture_stdout(_render_python_bytecode, data)
        self.assertIn('Bytecode Check: CLEAN', output)
        self.assertIn('* No bytecode issues found', output)

    def test_with_issues(self):
        """Should render bytecode issues."""
        data = {
            'status': 'issues',
            'issues': [
                {
                    'type': 'Stale bytecode',
                    'file': '/path/to/module.py',
                    'pyc_file': '/path/to/__pycache__/module.pyc',
                    'problem': '.pyc file older than .py source',
                    'fix': 'python -m compileall /path/to',
                    'severity': 'warning'
                }
            ]
        }
        output = capture_stdout(_render_python_bytecode, data)
        self.assertIn('Bytecode Check: ISSUES', output)
        self.assertIn('Found 1 issues:', output)
        self.assertIn('!  Stale bytecode', output)  # Note: double space after !
        self.assertIn('File: /path/to/module.py', output)
        self.assertIn('Problem: .pyc file older than .py source', output)
        self.assertIn('Fix: python -m compileall /path/to', output)


class TestRenderPythonEnvConfig(unittest.TestCase):
    """Test Python environment configuration rendering."""

    def test_with_active_venv(self):
        """Should render environment config with active venv."""
        data = {
            'virtual_env': {
                'active': True,
                'path': '/home/user/venv',
                'type': 'venv'
            },
            'sys_path_count': 3,
            'sys_path': ['/home/user/venv/lib/python3.10/site-packages', '/usr/lib/python3.10', '/usr/lib/python3'],
            'flags': {'debug': False, 'optimize': 0, 'verbose': 0}
        }
        output = capture_stdout(_render_python_env_config, data)
        self.assertIn('Python Environment Configuration', output)
        self.assertIn('Virtual Environment: * Active', output)
        self.assertIn('Path: /home/user/venv', output)
        self.assertIn('Type: venv', output)
        self.assertIn('sys.path (3 entries):', output)
        self.assertIn('/home/user/venv/lib/python3.10/site-packages', output)
        self.assertIn('Flags:', output)
        self.assertIn('debug: False', output)

    def test_without_venv(self):
        """Should render environment config without venv."""
        data = {
            'virtual_env': {'active': False},
            'sys_path_count': 2,
            'sys_path': ['/usr/lib/python3.10', '/usr/lib/python3'],
            'flags': {'debug': False, 'optimize': 0}
        }
        output = capture_stdout(_render_python_env_config, data)
        self.assertIn('Virtual Environment: X Not active', output)


class TestRenderPythonVersion(unittest.TestCase):
    """Test Python version details rendering."""

    def test_renders_version_details(self):
        """Should render complete version information."""
        data = {
            'version': '3.10.12',
            'implementation': 'CPython',
            'compiler': 'GCC 11.3.0',
            'build_number': 'main',
            'build_date': 'Jun  6 2023 12:00:00',
            'executable': '/usr/bin/python3',
            'prefix': '/usr',
            'base_prefix': '/usr',
            'platform': 'linux',
            'architecture': 'x86_64'
        }
        output = capture_stdout(_render_python_version, data)
        self.assertIn('Python Version Details', output)
        self.assertIn('Version:        3.10.12', output)
        self.assertIn('Implementation: CPython', output)
        self.assertIn('Compiler:       GCC 11.3.0', output)
        self.assertIn('Build:          main (Jun  6 2023 12:00:00)', output)
        self.assertIn('Executable:     /usr/bin/python3', output)
        self.assertIn('Platform:       linux (x86_64)', output)


class TestRenderPythonVenvStatus(unittest.TestCase):
    """Test virtual environment status rendering."""

    def test_active_venv(self):
        """Should render active venv status."""
        data = {
            'active': True,
            'path': '/home/user/venv',
            'type': 'venv',
            'prompt': '(venv)',
            'python_version': '3.10.12'
        }
        output = capture_stdout(_render_python_venv_status, data)
        self.assertIn('Virtual Environment Status', output)
        self.assertIn('Status:    * Active', output)
        self.assertIn('Path:      /home/user/venv', output)
        self.assertIn('Type:      venv', output)
        self.assertIn('Prompt:    (venv)', output)
        self.assertIn('Python:    3.10.12', output)

    def test_inactive_venv(self):
        """Should render inactive venv status."""
        data = {
            'active': False
        }
        output = capture_stdout(_render_python_venv_status, data)
        self.assertIn('Virtual Environment Status', output)
        self.assertIn('Status:    X Not active', output)
        self.assertIn('No virtual environment detected', output)
        self.assertIn('Checked: VIRTUAL_ENV, sys.prefix, CONDA_DEFAULT_ENV', output)


class TestRenderPythonPackageDetails(unittest.TestCase):
    """Test individual package details rendering."""

    def test_minimal_package_details(self):
        """Should render minimal package information."""
        data = {
            'name': 'requests',
            'version': '2.28.0',
            'location': '/usr/lib/python3/site-packages'
        }
        output = capture_stdout(_render_python_package_details, data)
        self.assertIn('Package: requests', output)
        self.assertIn('Version:    2.28.0', output)
        self.assertIn('Location:   /usr/lib/python3/site-packages', output)

    def test_full_package_details(self):
        """Should render full package information."""
        data = {
            'name': 'requests',
            'version': '2.28.0',
            'location': '/usr/lib/python3/site-packages',
            'summary': 'HTTP library for Python',
            'author': 'Kenneth Reitz',
            'license': 'Apache 2.0',
            'homepage': 'https://requests.readthedocs.io',
            'dependencies': ['urllib3>=1.26.0', 'certifi>=2021.5.30', 'charset-normalizer>=2.0.0']
        }
        output = capture_stdout(_render_python_package_details, data)
        self.assertIn('Package: requests', output)
        self.assertIn('Summary:    HTTP library for Python', output)
        self.assertIn('Author:     Kenneth Reitz', output)
        self.assertIn('License:    Apache 2.0', output)
        self.assertIn('Homepage:   https://requests.readthedocs.io', output)
        self.assertIn('Dependencies (3):', output)
        self.assertIn('* urllib3>=1.26.0', output)
        self.assertIn('* certifi>=2021.5.30', output)
        self.assertIn('* charset-normalizer>=2.0.0', output)


class TestRenderPythonElement(unittest.TestCase):
    """Test Python element dispatcher."""

    def test_json_output(self):
        """Should render JSON when requested."""
        data = {'test': 'data'}
        output = capture_stdout(render_python_element, data, 'json')
        self.assertIn('"test"', output)
        self.assertIn('data', output)

    def test_error_handling(self):
        """Should handle errors and exit."""
        data = {
            'error': 'Module not found',
            'details': 'No module named foo'
        }
        with self.assertRaises(SystemExit):
            render_python_element(data, 'text')

    def test_dispatches_to_packages(self):
        """Should dispatch to packages renderer."""
        data = {
            'packages': [{'name': 'test', 'version': '1.0', 'location': '/path'}],
            'count': 1
        }
        output = capture_stdout(render_python_element, data, 'text')
        self.assertIn('Installed Packages (1)', output)

    def test_dispatches_to_modules(self):
        """Should dispatch to modules renderer."""
        data = {
            'loaded': [{'name': 'os', 'file': None}],
            'count': 1
        }
        output = capture_stdout(render_python_element, data, 'text')
        self.assertIn('Loaded Modules (1)', output)

    def test_dispatches_to_doctor(self):
        """Should dispatch to doctor renderer."""
        data = {
            'health_score': 100,
            'status': 'healthy',
            'checks_performed': ['test']
        }
        output = capture_stdout(render_python_element, data, 'text')
        self.assertIn('Python Environment Health', output)

    def test_dispatches_to_bytecode(self):
        """Should dispatch to bytecode renderer."""
        data = {
            'status': 'clean',
            'issues': []
        }
        output = capture_stdout(render_python_element, data, 'text')
        self.assertIn('Bytecode Check', output)

    def test_dispatches_to_env_config(self):
        """Should dispatch to env config renderer."""
        data = {
            'sys_path': ['/usr/lib/python3'],
            'sys_path_count': 1,
            'virtual_env': {'active': False},
            'flags': {}
        }
        output = capture_stdout(render_python_element, data, 'text')
        self.assertIn('Python Environment Configuration', output)

    def test_dispatches_to_version(self):
        """Should dispatch to version renderer."""
        data = {
            'executable': '/usr/bin/python3',
            'compiler': 'GCC',
            'version': '3.10.0',
            'implementation': 'CPython',
            'build_number': 'main',
            'build_date': 'Jan 1 2023',
            'prefix': '/usr',
            'base_prefix': '/usr',
            'platform': 'linux',
            'architecture': 'x86_64'
        }
        output = capture_stdout(render_python_element, data, 'text')
        self.assertIn('Python Version Details', output)

    def test_dispatches_to_venv_status(self):
        """Should dispatch to venv status renderer."""
        data = {
            'active': True,
            'path': '/home/user/venv'
        }
        output = capture_stdout(render_python_element, data, 'text')
        self.assertIn('Virtual Environment Status', output)

    def test_dispatches_to_package_details(self):
        """Should dispatch to package details renderer."""
        data = {
            'name': 'requests',
            'version': '2.28.0',
            'location': '/usr/lib/python3/site-packages'
        }
        output = capture_stdout(render_python_element, data, 'text')
        self.assertIn('Package: requests', output)

    def test_fallback_to_json(self):
        """Should fallback to JSON for unknown data types."""
        data = {
            'unknown_field': 'value',
            'another': 'field'
        }
        output = capture_stdout(render_python_element, data, 'text')
        self.assertIn('"unknown_field"', output)
        self.assertIn('value', output)


if __name__ == '__main__':
    unittest.main()
