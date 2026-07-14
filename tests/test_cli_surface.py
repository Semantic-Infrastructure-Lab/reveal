"""Tests for reveal surface subcommand."""

import json
import os
import sys
import tempfile
import textwrap
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from reveal.adapters.ast.nav_surface import (
    _get_open_mode,
    _is_env_access,
    _is_fs_write,
    _is_http_route,
    _is_mock_patch_decorator,
    _is_mcp_tool,
)
from reveal.cli.commands.surface import (
    _render_report,
    _scan_surface,
    create_surface_parser,
    run_surface,
)


def _write(directory: str, filename: str, content: str) -> str:
    path = os.path.join(directory, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(textwrap.dedent(content))
    return path


class TestCreateSurfaceParser(unittest.TestCase):

    def test_parser_exists(self):
        parser = create_surface_parser()
        self.assertIsNotNone(parser)

    def test_defaults(self):
        parser = create_surface_parser()
        args = parser.parse_args([])
        self.assertEqual(args.path, '.')
        self.assertEqual(args.type, '')
        self.assertIsNone(args.top)

    def test_type_flag(self):
        parser = create_surface_parser()
        args = parser.parse_args(['--type', 'env'])
        self.assertEqual(args.type, 'env')

    def test_top_flag(self):
        parser = create_surface_parser()
        args = parser.parse_args(['--top', '20'])
        self.assertEqual(args.top, 20)


class TestClassifiers(unittest.TestCase):

    def test_is_http_route_flask(self):
        self.assertTrue(_is_http_route("app.route('/path')"))

    def test_is_http_route_fastapi_get(self):
        self.assertTrue(_is_http_route("router.get('/items')"))

    def test_is_http_route_post(self):
        self.assertTrue(_is_http_route("app.post('/create')"))

    def test_is_http_route_false(self):
        self.assertFalse(_is_http_route("app.command('deploy')"))

    def test_is_http_route_mock_patch_not_route(self):
        self.assertFalse(_is_http_route("mock.patch('payment.tasks.send_email')"))

    def test_is_http_route_mocker_patch_not_route(self):
        self.assertFalse(_is_http_route("mocker.patch('some.module.Class')"))

    def test_is_http_route_unittest_mock_patch_not_route(self):
        self.assertFalse(_is_http_route("unittest.mock.patch('package.module')"))

    def test_is_http_route_real_patch_endpoint(self):
        self.assertTrue(_is_http_route("app.patch('/items/{id}')"))

    def test_is_mock_patch_decorator_mock(self):
        self.assertTrue(_is_mock_patch_decorator("mock.patch('module.Class')"))

    def test_is_mock_patch_decorator_mocker(self):
        self.assertTrue(_is_mock_patch_decorator("mocker.patch('module.func')"))

    def test_is_mock_patch_decorator_unittest(self):
        self.assertTrue(_is_mock_patch_decorator("unittest.mock.patch('mod.fn')"))

    def test_is_mock_patch_decorator_bare_patch(self):
        self.assertTrue(_is_mock_patch_decorator("patch('module.func')"))

    def test_is_mock_patch_decorator_real_route_false(self):
        self.assertFalse(_is_mock_patch_decorator("app.patch('/endpoint')"))

    # CLI-command classification is provenance-based (BACK-534), not a string
    # heuristic — covered by TestCliCommandProvenance below.

    def test_is_mcp_tool(self):
        self.assertTrue(_is_mcp_tool("mcp.tool()"))
        self.assertTrue(_is_mcp_tool("server.tool()"))

    def test_is_mcp_tool_false(self):
        self.assertFalse(_is_mcp_tool("app.route('/x')"))

    def test_is_env_access_os_getenv(self):
        self.assertTrue(_is_env_access("os.getenv"))

    def test_is_env_access_os_environ_get(self):
        self.assertTrue(_is_env_access("os.environ.get"))

    def test_is_env_access_environ_get(self):
        self.assertTrue(_is_env_access("environ.get"))

    def test_is_env_access_getenv(self):
        self.assertTrue(_is_env_access("getenv"))

    def test_is_env_access_dunder_getitem(self):
        self.assertTrue(_is_env_access("os.environ.__getitem__"))

    def test_is_env_access_false_os_path_join(self):
        self.assertFalse(_is_env_access("os.path.join"))

    def test_is_env_access_false_dict_get(self):
        self.assertFalse(_is_env_access("trade.get"))

    def test_is_env_access_false_md_get(self):
        self.assertFalse(_is_env_access("md.get"))

    def test_is_env_access_false_regime_get(self):
        self.assertFalse(_is_env_access("REGIME_SIZE_MULT.get"))

    def test_is_env_access_false_bare_get(self):
        self.assertFalse(_is_env_access("get"))


class TestScanSurface(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def test_finds_env_vars(self):
        _write(self.tmp, 'app.py', '''\
            import os
            DB_URL = os.getenv('DATABASE_URL')
            SECRET = os.environ.get('SECRET_KEY')
        ''')
        report = _scan_surface(Path(self.tmp))
        env = report['surfaces']['env']
        names = [e['name'] for e in env]
        self.assertIn('DATABASE_URL', names)
        self.assertIn('SECRET_KEY', names)

    def test_finds_network_imports(self):
        _write(self.tmp, 'client.py', '''\
            import requests
            import httpx
        ''')
        report = _scan_surface(Path(self.tmp))
        net = report['surfaces']['network']
        names = [e['name'] for e in net]
        self.assertIn('requests', names)
        self.assertIn('httpx', names)

    def test_finds_db_imports(self):
        _write(self.tmp, 'db.py', '''\
            import psycopg2
            import redis
        ''')
        report = _scan_surface(Path(self.tmp))
        db = report['surfaces']['db']
        names = [e['name'] for e in db]
        self.assertIn('psycopg2', names)
        self.assertIn('redis', names)

    def test_finds_sdk_imports(self):
        _write(self.tmp, 'ai.py', '''\
            import anthropic
            import openai
        ''')
        report = _scan_surface(Path(self.tmp))
        sdk = report['surfaces']['sdk']
        names = [e['name'] for e in sdk]
        self.assertIn('anthropic', names)
        self.assertIn('openai', names)

    def test_finds_http_routes(self):
        _write(self.tmp, 'routes.py', '''\
            from flask import Flask
            app = Flask(__name__)
            @app.route('/health', methods=['GET'])
            def health():
                return 'ok'
            @app.post('/create')
            def create():
                pass
        ''')
        report = _scan_surface(Path(self.tmp))
        http = report['surfaces']['http']
        self.assertGreater(len(http), 0)
        paths = [e.get('path', '') for e in http]
        self.assertIn('/health', paths)

    def test_finds_cli_arguments(self):
        _write(self.tmp, 'cli.py', '''\
            import argparse
            parser = argparse.ArgumentParser()
            parser.add_argument('--verbose', action='store_true')
            parser.add_argument('--output', type=str)
        ''')
        report = _scan_surface(Path(self.tmp))
        cli = report['surfaces']['cli']
        names = [e['name'] for e in cli]
        self.assertIn('--verbose', names)
        self.assertIn('--output', names)

    def test_bare_name_decorator_matching_command_is_not_a_cli_surface(self):
        # BACK-533: must not crash on a bare @command decorator.
        # BACK-534: a locally-defined (non-click/typer) @command is NOT a CLI
        # surface — name-only matching used to report it (the 39%-FP class).
        _write(self.tmp, 'entity.py', '''\
            def command(func):
                return func

            class Thing:
                @property
                @command
                def value(self):
                    return 1
        ''')
        report = _scan_surface(Path(self.tmp))
        cli = report['surfaces']['cli']
        names = [e['name'] for e in cli]
        self.assertNotIn('value', names)

    def test_finds_fs_writes(self):
        _write(self.tmp, 'writer.py', '''\
            def save(path, data):
                with open(path, 'w') as f:
                    f.write(data)
        ''')
        report = _scan_surface(Path(self.tmp))
        fs = report['surfaces']['fs']
        self.assertGreater(len(fs), 0)

    def test_type_filter(self):
        _write(self.tmp, 'app.py', '''\
            import os
            import requests
            DB = os.getenv('DB_URL')
        ''')
        report = _scan_surface(Path(self.tmp), type_filter='env')
        self.assertIn('env', report['surfaces'])
        self.assertNotIn('network', report['surfaces'])

    def test_empty_directory_returns_zero(self):
        report = _scan_surface(Path(self.tmp))
        self.assertEqual(report['total'], 0)

    def test_total_sum_matches_surfaces(self):
        _write(self.tmp, 'app.py', '''\
            import os, requests
            X = os.getenv('KEY')
        ''')
        report = _scan_surface(Path(self.tmp))
        counted = sum(len(v) for v in report['surfaces'].values())
        self.assertEqual(report['total'], counted)

    def test_syntax_error_file_skipped(self):
        _write(self.tmp, 'bad.py', 'def broken(\n')
        report = _scan_surface(Path(self.tmp))
        self.assertEqual(report['total'], 0)

    def test_mock_patch_decorator_not_counted_as_http_route(self):
        _write(self.tmp, 'test_tasks.py', '''\
            import unittest
            from unittest.mock import patch
            class TestPayment(unittest.TestCase):
                @patch('payment.tasks.send_email')
                @patch('payment.gateway.charge')
                def test_process(self, mock_charge, mock_email):
                    pass
                @patch('payment.tasks.refund')
                def test_refund(self, mock_refund):
                    pass
        ''')
        report = _scan_surface(Path(self.tmp))
        http = report['surfaces']['http']
        self.assertEqual(http, [], f"Expected no HTTP routes but got: {http}")

    def test_vendor_dir_excluded_from_surface(self):
        _write(self.tmp, 'app.py', 'import os\nDB = os.getenv("REAL_KEY")\n')
        _write(self.tmp, 'venv/lib/site-packages/some_lib/client.py',
               'import os\nX = os.getenv("VENV_KEY")\n')
        _write(self.tmp, 'site-packages/dep/utils.py',
               'import os\nY = os.getenv("SITE_PACKAGES_KEY")\n')
        report = _scan_surface(Path(self.tmp))
        env_names = [e['name'] for e in report['surfaces']['env']]
        self.assertIn('REAL_KEY', env_names)
        self.assertNotIn('VENV_KEY', env_names)
        self.assertNotIn('SITE_PACKAGES_KEY', env_names)


class TestCliCommandProvenance(unittest.TestCase):
    """BACK-534: @command is a CLI surface only with click/typer provenance."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _cli_names(self):
        report = _scan_surface(Path(self.tmp))
        return [e['name'] for e in report['surfaces']['cli'] if e.get('type') == 'command']

    def test_click_and_typer_and_subgroups_detected(self):
        _write(self.tmp, 'app.py', '''\
            import click
            import typer

            app = typer.Typer()

            @click.group()
            def cli():
                pass

            @cli.command()
            def deploy():
                pass

            @cli.group()
            def db():
                pass

            @db.command()
            def migrate():
                pass

            @app.command()
            def serve():
                pass
        ''')
        names = self._cli_names()
        self.assertIn('deploy', names)
        self.assertIn('migrate', names)   # sub-group command
        self.assertIn('serve', names)     # typer

    def test_unrelated_command_decorator_excluded(self):
        # An entity-style @command from a non-CLI framework (the home-assistant
        # 39%-false-positive case) must not be reported as a CLI surface.
        _write(self.tmp, 'entity.py', '''\
            from homeassistant.core import command

            class Light:
                @command
                def turn_on(self):
                    pass

                @command
                def turn_off(self):
                    pass
        ''')
        self.assertEqual(self._cli_names(), [])

    def test_command_on_unknown_object_excluded(self):
        # `.command()` on an object of unresolved provenance is not a CLI surface.
        _write(self.tmp, 'thing.py', '''\
            class Registry:
                def command(self, fn):
                    return fn

            reg = Registry()

            @reg.command()
            def handle():
                pass
        ''')
        self.assertEqual(self._cli_names(), [])

    def test_aliased_click_import_detected(self):
        _write(self.tmp, 'aliased.py', '''\
            from click import command as ccmd

            @ccmd()
            def run():
                pass
        ''')
        self.assertIn('run', self._cli_names())


class TestRenderReport(unittest.TestCase):

    def _capture(self, report, **kwargs):
        buf = StringIO()
        with patch('sys.stdout', buf):
            _render_report(report, **kwargs)
        return buf.getvalue()

    def _empty_report(self, **kwargs):
        base = {
            'path': '/proj',
            'total': 0,
            'surfaces': {k: [] for k in ('cli', 'http', 'mcp', 'env', 'network', 'db', 'sdk', 'fs')},
        }
        base.update(kwargs)
        return base

    def _report_with_env(self, n: int):
        surfs = {k: [] for k in ('cli', 'http', 'mcp', 'network', 'db', 'sdk', 'fs')}
        surfs['env'] = [
            {'type': 'env_var', 'name': f'KEY_{i}', 'expr': 'os.getenv', 'file': 'app.py', 'line': i}
            for i in range(n)
        ]
        return self._empty_report(total=n, surfaces=surfs)

    def test_no_surfaces_shows_message(self):
        out = self._capture(self._empty_report())
        self.assertIn('No external surfaces', out)

    def test_coverage_warning_shown_with_results(self):
        # BACK-518: total>0 but built from a supported-language minority.
        rep = self._report_with_env(3)
        rep['coverage'] = {'warning': '⚠ Analyzed 15 of 1,384 source files. '
                           "Dominant language 'Lua' (1,305 files) is not "
                           'supported by `surface` — the rest of the tree was '
                           'not analyzed.'}
        out = self._capture(rep)
        self.assertIn('⚠ Analyzed 15 of 1,384', out)
        self.assertIn('Lua', out)

    def test_coverage_warning_shown_on_false_clean(self):
        # BACK-518: total==0 that is a false-clean (stray supported files in a
        # mostly-unsupported tree), not a real "no surfaces" verdict. The
        # warning replaces the legacy "No external surfaces" line.
        rep = self._empty_report(coverage={'warning': '⚠ Analyzed 15 of 1,384 '
                                 "source files. Dominant language 'Lua' is not "
                                 'supported by `surface` — the rest of the tree '
                                 'was not analyzed.'})
        out = self._capture(rep)
        self.assertIn('⚠ Analyzed 15 of 1,384', out)
        self.assertNotIn('No external surfaces', out)

    def test_no_warning_when_coverage_clean(self):
        # A supported-majority (or empty coverage) report renders unchanged.
        rep = self._empty_report(coverage={'warning': ''})
        out = self._capture(rep)
        self.assertNotIn('⚠', out)
        self.assertIn('No external surfaces', out)

    def test_shows_path(self):
        out = self._capture(self._empty_report(path='/myproject'))
        self.assertIn('/myproject', out)

    def test_env_section_shown(self):
        surfs = {k: [] for k in ('cli', 'http', 'mcp', 'network', 'db', 'sdk', 'fs')}
        surfs['env'] = [{'type': 'env_var', 'name': 'API_KEY', 'expr': 'os.getenv', 'file': 'app.py', 'line': 5}]
        report = self._empty_report(total=1, surfaces=surfs)
        out = self._capture(report)
        self.assertIn('API_KEY', out)
        self.assertIn('Environment variables', out)

    def test_top_limits_entries_shown(self):
        out = self._capture(self._report_with_env(10), top=3)
        # Only first 3 should appear
        self.assertIn('KEY_0', out)
        self.assertIn('KEY_2', out)
        self.assertNotIn('KEY_3', out)

    def test_top_shows_truncation_hint(self):
        out = self._capture(self._report_with_env(10), top=3)
        self.assertIn('7 more', out)
        self.assertIn('--top 10', out)

    def test_top_none_shows_all(self):
        out = self._capture(self._report_with_env(10))
        self.assertIn('KEY_9', out)
        self.assertNotIn('more', out)

    def test_top_header_shown_when_limited(self):
        out = self._capture(self._report_with_env(5), top=2)
        self.assertIn('Showing top 2', out)

    def test_top_no_header_when_unlimited(self):
        out = self._capture(self._report_with_env(5))
        self.assertNotIn('Showing top', out)

    def test_top_larger_than_count_shows_all(self):
        out = self._capture(self._report_with_env(3), top=100)
        self.assertIn('KEY_2', out)
        self.assertNotIn('more', out)


class TestRunSurface(unittest.TestCase):

    def test_nonexistent_path_exits_1(self):
        parser = create_surface_parser()
        args = parser.parse_args(['/nonexistent/path'])
        args.format = 'text'
        with self.assertRaises(SystemExit) as cm:
            run_surface(args)
        self.assertEqual(cm.exception.code, 1)

    def test_json_format(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, 'app.py', 'import os\nX = os.getenv("KEY")\n')
            parser = create_surface_parser()
            args = parser.parse_args([d])
            args.format = 'json'
            buf = StringIO()
            with patch('sys.stdout', buf):
                run_surface(args)
            data = json.loads(buf.getvalue())
            self.assertIn('surfaces', data)
            self.assertIn('env', data['surfaces'])


class TestNavSurfaceTS(unittest.TestCase):
    """Unit tests for the TypeScript surface scanner (nav_surface_ts)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _scan_ts(self, filename: str, content: str):
        from reveal.adapters.ast.nav_surface_ts import scan_file_surface_ts
        path = _write(self.tmp, filename, content)
        return scan_file_surface_ts(path)

    def test_ts_network_import_axios(self):
        result = self._scan_ts('client.ts', 'import axios from "axios";\n')
        names = [e['name'] for e in result['network']]
        self.assertIn('axios', names)

    def test_ts_db_import_prisma(self):
        result = self._scan_ts('db.ts', 'import { PrismaClient } from "@prisma/client";\n')
        names = [e['name'] for e in result['db']]
        self.assertIn('@prisma/client', names)

    def test_ts_sdk_import_anthropic(self):
        result = self._scan_ts('ai.ts', 'import Anthropic from "@anthropic-ai/sdk";\n')
        names = [e['name'] for e in result['sdk']]
        self.assertIn('@anthropic-ai/sdk', names)

    def test_ts_env_member_expression(self):
        result = self._scan_ts('config.ts', 'const k = process.env.API_KEY;\n')
        names = [e['name'] for e in result['env']]
        self.assertIn('API_KEY', names)

    def test_ts_env_subscript_expression(self):
        result = self._scan_ts('config.ts', 'const k = process.env["SECRET"];\n')
        names = [e['name'] for e in result['env']]
        self.assertIn('SECRET', names)

    def test_ts_fs_write(self):
        result = self._scan_ts('writer.ts', 'fs.writeFile("out.txt", data);\n')
        names = [e['name'] for e in result['fs']]
        self.assertIn('fs.writeFile', names)

    def test_ts_fs_bun_write(self):
        result = self._scan_ts('writer.ts', 'Bun.write("out.txt", data);\n')
        names = [e['name'] for e in result['fs']]
        self.assertIn('Bun.write', names)

    def test_ts_http_route_get(self):
        result = self._scan_ts('routes.ts', 'app.get("/health", handler);\n')
        entries = result['http']
        self.assertGreater(len(entries), 0)
        paths = [e['path'] for e in entries]
        self.assertIn('/health', paths)

    def test_ts_http_route_post(self):
        result = self._scan_ts('routes.ts', 'router.post("/users", createUser);\n')
        entries = result['http']
        self.assertGreater(len(entries), 0)
        methods = [e['methods'] for e in entries]
        self.assertIn('POST', methods)

    def test_ts_subprocess_child_process(self):
        result = self._scan_ts('spawn.ts', 'child_process.exec("ls");\n')
        names = [e['name'] for e in result['subprocess']]
        self.assertIn('child_process.exec', names)

    def test_ts_subprocess_execa(self):
        result = self._scan_ts('spawn.ts', 'execa("git", ["status"]);\n')
        names = [e['name'] for e in result['subprocess']]
        self.assertIn('execa', names)

    def test_ts_cli_command(self):
        result = self._scan_ts('cli.ts', 'yargs.command("serve", "Start server");\n')
        names = [e['name'] for e in result['cli']]
        self.assertIn('serve', names)

    def test_ts_cli_option(self):
        result = self._scan_ts('cli.ts', 'yargs.option("port", { type: "number" });\n')
        names = [e['name'] for e in result['cli']]
        self.assertIn('port', names)

    def test_ts_tsx_file_scanned(self):
        result = self._scan_ts('app.tsx', 'import axios from "axios";\n')
        names = [e['name'] for e in result['network']]
        self.assertIn('axios', names)

    def test_ts_supertest_not_flagged_as_http_route(self):
        # request(app).get('/path') is a supertest assertion, not a route registration
        result = self._scan_ts('routes.test.ts', 'request(app).get("/health");\n')
        self.assertEqual(result['http'], [], "supertest calls should not be detected as HTTP routes")

    def test_ts_invalid_file_returns_empty(self):
        from reveal.adapters.ast.nav_surface_ts import scan_file_surface_ts
        result = scan_file_surface_ts('/nonexistent/path/file.ts')
        self.assertEqual(result['network'], [])
        self.assertEqual(result['env'], [])

    def test_ts_sdk_import_openai(self):
        result = self._scan_ts('ai.ts', 'import OpenAI from "openai";\n')
        names = [e['name'] for e in result['sdk']]
        self.assertIn('openai', names)

    def test_ts_db_import_ioredis(self):
        result = self._scan_ts('cache.ts', 'import Redis from "ioredis";\n')
        names = [e['name'] for e in result['db']]
        self.assertIn('ioredis', names)


class TestScanSurfaceTS(unittest.TestCase):
    """Integration tests: _scan_surface picks up .ts/.tsx files."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def test_ts_files_included_in_scan(self):
        _write(self.tmp, 'server.ts', 'import axios from "axios";\n')
        report = _scan_surface(Path(self.tmp))
        names = [e['name'] for e in report['surfaces']['network']]
        self.assertIn('axios', names)

    def test_tsx_files_included_in_scan(self):
        _write(self.tmp, 'App.tsx', 'import axios from "axios";\n')
        report = _scan_surface(Path(self.tmp))
        names = [e['name'] for e in report['surfaces']['network']]
        self.assertIn('axios', names)

    def test_subprocess_category_present_in_report(self):
        _write(self.tmp, 'run.ts', 'child_process.exec("ls");\n')
        report = _scan_surface(Path(self.tmp))
        self.assertIn('subprocess', report['surfaces'])
        names = [e['name'] for e in report['surfaces']['subprocess']]
        self.assertIn('child_process.exec', names)

    def test_mixed_py_and_ts(self):
        _write(self.tmp, 'app.py', 'import requests\n')
        _write(self.tmp, 'client.ts', 'import axios from "axios";\n')
        report = _scan_surface(Path(self.tmp))
        net_names = [e['name'] for e in report['surfaces']['network']]
        self.assertIn('requests', net_names)
        self.assertIn('axios', net_names)

    def test_ts_env_vars_detected(self):
        _write(self.tmp, 'config.ts', 'const key = process.env.API_KEY;\n')
        report = _scan_surface(Path(self.tmp))
        env_names = [e['name'] for e in report['surfaces']['env']]
        self.assertIn('API_KEY', env_names)

    def test_subprocess_label_in_surface_labels(self):
        from reveal.cli.commands.surface import _SURFACE_LABELS
        self.assertIn('subprocess', _SURFACE_LABELS)


class TestSourceOnly(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def test_source_only_flag_in_parser(self):
        parser = create_surface_parser()
        args = parser.parse_args(['.', '--source-only'])
        self.assertTrue(args.source_only)

    def test_source_only_default_false(self):
        parser = create_surface_parser()
        args = parser.parse_args(['.'])
        self.assertFalse(args.source_only)

    def test_source_only_excludes_tests_dir(self):
        _write(self.tmp, 'app.py', 'import os\nDB = os.getenv("PROD_KEY")\n')
        _write(self.tmp, 'tests/test_app.py', 'import os\nX = os.getenv("TEST_KEY")\n')
        report = _scan_surface(Path(self.tmp), source_only=True)
        env_names = [e['name'] for e in report['surfaces']['env']]
        self.assertIn('PROD_KEY', env_names)
        self.assertNotIn('TEST_KEY', env_names)

    def test_source_only_excludes_test_prefix_file(self):
        _write(self.tmp, 'app.py', 'import os\nDB = os.getenv("PROD_KEY")\n')
        _write(self.tmp, 'test_app.py', 'import os\nX = os.getenv("TEST_KEY")\n')
        report = _scan_surface(Path(self.tmp), source_only=True)
        env_names = [e['name'] for e in report['surfaces']['env']]
        self.assertIn('PROD_KEY', env_names)
        self.assertNotIn('TEST_KEY', env_names)

    def test_source_only_excludes_test_suffix_file(self):
        _write(self.tmp, 'app.py', 'import os\nDB = os.getenv("PROD_KEY")\n')
        _write(self.tmp, 'app_test.py', 'import os\nX = os.getenv("TEST_KEY")\n')
        report = _scan_surface(Path(self.tmp), source_only=True)
        env_names = [e['name'] for e in report['surfaces']['env']]
        self.assertIn('PROD_KEY', env_names)
        self.assertNotIn('TEST_KEY', env_names)

    def test_source_only_excludes_conftest(self):
        _write(self.tmp, 'app.py', 'import os\nDB = os.getenv("PROD_KEY")\n')
        _write(self.tmp, 'conftest.py', 'import os\nX = os.getenv("CONFTEST_KEY")\n')
        report = _scan_surface(Path(self.tmp), source_only=True)
        env_names = [e['name'] for e in report['surfaces']['env']]
        self.assertNotIn('CONFTEST_KEY', env_names)

    def test_source_only_excludes_ts_test_file(self):
        _write(self.tmp, 'app.ts', 'const k = process.env.PROD_KEY;\n')
        _write(self.tmp, 'app.test.ts', 'const k = process.env.TEST_KEY;\n')
        report = _scan_surface(Path(self.tmp), source_only=True)
        env_names = [e['name'] for e in report['surfaces']['env']]
        self.assertIn('PROD_KEY', env_names)
        self.assertNotIn('TEST_KEY', env_names)

    def test_source_only_excludes_ts_spec_file(self):
        _write(self.tmp, 'app.ts', 'const k = process.env.PROD_KEY;\n')
        _write(self.tmp, 'app.spec.tsx', 'const k = process.env.SPEC_KEY;\n')
        report = _scan_surface(Path(self.tmp), source_only=True)
        env_names = [e['name'] for e in report['surfaces']['env']]
        self.assertNotIn('SPEC_KEY', env_names)

    def test_without_source_only_test_files_included(self):
        _write(self.tmp, 'app.py', 'import os\nDB = os.getenv("PROD_KEY")\n')
        _write(self.tmp, 'test_app.py', 'import os\nX = os.getenv("TEST_KEY")\n')
        report = _scan_surface(Path(self.tmp), source_only=False)
        env_names = [e['name'] for e in report['surfaces']['env']]
        self.assertIn('PROD_KEY', env_names)
        self.assertIn('TEST_KEY', env_names)

    def test_source_only_meta_limit_recorded(self):
        report = _scan_surface(Path(self.tmp), source_only=True)
        limits = report['_meta']['known_limits']
        self.assertTrue(any('source-only' in lim for lim in limits))

    def test_source_only_excludes_nested_tests_dir(self):
        _write(self.tmp, 'src/core.py', 'import os\nDB = os.getenv("CORE_KEY")\n')
        _write(self.tmp, 'src/tests/test_core.py', 'import os\nX = os.getenv("NESTED_TEST_KEY")\n')
        report = _scan_surface(Path(self.tmp), source_only=True)
        env_names = [e['name'] for e in report['surfaces']['env']]
        self.assertIn('CORE_KEY', env_names)
        self.assertNotIn('NESTED_TEST_KEY', env_names)


class TestNavSurfaceJava(unittest.TestCase):
    """Unit tests for the Java surface scanner (nav_surface_java, BACK-403 pt 2)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _scan_java(self, filename: str, content: str):
        from reveal.adapters.ast.nav_surface_java import scan_file_surface_java
        path = _write(self.tmp, filename, content)
        return scan_file_surface_java(path)

    def test_java_network_import(self):
        result = self._scan_java('Client.java', 'import java.net.http.HttpClient;\n')
        names = [e['name'] for e in result['network']]
        self.assertIn('java.net.http.HttpClient', names)

    def test_java_db_import(self):
        result = self._scan_java('Db.java', 'import com.mongodb.client.MongoClient;\n')
        names = [e['name'] for e in result['db']]
        self.assertIn('com.mongodb.client.MongoClient', names)

    def test_java_sdk_import(self):
        result = self._scan_java('Pay.java', 'import com.stripe.Stripe;\n')
        names = [e['name'] for e in result['sdk']]
        self.assertIn('com.stripe.Stripe', names)

    def test_java_env_getenv(self):
        result = self._scan_java('Config.java', '''\
            class Config {
                void load() {
                    String k = System.getenv("API_KEY");
                }
            }
        ''')
        names = [e['name'] for e in result['env']]
        self.assertIn('API_KEY', names)

    def test_java_http_route_get_mapping(self):
        result = self._scan_java('Controller.java', '''\
            class UserController {
                @GetMapping("/users/{id}")
                public String getUser(String id) { return "x"; }
            }
        ''')
        entries = result['http']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['path'], '/users/{id}')
        self.assertEqual(entries[0]['methods'], 'GET')

    def test_java_http_route_post_mapping_value_kwarg(self):
        result = self._scan_java('Controller.java', '''\
            class UserController {
                @PostMapping(value = "/users")
                public void createUser() {}
            }
        ''')
        entries = result['http']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['path'], '/users')
        self.assertEqual(entries[0]['methods'], 'POST')

    def test_java_cli_main_entrypoint(self):
        result = self._scan_java('App.java', '''\
            class App {
                public static void main(String[] args) {}
            }
        ''')
        entries = result['cli']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['type'], 'main')

    def test_java_non_static_method_named_main_not_cli(self):
        """A non-static method happening to be named 'main' isn't a CLI entrypoint."""
        result = self._scan_java('NotEntry.java', '''\
            class Thing {
                public void main() {}
            }
        ''')
        self.assertEqual(len(result['cli']), 0)


