"""The retirement seam: one table, one hook, one wording (BACK-2066 slice A, ground rule 7).

A retired spelling prints a note naming its replacement and answers as before; after the cut
release it is an error with the same text. The table is `RETIREMENTS` in cli/invocation.py and
`retirement_note` is the one reader, consulted where each kind of spelling is parsed. The
production rows are two BACK-1906 notes and Phase 2b's call-graph spellings (BACK-2066); the tests
below inject test-only rows (one per kind) so the seam is proven independently of what the table
holds today.
"""
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.cli import invocation
from reveal.cli.invocation import (RETIREMENT_KEY, RETIREMENTS, STAGES, Retirement,
                                   uri_retirement_keys)

SOURCE = 'def auth_gate(value):\n    return value\n'


@pytest.fixture
def source(tmp_path):
    path = tmp_path / 'sample.py'
    path.write_text(SOURCE, encoding='utf-8')
    return path


def _retire(monkeypatch, key, old, replacement='NEW SPELLING', stage='note'):
    monkeypatch.setitem(RETIREMENTS, key, Retirement(old, replacement, stage))
    return f'{old} is deprecated; use {replacement}.'


def _notes(stderr, text):
    return stderr.count(f'note: {text}')


def _warnings(doc):
    return [w for w in (doc.get('meta') or {}).get('warnings') or [] if w.get('code') == 'retired_spelling']


def _without_retirement_warning(doc):
    """The answer minus the retirement fact, an emptied warnings list or meta dropped: what an unretired
    spelling prints."""
    meta = doc.get('meta')
    if isinstance(meta, dict) and 'warnings' in meta:
        meta['warnings'] = [w for w in meta['warnings'] if w.get('code') != 'retired_spelling']
        if not meta['warnings']:
            del meta['warnings']
        if not meta:
            del doc['meta']
    return doc


# One test-only row per kind of spelling, each with the command line that spells it.
# (key, old spelling, argv builder taking the sample file)
KINDS = {
    'subcommand': ('subcommand:check', 'reveal check',
                   lambda f: ['check', f, '--select', 'B001']),
    'scheme': ('scheme:ast', 'ast://', lambda f: [f'ast://{f}?type=function']),
    'param': ('param:ast.name', 'ast://?name=', lambda f: [f'ast://{f}?name=auth*']),
    'value': ('value:ast.type=function', 'ast://?type=function',
              lambda f: [f'ast://{f}?type=function']),
    'declared scheme': ('scheme:hotspots', 'hotspots://', lambda f: [f'hotspots://{f}']),
}


@pytest.mark.parametrize('kind', KINDS)
def test_a_retired_spelling_prints_one_note_and_the_answer_is_unchanged(monkeypatch, source, kind):
    key, old, argv = KINDS[kind]
    argv = argv(str(source))
    base_json = _run_reveal_direct(*argv, '--format', 'json')
    base_text = _run_reveal_direct(*argv)
    assert not base_json.stderr.count('deprecated') and not base_text.stderr.count('deprecated')

    text = _retire(monkeypatch, key, old)
    as_json = _run_reveal_direct(*argv, '--format', 'json')
    as_text = _run_reveal_direct(*argv)

    # Exactly one note on stderr, in either format; the exit code and the answer do not move.
    assert _notes(as_json.stderr, text) == 1
    assert _notes(as_text.stderr, text) == 1
    assert as_json.returncode == base_json.returncode
    assert as_text.returncode == base_text.returncode
    assert as_text.stdout == base_text.stdout
    # JSON stdout still parses and carries the same fact as a meta.warnings entry.
    doc = json.loads(as_json.stdout)
    entries = _warnings(doc)
    assert [(w['old'], w['replacement'], w['stage']) for w in entries] == [(old, 'NEW SPELLING', 'note')]
    assert entries[0]['message'] == text
    assert _without_retirement_warning(doc) == _without_retirement_warning(json.loads(base_json.stdout))


@pytest.mark.parametrize('kind', KINDS)
def test_a_spelling_that_is_not_retired_prints_nothing(monkeypatch, source, kind):
    """Negative control: a table row for another spelling leaves this command line alone."""
    key, old, argv = KINDS[kind]
    _retire(monkeypatch, 'scheme:never-spelled', 'never-spelled://')
    result = _run_reveal_direct(*argv(str(source)), '--format', 'json')
    assert 'deprecated' not in result.stderr
    assert not _warnings(json.loads(result.stdout))


