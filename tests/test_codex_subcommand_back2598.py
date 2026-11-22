"""The codex subcommand, generated from Codex's declarations (BACK-2598, codex part of BACK-2618; ruling Q6).

Before, codex was a URI-only noun: ``reveal codex X`` exited 2 ("codex is a URI noun"), ``api.query('codex', ...)``
raised ``ValueError: 'codex' has no subcommand`` and ``reveal_run(['codex', ...])`` was refused. ``since``/``until``
reached the adapter after a URI through a hand flag-forwarding table (``CLI_QUERY_FLAGS``). ``--head``/``--tail``/
``--range`` after a codex URI sliced rows with no note, and codex had no row control to name in their place.

Now ``reveal codex [RESOURCE]`` takes every Codex control as a flag through the shared declared builder, with the same
JSON and exit as the URI with the same controls; the typed API's noun form and MCP answer alike. List answers take the
shared ``--limit``/``--offset`` (``--limit 0`` is uncapped), refused on answers without rows. ``--head``/``--tail``/
``--range`` and ``--check``/``--lint`` are legacy modifiers with their ``flag:codex.<flag>`` notes, on both forms.
"""
import json

import pytest

from codex_session_fixture import DOC_SESSION_ID as S, build_codex_home
from conftest import _run_reveal_direct, without_request_notes
from reveal import api
from reveal.adapters.codex.adapter import CodexAdapter
from reveal.cli.invocation import RETIREMENTS


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


def _answer(doc):
    """The answer without the URI request's own note (BACK-2716) and the command echo of its spelling."""
    doc = without_request_notes(doc)
    doc.get('execution', {}).pop('command', None)
    return doc


# (subcommand argv after `codex`, the same request as a URI), in the canonical spelling (the legacy words and their
# old flags answer as these: tests/test_codex_vocabulary_back2618.py)
PAIRS = [
    ([], 'codex://'),
    (['sessions'], 'codex://sessions'),
    (['sessions', '--match', 'auth', '--matches', '1'], 'codex://sessions/?match=auth&matches=1'),
    (['sessions', '--where', 'session~=auth', '--since', '2020-01-01', '--until', 'today'],
     'codex://sessions/?where=session~=auth&since=2020-01-01&until=today'),
    ([S], f'codex://{S}'),
    ([S, '--view', 'last'], f'codex://{S}?view=last'),
    ([S, '--view', 'tokens'], f'codex://{S}?view=tokens'),
    ([S, '--view', 'goal'], f'codex://{S}?view=goal'),
    ([S, '--view', 'tools'], f'codex://{S}/tools'),
    ([f'{S}/exchanges', '--detail', 'full'], f'codex://{S}/exchanges?detail=full'),
    ([f'{S}/messages', '--limit', '2', '--offset', '1'], f'codex://{S}/messages?limit=2&offset=1'),
    (['config', '--key', 'model'], 'codex://config?key=model'),
    (['info'], 'codex://info'),
    (['skills'], 'codex://skills'),
]


@pytest.mark.parametrize('argv,uri', PAIRS, ids=[' '.join(row[0]) or '(root)' for row in PAIRS])
def test_the_subcommand_answers_as_the_uri(codex, argv, uri):
    cli, cli_doc = _json('codex', *argv)
    url, url_doc = _json(uri)
    assert cli.returncode == url.returncode == 0, (cli.stderr, url.stderr)
    assert _answer(cli_doc) == _answer(url_doc)


@pytest.mark.parametrize('argv,uri', [PAIRS[2], PAIRS[5]], ids=['match', 'view last'])
def test_text_output_matches(codex, argv, uri):
    from conftest import without_request_note_lines
    cli = _run_reveal_direct('codex', *argv)
    url = _run_reveal_direct(uri)
    assert cli.returncode == url.returncode == 0
    assert without_request_note_lines(cli.stdout) == without_request_note_lines(url.stdout)


def test_the_typed_api_noun_form_answers_as_the_uri(codex):
    noun = api.query('codex', 'sessions', match='auth', matches=1)
    uri = api.query('codex://sessions/', match='auth', matches=1)
    assert noun['type'] == 'codex_content_search'
    assert _answer(noun) == _answer(uri)


def test_mcp_runs_the_subcommand(codex):
    pytest.importorskip('mcp')
    from reveal import mcp_server
    answer = json.loads(mcp_server.reveal_run(['codex', 'sessions', '--match', 'auth', '--format', 'json']))
    assert answer['type'] == 'codex_content_search' and [row['id'] for row in answer['sessions']] == [S]


def test_an_invalid_resource_exits_2_alike(codex):
    cli, _ = _json('codex', 'no-such-thread')
    url, _ = _json('codex://no-such-thread')
    assert cli.returncode == url.returncode == 2
    assert "Unknown codex:// resource: 'no-such-thread'" in cli.stderr + cli.stdout


