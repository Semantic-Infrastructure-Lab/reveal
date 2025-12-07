"""Tests for URI adapters (env://, ast://, help://)."""

import unittest
import sys
import os
from pathlib import Path

# Add parent directory to path to import reveal
sys.path.insert(0, str(Path(__file__).parent.parent))

from reveal.adapters.env import EnvAdapter
from reveal.adapters.ast import AstAdapter
from reveal.adapters.help import HelpAdapter
from reveal.adapters.python import PythonAdapter
from reveal.adapters.base import get_adapter_class, list_supported_schemes


class TestAdapterRegistry(unittest.TestCase):
    """Test adapter registration and discovery."""

    def test_adapter_registration(self):
        """Adapters should auto-register on import."""
        schemes = list_supported_schemes()

        self.assertIn('env', schemes)
        self.assertIn('ast', schemes)
        self.assertIn('help', schemes)
        self.assertIn('python', schemes)

    def test_get_adapter_class(self):
        """Should retrieve adapter class by scheme."""
        env_adapter = get_adapter_class('env')
        self.assertEqual(env_adapter, EnvAdapter)

        ast_adapter = get_adapter_class('ast')
        self.assertEqual(ast_adapter, AstAdapter)

        help_adapter = get_adapter_class('help')
        self.assertEqual(help_adapter, HelpAdapter)

    def test_unknown_scheme(self):
        """Should return None for unknown scheme."""
        unknown = get_adapter_class('unknown')
        self.assertIsNone(unknown)


class TestEnvAdapter(unittest.TestCase):
    """Test environment variable adapter."""

    def test_get_structure(self):
        """Should return environment variables grouped by category."""
        adapter = EnvAdapter()
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'environment')
        self.assertIn('total_count', result)
        self.assertIn('categories', result)
        self.assertIsInstance(result['categories'], dict)

    def test_get_element(self):
        """Should retrieve specific environment variable."""
        adapter = EnvAdapter()

        # Test with PATH (should exist on all systems)
        result = adapter.get_element('PATH')
        if result:  # PATH might not exist in some test environments
            self.assertEqual(result['name'], 'PATH')
            self.assertIn('value', result)
            self.assertIn('category', result)

    def test_get_help(self):
        """Should provide help documentation."""
        help_data = EnvAdapter.get_help()

        self.assertIsInstance(help_data, dict)
        self.assertEqual(help_data['name'], 'env')
        self.assertIn('description', help_data)
        self.assertIn('examples', help_data)
        self.assertIn('syntax', help_data)


class TestAstAdapter(unittest.TestCase):
    """Test AST query adapter."""

    def setUp(self):
        """Create test file for AST analysis."""
        self.test_file = Path(__file__).parent / 'test_adapters.py'  # This file!

    def test_parse_query(self):
        """Should parse query string into filters."""
        adapter = AstAdapter('.', 'lines>50')

        self.assertIn('lines', adapter.query)
        self.assertEqual(adapter.query['lines']['op'], '>')
        self.assertEqual(adapter.query['lines']['value'], 50)

    def test_parse_multiple_filters(self):
        """Should parse multiple filters."""
        adapter = AstAdapter('.', 'lines>20&complexity<5')

        self.assertIn('lines', adapter.query)
        self.assertIn('complexity', adapter.query)

    def test_parse_operators(self):
        """Should handle all comparison operators."""
        test_cases = [
            ('lines>50', '>'),
            ('lines<50', '<'),
            ('lines>=50', '>='),
            ('lines<=50', '<='),
            ('complexity==5', '=='),
        ]

        for query_str, expected_op in test_cases:
            adapter = AstAdapter('.', query_str)
            field = query_str.split(expected_op.replace('=', '\\='))[0]

            # Get the actual field name (might be remapped)
            if 'lines' in query_str:
                self.assertEqual(adapter.query['lines']['op'], expected_op)
            elif 'complexity' in query_str:
                self.assertEqual(adapter.query['complexity']['op'], expected_op)

    def test_get_structure(self):
        """Should return AST query results."""
        adapter = AstAdapter(str(self.test_file.parent), None)
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'ast-query')
        self.assertIn('total_files', result)
        self.assertIn('total_results', result)
        self.assertIn('results', result)
        self.assertIsInstance(result['results'], list)

    def test_filter_by_complexity(self):
        """Should filter by complexity."""
        # Find functions with complexity > 1 in this file
        adapter = AstAdapter(str(self.test_file), 'complexity>1')
        result = adapter.get_structure()

        # Should find some functions
        self.assertGreater(result['total_results'], 0)

        # All results should have complexity > 1
        for elem in result['results']:
            if 'complexity' in elem:
                self.assertGreater(elem['complexity'], 1)

    def test_get_help(self):
        """Should provide comprehensive help documentation."""
        help_data = AstAdapter.get_help()

        self.assertIsInstance(help_data, dict)
        self.assertEqual(help_data['name'], 'ast')
        self.assertIn('description', help_data)
        self.assertIn('syntax', help_data)
        self.assertIn('operators', help_data)
        self.assertIn('filters', help_data)
        self.assertIn('examples', help_data)
        self.assertIn('notes', help_data)

        # Check operators
        self.assertIn('>', help_data['operators'])
        self.assertIn('<', help_data['operators'])

        # Check filters
        self.assertIn('lines', help_data['filters'])
        self.assertIn('complexity', help_data['filters'])


