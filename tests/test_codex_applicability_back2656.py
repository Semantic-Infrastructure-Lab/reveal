"""Codex applicability (COMMAND_MODEL "Applicability", BACK-2656 Step 2d).

The path selects most Codex answers (the session catalog, a session's overview and its sub-views, config, info and
the other named resources), and three flags select a session's answer without being operations (Scott 2026-11-18, Q5:
``last`` the last agent message, ``tokens`` the per-request breakdown, ``goal`` the thread goal); each declares the
answer it selects. ``search`` selects the content search; ``filter`` narrows the session list; ``matches`` is the
search's; ``since``/``until`` bound a filtered or searched catalog (they require ``filter`` or ``search``); ``key`` is
config's; ``full`` is the paired exchanges'. A control on another answer is an invalid request with the one shared
message, on the URI, the URI with a flag and ``api.query``. Before, each answered: the ledger noted most of them,
exit 0; Codex printed its own "Unknown query param 'full' ... ignored"; ``filter`` beside ``search`` was dropped with
no word at all. The predictor named every resource a session overview; it now names the answer the path selects.
"""
import json

import pytest

from codex_session_fixture import DOC_SESSION_ID as S, build_codex_home
from conftest import _run_reveal_direct
from reveal.adapters.codex.adapter import CodexAdapter
from reveal.errors import RequestValidationError

UNREAD_WARNINGS = ('unused_query_param', 'unused_flag', 'unknown_query_param')


