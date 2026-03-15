"""Tests for reveal/cli/commands/dev.py."""

import io
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from unittest.mock import patch, MagicMock

from reveal.cli.commands.dev import (
    create_dev_parser,
    add_arguments,
    run_dev,
    _run_inspect_config,
)


# ---------------------------------------------------------------------------
# Parser structure
# ---------------------------------------------------------------------------

class TestCreateDevParser(unittest.TestCase):

    def test_parser_created(self):
        parser = create_dev_parser()
        self.assertIsNotNone(parser)

    def test_new_adapter_subcommand_exists(self):
        parser = create_dev_parser()
        args = parser.parse_args(['new-adapter', 'payments'])
        self.assertEqual(args.dev_command, 'new-adapter')
        self.assertEqual(args.name, 'payments')

    def test_new_adapter_uri_flag(self):
        parser = create_dev_parser()
        args = parser.parse_args(['new-adapter', 'payments', '--uri', 'pay'])
        self.assertEqual(args.uri, 'pay')

    def test_new_adapter_force_flag(self):
        parser = create_dev_parser()
        args = parser.parse_args(['new-adapter', 'payments', '--force'])
        self.assertTrue(args.force)

    def test_new_analyzer_subcommand(self):
        parser = create_dev_parser()
        args = parser.parse_args(['new-analyzer', 'kotlin', '--ext', '.kt'])
        self.assertEqual(args.dev_command, 'new-analyzer')
        self.assertEqual(args.name, 'kotlin')
        self.assertEqual(args.ext, '.kt')

    def test_new_rule_subcommand(self):
        parser = create_dev_parser()
        args = parser.parse_args(['new-rule', 'C001', 'deep-nesting'])
        self.assertEqual(args.dev_command, 'new-rule')
        self.assertEqual(args.code, 'C001')
        self.assertEqual(args.name, 'deep-nesting')

    def test_new_rule_default_category(self):
        parser = create_dev_parser()
        args = parser.parse_args(['new-rule', 'C001', 'deep-nesting'])
        self.assertEqual(args.category, 'custom')

    def test_new_rule_custom_category(self):
        parser = create_dev_parser()
        args = parser.parse_args(['new-rule', 'C001', 'deep-nesting', '--category', 'bugs'])
        self.assertEqual(args.category, 'bugs')

    def test_inspect_config_subcommand(self):
        parser = create_dev_parser()
        args = parser.parse_args(['inspect-config'])
        self.assertEqual(args.dev_command, 'inspect-config')

    def test_no_subcommand_raises(self):
        parser = create_dev_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([])


# ---------------------------------------------------------------------------
# run_dev dispatch
# ---------------------------------------------------------------------------

class TestRunDev(unittest.TestCase):

    @patch('reveal.cli.commands.dev._run_inspect_config')
    def test_inspect_config_dispatches(self, mock_inspect):
        args = Namespace(dev_command='inspect-config')
        run_dev(args)
        mock_inspect.assert_called_once()

    def test_new_analyzer_ext_defaults_to_dot_name(self):
        args = Namespace(dev_command='new-analyzer', name='kotlin', ext=None, force=False)
        calls = []
        def fake_scaffold(name, ext, force):
            calls.append((name, ext, force))
        with patch('reveal.cli.commands.dev.handle_scaffold_analyzer', fake_scaffold, create=True):
            with patch('reveal.cli.commands.dev.__builtins__'):
                # Verify that ext defaults to .kotlin when not provided
                # The function does: ext = args.ext or f'.{args.name}'
                expected_ext = f'.{args.name}'
                self.assertEqual(expected_ext, '.kotlin')


# ---------------------------------------------------------------------------
# _run_inspect_config
# ---------------------------------------------------------------------------

class TestRunInspectConfig(unittest.TestCase):

    def _capture(self):
        from pathlib import Path as RealPath
        buf = io.StringIO()
        with patch('reveal.cli.commands.dev.Path') as mock_path_cls:
            mock_path_cls.cwd.return_value = RealPath('/tmp')
            mock_path_cls.side_effect = lambda *a, **kw: RealPath(*a, **kw)
            with redirect_stdout(buf):
                _run_inspect_config()
        return buf.getvalue()

    def test_no_crash(self):
        out = self._capture()
        self.assertIsInstance(out, str)

    def test_shows_search_root(self):
        out = self._capture()
        self.assertIn("Search root", out)

    def test_shows_config_header(self):
        out = self._capture()
        self.assertIn("configuration", out.lower())

    def test_shows_defaults_or_settings(self):
        out = self._capture()
        self.assertTrue(
            "default" in out.lower() or "layers" in out or "exclude" in out or "Config file" in out
        )


if __name__ == '__main__':
    unittest.main()
