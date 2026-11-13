"""JSON declarations keep dataset fields separate from first-token inspection selectors."""
import json

import pytest

from conftest import _run_reveal_in


@pytest.fixture
def data(tmp_path):
    (tmp_path / 'data.json').write_text(json.dumps({'items': [
        {'type': 'book', 'n': 1}, {'type': 'photo', 'n': 3}], 'flag': False, 'nothing': None}), encoding='utf-8')
    return tmp_path


def answer(data, *argv):
    result = _run_reveal_in(data, *argv, '--format', 'json')
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_cli_uri_api_filter_and_zero_overrides(data):
    from reveal.api import query
    a = answer(data, 'json', 'data.json/items', '--where', 'n>1', '--sort=-n')
    b = answer(data, 'json://data.json/items?where=n%3E1&sort=-n')
    assert a == b and a['value'] == [{'type': 'photo', 'n': 3}]
    uri = f'json://{data / "data.json"}/items?limit=1'
    assert query(uri, limit=0)['value'] == []
    assert len(query(uri)['value']) == 1


def test_type_field_filter_is_not_a_view_selector(data):
    a = answer(data, 'json://data.json/items?type=book')
    b = answer(data, 'json', 'data.json/items', '--where', 'type=book')
    assert a == b and a['type'] == 'json_value'
    assert a['value'] == [{'type': 'book', 'n': 1}]


@pytest.mark.parametrize('view', ['schema', 'flatten', 'type', 'keys', 'length'])
def test_existing_inspection_views_share_generated_bindings(data, view):
    a = answer(data, 'json', 'data.json', '--view', view)
    b = answer(data, 'json://data.json?view=' + view)
    assert a == b and a['type'] == 'json_' + view


def test_first_bare_legacy_selector_and_type_field_stay_distinct(data):
    inspection = answer(data, 'json://data.json/items?type')
    assert inspection['type'] == 'json_type'
    filtered = answer(data, 'json://data.json/items?type=book')
    assert filtered['type'] == 'json_value' and len(filtered['value']) == 1


def test_invalid_inspection_target_is_usage_and_bad_bytes_are_analysis(data):
    result = _run_reveal_in(data, 'json', 'data.json/flag', '--view', 'keys', '--format', 'json')
    assert result.returncode == 2
    assert json.loads(result.stdout)['type'] == 'json_keys'
    (data / 'broken.json').write_text('{bad', encoding='utf-8')
    result = _run_reveal_in(data, 'json', 'broken.json', '--view', 'schema', '--format', 'json')
    assert result.returncode == 3
    assert json.loads(result.stdout)['type'] == 'json_schema'


def test_raw_flatten_preserves_legacy_array_and_canonical_envelope(data):
    sink = data / 'legacy-output.json'
    legacy = answer(data, 'json://data.json?flatten&data-only', '--also-json', str(sink))
    assert isinstance(legacy, list) and legacy == json.loads(sink.read_text(encoding='utf-8'))
    canonical = answer(data, 'json', 'data.json', '--view', 'flatten', '--detail', 'raw')
    assert canonical['lines'] == legacy and canonical['type'] == 'json_flatten'
    text = _run_reveal_in(data, 'json', 'data.json', '--view', 'flatten', '--detail', 'raw')
    assert text.returncode == 0 and '# File:' not in text.stdout
    assert text.stdout.splitlines() == legacy


@pytest.mark.parametrize('spelling', ['cli', 'uri'])
def test_bad_source_precedes_bad_controls_in_both_spellings(data, spelling):
    (data / 'broken.json').write_text('{bad', encoding='utf-8')
    argv = ['json', 'broken.json', '--limit', '-1'] if spelling == 'cli' else ['json://broken.json?limit=-1']
    result = _run_reveal_in(data, *argv, '--format', 'json')
    assert result.returncode == 3
    assert 'invalid_request' not in result.stdout


@pytest.mark.parametrize('flag', ['--exclude=*.json', '--no-gitignore'])
def test_file_reader_rejects_walking_flags(data, flag):
    for argv in (['json', 'data.json'], ['json://data.json']):
        result = _run_reveal_in(data, *argv, flag, '--format', 'json')
        assert result.returncode == 2
        assert flag.partition('=')[0] in result.stderr + result.stdout


def test_api_legacy_inspection_ignores_old_array_controls(data):
    from reveal.api import query
    result = query(f'json://{data / "data.json"}?keys&limit=-1')
    assert result['keys'] == ['items', 'flag', 'nothing']


@pytest.mark.parametrize('view,field', [('schema', 'schema'), ('flatten', 'line_count'),
                                       ('keys', 'count'), ('type', 'value_type'), ('length', 'length')])
def test_inspection_postprocessing_cannot_erase_required_observations(data, monkeypatch, view, field):
    from reveal.adapters.json.adapter import JsonAdapter
    def erase(self, result, args):
        result[field] = None
        return result
    monkeypatch.setattr(JsonAdapter, 'post_process', erase, raising=False)
    result = _run_reveal_in(data, 'json', 'data.json', '--view', view, '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


@pytest.mark.parametrize('filename', ['percent%20 #雪.json', 'percent%20?source.json'])
def test_encoded_source_selector_and_literal_typed_question_mark(data, filename):
    from reveal.api import query
    from urllib.parse import quote
    from filename_fixture import require_filename
    literal = data / filename
    require_filename(literal)
    literal.write_text('{"answer": 42}', encoding='utf-8')
    canonical = answer(data, 'json', str(literal) + '/answer')
    encoded = quote(str(literal), safe='/')
    assert query('json://' + encoded + '/answer')['value'] == canonical['value'] == 42


def test_typed_override_cannot_hide_an_invalid_original_predicate(data):
    from reveal.api import query
    with pytest.raises(ValueError, match='regular expression'):
        query(f'json://{data / "data.json"}/items?n~=[', where=['n>1'])
