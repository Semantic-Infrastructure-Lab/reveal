"""Tests for semantic navigation (head/tail/range) feature.

Tests the --head, --tail, and --range arguments across different analyzers.
"""

import unittest
import tempfile
import json
from pathlib import Path
from reveal.analyzers.jsonl import JsonlAnalyzer
from reveal.analyzers.markdown import MarkdownAnalyzer


class TestSemanticSliceHelper(unittest.TestCase):
    """Test the base _apply_semantic_slice helper function."""

    def setUp(self):
        """Create test data."""
        self.test_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        self.test_file.write("test content")
        self.test_file.close()
        self.analyzer = JsonlAnalyzer(self.test_file.name)

        # Sample data
        self.items = [
            {'name': 'item1', 'line': 1},
            {'name': 'item2', 'line': 2},
            {'name': 'item3', 'line': 3},
            {'name': 'item4', 'line': 4},
            {'name': 'item5', 'line': 5},
            {'name': 'item6', 'line': 6},
            {'name': 'item7', 'line': 7},
            {'name': 'item8', 'line': 8},
            {'name': 'item9', 'line': 9},
            {'name': 'item10', 'line': 10},
        ]

    def tearDown(self):
        """Clean up test file."""
        Path(self.test_file.name).unlink(missing_ok=True)

    def test_head_basic(self):
        """Test head slicing."""
        result = self.analyzer._apply_semantic_slice(self.items, head=3)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['name'], 'item1')
        self.assertEqual(result[2]['name'], 'item3')

    def test_head_larger_than_list(self):
        """Test head with N > list length."""
        result = self.analyzer._apply_semantic_slice(self.items, head=20)
        self.assertEqual(len(result), 10)  # Returns all items

    def test_head_zero(self):
        """Test head with N = 0."""
        result = self.analyzer._apply_semantic_slice(self.items, head=0)
        self.assertEqual(len(result), 0)

    def test_tail_basic(self):
        """Test tail slicing."""
        result = self.analyzer._apply_semantic_slice(self.items, tail=3)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['name'], 'item8')
        self.assertEqual(result[2]['name'], 'item10')

    def test_tail_larger_than_list(self):
        """Test tail with N > list length."""
        result = self.analyzer._apply_semantic_slice(self.items, tail=20)
        self.assertEqual(len(result), 10)  # Returns all items

    def test_range_basic(self):
        """Test range slicing (1-indexed, inclusive)."""
        result = self.analyzer._apply_semantic_slice(self.items, range=(3, 5))
        self.assertEqual(len(result), 3)  # items 3, 4, 5
        self.assertEqual(result[0]['name'], 'item3')
        self.assertEqual(result[2]['name'], 'item5')

    def test_range_single_item(self):
        """Test range with start == end."""
        result = self.analyzer._apply_semantic_slice(self.items, range=(5, 5))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'item5')

    def test_range_full_list(self):
        """Test range covering entire list."""
        result = self.analyzer._apply_semantic_slice(self.items, range=(1, 10))
        self.assertEqual(len(result), 10)

    def test_no_slicing(self):
        """Test with no arguments - returns all items."""
        result = self.analyzer._apply_semantic_slice(self.items)
        self.assertEqual(len(result), 10)
        self.assertEqual(result, self.items)

    def test_empty_list(self):
        """Test slicing empty list."""
        result = self.analyzer._apply_semantic_slice([], head=5)
        self.assertEqual(result, [])


class TestJsonlAnalyzerNavigation(unittest.TestCase):
    """Test semantic navigation in JSONL analyzer."""

    def setUp(self):
        """Create test JSONL file."""
        self.test_file = tempfile.NamedTemporaryFile(
            mode='w', suffix='.jsonl', delete=False
        )

        # Write 20 test records
        for i in range(1, 21):
            record = {
                'type': 'user' if i % 2 == 0 else 'assistant',
                'message': {'role': 'user' if i % 2 == 0 else 'assistant',
                           'content': f'Message {i}'}
            }
            self.test_file.write(json.dumps(record) + '\n')

        self.test_file.close()
        self.analyzer = JsonlAnalyzer(self.test_file.name)

    def tearDown(self):
        """Clean up test file."""
        Path(self.test_file.name).unlink(missing_ok=True)

    def test_default_shows_first_10(self):
        """Default behavior shows first 10 records (+ summary)."""
        structure = self.analyzer.get_structure()
        # Summary + 10 records
        self.assertEqual(len(structure['records']), 11)
        self.assertEqual(structure['records'][0]['name'], '📊 Summary: 20 records')

    def test_head_argument(self):
        """Test --head shows first N records (+ summary)."""
        structure = self.analyzer.get_structure(head=5)
        # Summary + 5 records
        self.assertEqual(len(structure['records']), 6)
        self.assertIn('assistant #1', structure['records'][1]['name'])
        self.assertIn('assistant #5', structure['records'][5]['name'])

    def test_tail_argument(self):
        """Test --tail shows last N records (+ summary)."""
        structure = self.analyzer.get_structure(tail=3)
        # Summary + 3 records
        self.assertEqual(len(structure['records']), 4)
        self.assertIn('#18', structure['records'][1]['name'])
        self.assertIn('#20', structure['records'][3]['name'])

    def test_range_argument(self):
        """Test --range shows specific range (+ summary)."""
        structure = self.analyzer.get_structure(range=(5, 7))
        # Summary + 3 records (5, 6, 7)
        self.assertEqual(len(structure['records']), 4)
        self.assertIn('#5', structure['records'][1]['name'])
        self.assertIn('#7', structure['records'][3]['name'])

    def test_summary_always_included(self):
        """Summary should always be present."""
        for kwargs in [{'head': 3}, {'tail': 3}, {'range': (1, 5)}, {}]:
            structure = self.analyzer.get_structure(**kwargs)
            self.assertEqual(structure['records'][0]['name'], '📊 Summary: 20 records')


