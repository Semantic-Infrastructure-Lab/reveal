"""Tests for reveal/cli/commands/review.py."""

import io
import json
import sys
import unittest
import tempfile
from argparse import Namespace
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import MagicMock, patch

from reveal.cli.commands.review import (
    _render_diff_section,
    _render_violations_section,
    _render_hotspots_section,
    _render_complexity_section,
    _render_complexity_spikes_section,
    _render_recommendation,
    _render_report,
    _run_diff,
    _run_check,
    _run_hotspots,
    _run_complexity,
    _detect_source_root,
    _extract_complexity_spikes,
    run_review,
)


# ---------------------------------------------------------------------------
# _render_diff_section
# ---------------------------------------------------------------------------

class TestRenderDiffSection(unittest.TestCase):

    def _capture(self, diff):
        buf = io.StringIO()
        with redirect_stdout(buf):
            _render_diff_section(diff)
        return buf.getvalue()

    def test_empty_dict_renders_nothing(self):
        self.assertEqual(self._capture({}), "")

    def test_unavailable_status_renders_nothing(self):
        self.assertEqual(self._capture({'status': 'unavailable'}), "")

    def test_ok_status_shows_count(self):
        out = self._capture({'status': 'ok', 'changed_files': ['a.py', 'b.py'], 'count': 2})
        self.assertIn("2 files modified", out)

    def test_few_files_listed_individually(self):
        files = ['a.py', 'b.py', 'c.py']
        out = self._capture({'status': 'ok', 'changed_files': files, 'count': 3})
        self.assertIn("a.py", out)
        self.assertIn("b.py", out)

    def test_many_files_truncated(self):
        files = [f"file{i}.py" for i in range(20)]
        out = self._capture({'status': 'ok', 'changed_files': files, 'count': 20})
        self.assertIn("more", out)

    def test_no_changed_files_key_uses_count(self):
        out = self._capture({'status': 'ok', 'count': 5})
        self.assertIn("5 files modified", out)


# ---------------------------------------------------------------------------
# _render_violations_section
# ---------------------------------------------------------------------------

class TestRenderViolationsSection(unittest.TestCase):

    def _capture(self, violations, verbose=False):
        buf = io.StringIO()
        with redirect_stdout(buf):
            _render_violations_section(violations, verbose)
        return buf.getvalue()

    def test_no_violations_shows_clean(self):
        out = self._capture([])
        self.assertIn("No violations", out)

    def test_violations_shows_count(self):
        v = [{'severity': 'error', 'rule': 'B001', 'file': 'a.py', 'line': 1, 'message': 'bad'}]
        out = self._capture(v)
        self.assertIn("1", out)
        self.assertIn("B001", out)

    def test_violations_grouped_by_severity(self):
        violations = [
            {'severity': 'error', 'rule': 'B001', 'file': 'a.py', 'line': 1, 'message': 'x'},
            {'severity': 'warning', 'rule': 'C001', 'file': 'b.py', 'line': 2, 'message': 'y'},
        ]
        out = self._capture(violations)
        self.assertIn("Critical", out)
        self.assertIn("Warning", out)

    def test_verbose_shows_file_locations(self):
        v = [{'severity': 'error', 'rule': 'B001', 'file': 'a.py', 'line': 42, 'message': 'bad thing'}]
        out = self._capture(v, verbose=True)
        self.assertIn("a.py", out)
        self.assertIn("42", out)

    def test_missing_severity_defaults_to_warning(self):
        v = [{'rule': 'X001', 'file': 'a.py', 'line': 1, 'message': 'thing'}]
        out = self._capture(v)
        self.assertIn("Warning", out)


# ---------------------------------------------------------------------------
# _render_hotspots_section
# ---------------------------------------------------------------------------

class TestRenderHotspotsSection(unittest.TestCase):

    def _capture(self, hotspots):
        buf = io.StringIO()
        with redirect_stdout(buf):
            _render_hotspots_section(hotspots)
        return buf.getvalue()

    def test_empty_renders_nothing(self):
        self.assertEqual(self._capture([]), "")

    def test_shows_file_and_quality(self):
        h = [{'file': 'src/auth.py', 'quality_score': 72, 'complexity': 15}]
        out = self._capture(h)
        self.assertIn("src/auth.py", out)
        self.assertIn("72", out)

    def test_handles_missing_keys(self):
        h = [{'path': 'src/app.py', 'score': 80}]
        out = self._capture(h)
        self.assertIn("src/app.py", out)

    def test_limits_to_five(self):
        hotspots = [{'file': f'f{i}.py', 'quality_score': i} for i in range(10)]
        out = self._capture(hotspots)
        self.assertIn("f0.py", out)
        self.assertNotIn("f5.py", out)


# ---------------------------------------------------------------------------
# _render_complexity_section
# ---------------------------------------------------------------------------

