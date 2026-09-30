"""Tests for semantic navigation (head/tail/range) feature.

Tests the --head, --tail, and --range arguments across different analyzers.
"""

import unittest
import tempfile
import json
from pathlib import Path
import pytest

from reveal.analyzers.jsonl import JsonlAnalyzer
from reveal.api import analyze
from reveal.utils.results import slice_items, slice_structure

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP/network
pytestmark = pytest.mark.component


def _cut(result, field):
    """The (shown, total, cause) a result records for a cut ``field``, or None."""
    for w in (result.get('meta') or {}).get('warnings') or []:
        if w.get('type') == 'truncated' and w.get('field') == field:
            return w['shown'], w['total'], w['cause']
    return None


class TestSliceItems(unittest.TestCase):
    """reveal.utils.results.slice_items: --head/--tail/--range on one list (BACK-1548)."""

    items = [{'name': f'item{i}', 'line': i} for i in range(1, 11)]

    def test_head_basic(self):
        result = slice_items(self.items, head=3)
        self.assertEqual([r['name'] for r in result], ['item1', 'item2', 'item3'])

    def test_head_larger_than_list(self):
        self.assertEqual(len(slice_items(self.items, head=20)), 10)

    def test_head_zero_cuts_nothing(self):
        """0 is 'no flag', as `reveal f.py --head 0` has always shown the whole list."""
        self.assertEqual(slice_items(self.items, head=0), self.items)

    def test_tail_basic(self):
        result = slice_items(self.items, tail=3)
        self.assertEqual([r['name'] for r in result], ['item8', 'item9', 'item10'])

    def test_tail_larger_than_list(self):
        self.assertEqual(len(slice_items(self.items, tail=20)), 10)

    def test_range_is_one_indexed_and_inclusive(self):
        result = slice_items(self.items, range_=(3, 5))
        self.assertEqual([r['name'] for r in result], ['item3', 'item4', 'item5'])

    def test_range_single_item(self):
        self.assertEqual(slice_items(self.items, range_=(5, 5)), [self.items[4]])

    def test_range_full_list(self):
        self.assertEqual(len(slice_items(self.items, range_=(1, 10))), 10)

    def test_no_slicing(self):
        self.assertEqual(slice_items(self.items), self.items)

    def test_empty_list(self):
        self.assertEqual(slice_items([], head=5), [])


class TestSliceStructure(unittest.TestCase):
    """reveal.utils.results.slice_structure: file mode's one cut, disclosed (BACK-1548)."""

    def _structure(self):
        return {'functions': [{'name': f'f{i}'} for i in range(6)],
                'classes': [{'name': f'C{i}'} for i in range(3)],
                'stats': {'total': 9}, '_has_errors': True}

    def test_every_list_is_cut_per_category_and_disclosed(self):
        s = self._structure()
        self.assertEqual(slice_structure(s, head=2), ['functions', 'classes'])
        self.assertEqual((len(s['functions']), len(s['classes'])), (2, 2))
        self.assertEqual(_cut(s, 'functions'), (2, 6, 'head'))
        self.assertEqual(_cut(s, 'classes'), (2, 3, 'head'))
        self.assertEqual(s['stats'], {'total': 9})  # not a list: untouched

    def test_a_list_the_cut_leaves_whole_records_nothing(self):
        s = self._structure()
        slice_structure(s, head=5)
        self.assertIsNotNone(_cut(s, 'functions'))
        self.assertIsNone(_cut(s, 'classes'))

    def test_fields_limits_the_cut(self):
        s = self._structure()
        self.assertEqual(slice_structure(s, tail=1, fields=('classes',)), ['classes'])
        self.assertEqual(len(s['functions']), 6)
        self.assertEqual(s['classes'], [{'name': 'C2'}])

    def test_default_head_is_a_disclosed_sample(self):
        s = self._structure()
        slice_structure(s, default_head=4, fields=('functions',))
        self.assertEqual(_cut(s, 'functions'), (4, 6, 'sample'))

    def test_a_flag_overrides_the_default_sample(self):
        s = self._structure()
        slice_structure(s, head=5, default_head=2, fields=('functions',))
        self.assertEqual(len(s['functions']), 5)

    def test_nothing_to_slice_returns_no_fields(self):
        self.assertEqual(slice_structure({'stats': {}}, head=2), [])
        self.assertEqual(slice_structure(self._structure()), [])


