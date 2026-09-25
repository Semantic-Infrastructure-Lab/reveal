"""BACK-1485: the shared gitignore oracle (reveal/utils/gitignore.py).

The old matcher dropped tracked files and ignored ``!negation``. These tests
pin git's own semantics: tracked files are never ignored, negation
re-includes, nested .gitignore / info/exclude count, nested repositories
answer for themselves. The pattern fallback (non-git trees) is checked against
git itself on a battery of gitignore(5) forms.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from reveal.utils import gitignore
from reveal.utils.gitignore import (
    GitIgnoreFilter,
    _PatternMatcher,
    compile_gitignore_line,
    gitignore_filter,
    is_gitignored,
)

pytestmark = pytest.mark.skipif(shutil.which('git') is None, reason='git not installed')


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ['git', '-C', str(root), '-c', 'user.name=t', '-c', 'user.email=t@t',
         '-c', 'core.excludesFile=', *args],
        check=True, capture_output=True, text=True, encoding='utf-8',
    ).stdout


def _write(root: Path, rel: str, text: str = 'x\n') -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')


def _walk(root: Path, flt: GitIgnoreFilter):
    kept = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != '.git']
        flt.prune(dirpath, dirs)
        for name in files:
            p = os.path.join(dirpath, name)
            if not flt.ignored(p):
                kept.append(Path(p).relative_to(root).as_posix())
    return sorted(kept)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    # Keep the developer's global excludes file out of the verdicts.
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', os.devnull)
    root = tmp_path / 'repo'
    root.mkdir()
    _git(root, 'init', '-q')
    return root


def test_tracked_file_under_ignored_dir_is_kept(repo):
    """tia's '**/env/' dropped committed config/env/* (19,292 tracked files)."""
    _write(repo, '.gitignore', '**/env/\n')
    _write(repo, 'config/env/settings.py')
    _write(repo, 'other/env/cache.py')
    _git(repo, 'add', '-f', '.gitignore', 'config/env/settings.py')
    _git(repo, 'commit', '-q', '-m', 'init')
    _write(repo, 'config/env/scratch.py')  # untracked beside a tracked file

    kept = _walk(repo, GitIgnoreFilter(repo))

    assert 'config/env/settings.py' in kept
    assert 'config/env/scratch.py' not in kept
    assert 'other/env/cache.py' not in kept


def test_negation_reincludes(repo):
    """sociamonials-ops: '*.sql' + '!docs/database/procedures/*.sql'."""
    _write(repo, '.gitignore', '*.sql\n!docs/database/procedures/*.sql\n')
    _write(repo, 'docs/database/procedures/sp_a.sql')
    _write(repo, 'dump.sql')

    kept = _walk(repo, GitIgnoreFilter(repo))

    assert 'docs/database/procedures/sp_a.sql' in kept
    assert 'dump.sql' not in kept


def test_nested_gitignore_and_info_exclude(repo):
    _write(repo, 'sub/.gitignore', 'local.py\n')
    _write(repo, 'sub/local.py')
    _write(repo, 'local.py')  # the nested rule does not reach the root
    (repo / '.git' / 'info').mkdir(exist_ok=True)
    (repo / '.git' / 'info' / 'exclude').write_text('secret/\n', encoding='utf-8')
    _write(repo, 'secret/key.py')

    kept = _walk(repo, GitIgnoreFilter(repo))

    assert 'sub/local.py' not in kept
    assert 'local.py' in kept
    assert 'secret/key.py' not in kept


def test_ignored_directory_is_pruned_whole(repo):
    _write(repo, '.gitignore', 'node_modules/\n')
    for i in range(3):
        _write(repo, f'node_modules/pkg{i}/index.js')
    flt = GitIgnoreFilter(repo)
    dirs = ['node_modules', 'src']

    flt.prune(repo, dirs)

    assert dirs == ['src']
    assert flt.skipped_dirs == 1


def test_nested_repo_answers_for_itself(repo):
    _write(repo, '.gitignore', '*.log\n')
    inner = repo / 'vendor_repo'
    inner.mkdir()
    _git(inner, 'init', '-q')
    _write(inner, '.gitignore', '*.tmp\n')
    _write(inner, 'a.log')
    _write(inner, 'b.tmp')

    flt = GitIgnoreFilter(repo)

    assert flt.ignored(inner / 'a.log') is False  # outer rule does not apply
    assert flt.ignored(inner / 'b.tmp') is True
    assert flt.modes == {'git'}


