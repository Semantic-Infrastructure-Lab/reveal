"""Tests for reveal hotspots subcommand."""

import json
import sys
import unittest
from argparse import Namespace
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from reveal.cli.commands.hotspots import (
    _render_file_hotspots,
    _render_function_hotspots,
    _render_report,
    _render_summary,
    _run_file_hotspots,
    _run_function_hotspots,
    create_hotspots_parser,
    run_hotspots,
)


def _args(**kwargs):
    defaults = {
        'path': '.',
        'top': 10,
        'min_complexity': 10,
        'functions_only': False,
        'files_only': False,
        'format': 'text',
        'verbose': False,
    }
    defaults.update(kwargs)
    return Namespace(**defaults)


def _file_hotspot(name, quality, score=5, issues=None, lines=100):
    return {
        'file': name,
        'quality_score': quality,
        'hotspot_score': score,
        'issues': issues or [],
        'details': {'lines': lines},
    }


def _fn_hotspot(name, complexity, file='mod.py', line=10, line_count=20):
    return {
        'name': name,
        'complexity': complexity,
        'file': file,
        'line': line,
        'line_count': line_count,
    }


class TestCreateHotspotsParser(unittest.TestCase):
    """Parser smoke tests."""

    def test_parser_returns_parser(self):
        parser = create_hotspots_parser()
        self.assertIsNotNone(parser)

    def test_defaults(self):
        parser = create_hotspots_parser()
        args = parser.parse_args([])
        self.assertEqual(args.path, '.')
        self.assertEqual(args.top, 10)
        self.assertEqual(args.min_complexity, 10)
        self.assertFalse(args.functions_only)
        self.assertFalse(args.files_only)

    def test_path_positional(self):
        parser = create_hotspots_parser()
        args = parser.parse_args(['./src'])
        self.assertEqual(args.path, './src')

    def test_top_flag(self):
        parser = create_hotspots_parser()
        args = parser.parse_args(['--top', '20'])
        self.assertEqual(args.top, 20)

    def test_min_complexity_flag(self):
        parser = create_hotspots_parser()
        args = parser.parse_args(['--min-complexity', '15'])
        self.assertEqual(args.min_complexity, 15)

    def test_functions_only_flag(self):
        parser = create_hotspots_parser()
        args = parser.parse_args(['--functions-only'])
        self.assertTrue(args.functions_only)

    def test_files_only_flag(self):
        parser = create_hotspots_parser()
        args = parser.parse_args(['--files-only'])
        self.assertTrue(args.files_only)


class TestRunFileHotspots(unittest.TestCase):
    """_run_file_hotspots: subprocess mocked."""

    @patch('reveal.cli.commands.hotspots.subprocess.run')
    def test_returns_hotspots_list(self, mock_run):
        data = {'hotspots': [_file_hotspot('a.py', 60), _file_hotspot('b.py', 75)]}
        mock_run.return_value = MagicMock(stdout=json.dumps(data), returncode=0)
        result = _run_file_hotspots(Path('/tmp'), top=10)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['file'], 'a.py')

    @patch('reveal.cli.commands.hotspots.subprocess.run')
    def test_respects_top_limit(self, mock_run):
        data = {'hotspots': [_file_hotspot(f'f{i}.py', 50) for i in range(20)]}
        mock_run.return_value = MagicMock(stdout=json.dumps(data), returncode=0)
        result = _run_file_hotspots(Path('/tmp'), top=5)
        self.assertEqual(len(result), 5)

    @patch('reveal.cli.commands.hotspots.subprocess.run')
    def test_empty_stdout_returns_empty(self, mock_run):
        mock_run.return_value = MagicMock(stdout='', returncode=0)
        result = _run_file_hotspots(Path('/tmp'), top=10)
        self.assertEqual(result, [])

    @patch('reveal.cli.commands.hotspots.subprocess.run')
    def test_missing_hotspots_key_returns_empty(self, mock_run):
        mock_run.return_value = MagicMock(stdout=json.dumps({'other': []}), returncode=0)
        result = _run_file_hotspots(Path('/tmp'), top=10)
        self.assertEqual(result, [])

    @patch('reveal.cli.commands.hotspots.subprocess.run', side_effect=Exception("boom"))
    def test_exception_returns_empty(self, _mock):
        result = _run_file_hotspots(Path('/tmp'), top=10)
        self.assertEqual(result, [])