class TestRenderComplexitySection(unittest.TestCase):

    def _capture(self, fns):
        buf = io.StringIO()
        with redirect_stdout(buf):
            _render_complexity_section(fns)
        return buf.getvalue()

    def test_empty_renders_nothing(self):
        self.assertEqual(self._capture([]), "")

    def test_shows_function_name_and_complexity(self):
        fns = [{'name': 'parse_auth', 'complexity': 18, 'file': 'auth.py'}]
        out = self._capture(fns)
        self.assertIn("parse_auth", out)
        self.assertIn("18", out)

    def test_limits_to_five(self):
        fns = [{'name': f'fn{i}', 'complexity': i, 'file': 'a.py'} for i in range(10)]
        out = self._capture(fns)
        self.assertIn("fn0", out)
        self.assertNotIn("fn5", out)


# ---------------------------------------------------------------------------
# _render_recommendation
# ---------------------------------------------------------------------------

class TestRenderRecommendation(unittest.TestCase):

    def _capture(self, violations):
        buf = io.StringIO()
        with redirect_stdout(buf):
            _render_recommendation(violations)
        return buf.getvalue()

    def test_no_violations_ready_for_review(self):
        out = self._capture([])
        self.assertIn("Ready for review", out)

    def test_warnings_only(self):
        v = [{'severity': 'warning', 'rule': 'C001'}]
        out = self._capture(v)
        self.assertIn("warning", out.lower())

    def test_critical_blocks_merge(self):
        v = [{'severity': 'error', 'rule': 'B001'}]
        out = self._capture(v)
        self.assertIn("critical", out.lower())
        self.assertIn("before merge", out)


# ---------------------------------------------------------------------------
# _render_report
# ---------------------------------------------------------------------------

class TestRenderReport(unittest.TestCase):

    def _capture(self, report, verbose=False):
        buf = io.StringIO()
        with redirect_stdout(buf):
            _render_report(report, verbose)
        return buf.getvalue()

    def test_shows_target(self):
        report = {'target': 'main..feature', 'sections': {'violations': [], 'hotspots': [], 'complexity': []}}
        out = self._capture(report)
        self.assertIn("main..feature", out)

    def test_no_crash_empty_sections(self):
        report = {'target': './src', 'sections': {}}
        out = self._capture(report)
        self.assertIn("./src", out)


# ---------------------------------------------------------------------------
# _detect_source_root
# ---------------------------------------------------------------------------

class TestDetectSourceRoot(unittest.TestCase):

    def test_returns_path(self):
        result = _detect_source_root()
        self.assertIsInstance(result, Path)

    @patch('reveal.cli.commands.review.subprocess.run')
    def test_finds_git_root(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='/tmp/myproject\n')
        with tempfile.TemporaryDirectory() as d:
            # No src/lib/app subdir → returns root
            with patch('pathlib.Path.is_dir', return_value=False):
                result = _detect_source_root()
        self.assertIsInstance(result, Path)

    @patch('reveal.cli.commands.review.subprocess.run')
    def test_falls_back_on_git_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout='')
        result = _detect_source_root()
        self.assertEqual(result, Path('.'))

    @patch('reveal.cli.commands.review.subprocess.run')
    def test_exception_falls_back(self, mock_run):
        mock_run.side_effect = Exception("no git")
        result = _detect_source_root()
        self.assertEqual(result, Path('.'))


# ---------------------------------------------------------------------------
# _run_diff, _run_check, _run_hotspots, _run_complexity (subprocess mocked)
# ---------------------------------------------------------------------------

class TestRunDiff(unittest.TestCase):

    @patch('reveal.cli.commands.review.subprocess.run')
    def test_success_returns_ok_status(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps({'diff': 'data'}), stderr=''
        )
        result = _run_diff('main..feature')
        self.assertEqual(result['status'], 'ok')

    @patch('reveal.cli.commands.review.subprocess.run')
    def test_fallback_to_git_diff(self, mock_run):
        # First call (reveal diff) fails, second (git diff) succeeds
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout='', stderr=''),
            MagicMock(returncode=0, stdout='a.py\nb.py\n', stderr=''),
        ]
        result = _run_diff('main..feature')
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['count'], 2)

    @patch('reveal.cli.commands.review.subprocess.run')
    def test_all_failures_returns_unavailable(self, mock_run):
        mock_run.side_effect = Exception("no subprocess")
        result = _run_diff('main..feature')
        self.assertEqual(result['status'], 'unavailable')


