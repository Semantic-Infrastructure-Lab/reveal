"""Claude applicability (COMMAND_MODEL "Applicability", BACK-2656 Step 2e).

Claude's answers are selected by the path (the session list and search, the workspace and installation namespaces,
a session's overview and its sub-views) and by the selectors that keep their roles (Scott 2026-11-18, Q5: ``errors``,
``tools``, ``tokens``, ``digest`` and ``timeline`` name the answer they select; ``tools`` and ``errors`` still
combine). Each control declares the answers that read it; on another answer it is an invalid request with the one
shared message, before analysis, on the URI, the subcommand, the URI with a flag and ``api.query``.

Before, ``contains``, ``full``, ``raw`` and ``detail=normal`` answered unchanged with no word on most answers
(``contains`` on the session root and on tail's slice, ``full`` outside the exchanges, the turn range and raw
assistant records, ``raw`` outside ``/prompts`` and ``/messages``), and every selector and ``detail`` answered the
chain unchanged; the other refusals came from Claude's own scope tables (``MODIFIER_SCOPES``, the selector, page,
where and match checks), each with its own text. Checks that are not applicability keep their own text: an operation
beside another selector (rule 17), a detail level the view lacks, a filter field another answer reads, ``key``
selecting one config value rather than a list.
"""
import json

import pytest

from claude_session_fixture import build_claude_home
from conftest import _run_reveal_direct
from reveal.cli.routing.declared import declared_adapter_class

S = 'session/my-session'
UNREAD_WARNINGS = ('unused_query_param', 'unused_flag', 'unknown_query_param')


@pytest.fixture
def claude(tmp_path, monkeypatch):
    adapter = declared_adapter_class('claude')
    home = build_claude_home(tmp_path / 'home')
    monkeypatch.setattr(adapter, 'CLAUDE_HOME', home)
    monkeypatch.setattr(adapter, 'CONVERSATION_BASE', home / 'projects')
    monkeypatch.chdir(tmp_path)
    return home


