"""Codex's vocabulary under D20 (BACK-2618, rulings Q1-Q4).

Before, Codex spelled its options with words of its own: ``?filter=TEXT`` (a title or first-message substring),
``?search=TEXT`` (content search), ``?full`` (expanded exchange text) and the presence flags ``?last``, ``?tokens`` and
``?goal``, which selected the last agent message, the token rows or the goal whatever value they had
(``?last=false`` selected it too) and silently won over the path's view (``codex://UUID/tools?last``). The session
views were path segments only.

Now each word is a legacy spelling of a shared control with a note-stage ``param:codex.*`` row, until the cut:
``filter`` is ``--where 'session~=TEXT'`` (the Claude precedent, closed field ``session``, the same population),
``full`` is ``--detail full``, and ``last``/``tokens``/``goal`` are ``--view last|tokens|goal``; each answers exactly
as its replacement, JSON and text. A path's view is ``--view NAME`` too; a path view and a different ``--view`` are two
answers (exit 2 naming both), an equal one is one selection. A false or malformed presence value exits 2 naming the
view. ``search`` answers as ``--match`` except that its JSON ``query`` stays a string where match echoes a list of
terms, so it is a standalone legacy operation with its own note naming ``--match``.
"""
import json

import pytest

from codex_session_fixture import DOC_SESSION_ID as S, build_codex_home
from conftest import _run_reveal_direct, without_request_note_lines
from reveal import api
from reveal.adapters.codex.adapter import CodexAdapter
from reveal.adapters.codex.params import PARAM_SPECS
from reveal.cli.invocation import RETIREMENTS
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


def _notes(doc):
    return [w.get('field') for w in (doc.get('meta') or {}).get('warnings', []) if w.get('code') == 'retired_spelling']


def _answer(doc):
    """The answer without its spelling: retirement notes (the request note and a row's own) and the command echo."""
    doc = json.loads(json.dumps(doc))
    meta = doc.get('meta') or {}
    meta['warnings'] = [w for w in meta.get('warnings', []) if w.get('code') != 'retired_spelling']
    doc.get('execution', {}).pop('command', None)
    return doc


# (legacy request, the canonical subcommand argv after `codex`, the RETIREMENTS row the legacy word spells)
TRANSLATED = [
    ('codex://sessions/?filter=auth', ['sessions', '--where', 'session~=auth'], 'param:codex.filter'),
    # the first user message is part of the population ("Help me refactor this module."; the title is auth-refactor)
    ('codex://sessions/?filter=MODULE', ['sessions', '--where', 'session~=MODULE'], 'param:codex.filter'),
    ('codex://sessions/?filter=nomatch', ['sessions', '--where', 'session~=nomatch'], 'param:codex.filter'),
    ('codex://sessions/?filter=auth&since=2020-01-01&until=today',
     ['sessions', '--where', 'session~=auth', '--since', '2020-01-01', '--until', 'today'], 'param:codex.filter'),
    (f'codex://{S}/exchanges?full', [f'{S}/exchanges', '--detail', 'full'], 'param:codex.full'),
    (f'codex://{S}/exchanges?full=false', [f'{S}/exchanges', '--detail', 'normal'], 'param:codex.full'),
    (f'codex://{S}?last', [S, '--view', 'last'], 'param:codex.last'),
    (f'codex://{S}?last=true', [S, '--view', 'last'], 'param:codex.last'),
    (f'codex://{S}?tokens', [S, '--view', 'tokens'], 'param:codex.tokens'),
    (f'codex://{S}?goal', [S, '--view', 'goal'], 'param:codex.goal'),
]
_IDS = [row[0].split('://', 1)[1].replace(S, 'UUID') for row in TRANSLATED]


@pytest.mark.parametrize('legacy,canonical,row', TRANSLATED, ids=_IDS)
def test_a_legacy_word_answers_as_its_replacement_json_and_text(codex, legacy, canonical, row):
    old, old_doc = _json(legacy)
    new, new_doc = _json('codex', *canonical)
    assert old.returncode == new.returncode == 0, (old.stderr, new.stderr)
    assert _answer(old_doc) == _answer(new_doc)
    assert _notes(new_doc) == []  # the canonical spelling says nothing
    assert _notes(old_doc) == ['request:codex']  # the URI's one note, rendered from the bound request
    note = next(w for w in old_doc['meta']['warnings'] if w.get('field') == 'request:codex')
    assert note['replacement'] == f"reveal {legacy.partition('?')[0]} " + ' '.join(
        f"'{arg}'" if '~=' in arg else arg for arg in canonical[1:])
    old_text, new_text = _run_reveal_direct(legacy), _run_reveal_direct('codex', *canonical)
    assert (old_text.returncode, without_request_note_lines(old_text.stdout)) == (new_text.returncode, new_text.stdout)


