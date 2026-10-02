"""BACK-1614: a getfacl that times out or can't run is "not checked", not "no grant"."""

import subprocess

from reveal.analyzers import nginx


def test_getfacl_timeout_is_not_checked(monkeypatch):
    monkeypatch.setattr(nginx.shutil, 'which', lambda _: '/usr/bin/getfacl')

    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd='getfacl', timeout=3)

    monkeypatch.setattr(nginx.subprocess, 'run', _timeout)
    assert nginx._acl_grants_nobody('/srv/www', 'r') is None


def test_getfacl_with_no_grant_is_false(monkeypatch):
    monkeypatch.setattr(nginx.shutil, 'which', lambda _: '/usr/bin/getfacl')
    monkeypatch.setattr(nginx.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(
        a, 0, stdout='user::rwx\ngroup::r-x\nother::---\n', stderr=''))
    assert nginx._acl_grants_nobody('/srv/www', 'r') is False
