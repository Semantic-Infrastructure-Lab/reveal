"""Real Surface answers establish typed API overlay admission and precedence."""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.adapters.surface import SurfaceAdapter
from reveal.utils.query_parser import collect_query_keys, peek_query_items


@pytest.fixture
def project(tmp_path):
    source = tmp_path / 'pkg' / 'nested' / 'app.py'
    source.parent.mkdir(parents=True)
    source.write_text('import os\nvalue = os.getenv("PRODUCTION_VAR")\n', encoding='utf-8')
    tests = tmp_path / 'tests'
    tests.mkdir()
    (tests / 'test_app.py').write_text('import os\nvalue = os.getenv("TEST_VAR")\n', encoding='utf-8')
    return tmp_path


def uri(root, query='type=env'):
    return f'surface://{root.as_posix()}?{query}'


def names(answer):
    return {entry['name'] for entry in answer['surfaces'].get('env', [])}


def test_api_source_only_matches_supported_uri_constructor_and_command(project):
    expected = api.query(uri(project, 'type=env&source_only=true'))
    constructor = SurfaceAdapter(str(project), params={'type': 'env', 'source_only': True}).get_structure()
    command = _run_reveal_direct('surface', str(project), '--type', 'env', '--source-only', '--format', 'json')
    assert command.returncode == 0
    assert expected == constructor == json.loads(command.stdout)
    actual = api.query(uri(project), source_only=True)
    assert names(actual) == {'PRODUCTION_VAR'}
    assert actual == expected
    assert actual['scope']['total_code_files'] == 2


@pytest.mark.parametrize('raw,override,expected', [
    ('true', False, {'PRODUCTION_VAR', 'TEST_VAR'}),
    ('false', True, {'PRODUCTION_VAR'}),
    ('true', None, {'PRODUCTION_VAR', 'TEST_VAR'}),
])
def test_explicit_boolean_and_none_override_uri(project, raw, override, expected):
    assert names(api.query(uri(project, 'type=env&source_only=' + raw), source_only=override)) == expected


def test_omission_leaves_bound_uri_and_zero_changes_actual_group(project):
    assert names(api.query(uri(project, 'type=env&source_only=true'))) == {'PRODUCTION_VAR'}
    grouped = uri(project, 'type=env&source_only=true&by=dir&depth=1')
    assert [row['dir'] for row in api.query(grouped)['by_dir']] == ['pkg']
    for value in (0, None):
        answer = api.query(grouped, depth=value)
        assert [row['dir'] for row in answer['by_dir']] == ['pkg/nested']


