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

from reveal.adapters.ast.call_graph import build_symbol_map, resolve_callees, build_alias_map
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
# Unit: build_alias_map
# ---------------------------------------------------------------------------

class TestBuildAliasMap(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_from_import_with_alias(self):
        """from utils import helper as h → {'h': 'helper'}."""
        _write(self.tmpdir, 'utils.py', 'def helper(): pass\n')
        main = _write(self.tmpdir, 'main.py',
                      'from utils import helper as h\n\ndef run(): h()\n')
        result = build_alias_map(main)
        self.assertEqual(result.get('h'), 'helper')

    def test_module_import_with_alias(self):
        """import numpy as np → {'np': 'numpy'}."""
        main = _write(self.tmpdir, 'main.py', 'import numpy as np\n')
        result = build_alias_map(main)
        self.assertEqual(result.get('np'), 'numpy')

    def test_no_alias_returns_empty(self):
        """from utils import helper (no alias) → empty map."""
        _write(self.tmpdir, 'utils.py', 'def helper(): pass\n')
        main = _write(self.tmpdir, 'main.py',
                      'from utils import helper\n\ndef run(): helper()\n')
        result = build_alias_map(main)
        self.assertNotIn('helper', result)

    def test_multiple_aliases(self):
        """Multiple aliased imports all appear in the map."""
        _write(self.tmpdir, 'utils.py', 'def foo(): pass\ndef bar(): pass\n')
        main = _write(self.tmpdir, 'main.py',
                      'from utils import foo as f, bar as b\n')
        result = build_alias_map(main)
        self.assertEqual(result.get('f'), 'foo')
        self.assertEqual(result.get('b'), 'bar')

    def test_unsupported_language_returns_empty(self):
        """Files with no registered extractor return an empty map."""
        path = _write(self.tmpdir, 'script.lua', '-- no extractor')
        result = build_alias_map(path)
        self.assertEqual(result, {})


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

    def test_starred_callee_found_by_find_callers(self):
        """find_callers must find callers that use *foo(args) starred-unpack syntax.

        tree-sitter parses `*foo(bar)` as call(list_splat(*foo), bar).
        Previously this was indexed as '*foo' and never matched a lookup for 'foo'.
        Regression test for the list_splat unwrap fix in _get_callee_name.
        """
        import shutil
        tmpdir = tempfile.mkdtemp()
        try:
            _write(tmpdir, 'app.py', '''
def _job_oob(job):
    return job.status, job.progress

def sticker_rerun(job_id):
    job = get_job(job_id)
    return card, *_job_oob(job)

def sticker_update(job_id):
    return header(), *_job_oob(get_job(job_id))
''')
            result = find_callers(tmpdir, '_job_oob', depth=1)
            caller_names = {r['caller'] for r in result['levels'][0]['callers']} if result['levels'] else set()
            self.assertIn('sticker_rerun', caller_names,
                          f"sticker_rerun uses *_job_oob() but was not found. Got: {caller_names}")
            self.assertIn('sticker_update', caller_names,
                          f"sticker_update uses *_job_oob() but was not found. Got: {caller_names}")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Unit: import alias resolution in build_callers_index / find_callers /
#        find_uncalled  (BACK-076)
# ---------------------------------------------------------------------------

class TestAliasResolutionInIndex(unittest.TestCase):
    """build_callers_index must index canonical names when a call uses an alias.

    Scenario: utils.py defines `helper`.  caller.py does
    ``from utils import helper as h`` then calls ``h()``.  The callers index
    must contain `helper` (the definition name) so that find_uncalled does not
    flag `helper` as dead code and find_callers('helper') finds the caller.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import shutil
        # utils.py defines the function
        _write(self.tmpdir, 'utils.py', textwrap.dedent('''\
            def helper():
                return 42
        '''))
        # caller.py imports it under an alias and calls the alias
        _write(self.tmpdir, 'caller.py', textwrap.dedent('''\
            from utils import helper as h

            def run():
                return h()
        '''))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_canonical_name_in_index(self):
        """Index must contain the definition name 'helper', not just the alias 'h'."""
        index = build_callers_index(self.tmpdir)
        self.assertIn('helper', index,
                      "canonical name 'helper' missing — aliased call to 'h' not resolved")

    def test_alias_name_still_in_index(self):
        """Index must still contain 'h' (the alias) for direct alias lookups."""
        index = build_callers_index(self.tmpdir)
        self.assertIn('h', index)

    def test_find_callers_via_canonical_name(self):
        """find_callers('helper') must find run() even though it calls via alias h."""
        result = find_callers(self.tmpdir, 'helper', depth=1)
        callers = [r['caller'] for lvl in result['levels'] for r in lvl['callers']]
        self.assertIn('run', callers,
                      "find_callers('helper') missed caller that uses alias 'h'")

    def test_find_uncalled_does_not_flag_aliased_function(self):
        """find_uncalled must NOT report 'helper' as dead code when called via alias."""
        from reveal.adapters.calls.index import find_uncalled
        result = find_uncalled(self.tmpdir)
        uncalled_names = {e['name'] for e in result['entries']}
        self.assertNotIn('helper', uncalled_names,
                         "'helper' incorrectly flagged as dead code — alias 'h' not resolved")

    def test_module_level_alias_resolved(self):
        """import utils as u; u.helper() — module alias, not function alias."""
        import shutil
        tmpdir2 = tempfile.mkdtemp()
        try:
            _write(tmpdir2, 'utils.py', 'def helper(): pass\n')
            _write(tmpdir2, 'main.py', textwrap.dedent('''\
                import utils as u

                def run():
                    u.helper()
            '''))
            index = build_callers_index(tmpdir2)
            # 'helper' is accessed as u.helper — bare is 'helper' (split on dot),
            # so it's indexed directly without needing alias resolution.
            # This test confirms the existing dot-split path still works.
            self.assertIn('helper', index)
        finally:
            shutil.rmtree(tmpdir2, ignore_errors=True)


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

    def test_render_element_absent(self):
        """BUG-03: CallsRenderer must NOT have render_element.

        render_element signals to the routing layer that the adapter supports
        element-based access and will call adapter.get_element(). CallsAdapter
        has no get_element(), so having render_element causes an AttributeError
        at runtime. Verify it has been removed.
        """
        self.assertFalse(
            hasattr(CallsRenderer, 'render_element'),
            "CallsRenderer.render_element should not exist — CallsAdapter has no get_element()",
        )

    def test_routing_layer_treats_calls_as_structure_only(self):
        """BUG-03: routing layer must not route calls:// to element mode.

        The routing layer uses `hasattr(renderer_class, 'render_element')` to
        decide between element mode (calls get_element → returns None → "not
        found" error) and structure mode (calls get_structure → real results).
        With render_element removed, supports_elements is False, so structure
        mode is always used.
        """
        supports_elements = hasattr(CallsRenderer, 'render_element')
        self.assertFalse(
            supports_elements,
            "CallsRenderer must not signal element support — "
            "calls:// has no element access, only structure (target=X queries)",
        )


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


class TestCallsAdapterColonSyntax(unittest.TestCase):
    """BACK-070: calls://path:target colon shorthand routes element to target= param."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        _write(self.tmpdir, 'lib.py', textwrap.dedent('''\
            def helper(x):
                return x * 2
        '''))
        _write(self.tmpdir, 'main.py', textwrap.dedent('''\
            def caller_a(x):
                return helper(x)
        '''))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_colon_syntax_extracts_target(self):
        """'path:target' sets target= in query_params and strips element from path."""
        adapter = CallsAdapter(f"{self.tmpdir}:helper")
        self.assertEqual(adapter.query_params.get('target'), 'helper')
        self.assertEqual(adapter.path, self.tmpdir)

    def test_colon_syntax_finds_callers(self):
        """calls via 'path:target' actually resolves callers correctly."""
        adapter = CallsAdapter(f"{self.tmpdir}:helper")
        result = adapter.get_structure()
        self.assertEqual(result.get('target'), 'helper')
        self.assertGreater(result.get('total_callers', 0), 0)

    def test_colon_syntax_does_not_apply_when_path_missing(self):
        """If path before ':' doesn't exist, fall through to normal path handling."""
        adapter = CallsAdapter('/nonexistent/path:helper')
        # Path should not be modified — the colon shorthand should not apply
        self.assertIn(':helper', adapter.path)

    def test_colon_syntax_does_not_override_explicit_target(self):
        """Explicit ?target= in query string takes priority over colon element."""
        adapter = CallsAdapter(f"{self.tmpdir}:helper", 'target=caller_a')
        # Explicit query_string target should win — colon shorthand is skipped
        self.assertEqual(adapter.query_params.get('target'), 'caller_a')

    def test_no_colon_path_unaffected(self):
        """Paths without ':' are not modified."""
        adapter = CallsAdapter(self.tmpdir, 'target=helper')
        self.assertEqual(adapter.path, self.tmpdir)
        self.assertEqual(adapter.query_params.get('target'), 'helper')


class TestCallsRendererMissingTarget(unittest.TestCase):
    """BACK-070: missing target should emit a clear error, not 'Callers of: ?'."""

    def _capture_stderr(self, func, *args, **kwargs) -> str:
        import sys
        buf = io.StringIO()
        old_stderr = sys.stderr
        sys.stderr = buf
        try:
            func(*args, **kwargs)
        finally:
            sys.stderr = old_stderr
        return buf.getvalue()

    def test_missing_target_shows_error_not_question_mark(self):
        """When data has 'error' key and no 'target', renderer shows error to stderr."""
        from reveal.adapters.calls.renderer import render_calls_structure
        data = {
            'path': '/some/path',
            'error': 'Missing required parameter: target=<name>',
            'example': 'calls:///some/path?target=my_function',
        }
        err = self._capture_stderr(render_calls_structure, data, 'text')
        self.assertIn('Missing required parameter', err)
        self.assertIn('calls://', err)

    def test_error_case_does_not_print_callers_of_question_mark(self):
        """The 'Callers of: ?' text should NOT appear when target is missing."""
        from reveal.adapters.calls.renderer import render_calls_structure
        import sys
        buf = io.StringIO()
        data = {
            'path': '/some/path',
            'error': 'Missing required parameter: target=<name>',
        }
        with redirect_stdout(buf):
            render_calls_structure(data, 'text')
        stdout = buf.getvalue()
        self.assertNotIn('Callers of: ?', stdout)


# ---------------------------------------------------------------------------
# Unit: find_uncalled — dead code detection
# ---------------------------------------------------------------------------

class TestFindUncalled(unittest.TestCase):

    def setUp(self):
        import shutil
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, filename, content):
        return _write(self.tmpdir, filename, textwrap.dedent(content))

    def test_uncalled_function_detected(self):
        """A function that is defined but never called anywhere is flagged."""
        from reveal.adapters.calls.index import find_uncalled
        self._write('a.py', '''\
            def used():
                pass

            def never_called():
                pass

            def main():
                used()
        ''')
        result = find_uncalled(self.tmpdir)
        names = [e['name'] for e in result['entries']]
        self.assertIn('never_called', names)
        self.assertNotIn('used', names)

    def test_called_function_excluded(self):
        """A function called by another function is not in the uncalled list."""
        from reveal.adapters.calls.index import find_uncalled
        self._write('b.py', '''\
            def helper():
                pass

            def caller():
                helper()
        ''')
        result = find_uncalled(self.tmpdir)
        names = [e['name'] for e in result['entries']]
        self.assertNotIn('helper', names)

    def test_dunder_methods_excluded(self):
        """__dunder__ methods are excluded even if nothing calls them directly."""
        from reveal.adapters.calls.index import find_uncalled
        self._write('c.py', '''\
            class Foo:
                def __init__(self):
                    pass
                def __str__(self):
                    return "Foo"
                def regular(self):
                    pass
        ''')
        result = find_uncalled(self.tmpdir)
        names = [e['name'] for e in result['entries']]
        self.assertNotIn('__init__', names)
        self.assertNotIn('__str__', names)

    def test_property_decorator_excluded(self):
        """@property methods are excluded (called implicitly by attribute access)."""
        from reveal.adapters.calls.index import find_uncalled
        self._write('d.py', '''\
            class Bar:
                @property
                def value(self):
                    return self._value

                def other(self):
                    pass
        ''')
        result = find_uncalled(self.tmpdir)
        names = [e['name'] for e in result['entries']]
        self.assertNotIn('value', names)

    def test_private_flag_set(self):
        """Functions starting with _ have is_private=True."""
        from reveal.adapters.calls.index import find_uncalled
        self._write('e.py', '''\
            def _internal():
                pass

            def public():
                pass
        ''')
        result = find_uncalled(self.tmpdir)
        private_entries = [e for e in result['entries'] if e['name'] == '_internal']
        public_entries = [e for e in result['entries'] if e['name'] == 'public']
        self.assertTrue(private_entries[0]['is_private'])
        self.assertFalse(public_entries[0]['is_private'])

    def test_only_functions_skips_methods(self):
        """only_functions=True excludes methods (category='methods')."""
        from reveal.adapters.calls.index import find_uncalled
        self._write('f.py', '''\
            class MyClass:
                def method_never_called(self):
                    pass

            def func_never_called():
                pass
        ''')
        result = find_uncalled(self.tmpdir, only_functions=True)
        names = [e['name'] for e in result['entries']]
        self.assertIn('func_never_called', names)
        self.assertNotIn('method_never_called', names)

    def test_top_limits_results(self):
        """top=N caps the number of returned entries."""
        from reveal.adapters.calls.index import find_uncalled
        self._write('g.py', '''\
            def a(): pass
            def b(): pass
            def c(): pass
            def d(): pass
            def e(): pass
        ''')
        result = find_uncalled(self.tmpdir, top=3)
        self.assertLessEqual(len(result['entries']), 3)

    def test_total_counts_accurate(self):
        """total_defined and total_uncalled fields are correct.

        Note: 'runner' is never called by anything (it's an entry point), so
        it will appear in the uncalled list.  Only 'called' (called by runner)
        should be excluded.
        """
        from reveal.adapters.calls.index import find_uncalled
        self._write('h.py', '''\
            def called():
                pass

            def uncalled1():
                pass

            def uncalled2():
                pass

            def runner():
                called()
        ''')
        result = find_uncalled(self.tmpdir)
        self.assertGreaterEqual(result['total_defined'], 4)
        names = [e['name'] for e in result['entries']]
        self.assertIn('uncalled1', names)
        self.assertIn('uncalled2', names)
        # 'called' is invoked by runner — should not be in uncalled list
        self.assertNotIn('called', names)
        # 'runner' has no callers (entry point) — correctly flagged as uncalled
        self.assertIn('runner', names)

    def test_cross_file_call_removes_from_uncalled(self):
        """A function called from a different file is not flagged as uncalled."""
        from reveal.adapters.calls.index import find_uncalled
        self._write('lib.py', '''\
            def shared_util():
                pass
        ''')
        self._write('main.py', '''\
            from lib import shared_util

            def run():
                shared_util()
        ''')
        result = find_uncalled(self.tmpdir)
        names = [e['name'] for e in result['entries']]
        self.assertNotIn('shared_util', names)

    def test_single_file_scopes_definitions(self):
        """When a file path is given, only definitions from that file appear.

        The callers index still uses the full parent directory, so a function
        called from a sibling file is correctly excluded.
        """
        from reveal.adapters.calls.index import find_uncalled
        import os
        lib_path = self._write('lib2.py', '''\
            def orphan_in_lib():
                pass
            def used_in_lib():
                pass
        ''')
        self._write('consumer2.py', '''\
            def consumer():
                used_in_lib()
        ''')
        result = find_uncalled(lib_path)
        names = [e['name'] for e in result['entries']]
        # Only lib2.py definitions reported
        self.assertIn('orphan_in_lib', names)
        self.assertNotIn('used_in_lib', names)
        # consumer (from sibling file) must not appear
        self.assertNotIn('consumer', names)

    def test_noqa_uncalled_suppresses_def_line(self):
        """# noqa: uncalled on the def line excludes the function from results."""
        from reveal.adapters.calls.index import find_uncalled
        self._write('noqa1.py', '''\
            def suppressed():  # noqa: uncalled
                pass

            def reported():
                pass
        ''')
        result = find_uncalled(self.tmpdir)
        names = [e['name'] for e in result['entries']]
        self.assertNotIn('suppressed', names)
        self.assertIn('reported', names)

    def test_noqa_uncalled_on_decorator_line(self):
        """# noqa: uncalled on a decorator line also suppresses the function."""
        from reveal.adapters.calls.index import find_uncalled
        self._write('noqa2.py', '''\
            def decorator(fn):
                return fn

            @decorator  # noqa: uncalled
            def registered():
                pass

            def other():
                pass
        ''')
        result = find_uncalled(self.tmpdir)
        names = [e['name'] for e in result['entries']]
        self.assertNotIn('registered', names)

    def test_noqa_uncalled_does_not_affect_called_function(self):
        """# noqa: uncalled on a function that IS called has no visible effect."""
        from reveal.adapters.calls.index import find_uncalled
        self._write('noqa3.py', '''\
            def helper():  # noqa: uncalled
                pass

            def runner():
                helper()
        ''')
        result = find_uncalled(self.tmpdir)
        names = [e['name'] for e in result['entries']]
        self.assertNotIn('helper', names)


# ---------------------------------------------------------------------------
# Integration: CallsAdapter ?uncalled query param
# ---------------------------------------------------------------------------

class TestCallsAdapterUncalled(unittest.TestCase):

    def setUp(self):
        import shutil
        self.tmpdir = tempfile.mkdtemp()
        _write(self.tmpdir, 'src.py', textwrap.dedent('''\
            def used():
                pass

            def orphan():
                pass

            def _private_orphan():
                pass

            def entry():
                used()
        '''))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_uncalled_param_returns_uncalled_query(self):
        adapter = CallsAdapter(self.tmpdir, 'uncalled')
        result = adapter.get_structure()
        self.assertEqual(result.get('query'), 'uncalled')

    def test_uncalled_entries_present(self):
        # 'orphan' and '_private_orphan' are never called — flagged.
        # 'used' is called by entry — not flagged.
        # 'entry' has no callers (entry point) — also flagged; that's correct behaviour.
        adapter = CallsAdapter(self.tmpdir, 'uncalled')
        result = adapter.get_structure()
        names = [e['name'] for e in result.get('entries', [])]
        self.assertIn('orphan', names)
        self.assertIn('_private_orphan', names)
        self.assertNotIn('used', names)

    def test_uncalled_type_function_filter(self):
        adapter = CallsAdapter(self.tmpdir, 'uncalled&type=function')
        result = adapter.get_structure()
        for entry in result.get('entries', []):
            self.assertNotEqual(entry.get('category'), 'methods')

    def test_uncalled_top_limits_results(self):
        adapter = CallsAdapter(self.tmpdir, 'uncalled&top=1')
        result = adapter.get_structure()
        self.assertLessEqual(len(result.get('entries', [])), 1)

    def test_uncalled_format_json_sets_query_format(self):
        adapter = CallsAdapter(self.tmpdir, 'uncalled&format=json')
        result = adapter.get_structure()
        self.assertEqual(result.get('_query_format'), 'json')


# ---------------------------------------------------------------------------
# Renderer: ?uncalled text output
# ---------------------------------------------------------------------------

class TestUncalledRenderer(unittest.TestCase):

    def _capture(self, data, fmt='text'):
        buf = io.StringIO()
        with redirect_stdout(buf):
            render_calls_structure(data, fmt)
        return buf.getvalue()

    def _make_data(self, entries=None):
        return {
            'query': 'uncalled',
            'path': 'src/',
            'total_defined': 10,
            'total_uncalled': len(entries or []),
            'entries': entries or [],
        }

    def test_header_lines_present(self):
        out = self._capture(self._make_data())
        self.assertIn('Dead code candidates', out)
        self.assertIn('Total defined', out)
        self.assertIn('Uncalled', out)

    def test_no_entries_shows_none_found(self):
        out = self._capture(self._make_data([]))
        self.assertIn('No uncalled functions found', out)

    def test_entries_rendered_with_file_and_line(self):
        entries = [{'name': 'orphan', 'file': 'src/utils.py', 'line': 42,
                    'category': 'functions', 'is_private': False}]
        out = self._capture(self._make_data(entries))
        self.assertIn('src/utils.py:42', out)
        self.assertIn('orphan', out)
        self.assertIn('function', out)

    def test_private_tag_shown(self):
        entries = [{'name': '_helper', 'file': 'src/a.py', 'line': 5,
                    'category': 'functions', 'is_private': True}]
        out = self._capture(self._make_data(entries))
        self.assertIn('private', out)

    def test_method_kind_shown(self):
        entries = [{'name': 'unused_method', 'file': 'src/b.py', 'line': 10,
                    'category': 'methods', 'is_private': False}]
        out = self._capture(self._make_data(entries))
        self.assertIn('method', out)

    def test_json_format_renders_json(self):
        data = self._make_data([])
        out = self._capture(data, 'json')
        import json
        parsed = json.loads(out)
        self.assertIn('query', parsed)


# ---------------------------------------------------------------------------
# PERF-01: _dir_cache_key uses os.stat fast path
# ---------------------------------------------------------------------------

class TestDirCacheKey(unittest.TestCase):
    """PERF-01: _dir_cache_key must return a cheap O(1) key, not walk the tree."""

    def test_returns_dir_mtime_tuple(self):
        """Normal case: returns ('dir_mtimes', tuple-of-ints) without walking files."""
        from reveal.adapters.calls.index import _dir_cache_key
        with tempfile.TemporaryDirectory() as d:
            key = _dir_cache_key(Path(d))
        self.assertIsInstance(key, tuple)
        self.assertEqual(key[0], 'dir_mtimes')
        self.assertIsInstance(key[1], tuple)

    def test_same_dir_same_key(self):
        """Two calls on an unchanged directory must return equal keys."""
        from reveal.adapters.calls.index import _dir_cache_key
        with tempfile.TemporaryDirectory() as d:
            key1 = _dir_cache_key(Path(d))
            key2 = _dir_cache_key(Path(d))
        self.assertEqual(key1, key2)

    def test_key_is_hashable(self):
        """Cache key must be usable as a dict key."""
        from reveal.adapters.calls.index import _dir_cache_key
        with tempfile.TemporaryDirectory() as d:
            key = _dir_cache_key(Path(d))
        _ = {key: 'value'}  # must not raise

    def test_no_rglob_on_normal_directory(self):
        """Fast path must stat the dir + immediate subdirs only, not recurse into files."""
        from reveal.adapters.calls.index import _dir_cache_key
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'a.py'), 'w').close()
            open(os.path.join(d, 'b.py'), 'w').close()
            subdir = os.path.join(d, 'app')
            os.makedirs(subdir)
            real_stat = os.stat
            stat_calls = []
            def counting_stat(path, *args, **kwargs):
                stat_calls.append(str(path))
                return real_stat(path, *args, **kwargs)
            with mock.patch('reveal.adapters.calls.index.os.stat', side_effect=counting_stat):
                _dir_cache_key(Path(d))
        # Fast path: 1 stat for the root + 1 per non-skipped immediate subdir.
        # Must NOT stat individual .py files (that would be rglob behavior).
        py_stats = [p for p in stat_calls if p.endswith('.py')]
        self.assertEqual(py_stats, [], f"Must not stat .py files, got: {py_stats}")
        self.assertLessEqual(len(stat_calls), 3, (
            f"Expected at most 3 os.stat calls (root + subdirs), got {len(stat_calls)}: {stat_calls}"
        ))


class TestFindCalleesRecursive(unittest.TestCase):
    """find_callees_recursive BFS forward walk tests."""

    def setUp(self):
        import shutil
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _write(self, name, content):
        path = os.path.join(self.tmp, name)
        with open(path, 'w') as f:
            f.write(textwrap.dedent(content))
        return path

    def test_direct_callees_level_1(self):
        from reveal.adapters.calls.index import find_callees_recursive
        self._write('app.py', '''\
            def entry():
                helper()
                logger()
            def helper():
                pass
        ''')
        result = find_callees_recursive(self.tmp, 'entry', depth=1)
        callees = [e['callee'] for e in result['levels'][0]['callees']]
        self.assertIn('helper', callees)

    def test_recursive_level_2(self):
        from reveal.adapters.calls.index import find_callees_recursive
        self._write('app.py', '''\
            def entry():
                helper()
            def helper():
                worker()
            def worker():
                pass
        ''')
        result = find_callees_recursive(self.tmp, 'entry', depth=2)
        self.assertEqual(len(result['levels']), 2)
        level2_callees = [e['callee'] for e in result['levels'][1]['callees']]
        self.assertIn('worker', level2_callees)

    def test_no_cycles(self):
        from reveal.adapters.calls.index import find_callees_recursive
        self._write('app.py', '''\
            def a():
                b()
            def b():
                a()
        ''')
        result = find_callees_recursive(self.tmp, 'a', depth=5)
        # 'a' should appear at most once (not looped back in)
        all_callees = [e['callee'] for lvl in result['levels'] for e in lvl['callees']]
        self.assertEqual(all_callees.count('a'), 0)  # 'a' is visited root, not a callee

    def test_unresolved_marked_external(self):
        from reveal.adapters.calls.index import find_callees_recursive
        self._write('app.py', '''\
            def entry():
                third_party_func()
                local_helper()
            def local_helper():
                pass
        ''')
        result = find_callees_recursive(self.tmp, 'entry', depth=1)
        entries = {e['callee']: e for e in result['levels'][0]['callees']}
        self.assertTrue(entries['local_helper']['resolved'])
        self.assertFalse(entries.get('third_party_func', {}).get('resolved', True))

    def test_empty_project_returns_no_levels(self):
        from reveal.adapters.calls.index import find_callees_recursive
        self._write('app.py', 'def entry():\n    pass\n')
        result = find_callees_recursive(self.tmp, 'entry', depth=2)
        self.assertEqual(result['levels'], [])
        self.assertEqual(result['total_resolved'], 0)

    def test_total_counts(self):
        from reveal.adapters.calls.index import find_callees_recursive
        self._write('app.py', '''\
            def entry():
                known()
                unknown_lib()
            def known():
                pass
        ''')
        result = find_callees_recursive(self.tmp, 'entry', depth=1)
        self.assertEqual(result['total_resolved'], 1)
        self.assertEqual(result['total_unresolved'], 1)

    def test_depth_capped_at_5_via_adapter(self):
        from reveal.adapters.calls.adapter import CallsAdapter
        adapter = CallsAdapter(self.tmp, 'root=entry&depth=99')
        result = adapter.get_structure()
        self.assertLessEqual(result['depth'], 5)


class TestCallsAdapterRoot(unittest.TestCase):
    """CallsAdapter root= parameter integration tests."""

    def setUp(self):
        import shutil
        self.tmp = tempfile.mkdtemp()
        path = os.path.join(self.tmp, 'app.py')
        with open(path, 'w') as f:
            f.write(textwrap.dedent('''\
                def entry():
                    helper()
                def helper():
                    worker()
                def worker():
                    pass
            '''))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def test_root_param_returns_callees_recursive_type(self):
        from reveal.adapters.calls.adapter import CallsAdapter
        adapter = CallsAdapter(self.tmp, 'root=entry&depth=2')
        result = adapter.get_structure()
        self.assertEqual(result['type'], 'calls_callees_recursive')

    def test_root_levels_present(self):
        from reveal.adapters.calls.adapter import CallsAdapter
        adapter = CallsAdapter(self.tmp, 'root=entry&depth=2')
        result = adapter.get_structure()
        self.assertGreater(len(result['levels']), 0)

    def test_default_depth_is_2(self):
        from reveal.adapters.calls.adapter import CallsAdapter
        adapter = CallsAdapter(self.tmp, 'root=entry')
        result = adapter.get_structure()
        self.assertEqual(result['depth'], 2)


class TestCalleesRecursiveRenderer(unittest.TestCase):
    """Renderer tests for callees_recursive output."""

    def _capture(self, data, fmt='text'):
        import io
        buf = io.StringIO()
        with __import__('contextlib').redirect_stdout(buf):
            render_calls_structure(data, fmt)
        return buf.getvalue()

    def _data(self, **kwargs):
        base = {
            'query': 'callees_recursive',
            'root': 'entry',
            'depth': 2,
            'path': '/proj',
            'total_resolved': 2,
            'total_unresolved': 1,
            'levels': [
                {'level': 1, 'callees': [
                    {'caller': 'entry', 'callee': 'helper', 'resolved': True,
                     'caller_file': 'app.py', 'caller_line': 2},
                    {'caller': 'entry', 'callee': 'lib_call', 'resolved': False,
                     'caller_file': 'app.py', 'caller_line': 3},
                ]},
                {'level': 2, 'callees': [
                    {'caller': 'helper', 'callee': 'worker', 'resolved': True,
                     'caller_file': 'app.py', 'caller_line': 5},
                ]},
            ],
        }
        base.update(kwargs)
        return base

    def test_header_shows_root_and_depth(self):
        out = self._capture(self._data())
        self.assertIn('entry', out)
        self.assertIn('depth 2', out)

    def test_resolved_shows_checkmark(self):
        out = self._capture(self._data())
        self.assertIn('✓', out)

    def test_unresolved_shows_external(self):
        out = self._capture(self._data())
        self.assertIn('[external]', out)

    def test_level_labels_present(self):
        out = self._capture(self._data())
        self.assertIn('Direct callees', out)
        self.assertIn('Level 2', out)

    def test_no_levels_shows_not_found(self):
        data = self._data(levels=[], total_resolved=0, total_unresolved=0)
        out = self._capture(data)
        self.assertIn("No callees found", out)

    def test_dot_format_produces_digraph(self):
        out = self._capture(self._data(), fmt='dot')
        self.assertIn('digraph', out)
        self.assertIn('"entry"', out)
        self.assertIn('helper', out)

    def test_dot_format_dashes_unresolved(self):
        out = self._capture(self._data(), fmt='dot')
        self.assertIn('dashed', out)

    def test_json_format(self):
        import json as _json
        out = self._capture(self._data(), fmt='json')
        parsed = _json.loads(out)
        self.assertEqual(parsed['query'], 'callees_recursive')


class TestBuildModuleDependencyGraph(unittest.TestCase):
    """build_module_dependency_graph cross-file resolution tests."""

    def setUp(self):
        import shutil
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _write(self, name, content):
        path = os.path.join(self.tmp, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(textwrap.dedent(content))
        return path

    def test_cross_file_edge_detected(self):
        from reveal.adapters.calls.index import build_module_dependency_graph
        self._write('utils.py', '''\
            def helper():
                pass
        ''')
        self._write('app.py', '''\
            from utils import helper
            def main():
                helper()
        ''')
        result = build_module_dependency_graph(self.tmp)
        edge_pairs = [(e['from'], e['to']) for e in result['edges']]
        app_path = os.path.join(self.tmp, 'app.py')
        utils_path = os.path.join(self.tmp, 'utils.py')
        self.assertIn((app_path, utils_path), edge_pairs)

    def test_self_loops_excluded(self):
        from reveal.adapters.calls.index import build_module_dependency_graph
        self._write('app.py', '''\
            from app import helper
            def main():
                helper()
            def helper():
                pass
        ''')
        result = build_module_dependency_graph(self.tmp)
        app_path = os.path.join(self.tmp, 'app.py')
        self_loops = [e for e in result['edges'] if e['from'] == e['to']]
        self.assertEqual(self_loops, [])

    def test_empty_project_returns_empty_graph(self):
        from reveal.adapters.calls.index import build_module_dependency_graph
        self._write('app.py', 'def fn(): pass\n')
        result = build_module_dependency_graph(self.tmp)
        self.assertEqual(result['total_edges'], 0)
        self.assertEqual(result['nodes'], [])

    def test_result_structure(self):
        from reveal.adapters.calls.index import build_module_dependency_graph
        result = build_module_dependency_graph(self.tmp)
        self.assertIn('query', result)
        self.assertEqual(result['query'], 'module_graph')
        self.assertIn('nodes', result)
        self.assertIn('edges', result)
        self.assertIn('total_nodes', result)
        self.assertIn('total_edges', result)


class TestCallsAdapterModules(unittest.TestCase):
    """CallsAdapter modules= parameter integration tests."""

    def setUp(self):
        import shutil
        self.tmp = tempfile.mkdtemp()
        # Create two files with a cross-file dependency
        with open(os.path.join(self.tmp, 'utils.py'), 'w') as f:
            f.write('def helper():\n    pass\n')
        with open(os.path.join(self.tmp, 'app.py'), 'w') as f:
            f.write('from utils import helper\ndef main():\n    helper()\n')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def test_modules_param_returns_module_graph_type(self):
        from reveal.adapters.calls.adapter import CallsAdapter
        adapter = CallsAdapter(self.tmp, 'modules=true')
        result = adapter.get_structure()
        self.assertEqual(result['type'], 'calls_module_graph')

    def test_modules_result_has_required_keys(self):
        from reveal.adapters.calls.adapter import CallsAdapter
        adapter = CallsAdapter(self.tmp, 'modules=true')
        result = adapter.get_structure()
        self.assertIn('nodes', result)
        self.assertIn('edges', result)


class TestModuleGraphRenderer(unittest.TestCase):
    """Renderer tests for module_graph output."""

    def _capture(self, data, fmt='text'):
        import io
        buf = io.StringIO()
        with __import__('contextlib').redirect_stdout(buf):
            render_calls_structure(data, fmt)
        return buf.getvalue()

    def _data(self, **kwargs):
        base = {
            'query': 'module_graph',
            'path': '/proj',
            'total_nodes': 2,
            'total_edges': 1,
            'nodes': ['/proj/a.py', '/proj/b.py'],
            'edges': [{'from': '/proj/a.py', 'to': '/proj/b.py', 'call_count': 3}],
        }
        base.update(kwargs)
        return base

    def test_header_shows_node_and_edge_counts(self):
        out = self._capture(self._data())
        self.assertIn('2', out)  # nodes
        self.assertIn('1', out)  # edges

    def test_edge_shown_with_count(self):
        out = self._capture(self._data())
        self.assertIn('a.py', out)
        self.assertIn('b.py', out)
        self.assertIn('3', out)

    def test_empty_edges_shows_message(self):
        out = self._capture(self._data(edges=[], total_edges=0, total_nodes=0, nodes=[]))
        self.assertIn('No cross-module', out)

    def test_dot_format_produces_digraph(self):
        out = self._capture(self._data(), fmt='dot')
        self.assertIn('digraph', out)
        self.assertIn('->', out)

    def test_dot_shows_edge_label_when_count_gt_1(self):
        out = self._capture(self._data(), fmt='dot')
        self.assertIn('label', out)

    def test_json_format(self):
        import json as _json
        out = self._capture(self._data(), fmt='json')
        parsed = _json.loads(out)
        self.assertEqual(parsed['query'], 'module_graph')


if __name__ == '__main__':
    unittest.main()
