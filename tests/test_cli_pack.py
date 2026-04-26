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
    _get_changed_files,
    _get_file_structure,
    _get_file_raw_content,
    _emit_content_section,
    _collect_file_contents,
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

    def test_large_init_scores_below_key_module_tier(self):
        """__init__.py with substantial content should NOT reach 'Key modules' tier.

        Large __init__.py files are packaging/re-export hubs, not logic. They
        should score < 2.0 so they land in 'Other files' and don't displace
        real modules from the key-module tier.
        """
        with tempfile.TemporaryDirectory() as d:
            # >2000 bytes triggers the __init__ bonus
            path, rel = self._make_file(Path(d), "pkg/__init__.py", "x" * 2100)
            score = _compute_priority(path, rel, focus=None)
            self.assertLess(score, 2.0)

    def test_large_init_scores_below_key_module(self):
        """A substantial __init__.py should rank below a module in a key directory.

        core/engine.py scores 2.0 (key-dir bonus); pkg/__init__.py scores 0.5.
        This ensures __init__ files don't displace real logic from 'Key modules'.
        """
        with tempfile.TemporaryDirectory() as d:
            init_path, init_rel = self._make_file(Path(d), "pkg/__init__.py", "x" * 2100)
            mod_path, mod_rel = self._make_file(Path(d), "core/engine.py", "x" * 100)
            init_score = _compute_priority(init_path, init_rel, focus=None)
            mod_score = _compute_priority(mod_path, mod_rel, focus=None)
            self.assertLess(init_score, mod_score)


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
        files = list(_walk_files(p))
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


# ---------------------------------------------------------------------------
# _compute_priority: is_changed boost
# ---------------------------------------------------------------------------

class TestComputePriorityChanged(unittest.TestCase):

    def _make_file(self, tmpdir: Path, rel: str, content: str = "x") -> tuple:
        p = tmpdir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return p, Path(rel)

    def test_changed_file_gets_highest_priority(self):
        with tempfile.TemporaryDirectory() as d:
            p, rel = self._make_file(Path(d), "utils.py")
            changed = _compute_priority(p, rel, focus=None, is_changed=True)
            unchanged = _compute_priority(p, rel, focus=None, is_changed=False)
            self.assertGreater(changed, unchanged)

    def test_changed_score_above_entry_point(self):
        """Changed file should rank above entry points (score > 10)."""
        with tempfile.TemporaryDirectory() as d:
            p, rel = self._make_file(Path(d), "utils.py")
            entry, entry_rel = self._make_file(Path(d), "main.py")
            changed_score = _compute_priority(p, rel, focus=None, is_changed=True)
            entry_score = _compute_priority(entry, entry_rel, focus=None, is_changed=False)
            self.assertGreater(changed_score, entry_score)

    def test_changed_entry_point_stacks(self):
        """A changed entry point gets both boosts."""
        with tempfile.TemporaryDirectory() as d:
            p, rel = self._make_file(Path(d), "main.py")
            changed = _compute_priority(p, rel, focus=None, is_changed=True)
            unchanged = _compute_priority(p, rel, focus=None, is_changed=False)
            self.assertGreater(changed, unchanged + 15)  # 20 point boost


# ---------------------------------------------------------------------------
# _collect_candidates: changed_files set
# ---------------------------------------------------------------------------

