"""Tests for D005: Cross-file hardcoded literal cluster detection."""

import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from reveal.rules.duplicates.D005 import (
    D005, _clear_index, _canonical_key, _find_project_root,
    _max_project_files, _build_index, _DEFAULT_MAX_PROJECT_FILES,
)


def _write(directory: str, name: str, content: str) -> str:
    """Write a temp Python file and return its absolute path."""
    path = Path(directory) / name
    path.write_text(textwrap.dedent(content))
    return str(path)


class TestD005CanonicalKey(unittest.TestCase):
    """Unit tests for the canonical key helper."""

    def test_order_independent(self):
        """Same values in different order should produce the same key."""
        a = _canonical_key(frozenset(['.py', '.js', '.ts', '.rs', '.go']))
        b = _canonical_key(frozenset(['.go', '.rs', '.ts', '.js', '.py']))
        self.assertEqual(a, b)

    def test_different_values_differ(self):
        """Different value sets must produce different keys."""
        a = _canonical_key(frozenset(['.py', '.js', '.ts', '.rs', '.go']))
        b = _canonical_key(frozenset(['.py', '.js', '.ts', '.rs', '.rb']))
        self.assertNotEqual(a, b)


class TestD005ExtractFileLiterals(unittest.TestCase):
    """Unit tests for extract_file_literals — no filesystem needed."""

    def setUp(self):
        self.rule = D005()

    def test_basic_list_extracted(self):
        code = "EXTS = ['.py', '.js', '.ts', '.rs', '.go']"
        results = self.rule.extract_file_literals('f.py', code)
        self.assertEqual(len(results), 1)
        key, line, name, values = results[0]
        self.assertEqual(name, 'EXTS')
        self.assertIn('.py', values)

    def test_frozenset_extracted(self):
        code = "SKIP = frozenset({'.git', 'node_modules', 'venv', '__pycache__', 'dist'})"
        results = self.rule.extract_file_literals('f.py', code)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][2], 'SKIP')

    def test_set_literal_extracted(self):
        code = "DIRS = {'.git', 'node_modules', 'venv', '__pycache__', 'dist'}"
        results = self.rule.extract_file_literals('f.py', code)
        self.assertEqual(len(results), 1)

    def test_too_small_skipped(self):
        code = "SMALL = ['.py', '.js', '.ts']"
        results = self.rule.extract_file_literals('f.py', code)
        self.assertEqual(results, [])

    def test_stable_name_skipped(self):
        code = "__all__ = ['foo', 'bar', 'baz', 'qux', 'quux']"
        results = self.rule.extract_file_literals('f.py', code)
        self.assertEqual(results, [])

    def test_non_constant_elements_skipped(self):
        code = "MIXED = ['.py', some_var, '.ts', '.rs', '.go']"
        results = self.rule.extract_file_literals('f.py', code)
        self.assertEqual(results, [])

    def test_duplicate_within_file_deduplicated(self):
        code = textwrap.dedent("""\
            A = ['.py', '.js', '.ts', '.rs', '.go']
            B = ['.py', '.js', '.ts', '.rs', '.go']
        """)
        results = self.rule.extract_file_literals('f.py', code)
        self.assertEqual(len(results), 1)

    def test_syntax_error_returns_empty(self):
        results = self.rule.extract_file_literals('f.py', 'def (')
        self.assertEqual(results, [])