class TestRunFunctionHotspots(unittest.TestCase):
    """_run_function_hotspots: subprocess mocked."""

    @patch('reveal.cli.commands.hotspots.subprocess.run')
    def test_returns_results_list(self, mock_run):
        data = {'results': [_fn_hotspot('foo', 15), _fn_hotspot('bar', 12)]}
        mock_run.return_value = MagicMock(stdout=json.dumps(data), returncode=0)
        result = _run_function_hotspots(Path('/tmp'), min_complexity=10, top=10)
        self.assertEqual(len(result), 2)

    @patch('reveal.cli.commands.hotspots.subprocess.run')
    def test_falls_back_to_elements_key(self, mock_run):
        data = {'elements': [_fn_hotspot('baz', 11)]}
        mock_run.return_value = MagicMock(stdout=json.dumps(data), returncode=0)
        result = _run_function_hotspots(Path('/tmp'), min_complexity=10, top=10)
        self.assertEqual(len(result), 1)

    @patch('reveal.cli.commands.hotspots.subprocess.run')
    def test_respects_top_limit(self, mock_run):
        data = {'results': [_fn_hotspot(f'fn{i}', 10 + i) for i in range(15)]}
        mock_run.return_value = MagicMock(stdout=json.dumps(data), returncode=0)
        result = _run_function_hotspots(Path('/tmp'), min_complexity=10, top=5)
        self.assertEqual(len(result), 5)

    @patch('reveal.cli.commands.hotspots.subprocess.run')
    def test_empty_stdout_returns_empty(self, mock_run):
        mock_run.return_value = MagicMock(stdout='', returncode=0)
        result = _run_function_hotspots(Path('/tmp'), min_complexity=10, top=10)
        self.assertEqual(result, [])

    @patch('reveal.cli.commands.hotspots.subprocess.run', side_effect=Exception("oops"))
    def test_exception_returns_empty(self, _mock):
        result = _run_function_hotspots(Path('/tmp'), min_complexity=10, top=10)
        self.assertEqual(result, [])


class TestRenderFileHotspots(unittest.TestCase):
    """_render_file_hotspots output tests."""

    def _capture(self, hotspots, top=10):
        buf = StringIO()
        with patch('sys.stdout', buf):
            _render_file_hotspots(hotspots, top)
        return buf.getvalue()

    def test_empty_produces_no_output(self):
        self.assertEqual(self._capture([]), '')

    def test_critical_quality_shows_x_icon(self):
        out = self._capture([_file_hotspot('bad.py', 60)])
        self.assertIn('❌', out)
        self.assertIn('bad.py', out)

    def test_warning_quality_shows_warning_icon(self):
        out = self._capture([_file_hotspot('warn.py', 80)])
        self.assertIn('⚠️', out)

    def test_ok_quality_shows_bulb_icon(self):
        out = self._capture([_file_hotspot('ok.py', 90)])
        self.assertIn('💡', out)

    def test_shows_quality_score(self):
        out = self._capture([_file_hotspot('f.py', 72)])
        self.assertIn('72', out)

    def test_shows_suggest_reveal_command(self):
        out = self._capture([_file_hotspot('mymod.py', 80)])
        self.assertIn('reveal mymod.py', out)

    def test_shows_issues(self):
        out = self._capture([_file_hotspot('f.py', 80, issues=['complexity', 'length'])])
        self.assertIn('complexity', out)
        self.assertIn('length', out)

    def test_missing_quality_score_no_crash(self):
        h = {'file': 'x.py', 'hotspot_score': 3, 'issues': [], 'details': {}}
        out = self._capture([h])
        self.assertIn('x.py', out)


class TestRenderFunctionHotspots(unittest.TestCase):
    """_render_function_hotspots output tests."""

    def _capture(self, fns):
        buf = StringIO()
        with patch('sys.stdout', buf):
            _render_function_hotspots(fns)
        return buf.getvalue()

    def test_empty_produces_no_output(self):
        self.assertEqual(self._capture([]), '')

    def test_critical_complexity_shows_x_icon(self):
        out = self._capture([_fn_hotspot('big_fn', 21)])
        self.assertIn('❌', out)

    def test_high_complexity_shows_warning(self):
        out = self._capture([_fn_hotspot('mid_fn', 17)])
        self.assertIn('⚠️', out)

    def test_moderate_complexity_shows_bulb(self):
        out = self._capture([_fn_hotspot('ok_fn', 12)])
        self.assertIn('💡', out)

    def test_shows_function_name(self):
        out = self._capture([_fn_hotspot('calculate_risk', 11)])
        self.assertIn('calculate_risk', out)

    def test_shows_complexity(self):
        out = self._capture([_fn_hotspot('fn', 14)])
        self.assertIn('14', out)


