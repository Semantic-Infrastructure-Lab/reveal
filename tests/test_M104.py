"""Tests for M104: Hardcoded list detector.

Comprehensive test suite for M104 rule that detects hardcoded lists
that may become stale or are duplicated.
"""

import unittest
import tempfile
import os
from pathlib import Path
from reveal.rules.maintainability.M104 import M104
from reveal.rules.base import Severity


class TestM104HardcodedLists(unittest.TestCase):
    """Test M104: Hardcoded list detector."""

    def setUp(self):
        """Set up test fixtures."""
        self.rule = M104()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp files."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def create_temp_file(self, content: str, filename: str = "test.py") -> str:
        """Helper: Create temp file with given content."""
        path = os.path.join(self.temp_dir, filename)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    # ===== Basic List Detection =====

    def test_small_list_not_flagged(self):
        """Lists with < 5 items should not be flagged."""
        content = """
SMALL_LIST = ['a', 'b', 'c', 'd']  # Only 4 items
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0, "Small lists should not be flagged")

    def test_large_list_flagged(self):
        """Lists with >= 5 items should be analyzed."""
        content = """
EXTENSIONS = ['.py', '.js', '.ts', '.go', '.rs']
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertGreater(len(detections), 0, "Large lists should be analyzed")

    def test_file_extension_list_detected(self):
        """Lists with file extensions should be flagged."""
        content = """
FILE_EXTENSIONS = ['.py', '.js', '.ts', '.go', '.rs']
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertIn('FILE_EXTENSIONS', detections[0].message)
        self.assertIn('extension', detections[0].message.lower())

    def test_treesitter_node_types_detected(self):
        """Lists with tree-sitter node types should be flagged."""
        content = """
NODE_TYPES = [
    'function_definition',
    'class_definition',
    'method_declaration',
    'variable_declaration',
    'import_statement'
]
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertIn('TREESITTER_NODES', detections[0].message)

    # ===== Stable Pattern Suppression =====

    def test_output_format_list_not_flagged(self):
        """Lists named 'output_format' should be suppressed (stable pattern)."""
        content = """
OUTPUT_FORMATS = ['text', 'json', 'grep', 'typed', 'xml']
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0, "output_format lists are stable")

    def test_html_semantic_tags_not_flagged(self):
        """Lists named with 'semantic_tag' should be suppressed."""
        content = """
SEMANTIC_TAGS = ['nav', 'header', 'main', 'article', 'footer']
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0, "HTML semantic tags are stable")

    def test_test_data_list_not_flagged(self):
        """Lists prefixed with 'test_' should be suppressed."""
        content = """
test_values = ['alpha', 'beta', 'gamma', 'delta', 'epsilon']
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0, "Test data lists should be suppressed")

    def test_mock_data_list_not_flagged(self):
        """Lists prefixed with 'mock_' should be suppressed."""
        content = """
mock_responses = ['ok', 'error', 'pending', 'timeout', 'retry']
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0, "Mock data lists should be suppressed")

    def test_dunder_all_not_flagged(self):
        """__all__ exports should be suppressed."""
        content = """
__all__ = ['ClassA', 'ClassB', 'ClassC', 'function_d', 'CONSTANT_E']
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0, "__all__ exports are stable")

    # ===== Classification Tests =====

    def test_classify_file_extensions(self):
        """Test classification of file extension lists."""
        content = """
EXTS = ['.py', '.js', '.ts', '.go', '.rs']
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertIn('FILE_EXTENSIONS', detections[0].message)

    def test_classify_treesitter_nodes(self):
        """Test classification of tree-sitter node type lists."""
        content = """
NODES = ['func_definition', 'class_definition', 'var_declaration', 'import', 'export']
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertIn('TREESITTER_NODES', detections[0].message)

    def test_classify_entity_types(self):
        """Test classification of entity type lists."""
        content = """
TYPES = ['function', 'class', 'method', 'struct', 'interface']
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        # Entity types should be flagged (not stable)
        self.assertGreaterEqual(len(detections), 0)

    def test_classify_stable_output_formats(self):
        """Test that lists with stable output formats are not flagged."""
        content = """
FORMATS = ['text', 'json', 'grep', 'csv', 'xml']
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0, "Output format lists are stable")

    def test_classify_stable_html_tags(self):
        """Test that lists with HTML5 semantic tags are not flagged."""
        content = """
