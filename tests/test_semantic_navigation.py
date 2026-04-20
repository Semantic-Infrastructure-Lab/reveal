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


class TestParseLineRange(unittest.TestCase):
    """Unit tests for file_handler._parse_line_range."""

    def setUp(self):
        from reveal.file_handler import _parse_line_range
        self.parse = _parse_line_range

    def test_none_returns_defaults(self):
        """None input (--range absent) should fall back cleanly, not crash."""
        self.assertEqual(self.parse(None, 1, 100), (1, 100))

    def test_string_start_end(self):
        self.assertEqual(self.parse('10-20', 1, 100), (10, 20))

    def test_string_single_number(self):
        self.assertEqual(self.parse('15', 1, 100), (15, 100))

    def test_string_invalid_falls_back(self):
        self.assertEqual(self.parse('bad', 1, 100), (1, 100))

    def test_tuple_both_values(self):
        """validate_navigation_args() pre-converts --range to a (start, end) tuple."""
        self.assertEqual(self.parse((10, 20), 1, 100), (10, 20))

    def test_tuple_open_ended(self):
        """Open-ended range like '300-' produces (300, None); None should use default_end."""
        self.assertEqual(self.parse((300, None), 1, 500), (300, 500))

    def test_tuple_does_not_crash(self):
        """Regression: tuple input previously raised AttributeError on .strip()."""
        try:
            self.parse((890, 920), 886, 930)
        except AttributeError as e:
            self.fail(f'_parse_line_range raised AttributeError on tuple input: {e}')


class TestRangeWithNavFlags(unittest.TestCase):
    """Integration tests: --range combined with --deps/--mutations/--exits via dispatch."""

    def _make_args(self, **kwargs):
        import argparse
        defaults = dict(
            scope=False, around=None, outline=False, varflow=None, calls=None,
            ifmap=False, catchmap=False, exits=False, flowto=False,
            deps=False, mutations=False, depth=3, range=None,
        )
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def _nav_file(self):
        """Return path to nav_exits.py as a test target (functions moved from nav.py, BACK-185)."""
        from pathlib import Path
        return str(Path(__file__).parent.parent / 'reveal' / 'adapters' / 'ast' / 'nav_exits.py')

    def test_deps_with_tuple_range(self):
        """--deps with a pre-parsed tuple range should not crash."""
        import io, sys
        from reveal.file_handler import _dispatch_nav
        from reveal.analyzers.python import PythonAnalyzer

        analyzer = PythonAnalyzer(self._nav_file())
        analyzer.get_structure()
        args = self._make_args(deps=True, range=(106, 133))
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            _dispatch_nav(analyzer, 'collect_deps', 'text', args)
        finally:
            sys.stdout = old_stdout
        output = captured.getvalue()
        self.assertIn('PARAM', output)

    def test_mutations_with_tuple_range(self):
        """--mutations with a pre-parsed tuple range should not crash.
        Uses collect_mutations (L936) with a sub-range that leaves the return
        statement outside, so at least one mutation qualifies."""
        import io, sys
        from reveal.file_handler import _dispatch_nav
        from reveal.analyzers.python import PythonAnalyzer

        analyzer = PythonAnalyzer(self._nav_file())
        analyzer.get_structure()
        # Sub-range: covers writes to `mutations` but stops before the sort/return read
        args = self._make_args(mutations=True, range=(136, 158))
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            _dispatch_nav(analyzer, 'collect_mutations', 'text', args)
        finally:
            sys.stdout = old_stdout
        # render_mutations outputs 'RETURN var  written Lx, next read Ly' lines
        output = captured.getvalue()
        self.assertIn('RETURN', output)

    def test_exits_with_tuple_range(self):
        """--exits with a pre-parsed tuple range should not crash and find exits.
        collect_exits (L723) unconditionally returns at its end, so RETURN is certain."""
        import io, sys
        from reveal.file_handler import _dispatch_nav
        from reveal.analyzers.python import PythonAnalyzer

        analyzer = PythonAnalyzer(self._nav_file())
        analyzer.get_structure()
        args = self._make_args(exits=True, range=(30, 75))
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            _dispatch_nav(analyzer, 'collect_exits', 'text', args)
        finally:
            sys.stdout = old_stdout
        output = captured.getvalue()
        self.assertIn('RETURN', output)


