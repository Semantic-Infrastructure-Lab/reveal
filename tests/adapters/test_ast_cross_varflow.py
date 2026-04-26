"""Tests for BACK-220: --varflow --cross-calls cross-function variable trace."""
import os
import subprocess
import tempfile
import unittest

from reveal.analyzers.python import PythonAnalyzer
from reveal.adapters.ast.nav_cross_varflow import (
    cross_var_flow,
    render_cross_var_flow,
    _find_callouts,
    _resolve_param_name,
    _find_function_node,
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


def _cross(path: str, func_name: str, var_name: str, max_depth: int = 3):
    a = _analyzer(path)
    func_node = _find_function_node(a, func_name)
    get_text = a._get_node_text
    from_line = func_node.start_point[0] + 1
    to_line = func_node.end_point[0] + 1
    return cross_var_flow(a, func_node, var_name, from_line, to_line, get_text, max_depth)


def _cli(path: str, func: str, var: str) -> str:
    out = subprocess.run(
        ['reveal', path, func, '--varflow', var, '--cross-calls'],
        capture_output=True, text=True,
    )
    return out.stdout


# ─────────────────────────── _find_callouts ──────────────────────────────────

class TestFindCallouts(unittest.TestCase):

    def setUp(self):
        src = """\
def process(data):
    result = validate(data)
    return result

def validate(val):
    return val.strip()
"""
        self.path = _write_py(src)
        self.a = _analyzer(self.path)
        self.get_text = self.a._get_node_text

    def tearDown(self):
        os.unlink(self.path)

    def test_finds_positional_callout(self):
        func_node = _find_function_node(self.a, 'process')
        callouts = _find_callouts(func_node, 'data', 1, 3, self.get_text)
        self.assertEqual(len(callouts), 1)
        self.assertEqual(callouts[0]['callee'], 'validate')
        self.assertEqual(callouts[0]['arg_pos'], 0)

    def test_no_callout_when_var_not_passed(self):
        func_node = _find_function_node(self.a, 'process')
        callouts = _find_callouts(func_node, 'result', 1, 3, self.get_text)
        self.assertEqual(len(callouts), 0)

    def test_callout_line_recorded(self):
        func_node = _find_function_node(self.a, 'process')
        callouts = _find_callouts(func_node, 'data', 1, 3, self.get_text)
        self.assertEqual(callouts[0]['line'], 2)


class TestFindCalloutsKeyword(unittest.TestCase):

    def setUp(self):
        src = """\
def process(data):
    result = validate(val=data)
    return result

def validate(val):
    return val.strip()
"""
        self.path = _write_py(src)
        self.a = _analyzer(self.path)
        self.get_text = self.a._get_node_text

    def tearDown(self):
        os.unlink(self.path)

    def test_keyword_callout_detected(self):
        func_node = _find_function_node(self.a, 'process')
        callouts = _find_callouts(func_node, 'data', 1, 3, self.get_text)
        self.assertEqual(len(callouts), 1)
        self.assertEqual(callouts[0]['callee'], 'validate')
        self.assertEqual(callouts[0]['arg_pos'], -1)
        self.assertEqual(callouts[0]['param'], 'val')


# ─────────────────────────── cross_var_flow frames ───────────────────────────

class TestCrossVarFlowBasic(unittest.TestCase):

    def setUp(self):
        src = """\
def process(data):
    result = validate(data)
    return result

def validate(val):
    cleaned = val.strip()
    return cleaned
"""
        self.path = _write_py(src)

    def tearDown(self):
        os.unlink(self.path)

    def test_returns_two_frames(self):
        frames = _cross(self.path, 'process', 'data')
        self.assertEqual(len(frames), 2)

    def test_root_frame_depth_zero(self):
        frames = _cross(self.path, 'process', 'data')
        self.assertEqual(frames[0]['depth'], 0)
        self.assertEqual(frames[0]['function'], 'process')
        self.assertEqual(frames[0]['var'], 'data')

    def test_callee_frame_depth_one(self):
        frames = _cross(self.path, 'process', 'data')
        self.assertEqual(frames[1]['depth'], 1)
        self.assertEqual(frames[1]['function'], 'validate')
        self.assertEqual(frames[1]['var'], 'val')

    def test_callee_param_resolved(self):
        frames = _cross(self.path, 'process', 'data')
        callouts = frames[0]['callouts']
        self.assertEqual(len(callouts), 1)
        self.assertEqual(callouts[0]['param'], 'val')

    def test_callee_frame_has_events(self):
        frames = _cross(self.path, 'process', 'data')
        callee_events = frames[1]['events']
        lines = [e['line'] for e in callee_events]
        self.assertIn(6, lines)  # val.strip()


class TestCrossVarFlowNoCallee(unittest.TestCase):
    """When the var is not passed to any local function, only one frame."""

    def setUp(self):
        src = """\
def process(data):
    cleaned = data.strip()
    return cleaned
"""
        self.path = _write_py(src)

    def tearDown(self):
        os.unlink(self.path)

    def test_single_frame(self):
        frames = _cross(self.path, 'process', 'data')
        self.assertEqual(len(frames), 1)

    def test_root_events_present(self):
        frames = _cross(self.path, 'process', 'data')
        self.assertGreater(len(frames[0]['events']), 0)


class TestCrossVarFlowCalleeNotInModule(unittest.TestCase):
    """Callee defined outside the module — follows only what it can find."""

    def setUp(self):
        src = """\
def process(data):
    result = external_lib(data)
    return result
"""
        self.path = _write_py(src)

    def tearDown(self):
        os.unlink(self.path)

    def test_only_root_frame(self):
        frames = _cross(self.path, 'process', 'data')
        self.assertEqual(len(frames), 1)

    def test_callout_recorded_but_not_followed(self):
        frames = _cross(self.path, 'process', 'data')
        self.assertEqual(len(frames[0]['callouts']), 1)
        self.assertEqual(frames[0]['callouts'][0]['callee'], 'external_lib')


class TestCrossVarFlowMaxDepth(unittest.TestCase):

    def setUp(self):
        src = """\
def a(x):
    return b(x)

def b(y):
    return c(y)

def c(z):
    return z.upper()
"""
        self.path = _write_py(src)

    def tearDown(self):
        os.unlink(self.path)

    def test_depth_3_follows_chain(self):
        frames = _cross(self.path, 'a', 'x', max_depth=3)
        func_names = [f['function'] for f in frames]
        self.assertIn('a', func_names)
        self.assertIn('b', func_names)
        self.assertIn('c', func_names)

    def test_depth_1_stops_early(self):
        frames = _cross(self.path, 'a', 'x', max_depth=1)
        func_names = [f['function'] for f in frames]
        self.assertIn('a', func_names)
        self.assertIn('b', func_names)
        self.assertNotIn('c', func_names)


class TestCrossVarFlowCycleGuard(unittest.TestCase):
    """Mutual recursion must not cause infinite loops."""

    def setUp(self):
        src = """\
def ping(x):
    return pong(x)

def pong(y):
    return ping(y)
"""
        self.path = _write_py(src)

    def tearDown(self):
        os.unlink(self.path)

    def test_no_infinite_loop(self):
        frames = _cross(self.path, 'ping', 'x', max_depth=3)
        self.assertIsInstance(frames, list)
        func_names = [f['function'] for f in frames]
        self.assertEqual(func_names.count('ping'), 1)
        self.assertEqual(func_names.count('pong'), 1)


class TestCrossVarFlowKeywordArg(unittest.TestCase):

    def setUp(self):
        src = """\
def process(data):
    return validate(val=data)

def validate(val):
    return val.strip()
"""
        self.path = _write_py(src)

    def tearDown(self):
        os.unlink(self.path)

    def test_keyword_arg_followed(self):
        frames = _cross(self.path, 'process', 'data')
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[1]['function'], 'validate')
        self.assertEqual(frames[1]['var'], 'val')


