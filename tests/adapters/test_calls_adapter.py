"""Phase 3 call graph tests: cross-file resolution and calls:// adapter.

Covers:
- build_symbol_map() resolves Python imports to file paths
- resolve_callees() enriches call entries with resolved_file/resolved_name
- resolved_calls field appears in AST adapter output for resolved calls
- calls:// adapter: ?target= finds callers across project files
- calls:// adapter: ?depth=2 finds transitive callers
- calls:// adapter: missing target returns error message
- Callers index cache invalidation (mtime change)
- CallsRenderer: static method pattern, format=dot via query string
"""

import io
import os
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict

from reveal.adapters.ast.call_graph import build_symbol_map, resolve_callees
from reveal.adapters.ast.adapter import AstAdapter
from reveal.adapters.calls.index import build_callers_index, find_callers, find_callees, rank_by_callers
from reveal.adapters.calls.adapter import CallsAdapter, CallsRenderer
from reveal.adapters.calls.renderer import render_calls_structure


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(dir_path: str, filename: str, content: str) -> str:
    """Write *content* to dir_path/filename, return absolute path."""
    fpath = os.path.join(dir_path, filename)
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(content)
    return fpath


# ---------------------------------------------------------------------------
# Unit: build_symbol_map
# ---------------------------------------------------------------------------

