"""The update-available notice goes to stderr, so a machine answer on stdout stays parseable (BACK-2738).

``check_for_updates()`` runs before every answer, whatever ``--format``. Once a day a user behind PyPI got
the two notice lines on stdout in front of the JSON. Here the installed version is stale, the daily cache is
missing (so the check runs) and the PyPI read is a stub: no network.
"""
import io
import json
import urllib.request

import pytest

from conftest import _run_reveal_direct

NOTICE = 'Update available: reveal 999.0.0'


class _PyPIResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


@pytest.fixture
def stale_install(tmp_path, monkeypatch):
    from reveal import config, version
    from reveal.utils import updates

    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append(request.full_url)
        return _PyPIResponse(json.dumps({'info': {'version': '999.0.0'}}).encode('utf-8'))

    monkeypatch.delenv('REVEAL_NO_UPDATE_CHECK', raising=False)
    monkeypatch.setattr(updates, '_update_check_disabled_in_config', lambda: False)
    monkeypatch.setattr(config, 'get_cache_path', lambda name: tmp_path / 'cache' / name)
    (tmp_path / 'cache').mkdir()
    monkeypatch.setattr(version, '__version__', '0.0.1')
    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
    target = tmp_path / 'mod.py'
    target.write_text('def greet():\n    return 1\n', encoding='utf-8')
    return target, calls


def _forms(target):
    return {
        'path': [target, '--format', 'json'],
        'declared-uri': [f'ast://{target.as_posix()}', '--format', 'json'],
        'check': ['check', target, '--format', 'json'],
    }


@pytest.mark.parametrize('form', ['path', 'declared-uri', 'check'])
def test_json_stdout_parses_and_the_notice_reaches_stderr(stale_install, form):
    target, calls = stale_install
    result = _run_reveal_direct(*_forms(target)[form])
    assert calls, 'positive control: the update check ran against the stubbed PyPI read'
    json.loads(result.stdout)  # the whole of stdout is the answer
    assert NOTICE not in result.stdout
    assert result.stderr.count(NOTICE) == 1


def test_text_output_shows_the_notice_once(stale_install):
    target, _ = stale_install
    result = _run_reveal_direct(target)
    assert 'greet' in result.stdout
    assert NOTICE not in result.stdout
    assert result.stderr.count(NOTICE) == 1


def test_opt_out_shows_no_notice_on_either_stream(stale_install, monkeypatch):
    target, calls = stale_install
    monkeypatch.setenv('REVEAL_NO_UPDATE_CHECK', '1')
    result = _run_reveal_direct(target, '--format', 'json')
    json.loads(result.stdout)
    assert calls == []
    assert 'Update available' not in result.stdout + result.stderr
