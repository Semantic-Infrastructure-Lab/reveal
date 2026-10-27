"""BACK-2274: `.reveal.yaml` `overrides.files`: `*` and `?` stay inside one path segment.

`config._compile_glob_regex` ran a pattern without `**` through plain `fnmatch.translate`, where `*`
also matches `/`: `src/*.py` matched `src/a/b.py` and `*.py` matched every Python file at any depth,
against `glob_match`'s own docstring. Inside a `**` pattern the other `*`s crossed `/` too
(`**/test_*.py` matched `tests/test_dir/x.py`). `ignore:` keeps `.gitignore` rules (a bare name
matches at any depth); overrides stay anchored at the project root.
"""
import json
from pathlib import Path

import pytest
import yaml

from conftest import _run_reveal_in
from reveal.config import RevealConfig, glob_match
from reveal.utils.gitignore import PatternSet


@pytest.mark.parametrize('path, pattern', [
    ('src/a/b.py', 'src/*.py'),           # * does not cross a slash
    ('a/b/c.py', '*.py'),                 # a pattern without a slash is the root only
    ('src/a/b.py', 'src?a/b.py'),         # ? is not a slash either
    ('tests/test_dir/x.py', '**/test_*.py'),  # nor the * beside a **
])
def test_star_and_question_mark_stay_in_one_segment(path, pattern):
    assert glob_match(Path(path), pattern) is False


@pytest.mark.parametrize('path, pattern', [
    ('src/b.py', 'src/*.py'),
    ('b.py', '*.py'),
    ('src/a/b.py', 'src/*/b.py'),
    ('src/a/b.py', 'src/?/b.py'),
    ('src/a/b.py', 'src/[ab]/b.py'),
    ('tests/x.py', 'tests/**'),
    ('tests/a/b/x.py', 'tests/**'),
    ('tests/x.py', 'tests/**/*.py'),          # ** matches zero segments
    ('tests/unit/deep/x.py', 'tests/**/*.py'),
    ('a/b/test_x.py', '**/test_*.py'),
    ('test_x.py', '**/test_*.py'),
    ('a/b.py', 'a/**/b.py'),
    ('a/x/y/b.py', 'a/**/b.py'),
    ('src/utils/helpers.py', 'src/**/*.py'),  # the CONFIGURATION_GUIDE example
    ('reveal/adapters/git/help.py', 'reveal/adapters/**/help.py'),  # this repo's .reveal.yaml
])
def test_patterns_that_still_match(path, pattern):
    assert glob_match(Path(path), pattern) is True


def test_ignore_keeps_gitignore_semantics():
    """Negative control on the sibling matcher: `ignore:` is `.gitignore` syntax, unchanged."""
    assert PatternSet(('*.py',)).matches('a/b/c.py')        # a bare name at any depth
    assert PatternSet(('tests/',)).matches('a/tests/x.py')  # a directory name at any depth
    assert not PatternSet(('src/*.py',)).matches('src/a/b.py')


def _project(tmp_path, pattern):
    long_line = 'x = "' + 'a' * 120 + '"\n'
    for rel in ('tests/test_top.py', 'tests/deep/test_g.py', 'src/app.py'):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(long_line, encoding='utf-8')
    config = {'root': True, 'overrides': [{'files': pattern, 'rules': {'disable': ['E501']}}]}
    (tmp_path / '.reveal.yaml').write_text(yaml.safe_dump(config), encoding='utf-8')
    return tmp_path


@pytest.fixture(autouse=True)
def _fresh_config_cache():
    RevealConfig._cache.clear()
    yield
    RevealConfig._cache.clear()


@pytest.mark.parametrize('pattern, suppressed', [
    ('tests/*.py', ['tests/test_top.py']),
    ('tests/**/*.py', ['tests/deep/test_g.py', 'tests/test_top.py']),
    ('**/test_*.py', ['tests/deep/test_g.py', 'tests/test_top.py']),
])
def test_override_applies_through_file_config(tmp_path, pattern, suppressed):
    root = _project(tmp_path, pattern)
    cfg = RevealConfig.get(root)
    files = ['src/app.py', 'tests/deep/test_g.py', 'tests/test_top.py']
    disabled = [rel for rel in files if not cfg.get_file_config(root / rel).is_rule_enabled('E501')]
    assert disabled == suppressed


def test_check_reports_e501_in_the_nested_file(tmp_path):
    root = _project(tmp_path, 'tests/*.py')
    # No --select: a CLI --select re-enables a rule the config disables.
    result = _run_reveal_in(root, 'check', '.', '--format', 'json')
    data = json.loads(result.stdout)
    flagged = sorted({Path(f['file']).as_posix() for f in data['files']
                      if any(d['rule_code'] == 'E501' for d in f.get('detections', []))})
    assert flagged == ['src/app.py', 'tests/deep/test_g.py']
