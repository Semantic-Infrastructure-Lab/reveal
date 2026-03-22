"""Unit tests for AstAdapter (TEST-01).

Covers:
- __init__: query string parsing, show_mode, include_builtins, result_control
- get_structure: filters, sort/limit/offset, auto-cap, builtin filtering
- Output contract: source, source_type, contract_version, meta fields
- Error cases: multi-file colon syntax, empty path, binary file
"""

import os
import tempfile
import textwrap
import unittest
from pathlib import Path

from reveal.adapters.ast.adapter import AstAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(dir_path: str, filename: str, content: str) -> str:
    fpath = os.path.join(dir_path, filename)
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(content)
    return fpath


SIMPLE_PY = textwrap.dedent("""\
    def short(): pass

    def medium(a, b):
        if a:
            return b
        return a

    @staticmethod
    def decorated(): pass

    class MyClass:
        def method(self): pass
""")

CALLS_PY = textwrap.dedent("""\
    def caller():
        result = len([1, 2, 3])
        return sorted(result)

    def helper():
        caller()
""")


# ---------------------------------------------------------------------------
# __init__: query string parsing
# ---------------------------------------------------------------------------

class TestAstAdapterInit(unittest.TestCase):

    def test_no_query_string_defaults(self):
        adapter = AstAdapter('/tmp')
        self.assertEqual(adapter.query, {})
        self.assertIsNone(adapter.show_mode)
        self.assertFalse(adapter.include_builtins)
        self.assertIsNone(adapter.result_control.limit)

    def test_show_calls_extracted(self):
        adapter = AstAdapter('/tmp', 'show=calls')
        self.assertEqual(adapter.show_mode, 'calls')
        # show= should not bleed into filter query
        self.assertNotIn('show', adapter.query)

    def test_builtins_true_extracted(self):
        adapter = AstAdapter('/tmp', 'builtins=true')
        self.assertTrue(adapter.include_builtins)
        self.assertNotIn('builtins', adapter.query)

    def test_limit_parsed(self):
        adapter = AstAdapter('/tmp', 'limit=10')
        self.assertEqual(adapter.result_control.limit, 10)

    def test_sort_parsed(self):
        adapter = AstAdapter('/tmp', 'sort=-lines')
        self.assertEqual(adapter.result_control.sort_field, 'lines')
        self.assertTrue(adapter.result_control.sort_descending)

    def test_colon_syntax_raises_value_error(self):
        with tempfile.TemporaryDirectory() as d:
            f1 = _write(d, 'a.py', 'def f(): pass\n')
            f2 = _write(d, 'b.py', 'def g(): pass\n')
            with self.assertRaises(ValueError) as ctx:
                AstAdapter(f'{f1}:{f2}')
            self.assertIn('multi-file colon syntax', str(ctx.exception))

    def test_tilde_expanded(self):
        adapter = AstAdapter('~/some/path')
        self.assertNotIn('~', adapter.path)


# ---------------------------------------------------------------------------
# get_structure: output contract
# ---------------------------------------------------------------------------

