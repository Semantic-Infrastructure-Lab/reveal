"""Tests for BACK-225: ast://...?reveal_type=<var> type evidence query."""
import os
import tempfile
import unittest

from reveal.adapters.ast.adapter import AstAdapter
from reveal.adapters.ast.nav_reveal_type import (
    collect_type_evidence,
    render_type_evidence,
)


# ─────────────────────────── helpers ─────────────────────────────────────────

def _write_py(content: str) -> str:
    """Write content to a temp .py file and return path."""
    tmp = tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False)
    tmp.write(content)
    tmp.close()
    return tmp.name


def _evidence(path: str, var: str):
    return collect_type_evidence(path, var)


def _evs_by_kind(evs, kind):
    return [e for e in evs if e['kind'] == kind]


# ─────────────────────────── query extraction ────────────────────────────────

class TestRevealTypeQueryExtraction(unittest.TestCase):
    """reveal_type= is extracted before the filter pipeline."""

    def test_reveal_type_extracted(self):
        adapter = AstAdapter('/tmp', 'reveal_type=trade')
        self.assertEqual(adapter.reveal_type_var, 'trade')
        self.assertEqual(adapter.query, {})

    def test_no_reveal_type_is_none(self):
        adapter = AstAdapter('/tmp', 'lines>10')
        self.assertIsNone(adapter.reveal_type_var)

    def test_reveal_type_combined_with_other_params(self):
        adapter = AstAdapter('/tmp', 'reveal_type=result&limit=20')
        self.assertEqual(adapter.reveal_type_var, 'result')


# ─────────────────────────── parameter evidence ──────────────────────────────

class TestRevealTypeParams(unittest.TestCase):

    def setUp(self):
        src = """\
def process(trade: dict) -> bool:
    pass

def monitor(trade: dict, ctx: str) -> None:
    pass

def bare(trade) -> None:
    pass
"""
        self.path = _write_py(src)

    def tearDown(self):
        os.unlink(self.path)

    def test_annotated_param_found(self):
        evs = _evs_by_kind(_evidence(self.path, 'trade'), 'param')
        self.assertEqual(len(evs), 3)

    def test_annotation_extracted(self):
        evs = _evs_by_kind(_evidence(self.path, 'trade'), 'param')
        annotated = [e for e in evs if e['annotation'] == 'dict']
        self.assertEqual(len(annotated), 2)

    def test_bare_param_no_annotation(self):
        evs = _evs_by_kind(_evidence(self.path, 'trade'), 'param')
        bare = [e for e in evs if e['function'] == 'bare']
        self.assertEqual(len(bare), 1)
        self.assertEqual(bare[0]['annotation'], '')

    def test_function_name_captured(self):
        evs = _evs_by_kind(_evidence(self.path, 'trade'), 'param')
        names = {e['function'] for e in evs}
        self.assertEqual(names, {'process', 'monitor', 'bare'})

    def test_correct_line_numbers(self):
        evs = {e['function']: e['line'] for e in _evs_by_kind(_evidence(self.path, 'trade'), 'param')}
        self.assertEqual(evs['process'], 1)
        self.assertEqual(evs['monitor'], 4)
        self.assertEqual(evs['bare'], 7)


class TestRevealTypeComplexAnnotations(unittest.TestCase):

    def setUp(self):
        src = """\
from typing import Dict, List, Optional

def func(
    trade: Dict[str, int],
    items: List[str],
    maybe: Optional[dict] = None,
) -> None:
    pass
"""
        self.path = _write_py(src)

    def tearDown(self):
        os.unlink(self.path)

    def test_generic_annotation_extracted(self):
        evs = _evs_by_kind(_evidence(self.path, 'trade'), 'param')
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]['annotation'], 'Dict[str, int]')

    def test_optional_annotation_extracted(self):
        evs = _evs_by_kind(_evidence(self.path, 'maybe'), 'param')
        self.assertEqual(len(evs), 1)
        self.assertIn('Optional', evs[0]['annotation'])


# ─────────────────────────── assignment evidence ─────────────────────────────

class TestRevealTypeAssignments(unittest.TestCase):

    def setUp(self):
        src = """\
def make():
    trade = {}
    trade = {'symbol': 'ES', 'pnl': 0.0}
    trade = get_trade(order_id)
    trade = other_var
    result: dict = trade
"""
        self.path = _write_py(src)

    def tearDown(self):
        os.unlink(self.path)

    def test_assignment_count(self):
        evs = _evs_by_kind(_evidence(self.path, 'trade'), 'assign')
        self.assertEqual(len(evs), 4)  # trade = {}, trade = {...}, trade = call(), trade = other_var

    def test_empty_dict_literal(self):
        evs = _evs_by_kind(_evidence(self.path, 'trade'), 'assign')
        shapes = [e['shape'] for e in evs]
        self.assertIn('dict literal {}', shapes)

    def test_keyed_dict_literal(self):
        evs = _evs_by_kind(_evidence(self.path, 'trade'), 'assign')
        shapes = [e['shape'] for e in evs]
        self.assertTrue(any('symbol' in s and 'pnl' in s for s in shapes))

    def test_call_return_shape(self):
        evs = _evs_by_kind(_evidence(self.path, 'trade'), 'assign')
        shapes = [e['shape'] for e in evs]
        self.assertIn('return of get_trade()', shapes)

    def test_inline_annotation_captured(self):
        evs = _evs_by_kind(_evidence(self.path, 'result'), 'assign')
        self.assertEqual(len(evs), 1)
        self.assertIn('dict', evs[0]['annotation'])


