"""Tests for BACK-227: ast://...?show=dict-heatmap bare-dict param ranking."""
import os
import tempfile
import unittest

import pytest

from reveal.adapters.ast.adapter import AstAdapter
from reveal.adapters.ast.nav_dict_heatmap import render_dict_heatmap, render_dict_schemas
from reveal.analyzers._python_dict_usage import (
    collect_dict_analysis,
    collect_dict_heatmap,
    collect_dict_schemas,
    has_python_files,
    suggest_typeddict_name,
)

# BACK-1149: component-layer test -- single adapter/module in isolation, no subprocess/CLI/MCP
pytestmark = pytest.mark.component


def _write_py(content: str) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False)
    tmp.write(content)
    tmp.close()
    return tmp.name


class TestDictHeatmapSuggestName(unittest.TestCase):
    def test_trade_becomes_trade_state(self):
        assert suggest_typeddict_name('trade') == 'TradeState'

    def test_item_becomes_item_state(self):
        assert suggest_typeddict_name('item') == 'ItemState'

    def test_capitalizes(self):
        assert suggest_typeddict_name('x') == 'XState'

    def test_attribute_owner_and_underscores_stripped(self):
        assert suggest_typeddict_name('self._config') == 'ConfigState'

    def test_empty_falls_back(self):
        assert suggest_typeddict_name('') == 'ItemState'
        assert suggest_typeddict_name('_') == 'ItemState'


class TestDictHeatmapCollection(unittest.TestCase):

    def setUp(self):
        src = """\
def process(trade: dict) -> bool:
    x = trade['symbol']
    y = trade['pnl']
    z = trade['outcome']
    return True

def simple(trade: dict) -> None:
    a = trade['symbol']
"""
        self.path = _write_py(src)

    def tearDown(self):
        os.unlink(self.path)

    def test_finds_dict_params(self):
        items = collect_dict_heatmap(self.path)
        self.assertEqual(len(items), 2)

    def test_ranked_by_key_count_descending(self):
        items = collect_dict_heatmap(self.path)
        counts = [i['key_count'] for i in items]
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_keys_extracted_correctly(self):
        items = collect_dict_heatmap(self.path)
        top = items[0]
        self.assertEqual(top['key_count'], 3)
        self.assertIn('symbol', top['keys'])
        self.assertIn('pnl', top['keys'])
        self.assertIn('outcome', top['keys'])

    def test_function_name_captured(self):
        items = collect_dict_heatmap(self.path)
        names = {i['function'] for i in items}
        self.assertEqual(names, {'process', 'simple'})

    def test_suggested_name(self):
        items = collect_dict_heatmap(self.path)
        top = items[0]
        self.assertEqual(top['suggested_name'], 'TradeState')

    def test_annotation_captured(self):
        items = collect_dict_heatmap(self.path)
        for item in items:
            self.assertIn('dict', item['annotation'])


class TestDictHeatmapNoMatches(unittest.TestCase):

    def test_no_dict_params(self):
        path = _write_py("def f(x: int, y: str): pass\n")
        try:
            items = collect_dict_heatmap(path)
            self.assertEqual(items, [])
        finally:
            os.unlink(path)

    def test_unannotated_single_key_skipped(self):
        path = _write_py("def f(x): x['a']\n")
        try:
            items = collect_dict_heatmap(path)
            self.assertEqual(items, [])
        finally:
            os.unlink(path)

    def test_specifically_typed_param_skipped(self):
        path = _write_py(
            "from typing import TypedDict\n"
            "class Trade(TypedDict):\n    a: int\n    b: int\n"
            "def f(x: Trade): x['a']; x['b']\n"
        )
        try:
            items = collect_dict_heatmap(path)
            self.assertEqual(items, [])
        finally:
            os.unlink(path)

    def test_free_names_skipped(self):
        """Module-level globals read inside a function aren't the function's
        own dict -- only params, loop targets and locals count."""
        path = _write_py("CONFIG = {}\ndef f(): CONFIG['a']; CONFIG['b']; CONFIG['c']\n")
        try:
            items = collect_dict_heatmap(path)
            self.assertEqual(items, [])
        finally:
            os.unlink(path)

    def test_no_key_accesses_skipped(self):
        path = _write_py("def f(x: dict): return bool(x)\n")
        try:
            items = collect_dict_heatmap(path)
            self.assertEqual(items, [])
        finally:
            os.unlink(path)

    def test_empty_file(self):
        path = _write_py("")
        try:
            items = collect_dict_heatmap(path)
            self.assertEqual(items, [])
        finally:
            os.unlink(path)


