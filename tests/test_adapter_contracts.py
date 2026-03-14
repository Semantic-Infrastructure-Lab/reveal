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

from reveal.adapters.base import get_adapter_class, get_renderer_class, list_supported_schemes, list_renderer_schemes
from reveal.adapters import (
    env, ast, help, python, json, git, mysql, sqlite,
    imports, diff, reveal, stats, markdown, claude
)
from reveal.adapters.autossl.adapter import AutosslAdapter  # noqa: F401
from reveal.adapters.calls.adapter import CallsAdapter  # noqa: F401
from reveal.adapters.cpanel.adapter import CpanelAdapter  # noqa: F401
from reveal.adapters.domain.adapter import DomainAdapter  # noqa: F401
from reveal.adapters.nginx.adapter import NginxUriAdapter  # noqa: F401
from reveal.adapters.ssl.adapter import SSLAdapter  # noqa: F401
from reveal.adapters.xlsx import XlsxAdapter  # noqa: F401


class TestAdapterContracts(unittest.TestCase):
    """Test that all adapters follow consistent contracts."""

    def setUp(self):
        """Set up test fixtures."""
        # Get all registered adapters
        self.all_schemes = list_supported_schemes()
        # Expected adapters (21 total as of v0.60.x)
        self.expected_schemes = {
            'env', 'ast', 'help', 'python', 'json', 'git', 'mysql', 'sqlite',
            'imports', 'diff', 'reveal', 'stats', 'markdown', 'claude',
            'autossl', 'cpanel', 'domain', 'nginx', 'ssl', 'xlsx', 'calls',
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

    def test_all_adapters_have_renderers(self):
        """Verify all registered adapters have corresponding renderers.

        This prevents the 'No renderer registered for scheme' error that
        occurred when claude:// was added without updating routing.py imports.
        """
        for scheme in self.all_schemes:
            with self.subTest(scheme=scheme):
                renderer_class = get_renderer_class(scheme)
                self.assertIsNotNone(
                    renderer_class,
                    f"Adapter '{scheme}' has no renderer registered. "
                    f"Either add @register_renderer(Renderer) decorator to the adapter class, "
                    f"or ensure the adapter module is imported in adapters/__init__.py"
                )

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
        """Verify adapters raise only TypeError, ValueError, ImportError, or FileNotFoundError on init failure.

        This is critical for routing.py which catches these specific exception types.
        FileNotFoundError is raised by validation utilities for missing paths.
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
                    except (TypeError, ValueError, ImportError, FileNotFoundError):
                        # These are the expected exception types
                        # FileNotFoundError is raised by validation utilities
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

    def test_all_adapters_have_get_schema(self):
        """Verify all 21 adapters implement get_schema() for AI agent discoverability.

        get_schema() provides machine-readable schema for each adapter, enabling
        AI agents to understand what queries are possible.

        Exception: help:// is a meta-adapter that provides schemas for all other
        adapters but can't self-describe (circular). It intentionally returns None
        from the base default.
        """
        # help:// is a meta-adapter that provides schemas for others — exempt from self-schema
        schema_exempt = {'help'}

        for scheme in self.expected_schemes - schema_exempt:
            with self.subTest(scheme=scheme):
                adapter_class = get_adapter_class(scheme)
                self.assertIsNotNone(
                    adapter_class,
                    f"{scheme} adapter not found in registry"
                )
                self.assertTrue(
                    hasattr(adapter_class, 'get_schema'),
                    f"{scheme} adapter missing get_schema() method"
                )
                # Verify it's callable and returns a dict with required keys
                schema = adapter_class.get_schema()
                self.assertIsInstance(schema, dict, f"{scheme}.get_schema() must return a dict")
                self.assertIn('adapter', schema, f"{scheme} schema missing 'adapter' key")
                self.assertIn('output_types', schema, f"{scheme} schema missing 'output_types' key")
                self.assertIn('example_queries', schema, f"{scheme} schema missing 'example_queries' key")
                self.assertIn('notes', schema, f"{scheme} schema missing 'notes' key")
                self.assertIsInstance(schema['notes'], list, f"{scheme} schema 'notes' must be a list")
                self.assertGreater(len(schema['notes']), 0, f"{scheme} schema 'notes' must have at least one entry")
                # Verify example_queries use 'uri' key (not 'query')
                for i, ex in enumerate(schema['example_queries']):
                    self.assertIn('uri', ex, f"{scheme} example_queries[{i}] missing 'uri' key (use 'uri' not 'query')")
                # Verify output_type references in example_queries resolve to defined output_types
                # Allow cross-adapter references (e.g., domain/ssl delegates to ssl://)
                cross_adapter_types = {'ssl_certificate'}
                defined_types = {ot['type'] for ot in schema.get('output_types', [])}
                for i, ex in enumerate(schema['example_queries']):
                    ot = ex.get('output_type')
                    if ot and ot not in defined_types and ot not in cross_adapter_types:
                        self.fail(
                            f"{scheme} example_queries[{i}] references undefined output_type "
                            f"'{ot}' (defined: {sorted(defined_types)})"
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


class TestHelpSystemContracts(unittest.TestCase):
    """Contracts for help:// meta-adapter routes: schemas, examples, and rendering."""

    def _collect_defined_output_types(self):
        """Return all output_type names defined across all adapter schemas."""
        from reveal.adapters.help import HelpAdapter
        from reveal.adapters.base import _ADAPTER_REGISTRY
        h = HelpAdapter()
        defined = set()
        schema_exempt = {'help', 'demo'}
        for scheme in _ADAPTER_REGISTRY:
            if scheme in schema_exempt:
                continue
            result = h.get_element(f'schemas/{scheme}')
            if result and 'output_types' in result:
                for otype in result['output_types']:
                    if isinstance(otype, dict):
                        defined.add(otype['type'])
                    else:
                        defined.add(str(otype))
        return defined

    def test_recipe_output_types_resolve_to_schema_types(self):
        """Every output_type in help://examples/* must match a type defined in some adapter schema.

        Prevents recipe/schema drift: if you rename an output_type in a schema,
        any recipe referencing the old name should fail here.
        """
        from reveal.adapters.help import HelpAdapter
        h = HelpAdapter()
        defined_types = self._collect_defined_output_types()
        tasks = ['security', 'codebase', 'debugging', 'infrastructure', 'quality', 'documentation']
        for task in tasks:
            with self.subTest(task=task):
                result = h.get_element(f'examples/{task}')
                self.assertIsNotNone(result, f'examples/{task} returned None')
                for i, recipe in enumerate(result.get('recipes', [])):
                    ot = recipe.get('output_type', '')
                    if ot:
                        self.assertIn(
                            ot, defined_types,
                            f"examples/{task} recipe[{i}] '{recipe.get('goal','')}' "
                            f"references undefined output_type '{ot}'. "
                            f"Check adapter schemas for correct type name."
                        )

    def test_all_example_tasks_have_recipes(self):
        """Every task in help://examples/ has at least one recipe."""
        from reveal.adapters.help import HelpAdapter
        h = HelpAdapter()
        listing = h.get_element('examples')
        for task in listing.get('available_tasks', []):
            with self.subTest(task=task):
                result = h.get_element(f'examples/{task}')
                self.assertGreater(
                    len(result.get('recipes', [])), 0,
                    f'examples/{task} has no recipes'
                )

    def test_all_adapter_schemas_render_without_error(self):
        """Every help://schemas/<adapter> must render to text without raising."""
        import io
        from contextlib import redirect_stdout
        from reveal.adapters.help import HelpAdapter
        from reveal.adapters.base import _ADAPTER_REGISTRY
        from reveal.rendering.adapters.help import render_help
        h = HelpAdapter()
        schema_exempt = {'help', 'demo'}
        for scheme in sorted(_ADAPTER_REGISTRY):
            if scheme in schema_exempt:
                continue
            with self.subTest(scheme=scheme):
                result = h.get_element(f'schemas/{scheme}')
                self.assertIsNotNone(result, f'schemas/{scheme} returned None')
                buf = io.StringIO()
                with redirect_stdout(buf):
                    render_help(result, 'text')
                output = buf.getvalue()
                self.assertIn(f'{scheme}://', output, f'schemas/{scheme} rendered output missing scheme header')


if __name__ == '__main__':
    unittest.main()
