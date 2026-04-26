"""Tests for BACK-227: ast://...?show=dict-heatmap bare-dict param ranking."""
import os
import tempfile
import unittest

from reveal.adapters.ast.adapter import AstAdapter
from reveal.adapters.ast.nav_dict_heatmap import (
    collect_dict_heatmap,
    render_dict_heatmap,
    _suggest_typeddict_name,
)


def _write_py(content: str) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False)
    tmp.write(content)
    tmp.close()
    return tmp.name


class TestDictHeatmapSuggestName(unittest.TestCase):
    def test_trade_becomes_trade_state(self):
        assert _suggest_typeddict_name('trade') == 'TradeState'

    def test_item_becomes_item_state(self):
        assert _suggest_typeddict_name('item') == 'ItemState'

    def test_capitalizes(self):
        assert _suggest_typeddict_name('x') == 'XState'


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

    def test_unannotated_params_skipped(self):
        path = _write_py("def f(x): x['a']; x['b']; x['c']\n")
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
            self.assertIn('file', item)
            self.assertIn('function', item)
            self.assertIn('line', item)
            self.assertIn('param', item)
            self.assertIn('key_count', item)
            self.assertIn('keys', item)
            self.assertIn('suggested_name', item)


class TestDictHeatmapRenderer(unittest.TestCase):

    def test_render_empty(self):
        text = render_dict_heatmap([], '/some/path')
        self.assertIn('no bare-dict params', text)

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