# The old flag spells each word that selects (a flag takes no false value: ?full=false has none).
_FLAGGED = [(row, ident) for row, ident in zip(TRANSLATED, _IDS) if not row[0].endswith('=false')]


@pytest.mark.parametrize('legacy,canonical,row', [row for row, _ in _FLAGGED], ids=[ident for _, ident in _FLAGGED])
def test_the_old_flag_of_a_legacy_word_is_the_same_spelling_with_its_row(codex, legacy, canonical, row):
    word = row.rpartition('.')[2]
    query = legacy.partition('?')[2]
    value = next(part.partition('=')[2] for part in query.split('&') if part.partition('=')[0] == word)
    flag = [f'--{word}'] + ([value] if word == 'filter' else [])
    rest = [arg for part in query.split('&') if part.partition('=')[0] in ('since', 'until')
            for arg in (f"--{part.partition('=')[0]}", part.partition('=')[2])]
    old, old_doc = _json('codex', canonical[0], *flag, *rest)
    new, new_doc = _json('codex', *canonical)
    assert old.returncode == new.returncode == 0, old.stderr
    assert _answer(old_doc) == _answer(new_doc)
    assert _notes(old_doc) == [row]
    assert RETIREMENTS[row].replacement.split(' ', 2)[:1] == [canonical[1]]


def test_the_rows_are_note_stage_and_only_search_is_standalone():
    words = ('filter', 'search', 'full', 'last', 'tokens', 'goal')
    rows = {word: RETIREMENTS.get(f'param:codex.{word}') for word in words}
    assert all(row is not None and row.stage == 'note' for row in rows.values()), rows
    assert [word for word, row in rows.items() if row.standalone] == ['search']
    assert '--match TEXT' in rows['search'].replacement


def test_the_typed_api_takes_the_canonical_keywords_and_the_legacy_ones(codex):
    canonical = api.query('codex', 'sessions', where='session~=auth')
    legacy = api.query('codex://sessions/?filter=auth')
    assert _answer(legacy) == _answer(canonical) and canonical['total'] == 1
    assert _answer(api.query('codex', S, view='last')) == _answer(api.query('codex', S, last=True))
    # a typed False restores omission, as it always did (BACK-2701): the overview
    assert api.query('codex', S, last=False)['type'] == 'codex_session_overview'


# --- Q2: the where population -------------------------------------------------------------------------------

def test_where_terms_and_and_a_bare_session_key_is_the_same_filter(codex):
    _run, both = _json('codex', 'sessions', '--where', 'session~=auth', '--where', 'session~=module')
    _run, neither = _json('codex', 'sessions', '--where', 'session~=auth', '--where', 'session~=nomatch')
    assert (both['total'], neither['total']) == (1, 0)
    assert both['where'] == ['session~=auth', 'session~=module']
    bare, bare_doc = _json('codex://sessions/?session~=auth')
    _run, where_doc = _json('codex://sessions/?where=session~=auth')
    assert bare.returncode == 0 and _answer(bare_doc) == _answer(where_doc)


def test_where_names_its_one_field(codex):
    run, doc = _json('codex', 'sessions', '--where', 'title~=auth')
    assert run.returncode == 2 and 'session~=TEXT' in run.stderr


def test_an_empty_filter_still_lists_every_session(codex):
    """Negative control: the empty-term decision is parked for every noun; ``?filter=`` answers the bare list."""
    _run, empty = _json('codex://sessions/?filter=')
    _run, bare = _json('codex://sessions/')
    assert _answer(empty) == _answer(bare) and 'where' not in empty


# --- Q1: search and --match --------------------------------------------------------------------------------

def test_search_answers_as_match_but_its_query_stays_a_string(codex):
    old, legacy = _json('codex://sessions/?search=auth')
    new, match = _json('codex', 'sessions', '--match', 'auth')
    assert old.returncode == new.returncode == 0
    assert (legacy['query'], match['query']) == ('auth', ['auth'])  # not identical: search stays standalone
    for key in ('sessions', 'total', 'type'):
        assert legacy[key] == match[key]
    assert match['total'] == 1 and match['sessions'][0]['match_count'] >= 1
    old_text, new_text = _run_reveal_direct('codex://sessions/?search=auth'), _run_reveal_direct(
        'codex', 'sessions', '--match', 'auth')
    assert without_request_note_lines(old_text.stdout) == new_text.stdout
    assert 'param:codex.search' in _notes(legacy)
    assert next(spec for spec in PARAM_SPECS if spec.name == 'search').role == 'operation'


