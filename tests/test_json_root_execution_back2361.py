"""Direct unqueried JSON roots use owner facts; other JSON operations stay legacy."""
import builtins
import io
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal import api
from reveal.adapters.json import JsonAdapter
from reveal.cli.defaults import _default_args
from reveal.cli.routing.uri import _uri_execution_facts, resolve_uri
from reveal.utils.results import AnalysisCompleteness, FailureCause

pytestmark = pytest.mark.component


@pytest.fixture
def files(tmp_path):
    for name, text in {
        'good.json': '[{"name":"alpha","score":2},{"name":"beta","score":1}]\n',
        'empty.json': '[]\n', 'null.json': 'null\n', 'bad.json': '{"items":[1,}\n',
        'object.json': '{"items":[1,2],"scalar":7}\n',
    }.items():
        (tmp_path / name).write_text(text, encoding='utf-8')
    return tmp_path


def uri(path):
    return 'json://' + path.as_posix()


@pytest.mark.parametrize('name,code,state,cause', [
    ('good.json', 0, AnalysisCompleteness.COMPLETE, None),
    ('empty.json', 0, AnalysisCompleteness.COMPLETE, None),
    ('null.json', 0, AnalysisCompleteness.COMPLETE, None),
    ('bad.json', 3, AnalysisCompleteness.FAILED, FailureCause.ANALYSIS),
    ('missing.json', 2, AnalysisCompleteness.NOT_STARTED, FailureCause.INVALID_REQUEST),
    ('.', 2, AnalysisCompleteness.NOT_STARTED, FailureCause.INVALID_REQUEST),
], ids=['healthy', 'empty', 'null', 'parse-loss', 'missing', 'directory'])
def test_actual_root_answer_identity_exit_and_owner_facts(files, name, code, state, cause):
    target = files / name
    result = run(uri(target), '--format', 'json')
    answer = json.loads(result.stdout)
    assert result.returncode == code, result.stderr
    assert answer['type'] == 'json_value'
    resolved = resolve_uri(uri(target), _default_args(format='json'))
    assert resolved.execution_facts is not None
    assert resolved.execution_facts.completeness is state
    assert resolved.execution_facts.failures == (frozenset({cause}) if cause else frozenset())
    if name == 'good.json':
        assert answer['value'] == [{'name': 'alpha', 'score': 2}, {'name': 'beta', 'score': 1}]
    elif name in ('empty.json', 'null.json'):
        assert answer['value'] == ([] if name == 'empty.json' else None)
    else:
        assert answer['error'] and result.stderr.count('Error (json://)') == 1


def test_bare_root_is_directory_misuse_not_source_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run('json://', '--format', 'json')
    answer = json.loads(result.stdout)
    assert result.returncode == 2 and answer['type'] == 'json_value'
    assert 'needs a JSON file, not a directory' in answer['error']


