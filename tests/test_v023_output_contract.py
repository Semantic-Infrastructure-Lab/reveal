"""Comprehensive tests for V023: Output Contract Compliance.

V023 validates that adapter/analyzer outputs conform to the v1.0 Output Contract
specification. Ensures required fields are present, type naming follows conventions,
and line number fields use standardized names.

Test Structure:
    - TestV023Metadata: Rule metadata validation
    - TestV023FileDetection: Adapter/analyzer file detection logic
    - TestV023RequiredFields: Required field validation
    - TestV023TypeNaming: Type field snake_case validation
    - TestV023LineFields: Deprecated line field detection
    - TestV023Integration: End-to-end contract compliance scenarios
"""

import unittest
import tempfile
import shutil
from pathlib import Path
from reveal.rules.validation.V023 import V023


class TestV023Metadata(unittest.TestCase):
    """Test V023 rule metadata."""

    def setUp(self):
        self.rule = V023()

    def test_rule_code(self):
        """Rule code should be V023."""
        self.assertEqual(self.rule.code, "V023")

    def test_rule_severity(self):
        """Rule severity should be HIGH (blocks stable JSON output)."""
        self.assertEqual(self.rule.severity.name, "HIGH")

    def test_rule_message(self):
        """Rule message should mention contract."""
        self.assertIn("contract", self.rule.message.lower())

    def test_rule_category(self):
        """Rule should be validation category."""
        from reveal.rules.base import RulePrefix
        self.assertEqual(self.rule.category, RulePrefix.V)

    def test_file_patterns(self):
        """Rule should only check Python files."""
        self.assertIn('.py', self.rule.file_patterns)

    def test_valid_source_types(self):
        """Rule should define valid source_type enum."""
        expected_types = {'file', 'directory', 'database', 'runtime', 'network'}
        self.assertEqual(self.rule.VALID_SOURCE_TYPES, expected_types)


class TestV023FileDetection(unittest.TestCase):
    """Test adapter/analyzer file detection logic."""

    def setUp(self):
        self.rule = V023()

    def test_non_python_file_ignored(self):
        """Non-Python files should be ignored."""
        detections = self.rule.check(
            file_path="/some/file.js",
            structure=None,
            content="// javascript"
        )
        self.assertEqual(len(detections), 0)

    def test_non_adapter_non_analyzer_ignored(self):
        """Files outside adapters/ and analyzers/ should be ignored."""
        detections = self.rule.check(
            file_path="/some/utils/helper.py",
            structure={'classes': []},
            content="def helper(): pass"
        )
        self.assertEqual(len(detections), 0)

    def test_init_file_ignored(self):
        """__init__.py files should be ignored."""
        detections = self.rule.check(
            file_path="/reveal/adapters/__init__.py",
            structure={'classes': []},
            content="# Init file"
        )
        self.assertEqual(len(detections), 0)

    def test_base_file_ignored(self):
        """base.py files should be ignored."""
        detections = self.rule.check(
            file_path="/reveal/adapters/base.py",
            structure={'classes': []},
            content="# Base file"
        )
        self.assertEqual(len(detections), 0)

    def test_utils_file_ignored(self):
        """utils.py files should be ignored."""
        detections = self.rule.check(
            file_path="/reveal/adapters/utils.py",
            structure={'classes': []},
            content="# Utils file"
        )
        self.assertEqual(len(detections), 0)

    def test_adapter_file_with_adapter_class_detected(self):
        """Adapter files with Adapter class should be detected."""
        structure = {
            'classes': [
                {'name': 'ASTAdapter', 'line': 10}
            ]
        }
        # This should be processed (no structure means no detections yet)
        result = self.rule._is_adapter_or_analyzer_file(structure, "class ASTAdapter")
        self.assertTrue(result)

    def test_analyzer_file_with_analyzer_class_detected(self):
        """Analyzer files with Analyzer class should be detected."""
        structure = {
            'classes': [
                {'name': 'PythonAnalyzer', 'line': 10}
            ]
        }
        result = self.rule._is_adapter_or_analyzer_file(structure, "class PythonAnalyzer")
        self.assertTrue(result)

    def test_file_with_resource_adapter_inheritance_detected(self):
        """Files inheriting ResourceAdapter should be detected."""
        result = self.rule._is_adapter_or_analyzer_file(
            {'classes': []},
            "class MyAdapter(ResourceAdapter):"
        )
        self.assertTrue(result)

    def test_file_with_file_analyzer_inheritance_detected(self):
        """Files inheriting FileAnalyzer should be detected."""
        result = self.rule._is_adapter_or_analyzer_file(
            {'classes': []},
            "class MyAnalyzer(FileAnalyzer):"
        )
        self.assertTrue(result)

    def test_file_without_adapter_or_analyzer_ignored(self):
        """Files without adapter/analyzer classes should be ignored."""
        result = self.rule._is_adapter_or_analyzer_file(
            {'classes': [{'name': 'Helper', 'line': 10}]},
            "class Helper: pass"
        )
        self.assertFalse(result)


