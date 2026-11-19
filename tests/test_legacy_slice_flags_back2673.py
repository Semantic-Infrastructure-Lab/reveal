"""--head/--tail/--range on a declared noun (Scott 2026-11-19, BACK-2706 and BACK-2708; COMMAND_MODEL "Flags after a
URI", BACK-2673). After a URI they sliced a noun's rows with no note while the subcommand exited 2. Where they slice
today they are now a note-stage legacy modifier on both spellings, one RETIREMENTS row per flag per noun; an answer
that does not read them exits 2 on both, as applicability rules; a JSON value only the data shows is not a list
answers with the one shared warning. Claude --tail is held for a ruling and keeps its old route."""
import json

import pytest

import test_vocabulary_conformance_back2654 as C
from legacy_modifier_fixture import rich, workspace  # noqa: F401  (fixtures)

SLICE = {'--head': (['--head', '1'], lambda rows: rows[:1]), '--tail': (['--tail', '1'], lambda rows: rows[-1:]),
         '--range': (['--range', '2-2'], lambda rows: rows[1:2])}
ALL = tuple(SLICE)
# (noun, URI, subcommand argv, the list it slices, flags that slice it)
SLICING = [
    ('ast', 'ast://proj', ['ast', 'proj'], 'results', ALL),
    ('calls', 'calls://proj?sort=-callers', ['calls', 'proj', '--sort=-callers'], 'entries', ALL),
    ('calls', 'calls://proj?callers=helper_c&depth=3', ['calls', 'proj', '--callers', 'helper_c', '--depth', '3'],
     'levels', ALL),
    ('claude', 'claude://sessions', ['claude', 'sessions'], 'recent_sessions', ('--head',)),
    ('claude', 'claude://session/my-session?view=messages', ['claude', 'session/my-session', '--view', 'messages'],
     'messages', ('--head', '--range')),
    ('claude', 'claude://session/my-session/workflow', ['claude', 'session/my-session/workflow'], 'workflow',
     ('--head', '--range')),
    ('git', 'git://proj', ['git', 'proj'], 'commits.recent', ALL),
    ('git', 'git://proj/mod_a.py?view=history', ['git', 'proj/mod_a.py', '--view', 'history'], 'commits', ALL),
    ('hotspots', 'hotspots://proj?min_complexity=1', ['hotspots', 'proj', '--min-complexity', '1'],
     'function_hotspots', ALL),
    ('imports', 'imports://proj?sort=-fan-in', ['imports', 'proj', '--sort=-fan-in'], 'entries', ALL),
    ('imports', 'imports://proj?entrypoints', ['imports', 'proj', '--entrypoints'], 'entries', ALL),
    ('json', 'json://proj/rows.json', ['json', 'proj/rows.json'], 'value', ALL),
    ('markdown', 'markdown://proj', ['markdown', 'proj'], 'results', ALL),
    ('metrics', 'metrics://proj', ['metrics', 'proj'], 'files', ALL),
    ('pack', 'pack://proj', ['pack', 'proj'], 'files', ALL),
    ('patches', 'patches://proj', ['patches', 'proj'], 'groups', ALL),
    ('testability', 'testability://proj?min_patches=1&min_categories=1&include_unresolved=true',
     ['testability', 'proj', '--min-patches', '1', '--min-categories', '1', '--include-unresolved'],
     'patch_hotspots', ALL),
]
# (noun, URI, subcommand argv, flags): answers that never read the flags; they were noted unused or ignored in silence
NOT_READ = [
    ('git', 'git://proj/mod_a.py', ['git', 'proj/mod_a.py'], ALL),
    ('git', 'git://proj/mod_a.py?view=blame', ['git', 'proj/mod_a.py', '--view', 'blame'], ALL),
    ('git', 'git://proj?view=ownership', ['git', 'proj', '--view', 'ownership'], ALL),
    ('imports', 'imports://proj', ['imports', 'proj'], ALL),
    ('imports', 'imports://proj?unused', ['imports', 'proj', '--unused'], ALL),
    ('imports', 'imports://proj?circular', ['imports', 'proj', '--circular'], ALL),
    ('json', 'json://proj/rows.json?view=keys', ['json', 'proj/rows.json', '--view', 'keys'], ALL),
    ('json', 'json://proj/data.json?view=flatten', ['json', 'proj/data.json', '--view', 'flatten'], ALL),
    ('markdown', 'markdown://proj?view=links', ['markdown', 'proj', '--view', 'links'], ALL),
    ('markdown', 'markdown://proj?view=lint', ['markdown', 'proj', '--view', 'lint'], ALL),
    ('calls', 'calls://proj?modules', ['calls', 'proj', '--modules'], ALL),
    ('claude', 'claude://sessions', ['claude', 'sessions'], ('--range',)),
    ('claude', 'claude://session/my-session', ['claude', 'session/my-session'], ('--head',)),
]


def _at(doc, dotted):
    for part in dotted.split('.'):
        doc = doc[part]
    return doc


