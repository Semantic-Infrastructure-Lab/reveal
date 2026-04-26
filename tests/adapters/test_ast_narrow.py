"""Tests for nav_narrow.py — type-narrowing path display (BACK-226)."""

import os
import subprocess
import tempfile
import unittest

from reveal.analyzers.python import PythonAnalyzer
from reveal.adapters.ast.nav_narrow import (
    collect_narrowing,
    render_narrowing,
    _extract_param_types,
    _classify_guard,
    _apply_guard,
    _block_always_exits,
    _fmt_types,
)


# ─────────────────────────── helpers ─────────────────────────────────────────

def _write_py(content: str) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False)
    tmp.write(content)
    tmp.close()
    return tmp.name


def _analyzer(path: str) -> PythonAnalyzer:
    a = PythonAnalyzer(path)
    a.get_structure()
    return a


def _find_func(analyzer: PythonAnalyzer, name: str):
    for n in analyzer.tree.root_node.children:
        if n.type == 'function_definition':
            ident = next((c for c in n.children if c.type == 'identifier'), None)
            if ident and analyzer._get_node_text(ident) == name:
                return n
    return None


def _narrow(path: str, func_name: str, var_name: str):
    a = _analyzer(path)
    func_node = _find_func(a, func_name)
    return collect_narrowing(func_node, var_name, a._get_node_text)


def _render(path: str, func_name: str, var_name: str) -> str:
    a = _analyzer(path)
    func_node = _find_func(a, func_name)
    events = collect_narrowing(func_node, var_name, a._get_node_text)
    content_lines = open(path).read().splitlines()
    return render_narrowing(var_name, events, content_lines)


def _cli(path: str, func: str, var: str) -> str:
    out = subprocess.run(
        ['reveal', path, func, '--narrow', var],
        capture_output=True, text=True,
    )
    return out.stdout


# ─────────────────────────── _extract_param_types ────────────────────────────

class TestExtractParamTypes(unittest.TestCase):

    def setUp(self):
        src = """\
from typing import Optional, Union

def f1(x: Optional[str]) -> None: pass
def f2(y: Union[str, int, None]) -> None: pass
def f3(z: str) -> None: pass
def f4(w: str | None) -> None: pass
def f5(v) -> None: pass
"""
        self.path = _write_py(src)
        self.a = _analyzer(self.path)

    def tearDown(self):
        os.unlink(self.path)

    def _types(self, func_name: str, var_name: str):
        fn = _find_func(self.a, func_name)
        return _extract_param_types(fn, var_name, self.a._get_node_text)

    def test_optional_str(self):
        self.assertEqual(self._types('f1', 'x'), frozenset({'str', 'None'}))

    def test_union_three_types(self):
        self.assertEqual(self._types('f2', 'y'), frozenset({'str', 'int', 'None'}))

    def test_plain_str(self):
        self.assertEqual(self._types('f3', 'z'), frozenset({'str'}))

    def test_pep604_union(self):
        self.assertEqual(self._types('f4', 'w'), frozenset({'str', 'None'}))

    def test_unannotated_returns_none(self):
        self.assertIsNone(self._types('f5', 'v'))

    def test_wrong_var_name_returns_none(self):
        self.assertIsNone(self._types('f1', 'missing'))


# ─────────────────────────── _classify_guard ─────────────────────────────────

