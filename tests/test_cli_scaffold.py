"""Tests for reveal/cli/commands/scaffold.py — 0% → covered.

Covers:
  - create_scaffold_parser(): all three subcommands, arguments, defaults, flags
  - run_scaffold(): dispatch to handle_scaffold_adapter/analyzer/rule
"""

import argparse
from argparse import Namespace
from unittest.mock import patch

import pytest

from reveal.cli.commands.scaffold import create_scaffold_parser, run_scaffold


# ─── create_scaffold_parser ───────────────────────────────────────────────────

class TestCreateScaffoldParser:

    def test_returns_argument_parser(self):
        parser = create_scaffold_parser()
        assert isinstance(parser, argparse.ArgumentParser)

    def test_prog_name(self):
        parser = create_scaffold_parser()
        assert parser.prog == 'reveal scaffold'

    def test_no_subcommand_raises(self):
        parser = create_scaffold_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_unknown_subcommand_raises(self):
        parser = create_scaffold_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(['unknown'])

    # adapter subcommand

    def test_adapter_sets_component(self):
        parser = create_scaffold_parser()
        args = parser.parse_args(['adapter', 'github', 'github://'])
        assert args.component == 'adapter'

    def test_adapter_parses_name_and_uri(self):
        parser = create_scaffold_parser()
        args = parser.parse_args(['adapter', 'docker', 'docker://'])
        assert args.name == 'docker'
        assert args.uri == 'docker://'

    def test_adapter_force_defaults_false(self):
        parser = create_scaffold_parser()
        args = parser.parse_args(['adapter', 'git', 'git://'])
        assert args.force is False

    def test_adapter_force_flag(self):
        parser = create_scaffold_parser()
        args = parser.parse_args(['adapter', 'git', 'git://', '--force'])
        assert args.force is True

    def test_adapter_missing_args_raises(self):
        parser = create_scaffold_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(['adapter'])

    # analyzer subcommand

    def test_analyzer_sets_component(self):
        parser = create_scaffold_parser()
        args = parser.parse_args(['analyzer', 'kotlin', '.kt'])
        assert args.component == 'analyzer'

    def test_analyzer_parses_name_and_extension(self):
        parser = create_scaffold_parser()
        args = parser.parse_args(['analyzer', 'dart', '.dart'])
        assert args.name == 'dart'
        assert args.extension == '.dart'

    def test_analyzer_force_defaults_false(self):
        parser = create_scaffold_parser()
        args = parser.parse_args(['analyzer', 'dart', '.dart'])
        assert args.force is False

    def test_analyzer_force_flag(self):
        parser = create_scaffold_parser()
        args = parser.parse_args(['analyzer', 'dart', '.dart', '--force'])
        assert args.force is True

    def test_analyzer_missing_args_raises(self):
        parser = create_scaffold_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(['analyzer'])

    # rule subcommand

    def test_rule_sets_component(self):
        parser = create_scaffold_parser()
        args = parser.parse_args(['rule', 'C001', 'custom-check'])
        assert args.component == 'rule'

    def test_rule_parses_code_and_name(self):
        parser = create_scaffold_parser()
        args = parser.parse_args(['rule', 'X001', 'my-pattern'])
        assert args.code == 'X001'
        assert args.name == 'my-pattern'

    def test_rule_category_default(self):
        parser = create_scaffold_parser()
        args = parser.parse_args(['rule', 'C001', 'my-rule'])
        assert args.category == 'custom'

    def test_rule_category_override(self):
        parser = create_scaffold_parser()
        args = parser.parse_args(['rule', 'C001', 'my-rule', '--category', 'security'])
        assert args.category == 'security'

    def test_rule_force_defaults_false(self):
        parser = create_scaffold_parser()
        args = parser.parse_args(['rule', 'C001', 'my-rule'])
        assert args.force is False

    def test_rule_force_flag(self):
        parser = create_scaffold_parser()
        args = parser.parse_args(['rule', 'C001', 'my-rule', '--force'])
        assert args.force is True

    def test_rule_missing_args_raises(self):
        parser = create_scaffold_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(['rule'])


# ─── run_scaffold ─────────────────────────────────────────────────────────────

class TestRunScaffold:

    def test_dispatches_adapter(self):
        args = Namespace(component='adapter', name='github', uri='github://', force=False)
        with patch('reveal.cli.handle_scaffold_adapter') as mock_fn:
            run_scaffold(args)
        mock_fn.assert_called_once_with('github', 'github://', False)

    def test_dispatches_adapter_with_force(self):
        args = Namespace(component='adapter', name='docker', uri='docker://', force=True)
        with patch('reveal.cli.handle_scaffold_adapter') as mock_fn:
            run_scaffold(args)
        mock_fn.assert_called_once_with('docker', 'docker://', True)

    def test_dispatches_analyzer(self):
        args = Namespace(component='analyzer', name='kotlin', extension='.kt', force=False)
        with patch('reveal.cli.handle_scaffold_analyzer') as mock_fn:
            run_scaffold(args)
        mock_fn.assert_called_once_with('kotlin', '.kt', False)

    def test_dispatches_analyzer_with_force(self):
        args = Namespace(component='analyzer', name='dart', extension='.dart', force=True)
        with patch('reveal.cli.handle_scaffold_analyzer') as mock_fn:
            run_scaffold(args)
        mock_fn.assert_called_once_with('dart', '.dart', True)

    def test_dispatches_rule(self):
        args = Namespace(component='rule', code='C001', name='my-rule', category='custom', force=False)
        with patch('reveal.cli.handle_scaffold_rule') as mock_fn:
            run_scaffold(args)
        mock_fn.assert_called_once_with('C001', 'my-rule', 'custom', False)

    def test_dispatches_rule_with_force_and_category(self):
        args = Namespace(component='rule', code='S001', name='security-check', category='security', force=True)
        with patch('reveal.cli.handle_scaffold_rule') as mock_fn:
            run_scaffold(args)
        mock_fn.assert_called_once_with('S001', 'security-check', 'security', True)
