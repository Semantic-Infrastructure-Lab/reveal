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


if __name__ == '__main__':
    unittest.main()