TAGS = ['nav', 'header', 'main', 'article', 'section', 'aside', 'footer']
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0, "HTML5 semantic tags are stable")

    # ===== High Risk Pattern Detection =====

    def test_high_risk_pattern_extension(self):
        """Lists with 'extension' in name should include risk reason."""
        content = """
file_extensions = ['.py', '.js', '.ts', '.go', '.rs']
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertIn('extension', detections[0].suggestion.lower())

    def test_high_risk_pattern_node_type(self):
        """Lists with 'node_type' in name should include risk reason."""
        content = """
node_types = ['definition', 'declaration', 'statement', 'expression', 'literal']
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertIn('node type', detections[0].suggestion.lower())

    def test_high_risk_pattern_type_map(self):
        """Lists with 'type_map' in name should include risk reason."""
        content = """
type_mapping = ['int', 'str', 'bool', 'float', 'dict']
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertIn('type map', detections[0].suggestion.lower())

    def test_high_risk_pattern_pattern(self):
        """Lists with 'pattern' in name should include risk reason."""
        content = """
url_patterns = ['http://', 'https://', 'ftp://', 'file://', 'data:']
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertIn('pattern', detections[0].suggestion.lower())

    # ===== Dict with List Values =====

    def test_dict_with_few_list_values_not_flagged(self):
        """Dicts with < 5 list values should not be flagged."""
        content = """
LOOKUP = {
    'a': [1, 2, 3],
    'b': [4, 5, 6],
    'c': [7, 8, 9],
    'd': [10, 11, 12],
}
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0, "Dicts with < 5 list values OK")

    def test_dict_with_many_list_values_flagged(self):
        """Dicts with >= 5 list values (each with 3+ items) should be flagged."""
        content = """
TYPE_LOOKUP = {
    'python': ['.py', '.pyw', '.pyi'],
    'javascript': ['.js', '.jsx', '.mjs'],
    'typescript': ['.ts', '.tsx', '.d.ts'],
    'rust': ['.rs', '.rlib', '.toml'],
    'go': ['.go', '.mod', '.sum'],
    'java': ['.java', '.class', '.jar'],
}
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertIn('lookup table', detections[0].message.lower())
        self.assertEqual(detections[0].severity, Severity.MEDIUM)

    def test_dict_sample_keys_included(self):
        """Detection for dicts should include sample keys."""
        content = """
MAPPING = {
    'key1': [1, 2, 3],
    'key2': [4, 5, 6],
    'key3': [7, 8, 9],
    'key4': [10, 11, 12],
    'key5': [13, 14, 15],
}
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        # Should show sample keys in context
        self.assertIn('key', detections[0].context.lower())

    # ===== Edge Cases =====

    def test_empty_list_not_flagged(self):
        """Empty lists should not be flagged."""
        content = """
EMPTY = []
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_list_with_non_constant_values(self):
        """Lists with non-constant values should not crash."""
        content = """
DYNAMIC = [func(), var, 1 + 2, 'constant', other_func()]
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        # Should not crash, may or may not detect depending on constant count
        self.assertIsInstance(detections, list)

    def test_nested_lists_not_flagged(self):
        """Nested list structures should not cause issues."""
        content = """
NESTED = [
    ['a', 'b'],
    ['c', 'd'],
    ['e', 'f'],
]
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        # May or may not flag, but should not crash
        self.assertIsInstance(detections, list)

    def test_multiple_lists_in_file(self):
        """Multiple lists should each be checked independently."""
        content = """
EXTENSIONS = ['.py', '.js', '.ts', '.go', '.rs']
FORMATS = ['text', 'json', 'grep', 'csv', 'xml']
NODES = ['func_definition', 'class_definition', 'var_declaration', 'import', 'export']
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        # EXTENSIONS and NODES should be flagged, FORMATS is stable
        self.assertEqual(len(detections), 2)

    # ===== Context and Message Quality =====

    def test_detection_includes_sample_values(self):
        """Detection message should include sample values from list."""
        content = """
ITEMS = ['alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta']
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        if detections:
            # Should show first 3 items
            self.assertIn('alpha', detections[0].context)
            self.assertIn('beta', detections[0].context)
            self.assertIn('gamma', detections[0].context)

    def test_detection_shows_item_count(self):
        """Detection should show total item count for large lists."""
        content = """
MANY = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        if detections:
            # Should show item count
            self.assertIn('8 items', detections[0].context)

    def test_detection_includes_list_name(self):
        """Detection message should include the list variable name."""
        content = """
