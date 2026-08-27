"""Tests for reveal deps subcommand."""

import json
import sys
import unittest
from argparse import Namespace
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from reveal.adapters.deps import (
    DepsAdapter,
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
)
from reveal.cli.commands.deps import (
    create_deps_parser,
    run_deps,
)

# BACK-1149: component-layer test -- calls a reveal.cli.* handler function directly, not through reveal.main
pytestmark = pytest.mark.component


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



def _make_import(module, is_relative=False, names=None, line=1, resolved=None):
    return {
        'file': '/project/src/mod.py',
        'line': line,
        'module': module,
        'names': names or [],
        'type': 'from_import' if names else 'import',
        'is_relative': is_relative,
        'alias': None,
        'resolved': resolved,
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

    def test_summary_only_flag_default_false(self):
        parser = create_deps_parser()
        args = parser.parse_args([])
        self.assertFalse(args.summary_only)

    def test_summary_only_flag(self):
        parser = create_deps_parser()
        args = parser.parse_args(['--summary-only'])
        self.assertTrue(args.summary_only)


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

    def test_top_importers_relative_when_base_path_is_unresolved(self):
        """BACK-1194: deps:// shared overview.py's expanduser()-without-
        resolve() bug -- a relative base_path (e.g. deps://. from inside
        the project dir) left the comparison lexical-only, so an already-
        absolute file path (typical of a separate file-walk subsystem)
        raised ValueError on relative_to() and leaked straight through."""
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "sub").mkdir()
            abs_file = str((tmp / "sub" / "heavy.py").resolve())
            files = {abs_file: [_make_import('os')]}
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                result = _analyse_imports(files, Path("."))
            finally:
                os.chdir(old_cwd)
        self.assertEqual(result['top_importers'][0]['file'], 'sub/heavy.py')

    def test_external_packages_sorted_by_usage(self):
        files = {
            '/proj/a.py': [_make_import('requests'), _make_import('requests'), _make_import('yaml')],
        }
        result = _analyse_imports(files, Path('/proj'))
        packages = result['external_packages']
        self.assertEqual(packages[0][0], 'requests')
        self.assertEqual(packages[0][1], 2)

    # BACK-1193: deps:// applied a Python-only classifier to every language.
    def test_resolved_import_treated_as_internal(self):
        # imports:// resolved this to a real in-tree file (e.g. Ruby
        # `require "s3_helper"` -> lib/s3_helper.rb) -- must not land in
        # external_packages just because it isn't syntactically relative.
        files = {'/proj/a.rb': [_make_import('s3_helper', resolved='/proj/lib/s3_helper.rb')]}
        result = _analyse_imports(files, Path('/proj'))
        ext_names = [p for p, _ in result['external_packages']]
        self.assertNotIn('s3_helper', ext_names)
        self.assertEqual(result['relative_count'], 1)

    def test_non_python_stdlib_name_collision_not_counted_as_stdlib(self):
        # Ruby's stdlib 'socket'/'digest' collide with Python's stdlib list by
        # name only -- must not be reported as stdlib for a non-Python file
        # (no Ruby stdlib list exists, so "unresolved" is the honest answer).
        files = {'/proj/a.rb': [_make_import('socket'), _make_import('digest')]}
        result = _analyse_imports(files, Path('/proj'))
        stdlib_names = [p for p, _ in result['stdlib_packages']]
        ext_names = [p for p, _ in result['external_packages']]
        self.assertEqual(stdlib_names, [])
        self.assertIn('socket', ext_names)
        self.assertIn('digest', ext_names)

    def test_python_stdlib_still_classified_for_python_files(self):
        # The gate gained in BACK-1193 is per-file-language, not a regression
        # for Python itself.
        files = {'/proj/a.py': [_make_import('socket')]}
        result = _analyse_imports(files, Path('/proj'))
        stdlib_names = [p for p, _ in result['stdlib_packages']]
        self.assertIn('socket', stdlib_names)

    def test_dart_stdlib_prefix_classified_without_a_list(self):
        # BACK-1193 addendum: 'dart:' is a syntactic marker, not a name that
        # could collide -- Dart is the one other language deps:// classifies
        # as stdlib, with no per-language stdlib list needed.
        files = {'/proj/a.dart': [_make_import('dart:async'), _make_import('package:flutter/material')]}
        result = _analyse_imports(files, Path('/proj'))
        stdlib_names = [p for p, _ in result['stdlib_packages']]
        ext_names = [p for p, _ in result['external_packages']]
        self.assertIn('dart:async', stdlib_names)
        self.assertIn('package:flutter/material', ext_names)