class TestDictHeatmapAnnotationVariants(unittest.TestCase):

    def setUp(self):
        src = """\
from typing import Dict, Any

def f_bare(x: dict):
    x['a']; x['b']; x['c']

def f_typed(x: Dict[str, Any]):
    x['a']; x['b']; x['c']
"""
        self.path = _write_py(src)

    def tearDown(self):
        os.unlink(self.path)

    def test_bare_dict_found(self):
        items = collect_dict_heatmap(self.path)
        names = {i['function'] for i in items}
        self.assertIn('f_bare', names)

    def test_typed_dict_annotation_found(self):
        items = collect_dict_heatmap(self.path)
        names = {i['function'] for i in items}
        self.assertIn('f_typed', names)


def _items_for(src: str):
    path = _write_py(src)
    try:
        return collect_dict_heatmap(path)
    finally:
        os.unlink(path)


def _by_name(items):
    return {i['param']: i for i in items}


class TestDictHeatmapSources(unittest.TestCase):
    """Untyped dicts that no annotation-based check can see."""

    def test_unannotated_param(self):
        item = _by_name(_items_for("def f(x): x['a']; x['b']; x['c']\n"))['x']
        self.assertEqual(item['source'], 'unannotated_param')
        self.assertEqual(item['annotation'], '')
        self.assertEqual(item['keys'], ['a', 'b', 'c'])

    def test_loop_var_over_list_of_dicts(self):
        items = _items_for(
            "def f(structure):\n"
            "    for elem in structure['functions']:\n"
            "        print(elem['name'], elem.get('line'), elem.get('decorators', []))\n"
        )
        elem = _by_name(items)['elem']
        self.assertEqual(elem['source'], 'loop_var')
        self.assertEqual(elem['iterable'], "structure['functions']")
        self.assertEqual(elem['keys'], ['decorators', 'line', 'name'])

    def test_comprehension_target(self):
        items = _items_for("def f(rows): return [r['a'] + r.get('b', 0) for r in rows]\n")
        self.assertEqual(_by_name(items)['r']['source'], 'loop_var')

    def test_tuple_loop_target(self):
        items = _items_for("def f(d):\n    for k, v in d.items():\n        v['a']; v['b']\n")
        self.assertEqual(_by_name(items)['v']['source'], 'loop_var')

    def test_local(self):
        items = _items_for("def f():\n    cfg = load()\n    return cfg['host'], cfg['port']\n")
        self.assertEqual(_by_name(items)['cfg']['source'], 'local')

    def test_annotated_local_untyped_dict(self):
        items = _items_for("from typing import Dict\ndef f():\n    m: Dict[str, int] = {}\n    m['a']\n")
        item = _by_name(items)['m']
        self.assertEqual(item['source'], 'local')
        self.assertEqual(item['annotation'], 'Dict[str, int]')

    def test_annotated_local_specific_type_skipped(self):
        items = _items_for("def f():\n    m: Trade = get()\n    m['a']; m['b']\n")
        self.assertNotIn('m', _by_name(items))

    def test_first_binding_in_document_order_wins(self):
        items = _items_for(
            "def f(rows):\n"
            "    x = load()\n"
            "    for x in rows:\n"
            "        pass\n"
            "    x['a']; x['b']\n"
        )
        self.assertEqual(_by_name(items)['x']['source'], 'local')

    def test_optional_and_union_dict_annotations(self):
        items = _items_for(
            "from typing import Optional, Dict, Any\n"
            "def f(a: Optional[Dict[str, Any]], b: 'dict | None', c: Any):\n"
            "    a['x']; b['x']; c['x']\n"
        )
        self.assertEqual(
            {n: i['source'] for n, i in _by_name(items).items()},
            {'a': 'annotated_param', 'b': 'annotated_param', 'c': 'annotated_param'},
        )