class TestNavJsonOutput(unittest.TestCase):
    """--format json produces a consistent envelope for all nav flags."""

    def _nav_file(self):
        from pathlib import Path
        return str(Path(__file__).parent.parent / 'reveal' / 'adapters' / 'ast' / 'nav_exits.py')

    def _make_args(self, **kwargs):
        import argparse
        defaults = dict(
            scope=False, around=None, outline=False, varflow=None, calls=None,
            ifmap=False, catchmap=False, exits=False, flowto=False,
            deps=False, mutations=False, sideeffects=False, returns=False,
            boundary=False, depth=3, range=None,
        )
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def _run(self, element, flag_kwargs):
        import io, json, sys
        from reveal.file_handler import _dispatch_nav
        from reveal.analyzers.python import PythonAnalyzer
        analyzer = PythonAnalyzer(self._nav_file())
        analyzer.get_structure()
        args = self._make_args(**flag_kwargs)
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            _dispatch_nav(analyzer, element, 'json', args)
        finally:
            sys.stdout = old
        return json.loads(buf.getvalue())

    def _assert_envelope(self, result, expected_flag):
        self.assertIn('meta', result)
        self.assertIn('findings', result)
        self.assertIn('warnings', result)
        self.assertEqual(result['meta']['flag'], expected_flag)
        self.assertIsInstance(result['findings'], list)
        self.assertIsInstance(result['warnings'], list)

    def test_deps_json_envelope(self):
        result = self._run('collect_deps', {'deps': True})
        self._assert_envelope(result, 'deps')

    def test_deps_findings_have_kind_var_line(self):
        result = self._run('collect_deps', {'deps': True})
        for f in result['findings']:
            self.assertEqual(f['kind'], 'dep')
            self.assertIn('var', f)
            self.assertIn('line', f)
            self.assertIn('first_write_line', f)

    def test_mutations_json_envelope(self):
        result = self._run('collect_mutations', {'mutations': True})
        self._assert_envelope(result, 'mutations')

    def test_mutations_findings_have_kind(self):
        result = self._run('collect_mutations', {'mutations': True})
        for f in result['findings']:
            self.assertEqual(f['kind'], 'mutation')
            self.assertIn('var', f)
            self.assertIn('line', f)
            self.assertIn('next_read_line', f)

    def test_exits_json_envelope(self):
        result = self._run('collect_exits', {'exits': True})
        self._assert_envelope(result, 'exits')

    def test_sideeffects_json_envelope(self):
        result = self._run('collect_deps', {'sideeffects': True})
        self._assert_envelope(result, 'sideeffects')

    def test_returns_json_envelope(self):
        result = self._run('collect_deps', {'returns': True})
        self._assert_envelope(result, 'returns')

    def test_boundary_json_envelope(self):
        result = self._run('collect_deps', {'boundary': True})
        self._assert_envelope(result, 'boundary')

    def test_boundary_findings_kinds(self):
        result = self._run('collect_deps', {'boundary': True})
        kinds = {f['kind'] for f in result['findings']}
        valid = {'input', 'superglobal', 'db', 'http', 'cache', 'log', 'file', 'sleep', 'hard_stop'}
        self.assertTrue(kinds.issubset(valid), f"unexpected kinds: {kinds - valid}")

    def test_calls_json_envelope(self):
        result = self._run('collect_deps', {'calls': 'FULL'})
        self._assert_envelope(result, 'calls')

    def test_varflow_json_envelope(self):
        result = self._run('collect_deps', {'varflow': 'deps'})
        self._assert_envelope(result, 'varflow')
        self.assertEqual(result['meta']['var'], 'deps')

    def test_meta_has_file_element_range(self):
        result = self._run('collect_deps', {'deps': True})
        meta = result['meta']
        self.assertIn('file', meta)
        self.assertIn('element', meta)
        self.assertIn('from_line', meta)
        self.assertIn('to_line', meta)
        self.assertIsInstance(meta['from_line'], int)
        self.assertIsInstance(meta['to_line'], int)

    def test_file_is_string_not_path(self):
        result = self._run('collect_deps', {'deps': True})
        self.assertIsInstance(result['meta']['file'], str)


if __name__ == '__main__':
    unittest.main()