class TestHelpAdapter(unittest.TestCase):
    """Test help meta-adapter."""

    def test_get_structure(self):
        """Should list all available help topics."""
        adapter = HelpAdapter()
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'help')
        self.assertIn('available_topics', result)
        self.assertIn('adapters', result)
        self.assertIn('static_guides', result)

        # Should include all registered adapters
        topics = result['available_topics']
        self.assertIn('env', topics)
        self.assertIn('ast', topics)
        self.assertIn('help', topics)

    def test_get_adapter_help(self):
        """Should retrieve help for specific adapter."""
        adapter = HelpAdapter()

        # Test ast:// help
        ast_help = adapter.get_element('ast')
        self.assertIsNotNone(ast_help)
        self.assertEqual(ast_help['name'], 'ast')
        self.assertIn('description', ast_help)

        # Test env:// help
        env_help = adapter.get_element('env')
        self.assertIsNotNone(env_help)
        self.assertEqual(env_help['name'], 'env')

    def test_get_all_adapters(self):
        """Should provide summary of all adapters."""
        adapter = HelpAdapter()
        result = adapter.get_element('adapters')

        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'adapter_summary')
        self.assertIn('adapters', result)
        self.assertIn('ast', result['adapters'])
        self.assertIn('env', result['adapters'])

    def test_unknown_topic(self):
        """Should return None for unknown topic."""
        adapter = HelpAdapter()
        result = adapter.get_element('unknown_topic')

        self.assertIsNone(result)

    def test_get_help(self):
        """Should provide help about help (meta!)."""
        help_data = HelpAdapter.get_help()

        self.assertIsInstance(help_data, dict)
        self.assertEqual(help_data['name'], 'help')
        self.assertIn('description', help_data)
        self.assertIn('examples', help_data)


