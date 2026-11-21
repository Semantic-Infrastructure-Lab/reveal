"""Codex resource validity (BACK-2700; D6: an invalid resource exits 2, plan rule 9: a named target that matches
nothing exits 2 naming what was searched).

Before: ``codex://no-such-thread`` answered ``Unknown codex:// resource`` with exit 1 (the findings code); an unknown
session view (``codex://UUID/bogus``) answered the overview and an unknown catalog or named-resource suffix
(``codex://sessions/foo``, ``codex://info/x``, ...) answered as if the suffix were absent, exit 0; ``history/x`` exited 1
where ``history`` exits 2; ``skills/NAME`` and ``plugins/NAME`` that match no definition exited 1. The predictor named
``sessions/foo`` a session overview while the router answered the session list, so a catalog control there was refused
as "not read by codex_session_overview". Each is now one invalid request, exit 2, on the CLI (text and JSON), the
typed API (``RequestValidationError``) and MCP, before any session is read; every valid resource answers as before.
"""
import json

import pytest

from codex_session_fixture import DOC_SESSION_ID as S, build_codex_home
from conftest import _run_reveal_direct
from reveal.adapters.codex.adapter import CodexAdapter
from reveal.errors import RequestValidationError


@pytest.fixture
def codex(tmp_path, monkeypatch):
    home = build_codex_home(tmp_path / 'home')
    monkeypatch.setattr(CodexAdapter, 'CODEX_HOME', home)
    monkeypatch.setattr(CodexAdapter, 'CODEX_DB', home / 'state_5.sqlite')
    monkeypatch.chdir(tmp_path)
    return home


def _json(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run, (json.loads(run.stdout) if run.stdout.strip().startswith('{') else {})


_RESOURCES = 'resources: sessions, <UUID>[/VIEW], info, history, config, memories[/pipeline], rules, skills[/NAME], plugins[/NAME]'

# (resource, the message the invalid request names)
INVALID = [
    ('no-such-thread', f"Unknown codex:// resource: 'no-such-thread'; {_RESOURCES}"),
    ('019E5CC5', f"Unknown codex:// resource: '019E5CC5'; {_RESOURCES}"),            # ids are lower-case hex
    (f'{S}/bogus', f'Unsupported Codex session view: {S}/bogus; views: messages, tools, errors, shell, workflow, '
                   'timeline, digest, exchanges, message/N'),
    (f'{S}/messages/x', f'Unsupported Codex session view: {S}/messages/x; views: messages, tools, errors, shell, '
                        'workflow, timeline, digest, exchanges, message/N'),
    ('sessions/foo', 'codex://sessions does not support a resource suffix: foo'),
    ('info/x', 'codex://info does not support a resource suffix: x'),
    ('config/x', 'codex://config does not support a resource suffix: x'),
    ('history/x', 'codex://history does not support a resource suffix: x'),
    ('rules/x', 'codex://rules does not support a resource suffix: x'),
    ('memories/x', 'codex://memories does not support a resource suffix: x'),
    ('memories/pipeline/x', 'codex://memories/pipeline does not support a resource suffix: x'),
]
# Named items: the definitions searched are named (rule 9).
NOT_FOUND = [
    ('skills/nope', 'Skill not found: nope (searched 1 skill definition: openai-docs)'),
    ('plugins/nope', 'Plugin not found: nope (searched 1 plugin manifest: demo)'),
]


@pytest.mark.parametrize('resource,message', INVALID + NOT_FOUND)
def test_an_invalid_resource_exits_2_naming_it(codex, resource, message):
    run, doc = _json(f'codex://{resource}')
    assert run.returncode == 2, (run.returncode, run.stderr)
    assert message in run.stderr, run.stderr
    assert message in json.dumps(doc), doc


@pytest.mark.parametrize('resource,message', INVALID[:1] + INVALID[2:3] + NOT_FOUND[:1])
def test_text_mode_exits_2_with_the_message_on_stderr_and_no_answer(codex, resource, message):
    run = _run_reveal_direct(f'codex://{resource}')
    assert run.returncode == 2, (run.returncode, run.stderr)
    assert message in run.stderr and not run.stdout.strip(), (run.stdout, run.stderr)


def test_the_predictor_names_the_catalog_for_a_catalog_suffix(codex):
    """The router dispatches every ``sessions/...`` path to the catalog, so the predictor does too: a catalog control
    there meets the resource's own refusal, not "search is not read by codex_session_overview"."""
    assert CodexAdapter.result_type_at({}, 'sessions/foo') == 'codex_session_list'
    assert CodexAdapter.result_type_at({'search': 'auth'}, 'sessions/foo') == 'codex_content_search'
    run, _ = _json('codex://sessions/foo?search=auth')
    assert run.returncode == 2
    assert 'codex://sessions does not support a resource suffix: foo' in run.stderr, run.stderr
    assert 'not read by this answer' not in run.stderr, run.stderr


@pytest.mark.parametrize('resource,message', INVALID[:1] + INVALID[2:3] + INVALID[4:5] + NOT_FOUND)
def test_the_typed_api_raises_the_invalid_request(codex, resource, message):
    from reveal import api
    with pytest.raises(RequestValidationError) as raised:
        api.query(f'codex://{resource}')
    assert message in str(raised.value)


@pytest.mark.parametrize('resource,message', INVALID[:1] + NOT_FOUND[:1])
def test_mcp_reports_the_invalid_request_as_the_missing_session_does(codex, resource, message):
    pytest.importorskip('mcp')
    from reveal import mcp_server
    missing = mcp_server.reveal_query('codex://deadbeef00')
    assert missing.startswith('[reveal error: Session not found: deadbeef00')  # the outcome form an invalid request has
    answer = mcp_server.reveal_query(f'codex://{resource}')
    assert answer.startswith('[reveal error: ') and message in answer, answer
    assert 'exited with code 1' not in answer
    run = mcp_server.reveal_run([f'codex://{resource}', '--format', 'json'])
    assert run.startswith('[reveal error: ') and message in run, run


VALID = ['', '.', 'sessions', 'sessions/', S, f'{S}/messages', f'{S}/tools', f'{S}/exchanges', f'{S}/message/0',
         f'{S}/message/-1', 'info', 'config', 'memories', 'rules', 'skills', 'skills/openai-docs', 'plugins',
         'plugins/demo']


@pytest.mark.parametrize('resource', VALID)
def test_valid_resources_answer_as_before(codex, resource):
    """Negative control: every valid resource still answers, exit 0, with its own answer type."""
    run, doc = _json(f'codex://{resource}')
    assert run.returncode == 0, (resource, run.stderr)
    assert doc['type'].startswith('codex_') and doc['type'] != 'codex_error', doc['type']
    assert 'error' not in doc, doc.get('error')


@pytest.mark.parametrize('resource,message', [
    ('deadbeef00', 'Session not found: deadbeef00'),
    (f'{S}/message/x', "Invalid message index: 'x'"),
    (f'{S}/message/99', 'No record at index 99'),
])
def test_existing_session_rejections_keep_exit_2(codex, resource, message):
    """Negative control: the session lookup and index rejections were already exit 2 and say what they said."""
    run, _ = _json(f'codex://{resource}')
    assert run.returncode == 2 and message in run.stderr, (run.returncode, run.stderr)
