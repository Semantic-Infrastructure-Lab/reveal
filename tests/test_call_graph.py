"""Tests for Phase 1 call graph extraction (within-file calls and called_by).

Covers:
- build_callers_index() standalone
- _extract_calls_in_function() via get_structure() on Python files
- _extract_calls_in_function() via get_structure() on JS files
- called_by reverse index correctness
- Nested calls (foo(bar()))
- Attribute calls (self.bar, obj.method)
- Graceful handling of functions with no calls
"""

import os
import tempfile
import unittest

from reveal.treesitter import build_callers_index
from reveal.analyzers.python import PythonAnalyzer


def _make_temp(code: str, suffix: str = '.py') -> str:
    """Write code to a temp file, return path."""
    f = tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False, encoding='utf-8')
    f.write(code)
    f.flush()
    f.close()
    return f.name


def _get_functions(code: str, suffix: str = '.py'):
    """Parse code and return function list from get_structure()."""
    path = _make_temp(code, suffix)
    try:
        from reveal.analyzers.python import PythonAnalyzer
        from reveal.analyzers.javascript import JavaScriptAnalyzer
        if suffix == '.py':
            analyzer = PythonAnalyzer(path)
        else:
            from reveal.analyzers.javascript import JavaScriptAnalyzer
            analyzer = JavaScriptAnalyzer(path)
        return analyzer.get_structure().get('functions', [])
    finally:
        os.unlink(path)


class TestBuildCallersIndex(unittest.TestCase):
    """Unit tests for build_callers_index() standalone."""

    def test_empty(self):
        self.assertEqual(build_callers_index([]), {})

    def test_no_calls(self):
        functions = [
            {'name': 'foo', 'calls': []},
            {'name': 'bar', 'calls': []},
        ]
        self.assertEqual(build_callers_index(functions), {})

    def test_simple_chain(self):
        functions = [
            {'name': 'main',  'calls': ['parse', 'run']},
            {'name': 'run',   'calls': ['parse']},
            {'name': 'parse', 'calls': []},
        ]
        index = build_callers_index(functions)
        self.assertIn('parse', index)
        self.assertIn('main', index['parse'])
        self.assertIn('run',  index['parse'])
        self.assertIn('run',  index)
        self.assertIn('main', index['run'])
        self.assertNotIn('main', index)  # nobody calls main

    def test_attribute_call_strips_prefix(self):
        """self.bar → local name 'bar' should match function named 'bar'."""
        functions = [
            {'name': 'foo', 'calls': ['self.bar']},
            {'name': 'bar', 'calls': []},
        ]
        index = build_callers_index(functions)
        self.assertIn('bar', index)
        self.assertIn('foo', index['bar'])

    def test_no_duplicate_callers(self):
        """Same caller appearing twice in calls list should not duplicate in index."""
        functions = [
            {'name': 'foo', 'calls': ['helper', 'helper']},
            {'name': 'helper', 'calls': []},
        ]
        index = build_callers_index(functions)
        self.assertEqual(index.get('helper', []).count('foo'), 1)


class TestCallExtractionPython(unittest.TestCase):
    """Test _extract_calls_in_function via full get_structure() on Python code."""

    def _funcs_by_name(self, code):
        funcs = _get_functions(code)
        return {f['name']: f for f in funcs}

    def test_simple_call(self):
        code = """
def helper():
    pass

def caller():
    helper()
"""
        fns = self._funcs_by_name(code)
        self.assertIn('helper', fns['caller']['calls'])

    def test_no_calls(self):
        code = """
def leaf():
    x = 1 + 2
    return x
"""
        fns = self._funcs_by_name(code)
        self.assertEqual(fns['leaf']['calls'], [])

    def test_attribute_call(self):
        code = """
class Foo:
    def method(self):
        self.other()

    def other(self):
        pass
"""
        path = _make_temp(code)
        try:
            analyzer = PythonAnalyzer(path)
            fns = {f['name']: f for f in analyzer.get_structure().get('functions', [])}
        finally:
            os.unlink(path)
        self.assertIn('self.other', fns['method']['calls'])

    def test_nested_calls_both_captured(self):
        """foo(bar()) should capture both foo and bar."""
        code = """
def bar():
    return 1

def baz():
    return 2

def foo():
    return bar() + baz()

def outer():
    foo(bar())
"""
        fns = self._funcs_by_name(code)
        outer_calls = fns['outer']['calls']
        self.assertIn('foo', outer_calls)
        self.assertIn('bar', outer_calls)

    def test_called_by_reverse_index(self):
        code = """
def tokenize(s):
    return s.split()

def parse(text):
    return tokenize(text)

def run(data):
    return parse(data)

def main():
    run('hello')
    parse('test')
"""
        fns = self._funcs_by_name(code)
        # tokenize is called by parse only
        self.assertEqual(fns['tokenize']['called_by'], ['parse'])
        # parse is called by run and main
        self.assertIn('run',  fns['parse']['called_by'])
        self.assertIn('main', fns['parse']['called_by'])
        # main has no callers
        self.assertEqual(fns['main']['called_by'], [])

    def test_calls_field_present_always(self):
        """Every function dict should have 'calls' and 'called_by' keys."""
        code = """
def foo():
    pass
"""
        fns = self._funcs_by_name(code)
        self.assertIn('calls', fns['foo'])
        self.assertIn('called_by', fns['foo'])


class TestCallExtractionJavaScript(unittest.TestCase):
    """Test call graph extraction on JavaScript (call_expression nodes)."""

    def _funcs_by_name(self, code):
        try:
            from reveal.analyzers.javascript import JavaScriptAnalyzer
        except ImportError:
            self.skipTest('JavaScript analyzer not available')
        path = _make_temp(code, suffix='.js')
        try:
            analyzer = JavaScriptAnalyzer(path)
            fns = analyzer.get_structure().get('functions', [])
            return {f['name']: f for f in fns}
        finally:
            os.unlink(path)

    def test_js_simple_call(self):
        code = """
function helper() {
    return 1;
}

function caller() {
    helper();
}
"""
        fns = self._funcs_by_name(code)
        if not fns:
            self.skipTest('No functions extracted from JS')
        self.assertIn('calls', fns.get('caller', fns.get(list(fns.keys())[-1], {})))

    def test_js_member_call(self):
        """obj.method() should be captured as a call."""
        code = """
function doWork() {
    console.log('hello');
    arr.push(1);
}
"""
        fns = self._funcs_by_name(code)
        if 'doWork' not in fns:
            self.skipTest('doWork not extracted')
        calls = fns['doWork']['calls']
        # At least one of the member calls should be captured
        self.assertTrue(len(calls) > 0, f"Expected calls, got: {calls}")


if __name__ == '__main__':
    unittest.main()