class TestD005Integration(unittest.TestCase):
    """Integration tests using real temp files."""

    def setUp(self):
        _clear_index()
        self.rule = D005()
        self._tmpdir = tempfile.mkdtemp()
        Path(self._tmpdir, 'pyproject.toml').write_text('[project]\nname="test"')

    def tearDown(self):
        _clear_index()

    def _check(self, filename: str, content: str) -> list:
        path = _write(self._tmpdir, filename, content)
        return self.rule.check(path, None, textwrap.dedent(content))

    # ── Threshold: cluster must span MIN_CLUSTER_FILES ────────────────────────

    def test_two_files_below_threshold_no_detection(self):
        """Two files sharing a literal — below MIN_CLUSTER_FILES=3, no flag."""
        code = "EXTS = ['.py', '.js', '.ts', '.rs', '.go']\n"
        self._check('a.py', code)
        detections = self._check('b.py', code)
        self.assertEqual(detections, [])

    def test_three_files_at_threshold_detected(self):
        """Three files sharing the same literal — at threshold, flag all three."""
        code = "EXTS = ['.py', '.js', '.ts', '.rs', '.go']\n"
        self._check('a.py', code)
        self._check('b.py', code)
        _clear_index()  # force re-scan after all files written
        detections = self._check('c.py', code)
        self.assertGreater(len(detections), 0)
        self.assertIn("3 files", detections[0].message)

    # ── Order independence ────────────────────────────────────────────────────

    def test_different_order_same_values_detected(self):
        """List and frozenset with same values in different order are the same cluster."""
        _write(self._tmpdir, 'a.py', "A = ['.py', '.js', '.ts', '.rs', '.go']\n")
        _write(self._tmpdir, 'b.py', "B = frozenset({'.go', '.rs', '.ts', '.js', '.py'})\n")
        _write(self._tmpdir, 'c.py', "C = ('.ts', '.rs', '.go', '.py', '.js')\n")
        _clear_index()
        path = str(Path(self._tmpdir) / 'c.py')
        content = "C = ('.ts', '.rs', '.go', '.py', '.js')\n"
        detections = self.rule.check(path, None, content)
        self.assertGreater(len(detections), 0)

    # ── Below minimum size ────────────────────────────────────────────────────

    def test_small_literal_not_flagged(self):
        """Lists with fewer than MIN_LITERAL_SIZE items are never flagged."""
        code = "TINY = ['.py', '.js', '.ts']\n"
        for name in ('a.py', 'b.py', 'c.py', 'd.py'):
            self._check(name, code)
        _clear_index()
        detections = self._check('e.py', code)
        self.assertEqual(detections, [])

    # ── Stable name patterns ──────────────────────────────────────────────────

    def test_stable_names_not_flagged(self):
        """__all__ and similar names are exempt even when duplicated."""
        code = "__all__ = ['foo', 'bar', 'baz', 'qux', 'quux']\n"
        for name in ('a.py', 'b.py', 'c.py'):
            self._check(name, code)
        _clear_index()
        detections = self._check('d.py', code)
        self.assertEqual(detections, [])

    # ── Different values don't collide ───────────────────────────────────────

    def test_different_literals_no_cross_detection(self):
        """Two sets of similar-but-different literals don't merge."""
        _write(self._tmpdir, 'a.py', "A = ['.py', '.js', '.ts', '.rs', '.go']\n")
        _write(self._tmpdir, 'b.py', "B = ['.py', '.js', '.ts', '.rs', '.rb']\n")
        _write(self._tmpdir, 'c.py', "C = ['.py', '.js', '.ts', '.rs', '.go']\n")
        _clear_index()
        # Only .go-variant appears in 2 files — below threshold
        path_b = str(Path(self._tmpdir) / 'b.py')
        content_b = "B = ['.py', '.js', '.ts', '.rs', '.rb']\n"
        detections = self.rule.check(path_b, None, content_b)
        self.assertEqual(detections, [])

    # ── Detection message quality ─────────────────────────────────────────────

    def test_detection_message_names_variable(self):
        """Detection message should include the variable name."""
        code = "MY_EXTS = ['.py', '.js', '.ts', '.rs', '.go']\n"
        for name in ('a.py', 'b.py', 'c.py'):
            _write(self._tmpdir, name, code)
        _clear_index()
        path = str(Path(self._tmpdir) / 'c.py')
        detections = self.rule.check(path, None, code)
        self.assertTrue(any('MY_EXTS' in d.message for d in detections))

    def test_detection_context_names_other_files(self):
        """Context field should reference other files where the cluster appears."""
        code = "DIRS = {'.git', 'node_modules', 'venv', '__pycache__', 'dist'}\n"
        for name in ('alpha.py', 'beta.py', 'gamma.py'):
            _write(self._tmpdir, name, code)
        _clear_index()
        path = str(Path(self._tmpdir) / 'gamma.py')
        detections = self.rule.check(path, None, code)
        self.assertGreater(len(detections), 0)
        ctx = detections[0].context
        self.assertIn('Also in:', ctx)

    # ── Cache behaviour ───────────────────────────────────────────────────────

    def test_index_is_cached_per_project(self):
        """Second call for same project reuses the index (no re-scan)."""
        from reveal.rules.duplicates import D005 as mod
        _clear_index()
        code = "EXTS = ['.py', '.js', '.ts', '.rs', '.go']\n"
        for name in ('a.py', 'b.py', 'c.py'):
            _write(self._tmpdir, name, code)
        path = str(Path(self._tmpdir) / 'c.py')
        self.rule.check(path, None, code)
        # index now populated
        from reveal.rules.duplicates.D005 import _project_index
        root = _find_project_root(Path(path).resolve())
        self.assertIn(root, _project_index)
        # Second call should return same index object
        index_before = _project_index[root]
        self.rule.check(path, None, code)
        self.assertIs(_project_index[root], index_before)


