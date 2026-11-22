"""JSON applicability (COMMAND_MODEL "Applicability", BACK-2656 Step 2a).

The array controls (``where``, ``sort``, ``limit``, ``offset``) are read by the value answer (``json_value``) and
``detail`` by the flatten answer (``json_flatten``); any other answer refuses them before it answers, legacy first-word
selectors (``?schema``, ``?gron``) included, with the one shared message. Whether the value answer applies an array
control only the data can tell (the value at the path may not be a list): that answers with the one shared
``control_unread_by_data`` warning, exit 0 (Scott 2026-11-18, Step 0 Q2), on every transport.
"""
import json

import pytest

from conftest import _run_reveal_direct, without_request_note_lines
from reveal.errors import RequestValidationError

UNREAD_WARNINGS = ('unused_query_param', 'unused_flag', 'unknown_query_param')


@pytest.fixture
def proj(tmp_path, monkeypatch):
    (tmp_path / 'data.json').write_text('{"items": [{"n": 1}, {"n": 2}], "name": "x"}', encoding='utf-8')
    (tmp_path / 'rows.json').write_text('[{"name": "a", "n": 1}, {"name": "b", "n": 2}]', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _json(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run, (json.loads(run.stdout) if run.stdout.strip().startswith('{') else {})


def _warnings(doc, *codes):
    return [w for w in (doc.get('meta') or {}).get('warnings') or [] if (w.get('code') or w.get('type')) in codes]


# --- only the data can tell: one shared warning, exit 0 ---------------------------------------------------------

@pytest.mark.parametrize('argv,fields,kind', [
    (('json://data.json?limit=1',), ['limit'], 'an object'),
    (('json://data.json?sort=-n&offset=1',), ['sort', 'offset'], 'an object'),
    (('json://data.json?where=n>1',), ['where'], 'an object'),       # answered silently before
    (('json://data.json?n>1',), ['where'], 'an object'),             # a bare field is the where filter
    (('json://data.json/name?limit=1',), ['limit'], 'a string'),
    (('json', 'data.json', '--limit', '1'), ['limit'], 'an object'),  # the subcommand
    (('json://data.json', '--limit', '1'), ['limit'], 'an object'),   # the URI and a flag
])
def test_an_array_control_on_a_value_that_is_not_a_list_answers_with_the_shared_warning(proj, argv, fields, kind):
    run, doc = _json(*argv)
    assert run.returncode == 0, (run.returncode, run.stderr)
    shared = _warnings(doc, 'control_unread_by_data')
    assert [warning['fields'] for warning in shared] == [fields], doc['meta']['warnings']
    assert f'is {kind}, not a list' in shared[0]['message'], shared
    assert not _warnings(doc, *UNREAD_WARNINGS), doc['meta']['warnings']  # disclosed once, not also as unread


@pytest.mark.parametrize('uri,named', [
    ('json://data.json?bogus=1', "'where' (bogus=1) has"),            # bare field keys: named as typed
    ('json://data.json?n>1&name~=x', "'where' (n>1, name~=x) has"),
    ('json://data.json?where=n>1&m=2', "'where' (m=2) has"),          # only the bare one was folded
    ('json://data.json?where=n>1', "'where' has"),                    # the control's own spelling
    ('json://data.json?bogus=1&limit=1', "'where' (bogus=1), 'limit' have"),
])
def test_the_shared_warning_names_bare_field_keys_as_typed(proj, uri, named):
    run, doc = _json(uri)
    assert run.returncode == 0, run.stderr
    shared = _warnings(doc, 'control_unread_by_data')
    assert shared and shared[0]['message'].startswith(f'{named} no effect on this data: '), shared
    assert shared[0]['fields'][0] == 'where'  # the fields stay canonical
    assert not _warnings(doc, *UNREAD_WARNINGS), doc['meta']['warnings']


def test_the_shared_warning_reaches_the_api_and_the_text_answer(proj):
    from reveal import api
    for answer in (api.query('json://data.json?limit=1'), api.query('json://data.json', limit=1)):
        assert [w['fields'] for w in _warnings(answer, 'control_unread_by_data')] == [['limit']], answer['meta']
    text = _run_reveal_direct('json://data.json?limit=1')
    assert text.returncode == 0, text.stderr
    assert "'limit' has no effect on this data: the value at (root) is an object, not a list" in text.stdout, text.stdout
    assert 'limit' not in without_request_note_lines(text.stderr), text.stderr  # not also the ledger's note (the request note, BACK-2716, aside)


# --- an answer that does not read the control: exit 2, one message ------------------------------------------------

@pytest.mark.parametrize('argv,control,facets', [
    (('json://rows.json?schema&limit=1',), 'limit', 'json_schema, view, view=schema'),     # legacy selector: warned
    (('json://rows.json?flatten&sort=n',), 'sort', 'json_flatten, view, view=flatten'),
    (('json://rows.json?schema&n>1',), 'where (n>1)', 'json_schema, view, view=schema'),  # a bare field: as typed
    (('json://rows.json?gron&data-only&n>1',), 'where (n>1)', 'json_flatten, view, view=flatten'),
    (('json://rows.json?view=schema&where=n>1',), 'where', 'json_schema, view, view=schema'),
    (('json://rows.json?view=keys&offset=1',), 'offset', 'json_keys, view, view=keys'),    # the hand check's text
    (('json', 'rows.json', '--view', 'keys', '--limit', '1'), 'limit', 'json_keys, view, view=keys'),
    (('json://rows.json?detail=raw',), 'detail', 'json_value, default'),
    (('json://rows.json?view=schema&detail=raw',), 'detail', 'json_schema, view, view=schema'),
])
def test_a_control_the_answer_does_not_read_exits_2_naming_where_it_is_read(proj, argv, control, facets):
    run, doc = _json(*argv)
    assert run.returncode == 2, (run.returncode, run.stdout, run.stderr)
    name, _, typed = control.partition(' ')
    named = f"'{name}'" + (f' {typed}' if typed else '')
    assert f"control {named} is not read by this answer ({facets}); {name} is read by: " in run.stderr, \
        run.stderr
    assert doc.get('type', '').startswith('json_'), doc  # the invalid-request document


@pytest.mark.parametrize('uri,overrides', [('json://rows.json?schema&limit=1', {}),
                                           ('json://rows.json', {'view': 'keys', 'limit': 1}),
                                           ('json://rows.json?view=type', {'detail': 'raw'})])
def test_the_api_refuses_the_same_requests(proj, uri, overrides):
    from reveal import api
    with pytest.raises(RequestValidationError, match='is not read by this answer'):
        api.query(uri, **overrides)


# --- negative controls: answers that read the control answer as before ------------------------------------------

@pytest.mark.parametrize('argv,rows', [(('json://rows.json?limit=1',), 1), (('json://data.json/items?sort=-n&limit=1',), 1),
                                       (('json://rows.json?n>1',), 1), (('json', 'rows.json', '--offset', '1'), 1)])
def test_an_array_control_on_a_list_still_applies(proj, argv, rows):
    run, doc = _json(*argv)
    assert run.returncode == 0, run.stderr
    assert len(doc['value']) == rows
    assert not _warnings(doc, 'control_unread_by_data', *UNREAD_WARNINGS), doc['meta']


@pytest.mark.parametrize('uri', ['json://rows.json?gron&data-only', 'json://rows.json?view=flatten&detail=raw',
                                 'json://rows.json?gron&detail=raw'])
def test_the_flatten_answer_still_reads_its_own_controls(proj, uri):
    run = _run_reveal_direct(uri, '--format', 'json')
    assert run.returncode == 0, run.stderr
    # the bare legacy array has no meta to carry the URI request's note, so it is said on stderr (BACK-2716)
    if 'data-only' in uri:  # no canonical form: its own standalone row and gron's, no request note (BACK-2725)
        from reveal.cli.invocation import RETIREMENTS
        assert sorted(run.stderr.splitlines()) == sorted(
            f'note: {RETIREMENTS[key].text}' for key in ('param:json.data-only', 'param:json.gron')), run.stderr
    else:
        assert without_request_note_lines(run.stderr) == '', run.stderr


def test_a_sibling_noun_refuses_through_its_own_declaration(tmp_path, monkeypatch):
    """Markdown declares its answers since group 2d: its links view refuses limit with the same shared message."""
    (tmp_path / 'a.md').write_text('# A\n\n[b](b.md)\n', encoding='utf-8')
    (tmp_path / 'b.md').write_text('# B\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    run, _doc = _json('markdown://.?view=links&limit=1')
    assert run.returncode == 2 and "control 'limit' is not read by this answer" in run.stderr, run.stderr