def test_actual_required_open_loss_repairs_and_keeps_sibling_and_api(files, monkeypatch):
    source = files / 'good.json'
    sibling_uri = uri(files / 'object.json') + '?keys'
    sibling = run(sibling_uri, '--format', 'json')
    clean = api.query(uri(source))
    original = builtins.open
    reached = []

    def denied(file, *args, **kwargs):
        if isinstance(file, (str, os.PathLike)) and Path(file) == source:
            reached.append(file)
            raise PermissionError(13, 'JSON_ROOT_REQUIRED_READ_DENIED', source.as_posix())
        return original(file, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(builtins, 'open', denied)
        failed = run(uri(source), '--format', 'json')
        answer = json.loads(failed.stdout)
        assert reached
        assert failed.returncode == 3 and answer['type'] == 'json_value'
        assert 'JSON_ROOT_REQUIRED_READ_DENIED' in answer['error']
        with pytest.raises(PermissionError, match='JSON_ROOT_REQUIRED_READ_DENIED'):
            api.query(uri(source))
        other = run(sibling_uri, '--format', 'json')
        assert (other.returncode, other.stdout, other.stderr) == (sibling.returncode, sibling.stdout, sibling.stderr)
    assert api.query(uri(source)) == clean
    source.write_text('[{"name":"fresh","score":3}]\n', encoding='utf-8')
    assert api.query(uri(source))['value'] == [{'name': 'fresh', 'score': 3}]
    assert json.loads(run(uri(source), '--format', 'json').stdout)['value'][0]['name'] == 'fresh'


def test_api_exception_and_returned_error_contracts_stay(files):
    with pytest.raises(FileNotFoundError, match='JSON file not found'):
        api.query(uri(files / 'missing.json'))
    with pytest.raises(ValueError, match='not valid JSON'):
        api.query(uri(files / 'bad.json'))
    with pytest.raises(ValueError, match='needs a JSON file'):
        api.query(uri(files))
    with pytest.raises(ValueError, match='non-negative'):
        api.query(uri(files / 'good.json') + '?limit=-1')
    assert api.query(uri(files / 'object.json') + '/absent')['type'] == 'json_error'


@pytest.mark.parametrize('suffix,code,result_type', [
    ('?limit=-1', 1, 'json'), ('?limit=1', 0, 'json_value'),
    ('?keys', 0, 'json_keys'), ('/absent', 1, 'json_error'),
    ('/items[0:1]', 0, 'json_value'), ('?', 0, 'json_value'),
])
def test_queried_navigation_and_introspection_policies_stay_legacy(files, suffix, code, result_type):
    result = run(uri(files / 'object.json') + suffix, '--format', 'json')
    assert result.returncode == code
    assert json.loads(result.stdout)['type'] == result_type
    assert resolve_uri(uri(files / 'object.json') + suffix, _default_args(format='json')).execution_facts is None


def test_excluded_queries_keep_source_before_control_validation(files):
    result = run(uri(files / 'bad.json') + '?limit=-1', '--format', 'json')
    assert result.returncode == 1
    assert 'not valid JSON' in json.loads(result.stdout)['error']
    assert 'non-negative' not in result.stderr


def test_missing_legacy_resource_has_only_the_accepted_diagnostic_delta(files):
    result = run(uri(files / 'missing.json') + '?keys', '--format', 'json')
    answer = json.loads(result.stdout)
    assert result.returncode == 1 and answer['type'] == 'json'
    assert answer['error'] == 'Path not found: ' + (files / 'missing.json').as_posix()
    assert answer['meta']['errors'][0]['code'] == 'adapter_error'


def test_admission_uses_resource_syntax_before_any_content_load(files, monkeypatch):
    from reveal.adapters.json import adapter as owner

    def unexpected(*args, **kwargs):
        pytest.fail('admission attempted to load source content')

    monkeypatch.setattr(owner, 'load_json', unexpected)
    args = _default_args()
    assert callable(_uri_execution_facts(JsonAdapter, (files / 'missing.json').as_posix(), None, args))
    for resource in ('missing.json?keys', 'missing.json?limit=-1', 'missing.json/a', 'missing.json/[0:1]', 'missing.json?'):
        assert _uri_execution_facts(JsonAdapter, resource, None, args) is None
    for flag in ('stdin', 'batch', 'check'):
        assert _uri_execution_facts(JsonAdapter, 'missing.json', None, _default_args(**{flag: True})) is None
    assert _uri_execution_facts(JsonAdapter, 'missing.json', 'scalar', args) is None


def test_element_stdin_and_batch_remain_legacy(files, monkeypatch):
    from reveal.adapters.json.renderer import JsonRenderer
    from reveal.cli.routing.uri import resolve_adapter
    element = resolve_adapter(JsonAdapter, JsonRenderer, 'json',
                              (files / 'object.json').as_posix(), 'scalar', _default_args())
    # The existing JSON renderer has no element route; the resolver keeps the root.
    assert element.execution_facts is None and element.result['value'] == {'items': [1, 2], 'scalar': 7}
    assert api.query(uri(files / 'object.json'), 'scalar')['value'] == 7
    for options, code in ((['--stdin'], 1), (['--stdin', '--batch'], 2)):
        with monkeypatch.context() as context:
            context.setattr('sys.stdin', io.StringIO(uri(files / 'bad.json') + '\n'))
            failed = run(*options, '--format', 'json')
        assert failed.returncode == code
        assert 'not valid JSON' in failed.stdout + failed.stderr


def test_requested_output_failure_and_primary_json_noop_stay(files):
    failed = run(uri(files / 'good.json'), '--output', 'json=' + files.as_posix())
    assert failed.returncode == 3 and 'Requested JSON artifact failed' in failed.stderr
    assert 'alpha' in failed.stdout
    primary = run(uri(files / 'good.json'), '--format', 'json', '--output', 'json=' + files.as_posix())
    assert primary.returncode == 0 and json.loads(primary.stdout)['type'] == 'json_value'
