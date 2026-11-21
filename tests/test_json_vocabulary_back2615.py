"""BACK-2615: json's vocabulary under D20.

The first bare words of a json:// query (?schema ?flatten ?gron ?type ?keys ?length) are legacy spellings of
--view; each answers as its view with a note naming it, one view named twice is one setting, and two different
views exit 2 naming both. A dataset field called ``type`` stays a data predicate.
"""
import json

import pytest
from conftest import _run_reveal_direct as run, without_request_notes

VIEWS = {'schema': 'schema', 'flatten': 'flatten', 'gron': 'flatten', 'type': 'type', 'keys': 'keys',
         'length': 'length'}


@pytest.fixture
def rows(tmp_path):
    path = tmp_path / 'rows.json'
    path.write_text(json.dumps([{'type': 'a', 'n': 1}, {'type': 'b', 'n': 2}]), encoding='utf-8')
    return path


def _answer(*argv):
    response = run(*argv, '--format', 'json')
    return response.returncode, (json.loads(response.stdout) if response.stdout.strip() else None), response.stderr


def _note(answer):
    return [w for w in answer['meta']['warnings'] if w.get('field') == 'request:json']


@pytest.mark.parametrize('word,view', sorted(VIEWS.items()))
def test_bare_selector_is_the_view_with_its_note(rows, word, view):
    code, new, _ = _answer('json', str(rows), '--view', view)
    legacy_code, old, _ = _answer(f'json://{rows}?{word}')
    assert code == legacy_code == 0
    assert [w['replacement'] for w in _note(old)] == [f'reveal json://{rows} --view {view}']
    assert _note(new) == []
    assert without_request_notes(old) == new


@pytest.mark.parametrize('word,view', sorted(VIEWS.items()))
def test_selector_and_the_same_view_are_one_setting(rows, word, view):
    code, both, _ = _answer(f'json://{rows}?{word}&view={view}')
    _, single, _ = _answer(f'json://{rows}?view={view}')
    assert code == 0 and without_request_notes(both) == without_request_notes(single)


def test_selector_and_a_different_view_exit_2_naming_both(rows):
    code, doc, err = _answer(f'json://{rows}?keys&view=schema')
    assert code == 2
    assert 'keys' in (err + json.dumps(doc)) and 'view' in (err + json.dumps(doc))


def test_a_type_field_stays_a_data_predicate(rows):
    code, doc, _ = _answer(f'json://{rows}?type=a')
    assert code == 0 and doc['type'] == 'json_value' and doc['value'] == [{'type': 'a', 'n': 1}]
    assert _note(doc) and 'view' not in _note(doc)[0]['replacement']