class TestNavSurfaceCSharp(unittest.TestCase):
    """Unit tests for the C# surface scanner (nav_surface_csharp, BACK-403 pt 2)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _scan_cs(self, filename: str, content: str):
        from reveal.adapters.ast.nav_surface_csharp import scan_file_surface_csharp
        path = _write(self.tmp, filename, content)
        return scan_file_surface_csharp(path)

    def test_csharp_network_using(self):
        result = self._scan_cs('Client.cs', 'using System.Net.Http;\n')
        names = [e['name'] for e in result['network']]
        self.assertIn('System.Net.Http', names)

    def test_csharp_db_using(self):
        result = self._scan_cs('Db.cs', 'using Npgsql;\n')
        names = [e['name'] for e in result['db']]
        self.assertIn('Npgsql', names)

    def test_csharp_sdk_using(self):
        result = self._scan_cs('Pay.cs', 'using Stripe;\n')
        names = [e['name'] for e in result['sdk']]
        self.assertIn('Stripe', names)

    def test_csharp_env_getenvironmentvariable(self):
        result = self._scan_cs('Config.cs', '''\
            class Config {
                void Load() {
                    string k = Environment.GetEnvironmentVariable("API_KEY");
                }
            }
        ''')
        names = [e['name'] for e in result['env']]
        self.assertIn('API_KEY', names)

    def test_csharp_http_route_get(self):
        result = self._scan_cs('Controller.cs', '''\
            class UserController {
                [HttpGet("/users/{id}")]
                public string GetUser(string id) { return "x"; }
            }
        ''')
        entries = result['http']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['path'], '/users/{id}')
        self.assertEqual(entries[0]['methods'], 'GET')

    def test_csharp_http_route_verb_and_route_merge_into_one_entry(self):
        """[HttpPost] + [Route(...)] on the same method is one endpoint, not two."""
        result = self._scan_cs('Controller.cs', '''\
            class UserController {
                [HttpPost]
                [Route("/users")]
                public void CreateUser() {}
            }
        ''')
        entries = result['http']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['path'], '/users')
        self.assertEqual(entries[0]['methods'], 'POST')

    def test_csharp_cli_main_entrypoint(self):
        result = self._scan_cs('Program.cs', '''\
            class Program {
                public static void Main(string[] args) {}
            }
        ''')
        entries = result['cli']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['type'], 'main')

    def test_csharp_non_static_method_named_main_not_cli(self):
        result = self._scan_cs('NotEntry.cs', '''\
            class Thing {
                public void Main() {}
            }
        ''')
        self.assertEqual(len(result['cli']), 0)


class TestNavSurfacePhp(unittest.TestCase):
    """Unit tests for the PHP surface scanner (nav_surface_php, BACK-403 pt 2)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _scan_php(self, filename: str, content: str):
        from reveal.adapters.ast.nav_surface_php import scan_file_surface_php
        path = _write(self.tmp, filename, content)
        return scan_file_surface_php(path)

    def test_php_network_use(self):
        result = self._scan_php('Client.php', '<?php\nuse GuzzleHttp\\Client;\n')
        names = [e['name'] for e in result['network']]
        self.assertIn('GuzzleHttp\\Client', names)

    def test_php_db_use(self):
        result = self._scan_php('Db.php', '<?php\nuse Doctrine\\ORM\\EntityManager;\n')
        names = [e['name'] for e in result['db']]
        self.assertIn('Doctrine\\ORM\\EntityManager', names)

    def test_php_sdk_use(self):
        result = self._scan_php('Pay.php', '<?php\nuse Stripe\\StripeClient;\n')
        names = [e['name'] for e in result['sdk']]
        self.assertIn('Stripe\\StripeClient', names)

    def test_php_env_getenv(self):
        result = self._scan_php('c.php', "<?php\n$k = getenv('API_KEY');\n")
        self.assertIn('API_KEY', [e['name'] for e in result['env']])

    def test_php_env_superglobal(self):
        result = self._scan_php('c.php', "<?php\n$k = $_ENV['DB_HOST'];\n")
        self.assertIn('DB_HOST', [e['name'] for e in result['env']])

    def test_php_server_superglobal_excluded(self):
        """$_SERVER is a request superglobal, not env config — must not be surfaced."""
        result = self._scan_php('c.php', "<?php\n$h = $_SERVER['HTTP_HOST'];\n")
        self.assertEqual(len(result['env']), 0)

    def test_php_laravel_route(self):
        result = self._scan_php('routes.php', "<?php\nRoute::get('/users/{id}', 'C@show');\n")
        entries = result['http']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['path'], '/users/{id}')
        self.assertEqual(entries[0]['methods'], 'GET')

    def test_php_symfony_route_attribute(self):
        result = self._scan_php('Ctrl.php', '''\
            <?php
            class Ctrl {
                #[Route('/api/tasks', methods: ['GET', 'POST'])]
                public function list() {}
            }
        ''')
        entries = result['http']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['path'], '/api/tasks')
        self.assertEqual(entries[0]['methods'], 'GET|POST')

    def test_php_wordpress_rest_route(self):
        result = self._scan_php('plugin.php',
                                "<?php\nregister_rest_route('myplugin/v1', '/data', array());\n")
        entries = result['http']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['path'], '/myplugin/v1/data')

    def test_php_plain_static_call_not_a_route(self):
        """A non-Route static call must not be misclassified as an HTTP route."""
        result = self._scan_php('x.php', "<?php\nLogger::get('channel');\n")
        self.assertEqual(len(result['http']), 0)


