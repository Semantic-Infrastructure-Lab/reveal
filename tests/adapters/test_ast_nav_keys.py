"""Tests for BACK-439d: --keys VAR dynamic key/property access surface.

Acceptance cases from design/PROBE_DERIVED_GENERIC_NAV_2026-07-04.md:
  Python: config["x"], config.get("x"), if config['enabled']
  PHP:    $row['id'], writes, isset($row['x'])
  JS/TS:  payload.id, payload["id"], optional chaining
"""
import os
import tempfile
import unittest

from conftest import _run_reveal_direct
from reveal.analyzers.python import PythonAnalyzer
from reveal.analyzers.php import PhpAnalyzer
from reveal.analyzers.javascript import JavaScriptAnalyzer
from reveal.analyzers.rust import RustAnalyzer
from reveal.analyzers.go import GoAnalyzer
from reveal.analyzers.csharp import CSharpAnalyzer
from reveal.analyzers.lua import LuaAnalyzer
from reveal.adapters.ast.nav_keys import collect_keys, render_keys
from reveal.adapters.ast.nav_cross_varflow import _find_function_node


def _write(content: str, suffix: str) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, mode='w', delete=False)
    tmp.write(content)
    tmp.close()
    return tmp.name


def _keys(analyzer_cls, path: str, func_name: str, var_name: str):
    a = analyzer_cls(path)
    a.get_structure()
    func_node = _find_function_node(a, func_name)
    assert func_node is not None, f'{func_name} not found'
    get_text = a._get_node_text
    from_line = func_node.start_position().row + 1
    to_line = func_node.end_position().row + 1
    return collect_keys(func_node, var_name, from_line, to_line, get_text)


class TestCollectKeysPython(unittest.TestCase):

    def setUp(self):
        self.path = _write("""\
def normalize(config):
    if config['enabled']:
        x = config.get('x', None)
        config['y'] = 1
    return x
""", '.py')

    def tearDown(self):
        os.unlink(self.path)

    def _events(self):
        return _keys(PythonAnalyzer, self.path, 'normalize', 'config')

    def test_subscript_read_in_condition_is_cond(self):
        events = self._events()
        enabled = [e for e in events if e['key'] == 'enabled']
        self.assertEqual(len(enabled), 1)
        self.assertEqual(enabled[0]['kind'], 'COND')
        self.assertEqual(enabled[0]['access'], 'subscript')

    def test_dict_get_call_is_read(self):
        events = self._events()
        x = [e for e in events if e['key'] == 'x']
        self.assertEqual(len(x), 1)
        self.assertEqual(x[0]['kind'], 'READ')
        self.assertEqual(x[0]['access'], 'call')

    def test_subscript_assignment_is_write(self):
        events = self._events()
        y = [e for e in events if e['key'] == 'y']
        self.assertEqual(len(y), 1)
        self.assertEqual(y[0]['kind'], 'WRITE')
        self.assertEqual(y[0]['access'], 'subscript')

    def test_render_groups_by_key(self):
        text = render_keys('config', self._events(), 1, 5)
        self.assertIn('enabled', text)
        self.assertIn('COND', text)
        self.assertIn('WRITE', text)

    def test_render_empty(self):
        text = render_keys('missing_var', [], 1, 5)
        self.assertIn('No key access found', text)


class TestCollectKeysPhp(unittest.TestCase):

    def setUp(self):
        self.path = _write("""<?php
function f($row) {
    if (isset($row['x'])) {
        $y = $row['id'];
        $row['z'] = 1;
    }
}
""", '.php')

    def tearDown(self):
        os.unlink(self.path)

    def _events(self):
        return _keys(PhpAnalyzer, self.path, 'f', '$row')

    def test_isset_wrapped_subscript_is_cond(self):
        events = self._events()
        x = [e for e in events if e['key'] == 'x']
        self.assertEqual(len(x), 1)
        self.assertEqual(x[0]['kind'], 'COND')

    def test_subscript_read(self):
        events = self._events()
        idk = [e for e in events if e['key'] == 'id']
        self.assertEqual(len(idk), 1)
        self.assertEqual(idk[0]['kind'], 'READ')

    def test_subscript_write(self):
        events = self._events()
        z = [e for e in events if e['key'] == 'z']
        self.assertEqual(len(z), 1)
        self.assertEqual(z[0]['kind'], 'WRITE')


class TestCollectKeysJavaScript(unittest.TestCase):

    def setUp(self):
        self.path = _write("""\
function f(payload) {
  if (payload.id) {
    const x = payload["id"];
    payload.y = 1;
    const z = payload?.id;
  }
}
""", '.js')

    def tearDown(self):
        os.unlink(self.path)

    def _events(self):
        return _keys(JavaScriptAnalyzer, self.path, 'f', 'payload')

    def test_attribute_read_in_condition_is_cond(self):
        events = self._events()
        first = events[0]
        self.assertEqual(first['key'], 'id')
        self.assertEqual(first['kind'], 'COND')
        self.assertEqual(first['access'], 'attribute')

    def test_subscript_read(self):
        events = self._events()
        subscript_reads = [e for e in events if e['access'] == 'subscript' and e['key'] == 'id']
        self.assertEqual(len(subscript_reads), 1)
        self.assertEqual(subscript_reads[0]['kind'], 'READ')

    def test_attribute_write(self):
        events = self._events()
        y = [e for e in events if e['key'] == 'y']
        self.assertEqual(len(y), 1)
        self.assertEqual(y[0]['kind'], 'WRITE')

    def test_optional_chaining_still_matches(self):
        events = self._events()
        attribute_reads = [e for e in events if e['access'] == 'attribute' and e['key'] == 'id' and e['kind'] == 'READ']
        self.assertEqual(len(attribute_reads), 1)


