"""Tests for reveal MCP server tools.

Tests verify that each tool returns plausible output for real inputs.
They do NOT test the MCP protocol itself (that's the SDK's job) — they
test reveal_structure, reveal_element, reveal_nav, reveal_query, reveal_pack,
reveal_check, reveal_grep, and reveal_trace as callable Python functions.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TestRevealStructureTool(unittest.TestCase):

    def setUp(self):
        from reveal.mcp_server import reveal_structure
        self.reveal_structure = reveal_structure
        self._orig_dir = os.getcwd()
        # Work from the repo root so relative paths resolve
        os.chdir(Path(__file__).parent.parent)

    def tearDown(self):
        os.chdir(self._orig_dir)

    def test_file_returns_function_names(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("def greet(name):\n    return f'Hello {name}'\n\ndef farewell():\n    pass\n")
            fpath = f.name
        try:
            result = self.reveal_structure(fpath)
            self.assertIsInstance(result, str)
            self.assertIn('greet', result)
            self.assertIn('farewell', result)
        finally:
            os.unlink(fpath)

    def test_directory_returns_file_listing(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'app.py').write_text("x = 1\n")
            (Path(d) / 'utils.py').write_text("y = 2\n")
            result = self.reveal_structure(d)
            self.assertIsInstance(result, str)
            self.assertIn('app.py', result)
            self.assertIn('utils.py', result)

    def test_missing_path_returns_error_string(self):
        result = self.reveal_structure('/nonexistent/path/xyz')
        self.assertIsInstance(result, str)
        # Should return an error message, not raise
        self.assertGreater(len(result), 0)

    def test_real_python_file_has_no_crash(self):
        # Use reveal's own codebase
        result = self.reveal_structure('reveal/utils/query.py')
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_returns_string_not_none(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("pass\n")
            fpath = f.name
        try:
            result = self.reveal_structure(fpath)
            self.assertIsNotNone(result)
            self.assertIsInstance(result, str)
        finally:
            os.unlink(fpath)


class TestRevealElementTool(unittest.TestCase):

    def setUp(self):
        from reveal.mcp_server import reveal_element
        self.reveal_element = reveal_element
        self._orig_dir = os.getcwd()
        os.chdir(Path(__file__).parent.parent)

    def tearDown(self):
        os.chdir(self._orig_dir)

    def test_extracts_function_body(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("def add(a, b):\n    return a + b\n\ndef mul(a, b):\n    return a * b\n")
            fpath = f.name
        try:
            result = self.reveal_element(fpath, 'add')
            self.assertIsInstance(result, str)
            self.assertIn('add', result)
            self.assertIn('return a + b', result)
        finally:
            os.unlink(fpath)

    def test_real_codebase_function(self):
        result = self.reveal_element('reveal/utils/query.py', 'parse_query_params')
        self.assertIsInstance(result, str)
        self.assertIn('parse_query_params', result)

    def test_missing_element_returns_string(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("x = 1\n")
            fpath = f.name
        try:
            result = self.reveal_element(fpath, 'nonexistent_function')
            self.assertIsInstance(result, str)
        finally:
            os.unlink(fpath)

    def test_missing_path_returns_error_string_not_raw_exception(self):
        # Every other reveal_* tool returns "[reveal error: ...]" on a bad
        # path instead of propagating a raw exception -- reveal_element must
        # match, not leak an unguarded FileNotFoundError with the full path.
        result = self.reveal_element('/nonexistent/path/xyz.py', 'foo')
        self.assertIsInstance(result, str)
        self.assertIn('reveal error', result)


class TestRevealNavTool(unittest.TestCase):

    def setUp(self):
        from reveal.mcp_server import reveal_nav
        self.reveal_nav = reveal_nav
        self._orig_dir = os.getcwd()
        os.chdir(Path(__file__).parent.parent)

    def tearDown(self):
        os.chdir(self._orig_dir)

    def test_returns_string(self):
        result = self.reveal_nav('reveal/adapters/ast/nav_effects.py', 'collect_effects', 'deps')
        self.assertIsInstance(result, str)

    def test_deps_flag_produces_output(self):
        result = self.reveal_nav('reveal/adapters/ast/nav_effects.py', 'collect_effects', 'deps')
        self.assertNotIn('[reveal error', result)
        self.assertGreater(len(result), 0)

    def test_boundary_flag_produces_sections(self):
        result = self.reveal_nav('reveal/adapters/ast/nav_effects.py', 'collect_effects', 'boundary')
        self.assertIn('INPUTS', result)
        self.assertIn('EFFECTS', result)

    def test_sideeffects_flag(self):
        result = self.reveal_nav('reveal/adapters/ast/nav_effects.py', 'collect_effects', 'sideeffects')
        self.assertIsInstance(result, str)
        self.assertNotIn('[reveal error', result)

    def test_varflow_requires_flag_value(self):
        result = self.reveal_nav('reveal/adapters/ast/nav_effects.py', 'collect_effects', 'varflow')
        self.assertIn('[reveal error', result)
        self.assertIn('flag_value', result)

    def test_varflow_with_value(self):
        result = self.reveal_nav('reveal/adapters/ast/nav_effects.py', 'collect_effects', 'varflow', 'calls')
        self.assertIsInstance(result, str)
        self.assertNotIn('[reveal error', result)

    def test_loopmap_flag(self):
        result = self.reveal_nav('reveal/adapters/ast/nav_exits.py', 'collect_gate_chains', 'loopmap')
        self.assertIsInstance(result, str)
        self.assertNotIn('[reveal error', result)

    def test_fanout_flag(self):
        result = self.reveal_nav('reveal/adapters/ast/nav_exits.py', 'collect_gate_chains', 'fanout')
        self.assertIsInstance(result, str)
        self.assertNotIn('[reveal error', result)

    def test_statewrites_flag(self):
        result = self.reveal_nav('reveal/adapters/ast/nav_exits.py', 'collect_gate_chains', 'statewrites')
        self.assertIsInstance(result, str)
        self.assertNotIn('[reveal error', result)

    def test_narrow_requires_flag_value(self):
        result = self.reveal_nav('reveal/adapters/ast/nav_effects.py', 'collect_effects', 'narrow')
        self.assertIn('[reveal error', result)
        self.assertIn('flag_value', result)

    def test_narrow_with_value(self):
        result = self.reveal_nav('reveal/adapters/ast/nav_effects.py', 'collect_effects', 'narrow', 'calls')
        self.assertIsInstance(result, str)
        self.assertNotIn('[reveal error', result)

    def test_unknown_flag_returns_error(self):
        result = self.reveal_nav('reveal/adapters/ast/nav_effects.py', 'collect_effects', 'notaflag')
        self.assertIn('[reveal error', result)
        self.assertIn('notaflag', result)

    def test_around_with_invalid_value_returns_error(self):
        result = self.reveal_nav('reveal/adapters/ast/nav_effects.py', ':70', 'around', 'notanint')
        self.assertIn('[reveal error', result)

    def test_flat_file_line_range(self):
        result = self.reveal_nav('reveal/adapters/ast/nav_effects.py', ':68-87', 'sideeffects')
        self.assertIsInstance(result, str)
        self.assertNotIn('[reveal error', result)

    def test_every_dispatch_boolean_flag_is_reachable(self):
        # BACK-457 regression: every boolean flag name nav_handlers._NAV_DISPATCH
        # declares must actually work through reveal_nav, not just appear in a
        # hand-maintained list that can silently drift (as loopmap/fanout/
        # statewrites/writes previously did). Exercises the real dispatch table
        # instead of a copy of it, so a newly added flag can't be forgotten here.
        from reveal.nav_handlers import NAV_BOOLEAN_FLAG_NAMES
        for flag in sorted(NAV_BOOLEAN_FLAG_NAMES - {'scope'}):
            result = self.reveal_nav('reveal/adapters/ast/nav_exits.py', 'collect_gate_chains', flag)
            self.assertNotIn(
                '[reveal error: unknown nav flag', result,
                f"flag '{flag}' from NAV_BOOLEAN_FLAG_NAMES is not dispatched by reveal_nav",
            )

    def test_writes_alias_reachable_via_mcp(self):
        # 'writes' is the CLI's documented alias for 'mutations' but was missing
        # from the old hand-maintained MCP boolean-flag set entirely.
        result = self.reveal_nav('reveal/adapters/ast/nav_exits.py', 'collect_gate_chains', 'writes')
        self.assertIsInstance(result, str)
        self.assertNotIn('[reveal error', result)


class TestRevealQueryTool(unittest.TestCase):

    def setUp(self):
        from reveal.mcp_server import reveal_query
        self.reveal_query = reveal_query
        self._orig_dir = os.getcwd()
        os.chdir(Path(__file__).parent.parent)

    def tearDown(self):
        os.chdir(self._orig_dir)

    def test_ast_query_returns_functions(self):
        result = self.reveal_query('ast://reveal/utils/query.py?show=functions')
        self.assertIsInstance(result, str)
        self.assertIn('parse_query_params', result)

    def test_calls_uncalled_query(self):
        result = self.reveal_query('calls://reveal/utils/?uncalled')
        self.assertIsInstance(result, str)
        # Should get some output without crashing
        self.assertGreater(len(result), 0)

    def test_invalid_scheme_returns_error(self):
        result = self.reveal_query('notascheme://something')
        self.assertIsInstance(result, str)
        # Should gracefully return error, not crash

    def test_help_quick_uri(self):
        result = self.reveal_query('help://quick')
        self.assertIsInstance(result, str)
        # help://quick should return the quick help
        self.assertGreater(len(result), 0)

    def test_imports_unused_query(self):
        result = self.reveal_query('imports://reveal/utils/query.py?unused')
        self.assertIsInstance(result, str)


class TestRevealPackTool(unittest.TestCase):

    def setUp(self):
        from reveal.mcp_server import reveal_pack
        self.reveal_pack = reveal_pack

    def test_pack_returns_selected_files(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'main.py').write_text("def main():\n    pass\n")
            (Path(d) / 'utils.py').write_text("def helper():\n    pass\n")
            result = self.reveal_pack(d, budget=5000)
            self.assertIsInstance(result, str)
            self.assertIn('Pack:', result)
            self.assertIn('Selected', result)

    def test_pack_with_content(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'app.py').write_text("def run():\n    pass\n")
            result = self.reveal_pack(d, budget=5000, content=True)
            self.assertIsInstance(result, str)
            self.assertIn('CONTENT', result)

    def test_pack_without_content(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'app.py').write_text("x = 1\n")
            result = self.reveal_pack(d, budget=1000, content=False)
            self.assertIsInstance(result, str)
            self.assertNotIn('CONTENT', result)

    def test_pack_missing_path_returns_string(self):
        result = self.reveal_pack('/nonexistent/path/xyz')
        self.assertIsInstance(result, str)


class TestRevealCheckTool(unittest.TestCase):

    def setUp(self):
        from reveal.mcp_server import reveal_check
        self.reveal_check = reveal_check

    def test_clean_file_returns_output(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("x = 1\n")
            fpath = f.name
        try:
            result = self.reveal_check(fpath)
            self.assertIsInstance(result, str)
        finally:
            os.unlink(fpath)

    def test_severity_filter_accepted(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("x = 1\n")
            fpath = f.name
        try:
            result = self.reveal_check(fpath, severity='high')
            self.assertIsInstance(result, str)
        finally:
            os.unlink(fpath)

    def test_missing_path_returns_string(self):
        result = self.reveal_check('/nonexistent/path.py')
        self.assertIsInstance(result, str)

    def test_select_filter_accepted(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("x = 1\n")
            fpath = f.name
        try:
            result = self.reveal_check(fpath, select='B')
            self.assertIsInstance(result, str)
        finally:
            os.unlink(fpath)

    def test_ignore_filter_accepted(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("x = 1\n")
            fpath = f.name
        try:
            result = self.reveal_check(fpath, ignore='N')
            self.assertIsInstance(result, str)
        finally:
            os.unlink(fpath)

    def test_select_narrows_results_vs_unfiltered(self):
        with tempfile.TemporaryDirectory() as d:
            fpath = Path(d) / 'app.py'
            fpath.write_text("def f():\n    pass\n")
            unfiltered_calls = {}
            from reveal.cli import file_checker as fc

            original = fc._check_files_json

            def spy(*args, **kwargs):
                unfiltered_calls['select'] = args[2] if len(args) > 2 else kwargs.get('select')
                unfiltered_calls['ignore'] = args[3] if len(args) > 3 else kwargs.get('ignore')
                return original(*args, **kwargs)

            with patch.object(fc, '_check_files_json', side_effect=spy):
                self.reveal_check(str(d), select='M', ignore='N')
            self.assertEqual(unfiltered_calls['select'], ['M'])
            self.assertEqual(unfiltered_calls['ignore'], ['N'])


class TestRevealHealthTool(unittest.TestCase):

    def setUp(self):
        from reveal.mcp_server import reveal_health
        self.reveal_health = reveal_health

    def test_healthy_code_target_passes(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'app.py').write_text("x = 1\n")
            result = self.reveal_health(d)
            self.assertIsInstance(result, str)
            self.assertIn('PASS', result)

    def test_select_filter_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'app.py').write_text("x = 1\n")
            result = self.reveal_health(d, select='B,S')
            self.assertIsInstance(result, str)

    def test_missing_target_returns_error_string(self):
        result = self.reveal_health('/nonexistent/path/xyz')
        self.assertIsInstance(result, str)
        self.assertIn('not found', result)

    def test_uri_target_routes_to_uri_check(self):
        """A non-code URI target (unknown scheme) should not be treated as a path."""
        result = self.reveal_health('nosuchscheme://example.com')
        self.assertIsInstance(result, str)


class TestRevealReviewTool(unittest.TestCase):

    def setUp(self):
        from reveal.mcp_server import reveal_review
        self.reveal_review = reveal_review

    def test_directory_target_returns_report(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'app.py').write_text("def run():\n    pass\n")
            result = self.reveal_review(d)
            self.assertIsInstance(result, str)
            self.assertIn('Review:', result)

    def test_select_filter_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'app.py').write_text("def run():\n    pass\n")
            result = self.reveal_review(d, select='B,S')
            self.assertIsInstance(result, str)

    def test_git_range_target_does_not_crash(self):
        """A git-range target (diff-scoped review) should not raise, even on a
        range with 0 changed files -- also exercises the argument-injection
        fix (BACK-1141) via a target that would otherwise be a single-token
        git-diff argv element."""
        result = self.reveal_review('HEAD..HEAD')
        self.assertIsInstance(result, str)


class TestRevealGrepTool(unittest.TestCase):

    def setUp(self):
        from reveal.mcp_server import reveal_grep
        self.reveal_grep = reveal_grep

    def test_file_search_finds_match(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("def greet(name):\n    return f'Hello {name}'\n")
            fpath = f.name
        try:
            result = self.reveal_grep(fpath, 'greet')
            self.assertIsInstance(result, str)
            self.assertIn('greet', result)
        finally:
            os.unlink(fpath)

    def test_directory_search_finds_match(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'a.py').write_text("API_TIMEOUT = 30\n")
            (Path(d) / 'b.py').write_text("x = 1\n")
            result = self.reveal_grep(d, 'API_TIMEOUT')
            self.assertIsInstance(result, str)
            self.assertIn('a.py', result)

    def test_ignore_case(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("VALUE = 1\n")
            fpath = f.name
        try:
            result = self.reveal_grep(fpath, 'value', ignore_case=True)
            self.assertIn('1 hit', result)
        finally:
            os.unlink(fpath)

    def test_missing_path_returns_error_string(self):
        result = self.reveal_grep('/nonexistent/path/xyz', 'pattern')
        self.assertIsInstance(result, str)
        self.assertIn('not found', result)


class TestRevealTraceTool(unittest.TestCase):

    def setUp(self):
        from reveal.mcp_server import reveal_trace
        self.reveal_trace = reveal_trace

    def test_trace_from_entry_point(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'app.py').write_text(
                "def helper():\n    pass\n\n"
                "def main():\n    helper()\n"
            )
            result = self.reveal_trace(d, 'main', depth=2)
            self.assertIsInstance(result, str)
            self.assertIn('main', result)

    def test_unresolved_entry_point_returns_error_string(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'app.py').write_text("def main():\n    pass\n")
            result = self.reveal_trace(d, 'does_not_exist_xyz')
            self.assertIsInstance(result, str)
            self.assertIn('not found', result)

    def test_missing_path_returns_error_string(self):
        result = self.reveal_trace('/nonexistent/path/xyz', 'main')
        self.assertIsInstance(result, str)
        self.assertIn('not found', result)


class TestCaptureHelper(unittest.TestCase):
    """Tests for the _run_and_capture() internal helper."""

    def setUp(self):
        from reveal.mcp_server import _run_and_capture
        self._capture = _run_and_capture

    def test_captures_stdout(self):
        def fn():
            print("hello stdout")
        result = self._capture(fn)
        self.assertIn("hello stdout", result)

    def test_captures_stderr_on_exit_1(self):
        """Non-zero SystemExit: stderr message should appear in the response."""
        def fn():
            print("error detail", file=sys.stderr)
            raise SystemExit(1)
        result = self._capture(fn)
        self.assertIn("error detail", result)
        self.assertIn("1", result)  # exit code mentioned

    def test_captures_stderr_appended_to_stdout(self):
        """When both stdout and stderr produced, both appear in result."""
        def fn():
            print("normal output")
            print("warning detail", file=sys.stderr)
        result = self._capture(fn)
        self.assertIn("normal output", result)
        self.assertIn("warning detail", result)

    def test_stderr_only_returned_as_stderr_prefix(self):
        """Stderr with no stdout is returned with [stderr: ...] prefix."""
        def fn():
            print("just stderr", file=sys.stderr)
        result = self._capture(fn)
        self.assertIn("just stderr", result)

    def test_systemexit_0_swallowed(self):
        def fn():
            print("clean exit")
            raise SystemExit(0)
        result = self._capture(fn)
        self.assertIn("clean exit", result)

    def test_exception_returns_error_string(self):
        def fn():
            raise ValueError("something broke")
        result = self._capture(fn)
        self.assertIn("reveal error", result)
        self.assertIn("something broke", result)

    def test_concurrent_calls_do_not_cross_attribute_output(self):
        """BACK-898: concurrent _run_and_capture calls must not race on
        process-global sys.stdout/sys.stderr and leak each other's output."""
        import threading
        import time

        results = {}

        def make_fn(label):
            def fn():
                print(f"start-{label}")
                time.sleep(0.05)
                print(f"end-{label}")
            return fn

        def worker(label):
            results[label] = self._capture(make_fn(label))

        labels = [f"call{i}" for i in range(8)]
        threads = [threading.Thread(target=worker, args=(label,)) for label in labels]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for label in labels:
            result = results[label]
            self.assertIn(f"start-{label}", result)
            self.assertIn(f"end-{label}", result)
            for other in labels:
                if other != label:
                    self.assertNotIn(f"start-{other}", result)
                    self.assertNotIn(f"end-{other}", result)