def _run(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run, (json.loads(run.stdout) if run.stdout.strip().startswith('{') else {})


def _unread(doc):
    return [w for w in (doc.get('meta') or {}).get('warnings') or [] if (w.get('code') or w.get('type'))
            in UNREAD_WARNINGS]


@pytest.mark.parametrize('argv,control,answer', [
    # answered unchanged with no word before
    ((f'claude://{S}?contains=validate',), 'contains', 'claude_session_overview, default'),
    (('claude://sessions?contains=validate',), 'contains', 'claude_session_list, default'),
    ((f'claude://{S}?tail=2&contains=validate',), 'contains', 'claude_messages, tail, tail=2'),
    ((f'claude://{S}/errors?contains=validate',), 'contains', 'claude_errors, default'),
    ((f'claude://{S}/messages?full',), 'full', 'claude_messages, default'),
    ((f'claude://{S}/message/0?full',), 'full', 'claude_message, default'),
    ((f'claude://{S}?raw',), 'raw', 'claude_session_overview, default'),
    ((f'claude://{S}?tail=2&raw',), 'raw', 'claude_messages, tail, tail=2'),
    ((f'claude://{S}/thinking?raw',), 'raw', 'claude_thinking, default'),
    ((f'claude://{S}/chain?errors',), 'errors', 'claude_chain, default'),
    ((f'claude://{S}/chain?detail=summary',), 'detail', 'claude_chain, default'),
    (('claude://sessions?detail=normal',), 'detail', 'claude_session_list, default'),
    ((f'claude://{S}?digest&detail=normal',), 'detail', 'claude_digest, default'),
    # refused before by Claude's own scope checks, with their own text
    (('claude://sessions?key=model',), 'key', 'claude_session_list, default'),
    (('claude://history?word',), 'word', 'claude_history, default'),
    (('claude://sessions?errors',), 'errors', 'claude_session_list, default'),
    ((f'claude://{S}?tokens&digest',), 'tokens', 'claude_digest, default'),
    # an operation selects its answer before a selector does; the selector beside it is unread (rule 17 judges two
    # operations; Conflicting Claude selectors before)
    ((f'claude://{S}?tail=2&errors',), 'errors', 'claude_messages, tail, tail=2'),
    ((f'claude://{S}?summary&tokens',), 'tokens', 'claude_analytics, summary'),
    ((f'claude://{S}?search=x&tokens',), 'tokens', 'claude_search_results, search, search=x'),
    ((f'claude://{S}?tail=2&tools=Bash',), 'tools', 'claude_messages, tail, tail=2'),
    ((f'claude://{S}/tools?patches=true',), 'patches', 'claude_tool_summary, default'),
    ((f'claude://{S}?tail=2&limit=1',), 'limit', 'claude_messages, tail, tail=2'),
    (('claude://info?limit=1',), 'limit', 'claude_info, default'),
    ((f'claude://{S}/thinking?where=tool==Bash',), 'where', 'claude_thinking, default'),
    (('claude://sessions?search=x&where=session~=my',), 'where', 'claude_cross_session_search, search, search=x'),
    ((f'claude://{S}?summary&match=validate',), 'match', 'claude_analytics, summary'),
    ((f'claude://{S}/messages?raw&match=validate',), 'match', 'claude_assistant_messages, default'),
    (('claude://settings?match=x',), 'match', 'claude_settings, default'),
    ((f'claude://{S}/thinking?detail=full',), 'detail', 'claude_thinking, default'),
    (('claude://settings?detail=full',), 'detail', 'claude_settings, default'),
    # the subcommand and the URI with a flag
    (('claude', 'sessions', '--key', 'model'), 'key', 'claude_session_list, default'),
    (('claude', S, '--tokens', '--digest'), 'tokens', 'claude_digest, default'),
    (('claude', f'{S}/thinking', '--detail', 'full'), 'detail', 'claude_thinking, default'),
    ((f'claude://{S}/thinking', '--since', '2020-01-01'), 'since', 'claude_thinking, default'),
    ((f'claude://{S}/tools', '--until', '2030-01-01'), 'until', 'claude_tool_summary, default'),
])
def test_claude_refuses_a_control_its_answer_does_not_read(claude, argv, control, answer):
    run, _doc = _run(*argv)
    assert run.returncode == 2, (run.returncode, run.stdout[:300], run.stderr)
    assert f"control '{control}' is not read by this answer ({answer})" in run.stderr, run.stderr
    assert f'{control} is read by: ' in run.stderr, run.stderr


@pytest.mark.parametrize('uri,keywords,control', [
    (f'claude://{S}?contains=validate', {}, 'contains'),
    (f'claude://{S}', {'raw': True}, 'raw'),
    (f'claude://{S}/messages', {'full': True}, 'full'),
    ('claude://sessions', {'key': 'model'}, 'key'),
    (f'claude://{S}', {'tokens': True, 'digest': True}, 'tokens'),
])
def test_claude_api_refuses_the_same_request(claude, uri, keywords, control):
    from reveal import api
    from reveal.errors import RequestValidationError
    with pytest.raises(RequestValidationError, match=f"control '{control}' is not read by this answer"):
        api.query(uri, **keywords)


@pytest.mark.parametrize('argv', [
    (f'claude://{S}/messages?contains=validate',), (f'claude://{S}?tools=Bash&contains=validate',),
    (f'claude://{S}?errors&contains=error',), (f'claude://{S}/exchanges?full',), (f'claude://{S}/message?full',),
    (f'claude://{S}/messages?raw&full',), (f'claude://{S}/prompts?raw',), (f'claude://{S}/messages?raw',),
    (f'claude://{S}?view=messages&raw',), (f'claude://{S}?view=messages&contains=validate',),
    ('claude://sessions?since=2020-01-01',), ('claude://history?project=proj',), (f'claude://{S}/files?patches=true',),
    (f'claude://{S}/workflow?where=tool==Bash',), ('claude://sessions?where=session~=my',),
    (f'claude://{S}?tools=Bash&errors',), (f'claude://{S}/errors?errors',), (f'claude://{S}?detail=normal',),
    (f'claude://{S}?detail=summary',), (f'claude://{S}/messages?detail=raw',), (f'claude://{S}?match=validate',),
    (f'claude://{S}/messages?match=validate',), (f'claude://{S}/workflow?match=edit',), ('claude://history?match=fix',),
    (f'claude://{S}/errors?match=error',), (f'claude://{S}/messages?limit=1',), (f'claude://{S}?view=messages&limit=1',),
    ('claude://config?limit=1',), (f'claude://{S}?tail=2',), (f'claude://{S}?view=search&match=validate',),
    ('claude://sessions?search=validate&word&snippet=300',), ('claude://settings?key=model',),
    ('claude', 'sessions', '--since', '2020-01-01'), (f'claude://{S}/messages', '--limit', '1'),
])
def test_claude_answers_a_control_its_answer_reads(claude, argv):
    run, doc = _run(*argv)
    assert run.returncode == 0, (run.returncode, run.stderr)
    assert 'is not read by this answer' not in run.stderr
    assert not _unread(doc), _unread(doc)


@pytest.mark.parametrize('uri,text', [
    ('claude://config?key=model&limit=1', 'limit/offset/sort require a supported list answer'),  # key: one value
    ('claude://sessions?summary', 'Session selectors require a session resource: summary'),  # an operation on a path
    ('claude://settings?search=x', 'search selector is unsupported on this resource'),         # with its own answer
    (f'claude://{S}?summary&tail=2', 'summary and tail select different answers'),              # rule 17
    (f'claude://{S}/workflow?detail=raw', 'detail=raw is not supported by this session view'),  # a level, not detail
    (f'claude://{S}/workflow?where=session~=x', 'where supports session~=TEXT on catalog listings or tool==NAME'),
    (f'claude://{S}/messages?limit=1&sort=bogus', 'Unsupported sort field for claude_messages: bogus'),
    (f'claude://{S}?search=x&match=y', 'match conflicts with search on this resource'),
])
def test_claude_checks_that_are_not_applicability_keep_their_own_text(claude, uri, text):
    run, _doc = _run(uri)
    assert run.returncode == 2, (run.returncode, run.stderr)
    assert text in run.stderr, run.stderr
    assert 'is not read by this answer' not in run.stderr, run.stderr


def test_a_sibling_noun_is_unchanged(claude, tmp_path):
    """Codex shares the seam: its refusal and its reading answer are what they were."""
    run, _doc = _run('codex://info?key=model')
    assert run.returncode == 2 and "control 'key' is not read by this answer (codex_info" in run.stderr, run.stderr