class TestJsonlAnalyzerNavigation(unittest.TestCase):
    """--head/--tail/--range on JSONL records, through reveal.api.analyze (the CLI's cut)."""

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
        self.path = self.test_file.name

    def tearDown(self):
        """Clean up test file."""
        Path(self.test_file.name).unlink(missing_ok=True)

    def test_default_shows_first_10(self):
        """Default behavior shows a disclosed sample of the first 10 records."""
        structure = analyze(self.path)
        self.assertEqual(len(structure['records']), 10)
        self.assertEqual(_cut(structure, 'records'), (10, 20, 'sample'))

    def test_the_analyzer_returns_every_record(self):
        self.assertEqual(len(JsonlAnalyzer(self.path).get_structure()['records']), 20)

    def test_head_argument(self):
        structure = analyze(self.path, head=5)
        self.assertEqual(len(structure['records']), 5)
        self.assertIn('assistant #1', structure['records'][0]['name'])
        self.assertIn('assistant #5', structure['records'][4]['name'])
        self.assertEqual(_cut(structure, 'records'), (5, 20, 'head'))

    def test_tail_argument(self):
        structure = analyze(self.path, tail=3)
        self.assertEqual(len(structure['records']), 3)
        self.assertIn('#18', structure['records'][0]['name'])
        self.assertIn('#20', structure['records'][2]['name'])

    def test_range_argument(self):
        structure = analyze(self.path, range=(5, 7))
        self.assertEqual(len(structure['records']), 3)
        self.assertIn('#5', structure['records'][0]['name'])
        self.assertIn('#7', structure['records'][2]['name'])

    def test_summary_is_its_own_field_and_never_cut(self):
        """The summary was records[0], so a --head cut counted it as a record."""
        for kwargs in [{'head': 3}, {'tail': 3}, {'range': (1, 5)}, {}]:
            structure = analyze(self.path, **kwargs)
            self.assertEqual(structure['summary'][0]['name'], '📊 Summary: 20 records')
            self.assertNotIn('Summary', structure['records'][0]['name'])


class TestPythonAnalyzerNavigation(unittest.TestCase):
    """--head/--tail/--range on tree-sitter functions, through reveal.api.analyze."""

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
        structure = analyze(self.test_file.name, head=3)
        self.assertEqual(len(structure['functions']), 3)
        self.assertIn('func1', structure['functions'][0]['name'])
        self.assertIn('func3', structure['functions'][2]['name'])
        self.assertEqual(_cut(structure, 'functions'), (3, 10, 'head'))

    def test_tail_functions(self):
        structure = analyze(self.test_file.name, tail=3)
        self.assertEqual(len(structure['functions']), 3)
        self.assertIn('func8', structure['functions'][0]['name'])
        self.assertIn('func10', structure['functions'][2]['name'])

    def test_range_functions(self):
        structure = analyze(self.test_file.name, range=(3, 5))
        self.assertEqual(len(structure['functions']), 3)
        self.assertIn('func3', structure['functions'][0]['name'])
        self.assertIn('func5', structure['functions'][2]['name'])