class TestKeysCli(unittest.TestCase):
    """CLI-level: --keys through the real handle_file dispatch path."""

    def setUp(self):
        self.path = _write("""\
def normalize(config):
    if config['enabled']:
        x = config.get('x', None)
        config['y'] = 1
    return x
""", '.py')

    def tearDown(self):
        os.unlink(self.path)

    def test_text_output(self):
        out = _run_reveal_direct(self.path, 'normalize', '--keys', 'config')
        self.assertIn('enabled', out.stdout)
        self.assertIn('COND', out.stdout)

    def test_json_envelope(self):
        import json
        out = _run_reveal_direct(self.path, 'normalize', '--keys', 'config', '--format=json')
        result = json.loads(out.stdout)
        self.assertIn('meta', result)
        self.assertIn('findings', result)
        self.assertIn('warnings', result)
        self.assertEqual(result['meta']['flag'], 'keys')
        self.assertEqual(result['meta']['var'], 'config')
        for f in result['findings']:
            self.assertIn('key', f)
            self.assertIn('kind', f)
            self.assertIn('line', f)
            self.assertIn('access', f)

    def test_flat_file_range_form(self):
        php_path = _write("""<?php
function f($row) {
    if (isset($row['x'])) {
        $y = $row['id'];
        $row['z'] = 1;
    }
}
""", '.php')
        try:
            out = _run_reveal_direct(php_path, ':1-7', '--keys', '$row')
            self.assertIn('id', out.stdout)
        finally:
            os.unlink(php_path)


class TestMemberAccessNonObjectFieldNames(unittest.TestCase):
    """Regression: _member_parts() must not assume 'object' is the only
    base-field name — Rust/Go/C# each name it differently. Found by
    roaring-mist-0704's review; every case below returned zero events
    before the fix."""

    def test_rust_field_expression_uses_value_field(self):
        path = _write("""\
fn f(cfg: &Config) -> i32 {
    let x = cfg.x;
    x
}
""", '.rs')
        try:
            events = _keys(RustAnalyzer, path, 'f', 'cfg')
            self.assertEqual([e['key'] for e in events], ['x'])
        finally:
            os.unlink(path)

    def test_go_selector_expression_uses_operand_field(self):
        path = _write("""\
package main
func f(cfg Config) int {
	x := cfg.X
	return x
}
""", '.go')
        try:
            events = _keys(GoAnalyzer, path, 'f', 'cfg')
            self.assertEqual([e['key'] for e in events], ['X'])
        finally:
            os.unlink(path)

    def test_csharp_member_access_expression_uses_expression_field(self):
        path = _write("""\
class C {
    int F(Config cfg) {
        int x = cfg.X;
        return x;
    }
}
""", '.cs')
        try:
            events = _keys(CSharpAnalyzer, path, 'F', 'cfg')
            self.assertEqual([e['key'] for e in events], ['X'])
        finally:
            os.unlink(path)


class TestFlatFileNarrowFlag(unittest.TestCase):
    """Regression: --narrow was missing from file_handler.py's _FLAT_FLAGS,
    so `reveal file.py --narrow x` (no explicit function/range) silently
    fell through to show_structure instead of running the narrowing
    analysis. Found by roaring-mist-0704's review."""

    def test_narrow_with_no_element_runs_narrowing_not_structure(self):
        path = _write("""\
def f(x: int):
    if x > 0:
        x = str(x)
    return x
""", '.py')
        try:
            out = _run_reveal_direct(path, '--narrow', 'x')
        finally:
            os.unlink(path)
        self.assertNotIn('[reveal error', out.stdout)
        self.assertNotIn('Functions (', out.stdout)


class TestPythonTernaryCondition(unittest.TestCase):
    """Regression: Python's fieldless conditional_expression (ternary) must
    still flip its middle sub-expression to COND, matching if/while."""

    def test_ternary_condition_is_cond_not_read(self):
        path = _write("""\
def f(config):
    return config['a'] if config['cond'] else config['b']
""", '.py')
        try:
            events = _keys(PythonAnalyzer, path, 'f', 'config')
        finally:
            os.unlink(path)
        by_key = {e['key']: e['kind'] for e in events}
        self.assertEqual(by_key['cond'], 'COND')
        self.assertEqual(by_key['a'], 'READ')
        self.assertEqual(by_key['b'], 'READ')


class TestLuaFieldlessAssignment(unittest.TestCase):
    """BACK-456 regression: Lua's assignment_statement exposes no 'left'/
    'right' fields at all — targets are a positional 'variable_list' child,
    values an 'expression_list' child. nav_keys._walk() used to look up only
    the fielded shape and silently fell through to generic recursion,
    classifying assignment targets as READ instead of WRITE. Now shares
    nav_varflow.resolve_assignment_sides() instead of reimplementing a
    narrower, fielded-only copy."""

    def test_multi_target_assignment_is_write_not_read(self):
        path = _write("""\
function f(cfg)
  cfg.x, cfg.y = 1, 2
  return cfg.x
end
""", '.lua')
        try:
            events = _keys(LuaAnalyzer, path, 'f', 'cfg')
        finally:
            os.unlink(path)
        by_key_kind = [(e['key'], e['kind']) for e in events]
        self.assertIn(('x', 'WRITE'), by_key_kind)
        self.assertIn(('y', 'WRITE'), by_key_kind)
        self.assertIn(('x', 'READ'), by_key_kind)


if __name__ == '__main__':
    unittest.main()