def test_a_note_names_the_spelling_that_was_used_not_a_sibling(monkeypatch, source):
    """A retired value does not retire its parameter, and a retired parameter not its scheme."""
    text = _retire(monkeypatch, 'value:ast.type=class', 'ast://?type=class')
    result = _run_reveal_direct(f'ast://{source}?type=function', '--format', 'json')
    assert 'deprecated' not in result.stderr and text not in result.stderr
    _retire(monkeypatch, 'param:calls.root', 'calls://?root=')
    result = _run_reveal_direct(f'ast://{source}?name=auth*', '--format', 'json')
    assert 'deprecated' not in result.stderr


def test_the_same_parameter_on_another_scheme_is_a_different_spelling(monkeypatch, source):
    """depends://?root= is the scan root; only calls://?root= is retired."""
    assert uri_retirement_keys('depends://src?root=/x') == [
        'scheme:depends', 'param:depends.root', 'value:depends.root=/x']
    assert uri_retirement_keys('calls://src?root=main&depth=2') == [
        'scheme:calls', 'param:calls.root', 'value:calls.root=main',
        'param:calls.depth', 'value:calls.depth=2']
    text = _retire(monkeypatch, 'param:calls.root', 'calls://?root=')
    result = _run_reveal_direct(f'depends://{source}?root={source.parent}', '--format', 'json')
    assert text not in result.stderr


def test_an_operator_spells_the_parameter_before_it():
    assert uri_retirement_keys('ast://src?calls~=a*&callers>2&lines<=9&name!=x&type=function') == [
        'scheme:ast', 'param:ast.calls', 'param:ast.callers', 'param:ast.lines', 'param:ast.name',
        'param:ast.type', 'value:ast.type=function']


def test_a_repeated_spelling_notes_once_per_invocation(monkeypatch, source):
    text = _retire(monkeypatch, 'param:ast.name', 'ast://?name=')
    result = _run_reveal_direct(f'ast://{source}?name=auth*&name=gate*', '--format', 'json')
    assert _notes(result.stderr, text) == 1
    assert len(_warnings(json.loads(result.stdout))) == 1


def test_two_retired_spellings_are_two_notes_and_two_warnings(monkeypatch, source):
    one = _retire(monkeypatch, 'param:ast.name', 'ast://?name=', 'A')
    two = _retire(monkeypatch, 'value:ast.type=function', 'ast://?type=function', 'B')
    result = _run_reveal_direct(f'ast://{source}?type=function&name=auth*', '--format', 'json')
    assert _notes(result.stderr, one) == _notes(result.stderr, two) == 1
    assert sorted(w['replacement'] for w in _warnings(json.loads(result.stdout))) == ['A', 'B']


def test_phase7_is_recorded_and_prints_nothing(monkeypatch, source):
    _retire(monkeypatch, 'scheme:ast', 'ast://', stage='phase7')
    result = _run_reveal_direct(f'ast://{source}?type=function', '--format', 'json')
    assert result.returncode == 0 and 'deprecated' not in result.stderr
    assert not _warnings(json.loads(result.stdout))


@pytest.mark.parametrize('kind', KINDS)
def test_the_error_stage_exits_2_with_the_same_text(monkeypatch, source, kind):
    key, old, argv = KINDS[kind]
    text = _retire(monkeypatch, key, old, stage='error')
    result = _run_reveal_direct(*argv(str(source)), '--format', 'json')
    assert result.returncode == 2
    assert f'error: {text}' in result.stderr
    assert result.stdout == ''


def test_a_retirement_row_validates_itself():
    with pytest.raises(ValueError):
        Retirement('x', 'y', 'later')
    with pytest.raises(ValueError):
        Retirement('x', '')
    with pytest.raises(ValueError):
        Retirement('', 'y')


# --- the production table -------------------------------------------------------------------

# Every production row and one command line that spells it. A row without a case fails the
# last test, so a later phase cannot add a spelling it never exercised.
PRODUCTION_CASES = {
    'flag:--search': lambda f: [f, '--search', 'auth'],
    'flag:--check': lambda f: [f, '--check', '--select', 'B001'],
    # Phase 2b (BACK-2066); every spelling of each row is in tests/test_retired_call_spellings_back2066.py.
    'param:calls.root': lambda f: [f'calls://{Path(f).parent}?root=auth_gate'],
    'param:calls.target': lambda f: [f'calls://{Path(f).parent}?target=auth_gate'],
    'param:ast.calls': lambda f: [f'ast://{f}?calls=auth_gate'],
    'param:ast.callee_of': lambda f: [f'ast://{f}?callee_of=auth_gate'],
    'value:ast.show=calls': lambda f: [f'ast://{f}?show=calls'],
    'subcommand:trace': lambda f: ['trace', str(Path(f).parent), '--from', 'auth_gate'],
    'scheme:trace': lambda f: [f'trace://{Path(f).parent}?from=auth_gate'],
}