class TestDictHeatmapContext(unittest.TestCase):
    """Tree-wide facts: key constants, dict type aliases, self attributes."""

    def _scan_dir(self, files):
        with tempfile.TemporaryDirectory() as d:
            for name, src in files.items():
                with open(os.path.join(d, name), 'w') as f:
                    f.write(src)
            return collect_dict_heatmap(d)

    def test_constant_key_resolved_across_files(self):
        items = self._scan_dir({
            'const.py': "CONF_NAME = 'name'\nCONF_HOST = 'host'\n",
            'a.py': "from const import CONF_NAME, CONF_HOST\ndef f(config):\n    config[CONF_NAME]; config.get(CONF_HOST); config['port']\n",
        })
        self.assertEqual(_by_name(items)['config']['keys'], ['host', 'name', 'port'])

    def test_unresolved_constant_kept_as_symbol(self):
        items = _items_for("from x import ATTR_ID, const\ndef f(d):\n    d[ATTR_ID]; d[const.ATTR_NAME]\n")
        self.assertEqual(_by_name(items)['d']['keys'], ['ATTR_ID', 'ATTR_NAME'])

    def test_ambiguous_constant_kept_as_symbol(self):
        items = self._scan_dir({
            'a.py': "KEY = 'a'\n",
            'b.py': "KEY = 'b'\ndef f(d): d[KEY]; d['z']\n",
        })
        self.assertEqual(_by_name(items)['d']['keys'], ['KEY', 'z'])

    def test_lowercase_name_key_ignored(self):
        self.assertEqual(_items_for("def f(d, k): d[k]; d[k]\n"), [])

    def test_dict_type_alias_across_files(self):
        items = self._scan_dir({
            'typing_.py': "from typing import Any, Optional\nConfigType = dict[str, Any]\nMaybeConfig = Optional[ConfigType]\n",
            'a.py': "def f(config: ConfigType, other: MaybeConfig):\n    config['a']; other['b']\n",
        })
        found = _by_name(items)
        self.assertEqual(found['config']['source'], 'annotated_param')
        self.assertEqual(found['other']['source'], 'annotated_param')

    def test_self_attribute(self):
        items = _items_for(
            "class C:\n"
            "    def f(self):\n"
            "        return self._config['name'], self._config.get('host')\n"
        )
        item = _by_name(items)['self._config']
        self.assertEqual(item['source'], 'attribute')
        self.assertEqual(item['keys'], ['host', 'name'])


class TestDictHeatmapKeyReads(unittest.TestCase):

    def test_get_pop_setdefault_and_membership_count(self):
        items = _items_for(
            "def f(x: dict):\n"
            "    x.get('a'); x.pop('b', None); x.setdefault('c', 1)\n"
            "    if 'd' in x: pass\n"
            "    if 'e' not in x: pass\n"
        )
        self.assertEqual(items[0]['keys'], ['a', 'b', 'c', 'd', 'e'])

    def test_access_count_counts_repeats(self):
        item = _items_for("def f(x: dict): x['a']; x['a']; x.get('a')\n")[0]
        self.assertEqual(item['key_count'], 1)
        self.assertEqual(item['access_count'], 3)

    def test_non_string_keys_ignored(self):
        self.assertEqual(_items_for("def f(x: dict): x[0]; x[i]\n"), [])

    def test_nested_function_reads_not_attributed_to_outer(self):
        items = _items_for(
            "def outer(x: dict):\n"
            "    x['a']\n"
            "    def inner(y: dict):\n"
            "        y['b']; x['c']\n"
        )
        outer = [i for i in items if i['function'] == 'outer'][0]
        self.assertEqual(outer['keys'], ['a'])
        self.assertIn('inner', {i['function'] for i in items})