def test_scan_root_below_repo_root(repo):
    _write(repo, '.gitignore', 'pkg/generated/\n')
    _write(repo, 'pkg/generated/out.py')
    _write(repo, 'pkg/src.py')

    assert _walk(repo / 'pkg', GitIgnoreFilter(repo / 'pkg')) == ['src.py']


def test_git_failure_falls_back_to_patterns(repo, monkeypatch):
    _write(repo, '.gitignore', '*.sql\n!keep.sql\n')

    def boom(*a, **k):
        raise OSError('git not found')

    monkeypatch.setattr(gitignore.subprocess, 'run', boom)
    flt = GitIgnoreFilter(repo)

    assert flt.ignored(repo / 'drop.sql') is True
    assert flt.ignored(repo / 'keep.sql') is False
    assert flt.modes == {'patterns'}


def test_non_repo_uses_patterns(tmp_path):
    root = tmp_path / 'plain'
    _write(root, '.gitignore', 'build/\n*.pyc\n')
    _write(root, 'build/x.py')
    _write(root, 'a.pyc')
    _write(root, 'a.py')

    flt = GitIgnoreFilter(root)

    assert _walk(root, flt) == ['.gitignore', 'a.py']
    assert flt.modes == {'patterns'}


def test_opt_out_returns_none(tmp_path):
    assert gitignore_filter(tmp_path, respect_gitignore=False) is None
    assert isinstance(gitignore_filter(tmp_path), GitIgnoreFilter)


def test_is_gitignored_one_off(repo):
    _write(repo, '.gitignore', 'out/\n')
    _write(repo, 'out/a.py')

    assert is_gitignored(repo / 'out' / 'a.py') is True
    assert is_gitignored(repo / 'out', is_dir=True) is True


def test_tree_view_filter_shows_tracked_file(repo):
    """The tree view / --files filter used a second parser that hid tracked files."""
    from reveal.display.filtering import PathFilter
    _write(repo, '.gitignore', '**/env/\n')
    _write(repo, 'env/settings.py')
    _write(repo, 'build/out.py')
    (repo / '.gitignore').write_text('**/env/\nbuild/\n', encoding='utf-8')
    _git(repo, 'add', '-f', '.gitignore', 'env/settings.py')
    _git(repo, 'commit', '-q', '-m', 'init')

    pf = PathFilter(repo, respect_gitignore=True, include_defaults=False)

    assert pf.filter_reason(repo / 'env') is None
    assert pf.filter_reason(repo / 'env' / 'settings.py') is None
    assert pf.filter_reason(repo / 'build') == 'gitignore'


@pytest.mark.parametrize('resource,expected', [
    ('src', ('src', None)),
    ('src?respect_gitignore=false', ('src', False)),
    ('src?type=function&respect_gitignore=false&limit=3', ('src?type=function&limit=3', False)),
    ('src?respect_gitignore=true', ('src', True)),
    ('src?rank=callers', ('src?rank=callers', None)),
])
def test_uri_query_key_is_consumed(resource, expected):
    """handle_uri takes ?respect_gitignore= off the query: ast:// and
    markdown:// would otherwise read it as a field filter and match nothing."""
    from reveal.utils.gitignore import split_respect_gitignore
    assert split_respect_gitignore(resource) == expected


def test_no_gitignore_flag_sets_process_switch():
    from argparse import Namespace
    from reveal.cli.global_flags import apply_global_flags
    from reveal.utils.gitignore import gitignore_enabled, set_gitignore_enabled
    try:
        apply_global_flags(Namespace(respect_gitignore=False))
        assert gitignore_enabled() is False
        assert gitignore_filter('.') is None
        apply_global_flags(Namespace())  # MCP builds default args per call: resets
        assert gitignore_enabled() is True
    finally:
        set_gitignore_enabled(True)


def test_scope_restores_previous_switch():
    from reveal.utils.gitignore import gitignore_enabled, gitignore_scope
    with gitignore_scope(False):
        assert gitignore_enabled() is False
        with gitignore_scope(None):
            assert gitignore_enabled() is False
    assert gitignore_enabled() is True


def test_stats_walk_follows_switch(repo):
    from reveal.adapters.stats.analysis import find_analyzable_files
    from reveal.utils.gitignore import gitignore_scope
    _write(repo, '.gitignore', 'gen/\n')
    _write(repo, 'gen/out.py', 'x = 1\n')
    _write(repo, 'app.py', 'x = 1\n')

    def names():
        return sorted(p.relative_to(repo).as_posix() for p in find_analyzable_files(repo))

    assert names() == ['app.py']
    with gitignore_scope(False):
        assert names() == ['app.py', 'gen/out.py']


