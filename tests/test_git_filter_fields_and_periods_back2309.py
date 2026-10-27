"""git:// unknown filter fields warn; date equality, years and zoned timestamps (BACK-2309).

A key that carries an operator (``authr~=Scott``) skips the BACK-909 unknown-param check, so a
typo'd field compared None on every commit and the answer was 0 commits, silently. It now
carries an ``unknown_filter_field`` entry in ``meta.warnings``, the shape metrics:// and json://
use; the known fields are those of the commit record the filters read.

BACK-2277/2300 made a day or month bound name the whole period for ``>``/``<``/``>=``/``<=``
and ranges. Equality still compared the full timestamp (``date=2026-01-15`` matched nothing), and
a year bound (``date>2026``) compared as text, so ``date>2025`` kept 2025 and ``date<=2026``
lost 2026. A year, month or day now names the whole period for every operator.

The commit ``date`` is written in the local time of the machine running reveal, with no zone. A
timestamp bound with a zone (``Z``, ``+02:00``, ``-1200``) compared its wall-clock digits with
that local time; it is now converted to local time first, so it names the same instant.
"""
import json
import os
import subprocess

import pytest

from reveal.adapters.git.adapter import GitAdapter

from conftest import _run_reveal_direct

_COMMITS = [('a', '2025-12-31 12:00:00'), ('b', '2026-01-15 12:00:00'),
            ('c', '2026-01-31 12:00:00'), ('d', '2026-02-01 12:00:00')]

# 2026-01-15 11:00, 12:00 and 13:00 UTC, as epoch seconds with an explicit zone: the same
# instants on every machine, whatever its local zone (mid-January, clear of DST changes).
_NOON_UTC = 1768478400
_INSTANTS = [('x', _NOON_UTC - 3600), ('y', _NOON_UTC), ('z', _NOON_UTC + 3600)]


def _make_repo(path, commits):
    def git(*args, env=None):
        subprocess.run(['git', *args], cwd=path, check=True, capture_output=True, env=env, timeout=60)
    git('init', '-q', '.')
    for msg, when in commits:
        (path / msg).write_text(msg, encoding='utf-8')
        git('add', '.')
        env = {**os.environ, 'GIT_AUTHOR_DATE': when, 'GIT_COMMITTER_DATE': when}
        git('-c', 'user.name=T', '-c', 'user.email=t@example.com', 'commit', '-q', '-m', msg, env=env)
    return path


@pytest.fixture()
def repo(tmp_path):
    # No zone: git reads local time and reveal formats commit_time in local time (BACK-2277).
    return _make_repo(tmp_path, _COMMITS)


@pytest.fixture()
def utc_repo(tmp_path):
    return _make_repo(tmp_path, [(msg, f'@{epoch} +0000') for msg, epoch in _INSTANTS])


def _messages(repo, query):
    history = GitAdapter(str(repo), f'type=log&{query}').get_structure()['history']
    return sorted(c['message'].strip() for c in history)


def _router(repo, monkeypatch, uri, *args):
    monkeypatch.chdir(repo)
    result = _run_reveal_direct(uri, *args)
    assert result.returncode == 0, result.stderr
    return result


def _unknown(result):
    return [w for w in (result.get('meta') or {}).get('warnings', []) if w.get('type') == 'unknown_filter_field']


def test_fixture_dates_are_what_the_test_assumes(repo):
    history = GitAdapter(str(repo), 'type=log').get_structure()['history']
    assert sorted(c['date'] for c in history) == [when for _, when in _COMMITS]


# An unknown field with an operator warns.

@pytest.mark.parametrize('query, expected', [
    ('authr~=T', []),
    ('authr>a', []),
    ('authr!=T', ['a', 'b', 'c', 'd']),   # != matches a missing value: every commit, still a typo
])
def test_an_unknown_field_with_an_operator_warns(repo, query, expected):
    result = GitAdapter(str(repo), f'type=log&{query}').get_structure()
    assert sorted(c['message'].strip() for c in result['history']) == expected
    [warning] = _unknown(result)
    assert "'authr'" in warning['message'] and 'author' in warning['message']


def test_the_repository_overview_warns(repo, monkeypatch):
    result = _router(repo, monkeypatch, 'git://.?authr~=T', '--format', 'json')
    data = json.loads(result.stdout)
    assert data['commits']['recent'] == []
    [warning] = _unknown(data)
    assert "'authr'" in warning['message']


def test_file_history_warns(repo, monkeypatch):
    result = _router(repo, monkeypatch, 'git://b?type=history&authr~=T', '--format', 'json')
    assert len(_unknown(json.loads(result.stdout))) == 1


def test_only_the_unknown_field_is_named(repo):
    [warning] = _unknown(GitAdapter(str(repo), 'type=log&author~=T&mesage~=b').get_structure())
    assert "'mesage'" in warning['message'] and "'author'" not in warning['message']


def test_the_text_output_shows_the_warning_once(repo, monkeypatch):
    result = _router(repo, monkeypatch, 'git://.?authr~=T')
    assert result.stdout.count("'authr'") == 1