class TestClassifyGuard(unittest.TestCase):

    def setUp(self):
        src = """\
def f(x: Optional[str]) -> None:
    if isinstance(x, str): pass
    if not isinstance(x, str): pass
    if x is None: pass
    if x is not None: pass
"""
        self.path = _write_py(src)
        self.a = _analyzer(self.path)

    def tearDown(self):
        os.unlink(self.path)

    def _conditions(self):
        fn = _find_func(self.a, 'f')
        body = next(c for c in fn.children if c.type == 'block')
        conds = []
        for stmt in body.children:
            if stmt.type == 'if_statement':
                skip = {'if', ':', 'block', 'elif_clause', 'else_clause', 'comment'}
                cond = next((c for c in stmt.children if c.type not in skip), None)
                conds.append(cond)
        return conds

    def test_isinstance_positive(self):
        conds = self._conditions()
        g = _classify_guard(conds[0], 'x', self.a._get_node_text)
        self.assertEqual(g, {'kind': 'isinstance', 'type': 'str', 'negated': False})

    def test_isinstance_negated(self):
        conds = self._conditions()
        g = _classify_guard(conds[1], 'x', self.a._get_node_text)
        self.assertEqual(g, {'kind': 'isinstance', 'type': 'str', 'negated': True})

    def test_is_none(self):
        conds = self._conditions()
        g = _classify_guard(conds[2], 'x', self.a._get_node_text)
        self.assertEqual(g, {'kind': 'is_none', 'negated': False})

    def test_is_not_none(self):
        conds = self._conditions()
        g = _classify_guard(conds[3], 'x', self.a._get_node_text)
        self.assertEqual(g, {'kind': 'is_none', 'negated': True})

    def test_other_var_returns_none(self):
        conds = self._conditions()
        self.assertIsNone(_classify_guard(conds[0], 'other', self.a._get_node_text))


# ─────────────────────────── _apply_guard ────────────────────────────────────

class TestApplyGuard(unittest.TestCase):

    TS = frozenset({'str', 'int', 'None'})

    def test_isinstance_positive(self):
        g = {'kind': 'isinstance', 'type': 'str', 'negated': False}
        if_t, else_t = _apply_guard(g, self.TS)
        self.assertEqual(if_t, frozenset({'str'}))
        self.assertEqual(else_t, frozenset({'int', 'None'}))

    def test_isinstance_negated(self):
        g = {'kind': 'isinstance', 'type': 'str', 'negated': True}
        if_t, else_t = _apply_guard(g, self.TS)
        self.assertEqual(if_t, frozenset({'int', 'None'}))
        self.assertEqual(else_t, frozenset({'str'}))

    def test_is_none(self):
        g = {'kind': 'is_none', 'negated': False}
        if_t, else_t = _apply_guard(g, self.TS)
        self.assertEqual(if_t, frozenset({'None'}))
        self.assertEqual(else_t, frozenset({'str', 'int'}))

    def test_is_not_none(self):
        g = {'kind': 'is_none', 'negated': True}
        if_t, else_t = _apply_guard(g, self.TS)
        self.assertEqual(if_t, frozenset({'str', 'int'}))
        self.assertEqual(else_t, frozenset({'None'}))

    def test_type_not_in_set(self):
        g = {'kind': 'isinstance', 'type': 'bytes', 'negated': False}
        if_t, else_t = _apply_guard(g, self.TS)
        self.assertEqual(if_t, frozenset())
        self.assertEqual(else_t, self.TS)


# ─────────────────────────── collect_narrowing: Optional ─────────────────────

class TestCollectNarrowingOptional(unittest.TestCase):

    def setUp(self):
        src = """\
from typing import Optional

def process(x: Optional[str]) -> None:
    if isinstance(x, str):
        use(x)
    else:
        handle_none()
"""
        self.path = _write_py(src)

    def tearDown(self):
        os.unlink(self.path)

    def test_entry_event_present(self):
        events = _narrow(self.path, 'process', 'x')
        self.assertIsNotNone(events)
        self.assertEqual(events[0]['kind'], 'ENTRY')

    def test_entry_type_set(self):
        events = _narrow(self.path, 'process', 'x')
        self.assertEqual(events[0]['type_set'], frozenset({'str', 'None'}))

    def test_if_event_emitted(self):
        events = _narrow(self.path, 'process', 'x')
        kinds = [e['kind'] for e in events]
        self.assertIn('IF', kinds)

    def test_if_type_set_is_str(self):
        events = _narrow(self.path, 'process', 'x')
        if_ev = next(e for e in events if e['kind'] == 'IF')
        self.assertEqual(if_ev['type_set'], frozenset({'str'}))

    def test_else_event_emitted(self):
        events = _narrow(self.path, 'process', 'x')
        kinds = [e['kind'] for e in events]
        self.assertIn('ELSE', kinds)

    def test_else_type_set_is_none(self):
        events = _narrow(self.path, 'process', 'x')
        else_ev = next(e for e in events if e['kind'] == 'ELSE')
        self.assertEqual(else_ev['type_set'], frozenset({'None'}))


