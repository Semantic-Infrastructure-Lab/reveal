"""Tests for reveal/config.py's user-config write helpers (BACK-980).

disable_breadcrumbs_permanently() predates this and had no direct test;
covering both it and its new sibling disable_update_check_permanently()
here since they now share _read_user_config()/_write_user_config().
"""

from unittest.mock import patch

import yaml

from reveal.config import (
    RevealConfig,
    disable_breadcrumbs_permanently,
    disable_update_check_permanently,
    _read_user_config,
)


def _patch_user_config_path(tmp_path):
    config_path = tmp_path / 'reveal' / 'config.yaml'
    return patch.object(RevealConfig, '_get_user_config_path', return_value=config_path), config_path


class TestDisableUpdateCheckPermanently:
    def test_creates_config_with_network_section(self, tmp_path):
        patcher, config_path = _patch_user_config_path(tmp_path)
        with patcher:
            result = disable_update_check_permanently()

        assert result is True
        written = yaml.safe_load(config_path.read_text(encoding='utf-8'))
        assert written == {'network': {'no_update_check': True}}

    def test_preserves_existing_unrelated_keys(self, tmp_path):
        config_path = tmp_path / 'reveal' / 'config.yaml'
        config_path.parent.mkdir(parents=True)
        config_path.write_text(yaml.dump({'display': {'breadcrumbs': False}}), encoding='utf-8')

        patcher, _ = _patch_user_config_path(tmp_path)
        with patcher:
            disable_update_check_permanently()

        written = yaml.safe_load(config_path.read_text(encoding='utf-8'))
        assert written == {
            'display': {'breadcrumbs': False},
            'network': {'no_update_check': True},
        }

    def test_write_failure_returns_false(self, tmp_path):
        patcher, config_path = _patch_user_config_path(tmp_path)
        with patcher:
            with patch('builtins.open', side_effect=OSError('disk full')):
                result = disable_update_check_permanently()
        assert result is False


class TestDisableBreadcrumbsPermanently:
    def test_creates_config_with_display_section(self, tmp_path):
        patcher, config_path = _patch_user_config_path(tmp_path)
        with patcher:
            result = disable_breadcrumbs_permanently()

        assert result is True
        written = yaml.safe_load(config_path.read_text(encoding='utf-8'))
        assert written == {'display': {'breadcrumbs': False}}


class TestReadUserConfig:
    def test_missing_file_returns_empty_dict(self, tmp_path):
        patcher, _ = _patch_user_config_path(tmp_path)
        with patcher:
            assert _read_user_config() == {}

    def test_malformed_yaml_returns_empty_dict(self, tmp_path):
        config_path = tmp_path / 'reveal' / 'config.yaml'
        config_path.parent.mkdir(parents=True)
        config_path.write_text('not: valid: yaml: [', encoding='utf-8')

        patcher, _ = _patch_user_config_path(tmp_path)
        with patcher:
            assert _read_user_config() == {}