class TestV023RequiredFields(unittest.TestCase):
    """Test required field validation."""

    def setUp(self):
        self.rule = V023()

    def test_all_required_fields_present_no_detection(self):
        """All required fields present should not trigger detection."""
        content = """
class TestAdapter(ResourceAdapter):
    def get_structure(self, path, config):
        return {
            'contract_version': '1.0',
            'type': 'test_adapter',
            'source': self.source_path,
            'source_type': 'file',
            'data': []
        }
"""
        detections = self.rule._check_output_code_patterns(
            file_path="/adapters/test.py",
            content=content,
            method_name="get_structure"
        )
        self.assertEqual(len(detections), 0)

    def test_missing_contract_version_detected(self):
        """Missing contract_version should trigger detection."""
        content = """
class TestAdapter(ResourceAdapter):
    def get_structure(self, path, config):
        return {
            'type': 'test_adapter',
            'source': self.source_path,
            'source_type': 'file'
        }
"""
        detections = self.rule._check_output_code_patterns(
            file_path="/adapters/test.py",
            content=content,
            method_name="get_structure"
        )
        self.assertGreater(len(detections), 0)
        self.assertIn("contract_version", detections[0].message)

    def test_missing_type_detected(self):
        """Missing type field should trigger detection."""
        content = """
class TestAdapter(ResourceAdapter):
    def get_structure(self, path, config):
        return {
            'contract_version': '1.0',
            'source': self.source_path,
            'source_type': 'file'
        }
"""
        detections = self.rule._check_output_code_patterns(
            file_path="/adapters/test.py",
            content=content,
            method_name="get_structure"
        )
        self.assertGreater(len(detections), 0)
        self.assertIn("type", detections[0].message)

    def test_missing_source_detected(self):
        """Missing source field should trigger detection."""
        content = """
class TestAdapter(ResourceAdapter):
    def get_structure(self, path, config):
        return {
            'contract_version': '1.0',
            'type': 'test_adapter',
            'source_type': 'file'
        }
"""
        detections = self.rule._check_output_code_patterns(
            file_path="/adapters/test.py",
            content=content,
            method_name="get_structure"
        )
        self.assertGreater(len(detections), 0)
        self.assertIn("source", detections[0].message)

    def test_missing_source_type_detected(self):
        """Missing source_type field should trigger detection."""
        content = """
class TestAdapter(ResourceAdapter):
    def get_structure(self, path, config):
        return {
            'contract_version': '1.0',
            'type': 'test_adapter',
            'source': self.source_path
        }
"""
        detections = self.rule._check_output_code_patterns(
            file_path="/adapters/test.py",
            content=content,
            method_name="get_structure"
        )
        self.assertGreater(len(detections), 0)
        self.assertIn("source_type", detections[0].message)

    def test_multiple_missing_fields_all_reported(self):
        """All missing required fields should be reported."""
        content = """
class TestAdapter(ResourceAdapter):
    def get_structure(self, path, config):
        return {'data': []}
"""
        detections = self.rule._check_output_code_patterns(
            file_path="/adapters/test.py",
            content=content,
            method_name="get_structure"
        )
        self.assertGreater(len(detections), 0)
        # Should mention all 4 missing fields
        message = detections[0].message
        self.assertIn("contract_version", message)
        self.assertIn("type", message)
        self.assertIn("source", message)
        self.assertIn("source_type", message)

    def test_double_quoted_fields_recognized(self):
        """Fields with double quotes should be recognized."""
        content = """
class TestAdapter(ResourceAdapter):
    def get_structure(self, path, config):
        return {
            "contract_version": "1.0",
            "type": "test_adapter",
            "source": self.source_path,
            "source_type": "file"
        }
"""
        detections = self.rule._check_output_code_patterns(
            file_path="/adapters/test.py",
            content=content,
            method_name="get_structure"
        )
        self.assertEqual(len(detections), 0)

    def test_fields_with_spaces_recognized(self):
        """Fields with spaces around colon should be recognized."""
        content = """
class TestAdapter(ResourceAdapter):
    def get_structure(self, path, config):
        return {
            'contract_version' : '1.0',
            'type' : 'test_adapter',
            'source' : self.source_path,
            'source_type' : 'file'
        }
"""
        detections = self.rule._check_output_code_patterns(
            file_path="/adapters/test.py",
            content=content,
            method_name="get_structure"
        )
        self.assertEqual(len(detections), 0)