class TestDictSchemas(unittest.TestCase):

    def _run(self, files):
        with tempfile.TemporaryDirectory() as d:
            for name, src in files.items():
                with open(os.path.join(d, name), 'w') as f:
                    f.write(src)
            items, typeddicts = collect_dict_analysis(d)
            return collect_dict_schemas(items, typeddicts)

    def test_same_shape_across_files_clusters(self):
        schemas = self._run({
            'a.py': "def render(elem): elem['name']; elem['line']; elem['calls']\n",
            'b.py': "def rank(e):\n    return e['name'], e['line'], e['calls'], e['complexity']\n",
            'c.py': "def other(row): row['x']; row['y']; row['z']\n",
        })
        self.assertEqual(len(schemas), 1)
        schema = schemas[0]
        self.assertEqual(schema['consumer_count'], 2)
        self.assertEqual(schema['file_count'], 2)
        self.assertEqual({k['key'] for k in schema['keys']}, {'name', 'line', 'calls', 'complexity'})

    def test_single_consumer_is_not_a_schema(self):
        schemas = self._run({'a.py': "def f(x): x['a']; x['b']; x['c']\n"})
        self.assertEqual(schemas, [])

    def test_existing_typeddict_matched_with_drift(self):
        schemas = self._run({
            'types_.py': (
                "from typing import TypedDict\n"
                "class _Base(TypedDict):\n    name: str\n"
                "class Element(_Base, total=False):\n    line: int\n    calls: list\n"
            ),
            'a.py': "def f(elem): elem['name']; elem['line']; elem['calls']; elem['line_end']\n",
            'b.py': "def g(e): e['name']; e['line']; e['calls']\n",
        })
        match = schemas[0]['typeddict_matches'][0]
        self.assertEqual(match['name'], 'Element')
        self.assertEqual(match['undeclared_keys'], ['line_end'])

    def test_non_typeddict_class_not_matched(self):
        schemas = self._run({
            'm.py': "class Element:\n    name: str\n    line: int\n    calls: list\n",
            'a.py': "def f(elem): elem['name']; elem['line']; elem['calls']\n",
            'b.py': "def g(e): e['name']; e['line']; e['calls']\n",
        })
        self.assertEqual(schemas[0]['typeddict_matches'], [])

    def test_render(self):
        schemas = self._run({
            'a.py': "def f(elem): elem['name']; elem['line']; elem['calls']\n",
            'b.py': "def g(elem): elem['name']; elem['line']; elem['calls']\n",
        })
        text = render_dict_schemas(schemas, 'proj')
        self.assertIn('ElemState', text)
        self.assertIn('2 consumers in 2 files', text)
        self.assertIn('name×2', text)

    def test_render_empty(self):
        self.assertIn('no untyped dict shape', render_dict_schemas([], 'proj'))


class TestDictHeatmapDirectoryScan(unittest.TestCase):

    def test_directory_scan(self):
        with tempfile.TemporaryDirectory() as d:
            for i in range(3):
                with open(os.path.join(d, f'f{i}.py'), 'w') as f:
                    f.write(f"def f(x: dict): x['a{i}']; x['b{i}']; x['c{i}']\n")
            items = collect_dict_heatmap(d)
            self.assertEqual(len(items), 3)


