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
from reveal.adapters.base import get_adapter_class, list_supported_schemes


class TestAdapterRegistry(unittest.TestCase):
    """Test adapter registration and discovery."""

    def test_adapter_registration(self):
        """Adapters should auto-register on import."""
        schemes = list_supported_schemes()

        self.assertIn('env', schemes)
        self.assertIn('ast', schemes)
        self.assertIn('help', schemes)

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
