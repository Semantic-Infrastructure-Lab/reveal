"""Tests for reveal trace subcommand."""

import ast
import json
import os
import sys
import tempfile
import textwrap
import unittest
from argparse import Namespace
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from reveal.cli.commands.trace import (
    _bfs_depth,
    _build_trace,
    _call_name,
    _collect_function_index,
    _extract_effects,
    _relpath,
    _render_trace,
    create_trace_parser,
    run_trace,
)


def _write(directory: str, filename: str, content: str) -> str:
    path = os.path.join(directory, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(textwrap.dedent(content))
    return path


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class TestCreateTraceParser(unittest.TestCase):

    def test_parser_created(self):
        self.assertIsNotNone(create_trace_parser())

    def test_default_path_is_dot(self):
        args = create_trace_parser().parse_args(['--from', 'main'])
        self.assertEqual(args.path, '.')

    def test_root_required(self):
        with self.assertRaises(SystemExit):
            create_trace_parser().parse_args([])

    def test_root_set(self):
        args = create_trace_parser().parse_args(['--from', 'my_func'])
        self.assertEqual(args.root, 'my_func')

    def test_path_positional(self):
        args = create_trace_parser().parse_args(['src/', '--from', 'entry'])
        self.assertEqual(args.path, 'src/')

    def test_depth_default(self):
        args = create_trace_parser().parse_args(['--from', 'f'])
        self.assertEqual(args.depth, 2)

    def test_depth_custom(self):
        args = create_trace_parser().parse_args(['--from', 'f', '--depth', '4'])
        self.assertEqual(args.depth, 4)

    def test_format_json(self):
        args = create_trace_parser().parse_args(['--from', 'f', '--format', 'json'])
        self.assertEqual(args.format, 'json')

    def test_format_default_text(self):
        args = create_trace_parser().parse_args(['--from', 'f'])
        self.assertEqual(args.format, 'text')


# ---------------------------------------------------------------------------
# _call_name
# ---------------------------------------------------------------------------

class TestCallName(unittest.TestCase):

    def _parse_call(self, src: str) -> ast.expr:
        tree = ast.parse(src, mode='eval')
        return tree.body.func  # type: ignore[attr-defined]

    def test_simple_name(self):
        func = self._parse_call('foo()')
        self.assertEqual(_call_name(func), 'foo')

    def test_attribute_chain(self):
        func = self._parse_call('os.path.join()')
        self.assertEqual(_call_name(func), 'os.path.join')

    def test_method_call(self):
        func = self._parse_call('obj.method()')
        self.assertEqual(_call_name(func), 'obj.method')

    def test_non_name_returns_none(self):
        # subscript call like d['key']() has no simple name
        func = ast.parse('d["k"]()', mode='eval').body.func  # type: ignore[attr-defined]
        self.assertIsNone(_call_name(func))


# ---------------------------------------------------------------------------
# _extract_effects
# ---------------------------------------------------------------------------

class TestExtractEffects(unittest.TestCase):

    def _func_node(self, src: str) -> ast.FunctionDef:
        tree = ast.parse(textwrap.dedent(src))
        return next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef))

    def test_no_effects(self):
        node = self._func_node("""\
            def f():
                x = 1 + 1
        """)
        self.assertEqual(_extract_effects(node), [])

    def test_sys_exit_classified_hard_stop(self):
        node = self._func_node("""\
            def f():
                sys.exit(1)
        """)
        effects = _extract_effects(node)
        self.assertTrue(any('hard_stop' in e for e in effects))

    def test_file_shutil_classified(self):
        node = self._func_node("""\
            def f(src, dst):
                shutil.copy(src, dst)
        """)
        effects = _extract_effects(node)
        self.assertTrue(any('file' in e for e in effects))

    def test_logging_classified(self):
        node = self._func_node("""\
            def f():
                logging.info("hello")
        """)
        effects = _extract_effects(node)
        self.assertTrue(any('log' in e for e in effects))

    def test_deduplicated(self):
        node = self._func_node("""\
            def f():
                logging.info("a")
                logging.info("b")
        """)
        log_effects = [e for e in _extract_effects(node) if 'log' in e]
        self.assertEqual(len(log_effects), 1)

    def test_multiple_kinds(self):
        node = self._func_node("""\
            def f():
                sys.exit(0)
                shutil.copy("a", "b")
        """)
        effects = _extract_effects(node)
        kinds = {e.split(':')[0] for e in effects}
        self.assertIn('hard_stop', kinds)
        self.assertIn('file', kinds)


