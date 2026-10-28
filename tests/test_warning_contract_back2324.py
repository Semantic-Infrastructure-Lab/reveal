"""Warnings are typed at construction and qualification, including dynamic entries."""

import copy

import pytest

from reveal.adapters.imports import ImportsAdapter
from reveal.cli.routing.declared import _valid_answer_meta, qualify_declared_answer
from reveal.reveal_types import WarningEntry
from reveal.utils.results import ResultBuilder, note_warning, outcome_of


pytestmark = pytest.mark.contract

BAD_WARNINGS = [{}, {'message': 'untyped warning detail'}, {'type': None},
                {'type': []}, {'type': 1}, {'type': ''}, 'not a warning']


def test_warning_type_is_required_but_error_type_and_warning_code_are_optional():
    from reveal.reveal_types import ErrorEntry

    assert WarningEntry.__required_keys__ == {'type'}
    assert 'code' in WarningEntry.__optional_keys__
    assert 'type' not in ErrorEntry.__required_keys__


@pytest.mark.parametrize('entry', BAD_WARNINGS)
@pytest.mark.parametrize('boundary', ['builder', 'metadata', 'prepared', 'writer'])
def test_malformed_dynamic_warning_is_rejected_at_each_writer(entry, boundary):
    # Copying models warnings assembled after the literal-only source guard ran.
    entry = copy.deepcopy(entry)
    result = {}
    with pytest.raises(ValueError, match='warning'):
        if boundary == 'builder':
            ResultBuilder.create('imports', '.', warnings=[entry])
        elif boundary == 'metadata':
            ResultBuilder.create_meta(warnings=[entry])
        elif boundary == 'prepared':
            ResultBuilder.create('imports', '.', meta={'warnings': [entry]})
        else:
            note_warning(result, entry)
    assert result == {}, 'failed writes must not change the answer'


@pytest.mark.parametrize('entries', [{}, (), 'bad', 0])
def test_builder_does_not_ignore_falsey_invalid_warning_collections(entries):
    with pytest.raises(ValueError, match='warning'):
        ResultBuilder.create('imports', '.', warnings=entries)


@pytest.mark.parametrize('entry', BAD_WARNINGS)
def test_qualification_reports_malformed_warning_without_reemitting_it(entry):
    valid = {'type': 'custom_kind', 'message': 'retained good warning'}
    original = ResultBuilder.create('imports', '.', warnings=[valid])
    original['meta']['warnings'].append(copy.deepcopy(entry))
    before = copy.deepcopy(original)

    assert not _valid_answer_meta(original['meta'])
    repaired = qualify_declared_answer(original, ImportsAdapter, '.', 'imports')

    assert outcome_of(repaired) == 'failed'
    assert repaired['meta']['warnings'] == [valid]
    assert any(error.get('code') == 'invalid_adapter_answer'
               for error in repaired['meta']['errors'])
    assert any('Invalid warning diagnostic' in error.get('message', '')
               for error in repaired['meta']['errors'])
    if isinstance(entry, dict) and entry.get('message'):
        assert any(entry['message'] in error.get('message', '')
                   for error in repaired['meta']['errors'])
    assert original == before, 'qualification must not mutate the child diagnostics'
    assert _valid_answer_meta(repaired['meta'])


def test_invalid_warning_narrative_is_bounded():
    original = ResultBuilder.create('imports', '.', warnings=[])
    original['meta'] = {'warnings': [{'message': 'retained prefix ' + 'x' * 10_000}] * 100}
    repaired = qualify_declared_answer(original, ImportsAdapter, '.', 'imports')
    messages = [error.get('message', '') for error in repaired['meta']['errors']]
    assert any('retained prefix' in message for message in messages)
    assert sum(map(len, messages)) < 1500
    assert _valid_answer_meta(repaired['meta'])


def test_valid_warning_and_independent_partial_error_survive_unchanged():
    warning = {'type': 'custom_kind', 'message': 'valid without a catalog code'}
    error = {'code': 'E_PARSE', 'message': 'one file could not be parsed'}
    answer = ResultBuilder.create('imports', '.', warnings=[warning], errors=[error])
    assert _valid_answer_meta(answer['meta'])
    assert qualify_declared_answer(answer, ImportsAdapter, '.', 'imports') is answer
    assert answer['meta']['warnings'] == [warning]
    assert answer['meta']['errors'] == [error]
    assert outcome_of(answer) == 'ok'
    note_warning(answer, warning)
    assert answer['meta']['warnings'] == [warning]


def test_warning_message_is_not_a_new_required_field():
    warning = {'type': 'custom_kind'}
    answer = ResultBuilder.create('imports', '.', warnings=[warning])
    assert qualify_declared_answer(answer, ImportsAdapter, '.', 'imports') is answer


def test_none_writer_entry_remains_an_explicit_noop():
    answer = {}
    note_warning(answer, None)
    assert answer == {}


@pytest.mark.parametrize('errors', [[None], [{'type': []}], 'not a list'])
def test_error_diagnostic_shape_is_validated_separately(errors):
    with pytest.raises(ValueError, match='error'):
        ResultBuilder.create('imports', '.', errors=errors)


def test_empty_error_and_optional_string_type_keep_existing_contract():
    errors = [{}, {'type': '', 'message': 'legacy typed error'}]
    answer = ResultBuilder.create('imports', '.', errors=errors)
    assert _valid_answer_meta(answer['meta'])
    assert answer['meta']['errors'] == errors
