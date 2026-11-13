"""Byte acquisition must avoid Windows text-reader loss and locale-dependent decoding."""
import json
import locale
import subprocess

import pytest

from conftest import _run_reveal_in
from test_declared_git_back2616 import commit_bytes
from test_git_declared_api_back2616 import repo_path  # noqa: F401
from test_mcp_expected_errors_back1992 import _run, _text


WINDOWS_READER = '''
import subprocess, locale
locale.getencoding = lambda: 'cp1252'
locale.getpreferredencoding = lambda *args: 'cp1252'
_real_run = subprocess.run

def windows_run(command, *args, **kwargs):
    if command[0] == 'git' and 'diff' in command and kwargs.get('text'):
        raw_kwargs = {k: v for k, v in kwargs.items() if k not in ('text', 'encoding', 'errors')}
        raw = _real_run(command, *args, **raw_kwargs)
        try:
            text = raw.stdout.decode(kwargs.get('encoding') or locale.getencoding())
        except UnicodeDecodeError:
            # Windows subprocess reader threads lose stdout on strict decode failure.
            text = None
        return subprocess.CompletedProcess(command, raw.returncode, text, '')
    return _real_run(command, *args, **kwargs)
subprocess.run = windows_run
'''


@pytest.fixture
def windows_reader(monkeypatch):
    # Record restorations before executing the same simulation used by the MCP child.
    monkeypatch.setattr(subprocess, 'run', subprocess.run)
    monkeypatch.setattr(locale, 'getencoding', locale.getencoding)
    monkeypatch.setattr(locale, 'getpreferredencoding', locale.getpreferredencoding)
    exec(WINDOWS_READER, {})


def test_windows_reader_retains_known_history_and_declares_loss(repo_path, windows_reader):
    commit_bytes(repo_path, b'def answer():\n    return 3\n# \xff\n')
    result = _run_reveal_in(repo_path, f'git://{repo_path}/code.py?view=history&where=content~%3Dreturn', '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['commits'][0]['message'] == 'damaged source'
    assert any(w.get('code') == 'analysis_incomplete' for w in answer['meta']['warnings'])
    fresh = _run_reveal_in(repo_path, f'git://{repo_path}?view=history&limit=1', '--format', 'json')
    assert fresh.returncode == 0


def test_git_search_is_utf8_under_non_utf8_locale(repo_path, windows_reader):
    from reveal.api import query
    commit_bytes(repo_path, '# café\ndef answer(): return 2\n'.encode('utf-8'))
    result = query(f'git://{repo_path}/code.py?view=history', where=['content~=café'])
    assert [row['message'] for row in result['commits']] == ['damaged source']
    assert result['meta']['warnings'] == []


@pytest.mark.mcp
@pytest.mark.component
def test_mcp_windows_reader_returns_partial_answer_not_internal_error(repo_path):
    commit_bytes(repo_path, b'def answer():\n    return 3\n# \xff\n')
    async def scenario(session):
        result = await session.call_tool('reveal_query', {
            'uri': f'git://{repo_path}/code.py?view=history&where=content~%3Dreturn', 'provenance': True})
        assert not result.is_error, _text(result)
        answer = json.loads(_text(result))
        assert answer['commits'][0]['message'] == 'damaged source'
        assert any(w.get('code') == 'analysis_incomplete' for w in answer['meta']['warnings'])
    _run(repo_path, scenario, code=WINDOWS_READER + '\nfrom reveal import mcp_server\nmcp_server.main()\n')


def test_windows_diff_keeps_recovered_text_and_declares_loss(repo_path, windows_reader):
    commit_bytes(repo_path, b'def answer():\n    return 3\n# \xff\n')
    result = _run_reveal_in(repo_path, f'git://{repo_path}/code.py?view=diff', '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert '+    return 3' in answer['diff_text']
    assert answer['meta']['blob_text'] == {'encoding': 'utf-8', 'decoding_loss': True}