# ── Data collector tests ───────────────────────────────────────────────────────

class TestRunBase(unittest.TestCase):

    def setUp(self):
        self.adapter = DepsAdapter('/project')

    @patch('reveal.adapters.deps.ImportsAdapter')
    def test_returns_adapter_data(self, MockAdapter):
        MockAdapter.return_value.get_structure.return_value = json.loads(_BASE_JSON)
        result = _run_base(self.adapter, Path('/project'))
        self.assertIn('files', result)
        MockAdapter.assert_called_once_with(str(Path('/project')), None)

    @patch('reveal.adapters.deps.ImportsAdapter')
    def test_exception_returns_empty_dict(self, MockAdapter):
        MockAdapter.return_value.get_structure.side_effect = Exception('fail')
        self.assertEqual(_run_base(self.adapter, Path('/project')), {})


class TestRunCircular(unittest.TestCase):

    def setUp(self):
        self.adapter = DepsAdapter('/project')

    @patch('reveal.adapters.deps.ImportsAdapter')
    def test_returns_cycles(self, MockAdapter):
        MockAdapter.return_value.get_structure.return_value = json.loads(_CIRCULAR_JSON)
        result = _run_circular(self.adapter, Path('/project'))
        self.assertEqual(result['count'], 2)
        self.assertEqual(len(result['cycles']), 2)
        MockAdapter.assert_called_once_with(str(Path('/project')), 'circular')

    @patch('reveal.adapters.deps.ImportsAdapter')
    def test_exception_returns_empty_dict(self, MockAdapter):
        MockAdapter.return_value.get_structure.side_effect = Exception('fail')
        self.assertEqual(_run_circular(self.adapter, Path('/project')), {})


class TestRunUnused(unittest.TestCase):

    def setUp(self):
        self.adapter = DepsAdapter('/project')

    @patch('reveal.adapters.deps.ImportsAdapter')
    def test_returns_unused_list(self, MockAdapter):
        MockAdapter.return_value.get_structure.return_value = json.loads(_UNUSED_JSON)
        result = _run_unused(self.adapter, Path('/project'))
        self.assertEqual(len(result), 2)
        MockAdapter.assert_called_once_with(str(Path('/project')), 'unused')

    @patch('reveal.adapters.deps.ImportsAdapter')
    def test_exception_returns_empty_list(self, MockAdapter):
        MockAdapter.return_value.get_structure.side_effect = Exception('fail')
        self.assertEqual(_run_unused(self.adapter, Path('/project')), [])

    @patch('reveal.adapters.deps.ImportsAdapter')
    def test_missing_unused_key_returns_empty(self, MockAdapter):
        MockAdapter.return_value.get_structure.return_value = {'other': 'data'}
        self.assertEqual(_run_unused(self.adapter, Path('/project')), [])


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
            patch('reveal.adapters.deps._run_base', return_value=base_val),
            patch('reveal.adapters.deps._run_circular', return_value=circ_val),
            patch('reveal.adapters.deps._run_unused', return_value=unused_val),
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

    def test_summary_only_drops_base_files(self):
        """BACK-1040: --summary-only strips base.files (the bulk of deps.json
        on a real repo) but leaves circular/unused and file/import counts."""
        import tempfile
        p_base, p_circ, p_unused = self._patch_runners()
        with p_base, p_circ, p_unused:
            with tempfile.TemporaryDirectory() as tmp:
                buf = StringIO()
                with patch('sys.stdout', buf):
                    run_deps(_args(path=tmp, format='json', summary_only=True))
                data = json.loads(buf.getvalue())
                self.assertNotIn('files', data['base'])
                self.assertEqual(data['base']['total_files'], len(_BASE_DATA['files']))
                expected_imports = sum(len(v) for v in _BASE_DATA['files'].values())
                self.assertEqual(data['base']['total_imports'], expected_imports)
                # unaffected
                self.assertEqual(data['circular']['count'], 2)

    def test_summary_only_ignored_without_json_format(self):
        """--summary-only only touches the JSON path; text rendering (which
        never dumps base.files verbatim) must not change or error."""
        import tempfile
        p_base, p_circ, p_unused = self._patch_runners(circular={}, unused=[])
        with p_base, p_circ, p_unused:
            with tempfile.TemporaryDirectory() as tmp:
                out = _capture(run_deps, _args(path=tmp, format='text', summary_only=True))
                self.assertIn('Dependencies:', out)

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