@pytest.fixture
def codex(tmp_path, monkeypatch):
    home = build_codex_home(tmp_path / 'home')
    monkeypatch.setattr(CodexAdapter, 'CODEX_HOME', home)
    monkeypatch.setattr(CodexAdapter, 'CODEX_DB', home / 'state_5.sqlite')
    (tmp_path / 'rows.json').write_text('[{"n": 1}, {"n": 2}]', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return home


def _run(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run, (json.loads(run.stdout) if run.stdout.strip().startswith('{') else {})


def _unread(doc):
    return [w for w in (doc.get('meta') or {}).get('warnings') or [] if (w.get('code') or w.get('type'))
            in UNREAD_WARNINGS]


@pytest.mark.parametrize('argv,control,answer', [
    (('codex://?key=model',), 'key', 'codex_session_list, default'),                  # the ledger's note before
    (('codex://?search=auth&filter=auth',), 'filter', 'codex_content_search, default'),  # silent before
    (('codex://?filter=auth&matches=1',), 'matches', 'codex_session_list, default'),
    (('codex://?last',), 'last', 'codex_session_list, default'),
    ((f'codex://{S}?search=auth',), 'search', 'codex_session_overview, default'),
    ((f'codex://{S}/messages?full',), 'full', 'codex_messages, default'),             # its own warning before
    ((f'codex://{S}/exchanges?full&last',), 'full', 'codex_messages, default'),       # last selects the messages
    ((f'codex://{S}?last&tokens',), 'tokens', 'codex_messages, default'),
    ((f'codex://{S}?tokens&goal',), 'goal', 'codex_tokens, default'),
    ((f'codex://{S}/tools?until=2030-01-01',), 'until', 'codex_tools, default'),
    (('codex://config?since=2020-01-01',), 'since', 'codex_config, default'),
    (('codex://info?key=model',), 'key', 'codex_info, default'),
    (('codex://info?last',), 'last', 'codex_info, default'),
    ((f'codex://{S}/messages', '--since', '2020-01-01'), 'since', 'codex_messages, default'),  # URI and a flag
])
def test_codex_refuses_a_control_its_answer_does_not_read(codex, argv, control, answer):
    run, _doc = _run(*argv)
    assert run.returncode == 2, (run.returncode, run.stdout[:300], run.stderr)
    assert f"control '{control}' is not read by this answer ({answer}" in run.stderr, run.stderr
    assert f'{control} is read by: ' in run.stderr, run.stderr


@pytest.mark.parametrize('argv', [('codex://?since=2020-01-01',), ('codex://?until=2030-01-01',),
                                  ('codex://sessions', '--since', '2020-01-01')])
def test_codex_catalog_bounds_require_a_filter_or_a_search(codex, argv):
    """The bare session list lists every session; its date bounds apply only to a filter or a search (they answered
    the whole list before, with the ledger's note)."""
    run, _doc = _run(*argv)
    assert run.returncode == 2, (run.returncode, run.stderr)
    assert 'requires filter or search' in run.stderr, run.stderr


@pytest.mark.parametrize('resource,answer', [('memories', 'codex_memories'), ('memories/pipeline',
                                                                         'codex_memories_pipeline'),
                                             ('rules', 'codex_rules'), ('skills', 'codex_skills'),
                                             ('plugins', 'codex_plugins')])
def test_codex_refuses_a_flag_on_a_named_resource_that_selects_its_own_answer(codex, resource, answer):
    """A named resource answers itself whatever last says (predicted a session's messages before, so last went unread
    with the ledger's note). The refusal is an invalid request, exit 2, like every applicability refusal, although
    these resources have no execution facts on the generic route (which exits 1 for its other construction errors)."""
    run, _doc = _run(f'codex://{resource}?last')
    assert run.returncode == 2, (run.returncode, run.stderr)
    assert f"control 'last' is not read by this answer ({answer}, default" in run.stderr, run.stderr


def test_codex_api_refuses_the_same_request(codex):
    from reveal import api
    with pytest.raises(RequestValidationError, match=r"control 'full' is not read by this answer \(codex_messages"):
        api.query(f'codex://{S}/messages', full=True)


@pytest.mark.parametrize('uri', [
    'codex://?filter=auth&since=2020-01-01&until=2030-01-01',
    'codex://?search=auth&since=2020-01-01&matches=1',
    'codex://',
    f'codex://{S}',
    f'codex://{S}/exchanges?full',
    f'codex://{S}?last',
    f'codex://{S}?tokens',
    f'codex://{S}?goal',
    f'codex://{S}/tools?last',  # last selects the last message on any session resource
    'codex://config?key=model',
    'json://rows.json?limit=1',  # a sibling noun's reading answer, unchanged
])
def test_codex_answers_where_its_controls_are_read(codex, uri):
    run, doc = _run(uri)
    assert run.returncode in (0, 3), (run.returncode, run.stderr)
    assert not _unread(doc), doc.get('meta')
    assert 'ignored' not in run.stderr and 'no effect' not in run.stderr, run.stderr


@pytest.mark.parametrize('resource,query,expected', [
    ('.', '', 'codex_session_list'), ('sessions', 'search=auth', 'codex_content_search'),
    (S, '', 'codex_session_overview'), (f'{S}/tools', '', 'codex_tools'), (f'{S}/exchanges', '', 'codex_exchanges'),
    (f'{S}/message/0', '', 'codex_message'), (S, 'last', 'codex_messages'), (f'{S}/tools', 'tokens', 'codex_tokens'),
    (S, 'goal', 'codex_goal'), ('config', '', 'codex_config'), ('info', '', 'codex_info'),
    ('memories', '', 'codex_memories'), ('memories/pipeline', '', 'codex_memories_pipeline'),
    ('rules', '', 'codex_rules'), ('skills', '', 'codex_skills'), ('plugins', '', 'codex_plugins'),
    ('memories', 'last', 'codex_memories'),
])
def test_the_predictor_names_the_answer_the_path_selects(resource, query, expected):
    """The shared predictor (adapters/factory.predicted_result_type) asks Codex's own selection for each resource."""
    from reveal.adapters.factory import predicted_result_type
    from reveal.adapters.codex.params import PARAM_SPECS
    from reveal.utils.query_binding import bind_declared_params
    params = bind_declared_params(PARAM_SPECS, query, transport='uri')
    assert predicted_result_type(CodexAdapter, params, resource) == expected
