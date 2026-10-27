"""git:// date bounds: a bare `?date>D` is a filter, and a date-only bound covers whole days (BACK-2277).

`git://.?date>D` with no other parameter has no '=', so the router handed the query string to
GitAdapter's second positional parameter, which was `ref`: "Invalid ref: date>D". With another
parameter it reached the filters, but rebuilt as `date>D=True`, so `date>D` excluded the commits
of day D only by a lexical accident ('2026-02-01 12:00:00' < '2026-02-01=True').

The semantics of a date-only bound: `date>D` is after the END of day D, `date<D` before the START
of day D, and `date>=D`/`date<=D` (and the range `D1..D2`) include the whole day. A full timestamp
bound compares the timestamp as before.
"""
import json
import os
import subprocess

import pytest

from reveal.adapters.factory import _canonical_init
from reveal.adapters.git.adapter import GitAdapter

from conftest import _run_reveal_direct

_COMMITS = [('a', '2026-01-31 12:00:00'), ('b', '2026-02-01 12:00:00'), ('c', '2026-02-02 12:00:00')]


@pytest.fixture()
def repo(tmp_path):
    def git(*args, env=None):
        subprocess.run(['git', *args], cwd=tmp_path, check=True, capture_output=True, env=env, timeout=60)
    git('init', '-q', '.')
    for msg, when in _COMMITS:
        (tmp_path / msg).write_text(msg, encoding='utf-8')
        git('add', '.')
        # No zone in the date: git reads it as local time and reveal formats commit_time in local
        # time, so the commit shows as `when` on any machine (noon keeps clear of DST edges).
        env = {**os.environ, 'GIT_AUTHOR_DATE': when, 'GIT_COMMITTER_DATE': when}
        git('-c', 'user.name=T', '-c', 'user.email=t@example.com', 'commit', '-q', '-m', msg, env=env)
    return tmp_path


def _messages(repo, query):
    history = GitAdapter(f'{repo}?type=log&{query}').get_structure()['history']
    return sorted(c['message'].strip() for c in history)


def test_fixture_dates_are_what_the_test_assumes(repo):
    # Control for every case below: the commits show the dates the bounds are written against.
    history = GitAdapter(f'{repo}?type=log').get_structure()['history']
    assert sorted(c['date'] for c in history) == [when for _, when in _COMMITS]


def test_bare_bound_alone_is_a_filter_not_a_ref(repo, monkeypatch):
    monkeypatch.chdir(repo)
    result = _run_reveal_direct('git://.?date>2026-02-01', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert 'Invalid ref' not in result.stderr
    recent = json.loads(result.stdout)['commits']['recent']
    assert [c['message'].strip() for c in recent] == ['c']


def test_router_constructor_takes_the_query_not_a_ref(repo):
    # factory._canonical_init is the router's path: adapter_class(path, query_string).
    adapter = _canonical_init(GitAdapter, f'{repo}?date<2026-02-01')
    assert adapter.ref == 'HEAD'
    assert [(f.field, f.op, f.value) for f in adapter.query_filters] == [('date', '<', '2026-02-01')]


@pytest.mark.parametrize('query, expected', [
    ('date>2026-02-01', ['c']),           # after the end of day D: D excluded (as before)
    ('date<2026-02-01', ['a']),           # before the start of day D
    ('date>=2026-02-01', ['b', 'c']),     # whole day D included
    ('date<=2026-02-01', ['a', 'b']),     # whole day D included (was: D excluded)
    ('until=2026-02-01', ['a', 'b']),     # the date<= alias (was: D excluded)
    ('since=2026-02-01', ['b', 'c']),     # the date>= alias
    ('date=2026-02-01..2026-02-01', ['b']),       # a range of whole days (was: [])
    ('date=2026-01-31..2026-02-01', ['a', 'b']),  # (was: ['a'])
])
def test_date_only_bounds_cover_whole_days(repo, query, expected):
    assert _messages(repo, query) == expected


@pytest.mark.parametrize('query, expected', [
    ('date>2026-02-01 11:59:59', ['b', 'c']),
    ('date>2026-02-01 12:00:00', ['c']),
    ('date>=2026-02-01 12:00:00', ['b', 'c']),
    ('date<2026-02-01 12:00:00', ['a']),
    ('date<=2026-02-01 12:00:00', ['a', 'b']),
])
def test_full_timestamp_bounds_compare_the_timestamp(repo, query, expected):
    assert _messages(repo, query) == expected


def test_bound_with_another_filter_still_works(repo):
    assert _messages(repo, 'author~=T&date>2026-01-31') == ['b', 'c']
    assert _messages(repo, 'message~=^(a|c)$&date>=2026-02-01') == ['c']


def test_metrics_bound_params_still_rebuild_bare_filters(tmp_path):
    # Sibling consumer of the shared bare-key rebuild: a bound metrics:// request.
    from reveal.adapters.stats.adapter import StatsAdapter
    from reveal.utils.query_parser import parse_query_params
    (tmp_path / 'small.py').write_text('x = 1\n', encoding='utf-8')
    (tmp_path / 'big.py').write_text(''.join(f'x{i} = {i}\n' for i in range(20)), encoding='utf-8')
    adapter = StatsAdapter(str(tmp_path), params=parse_query_params('lines>5'))
    files = adapter.get_structure().get('files', [])
    assert sorted(f['file'].replace('\\', '/').rsplit('/', 1)[-1] for f in files) == ['big.py']