class TestRunCheck(unittest.TestCase):

    @patch('reveal.cli.commands.review.subprocess.run')
    def test_returns_violations(self, mock_run):
        data = {'violations': [{'rule': 'B001', 'severity': 'error'}]}
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(data))
        result = _run_check(Path('/tmp'), 'B,S')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['rule'], 'B001')

    @patch('reveal.cli.commands.review.subprocess.run')
    def test_empty_stdout_returns_empty_list(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='')
        result = _run_check(Path('/tmp'), 'B,S')
        self.assertEqual(result, [])

    @patch('reveal.cli.commands.review.subprocess.run')
    def test_exception_returns_empty_list(self, mock_run):
        mock_run.side_effect = Exception("timeout")
        result = _run_check(Path('/tmp'), 'B,S')
        self.assertEqual(result, [])


class TestRunHotspots(unittest.TestCase):

    @patch('reveal.cli.commands.review.subprocess.run')
    def test_returns_top_10(self, mock_run):
        data = {'hotspots': [{'file': f'f{i}.py'} for i in range(15)]}
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(data))
        result = _run_hotspots(Path('/tmp'))
        self.assertEqual(len(result), 10)

    @patch('reveal.cli.commands.review.subprocess.run')
    def test_exception_returns_empty(self, mock_run):
        mock_run.side_effect = Exception("fail")
        self.assertEqual(_run_hotspots(Path('/tmp')), [])


class TestRunComplexity(unittest.TestCase):

    @patch('reveal.cli.commands.review.subprocess.run')
    def test_returns_elements(self, mock_run):
        data = {'elements': [{'name': 'fn', 'complexity': 12}]}
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(data))
        result = _run_complexity(Path('/tmp'))
        self.assertEqual(result[0]['name'], 'fn')

    @patch('reveal.cli.commands.review.subprocess.run')
    def test_handles_results_key(self, mock_run):
        data = {'results': [{'name': 'fn2', 'complexity': 15}]}
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(data))
        result = _run_complexity(Path('/tmp'))
        self.assertEqual(result[0]['name'], 'fn2')

    @patch('reveal.cli.commands.review.subprocess.run')
    def test_exception_returns_empty(self, mock_run):
        mock_run.side_effect = Exception("fail")
        self.assertEqual(_run_complexity(Path('/tmp')), [])


# ---------------------------------------------------------------------------
# run_review integration
# ---------------------------------------------------------------------------

class TestRunReview(unittest.TestCase):

    def _args(self, target, fmt='text', verbose=False, select='B,S,I,C,M'):
        return Namespace(target=target, format=fmt, verbose=verbose, select=select)

    @patch('reveal.cli.commands.review._run_check', return_value=[])
    @patch('reveal.cli.commands.review._run_hotspots', return_value=[])
    @patch('reveal.cli.commands.review._run_complexity', return_value=[])
    def test_path_target_exits_0_clean(self, mock_cx, mock_hs, mock_chk):
        with tempfile.TemporaryDirectory() as d:
            args = self._args(d)
            buf_out = io.StringIO()
            buf_err = io.StringIO()
            with redirect_stdout(buf_out), redirect_stderr(buf_err):
                with self.assertRaises(SystemExit) as ctx:
                    run_review(args)
            self.assertEqual(ctx.exception.code, 0)

    @patch('reveal.cli.commands.review._run_check',
           return_value=[{'severity': 'error', 'rule': 'B001'}])
    @patch('reveal.cli.commands.review._run_hotspots', return_value=[])
    @patch('reveal.cli.commands.review._run_complexity', return_value=[])
    def test_critical_violations_exits_2(self, mock_cx, mock_hs, mock_chk):
        with tempfile.TemporaryDirectory() as d:
            args = self._args(d)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    run_review(args)
            self.assertEqual(ctx.exception.code, 2)

    @patch('reveal.cli.commands.review._run_check',
           return_value=[{'severity': 'warning', 'rule': 'C001'}])
    @patch('reveal.cli.commands.review._run_hotspots', return_value=[])
    @patch('reveal.cli.commands.review._run_complexity', return_value=[])
    def test_warnings_only_exits_1(self, mock_cx, mock_hs, mock_chk):
        with tempfile.TemporaryDirectory() as d:
            args = self._args(d)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    run_review(args)
            self.assertEqual(ctx.exception.code, 1)

    @patch('reveal.cli.commands.review._run_check', return_value=[])
    @patch('reveal.cli.commands.review._run_hotspots', return_value=[])
    @patch('reveal.cli.commands.review._run_complexity', return_value=[])
    def test_json_format_output(self, mock_cx, mock_hs, mock_chk):
        with tempfile.TemporaryDirectory() as d:
            args = self._args(d, fmt='json')
            buf = io.StringIO()
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    run_review(args)
            data = json.loads(buf.getvalue())
            self.assertIn('sections', data)
            self.assertIn('target', data)


# ---------------------------------------------------------------------------
# _extract_complexity_spikes


