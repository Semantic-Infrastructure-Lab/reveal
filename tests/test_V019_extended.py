"""Extended tests for V019: Adapter initialization pattern compliance.

Comprehensive edge case coverage for V019 rule testing.
"""

import unittest
from pathlib import Path
from unittest import mock

from reveal.rules.validation.V019 import V019
from reveal.rules.base import Severity


class TestV019NoRevealRoot(unittest.TestCase):
    """Test V019 when reveal root cannot be found."""

    def setUp(self):
        self.rule = V019()

    def test_no_reveal_root_returns_empty(self):
        """Test that no detections when reveal root not found."""
        with mock.patch('reveal.rules.validation.V019.find_reveal_root', return_value=None):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 0)


class TestV019ImportException(unittest.TestCase):
    """Test V019 when imports fail."""

    def setUp(self):
        self.rule = V019()

    def test_import_exception_returns_empty(self):
        """Test that import exceptions are handled gracefully."""
        with mock.patch('reveal.rules.validation.V019.find_reveal_root', return_value=Path('/fake')):
            # Mock the import to raise an exception
            with mock.patch.dict('sys.modules', {'reveal.adapters.base': None}):
                detections = self.rule.check(
                    file_path="reveal://test",
                    structure=None,
                    content=""
                )
                self.assertEqual(len(detections), 0)


class TestV019AdapterNotFound(unittest.TestCase):
    """Test V019 when adapter class or file not found."""

    def setUp(self):
        self.rule = V019()

    def test_adapter_class_none_skipped(self):
        """Test that None adapter class is skipped."""
        reveal_root = Path('/fake/reveal')

        with mock.patch('reveal.rules.validation.V019.find_reveal_root', return_value=reveal_root):
            # Mock at the actual import location
            with mock.patch('reveal.adapters.base.list_supported_schemes', return_value=['fake']):
                with mock.patch('reveal.adapters.base.get_adapter_class', return_value=None):
                    detections = self.rule.check(
                        file_path="reveal://test",
                        structure=None,
                        content=""
                    )
                    # Should skip adapters with None class
                    self.assertEqual(len(detections), 0)

    def test_adapter_file_none_skipped(self):
        """Test that None adapter file is skipped."""
        reveal_root = Path('/fake/reveal')
        mock_adapter_class = mock.MagicMock()

        with mock.patch('reveal.rules.validation.V019.find_reveal_root', return_value=reveal_root):
            # Mock at the actual import location
            with mock.patch('reveal.adapters.base.list_supported_schemes', return_value=['fake']):
                with mock.patch('reveal.adapters.base.get_adapter_class', return_value=mock_adapter_class):
                    with mock.patch('reveal.rules.validation.V019.find_adapter_file', return_value=None):
                        detections = self.rule.check(
                            file_path="reveal://test",
                            structure=None,
                            content=""
                        )
                        # Should skip adapters with None file
                        self.assertEqual(len(detections), 0)


class TestV019NoArgInitViolations(unittest.TestCase):
    """Test V019 no-arg initialization violations."""

    def setUp(self):
        self.rule = V019()
        self.adapter_file = Path('/fake/adapters/custom.py')

    def test_no_arg_init_valueerror_creates_detection(self):
        """Test detection when adapter raises ValueError on no-arg init."""
        class BadAdapter:
            def __init__(self):
                raise ValueError("Need arguments")

        with mock.patch('reveal.rules.validation.V019.find_init_definition_line', return_value=10):
            detection = self.rule._test_no_arg_init('custom', BadAdapter, self.adapter_file)

            self.assertIsNotNone(detection)
            self.assertIn("raises ValueError instead of TypeError", detection.message)
            self.assertIn("custom", detection.message)
            self.assertIn("TypeError", detection.suggestion)

    def test_no_arg_init_crash_creates_detection(self):
        """Test detection when adapter crashes on no-arg init."""
        class CrashingAdapter:
            def __init__(self):
                raise AttributeError("Attribute not found")

        with mock.patch('reveal.rules.validation.V019.find_init_definition_line', return_value=10):
            detection = self.rule._test_no_arg_init('custom', CrashingAdapter, self.adapter_file)

            self.assertIsNotNone(detection)
            self.assertIn("crashes with AttributeError", detection.message)
            self.assertIn("custom", detection.message)
            self.assertIn("Fix __init__", detection.suggestion)

    def test_no_arg_init_typeerror_no_detection(self):
        """Test no detection when adapter raises TypeError (expected)."""
        class GoodAdapter:
            def __init__(self, required_arg):
                pass

        detection = self.rule._test_no_arg_init('custom', GoodAdapter, self.adapter_file)
        self.assertIsNone(detection)

    def test_no_arg_init_success_no_detection(self):
        """Test no detection when adapter supports no-arg init."""
        class NoArgAdapter:
            def __init__(self):
                pass

        detection = self.rule._test_no_arg_init('custom', NoArgAdapter, self.adapter_file)
        self.assertIsNone(detection)