def test_repeated_match_terms_and_per_session(codex):
    _run, both = _json('codex', 'sessions', '--match', 'auth', '--match', 'simplify')
    _run, neither = _json('codex', 'sessions', '--match', 'auth', '--match', 'nomatch')
    assert (both['total'], neither['total']) == (1, 0)
    assert both['query'] == ['auth', 'simplify']


def test_search_beside_match_is_refused(codex):
    run, _doc = _json('codex://sessions/?search=auth&match=auth')
    assert run.returncode == 2 and 'match' in run.stderr


# --- Q3: views ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize('view', ['messages', 'tools', 'errors', 'shell', 'workflow', 'timeline', 'digest',
                                  'exchanges'])
def test_a_path_view_is_the_view_flag(codex, view):
    path, path_doc = _json(f'codex://{S}/{view}')
    flag, flag_doc = _json('codex', S, '--view', view)
    both, both_doc = _json(f'codex://{S}/{view}', '--view', view)
    assert path.returncode == flag.returncode == both.returncode == 0, flag.stderr
    assert _answer(path_doc) == _answer(flag_doc) == _answer(both_doc)


def test_the_overview_view_is_the_default(codex):
    _run, default = _json('codex', S)
    _run, overview = _json('codex', S, '--view', 'overview')
    assert _answer(default) == _answer(overview) and overview['type'] == 'codex_session_overview'


@pytest.mark.parametrize('argv,names', [
    ((f'codex://{S}/tools', '--view', 'messages'), ('view=messages', 'tools')),
    ((f'codex://{S}/messages?last',), ('last', 'messages')),
    ((f'codex://{S}/exchanges?tokens',), ('tokens', 'exchanges')),
    ((f'codex://{S}/message/0', '--view', 'messages'), ('view=messages', 'message/0')),
    (('codex://sessions', '--view', 'tools'), ('view=tools', 'codex://sessions')),
    (('codex://config?goal',), ('goal', 'codex://config')),
])
def test_two_different_selections_exit_2_naming_both(codex, argv, names):
    run, doc = _json(*argv)
    assert run.returncode == 2, run.stderr
    assert all(name in run.stderr for name in names), run.stderr
    assert doc.get('meta', {}).get('errors') and doc['meta']['errors'][0]['code'] == 'invalid_request'


def test_two_selections_are_refused_on_the_api_too(codex):
    with pytest.raises(RequestValidationError, match='messages'):
        api.query(f'codex://{S}/tools', view='messages')


# --- Q4: last, tokens and goal ------------------------------------------------------------------------------

@pytest.mark.parametrize('word', ['last', 'tokens', 'goal'])
@pytest.mark.parametrize('value', ['false', '0', 'no', 'maybe'])
def test_a_false_or_malformed_presence_exits_2_naming_the_view(codex, word, value):
    run, _doc = _json(f'codex://{S}?{word}={value}')
    assert run.returncode == 2 and f'--view {word}' in run.stderr, run.stderr


def test_two_legacy_views_conflict_and_an_equal_view_is_one(codex):
    run, _doc = _json(f'codex://{S}?last&tokens')
    assert run.returncode == 2 and 'last' in run.stderr and 'tokens' in run.stderr
    _run, once = _json(f'codex://{S}?last&view=last')
    _run, canonical = _json('codex', S, '--view', 'last')
    assert _answer(once) == _answer(canonical)
    run, _doc = _json(f'codex://{S}?last&view=tokens')
    assert run.returncode == 2


# --- full and detail -------------------------------------------------------------------------------------------

def test_full_and_detail_conflict_or_agree(codex):
    run, _doc = _json(f'codex://{S}/exchanges?full&detail=normal')
    assert run.returncode == 2 and 'full' in run.stderr and 'detail' in run.stderr
    _run, once = _json(f'codex://{S}/exchanges?full&detail=full')
    _run, canonical = _json('codex', f'{S}/exchanges', '--detail', 'full')
    assert _answer(once) == _answer(canonical) and canonical['full'] is True


def test_verbose_is_detail_full_on_exchanges(codex):
    _run, verbose = _json('codex', f'{S}/exchanges', '--verbose')
    _run, canonical = _json('codex', f'{S}/exchanges', '--detail', 'full')
    assert _answer(verbose) == _answer(canonical)


# --- negative controls ----------------------------------------------------------------------------------------

def test_the_catalog_and_matches_answer_as_before(codex):
    _run, bare = _json('codex://sessions/')
    assert bare['type'] == 'codex_session_list' and bare['total'] == 1 and _notes(bare) == []
    _run, capped = _json('codex://sessions/?search=refactor&matches=1')
    assert capped['total'] == 1 and all(row['match_count'] <= 1 for row in capped['sessions'])
    assert capped['query'] == 'refactor'  # the legacy search keeps its string query
