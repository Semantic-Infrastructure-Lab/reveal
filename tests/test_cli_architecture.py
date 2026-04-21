"""Tests for reveal architecture subcommand."""

import json
import sys
import unittest
from argparse import Namespace
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from reveal.cli.commands.architecture import (
    _build_next_commands,
    _compute_risks,
    _is_test_file,
    _relpath,
    _render_brief,
    _render_components,
    _render_core_abstractions,
    _render_entry_points,
    _render_next_commands,
    _render_risks,
    _run_complex_functions,
    _run_imports_analysis,
    create_architecture_parser,
    run_architecture,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _args(**kwargs):
    defaults = {
        'path': '.',
        'top': 5,
        'no_imports': False,
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


_BASE = Path('/project/src')

_IMPORTS_DATA = {
    'entry_points': [
        {'file': '/project/src/main.py', 'fan_in': 0, 'fan_out': 8},
        {'file': '/project/src/cli.py', 'fan_in': 0, 'fan_out': 3},
    ],
    'core_abstractions': [
        {'file': '/project/src/registry.py', 'fan_in': 20, 'fan_out': 2},
        {'file': '/project/src/base.py', 'fan_in': 15, 'fan_out': 1},
        {'file': '/project/src/utils.py', 'fan_in': 9, 'fan_out': 5},
    ],
    'components': [
        {'component': '/project/src/adapters', 'cohesion': 0.75, 'files': 10},
        {'component': '/project/src/rules', 'cohesion': 0.60, 'files': 5},
    ],
    'circular_groups': [
        ['/project/src/a.py', '/project/src/b.py'],
        ['/project/src/x.py', '/project/src/y.py', '/project/src/z.py'],
    ],
}

_COMPLEX_FNS = [
    {'name': 'big_fn', 'complexity': 45, 'file': '/project/src/main.py', 'line': 10},
    {'name': 'medium_fn', 'complexity': 12, 'file': '/project/src/cli.py', 'line': 5},
]


# ── Parser tests ───────────────────────────────────────────────────────────────

class TestCreateArchitectureParser(unittest.TestCase):

    def test_returns_parser(self):
        parser = create_architecture_parser()
        self.assertEqual(parser.prog, 'reveal architecture')

    def test_defaults(self):
        parser = create_architecture_parser()
        args = parser.parse_args([])
        self.assertEqual(args.path, '.')
        self.assertEqual(args.top, 5)
        self.assertFalse(args.no_imports)

    def test_path_argument(self):
        parser = create_architecture_parser()
        args = parser.parse_args(['src/'])
        self.assertEqual(args.path, 'src/')

    def test_no_imports_flag(self):
        parser = create_architecture_parser()
        args = parser.parse_args(['--no-imports'])
        self.assertTrue(args.no_imports)

    def test_top_flag(self):
        parser = create_architecture_parser()
        args = parser.parse_args(['--top', '10'])
        self.assertEqual(args.top, 10)

    def test_format_json(self):
        parser = create_architecture_parser()
        args = parser.parse_args(['--format', 'json'])
        self.assertEqual(args.format, 'json')


# ── _is_test_file ──────────────────────────────────────────────────────────────

class TestIsTestFile(unittest.TestCase):

    def test_test_prefix(self):
        self.assertTrue(_is_test_file('/project/tests/test_main.py'))

    def test_tests_dir(self):
        self.assertTrue(_is_test_file('/project/tests/utils.py'))

    def test_test_dir(self):
        self.assertTrue(_is_test_file('/project/test/helpers.py'))

    def test_normal_file(self):
        self.assertFalse(_is_test_file('/project/src/main.py'))

    def test_file_with_test_in_name(self):
        self.assertFalse(_is_test_file('/project/src/latest.py'))


# ── _relpath ───────────────────────────────────────────────────────────────────

class TestRelpath(unittest.TestCase):

    def test_inside_base(self):
        result = _relpath('/project/src/main.py', Path('/project/src'))
        self.assertEqual(result, 'main.py')

    def test_outside_base(self):
        result = _relpath('/other/lib.py', Path('/project/src'))
        self.assertEqual(result, '/other/lib.py')

    def test_no_base(self):
        result = _relpath('/project/src/main.py', None)
        self.assertEqual(result, '/project/src/main.py')

    def test_subdirectory(self):
        result = _relpath('/project/src/adapters/base.py', Path('/project/src'))
        self.assertEqual(result, 'adapters/base.py')


# ── _compute_risks ─────────────────────────────────────────────────────────────

class TestComputeRisks(unittest.TestCase):

    def test_circular_risk_high(self):
        imports_data = {
            'circular_groups': [[f'/p/file{i}.py' for i in range(15)]],
            'entry_points': [],
            'core_abstractions': [],
        }
        risks = _compute_risks(imports_data, [], Path('/p'))
        self.assertEqual(len(risks), 1)
        self.assertEqual(risks[0]['type'], 'circular')
        self.assertEqual(risks[0]['severity'], 'high')
        self.assertEqual(risks[0]['file_count'], 15)

    def test_circular_risk_medium(self):
        imports_data = {
            'circular_groups': [['/p/a.py', '/p/b.py']],  # 2-file group → medium
            'entry_points': [],
            'core_abstractions': [],
        }
        risks = _compute_risks(imports_data, [], Path('/p'))
        self.assertEqual(risks[0]['severity'], 'medium')

    def test_high_complexity_entry_point(self):
        imports_data = {
            'circular_groups': [],
            'entry_points': [{'file': '/p/main.py', 'fan_in': 0, 'fan_out': 5}],
            'core_abstractions': [],
        }
        complex_fns = [{'name': 'f', 'complexity': 30, 'file': '/p/main.py'}]
        risks = _compute_risks(imports_data, complex_fns, Path('/p'))
        self.assertEqual(len(risks), 1)
        self.assertEqual(risks[0]['type'], 'high_complexity_entry')
        self.assertEqual(risks[0]['complexity'], 30)

    def test_below_complexity_threshold_no_risk(self):
        imports_data = {
            'circular_groups': [],
            'entry_points': [{'file': '/p/main.py', 'fan_in': 0, 'fan_out': 5}],
            'core_abstractions': [],
        }
        complex_fns = [{'name': 'f', 'complexity': 15, 'file': '/p/main.py'}]
        risks = _compute_risks(imports_data, complex_fns, Path('/p'))
        self.assertEqual(len(risks), 0)

    def test_load_bearing_risk(self):
        imports_data = {
            'circular_groups': [],
            'entry_points': [],
            'core_abstractions': [
                {'file': '/p/registry.py', 'fan_in': 25, 'fan_out': 2},
            ],
        }
        risks = _compute_risks(imports_data, [], Path('/p'))
        self.assertEqual(len(risks), 1)
        self.assertEqual(risks[0]['type'], 'load_bearing')
        self.assertEqual(risks[0]['fan_in'], 25)

    def test_below_fan_in_threshold_no_load_bearing(self):
        imports_data = {
            'circular_groups': [],
            'entry_points': [],
            'core_abstractions': [
                {'file': '/p/utils.py', 'fan_in': 3, 'fan_out': 1},
            ],
        }
        risks = _compute_risks(imports_data, [], Path('/p'))
        self.assertEqual(len(risks), 0)

    def test_load_bearing_capped_at_five(self):
        imports_data = {
            'circular_groups': [],
            'entry_points': [],
            'core_abstractions': [
                {'file': f'/p/file{i}.py', 'fan_in': 20 - i, 'fan_out': 1}
                for i in range(10)
            ],
        }
        risks = _compute_risks(imports_data, [], Path('/p'))
        self.assertLessEqual(len(risks), 5)

    def test_empty_imports(self):
        risks = _compute_risks({}, [], Path('/p'))
        self.assertEqual(risks, [])

    def test_combined_risks(self):
        risks = _compute_risks(_IMPORTS_DATA, _COMPLEX_FNS, _BASE)
        types = [r['type'] for r in risks]
        self.assertIn('circular', types)
        self.assertIn('high_complexity_entry', types)
        self.assertIn('load_bearing', types)


# ── _build_next_commands ───────────────────────────────────────────────────────

class TestBuildNextCommands(unittest.TestCase):

    def test_circular_surfaces_imports_command(self):
        risks = [{'type': 'circular', 'severity': 'high', 'representative': '/p/a.py'}]
        cmds = _build_next_commands(Path('/p'), risks, {})
        self.assertTrue(any('imports://' in c for c in cmds))

    def test_cx_entry_surfaces_boundary(self):
        risks = [
            {'type': 'high_complexity_entry', 'severity': 'medium',
             'file': '/p/main.py', 'complexity': 45, 'fan_out': 8},
        ]
        cmds = _build_next_commands(Path('/p'), risks, {})
        self.assertTrue(any('--boundary' in c for c in cmds))
        self.assertTrue(any('main.py' in c for c in cmds))

    def test_worst_cx_entry_chosen(self):
        risks = [
            {'type': 'high_complexity_entry', 'file': '/p/a.py', 'complexity': 20, 'fan_out': 3},
            {'type': 'high_complexity_entry', 'file': '/p/b.py', 'complexity': 50, 'fan_out': 5},
        ]
        cmds = _build_next_commands(Path('/p'), risks, {})
        boundary_cmds = [c for c in cmds if '--boundary' in c]
        self.assertEqual(len(boundary_cmds), 1)
        self.assertIn('b.py', boundary_cmds[0])

    def test_core_abstractions_surfaces_ast_query(self):
        risks = []
        imports_data = {'core_abstractions': [{'file': '/p/base.py', 'fan_in': 10}]}
        cmds = _build_next_commands(Path('/p'), risks, imports_data)
        self.assertTrue(any('ast://' in c and 'complexity>20' in c for c in cmds))

    def test_load_bearing_surfaces_reveal_file(self):
        risks = [
            {'type': 'load_bearing', 'file': '/p/registry.py', 'fan_in': 20},
        ]
        cmds = _build_next_commands(Path('/p'), risks, {})
        self.assertTrue(any('registry.py' in c for c in cmds))

    def test_fallback_when_no_risks(self):
        cmds = _build_next_commands(Path('/p'), [], {})
        self.assertGreater(len(cmds), 0)

    def test_highest_fan_in_load_bearing_chosen(self):
        risks = [
            {'type': 'load_bearing', 'file': '/p/a.py', 'fan_in': 10},
            {'type': 'load_bearing', 'file': '/p/b.py', 'fan_in': 30},
        ]
        cmds = _build_next_commands(Path('/p'), risks, {})
        reveal_cmds = [c for c in cmds if '--boundary' not in c and 'imports://' not in c and 'ast://' not in c]
        self.assertTrue(any('b.py' in c for c in reveal_cmds))


# ── Render functions ───────────────────────────────────────────────────────────

class TestRenderEntryPoints(unittest.TestCase):

    def test_renders_entry_points(self):
        eps = [{'file': '/p/main.py', 'fan_in': 0, 'fan_out': 8}]
        out = _capture(_render_entry_points, eps, 5, Path('/p'))
        self.assertIn('main.py', out)
        self.assertIn('fan-out', out)
        self.assertIn('8', out)

    def test_empty_produces_no_output(self):
        out = _capture(_render_entry_points, [], 5, Path('/p'))
        self.assertEqual(out, '')

    def test_respects_top(self):
        eps = [{'file': f'/p/file{i}.py', 'fan_in': 0, 'fan_out': i} for i in range(10)]
        out = _capture(_render_entry_points, eps, 3, Path('/p'))
        self.assertEqual(out.count('fan-out'), 3)


class TestRenderCoreAbstractions(unittest.TestCase):

    def test_renders_abstractions(self):
        core = [{'file': '/p/registry.py', 'fan_in': 20, 'fan_out': 2}]
        out = _capture(_render_core_abstractions, core, 5, Path('/p'))
        self.assertIn('registry.py', out)
        self.assertIn('fan-in', out)
        self.assertIn('20', out)

    def test_filters_init_py(self):
        core = [
            {'file': '/p/__init__.py', 'fan_in': 15, 'fan_out': 0},
            {'file': '/p/base.py', 'fan_in': 10, 'fan_out': 1},
        ]
        out = _capture(_render_core_abstractions, core, 5, Path('/p'))
        self.assertNotIn('__init__.py', out)
        self.assertIn('base.py', out)

    def test_empty_produces_no_output(self):
        out = _capture(_render_core_abstractions, [], 5, Path('/p'))
        self.assertEqual(out, '')


class TestRenderComponents(unittest.TestCase):

    def test_renders_components(self):
        comps = [{'component': '/p/adapters', 'cohesion': 0.75, 'files': 10}]
        out = _capture(_render_components, comps, 5, Path('/p'))
        self.assertIn('adapters', out)
        self.assertIn('0.75', out)
        self.assertIn('10 files', out)

    def test_renders_cohesion_bar(self):
        comps = [{'component': '/p/core', 'cohesion': 1.0, 'files': 3}]
        out = _capture(_render_components, comps, 5, Path('/p'))
        self.assertIn('██████████', out)

    def test_empty_produces_no_output(self):
        out = _capture(_render_components, [], 5, Path('/p'))
        self.assertEqual(out, '')


class TestRenderRisks(unittest.TestCase):

    def test_renders_risks(self):
        risks = [{'description': '41-file circular group', 'detail': 'a.py + 40 more'}]
        out = _capture(_render_risks, risks)
        self.assertIn('41-file circular group', out)
        self.assertIn('a.py + 40 more', out)
        self.assertIn('⚠', out)

    def test_shows_count(self):
        risks = [
            {'description': 'risk one', 'detail': ''},
            {'description': 'risk two', 'detail': ''},
        ]
        out = _capture(_render_risks, risks)
        self.assertIn('2 found', out)

    def test_empty_produces_no_output(self):
        out = _capture(_render_risks, [])
        self.assertEqual(out, '')

    def test_no_detail_no_parens(self):
        risks = [{'description': 'something risky', 'detail': ''}]
        out = _capture(_render_risks, risks)
        self.assertNotIn('()', out)


class TestRenderNextCommands(unittest.TestCase):

    def test_renders_commands(self):
        cmds = ["reveal 'imports://src?circular'", "reveal src/main.py --boundary"]
        out = _capture(_render_next_commands, cmds)
        self.assertIn('imports://', out)
        self.assertIn('--boundary', out)

    def test_empty_produces_no_output(self):
        out = _capture(_render_next_commands, [])
        self.assertEqual(out, '')


# ── run_architecture ───────────────────────────────────────────────────────────

class TestRunArchitecture(unittest.TestCase):

    def test_invalid_path_exits(self):
        args = _args(path='/nonexistent/path/that/does/not/exist')
        with self.assertRaises(SystemExit):
            run_architecture(args)

    def test_no_imports_skips_analysis(self):
        args = _args(path='/tmp', no_imports=True)
        with patch('reveal.cli.commands.architecture._run_complex_functions', return_value=[]):
            with patch('reveal.cli.commands.architecture._run_imports_analysis') as mock_imports:
                with patch('reveal.cli.commands.architecture._render_brief'):
                    run_architecture(args)
        mock_imports.assert_not_called()

    def test_json_output(self):
        args = _args(path='/tmp', format='json')
        mock_complex = [{'name': 'f', 'complexity': 25, 'file': '/tmp/a.py'}]
        with patch('reveal.cli.commands.architecture._run_complex_functions', return_value=mock_complex):
            with patch('reveal.cli.commands.architecture._run_imports_analysis', return_value=_IMPORTS_DATA):
                out = _capture(run_architecture, args)

        data = json.loads(out)
        self.assertIn('path', data)
        self.assertIn('facts', data)
        self.assertIn('risks', data)
        self.assertIn('next_commands', data)

    def test_json_facts_structure(self):
        args = _args(path='/tmp', format='json')
        with patch('reveal.cli.commands.architecture._run_complex_functions', return_value=[]):
            with patch('reveal.cli.commands.architecture._run_imports_analysis', return_value=_IMPORTS_DATA):
                out = _capture(run_architecture, args)

        facts = json.loads(out)['facts']
        self.assertIn('entry_points', facts)
        self.assertIn('core_abstractions', facts)
        self.assertIn('components', facts)
        self.assertIn('circular_groups', facts)

    def test_text_output_renders(self):
        args = _args(path='/tmp')
        with patch('reveal.cli.commands.architecture._run_complex_functions', return_value=_COMPLEX_FNS):
            with patch('reveal.cli.commands.architecture._run_imports_analysis', return_value=_IMPORTS_DATA):
                out = _capture(run_architecture, args)

        self.assertIn('Architecture Brief', out)

    def test_text_output_sections(self):
        args = _args(path='/tmp')
        with patch('reveal.cli.commands.architecture._run_complex_functions', return_value=_COMPLEX_FNS):
            with patch('reveal.cli.commands.architecture._run_imports_analysis', return_value=_IMPORTS_DATA):
                out = _capture(run_architecture, args)

        self.assertIn('Entry Points', out)
        self.assertIn('Core Abstractions', out)
        self.assertIn('Components', out)
        self.assertIn('Risks', out)
        self.assertIn('Next Commands', out)


# ── _run_complex_functions ─────────────────────────────────────────────────────

class TestRunComplexFunctions(unittest.TestCase):

    def test_returns_list_on_failure(self):
        with patch('reveal.adapters.ast.AstAdapter', side_effect=Exception('fail')):
            result = _run_complex_functions(Path('/p'), 5)
        self.assertEqual(result, [])


# ── _run_imports_analysis ──────────────────────────────────────────────────────

class TestRunImportsAnalysis(unittest.TestCase):

    def test_returns_empty_on_failure(self):
        with patch('reveal.adapters.imports.ImportsAdapter', side_effect=Exception('fail')):
            result = _run_imports_analysis(Path('/p'))
        self.assertEqual(result, {})

    def test_filters_init_from_entry_points(self):
        mock_adapter = MagicMock()
        mock_adapter._format_fan_in.return_value = {'entries': []}
        mock_adapter._format_entrypoints.return_value = {'entries': [
            {'file': '/p/__init__.py', 'fan_in': 0, 'fan_out': 3},
            {'file': '/p/main.py', 'fan_in': 0, 'fan_out': 5},
        ]}
        mock_adapter._format_components.return_value = {'components': []}
        mock_adapter._format_circular.return_value = {'cycles': [], 'count': 0}

        with patch('reveal.adapters.imports.ImportsAdapter', return_value=mock_adapter):
            result = _run_imports_analysis(Path('/p'))

        ep_files = [e['file'] for e in result.get('entry_points', [])]
        self.assertNotIn('/p/__init__.py', ep_files)
        self.assertIn('/p/main.py', ep_files)

    def test_filters_test_files_from_entry_points(self):
        mock_adapter = MagicMock()
        mock_adapter._format_fan_in.return_value = {'entries': []}
        mock_adapter._format_entrypoints.return_value = {'entries': [
            {'file': '/p/tests/test_main.py', 'fan_in': 0, 'fan_out': 2},
            {'file': '/p/main.py', 'fan_in': 0, 'fan_out': 5},
        ]}
        mock_adapter._format_components.return_value = {'components': []}
        mock_adapter._format_circular.return_value = {'cycles': [], 'count': 0}

        with patch('reveal.adapters.imports.ImportsAdapter', return_value=mock_adapter):
            result = _run_imports_analysis(Path('/p'))

        ep_files = [e['file'] for e in result.get('entry_points', [])]
        self.assertNotIn('/p/tests/test_main.py', ep_files)


if __name__ == '__main__':
    unittest.main()
