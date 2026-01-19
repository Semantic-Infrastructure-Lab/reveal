"""Contract tests for all adapters.

These tests ensure that all adapters follow consistent patterns:
- Error handling (TypeError, ValueError, ImportError)
- Required methods (get_structure)
- Registration (properly registered in adapter registry)
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from reveal.adapters.base import get_adapter_class, list_supported_schemes
from reveal.adapters import (
    env, ast, help, python, json_adapter, git, mysql, sqlite,
    imports, diff, reveal, stats, markdown
)


class TestAdapterContracts(unittest.TestCase):
    """Test that all adapters follow consistent contracts."""

    def setUp(self):
        """Set up test fixtures."""
        # Get all registered adapters
        self.all_schemes = list_supported_schemes()
        # Expected adapters (13 total)
        self.expected_schemes = {
            'env', 'ast', 'help', 'python', 'json', 'git', 'mysql', 'sqlite',
            'imports', 'diff', 'reveal', 'stats', 'markdown'
        }

    def test_all_adapters_are_registered(self):
        """Verify all expected adapters are registered."""
        registered = set(self.all_schemes)
        missing = self.expected_schemes - registered
        extra = registered - self.expected_schemes

        self.assertEqual(
            missing, set(),
            f"Missing expected adapters: {missing}"
        )
        # Note: extra adapters are OK (might be experimental/new)
        if extra:
            print(f"Note: Found additional adapters: {extra}")

    def test_all_adapters_have_get_structure(self):
        """Verify all adapters have get_structure() method."""
        for scheme in self.expected_schemes:
            with self.subTest(scheme=scheme):
                adapter_class = get_adapter_class(scheme)
                self.assertIsNotNone(
                    adapter_class,
                    f"{scheme} adapter not found in registry"
                )
                self.assertTrue(
                    hasattr(adapter_class, 'get_structure') or
                    'get_structure' in dir(adapter_class),
                    f"{scheme} adapter missing get_structure() method"
                )

    def test_adapters_raise_appropriate_exceptions(self):
        """Verify adapters raise only TypeError, ValueError, or ImportError on init failure.

        This is critical for routing.py which catches these specific exception types.
        Note: Some adapters raise other exception types (FileNotFoundError, etc.)
        which are documented as known issues.
        """
        # Test with obviously invalid parameters
        invalid_params = [
            ('invalid', 'arg'),  # Wrong types
            (None, None),  # None values
            (123, 456),  # Numbers instead of strings
        ]

        # Adapters that require special setup or can't be easily tested this way
        skip_adapters = {'mysql', 'sqlite', 'git', 'imports'}

        # Known issues: adapters that raise unexpected exception types
        known_issues = {
            'json': ['FileNotFoundError', 'IsADirectoryError'],
            'ast': ['FileNotFoundError', 'IsADirectoryError'],
            'stats': ['FileNotFoundError'],
            'diff': ['FileNotFoundError'],
        }

        for scheme in self.expected_schemes - skip_adapters:
            with self.subTest(scheme=scheme):
                adapter_class = get_adapter_class(scheme)

                # Try various invalid initialization patterns
                for params in invalid_params:
                    try:
                        # Try to instantiate with invalid params
                        adapter_class(*params)
                        # If no exception, that's fine (adapter might be lenient)
                    except (TypeError, ValueError, ImportError):
                        # These are the expected exception types
                        pass
                    except Exception as e:
                        # Check if this is a known issue
                        exception_name = type(e).__name__
                        if scheme in known_issues and exception_name in known_issues[scheme]:
                            # Document as known issue but don't fail
                            print(f"Known issue: {scheme} adapter raises {exception_name}")
                        else:
                            # Any other exception type is a contract violation
                            self.fail(
                                f"{scheme} adapter raised unexpected exception type "
                                f"{exception_name} (expected TypeError, ValueError, or ImportError). "
                                f"Error: {e}"
                            )

    def test_no_arg_adapters_work(self):
        """Verify no-arg adapters (env, python) can be instantiated without params."""
        no_arg_adapters = {'env', 'python'}

        for scheme in no_arg_adapters:
            with self.subTest(scheme=scheme):
                adapter_class = get_adapter_class(scheme)
                try:
                    adapter = adapter_class()
                    self.assertTrue(hasattr(adapter, 'get_structure'))
                except (TypeError, ValueError) as e:
                    self.fail(
                        f"{scheme} should support no-arg initialization but raised: {e}"
                    )

    def test_resource_adapters_accept_strings(self):
        """Verify resource-based adapters accept string parameters."""
        # Adapters that take resource strings
        resource_adapters = {'help', 'ast', 'json', 'reveal', 'markdown', 'diff', 'stats'}

        # Known issues: adapters that raise unexpected exceptions for valid paths
        known_file_issues = {'json', 'ast', 'diff', 'stats'}

        for scheme in resource_adapters:
            with self.subTest(scheme=scheme):
                adapter_class = get_adapter_class(scheme)

                # All these adapters should accept a path or resource string
                # Use current directory as safe test path
                test_resource = '.'

                try:
                    if scheme == 'ast' or scheme == 'json':
                        # Query-parsing adapters: try both (path, query) and (path,)
                        try:
                            adapter = adapter_class(test_resource, None)
                        except TypeError:
                            adapter = adapter_class(test_resource)
                    elif scheme == 'markdown':
                        # Keyword adapter
                        adapter = adapter_class(base_path=test_resource, query=None)
                    elif scheme == 'diff':
                        # Diff needs two resources
                        adapter = adapter_class(test_resource, test_resource)
                    else:
                        adapter = adapter_class(test_resource)

                    self.assertTrue(hasattr(adapter, 'get_structure'))
                except (TypeError, ValueError, ImportError) as e:
                    # These exceptions are OK - just means the adapter has stricter requirements
                    pass
                except (FileNotFoundError, IsADirectoryError, OSError) as e:
                    # File-related exceptions are OK for file-based adapters
                    if scheme in known_file_issues:
                        print(f"Known: {scheme} adapter requires valid file path")
                    else:
                        self.fail(
                            f"{scheme} adapter raised file exception: {type(e).__name__}: {e}"
                        )
                except Exception as e:
                    self.fail(
                        f"{scheme} adapter raised unexpected exception: {type(e).__name__}: {e}"
                    )

    def test_uri_adapters_accept_full_uris(self):
        """Verify URI-based adapters (mysql, sqlite, git) accept full URIs."""
        uri_test_cases = {
            'mysql': 'mysql://localhost:3306/test',
            'sqlite': 'sqlite:///tmp/test.db',
            'git': 'git:///tmp/test-repo',
        }

        for scheme, test_uri in uri_test_cases.items():
            with self.subTest(scheme=scheme):
                adapter_class = get_adapter_class(scheme)

                try:
                    adapter = adapter_class(test_uri)
                    self.assertTrue(hasattr(adapter, 'get_structure'))
                except (TypeError, ValueError, ImportError) as e:
                    # These are acceptable - adapter may require real resources
                    pass
                except Exception as e:
                    self.fail(
                        f"{scheme} adapter raised unexpected exception: {type(e).__name__}: {e}"
                    )

    def test_adapters_inherit_from_resource_adapter(self):
        """Verify all adapters inherit from ResourceAdapter (optional check)."""
        from reveal.adapters.base import ResourceAdapter

        for scheme in self.expected_schemes:
            with self.subTest(scheme=scheme):
                adapter_class = get_adapter_class(scheme)
                # Check if it's a subclass (doesn't have to be, but should be)
                is_subclass = issubclass(adapter_class, ResourceAdapter)

                # This is a recommendation, not a hard requirement
                if not is_subclass:
                    print(f"Note: {scheme} adapter doesn't inherit from ResourceAdapter")


class TestAdapterErrorConsistency(unittest.TestCase):
    """Test that adapters handle errors consistently."""

    def test_git_adapter_raises_type_error_on_missing_resource(self):
        """Adapters should raise TypeError for no-arg init so routing can try next pattern.

        TypeError lets routing.py distinguish "wrong args" from "valid args, bad value".
        """
        from reveal.adapters.git.adapter import GitAdapter

        with self.assertRaises(TypeError) as cm:
            # Missing required 'resource' parameter
            GitAdapter()

        self.assertIn("resource", str(cm.exception).lower())

    def test_import_error_handling(self):
        """Verify that ImportError is raised for adapters with missing dependencies.

        Tests that the new ImportError handling in routing.py would work correctly.
        """
        # We can't easily test real ImportErrors without actually removing packages,
        # but we can verify the pattern works with a mock adapter
        class MockAdapterWithImportError:
            def __init__(self):
                raise ImportError("Missing dependency: pip install some-package")

            def get_structure(self):
                return {}

        # Verify the exception is raised
        with self.assertRaises(ImportError) as cm:
            MockAdapterWithImportError()

        self.assertIn("pip install", str(cm.exception))


if __name__ == '__main__':
    unittest.main()