class TestUpdateCheckSuppressed(unittest.TestCase):
    """MCP server must suppress reveal's update-check stdout injection."""

    def test_reveal_no_update_check_set(self):
        """REVEAL_NO_UPDATE_CHECK must be set at import time.

        Must import reveal.mcp_server itself rather than relying on a sibling
        test's setUp() having already triggered it in this worker process --
        under xdist, a worker that only ever runs this one test item (e.g.
        `-k TestUpdateCheckSuppressed`, or an unlucky item distribution) would
        otherwise never see the module-level setdefault() fire. BACK-REVEAL-5.
        """
        import os
        import reveal.mcp_server  # noqa: F401 -- import for its setdefault() side effect
        self.assertEqual(os.environ.get('REVEAL_NO_UPDATE_CHECK'), '1')

    def test_reveal_check_output_has_no_update_notice(self):
        """reveal_check output must not contain update notice text."""
        from reveal.mcp_server import reveal_check
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("x = 1\n")
            fpath = f.name
        try:
            result = reveal_check(fpath)
            self.assertNotIn('Update available', result)
            self.assertNotIn('pip install --upgrade', result)
        finally:
            os.unlink(fpath)


class TestMcpToolErrorSignaling(unittest.TestCase):
    """BACK-REVEAL-1: the registered MCP tool must raise (-> isError=True via the
    SDK's tool.run()/_handle_call_tool()) on reveal's "[reveal error:" sentinel,
    while the plain module-level function keeps returning the string unchanged
    for direct Python callers (see mcp_tool() in mcp_server.py)."""

    def setUp(self):
        from reveal.mcp_server import mcp
        self.mcp = mcp
        self._orig_dir = os.getcwd()
        os.chdir(Path(__file__).parent.parent)

    def tearDown(self):
        os.chdir(self._orig_dir)

    def _registered_fn(self, tool_name):
        return self.mcp._tool_manager._tools[tool_name].fn

    def test_direct_call_still_returns_string(self):
        from reveal.mcp_server import reveal_structure
        result = reveal_structure('/nonexistent/path/xyz')
        self.assertIsInstance(result, str)
        self.assertIn('reveal error', result)

    def test_registered_tool_raises_on_error_sentinel(self):
        fn = self._registered_fn('reveal_structure')
        with self.assertRaises(ValueError) as ctx:
            fn(path='/nonexistent/path/xyz')
        self.assertIn('path not found', str(ctx.exception))

    def test_registered_tool_does_not_raise_on_success(self):
        fn = self._registered_fn('reveal_structure')
        result = fn(path='reveal/mcp_server.py')
        self.assertIsInstance(result, str)

    def test_registered_tool_does_not_raise_on_cli_exit_code(self):
        # "[reveal exited with code N]" is a CLI verdict passthrough (e.g. a
        # FAIL health check), not a call failure -- must stay non-raising.
        from reveal.mcp_server import _run_and_capture

        def fn():
            raise SystemExit(1)

        result = _run_and_capture(fn)
        self.assertIn('[reveal exited with code', result)

    def test_every_tool_raises_on_missing_path(self):
        # Every tool that pre-checks Path.exists() before doing real work.
        cases = {
            'reveal_structure': {'path': '/nonexistent/path/xyz'},
            'reveal_element': {'path': '/nonexistent/path/xyz.py', 'element': 'foo'},
            'reveal_pack': {'path': '/nonexistent/path/xyz'},
            'reveal_check': {'path': '/nonexistent/path/xyz'},
            'reveal_grep': {'path': '/nonexistent/path/xyz', 'pattern': 'x'},
            'reveal_trace': {'path': '/nonexistent/path/xyz', 'entry_point': 'main'},
        }
        for tool_name, kwargs in cases.items():
            with self.subTest(tool=tool_name):
                fn = self._registered_fn(tool_name)
                with self.assertRaises(ValueError):
                    fn(**kwargs)

    def test_end_to_end_call_tool_sets_is_error(self):
        import asyncio
        from mcp.types import CallToolRequestParams

        async def call(name, arguments):
            return await self.mcp._handle_call_tool(None, CallToolRequestParams(name=name, arguments=arguments))

        error_result = asyncio.run(call('reveal_structure', {'path': '/nonexistent/path/xyz'}))
        self.assertTrue(error_result.is_error)

        ok_result = asyncio.run(call('reveal_structure', {'path': 'reveal/mcp_server.py'}))
        self.assertFalse(ok_result.is_error)


