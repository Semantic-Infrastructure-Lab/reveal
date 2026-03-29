"""Tests for display/filtering.py — GitignoreParser, PathFilter, should_filter_path."""

import pytest
from pathlib import Path
from reveal.display.filtering import (
    GitignoreParser,
    PathFilter,
    should_filter_path,
    DEFAULT_NOISE_PATTERNS,
)


# ============================================================================
# GitignoreParser
# ============================================================================

class TestGitignoreParserParsing:
    def test_skips_blank_lines(self, tmp_path):
        (tmp_path / '.gitignore').write_text('\n\n*.pyc\n')
        parser = GitignoreParser(tmp_path / '.gitignore')
        assert len(parser.patterns) == 1

    def test_skips_comment_lines(self, tmp_path):
        (tmp_path / '.gitignore').write_text('# this is a comment\n*.pyc\n')
        parser = GitignoreParser(tmp_path / '.gitignore')
        assert len(parser.patterns) == 1
        assert parser.patterns[0]['pattern'] == '*.pyc'

    def test_negate_flag_set(self, tmp_path):
        (tmp_path / '.gitignore').write_text('!important.py\n')
        parser = GitignoreParser(tmp_path / '.gitignore')
        assert parser.patterns[0]['negate'] is True
        assert parser.patterns[0]['pattern'] == 'important.py'

    def test_dir_only_flag_set(self, tmp_path):
        (tmp_path / '.gitignore').write_text('build/\n')
        parser = GitignoreParser(tmp_path / '.gitignore')
        assert parser.patterns[0]['dir_only'] is True

    def test_regular_pattern_not_dir_only(self, tmp_path):
        (tmp_path / '.gitignore').write_text('*.log\n')
        parser = GitignoreParser(tmp_path / '.gitignore')
        assert parser.patterns[0]['dir_only'] is False

    def test_nonexistent_gitignore_yields_empty_patterns(self, tmp_path):
        parser = GitignoreParser(tmp_path / '.gitignore')
        assert parser.patterns == []

    def test_multiple_patterns_parsed(self, tmp_path):
        (tmp_path / '.gitignore').write_text('*.pyc\ndist/\n.env\n')
        parser = GitignoreParser(tmp_path / '.gitignore')
        assert len(parser.patterns) == 3


class TestGitignoreParserMatching:
    def test_matches_file_by_glob(self, tmp_path):
        (tmp_path / '.gitignore').write_text('*.pyc\n')
        f = tmp_path / 'module.pyc'
        f.write_text('')
        parser = GitignoreParser(tmp_path / '.gitignore')
        assert parser.matches(f) is True

    def test_no_match_different_extension(self, tmp_path):
        (tmp_path / '.gitignore').write_text('*.pyc\n')
        f = tmp_path / 'module.py'
        f.write_text('')
        parser = GitignoreParser(tmp_path / '.gitignore')
        assert parser.matches(f) is False

    def test_matches_filename_only_pattern(self, tmp_path):
        (tmp_path / '.gitignore').write_text('.DS_Store\n')
        f = tmp_path / 'subdir' / '.DS_Store'
        f.parent.mkdir()
        f.write_text('')
        parser = GitignoreParser(tmp_path / '.gitignore')
        assert parser.matches(f) is True

    def test_negation_overrides_earlier_match(self, tmp_path):
        (tmp_path / '.gitignore').write_text('*.py\n!keep.py\n')
        f = tmp_path / 'keep.py'
        f.write_text('')
        parser = GitignoreParser(tmp_path / '.gitignore')
        assert parser.matches(f) is False

    def test_path_outside_gitignore_dir_not_matched(self, tmp_path):
        (tmp_path / '.gitignore').write_text('*.pyc\n')
        parser = GitignoreParser(tmp_path / '.gitignore')
        outside = Path('/tmp/unrelated_dir_xyz/module.pyc')
        assert parser.matches(outside) is False

    def test_matches_directory_pattern(self, tmp_path):
        (tmp_path / '.gitignore').write_text('dist/\n')
        d = tmp_path / 'dist'
        d.mkdir()
        parser = GitignoreParser(tmp_path / '.gitignore')
        assert parser.matches(d) is True


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
        # No .gitignore — should not crash
        pf = PathFilter(tmp_path, respect_gitignore=True)
        assert pf.gitignore_parser is None

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
