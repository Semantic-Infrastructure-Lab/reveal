"""Phase 2 call graph tests: AST adapter surface (calls=, callee_of=, show=calls).

Tests that calls/called_by propagate through create_element_dict, that the
calls= and callee_of= filters work, and that show=calls produces a graph result.
"""

import io
import os
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from typing import Dict, Any

from reveal.adapters.ast.adapter import AstAdapter
from reveal.adapters.ast.analysis import create_element_dict
from reveal.adapters.ast.queries import extract_show_param, extract_builtins_param
from reveal.adapters.ast.filtering import _matches_call_list
from reveal.rendering.adapters.ast import render_ast_structure


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_temp(code: str, suffix: str = '.py') -> str:
    f = tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False, encoding='utf-8')
    f.write(code)
    f.flush()
    f.close()
    return f.name


def _query(path: str, query_string: str) -> Dict[str, Any]:
    adapter = AstAdapter(path, query_string)
    return adapter.get_structure()


def _results_by_name(path: str, query_string: str) -> Dict[str, Dict]:
    s = _query(path, query_string)
    return {r['name']: r for r in s.get('results', [])}


# ---------------------------------------------------------------------------
# Unit: extract_show_param
# ---------------------------------------------------------------------------

class TestExtractShowParam(unittest.TestCase):

    def test_no_show(self):
        q, mode = extract_show_param('lines>50&type=function')
        self.assertEqual(q, 'lines>50&type=function')
        self.assertIsNone(mode)

    def test_show_calls(self):
        q, mode = extract_show_param('show=calls')
        self.assertEqual(q, '')
        self.assertEqual(mode, 'calls')

    def test_show_with_other_params(self):
        q, mode = extract_show_param('type=function&show=calls&lines>10')
        self.assertNotIn('show=calls', q)
        self.assertEqual(mode, 'calls')
        self.assertIn('type=function', q)
        self.assertIn('lines>10', q)

    def test_empty_string(self):
        q, mode = extract_show_param('')
        self.assertEqual(q, '')
        self.assertIsNone(mode)

    def test_none(self):
        q, mode = extract_show_param(None)
        self.assertIsNone(q)
        self.assertIsNone(mode)


# ---------------------------------------------------------------------------
# Unit: _matches_call_list
# ---------------------------------------------------------------------------

class TestMatchesCallList(unittest.TestCase):

    def test_exact_bare_name(self):
        cond = {'op': '==', 'value': 'parse'}
        self.assertTrue(_matches_call_list(['parse', 'run'], cond))

    def test_attribute_suffix_match(self):
        cond = {'op': '==', 'value': 'bar'}
        self.assertTrue(_matches_call_list(['self.bar'], cond))

    def test_no_match(self):
        cond = {'op': '==', 'value': 'baz'}
        self.assertFalse(_matches_call_list(['parse', 'run'], cond))

    def test_glob(self):
        cond = {'op': 'glob', 'value': 'self.*'}
        self.assertTrue(_matches_call_list(['self.bar'], cond))
        self.assertFalse(_matches_call_list(['parse'], cond))

    def test_empty_list(self):
        cond = {'op': '==', 'value': 'parse'}
        self.assertFalse(_matches_call_list([], cond))


# ---------------------------------------------------------------------------
# Integration: calls= and callee_of= filters
# ---------------------------------------------------------------------------

SAMPLE_CODE = """
def tokenize(s):
    return s.split()

def parse(text):
    tokens = tokenize(text)
    return tokens

def run(data):
    result = parse(data)
    return result

def main():
    run("hello")
    parse("test")
"""


class TestCallFilters(unittest.TestCase):

    def setUp(self):
        self.path = _write_temp(SAMPLE_CODE)

    def tearDown(self):
        os.unlink(self.path)

    def test_calls_filter_finds_callers(self):
        """calls=tokenize should find functions that call tokenize."""
        fns = _results_by_name(self.path, 'calls=tokenize')
        self.assertIn('parse', fns, f"Expected 'parse' in {list(fns.keys())}")
        self.assertNotIn('main', fns)
        self.assertNotIn('tokenize', fns)

    def test_calls_filter_multiple_callers(self):
        """calls=parse should find run and main (both call parse)."""
        fns = _results_by_name(self.path, 'calls=parse')
        self.assertIn('run', fns)
        self.assertIn('main', fns)
        self.assertNotIn('parse', fns)

    def test_callee_of_filter(self):
        """callee_of=main should find functions called by main."""
        fns = _results_by_name(self.path, 'callee_of=main')
        self.assertIn('run', fns)
        self.assertIn('parse', fns)
        self.assertNotIn('main', fns)
        self.assertNotIn('tokenize', fns)

    def test_no_match(self):
        """calls=nonexistent should return nothing."""
        fns = _results_by_name(self.path, 'calls=nonexistent')
        self.assertEqual(fns, {})