# ─────────────────────────── early-return narrowing ──────────────────────────

class TestCollectNarrowingEarlyReturn(unittest.TestCase):

    def setUp(self):
        src = """\
from typing import Union

def guard(val: Union[str, int, None]) -> str:
    if val is None:
        raise ValueError('no val')
    if not isinstance(val, str):
        return 'not a string'
    return val.upper()
"""
        self.path = _write_py(src)

    def tearDown(self):
        os.unlink(self.path)

    def test_entry_type_set(self):
        events = _narrow(self.path, 'guard', 'val')
        self.assertEqual(events[0]['type_set'], frozenset({'str', 'int', 'None'}))

    def test_narrow_event_after_is_none_raise(self):
        events = _narrow(self.path, 'guard', 'val')
        narrow_events = [e for e in events if e['kind'] == 'NARROW']
        self.assertGreater(len(narrow_events), 0)
        first_narrow = narrow_events[0]
        self.assertNotIn('None', first_narrow['type_set'])

    def test_narrow_event_after_not_isinstance(self):
        events = _narrow(self.path, 'guard', 'val')
        narrow_events = [e for e in events if e['kind'] == 'NARROW']
        final_narrow = narrow_events[-1]
        self.assertEqual(final_narrow['type_set'], frozenset({'str'}))


# ─────────────────────────── assert narrowing ────────────────────────────────

class TestCollectNarrowingAssert(unittest.TestCase):

    def setUp(self):
        src = """\
from typing import Optional

def use_it(x: Optional[str]) -> int:
    assert isinstance(x, str)
    return len(x)
"""
        self.path = _write_py(src)

    def tearDown(self):
        os.unlink(self.path)

    def test_assert_event_emitted(self):
        events = _narrow(self.path, 'use_it', 'x')
        kinds = [e['kind'] for e in events]
        self.assertIn('ASSERT', kinds)

    def test_assert_type_set(self):
        events = _narrow(self.path, 'use_it', 'x')
        assert_ev = next(e for e in events if e['kind'] == 'ASSERT')
        self.assertEqual(assert_ev['type_set'], frozenset({'str'}))


# ─────────────────────────── no annotation ───────────────────────────────────

class TestNoAnnotation(unittest.TestCase):

    def setUp(self):
        src = """\
def unannotated(x) -> None:
    if isinstance(x, str):
        pass
"""
        self.path = _write_py(src)

    def tearDown(self):
        os.unlink(self.path)

    def test_returns_none(self):
        events = _narrow(self.path, 'unannotated', 'x')
        self.assertIsNone(events)

    def test_render_none_message(self):
        output = _render(self.path, 'unannotated', 'x')
        self.assertIn('No annotation', output)


# ─────────────────────────── elif chain ──────────────────────────────────────

class TestCollectNarrowingElif(unittest.TestCase):

    def setUp(self):
        src = """\
from typing import Union

def classify(x: Union[str, int, None]) -> str:
    if isinstance(x, str):
        return 'string'
    elif isinstance(x, int):
        return 'int'
    else:
        return 'none'
"""
        self.path = _write_py(src)

    def tearDown(self):
        os.unlink(self.path)

    def test_elif_event_emitted(self):
        events = _narrow(self.path, 'classify', 'x')
        kinds = [e['kind'] for e in events]
        self.assertIn('ELIF', kinds)

    def test_elif_type_set_excludes_str(self):
        events = _narrow(self.path, 'classify', 'x')
        elif_ev = next(e for e in events if e['kind'] == 'ELIF')
        # isinstance(x, int) on remainder after str removed → {int}
        self.assertEqual(elif_ev['type_set'], frozenset({'int'}))

    def test_else_type_set_is_none_only(self):
        events = _narrow(self.path, 'classify', 'x')
        else_ev = next(e for e in events if e['kind'] == 'ELSE')
        self.assertEqual(else_ev['type_set'], frozenset({'None'}))