def test_since_after_a_uri_binds_through_the_declarations(codex):
    """The hand forwarding table is gone; the flag after a URI is the subcommand's flag (COMMAND_MODEL "Flags after a
    URI")."""
    assert 'since' not in (getattr(CodexAdapter, 'CLI_QUERY_FLAGS', None) or {})
    run, doc = _json('codex://sessions/?filter=auth', '--since', '2027-01-01')
    assert (run.returncode, doc['type'], doc['total']) == (0, 'codex_session_list', 0)


# ---- ruling Q6: the shared --limit/--offset page list answers ----

def test_limit_and_offset_page_a_list_answer(codex):
    _, whole = _json('codex', f'{S}/messages')
    run, doc = _json('codex', f'{S}/messages', '--limit', '1', '--offset', '1')
    assert run.returncode == 0, run.stderr
    assert doc['messages'] == whole['messages'][1:2]
    receipt = doc['meta']['pagination']
    assert (receipt['applied'], receipt['total'], receipt['shown'], receipt['limit'], receipt['offset']) == \
        (True, len(whole['messages']), 1, 1, 1)
    assert any(entry.get('field') == 'messages' for entry in doc['meta'].get('truncated', []) or
               [w for w in doc['meta']['warnings'] if w.get('type') == 'truncated'])


def test_limit_zero_is_uncapped(codex):
    _, whole = _json('codex', f'{S}/messages')
    run, doc = _json('codex', f'{S}/messages', '--limit', '0')
    assert run.returncode == 0 and doc['messages'] == whole['messages']


@pytest.mark.parametrize('argv', [['config', '--limit', '1'], [S, '--offset', '1'], ['info', '--limit', '1']],
                         ids=['config', 'overview', 'info'])
def test_limit_on_an_answer_without_rows_exits_2(codex, argv):
    run, doc = _json('codex', *argv)
    assert run.returncode == 2
    control = argv[-2].lstrip('-')
    assert f"control '{control}' is not read by this answer" in doc['error']


def test_a_negative_limit_exits_2(codex):
    run, _ = _json('codex', 'sessions', '--limit', '-1')
    assert run.returncode == 2


# ---- legacy modifiers: notes on both forms ----

@pytest.mark.parametrize('form', ['subcommand', 'uri'])
def test_head_slices_with_its_note_naming_limit(codex, form):
    argv = ['codex', f'{S}/messages'] if form == 'subcommand' else [f'codex://{S}/messages']
    run, doc = _json(*argv, '--head', '1')
    assert run.returncode == 0, run.stderr
    assert len(doc['messages']) == 1
    notes = [w for w in doc['meta']['warnings'] if w.get('field') == 'flag:codex.--head']
    assert [note['replacement'] for note in notes] == ['--limit N']


def test_every_legacy_modifier_has_its_row():
    for flag in ('--head', '--tail', '--range', '--check', '--lint'):
        assert f'flag:codex.{flag}' in RETIREMENTS


def test_two_slices_exit_2(codex):
    run, _ = _json('codex', f'{S}/messages', '--head', '1', '--tail', '1')
    assert run.returncode == 2


def test_check_is_noted_and_changes_nothing(codex):
    _, whole = _json('codex', f'{S}/messages')
    run, doc = _json('codex', f'{S}/messages', '--check')
    assert run.returncode == 0
    assert doc['messages'] == whole['messages']
    assert [w['field'] for w in doc['meta']['warnings'] if w.get('code') == 'retired_spelling'] == ['flag:codex.--check']


def test_the_subcommand_help_lists_its_controls():
    run = _run_reveal_direct('codex', '--help')
    assert run.returncode == 0
    for flag in ('--where', '--match', '--since', '--until', '--key', '--view', '--detail', '--matches', '--limit',
                 '--offset'):
        assert flag in run.stdout
    # the legacy words are URI spellings only, never flags of the subcommand (BACK-2618 ruling 2)
    for flag in ('--search', '--filter', '--last', '--tokens', '--goal', '--full'):
        assert flag not in run.stdout.split(), flag


# ---- negative controls: the URI answers are unchanged ----

@pytest.mark.parametrize('uri,kind,field,rows', [
    ('codex://', 'codex_session_list', 'sessions', 1),
    ('codex://sessions/?search=auth', 'codex_content_search', 'sessions', 1),
    (f'codex://{S}/messages', 'codex_messages', 'messages', 4),
    (f'codex://{S}?last', 'codex_messages', 'messages', 1),
])
def test_uri_answers_are_unchanged(codex, uri, kind, field, rows):
    run, doc = _json(uri)
    assert (run.returncode, doc['type'], len(doc[field])) == (0, kind, rows)


def test_head_after_a_uri_still_slices(codex):
    run, doc = _json(f'codex://{S}/messages', '--head', '1')
    assert (run.returncode, len(doc['messages'])) == (0, 1)