def test_every_production_row_is_well_formed():
    assert RETIREMENTS, 'the two BACK-1906 notes live in the table'
    for key, entry in RETIREMENTS.items():
        assert RETIREMENT_KEY.match(key), key
        assert entry.replacement.strip() and entry.old.strip(), key
        assert entry.stage in STAGES, key


def test_every_production_row_is_exercised_and_prints_once(source):
    assert set(RETIREMENTS) == set(PRODUCTION_CASES)
    for key, argv in PRODUCTION_CASES.items():
        result = _run_reveal_direct(*argv(str(source)), '--format', 'json')
        text = RETIREMENTS[key].text
        assert _notes(result.stderr, text) == 1, (key, result.stderr)
        assert [w['field'] for w in _warnings(json.loads(result.stdout))] == [key]


def test_the_moved_notes_keep_their_wording():
    assert RETIREMENTS['flag:--search'].text == '--search is deprecated; use --name PATTERN (regex).'
    assert RETIREMENTS['flag:--check'].text == (
        'file --check/--lint is deprecated; use reveal check <path>.')


@pytest.mark.parametrize('key', ['subcommand:trace', 'scheme:trace', 'param:calls.root',
                                 'value:ast.show=calls', 'flag:--search', 'mcp:reveal_trace'])
def test_the_key_scheme_accepts_each_kind(key):
    assert RETIREMENT_KEY.match(key)


@pytest.mark.parametrize('key', ['trace', 'param:root', 'flag:search', 'Scheme:x', 'mcp:Reveal',
                                 'subcommand:'])
def test_the_key_scheme_rejects_an_unnamespaced_or_malformed_key(key):
    assert not RETIREMENT_KEY.match(key)


# --- MCP: the fact is in the tool result, never on stderr ------------------------------------

def test_mcp_returns_the_note_in_the_result_and_not_on_stderr(monkeypatch, source, capsys):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_query
    uri = f'ast://{source}?name=auth*'
    base = reveal_query(uri)
    text = _retire(monkeypatch, 'param:ast.name', 'ast://?name=')
    capsys.readouterr()
    out = reveal_query(uri)
    assert capsys.readouterr().err == ''
    assert out.count(text) == 1 and base.count(text) == 0
    assert out.startswith(base.rstrip('\n'))
    # Provenance forces JSON: the fact is a parseable meta.warnings entry.
    doc = json.loads(reveal_query(uri, provenance=True))
    assert [w['old'] for w in _warnings(doc)] == ['ast://?name=']


def test_mcp_does_not_note_a_spelling_that_is_not_retired(monkeypatch, source):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_query
    _retire(monkeypatch, 'param:ast.type', 'ast://?type=')
    out = reveal_query(f'ast://{source}?name=auth*')
    assert 'deprecated' not in out
    assert not _warnings(json.loads(reveal_query(f'ast://{source}?name=auth*', provenance=True)))


def test_mcp_tool_names_are_a_kind_of_spelling(monkeypatch, source):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_trace
    base = reveal_trace(str(source.parent), 'auth_gate')
    text = _retire(monkeypatch, 'mcp:reveal_trace', 'reveal_trace', stage='phase7')
    assert reveal_trace(str(source.parent), 'auth_gate') == base
    text = _retire(monkeypatch, 'mcp:reveal_trace', 'reveal_trace', stage='note')
    out = reveal_trace(str(source.parent), 'auth_gate')
    assert out.count(text) == 1 and out.startswith(base.rstrip('\n'))


def test_the_log_is_per_invocation(monkeypatch, source):
    """A second invocation in the same process notes again (nothing leaks between calls)."""
    text = _retire(monkeypatch, 'param:ast.name', 'ast://?name=')
    for _ in range(2):
        result = _run_reveal_direct(f'ast://{source}?name=auth*')
        assert _notes(result.stderr, text) == 1
    assert not invocation.noted_retirements()


@pytest.mark.parametrize('key', sorted(PRODUCTION_CASES))
def test_a_production_row_at_the_error_stage_exits_2_with_its_text(monkeypatch, source, key):
    """The cut release flips a row's stage and nothing else: same text, exit 2, no answer."""
    monkeypatch.setitem(RETIREMENTS, key, Retirement(RETIREMENTS[key].old, RETIREMENTS[key].replacement, 'error'))
    result = _run_reveal_direct(*PRODUCTION_CASES[key](str(source)), '--format', 'json')
    assert result.returncode == 2
    assert f'error: {RETIREMENTS[key].text}' in result.stderr
    assert result.stdout == ''