def test_stats_keeps_tracked_and_negated_files(repo):
    """The BACK-1485 regression itself, at the stats:// walker."""
    from reveal.adapters.stats.analysis import find_analyzable_files
    _write(repo, '.gitignore', '**/env/\n*.sql\n!procedures/*.sql\n')
    _write(repo, 'config/env/settings.py', 'x = 1\n')
    _write(repo, 'procedures/sp.sql', 'select 1;\n')
    _write(repo, 'dump.sql', 'select 2;\n')
    _git(repo, 'add', '-f', '.gitignore', 'config/env/settings.py')
    _git(repo, 'commit', '-q', '-m', 'init')

    names = {p.relative_to(repo).as_posix() for p in find_analyzable_files(repo)}

    assert 'config/env/settings.py' in names
    assert 'procedures/sp.sql' in names
    assert 'dump.sql' not in names


def test_grep_directory_honors_gitignore_and_exclude(repo):
    """--exclude was read by handle_grep_directory and then dropped."""
    import re
    from reveal.grep_handler import _collect_dir_results
    _write(repo, '.gitignore', 'gen/\n')
    _write(repo, 'gen/out.py', 'needle = 1\n')
    _write(repo, 'vendor/lib.py', 'needle = 2\n')
    _write(repo, 'app.py', 'needle = 3\n')

    results, _ = _collect_dir_results(repo, re.compile('needle'), None, ['vendor/*'])

    assert [Path(r['path']).name for r in results] == ['app.py']


@pytest.mark.parametrize('line', ['', '   ', '# comment', '/', '!'])
def test_blank_and_comment_lines_compile_to_nothing(line):
    assert compile_gitignore_line(line) is None


# gitignore(5) forms the fallback must agree with git on. Each entry is
# (.gitignore at root, {nested dir: .gitignore}, files to create).
_BATTERY = [
    ('*.log\n!keep.log\n', {}, ['a.log', 'keep.log', 'd/b.log', 'd/keep.log']),
    ('/root_only.py\n', {}, ['root_only.py', 'd/root_only.py']),
    ('d/x.py\n', {}, ['d/x.py', 'e/d/x.py']),
    ('build/\n', {}, ['build/a.py', 'src/build/b.py', 'build.py']),
    ('**/gen/\n', {}, ['gen/a.py', 'a/b/gen/c.py', 'gen.py']),
    ('a/**/z.py\n', {}, ['a/z.py', 'a/b/z.py', 'a/b/c/z.py', 'b/a/z.py']),
    ('logs/**\n', {}, ['logs/a.txt', 'logs/d/b.txt', 'logsx/c.txt']),
    ('file?.txt\n', {}, ['file1.txt', 'file12.txt', 'd/fileA.txt']),
    ('[ab]*.c\n', {}, ['a1.c', 'b2.c', 'c3.c', 'd/ax.c']),
    ('[!a]*.h\n', {}, ['a.h', 'b.h']),
    ('\\#hash.txt\n\\!bang.txt\n', {}, ['#hash.txt', '!bang.txt', 'plain.txt']),
    ('trailing.txt   \n', {}, ['trailing.txt']),
    ('dir/\n!dir/keep.py\n', {}, ['dir/a.py', 'dir/keep.py']),  # cannot re-include
    ('*.py\n', {'sub': '!sub_keep.py\n'}, ['a.py', 'sub/sub_keep.py', 'sub/other.py']),
    ('', {'sub': '/anchored.py\nfloat.py\n'},
     ['anchored.py', 'sub/anchored.py', 'sub/x/anchored.py', 'sub/x/float.py', 'float.py']),
    ('*\n!*/\n!*.md\n', {}, ['a.md', 'a.py', 'd/b.md', 'd/b.py']),
]


@pytest.mark.parametrize('root_ignore,nested,files', _BATTERY)
def test_pattern_fallback_agrees_with_git(repo, root_ignore, nested, files):
    if root_ignore:
        _write(repo, '.gitignore', root_ignore)
    for d, text in nested.items():
        _write(repo, f'{d}/.gitignore', text)
    for f in files:
        _write(repo, f)

    truth = set()
    for entry in _git(repo, 'ls-files', '-z', '--others', '--ignored',
                      '--exclude-standard').split('\0'):
        if entry:
            truth.add(entry)

    matcher = _PatternMatcher(str(repo))
    for f in files:
        assert matcher.ignored(f, False) == (f in truth), (
            f'{f!r}: git says {"ignored" if f in truth else "kept"} '
            f'under {root_ignore!r} {nested!r}'
        )
