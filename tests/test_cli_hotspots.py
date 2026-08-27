"""Tests for reveal hotspots subcommand."""

import json
import sys
import tempfile
import unittest
from argparse import Namespace
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from reveal.adapters.hotspots import (
    HotspotsAdapter,
    _build_test_name_index,
    _is_covered,
    _provenance_for_file,
    _render_file_hotspots,
    _render_function_hotspots,
    _render_report,
    _render_summary,
    _run_file_hotspots,
    _run_function_hotspots,
)
from reveal.cli.commands.hotspots import (
    create_hotspots_parser,
    run_hotspots,
)

# BACK-1149: component-layer test -- calls a reveal.cli.* handler function directly, not through reveal.main
pytestmark = pytest.mark.component


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
    """_run_file_hotspots: StatsAdapter mocked, composed via adapter.compose()."""

    def setUp(self):
        self.adapter = HotspotsAdapter('.')

    @patch('reveal.adapters.stats.StatsAdapter.get_structure')
    def test_returns_hotspots_list(self, mock_gs):
        mock_gs.return_value = {'hotspots': [_file_hotspot('a.py', 60), _file_hotspot('b.py', 75)]}
        result = _run_file_hotspots(self.adapter, Path('.'), top=10)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['file'], 'a.py')

    @patch('reveal.adapters.stats.StatsAdapter.get_structure')
    def test_respects_top_limit(self, mock_gs):
        mock_gs.return_value = {'hotspots': [_file_hotspot(f'f{i}.py', 50) for i in range(20)]}
        result = _run_file_hotspots(self.adapter, Path('.'), top=5)
        self.assertEqual(len(result), 5)

    @patch('reveal.adapters.stats.StatsAdapter.get_structure')
    def test_missing_hotspots_key_returns_empty(self, mock_gs):
        mock_gs.return_value = {'other': []}
        result = _run_file_hotspots(self.adapter, Path('.'), top=10)
        self.assertEqual(result, [])

    @patch('reveal.adapters.stats.StatsAdapter.get_structure', side_effect=Exception("boom"))
    def test_exception_returns_empty(self, _mock):
        result = _run_file_hotspots(self.adapter, Path('.'), top=10)
        self.assertEqual(result, [])

    @patch('reveal.adapters.stats.StatsAdapter.get_structure', side_effect=Exception("boom"))
    def test_exception_records_attributed_error(self, _mock):
        """BACK-984: a crashed sub-scan must not be silently indistinguishable
        from a clean empty result — it records an attributed error."""
        _run_file_hotspots(self.adapter, Path('.'), top=10)
        meta = self.adapter.composed_meta()
        self.assertIsNotNone(meta)
        self.assertEqual(len(meta['errors']), 1)
        self.assertIn('boom', meta['errors'][0]['message'])


class TestGetStructureFalsyDefaults(unittest.TestCase):
    """BACK-985: '?top=0'/'?min_complexity=0' must be respected, not silently
    replaced by the adapter's default."""

    @patch('reveal.adapters.ast.AstAdapter.get_structure')
    @patch('reveal.adapters.stats.StatsAdapter.get_structure')
    def test_top_zero_returns_zero_hotspots(self, mock_stats, mock_ast):
        mock_stats.return_value = {'hotspots': [_file_hotspot('a.py', 60)]}
        mock_ast.return_value = {'results': [_fn_hotspot('foo', 15)]}
        adapter = HotspotsAdapter('.', 'top=0')
        result = adapter.get_structure()
        self.assertEqual(result['file_hotspots'], [])
        self.assertEqual(result['function_hotspots'], [])

    @patch('reveal.adapters.ast.AstAdapter.__init__', return_value=None)
    @patch('reveal.adapters.ast.AstAdapter.get_structure', return_value={'results': []})
    def test_min_complexity_zero_is_respected(self, _mock_gs, mock_init):
        adapter = HotspotsAdapter('.', 'min_complexity=0')
        adapter.get_structure()
        _resource, query = mock_init.call_args.args
        self.assertTrue(query.startswith('complexity>=0&'))