# ---------------------------------------------------------------------------
# Integration: calls/called_by in result elements
# ---------------------------------------------------------------------------

class TestCallFieldsPropagation(unittest.TestCase):

    def setUp(self):
        self.path = _write_temp(SAMPLE_CODE)

    def tearDown(self):
        os.unlink(self.path)

    def test_calls_field_present(self):
        fns = _results_by_name(self.path, 'type=function')
        self.assertIn('calls', fns['parse'])
        self.assertIn('tokenize', fns['parse']['calls'])

    def test_called_by_field_present(self):
        fns = _results_by_name(self.path, 'type=function')
        self.assertIn('called_by', fns['parse'])
        self.assertIn('run', fns['parse']['called_by'])
        self.assertIn('main', fns['parse']['called_by'])

    def test_leaf_function_empty_called_by(self):
        fns = _results_by_name(self.path, 'type=function')
        self.assertEqual(fns['main']['called_by'], [])


# ---------------------------------------------------------------------------
# Integration: show=calls mode
# ---------------------------------------------------------------------------

class TestShowCallsMode(unittest.TestCase):

    def setUp(self):
        self.path = _write_temp(SAMPLE_CODE)

    def tearDown(self):
        os.unlink(self.path)

    def test_show_mode_set(self):
        adapter = AstAdapter(self.path, 'show=calls')
        self.assertEqual(adapter.show_mode, 'calls')

    def test_show_mode_in_result(self):
        s = _query(self.path, 'show=calls')
        self.assertEqual(s.get('show_mode'), 'calls')

    def test_show_calls_returns_functions(self):
        """show=calls with no other filter still returns all functions."""
        s = _query(self.path, 'show=calls&type=function')
        names = {r['name'] for r in s.get('results', [])}
        self.assertIn('main', names)
        self.assertIn('parse', names)

    def test_show_calls_combined_with_filter(self):
        """show=calls + name filter narrows results normally."""
        s = _query(self.path, 'show=calls&name=parse')
        names = [r['name'] for r in s.get('results', [])]
        self.assertEqual(names, ['parse'])
        self.assertEqual(s.get('show_mode'), 'calls')


# ---------------------------------------------------------------------------
# Renderer: show=calls — imports excluded, callable elements only
# ---------------------------------------------------------------------------

def _capture(func, *args, **kwargs) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        func(*args, **kwargs)
    return buf.getvalue()


class TestShowCallsRenderer(unittest.TestCase):
    """Renderer tests for show=calls mode."""

    def _data_with(self, results, show_mode='calls'):
        return {
            'path': 'test.py',
            'query': 'none',
            'show_mode': show_mode,
            'total_files': 1,
            'total_results': len(results),
            'displayed_results': len(results),
            'results': results,
        }

    def test_imports_excluded_from_call_graph(self):
        """show=calls should not render import elements."""
        results = [
            {'category': 'imports', 'name': 'os', 'file': 't.py', 'line': 1, 'calls': [], 'called_by': []},
            {'category': 'functions', 'name': 'main', 'file': 't.py', 'line': 5, 'calls': ['helper'], 'called_by': []},
        ]
        out = _capture(render_ast_structure, self._data_with(results), 'text')
        self.assertNotIn('import os', out)
        self.assertIn('main', out)

    def test_function_calls_rendered(self):
        """Functions with calls should show the calls line."""
        results = [
            {'category': 'functions', 'name': 'process', 'file': 't.py', 'line': 3, 'calls': ['validate', 'save'], 'called_by': []},
        ]
        out = _capture(render_ast_structure, self._data_with(results), 'text')
        self.assertIn('process', out)
        self.assertIn('validate', out)
        self.assertIn('save', out)

    def test_called_by_rendered(self):
        """Functions with called_by should show the called-by line."""
        results = [
            {'category': 'functions', 'name': 'validate', 'file': 't.py', 'line': 10, 'calls': [], 'called_by': ['process']},
        ]
        out = _capture(render_ast_structure, self._data_with(results), 'text')
        self.assertIn('validate', out)
        self.assertIn('process', out)

    def test_no_callable_elements_shows_message(self):
        """show=calls with only imports shows 'No functions or methods found'."""
        results = [
            {'category': 'imports', 'name': 'os', 'file': 't.py', 'line': 1, 'calls': [], 'called_by': []},
        ]
        out = _capture(render_ast_structure, self._data_with(results), 'text')
        self.assertIn('No functions or methods found', out)

    def test_class_elements_excluded(self):
        """show=calls should not render class elements."""
        results = [
            {'category': 'classes', 'name': 'MyClass', 'file': 't.py', 'line': 1, 'calls': [], 'called_by': []},
            {'category': 'methods', 'name': '__init__', 'file': 't.py', 'line': 3, 'calls': ['super'], 'called_by': []},
        ]
        out = _capture(render_ast_structure, self._data_with(results), 'text')
        self.assertNotIn('MyClass', out)
        self.assertIn('__init__', out)