# ---------------------------------------------------------------------------
# _collect_function_index
# ---------------------------------------------------------------------------

class TestCollectFunctionIndex(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_simple_function_indexed(self):
        _write(self.tmpdir, 'a.py', """\
            def greet(name, greeting):
                print(greeting, name)
        """)
        index = _collect_function_index(self.tmpdir)
        self.assertIn('greet', index)
        self.assertEqual(index['greet']['params'], ['name', 'greeting'])

    def test_self_stripped_from_params(self):
        _write(self.tmpdir, 'b.py', """\
            class Foo:
                def bar(self, x):
                    pass
        """)
        index = _collect_function_index(self.tmpdir)
        self.assertIn('bar', index)
        self.assertNotIn('self', index['bar']['params'])

    def test_file_path_recorded(self):
        path = _write(self.tmpdir, 'c.py', """\
            def my_func():
                pass
        """)
        index = _collect_function_index(self.tmpdir)
        self.assertEqual(index['my_func']['file'], path)

    def test_effects_captured(self):
        _write(self.tmpdir, 'd.py', """\
            import shutil
            def writer(src, dst):
                shutil.copy(src, dst)
        """)
        index = _collect_function_index(self.tmpdir)
        self.assertIn('writer', index)
        self.assertTrue(any('file' in e for e in index['writer']['effects']))

    def test_syntax_error_file_skipped(self):
        _write(self.tmpdir, 'bad.py', "def (:\n  pass\n")
        _write(self.tmpdir, 'good.py', "def ok(): pass\n")
        index = _collect_function_index(self.tmpdir)
        self.assertIn('ok', index)


# ---------------------------------------------------------------------------
# _bfs_depth
# ---------------------------------------------------------------------------

class TestBfsDepth(unittest.TestCase):

    def _make_bfs(self):
        return {
            'levels': [
                {'level': 1, 'callees': [
                    {'caller': 'root', 'callee': 'a'},
                    {'caller': 'root', 'callee': 'b'},
                ]},
                {'level': 2, 'callees': [
                    {'caller': 'a', 'callee': 'c'},
                ]},
            ]
        }

    def test_root_is_zero(self):
        self.assertEqual(_bfs_depth('root', 'root', self._make_bfs()), 0)

    def test_level1_callee(self):
        self.assertEqual(_bfs_depth('a', 'root', self._make_bfs()), 1)

    def test_level2_callee(self):
        self.assertEqual(_bfs_depth('c', 'root', self._make_bfs()), 2)

    def test_unknown_returns_minus_one(self):
        self.assertEqual(_bfs_depth('z', 'root', self._make_bfs()), -1)


# ---------------------------------------------------------------------------
# _relpath
# ---------------------------------------------------------------------------

class TestRelpath(unittest.TestCase):

    def test_relative_path(self):
        result = _relpath('/foo/bar/baz.py', '/foo/bar')
        self.assertEqual(result, 'baz.py')

    def test_subdir_path(self):
        result = _relpath('/foo/bar/sub/f.py', '/foo/bar')
        self.assertEqual(result, os.path.join('sub', 'f.py'))


# ---------------------------------------------------------------------------
# _build_trace + _render_trace integration
# ---------------------------------------------------------------------------

class TestBuildTrace(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _make_two_file_project(self):
        _write(self.tmpdir, 'entry.py', """\
            from helper import do_work

            def main():
                do_work()
        """)
        _write(self.tmpdir, 'helper.py', """\
            import shutil
            def do_work():
                shutil.copy('a', 'b')
        """)

    def test_root_frame_present(self):
        self._make_two_file_project()
        report = _build_trace(self.tmpdir, 'main', 2)
        names = [f['name'] for f in report['frames']]
        self.assertIn('main', names)

    def test_callee_frame_present(self):
        self._make_two_file_project()
        report = _build_trace(self.tmpdir, 'main', 2)
        names = [f['name'] for f in report['frames']]
        self.assertIn('do_work', names)

    def test_root_depth_is_zero(self):
        self._make_two_file_project()
        report = _build_trace(self.tmpdir, 'main', 2)
        root_frame = next(f for f in report['frames'] if f['name'] == 'main')
        self.assertEqual(root_frame['depth'], 0)

    def test_callee_depth_is_one(self):
        self._make_two_file_project()
        report = _build_trace(self.tmpdir, 'main', 2)
        callee_frame = next(f for f in report['frames'] if f['name'] == 'do_work')
        self.assertEqual(callee_frame['depth'], 1)

    def test_report_keys(self):
        self._make_two_file_project()
        report = _build_trace(self.tmpdir, 'main', 1)
        for key in ('root', 'path', 'depth', 'frames', 'total_resolved', 'total_unresolved'):
            self.assertIn(key, report)

    def test_depth_capped_at_five_externally(self):
        """run_trace caps depth; _build_trace passes it through unchanged."""
        self._make_two_file_project()
        report = _build_trace(self.tmpdir, 'main', 1)
        self.assertEqual(report['depth'], 1)

    def test_unknown_root_produces_empty_frames(self):
        self._make_two_file_project()
        report = _build_trace(self.tmpdir, 'no_such_function', 2)
        self.assertEqual(report['frames'], [{'name': 'no_such_function',
                                              'file': '',
                                              'line': 0,
                                              'params': [],
                                              'effects': [],
                                              'calls': [],
                                              'depth': 0,
                                              'resolved': False}])

    def test_effects_populated_for_callee(self):
        self._make_two_file_project()
        report = _build_trace(self.tmpdir, 'main', 2)
        callee_frame = next(f for f in report['frames'] if f['name'] == 'do_work')
        self.assertTrue(any('file' in e for e in callee_frame['effects']))


class TestRenderTrace(unittest.TestCase):

    def _capture(self, report):
        buf = StringIO()
        with patch('sys.stdout', buf):
            _render_trace(report)
        return buf.getvalue()

    def test_header_printed(self):
        report = {
            'root': 'entry', 'path': '/proj', 'depth': 2,
            'frames': [], 'total_resolved': 0, 'total_unresolved': 0,
        }
        out = self._capture(report)
        self.assertIn('Trace: entry', out)
        self.assertIn('depth 2', out)

    def test_no_frames_message(self):
        report = {
            'root': 'ghost', 'path': '/proj', 'depth': 1,
            'frames': [], 'total_resolved': 0, 'total_unresolved': 0,
        }
        out = self._capture(report)
        self.assertIn("No functions found for 'ghost'", out)

    def test_frame_name_printed(self):
        report = {
            'root': 'foo', 'path': '/proj', 'depth': 1,
            'total_resolved': 1, 'total_unresolved': 0,
            'frames': [{
                'name': 'foo', 'file': '/proj/foo.py', 'line': 5,
                'params': ['x'], 'effects': [], 'calls': [], 'depth': 0, 'resolved': True,
            }],
        }
        out = self._capture(report)
        self.assertIn('foo', out)

    def test_params_printed(self):
        report = {
            'root': 'f', 'path': '/proj', 'depth': 1,
            'total_resolved': 1, 'total_unresolved': 0,
            'frames': [{
                'name': 'f', 'file': '', 'line': 0,
                'params': ['a', 'b'], 'effects': [], 'calls': [], 'depth': 0, 'resolved': True,
            }],
        }
        out = self._capture(report)
        self.assertIn('params:  a, b', out)

    def test_effects_printed(self):
        report = {
            'root': 'f', 'path': '/proj', 'depth': 1,
            'total_resolved': 1, 'total_unresolved': 0,
            'frames': [{
                'name': 'f', 'file': '', 'line': 0,
                'params': [], 'effects': ['file:open'], 'calls': [], 'depth': 0, 'resolved': True,
            }],
        }
        out = self._capture(report)
        self.assertIn('effects: file:open', out)

    def test_calls_printed(self):
        report = {
            'root': 'f', 'path': '/proj', 'depth': 1,
            'total_resolved': 1, 'total_unresolved': 0,
            'frames': [{
                'name': 'f', 'file': '', 'line': 0,
                'params': [], 'effects': [], 'calls': ['g', 'h'], 'depth': 0, 'resolved': True,
            }],
        }
        out = self._capture(report)
        self.assertIn('calls:   g, h', out)

    def test_external_marker(self):
        report = {
            'root': 'f', 'path': '/proj', 'depth': 1,
            'total_resolved': 0, 'total_unresolved': 1,
            'frames': [{
                'name': 'requests.get', 'file': '', 'line': 0,
                'params': [], 'effects': [], 'calls': [], 'depth': 1, 'resolved': False,
            }],
        }
        out = self._capture(report)
        self.assertIn('[external]', out)

    def test_depth_indentation(self):
        report = {
            'root': 'f', 'path': '/proj', 'depth': 2,
            'total_resolved': 1, 'total_unresolved': 0,
            'frames': [
                {'name': 'f', 'file': '', 'line': 0, 'params': [], 'effects': [],
                 'calls': ['g'], 'depth': 0, 'resolved': True},
                {'name': 'g', 'file': '', 'line': 0, 'params': [], 'effects': [],
                 'calls': [], 'depth': 1, 'resolved': True},
            ],
        }
        out = self._capture(report)
        lines = out.splitlines()
        f_line = next(l for l in lines if l.startswith('f'))
        g_line = next(l for l in lines if l.startswith('  g'))
        self.assertTrue(f_line.startswith('f'))
        self.assertTrue(g_line.startswith('  g'))


# ---------------------------------------------------------------------------
# run_trace
# ---------------------------------------------------------------------------

class TestRunTrace(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _make_project(self):
        _write(self.tmpdir, 'app.py', """\
            def start():
                do_thing()

            def do_thing():
                pass
        """)

    def test_invalid_path_exits(self):
        args = Namespace(path='/no/such/path', root='main', depth=2, format='text')
        with self.assertRaises(SystemExit):
            run_trace(args)

    def test_text_output_produced(self):
        self._make_project()
        args = Namespace(path=self.tmpdir, root='start', depth=2, format='text')
        buf = StringIO()
        with patch('sys.stdout', buf):
            run_trace(args)
        out = buf.getvalue()
        self.assertIn('Trace: start', out)

    def test_json_output_valid(self):
        self._make_project()
        args = Namespace(path=self.tmpdir, root='start', depth=1, format='json')
        buf = StringIO()
        with patch('sys.stdout', buf):
            run_trace(args)
        data = json.loads(buf.getvalue())
        self.assertEqual(data['root'], 'start')
        self.assertIn('frames', data)

    def test_depth_capped_at_five(self):
        self._make_project()
        args = Namespace(path=self.tmpdir, root='start', depth=99, format='json')
        buf = StringIO()
        with patch('sys.stdout', buf):
            run_trace(args)
        data = json.loads(buf.getvalue())
        self.assertLessEqual(data['depth'], 5)

    def test_depth_floored_at_one(self):
        self._make_project()
        args = Namespace(path=self.tmpdir, root='start', depth=0, format='json')
        buf = StringIO()
        with patch('sys.stdout', buf):
            run_trace(args)
        data = json.loads(buf.getvalue())
        self.assertGreaterEqual(data['depth'], 1)

    def test_unknown_from_exits_nonzero(self):
        self._make_project()
        args = Namespace(path=self.tmpdir, root='nonexistent_func', depth=2, format='text')
        with self.assertRaises(SystemExit) as ctx:
            run_trace(args)
        self.assertNotEqual(ctx.exception.code, 0)

    def test_unknown_from_prints_helpful_message(self):
        self._make_project()
        args = Namespace(path=self.tmpdir, root='nonexistent_func', depth=2, format='text')
        buf = StringIO()
        with patch('sys.stderr', buf):
            with self.assertRaises(SystemExit):
                run_trace(args)
        err = buf.getvalue()
        self.assertIn('nonexistent_func', err)
        self.assertIn('not found', err)

    def test_known_function_does_not_exit(self):
        self._make_project()
        args = Namespace(path=self.tmpdir, root='start', depth=2, format='text')
        buf = StringIO()
        with patch('sys.stdout', buf):
            run_trace(args)
        self.assertIn('Trace:', buf.getvalue())


if __name__ == '__main__':
    unittest.main()
