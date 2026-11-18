"""git:// commit times say which zone they are in (BACK-2643).

A commit made at 2026-01-03T12:00:00Z printed as ``Date:   2026-01-03 04:00:00`` on a UTC-8 host: the
host's wall-clock time with no zone, so a reader comparing it with the commit's own metadata was off by the
host offset. The time is still the host's wall clock (the ``date`` filter reads it), now with its UTC
offset: ``2026-01-03 04:00:00 -0800``. Blame and diff commit dates carry it too.
"""
import json
import os
import subprocess
import sys

import pytest

pytestmark = [
    pytest.mark.cli,
    # TZ in the environment selects the zone of the child process only where time.tzset exists.
    pytest.mark.skipif(sys.platform == 'win32', reason='TZ selects the local zone on POSIX only'),
]

UTC_NOON = '2026-01-03T12:00:00Z'


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / 'repo'
    root.mkdir()
    env = {**os.environ, 'GIT_AUTHOR_DATE': UTC_NOON, 'GIT_COMMITTER_DATE': UTC_NOON}

    def git(*args):
        subprocess.run(['git', *args], cwd=root, check=True, capture_output=True, env=env, timeout=60)
    git('init', '-q', '.')
    (root / 'a.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    git('add', '.')
    git('-c', 'user.name=T', '-c', 'user.email=t@example.com', 'commit', '-q', '-m', 'one')
    return root


def _reveal(repo, zone, *argv):
    env = {key: value for key, value in os.environ.items() if not key.startswith('REVEAL_')}
    env.update(TZ=zone, REVEAL_DISK_CACHE='0')
    return subprocess.run([sys.executable, '-m', 'reveal', *argv], capture_output=True, text=True,
                          encoding='utf-8', env=env, cwd=repo, timeout=180)


@pytest.mark.parametrize('zone, shown', [
    ('America/Los_Angeles', '2026-01-03 04:00:00 -0800'),
    ('UTC', '2026-01-03 12:00:00 +0000'),
])
def test_history_text_and_json_carry_the_offset(repo, zone, shown):
    text = _reveal(repo, zone, 'git://.?type=history&limit=1')
    assert text.returncode == 0, text.stderr
    assert f'Date:   {shown}\n' in text.stdout
    answer = _reveal(repo, zone, 'git://.?type=history', '--format', 'json')
    assert [commit['date'] for commit in json.loads(answer.stdout)['history']] == [shown]


def test_blame_dates_carry_the_offset(repo):
    answer = _reveal(repo, 'America/Los_Angeles', 'git://a.py?type=blame', '--format', 'json')
    assert answer.returncode == 0, answer.stderr
    assert '2026-01-03 04:00:00 -0800' in answer.stdout


@pytest.mark.parametrize('query, count', [
    ('date=2026-01-03 04:00:00', 1),          # the clock part, as before
    ('date>=2026-01-03T11:00:00Z', 1),       # a zoned bound names the same instant
    ('date<=2026-01-03T11:00:00Z', 0),
    ('date=2026-01-03', 1),
])
def test_date_filters_still_read_the_clock(repo, query, count):
    answer = _reveal(repo, 'America/Los_Angeles', f'git://.?type=history&{query}', '--format', 'json')
    assert answer.returncode == 0, answer.stderr
    assert len(json.loads(answer.stdout)['history']) == count