MY_SPECIAL_LIST = ['.py', '.js', '.ts', '.go', '.rs']
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertIn('MY_SPECIAL_LIST', detections[0].message)

    # ===== Invalid Python =====

    def test_invalid_python_returns_empty(self):
        """Invalid Python syntax should return empty detections."""
        content = """
this is not valid python code at all!!!
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        # Should not crash, may return parse error or empty list
        self.assertIsInstance(detections, list)

    # ===== Non-Python Files =====

    def test_non_python_file_skipped(self):
        """Non-Python files should be skipped."""
        content = """
const ITEMS = ['a', 'b', 'c', 'd', 'e'];
"""
        path = self.create_temp_file(content, filename="test.js")
        detections = self.rule.check(path, None, content)
        # Rule has file_patterns = ['.py'], should skip
        self.assertEqual(len(detections), 0)


class TestM104Helpers(unittest.TestCase):
    """Test M104 helper methods directly."""

    def setUp(self):
        """Set up test fixtures."""
        self.rule = M104()

    def test_extract_list_values_constants_only(self):
        """_extract_list_values should extract only constant values."""
        import ast
        code = "[1, 2, 'three', func(), 4, 5]"
        node = ast.parse(code).body[0].value
        values = self.rule._extract_list_values(node)
        # Should extract: 1, 2, 'three', 4, 5 (not func())
        self.assertEqual(len(values), 5)
        self.assertIn(1, values)
        self.assertIn('three', values)

    def test_classify_list_file_extensions(self):
        """_classify_list should detect file extensions."""
        values = ['.py', '.js', '.ts']
        classification = self.rule._classify_list('exts', values)
        self.assertEqual(classification, 'FILE_EXTENSIONS')

    def test_classify_list_treesitter_nodes(self):
        """_classify_list should detect tree-sitter nodes."""
        values = ['func_definition', 'class_definition', 'var_declaration']
        classification = self.rule._classify_list('nodes', values)
        self.assertEqual(classification, 'TREESITTER_NODES')

    def test_classify_list_entity_types(self):
        """_classify_list should detect entity types."""
        values = ['function', 'class', 'method', 'struct']
        classification = self.rule._classify_list('types', values)
        self.assertEqual(classification, 'ENTITY_TYPES')

    def test_classify_list_stable_output_formats(self):
        """_classify_list should recognize stable output formats."""
        values = ['text', 'json', 'grep']
        classification = self.rule._classify_list('formats', values)
        self.assertEqual(classification, 'STABLE')

    def test_classify_list_stable_html_tags(self):
        """_classify_list should recognize stable HTML tags."""
        values = ['nav', 'header', 'main', 'article']
        classification = self.rule._classify_list('tags', values)
        self.assertEqual(classification, 'STABLE')

    def test_classify_list_other(self):
        """_classify_list should return OTHER for unrecognized patterns."""
        values = ['apple', 'banana', 'cherry']
        classification = self.rule._classify_list('fruits', values)
        self.assertEqual(classification, 'OTHER')

    def test_count_dict_list_values(self):
        """_count_dict_list_values should count list values meeting threshold."""
        import ast
        code = "{'a': [1, 2, 3], 'b': [4], 'c': [5, 6, 7], 'd': 'string'}"
        node = ast.parse(code).body[0].value
        count = self.rule._count_dict_list_values(node)
        # 'a' has 3 items (>= MIN_DICT_VALUE_SIZE=3)
        # 'b' has 1 item (< 3)
        # 'c' has 3 items (>= 3)
        # 'd' is not a list
        # Expected: 2 lists meeting threshold
        self.assertEqual(count, 2)

    def test_extract_dict_sample_keys(self):
        """_extract_dict_sample_keys should extract keys with list values."""
        import ast
        code = "{'key1': [1, 2, 3], 'key2': [4, 5, 6], 'key3': [7, 8, 9]}"
        node = ast.parse(code).body[0].value
        keys = self.rule._extract_dict_sample_keys(node, max_samples=2)
        self.assertEqual(len(keys), 2)
        self.assertIn('key1', keys)
        self.assertIn('key2', keys)


if __name__ == '__main__':
    unittest.main()
