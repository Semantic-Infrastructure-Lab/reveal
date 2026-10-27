"""BACK-2241: mysql://HOST/health recursed forever; --check on an unreachable server exited 1.

`/health` -> get_element -> _get_health -> get_structure -> get_element (element still set)
raised RecursionError. And a server that could not be reached came back as a plain adapter
error (exit 1), the same code the guide gives to "warnings", so a CI gate that tolerates
warnings passed a dead database.
"""
import json
import os
import site
import subprocess
import sys

import pytest

pytest.importorskip('pymysql')

from reveal.adapters.mysql.adapter import MySQLAdapter  # noqa: E402


def _bare_adapter(element):
    adapter = MySQLAdapter.__new__(MySQLAdapter)
    adapter.element = element
    return adapter


def test_health_element_returns_the_overview_instead_of_recursing(monkeypatch):
    adapter = _bare_adapter('health')
    monkeypatch.setattr(adapter, '_build_overview', lambda: {'type': 'mysql_server'})
    assert adapter.get_structure() == {'type': 'mysql_server'}
    assert adapter.get_element('health') == {'type': 'mysql_server'}


def test_unrecognised_element_still_falls_through_to_the_overview(monkeypatch):
    adapter = _bare_adapter('no-such-element')
    monkeypatch.setattr(adapter, '_build_overview', lambda: {'type': 'mysql_server'})
    assert adapter.get_structure() == {'type': 'mysql_server'}


def _reveal(tmp_path, *args):
    # An empty HOME keeps a real ~/.my.cnf out of the picture; .invalid never resolves (RFC 2606).
    # The user site is derived from HOME, so pin it (BACK-2292): an interpreter whose pymysql lives
    # in ~/.local passed the importorskip above and then lost pymysql in the child. The empty HOME
    # also empties the update-check cache, so without the opt-out every run asked PyPI and a
    # version notice could land on stdout ahead of the JSON.
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path), PYTHONIOENCODING='utf-8',
               PYTHONUSERBASE=site.getuserbase(), REVEAL_NO_UPDATE_CHECK='1')
    for key in [k for k in env if k.startswith('MYSQL_')]:
        del env[key]
    return subprocess.run([sys.executable, '-m', 'reveal', *args], capture_output=True,
                          text=True, encoding='utf-8', timeout=120, env=env)


def test_check_on_an_unreachable_server_is_a_failure_with_exit_2(tmp_path):
    r = _reveal(tmp_path, 'mysql://no-such-host.invalid', '--check', '--format=json')
    assert r.returncode == 2, (r.stdout, r.stderr)
    data = json.loads(r.stdout)
    assert data['status'] == 'failure' and data['exit_code'] == 2
    assert 'no-such-host.invalid' in data['error']
    assert data['summary']['total'] == 0


def test_check_text_on_an_unreachable_server_says_why(tmp_path):
    r = _reveal(tmp_path, 'mysql://no-such-host.invalid', '--check')
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert 'FAILURE' in r.stdout and 'Failed to connect to MySQL' in r.stdout
    assert 'Traceback' not in r.stderr


def test_health_element_on_an_unreachable_server_fails_on_the_connection_not_on_recursion(tmp_path):
    r = _reveal(tmp_path, 'mysql://no-such-host.invalid/health')
    assert r.returncode != 0
    assert 'recursion' not in (r.stderr + r.stdout).lower()
    assert 'Failed to connect to MySQL' in r.stderr + r.stdout
