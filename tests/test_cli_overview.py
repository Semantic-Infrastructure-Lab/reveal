"""Tests for reveal overview subcommand."""

import json
import sys
import time
import unittest
from argparse import Namespace
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from reveal.cli.commands.overview import (
    _age_label,
    _language_breakdown,
    _render_codebase_stats,
    _render_complex_functions,
    _render_git_log,
    _render_hotspots,
    _render_language_breakdown,
    _render_next_steps,
    _render_quality_pulse,
    _run_complex_functions,
    _run_git_log,
    _run_stats,
    create_overview_parser,
    run_overview,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _args(**kwargs):
    defaults = {
        'path': '.',
        'top': 5,
        'no_git': False,
        'format': 'text',
        'verbose': False,
    }
    defaults.update(kwargs)
    return Namespace(**defaults)


def _capture(fn, *args, **kwargs):
    buf = StringIO()
    with patch('sys.stdout', buf):
        fn(*args, **kwargs)
    return buf.getvalue()


def _mock_run(stdout='', returncode=0):
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    return m


_STATS_JSON = json.dumps({
    'contract_version': '1.0',
    'type': 'stats',
    'summary': {
        'total_files': 100,
        'total_lines': 5000,
        'total_code_lines': 3500,
        'total_functions': 200,
        'total_classes': 30,
        'avg_complexity': 2.3,
        'avg_quality_score': 88.5,
    },
    'files': [
        {'file': 'src/main.py'},
        {'file': 'src/utils.py'},
        {'file': 'docs/README.md'},
        {'file': 'config.yaml'},
    ],
    'hotspots': [
        {
            'file': 'src/complex.py',
            'hotspot_score': 15,
            'quality_score': 65.0,
            'issues': ['2 function(s) >100 lines'],
            'details': {'lines': 400},
        },
        {
            'file': 'src/messy.py',
            'hotspot_score': 8,
            'quality_score': 78.0,
            'issues': ['1 function(s) depth >4'],
            'details': {'lines': 200},
        },
    ],
})

_GIT_JSON = json.dumps({
    'history': [
        {'hash': 'abc1234', 'message': 'feat: add overview command', 'timestamp': int(time.time()) - 3600},
        {'hash': 'def5678', 'message': 'fix: edge case', 'timestamp': int(time.time()) - 86400},
    ]
})

_AST_JSON = json.dumps({
    'results': [
        {'name': 'complex_fn', 'complexity': 25, 'file': '/project/src/big.py', 'line': 50, 'line_count': 80},
        {'name': 'medium_fn', 'complexity': 14, 'file': '/project/src/other.py', 'line': 10, 'line_count': 40},
    ]
})


# ── Parser tests ───────────────────────────────────────────────────────────────

class TestCreateOverviewParser(unittest.TestCase):

    def test_returns_parser(self):
        parser = create_overview_parser()
        self.assertEqual(parser.prog, 'reveal overview')

    def test_defaults(self):
        parser = create_overview_parser()
        args = parser.parse_args([])
        self.assertEqual(args.path, '.')
        self.assertEqual(args.top, 5)
        self.assertFalse(args.no_git)

    def test_path_positional(self):
        parser = create_overview_parser()
        args = parser.parse_args(['./src'])
        self.assertEqual(args.path, './src')

    def test_top_flag(self):
        parser = create_overview_parser()
        args = parser.parse_args(['--top', '10'])
        self.assertEqual(args.top, 10)

    def test_no_git_flag(self):
        parser = create_overview_parser()
        args = parser.parse_args(['--no-git'])
        self.assertTrue(args.no_git)


# ── _language_breakdown tests ──────────────────────────────────────────────────

class TestLanguageBreakdown(unittest.TestCase):

    def test_python_files(self):
        files = [{'file': 'a.py'}, {'file': 'b.py'}, {'file': 'c.py'}]
        result = dict(_language_breakdown(files))
        self.assertEqual(result['Python'], 3)

    def test_mixed_languages(self):
        files = [
            {'file': 'a.py'}, {'file': 'b.py'},
            {'file': 'c.ts'}, {'file': 'README.md'},
        ]
        result = dict(_language_breakdown(files))
        self.assertEqual(result['Python'], 2)
        self.assertEqual(result['TypeScript'], 1)
        self.assertEqual(result['Markdown'], 1)

    def test_yaml_extensions(self):
        files = [{'file': 'a.yaml'}, {'file': 'b.yml'}]
        result = dict(_language_breakdown(files))
        self.assertEqual(result.get('YAML', 0), 2)

    def test_dockerfile_no_extension(self):
        files = [{'file': 'Dockerfile'}]
        result = dict(_language_breakdown(files))
        self.assertEqual(result.get('Dockerfile', 0), 1)

    def test_empty_input_returns_empty(self):
        self.assertEqual(_language_breakdown([]), [])

    def test_unknown_extension_uppercased(self):
        files = [{'file': 'a.xyz'}]
        result = dict(_language_breakdown(files))
        self.assertIn('XYZ', result)

    def test_sorted_by_count_descending(self):
        files = [{'file': 'a.md'}] + [{'file': f'{i}.py'} for i in range(5)]
        langs = _language_breakdown(files)
        self.assertEqual(langs[0][0], 'Python')

    def test_jsx_maps_to_javascript(self):
        files = [{'file': 'comp.jsx'}]
        result = dict(_language_breakdown(files))
        self.assertEqual(result.get('JavaScript', 0), 1)


# ── _age_label tests ───────────────────────────────────────────────────────────

class TestAgeLabel(unittest.TestCase):

    def test_minutes_ago(self):
        ts = int(time.time()) - 1800  # 30 minutes ago
        label = _age_label(ts)
        self.assertIn('m ago', label)
        self.assertIn('30', label)

    def test_hours_ago(self):
        ts = int(time.time()) - 7200  # 2 hours ago
        label = _age_label(ts)
        self.assertIn('h ago', label)
        self.assertIn('2', label)

    def test_days_ago(self):
        ts = int(time.time()) - 3 * 86400  # 3 days ago
        label = _age_label(ts)
        self.assertIn('d ago', label)
        self.assertIn('3', label)

    def test_none_returns_empty(self):
        self.assertEqual(_age_label(None), '')

    def test_zero_returns_0m(self):
        ts = int(time.time())
        label = _age_label(ts)
        self.assertIn('m ago', label)


# ── Data collector tests ───────────────────────────────────────────────────────

class TestRunStats(unittest.TestCase):

    @patch('subprocess.run')
    def test_returns_parsed_json(self, mock_run):
        mock_run.return_value = _mock_run(_STATS_JSON)
        result = _run_stats(Path('/project'))
        self.assertIn('summary', result)
        self.assertEqual(result['summary']['total_files'], 100)

    @patch('subprocess.run')
    def test_empty_stdout_returns_empty_dict(self, mock_run):
        mock_run.return_value = _mock_run('')
        result = _run_stats(Path('/project'))
        self.assertEqual(result, {})

    @patch('subprocess.run')
    def test_exception_returns_empty_dict(self, _mock):
        _mock.side_effect = Exception('fail')
        result = _run_stats(Path('/project'))
        self.assertEqual(result, {})


class TestRunGitLog(unittest.TestCase):

    @patch('subprocess.run')
    def test_returns_history_list(self, mock_run):
        mock_run.return_value = _mock_run(_GIT_JSON)
        result = _run_git_log(Path('/project'), 5)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['hash'], 'abc1234')

    @patch('subprocess.run')
    def test_empty_stdout_returns_empty(self, mock_run):
        mock_run.return_value = _mock_run('')
        result = _run_git_log(Path('/project'), 5)
        self.assertEqual(result, [])

    @patch('subprocess.run')
    def test_exception_returns_empty(self, _mock):
        _mock.side_effect = Exception('fail')
        result = _run_git_log(Path('/project'), 5)
        self.assertEqual(result, [])

    @patch('subprocess.run')
    def test_missing_history_key_returns_empty(self, mock_run):
        mock_run.return_value = _mock_run(json.dumps({'other': 'data'}))
        result = _run_git_log(Path('/project'), 5)
        self.assertEqual(result, [])