class TestPythonAdapter(unittest.TestCase):
    """Test Python runtime adapter."""

    def test_adapter_registration(self):
        """Python adapter should be registered."""
        adapter_class = get_adapter_class('python')
        self.assertEqual(adapter_class, PythonAdapter)

    def test_get_structure(self):
        """Should return Python environment overview."""
        adapter = PythonAdapter()
        result = adapter.get_structure()

        # Check required fields
        self.assertIn('version', result)
        self.assertIn('implementation', result)
        self.assertIn('executable', result)
        self.assertIn('virtual_env', result)
        self.assertIn('packages_count', result)
        self.assertIn('modules_loaded', result)
        self.assertIn('platform', result)
        self.assertIn('architecture', result)

        # Validate types
        self.assertIsInstance(result['version'], str)
        self.assertIsInstance(result['packages_count'], int)
        self.assertIsInstance(result['modules_loaded'], int)
        self.assertIsInstance(result['virtual_env'], dict)

        # Should have loaded modules
        self.assertGreater(result['modules_loaded'], 0)

    def test_get_version(self):
        """Should return detailed version information."""
        adapter = PythonAdapter()
        result = adapter.get_element('version')

        self.assertIsNotNone(result)
        self.assertIn('version', result)
        self.assertIn('implementation', result)
        self.assertIn('compiler', result)
        self.assertIn('build_date', result)
        self.assertIn('executable', result)
        self.assertIn('prefix', result)
        self.assertIn('platform', result)
        self.assertIn('version_info', result)

        # Check version_info structure
        version_info = result['version_info']
        self.assertIn('major', version_info)
        self.assertIn('minor', version_info)
        self.assertIn('micro', version_info)

    def test_get_venv(self):
        """Should detect virtual environment status."""
        adapter = PythonAdapter()
        result = adapter.get_element('venv')

        self.assertIsNotNone(result)
        self.assertIn('active', result)
        self.assertIsInstance(result['active'], bool)

        # If active, should have additional fields
        if result['active']:
            self.assertIn('path', result)
            self.assertIn('type', result)

    def test_get_env(self):
        """Should return Python environment configuration."""
        adapter = PythonAdapter()
        result = adapter.get_element('env')

        self.assertIsNotNone(result)
        self.assertIn('virtual_env', result)
        self.assertIn('sys_path', result)
        self.assertIn('sys_path_count', result)
        self.assertIn('flags', result)
        self.assertIn('encoding', result)

        # Validate sys.path
        self.assertIsInstance(result['sys_path'], list)
        self.assertGreater(len(result['sys_path']), 0)
        self.assertEqual(len(result['sys_path']), result['sys_path_count'])

        # Validate flags
        flags = result['flags']
        self.assertIn('dont_write_bytecode', flags)
        self.assertIn('optimize', flags)
        self.assertIn('verbose', flags)

        # Validate encoding
        encoding = result['encoding']
        self.assertIn('filesystem', encoding)
        self.assertIn('default', encoding)

    def test_get_packages(self):
        """Should list installed packages."""
        adapter = PythonAdapter()
        result = adapter.get_element('packages')

        self.assertIsNotNone(result)
        self.assertIn('count', result)
        self.assertIn('packages', result)

        # Should have some packages
        self.assertGreater(result['count'], 0)
        self.assertIsInstance(result['packages'], list)
        self.assertEqual(len(result['packages']), result['count'])

        # Check package structure
        if result['packages']:
            pkg = result['packages'][0]
            self.assertIn('name', pkg)
            self.assertIn('version', pkg)
            self.assertIn('location', pkg)

    def test_get_package_details(self):
        """Should get details for specific package."""
        adapter = PythonAdapter()

        # Try to get details for a package we know exists
        # We can use 'pip' or 'setuptools' which should be installed
        result = adapter.get_element('packages/pip')

        # Result might be error if pip not installed as package
        if 'error' not in result:
            self.assertIn('name', result)
            self.assertIn('version', result)
            self.assertIn('location', result)

    def test_get_imports(self):
        """Should list currently loaded modules."""
        adapter = PythonAdapter()
        result = adapter.get_element('imports')

        self.assertIsNotNone(result)
        self.assertIn('count', result)
        self.assertIn('loaded', result)

        # Should have loaded modules
        self.assertGreater(result['count'], 0)
        self.assertIsInstance(result['loaded'], list)

        # sys should always be loaded
        module_names = [m['name'] for m in result['loaded']]
        self.assertIn('sys', module_names)

        # Check module structure
        sys_module = next(m for m in result['loaded'] if m['name'] == 'sys')
        self.assertIn('name', sys_module)
        self.assertIn('file', sys_module)
        self.assertIn('package', sys_module)

    def test_debug_bytecode_clean(self):
        """Should detect clean directory with no bytecode issues."""
        import tempfile
        import shutil

        # Create temporary directory with clean Python file
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / 'test.py'
            test_file.write_text('print("hello")')

            adapter = PythonAdapter()
            result = adapter.get_element('debug/bytecode', root_path=tmpdir)

            self.assertIsNotNone(result)
            self.assertIn('status', result)
            self.assertIn('issues', result)
            self.assertIn('summary', result)

            # Should be clean (no .pyc files)
            self.assertEqual(result['status'], 'clean')
            self.assertEqual(len(result['issues']), 0)

    def test_debug_bytecode_stale(self):
        """Should detect stale bytecode."""
        import tempfile
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create Python file
            test_file = Path(tmpdir) / 'test.py'
            test_file.write_text('print("hello")')

            # Create __pycache__ directory
            pycache = Path(tmpdir) / '__pycache__'
            pycache.mkdir()

            # Create .pyc file
            pyc_file = pycache / 'test.cpython-310.pyc'
            pyc_file.write_bytes(b'fake pyc content')

            # Make .pyc newer than .py (stale bytecode)
            time.sleep(0.01)
            pyc_file.touch()

            adapter = PythonAdapter()
            result = adapter.get_element('debug/bytecode', root_path=tmpdir)

            self.assertIsNotNone(result)
            self.assertEqual(result['status'], 'issues_found')
            self.assertGreater(len(result['issues']), 0)

            # Check issue structure
            issue = result['issues'][0]
            self.assertIn('type', issue)
            self.assertEqual(issue['type'], 'stale_bytecode')
            self.assertIn('severity', issue)
            self.assertIn('problem', issue)
            self.assertIn('fix', issue)

    def test_debug_bytecode_orphaned(self):
        """Should detect orphaned bytecode."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create __pycache__ with .pyc but no corresponding .py
            pycache = Path(tmpdir) / '__pycache__'
            pycache.mkdir()

            pyc_file = pycache / 'missing.cpython-310.pyc'
            pyc_file.write_bytes(b'orphaned pyc')

            adapter = PythonAdapter()
            result = adapter.get_element('debug/bytecode', root_path=tmpdir)

            self.assertIsNotNone(result)
            self.assertEqual(result['status'], 'issues_found')

            # Should find orphaned bytecode
            self.assertGreater(len(result['issues']), 0)
            issue = result['issues'][0]
            self.assertEqual(issue['type'], 'orphaned_bytecode')

    def test_pyc_to_source_conversion(self):
        """Should correctly convert .pyc paths to .py paths."""
        # Test __pycache__ style
        pyc_path = Path('/home/user/project/__pycache__/module.cpython-310.pyc')
        py_path = PythonAdapter._pyc_to_source(pyc_path)
        self.assertEqual(py_path, Path('/home/user/project/module.py'))

        # Test old style
        old_pyc = Path('/home/user/project/module.pyc')
        old_py = PythonAdapter._pyc_to_source(old_pyc)
        self.assertEqual(old_py, Path('/home/user/project/module.py'))

    def test_unknown_element(self):
        """Should return None for unknown elements."""
        adapter = PythonAdapter()
        result = adapter.get_element('unknown_element')
        self.assertIsNone(result)

    def test_future_features(self):
        """Should return error messages for unimplemented features."""
        adapter = PythonAdapter()

        # Import graph - coming in v0.18.0
        result = adapter.get_element('imports/graph')
        self.assertIn('error', result)
        self.assertIn('0.18.0', result['error'])

        # Circular import detection - coming in v0.18.0
        result = adapter.get_element('imports/circular')
        self.assertIn('error', result)

        # Syntax checking - coming in v0.18.0
        result = adapter.get_element('debug/syntax')
        self.assertIn('error', result)

    def test_get_help(self):
        """Should provide comprehensive help documentation."""
        help_data = PythonAdapter.get_help()

        self.assertIsInstance(help_data, dict)
        self.assertEqual(help_data['name'], 'python')
        self.assertIn('description', help_data)
        self.assertIn('syntax', help_data)
        self.assertIn('examples', help_data)
        self.assertIn('elements', help_data)
        self.assertIn('features', help_data)
        self.assertIn('use_cases', help_data)
        self.assertIn('separation_of_concerns', help_data)

        # Check examples
        self.assertGreater(len(help_data['examples']), 0)
        example = help_data['examples'][0]
        self.assertIn('uri', example)
        self.assertIn('description', example)

        # Check elements
        elements = help_data['elements']
        self.assertIn('version', elements)
        self.assertIn('venv', elements)
        self.assertIn('packages', elements)

        # Check separation of concerns
        separation = help_data['separation_of_concerns']
        self.assertIn('env://', separation)
        self.assertIn('ast://', separation)
        self.assertIn('python://', separation)


class TestHelpDiscovery(unittest.TestCase):
    """Test that all adapters expose help."""

    def test_all_adapters_have_help(self):
        """All registered adapters should have get_help() method."""
        schemes = list_supported_schemes()

        for scheme in schemes:
            adapter_class = get_adapter_class(scheme)
            self.assertTrue(
                hasattr(adapter_class, 'get_help'),
                f"{scheme}:// adapter should have get_help() method"
            )

            # Try calling it
            help_data = adapter_class.get_help()
            if help_data:  # Some might return None
                self.assertIsInstance(help_data, dict)
                self.assertIn('name', help_data)


if __name__ == '__main__':
    unittest.main()