class TestAstAdapterOutputContract(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        _write(self.tmpdir, 'mod.py', SIMPLE_PY)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_source_and_source_type_present(self):
        adapter = AstAdapter(self.tmpdir)
        result = adapter.get_structure()
        self.assertIn('source', result)
        self.assertIn('source_type', result)

    def test_contract_version_present(self):
        adapter = AstAdapter(self.tmpdir)
        result = adapter.get_structure()
        self.assertIn('contract_version', result)
        self.assertEqual(result['contract_version'], '1.1')

    def test_meta_present(self):
        adapter = AstAdapter(self.tmpdir)
        result = adapter.get_structure()
        self.assertIn('meta', result)
        self.assertIn('parse_mode', result['meta'])
        self.assertEqual(result['meta']['parse_mode'], 'tree_sitter_full')

    def test_result_type_is_ast_query(self):
        adapter = AstAdapter(self.tmpdir)
        result = adapter.get_structure()
        self.assertEqual(result.get('type'), 'ast_query')

    def test_results_list_present(self):
        adapter = AstAdapter(self.tmpdir)
        result = adapter.get_structure()
        self.assertIn('results', result)
        self.assertIsInstance(result['results'], list)

    def test_total_files_count(self):
        adapter = AstAdapter(self.tmpdir)
        result = adapter.get_structure()
        self.assertEqual(result['total_files'], 1)


# ---------------------------------------------------------------------------
# get_structure: filtering
# ---------------------------------------------------------------------------

class TestAstAdapterFiltering(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        _write(self.tmpdir, 'mod.py', SIMPLE_PY)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_no_filter_returns_all_definitions(self):
        adapter = AstAdapter(self.tmpdir)
        result = adapter.get_structure()
        names = {r['name'] for r in result['results']}
        self.assertIn('short', names)
        self.assertIn('medium', names)
        self.assertIn('method', names)

    def test_filter_by_name(self):
        adapter = AstAdapter(self.tmpdir, 'name=short')
        result = adapter.get_structure()
        self.assertEqual(len(result['results']), 1)
        self.assertEqual(result['results'][0]['name'], 'short')

    def test_total_results_reflects_pre_limit_count(self):
        # total_results should count all matches, not just displayed
        adapter = AstAdapter(self.tmpdir, 'limit=1')
        result = adapter.get_structure()
        self.assertEqual(result['displayed_results'], 1)
        self.assertGreater(result['total_results'], 1)

    def test_directory_scan_finds_multiple_files(self):
        _write(self.tmpdir, 'other.py', 'def extra(): pass\n')
        adapter = AstAdapter(self.tmpdir)
        result = adapter.get_structure()
        self.assertEqual(result['total_files'], 2)

    def test_single_file_path(self):
        fpath = _write(self.tmpdir, 'single.py', 'def only(): pass\n')
        adapter = AstAdapter(fpath)
        result = adapter.get_structure()
        self.assertEqual(result['total_files'], 1)
        names = {r['name'] for r in result['results']}
        self.assertIn('only', names)


# ---------------------------------------------------------------------------
# get_structure: result control (sort, limit, offset)
# ---------------------------------------------------------------------------

class TestAstAdapterResultControl(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Write a file with several functions
        code = '\n'.join(
            f'def func_{i}(): pass\n' for i in range(10)
        )
        _write(self.tmpdir, 'many.py', code)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_limit_caps_displayed_results(self):
        adapter = AstAdapter(self.tmpdir, 'limit=3')
        result = adapter.get_structure()
        self.assertEqual(result['displayed_results'], 3)
        self.assertEqual(len(result['results']), 3)

    def test_limit_warning_in_meta(self):
        adapter = AstAdapter(self.tmpdir, 'limit=3')
        result = adapter.get_structure()
        warning_types = [w['type'] for w in result['meta']['warnings']]
        self.assertIn('truncated', warning_types)

    def test_offset_skips_results(self):
        adapter_all = AstAdapter(self.tmpdir)
        adapter_offset = AstAdapter(self.tmpdir, 'offset=2')
        all_results = adapter_all.get_structure()['results']
        offset_results = adapter_offset.get_structure()['results']
        # First result with offset should be the third result without offset
        if len(all_results) > 2 and offset_results:
            self.assertEqual(all_results[2]['name'], offset_results[0]['name'])


# ---------------------------------------------------------------------------
# get_structure: auto-cap (200 result default)
# ---------------------------------------------------------------------------

class TestAstAdapterAutoCap(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # 210 single-line functions
        lines = [f'def f{i}(): pass' for i in range(210)]
        _write(self.tmpdir, 'big.py', '\n'.join(lines) + '\n')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_auto_cap_limits_to_200(self):
        adapter = AstAdapter(self.tmpdir)
        result = adapter.get_structure()
        self.assertLessEqual(result['displayed_results'], 200)

    def test_auto_cap_warning_in_meta(self):
        adapter = AstAdapter(self.tmpdir)
        result = adapter.get_structure()
        warning_types = [w['type'] for w in result['meta']['warnings']]
        self.assertIn('auto_capped', warning_types)

    def test_explicit_limit_overrides_auto_cap(self):
        adapter = AstAdapter(self.tmpdir, 'limit=210')
        result = adapter.get_structure()
        # With explicit limit=210 covering all 210 functions, no auto_cap warning
        warning_types = [w['type'] for w in result['meta']['warnings']]
        self.assertNotIn('auto_capped', warning_types)


# ---------------------------------------------------------------------------
# get_structure: builtin filtering
# ---------------------------------------------------------------------------

class TestAstAdapterBuiltinFiltering(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        _write(self.tmpdir, 'calls.py', CALLS_PY)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_builtins_filtered_by_default(self):
        adapter = AstAdapter(self.tmpdir, 'show=calls')
        result = adapter.get_structure()
        all_calls = []
        for elem in result['results']:
            all_calls.extend(elem.get('calls', []))
        # len and sorted are Python builtins — must be filtered by default
        self.assertNotIn('len', all_calls)
        self.assertNotIn('sorted', all_calls)

    def test_builtins_true_includes_builtins(self):
        adapter = AstAdapter(self.tmpdir, 'show=calls&builtins=true')
        result = adapter.get_structure()
        all_calls = []
        for elem in result['results']:
            all_calls.extend(elem.get('calls', []))
        # With builtins=true, len and sorted should appear
        self.assertTrue(
            'len' in all_calls or 'sorted' in all_calls,
            "Expected at least one builtin in calls list when builtins=true"
        )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestAstAdapterEdgeCases(unittest.TestCase):

    def test_empty_directory_returns_zero_results(self):
        with tempfile.TemporaryDirectory() as d:
            adapter = AstAdapter(d)
            result = adapter.get_structure()
            self.assertEqual(result['total_files'], 0)
            self.assertEqual(result['total_results'], 0)
            self.assertEqual(result['results'], [])

    def test_nonexistent_path_returns_empty(self):
        adapter = AstAdapter('/nonexistent/path/that/does/not/exist')
        result = adapter.get_structure()
        self.assertEqual(result['results'], [])

    def test_binary_file_does_not_crash(self):
        with tempfile.TemporaryDirectory() as d:
            bin_path = os.path.join(d, 'binary.py')
            with open(bin_path, 'wb') as f:
                f.write(bytes(range(256)))
            adapter = AstAdapter(d)
            # Must not raise
            result = adapter.get_structure()
            self.assertIn('results', result)

    def test_empty_python_file_does_not_crash(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, 'empty.py', '')
            adapter = AstAdapter(d)
            result = adapter.get_structure()
            self.assertIn('results', result)


if __name__ == '__main__':
    unittest.main()