class TestRunComplexFunctions(unittest.TestCase):

    @patch('subprocess.run')
    def test_returns_results_list(self, mock_run):
        mock_run.return_value = _mock_run(_AST_JSON)
        result = _run_complex_functions(Path('/project'), 5)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['name'], 'complex_fn')

    @patch('subprocess.run')
    def test_falls_back_to_elements_key(self, mock_run):
        data = json.dumps({'elements': [{'name': 'fn', 'complexity': 15}]})
        mock_run.return_value = _mock_run(data)
        result = _run_complex_functions(Path('/project'), 5)
        self.assertEqual(result[0]['name'], 'fn')

    @patch('subprocess.run')
    def test_empty_stdout_returns_empty(self, mock_run):
        mock_run.return_value = _mock_run('')
        result = _run_complex_functions(Path('/project'), 5)
        self.assertEqual(result, [])

    @patch('subprocess.run')
    def test_exception_returns_empty(self, _mock):
        _mock.side_effect = Exception('fail')
        result = _run_complex_functions(Path('/project'), 5)
        self.assertEqual(result, [])


# ── Renderer tests ─────────────────────────────────────────────────────────────

class TestRenderCodebaseStats(unittest.TestCase):

    def test_shows_file_count(self):
        out = _capture(_render_codebase_stats, {'total_files': 100, 'total_lines': 5000})
        self.assertIn('100', out)

    def test_shows_total_lines(self):
        out = _capture(_render_codebase_stats, {'total_files': 100, 'total_lines': 5000})
        self.assertIn('5,000', out)

    def test_shows_functions_and_classes(self):
        out = _capture(_render_codebase_stats, {
            'total_files': 10, 'total_lines': 100,
            'total_functions': 50, 'total_classes': 5,
        })
        self.assertIn('50', out)
        self.assertIn('5', out)

    def test_empty_summary_produces_no_output(self):
        out = _capture(_render_codebase_stats, {})
        self.assertEqual(out, '')