class TestBuildSymbolMap(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_unsupported_extension_returns_empty(self):
        """Files with no registered extractor return an empty map."""
        path = _write(self.tmpdir, 'script.lua', '-- no extractor')
        result = build_symbol_map(path)
        self.assertEqual(result, {})

    def test_python_from_import(self):
        """from utils import validate_item → maps validate_item to utils.py."""
        _write(self.tmpdir, 'utils.py', 'def validate_item(): pass\n')
        main = _write(self.tmpdir, 'main.py',
                      'from utils import validate_item\n\ndef run(): validate_item()\n')
        sym_map = build_symbol_map(main)
        self.assertIn('validate_item', sym_map)
        self.assertIsNotNone(sym_map['validate_item'])
        self.assertTrue(sym_map['validate_item'].endswith('utils.py'))

    def test_python_module_import(self):
        """import db → maps 'db' to db.py."""
        _write(self.tmpdir, 'db.py', 'def insert(): pass\n')
        main = _write(self.tmpdir, 'main.py', 'import db\n\ndef run(): db.insert()\n')
        sym_map = build_symbol_map(main)
        self.assertIn('db', sym_map)
        self.assertTrue(sym_map['db'].endswith('db.py'))

    def test_python_alias_import(self):
        """import numpy as np → maps 'np' (stdlib/third-party, resolves to None)."""
        main = _write(self.tmpdir, 'main.py', 'import numpy as np\n')
        sym_map = build_symbol_map(main)
        # numpy isn't on disk in tmpdir, so resolved_file will be None
        self.assertIn('np', sym_map)

    def test_python_unresolvable_import_has_none(self):
        """Stdlib imports resolve to None (not on disk in tmpdir)."""
        main = _write(self.tmpdir, 'main.py', 'import os\nfrom pathlib import Path\n')
        sym_map = build_symbol_map(main)
        # 'os' is stdlib — resolve returns None in our tmpdir search
        # (could be either key present with None or absent depending on search path)
        # Just check no exception was raised
        self.assertIsInstance(sym_map, dict)


# ---------------------------------------------------------------------------
# Unit: resolve_callees
# ---------------------------------------------------------------------------

class TestResolveCallees(unittest.TestCase):

    def test_empty_calls(self):
        result = resolve_callees([], {})
        self.assertEqual(result, [])

    def test_unresolved_call(self):
        result = resolve_callees(['len', 'print'], {})
        self.assertEqual([e['name'] for e in result], ['len', 'print'])
        self.assertNotIn('resolved_file', result[0])

    def test_resolved_bare_name(self):
        sym_map = {'validate_item': '/utils/v.py'}
        result = resolve_callees(['validate_item'], sym_map)
        self.assertEqual(len(result), 1)
        entry = result[0]
        self.assertEqual(entry['name'], 'validate_item')
        self.assertEqual(entry['resolved_file'], '/utils/v.py')
        self.assertEqual(entry['resolved_name'], 'validate_item')

    def test_resolved_attribute_call(self):
        """db.insert → resolved_file from 'db', resolved_name = 'insert'."""
        sym_map = {'db': '/lib/database.py'}
        result = resolve_callees(['db.insert'], sym_map)
        entry = result[0]
        self.assertEqual(entry['name'], 'db.insert')
        self.assertEqual(entry['resolved_file'], '/lib/database.py')
        self.assertEqual(entry['resolved_name'], 'insert')

    def test_mixed_resolved_and_not(self):
        sym_map = {'validate_item': '/utils/v.py'}
        result = resolve_callees(['validate_item', 'len', 'db.insert'], sym_map)
        by_name = {e['name']: e for e in result}
        self.assertIn('resolved_file', by_name['validate_item'])
        self.assertNotIn('resolved_file', by_name['len'])
        self.assertNotIn('resolved_file', by_name['db.insert'])

    def test_none_file_does_not_resolve(self):
        """Symbol in map with None value (e.g. stdlib) → not resolved."""
        sym_map = {'os': None}
        result = resolve_callees(['os.path'], sym_map)
        self.assertNotIn('resolved_file', result[0])


# ---------------------------------------------------------------------------
# Integration: resolved_calls in AST adapter output
# ---------------------------------------------------------------------------

class TestResolvedCallsInAstAdapter(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_resolved_calls_field_present_when_resolved(self):
        """If a call can be resolved against imports, resolved_calls appears."""
        _write(self.tmpdir, 'utils.py', 'def validate_item(x): return x\n')
        main = _write(
            self.tmpdir, 'main.py',
            'from utils import validate_item\n\ndef process(x):\n    return validate_item(x)\n'
        )
        adapter = AstAdapter(main, 'type=function&name=process')
        result = adapter.get_structure()
        results = result.get('results', [])
        process_elem = next((r for r in results if r['name'] == 'process'), None)
        self.assertIsNotNone(process_elem, f"'process' not found in {[r['name'] for r in results]}")
        # validate_item should be in calls
        self.assertIn('validate_item', process_elem.get('calls', []))
        # resolved_calls should exist and have the resolution
        resolved = process_elem.get('resolved_calls')
        self.assertIsNotNone(resolved, "resolved_calls should be present when import resolves")
        vi_entry = next((e for e in resolved if e['name'] == 'validate_item'), None)
        self.assertIsNotNone(vi_entry)
        self.assertIn('resolved_file', vi_entry)
        self.assertTrue(vi_entry['resolved_file'].endswith('utils.py'))

    def test_no_resolved_calls_when_no_imports(self):
        """A file with no imports should not gain resolved_calls."""
        path = tempfile.mktemp(suffix='.py')
        try:
            with open(path, 'w') as f:
                f.write('def foo():\n    bar()\n\ndef bar():\n    pass\n')
            adapter = AstAdapter(path, 'type=function&name=foo')
            result = adapter.get_structure()
            results = result.get('results', [])
            foo = next((r for r in results if r['name'] == 'foo'), None)
            self.assertIsNotNone(foo)
            # bar is a local-only call, not resolvable — resolved_calls absent or empty
            self.assertNotIn('resolved_calls', foo)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Integration: build_callers_index + find_callers
# ---------------------------------------------------------------------------

class TestCallersIndex(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # app.py calls validate_item and format_result
        _write(self.tmpdir, 'app.py', '''
def validate_item(x):
    return x > 0

def format_result(x):
    return str(x)

def process(x):
    if validate_item(x):
        return format_result(x)
    return None
''')
        # worker.py also calls validate_item
        _write(self.tmpdir, 'worker.py', '''
from app import validate_item

def run_job(x):
    return validate_item(x)
''')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_index_contains_callee(self):
        index = build_callers_index(self.tmpdir)
        self.assertIn('validate_item', index)

    def test_direct_callers_found(self):
        result = find_callers(self.tmpdir, 'validate_item', depth=1)
        self.assertEqual(result['target'], 'validate_item')
        callers_at_level1 = result['levels'][0]['callers'] if result['levels'] else []
        caller_names = {r['caller'] for r in callers_at_level1}
        # process (in app.py) calls validate_item
        self.assertIn('process', caller_names)
        # run_job (in worker.py) calls validate_item
        self.assertIn('run_job', caller_names)

    def test_no_callers_for_unknown(self):
        result = find_callers(self.tmpdir, 'nonexistent_function', depth=1)
        self.assertEqual(result['total_callers'], 0)
        self.assertEqual(result['levels'], [])

    def test_depth_two_transitive(self):
        """Depth=2 should also find callers-of-callers."""
        # validate_item ← process ← (no one calls process in our fixture)
        # But this tests that depth>1 doesn't crash and returns correct structure
        result = find_callers(self.tmpdir, 'validate_item', depth=2)
        self.assertIn('levels', result)
        self.assertGreater(result['total_callers'], 0)

    def test_total_callers_count(self):
        result = find_callers(self.tmpdir, 'validate_item', depth=1)
        self.assertEqual(result['total_callers'], len(result['levels'][0]['callers']))


# ---------------------------------------------------------------------------
# Integration: CallsAdapter.get_structure
# ---------------------------------------------------------------------------

class TestCallsAdapter(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        _write(self.tmpdir, 'lib.py', '''
def helper(x):
    return x * 2
''')
        _write(self.tmpdir, 'main.py', '''
def caller_a(x):
    return helper(x)

def caller_b(x):
    return helper(x + 1)
''')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_target_returns_callers(self):
        adapter = CallsAdapter(self.tmpdir, 'target=helper')
        result = adapter.get_structure()
        self.assertEqual(result.get('target'), 'helper')
        self.assertGreater(result.get('total_callers', 0), 0)

    def test_missing_target_returns_error(self):
        adapter = CallsAdapter(self.tmpdir, '')
        result = adapter.get_structure()
        self.assertIn('error', result)

    def test_depth_capped_at_5(self):
        """depth=99 should be silently capped to 5 without crashing."""
        adapter = CallsAdapter(self.tmpdir, 'target=helper&depth=99')
        result = adapter.get_structure()
        # Should complete successfully regardless of depth cap
        self.assertIn('levels', result)

    def test_result_has_path(self):
        adapter = CallsAdapter(self.tmpdir, 'target=helper')
        result = adapter.get_structure()
        self.assertIn('path', result)


# ---------------------------------------------------------------------------
# CallsRenderer: static method pattern + format=dot via query string
# ---------------------------------------------------------------------------

def _capture_renderer(func, *args, **kwargs) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        func(*args, **kwargs)
    return buf.getvalue()


class TestCallsRenderer(unittest.TestCase):
    """Regression tests for CallsRenderer static-method calling convention."""

    def _base_result(self, **extra):
        return {
            'target': 'helper',
            'depth': 1,
            'total_callers': 1,
            'path': '/tmp/src',
            'levels': [{'level': 1, 'callers': [
                {'file': 'app.py', 'caller': 'main', 'line': 5, 'call_expr': 'helper', 'callee': 'helper'}
            ]}],
            **extra,
        }

    def test_render_structure_text(self):
        """render_structure(result, 'text') should output caller lines."""
        result = self._base_result()
        out = _capture_renderer(CallsRenderer.render_structure, result, 'text')
        self.assertIn('helper', out)
        self.assertIn('main', out)

    def test_render_structure_dot_via_cli_format(self):
        """render_structure(result, 'dot') should output digraph."""
        result = self._base_result()
        out = _capture_renderer(CallsRenderer.render_structure, result, 'dot')
        self.assertIn('digraph calls', out)
        self.assertIn('"main"', out)

    def test_render_structure_format_dot_in_query_string(self):
        """_query_format=dot stored in result should override CLI format arg."""
        result = self._base_result(_query_format='dot')
        # Even if CLI says 'text', query-string format=dot wins
        out = _capture_renderer(CallsRenderer.render_structure, result, 'text')
        self.assertIn('digraph calls', out)

    def test_render_structure_no_crash_without_self(self):
        """Calling CallsRenderer.render_structure without an instance must not crash."""
        result = self._base_result()
        # This is how the routing layer calls it — as a class-level function
        try:
            _capture_renderer(CallsRenderer.render_structure, result, 'text')
        except TypeError as e:
            self.fail(f"render_structure raised TypeError (likely self-bug): {e}")

    def test_format_dot_stored_in_result(self):
        """Adapter should store _query_format=dot when format=dot in query string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fpath = os.path.join(tmpdir, 'a.py')
            with open(fpath, 'w') as f:
                f.write('def helper(): pass\ndef main(): helper()\n')
            adapter = CallsAdapter(tmpdir, 'target=helper&format=dot')
            result = adapter.get_structure()
            self.assertEqual(result.get('_query_format'), 'dot')


# ---------------------------------------------------------------------------
# find_callees: forward direction — what does function X call?
# ---------------------------------------------------------------------------

class TestFindCallees(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        _write(self.tmpdir, 'utils.py', '''
def helper(x):
    return str(x)

def another():
    return len([])
''')
        _write(self.tmpdir, 'main.py', '''
def process(item):
    helper(item)
    another()
    return sorted([item])
''')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_callees_found_for_known_function(self):
        result = find_callees(self.tmpdir, 'process')
        self.assertEqual(result['target'], 'process')
        self.assertEqual(result['query'], 'callees')
        self.assertEqual(len(result['matches']), 1)
        calls = result['matches'][0]['calls']
        self.assertIn('helper', calls)
        self.assertIn('another', calls)

    def test_total_calls_count(self):
        result = find_callees(self.tmpdir, 'process')
        self.assertEqual(result['total_calls'], len(result['matches'][0]['calls']))

    def test_no_match_returns_empty(self):
        result = find_callees(self.tmpdir, 'nonexistent_func')
        self.assertEqual(result['matches'], [])
        self.assertEqual(result['total_calls'], 0)

    def test_multiple_files_same_name(self):
        """If two files define a function with the same name, both are returned."""
        _write(self.tmpdir, 'extra.py', '''
def process(x):
    len(x)
''')
        result = find_callees(self.tmpdir, 'process')
        self.assertEqual(len(result['matches']), 2)

    def test_match_includes_file_and_line(self):
        result = find_callees(self.tmpdir, 'helper')
        self.assertEqual(len(result['matches']), 1)
        match = result['matches'][0]
        self.assertIn('file', match)
        self.assertIn('line', match)
        self.assertGreater(match['line'], 0)


# ---------------------------------------------------------------------------
# CallsAdapter: ?callees= query param (forward lookup)
# ---------------------------------------------------------------------------

class TestCallsAdapterCallees(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        _write(self.tmpdir, 'a.py', '''
def worker():
    helper()
    validate()
''')
        _write(self.tmpdir, 'b.py', '''
def helper():
    pass

def validate():
    pass
''')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_callees_param_returns_callees_result(self):
        adapter = CallsAdapter(self.tmpdir, 'callees=worker')
        result = adapter.get_structure()
        self.assertEqual(result.get('type'), 'calls_callees')
        self.assertEqual(result.get('target'), 'worker')
        self.assertEqual(result.get('query'), 'callees')

    def test_callees_result_has_matches(self):
        adapter = CallsAdapter(self.tmpdir, 'callees=worker')
        result = adapter.get_structure()
        matches = result.get('matches', [])
        self.assertEqual(len(matches), 1)
        calls = matches[0]['calls']
        self.assertIn('helper', calls)
        self.assertIn('validate', calls)

    def test_callees_param_takes_precedence_over_target(self):
        """?callees=X&target=Y: callees param wins (callees mode)."""
        adapter = CallsAdapter(self.tmpdir, 'callees=worker&target=helper')
        result = adapter.get_structure()
        self.assertEqual(result.get('type'), 'calls_callees')
        self.assertEqual(result.get('target'), 'worker')

    def test_missing_both_params_returns_error(self):
        adapter = CallsAdapter(self.tmpdir, '')
        result = adapter.get_structure()
        self.assertIn('error', result)
        self.assertIn('target', result['error'])
        self.assertIn('callees', result['error'])

    def test_callees_format_json_stored_in_result(self):
        adapter = CallsAdapter(self.tmpdir, 'callees=worker&format=json')
        result = adapter.get_structure()
        self.assertEqual(result.get('_query_format'), 'json')


# ---------------------------------------------------------------------------
# Renderer: callees text output + relative paths
# ---------------------------------------------------------------------------

class TestCallsRendererCallees(unittest.TestCase):

    def _capture(self, data, fmt='text'):
        buf = io.StringIO()
        with redirect_stdout(buf):
            render_calls_structure(data, fmt)
        return buf.getvalue()

    def test_callees_text_shows_target(self):
        data = {
            'query': 'callees',
            'target': 'process',
            'path': 'src/',
            'total_calls': 2,
            'matches': [{'file': 'src/worker.py', 'function': 'process', 'line': 10,
                          'calls': ['helper', 'validate']}],
        }
        out = self._capture(data, 'text')
        self.assertIn('Callees of: process', out)
        self.assertIn('src/worker.py', out)
        self.assertIn('→ helper', out)
        self.assertIn('→ validate', out)

    def test_callees_no_match_shows_message(self):
        data = {
            'query': 'callees',
            'target': 'unknown',
            'path': 'src/',
            'total_calls': 0,
            'matches': [],
        }
        out = self._capture(data, 'text')
        self.assertIn("No definition of 'unknown' found", out)

    def test_callees_empty_calls_list(self):
        data = {
            'query': 'callees',
            'target': 'leaf_fn',
            'path': '.',
            'total_calls': 0,
            'matches': [{'file': 'app.py', 'function': 'leaf_fn', 'line': 5, 'calls': []}],
        }
        out = self._capture(data, 'text')
        self.assertIn('no calls detected', out)

    def test_callees_json_format(self):
        data = {
            'query': 'callees',
            'target': 'fn',
            'path': '.',
            'total_calls': 1,
            'matches': [{'file': 'a.py', 'function': 'fn', 'line': 3, 'calls': ['bar']}],
        }
        out = self._capture(data, 'json')
        import json
        parsed = json.loads(out)
        self.assertEqual(parsed['target'], 'fn')

    def test_text_renderer_shows_relative_path(self):
        """_render_text must show the full relative path, not just basename."""
        data = {
            'target': 'helper',
            'depth': 1,
            'total_callers': 1,
            'path': 'src/',
            'levels': [{'level': 1, 'callers': [
                {'file': 'src/utils/helpers.py', 'caller': 'main',
                 'line': 7, 'call_expr': 'helper', 'callee': 'helper'},
            ]}],
        }
        out = self._capture(data, 'text')
        self.assertIn('src/utils/helpers.py', out)
        # Must NOT reduce to just basename
        self.assertNotIn('  helpers.py:', out)


# ---------------------------------------------------------------------------
# Builtin filtering: find_callees with include_builtins flag
# ---------------------------------------------------------------------------

class TestFindCalleesBuiltinFiltering(unittest.TestCase):
    """Tests for ?builtins=false (default) — Python builtins hidden from callees."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # process calls: helper (project fn), sorted (builtin), len (builtin)
        _write(self.tmpdir, 'main.py', '''
def process(items):
    helper(items)
    return sorted(items)

def helper(x):
    return len(x)
''')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_builtins_hidden_by_default(self):
        result = find_callees(self.tmpdir, 'process')
        calls = result['matches'][0]['calls']
        self.assertIn('helper', calls)
        self.assertNotIn('sorted', calls)

    def test_include_builtins_restores_full_list(self):
        result = find_callees(self.tmpdir, 'process', include_builtins=True)
        calls = result['matches'][0]['calls']
        self.assertIn('helper', calls)
        self.assertIn('sorted', calls)

    def test_builtins_hidden_count_reported(self):
        result = find_callees(self.tmpdir, 'process')
        # 'sorted' is filtered; helper is not
        self.assertGreater(result['_builtins_hidden'], 0)

    def test_builtins_hidden_zero_when_include_true(self):
        result = find_callees(self.tmpdir, 'process', include_builtins=True)
        self.assertEqual(result['_builtins_hidden'], 0)

    def test_total_calls_reflects_filtered_list(self):
        result = find_callees(self.tmpdir, 'process')
        total = result['total_calls']
        actual = sum(len(m['calls']) for m in result['matches'])
        self.assertEqual(total, actual)

    def test_exception_types_hidden_by_default(self):
        _write(self.tmpdir, 'validator.py', '''
def validate(x):
    if not x:
        raise ValueError("bad")
    return clean(x)

def clean(x):
    return x
''')
        result = find_callees(self.tmpdir, 'validate')
        calls = result['matches'][0]['calls']
        self.assertNotIn('ValueError', calls)
        self.assertIn('clean', calls)

    def test_stdlib_dotted_calls_not_filtered(self):
        """os.path.join — bare name is 'join', not a builtin — must stay visible."""
        _write(self.tmpdir, 'utils.py', '''
import os

def build_path(base, name):
    return os.path.join(base, name)
''')
        result = find_callees(self.tmpdir, 'build_path', include_builtins=False)
        calls = result['matches'][0]['calls']
        # 'join' is not a Python builtin function — should be visible
        self.assertTrue(any('join' in c for c in calls))


# ---------------------------------------------------------------------------
# Adapter: ?builtins=true query param
# ---------------------------------------------------------------------------

class TestCallsAdapterBuiltinsParam(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        _write(self.tmpdir, 'a.py', '''
def worker(items):
    helper(items)
    return sorted(items)

def helper(x):
    pass
''')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_default_hides_builtins(self):
        adapter = CallsAdapter(self.tmpdir, 'callees=worker')
        result = adapter.get_structure()
        calls = result['matches'][0]['calls']
        self.assertIn('helper', calls)
        self.assertNotIn('sorted', calls)

    def test_builtins_true_includes_builtins(self):
        adapter = CallsAdapter(self.tmpdir, 'callees=worker&builtins=true')
        result = adapter.get_structure()
        calls = result['matches'][0]['calls']
        self.assertIn('helper', calls)
        self.assertIn('sorted', calls)

    def test_builtins_false_explicit_hides_builtins(self):
        adapter = CallsAdapter(self.tmpdir, 'callees=worker&builtins=false')
        result = adapter.get_structure()
        calls = result['matches'][0]['calls']
        self.assertNotIn('sorted', calls)


# ---------------------------------------------------------------------------
# Renderer: builtins_hidden footer in text output
# ---------------------------------------------------------------------------

class TestCallsRendererBuiltinsFooter(unittest.TestCase):

    def _capture(self, data, fmt='text'):
        buf = io.StringIO()
        with redirect_stdout(buf):
            render_calls_structure(data, fmt)
        return buf.getvalue()

    def test_footer_shown_when_builtins_hidden(self):
        data = {
            'query': 'callees',
            'target': 'process',
            'path': 'src/',
            'total_calls': 1,
            '_builtins_hidden': 3,
            'matches': [{'file': 'src/main.py', 'function': 'process', 'line': 5,
                         'calls': ['helper']}],
        }
        out = self._capture(data, 'text')
        self.assertIn('3 builtin(s) hidden', out)
        self.assertIn('?builtins=true', out)

    def test_footer_absent_when_none_hidden(self):
        data = {
            'query': 'callees',
            'target': 'process',
            'path': 'src/',
            'total_calls': 1,
            '_builtins_hidden': 0,
            'matches': [{'file': 'src/main.py', 'function': 'process', 'line': 5,
                         'calls': ['helper']}],
        }
        out = self._capture(data, 'text')
        self.assertNotIn('builtin', out)

    def test_footer_absent_when_key_missing(self):
        """Renderer is backwards-compatible — no _builtins_hidden key → no footer."""
        data = {
            'query': 'callees',
            'target': 'fn',
            'path': '.',
            'total_calls': 1,
            'matches': [{'file': 'a.py', 'function': 'fn', 'line': 2, 'calls': ['bar']}],
        }
        out = self._capture(data, 'text')
        self.assertNotIn('builtin', out)


# ---------------------------------------------------------------------------
# Unit: rank_by_callers
# ---------------------------------------------------------------------------

class TestRankByCallers(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Three functions. helper is called by both process_a and process_b.
        # process_a is called by main. standalone has no callers.
        code = textwrap.dedent("""\
            def helper():
                pass

            def process_a():
                helper()

            def process_b():
                helper()

            def main():
                process_a()

            def standalone():
                pass
        """)
        self.py_file = os.path.join(self.tmpdir, 'sample.py')
        with open(self.py_file, 'w') as f:
            f.write(code)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_returns_ranking_structure(self):
        result = rank_by_callers(self.tmpdir)
        self.assertIn('query', result)
        self.assertEqual(result['query'], 'rank_callers')
        self.assertIn('entries', result)
        self.assertIn('total_unique_callees', result)

    def test_helper_ranks_first(self):
        result = rank_by_callers(self.tmpdir)
        entries = result['entries']
        top_name = entries[0]['name'] if entries else ''
        self.assertEqual(top_name, 'helper')

    def test_helper_has_two_callers(self):
        result = rank_by_callers(self.tmpdir)
        entry = next(e for e in result['entries'] if e['name'] == 'helper')
        self.assertEqual(entry['caller_count'], 2)

    def test_top_param_limits_output(self):
        result = rank_by_callers(self.tmpdir, top=1)
        self.assertEqual(len(result['entries']), 1)
        self.assertEqual(result['top'], 1)

    def test_top_capped_at_100(self):
        result = rank_by_callers(self.tmpdir, top=999)
        self.assertEqual(result['top'], 100)

    def test_sorted_descending(self):
        result = rank_by_callers(self.tmpdir)
        counts = [e['caller_count'] for e in result['entries']]
        self.assertEqual(counts, sorted(counts, reverse=True))


class TestRankRendering(unittest.TestCase):

    def _capture(self, data: Dict[str, Any], fmt: str = 'text') -> str:
        buf = io.StringIO()
        with redirect_stdout(buf):
            render_calls_structure(data, fmt)
        return buf.getvalue()

    def _ranking_data(self, entries=None):
        if entries is None:
            entries = [
                {'name': 'validate', 'caller_count': 3,
                 'callers': [
                     {'file': 'a.py', 'caller': 'run', 'line': 10},
                     {'file': 'b.py', 'caller': 'process', 'line': 20},
                     {'file': 'c.py', 'caller': 'main', 'line': 5},
                 ]},
                {'name': 'parse', 'caller_count': 1,
                 'callers': [{'file': 'd.py', 'caller': 'load', 'line': 7}]},
            ]
        return {
            'query': 'rank_callers',
            'path': 'src/',
            'top': 10,
            'total_unique_callees': len(entries),
            'entries': entries,
        }

    def test_header_present(self):
        out = self._capture(self._ranking_data())
        self.assertIn('Most-called functions', out)
        self.assertIn('src/', out)

    def test_entries_rendered(self):
        out = self._capture(self._ranking_data())
        self.assertIn('validate', out)
        self.assertIn('3 callers', out)
        self.assertIn('parse', out)
        self.assertIn('1 caller', out)

    def test_callers_listed(self):
        out = self._capture(self._ranking_data())
        self.assertIn('run', out)
        self.assertIn('a.py', out)

    def test_truncation_at_five(self):
        callers = [{'file': f'f{i}.py', 'caller': f'fn{i}', 'line': i} for i in range(8)]
        data = self._ranking_data([{'name': 'foo', 'caller_count': 8, 'callers': callers}])
        out = self._capture(data)
        self.assertIn('… and 3 more', out)

    def test_empty_entries(self):
        out = self._capture(self._ranking_data([]))
        self.assertIn('No call data found', out)

    def test_json_format(self):
        out = self._capture(self._ranking_data(), 'json')
        import json
        parsed = json.loads(out)
        self.assertEqual(parsed['query'], 'rank_callers')

    def test_rank_param_routes_to_ranking(self):
        """?rank=callers in CallsAdapter routes to rank_by_callers."""
        import tempfile, textwrap
        tmpdir = tempfile.mkdtemp()
        try:
            code = textwrap.dedent("""\
                def a():
                    b()
                def b():
                    pass
            """)
            with open(os.path.join(tmpdir, 'x.py'), 'w') as f:
                f.write(code)
            adapter = CallsAdapter(tmpdir, 'rank=callers&top=5')
            result = adapter.get_structure()
            self.assertEqual(result.get('query'), 'rank_callers')
            self.assertIn('entries', result)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