# ---------------------------------------------------------------------------
# Unit: extract_builtins_param
# ---------------------------------------------------------------------------

class TestExtractBuiltinsParam(unittest.TestCase):

    def test_no_builtins_param(self):
        q, include = extract_builtins_param('lines>50&type=function')
        self.assertEqual(q, 'lines>50&type=function')
        self.assertFalse(include)

    def test_builtins_true(self):
        q, include = extract_builtins_param('builtins=true')
        self.assertEqual(q, '')
        self.assertTrue(include)

    def test_builtins_false(self):
        q, include = extract_builtins_param('builtins=false')
        self.assertEqual(q, '')
        self.assertFalse(include)

    def test_bare_builtins_flag(self):
        q, include = extract_builtins_param('builtins')
        self.assertEqual(q, '')
        self.assertTrue(include)

    def test_builtins_with_other_params(self):
        q, include = extract_builtins_param('type=function&builtins=true&lines>10')
        self.assertNotIn('builtins', q)
        self.assertIn('type=function', q)
        self.assertIn('lines>10', q)
        self.assertTrue(include)

    def test_empty_string(self):
        q, include = extract_builtins_param('')
        self.assertEqual(q, '')
        self.assertFalse(include)

    def test_none(self):
        q, include = extract_builtins_param(None)
        self.assertIsNone(q)
        self.assertFalse(include)


# ---------------------------------------------------------------------------
# Integration: builtins filtering in ast:// adapter
# ---------------------------------------------------------------------------

class TestBuiltinsFiltering(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Write a Python file that calls both user-defined and builtin functions
        code = textwrap.dedent("""\
            def process(items):
                result = []
                for item in items:
                    result.append(validate(item))
                return result

            def validate(item):
                return len(item) > 0
        """)
        self.py_file = os.path.join(self.tmpdir, 'sample.py')
        with open(self.py_file, 'w') as f:
            f.write(code)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _get_calls_for(self, fn_name: str, query_string: str = '') -> list:
        adapter = AstAdapter(self.py_file, query_string)
        data = adapter.get_structure()
        results = data.get('results', [])
        for elem in results:
            if elem.get('name') == fn_name:
                return elem.get('calls', [])
        return []

    def test_builtins_filtered_by_default(self):
        """len/append should not appear in calls by default."""
        calls = self._get_calls_for('process')
        self.assertNotIn('append', calls)  # list method — a builtin
        self.assertNotIn('len', calls)

    def test_user_calls_preserved(self):
        """User-defined function calls should survive filtering."""
        calls = self._get_calls_for('process')
        self.assertIn('validate', calls)

    def test_builtins_shown_with_param(self):
        """?builtins=true should restore builtin calls in output."""
        calls = self._get_calls_for('validate', 'builtins=true')
        self.assertIn('len', calls)

    def test_include_builtins_false_attribute(self):
        adapter = AstAdapter(self.py_file, 'builtins=false')
        self.assertFalse(adapter.include_builtins)

    def test_include_builtins_true_attribute(self):
        adapter = AstAdapter(self.py_file, 'builtins=true')
        self.assertTrue(adapter.include_builtins)


if __name__ == '__main__':
    unittest.main()