@pytest.mark.parametrize('query,overrides', [
    ('type=env', {'depth': -1}),
    ('type=env&depth=-1', {'depth': 0}),
])
def test_invalid_typed_or_shadowed_uri_depth_rejects_before_scan(project, monkeypatch, query, overrides):
    from reveal.adapters import surface
    original = surface._scan_surface
    calls = []
    def scan(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(surface, '_scan_surface', scan)
    with pytest.raises(ValueError, match='depth'):
        api.query(uri(project, query), **overrides)
    assert calls == []


def test_unknown_api_keyword_rejects(project):
    with pytest.raises(TypeError, match='nonsense'):
        api.query(uri(project), nonsense=True)


def test_direct_method_keyword_rejects_without_mutating_adapter(project):
    adapter = SurfaceAdapter(str(project), 'type=env')
    with pytest.raises(TypeError, match='source_only'):
        adapter.get_structure(source_only=True)
    assert names(adapter.get_structure()) == {'PRODUCTION_VAR', 'TEST_VAR'}


def test_top_zero_and_none_do_not_cut_raw_analysis(project):
    complete = api.query(uri(project))
    assert api.query(uri(project), top=0) == complete
    assert api.query(uri(project, 'type=env&top=0'), top=None) == complete
    assert complete['total'] == 2


def test_reused_constructor_binding_and_read_tracking_remain_unchanged(project):
    with collect_query_keys() as log:
        adapter = SurfaceAdapter(str(project), 'type=env&source_only=true&top=0')
        before = list(peek_query_items(adapter.query_params))
        assert not log.used
        first = adapter.get_structure()
        assert 'top' not in log.used
        assert names(api.query(uri(project), source_only=False)) == {'PRODUCTION_VAR', 'TEST_VAR'}
        assert adapter.get_structure() == first
        assert list(peek_query_items(adapter.query_params)) == before


def test_api_overlay_analysis_stays_inside_host_request(project, monkeypatch):
    from reveal.adapters import surface
    from reveal.utils.request_cache import in_host_request
    original = surface._scan_surface
    observed = []
    def scan(*args, **kwargs):
        observed.append(in_host_request())
        return original(*args, **kwargs)
    monkeypatch.setattr(surface, '_scan_surface', scan)
    assert names(api.query(uri(project), source_only=True)) == {'PRODUCTION_VAR'}
    assert observed == [True]


def test_legacy_structure_element_and_check_forwarding_are_unchanged(monkeypatch):
    from reveal.adapters import base
    from reveal.cli.defaults import _default_args
    from reveal.cli.routing.uri import _build_check_kwargs
    class Legacy:
        LEGACY_INIT = False
        def __init__(self, resource, query=None):
            self.resource = resource
        def get_structure(self, **kwargs):
            return {'received': kwargs}
        def get_element(self, name, **kwargs):
            return {'name': name, 'received': kwargs}
        def check(self, **kwargs):
            return kwargs
    original = base.get_adapter_class
    monkeypatch.setattr(base, 'get_adapter_class', lambda scheme: Legacy if scheme == 'overlay-legacy' else original(scheme))
    assert api.query('overlay-legacy://resource', nonsense=False) == {'received': {'nonsense': False}}
    assert api.query('overlay-legacy://resource', element_name='entry', depth=0) == {
        'name': 'entry', 'received': {'depth': 0}}
    kwargs = _build_check_kwargs(Legacy('resource'), _default_args(select='A,B', advanced=False))
    assert kwargs['select'] == ['A', 'B'] and kwargs['advanced'] is False


def test_api_raw_resource_spelling_and_literal_constructor_path_remain(project):
    literal = project / 'literal%26+value'
    literal.mkdir()
    (literal / 'app.py').write_text('import os\nx=os.getenv("LITERAL_VAR")\n', encoding='utf-8')
    answer = api.query(uri(literal), source_only=True)
    assert names(answer) == {'LITERAL_VAR'}
    assert answer['source'] == literal.as_posix()
    # Typed construction never serializes a literal question mark into a query.
    adapter = SurfaceAdapter(str(project) + '?literal%26+', params={'type': 'env'})
    assert adapter.path == str(project) + '?literal%26+'


def test_unknown_uri_key_still_warns_and_ignores(project, capsys):
    answer = api.query(uri(project, 'type=env&nonsense=true'))
    assert names(answer) == {'PRODUCTION_VAR', 'TEST_VAR'}
    assert "Unknown query param 'nonsense'" in capsys.readouterr().err


def test_overlay_constructs_once(project, monkeypatch):
    original = SurfaceAdapter.__init__
    constructed = []
    def initialize(self, *args, **kwargs):
        constructed.append(True)
        original(self, *args, **kwargs)
    monkeypatch.setattr(SurfaceAdapter, '__init__', initialize)
    answer = api.query(uri(project), source_only=True)
    assert constructed == [True]
    assert names(answer) == {'PRODUCTION_VAR'}


def test_api_does_not_adopt_uri_resource_decoding(project):
    decoded = project / 'literal space'
    decoded.mkdir()
    (decoded / 'app.py').write_text('import os\nx=os.getenv("DECODED_VAR")\n', encoding='utf-8')
    encoded = project / 'literal%20space'
    baseline = api.query(uri(encoded))
    answer = api.query(uri(encoded), source_only=True)
    assert baseline['total'] == answer['total'] == 0
    assert baseline['source'] == answer['source'] == encoded.as_posix()


def test_typed_type_and_grouping_controls_match_supported_uri(project):
    expected = api.query(uri(project, 'type=env&by=dir&depth=0'))
    answer = api.query(uri(project, 'type=fs'), type='env', by='dir', depth=0)
    assert names(answer) == {'PRODUCTION_VAR', 'TEST_VAR'}
    assert answer == expected


def test_explicit_none_type_restores_declared_default(project):
    expected = api.query(uri(project, ''))
    assert names(expected) == {'PRODUCTION_VAR', 'TEST_VAR'}
    assert api.query(uri(project, 'type=fs'), type=None) == expected
