"""BACK-1581: the display walk -- what the tree, --files, --meta, --grep and pack:// show.

It replaced display/filtering.PathFilter, a second skip predicate with its own noise list
(tmp/ and build/ always hidden), a name-only --exclude and no REVEAL_IGNORE. The display
purpose is the analysis walk minus dot entries (as ls and rg) and file droppings.
"""
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.tree_view import display_filter


@pytest.fixture
def root(tmp_path):
    return tmp_path


def _mk(root, rel, is_dir=False):
    p = root / rel
    if is_dir:
        p.mkdir(parents=True, exist_ok=True)
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('x = 1\n', encoding='utf-8')
    return p


@pytest.mark.parametrize('rel, is_dir, cause', [
    ('__pycache__', True, 'noise'),
    ('node_modules', True, 'noise'),
    ('.git', True, 'noise'),
    ('.pytest_cache', True, 'noise'),   # noise wins over dot, so the footer says why
    ('module.pyc', False, 'noise'),
    ('notes.swp', False, 'noise'),
    ('.DS_Store', False, 'dot'),
    ('.github', True, 'dot'),
    ('.env', False, 'dot'),
    ('app.py', False, None),
    ('src', True, None),
    ('tmp', True, None),                 # PathFilter hid tmp/ and temp/ unconditionally
])
def test_display_causes(root, rel, is_dir, cause):
    p = _mk(root, rel, is_dir)
    assert display_filter(root, respect_gitignore=False)(p, is_dir) == cause


def test_show_hidden_keeps_dot_entries_but_not_noise(root):
    hidden = display_filter(root, show_hidden=True, respect_gitignore=False)
    assert hidden(_mk(root, '.github', True), True) is None
    assert hidden(_mk(root, '.git', True), True) == 'noise'


def test_gitignore_and_exclude(root):
    (root / '.gitignore').write_text('secret.txt\n', encoding='utf-8')
    secret, cfg = _mk(root, 'secret.txt'), _mk(root, 'sub/local.cfg')
    assert display_filter(root)(secret, False) == 'gitignore'
    assert display_filter(root, respect_gitignore=False)(secret, False) is None
    assert display_filter(root, respect_gitignore=False,
                          exclude_patterns=['*.env', '*.cfg'])(cfg, False) == 'exclude'


@pytest.fixture
def tree(tmp_path, monkeypatch):
    from reveal.config import RevealConfig
    for rel in ('keep/a.py', 'gen/g.py', 'build/b.py', 'tmp/t.py', 'deep/skipme/s.py'):
        _mk(tmp_path, rel)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('REVEAL_IGNORE', 'gen/')
    monkeypatch.setattr(RevealConfig, '_cache', {})
    return tmp_path


def _listed(*args):
    out = _run_reveal_direct('.', '--files', '--format', 'json', *args).stdout
    # Windows prints native separators until BACK-1586; compare POSIX spellings
    return sorted(Path(e['path']).as_posix() for e in json.loads(out)['entries'])


def test_files_honor_reveal_ignore_and_path_exclude(tree):
    """REVEAL_IGNORE reached no display view; a path-shaped --exclude never matched."""
    assert _listed('--exclude', 'deep/skipme') == ['build/b.py', 'keep/a.py', 'tmp/t.py']


def test_tree_footer_names_reveal_ignore(tree):
    out = _run_reveal_direct('.').stdout
    assert 'REVEAL_IGNORE' in out and 'g.py' not in out


def test_meta_counts_what_files_lists(tree):
    meta = json.loads(_run_reveal_direct('.', '--meta', '--format', 'json').stdout)
    assert meta['total_files'] == len(_listed())


def test_grep_searches_what_files_lists(tree):
    out = _run_reveal_direct('.', '--grep', 'x = 1', '--format', 'json').stdout
    searched = sorted(Path(f['path']).as_posix() for f in json.loads(out)['files'])
    assert searched == _listed()
    assert json.loads(out)['hidden'] == {'reveal_ignore': 1}
