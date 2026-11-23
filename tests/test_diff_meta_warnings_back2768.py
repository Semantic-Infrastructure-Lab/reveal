"""diff:// JSON carries the invocation's notes in ``meta.warnings``, and an unknown query key is disclosed (BACK-2768).

Pathread P5 B19: ``rendering.diff.render_diff_json`` printed ``json.dumps`` itself, so an element diff's JSON never
carried what the invocation recorded: a config warning (and a retirement note) went to stderr beside the JSON, against
COMMAND_MODEL "Transports". The comparison's JSON happened to carry them only because the URI route attached them
first.

An unknown query key (``diff://a.py:b.py?bogus=1``) was read as the right side: the canonical construction passes
``(resource, query)`` and diff's constructor takes ``(left, right)``, so the answer was "File not found: a.py:b.py"
(exit 2) on the CLI and ``DiffTargetNotFoundError`` on the API. diff:// takes no query keys; an unknown one is now
disclosed as every adapter that reads no query discloses it (``unknown_query_param``, the answer still runs), as a
result-control key (``?limit=``) already was.
"""
import json
import os
import subprocess
import sys

import pytest

from reveal import api

pytestmark = [pytest.mark.component]


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'a.py').write_text('def ok():\n    return 1\n', encoding='utf-8')
    (root / 'b.py').write_text('def ok():\n    return 2\n', encoding='utf-8')
    (tmp_path / 'xdg').mkdir()
    monkeypatch.chdir(root)
    return root


def _cli(root, *argv):
    env = {key: value for key, value in os.environ.items() if not key.startswith('REVEAL_')}
    env.update(REVEAL_DISK_CACHE='0', XDG_CONFIG_HOME=str(root.parent / 'xdg'))
    return subprocess.run([sys.executable, '-m', 'reveal', *argv], capture_output=True, text=True,
                          encoding='utf-8', env=env, cwd=root, timeout=180)


def _warnings(document, code):
    return [w for w in (document.get('meta') or {}).get('warnings') or [] if w.get('code') == code]


@pytest.mark.cli
@pytest.mark.parametrize('argv,answer_type', [
    (('diff://a.py:b.py/ok',), 'diff_element'),
    (('diff://a.py:b.py', 'ok'), 'diff_element'),
    (('diff://a.py:b.py',), 'diff_comparison'),  # control: the comparison's JSON already carried it
], ids=['embedded-element', 'positional-element', 'comparison'])
def test_a_config_warning_is_in_the_json_and_not_on_stderr(project, argv, answer_type):
    (project / '.reveal.yaml').write_text('root: true\nbogus_top: 3\n', encoding='utf-8')
    result = _cli(project, *argv, '--format', 'json')
    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)
    assert document['type'] == answer_type
    assert [w['type'] for w in _warnings(document, 'config_schema_invalid')] == ['config_warning'], document['meta']
    assert result.stderr == ''


@pytest.mark.cli
@pytest.mark.parametrize('uri,answer_type,key', [
    ('diff://a.py:b.py?bogus=1', 'diff_comparison', 'bogus'),
    ('diff://a.py:b.py/ok?bogus=1', 'diff_element', 'bogus'),
    ('diff://a.py:b.py?limit=1', 'diff_comparison', 'limit'),  # control: a result-control key was disclosed already
], ids=['comparison', 'element', 'result-control'])
def test_an_unknown_query_key_is_disclosed_and_the_answer_runs(project, uri, answer_type, key):
    result = _cli(project, uri, '--format', 'json')
    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)
    assert document['type'] == answer_type
    assert [w['fields'] for w in _warnings(document, 'unknown_query_param')] == [[key]], document['meta']
    assert result.stderr == ''
    text = _cli(project, uri)
    assert text.returncode == 0 and f"Unknown query param '{key}' for diff://" in text.stderr, text.stderr


def test_api_reads_no_query_key_as_the_right_side(project):
    assert api.query('diff://a.py:b.py?bogus=1')['type'] == 'diff_comparison'
    assert api.query('diff://a.py:b.py/ok?bogus=1')['type'] == 'diff_element'


def test_mcp_discloses_an_unknown_query_key(project):
    from reveal.mcp_server import reveal_query, _ToolFailure
    answer = reveal_query('diff://a.py:b.py?bogus=1')
    assert not isinstance(answer, _ToolFailure), str(answer)[:400]
    assert "Unknown query param 'bogus' for diff://" in str(answer), str(answer)[-400:]
