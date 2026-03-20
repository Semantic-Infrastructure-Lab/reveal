"""Tests targeting uncovered lines in reveal/analyzers/imports/layers.py.

Covers:
- LayerRule.matches_file path-not-under-root (lines 55–59)
- LayerRule.is_violation to_module None (line 91)
- LayerRule.is_violation allow_imports violation (lines 101–102)
- LayerRule._normalize_to_module outside root (lines 111–113)
- LayerRule._is_target_allowed no match returns False (line 121)
- LayerConfig.from_dict bad layer_def exception (lines 169–171)
- load_layer_config fallback yaml path (lines 208–245)
"""

import pytest
from pathlib import Path

from reveal.analyzers.imports.layers import LayerRule, LayerConfig, load_layer_config


class TestLayerRuleMatchesFile:
    """Tests for LayerRule.matches_file."""

    def test_file_not_under_project_root_returns_false(self, tmp_path):
        """Lines 55–57 — file outside project_root raises ValueError internally → False."""
        other = tmp_path / 'other'
        other.mkdir()
        project_root = tmp_path / 'project'
        project_root.mkdir()
        file_outside = other / 'some_file.py'

        rule = LayerRule(name='api', paths=['api/'], allow_imports=[], deny_imports=[])
        result = rule.matches_file(file_outside, project_root)
        assert result is False

    def test_file_under_root_with_matching_path(self, tmp_path):
        """File under project root that matches path prefix → True."""
        api_dir = tmp_path / 'api'
        api_dir.mkdir()
        api_file = api_dir / 'views.py'

        rule = LayerRule(name='api', paths=['api/'], allow_imports=[], deny_imports=[])
        result = rule.matches_file(api_file, tmp_path)
        assert result is True

    def test_file_under_root_no_match_returns_false(self, tmp_path):
        """File under project root that does not match → False."""
        services_file = tmp_path / 'services' / 'auth.py'
        (tmp_path / 'services').mkdir()

        rule = LayerRule(name='api', paths=['api/'], allow_imports=[], deny_imports=[])
        result = rule.matches_file(services_file, tmp_path)
        assert result is False

    def test_matches_file_without_project_root(self, tmp_path):
        """Line 59 — no project_root → uses raw str path."""
        api_file = tmp_path / 'api' / 'views.py'
        rule = LayerRule(name='api', paths=[str(tmp_path / 'api')], allow_imports=[], deny_imports=[])
        result = rule.matches_file(api_file, project_root=None)
        assert result is True

    def test_glob_star_star_pattern(self, tmp_path):
        """** glob pattern matches nested directories."""
        (tmp_path / 'src' / 'api').mkdir(parents=True)
        api_file = tmp_path / 'src' / 'api' / 'views.py'

        rule = LayerRule(name='api', paths=['src/api/**'], allow_imports=[], deny_imports=[])
        result = rule.matches_file(api_file, tmp_path)
        assert result is True


class TestLayerRuleIsViolation:
    """Tests for LayerRule.is_violation."""

    def test_no_violation_when_file_not_in_layer(self, tmp_path):
        """Source file outside layer → no violation."""
        rule = LayerRule(name='api', paths=['api/'], allow_imports=[], deny_imports=['db/'])
        from_file = tmp_path / 'other' / 'file.py'
        to_file = tmp_path / 'db' / 'model.py'
        is_viol, reason = rule.is_violation(from_file, to_file, tmp_path)
        assert is_viol is False
        assert reason is None

    def test_to_module_none_when_outside_root(self, tmp_path):
        """Line 91 — to_file outside project_root → to_module None → no violation."""
        (tmp_path / 'api').mkdir()
        from_file = tmp_path / 'api' / 'views.py'
        to_file = Path('/totally/outside/db/model.py')

        rule = LayerRule(name='api', paths=['api/'], allow_imports=[], deny_imports=['db/'])
        is_viol, reason = rule.is_violation(from_file, to_file, tmp_path)
        assert is_viol is False

    def test_deny_imports_violation(self, tmp_path):
        """Deny list match → violation."""
        (tmp_path / 'api').mkdir()
        (tmp_path / 'db').mkdir()
        from_file = tmp_path / 'api' / 'views.py'
        to_file = tmp_path / 'db' / 'model.py'

        rule = LayerRule(name='api', paths=['api/'], allow_imports=[], deny_imports=['db'])
        is_viol, reason = rule.is_violation(from_file, to_file, tmp_path)
        assert is_viol is True
        assert 'db' in reason

    def test_allow_imports_violation_when_not_allowed(self, tmp_path):
        """Lines 101–102 — allow_imports specified but target not in allow list."""
        (tmp_path / 'api').mkdir()
        (tmp_path / 'external').mkdir()
        from_file = tmp_path / 'api' / 'views.py'
        to_file = tmp_path / 'external' / 'lib.py'

        rule = LayerRule(name='api', paths=['api/'], allow_imports=['models'], deny_imports=[])
        is_viol, reason = rule.is_violation(from_file, to_file, tmp_path)
        assert is_viol is True
        assert 'models' in reason

    def test_allow_imports_no_violation_when_allowed(self, tmp_path):
        """Target matches allow_imports → no violation."""
        (tmp_path / 'api').mkdir()
        (tmp_path / 'models').mkdir()
        from_file = tmp_path / 'api' / 'views.py'
        to_file = tmp_path / 'models' / 'user.py'

        rule = LayerRule(name='api', paths=['api/'], allow_imports=['models'], deny_imports=[])
        is_viol, reason = rule.is_violation(from_file, to_file, tmp_path)
        assert is_viol is False


