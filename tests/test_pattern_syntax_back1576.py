"""BACK-1576: --exclude and REVEAL_IGNORE / config ignore: are gitignore syntax, one matcher.

Three matchers used to read the same pattern three ways: should_skip_file (fnmatch; a bare name
only at the root), PathFilter (fnmatch on the name alone) and config.glob_match. So
``--exclude skipme`` hid ``sub/skipme/`` in the tree but not in ``check``, and
``--exclude sub/skipme`` did the reverse.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.cli.file_checker import should_skip_file
from reveal.utils.gitignore import PatternSet
from pathlib import Path


@pytest.mark.parametrize('pattern, path, is_dir, expected', [
    ('skipme', 'skipme/a.py', False, True),
    ('skipme', 'sub/skipme/a.py', False, True),        # a bare name matches at any depth
    ('*.min.js', 'web/lib/app.min.js', False, True),
    ('sub/skipme', 'sub/skipme/a.py', False, True),    # a slash anchors at the root
    ('sub/skipme', 'x/sub/skipme/a.py', False, False),
    ('/top', 'top/a.py', False, True),
    ('/top', 'x/top/a.py', False, False),
    ('gen/', 'gen', True, True),                        # trailing slash: directories only
    ('gen/', 'gen', False, False),
    ('gen/', 'x/gen/out.py', False, True),
    ('vendor/**', 'vendor/a/b.js', False, True),
    ('**/fixtures', 'a/b/fixtures/x.json', False, True),
    ('app/*', 'app/models/user.rb', False, True),       # under a matched directory
    ('src/*.py', 'src/a/b.py', False, False),          # * does not cross a slash
    ('setup.py', 'pkg/setup.py', False, True),
])
def test_gitignore_semantics(pattern, path, is_dir, expected):
    assert PatternSet((pattern,)).matches(path, is_dir) is expected


def test_negation_reincludes_a_file_but_not_under_an_excluded_dir():
    ps = PatternSet(('*.py', '!keep.py'))
    assert ps.matches('a/b.py') and not ps.matches('a/keep.py')
    assert PatternSet(('gen/', '!gen/keep.py')).matches('gen/keep.py')  # as in git


@pytest.mark.parametrize('patterns, rel, expected', [
    (('app/*',), 'app', True),
    (('vendor/**',), 'vendor', True),
    (('app/assets/*.js',), 'app/assets', False),   # only some children: walk it
    (('app/*', '!app/keep.rb'), 'app', False),     # a re-include keeps the dir walkable
    (('skipme',), 'sub/skipme', True),
])
def test_covers_dir(patterns, rel, expected):
    assert PatternSet(patterns).covers_dir(rel) is expected


def test_should_skip_file_uses_the_same_syntax():
    assert should_skip_file(Path('sub/skipme/a.py'), ['skipme'])
    assert should_skip_file(Path('sub/skipme/_'), ['skipme/'])  # a directory's probe child
    assert not should_skip_file(Path('keep/a.py'), ['skipme'])


@pytest.fixture
def repo(tmp_path, monkeypatch):
    for rel in ('keep/a.py', 'sub/skipme/b.py', 'pathx/deep/p.py'):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text('def f():\n    return 1\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _ast_files(*args):
    out = _run_reveal_direct('ast://.', '--format', 'json', *args).stdout
    # Windows prints native separators until BACK-1366; compare POSIX spellings
    return sorted({Path(r['file']).as_posix() for r in json.loads(out)['results']})


def _tree_files(*args):
    def walk(entries, prefix=''):
        for e in entries:
            if e.get('type') == 'dir':
                yield from walk(e.get('children') or [], f"{prefix}{e['name']}/")
            else:
                yield prefix + e['name']
    out = _run_reveal_direct('.', '--depth', '5', '--format', 'json', *args).stdout
    return sorted(walk(json.loads(out)['entries']))


@pytest.mark.parametrize('pattern', ['skipme', 'sub/skipme', 'skipme/', '**/skipme'])
def test_ast_and_tree_agree_on_every_spelling(repo, pattern):
    assert _ast_files('--exclude', pattern) == ['keep/a.py', 'pathx/deep/p.py']
    assert _tree_files('--exclude', pattern) == ['keep/a.py', 'pathx/deep/p.py']


def test_reveal_ignore_file_pattern_matches_at_any_depth(repo, monkeypatch):
    from reveal.config import RevealConfig
    (repo / 'sub' / 'x.min.js').write_text('x', encoding='utf-8')
    monkeypatch.setenv('REVEAL_IGNORE', 'p.py')
    monkeypatch.setattr(RevealConfig, '_cache', {})
    assert _ast_files() == ['keep/a.py', 'sub/skipme/b.py']