class TestDictHeatmapAdapterContract(unittest.TestCase):

    def setUp(self):
        src = """\
def f(x: dict):
    x['a']; x['b']; x['c']
"""
        self.path = _write_py(src)

    def tearDown(self):
        os.unlink(self.path)

    def test_result_type(self):
        adapter = AstAdapter(self.path, 'show=dict-heatmap')
        result = adapter.get_structure()
        self.assertEqual(result.get('type'), 'ast_dict_heatmap')

    def test_total_results(self):
        adapter = AstAdapter(self.path, 'show=dict-heatmap')
        result = adapter.get_structure()
        self.assertEqual(result.get('total_results'), len(result.get('results', [])))

    def test_result_fields(self):
        adapter = AstAdapter(self.path, 'show=dict-heatmap')
        result = adapter.get_structure()
        for item in result.get('results', []):
            for field in ('file', 'function', 'line', 'param', 'source', 'annotation',
                          'iterable', 'key_count', 'access_count', 'keys', 'suggested_name'):
                self.assertIn(field, item)

    def test_dict_schemas_mode(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ('a.py', 'b.py'):
                with open(os.path.join(d, name), 'w') as f:
                    f.write("def f(elem): elem['name']; elem['line']; elem['calls']\n")
            result = AstAdapter(d, 'show=dict-schemas').get_structure()
        self.assertEqual(result.get('type'), 'ast_dict_schemas')
        self.assertEqual(result.get('total_results'), 1)
        self.assertEqual(result['results'][0]['consumer_count'], 2)


class TestDictHeatmapNonPython(unittest.TestCase):
    """BACK-749: non-Python projects used to silently render as '0 found'
    instead of naming the unsupported language."""

    def test_has_python_files_false_for_non_python_dir(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, 'main.rb'), 'w') as f:
                f.write("def f(x); end\n")
            self.assertFalse(has_python_files(d))

    def test_has_python_files_true_when_py_present(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, 'main.rb'), 'w') as f:
                f.write("def f(x); end\n")
            with open(os.path.join(d, 'helper.py'), 'w') as f:
                f.write("def f(x): pass\n")
            self.assertTrue(has_python_files(d))

    def test_has_python_files_false_for_non_python_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'main.rb')
            with open(path, 'w') as f:
                f.write("def f(x); end\n")
            self.assertFalse(has_python_files(path))

    def test_adapter_reports_unsupported_language_for_non_python_dir(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, 'main.rb'), 'w') as f:
                f.write("def f(x)\n  x['a']\nend\n")
            adapter = AstAdapter(d, 'show=dict-heatmap')
            result = adapter.get_structure()
            self.assertEqual(result.get('total_results'), 0)
            self.assertEqual(result.get('unsupported_language'), 'Ruby')

    def test_adapter_no_unsupported_language_for_clean_python_project(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, 'main.py'), 'w') as f:
                f.write("def f(x: int) -> int: return x\n")
            adapter = AstAdapter(d, 'show=dict-heatmap')
            result = adapter.get_structure()
            self.assertEqual(result.get('total_results'), 0)
            self.assertEqual(result.get('unsupported_language'), '')


class TestDictHeatmapRenderer(unittest.TestCase):

    def test_render_empty(self):
        text = render_dict_heatmap([], '/some/path')
        self.assertIn('no untyped-dict names', text)

    def test_render_unsupported_language(self):
        text = render_dict_heatmap([], '/some/path', 'Ruby')
        self.assertIn('Ruby', text)
        self.assertNotIn('no untyped-dict names', text)

    def test_render_loop_var(self):
        items = [{
            'file': 'f.py', 'function': 'f', 'line': 1, 'param': 'elem',
            'source': 'loop_var', 'annotation': '', 'iterable': "structure['functions']",
            'key_count': 2, 'access_count': 2, 'keys': ['line', 'name'], 'suggested_name': 'ElemState',
        }]
        text = render_dict_heatmap(items, 'f.py')
        self.assertIn("for elem in structure['functions']", text)
        self.assertIn('[loop var]', text)

    def test_render_shows_function(self):
        items = [{
            'file': 'f.py', 'function': 'process', 'line': 1,
            'param': 'trade', 'annotation': 'dict', 'key_count': 3,
            'keys': ['outcome', 'pnl', 'symbol'], 'suggested_name': 'TradeState',
        }]
        text = render_dict_heatmap(items, 'f.py')
        self.assertIn('process', text)
        self.assertIn('TradeState', text)
        self.assertIn('3 keys', text)

    def test_render_shows_keys(self):
        items = [{
            'file': 'f.py', 'function': 'f', 'line': 1,
            'param': 'x', 'annotation': 'dict', 'key_count': 2,
            'keys': ['alpha', 'beta'], 'suggested_name': 'XState',
        }]
        text = render_dict_heatmap(items, 'f.py')
        self.assertIn('alpha', text)
        self.assertIn('beta', text)


if __name__ == '__main__':
    unittest.main()