# ─────────────────────────── render_cross_var_flow ───────────────────────────

class TestRenderCrossVarFlow(unittest.TestCase):

    def setUp(self):
        src = """\
def process(data):
    result = validate(data)
    return result

def validate(val):
    cleaned = val.strip()
    return cleaned
"""
        self.path = _write_py(src)

    def tearDown(self):
        os.unlink(self.path)

    def _render(self):
        a = _analyzer(self.path)
        func_node = _find_function_node(a, 'process')
        get_text = a._get_node_text
        from_line = func_node.start_point[0] + 1
        to_line = func_node.end_point[0] + 1
        frames = cross_var_flow(a, func_node, 'data', from_line, to_line, get_text)
        content_lines = a.content.splitlines()
        return render_cross_var_flow('data', frames, content_lines)

    def test_root_header_present(self):
        out = self._render()
        self.assertIn('process', out)
        self.assertIn('data', out)

    def test_callee_arrow_present(self):
        out = self._render()
        self.assertIn('↳ validate(val)', out)

    def test_callee_events_indented(self):
        out = self._render()
        lines = out.splitlines()
        callee_lines = [l for l in lines if 'val.strip' in l]
        self.assertTrue(len(callee_lines) > 0)
        # Callee lines must be indented
        self.assertTrue(callee_lines[0].startswith('  '))

    def test_empty_frames_message(self):
        out = render_cross_var_flow('x', [], [])
        self.assertIn('No frames', out)


# ─────────────────────────── CLI integration ─────────────────────────────────

class TestCrossVarFlowCLI(unittest.TestCase):

    def setUp(self):
        src = """\
def process(data):
    result = validate(data)
    return result

def validate(val):
    cleaned = val.strip()
    return cleaned
"""
        self.path = _write_py(src)

    def tearDown(self):
        os.unlink(self.path)

    def test_cli_runs_without_error(self):
        out = subprocess.run(
            ['reveal', self.path, 'process', '--varflow', 'data', '--cross-calls'],
            capture_output=True, text=True,
        )
        self.assertEqual(out.returncode, 0)

    def test_cli_root_frame_in_output(self):
        output = _cli(self.path, 'process', 'data')
        self.assertIn('process', output)
        self.assertIn('data', output)

    def test_cli_callee_in_output(self):
        output = _cli(self.path, 'process', 'data')
        self.assertIn('validate', output)

    def test_cli_plain_varflow_unaffected(self):
        """--varflow without --cross-calls still works normally."""
        out = subprocess.run(
            ['reveal', self.path, 'process', '--varflow', 'data'],
            capture_output=True, text=True,
        )
        self.assertEqual(out.returncode, 0)
        self.assertIn('data', out.stdout)
        self.assertNotIn('↳', out.stdout)


if __name__ == '__main__':
    unittest.main()