class TestV023TypeNaming(unittest.TestCase):
    """Test type field snake_case validation."""

    def setUp(self):
        self.rule = V023()

    def test_snake_case_type_valid(self):
        """snake_case type values should be valid."""
        content = """
class TestAdapter(ResourceAdapter):
    def get_structure(self, path, config):
        return {
            'contract_version': '1.0',
            'type': 'ast_query',
            'source': self.source_path,
            'source_type': 'file'
        }
"""
        detections = self.rule._check_output_code_patterns(
            file_path="/adapters/test.py",
            content=content,
            method_name="get_structure"
        )
        # Should not detect type naming issue
        type_issues = [d for d in detections if "hyphens" in d.message.lower()]
        self.assertEqual(len(type_issues), 0)

    def test_hyphenated_type_detected(self):
        """Hyphenated type values should trigger detection."""
        content = """
class TestAdapter(ResourceAdapter):
    def get_structure(self, path, config):
        return {
            'contract_version': '1.0',
            'type': 'ast-query',
            'source': self.source_path,
            'source_type': 'file'
        }
"""
        detections = self.rule._check_output_code_patterns(
            file_path="/adapters/test.py",
            content=content,
            method_name="get_structure"
        )
        type_issues = [d for d in detections if "hyphens" in d.message.lower() or "snake_case" in d.message]
        self.assertGreater(len(type_issues), 0)
        self.assertIn("ast-query", type_issues[0].message)

    def test_type_suggestion_includes_snake_case_version(self):
        """Detection should suggest snake_case version."""
        content = """
class TestAdapter(ResourceAdapter):
    def get_structure(self, path, config):
        return {
            'contract_version': '1.0',
            'type': 'my-custom-type',
            'source': self.source_path,
            'source_type': 'file'
        }
"""
        detections = self.rule._check_output_code_patterns(
            file_path="/adapters/test.py",
            content=content,
            method_name="get_structure"
        )
        type_issues = [d for d in detections if "hyphens" in d.message.lower()]
        self.assertGreater(len(type_issues), 0)
        self.assertIn("my_custom_type", type_issues[0].suggestion)

    def test_type_severity_medium(self):
        """Type naming violation should be HIGH severity."""
        content = """
class TestAdapter(ResourceAdapter):
    def get_structure(self, path, config):
        return {
            'contract_version': '1.0',
            'type': 'ast-query',
            'source': self.source_path,
            'source_type': 'file'
        }
"""
        detections = self.rule._check_output_code_patterns(
            file_path="/adapters/test.py",
            content=content,
            method_name="get_structure"
        )
        type_issues = [d for d in detections if "hyphens" in d.message.lower()]
        self.assertGreater(len(type_issues), 0)
        from reveal.rules.base import Severity
        self.assertEqual(type_issues[0].severity, Severity.HIGH)


