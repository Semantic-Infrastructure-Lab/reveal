"""Tests for reveal deps subcommand."""

import json
import sys
import unittest
from argparse import Namespace
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from reveal.cli.commands.deps import (
    _analyse_imports,
    _local_package_names,
    _render_circular,
    _render_deps,
    _render_external_packages,
    _render_next_steps,
    _render_summary,
    _render_top_importers,
    _render_unused,
    _run_base,
    _run_circular,
    _run_unused,
    create_deps_parser,
    run_deps,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _args(**kwargs):
    defaults = {
        'path': '.',
        'top': 10,
        'no_unused': False,
        'no_circular': False,
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



def _make_import(module, is_relative=False, names=None, line=1):
    return {
        'file': '/project/src/mod.py',
        'line': line,
        'module': module,
        'names': names or [],
        'type': 'from_import' if names else 'import',
        'is_relative': is_relative,
        'alias': None,
    }


_BASE_JSON = json.dumps({
    'contract_version': '1.0',
    'type': 'imports',
    'source': '/project',
    'source_type': 'directory',
    'files': {
        '/project/src/main.py': [
            _make_import('os'),
            _make_import('yaml'),
            _make_import('requests'),
        ],
        '/project/src/utils.py': [
            _make_import('typing', names=['Optional']),
            _make_import('requests'),
            _make_import('.helpers', is_relative=True),
        ],
    },
    'metadata': {},
})

_CIRCULAR_JSON = json.dumps({
    'contract_version': '1.0',
    'type': 'imports_circular',
    'source': '/project',
    'source_type': 'directory',
    'cycles': [
        ['/project/src/a.py', '/project/src/b.py', '/project/src/a.py'],
        ['/project/src/c.py', '/project/src/d.py', '/project/src/c.py'],
    ],
    'count': 2,
    'metadata': {},
})

_UNUSED_JSON = json.dumps({
    'contract_version': '1.0',
    'type': 'imports_unused',
    'source': '/project',
    'source_type': 'directory',
    'unused': [
        _make_import('os', names=['path'], line=5),
        _make_import('typing', names=['List'], line=3),
    ],
    'count': 2,
    'metadata': {},
})


# ── Parser tests ───────────────────────────────────────────────────────────────

class TestCreateDepsParser(unittest.TestCase):

    def test_returns_parser(self):
        parser = create_deps_parser()
        self.assertEqual(parser.prog, 'reveal deps')

    def test_defaults(self):
        parser = create_deps_parser()
        args = parser.parse_args([])
        self.assertEqual(args.path, '.')
        self.assertEqual(args.top, 10)
        self.assertFalse(args.no_unused)
        self.assertFalse(args.no_circular)

    def test_path_positional(self):
        parser = create_deps_parser()
        args = parser.parse_args(['./src'])
        self.assertEqual(args.path, './src')

    def test_top_flag(self):
        parser = create_deps_parser()
        args = parser.parse_args(['--top', '20'])
        self.assertEqual(args.top, 20)

    def test_no_unused_flag(self):
        parser = create_deps_parser()
        args = parser.parse_args(['--no-unused'])
        self.assertTrue(args.no_unused)

    def test_no_circular_flag(self):
        parser = create_deps_parser()
        args = parser.parse_args(['--no-circular'])
        self.assertTrue(args.no_circular)


# ── _local_package_names tests ─────────────────────────────────────────────────

class TestLocalPackageNames(unittest.TestCase):

    def test_includes_directory_name(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            result = _local_package_names(Path(tmp))
            self.assertIn(Path(tmp).name, result)

    def test_includes_subdirectory_with_init(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / 'mypackage'
            pkg.mkdir()
            (pkg / '__init__.py').touch()
            result = _local_package_names(Path(tmp))
            self.assertIn('mypackage', result)

    def test_excludes_subdirectory_without_init(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'notapackage').mkdir()
            result = _local_package_names(Path(tmp))
            self.assertNotIn('notapackage', result)


# ── _analyse_imports tests ─────────────────────────────────────────────────────

class TestAnalyseImports(unittest.TestCase):

    def _files(self, imports_by_file):
        return imports_by_file

    def test_counts_total_imports(self):
        files = {
            '/proj/a.py': [_make_import('os'), _make_import('yaml')],
            '/proj/b.py': [_make_import('sys')],
        }
        result = _analyse_imports(files, Path('/proj'))
        self.assertEqual(result['total_imports'], 3)

    def test_counts_total_files(self):
        files = {
            '/proj/a.py': [_make_import('os')],
            '/proj/b.py': [],
        }
        result = _analyse_imports(files, Path('/proj'))
        self.assertEqual(result['total_files'], 2)

    def test_stdlib_not_in_external(self):
        files = {'/proj/a.py': [_make_import('os'), _make_import('sys')]}
        result = _analyse_imports(files, Path('/proj'))
        ext_names = [p for p, _ in result['external_packages']]
        self.assertNotIn('os', ext_names)
        self.assertNotIn('sys', ext_names)

    def test_third_party_in_external(self):
        files = {'/proj/a.py': [_make_import('requests'), _make_import('yaml')]}
        result = _analyse_imports(files, Path('/proj'))
        ext_names = [p for p, _ in result['external_packages']]
        self.assertIn('requests', ext_names)
        self.assertIn('yaml', ext_names)

    def test_relative_imports_counted(self):
        files = {'/proj/a.py': [_make_import('.utils', is_relative=True)]}
        result = _analyse_imports(files, Path('/proj'))
        self.assertEqual(result['relative_count'], 1)

    def test_self_imports_treated_as_internal(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / 'myapp'
            pkg.mkdir()
            (pkg / '__init__.py').touch()
            # Import of 'myapp' from outside should be treated as local
            files = {'/other/x.py': [_make_import('myapp')]}
            result = _analyse_imports(files, Path(tmp))
            ext_names = [p for p, _ in result['external_packages']]
            self.assertNotIn('myapp', ext_names)

    def test_top_importers_sorted_by_count(self):
        files = {
            '/proj/heavy.py': [_make_import('os'), _make_import('sys'), _make_import('yaml')],
            '/proj/light.py': [_make_import('os')],
        }
        result = _analyse_imports(files, Path('/proj'))
        self.assertEqual(result['top_importers'][0]['count'], 3)

    def test_external_packages_sorted_by_usage(self):
        files = {
            '/proj/a.py': [_make_import('requests'), _make_import('requests'), _make_import('yaml')],
        }
        result = _analyse_imports(files, Path('/proj'))
        packages = result['external_packages']
        self.assertEqual(packages[0][0], 'requests')
        self.assertEqual(packages[0][1], 2)


# ── Data collector tests ───────────────────────────────────────────────────────

class TestRunBase(unittest.TestCase):

    @patch('reveal.cli.commands.deps.ImportsAdapter')
    def test_returns_adapter_data(self, MockAdapter):
        MockAdapter.return_value.get_structure.return_value = json.loads(_BASE_JSON)
        result = _run_base(Path('/project'))
        self.assertIn('files', result)
        MockAdapter.assert_called_once_with('/project')

    @patch('reveal.cli.commands.deps.ImportsAdapter')
    def test_exception_returns_empty_dict(self, MockAdapter):
        MockAdapter.return_value.get_structure.side_effect = Exception('fail')
        self.assertEqual(_run_base(Path('/project')), {})


class TestRunCircular(unittest.TestCase):

    @patch('reveal.cli.commands.deps.ImportsAdapter')
    def test_returns_cycles(self, MockAdapter):
        MockAdapter.return_value.get_structure.return_value = json.loads(_CIRCULAR_JSON)
        result = _run_circular(Path('/project'))
        self.assertEqual(result['count'], 2)
        self.assertEqual(len(result['cycles']), 2)
        MockAdapter.assert_called_once_with('/project', 'circular')

    @patch('reveal.cli.commands.deps.ImportsAdapter')
    def test_exception_returns_empty_dict(self, MockAdapter):
        MockAdapter.return_value.get_structure.side_effect = Exception('fail')
        self.assertEqual(_run_circular(Path('/project')), {})


class TestRunUnused(unittest.TestCase):

    @patch('reveal.cli.commands.deps.ImportsAdapter')
    def test_returns_unused_list(self, MockAdapter):
        MockAdapter.return_value.get_structure.return_value = json.loads(_UNUSED_JSON)
        result = _run_unused(Path('/project'))
        self.assertEqual(len(result), 2)
        MockAdapter.assert_called_once_with('/project', 'unused')

    @patch('reveal.cli.commands.deps.ImportsAdapter')
    def test_exception_returns_empty_list(self, MockAdapter):
        MockAdapter.return_value.get_structure.side_effect = Exception('fail')
        self.assertEqual(_run_unused(Path('/project')), [])

    @patch('reveal.cli.commands.deps.ImportsAdapter')
    def test_missing_unused_key_returns_empty(self, MockAdapter):
        MockAdapter.return_value.get_structure.return_value = {'other': 'data'}
        self.assertEqual(_run_unused(Path('/project')), [])


# ── Renderer tests ─────────────────────────────────────────────────────────────

class TestRenderSummary(unittest.TestCase):

    def _analysis(self, **kw):
        base = {
            'total_files': 10,
            'total_imports': 50,
            'relative_count': 5,
            'external_packages': [('requests', 3)],
            'stdlib_packages': [('os', 5)],
            'top_importers': [],
        }
        base.update(kw)
        return base

    def test_shows_file_count(self):
        out = _capture(_render_summary, self._analysis(), 0, 0)
        self.assertIn('10', out)

    def test_shows_import_count(self):
        out = _capture(_render_summary, self._analysis(), 0, 0)
        self.assertIn('50', out)

    def test_shows_no_circular_checkmark(self):
        out = _capture(_render_summary, self._analysis(), 0, 0)
        self.assertIn('✅', out)
        self.assertIn('no circular', out)

    def test_shows_circular_x_when_present(self):
        out = _capture(_render_summary, self._analysis(), 3, 0)
        self.assertIn('❌', out)
        self.assertIn('3 circular', out)

    def test_shows_unused_warning_when_present(self):
        out = _capture(_render_summary, self._analysis(), 0, 2)
        self.assertIn('⚠️', out)
        self.assertIn('2 unused', out)


class TestRenderExternalPackages(unittest.TestCase):

    def _analysis(self, packages):
        return {
            'external_packages': packages,
            'stdlib_packages': [],
            'top_importers': [],
            'total_files': 5,
            'total_imports': 10,
            'relative_count': 0,
        }

    def test_shows_package_names(self):
        out = _capture(_render_external_packages, self._analysis([('requests', 5), ('yaml', 2)]), 10)
        self.assertIn('requests', out)
        self.assertIn('yaml', out)

    def test_shows_usage_counts(self):
        out = _capture(_render_external_packages, self._analysis([('requests', 7)]), 10)
        self.assertIn('7', out)

    def test_truncates_at_top(self):
        pkgs = [(f'pkg{i}', i) for i in range(20, 0, -1)]
        out = _capture(_render_external_packages, self._analysis(pkgs), 5)
        self.assertIn('more', out)

    def test_empty_produces_no_output(self):
        out = _capture(_render_external_packages, self._analysis([]), 10)
        self.assertEqual(out, '')


class TestRenderCircular(unittest.TestCase):

    def test_shows_cycles(self):
        cycles = [['/p/a.py', '/p/b.py', '/p/a.py']]
        out = _capture(_render_circular, cycles, 1, Path('/p'), 10)
        self.assertIn('❌', out)
        self.assertIn('a.py', out)
        self.assertIn('b.py', out)

    def test_shows_arrow_between_files(self):
        cycles = [['/p/a.py', '/p/b.py', '/p/a.py']]
        out = _capture(_render_circular, cycles, 1, Path('/p'), 10)
        self.assertIn('→', out)

    def test_relative_paths_shown(self):
        cycles = [['/p/src/a.py', '/p/src/b.py', '/p/src/a.py']]
        out = _capture(_render_circular, cycles, 1, Path('/p'), 10)
        self.assertIn('src/a.py', out)
        self.assertNotIn('/p/src/a.py', out)

    def test_zero_cycles_produces_no_output(self):
        out = _capture(_render_circular, [], 0, Path('/p'), 10)
        self.assertEqual(out, '')

    def test_truncates_at_top(self):
        cycles = [[f'/p/{i}.py', f'/p/{i+1}.py', f'/p/{i}.py'] for i in range(10)]
        out = _capture(_render_circular, cycles, 10, Path('/p'), 3)
        self.assertIn('more', out)


class TestRenderUnused(unittest.TestCase):

    def _unused(self, module, names=None, file='/project/src/mod.py', line=5):
        return {
            'file': file,
            'line': line,
            'module': module,
            'names': names or [],
        }

    def test_shows_module_name(self):
        out = _capture(_render_unused, [self._unused('os')], Path('/project'), 10)
        self.assertIn('os', out)

    def test_shows_file_and_line(self):
        out = _capture(_render_unused, [self._unused('os', file='/project/src/foo.py', line=12)], Path('/project'), 10)
        self.assertIn('src/foo.py', out)
        self.assertIn('12', out)

    def test_shows_names_when_present(self):
        out = _capture(_render_unused, [self._unused('typing', names=['Optional'])], Path('/project'), 10)
        self.assertIn('Optional', out)

    def test_shows_warning_icon(self):
        out = _capture(_render_unused, [self._unused('os')], Path('/project'), 10)
        self.assertIn('⚠️', out)

    def test_empty_produces_no_output(self):
        out = _capture(_render_unused, [], Path('/project'), 10)
        self.assertEqual(out, '')

    def test_truncates_at_top(self):
        unused = [self._unused(f'mod{i}', line=i) for i in range(20)]
        out = _capture(_render_unused, unused, Path('/project'), 5)
        self.assertIn('more', out)


class TestRenderTopImporters(unittest.TestCase):

    def _analysis(self, importers):
        return {
            'top_importers': importers,
            'external_packages': [],
            'stdlib_packages': [],
            'total_files': 5,
            'total_imports': 10,
            'relative_count': 0,
        }

    def test_shows_file_names(self):
        importers = [{'file': 'src/heavy.py', 'count': 20}]
        out = _capture(_render_top_importers, self._analysis(importers), 10)
        self.assertIn('src/heavy.py', out)

    def test_shows_import_counts(self):
        importers = [{'file': 'a.py', 'count': 15}]
        out = _capture(_render_top_importers, self._analysis(importers), 10)
        self.assertIn('15', out)

    def test_shows_bar_chart(self):
        importers = [{'file': 'a.py', 'count': 10}]
        out = _capture(_render_top_importers, self._analysis(importers), 10)
        self.assertIn('█', out)

    def test_empty_produces_no_output(self):
        out = _capture(_render_top_importers, self._analysis([]), 10)
        self.assertEqual(out, '')


# ── Integration: run_deps ──────────────────────────────────────────────────────

_BASE_DATA = json.loads(_BASE_JSON)
_CIRCULAR_DATA = json.loads(_CIRCULAR_JSON)
_UNUSED_DATA = json.loads(_UNUSED_JSON)['unused']


class TestRunDeps(unittest.TestCase):

    def _patch_runners(self, base=None, circular=None, unused=None):
        """Return context managers patching all three data collectors."""
        base_val = base if base is not None else _BASE_DATA
        circ_val = circular if circular is not None else _CIRCULAR_DATA
        unused_val = unused if unused is not None else _UNUSED_DATA
        return (
            patch('reveal.cli.commands.deps._run_base', return_value=base_val),
            patch('reveal.cli.commands.deps._run_circular', return_value=circ_val),
            patch('reveal.cli.commands.deps._run_unused', return_value=unused_val),
        )

    def test_nonexistent_path_exits_1(self):
        with self.assertRaises(SystemExit) as ctx:
            run_deps(_args(path='/no/such/xyz'))
        self.assertEqual(ctx.exception.code, 1)

    def test_json_format_outputs_valid_json(self):
        import tempfile
        p_base, p_circ, p_unused = self._patch_runners()
        with p_base, p_circ, p_unused:
            with tempfile.TemporaryDirectory() as tmp:
                buf = StringIO()
                with patch('sys.stdout', buf):
                    run_deps(_args(path=tmp, format='json'))
                data = json.loads(buf.getvalue())
                self.assertIn('path', data)
                self.assertIn('base', data)
                self.assertIn('circular', data)
                self.assertIn('unused', data)

    def test_text_output_shows_header(self):
        import tempfile
        p_base, p_circ, p_unused = self._patch_runners(circular={}, unused=[])
        with p_base, p_circ, p_unused:
            with tempfile.TemporaryDirectory() as tmp:
                buf = StringIO()
                with patch('sys.stdout', buf):
                    run_deps(_args(path=tmp))
                self.assertIn('Dependencies:', buf.getvalue())

    def test_no_circular_skips_circular_runner(self):
        import tempfile
        p_base, p_circ, p_unused = self._patch_runners(circular={}, unused=[])
        with p_base, p_circ as mock_circ, p_unused:
            with tempfile.TemporaryDirectory() as tmp:
                buf = StringIO()
                with patch('sys.stdout', buf):
                    run_deps(_args(path=tmp, no_circular=True))
                mock_circ.assert_not_called()

    def test_no_unused_skips_unused_runner(self):
        import tempfile
        p_base, p_circ, p_unused = self._patch_runners(circular={}, unused=[])
        with p_base, p_circ, p_unused as mock_unused:
            with tempfile.TemporaryDirectory() as tmp:
                buf = StringIO()
                with patch('sys.stdout', buf):
                    run_deps(_args(path=tmp, no_unused=True))
                mock_unused.assert_not_called()

    def test_exits_0_when_no_issues(self):
        import tempfile
        clean_circular = {'cycles': [], 'count': 0}
        p_base, p_circ, p_unused = self._patch_runners(circular=clean_circular, unused=[])
        with p_base, p_circ, p_unused:
            with tempfile.TemporaryDirectory() as tmp:
                buf = StringIO()
                with patch('sys.stdout', buf):
                    run_deps(_args(path=tmp))
                # No SystemExit — method returns normally

    def test_exits_1_when_circular_deps(self):
        import tempfile
        p_base, p_circ, p_unused = self._patch_runners(unused=[])
        with p_base, p_circ, p_unused:
            with tempfile.TemporaryDirectory() as tmp:
                buf = StringIO()
                with patch('sys.stdout', buf):
                    with self.assertRaises(SystemExit) as ctx:
                        run_deps(_args(path=tmp))
                self.assertEqual(ctx.exception.code, 1)

    def test_empty_data_no_crash(self):
        import tempfile
        p_base, p_circ, p_unused = self._patch_runners(base={}, circular={}, unused=[])
        with p_base, p_circ, p_unused:
            with tempfile.TemporaryDirectory() as tmp:
                buf = StringIO()
                with patch('sys.stdout', buf):
                    run_deps(_args(path=tmp))
                self.assertIn('Dependencies:', buf.getvalue())


if __name__ == '__main__':
    unittest.main()