# ─────────────────────────── render ──────────────────────────────────────────

class TestRenderNarrowing(unittest.TestCase):

    def setUp(self):
        src = """\
from typing import Optional

def process(x: Optional[str]) -> None:
    if isinstance(x, str):
        use(x)
    else:
        handle_none()
"""
        self.path = _write_py(src)

    def tearDown(self):
        os.unlink(self.path)

    def test_entry_line_present(self):
        output = _render(self.path, 'process', 'x')
        self.assertIn('x  →', output)

    def test_str_type_shown(self):
        output = _render(self.path, 'process', 'x')
        self.assertIn('{str}', output)

    def test_none_type_shown(self):
        output = _render(self.path, 'process', 'x')
        self.assertIn('{None}', output)

    def test_render_none_events(self):
        output = render_narrowing('x', None, [])
        self.assertIn('No annotation', output)

    def test_render_empty_events(self):
        output = render_narrowing('x', [], [])
        self.assertIn('no narrowing', output)


# ─────────────────────────── CLI ─────────────────────────────────────────────

class TestNarrowCLI(unittest.TestCase):

    def setUp(self):
        src = """\
from typing import Optional

def process(x: Optional[str]) -> None:
    if isinstance(x, str):
        use(x)
    else:
        handle_none()
"""
        self.path = _write_py(src)

    def tearDown(self):
        os.unlink(self.path)

    def test_cli_zero_exit(self):
        out = subprocess.run(
            ['reveal', self.path, 'process', '--narrow', 'x'],
            capture_output=True, text=True,
        )
        self.assertEqual(out.returncode, 0)

    def test_cli_shows_entry(self):
        output = _cli(self.path, 'process', 'x')
        self.assertIn('x  →', output)

    def test_cli_shows_if_branch(self):
        output = _cli(self.path, 'process', 'x')
        self.assertIn('{str}', output)

    def test_cli_shows_else_branch(self):
        output = _cli(self.path, 'process', 'x')
        self.assertIn('{None}', output)

    def test_cli_no_annotation_message(self):
        src = "def f(x): pass\n"
        path = _write_py(src)
        try:
            out = subprocess.run(
                ['reveal', path, 'f', '--narrow', 'x'],
                capture_output=True, text=True,
            )
            self.assertEqual(out.returncode, 0)
            self.assertIn('No annotation', out.stdout)
        finally:
            os.unlink(path)

    def test_cli_json_zero_exit(self):
        out = subprocess.run(
            ['reveal', self.path, 'process', '--narrow', 'x', '--format', 'json'],
            capture_output=True, text=True,
        )
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_cli_json_valid_json(self):
        import json
        out = subprocess.run(
            ['reveal', self.path, 'process', '--narrow', 'x', '--format', 'json'],
            capture_output=True, text=True,
        )
        data = json.loads(out.stdout)
        self.assertEqual(data['meta']['flag'], 'narrow')

    def test_cli_json_findings_structure(self):
        import json
        out = subprocess.run(
            ['reveal', self.path, 'process', '--narrow', 'x', '--format', 'json'],
            capture_output=True, text=True,
        )
        data = json.loads(out.stdout)
        self.assertIn('findings', data)
        self.assertTrue(len(data['findings']) > 0)
        first = data['findings'][0]
        self.assertIn('kind', first)
        self.assertIn('line', first)
        self.assertIn('type_set', first)


# ─────────────────────────── _fmt_types ──────────────────────────────────────

class TestFmtTypes(unittest.TestCase):

    def test_empty(self):
        self.assertEqual(_fmt_types(frozenset()), '{}')

    def test_single(self):
        self.assertEqual(_fmt_types(frozenset({'str'})), '{str}')

    def test_sorted(self):
        result = _fmt_types(frozenset({'str', 'None', 'int'}))
        self.assertEqual(result, '{None, int, str}')


if __name__ == '__main__':
    unittest.main()