class TestRenderLanguageBreakdown(unittest.TestCase):

    def test_shows_language_names(self):
        files = [{'file': 'a.py'}, {'file': 'b.py'}, {'file': 'c.md'}]
        out = _capture(_render_language_breakdown, files, 5)
        self.assertIn('Python', out)
        self.assertIn('Markdown', out)

    def test_shows_file_counts(self):
        files = [{'file': 'a.py'}, {'file': 'b.py'}]
        out = _capture(_render_language_breakdown, files, 5)
        self.assertIn('2', out)

    def test_shows_percentage(self):
        files = [{'file': f'{i}.py'} for i in range(4)] + [{'file': 'a.md'}]
        out = _capture(_render_language_breakdown, files, 5)
        self.assertIn('%', out)

    def test_truncates_at_top(self):
        files = [{'file': f'a.py'}, {'file': 'b.md'}, {'file': 'c.yaml'},
                 {'file': 'd.json'}, {'file': 'e.rs'}, {'file': 'f.go'}]
        out = _capture(_render_language_breakdown, files, 3)
        self.assertIn('more', out)

    def test_empty_input_produces_no_output(self):
        out = _capture(_render_language_breakdown, [], 5)
        self.assertEqual(out, '')


class TestRenderQualityPulse(unittest.TestCase):

    def test_high_quality_shows_checkmark(self):
        out = _capture(_render_quality_pulse, {'avg_quality_score': 95}, [])
        self.assertIn('✅', out)

    def test_medium_quality_shows_warning(self):
        out = _capture(_render_quality_pulse, {'avg_quality_score': 80}, [])
        self.assertIn('⚠️', out)

    def test_low_quality_shows_x(self):
        out = _capture(_render_quality_pulse, {'avg_quality_score': 65}, [])
        self.assertIn('❌', out)

    def test_shows_score(self):
        out = _capture(_render_quality_pulse, {'avg_quality_score': 88.5}, [])
        self.assertIn('88.5', out)

    def test_shows_critical_count(self):
        hotspots = [{'quality_score': 60}, {'quality_score': 65}]
        out = _capture(_render_quality_pulse, {'avg_quality_score': 70}, hotspots)
        self.assertIn('2 critical', out)

    def test_no_hotspots_shows_no_hotspots(self):
        out = _capture(_render_quality_pulse, {'avg_quality_score': 99}, [])
        self.assertIn('no hotspots', out)

    def test_empty_summary_produces_no_output(self):
        out = _capture(_render_quality_pulse, {}, [])
        self.assertEqual(out, '')