class TestV019ResourceInitViolations(unittest.TestCase):
    """Test V019 resource initialization violations."""

    def setUp(self):
        self.rule = V019()
        self.adapter_file = Path('/fake/adapters/custom.py')

    def test_resource_init_importerror_no_detection(self):
        """Test no detection when adapter raises ImportError (optional deps)."""
        class ImportAdapter:
            def __init__(self, resource):
                raise ImportError("Optional dependency not installed")

        detection = self.rule._test_resource_init('custom', ImportAdapter, self.adapter_file)
        self.assertIsNone(detection)

    def test_resource_init_valueerror_acceptable_no_detection(self):
        """Test no detection for acceptable ValueError (format validation)."""
        class FormatAdapter:
            def __init__(self, resource):
                raise ValueError("Resource format invalid - requires X:Y")

        detection = self.rule._test_resource_init('custom', FormatAdapter, self.adapter_file)
        # Should be None because "requires" is in error message
        self.assertIsNone(detection)

    def test_resource_init_valueerror_format_keyword_no_detection(self):
        """Test no detection for ValueError with 'format' keyword."""
        class FormatAdapter:
            def __init__(self, resource):
                raise ValueError("Invalid format for resource")

        detection = self.rule._test_resource_init('custom', FormatAdapter, self.adapter_file)
        self.assertIsNone(detection)

    def test_resource_init_valueerror_invalid_keyword_no_detection(self):
        """Test no detection for ValueError with 'invalid' keyword."""
        class ValidatingAdapter:
            def __init__(self, resource):
                raise ValueError("Invalid resource specification")

        detection = self.rule._test_resource_init('custom', ValidatingAdapter, self.adapter_file)
        self.assertIsNone(detection)

    def test_resource_init_unexpected_valueerror_creates_detection(self):
        """Test detection for unexpected ValueError."""
        class BadAdapter:
            def __init__(self, resource):
                raise ValueError("Unexpected error message")

        with mock.patch('reveal.rules.validation.V019.find_init_definition_line', return_value=10):
            detection = self.rule._test_resource_init('custom', BadAdapter, self.adapter_file)

            self.assertIsNotNone(detection)
            self.assertIn("raises unexpected ValueError", detection.message)
            self.assertIn("custom", detection.message)
            # Severity should be overridden to MEDIUM
            self.assertEqual(detection.severity, Severity.MEDIUM)

    def test_resource_init_attributeerror_creates_detection(self):
        """Test detection when adapter has AttributeError on resource init."""
        class AttributeAdapter:
            def __init__(self, resource):
                self.missing_attr.do_something()  # Causes AttributeError

        with mock.patch('reveal.rules.validation.V019.find_init_definition_line', return_value=10):
            detection = self.rule._test_resource_init('custom', AttributeAdapter, self.adapter_file)

            self.assertIsNotNone(detection)
            self.assertIn("AttributeError", detection.message)
            self.assertIn("custom", detection.message)
            self.assertIn("Fix attribute access", detection.suggestion)

    def test_resource_init_typeerror_no_detection(self):
        """Test no detection when adapter raises TypeError (expected)."""
        class StrictAdapter:
            def __init__(self, required, args):
                pass

        detection = self.rule._test_resource_init('custom', StrictAdapter, self.adapter_file)
        self.assertIsNone(detection)

    def test_resource_init_success_no_detection(self):
        """Test no detection when adapter supports resource init."""
        class ResourceAdapter:
            def __init__(self, resource):
                self.resource = resource

        detection = self.rule._test_resource_init('custom', ResourceAdapter, self.adapter_file)
        self.assertIsNone(detection)

    def test_resource_init_other_exception_no_detection(self):
        """Test no detection for other exceptions (file not found, etc.)."""
        class FileAdapter:
            def __init__(self, resource):
                raise FileNotFoundError("File not found")

        detection = self.rule._test_resource_init('custom', FileAdapter, self.adapter_file)
        # Other exceptions might be OK
        self.assertIsNone(detection)


class TestV019GetDescription(unittest.TestCase):
    """Test V019 get_description method."""

    def setUp(self):
        self.rule = V019()

    def test_get_description(self):
        """Test that get_description returns meaningful text."""
        description = self.rule.get_description()
        self.assertIsInstance(description, str)
        self.assertIn("generic_adapter_handler", description)
        self.assertIn("TypeError", description)
        self.assertGreater(len(description), 50)


if __name__ == '__main__':
    unittest.main()
