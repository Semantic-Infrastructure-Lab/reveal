"""diff:// JSON carries the invocation's notes in ``meta.warnings`` (BACK-2768), and an unknown query key is refused
(BACK-2214).

Pathread P5 B19: ``rendering.diff.render_diff_json`` printed ``json.dumps`` itself, so an element diff's JSON never
carried what the invocation recorded: a config warning (and a retirement note) went to stderr beside the JSON, against
COMMAND_MODEL "Transports". The comparison's JSON happened to carry them only because the URI route attached them
first.

An unknown query key (``diff://a.py:b.py?bogus=1``) was read as the right side: the canonical construction passes
``(resource, query)`` and diff's constructor took ``(left, right)``, so the answer was "File not found: a.py:b.py"
(exit 2) on the CLI and ``DiffTargetNotFoundError`` on the API. diff takes no control: since its declaration
(BACK-2214) an unknown key, and a result-control key (``?limit=``), is an unsupported control, exit 2 naming it on
every transport, as on every declared noun (it was disclosed as ``unknown_query_param`` with the answer running
between BACK-2768 and BACK-2214).
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
@pytest.mark.parametrize('uri,key', [
    ('diff://a.py:b.py?bogus=1', 'bogus'),
    ('diff://a.py:b.py/ok?bogus=1', 'bogus'),
    ('diff://a.py:b.py?limit=1', 'limit'),  # a result-control key: diff declares no cap either
], ids=['comparison', 'element', 'result-control'])
def test_an_unknown_query_key_is_refused_naming_it(project, uri, key):
    result = _cli(project, uri, '--format', 'json')
    assert result.returncode == 2, result.stderr
    document = json.loads(result.stdout)  # the invalid-request document, not empty stdout
    assert f"unsupported control '{key}'" in document['error'], document
    assert 'File not found' not in document['error']  # never read as the right side
    text = _cli(project, uri)
    assert text.returncode == 2 and f"unsupported control '{key}'" in text.stderr, text.stderr


def test_api_refuses_a_query_key_and_never_reads_it_as_the_right_side(project):
    from reveal.errors import RequestValidationError
    for uri in ('diff://a.py:b.py?bogus=1', 'diff://a.py:b.py/ok?bogus=1'):
        with pytest.raises(RequestValidationError, match="unsupported control 'bogus'"):
            api.query(uri)


def test_mcp_refuses_an_unknown_query_key(project):
    from reveal.mcp_server import reveal_query, _ToolFailure
    answer = reveal_query('diff://a.py:b.py?bogus=1')
    assert isinstance(answer, _ToolFailure), str(answer)[:400]
    assert "unsupported control 'bogus'" in str(answer), str(answer)[-400:]