class TestCollectCandidatesChanged(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = Path(self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make(self, rel: str, content: str = "x\n") -> Path:
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return p

    def test_changed_file_gets_changed_flag(self):
        f = self._make("utils.py", "x\n")
        candidates = _collect_candidates(self.path, focus=None, changed_files={str(f.resolve())})
        entry = next(c for c in candidates if c['relative'] == 'utils.py')
        self.assertTrue(entry['changed'])

    def test_unchanged_file_has_changed_false(self):
        self._make("utils.py")
        candidates = _collect_candidates(self.path, focus=None, changed_files=set())
        entry = next(c for c in candidates if c['relative'] == 'utils.py')
        self.assertFalse(entry['changed'])

    def test_changed_file_sorts_first(self):
        self._make("aaa.py", "x\n")
        changed = self._make("zzz.py", "x\n")
        candidates = _collect_candidates(
            self.path, focus=None, changed_files={str(changed.resolve())}
        )
        self.assertEqual(candidates[0]['relative'], 'zzz.py')

    def test_no_changed_files_arg_defaults_to_no_boost(self):
        self._make("utils.py")
        candidates = _collect_candidates(self.path, focus=None)
        for c in candidates:
            self.assertFalse(c.get('changed'))


# ---------------------------------------------------------------------------
# _get_changed_files: git subprocess
# ---------------------------------------------------------------------------

class TestGetChangedFiles(unittest.TestCase):

    def test_not_a_git_repo_returns_error(self):
        with tempfile.TemporaryDirectory() as d:
            changed, err = _get_changed_files(Path(d), 'main')
            self.assertEqual(changed, set())
            self.assertIsNotNone(err)
            self.assertIn('git', err.lower())

    def test_bad_ref_returns_error(self):
        """An unknown git ref returns an error message, not an exception."""
        import subprocess as sp
        # Only run if the test directory is inside a git repo
        try:
            result = sp.run(['git', 'rev-parse', '--show-toplevel'],
                            capture_output=True, text=True,
                            cwd=str(Path(__file__).parent))
            if result.returncode != 0:
                self.skipTest("not in a git repo")
        except FileNotFoundError:
            self.skipTest("git not available")

        changed, err = _get_changed_files(Path(__file__).parent, 'nonexistent-ref-xyz-12345')
        self.assertEqual(changed, set())
        self.assertIsNotNone(err)

    def test_returns_set_of_abs_paths(self):
        """When run in a real git repo with HEAD~1, returns a set of strings."""
        import subprocess as sp
        try:
            result = sp.run(['git', 'rev-parse', 'HEAD~1'],
                            capture_output=True, text=True,
                            cwd=str(Path(__file__).parent))
            if result.returncode != 0:
                self.skipTest("not enough commits")
        except FileNotFoundError:
            self.skipTest("git not available")

        changed, err = _get_changed_files(Path(__file__).parent, 'HEAD~1')
        # No error expected (HEAD~1 always exists if we got past the check above)
        self.assertIsNone(err)
        # All entries should be strings (absolute paths)
        for p in changed:
            self.assertIsInstance(p, str)


# ---------------------------------------------------------------------------
# _render_pack: --since display
# ---------------------------------------------------------------------------

class TestRenderPackSince(unittest.TestCase):

    def _capture(self, selected, meta, verbose=False, budget_tokens=2000, budget_lines=None):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            _render_pack(Path('src/'), selected, meta, verbose, budget_tokens, budget_lines)
        return buf.getvalue()

    def _meta(self, **kwargs):
        base = {
            'total_candidates': 5, 'selected': 1, 'skipped': 0,
            'used_tokens_approx': 100, 'used_lines': 10,
            'budget_tokens': 2000, 'budget_lines': None,
        }
        base.update(kwargs)
        return base

    def _candidate(self, rel, changed=False, priority=1.0):
        return {
            'relative': rel, 'path': f'/tmp/{rel}',
            'priority': priority, 'tokens_approx': 100, 'lines': 10,
            'mtime': 0.0, 'size': 400, 'changed': changed,
        }

    def test_since_shown_in_header(self):
        meta = self._meta(since='main', changed_files_count=2)
        out = self._capture([self._candidate('a.py')], meta)
        self.assertIn('since main', out)

    def test_changed_files_count_shown(self):
        meta = self._meta(since='main', changed_files_count=3)
        out = self._capture([self._candidate('a.py')], meta)
        self.assertIn('3', out)

    def test_changed_tier_heading(self):
        meta = self._meta(since='HEAD~3', changed_files_count=1)
        candidates = [self._candidate('changed.py', changed=True, priority=20.0)]
        out = self._capture(candidates, meta)
        self.assertIn('Changed files', out)
        self.assertIn('HEAD~3', out)

    def test_changed_file_not_in_other_tiers(self):
        meta = self._meta(since='main', changed_files_count=1)
        candidates = [
            self._candidate('changed.py', changed=True, priority=20.0),
            self._candidate('entry.py', changed=False, priority=10.0),
        ]
        out = self._capture(candidates, meta)
        self.assertIn('Changed files', out)
        self.assertIn('Entry points', out)
        # changed.py should appear only once
        self.assertEqual(out.count('changed.py'), 1)

    def test_no_since_no_changed_tier(self):
        meta = self._meta()
        out = self._capture([self._candidate('a.py')], meta)
        self.assertNotIn('Changed files', out)
        self.assertNotIn('since', out)


# ---------------------------------------------------------------------------
# run_pack: --since integration
# ---------------------------------------------------------------------------

class TestRunPackSince(unittest.TestCase):

    def _make_args(self, path, budget="2000", focus=None, fmt="text", verbose=False, since=None):
        return Namespace(path=path, budget=budget, focus=focus, format=fmt,
                         verbose=verbose, since=since)

    def test_since_none_runs_normally(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "app.py").write_text("x = 1\n")
            args = self._make_args(d, since=None)
            buf = io.StringIO()
            with redirect_stdout(buf):
                run_pack(args)
            self.assertIn("Selected", buf.getvalue())

    def test_since_bad_ref_emits_warning_not_crash(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "app.py").write_text("x = 1\n")
            args = self._make_args(d, since='nonexistent-branch-xyz')
            buf = io.StringIO()
            stderr_buf = io.StringIO()
            import sys
            old_err = sys.stderr
            sys.stderr = stderr_buf
            try:
                with redirect_stdout(buf):
                    run_pack(args)
            finally:
                sys.stderr = old_err
            # Should still produce output (graceful degradation)
            self.assertIn("Selected", buf.getvalue())
            # Warning should mention --since
            self.assertIn('--since', stderr_buf.getvalue())

    def test_since_meta_in_json_output(self):
        import io, json
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "app.py").write_text("x = 1\n")
            args = self._make_args(d, fmt='json', since='HEAD~1')
            buf = io.StringIO()
            with redirect_stdout(buf):
                run_pack(args)
            data = json.loads(buf.getvalue())
            self.assertIn('since', data)

    def test_changed_flag_in_json_candidates(self):
        """Every file in JSON output has a 'changed' field."""
        import io, json
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "app.py").write_text("x = 1\n")
            args = self._make_args(d, fmt='json', since=None)
            buf = io.StringIO()
            with redirect_stdout(buf):
                run_pack(args)
            data = json.loads(buf.getvalue())
            for f in data['files']:
                self.assertIn('changed', f)


