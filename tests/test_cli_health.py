"""Tests for reveal/cli/commands/health.py."""

import io
import json
import sys
import unittest
import tempfile
from argparse import Namespace
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import MagicMock, patch

from reveal.cli.commands.health import (
    _detect_targets,
    _check_target,
    _check_code,
    _check_uri,
    _check_nginx,
    _render_results,
    _print_usage_and_exit,
    run_health,
)


# ---------------------------------------------------------------------------
# _detect_targets
# ---------------------------------------------------------------------------

class TestDetectTargets(unittest.TestCase):

    def test_returns_list(self):
        result = _detect_targets()
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) > 0)

    def test_fallback_is_dot(self):
        import os
        orig = os.getcwd()
        with tempfile.TemporaryDirectory() as d:
            os.chdir(d)
            try:
                result = _detect_targets()
                self.assertIn('.', result)
            finally:
                os.chdir(orig)

    def test_detects_src_dir(self):
        import os
        orig = os.getcwd()
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'src').mkdir()
            os.chdir(d)
            try:
                result = _detect_targets()
                self.assertIn('src', result)
            finally:
                os.chdir(orig)


# ---------------------------------------------------------------------------
# _check_target
# ---------------------------------------------------------------------------

class TestCheckTarget(unittest.TestCase):

    def test_nonexistent_path_returns_1(self):
        args = Namespace(select=None)
        code, summary = _check_target('/nonexistent/path/xyz', args)
        self.assertEqual(code, 1)
        self.assertIn('not found', summary)

    def test_uri_routes_to_check_uri(self):
        args = Namespace(select=None)
        with patch('reveal.cli.commands.health._check_uri', return_value=(0, 'ok')) as mock:
            code, summary = _check_target('ssl://example.com', args)
            mock.assert_called_once()
            self.assertEqual(code, 0)

    def test_nginx_conf_routes_to_nginx(self):
        with tempfile.NamedTemporaryFile(suffix='.conf', delete=False) as f:
            conf_path = f.name
        args = Namespace(select=None)
        with patch('reveal.cli.commands.health._check_nginx', return_value=(0, 'nginx: healthy')) as mock:
            code, _ = _check_target(conf_path, args)
            mock.assert_called_once()

    def test_directory_routes_to_code_check(self):
        with tempfile.TemporaryDirectory() as d:
            args = Namespace(select=None)
            with patch('reveal.cli.commands.health._check_code', return_value=(0, 'code: healthy')) as mock:
                code, summary = _check_target(d, args)
                mock.assert_called_once()
                self.assertEqual(code, 0)


# ---------------------------------------------------------------------------
# _check_code
# ---------------------------------------------------------------------------

class TestCheckCode(unittest.TestCase):

    @patch('subprocess.run')
    def test_healthy_returns_0(self, mock_run):
        data = {'total_violations': 0, 'violations': []}
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(data))
        code, summary = _check_code(Path('/tmp'), Namespace(select=None))
        self.assertEqual(code, 0)
        self.assertIn('healthy', summary)

    @patch('subprocess.run')
    def test_warnings_returns_1(self, mock_run):
        data = {'total_violations': 2, 'violations': [
            {'severity': 'warning', 'rule': 'C001'},
            {'severity': 'warning', 'rule': 'C002'},
        ]}
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(data))
        code, summary = _check_code(Path('/tmp'), Namespace(select=None))
        self.assertEqual(code, 1)
        self.assertIn('2', summary)

    @patch('subprocess.run')
    def test_critical_returns_2(self, mock_run):
        data = {'total_violations': 1, 'violations': [
            {'severity': 'error', 'rule': 'B001'},
        ]}
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(data))
        code, summary = _check_code(Path('/tmp'), Namespace(select=None))
        self.assertEqual(code, 2)
        self.assertIn('critical', summary)

    @patch('subprocess.run')
    def test_empty_stdout_returns_0(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='')
        code, summary = _check_code(Path('/tmp'), Namespace(select=None))
        self.assertEqual(code, 0)

    @patch('subprocess.run')
    def test_nonzero_returncode_returns_1(self, mock_run):
        # stdout must be non-empty but unparseable to trigger the except branch
        mock_run.return_value = MagicMock(returncode=1, stdout='not valid json')
        code, summary = _check_code(Path('/tmp'), Namespace(select=None))
        self.assertEqual(code, 1)


# ---------------------------------------------------------------------------
# _check_uri
# ---------------------------------------------------------------------------