class TestExtractComplexitySpikes(unittest.TestCase):
    """Tests for BACK-073: _extract_complexity_spikes."""

    def _diff_data(self, functions):
        return {'status': 'ok', 'data': {'diff': {'functions': functions}}}

    def test_empty_diff_data_returns_empty(self):
        self.assertEqual(_extract_complexity_spikes({}), [])

    def test_no_functions_returns_empty(self):
        data = {'status': 'ok', 'data': {'diff': {}}}
        self.assertEqual(_extract_complexity_spikes(data), [])

    def test_functions_below_threshold_excluded(self):
        fns = [
            {'name': 'small', 'complexity_delta': 3, 'complexity_before': 1, 'complexity_after': 4},
            {'name': 'equal', 'complexity_delta': 5, 'complexity_before': 2, 'complexity_after': 7},
        ]
        result = _extract_complexity_spikes(self._diff_data(fns))
        self.assertEqual(result, [])

    def test_functions_above_threshold_included(self):
        fns = [
            {'name': 'big', 'complexity_delta': 8, 'complexity_before': 2, 'complexity_after': 10},
            {'name': 'small', 'complexity_delta': 2, 'complexity_before': 1, 'complexity_after': 3},
        ]
        result = _extract_complexity_spikes(self._diff_data(fns))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'big')
        self.assertEqual(result[0]['complexity_delta'], 8)

    def test_results_sorted_by_delta_descending(self):
        fns = [
            {'name': 'b', 'complexity_delta': 7, 'complexity_before': 1, 'complexity_after': 8},
            {'name': 'a', 'complexity_delta': 12, 'complexity_before': 1, 'complexity_after': 13},
            {'name': 'c', 'complexity_delta': 9, 'complexity_before': 1, 'complexity_after': 10},
        ]
        result = _extract_complexity_spikes(self._diff_data(fns))
        deltas = [r['complexity_delta'] for r in result]
        self.assertEqual(deltas, sorted(deltas, reverse=True))

    def test_none_delta_excluded(self):
        """Functions with complexity_delta=None (e.g. removed with no complexity) are skipped."""
        fns = [
            {'name': 'removed', 'complexity_delta': None, 'complexity_before': None, 'complexity_after': None},
            {'name': 'big', 'complexity_delta': 9, 'complexity_before': 1, 'complexity_after': 10},
        ]
        result = _extract_complexity_spikes(self._diff_data(fns))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'big')

    def test_custom_threshold(self):
        fns = [
            {'name': 'medium', 'complexity_delta': 3, 'complexity_before': 1, 'complexity_after': 4},
            {'name': 'large', 'complexity_delta': 8, 'complexity_before': 1, 'complexity_after': 9},
        ]
        result = _extract_complexity_spikes(self._diff_data(fns), threshold=2)
        self.assertEqual(len(result), 2)

    def test_spike_fields_preserved(self):
        fns = [{'name': 'fn', 'complexity_delta': 7, 'complexity_before': 3, 'complexity_after': 10}]
        result = _extract_complexity_spikes(self._diff_data(fns))
        self.assertEqual(result[0]['complexity_before'], 3)
        self.assertEqual(result[0]['complexity_after'], 10)
        self.assertEqual(result[0]['complexity_delta'], 7)


# ---------------------------------------------------------------------------
# _render_complexity_spikes_section


class TestRenderComplexitySpikesSection(unittest.TestCase):
    """Tests for BACK-073: _render_complexity_spikes_section."""

    def _capture(self, spikes):
        buf = io.StringIO()
        with redirect_stdout(buf):
            _render_complexity_spikes_section(spikes)
        return buf.getvalue()

    def test_empty_list_renders_nothing(self):
        self.assertEqual(self._capture([]), '')

    def test_renders_spike_count(self):
        spikes = [{'name': 'big', 'complexity_before': 2, 'complexity_after': 10, 'complexity_delta': 8}]
        output = self._capture(spikes)
        self.assertIn('1 function', output)
        self.assertIn('delta > 5', output)

    def test_renders_function_name_and_delta(self):
        spikes = [{'name': 'process_data', 'complexity_before': 2, 'complexity_after': 9, 'complexity_delta': 7}]
        output = self._capture(spikes)
        self.assertIn('process_data', output)
        self.assertIn('+7', output)

    def test_limits_to_ten(self):
        spikes = [
            {'name': f'fn{i}', 'complexity_before': 1, 'complexity_after': 8, 'complexity_delta': 7}
            for i in range(15)
        ]
        output = self._capture(spikes)
        # Should only show 10 lines of function output
        lines = [l for l in output.splitlines() if l.strip().startswith('fn')]
        self.assertLessEqual(len(lines), 10)

    def test_renders_before_after_values(self):
        spikes = [{'name': 'fn', 'complexity_before': 3, 'complexity_after': 11, 'complexity_delta': 8}]
        output = self._capture(spikes)
        self.assertIn('3', output)
        self.assertIn('11', output)


if __name__ == '__main__':
    unittest.main()