class TestD005FindProjectRoot(unittest.TestCase):
    """Tests for _find_project_root."""

    def test_finds_pyproject_toml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / 'pyproject.toml').write_text('[project]')
            sub = root / 'src' / 'mypackage'
            sub.mkdir(parents=True)
            (sub / 'module.py').write_text('')
            found = _find_project_root(sub / 'module.py')
            self.assertEqual(found, root)

    def test_fallback_to_parent(self):
        """When no marker is found, returns the parent directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / 'lone.py'
            f.write_text('')
            found = _find_project_root(f)
            self.assertEqual(found, Path(tmpdir))


class TestD005Ceiling(unittest.TestCase):
    """Tests for the file-count ceiling and REVEAL_D005_MAX_FILES override."""

    def setUp(self):
        _clear_index()
        self.rule = D005()
        self._tmpdir = tempfile.mkdtemp()
        Path(self._tmpdir, 'pyproject.toml').write_text('[project]\nname="t"')

    def tearDown(self):
        _clear_index()

    def test_default_ceiling(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('REVEAL_D005_MAX_FILES', None)
            self.assertEqual(_max_project_files(), _DEFAULT_MAX_PROJECT_FILES)

    def test_env_override(self):
        with mock.patch.dict(os.environ, {'REVEAL_D005_MAX_FILES': '99'}):
            self.assertEqual(_max_project_files(), 99)

    def test_invalid_env_falls_back_to_default(self):
        with mock.patch.dict(os.environ, {'REVEAL_D005_MAX_FILES': 'not-a-number'}):
            self.assertEqual(_max_project_files(), _DEFAULT_MAX_PROJECT_FILES)

    def test_build_index_bails_over_ceiling(self):
        """A tree exceeding the ceiling returns an empty index without parsing."""
        # 6 files, ceiling forced to 3 → bail, empty index.
        code = "EXTS = ['.py', '.js', '.ts', '.rs', '.go']\n"
        for i in range(6):
            _write(self._tmpdir, f'mod{i}.py', code)
        with mock.patch.dict(os.environ, {'REVEAL_D005_MAX_FILES': '3'}):
            index = _build_index(Path(self._tmpdir), self.rule)
        self.assertEqual(index, {})

    def test_under_ceiling_scans_normally(self):
        """Below the ceiling, the index is built as usual."""
        code = "EXTS = ['.py', '.js', '.ts', '.rs', '.go']\n"
        for i in range(4):
            _write(self._tmpdir, f'mod{i}.py', code)
        with mock.patch.dict(os.environ, {'REVEAL_D005_MAX_FILES': '100'}):
            index = _build_index(Path(self._tmpdir), self.rule)
        # One literal key shared by 4 files
        self.assertEqual(len(index), 1)
        only = next(iter(index.values()))
        self.assertEqual(len({fp for fp, _, _ in only}), 4)


if __name__ == '__main__':
    unittest.main()
