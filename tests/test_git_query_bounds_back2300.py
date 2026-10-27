"""git:// bare ``?author`` is a presence filter; month and T-separated date bounds (BACK-2300).

A key with no operator parses as the presence filter ``?field`` (``parse_query_filters``), which
json://, ast:// and markdown:// answer through ``presence_matches``. git:// handed ``?`` to
``compare_values``, which matched nothing, so ``git://.?author`` listed no commits.

BACK-2277 made a ``YYYY-MM-DD`` bound name the whole day. A ``YYYY-MM`` bound was still compared
as a string with '2026-01-15 12:00:00', which sorts after '2026-01': ``date>2026-01`` included
January and ``date<=2026-01`` lost it. A month bound now names the whole month. A timestamp
written with 'T' compared 'T' with the commit's space (' ' < 'T'), so
``date>2026-01-31T11:59:59`` lost the commit at 12:00:00 that day; it now compares as the
space-separated timestamp.
"""
import json
import os
import subprocess

import pytest

from reveal.adapters.git.adapter import GitAdapter

from conftest import _run_reveal_direct

_COMMITS = [('a', '2025-12-31 12:00:00'), ('b', '2026-01-15 12:00:00'),
            ('c', '2026-01-31 12:00:00'), ('d', '2026-02-01 12:00:00')]


@pytest.fixture()
def repo(tmp_path):
    def git(*args, env=None):
        subprocess.run(['git', *args], cwd=tmp_path, check=True, capture_output=True, env=env, timeout=60)
    git('init', '-q', '.')
    for msg, when in _COMMITS:
        (tmp_path / msg).write_text(msg, encoding='utf-8')
        git('add', '.')
        # No zone: git reads local time and reveal formats commit_time in local time (BACK-2277).
        env = {**os.environ, 'GIT_AUTHOR_DATE': when, 'GIT_COMMITTER_DATE': when}
        git('-c', 'user.name=T', '-c', 'user.email=t@example.com', 'commit', '-q', '-m', msg, env=env)
    return tmp_path


def _messages(repo, query):
    history = GitAdapter(f'{repo}?type=log&{query}').get_structure()['history']
    return sorted(c['message'].strip() for c in history)


def test_fixture_dates_are_what_the_test_assumes(repo):
    history = GitAdapter(f'{repo}?type=log').get_structure()['history']
    assert sorted(c['date'] for c in history) == [when for _, when in _COMMITS]


# Bare key: presence.

def test_bare_author_is_a_presence_filter(repo):
    assert _messages(repo, 'author') == ['a', 'b', 'c', 'd']


def test_bare_author_alone_through_the_router(repo, monkeypatch):
    monkeypatch.chdir(repo)
    result = _run_reveal_direct('git://.?author', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert sorted(c['message'].strip() for c in json.loads(result.stdout)['commits']['recent']) == ['a', 'b', 'c', 'd']


def test_bare_presence_beside_a_value_filter(repo):
    assert _messages(repo, 'email&message~=^[bc]$') == ['b', 'c']


def test_negated_presence_and_an_unknown_bare_key_still_match_nothing(repo, capsys):
    # Controls: `!author` (absent) and a bare key no commit has stay empty, and the typo still warns.
    assert _messages(repo, '!author') == []
    assert _messages(repo, 'authr') == []
    assert "Unknown query param 'authr'" in capsys.readouterr().err


# Month bounds name the whole month.

@pytest.mark.parametrize('query, expected', [
    ('date>2026-01', ['d']),                    # after the end of January (was: b, c, d)
    ('date<2026-01', ['a']),                    # before its start
    ('date>=2026-01', ['b', 'c', 'd']),         # January included
    ('date<=2026-01', ['a', 'b', 'c']),         # January included (was: a)
    ('since=2026-01', ['b', 'c', 'd']),
    ('until=2026-01', ['a', 'b', 'c']),         # (was: a)
    ('date=2026-01..2026-01', ['b', 'c']),      # a range of whole months (was: [])
    ('date=2025-12..2026-01-15', ['a', 'b']),   # each end at its own precision
])
def test_month_bounds_cover_whole_months(repo, query, expected):
    assert _messages(repo, query) == expected


# A 'T' between date and time compares like the space.

@pytest.mark.parametrize('query, expected', [
    ('date>2026-01-31T11:59:59', ['c', 'd']),   # (was: d)
    ('date>2026-01-31T12:00:00', ['d']),
    ('date>=2026-01-31T12:00:00', ['c', 'd']),  # (was: d)
    ('date<2026-01-31T12:00:00', ['a', 'b']),    # (was: a, b, c)
    ('date<=2026-01-31T12:00:00', ['a', 'b', 'c']),
    ('date=2026-01-15T12:00:00..2026-01-31T12:00:00', ['b', 'c']),  # (was: b)
])
def test_t_separated_timestamps_compare_like_the_space_form(repo, query, expected):
    assert _messages(repo, query) == expected
    assert _messages(repo, query.replace('T', ' ')) == expected


# Negative controls: what BACK-2277 settled does not move.

@pytest.mark.parametrize('query, expected', [
    ('date>2026-01-31', ['d']),
    ('date<=2026-01-31', ['a', 'b', 'c']),
    ('date=2026-01-15..2026-01-31', ['b', 'c']),
    ('date>2026-01-31 11:59:59', ['c', 'd']),
    ('author~=T&date>2026-01-15', ['c', 'd']),
])
def test_day_and_space_timestamp_bounds_are_unchanged(repo, query, expected):
    assert _messages(repo, query) == expected
