"""Tests for reveal.adapters.base module."""

import unittest
import warnings
import pytest

from reveal.adapters.base import (
    ResourceAdapter,
    register_adapter,
    get_adapter_class,
    list_supported_schemes,
    _ADAPTER_REGISTRY,
    _is_constructor_error,
    _default_from_uri,
)
from reveal.adapters.factory import _legacy_init_warned

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP/network
pytestmark = pytest.mark.component


class TestResourceAdapter(unittest.TestCase):
    """Test ResourceAdapter base class."""

    def setUp(self):
        """Create a concrete implementation for testing."""
        class ConcreteAdapter(ResourceAdapter):
            def get_structure(self, **kwargs):
                return {'structure': 'data'}

        self.adapter = ConcreteAdapter()

    def test_get_element_default_returns_none(self):
        """Test that get_element returns None by default."""
        result = self.adapter.get_element('some_element')
        self.assertIsNone(result)

    def test_get_metadata_returns_class_name(self):
        """Test that get_metadata returns type with class name."""
        result = self.adapter.get_metadata()
        self.assertIsInstance(result, dict)
        self.assertIn('type', result)
        self.assertEqual(result['type'], 'ConcreteAdapter')

    def test_get_help_default_returns_none(self):
        """Test that get_help returns None by default."""
        result = ResourceAdapter.get_help()
        self.assertIsNone(result)


class TestIntParam(unittest.TestCase):
    """int_param(): explicit 0 must not be treated as absent (BACK-985)."""

    def setUp(self):
        class ConcreteAdapter(ResourceAdapter):
            def get_structure(self, **kwargs):
                return {'structure': 'data'}

        self.adapter = ConcreteAdapter()

    def test_explicit_zero_is_respected(self):
        self.adapter.query_params = {'top': 0}
        self.assertEqual(self.adapter.int_param('top', 10), 0)

    def test_absent_key_uses_default(self):
        self.adapter.query_params = {}
        self.assertEqual(self.adapter.int_param('top', 10), 10)

    def test_nonzero_value_is_respected(self):
        self.adapter.query_params = {'top': 3}
        self.assertEqual(self.adapter.int_param('top', 10), 3)

    def test_string_value_is_coerced(self):
        self.adapter.query_params = {'top': '0'}
        self.assertEqual(self.adapter.int_param('top', 10), 0)


class TestAdapterRegistry(unittest.TestCase):
    """Test adapter registration and lookup."""

    def setUp(self):
        """Save initial registry state."""
        self.initial_schemes = set(_ADAPTER_REGISTRY.keys())

    def tearDown(self):
        """Clean up test adapters from registry."""
        current_schemes = set(_ADAPTER_REGISTRY.keys())
        test_schemes = current_schemes - self.initial_schemes
        for scheme in test_schemes:
            _ADAPTER_REGISTRY.pop(scheme, None)

    def test_register_adapter_decorator(self):
        """Test that register_adapter decorator registers adapter via the public API."""
        @register_adapter('test-scheme')
        class TestAdapter(ResourceAdapter):
            def get_structure(self, **kwargs):
                return {}

        # Verify retrieval through public API, not internal dict
        result = get_adapter_class('test-scheme')
        self.assertEqual(result, TestAdapter)

        # Verify the decorator sets the scheme attribute on the class
        self.assertEqual(TestAdapter.scheme, 'test-scheme')

    def test_register_adapter_case_insensitive(self):
        """Test that scheme registration is case-insensitive."""
        @register_adapter('TEST-Case')
        class TestAdapter(ResourceAdapter):
            def get_structure(self, **kwargs):
                return {}

        # Should be stored lowercase
        self.assertIn('test-case', _ADAPTER_REGISTRY)

    def test_get_adapter_class_found(self):
        """Test get_adapter_class returns registered adapter."""
        @register_adapter('test-found')
        class TestAdapter(ResourceAdapter):
            def get_structure(self, **kwargs):
                return {}

        result = get_adapter_class('test-found')
        self.assertEqual(result, TestAdapter)

    def test_get_adapter_class_case_insensitive(self):
        """Test get_adapter_class is case-insensitive."""
        @register_adapter('test-case-lookup')
        class TestAdapter(ResourceAdapter):
            def get_structure(self, **kwargs):
                return {}

        result = get_adapter_class('TEST-CASE-LOOKUP')
        self.assertEqual(result, TestAdapter)

    def test_get_adapter_class_not_found(self):
        """Test get_adapter_class returns None for unknown scheme."""
        result = get_adapter_class('nonexistent-scheme-xyz')
        self.assertIsNone(result)

    def test_list_supported_schemes(self):
        """Test list_supported_schemes returns sorted list."""
        @register_adapter('test-z')
        class TestAdapterZ(ResourceAdapter):
            def get_structure(self, **kwargs):
                return {}

        @register_adapter('test-a')
        class TestAdapterA(ResourceAdapter):
            def get_structure(self, **kwargs):
                return {}

        schemes = list_supported_schemes()
        
        # Should be sorted
        self.assertEqual(schemes, sorted(schemes))
        
        # Should contain our test schemes
        self.assertIn('test-z', schemes)
        self.assertIn('test-a', schemes)


