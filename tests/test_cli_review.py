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

import pytest

from reveal.cli.file_checker import FileCollectionResult
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
    _changed_files,
    _extract_complexity_spikes,
    run_review,
)

# BACK-1149: exercises reveal.main's CLI entry point via conftest's _run_reveal_direct/subprocess
pytestmark = pytest.mark.cli


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

    def test_adapter_payload_shows_structural_summary(self):
        """BACK-1401: the diff adapter nests its result under data.summary;
        reading top-level keys printed "0 files modified" for every range."""
        out = self._capture({'status': 'ok', 'data': {'summary': {
            'functions': {'added': 5, 'removed': 1, 'modified': 2},
            'classes': {'added': 0, 'removed': 0, 'modified': 0},
            'imports': {'added': 1, 'removed': 0}}}})
        self.assertIn("functions +5 -1 ~2", out)
        self.assertIn("imports +1", out)
        self.assertNotIn("classes", out)

    def test_adapter_payload_without_changes_says_none(self):
        out = self._capture({'status': 'ok', 'data': {'summary': {
            'functions': {'added': 0}, 'classes': {}, 'imports': {}}}})
        self.assertIn("Structural changes: none", out)

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
        v = [{'severity': 'high', 'rule': 'B001', 'file': 'a.py', 'line': 1, 'message': 'bad'}]
        out = self._capture(v)
        self.assertIn("1", out)
        self.assertIn("B001", out)

    def test_violations_grouped_by_severity(self):
        violations = [
            {'severity': 'medium', 'rule': 'C901', 'file': 'b.py', 'line': 2, 'message': 'y'},
            {'severity': 'critical', 'rule': 'N002', 'file': 'a.py', 'line': 1, 'message': 'x'},
            {'severity': 'high', 'rule': 'B001', 'file': 'a.py', 'line': 1, 'message': 'x'},
        ]
        out = self._capture(violations)
        self.assertLess(out.index("Critical"), out.index("High"))
        self.assertLess(out.index("High"), out.index("Medium"))

    def test_verbose_shows_file_locations(self):
        v = [{'severity': 'high', 'rule': 'B001', 'file': 'a.py', 'line': 42, 'message': 'bad thing'}]
        out = self._capture(v, verbose=True)
        self.assertIn("a.py", out)
        self.assertIn("42", out)

    def test_missing_severity_defaults_to_medium(self):
        v = [{'rule': 'X001', 'file': 'a.py', 'line': 1, 'message': 'thing'}]
        out = self._capture(v)
        self.assertIn("Medium", out)


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

    def test_quality_score_rendered_out_of_100(self):
        out = self._capture([{'file': 'b.py', 'quality_score': 60.0, 'max_complexity': 31}])
        self.assertIn("quality: 60/100  complexity: 31", out)
        self.assertNotIn("{", out)

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
        v = [{'severity': 'medium', 'rule': 'C901'}]
        out = self._capture(v)
        self.assertIn("warning", out.lower())

    def test_high_blocks_merge(self):
        v = [{'severity': 'high', 'rule': 'B001'}]
        out = self._capture(v)
        self.assertIn("high/critical", out)
        self.assertIn("before merge", out)

    def test_incomplete_check_is_not_ready(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            _render_recommendation([], ['quality check failed: boom'])
        self.assertIn("incomplete", buf.getvalue())
        self.assertNotIn("Ready for review", buf.getvalue())


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

    def test_scan_disclosures_rendered(self):
        """BACK-1051: `review` is a composite wrapper around `check` -- a
        capped-scan disclosure (e.g. I002 skipping a 20,000+ file tree) must
        reach the rendered report, not be swallowed by the composite layer."""
        report = {
            'target': './src', 'sections': {'violations': [], 'hotspots': [], 'complexity': []},
            'scan_disclosures': ['I002: import-graph scan of ./src exceeded 20000 source files'],
        }
        out = self._capture(report)
        self.assertIn('I002: import-graph scan', out)

    def test_no_scan_disclosures_key_does_not_crash(self):
        """scan_disclosures is only added to the report when non-empty -- the
        renderer must tolerate its absence."""
        report = {'target': './src', 'sections': {'violations': [], 'hotspots': [], 'complexity': []}}
        out = self._capture(report)
        self.assertIn("./src", out)


# ---------------------------------------------------------------------------
# _changed_files (BACK-538: diff-scoped review)
# ---------------------------------------------------------------------------

class TestChangedFiles(unittest.TestCase):

    @patch('reveal.cli.commands.review.subprocess.run')
    def test_returns_existing_changed_files_only(self, mock_run):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'a.py').write_text('x = 1\n')

            def fake_run(cmd, **kwargs):
                if 'diff' in cmd:
                    # a.py exists; deleted.py does not → must be dropped
                    return MagicMock(returncode=0, stdout='a.py\ndeleted.py\n')
                return MagicMock(returncode=0, stdout=d + '\n')

            mock_run.side_effect = fake_run
            result = _changed_files('main..feature')
        self.assertEqual([p.name for p in result], ['a.py'])

    @patch('reveal.cli.commands.review.subprocess.run')
    def test_git_diff_failure_returns_empty(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout='')
        self.assertEqual(_changed_files('x..y'), [])

    @patch('reveal.cli.commands.review.subprocess.run', side_effect=Exception("no git"))
    def test_exception_returns_empty(self, _mock):
        self.assertEqual(_changed_files('x..y'), [])


