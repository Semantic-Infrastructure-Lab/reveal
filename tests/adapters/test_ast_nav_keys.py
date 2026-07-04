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


if __name__ == '__main__':
    unittest.main()
