"""Tests for reveal/cli/commands/pack.py.

Covers _parse_budget, _compute_priority, _apply_budget, _walk_files,
_count_lines, _collect_candidates, and run_pack integration.
"""

import sys
import unittest
import tempfile
from pathlib import Path
from argparse import Namespace

from reveal.cli.commands.pack import (
    _parse_budget,
    _compute_priority,
    _apply_budget,
    _walk_files,
    _count_lines,
    _collect_candidates,
    _render_pack,
    _print_file_line,
    run_pack,
)


# ---------------------------------------------------------------------------
# _parse_budget
# ---------------------------------------------------------------------------

class TestParseBudget(unittest.TestCase):

    def test_token_budget_plain_int(self):
        self.assertEqual(_parse_budget("2000"), (2000, None))

    def test_token_budget_large(self):
        self.assertEqual(_parse_budget("100000"), (100000, None))

    def test_line_budget(self):
        self.assertEqual(_parse_budget("500-lines"), (None, 500))

    def test_line_budget_small(self):
        self.assertEqual(_parse_budget("10-lines"), (None, 10))

    def test_invalid_budget_falls_back_to_default(self):
        # Non-numeric string → default 2000 tokens
        self.assertEqual(_parse_budget("abc"), (2000, None))

    def test_invalid_line_budget_falls_back(self):
        # "abc-lines" is invalid; the -lines suffix is stripped but int() fails
        # → falls through to the token parse, which also fails → default
        tokens, lines = _parse_budget("abc-lines")
        self.assertEqual(tokens, 2000)
        self.assertIsNone(lines)

    def test_zero_budget(self):
        self.assertEqual(_parse_budget("0"), (0, None))

    def test_zero_line_budget(self):
        self.assertEqual(_parse_budget("0-lines"), (None, 0))


# ---------------------------------------------------------------------------
# _count_lines
# ---------------------------------------------------------------------------

