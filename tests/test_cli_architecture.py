"""Architecture spelling: declared controls and retained shared/engine regressions.

The old severity, recommendations and ordinary AST dashboard are retired. Canonical
map behavior is qualified by test_architecture_alias_back2377 and overview controls.
"""
import json
import unittest
from argparse import Namespace
from functools import partial
from io import StringIO
from pathlib import Path
from contextlib import redirect_stdout

import pytest
from reveal.cli.routing.declared import create_declared_parser, run_declared_command
from reveal.adapters.architecture import ArchitectureAdapter
from reveal.utils.path_utils import is_test_path, to_relative_display

create_architecture_parser = partial(create_declared_parser, 'architecture')
run_architecture = partial(run_declared_command, 'architecture')
pytestmark = pytest.mark.component
try:
    import pygit2
    PYGIT2_AVAILABLE = True
except ImportError:
    PYGIT2_AVAILABLE = False


def _args(**kwargs):
    defaults = vars(create_architecture_parser().parse_args([]))
    defaults.update(kwargs)
    return Namespace(**defaults)


def _capture(fn, *args, **kwargs):
    buf = StringIO()
    with redirect_stdout(buf):
        fn(*args, **kwargs)
    return buf.getvalue()


class TestCreateArchitectureParser(unittest.TestCase):

    def test_returns_parser(self):
        parser = create_architecture_parser()
        self.assertEqual(parser.prog, 'reveal architecture')

    def test_defaults(self):
        parser = create_architecture_parser()
        args = parser.parse_args([])
        self.assertEqual(args.path, '.')
        self.assertNotIn('top', vars(args))
        self.assertEqual(ArchitectureAdapter.PARAM_SPECS[0].read({}), 5)
        self.assertNotIn('no_imports', vars(args))

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
        self.assertEqual(args.top, '10')  # conversion belongs to the declared binder

    def test_format_json(self):
        parser = create_architecture_parser()
        args = parser.parse_args(['--format', 'json'])
        self.assertEqual(args.format, 'json')

    def test_against_defaults_to_none(self):
        parser = create_architecture_parser()
        args = parser.parse_args([])
        self.assertNotIn('against', vars(args))

    def test_against_flag(self):
        parser = create_architecture_parser()
        args = parser.parse_args(['src/', '--against', 'v1.0.0'])
        self.assertEqual(args.against, 'v1.0.0')


# ── is_test_path ──────────────────────────────────────────────────────────────

class TestIsTestFile(unittest.TestCase):

    def test_test_prefix(self):
        self.assertTrue(is_test_path('/project/tests/test_main.py'))

    def test_tests_dir(self):
        self.assertTrue(is_test_path('/project/tests/utils.py'))

    def test_test_dir(self):
        self.assertTrue(is_test_path('/project/test/helpers.py'))

    def test_normal_file(self):
        self.assertFalse(is_test_path('/project/src/main.py'))

    def test_file_with_test_in_name(self):
        self.assertFalse(is_test_path('/project/src/latest.py'))


# ── _relpath ───────────────────────────────────────────────────────────────────

class TestRelpath(unittest.TestCase):

    def test_inside_base(self):
        result = to_relative_display('/project/src/main.py', Path('/project/src'))
        self.assertEqual(result, 'main.py')

    def test_outside_base(self):
        result = to_relative_display('/other/lib.py', Path('/project/src'))
        self.assertEqual(result, '/other/lib.py')

    def test_no_base(self):
        result = to_relative_display('/project/src/main.py', None)
        self.assertEqual(result, '/project/src/main.py')

    def test_subdirectory(self):
        result = to_relative_display('/project/src/adapters/base.py', Path('/project/src'))
        self.assertEqual(result, 'adapters/base.py')

    def test_relative_base_absolute_file_still_relativizes(self):
        """BACK-1194: architecture:// shares the same expanduser()-without-
        resolve() bug as overview.py/deps.py — a relative CLI target left
        base_path unresolved while file paths from elsewhere arrived
        absolute, so relative_to() raised and the absolute path leaked."""
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "sub").mkdir()
            abs_file = str((tmp / "sub" / "mod.py").resolve())
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                result = to_relative_display(abs_file, Path("."))
            finally:
                os.chdir(old_cwd)
        self.assertEqual(result, "sub/mod.py")


def _commit_all(repo, message, parents=None):
    signature = pygit2.Signature("Test User", "test@example.com")
    index = repo.index
    index.add_all()
    index.write()
    tree = index.write_tree()
    if parents is None:
        parents = [repo.head.target] if not repo.head_is_unborn else []
    ref = "HEAD" if not repo.head_is_unborn else "refs/heads/master"
    oid = repo.create_commit(ref, signature, signature, message, tree, parents)
    if repo.head_is_unborn:
        repo.set_head("refs/heads/master")
    return oid