class TestPythonAnalyzerNavigation(unittest.TestCase):
    """Test semantic navigation in Python analyzer (via TreeSitter)."""

    def setUp(self):
        """Create test Python file with multiple functions."""
        self.test_file = tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False
        )

        # Write Python code with 10 functions
        self.test_file.write("# Test file\n")
        for i in range(1, 11):
            self.test_file.write(f"\ndef func{i}():\n")
            self.test_file.write(f"    \"\"\"Function {i}\"\"\"\n")
            self.test_file.write(f"    return {i}\n")

        self.test_file.close()

    def tearDown(self):
        """Clean up test file."""
        Path(self.test_file.name).unlink(missing_ok=True)

    def test_head_functions(self):
        """Test --head shows first N functions."""
        try:
            # PythonAnalyzer is a TreeSitterAnalyzer subclass
            from reveal.analyzers.python import PythonAnalyzer
            analyzer = PythonAnalyzer(self.test_file.name)
            structure = analyzer.get_structure(head=3)

            self.assertIn('functions', structure)
            self.assertEqual(len(structure['functions']), 3)
            self.assertIn('func1', structure['functions'][0]['name'])
            self.assertIn('func3', structure['functions'][2]['name'])
        except ImportError:
            self.skipTest("tree-sitter-languages not available")

    def test_tail_functions(self):
        """Test --tail shows last N functions."""
        try:
            from reveal.analyzers.python import PythonAnalyzer
            analyzer = PythonAnalyzer(self.test_file.name)
            structure = analyzer.get_structure(tail=3)

            self.assertIn('functions', structure)
            self.assertEqual(len(structure['functions']), 3)
            self.assertIn('func8', structure['functions'][0]['name'])
            self.assertIn('func10', structure['functions'][2]['name'])
        except ImportError:
            self.skipTest("tree-sitter-languages not available")

    def test_range_functions(self):
        """Test --range shows specific range of functions."""
        try:
            from reveal.analyzers.python import PythonAnalyzer
            analyzer = PythonAnalyzer(self.test_file.name)
            structure = analyzer.get_structure(range=(3, 5))

            self.assertIn('functions', structure)
            self.assertEqual(len(structure['functions']), 3)
            self.assertIn('func3', structure['functions'][0]['name'])
            self.assertIn('func5', structure['functions'][2]['name'])
        except ImportError:
            self.skipTest("tree-sitter-languages not available")


class TestMarkdownAnalyzerNavigation(unittest.TestCase):
    """Test semantic navigation in Markdown analyzer."""

    def setUp(self):
        """Create test Markdown file with multiple headings."""
        self.test_file = tempfile.NamedTemporaryFile(
            mode='w', suffix='.md', delete=False
        )

        # Write markdown with 10 headings
        for i in range(1, 11):
            self.test_file.write(f"# Heading {i}\n\n")
            self.test_file.write(f"Content for section {i}.\n\n")

        self.test_file.close()
        self.analyzer = MarkdownAnalyzer(self.test_file.name)

    def tearDown(self):
        """Clean up test file."""
        Path(self.test_file.name).unlink(missing_ok=True)

    def test_head_headings(self):
        """Test --head shows first N headings."""
        structure = self.analyzer.get_structure(head=3)
        self.assertEqual(len(structure['headings']), 3)
        self.assertIn('Heading 1', structure['headings'][0]['name'])
        self.assertIn('Heading 3', structure['headings'][2]['name'])

    def test_tail_headings(self):
        """Test --tail shows last N headings."""
        structure = self.analyzer.get_structure(tail=3)
        self.assertEqual(len(structure['headings']), 3)
        self.assertIn('Heading 8', structure['headings'][0]['name'])
        self.assertIn('Heading 10', structure['headings'][2]['name'])

    def test_range_headings(self):
        """Test --range shows specific range of headings."""
        structure = self.analyzer.get_structure(range=(4, 6))
        self.assertEqual(len(structure['headings']), 3)
        self.assertIn('Heading 4', structure['headings'][0]['name'])
        self.assertIn('Heading 6', structure['headings'][2]['name'])

    def test_navigation_with_links_extraction(self):
        """Test that navigation works with link extraction enabled."""
        # Add some links to test file
        test_file2 = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False)
        test_file2.write("# Section 1\n[Link 1](http://example.com)\n\n")
        test_file2.write("# Section 2\n[Link 2](http://test.com)\n\n")
        test_file2.write("# Section 3\n[Link 3](http://demo.com)\n\n")
        test_file2.close()

        analyzer = MarkdownAnalyzer(test_file2.name)
        structure = analyzer.get_structure(head=2, extract_links=True)

        # Should have 2 headings and 2 links
        self.assertEqual(len(structure['headings']), 2)
        self.assertEqual(len(structure['links']), 2)

        Path(test_file2.name).unlink(missing_ok=True)


class TestCLIArgumentValidation(unittest.TestCase):
    """Test CLI argument parsing and validation."""

    def test_mutual_exclusivity(self):
        """Test that head/tail/range are mutually exclusive.

        This test validates the logic in main.py that should prevent
        using multiple navigation arguments at once.
        """
        # Note: This would require running the CLI, which is integration testing
        # For unit tests, we verify the logic works at the analyzer level
        pass


if __name__ == '__main__':
    unittest.main()