class TestNavSurfaceSwift(unittest.TestCase):
    """Unit tests for the Swift surface scanner (nav_surface_swift, BACK-403 pt 2)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _scan_swift(self, filename: str, content: str):
        from reveal.adapters.ast.nav_surface_swift import scan_file_surface_swift
        path = _write(self.tmp, filename, content)
        return scan_file_surface_swift(path)

    def test_swift_network_import(self):
        result = self._scan_swift('C.swift', 'import Alamofire\n')
        self.assertIn('Alamofire', [e['name'] for e in result['network']])

    def test_swift_db_import(self):
        result = self._scan_swift('D.swift', 'import FluentKit\n')
        self.assertIn('FluentKit', [e['name'] for e in result['db']])

    def test_swift_sdk_import(self):
        result = self._scan_swift('P.swift', 'import Stripe\n')
        self.assertIn('Stripe', [e['name'] for e in result['sdk']])

    def test_swift_foundation_not_network(self):
        """Foundation is imported ~everywhere — must not flood the network read."""
        result = self._scan_swift('F.swift', 'import Foundation\n')
        self.assertEqual(len(result['network']), 0)

    def test_swift_vapor_route(self):
        result = self._scan_swift('r.swift', 'app.get("users", ":id") { req in return "x" }\n')
        entries = result['http']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['path'], '/users/:id')
        self.assertEqual(entries[0]['methods'], 'GET')

    def test_swift_member_get_without_closure_not_a_route(self):
        """`someMap.get(0)` is an ordinary member call, not a Vapor route."""
        result = self._scan_swift('x.swift', 'let v = someMap.get(0)\n')
        self.assertEqual(len(result['http']), 0)

    def test_swift_env_environment_get(self):
        result = self._scan_swift('e.swift', 'let k = Environment.get("API_KEY")\n')
        self.assertIn('API_KEY', [e['name'] for e in result['env']])

    def test_swift_env_processinfo(self):
        result = self._scan_swift('e.swift',
                                  'let h = ProcessInfo.processInfo.environment["HOME"]\n')
        self.assertIn('HOME', [e['name'] for e in result['env']])

    def test_swift_main_attribute(self):
        result = self._scan_swift('App.swift', '@main\nstruct App { static func main() {} }\n')
        self.assertEqual(len(result['cli']), 1)
        self.assertEqual(result['cli'][0]['type'], 'main')


class TestNavSurfaceKotlin(unittest.TestCase):
    """Unit tests for the Kotlin surface scanner (nav_surface_kotlin, BACK-403 pt 2)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _scan_kt(self, filename: str, content: str):
        from reveal.adapters.ast.nav_surface_kotlin import scan_file_surface_kotlin
        path = _write(self.tmp, filename, content)
        return scan_file_surface_kotlin(path)

    def test_kotlin_network_import(self):
        result = self._scan_kt('C.kt', 'import okhttp3.OkHttpClient\n')
        self.assertIn('okhttp3.OkHttpClient', [e['name'] for e in result['network']])

    def test_kotlin_db_import(self):
        result = self._scan_kt('D.kt', 'import org.jetbrains.exposed.sql.Database\n')
        self.assertIn('org.jetbrains.exposed.sql.Database', [e['name'] for e in result['db']])

    def test_kotlin_sdk_import(self):
        result = self._scan_kt('P.kt', 'import com.stripe.Stripe\n')
        self.assertIn('com.stripe.Stripe', [e['name'] for e in result['sdk']])

    def test_kotlin_ktor_route(self):
        result = self._scan_kt('r.kt', '''\
            fun Application.routes() {
                routing {
                    get("/users/{id}") { call.respond("x") }
                }
            }
        ''')
        entries = result['http']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['path'], '/users/{id}')
        self.assertEqual(entries[0]['methods'], 'GET')

    def test_kotlin_member_get_not_a_route(self):
        """`list.get(0)` is an ordinary member call, not a Ktor route."""
        result = self._scan_kt('x.kt', 'val v = list.get(0)\n')
        self.assertEqual(len(result['http']), 0)

    def test_kotlin_spring_annotation_route(self):
        result = self._scan_kt('Ctrl.kt', '''\
            class Ctrl {
                @GetMapping("/spring")
                fun handler() {}
            }
        ''')
        entries = result['http']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['path'], '/spring')
        self.assertEqual(entries[0]['methods'], 'GET')

    def test_kotlin_env_getenv(self):
        result = self._scan_kt('e.kt', 'val k = System.getenv("API_KEY")\n')
        self.assertIn('API_KEY', [e['name'] for e in result['env']])

    def test_kotlin_top_level_main_is_cli(self):
        result = self._scan_kt('App.kt', 'fun main(args: Array<String>) {}\n')
        self.assertEqual(len(result['cli']), 1)
        self.assertEqual(result['cli'][0]['type'], 'main')

    def test_kotlin_class_method_main_not_cli(self):
        """A class method named main is not the top-level entrypoint."""
        result = self._scan_kt('T.kt', 'class Thing { fun main() {} }\n')
        self.assertEqual(len(result['cli']), 0)