@pytest.mark.parametrize('query', [
    'author~=T', 'email~=example', 'message~=a', 'hash~=^[0-9a-f]', 'date>2020-01-01',
    'timestamp>0',       # a field of every commit record, though the schema does not list it
    'since=2026-01-01',  # rewritten to date>=
    '!authr',            # absent: matches every commit, not a typo's zero
])
def test_a_known_field_or_an_absence_filter_does_not_warn(repo, query):
    assert _unknown(GitAdapter(str(repo), f'type=log&{query}').get_structure()) == []


def test_a_bare_unknown_key_keeps_its_one_warning(repo, capsys):
    # BACK-909 already says "Unknown query param" for a key with no operator; not twice.
    result = GitAdapter(str(repo), 'type=log&authr').get_structure()
    assert _unknown(result) == []
    assert "Unknown query param 'authr'" in capsys.readouterr().err


def test_the_known_fields_are_the_commit_record_fields(repo):
    import pygit2
    from reveal.adapters.git.commits import COMMIT_FIELDS, format_commit
    commit = pygit2.Repository(str(repo)).head.peel()
    assert tuple(format_commit(commit)) == COMMIT_FIELDS


# A year, month or day names the whole period, for equality too.

@pytest.mark.parametrize('query, expected', [
    ('date=2026-01-15', ['b']),         # was: [] (the full timestamp compared)
    ('date=2026-01', ['b', 'c']),
    ('date=2026', ['b', 'c', 'd']),
    ('date=2025', ['a']),
    ('date!=2026-01', ['a', 'd']),
    ('date!=2026-01-15', ['a', 'c', 'd']),
    ('date>2026', []),                  # after the end of 2026 (was: b, c, d)
    ('date>2025', ['b', 'c', 'd']),     # (was: a, b, c, d)
    ('date<2026', ['a']),
    ('date>=2026', ['b', 'c', 'd']),
    ('date<=2026', ['a', 'b', 'c', 'd']),  # (was: a)
    ('date<=2025', ['a']),
    ('date=2026..2026', ['b', 'c', 'd']),
    ('date=2025..2025', ['a']),
    ('until=2025', ['a']),
    ('since=2026', ['b', 'c', 'd']),
])
def test_a_period_bound_names_the_whole_period(repo, query, expected):
    assert _messages(repo, query) == expected


@pytest.mark.parametrize('query, expected', [
    # Controls: a timestamp equality is exact, regex is untouched, and BACK-2277/2300 bounds hold.
    ('date=2026-01-15 12:00:00', ['b']),
    ('date=2026-01-15T12:00:00', ['b']),
    ('date=2026-01-15 12:00:01', []),
    ('date~=^2026-01', ['b', 'c']),
    ('date>2026-01', ['d']),
    ('date<=2026-01-31', ['a', 'b', 'c']),
    ('date>2026-01-31 11:59:59', ['c', 'd']),
])
def test_timestamp_and_regex_controls(repo, query, expected):
    assert _messages(repo, query) == expected


def test_a_year_through_the_router(repo, monkeypatch):
    result = _router(repo, monkeypatch, 'git://.?date=2025', '--format', 'json')
    assert [c['message'].strip() for c in json.loads(result.stdout)['commits']['recent']] == ['a']


# A zoned timestamp names an instant.

def test_utc_fixture_is_three_consecutive_hours(utc_repo):
    history = GitAdapter(str(utc_repo), 'type=log').get_structure()['history']
    assert sorted(c['timestamp'] for c in history) == [epoch for _, epoch in _INSTANTS]


@pytest.mark.parametrize('bound', [
    '2026-01-15T12:30:00Z', '2026-01-15T12:30:00z', '2026-01-15 12:30:00Z',
    '2026-01-15T14:30:00+02:00', '2026-01-15T14:30:00+0200', '2026-01-15T00:30:00-12:00',
    '2026-01-16T02:30:00+14:00', '2026-01-15T12:30Z',
])
def test_a_zoned_bound_is_the_same_instant_in_every_spelling(utc_repo, bound):
    assert _messages(utc_repo, f'date>{bound}') == ['z']
    assert _messages(utc_repo, f'date<{bound}') == ['x', 'y']


@pytest.mark.parametrize('query, expected', [
    ('date=2026-01-15T12:00:00Z', ['y']),
    ('date!=2026-01-15T12:00:00Z', ['x', 'z']),
    ('date>=2026-01-15T12:00:00Z', ['y', 'z']),
    ('date<=2026-01-15T14:00:00+02:00', ['x', 'y']),
    ('date=2026-01-15T11:30:00Z..2026-01-15T12:30:00Z', ['y']),
    ('since=2026-01-15T12:00:00Z', ['y', 'z']),
])
def test_zoned_equality_and_ranges(utc_repo, query, expected):
    assert _messages(utc_repo, query) == expected


@pytest.mark.parametrize('bound', ['2026-01-15T14:30:00+02:00', '2026-01-15T12:30:00Z'])
def test_a_zoned_bound_through_the_router(utc_repo, monkeypatch, bound):
    # git:// query values are not percent-decoded, so '+' is written as itself.
    result = _router(utc_repo, monkeypatch, f'git://.?date>{bound}', '--format', 'json')
    assert [c['message'].strip() for c in json.loads(result.stdout)['commits']['recent']] == ['z']


def test_a_zoned_bound_that_is_not_a_time_fails_the_query(utc_repo):
    with pytest.raises(ValueError, match='2026-13-15'):
        _messages(utc_repo, 'date>2026-13-15T12:00:00Z')
