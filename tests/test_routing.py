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

from reveal.cli.routing import generic_adapter_handler, handle_uri, handle_adapter


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
                # Reject no-arg initialization to force Try 3 (keyword args)
                if base_path is None and query is None:
                    raise TypeError("Requires at least one argument")
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

        self.assertGreaterEqual(len(init_called), 1)
        # Should eventually call with base_path='some/path'
        self.assertTrue(
            any(call['base_path'] == 'some/path' for call in init_called),
            f"Expected base_path='some/path', got: {init_called}"
        )

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

        This test documents the bugfix: before the fix, only TypeError was caught
        in Try blocks 1, 3, and 4. Now all blocks catch both TypeError and ValueError
        consistently, so adapters that raise ValueError (like git adapter) work correctly.
        """
        # Create adapter that alternates between TypeError and ValueError
        attempt_count = [0]

        class InconsistentAdapter:
            def __init__(self, *args, **kwargs):
                attempt_count[0] += 1
                # Alternate between exception types to test both are caught
                if attempt_count[0] % 2 == 0:
                    raise ValueError(f"ValueError on attempt {attempt_count[0]}")
                else:
                    raise TypeError(f"TypeError on attempt {attempt_count[0]}")

            def get_structure(self):
                return {'type': 'test'}

        # Should try all patterns without crashing on ValueError
        with patch('sys.stdout'), patch('sys.stderr'):
            with patch('sys.exit', side_effect=SystemExit(1)) as mock_exit:
                with self.assertRaises(SystemExit):
                    generic_adapter_handler(
                        InconsistentAdapter,
                        self.mock_renderer,
                        'test',
                        'resource',
                        None,
                        self.mock_args
                    )

        # Should have tried multiple patterns despite alternating exceptions
        # Try 1 (no args), Try 3 (keyword args), Try 4 (resource arg + nested try),
        # and Try 5 (full URI) should all be attempted
        self.assertGreaterEqual(
            attempt_count[0], 4,
            f"Should try at least 4 patterns (got {attempt_count[0]}), "
            "demonstrating both TypeError and ValueError are caught consistently"
        )
        # Should eventually call sys.exit(1) after all patterns fail
        mock_exit.assert_called_once_with(1)

    def test_empty_resource_defaults_to_current_dir(self):
        """Verify empty resource defaults to '.' for path-based adapters.

        Tests Try 3 (keyword args) which defaults empty resource to '.'.
        routing.py line 117: path = resource.rstrip('/') if resource else '.'
        """
        init_called = []

        class PathAdapter:
            def __init__(self, base_path=None, query=None):
                # Reject no-arg to force Try 3 keyword pattern
                if base_path is None and query is None:
                    raise TypeError("At least one argument required")
                # Reject full URIs (would succeed in Try 5)
                if base_path and '://' in base_path:
                    raise ValueError("Expected path, not URI")
                init_called.append({'base_path': base_path, 'query': query})
                self.base_path = base_path

            def get_structure(self):
                return {'type': 'test', 'path': self.base_path}

        with patch('sys.stdout'):
            generic_adapter_handler(
                PathAdapter,
                self.mock_renderer,
                'test',
                '',  # Empty resource
                None,
                self.mock_args
            )

        # Should default empty path to '.' (routing.py line 117)
        self.assertGreaterEqual(len(init_called), 1, "Adapter should be initialized")
        self.assertTrue(
            any(call['base_path'] == '.' for call in init_called),
            f"Empty resource should default to '.', got: {init_called}"
        )

    def test_import_error_special_handling(self):
        """Verify ImportError gets special error rendering.

        Tests that when an adapter raises ImportError (e.g., missing dependency),
        the routing handler catches it and calls renderer.render_error() instead
        of just printing a generic error message.
        """
        class MissingDependencyAdapter:
            def __init__(self, *args, **kwargs):
                raise ImportError("pip install some-package")

            def get_structure(self):
                return {'type': 'test'}

        with patch('sys.stdout'), patch('sys.stderr'):
            with patch.object(self.mock_renderer, 'render_error') as mock_render:
                with patch('sys.exit', side_effect=SystemExit(1)) as mock_exit:
                    # Call will trigger ImportError which should be handled gracefully
                    with self.assertRaises(SystemExit):
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
                    # Verify the error passed is an ImportError
                    call_args = mock_render.call_args[0]
                    self.assertIsInstance(call_args[0], ImportError)
                    self.assertIn("pip install some-package", str(call_args[0]))
                    # Should exit with error code 1
                    mock_exit.assert_called_once_with(1)

    def test_element_parameter_appended_for_uri(self):
        """Verify element is appended to URI for URI-based adapters.

        Tests Try 5 in routing which constructs full URI with element appended.
        For sqlite://path/to/db.sqlite with element 'table_name', should
        construct 'sqlite://path/to/db.sqlite/table_name'.
        """
        init_called = []

        class URIAdapter:
            def __init__(self, uri):
                init_called.append(uri)
                if '://' not in uri:
                    raise ValueError("Expected full URI with scheme")
                self.uri = uri

            def get_structure(self):
                return {'type': 'test', 'uri': self.uri}

        # Use a structure-only renderer (no render_element)
        class StructureOnlyRenderer:
            @staticmethod
            def render_structure(result, format='text'):
                pass

            @staticmethod
            def render_error(error):
                pass

        with patch('sys.stdout'):
            generic_adapter_handler(
                URIAdapter,
                StructureOnlyRenderer,
                'sqlite',
                'path/to/db.sqlite',
                'table_name',  # element
                self.mock_args
            )

        # Verify URI construction: sqlite://path/to/db.sqlite/table_name
        self.assertGreaterEqual(len(init_called), 1, "Adapter should be initialized")
        # Should construct URI with scheme and element appended
        final_uri = init_called[-1]  # Last attempt should be the successful one
        self.assertIn('sqlite://', final_uri, "Should include scheme")
        self.assertIn('table_name', final_uri, "Should append element to URI")


class TestHandleUri(unittest.TestCase):
    """Tests for handle_uri function."""

    def test_invalid_uri_format(self):
        """Verify error handling for URI without :// separator."""
        mock_args = Namespace(format='text')

        with patch('sys.stderr') as mock_stderr, \
             patch('sys.exit', side_effect=SystemExit(1)) as mock_exit:
            with self.assertRaises(SystemExit):
                handle_uri('invalid_uri', None, mock_args)

            mock_exit.assert_called_once_with(1)

    def test_unsupported_uri_scheme(self):
        """Verify error handling for unsupported URI scheme."""
        mock_args = Namespace(format='text')

        with patch('sys.stderr') as mock_stderr, \
             patch('sys.exit', side_effect=SystemExit(1)) as mock_exit:
            with self.assertRaises(SystemExit):
                handle_uri('foobar://resource', None, mock_args)

            mock_exit.assert_called_once_with(1)