class TestRenderSummary(unittest.TestCase):
    """_render_summary output tests."""

    def _capture(self, file_hotspots, fn_hotspots):
        buf = StringIO()
        with patch('sys.stdout', buf):
            _render_summary(file_hotspots, fn_hotspots)
        return buf.getvalue()

    def test_critical_files_mention_in_summary(self):
        out = self._capture([_file_hotspot('f.py', 60)], [])
        self.assertIn('critical', out)
        self.assertIn('❌', out)

    def test_critical_functions_mention_in_summary(self):
        out = self._capture([], [_fn_hotspot('fn', 25)])
        self.assertIn('critical', out)
        self.assertIn('❌', out)

    def test_no_criticals_shows_warning_summary(self):
        out = self._capture([_file_hotspot('f.py', 80)], [_fn_hotspot('fn', 12)])
        self.assertIn('⚠️', out)
        self.assertNotIn('❌', out)


class TestRenderReport(unittest.TestCase):
    """_render_report integration (text mode)."""

    def _capture(self, report, top=10):
        buf = StringIO()
        with patch('sys.stdout', buf):
            _render_report(report, top)
        return buf.getvalue()

    def test_no_hotspots_shows_clean_message(self):
        report = {'path': '/tmp', 'file_hotspots': [], 'function_hotspots': []}
        out = self._capture(report)
        self.assertIn('No hotspots', out)

    def test_shows_path(self):
        report = {'path': '/myproject', 'file_hotspots': [], 'function_hotspots': []}
        out = self._capture(report)
        self.assertIn('/myproject', out)

    def test_includes_file_and_function_sections(self):
        report = {
            'path': '/tmp',
            'file_hotspots': [_file_hotspot('bad.py', 60)],
            'function_hotspots': [_fn_hotspot('complex_fn', 22)],
        }
        out = self._capture(report)
        self.assertIn('bad.py', out)
        self.assertIn('complex_fn', out)


class TestRunHotspots(unittest.TestCase):
    """run_hotspots: integration tests with subprocess mocked."""

    def _make_run(self, file_hotspots=None, fn_hotspots=None):
        """Patch both internal helpers."""
        return (
            patch('reveal.cli.commands.hotspots._run_file_hotspots',
                  return_value=file_hotspots or []),
            patch('reveal.cli.commands.hotspots._run_function_hotspots',
                  return_value=fn_hotspots or []),
        )

    def test_nonexistent_path_exits_1(self):
        args = _args(path='/does/not/exist/at/all')
        with self.assertRaises(SystemExit) as ctx:
            run_hotspots(args)
        self.assertEqual(ctx.exception.code, 1)

    def test_clean_code_exits_0(self, tmp_path=None):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            args = _args(path=d)
            p1, p2 = self._make_run([], [])
            with p1, p2:
                buf = StringIO()
                with patch('sys.stdout', buf):
                    run_hotspots(args)   # should NOT raise SystemExit

    def test_critical_file_exits_1(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            args = _args(path=d)
            p1, p2 = self._make_run([_file_hotspot('bad.py', 60)], [])
            with p1, p2:
                buf = StringIO()
                with patch('sys.stdout', buf):
                    with self.assertRaises(SystemExit) as ctx:
                        run_hotspots(args)
                self.assertEqual(ctx.exception.code, 1)

    def test_critical_function_exits_1(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            args = _args(path=d)
            p1, p2 = self._make_run([], [_fn_hotspot('fn', 25)])
            with p1, p2:
                buf = StringIO()
                with patch('sys.stdout', buf):
                    with self.assertRaises(SystemExit) as ctx:
                        run_hotspots(args)
                self.assertEqual(ctx.exception.code, 1)

    def test_json_format_outputs_json(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            args = _args(path=d, format='json')
            p1, p2 = self._make_run([], [])
            with p1, p2:
                buf = StringIO()
                with patch('sys.stdout', buf):
                    run_hotspots(args)
            output = buf.getvalue()
            parsed = json.loads(output)
            self.assertIn('file_hotspots', parsed)
            self.assertIn('function_hotspots', parsed)

    def test_functions_only_skips_file_hotspots(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            args = _args(path=d, functions_only=True)
            with patch('reveal.cli.commands.hotspots._run_file_hotspots') as mock_file:
                with patch('reveal.cli.commands.hotspots._run_function_hotspots', return_value=[]):
                    buf = StringIO()
                    with patch('sys.stdout', buf):
                        run_hotspots(args)
                    mock_file.assert_not_called()

    def test_files_only_skips_function_hotspots(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            args = _args(path=d, files_only=True)
            with patch('reveal.cli.commands.hotspots._run_file_hotspots', return_value=[]):
                with patch('reveal.cli.commands.hotspots._run_function_hotspots') as mock_fn:
                    buf = StringIO()
                    with patch('sys.stdout', buf):
                        run_hotspots(args)
                    mock_fn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
