"""Unit tests for reveal/cli/routing.py

These tests verify the CLI routing logic, particularly the generic_adapter_handler
which tries multiple initialization patterns for adapters.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
from argparse import Namespace

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from reveal.cli.routing import generic_adapter_handler


class MockRenderer:
    """Mock renderer for testing."""

    @staticmethod
    def render_structure(result, format='text'):
        pass

    @staticmethod
    def render_element(result, format='text'):
        pass

    @staticmethod
    def render_error(error):
        pass


class TestGenericAdapterHandler(unittest.TestCase):
    """Tests for generic_adapter_handler function."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_renderer = MockRenderer
        self.mock_args = Namespace(
            format='text',
            check=False,
            select=None,
            ignore=None
        )

    def test_no_arg_adapter_with_type_error(self):
        """Verify TypeError is caught when trying no-arg initialization."""
        attempts = []

        class NoArgAdapter:
            def __init__(self, *args, **kwargs):
                attempts.append(('init', args, kwargs))
                if not args and not kwargs:
                    raise TypeError("No-arg not supported")
                # Accept other patterns
                self.resource = args[0] if args else None

            def get_structure(self):
                return {'type': 'test'}

        # Should not crash, should try other patterns
        with patch('sys.stdout'), patch('sys.exit'):
            generic_adapter_handler(
                NoArgAdapter,
                self.mock_renderer,
                'test',
                'some_resource',
                None,
                self.mock_args
            )

        # Should have tried multiple patterns
        self.assertGreater(len(attempts), 1, "Should try multiple initialization patterns")

    def test_no_arg_adapter_with_value_error(self):
        """Verify ValueError is caught when trying no-arg initialization.

        This is the critical test for the bug we just fixed - git:// adapter
        raises ValueError, not TypeError, when resource is missing.
        """
        attempts = []

        class ValueErrorAdapter:
            def __init__(self, *args, **kwargs):
                attempts.append(('init', args, kwargs))
                if not args and not kwargs:
                    raise ValueError("Resource parameter required")
                # Accept resource argument
                self.resource = args[0] if args else None

            def get_structure(self):
                return {'type': 'test'}

        # Should not crash, should try other patterns
        with patch('sys.stdout'), patch('sys.exit'):
            generic_adapter_handler(
                ValueErrorAdapter,
                self.mock_renderer,
                'test',
                'some_resource',
                None,
                self.mock_args
            )

        # Should have tried multiple patterns, not crashed on first ValueError
        self.assertGreater(len(attempts), 1, "Should catch ValueError and try other patterns")

    def test_resource_arg_adapter_succeeds(self):
        """Verify adapter succeeds when resource pattern matches."""
        init_called = []

        class ResourceAdapter:
            def __init__(self, resource):
                init_called.append(resource)
                self.resource = resource

            def get_structure(self):
                return {'type': 'test', 'resource': self.resource}

        with patch('sys.stdout') as mock_stdout:
            generic_adapter_handler(
                ResourceAdapter,
                self.mock_renderer,
                'test',
                'my_resource',
                None,
                self.mock_args
            )

        self.assertEqual(len(init_called), 1)
        self.assertEqual(init_called[0], 'my_resource')

    def test_query_parsing_adapter(self):
        """Verify adapter with query string gets parsed correctly."""
        init_called = []

        class QueryAdapter:
            def __init__(self, path, query):
                init_called.append((path, query))
                self.path = path
                self.query = query

            def get_structure(self):
                return {'type': 'test', 'path': self.path, 'query': self.query}

        with patch('sys.stdout'):
            generic_adapter_handler(
                QueryAdapter,
                self.mock_renderer,
                'test',
                'path/to/file?type=function',
                None,
                self.mock_args
            )

        self.assertEqual(len(init_called), 1)
        path, query = init_called[0]
        self.assertEqual(path, 'path/to/file')
        self.assertEqual(query, 'type=function')

    def test_keyword_arg_adapter(self):
        """Verify adapter with keyword args works."""
        init_called = []

        class KeywordAdapter:
            def __init__(self, base_path=None, query=None):
                init_called.append({'base_path': base_path, 'query': query})
                self.base_path = base_path
                self.query = query

            def get_structure(self):
                return {'type': 'test'}

        with patch('sys.stdout'):
            generic_adapter_handler(
                KeywordAdapter,
                self.mock_renderer,
                'test',
                'some/path',
                None,
                self.mock_args
            )

        self.assertEqual(len(init_called), 1)
        self.assertEqual(init_called[0]['base_path'], 'some/path')

    def test_full_uri_adapter(self):
        """Verify adapter expecting full URI works."""
        init_called = []

        class URIAdapter:
            def __init__(self, uri):
                init_called.append(uri)
                if '://' not in uri:
                    raise ValueError("Expected full URI")
                self.uri = uri

            def get_structure(self):
                return {'type': 'test', 'uri': self.uri}

        with patch('sys.stdout'):
            generic_adapter_handler(
                URIAdapter,
                self.mock_renderer,
                'mysql',
                'localhost:3306/db',
                None,
                self.mock_args
            )

        # Should try patterns and eventually construct full URI
        self.assertTrue(any('mysql://' in str(call) for call in init_called))

    def test_exception_handling_consistency(self):
        """Verify all Try blocks catch both TypeError and ValueError.

        This test documents the fix: all initialization attempts should
        catch both exception types consistently.
        """
        # Create adapter that alternates between TypeError and ValueError
        attempt_count = [0]

        class InconsistentAdapter:
            def __init__(self, *args, **kwargs):
                attempt_count[0] += 1
                if attempt_count[0] % 2 == 0:
                    raise ValueError(f"Attempt {attempt_count[0]}")
                else:
                    raise TypeError(f"Attempt {attempt_count[0]}")

            def get_structure(self):
                return {'type': 'test'}

        # Should try all patterns without crashing on ValueError
        with patch('sys.stdout'), patch('sys.stderr'), patch('sys.exit'):
            generic_adapter_handler(
                InconsistentAdapter,
                self.mock_renderer,
                'test',
                'resource',
                None,
                self.mock_args
            )

        # Should have tried multiple patterns (5 Try blocks)
        # Even though it raises both TypeError and ValueError
        self.assertGreaterEqual(attempt_count[0], 3, "Should try multiple patterns despite mixed exceptions")

    def test_empty_resource_defaults_to_current_dir(self):
        """Verify empty resource defaults to '.' for path-based adapters."""
        init_called = []

        class PathAdapter:
            def __init__(self, path, query=None):
                init_called.append({'path': path, 'query': query})
                self.path = path

            def get_structure(self):
                return {'type': 'test', 'path': self.path}

        with patch('sys.stdout'):
            generic_adapter_handler(
                PathAdapter,
                self.mock_renderer,
                'test',
                '',  # Empty resource
                None,
                self.mock_args
            )

        # Should default empty path to '.'
        self.assertTrue(
            any(call['path'] == '.' for call in init_called),
            "Empty resource should default to '.'"
        )

    def test_import_error_special_handling(self):
        """Verify ImportError gets special error rendering."""
        class MissingDependencyAdapter:
            def __init__(self):
                raise ImportError("pip install some-package")

            def get_structure(self):
                return {'type': 'test'}

        with patch.object(self.mock_renderer, 'render_error') as mock_render:
            with patch('sys.exit'):
                generic_adapter_handler(
                    MissingDependencyAdapter,
                    self.mock_renderer,
                    'test',
                    'resource',
                    None,
                    self.mock_args
                )

        # Should call render_error for ImportError
        mock_render.assert_called_once()

    def test_element_parameter_appended_for_uri(self):
        """Verify element is appended to URI for URI-based adapters."""
        init_called = []

        class URIAdapter:
            def __init__(self, uri):
                init_called.append(uri)
                if '://' not in uri:
                    raise ValueError("Expected full URI")
                self.uri = uri

            def get_structure(self):
                return {'type': 'test'}

        with patch('sys.stdout'):
            generic_adapter_handler(
                URIAdapter,
                self.mock_renderer,
                'sqlite',
                'path/to/db.sqlite',
                'table_name',  # element
                self.mock_args
            )

        # Should construct URI with element appended
        self.assertTrue(
            any('table_name' in str(call) for call in init_called),
            "Element should be appended to URI"
        )


class TestRoutingEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def test_none_resource(self):
        """Verify None resource is handled gracefully."""
        # This tests a potential edge case in routing

    def test_special_characters_in_resource(self):
        """Verify special characters in resource don't break routing."""
        # Test with: spaces, unicode, special chars

    def test_very_long_resource(self):
        """Verify very long resource strings don't cause issues."""
        # Test with 10KB+ resource string


if __name__ == '__main__':
    unittest.main()