# ---------------------------------------------------------------------------
# _run_diff, _run_check, _run_hotspots, _run_complexity (subprocess mocked)
# ---------------------------------------------------------------------------

class TestRunDiff(unittest.TestCase):

    @patch('reveal.adapters.diff.adapter.DiffAdapter')
    def test_success_returns_ok_status(self, MockAdapter):
        MockAdapter.return_value.get_structure.return_value = {'type': 'diff_comparison'}
        result = _run_diff('main..feature')
        self.assertEqual(result['status'], 'ok')

    @patch('reveal.cli.commands.review.subprocess.run')
    @patch('reveal.adapters.diff.adapter.DiffAdapter', side_effect=Exception("parse error"))
    def test_fallback_to_git_diff(self, _mock_adapter, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='a.py\nb.py\n', stderr='')
        result = _run_diff('main..feature')
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['count'], 2)

    @patch('reveal.cli.commands.review.subprocess.run', side_effect=Exception("no subprocess"))
    @patch('reveal.adapters.diff.adapter.DiffAdapter', side_effect=Exception("parse error"))
    def test_all_failures_returns_unavailable(self, _mock_adapter, _mock_run):
        result = _run_diff('main..feature')
        self.assertEqual(result['status'], 'unavailable')


class TestRunCheck(unittest.TestCase):

    @patch('reveal.cli.file_checker._check_files_json')
    @patch('reveal.cli.file_checker.collect_files_to_check', return_value=FileCollectionResult(files=[Path('/tmp/f.py')]))
    @patch('reveal.cli.file_checker.load_gitignore_patterns', return_value=[])
    def test_returns_violations(self, _pats, _files, mock_check):
        mock_check.return_value = (1, 1, [{
            'file': 'f.py',
            'issues': 1,
            'detections': [{'rule_code': 'B001', 'severity': 'error', 'line': 5, 'message': 'bad'}],
        }], 0, False)
        result = _run_check(Path('/tmp'), 'B,S')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['rule'], 'B001')

    @patch('reveal.cli.file_checker._check_files_json')
    @patch('reveal.cli.file_checker.collect_files_to_check', return_value=FileCollectionResult(files=[]))
    @patch('reveal.cli.file_checker.load_gitignore_patterns', return_value=[])
    def test_no_files_returns_empty_list(self, _pats, _files, mock_check):
        mock_check.return_value = (0, 0, [], 0, False)
        result = _run_check(Path('/tmp'), 'B,S')
        self.assertEqual(result, [])

    @patch('reveal.cli.file_checker.load_gitignore_patterns', side_effect=Exception("fail"))
    def test_exception_returns_empty_list(self, _mock):
        errors = []
        # A directory that exists on every OS, so the patched gitignore loader
        # is what fails (on Windows '/tmp' is not a directory and a real check ran).
        result = _run_check(Path(tempfile.gettempdir()), 'B,S', errors=errors)
        self.assertEqual(result, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("quality check failed", errors[0])

    @patch('reveal.cli.file_checker._check_files_json')
    def test_files_param_scopes_to_existing_files(self, mock_check):
        mock_check.return_value = (1, 1, [{
            'file': 'a.py',
            'detections': [{'rule_code': 'B001', 'severity': 'error', 'line': 1, 'message': 'x'}],
        }], 0, False)
        with tempfile.TemporaryDirectory() as d:
            existing = Path(d) / 'a.py'
            existing.write_text('x = 1\n')
            missing = Path(d) / 'gone.py'  # deleted-in-diff file, should be dropped
            result = _run_check(None, 'B,S', files=[existing, missing])
        self.assertEqual(len(result), 1)
        passed_files = mock_check.call_args[0][0]
        self.assertEqual([p.name for p in passed_files], ['a.py'])

    @patch('reveal.cli.file_checker._check_files_json')
    def test_empty_files_list_returns_empty_without_checking(self, mock_check):
        result = _run_check(None, 'B,S', files=[])
        self.assertEqual(result, [])
        mock_check.assert_not_called()

    def test_no_path_and_no_files_returns_empty(self):
        self.assertEqual(_run_check(None, 'B,S'), [])


class TestRunHotspots(unittest.TestCase):

    @patch('reveal.adapters.stats.adapter.StatsAdapter')
    def test_returns_top_10(self, MockAdapter):
        hotspots = [{'file': f'f{i}.py'} for i in range(15)]
        MockAdapter.return_value.get_structure.return_value = {'hotspots': hotspots}
        result = _run_hotspots(Path('/tmp'))
        self.assertEqual(len(result), 10)

    @patch('reveal.adapters.stats.adapter.StatsAdapter', side_effect=Exception("fail"))
    def test_exception_returns_empty(self, _mock):
        self.assertEqual(_run_hotspots(Path('/tmp')), [])

    @patch('reveal.adapters.stats.adapter.StatsAdapter')
    def test_files_merged_and_ranked_by_score(self, MockAdapter):
        MockAdapter.return_value.get_structure.side_effect = [
            {'hotspots': [{'file': 'a.py', 'score': 5}]},
            {'hotspots': [{'file': 'b.py', 'score': 9}]},
        ]
        result = _run_hotspots(None, files=[Path('a.py'), Path('b.py')])
        self.assertEqual([h['file'] for h in result], ['b.py', 'a.py'])

    @patch('reveal.adapters.stats.adapter.StatsAdapter')
    def test_per_file_stats_shape_is_flattened_and_perfect_files_dropped(self, MockAdapter):
        """BACK-1401: a single-file stats target returns `files` entries with
        `quality`/`complexity` as dicts; they rendered as raw Python dicts and
        every 100/100 file was listed as needing attention."""
        def stats(score, cx):
            return {'files': [{'file': f'q{score}.py', 'quality': {'score': score, 'check_issues': 1},
                               'complexity': {'average': cx, 'max': cx, 'min': cx}}]}
        MockAdapter.return_value.get_structure.side_effect = [stats(100.0, 2), stats(60.0, 31), stats(90.0, 4)]
        result = _run_hotspots(None, files=[Path('a.py'), Path('b.py'), Path('c.py')])
        self.assertEqual([h['file'] for h in result], ['q60.0.py', 'q90.0.py'])
        self.assertEqual(result[0]['quality_score'], 60.0)
        self.assertEqual(result[0]['max_complexity'], 31)

    @patch('reveal.adapters.stats.adapter.StatsAdapter')
    def test_one_bad_file_does_not_sink_others(self, MockAdapter):
        MockAdapter.return_value.get_structure.side_effect = [
            Exception("unparseable"),
            {'hotspots': [{'file': 'b.py', 'score': 3}]},
        ]
        result = _run_hotspots(None, files=[Path('a.md'), Path('b.py')])
        self.assertEqual([h['file'] for h in result], ['b.py'])


class TestRunComplexity(unittest.TestCase):

    @patch('reveal.adapters.ast.adapter.AstAdapter')
    def test_returns_elements(self, MockAdapter):
        MockAdapter.return_value.get_structure.return_value = {
            'results': [{'name': 'fn', 'complexity': 12}]
        }
        result = _run_complexity(Path('/tmp'))
        self.assertEqual(result[0]['name'], 'fn')

    @patch('reveal.adapters.ast.adapter.AstAdapter')
    def test_handles_elements_key(self, MockAdapter):
        MockAdapter.return_value.get_structure.return_value = {
            'elements': [{'name': 'fn2', 'complexity': 15}]
        }
        result = _run_complexity(Path('/tmp'))
        self.assertEqual(result[0]['name'], 'fn2')

    @patch('reveal.adapters.ast.adapter.AstAdapter', side_effect=Exception("fail"))
    def test_exception_returns_empty(self, _mock):
        self.assertEqual(_run_complexity(Path('/tmp')), [])

    @patch('reveal.adapters.ast.adapter.AstAdapter')
    def test_files_merged_and_ranked_by_complexity(self, MockAdapter):
        MockAdapter.return_value.get_structure.side_effect = [
            {'results': [{'name': 'fa', 'complexity': 11}]},
            {'results': [{'name': 'fb', 'complexity': 20}]},
        ]
        result = _run_complexity(None, files=[Path('a.py'), Path('b.py')])
        self.assertEqual([r['name'] for r in result], ['fb', 'fa'])


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
           return_value=[{'severity': 'high', 'rule': 'B001'}])
    @patch('reveal.cli.commands.review._run_hotspots', return_value=[])
    @patch('reveal.cli.commands.review._run_complexity', return_value=[])
    def test_high_violations_exits_2(self, mock_cx, mock_hs, mock_chk):
        with tempfile.TemporaryDirectory() as d:
            args = self._args(d)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    run_review(args)
            self.assertEqual(ctx.exception.code, 2)

    @patch('reveal.cli.commands.review._run_check',
           return_value=[{'severity': 'medium', 'rule': 'C901'}])
    @patch('reveal.cli.commands.review._run_hotspots', return_value=[])
    @patch('reveal.cli.commands.review._run_complexity', return_value=[])
    def test_warnings_only_exits_1(self, mock_cx, mock_hs, mock_chk):
        with tempfile.TemporaryDirectory() as d:
            args = self._args(d)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    run_review(args)
            self.assertEqual(ctx.exception.code, 1)

    @patch('reveal.cli.commands.review._git_range_error', return_value=None)
    @patch('reveal.cli.commands.review._changed_files',
           return_value=[Path('/tmp/a.py')])
    @patch('reveal.cli.commands.review._run_diff',
           return_value={'status': 'ok', 'count': 1, 'changed_files': ['a.py']})
    @patch('reveal.cli.commands.review._run_check', return_value=[])
    @patch('reveal.cli.commands.review._run_hotspots', return_value=[])
    @patch('reveal.cli.commands.review._run_complexity', return_value=[])
    def test_git_range_scopes_quality_to_changed_files(
            self, mock_cx, mock_hs, mock_chk, mock_diff, mock_changed, _mock_valid):
        args = self._args('main..feature', fmt='json')
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                run_review(args)
        data = json.loads(buf.getvalue())
        self.assertTrue(data['is_diff'])
        self.assertEqual(data['scoped_files'], 1)
        mock_changed.assert_called_once_with('main..feature')
        # Each quality section must receive the diff-scoped file list, not a tree root.
        self.assertEqual(mock_chk.call_args.kwargs.get('files'), [Path('/tmp/a.py')])
        self.assertEqual(mock_hs.call_args.kwargs.get('files'), [Path('/tmp/a.py')])
        self.assertEqual(mock_cx.call_args.kwargs.get('files'), [Path('/tmp/a.py')])

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
            self.assertEqual((data['overall_status'], data['exit_code']), ('pass', 0))

    def test_check_failure_exits_3_incomplete(self):
        def failing_check(path, select, files=None, errors=None):
            errors.append('quality check failed: boom')
            return []
        with tempfile.TemporaryDirectory() as d, \
                patch('reveal.cli.commands.review._run_check', side_effect=failing_check), \
                patch('reveal.cli.commands.review._run_hotspots', return_value=[]), \
                patch('reveal.cli.commands.review._run_complexity', return_value=[]):
            buf = io.StringIO()
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    run_review(self._args(d, fmt='json'))
        self.assertEqual(ctx.exception.code, 3)
        data = json.loads(buf.getvalue())
        self.assertEqual(data['overall_status'], 'incomplete')
        self.assertEqual(data['errors'], ['quality check failed: boom'])

    @patch('reveal.cli.commands.review._git_range_error', return_value="unknown revision: 'nope'")
    @patch('reveal.cli.commands.review._run_check')
    def test_invalid_range_exits_2_without_reviewing(self, mock_chk, _mock_err):
        buf, err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf), redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                run_review(self._args('main..nope', fmt='json'))
        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(json.loads(buf.getvalue())['overall_status'], 'error')
        self.assertIn("unknown revision", err.getvalue())
        mock_chk.assert_not_called()

    @patch('reveal.cli.commands.review._run_check')
    def test_missing_path_exits_2(self, mock_chk):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                run_review(self._args('/nonexistent/review/target'))
        self.assertEqual(ctx.exception.code, 2)
        mock_chk.assert_not_called()


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