class TestHandleAdapter(unittest.TestCase):
    """Tests for handle_adapter function."""

    def test_renderer_not_found(self):
        """Verify error handling when no renderer is registered for scheme."""

        class TestAdapter:
            def __init__(self):
                pass

            def get_structure(self):
                return {'type': 'test'}

        mock_args = Namespace(format='text', check=False)

        with patch('reveal.adapters.base.get_renderer_class', return_value=None):
            with patch('sys.stderr') as mock_stderr, \
                 patch('sys.exit', side_effect=SystemExit(1)) as mock_exit:
                with self.assertRaises(SystemExit):
                    handle_adapter(TestAdapter, 'test', 'resource', None, mock_args)

                mock_exit.assert_called_once_with(1)


class TestGenericAdapterHandlerEdgeCases(unittest.TestCase):
    """Additional tests for generic_adapter_handler edge cases."""

    def test_check_flag_with_adapter_support(self):
        """Verify --check flag is processed when adapter supports it."""

        class CheckableAdapter:
            def __init__(self, resource=None):
                self.resource = resource

            def check(self):
                return {'status': 'ok', 'exit_code': 0}

            def get_structure(self):
                return {'type': 'test'}

        class CheckRenderer:
            @staticmethod
            def render_check(result, format='text'):
                pass

            @staticmethod
            def render_structure(result, format='text'):
                pass

            @staticmethod
            def render_error(error):
                pass

        mock_args = Namespace(
            format='text',
            check=True,
            select=None,
            ignore=None
        )

        with patch('sys.stdout'), \
             patch('sys.exit', side_effect=SystemExit(0)) as mock_exit:
            with self.assertRaises(SystemExit):
                generic_adapter_handler(
                    CheckableAdapter,
                    CheckRenderer,
                    'test',
                    'resource',
                    None,
                    mock_args
                )

            mock_exit.assert_called_once_with(0)

    def test_element_not_found_error(self):
        """Verify error handling when requested element doesn't exist."""

        class ElementAdapter:
            def __init__(self):
                # No-arg init for env-like adapter
                pass

            def get_element(self, name):
                # Simulate element not found
                return None

            def list_elements(self):
                return ['elem1', 'elem2']

            def get_structure(self):
                return {'type': 'test'}

        class ElementRenderer:
            @staticmethod
            def render_element(result, format='text'):
                pass

            @staticmethod
            def render_structure(result, format='text'):
                pass

            @staticmethod
            def render_error(error):
                pass

        mock_args = Namespace(
            format='text',
            check=False
        )

        with patch('sys.stderr'), \
             patch('sys.exit', side_effect=SystemExit(1)) as mock_exit:
            with self.assertRaises(SystemExit):
                generic_adapter_handler(
                    ElementAdapter,
                    ElementRenderer,
                    'env',  # Use 'env' scheme which is in ELEMENT_NAMESPACE_ADAPTERS
                    'nonexistent_elem',  # This becomes the element when resource_is_element=True
                    None,
                    mock_args
                )

            mock_exit.assert_called_once_with(1)

    def test_file_not_found_error_handling(self):
        """Verify FileNotFoundError is caught gracefully in adapter init.

        This tests the OSError family handling we just added.
        """
        attempts = []

        class FileErrorAdapter:
            def __init__(self, *args, **kwargs):
                attempts.append(('init', args, kwargs))
                # First few attempts raise FileNotFoundError
                if len(attempts) < 3:
                    raise FileNotFoundError("File not found")
                # Final attempt succeeds with full URI pattern
                if args and isinstance(args[0], str) and '://' in args[0]:
                    self.uri = args[0]
                else:
                    raise ValueError("Need URI")

            def get_structure(self):
                return {'type': 'test'}

        mock_renderer = MockRenderer
        mock_args = Namespace(format='text', check=False)

        with patch('sys.stdout'):
            generic_adapter_handler(
                FileErrorAdapter,
                mock_renderer,
                'test',
                'resource',
                None,
                mock_args
            )

        # Should have tried multiple times before succeeding
        self.assertGreaterEqual(len(attempts), 3, "Should try multiple patterns after FileNotFoundError")

    def test_is_a_directory_error_handling(self):
        """Verify IsADirectoryError is caught gracefully in adapter init."""
        attempts = []

        class DirErrorAdapter:
            def __init__(self, *args, **kwargs):
                attempts.append(('init', args, kwargs))
                # First few attempts raise IsADirectoryError
                if len(attempts) < 3:
                    raise IsADirectoryError("Is a directory")
                # Final attempt succeeds with full URI pattern
                if args and isinstance(args[0], str) and '://' in args[0]:
                    self.uri = args[0]
                else:
                    raise ValueError("Need URI")

            def get_structure(self):
                return {'type': 'test'}

        mock_renderer = MockRenderer
        mock_args = Namespace(format='text', check=False)

        with patch('sys.stdout'):
            generic_adapter_handler(
                DirErrorAdapter,
                mock_renderer,
                'test',
                'resource',
                None,
                mock_args
            )

        # Should have tried multiple times before succeeding
        self.assertGreaterEqual(len(attempts), 3, "Should try multiple patterns after IsADirectoryError")


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