# ---------------------------------------------------------------------------
# Content emission: _get_file_structure, _emit_content_section,
# _collect_file_contents, run_pack --content
# ---------------------------------------------------------------------------

class TestGetFileStructure(unittest.TestCase):

    def test_returns_string_for_python_file(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("def hello():\n    pass\n")
            fpath = f.name
        result = _get_file_structure(fpath)
        self.assertIsInstance(result, str)
        # Should contain something about the function
        self.assertIn('hello', result)

    def test_returns_empty_string_for_missing_file(self):
        result = _get_file_structure('/nonexistent/path/file.xyz_unknown')
        self.assertEqual(result, '')

    def test_returns_empty_string_for_unanalyzable_extension(self):
        with tempfile.NamedTemporaryFile(suffix='.xyz_custom_unknown', mode='w', delete=False) as f:
            f.write("content\n")
            fpath = f.name
        # May or may not get tree-sitter fallback; should not crash
        result = _get_file_structure(fpath)
        self.assertIsInstance(result, str)


class TestGetFileRawContent(unittest.TestCase):

    def test_returns_file_content(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("def hello():\n    return 42\n")
            fpath = f.name
        result = _get_file_raw_content(fpath)
        self.assertIn('def hello', result)
        self.assertIn('return 42', result)

    def test_missing_file_returns_empty(self):
        result = _get_file_raw_content('/nonexistent/path/file.py')
        self.assertEqual(result, '')

    def test_truncates_at_max_lines(self):
        lines = [f"line {i}\n" for i in range(600)]
        with tempfile.NamedTemporaryFile(suffix='.txt', mode='w', delete=False) as f:
            f.writelines(lines)
            fpath = f.name
        result = _get_file_raw_content(fpath, max_lines=100)
        result_lines = result.splitlines()
        # Last line is the truncation notice
        self.assertIn('more lines not shown', result_lines[-1])
        # Content lines only up to max_lines
        content_lines = [l for l in result_lines if 'more lines not shown' not in l]
        self.assertLessEqual(len(content_lines), 100)

    def test_short_file_not_truncated(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("x = 1\ny = 2\n")
            fpath = f.name
        result = _get_file_raw_content(fpath, max_lines=500)
        self.assertNotIn('more lines not shown', result)

    def test_returns_string_type(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("pass\n")
            fpath = f.name
        result = _get_file_raw_content(fpath)
        self.assertIsInstance(result, str)


class TestEmitContentSection(unittest.TestCase):

    def _make_file_infos(self, files):
        """Build minimal file info dicts for testing.

        Each entry: (path, rel, changed, priority=2.0)
        """
        infos = []
        for entry in files:
            fp, rel, changed = entry[0], entry[1], entry[2]
            priority = entry[3] if len(entry) > 3 else 2.0
            infos.append({'path': fp, 'relative': rel, 'changed': changed, 'priority': priority})
        return infos

    def test_emits_content_header(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("x = 1\n")
            fpath = f.name
        infos = self._make_file_infos([(fpath, 'x.py', False)])
        buf = io.StringIO()
        with redirect_stdout(buf):
            _emit_content_section(infos)
        output = buf.getvalue()
        self.assertIn('CONTENT', output)
        self.assertIn('x.py', output)

    def test_changed_file_gets_tag(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("def foo(): pass\n")
            fpath = f.name
        infos = self._make_file_infos([(fpath, 'foo.py', True, 20.0)])
        buf = io.StringIO()
        with redirect_stdout(buf):
            _emit_content_section(infos)
        self.assertIn('CHANGED', buf.getvalue())

    def test_changed_file_gets_full_content_not_structure(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("def secret_impl():\n    return 42\n")
            fpath = f.name
        infos = self._make_file_infos([(fpath, 'impl.py', True, 20.0)])
        buf = io.StringIO()
        with redirect_stdout(buf):
            _emit_content_section(infos)
        output = buf.getvalue()
        # Full content includes the actual implementation body
        self.assertIn('return 42', output)
        self.assertIn('full content', output)

    def test_low_priority_file_shown_as_name_only(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("x = 1\n")
            fpath = f.name
        infos = self._make_file_infos([(fpath, 'misc.py', False, 0.0)])
        buf = io.StringIO()
        with redirect_stdout(buf):
            _emit_content_section(infos)
        output = buf.getvalue()
        self.assertIn('misc.py', output)
        self.assertIn('Low-priority', output)
        # Should NOT include file content (just name)
        self.assertNotIn('x = 1', output)

    def test_high_priority_non_changed_gets_structure(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("def authenticate(): pass\n")
            fpath = f.name
        infos = self._make_file_infos([(fpath, 'auth.py', False, 10.0)])
        buf = io.StringIO()
        with redirect_stdout(buf):
            _emit_content_section(infos)
        output = buf.getvalue()
        self.assertIn('auth.py', output)
        # Should NOT have 'full content' tag
        self.assertNotIn('full content', output)
        # Should NOT have 'Low-priority' section
        self.assertNotIn('Low-priority', output)

    def test_unknown_file_type_shows_fallback_message(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.NamedTemporaryFile(suffix='.xyzunknownext', mode='w', delete=False) as f:
            f.write("no analyzer here\n")
            fpath = f.name
        infos = self._make_file_infos([(fpath, 'mystery.xyzunknownext', False)])
        buf = io.StringIO()
        with redirect_stdout(buf):
            _emit_content_section(infos)
        output = buf.getvalue()
        self.assertIn('mystery.xyzunknownext', output)
        # Either structure output or fallback message — no crash
        self.assertIn('\n', output)


class TestCollectFileContents(unittest.TestCase):

    def test_returns_list_of_dicts(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("x = 1\n")
            fpath = f.name
        infos = [{'path': fpath, 'relative': 'x.py', 'changed': False, 'priority': 2.0}]
        result = _collect_file_contents(infos)
        self.assertEqual(len(result), 1)
        item = result[0]
        self.assertIn('file', item)
        self.assertIn('changed', item)
        self.assertIn('content', item)
        self.assertIn('content_type', item)
        self.assertEqual(item['file'], 'x.py')
        self.assertFalse(item['changed'])

    def test_content_is_string(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("def bar(): pass\n")
            fpath = f.name
        infos = [{'path': fpath, 'relative': 'bar.py', 'changed': False, 'priority': 5.0}]
        result = _collect_file_contents(infos)
        self.assertIsInstance(result[0]['content'], str)
        self.assertFalse(result[0]['changed'])

    def test_changed_file_gets_full_content_type(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("def bar(): pass\n")
            fpath = f.name
        infos = [{'path': fpath, 'relative': 'bar.py', 'changed': True, 'priority': 20.0}]
        result = _collect_file_contents(infos)
        self.assertEqual(result[0]['content_type'], 'full')
        # Full content should include actual source code
        self.assertIn('def bar', result[0]['content'])

    def test_non_changed_high_priority_gets_structure_type(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("def foo():\n    pass\n")
            fpath = f.name
        infos = [{'path': fpath, 'relative': 'foo.py', 'changed': False, 'priority': 5.0}]
        result = _collect_file_contents(infos)
        self.assertEqual(result[0]['content_type'], 'structure')

    def test_low_priority_file_gets_name_only_type(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("x = 1\n")
            fpath = f.name
        infos = [{'path': fpath, 'relative': 'misc.py', 'changed': False, 'priority': 0.0}]
        result = _collect_file_contents(infos)
        self.assertEqual(result[0]['content_type'], 'name_only')
        self.assertEqual(result[0]['content'], '')


class TestRunPackContent(unittest.TestCase):

    def _make_args(self, path, budget='2000', fmt='text', since=None, content=False):
        return Namespace(
            path=str(path),
            budget=budget,
            focus=None,
            since=since,
            content=content,
            format=fmt,
            verbose=False,
        )

    def test_content_flag_adds_content_section(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "app.py").write_text("def main():\n    pass\n")
            args = self._make_args(d, content=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                run_pack(args)
            output = buf.getvalue()
            self.assertIn('CONTENT', output)
            self.assertIn('app.py', output)

    def test_no_content_flag_no_content_section(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "app.py").write_text("x = 1\n")
            args = self._make_args(d, content=False)
            buf = io.StringIO()
            with redirect_stdout(buf):
                run_pack(args)
            output = buf.getvalue()
            self.assertNotIn('CONTENT', output)

    def test_content_json_includes_content_key(self):
        import io, json
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "app.py").write_text("def main(): pass\n")
            args = self._make_args(d, fmt='json', content=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                run_pack(args)
            data = json.loads(buf.getvalue())
            self.assertIn('content', data)
            self.assertIsInstance(data['content'], list)
            self.assertGreater(len(data['content']), 0)

    def test_content_json_without_flag_no_content_key(self):
        import io, json
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "app.py").write_text("x = 1\n")
            args = self._make_args(d, fmt='json', content=False)
            buf = io.StringIO()
            with redirect_stdout(buf):
                run_pack(args)
            data = json.loads(buf.getvalue())
            self.assertNotIn('content', data)

    def test_content_structure_contains_function_names(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "auth.py").write_text(
                "def authenticate(user, pwd):\n    return True\n\ndef logout():\n    pass\n"
            )
            args = self._make_args(d, content=True, budget='5000')
            buf = io.StringIO()
            with redirect_stdout(buf):
                run_pack(args)
            output = buf.getvalue()
            # Structure output should reference function names
            self.assertIn('authenticate', output)
            self.assertIn('logout', output)


# ---------------------------------------------------------------------------
# BACK-213: --architecture / fan-in scoring
# ---------------------------------------------------------------------------

class TestComputePriorityFanIn(unittest.TestCase):

    def _make_file(self, tmpdir: Path, rel: str, content: str = "x") -> tuple:
        full = tmpdir / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
        return full, Path(rel)

    def test_no_fan_in_no_boost(self):
        with tempfile.TemporaryDirectory() as d:
            path, rel = self._make_file(Path(d), "utils.py")
            score_zero = _compute_priority(path, rel, focus=None, fan_in=0)
            score_none = _compute_priority(path, rel, focus=None)
            self.assertEqual(score_zero, score_none)

    def test_low_fan_in_small_boost(self):
        with tempfile.TemporaryDirectory() as d:
            path, rel = self._make_file(Path(d), "utils.py")
            score_no_fan = _compute_priority(path, rel, focus=None, fan_in=0)
            score_fan1 = _compute_priority(path, rel, focus=None, fan_in=1)
            self.assertAlmostEqual(score_fan1 - score_no_fan, 1.0)

    def test_mid_fan_in_medium_boost(self):
        with tempfile.TemporaryDirectory() as d:
            path, rel = self._make_file(Path(d), "utils.py")
            score_no_fan = _compute_priority(path, rel, focus=None, fan_in=0)
            score_fan5 = _compute_priority(path, rel, focus=None, fan_in=5)
            self.assertAlmostEqual(score_fan5 - score_no_fan, 3.0)

    def test_high_fan_in_large_boost(self):
        with tempfile.TemporaryDirectory() as d:
            path, rel = self._make_file(Path(d), "utils.py")
            score_no_fan = _compute_priority(path, rel, focus=None, fan_in=0)
            score_fan15 = _compute_priority(path, rel, focus=None, fan_in=15)
            self.assertAlmostEqual(score_fan15 - score_no_fan, 5.0)

    def test_fan_in_14_gets_mid_boost(self):
        with tempfile.TemporaryDirectory() as d:
            path, rel = self._make_file(Path(d), "utils.py")
            score_no_fan = _compute_priority(path, rel, focus=None, fan_in=0)
            score_fan14 = _compute_priority(path, rel, focus=None, fan_in=14)
            self.assertAlmostEqual(score_fan14 - score_no_fan, 3.0)

    def test_score_never_negative_with_fan_in(self):
        with tempfile.TemporaryDirectory() as d:
            path, rel = self._make_file(Path(d), "tests/test_big.py", "x" * 51_000)
            score = _compute_priority(path, rel, focus=None, fan_in=20)
            self.assertGreaterEqual(score, 0.0)


class TestFetchFanIn(unittest.TestCase):

    def test_graceful_failure_returns_empty_dict(self):
        from reveal.cli.commands.pack import _fetch_fan_in
        # Non-existent path — should return {} without raising
        result = _fetch_fan_in(Path("/nonexistent/path/that/cannot/exist"))
        self.assertIsInstance(result, dict)

    def test_returns_dict_for_valid_path(self):
        from reveal.cli.commands.pack import _fetch_fan_in
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.py").write_text("import b\n")
            (Path(d) / "b.py").write_text("X = 1\n")
            result = _fetch_fan_in(Path(d))
            self.assertIsInstance(result, dict)


class TestRenderArchitectureBrief(unittest.TestCase):

    def _capture(self, selected):
        import io
        from contextlib import redirect_stdout
        from reveal.cli.commands.pack import _render_architecture_brief
        buf = io.StringIO()
        with redirect_stdout(buf):
            _render_architecture_brief(selected)
        return buf.getvalue()

    def test_shows_entry_points(self):
        selected = [
            {'relative': 'main.py', 'priority': 10.0, 'fan_in': 0, 'changed': False},
        ]
        output = self._capture(selected)
        self.assertIn('Entry points', output)
        self.assertIn('main.py', output)

    def test_shows_core_abstractions(self):
        selected = [
            {'relative': 'utils.py', 'priority': 3.0, 'fan_in': 12, 'changed': False},
        ]
        output = self._capture(selected)
        self.assertIn('Core abstractions', output)
        self.assertIn('utils.py(12)', output)

    def test_no_entry_points_omits_that_line(self):
        selected = [
            {'relative': 'utils.py', 'priority': 1.0, 'fan_in': 8, 'changed': False},
        ]
        output = self._capture(selected)
        self.assertNotIn('Entry points', output)

    def test_no_core_abstractions_omits_that_line(self):
        selected = [
            {'relative': 'main.py', 'priority': 10.0, 'fan_in': 0, 'changed': False},
        ]
        output = self._capture(selected)
        self.assertNotIn('Core abstractions', output)

    def test_core_abstractions_sorted_by_fan_in_desc(self):
        selected = [
            {'relative': 'low.py', 'priority': 1.0, 'fan_in': 5, 'changed': False},
            {'relative': 'high.py', 'priority': 1.0, 'fan_in': 20, 'changed': False},
        ]
        output = self._capture(selected)
        self.assertLess(output.index('high.py'), output.index('low.py'))

    def test_core_abstractions_capped_at_five(self):
        selected = [
            {'relative': f'mod{i}.py', 'priority': 1.0, 'fan_in': 10 + i, 'changed': False}
            for i in range(8)
        ]
        output = self._capture(selected)
        # Only top 5 should appear
        shown = [f'mod{i}.py' for i in range(8) if f'mod{i}.py' in output]
        self.assertLessEqual(len(shown), 5)

    def test_section_renamed_to_architecture_hint(self):
        output = self._capture([
            {'relative': 'main.py', 'priority': 10.0, 'fan_in': 0, 'changed': False},
        ])
        self.assertIn('Architecture Hint', output)
        self.assertNotIn('Architecture Brief', output)

    def test_focus_match_priority_8_shown_as_entry_point(self):
        # priority=8 files (focus-matched) should appear as entry points
        selected = [
            {'relative': 'src/signals.py', 'priority': 8.0, 'fan_in': 0, 'changed': False},
        ]
        output = self._capture(selected)
        self.assertIn('Entry points', output)
        self.assertIn('src/signals.py', output)

    def test_top_files_fallback_when_nothing_qualifies(self):
        # No entry points (priority < 8), no core abstractions (fan_in < 5)
        selected = [
            {'relative': 'a.py', 'priority': 3.0, 'fan_in': 0, 'changed': False},
            {'relative': 'b.py', 'priority': 2.0, 'fan_in': 0, 'changed': False},
        ]
        output = self._capture(selected)
        self.assertIn('Top files', output)
        self.assertIn('a.py', output)

    def test_top_files_fallback_not_shown_when_core_exists(self):
        selected = [
            {'relative': 'utils.py', 'priority': 1.0, 'fan_in': 10, 'changed': False},
        ]
        output = self._capture(selected)
        self.assertNotIn('Top files', output)


class TestCollectCandidatesWithFanIn(unittest.TestCase):

    def test_fan_in_scores_boost_priority(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "utils.py").write_text("X = 1\n")
            (Path(d) / "main.py").write_text("import utils\n")

            candidates_no_fan = _collect_candidates(Path(d), focus=None)
            utils_no_fan = next(c for c in candidates_no_fan if 'utils' in c['relative'])

            abs_utils = str((Path(d) / "utils.py").resolve())
            fan_in_scores = {abs_utils: 10}
            candidates_fan = _collect_candidates(Path(d), focus=None, fan_in_scores=fan_in_scores)
            utils_fan = next(c for c in candidates_fan if 'utils' in c['relative'])

            self.assertGreater(utils_fan['priority'], utils_no_fan['priority'])

    def test_fan_in_stored_in_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "utils.py").write_text("X = 1\n")
            abs_utils = str((Path(d) / "utils.py").resolve())
            fan_in_scores = {abs_utils: 7}
            candidates = _collect_candidates(Path(d), focus=None, fan_in_scores=fan_in_scores)
            utils = next(c for c in candidates if 'utils' in c['relative'])
            self.assertEqual(utils['fan_in'], 7)

    def test_missing_fan_in_defaults_to_zero(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "utils.py").write_text("X = 1\n")
            candidates = _collect_candidates(Path(d), focus=None, fan_in_scores={})
            utils = next(c for c in candidates if 'utils' in c['relative'])
            self.assertEqual(utils['fan_in'], 0)


class TestRunPackArchitecture(unittest.TestCase):

    def _make_args(self, path, budget='2000', architecture=False):
        return Namespace(
            path=str(path),
            budget=budget,
            focus=None,
            since=None,
            content=False,
            format='text',
            verbose=False,
            architecture=architecture,
        )

    def test_architecture_flag_shows_brief(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "main.py").write_text("import utils\n")
            (Path(d) / "utils.py").write_text("X = 1\n")
            args = self._make_args(d, budget='5000', architecture=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                run_pack(args)
            output = buf.getvalue()
            self.assertIn('Architecture Hint', output)

    def test_no_architecture_flag_no_brief(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "main.py").write_text("import utils\n")
            (Path(d) / "utils.py").write_text("X = 1\n")
            args = self._make_args(d, budget='5000', architecture=False)
            buf = io.StringIO()
            with redirect_stdout(buf):
                run_pack(args)
            output = buf.getvalue()
            self.assertNotIn('Architecture Hint', output)


if __name__ == '__main__':
    unittest.main()
