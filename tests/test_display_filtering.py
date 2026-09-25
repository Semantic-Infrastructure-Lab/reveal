"""Tests for display/filtering.py — PathFilter, should_filter_path.

The gitignore matching itself is tests/test_gitignore_oracle.py (BACK-1485).
"""

import pytest
from pathlib import Path
from reveal.display.filtering import (
    PathFilter,
    should_filter_path,
    DEFAULT_NOISE_PATTERNS,
)

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP/network
pytestmark = pytest.mark.component


# ============================================================================
# PathFilter
# ============================================================================

class TestPathFilterDefaults:
    def test_pycache_dir_filtered(self, tmp_path):
        d = tmp_path / '__pycache__'
        d.mkdir()
        assert PathFilter(tmp_path).should_filter(d) is True

    def test_pyc_file_filtered(self, tmp_path):
        f = tmp_path / 'module.pyc'
        f.write_text('')
        assert PathFilter(tmp_path).should_filter(f) is True

    def test_dotgit_dir_filtered(self, tmp_path):
        d = tmp_path / '.git'
        d.mkdir()
        assert PathFilter(tmp_path).should_filter(d) is True

    def test_node_modules_filtered(self, tmp_path):
        d = tmp_path / 'node_modules'
        d.mkdir()
        assert PathFilter(tmp_path).should_filter(d) is True

    def test_pytest_cache_filtered(self, tmp_path):
        d = tmp_path / '.pytest_cache'
        d.mkdir()
        assert PathFilter(tmp_path).should_filter(d) is True

    def test_normal_py_file_not_filtered(self, tmp_path):
        f = tmp_path / 'app.py'
        f.write_text('')
        assert PathFilter(tmp_path).should_filter(f) is False

    def test_normal_dir_not_filtered(self, tmp_path):
        d = tmp_path / 'src'
        d.mkdir()
        assert PathFilter(tmp_path).should_filter(d) is False


class TestPathFilterOptions:
    def test_include_defaults_false_skips_noise_patterns(self, tmp_path):
        f = tmp_path / 'module.pyc'
        f.write_text('')
        pf = PathFilter(tmp_path, include_defaults=False)
        assert pf.should_filter(f) is False

    def test_custom_exclude_pattern_matches(self, tmp_path):
        f = tmp_path / 'secrets.env'
        f.write_text('')
        pf = PathFilter(tmp_path, exclude_patterns=['*.env'])
        assert pf.should_filter(f) is True

    def test_custom_exclude_pattern_no_match(self, tmp_path):
        f = tmp_path / 'app.py'
        f.write_text('')
        pf = PathFilter(tmp_path, exclude_patterns=['*.env'])
        assert pf.should_filter(f) is False

    def test_respect_gitignore_loads_parser(self, tmp_path):
        (tmp_path / '.gitignore').write_text('secret.txt\n')
        f = tmp_path / 'secret.txt'
        f.write_text('')
        pf = PathFilter(tmp_path, respect_gitignore=True, include_defaults=False)
        assert pf.should_filter(f) is True

    def test_respect_gitignore_false_ignores_gitignore(self, tmp_path):
        (tmp_path / '.gitignore').write_text('app.py\n')
        f = tmp_path / 'app.py'
        f.write_text('')
        pf = PathFilter(tmp_path, respect_gitignore=False, include_defaults=False)
        assert pf.should_filter(f) is False

    def test_no_gitignore_file_no_error(self, tmp_path):
        # No .gitignore — should not crash, and nothing is hidden for it
        f = tmp_path / 'app.py'
        f.write_text('')
        pf = PathFilter(tmp_path, respect_gitignore=True, include_defaults=False)
        assert pf.should_filter(f) is False

    def test_multiple_custom_patterns(self, tmp_path):
        f = tmp_path / 'local.cfg'
        f.write_text('')
        pf = PathFilter(tmp_path, exclude_patterns=['*.env', '*.cfg'])
        assert pf.should_filter(f) is True


# ============================================================================
# should_filter_path (convenience wrapper)
# ============================================================================

class TestShouldFilterPath:
    def test_pycache_filtered(self, tmp_path):
        d = tmp_path / '__pycache__'
        d.mkdir()
        assert should_filter_path(d, root_path=tmp_path) is True

    def test_normal_file_not_filtered(self, tmp_path):
        f = tmp_path / 'main.py'
        f.write_text('')
        assert should_filter_path(f, root_path=tmp_path) is False

    def test_root_path_defaults_to_parent_for_file(self, tmp_path):
        f = tmp_path / 'foo.pyc'
        f.write_text('')
        # root_path not supplied — should infer from parent
        assert should_filter_path(f) is True

    def test_root_path_defaults_to_self_for_dir(self, tmp_path):
        d = tmp_path / '__pycache__'
        d.mkdir()
        assert should_filter_path(d) is True

    def test_exclude_patterns_passed_through(self, tmp_path):
        f = tmp_path / 'local.env'
        f.write_text('')
        assert should_filter_path(f, root_path=tmp_path, exclude_patterns=['*.env']) is True

    def test_include_defaults_false(self, tmp_path):
        f = tmp_path / 'module.pyc'
        f.write_text('')
        assert should_filter_path(f, root_path=tmp_path, include_defaults=False) is False

    def test_respect_gitignore_false(self, tmp_path):
        (tmp_path / '.gitignore').write_text('app.py\n')
        f = tmp_path / 'app.py'
        f.write_text('')
        assert should_filter_path(f, root_path=tmp_path, respect_gitignore=False) is False


# ============================================================================
# DEFAULT_NOISE_PATTERNS sanity checks
# ============================================================================

class TestDefaultNoisePatterns:
    def test_pycache_in_defaults(self):
        assert '__pycache__' in DEFAULT_NOISE_PATTERNS

    def test_pyc_in_defaults(self):
        assert '*.pyc' in DEFAULT_NOISE_PATTERNS

    def test_git_in_defaults(self):
        assert '.git/' in DEFAULT_NOISE_PATTERNS

    def test_node_modules_in_defaults(self):
        assert 'node_modules/' in DEFAULT_NOISE_PATTERNS