class TestRenderHotspots(unittest.TestCase):

    def _hotspot(self, quality, issues=None):
        return {
            'file': 'src/bad.py',
            'quality_score': quality,
            'hotspot_score': 10,
            'issues': issues or [],
        }

    def test_critical_shows_x_icon(self):
        out = _capture(_render_hotspots, [self._hotspot(65)], 5)
        self.assertIn('❌', out)

    def test_warning_shows_warning_icon(self):
        out = _capture(_render_hotspots, [self._hotspot(78)], 5)
        self.assertIn('⚠️', out)

    def test_shows_quality_score(self):
        out = _capture(_render_hotspots, [self._hotspot(78)], 5)
        self.assertIn('78', out)

    def test_shows_suggest_reveal_command(self):
        out = _capture(_render_hotspots, [self._hotspot(78)], 5)
        self.assertIn('→ reveal', out)

    def test_shows_issues(self):
        out = _capture(_render_hotspots, [self._hotspot(78, ['2 fn >100L'])], 5)
        self.assertIn('2 fn >100L', out)

    def test_respects_top_limit(self):
        hotspots = [self._hotspot(70) for _ in range(10)]
        out = _capture(_render_hotspots, hotspots, 3)
        self.assertEqual(out.count('→ reveal'), 3)

    def test_empty_produces_no_output(self):
        out = _capture(_render_hotspots, [], 5)
        self.assertEqual(out, '')


class TestRenderComplexFunctions(unittest.TestCase):

    def _fn(self, name, cx, file='/base/src/mod.py', line=10, lc=50):
        return {'name': name, 'complexity': cx, 'file': file, 'line': line, 'line_count': lc}

    def test_critical_shows_x_icon(self):
        out = _capture(_render_complex_functions, [self._fn('f', 20)])
        self.assertIn('❌', out)

    def test_warning_shows_warning_icon(self):
        out = _capture(_render_complex_functions, [self._fn('f', 15)])
        self.assertIn('⚠️', out)

    def test_shows_function_name(self):
        out = _capture(_render_complex_functions, [self._fn('parse_me', 12)])
        self.assertIn('parse_me', out)

    def test_shows_complexity(self):
        out = _capture(_render_complex_functions, [self._fn('f', 17)])
        self.assertIn('cx:17', out)

    def test_shows_relative_path_when_base_provided(self):
        base = Path('/base')
        fn = self._fn('f', 12, file='/base/src/mod.py')
        out = _capture(_render_complex_functions, [fn], base_path=base)
        self.assertIn('src/mod.py', out)
        self.assertNotIn('/base/src/mod.py', out)

    def test_shows_absolute_path_when_no_base(self):
        fn = self._fn('f', 12, file='/abs/mod.py')
        out = _capture(_render_complex_functions, [fn])
        self.assertIn('/abs/mod.py', out)

    def test_empty_produces_no_output(self):
        out = _capture(_render_complex_functions, [])
        self.assertEqual(out, '')


