"""URI reader misses exit 2, the D6 code for an invalid resource (BACK-2521).

D6: exit 1 means a findings gate matched, 2 an invalid invocation or resource, 3 a
required read or analysis that failed. Plan rule 9: a target that matches nothing is
not a zero and not a finding. Before this, `sqlite://` with a missing database, a file
that is not a database or a missing table, and `env://` or `help://` naming nothing all
exited 1. An unreadable database is a failed read (3), not an invalid request.
"""

import json
import os
import sqlite3
import sys

import pytest

from conftest import _run_reveal_in


@pytest.fixture
def dbs(tmp_path):
    real = tmp_path / 'real.db'
    conn = sqlite3.connect(str(real))
    conn.execute('CREATE TABLE t (a INTEGER)')
    conn.commit()
    conn.close()
    (tmp_path / 'fake.db').write_bytes(b'this is not a sqlite database')
    return tmp_path


def _json(result):
    return json.loads(result.stdout)


@pytest.mark.parametrize('target, message', [
    ('missing.db', 'Database file not found'),
    ('fake.db', 'not a SQLite database'),
    ('real.db/nosuch', 'Table not found: nosuch'),
])
def test_sqlite_invalid_resource_exits_2(dbs, target, message):
    result = _run_reveal_in(dbs, f'sqlite://{(dbs / target).as_posix()}', '--format', 'json')
    assert result.returncode == 2, result.stderr
    answer = _json(result)
    assert message in answer['error']
    assert [e['code'] for e in answer['meta']['errors']] == ['invalid_request']


def test_sqlite_text_names_the_problem_once(dbs):
    result = _run_reveal_in(dbs, f'sqlite://{(dbs / "real.db/nosuch").as_posix()}')
    assert result.returncode == 2
    assert result.stderr.count('Table not found: nosuch') == 1


@pytest.mark.skipif(sys.platform == 'win32' or not hasattr(os, 'getuid') or os.getuid() == 0,
                    reason='file permissions cannot make a file unreadable here')
def test_sqlite_unreadable_database_is_a_failed_read_exit_3(dbs):
    path = dbs / 'real.db'
    os.chmod(path, 0)
    try:
        result = _run_reveal_in(dbs, f'sqlite://{path.as_posix()}', '--format', 'json')
    finally:
        os.chmod(path, 0o600)
    assert result.returncode == 3, result.stderr
    assert 'not readable' in _json(result)['error']


def test_sqlite_present_database_and_table_still_exit_0(dbs):
    overview = _run_reveal_in(dbs, f'sqlite://{(dbs / "real.db").as_posix()}', '--format', 'json')
    table = _run_reveal_in(dbs, f'sqlite://{(dbs / "real.db/t").as_posix()}', '--format', 'json')
    assert (overview.returncode, table.returncode) == (0, 0), (overview.stderr, table.stderr)
    assert _json(overview)['type'] == 'sqlite_database'
    assert [table['name'] for table in _json(overview)['tables']] == ['t']
    assert (_json(table)['type'], _json(table)['table']) == ('sqlite_table', 't')


def test_sqlite_check_keeps_its_own_exit_convention(dbs):
    """--check is a gate with its own 0/1/2 (integrity) codes; a missing table there is unchanged."""
    result = _run_reveal_in(dbs, f'sqlite://{(dbs / "real.db").as_posix()}', '--check')
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('argv', [('env://NO_SUCH_VAR_BACK2521',), ('env://', 'NO_SUCH_VAR_BACK2521')])
def test_env_missing_variable_exits_2(tmp_path, argv):
    result = _run_reveal_in(tmp_path, *argv, '--format', 'json')
    assert result.returncode == 2, result.stderr
    answer = _json(result)
    assert answer['error'] == "Element 'NO_SUCH_VAR_BACK2521' not found"
    assert [e['code'] for e in answer['meta']['errors']] == ['element_not_found']


def test_env_present_variable_still_exits_0(tmp_path):
    result = _run_reveal_in(tmp_path, 'env://HOME' if sys.platform != 'win32' else 'env://PATH')
    assert result.returncode == 0, result.stderr


def test_help_unknown_topic_exits_2_and_keeps_its_way_back(tmp_path):
    result = _run_reveal_in(tmp_path, 'help://no_such_topic_back2521')
    assert result.returncode == 2, result.stderr
    assert "Element 'no_such_topic_back2521' not found" in result.stderr
    assert 'help://quick' in result.stderr


def test_mcp_reports_the_miss_with_its_message(dbs):
    from reveal import mcp_server
    for uri, message in [('env://NO_SUCH_VAR_BACK2521', "Element 'NO_SUCH_VAR_BACK2521' not found"),
                         (f'sqlite://{(dbs / "real.db/nosuch").as_posix()}', 'Table not found: nosuch')]:
        answer = mcp_server.reveal_query(uri)
        assert getattr(answer, 'public', None) is True, answer
        assert message in str(answer)