class TestCountLines(unittest.TestCase):

    def test_counts_newlines(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("line1\nline2\nline3\n")
            path = Path(f.name)
        self.assertEqual(_count_lines(path), 3)

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("")
            path = Path(f.name)
        self.assertEqual(_count_lines(path), 0)

    def test_nonexistent_file_returns_zero(self):
        self.assertEqual(_count_lines(Path("/nonexistent/file.py")), 0)

    def test_single_line_no_newline(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("no newline")
            path = Path(f.name)
        self.assertEqual(_count_lines(path), 0)


# ---------------------------------------------------------------------------
# _compute_priority
# ---------------------------------------------------------------------------

class TestComputePriority(unittest.TestCase):

    def _make_file(self, tmpdir: Path, rel: str, content: str = "x") -> tuple:
        """Create a file and return (Path, relative_path)."""
        full = tmpdir / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
        return full, Path(rel)

    def test_entry_point_gets_high_score(self):
        with tempfile.TemporaryDirectory() as d:
            path, rel = self._make_file(Path(d), "main.py")
            score = _compute_priority(path, rel, focus=None)
            self.assertGreaterEqual(score, 10.0)

    def test_focus_match_boosts_score(self):
        with tempfile.TemporaryDirectory() as d:
            path, rel = self._make_file(Path(d), "auth/middleware.py")
            score_focused = _compute_priority(path, rel, focus="auth")
            score_unfocused = _compute_priority(path, rel, focus=None)
            self.assertGreater(score_focused, score_unfocused)

    def test_focus_boost_is_8_points(self):
        with tempfile.TemporaryDirectory() as d:
            path, rel = self._make_file(Path(d), "auth/middleware.py")
            score_focused = _compute_priority(path, rel, focus="auth")
            score_unfocused = _compute_priority(path, rel, focus=None)
            self.assertAlmostEqual(score_focused - score_unfocused, 8.0)

    def test_key_dir_segment_boosts_score(self):
        with tempfile.TemporaryDirectory() as d:
            path, rel = self._make_file(Path(d), "core/engine.py")
            score = _compute_priority(path, rel, focus=None)
            self.assertGreaterEqual(score, 2.0)

    def test_test_file_penalized(self):
        with tempfile.TemporaryDirectory() as d:
            path, rel = self._make_file(Path(d), "tests/test_foo.py")
            score = _compute_priority(path, rel, focus=None)
            self.assertEqual(score, 0.0)  # clamped to 0

    def test_vendor_dir_penalized(self):
        with tempfile.TemporaryDirectory() as d:
            path, rel = self._make_file(Path(d), "vendor/lib.py")
            score = _compute_priority(path, rel, focus=None)
            self.assertEqual(score, 0.0)

    def test_large_file_penalized(self):
        with tempfile.TemporaryDirectory() as d:
            # Use a key-dir file so baseline score is 2.0; large penalty (-1) → 1.0
            path, rel = self._make_file(Path(d), "core/engine.py", "x" * 51_000)
            score_big = _compute_priority(path, rel, focus=None)
            path2, rel2 = self._make_file(Path(d), "core/utils.py", "x" * 100)
            score_small = _compute_priority(path2, rel2, focus=None)
            self.assertLess(score_big, score_small)

    def test_score_never_negative(self):
        with tempfile.TemporaryDirectory() as d:
            # Combine multiple penalties
            path, rel = self._make_file(Path(d), "vendor/tests/test_big.py", "x" * 51_000)
            score = _compute_priority(path, rel, focus=None)
            self.assertGreaterEqual(score, 0.0)

    def test_key_stem_match(self):
        with tempfile.TemporaryDirectory() as d:
            path, rel = self._make_file(Path(d), "somelib/config.py")
            score = _compute_priority(path, rel, focus=None)
            self.assertGreaterEqual(score, 2.0)

    def test_focus_case_insensitive(self):
        with tempfile.TemporaryDirectory() as d:
            path, rel = self._make_file(Path(d), "Auth/middleware.py")
            score = _compute_priority(path, rel, focus="auth")
            self.assertGreaterEqual(score, 8.0)

    def test_key_dir_no_substring_false_positive(self):
        """'main' inside 'maintainability' should NOT trigger key dir bonus."""
        with tempfile.TemporaryDirectory() as d:
            path, rel = self._make_file(Path(d), "maintainability/utils.py")
            score = _compute_priority(path, rel, focus=None)
            # Should not get the key-dir +2 bonus for 'main'
            self.assertLess(score, 2.0)


# ---------------------------------------------------------------------------
# _walk_files
# ---------------------------------------------------------------------------

class TestWalkFiles(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.base = Path(self.tmp)

    def _make(self, rel: str, content: str = "x") -> Path:
        p = self.base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return p

    def test_returns_py_files(self):
        self._make("src/foo.py")
        files = _walk_files(self.base)
        self.assertTrue(any(f.name == "foo.py" for f in files))

    def test_skips_git_dir(self):
        self._make(".git/config", "gitconfig")
        files = _walk_files(self.base)
        self.assertFalse(any(".git" in str(f) for f in files))

    def test_skips_pycache(self):
        self._make("src/__pycache__/foo.pyc", "bytecode")
        files = _walk_files(self.base)
        self.assertFalse(any("__pycache__" in str(f) for f in files))

    def test_skips_node_modules(self):
        self._make("node_modules/lib/index.js")
        files = _walk_files(self.base)
        self.assertFalse(any("node_modules" in str(f) for f in files))

    def test_skips_venv(self):
        self._make(".venv/lib/python3.11/site.py")
        files = _walk_files(self.base)
        self.assertFalse(any(".venv" in str(f) for f in files))

    def test_includes_root_config_files(self):
        self._make("pyproject.toml", "[tool.reveal]")
        files = _walk_files(self.base)
        self.assertTrue(any(f.name == "pyproject.toml" for f in files))

    def test_skips_unknown_extensions(self):
        self._make("src/data.xyz")
        files = _walk_files(self.base)
        self.assertFalse(any(f.suffix == ".xyz" for f in files))

    def test_single_file_returns_that_file(self):
        p = self._make("solo.py")
        files = _walk_files(p)
        self.assertEqual(files, [p])

    def test_includes_yaml_and_toml(self):
        self._make("config.yaml")
        self._make("config.toml")
        files = _walk_files(self.base)
        names = {f.name for f in files}
        self.assertIn("config.yaml", names)
        self.assertIn("config.toml", names)

    def test_skips_hidden_dirs(self):
        self._make(".hidden/secret.py")
        files = _walk_files(self.base)
        self.assertFalse(any(".hidden" in str(f) for f in files))


# ---------------------------------------------------------------------------
# _collect_candidates
# ---------------------------------------------------------------------------

class TestCollectCandidates(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.base = Path(self.tmp)

    def _make(self, rel: str, content: str = "x\n") -> Path:
        p = self.base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return p

    def test_returns_list_of_dicts(self):
        self._make("app.py", "print('hi')\n")
        candidates = _collect_candidates(self.base, focus=None)
        self.assertIsInstance(candidates, list)
        self.assertTrue(len(candidates) > 0)
        self.assertIn('priority', candidates[0])
        self.assertIn('tokens_approx', candidates[0])
        self.assertIn('lines', candidates[0])

    def test_sorted_by_priority_descending(self):
        self._make("main.py", "# entry\n")
        self._make("utils/helpers.py", "# helper\n")
        candidates = _collect_candidates(self.base, focus=None)
        priorities = [c['priority'] for c in candidates]
        self.assertEqual(priorities, sorted(priorities, reverse=True))

    def test_skips_small_init_py(self):
        self._make("pkg/__init__.py", "# tiny\n")
        candidates = _collect_candidates(self.base, focus=None)
        self.assertFalse(any(c['relative'] == "pkg/__init__.py" for c in candidates))

    def test_includes_large_init_py(self):
        self._make("pkg/__init__.py", "x" * 600 + "\n")
        candidates = _collect_candidates(self.base, focus=None)
        self.assertTrue(any("__init__.py" in c['relative'] for c in candidates))

    def test_focus_promotes_matching_files(self):
        self._make("auth/login.py", "# login\n")
        self._make("utils/helpers.py", "# helper\n")
        candidates = _collect_candidates(self.base, focus="auth")
        auth_file = next(c for c in candidates if "auth" in c['relative'])
        other_file = next(c for c in candidates if "utils" in c['relative'])
        self.assertGreater(auth_file['priority'], other_file['priority'])


# ---------------------------------------------------------------------------
# _apply_budget
# ---------------------------------------------------------------------------

class TestApplyBudget(unittest.TestCase):

    def _make_candidate(self, name: str, tokens: int, lines: int, priority: float = 1.0) -> dict:
        return {
            'path': f'/tmp/{name}',
            'relative': name,
            'priority': priority,
            'tokens_approx': tokens,
            'lines': lines,
            'mtime': 0.0,
            'size': tokens * 4,
        }

    def test_token_budget_respected(self):
        candidates = [
            self._make_candidate("a.py", 100, 20),
            self._make_candidate("b.py", 200, 30),
            self._make_candidate("c.py", 800, 50),
        ]
        selected, meta = _apply_budget(candidates, budget_tokens=250, budget_lines=None, base_path=Path("/tmp"))
        # a.py (100) + b.py (200) = 300 > 250, so only a.py fits... wait
        # a.py (100) fits, b.py (100+200=300 > 250) skipped, c.py skipped
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['relative'], "a.py")
        self.assertEqual(meta['skipped'], 2)
        self.assertEqual(meta['used_tokens_approx'], 100)

    def test_line_budget_respected(self):
        candidates = [
            self._make_candidate("a.py", 10, 50),
            self._make_candidate("b.py", 10, 60),
        ]
        selected, meta = _apply_budget(candidates, budget_tokens=None, budget_lines=80, base_path=Path("/tmp"))
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['relative'], "a.py")
        self.assertEqual(meta['skipped'], 1)

    def test_no_budget_includes_all(self):
        candidates = [
            self._make_candidate("a.py", 1000, 100),
            self._make_candidate("b.py", 2000, 200),
        ]
        selected, meta = _apply_budget(candidates, budget_tokens=None, budget_lines=None, base_path=Path("/tmp"))
        self.assertEqual(len(selected), 2)
        self.assertEqual(meta['skipped'], 0)

    def test_empty_candidates(self):
        selected, meta = _apply_budget([], budget_tokens=2000, budget_lines=None, base_path=Path("/tmp"))
        self.assertEqual(selected, [])
        self.assertEqual(meta['total_candidates'], 0)
        self.assertEqual(meta['selected'], 0)

    def test_meta_fields_present(self):
        candidates = [self._make_candidate("a.py", 100, 10)]
        _, meta = _apply_budget(candidates, budget_tokens=500, budget_lines=None, base_path=Path("/tmp"))
        for key in ('total_candidates', 'selected', 'skipped', 'used_tokens_approx', 'used_lines', 'budget_tokens', 'budget_lines'):
            self.assertIn(key, meta)

    def test_exact_budget_fit(self):
        candidates = [self._make_candidate("a.py", 100, 10)]
        selected, meta = _apply_budget(candidates, budget_tokens=100, budget_lines=None, base_path=Path("/tmp"))
        self.assertEqual(len(selected), 1)
        self.assertEqual(meta['skipped'], 0)

    def test_zero_token_budget_skips_all(self):
        candidates = [self._make_candidate("a.py", 1, 1)]
        selected, meta = _apply_budget(candidates, budget_tokens=0, budget_lines=None, base_path=Path("/tmp"))
        self.assertEqual(len(selected), 0)
        self.assertEqual(meta['skipped'], 1)


# ---------------------------------------------------------------------------
# _render_pack and _print_file_line (output smoke tests)
# ---------------------------------------------------------------------------

class TestRenderPack(unittest.TestCase):

    def _make_candidate(self, name: str, tokens: int = 100, lines: int = 10, priority: float = 1.0) -> dict:
        return {
            'path': f'/tmp/{name}',
            'relative': name,
            'priority': priority,
            'tokens_approx': tokens,
            'lines': lines,
            'mtime': 0.0,
            'size': tokens * 4,
        }

    def test_render_no_crash_empty(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            _render_pack(Path("/tmp"), [], {'selected': 0, 'total_candidates': 0,
                          'used_tokens_approx': 0, 'used_lines': 0, 'skipped': 0,
                          'budget_tokens': 2000, 'budget_lines': None},
                         verbose=False, budget_tokens=2000, budget_lines=None)
        self.assertIn("No files fit", buf.getvalue())

    def test_render_shows_selected_count(self):
        import io
        from contextlib import redirect_stdout
        candidates = [self._make_candidate("main.py", priority=10.0)]
        meta = {'selected': 1, 'total_candidates': 1, 'used_tokens_approx': 100,
                'used_lines': 10, 'skipped': 0, 'budget_tokens': 2000, 'budget_lines': None}
        buf = io.StringIO()
        with redirect_stdout(buf):
            _render_pack(Path("/tmp"), candidates, meta, verbose=False, budget_tokens=2000, budget_lines=None)
        out = buf.getvalue()
        self.assertIn("Selected 1", out)

    def test_render_verbose_shows_token_count(self):
        import io
        from contextlib import redirect_stdout
        candidates = [self._make_candidate("app.py", tokens=42, priority=1.0)]
        meta = {'selected': 1, 'total_candidates': 1, 'used_tokens_approx': 42,
                'used_lines': 10, 'skipped': 0, 'budget_tokens': 2000, 'budget_lines': None}
        buf = io.StringIO()
        with redirect_stdout(buf):
            _render_pack(Path("/tmp"), candidates, meta, verbose=True, budget_tokens=2000, budget_lines=None)
        self.assertIn("42", buf.getvalue())

    def test_render_skipped_message(self):
        import io
        from contextlib import redirect_stdout
        candidates = [self._make_candidate("app.py")]
        meta = {'selected': 1, 'total_candidates': 2, 'used_tokens_approx': 100,
                'used_lines': 10, 'skipped': 1, 'budget_tokens': 2000, 'budget_lines': None}
        buf = io.StringIO()
        with redirect_stdout(buf):
            _render_pack(Path("/tmp"), candidates, meta, verbose=False, budget_tokens=2000, budget_lines=None)
        self.assertIn("excluded", buf.getvalue())

    def test_line_budget_description(self):
        import io
        from contextlib import redirect_stdout
        meta = {'selected': 0, 'total_candidates': 0, 'used_tokens_approx': 0,
                'used_lines': 0, 'skipped': 0, 'budget_tokens': None, 'budget_lines': 500}
        buf = io.StringIO()
        with redirect_stdout(buf):
            _render_pack(Path("/tmp"), [], meta, verbose=False, budget_tokens=None, budget_lines=500)
        self.assertIn("500 lines", buf.getvalue())

    def test_print_file_line_verbose(self):
        import io
        from contextlib import redirect_stdout
        f = {'relative': 'src/app.py', 'tokens_approx': 77, 'lines': 15}
        buf = io.StringIO()
        with redirect_stdout(buf):
            _print_file_line(f, verbose=True)
        out = buf.getvalue()
        self.assertIn("77", out)
        self.assertIn("src/app.py", out)

    def test_print_file_line_not_verbose(self):
        import io
        from contextlib import redirect_stdout
        f = {'relative': 'src/app.py', 'tokens_approx': 77, 'lines': 15}
        buf = io.StringIO()
        with redirect_stdout(buf):
            _print_file_line(f, verbose=False)
        out = buf.getvalue()
        self.assertIn("src/app.py", out)
        self.assertNotIn("77", out)


# ---------------------------------------------------------------------------
# run_pack integration
# ---------------------------------------------------------------------------

class TestRunPack(unittest.TestCase):

    def _make_args(self, path: str, budget: str = "2000", focus=None, fmt="text", verbose=False) -> Namespace:
        return Namespace(path=path, budget=budget, focus=focus, format=fmt, verbose=verbose)

    def test_nonexistent_path_exits_1(self):
        args = self._make_args("/nonexistent/path/xyz")
        with self.assertRaises(SystemExit) as ctx:
            run_pack(args)
        self.assertEqual(ctx.exception.code, 1)

    def test_real_dir_runs_without_crash(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "main.py").write_text("print('hello')\n")
            args = self._make_args(d)
            buf = io.StringIO()
            with redirect_stdout(buf):
                run_pack(args)
            self.assertIn("Selected", buf.getvalue())

    def test_json_format_output(self):
        import io, json
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "app.py").write_text("x = 1\n")
            args = self._make_args(d, fmt="json")
            buf = io.StringIO()
            with redirect_stdout(buf):
                run_pack(args)
            data = json.loads(buf.getvalue())
            self.assertIn("files", data)
            self.assertIn("meta", data)
            self.assertIn("budget", data)

    def test_line_budget_integration(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "app.py").write_text("line\n" * 100)
            args = self._make_args(d, budget="5-lines")
            buf = io.StringIO()
            with redirect_stdout(buf):
                run_pack(args)
            self.assertIn("lines", buf.getvalue())

    def test_focus_flag_passed_through(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "auth.py").write_text("# auth\n")
            (Path(d) / "utils.py").write_text("# utils\n")
            args = self._make_args(d, focus="auth")
            buf = io.StringIO()
            with redirect_stdout(buf):
                run_pack(args)
            # Should not crash; auth.py should appear
            self.assertIn("auth.py", buf.getvalue())


if __name__ == '__main__':
    unittest.main()