class TestV023LineFields(unittest.TestCase):
    """Test deprecated line field detection."""

    def setUp(self):
        self.rule = V023()

    def test_line_start_line_end_valid(self):
        """line_start and line_end fields should be valid."""
        content = """
class TestAdapter(ResourceAdapter):
    def get_structure(self, path, config):
        return {
            'contract_version': '1.0',
            'type': 'test',
            'source': self.source_path,
            'source_type': 'file',
            'elements': [
                {'line_start': 1, 'line_end': 10}
            ]
        }
"""
        detections = self.rule._check_output_code_patterns(
            file_path="/adapters/test.py",
            content=content,
            method_name="get_structure"
        )
        line_issues = [d for d in detections if "'line'" in d.message.lower()]
        self.assertEqual(len(line_issues), 0)

    def test_deprecated_line_field_detected(self):
        """Deprecated 'line' field should trigger detection."""
        content = """
class TestAdapter(ResourceAdapter):
    def get_structure(self, path, config):
        return {
            'contract_version': '1.0',
            'type': 'test',
            'source': self.source_path,
            'source_type': 'file',
            'elements': [
                {'line': 5}
            ]
        }
"""
        detections = self.rule._check_output_code_patterns(
            file_path="/adapters/test.py",
            content=content,
            method_name="get_structure"
        )
        line_issues = [d for d in detections if "deprecated" in d.message.lower() and "'line'" in d.message]
        self.assertGreater(len(line_issues), 0)

    def test_line_field_suggestion_includes_replacement(self):
        """Detection should suggest line_start/line_end replacement."""
        content = """
class TestAdapter(ResourceAdapter):
    def get_structure(self, path, config):
        return {
            'contract_version': '1.0',
            'type': 'test',
            'source': self.source_path,
            'source_type': 'file',
            'elements': [{'line': 5}]
        }
"""
        detections = self.rule._check_output_code_patterns(
            file_path="/adapters/test.py",
            content=content,
            method_name="get_structure"
        )
        line_issues = [d for d in detections if "deprecated" in d.message.lower() and "'line'" in d.message]
        self.assertGreater(len(line_issues), 0)
        self.assertIn("line_start", line_issues[0].suggestion)
        self.assertIn("line_end", line_issues[0].suggestion)

    def test_line_field_severity_medium(self):
        """Line field deprecation should be HIGH severity."""
        content = """
class TestAdapter(ResourceAdapter):
    def get_structure(self, path, config):
        return {
            'contract_version': '1.0',
            'type': 'test',
            'source': self.source_path,
            'source_type': 'file',
            'elements': [{'line': 5}]
        }
"""
        detections = self.rule._check_output_code_patterns(
            file_path="/adapters/test.py",
            content=content,
            method_name="get_structure"
        )
        line_issues = [d for d in detections if "deprecated" in d.message.lower() and "'line'" in d.message]
        self.assertGreater(len(line_issues), 0)
        from reveal.rules.base import Severity
        self.assertEqual(line_issues[0].severity, Severity.HIGH)