class TestRevealTypeModuleLevel(unittest.TestCase):

    def setUp(self):
        src = """\
config = {'debug': True, 'host': 'localhost'}

def use_config():
    pass
"""
        self.path = _write_py(src)

    def tearDown(self):
        os.unlink(self.path)

    def test_module_level_assignment_found(self):
        evs = _evidence(self.path, 'config')
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]['kind'], 'assign')
        self.assertEqual(evs[0]['function'], '')

    def test_module_level_dict_keys(self):
        evs = _evidence(self.path, 'config')
        self.assertIn('debug', evs[0]['shape'])
        self.assertIn('host', evs[0]['shape'])


# ─────────────────────────── for-loop evidence ───────────────────────────────

class TestRevealTypeForLoop(unittest.TestCase):

    def setUp(self):
        src = """\
def process_all(trades):
    for trade in trades:
        pass

    for trade in get_trades():
        pass
"""
        self.path = _write_py(src)

    def tearDown(self):
        os.unlink(self.path)

    def test_for_loop_count(self):
        evs = _evs_by_kind(_evidence(self.path, 'trade'), 'for')
        self.assertEqual(len(evs), 2)

    def test_for_iterable_identifier_shape(self):
        evs = _evs_by_kind(_evidence(self.path, 'trade'), 'for')
        shapes = [e['shape'] for e in evs]
        self.assertTrue(any('trades' in s for s in shapes))

    def test_for_call_iterable_shape(self):
        evs = _evs_by_kind(_evidence(self.path, 'trade'), 'for')
        shapes = [e['shape'] for e in evs]
        self.assertTrue(any('get_trades()' in s for s in shapes))


# ─────────────────────────── adapter result contract ─────────────────────────

class TestRevealTypeAdapterContract(unittest.TestCase):

    def setUp(self):
        src = """\
def f(x: int) -> None:
    x = 10
"""
        self.path = _write_py(src)

    def tearDown(self):
        os.unlink(self.path)

    def test_result_type(self):
        adapter = AstAdapter(self.path, 'reveal_type=x')
        result = adapter.get_structure()
        self.assertEqual(result.get('type'), 'ast_reveal_type')

    def test_var_name_in_result(self):
        adapter = AstAdapter(self.path, 'reveal_type=x')
        result = adapter.get_structure()
        self.assertEqual(result.get('var_name'), 'x')

    def test_total_results(self):
        adapter = AstAdapter(self.path, 'reveal_type=x')
        result = adapter.get_structure()
        self.assertEqual(result.get('total_results'), len(result.get('results', [])))

    def test_results_have_required_fields(self):
        adapter = AstAdapter(self.path, 'reveal_type=x')
        result = adapter.get_structure()
        for ev in result.get('results', []):
            self.assertIn('file', ev)
            self.assertIn('function', ev)
            self.assertIn('line', ev)
            self.assertIn('kind', ev)
            self.assertIn('annotation', ev)
            self.assertIn('shape', ev)


# ─────────────────────────── renderer ────────────────────────────────────────

class TestRevealTypeRenderer(unittest.TestCase):

    def test_render_no_results(self):
        text = render_type_evidence('x', [], '/some/path')
        self.assertIn('no occurrences', text)
        self.assertIn('x', text)

    def test_render_param_annotation(self):
        evs = [{'file': 'f.py', 'function': 'go', 'func_line': 1, 'line': 1,
                'kind': 'param', 'annotation': 'dict', 'shape': ''}]
        text = render_type_evidence('trade', evs, 'f.py')
        self.assertIn('PARAM', text)
        self.assertIn('annotated: dict', text)

    def test_render_assign_dict_shape(self):
        evs = [{'file': 'f.py', 'function': 'go', 'func_line': 1, 'line': 5,
                'kind': 'assign', 'annotation': '', 'shape': 'dict literal {symbol, pnl}'}]
        text = render_type_evidence('trade', evs, 'f.py')
        self.assertIn('ASSIGN', text)
        self.assertIn('dict literal {symbol, pnl}', text)

    def test_render_for_loop(self):
        evs = [{'file': 'f.py', 'function': 'main', 'func_line': 1, 'line': 3,
                'kind': 'for', 'annotation': '', 'shape': 'item from from trades'}]
        text = render_type_evidence('trade', evs, 'f.py')
        self.assertIn('FOR', text)

    def test_render_unannotated_param(self):
        evs = [{'file': 'f.py', 'function': 'go', 'func_line': 1, 'line': 1,
                'kind': 'param', 'annotation': '', 'shape': ''}]
        text = render_type_evidence('trade', evs, 'f.py')
        self.assertIn('unannotated', text)


# ─────────────────────────── edge cases ──────────────────────────────────────

class TestRevealTypeEdgeCases(unittest.TestCase):

    def test_no_matches_returns_empty(self):
        path = _write_py("def f(x: int): pass\n")
        try:
            evs = _evidence(path, 'nonexistent_var_xyz')
            self.assertEqual(evs, [])
        finally:
            os.unlink(path)

    def test_empty_file_returns_empty(self):
        path = _write_py("")
        try:
            evs = _evidence(path, 'trade')
            self.assertEqual(evs, [])
        finally:
            os.unlink(path)

    def test_nested_function_uses_innermost_name(self):
        src = """\
def outer():
    def inner(trade: dict):
        pass
"""
        path = _write_py(src)
        try:
            evs = _evidence(path, 'trade')
            self.assertEqual(len(evs), 1)
            self.assertEqual(evs[0]['function'], 'inner')
        finally:
            os.unlink(path)

    def test_directory_scan(self):
        """reveal_type works on a directory, scanning all .py files."""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            for i in range(3):
                with open(os.path.join(d, f'f{i}.py'), 'w') as f:
                    f.write(f"def func(trade: dict): pass\n")
            evs = _evidence(d, 'trade')
            self.assertEqual(len(evs), 3)


if __name__ == '__main__':
    unittest.main()