def _retired(doc):
    return [w['message'] for w in doc['meta'].get('warnings', []) if w.get('code') == 'retired_spelling']


def _slice_cases():
    return [pytest.param(noun, uri, sub, field, flag, id=f'{uri} {flag}')
            for noun, uri, sub, field, flags in SLICING for flag in flags]


def _unread_cases():
    return [pytest.param(noun, uri, sub, flag, id=f'{uri} {flag}') for noun, uri, sub, flags in NOT_READ for flag in flags]


@pytest.mark.parametrize('noun,uri,sub,field,flag', _slice_cases())
def test_a_slicing_flag_answers_alike_on_both_spellings_with_its_note(rich, noun, uri, sub, field, flag):  # noqa: F811
    argv, cut = SLICE[flag]
    base = json.loads(C._run(uri, '--format', 'json').out)
    after_uri = C._run(uri, *argv, '--format', 'json')
    on_sub = C._run(*sub, *argv, '--format', 'json')
    assert after_uri.rc == 0, after_uri.brief()
    assert on_sub.rc == 0, on_sub.brief()
    doc = json.loads(after_uri.out)
    assert _at(doc, field) == cut(_at(base, field))
    notes = [message for message in _retired(doc) if message.startswith(f'{noun} {flag} is deprecated; use ')]
    assert len(notes) == 1, _retired(doc)
    assert C._answer(on_sub, noun) == C._answer(after_uri, noun)
    assert notes == [m for m in _retired(json.loads(on_sub.out)) if m.startswith(f'{noun} {flag} ')]


@pytest.mark.parametrize('noun,uri,sub,field,flag', [case for case in _slice_cases() if case.values[0] in
                                                    ('ast', 'claude', 'json')])
def test_the_text_answer_prints_the_note_once_on_both_spellings(rich, noun, uri, sub, field, flag):  # noqa: F811
    argv, _ = SLICE[flag]
    for run in (C._run(uri, *argv), C._run(*sub, *argv)):
        assert run.rc == 0, run.brief()
        assert run.err.count(f'note: {noun} {flag} is deprecated; use ') == 1, run.err


@pytest.mark.parametrize('noun,uri,sub,flag', _unread_cases())
def test_an_answer_that_does_not_read_the_flag_exits_2_on_both_spellings(rich, noun, uri, sub, flag):  # noqa: F811
    argv, _ = SLICE[flag]
    for run in (C._run(uri, *argv, '--format', 'json'), C._run(*sub, *argv, '--format', 'json')):
        assert run.rc == 2, run.brief()
        assert f"control '{flag[2:]}' is not read by this answer" in run.err + run.out, run.brief()


@pytest.mark.parametrize('flag', ALL)
def test_a_json_value_that_is_not_a_list_is_the_shared_data_warning(rich, flag):  # noqa: F811
    argv, _ = SLICE[flag]
    for run in (C._run('json://proj/data.json', *argv, '--format', 'json'),
                C._run('json', 'proj/data.json', *argv, '--format', 'json')):
        assert run.rc == 0, run.brief()
        warnings = json.loads(run.out)['meta']['warnings']
        assert [w['fields'] for w in warnings if w.get('code') == 'control_unread_by_data'] == [[flag[2:]]]
        assert not [w for w in warnings if w.get('code') in ('unused_flag', 'unused_query_param')]


@pytest.mark.parametrize('argv', [('--head', '1', '--tail', '1'), ('--range', '2-1'), ('--head', '-1')])
def test_a_bad_slice_exits_2_on_both_spellings(rich, argv):  # noqa: F811
    for run in (C._run('ast://proj', *argv), C._run('ast', 'proj', *argv)):
        assert run.rc == 2, run.brief()


def test_no_transport_gains_a_spelling(rich):  # noqa: F811  (negative controls)
    from reveal import query
    from reveal.errors import UnsupportedOverrideError
    from reveal.mcp_server import reveal_query
    # (AST's open field set folds a bare head=1 into where, as any element key: hotspots has no field filter)
    run = C._run('hotspots://proj?head=1')
    assert run.rc == 2 and "unsupported control 'head'" in run.err
    with pytest.raises(UnsupportedOverrideError, match="unsupported control 'head'"):
        query('ast://proj', head=1)
    assert "unsupported control 'head'" in reveal_query('hotspots://proj?head=1')


def test_a_noun_that_never_sliced_still_refuses_the_flags(rich):  # noqa: F811  (negative control)
    for run in (C._run('overview://proj', '--head', '1'), C._run('overview', 'proj', '--head', '1')):
        assert run.rc == 2 and "unsupported control '--head'" in run.err


def test_claude_tail_is_held_on_its_old_route(rich):  # noqa: F811  (pending Scott's ruling)
    held = C._run('claude://session/my-session?view=messages', '--tail', '1', '--format', 'json')
    assert held.rc == 0 and len(json.loads(held.out)['messages']) == 1
    assert not [m for m in _retired(json.loads(held.out)) if '--tail' in m]
    assert C._run('claude', 'session/my-session', '--view', 'messages', '--tail', '1').rc == 2