class TestArchitectureDiffIntegration(unittest.TestCase):
    """End-to-end: reveal architecture <path> --against <ref>.

    Fixture shape (see _arch_diff_repo_fixture):
      1. two files, no cross-import.
      2. introduces a circular import between them.
      3. (working tree, uncommitted) adds a new load-bearing file with high
         fan-in, imported by two other new files.
    """

    def test_reports_introduced_cycle_and_new_load_bearing_file(self):
        from reveal.diff.architecture_diff import run_architecture_diff

        fixture = _arch_diff_repo_fixture()
        try:
            report = run_architecture_diff(
                fixture['src_path'], fixture['commit_no_cycle'], top_n=20,
            )

            self.assertEqual(report['type'], 'architecture_diff')
            self.assertEqual(report['base_ref'], fixture['commit_no_cycle'])

            deltas = report['deltas']

            introduced = deltas['circular_groups']['introduced']
            self.assertEqual(len(introduced), 1)
            self.assertEqual(sorted(introduced[0]), ['a.py', 'b.py'])
            self.assertEqual(deltas['circular_groups']['resolved'], [])

            fan_in_by_file = {e['file']: e for e in deltas['fan_in']}
            self.assertIn('c.py', fan_in_by_file)
            self.assertIsNone(fan_in_by_file['c.py']['base'])
            self.assertEqual(fan_in_by_file['c.py']['head'], 2)
            self.assertIsNone(fan_in_by_file['c.py']['change'])
        finally:
            fixture['cleanup']()

    def test_fast_exit_returns_empty_deltas_when_nothing_changed(self):
        from reveal.diff.architecture_diff import run_architecture_diff

        fixture = _arch_diff_repo_fixture(dirty=False)
        try:
            report = run_architecture_diff(
                fixture['src_path'], fixture['commit_with_cycle'], top_n=20,
            )
            self.assertEqual(report['deltas']['fan_in'], [])
            self.assertEqual(report['deltas']['fan_out'], [])
            self.assertEqual(
                report['deltas']['circular_groups'], {'introduced': [], 'resolved': []},
            )
        finally:
            fixture['cleanup']()

    def test_cli_json_output_shape(self):
        fixture = _arch_diff_repo_fixture()
        try:
            args = _args(path=str(fixture['src_path']), against=fixture['commit_no_cycle'], format='json')
            out = _capture(run_architecture, args)
            report = json.loads(out)
            self.assertEqual(report['type'], 'overview_diff')
            self.assertIn('deltas', report)
        finally:
            fixture['cleanup']()

    def test_materialize_ref_includes_ambiguous_named_source_dir(self):
        """BACK-913/BACK-552 parity: a real source dir bare-named 'venv'
        must be materialized, not silently skipped — mirrors the same fix
        applied to find_analyzable_files (reveal/adapters/diff/resolution.py)."""
        from reveal.diff.architecture_diff import materialize_ref, _open_repo

        if not PYGIT2_AVAILABLE:
            raise unittest.SkipTest("pygit2 not available")

        import shutil
        import tempfile

        tmp_dir = Path(tempfile.mkdtemp(prefix='reveal-archdiff-ambiguous-'))
        try:
            repo_path = tmp_dir / "repo"
            src = repo_path / "src"
            real_pkg = src / "venv"
            real_pkg.mkdir(parents=True)
            (real_pkg / "main.py").write_text("x = 1\n")
            repo = pygit2.init_repository(str(repo_path))
            commit = _commit_all(repo, "add real venv/ source package")

            opened_repo = _open_repo(repo_path)
            with materialize_ref(opened_repo, str(commit), "src") as tmp_root:
                self.assertTrue((tmp_root / "venv" / "main.py").exists())
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _arch_diff_repo_fixture(dirty=True):
    """Non-pytest-fixture variant of arch_diff_repo, usable from unittest.TestCase
    methods (which don't take pytest fixture args). Mirrors arch_diff_repo above.
    """
    if not PYGIT2_AVAILABLE:
        raise unittest.SkipTest("pygit2 not available")

    import shutil
    import tempfile

    tmp_dir = Path(tempfile.mkdtemp(prefix='reveal-archdiff-test-'))
    repo_path = tmp_dir / "repo"
    src = repo_path / "src"
    src.mkdir(parents=True)
    repo = pygit2.init_repository(str(repo_path))

    (src / "a.py").write_text("import b\n\ndef foo():\n    return b.bar()\n")
    (src / "b.py").write_text("def bar():\n    return 1\n")
    commit_no_cycle = _commit_all(repo, "initial: no cycle")

    (src / "b.py").write_text("import a\n\ndef bar():\n    return a.foo()\n")
    commit_with_cycle = _commit_all(repo, "introduce circular import")

    if dirty:
        (src / "c.py").write_text("def util():\n    return 42\n")
        (src / "d.py").write_text("import c\n\ndef use_c():\n    return c.util()\n")
        (src / "e.py").write_text("import c\n\ndef use_c2():\n    return c.util()\n")

    return {
        'repo_path': repo_path,
        'src_path': src,
        'commit_no_cycle': str(commit_no_cycle),
        'commit_with_cycle': str(commit_with_cycle),
        'cleanup': lambda: shutil.rmtree(tmp_dir, ignore_errors=True),
    }


if __name__ == '__main__':
    unittest.main()
