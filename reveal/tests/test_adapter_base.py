"""Tests for reveal.adapters.base module."""

import unittest
from reveal.adapters.base import (
    ResourceAdapter,
    register_adapter,
    get_adapter_class,
    list_supported_schemes,
    _ADAPTER_REGISTRY
)


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
        """Test that register_adapter decorator registers adapter."""
        @register_adapter('test-scheme')
        class TestAdapter(ResourceAdapter):
            def get_structure(self, **kwargs):
                return {}

        # Check adapter is registered
        self.assertIn('test-scheme', _ADAPTER_REGISTRY)
        self.assertEqual(_ADAPTER_REGISTRY['test-scheme'], TestAdapter)

        # Check scheme attribute is set
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


if __name__ == '__main__':
    unittest.main()