class TestMcpServerRegistration(unittest.TestCase):
    """Verify the MCP server registers all expected tools."""

    def test_all_tools_registered(self):
        from reveal.mcp_server import mcp
        tool_names = list(mcp._tool_manager._tools.keys())
        self.assertIn('reveal_structure', tool_names)
        self.assertIn('reveal_element', tool_names)
        self.assertIn('reveal_nav', tool_names)
        self.assertIn('reveal_query', tool_names)
        self.assertIn('reveal_pack', tool_names)
        self.assertIn('reveal_check', tool_names)
        self.assertIn('reveal_grep', tool_names)
        self.assertIn('reveal_trace', tool_names)
        self.assertIn('reveal_health', tool_names)
        self.assertIn('reveal_review', tool_names)

    def test_tool_count(self):
        from reveal.mcp_server import mcp
        self.assertEqual(len(mcp._tool_manager._tools), 10)

    def test_tool_count_matches_guide(self):
        """Validate that MCP_SETUP.md tool count matches actual registered tools."""
        import re
        from pathlib import Path
        from reveal.mcp_server import mcp

        guide_path = Path(__file__).parent.parent / 'reveal' / 'docs' / 'guides' / 'MCP_SETUP.md'
        if not guide_path.exists():
            self.skipTest("MCP_SETUP.md not found")

        content = guide_path.read_text()
        # Matches e.g. "6 tools" in the help_description frontmatter or body
        m = re.search(r'(\d+)\s+tools', content)
        self.assertIsNotNone(m, "MCP_SETUP.md should state a tool count")
        doc_count = int(m.group(1))
        actual_count = len(mcp._tool_manager._tools)
        self.assertEqual(
            doc_count, actual_count,
            f"MCP_SETUP.md says {doc_count} tools but {actual_count} are registered. "
            f"Update the guide count or add/remove mcp_server.py tool definitions."
        )

    def test_server_name(self):
        from reveal.mcp_server import mcp
        self.assertEqual(mcp.name, 'reveal')

    def test_server_has_instructions(self):
        from reveal.mcp_server import mcp
        self.assertIn('progressive disclosure', mcp.instructions.lower())


class TestDefaultArgs(unittest.TestCase):
    """Verify _default_args produces a complete Namespace."""

    def test_has_key_tree_attrs(self):
        from reveal.mcp_server import _default_args
        args = _default_args()
        self.assertEqual(args.max_entries, 200)
        self.assertEqual(args.dir_limit, 50)
        self.assertFalse(args.fast)
        self.assertTrue(args.respect_gitignore)

    def test_overrides_applied(self):
        from reveal.mcp_server import _default_args
        args = _default_args(format='json', verbose=True, budget='8000')
        self.assertEqual(args.format, 'json')
        self.assertTrue(args.verbose)
        self.assertEqual(args.budget, '8000')

    def test_no_missing_exclude_attr(self):
        from reveal.mcp_server import _default_args
        args = _default_args()
        # exclude was the first failure — verify it's present
        self.assertIsNone(args.exclude)


if __name__ == '__main__':
    unittest.main()