class TestCheckUri(unittest.TestCase):

    @patch('subprocess.run')
    def test_returncode_0_is_healthy(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
        code, summary = _check_uri('ssl', 'ssl://example.com', Namespace())
        self.assertEqual(code, 0)
        self.assertIn('healthy', summary)

    @patch('subprocess.run')
    def test_returncode_1_is_warning(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout='cert expires soon', stderr='')
        code, summary = _check_uri('ssl', 'ssl://example.com', Namespace())
        self.assertEqual(code, 1)
        self.assertIn('ssl', summary)

    @patch('subprocess.run')
    def test_returncode_2_is_critical(self, mock_run):
        mock_run.return_value = MagicMock(returncode=2, stdout='', stderr='connection refused')
        code, summary = _check_uri('ssl', 'ssl://example.com', Namespace())
        self.assertEqual(code, 2)
        self.assertIn('critical', summary)

    @patch('subprocess.run')
    def test_unknown_scheme_passes_no_flags(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
        _check_uri('custom', 'custom://host', Namespace())
        cmd = mock_run.call_args[0][0]
        self.assertIn('custom://host', cmd)


# ---------------------------------------------------------------------------
# _check_nginx
# ---------------------------------------------------------------------------

class TestCheckNginx(unittest.TestCase):

    @patch('subprocess.run')
    def test_clean_returns_0(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='')
        code, summary = _check_nginx(Path('/etc/nginx/nginx.conf'), Namespace())
        self.assertEqual(code, 0)
        self.assertIn('healthy', summary)

    @patch('subprocess.run')
    def test_violations_returns_1(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='violation found\n')
        code, summary = _check_nginx(Path('/etc/nginx/nginx.conf'), Namespace())
        self.assertEqual(code, 1)

    @patch('subprocess.run')
    def test_nonzero_returncode_returns_1(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout='')
        code, summary = _check_nginx(Path('/etc/nginx/nginx.conf'), Namespace())
        self.assertEqual(code, 1)


# ---------------------------------------------------------------------------
# _render_results
# ---------------------------------------------------------------------------

class TestRenderResults(unittest.TestCase):

    def _capture(self, results):
        buf = io.StringIO()
        with redirect_stdout(buf):
            _render_results(results)
        return buf.getvalue()

    def test_all_pass_shows_pass(self):
        results = [{'target': './src', 'exit_code': 0, 'summary': 'code: healthy'}]
        out = self._capture(results)
        self.assertIn("PASS", out)

    def test_warning_shows_warn(self):
        results = [{'target': './src', 'exit_code': 1, 'summary': 'code: 3 violations'}]
        out = self._capture(results)
        self.assertIn("WARN", out)

    def test_failure_shows_fail(self):
        results = [{'target': './src', 'exit_code': 2, 'summary': 'code: 1 critical'}]
        out = self._capture(results)
        self.assertIn("FAIL", out)

    def test_multiple_targets_shown(self):
        results = [
            {'target': './src', 'exit_code': 0, 'summary': 'code: healthy'},
            {'target': 'ssl://example.com', 'exit_code': 0, 'summary': 'ssl: healthy'},
        ]
        out = self._capture(results)
        self.assertIn('./src', out)
        self.assertIn('ssl://example.com', out)

    def test_empty_results_no_crash(self):
        out = self._capture([])
        self.assertIn("PASS", out)


# ---------------------------------------------------------------------------
# _print_usage_and_exit
# ---------------------------------------------------------------------------

class TestPrintUsageAndExit(unittest.TestCase):

    def test_exits_1(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                _print_usage_and_exit()
        self.assertEqual(ctx.exception.code, 1)

    def test_shows_usage(self):
        buf = io.StringIO()
        with redirect_stderr(buf):
            with self.assertRaises(SystemExit):
                _print_usage_and_exit()
        self.assertIn("reveal health", buf.getvalue())


# ---------------------------------------------------------------------------
# run_health integration
# ---------------------------------------------------------------------------

class TestRunHealth(unittest.TestCase):

    def _args(self, targets, fmt='text', health_all=False, select=None):
        return Namespace(targets=targets, format=fmt, health_all=health_all, select=select)

    def test_no_targets_exits_1(self):
        args = self._args([])
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                run_health(args)
        self.assertEqual(ctx.exception.code, 1)

    @patch('reveal.cli.commands.health._check_target', return_value=(0, 'code: healthy'))
    def test_single_target_exits_0(self, mock_check):
        with tempfile.TemporaryDirectory() as d:
            args = self._args([d])
            buf = io.StringIO()
            with redirect_stdout(buf):
                with self.assertRaises(SystemExit) as ctx:
                    run_health(args)
            self.assertEqual(ctx.exception.code, 0)

    @patch('reveal.cli.commands.health._check_target', return_value=(2, 'code: critical'))
    def test_critical_exits_2(self, mock_check):
        with tempfile.TemporaryDirectory() as d:
            args = self._args([d])
            with redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    run_health(args)
            self.assertEqual(ctx.exception.code, 2)

    @patch('reveal.cli.commands.health._check_target', return_value=(0, 'code: healthy'))
    def test_json_format(self, mock_check):
        with tempfile.TemporaryDirectory() as d:
            args = self._args([d], fmt='json')
            buf = io.StringIO()
            with redirect_stdout(buf):
                with self.assertRaises(SystemExit):
                    run_health(args)
            data = json.loads(buf.getvalue())
            self.assertIn('results', data)
            self.assertIn('overall_exit', data)

    @patch('reveal.cli.commands.health._detect_targets', return_value=['.'])
    @patch('reveal.cli.commands.health._check_target', return_value=(0, 'code: healthy'))
    def test_health_all_flag_uses_detected_targets(self, mock_check, mock_detect):
        args = self._args([], health_all=True)
        with redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                run_health(args)
        mock_detect.assert_called_once()

    @patch('reveal.cli.commands.health._check_target', side_effect=[(1, 'warn'), (2, 'fail')])
    def test_multiple_targets_max_exit_code(self, mock_check):
        args = self._args(['./a', './b'])
        with redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                run_health(args)
        self.assertEqual(ctx.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