class TestMarkdownAnalyzerNavigation(unittest.TestCase):
    """--head/--tail/--range on markdown headings, through reveal.api.analyze."""

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
        self.path = self.test_file.name

    def tearDown(self):
        """Clean up test file."""
        Path(self.test_file.name).unlink(missing_ok=True)

    def test_head_headings(self):
        structure = analyze(self.path, head=3)
        self.assertEqual(len(structure['headings']), 3)
        self.assertIn('Heading 1', structure['headings'][0]['name'])
        self.assertIn('Heading 3', structure['headings'][2]['name'])

    def test_tail_headings(self):
        structure = analyze(self.path, tail=3)
        self.assertEqual(len(structure['headings']), 3)
        self.assertIn('Heading 8', structure['headings'][0]['name'])
        self.assertIn('Heading 10', structure['headings'][2]['name'])

    def test_range_headings(self):
        structure = analyze(self.path, range=(4, 6))
        self.assertEqual(len(structure['headings']), 3)
        self.assertIn('Heading 4', structure['headings'][0]['name'])
        self.assertIn('Heading 6', structure['headings'][2]['name'])

    def test_navigation_with_links_extraction(self):
        """--head with --links keeps headings beside the links (c3b33c66), both cut."""
        test_file2 = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False)
        test_file2.write("# Section 1\n[Link 1](http://example.com)\n\n")
        test_file2.write("# Section 2\n[Link 2](http://test.com)\n\n")
        test_file2.write("# Section 3\n[Link 3](http://demo.com)\n\n")
        test_file2.close()

        structure = analyze(test_file2.name, head=2, extract_links=True)

        self.assertEqual(len(structure['headings']), 2)
        self.assertEqual(len(structure['links']), 2)
        # Without a walk, --links is a filter: links only.
        self.assertNotIn('headings', analyze(test_file2.name, extract_links=True))

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

    @staticmethod
    def _span(analyzer, name):
        """(line, line_end) of a function in nav_exits.py, looked up by name --
        hard-coded line numbers broke on every edit to that file."""
        for fn in analyzer.get_structure()['functions']:
            if fn['name'] == name:
                return (fn['line'], fn['line_end'])
        raise AssertionError(f'{name} not found in nav_exits.py')

    def test_deps_with_tuple_range(self):
        """--deps with a pre-parsed tuple range should not crash."""
        import io, sys
        from reveal.file_handler import _dispatch_nav
        from reveal.analyzers.python import PythonAnalyzer

        analyzer = PythonAnalyzer(self._nav_file())
        analyzer.get_structure()
        args = self._make_args(deps=True, range=self._span(analyzer, 'collect_deps'))
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
        Uses collect_mutations's own body with a sub-range that leaves the
        sort/return read outside, so at least one mutation qualifies."""
        import io, sys
        from reveal.file_handler import _dispatch_nav
        from reveal.analyzers.python import PythonAnalyzer

        analyzer = PythonAnalyzer(self._nav_file())
        analyzer.get_structure()
        # Sub-range: covers writes to `mutations` but stops before the sort/return read
        start, end = self._span(analyzer, 'collect_mutations')
        args = self._make_args(mutations=True, range=(start, end - 2))
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
        collect_exits unconditionally returns at its end, so RETURN is certain."""
        import io, sys
        from reveal.file_handler import _dispatch_nav
        from reveal.analyzers.python import PythonAnalyzer

        analyzer = PythonAnalyzer(self._nav_file())
        analyzer.get_structure()
        args = self._make_args(exits=True, range=self._span(analyzer, 'collect_exits'))
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
            deps=False, mutations=False, sideeffects=False, loopmap=False,
            fanout=False, statewrites=False, keys=None, returns=False,
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

    def test_loopmap_json_envelope(self):
        result = self._run('collect_deps', {'loopmap': True})
        self._assert_envelope(result, 'loopmap')

    def test_fanout_json_envelope(self):
        result = self._run('collect_deps', {'fanout': True})
        self._assert_envelope(result, 'fanout')

    def test_fanout_findings_have_effects_key(self):
        result = self._run('collect_deps', {'fanout': True})
        for f in result['findings']:
            self.assertIn('effects', f)
            self.assertIn('keyword', f)

    def test_statewrites_json_envelope(self):
        result = self._run('collect_deps', {'statewrites': True})
        self._assert_envelope(result, 'statewrites')

    def test_statewrites_findings_have_kind_line_target(self):
        result = self._run('collect_deps', {'statewrites': True})
        for f in result['findings']:
            self.assertIn('kind', f)
            self.assertIn('line', f)
            self.assertIn('target', f)

    def test_boundary_json_envelope(self):
        result = self._run('collect_deps', {'boundary': True})
        self._assert_envelope(result, 'boundary')

    def test_keys_json_envelope(self):
        result = self._run('collect_deps', {'keys': 'from_line'})
        self._assert_envelope(result, 'keys')
        self.assertEqual(result['meta']['var'], 'from_line')

    def test_keys_findings_have_key_kind_line_access(self):
        result = self._run('collect_deps', {'keys': 'from_line'})
        for f in result['findings']:
            self.assertIn('key', f)
            self.assertIn('kind', f)
            self.assertIn('line', f)
            self.assertIn('access', f)

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


