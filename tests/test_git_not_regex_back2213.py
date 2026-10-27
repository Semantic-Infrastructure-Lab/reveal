"""git:// `field!~pattern` filters instead of keeping everything (BACK-2213 V3).

The URI parser leaves `email!~@company.com` as a bare key (there is no '='), and the adapter
rebuilt every filter as `key=value`, so the pattern became `@company.com=True` and never matched.
"""
import os
import subprocess

import pytest

from reveal.adapters.git.adapter import GitAdapter


@pytest.fixture()
def repo(tmp_path):
    def git(*args, env=None):
        subprocess.run(['git', *args], cwd=tmp_path, check=True, capture_output=True, env=env)
    git('init', '-q', '.')
    for i, (name, email, msg) in enumerate([('John Smith', 'john@company.com', 'feat: one'),
                                            ('John Smith', 'john@company.com', 'feat: two'),
                                            ('ext Person', 'ext@other.org', 'Bug fix')]):
        (tmp_path / f'f{i}').write_text(str(i), encoding='utf-8')
        git('add', '.')
        git('-c', f'user.name={name}', '-c', f'user.email={email}', 'commit', '-q', '-m', msg)
    return tmp_path


def _emails(repo, query):
    history = GitAdapter(f'{repo}?type=log&{query}').get_structure()['history']
    return sorted(c['email'] for c in history)


def test_not_regex_excludes_matching_commits(repo):
    assert _emails(repo, 'email!~@company.com') == ['ext@other.org']


def test_not_regex_on_message(repo):
    assert _emails(repo, 'message!~feat') == ['ext@other.org']


def test_regex_control_still_matches(repo):
    assert _emails(repo, 'email~=@company.com') == ['john@company.com', 'john@company.com']


def test_metrics_not_regex_filters_files(tmp_path):
    from reveal.adapters.stats.adapter import StatsAdapter
    for name in ('keep_me.py', 'drop_me.py'):
        (tmp_path / name).write_text('def f():\n    return 1\n', encoding='utf-8')
    files = StatsAdapter(str(tmp_path), 'file!~drop').get_structure().get('files', [])
    names = sorted(os.path.basename(f['file']) for f in files)
    assert names == ['keep_me.py']
