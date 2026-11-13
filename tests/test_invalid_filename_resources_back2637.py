"""Windows-invalid literals cannot produce a clean or prefix-selected answer."""
import errno
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_in
from codex_session_fixture import DOC_SESSION_ID
from test_codex_declared_api_back2618 import codex


@pytest.mark.parametrize('character', list('<>:"|?*'))
@pytest.mark.parametrize('noun', ['json', 'markdown'])
@pytest.mark.parametrize('transport', ['typed', 'uri'])
@pytest.mark.parametrize('winerror,exit_code', [(123, 2), (5, 3), (None, 3)])
def test_windows_rejected_literal_is_reported_without_prefix_fallback(tmp_path, monkeypatch, noun, character, transport, winerror, exit_code):
    # Run the Windows metadata failure on Linux too, without changing os.name.
    target = tmp_path / ('invalid' + character + 'name.json')
    (tmp_path / 'invalid').mkdir()
    (tmp_path / 'invalid.json').write_text('{"wrong": true}', encoding='utf-8')
    original = Path.stat
    def stat(path, *args, **kwargs):
        if path == target:
            error = OSError(errno.EACCES if winerror == 5 else errno.EINVAL, 'resource metadata rejected')
            error.winerror = winerror
            raise error
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', stat)
    from urllib.parse import quote
    argv = (noun, str(target)) if transport == 'typed' else (noun + '://' + quote(target.as_posix(), safe='/:'),)
    run = _run_reveal_in(tmp_path, *argv, '--format', 'json')
    # WinError123 identifies an invalid requested resource, not failed analysis.
    assert run.returncode == exit_code, (run.stdout, run.stderr)
    answer = json.loads(run.stdout)
    assert answer['error']
    errors = answer['meta']['errors']
    assert errors
    assert (errors[0]['code'] == 'invalid_request') == (exit_code == 2)
    assert 'Traceback' not in run.stderr


def test_windows_rejected_database_keeps_failed_metadata_receipt(codex, monkeypatch):
    from reveal.adapters.codex.adapter import CodexAdapter
    from reveal import query
    target = codex / 'invalid?state.sqlite'
    monkeypatch.setattr(CodexAdapter, 'CODEX_DB', target)
    original = Path.stat
    def stat(path, *args, **kwargs):
        if path == target:
            error = OSError(errno.EINVAL, 'Windows invalid filename')
            error.winerror = 123
            raise error
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', stat)
    answer = query('codex://' + DOC_SESSION_ID)
    proof = answer['meta']['session_lookup']
    assert proof['decision'] == 'failed'
    assert proof['failures'][0]['phase'] == 'metadata'
    assert proof['source_present'] is None
    assert answer['error']