class TestSideEffectsTransitive(unittest.TestCase):
    """--sideeffects --transitive: follow calls into project-local helpers (BACK-545).

    Each test gets its own tmp directory so the call-graph forward index built
    per test never sees another test's same-named fixture functions.
    """

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _write(self, name, content):
        path = self.dir / name
        path.write_text(content)
        return str(path)

    def _make_args(self, **kwargs):
        import argparse
        defaults = dict(
            scope=False, around=None, outline=False, varflow=None, calls=None,
            ifmap=False, catchmap=False, exits=False, flowto=False,
            deps=False, mutations=False, sideeffects=False, transitive=False, loopmap=False,
            fanout=False, statewrites=False, keys=None, returns=False,
            boundary=False, depth=None, range=None,
        )
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def _dispatch(self, path, element, args, as_json=False):
        import io
        import sys
        import json
        from reveal.file_handler import _dispatch_nav
        from reveal.analyzers.python import PythonAnalyzer
        analyzer = PythonAnalyzer(path)
        analyzer.get_structure()
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            _dispatch_nav(analyzer, element, 'json' if as_json else 'text', args)
        finally:
            sys.stdout = old
        out = buf.getvalue()
        return json.loads(out) if as_json else out

    def test_direct_only_misses_helper_effect(self):
        """Without --transitive, dispatch-only body reports no effects — the BACK-545 gap."""
        entry_path = self._write('entry.py', (
            "def handle_request(order):\n"
            "    _save(order)\n"
        ))
        self._write('helper.py', (
            "def _save(order):\n"
            "    db.execute('insert into orders values (?)', order)\n"
        ))
        args = self._make_args(sideeffects=True)
        out = self._dispatch(entry_path, 'handle_request', args)
        self.assertIn('No classified side effects', out)

    def test_transitive_finds_helper_effect(self):
        entry_path = self._write('entry.py', (
            "def handle_request(order):\n"
            "    _save(order)\n"
        ))
        self._write('helper.py', (
            "def _save(order):\n"
            "    db.execute('insert into orders values (?)', order)\n"
        ))
        args = self._make_args(sideeffects=True, transitive=True)
        out = self._dispatch(entry_path, 'handle_request', args)
        self.assertIn('db', out)
        self.assertIn('_save', out)

    def test_transitive_json_tags_hop_and_chain(self):
        entry_path = self._write('entry.py', (
            "def handle_request(order):\n"
            "    _save(order)\n"
        ))
        self._write('helper.py', (
            "def _save(order):\n"
            "    db.execute('insert into orders values (?)', order)\n"
        ))
        args = self._make_args(sideeffects=True, transitive=True)
        result = self._dispatch(entry_path, 'handle_request', args, as_json=True)
        findings = result['findings']
        self.assertTrue(findings)
        self.assertEqual(findings[0]['hop'], 1)
        self.assertEqual(findings[0]['chain'], ['handle_request', '_save'])

    def test_transitive_depth_limits_traversal(self):
        """depth=1 (direct callees only) must not reach a second-hop effect."""
        entry_path = self._write('entry.py', (
            "def handle_request(order):\n"
            "    _save(order)\n"
        ))
        self._write('helper_a.py', (
            "def _save(order):\n"
            "    _persist(order)\n"
        ))
        self._write('helper_b.py', (
            "def _persist(order):\n"
            "    db.execute('insert into orders values (?)', order)\n"
        ))
        args = self._make_args(sideeffects=True, transitive=True, depth=1)
        result = self._dispatch(entry_path, 'handle_request', args, as_json=True)
        self.assertEqual(result['findings'], [])

    def test_transitive_two_hops_reaches_nested_effect(self):
        entry_path = self._write('entry.py', (
            "def handle_request(order):\n"
            "    _save(order)\n"
        ))
        self._write('helper_a.py', (
            "def _save(order):\n"
            "    _persist(order)\n"
        ))
        self._write('helper_b.py', (
            "def _persist(order):\n"
            "    db.execute('insert into orders values (?)', order)\n"
        ))
        args = self._make_args(sideeffects=True, transitive=True, depth=3)
        result = self._dispatch(entry_path, 'handle_request', args, as_json=True)
        chains = [tuple(f['chain']) for f in result['findings']]
        self.assertIn(('handle_request', '_save', '_persist'), chains)

    def test_transitive_cycle_does_not_hang(self):
        """A→B→A must terminate via the visited-name set, not hang or double-count."""
        entry_path = self._write('entry.py', (
            "def handle_request(order):\n"
            "    _save(order)\n"
        ))
        self._write('helper.py', (
            "def _save(order):\n"
            "    db.execute('x', order)\n"
            "    handle_request(order)\n"
        ))
        args = self._make_args(sideeffects=True, transitive=True, depth=5)
        result = self._dispatch(entry_path, 'handle_request', args, as_json=True)
        kinds = {f['kind'] for f in result['findings']}
        self.assertIn('db', kinds)

    def test_transitive_unresolved_call_terminates_branch(self):
        """A call with no project-local definition must not crash the walk."""
        entry_path = self._write('entry.py', (
            "def handle_request(order):\n"
            "    totally_unknown_external_fn(order)\n"
        ))
        args = self._make_args(sideeffects=True, transitive=True)
        result = self._dispatch(entry_path, 'handle_request', args, as_json=True)
        self.assertEqual(result['findings'], [])


