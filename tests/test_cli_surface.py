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

from reveal.cli.commands.surface import (
    _get_open_mode,
    _is_cli_command,
    _is_env_access,
    _is_fs_write,
    _is_http_route,
    _is_mcp_tool,
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

    def test_type_flag(self):
        parser = create_surface_parser()
        args = parser.parse_args(['--type', 'env'])
        self.assertEqual(args.type, 'env')


class TestClassifiers(unittest.TestCase):

    def test_is_http_route_flask(self):
        self.assertTrue(_is_http_route("app.route('/path')"))

    def test_is_http_route_fastapi_get(self):
        self.assertTrue(_is_http_route("router.get('/items')"))

    def test_is_http_route_post(self):
        self.assertTrue(_is_http_route("app.post('/create')"))

    def test_is_http_route_false(self):
        self.assertFalse(_is_http_route("app.command('deploy')"))

    def test_is_cli_command_click(self):
        self.assertTrue(_is_cli_command("click.command()"))
        self.assertTrue(_is_cli_command("app.command()"))

    def test_is_cli_command_false(self):
        self.assertFalse(_is_cli_command("app.route('/x')"))

    def test_is_mcp_tool(self):
        self.assertTrue(_is_mcp_tool("mcp.tool()"))
        self.assertTrue(_is_mcp_tool("server.tool()"))

    def test_is_mcp_tool_false(self):
        self.assertFalse(_is_mcp_tool("app.route('/x')"))

    def test_is_env_access_os_getenv(self):
        self.assertTrue(_is_env_access("os.getenv"))

    def test_is_env_access_os_environ_get(self):
        self.assertTrue(_is_env_access("os.environ.get"))

    def test_is_env_access_false(self):
        self.assertFalse(_is_env_access("os.path.join"))


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


class TestRenderReport(unittest.TestCase):

    def _capture(self, report):
        buf = StringIO()
        with patch('sys.stdout', buf):
            _render_report(report)
        return buf.getvalue()

    def _empty_report(self, **kwargs):
        base = {
            'path': '/proj',
            'total': 0,
            'surfaces': {k: [] for k in ('cli', 'http', 'mcp', 'env', 'network', 'db', 'sdk', 'fs')},
        }
        base.update(kwargs)
        return base

    def test_no_surfaces_shows_message(self):
        out = self._capture(self._empty_report())
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


if __name__ == '__main__':
    unittest.main()