class TestIsConstructorError(unittest.TestCase):
    """Tests for _is_constructor_error helper (BACK-099)."""

    def test_call_site_type_error_is_not_constructor_error(self):
        """TypeError from wrong number of args (call site) should return False."""
        def one_arg(x):
            pass

        try:
            one_arg(1, 2)  # too many args — raised at call site
        except TypeError as e:
            result = _is_constructor_error(e)
        self.assertFalse(result,
                         "Call-site TypeError (wrong arg count) should not be a constructor error")

    def test_constructor_body_type_error_is_constructor_error(self):
        """TypeError raised inside a constructor body should return True."""
        class BrokenAdapter:
            def __init__(self, resource):
                x = "string"
                _ = x + 42  # TypeError inside __init__ body

        try:
            BrokenAdapter("test")
        except TypeError as e:
            result = _is_constructor_error(e)
        self.assertTrue(result,
                        "TypeError inside constructor body should be a constructor error")

    def test_default_from_uri_propagates_constructor_body_error(self):
        """_default_from_uri should raise TypeError that came from constructor body."""
        class BrokenAdapter:
            def __init__(self, resource, query=None):
                x: str = "not_an_int"
                _ = x + 42  # TypeError inside __init__ body

        with self.assertRaises(TypeError):
            _default_from_uri(BrokenAdapter, 'test', 'resource', None)

    def test_default_from_uri_continues_on_call_site_type_error(self):
        """_default_from_uri should try next pattern on call-site TypeError."""
        class SucceedsWithNoArgs:
            def __init__(self):
                self.ok = True

        # This adapter only accepts zero args; _try_no_args_init will succeed.
        adapter = _default_from_uri(SucceedsWithNoArgs, 'test', '', None)
        self.assertTrue(adapter.ok)


class TestLegacyInitDeprecation(unittest.TestCase):
    """BACK-948: try-chain is a deprecated plugin-only compatibility shim."""

    def tearDown(self):
        _legacy_init_warned.clear()

    def test_legacy_adapter_warns_once_per_class(self):
        """First use of the try-chain for a class warns; repeats don't."""
        class LegacyAdapter:
            LEGACY_INIT = True

            def __init__(self, resource):
                self.resource = resource

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            _default_from_uri(LegacyAdapter, 'test', 'r', None)
            _default_from_uri(LegacyAdapter, 'test', 'r', None)

        deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        self.assertEqual(len(deprecations), 1)
        self.assertIn('LegacyAdapter', str(deprecations[0].message))
        self.assertIn('LEGACY_INIT', str(deprecations[0].message))

    def test_canonical_adapter_does_not_warn(self):
        """LEGACY_INIT = False adapters skip the try-chain and never warn."""
        class CanonicalAdapter:
            LEGACY_INIT = False

            def __init__(self, resource='', query=None, **kwargs):
                self.resource = resource
                self.query = query

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            _default_from_uri(CanonicalAdapter, 'test', 'r', None)

        deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        self.assertEqual(len(deprecations), 0)

    def test_warning_survives_mock_adapter_class_missing_dunder_attrs(self):
        """A Mock used as adapter_class (as several routing tests do) lacks a
        real __qualname__/__module__ and raises AttributeError on access —
        warning construction must getattr() with a fallback, not crash the
        whole from_uri() call (BACK-948 regression, caught via test_routing.py
        failing with 'Error initializing ... adapter: __qualname__')."""
        from unittest.mock import Mock

        mock_adapter_class = Mock(spec=['LEGACY_INIT', '__call__'])
        mock_adapter_class.LEGACY_INIT = True
        mock_adapter_class.return_value = Mock(resource='r')

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            adapter = _default_from_uri(mock_adapter_class, 'test', '', None)

        self.assertEqual(adapter.resource, 'r')
        deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        self.assertEqual(len(deprecations), 1)