class TestBoundaryTransitive(TestSideEffectsTransitive):
    """--boundary --transitive: same interprocedural walk, on the boundary report (BACK-546).

    Subclasses TestSideEffectsTransitive purely to reuse its setUp/tearDown/
    _write/_make_args/_dispatch helpers — tests below exercise boundary=True
    instead of sideeffects=True.
    """

    def test_direct_only_misses_helper_effect(self):
        entry_path = self._write('entry.py', (
            "def handle_request(order):\n"
            "    _save(order)\n"
        ))
        self._write('helper.py', (
            "def _save(order):\n"
            "    db.execute('insert into orders values (?)', order)\n"
        ))
        args = self._make_args(boundary=True)
        out = self._dispatch(entry_path, 'handle_request', args)
        self.assertIn('EFFECTS:\n  none', out)

    def test_transitive_finds_helper_effect(self):
        entry_path = self._write('entry.py', (
            "def handle_request(order):\n"
            "    _save(order)\n"
        ))
        self._write('helper.py', (
            "def _save(order):\n"
            "    db.execute('insert into orders values (?)', order)\n"
        ))
        args = self._make_args(boundary=True, transitive=True)
        out = self._dispatch(entry_path, 'handle_request', args)
        self.assertIn('db', out)
        self.assertIn('_save', out)

    def test_transitive_json_tags_hop_and_chain(self):
        entry_path = self._write('entry.py', (
            "def handle_request(order):\n"
            "    _save(order)\n"
        ))
        self._write('helper.py', (
            "def _save(order):\n"
            "    db.execute('insert into orders values (?)', order)\n"
        ))
        args = self._make_args(boundary=True, transitive=True)
        result = self._dispatch(entry_path, 'handle_request', args, as_json=True)
        effect_findings = [f for f in result['findings'] if f['kind'] not in ('input', 'superglobal')]
        self.assertTrue(effect_findings)
        self.assertEqual(effect_findings[0]['hop'], 1)
        self.assertEqual(effect_findings[0]['chain'], ['handle_request', '_save'])

    def test_transitive_depth_limits_traversal(self):
        entry_path = self._write('entry.py', (
            "def handle_request(order):\n"
            "    _save(order)\n"
        ))
        self._write('helper_a.py', (
            "def _save(order):\n"
            "    _persist(order)\n"
        ))
        self._write('helper_b.py', (
            "def _persist(order):\n"
            "    db.execute('insert into orders values (?)', order)\n"
        ))
        args = self._make_args(boundary=True, transitive=True, depth=1)
        result = self._dispatch(entry_path, 'handle_request', args, as_json=True)
        effect_findings = [f for f in result['findings'] if f['kind'] not in ('input', 'superglobal')]
        self.assertEqual(effect_findings, [])

    def test_transitive_two_hops_reaches_nested_effect(self):
        entry_path = self._write('entry.py', (
            "def handle_request(order):\n"
            "    _save(order)\n"
        ))
        self._write('helper_a.py', (
            "def _save(order):\n"
            "    _persist(order)\n"
        ))
        self._write('helper_b.py', (
            "def _persist(order):\n"
            "    db.execute('insert into orders values (?)', order)\n"
        ))
        args = self._make_args(boundary=True, transitive=True, depth=3)
        result = self._dispatch(entry_path, 'handle_request', args, as_json=True)
        chains = [tuple(f['chain']) for f in result['findings'] if f['kind'] not in ('input', 'superglobal')]
        self.assertIn(('handle_request', '_save', '_persist'), chains)

    def test_transitive_cycle_does_not_hang(self):
        entry_path = self._write('entry.py', (
            "def handle_request(order):\n"
            "    _save(order)\n"
        ))
        self._write('helper.py', (
            "def _save(order):\n"
            "    db.execute('x', order)\n"
            "    handle_request(order)\n"
        ))
        args = self._make_args(boundary=True, transitive=True, depth=5)
        result = self._dispatch(entry_path, 'handle_request', args, as_json=True)
        kinds = {f['kind'] for f in result['findings']}
        self.assertIn('db', kinds)

    def test_transitive_unresolved_call_terminates_branch(self):
        """A call with no project-local definition must not crash the walk (EFFECTS section only)."""
        entry_path = self._write('entry.py', (
            "def handle_request(order):\n"
            "    totally_unknown_external_fn(order)\n"
        ))
        args = self._make_args(boundary=True, transitive=True)
        result = self._dispatch(entry_path, 'handle_request', args, as_json=True)
        effect_findings = [f for f in result['findings'] if f['kind'] not in ('input', 'superglobal')]
        self.assertEqual(effect_findings, [])

    def test_inputs_and_superglobals_stay_intra_procedural(self):
        """INPUTS/ENVIRONMENT describe the entry function's own signature — unaffected by --transitive."""
        entry_path = self._write('entry.py', (
            "def handle_request(order):\n"
            "    _save(unbound_var)\n"
        ))
        self._write('helper.py', (
            "def _save(order):\n"
            "    db.execute('x', order)\n"
        ))
        args = self._make_args(boundary=True, transitive=True)
        result = self._dispatch(entry_path, 'handle_request', args, as_json=True)
        inputs = [f for f in result['findings'] if f['kind'] == 'input']
        self.assertEqual({f['var'] for f in inputs}, {'order', '_save', 'unbound_var'})


if __name__ == '__main__':
    unittest.main()
