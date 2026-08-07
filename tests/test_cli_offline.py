"""Tests for reveal/cli/commands/offline.py (BACK-980).

Covers:
  - create_offline_parser(): flags, defaults
  - run_offline(): download_all() default path, --languages subset path,
    --disable-update-check persistence, failure handling
"""

import argparse
from unittest.mock import patch

import pytest

from reveal.cli.commands.offline import create_offline_parser, run_offline


class TestCreateOfflineParser:
    def test_returns_argument_parser(self):
        assert isinstance(create_offline_parser(), argparse.ArgumentParser)

    def test_prog_name(self):
        assert create_offline_parser().prog == 'reveal offline'

    def test_defaults(self):
        args = create_offline_parser().parse_args([])
        assert args.languages is None
        assert args.disable_update_check is False


class TestRunOfflineDownloadAll:
    def test_no_languages_downloads_all(self):
        with patch('tree_sitter_language_pack.download_all', return_value=306) as mock_all:
            with patch('tree_sitter_language_pack.download') as mock_some:
                args = create_offline_parser().parse_args([])
                run_offline(args)
        mock_all.assert_called_once_with()
        mock_some.assert_not_called()

    def test_download_all_failure_exits_nonzero(self):
        with patch('tree_sitter_language_pack.download_all', side_effect=RuntimeError('no network')):
            args = create_offline_parser().parse_args([])
            with pytest.raises(SystemExit) as exc_info:
                run_offline(args)
        assert exc_info.value.code != 0


class TestRunOfflineLanguagesSubset:
    def test_languages_flag_downloads_subset(self):
        with patch('tree_sitter_language_pack.download', return_value=2) as mock_some:
            with patch('tree_sitter_language_pack.download_all') as mock_all:
                args = create_offline_parser().parse_args(['--languages', 'python,go'])
                run_offline(args)
        mock_some.assert_called_once_with(['python', 'go'])
        mock_all.assert_not_called()

    def test_languages_flag_trims_whitespace(self):
        with patch('tree_sitter_language_pack.download', return_value=2) as mock_some:
            args = create_offline_parser().parse_args(['--languages', ' python , go '])
            run_offline(args)
        mock_some.assert_called_once_with(['python', 'go'])

    def test_download_subset_failure_exits_nonzero(self):
        with patch('tree_sitter_language_pack.download', side_effect=RuntimeError('no network')):
            args = create_offline_parser().parse_args(['--languages', 'python'])
            with pytest.raises(SystemExit) as exc_info:
                run_offline(args)
        assert exc_info.value.code != 0


class TestRunOfflineDisableUpdateCheck:
    def test_disable_update_check_calls_persist_function(self):
        with patch('reveal.config.disable_update_check_permanently') as mock_persist:
            with patch('tree_sitter_language_pack.download_all', return_value=306):
                args = create_offline_parser().parse_args(['--disable-update-check'])
                run_offline(args)
        mock_persist.assert_called_once_with()

    def test_without_flag_does_not_persist(self):
        with patch('reveal.config.disable_update_check_permanently') as mock_persist:
            with patch('tree_sitter_language_pack.download_all', return_value=306):
                args = create_offline_parser().parse_args([])
                run_offline(args)
        mock_persist.assert_not_called()