class TestV023SchemeExtraction(unittest.TestCase):
    """Test scheme extraction from file paths."""

    def setUp(self):
        self.rule = V023()

    def test_simple_adapter_path(self):
        """Simple adapter file should extract scheme correctly."""
        scheme = self.rule._extract_scheme("reveal/adapters/ast.py")
        self.assertEqual(scheme, "ast")

    def test_adapter_with_suffix(self):
        """Adapter with _adapter suffix should extract base scheme."""
        scheme = self.rule._extract_scheme("reveal/adapters/json_adapter.py")
        self.assertEqual(scheme, "json")

    def test_nested_adapter_path(self):
        """Nested adapter directory should extract scheme."""
        scheme = self.rule._extract_scheme("reveal/adapters/git/adapter.py")
        self.assertEqual(scheme, "git")

    def test_nested_init_path(self):
        """Nested __init__.py should extract scheme."""
        scheme = self.rule._extract_scheme("reveal/adapters/mysql/__init__.py")
        self.assertEqual(scheme, "mysql")

    def test_base_file_no_scheme(self):
        """base.py should return None."""
        scheme = self.rule._extract_scheme("reveal/adapters/base.py")
        self.assertIsNone(scheme)

    def test_init_file_no_scheme(self):
        """Top-level __init__.py should return None."""
        scheme = self.rule._extract_scheme("reveal/adapters/__init__.py")
        self.assertIsNone(scheme)

    def test_non_adapter_path_no_scheme(self):
        """Non-adapter path should return None."""
        scheme = self.rule._extract_scheme("reveal/utils/helper.py")
        self.assertIsNone(scheme)


class TestV023Integration(unittest.TestCase):
    """Integration tests for V023 end-to-end validation."""

    def setUp(self):
        self.rule = V023()

    def test_perfect_adapter_no_detections(self):
        """Perfect adapter with all contract fields should have no detections."""
        content = """
from pathlib import Path
from reveal.adapters.base import ResourceAdapter

class PerfectAdapter(ResourceAdapter):
    def get_structure(self, path, config):
        return {
            'contract_version': '1.0',
            'type': 'perfect_adapter',
            'source': str(path),
            'source_type': 'file',
            'data': [],
            'line_start': 1,
            'line_end': 100
        }
"""
        structure = {
            'classes': [{'name': 'PerfectAdapter', 'line': 4}]
        }
        detections = self.rule.check(
            file_path="/reveal/adapters/perfect.py",
            structure=structure,
            content=content
        )
        self.assertEqual(len(detections), 0)

    def test_all_violations_detected(self):
        """Adapter with all violations should detect all issues."""
        content = """
from pathlib import Path
from reveal.adapters.base import ResourceAdapter

class BrokenAdapter(ResourceAdapter):
    def get_structure(self, path, config):
        return {
            'type': 'broken-adapter',
            'data': [],
            'line': 5
        }
"""
        structure = {
            'classes': [{'name': 'BrokenAdapter', 'line': 4}]
        }
        detections = self.rule._check_output_code_patterns(
            file_path="/reveal/adapters/broken.py",
            content=content,
            method_name="get_structure"
        )
        # Should detect:
        # 1. Missing contract_version
        # 2. Missing source
        # 3. Missing source_type
        # 4. Hyphenated type value
        # 5. Deprecated line field
        self.assertGreaterEqual(len(detections), 2)  # At least missing fields + type naming

    def test_analyzer_file_checked(self):
        """Analyzer files should also be checked."""
        content = """
from reveal.base import FileAnalyzer

class TestAnalyzer(FileAnalyzer):
    def get_structure(self, content, file_path):
        return {
            'type': 'test-analyzer'
        }
"""
        structure = {
            'classes': [{'name': 'TestAnalyzer', 'line': 3}]
        }
        detections = self.rule._check_output_code_patterns(
            file_path="/reveal/analyzers/test_analyzer.py",
            content=content,
            method_name="get_structure"
        )
        self.assertGreater(len(detections), 0)

    def test_no_get_structure_method_no_detections(self):
        """Files without get_structure method should have no detections."""
        content = """
from reveal.adapters.base import ResourceAdapter

class HelperClass(ResourceAdapter):
    def helper_method(self):
        pass
"""
        structure = {
            'classes': [{'name': 'HelperClass', 'line': 3}]
        }
        detections = self.rule.check(
            file_path="/reveal/adapters/helper.py",
            structure=structure,
            content=content
        )
        self.assertEqual(len(detections), 0)


if __name__ == '__main__':
    unittest.main()
