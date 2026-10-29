"""JSON request errors keep operation identity and use owner execution facts."""
import builtins
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal import api
from reveal.adapters.json import JsonAdapter
from reveal.cli.defaults import _default_args
from reveal.cli.routing.uri import resolve_uri
from reveal.errors import RequestValidationError
from reveal.utils.results import FailureCause

pytestmark = pytest.mark.component


@pytest.fixture
def source(tmp_path):
    path = tmp_path / 'data.json'
    path.write_text('{"items":[{"n":2},{"n":1}],"scalar":7}', encoding='utf-8')
    return path


def uri(path, suffix=''):
    return 'json://' + path.as_posix() + suffix


@pytest.mark.parametrize('suffix', [
    '/absent', '/items[99]', '/scalar/child', '?unknown',
    '?limit=-1', '?offset=bad', '/items?n~=[', '/items[-:]',
])
def test_invalid_request_is_two_with_canonical_identity(source, suffix):
    response = run(uri(source, suffix), '--format', 'json')
    assert response.returncode == 2, (response.stdout, response.stderr)
    answer = json.loads(response.stdout)
    assert answer['type'] == 'json_value' and answer['error']
    assert response.stderr.count('Error (json://)') == 1
    assert 'Traceback' not in response.stderr
    resolved = resolve_uri(uri(source, suffix), _default_args())
    assert resolved.execution_facts.failures == frozenset({FailureCause.INVALID_REQUEST})
    assert resolved.public_diagnostic


def test_python_api_returns_canonical_errors_and_typed_validation(source):
    for suffix in ('/absent', '?unknown', '/items[99]'):
        result = api.query(uri(source, suffix))
        assert result['type'] == 'json_value' and result['error']
        assert result['meta']['errors'][0]['code'] == 'invalid_request'
    for suffix in ('?limit=-1', '?offset=bad', '/items?n~=[', '/items[-:]'):
        with pytest.raises(RequestValidationError):
            api.query(uri(source, suffix))


@pytest.mark.parametrize('suffix', ['/absent', '?limit=-1', '/items?sort=n&limit=1'])
def test_required_source_failure_precedes_controls_and_navigation(source, suffix):
    source.write_text('{PRIVATE_SOURCE_PARSE', encoding='utf-8')
    response = run(uri(source, suffix), '--format', 'json')
    assert response.returncode == 3
    answer = json.loads(response.stdout)
    assert answer['type'] == 'json_value' and 'not valid JSON' in answer['error']
    assert 'non-negative' not in response.stderr
    with pytest.raises(ValueError) as raised:
        api.query(uri(source, suffix))
    assert not isinstance(raised.value, RequestValidationError)


def test_selector_validation_precedes_content_and_preflight_only_resolves_file(source):
    assert JsonAdapter.resource_path(str(source) + '/items[-:]') == source.as_posix()
    source.write_text('{INVALID', encoding='utf-8')
    response = run(uri(source, '/items[-:]'), '--format', 'json')
    assert response.returncode == 2 and 'slice' in json.loads(response.stdout)['error'].lower()
    assert 'not valid JSON' not in response.stderr
    # Legacy introspection also avoids the old preflight traceback, retaining exit 1.
    legacy = run(uri(source, '/items[-:]?keys'), '--format', 'json')
    assert legacy.returncode == 1 and 'Traceback' not in legacy.stderr
    assert 'slice' in json.loads(legacy.stdout)['error'].lower()


def test_read_loss_repair_and_fresh_calls(source, monkeypatch):
    request = uri(source, '/items?sort=n&limit=1')
    original = builtins.open
    reached = []

    def denied(file, *args, **kwargs):
        if isinstance(file, (str, Path)) and Path(file) == source:
            reached.append(file)
            raise PermissionError(13, 'PUBLIC_QUERY_READ_DENIED', str(file))
        return original(file, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(builtins, 'open', denied)
        response = run(request, '--format', 'json')
        assert reached and response.returncode == 3
        assert 'PUBLIC_QUERY_READ_DENIED' in response.stdout + response.stderr
    good = run(request, '--format', 'json')
    answer = json.loads(good.stdout)
    assert good.returncode == 0 and answer['value'] == [{'n': 1}]
    assert answer['total_matches'] == 2 and answer['displayed_results'] == 1
    assert answer['meta']['warnings'][0]['type'] == 'truncated'
    source.write_text('{"items":[{"n":9}]}', encoding='utf-8')
    assert api.query(request)['value'] == [{'n': 9}]
    source.unlink()
    assert run(request, '--format', 'json').returncode == 2


@pytest.mark.parametrize('value', [[], {}, None, 7])
def test_empty_null_scalar_and_no_match_are_complete(source, value):
    source.write_text(json.dumps(value), encoding='utf-8')
    response = run(uri(source, '?limit=0'), '--format', 'json')
    assert response.returncode == 0 and json.loads(response.stdout)['value'] == value
    source.write_text('[{"n":1}]', encoding='utf-8')
    response = run(uri(source, '?n=2'), '--format', 'json')
    assert response.returncode == 0 and json.loads(response.stdout)['value'] == []


@pytest.mark.parametrize('forgery', ['malformed', 'postprocess', 'postprocess_inplace'])
def test_repair_and_postprocessing_cannot_manufacture_request_rejection(source, monkeypatch, forgery):
    def rejection():
        return {'type': 'json_value', 'source': source.as_posix(), 'source_type': 'file',
                'contract_version': '1.1', 'error': 'FORGED_REQUEST',
                'meta': {'errors': [{'code': 'invalid_request', 'message': 'FORGED_REQUEST'}]}}

    if forgery == 'malformed':
        result = rejection()
        result['scope'] = []
        monkeypatch.setattr(JsonAdapter, 'get_structure', lambda self, **kw: result)
    else:
        def processed(self, result, args):
            forged = rejection()
            if forgery == 'postprocess_inplace':
                result.clear()
                result.update(forged)
                return result
            return forged
        monkeypatch.setattr(JsonAdapter, 'post_process', processed)
    response = run(uri(source, '/items'), '--format', 'json')
    assert response.returncode == 3
    answer = json.loads(response.stdout)
    assert any(e['code'] == 'invalid_adapter_answer' for e in answer['meta']['errors'])
    assert resolve_uri(uri(source, '/items'), _default_args()).public_diagnostic is None


def test_excluded_introspection_and_ordinary_warnings_keep_meaning(source):
    for suffix, result_type in [('?keys&limit=-1', 'json_keys'), ('?schema', 'json_schema'),
                                ('?gron&data-only', None)]:
        response = run(uri(source, suffix), '--format', 'json')
        assert response.returncode == 0
        answer = json.loads(response.stdout)
        assert isinstance(answer, list) if result_type is None else answer['type'] == result_type
        assert resolve_uri(uri(source, suffix), _default_args()).execution_facts is None
    response = run(uri(source, '/items?missing=1'), '--format', 'json')
    answer = json.loads(response.stdout)
    assert response.returncode == 0 and answer['value'] == []
    assert answer['meta']['warnings'][0]['type'] == 'unknown_filter_field'


def test_projection_cannot_drop_failure_and_requested_output_failure_wins(source, tmp_path):
    response = run(uri(source, '/absent'), '--fields', 'type', '--format', 'json')
    assert response.returncode == 2
    assert json.loads(response.stdout)['type'] == 'json_value'
    response = run(uri(source, '/items'), '--output', 'json=' + tmp_path.as_posix())
    assert response.returncode == 3 and 'Requested JSON artifact failed' in response.stderr