class TestNavSurfaceRuby(unittest.TestCase):
    """Unit tests for the Ruby surface scanner (nav_surface_ruby, BACK-403 pt 2)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _scan_rb(self, filename: str, content: str):
        from reveal.adapters.ast.nav_surface_ruby import scan_file_surface_ruby
        path = _write(self.tmp, filename, content)
        return scan_file_surface_ruby(path)

    def test_ruby_network_require(self):
        result = self._scan_rb('c.rb', "require 'net/http'\n")
        self.assertIn('net/http', [e['name'] for e in result['network']])

    def test_ruby_db_require(self):
        result = self._scan_rb('d.rb', "require 'pg'\n")
        self.assertIn('pg', [e['name'] for e in result['db']])

    def test_ruby_sdk_require(self):
        result = self._scan_rb('p.rb', "require 'aws-sdk-s3'\n")
        self.assertIn('aws-sdk-s3', [e['name'] for e in result['sdk']])

    def test_ruby_env_bracket(self):
        result = self._scan_rb('e.rb', "key = ENV['API_KEY']\n")
        self.assertIn('API_KEY', [e['name'] for e in result['env']])

    def test_ruby_env_fetch(self):
        result = self._scan_rb('e.rb', "key = ENV.fetch('API_KEY')\n")
        self.assertIn('API_KEY', [e['name'] for e in result['env']])

    def test_ruby_sinatra_route(self):
        result = self._scan_rb('app.rb', '''\
            class App < Sinatra::Base
              get "/users/:id" do
              end
            end
        ''')
        entries = result['http']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['path'], '/users/:id')
        self.assertEqual(entries[0]['methods'], 'GET')

    def test_ruby_rails_route(self):
        result = self._scan_rb('routes.rb', '''\
            Rails.application.routes.draw do
              get "/health", to: "health#index"
            end
        ''')
        entries = result['http']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['path'], '/health')
        self.assertEqual(entries[0]['methods'], 'GET')
        self.assertEqual(entries[0]['target'], 'health#index')

    def test_ruby_resources_not_a_route(self):
        """`resources :posts` fans out into many routes with no single explicit
        path, so it must not be surfaced as one (wrong-path) entry."""
        result = self._scan_rb('routes.rb', '''\
            Rails.application.routes.draw do
              resources :posts
            end
        ''')
        self.assertEqual(len(result['http']), 0)

    def test_ruby_member_get_not_a_route(self):
        """`http.get(url)` is a receiver call, not a bare DSL route invocation."""
        result = self._scan_rb('x.rb', "http.get(url)\n")
        self.assertEqual(len(result['http']), 0)

    def test_ruby_get_without_leading_slash_not_a_route(self):
        """A bare `get(key)` helper with a non-path string must not be misread
        as a route — the leading-`/` check is load-bearing here."""
        result = self._scan_rb('x.rb', "value = get('some_key')\n")
        self.assertEqual(len(result['http']), 0)


class TestNavSurfaceGo(unittest.TestCase):
    """Unit tests for the Go surface scanner (nav_surface_go, BACK-403 pt 2)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _scan_go(self, filename: str, content: str):
        from reveal.adapters.ast.nav_surface_go import scan_file_surface_go
        path = _write(self.tmp, filename, content)
        return scan_file_surface_go(path)

    def test_go_network_import(self):
        result = self._scan_go('c.go', 'package p\nimport "net/http"\n')
        self.assertIn('net/http', [e['name'] for e in result['network']])

    def test_go_db_import(self):
        result = self._scan_go('d.go', 'package p\nimport "database/sql"\n')
        self.assertIn('database/sql', [e['name'] for e in result['db']])

    def test_go_sdk_import_versioned_prefix(self):
        """A versioned module path (`.../stripe-go/v72`) matches the SDK prefix."""
        result = self._scan_go('pay.go', 'package p\nimport "github.com/stripe/stripe-go/v72"\n')
        self.assertIn('github.com/stripe/stripe-go/v72', [e['name'] for e in result['sdk']])

    def test_go_env_getenv(self):
        result = self._scan_go('cfg.go', '''\
package main
func load() {
	k := os.Getenv("API_KEY")
	_ = k
}
''')
        self.assertIn('API_KEY', [e['name'] for e in result['env']])

    def test_go_env_lookupenv(self):
        result = self._scan_go('cfg.go', '''\
package main
func load() {
	v, ok := os.LookupEnv("DATABASE_URL")
	_, _ = v, ok
}
''')
        self.assertIn('DATABASE_URL', [e['name'] for e in result['env']])

    def test_go_fs_write(self):
        result = self._scan_go('w.go', '''\
package main
func save() {
	os.WriteFile("/tmp/x", nil, 0644)
}
''')
        self.assertIn('os.WriteFile', [e['name'] for e in result['fs']])

    def test_go_route_gin_upper_verb(self):
        result = self._scan_go('r.go', '''\
package main
func routes() {
	r.GET("/users/:id", getUser)
}
''')
        entries = result['http']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['path'], '/users/:id')
        self.assertEqual(entries[0]['methods'], 'GET')

    def test_go_route_chi_title_verb(self):
        result = self._scan_go('r.go', '''\
package main
func routes() {
	r.Post("/users", createUser)
}
''')
        entries = result['http']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['path'], '/users')
        self.assertEqual(entries[0]['methods'], 'POST')

    def test_go_route_handlefunc_any(self):
        result = self._scan_go('r.go', '''\
package main
func routes() {
	http.HandleFunc("/health", healthCheck)
}
''')
        entries = result['http']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['path'], '/health')
        self.assertEqual(entries[0]['methods'], 'ANY')

    def test_go_cli_main_in_package_main(self):
        result = self._scan_go('app.go', 'package main\nfunc main() {}\n')
        self.assertEqual(len(result['cli']), 1)
        self.assertEqual(result['cli'][0]['name'], 'main')

    def test_go_main_outside_package_main_not_cli(self):
        """`func main` is only the program entrypoint in `package main`; a
        same-named function in any other package is an ordinary function."""
        result = self._scan_go('lib.go', 'package worker\nfunc main() {}\n')
        self.assertEqual(len(result['cli']), 0)

    def test_go_receiver_method_main_not_cli(self):
        """A receiver method named `main` is a method_declaration, not the
        top-level entrypoint — must not be surfaced as CLI."""
        result = self._scan_go('s.go', '''\
package main
type Server struct{}
func (s *Server) main() {}
''')
        self.assertEqual(len(result['cli']), 0)

    def test_go_title_verb_without_leading_slash_not_a_route(self):
        """`cache.Get("key")` shares Chi's title-case `Get` verb but its arg is
        not a path — the leading-`/` guard is load-bearing here."""
        result = self._scan_go('x.go', '''\
package main
func f() {
	v := cache.Get("some_key")
	_ = v
}
''')
        self.assertEqual(len(result['http']), 0)