class TestRunFunctionHotspots(unittest.TestCase):
    """_run_function_hotspots: AstAdapter mocked, composed via adapter.compose()."""

    def setUp(self):
        self.adapter = HotspotsAdapter('.')

    @patch('reveal.adapters.ast.AstAdapter.get_structure')
    def test_returns_results_list(self, mock_gs):
        mock_gs.return_value = {'results': [_fn_hotspot('foo', 15), _fn_hotspot('bar', 12)]}
        result = _run_function_hotspots(self.adapter, Path('/tmp'), min_complexity=10, top=10)
        self.assertEqual(len(result), 2)

    @patch('reveal.adapters.ast.AstAdapter.get_structure')
    def test_falls_back_to_elements_key(self, mock_gs):
        mock_gs.return_value = {'elements': [_fn_hotspot('baz', 11)]}
        result = _run_function_hotspots(self.adapter, Path('/tmp'), min_complexity=10, top=10)
        self.assertEqual(len(result), 1)

    @patch('reveal.adapters.ast.AstAdapter.get_structure')
    def test_respects_top_limit(self, mock_gs):
        mock_gs.return_value = {'results': [_fn_hotspot(f'fn{i}', 10 + i) for i in range(15)]}
        result = _run_function_hotspots(self.adapter, Path('/tmp'), min_complexity=10, top=5)
        self.assertEqual(len(result), 5)

    @patch('reveal.adapters.ast.AstAdapter.get_structure', side_effect=Exception("oops"))
    def test_exception_returns_empty(self, _mock):
        result = _run_function_hotspots(self.adapter, Path('/tmp'), min_complexity=10, top=10)
        self.assertEqual(result, [])

    def test_uses_ge_operator_not_off_by_one_hack(self):
        """BACK-984: query built with 'complexity>=N' directly — the filter
        parser supports >= natively, so the old 'complexity>{N-1}' hack to
        emulate it is no longer needed."""
        with patch('reveal.adapters.ast.AstAdapter.__init__', return_value=None) as mock_init, \
             patch('reveal.adapters.ast.AstAdapter.get_structure', return_value={'results': []}):
            _run_function_hotspots(self.adapter, Path('/tmp'), min_complexity=10, top=10)
            called_query = mock_init.call_args.args[1]
            self.assertIn('complexity>=10', called_query)


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
            patch('reveal.adapters.hotspots._run_file_hotspots',
                  return_value=file_hotspots or []),
            patch('reveal.adapters.hotspots._run_function_hotspots',
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
            with patch('reveal.adapters.hotspots._run_file_hotspots') as mock_file:
                with patch('reveal.adapters.hotspots._run_function_hotspots', return_value=[]):
                    buf = StringIO()
                    with patch('sys.stdout', buf):
                        run_hotspots(args)
                    mock_file.assert_not_called()

    def test_files_only_skips_function_hotspots(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            args = _args(path=d, files_only=True)
            with patch('reveal.adapters.hotspots._run_file_hotspots', return_value=[]):
                with patch('reveal.adapters.hotspots._run_function_hotspots') as mock_fn:
                    buf = StringIO()
                    with patch('sys.stdout', buf):
                        run_hotspots(args)
                    mock_fn.assert_not_called()


class TestBuildTestNameIndex(unittest.TestCase):
    """_build_test_name_index heuristic tests."""

    def test_finds_test_functions_in_tests_dir(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            tests_dir = os.path.join(d, 'tests')
            os.makedirs(tests_dir)
            Path(os.path.join(tests_dir, 'test_foo.py')).write_text(
                'def test_calculate():\n    pass\ndef test_render():\n    pass\n'
            )
            index = _build_test_name_index(Path(d))
            self.assertIn('calculate', index)
            self.assertIn('render', index)

    def test_finds_test_functions_in_test_dir(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            test_dir = os.path.join(d, 'test')
            os.makedirs(test_dir)
            Path(os.path.join(test_dir, 'test_bar.py')).write_text(
                'def test_parse_input():\n    pass\n'
            )
            index = _build_test_name_index(Path(d))
            self.assertIn('parse_input', index)

    def test_no_test_dir_returns_empty(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            index = _build_test_name_index(Path(d))
            self.assertEqual(index, set())

    def test_ignores_non_test_functions(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            tests_dir = os.path.join(d, 'tests')
            os.makedirs(tests_dir)
            Path(os.path.join(tests_dir, 'test_x.py')).write_text(
                'def setup():\n    pass\ndef test_something():\n    pass\n'
            )
            index = _build_test_name_index(Path(d))
            self.assertNotIn('setup', index)
            self.assertIn('something', index)

    def test_includes_module_name_from_test_filename(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            tests_dir = os.path.join(d, 'tests')
            os.makedirs(tests_dir)
            Path(os.path.join(tests_dir, 'test_liquidity_sweep.py')).write_text(
                'def test_bearish_sweep_of_session_high(): pass\n'
            )
            index = _build_test_name_index(Path(d))
            self.assertIn('liquidity_sweep', index)

    def test_module_name_not_added_for_non_test_prefix_files(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            tests_dir = os.path.join(d, 'tests')
            os.makedirs(tests_dir)
            Path(os.path.join(tests_dir, 'conftest.py')).write_text('pass\n')
            index = _build_test_name_index(Path(d))
            self.assertNotIn('conftest', index)

    def test_finds_test_functions_in_spec_dir(self):
        # BACK-1199: spec/ (RSpec/Jest convention) is part of the shared
        # canonical vocabulary, same as tests/ and test/.
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            spec_dir = os.path.join(d, 'spec')
            os.makedirs(spec_dir)
            Path(os.path.join(spec_dir, 'test_baz.py')).write_text(
                'def test_validate_input():\n    pass\n'
            )
            index = _build_test_name_index(Path(d))
            self.assertIn('validate_input', index)


class TestRenderFunctionHotspotsWithCoverage(unittest.TestCase):
    """_render_function_hotspots with test_index coverage overlay."""

    def _capture(self, fns, test_index=None):
        buf = StringIO()
        with patch('sys.stdout', buf):
            _render_function_hotspots(fns, test_index=test_index)
        return buf.getvalue()

    def test_no_index_shows_no_coverage_indicators(self):
        out = self._capture([_fn_hotspot('foo', 12)])
        self.assertNotIn('✅', out)
        self.assertNotIn('⚪', out)

    def test_covered_function_shows_checkmark(self):
        out = self._capture([_fn_hotspot('foo', 12)], test_index={'foo'})
        self.assertIn('✅', out)

    def test_uncovered_function_shows_circle(self):
        out = self._capture([_fn_hotspot('bar', 12)], test_index={'something_else'})
        self.assertIn('⚪', out)

    def test_legend_shown_when_index_provided(self):
        out = self._capture([_fn_hotspot('fn', 12)], test_index=set())
        self.assertIn('test found', out)

    def test_no_legend_without_index(self):
        out = self._capture([_fn_hotspot('fn', 12)])
        self.assertNotIn('test found', out)

    def test_module_level_coverage_shows_checkmark(self):
        # fn named 'generate' in 'liquidity_sweep.py' — index has 'liquidity_sweep' (module hit)
        fn = _fn_hotspot('generate', 12, file='src/liquidity_sweep.py')
        out = self._capture([fn], test_index={'liquidity_sweep'})
        self.assertIn('✅', out)

    def test_no_module_or_function_hit_shows_circle(self):
        fn = _fn_hotspot('generate', 12, file='src/liquidity_sweep.py')
        out = self._capture([fn], test_index={'unrelated_module'})
        self.assertIn('⚪', out)


class TestRunHotspotsTestCoverage(unittest.TestCase):
    """run_hotspots annotates fn_hotspots with has_test_hint."""

    def test_has_test_hint_annotated_on_json(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            tests_dir = os.path.join(d, 'tests')
            os.makedirs(tests_dir)
            Path(os.path.join(tests_dir, 'test_x.py')).write_text('def test_my_func(): pass\n')
            fn = _fn_hotspot('my_func', 15)
            args = _args(path=d, format='json')
            with patch('reveal.adapters.hotspots._run_file_hotspots', return_value=[]):
                with patch('reveal.adapters.hotspots._run_function_hotspots', return_value=[fn]):
                    buf = StringIO()
                    with patch('sys.stdout', buf):
                        run_hotspots(args)
                    data = json.loads(buf.getvalue())
                    self.assertTrue(data['function_hotspots'][0]['has_test_hint'])

    def test_has_test_hint_via_module_name(self):
        # Function 'generate' in 'liquidity_sweep.py' — test file is test_liquidity_sweep.py
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            tests_dir = os.path.join(d, 'tests')
            os.makedirs(tests_dir)
            Path(os.path.join(tests_dir, 'test_liquidity_sweep.py')).write_text(
                'def test_bearish_sweep_of_session_high(): pass\n'
            )
            fn = _fn_hotspot('generate', 15, file='src/liquidity_sweep.py')
            args = _args(path=d, format='json')
            with patch('reveal.adapters.hotspots._run_file_hotspots', return_value=[]):
                with patch('reveal.adapters.hotspots._run_function_hotspots', return_value=[fn]):
                    buf = StringIO()
                    with patch('sys.stdout', buf):
                        run_hotspots(args)
                    data = json.loads(buf.getvalue())
                    self.assertTrue(data['function_hotspots'][0]['has_test_hint'])

    def test_files_only_skips_test_index(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            args = _args(path=d, files_only=True)
            with patch('reveal.adapters.hotspots._run_file_hotspots', return_value=[]):
                with patch('reveal.adapters.hotspots._build_test_name_index') as mock_idx:
                    buf = StringIO()
                    with patch('sys.stdout', buf):
                        run_hotspots(args)
                    mock_idx.assert_not_called()


class TestHotspotsTopAppliesToFileHotspots:
    """BACK-1179 end-to-end: hotspots://?top=N reached function_hotspots
    (via AstAdapter's own limit) but silently had no effect on
    file_hotspots — StatsAdapter's identify_hotspots() hardcoded a top-10
    cap regardless of what HotspotsAdapter asked for."""

    # 16 levels of nesting -> deep_nesting flags well past identify_hotspots'
    # >4 threshold, so each file scores as a genuine hotspot on its own.
    DEEPLY_NESTED_CODE = "def f(x):\n" + "".join(
        "    " * (i + 1) + f"if x > {i}:\n" for i in range(15)
    ) + "    " * 16 + "return x\n    return 0\n"

    @pytest.fixture
    def fifteen_hotspot_files(self, tmp_path):
        for i in range(15):
            (tmp_path / f"m{i}.py").write_text(self.DEEPLY_NESTED_CODE)
        return tmp_path

    def test_default_top_caps_file_hotspots_at_ten(self, fifteen_hotspot_files):
        adapter = HotspotsAdapter(str(fifteen_hotspot_files))
        result = adapter.get_structure()
        assert len(result['file_hotspots']) == 10

    def test_top_query_param_expands_file_hotspots_past_ten(self, fifteen_hotspot_files):
        adapter = HotspotsAdapter(str(fifteen_hotspot_files), 'top=15')
        result = adapter.get_structure()
        assert len(result['file_hotspots']) == 15


class TestIsCovered(unittest.TestCase):
    """Unit tests for _is_covered coverage heuristic."""

    def test_exact_name_match(self):
        self.assertTrue(_is_covered('my_fn', '', {'my_fn'}))

    def test_bare_name_match_strips_leading_underscore(self):
        self.assertTrue(_is_covered('_my_fn', '', {'my_fn'}))

    def test_double_underscore_stripped(self):
        self.assertTrue(_is_covered('__init', '', {'init'}))

    def test_module_name_match(self):
        self.assertTrue(_is_covered('some_fn', 'reveal/utils/helper.py', {'helper'}))

    def test_test_index_starts_with_bare(self):
        # test index has 'my_fn_extra' which starts with bare 'my_fn'
        self.assertTrue(_is_covered('_my_fn', '', {'my_fn_extra'}))

    def test_reverse_containment_endswith(self):
        # bare='get_file_blame', index has 'file_blame' (len>=5)
        self.assertTrue(_is_covered('get_file_blame', '', {'file_blame'}))

    def test_reverse_containment_startswith(self):
        self.assertTrue(_is_covered('file_blame_get', '', {'file_blame'}))

    def test_reverse_containment_contains(self):
        self.assertTrue(_is_covered('get_file_blame_fast', '', {'file_blame'}))


class TestProvenanceForFile(unittest.TestCase):
    """BACK-1195: each hotspot entry tagged with its provenance
    classification so a reader can discount vendored/generated/test noise
    in place. Relativizes first since function_hotspots' 'file' arrives
    absolute (from AstAdapter) while file_hotspots' arrives relative (from
    StatsAdapter) -- both must classify correctly either way."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.base = Path(self.tmp)

    def test_none_returns_none(self):
        self.assertIsNone(_provenance_for_file(None, self.base))

    def test_relative_vendor_path(self):
        self.assertEqual(_provenance_for_file('vendor/lib/thing.rb', self.base), 'vendor')

    def test_absolute_test_path(self):
        abs_path = str(self.base / 'spec' / 'thing_spec.rb')
        self.assertEqual(_provenance_for_file(abs_path, self.base), 'test')

    def test_first_party_path_is_none(self):
        self.assertIsNone(_provenance_for_file('src/app.py', self.base))

    def test_no_match_returns_false(self):
        self.assertFalse(_is_covered('obscure_fn', 'reveal/core.py', {'other_fn', 'helper'}))

    def test_short_index_words_ignored_in_reverse(self):
        # 'ab' is len<5, should not match via reverse rule
        self.assertFalse(_is_covered('get_ab_fn', '', {'ab'}))

    def test_empty_index_returns_false(self):
        self.assertFalse(_is_covered('fn', 'file.py', set()))

    def test_empty_loc_no_crash(self):
        self.assertFalse(_is_covered('fn', '', {'other'}))


if __name__ == '__main__':
    unittest.main()