class TestCanonicalInit(unittest.TestCase):
    """ResourceAdapter.__init__ (BACK-1020): documented, additive, non-forced."""

    def test_super_init_sets_documented_attributes(self):
        class CallsSuper(ResourceAdapter):
            def __init__(self, resource='', query=None, **kwargs):
                super().__init__(resource, query, **kwargs)

            def get_structure(self, **kwargs):
                return {}

        adapter = CallsSuper('some/path', 'top=5')
        self.assertEqual(adapter.resource, 'some/path')
        self.assertEqual(adapter.query, 'top=5')
        self.assertEqual(adapter.query_params, {})
        self.assertEqual(adapter._composed_warnings, [])
        self.assertEqual(adapter._composed_errors, [])
        self.assertEqual(adapter._composed_confidences, [])

    def test_subclass_without_super_call_still_works(self):
        """Existing convention (no adapter calls super().__init__() today) —
        record_composed_error()'s setdefault() fallback must keep working."""
        class OwnInit(ResourceAdapter):
            def __init__(self, resource=''):
                self.resource = resource  # deliberately does NOT call super()

            def get_structure(self, **kwargs):
                return {}

        adapter = OwnInit('x')
        adapter.record_composed_error('child', 'x', RuntimeError('boom'))
        meta = adapter.composed_meta()
        self.assertIsNotNone(meta)
        self.assertEqual(len(meta['errors']), 1)


class TestComposedMetaConsuming(unittest.TestCase):
    """composed_meta() clears its accumulators after reading (BACK-1019) —
    a reused instance's next scan must not re-report a prior scan's errors."""

    def setUp(self):
        class ConcreteAdapter(ResourceAdapter):
            def get_structure(self, **kwargs):
                return {'structure': 'data'}

        self.adapter = ConcreteAdapter()

    def test_second_call_after_recorded_error_returns_none(self):
        self.adapter.record_composed_error('child', 'r', RuntimeError('boom'))
        first = self.adapter.composed_meta()
        self.assertIsNotNone(first)
        self.assertEqual(len(first['errors']), 1)

        second = self.adapter.composed_meta()
        self.assertIsNone(second)

    def test_fresh_error_after_consumption_is_reported_alone(self):
        self.adapter.record_composed_error('child', 'r', RuntimeError('first'))
        self.adapter.composed_meta()  # consumes it

        self.adapter.record_composed_error('child', 'r', RuntimeError('second'))
        meta = self.adapter.composed_meta()
        self.assertEqual(len(meta['errors']), 1)
        self.assertIn('second', meta['errors'][0]['message'])

    def test_healthy_scan_after_failed_scan_reports_no_errors(self):
        """BACK-1019's own verified repro shape, generalized: a DepsAdapter-like
        reused instance where compose() failed once, then succeeds — the
        second, healthy call must not carry over the first call's error."""
        from reveal.adapters.deps import DepsAdapter
        from reveal.adapters.imports import ImportsAdapter
        from unittest.mock import patch

        adapter = DepsAdapter('reveal/utils', None)

        with patch.object(ImportsAdapter, 'get_structure', side_effect=RuntimeError('boom')):
            first = adapter.get_structure()
        self.assertIsNotNone(first.get('meta'))
        self.assertTrue(first['meta'].get('errors'))

        second = adapter.get_structure()
        self.assertIsNone(second.get('meta'), "healthy re-scan must not re-report the prior call's errors")


if __name__ == '__main__':
    unittest.main()