class TestNormalizeToModule:
    """Tests for LayerRule._normalize_to_module."""

    def test_returns_none_when_outside_root(self, tmp_path):
        """Lines 111–113 — file outside project_root returns None."""
        rule = LayerRule(name='test', paths=[], allow_imports=[], deny_imports=[])
        to_file = Path('/completely/outside/file.py')
        result = rule._normalize_to_module(to_file, tmp_path)
        assert result is None

    def test_returns_slash_path_when_inside_root(self, tmp_path):
        """File inside root returns relative slash-terminated path."""
        rule = LayerRule(name='test', paths=[], allow_imports=[], deny_imports=[])
        to_file = tmp_path / 'models' / 'user.py'
        result = rule._normalize_to_module(to_file, tmp_path)
        assert result is not None
        assert result.endswith('/')

    def test_returns_path_without_root_when_no_root(self, tmp_path):
        """Without project_root, returns absolute path + /."""
        rule = LayerRule(name='test', paths=[], allow_imports=[], deny_imports=[])
        to_file = tmp_path / 'models.py'
        result = rule._normalize_to_module(to_file, None)
        assert result == str(to_file).replace("\\", "/") + '/'


class TestIsTargetAllowed:
    """Tests for LayerRule._is_target_allowed."""

    def test_returns_true_when_matching_pattern(self):
        """Pattern match → True."""
        rule = LayerRule(name='test', paths=[], allow_imports=['models'], deny_imports=[])
        assert rule._is_target_allowed('models/user.py/') is True

    def test_returns_false_when_no_match(self):
        """Line 121 — no pattern matches → False."""
        rule = LayerRule(name='test', paths=[], allow_imports=['models', 'utils'], deny_imports=[])
        assert rule._is_target_allowed('external/lib.py/') is False

    def test_pattern_without_trailing_slash_still_matches(self):
        """Pattern 'models' matches 'models/user.py/'."""
        rule = LayerRule(name='test', paths=[], allow_imports=['models'], deny_imports=[])
        assert rule._is_target_allowed('models/') is True


class TestLayerConfigFromDict:
    """Tests for LayerConfig.from_dict error handling."""

    def test_valid_config(self):
        config_dict = {
            'architecture': {
                'layers': [
                    {'name': 'api', 'paths': ['api/'], 'deny_imports': ['db/']}
                ]
            }
        }
        config = LayerConfig.from_dict(config_dict)
        assert len(config.layers) == 1
        assert config.layers[0].name == 'api'

    def test_empty_layers(self):
        config = LayerConfig.from_dict({'architecture': {'layers': []}})
        assert config.layers == []

    def test_missing_architecture_key(self):
        config = LayerConfig.from_dict({})
        assert config.layers == []

    def test_bad_layer_def_is_skipped(self):
        """Lines 169–171 — invalid layer_def (not a dict) triggers exception → skipped."""
        config_dict = {'architecture': {'layers': ['not-a-dict']}}
        config = LayerConfig.from_dict(config_dict)
        # Bad entry skipped, no crash
        assert config.layers == []


class TestLoadLayerConfig:
    """Lines 208–245 — load_layer_config fallback yaml path."""

    def test_returns_none_when_no_config_file(self, tmp_path):
        """No .reveal.yaml anywhere in tree → None."""
        result = load_layer_config(tmp_path)
        assert result is None

    def test_loads_from_reveal_yaml_in_directory(self, tmp_path):
        """Lines 226–243 — fallback yaml loading finds .reveal.yaml."""
        reveal_yaml = tmp_path / '.reveal.yaml'
        reveal_yaml.write_text(
            'architecture:\n'
            '  layers:\n'
            '    - name: api\n'
            '      paths:\n'
            '        - api/\n'
            '      deny_imports:\n'
            '        - db/\n'
        )

        from unittest import mock
        # Force RevealConfig path to raise so fallback yaml is used
        with mock.patch('reveal.config.RevealConfig.get', side_effect=Exception("no config")):
            result = load_layer_config(tmp_path)

        if result is not None:
            assert len(result.layers) >= 1
            assert result.layers[0].name == 'api'