class TestNavSurfaceRust(unittest.TestCase):
    """Unit tests for the Rust surface scanner (nav_surface_rust, BACK-403 pt 2)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _scan_rs(self, filename: str, content: str):
        from reveal.adapters.ast.nav_surface_rust import scan_file_surface_rust
        path = _write(self.tmp, filename, content)
        return scan_file_surface_rust(path)

    def test_rust_network_import(self):
        result = self._scan_rs('c.rs', 'use reqwest::Client;\n')
        self.assertIn('reqwest::Client', [e['name'] for e in result['network']])

    def test_rust_db_import(self):
        result = self._scan_rs('d.rs', 'use sqlx::PgPool;\n')
        self.assertIn('sqlx::PgPool', [e['name'] for e in result['db']])

    def test_rust_sdk_import_prefix(self):
        """`aws_sdk_*` crates match by prefix."""
        result = self._scan_rs('p.rs', 'use aws_sdk_s3::Client;\n')
        self.assertIn('aws_sdk_s3::Client', [e['name'] for e in result['sdk']])

    def test_rust_env_var(self):
        result = self._scan_rs('cfg.rs', 'fn f() { let k = env::var("API_KEY"); }\n')
        self.assertIn('API_KEY', [e['name'] for e in result['env']])

    def test_rust_env_var_fully_qualified(self):
        result = self._scan_rs('cfg.rs', 'fn f() { let k = std::env::var("PORT"); }\n')
        self.assertIn('PORT', [e['name'] for e in result['env']])

    def test_rust_fs_write(self):
        result = self._scan_rs('w.rs', 'fn f() { std::fs::write("/tmp/x", b"d"); }\n')
        self.assertIn('std::fs::write', [e['name'] for e in result['fs']])

    def test_rust_route_attribute_macro(self):
        result = self._scan_rs('h.rs', '#[get("/users/{id}")]\nasync fn get_user() {}\n')
        entries = result['http']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['path'], '/users/{id}')
        self.assertEqual(entries[0]['methods'], 'GET')

    def test_rust_route_axum_builder(self):
        result = self._scan_rs('r.rs', 'fn f() { let a = Router::new().route("/health", get(health)); }\n')
        entries = result['http']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['path'], '/health')
        self.assertEqual(entries[0]['methods'], 'GET')

    def test_rust_cli_top_level_main(self):
        result = self._scan_rs('main.rs', 'fn main() {}\n')
        self.assertEqual(len(result['cli']), 1)

    def test_rust_non_verb_attribute_not_a_route(self):
        """A non-HTTP attribute macro (e.g. `#[test]`) must not be a route."""
        result = self._scan_rs('t.rs', '#[test]\nfn it_works() {}\n')
        self.assertEqual(len(result['http']), 0)

    def test_rust_route_without_leading_slash_not_a_route(self):
        result = self._scan_rs('r.rs', 'fn f() { let a = x.route("relative", get(h)); }\n')
        self.assertEqual(len(result['http']), 0)

    def test_rust_actix_web_resource_route(self):
        result = self._scan_rs('r.rs', 'fn cfg() { s.service(web::resource("/tasks").route(web::get().to(list))); }\n')
        entries = [e for e in result['http'] if e['path'] == '/tasks']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['methods'], 'ANY')

    def test_rust_web_scope_route(self):
        result = self._scan_rs('r.rs', 'fn cfg() { s.service(web::scope("/api")); }\n')
        self.assertIn('/api', [e['path'] for e in result['http']])


if __name__ == '__main__':
    unittest.main()