class TestRenderGitLog(unittest.TestCase):

    def _commit(self, msg, seconds_ago=3600):
        return {
            'hash': 'abc1234',
            'message': msg,
            'timestamp': int(time.time()) - seconds_ago,
        }

    def test_shows_message(self):
        out = _capture(_render_git_log, [self._commit('feat: add overview')])
        self.assertIn('feat: add overview', out)

    def test_shows_hash(self):
        out = _capture(_render_git_log, [self._commit('msg')])
        self.assertIn('abc1234', out)

    def test_shows_age_label(self):
        out = _capture(_render_git_log, [self._commit('msg', 7200)])
        self.assertIn('ago', out)

    def test_truncates_long_messages(self):
        long_msg = 'a' * 80
        out = _capture(_render_git_log, [self._commit(long_msg)])
        self.assertIn('...', out)
        # Should not show full 80-char message
        self.assertNotIn('a' * 60, out)

    def test_empty_produces_no_output(self):
        out = _capture(_render_git_log, [])
        self.assertEqual(out, '')

    def test_shows_all_commits(self):
        commits = [self._commit(f'msg{i}') for i in range(3)]
        out = _capture(_render_git_log, commits)
        self.assertIn('msg0', out)
        self.assertIn('msg1', out)
        self.assertIn('msg2', out)


# ── Integration: run_overview ──────────────────────────────────────────────────

class TestRunOverview(unittest.TestCase):

    def _make_mocks(self, stats=_STATS_JSON, git=_GIT_JSON, ast=_AST_JSON):
        """Return a side_effect function for subprocess.run."""
        def side_effect(cmd, **kwargs):
            uri = cmd[1] if len(cmd) > 1 else ''
            if 'stats://' in uri:
                return _mock_run(stats)
            if 'git://' in uri:
                return _mock_run(git)
            if 'ast://' in uri:
                return _mock_run(ast)
            return _mock_run('')
        return side_effect

    def test_nonexistent_path_exits_1(self):
        with self.assertRaises(SystemExit) as ctx:
            run_overview(_args(path='/no/such/dir/xyz'))
        self.assertEqual(ctx.exception.code, 1)

    @patch('subprocess.run')
    def test_json_format_outputs_valid_json(self, mock_run):
        import tempfile
        mock_run.side_effect = self._make_mocks()
        with tempfile.TemporaryDirectory() as tmp:
            buf = StringIO()
            with patch('sys.stdout', buf):
                run_overview(_args(path=tmp, format='json'))
            data = json.loads(buf.getvalue())
            self.assertIn('path', data)
            self.assertIn('stats', data)
            self.assertIn('git_log', data)
            self.assertIn('complex_functions', data)

    @patch('subprocess.run')
    def test_text_output_contains_overview_header(self, mock_run):
        import tempfile
        mock_run.side_effect = self._make_mocks()
        with tempfile.TemporaryDirectory() as tmp:
            out = _capture(run_overview, _args(path=tmp))
            self.assertIn('Overview:', out)

    @patch('subprocess.run')
    def test_no_git_skips_git_section(self, mock_run):
        import tempfile
        mock_run.side_effect = self._make_mocks()
        with tempfile.TemporaryDirectory() as tmp:
            out = _capture(run_overview, _args(path=tmp, no_git=True))
            self.assertNotIn('Recent changes', out)
            # git:// should never be called
            for call in mock_run.call_args_list:
                cmd = call[0][0]
                self.assertNotIn('git://', cmd[1] if len(cmd) > 1 else '')

    @patch('subprocess.run')
    def test_text_output_shows_next_steps(self, mock_run):
        import tempfile
        mock_run.side_effect = self._make_mocks()
        with tempfile.TemporaryDirectory() as tmp:
            out = _capture(run_overview, _args(path=tmp))
            self.assertIn('Next steps', out)

    @patch('subprocess.run')
    def test_empty_stats_no_crash(self, mock_run):
        import tempfile
        mock_run.side_effect = self._make_mocks(stats='', git='', ast='')
        with tempfile.TemporaryDirectory() as tmp:
            out = _capture(run_overview, _args(path=tmp))
            self.assertIn('Overview:', out)  # Header always shows


if __name__ == '__main__':
    unittest.main()