# ---------------------------------------------------------------------------
# End to end against a real git repository (BACK-1401). The unit tests above
# mock payload shapes; these pin the shapes review actually receives.
# ---------------------------------------------------------------------------

import os
import shutil
import subprocess

_GUIDE = Path(__file__).resolve().parent.parent / 'reveal' / 'docs' / 'guides' / 'SUBCOMMANDS_GUIDE.md'

_MEDIUM_ONLY = "def branchy(x):\n" + "".join(
    f"    if x == {i}:\n        return {i}\n" for i in range(12)) + "    return -1\n"
_HIGH = "def swallow():\n    try:\n        return 1\n    except:\n        return 0\n"


class TestReviewAgainstRealRepo(unittest.TestCase):

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)
        self._git('init', '-q', '-b', 'main')
        self._commit('base.py', "def ok():\n    return 1\n")

    def _git(self, *args):
        subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', *args],
                       cwd=self.repo, check=True, capture_output=True)

    def _commit(self, name, content):
        (self.repo / name).write_text(content, encoding='utf-8')
        self._git('add', name)
        self._git('commit', '-q', '-m', name)

    def _review(self, *args):
        env = {**os.environ, 'REVEAL_DISK_CACHE': '0'}
        return subprocess.run([sys.executable, '-m', 'reveal', 'review', *args],
                              cwd=self.repo, capture_output=True, text=True, env=env, timeout=120, check=False, encoding='utf-8')

    def test_unknown_revision_is_a_usage_error(self):
        r = self._review('main..nonexistentbranch')
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("unknown revision: 'nonexistentbranch'", r.stderr)
        self.assertNotIn("Ready for review", r.stdout)

    def test_outside_a_repository_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as not_a_repo:
            env = {**os.environ, 'GIT_CEILING_DIRECTORIES': str(Path(not_a_repo).parent)}
            r = subprocess.run([sys.executable, '-m', 'reveal', 'review', 'HEAD~1..HEAD'],
                               cwd=not_a_repo, capture_output=True, text=True, env=env, timeout=120, check=False, encoding='utf-8')
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("not inside a git repository", r.stderr)

    def test_text_headline_reports_the_real_structural_change(self):
        self._commit('branchy.py', _MEDIUM_ONLY)
        r = self._review('HEAD~1..HEAD')
        self.assertIn("Structural changes: functions +1", r.stdout)
        self.assertIn("quality: ", r.stdout)
        self.assertNotIn("{'score'", r.stdout)

    def test_severity_decides_status_and_exit_code(self):
        self._commit('branchy.py', _MEDIUM_ONLY)
        warn = self._review('HEAD~1..HEAD', '--format', 'json')
        self._commit('swallow.py', _HIGH)
        fail = self._review('HEAD~1..HEAD', '--format', 'json')
        self.assertEqual((json.loads(warn.stdout)['overall_status'], warn.returncode), ('warn', 1))
        self.assertEqual((json.loads(fail.stdout)['overall_status'], fail.returncode), ('fail', 2))

    @unittest.skipUnless(shutil.which('jq'), 'jq not installed')
    @unittest.skipIf(sys.platform == 'win32', "the documented gates use POSIX-shell quoting")
    def test_documented_ci_gates_work(self):
        """Every `reveal review` line in the guide's CI/CD block, run verbatim
        (C13: `.overall_status` did not exist and `severity=="error"` never
        matched, so both documented gates passed on anything)."""
        section = _GUIDE.read_text(encoding='utf-8').split('### CI/CD Integration', 1)[1].split('```bash', 1)[1]
        gates = [ln for ln in section.split('```', 1)[0].splitlines() if ln.startswith('reveal review')]
        self.assertEqual(len(gates), 3, gates)
        cli = f"{sys.executable} -m reveal"
        env = {**os.environ, 'REVEAL_DISK_CACHE': '0'}

        def outcomes():
            return [subprocess.run((cli + g[len('reveal'):]).replace('main..HEAD', 'HEAD~1..HEAD'),
                                   shell=True, cwd=self.repo, capture_output=True, env=env,
                                   timeout=120, check=False).returncode == 0 for g in gates]

        self._commit('clean.py', "def fine():\n    return 2\n")
        self.assertEqual(outcomes(), [True, True, True], 'clean change')
        self._commit('branchy.py', _MEDIUM_ONLY)
        self.assertEqual(outcomes(), [False, True, True], 'medium-only change')
        self._commit('swallow.py', _HIGH)
        self.assertEqual(outcomes(), [False, False, False], 'high-severity change')
