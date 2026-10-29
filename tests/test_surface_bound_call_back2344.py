"""Surface binds declared API controls before its zero-argument analysis call."""
import inspect
import json
from types import SimpleNamespace

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.adapters.base import ResourceAdapter
from reveal.adapters.factory import _canonical_init
from reveal.adapters.surface import SurfaceAdapter
from reveal.utils.query_parser import QueryParams, collect_query_keys


@pytest.fixture
def project(tmp_path):
    for name, key in [('src/deep/code.py', 'PRODUCTION'), ('tests/test_code.py', 'TESTING')]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'import os\nVALUE = os.getenv("{key}")\n', encoding='utf-8')
    return tmp_path


def query(project, controls='type=env', **kwargs):
    return api.query(f'surface://{project}?{controls}', **kwargs)


def directories(result):
    return {row['dir'] for row in result['by_dir']}


def test_actual_source_only_api_override_applies(project):
    result = query(project, source_only=True)
    assert result['total'] == 1
    assert result['surfaces']['env'][0]['file'] == 'src/deep/code.py'


def test_false_zero_none_and_omission_preserve_precedence(project):
    assert query(project, 'type=env&source_only=true', source_only=False)['total'] == 2
    assert query(project, 'type=env&source_only=true')['total'] == 1
    assert query(project, 'type=env&source_only=true', source_only=None)['total'] == 2
    assert directories(query(project, 'type=env&by=dir&depth=1', depth=0)) == {'src/deep', 'tests'}
    assert directories(query(project, 'type=env&by=dir&depth=1')) == {'src', 'tests'}


def test_typed_grouping_depth_and_type_change_real_records(project):
    result = query(project, by='dir', depth=1, source_only=True)
    assert directories(result) == {'src'} and result['total'] == 1
    assert query(project, type='fs')['total'] == 0


@pytest.mark.parametrize('kwargs', [{'depth': -1}, {'depth': True}, {'top': False}, {'type': 'unknown'}])
def test_typed_invalid_values_reject_before_scan(project, kwargs):
    with pytest.raises(ValueError):
        query(project, **kwargs)


def test_unknown_api_keys_reject_and_invalid_uri_cannot_be_shadowed(project):
    with pytest.raises(TypeError, match='nonsense'):
        query(project, nonsense=True)
    with pytest.raises(ValueError, match='depth'):
        query(project, 'depth=-1', depth=0)


def test_direct_method_kwargs_reject_constructor_controls_work(project):
    adapter = SurfaceAdapter(str(project), params={'type': 'env', 'source_only': True})
    assert adapter.get_structure()['total'] == 1
    with pytest.raises(TypeError, match='source_only'):
        adapter.get_structure(source_only=False)
    assert adapter.get_structure()['total'] == 1


def test_top_zero_remains_presentation_only(project):
    result = query(project, top=0)
    assert result['total'] == 2 and len(result['surfaces']['env']) == 2
    assert query(project, 'type=env&top=0')['surfaces'] == result['surfaces']


def test_existing_uri_constructor_and_legacy_siblings(project, monkeypatch):
    native = SurfaceAdapter(str(project), 'type=env&source_only=true').get_structure()
    assert native['total'] == 1
    response = _run_reveal_direct(f'surface://{project}?type=env&source_only=true', '--format', 'json')
    assert response.returncode == 0 and json.loads(response.stdout)['surfaces'] == native['surfaces']
    class Plugin(ResourceAdapter):
        @classmethod
        def from_uri(cls, scheme, resource, element=None):
            return SimpleNamespace(get_structure=lambda **kwargs: {'legacy': kwargs},
                                   get_element=lambda name, **kwargs: {'element': name, 'legacy': kwargs})
        def get_structure(self, **kwargs):
            return kwargs
    monkeypatch.setattr('reveal.adapters.base.get_adapter_class', lambda scheme: Plugin)
    assert api.query('plugin://resource', custom=0) == {'legacy': {'custom': 0}}
    assert api.query('plugin://resource', 'item', custom=False) == {'element': 'item', 'legacy': {'custom': False}}


def test_surface_subclass_custom_from_uri_is_not_inherited_adoption(project, monkeypatch):
    class Plugin(SurfaceAdapter):
        @classmethod
        def from_uri(cls, scheme, resource, element=None):
            return SimpleNamespace(get_structure=lambda **kwargs: {'custom_factory': resource, 'kwargs': kwargs})
    monkeypatch.setattr('reveal.adapters.base.get_adapter_class', lambda scheme: Plugin)
    assert api.query('plugin://literal?path', custom=False) == {
        'custom_factory': 'literal?path', 'kwargs': {'custom': False}}


def test_factory_overlay_preserves_existing_resource_codec_and_single_construction(project):
    calls = []
    class Target(SurfaceAdapter):
        def __init__(self, resource, query=None, *, params=None):
            calls.append((resource, query, params))
            super().__init__(resource, query, params=params)
    adapter = _canonical_init(Target, f'{project}?type=env', overrides={'source_only': True})
    assert len(calls) == 1 and calls[0][0] == str(project) and calls[0][1] is None
    assert adapter.get_structure()['total'] == 1
    bound = QueryParams({'type': 'env'})
    literal = _canonical_init(Target, 'literal?name%26+path', params=bound)
    assert literal.path == 'literal?name%26+path' and literal.query_params is bound
    with pytest.raises(TypeError):
        _canonical_init(Target, str(project), params=bound, overrides={})


@pytest.mark.parametrize('spelling', ['plus+path', 'percent%26path'])
def test_api_keeps_literal_resource_spelling(project, spelling):
    path = project / spelling
    path.mkdir()
    (path / 'code.py').write_text('import os\nVALUE = os.getenv("LITERAL")\n', encoding='utf-8')
    assert query(path, source_only=True)['total'] == 1


def test_typed_calls_do_not_mutate_reused_adapter_or_consume_top(project):
    original = SurfaceAdapter(str(project), 'type=env&source_only=true')
    before = original.get_structure()
    assert query(project, source_only=False)['total'] == 2
    assert original.get_structure() == before
    with collect_query_keys() as keys:
        assert query(project, source_only=True, top=0)['total'] == 1
        assert 'source_only' in keys.used and 'top' not in keys.used


def test_adopter_callable_and_class_local_capability():
    from reveal.adapters.factory import uses_bound_query_call
    from reveal.adapters.registry import BUILTIN_SCHEMES
    from reveal.adapters.base import get_adapter_class
    adopted = {get_adapter_class(scheme) for scheme in BUILTIN_SCHEMES
               if uses_bound_query_call(get_adapter_class(scheme))}
    assert adopted == {SurfaceAdapter, get_adapter_class('contracts')}
    assert list(inspect.signature(SurfaceAdapter.get_structure).parameters) == ['self']
    assert SurfaceAdapter.__dict__['BOUND_QUERY_CALL'] is True
    assert ResourceAdapter.BOUND_QUERY_CALL is False
    assert 'from_uri' not in SurfaceAdapter.__dict__
    assert {spec.name for spec in SurfaceAdapter.PARAM_SPECS} == {'type', 'source_only', 'by', 'depth', 'top'}
    class Child(SurfaceAdapter):
        pass
    assert not uses_bound_query_call(Child)


def test_bound_uri_and_declared_calls_bypass_legacy_kwargs_builder(project, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('bound operation reached legacy keyword forwarding')
    monkeypatch.setattr('reveal.cli.routing.uri._build_adapter_kwargs', forbidden)
    for argv in [(f'surface://{project}?type=env&source_only=true',),
                 ('surface', str(project), '--type', 'env', '--source-only')]:
        response = _run_reveal_direct(*argv, '--format', 'json')
        assert response.returncode == 0 and json.loads(response.stdout)['total'] == 1


def test_uri_unknowns_remain_disclosed_and_api_question_split_stays_legacy(project, capsys):
    result = query(project, 'type=env&unrecognized=example', source_only=True)
    assert result['total'] == 1
    assert "Unknown query param 'unrecognized'" in capsys.readouterr().err
    calls = []
    class Target:
        CANONICAL_EMPTY_RESOURCE = '.'
        PARAM_SPECS = SurfaceAdapter.PARAM_SPECS
        def __init__(self, resource, query=None, *, params=None):
            calls.append((resource, query, params))
    _canonical_init(Target, 'literal?name?type=env', overrides={})
    assert calls[0][0] == 'literal'
    assert calls[0][2]['name?type'] == 'env'


def test_bare_kwargs_inventory_ratchet_and_surface_mutation():
    import ast
    from scripts.check_boundaries import ROOT, compare, find_sites
    baseline = json.loads((ROOT / 'scripts/boundary_baseline.json').read_text(encoding='utf-8'))
    rule = 'bare-get-structure-kwargs'
    identities = []
    for path in sorted((ROOT / 'reveal/adapters').rglob('*.py')):
        source = path.read_text(encoding='utf-8')
        sites = find_sites(source, path.relative_to(ROOT).as_posix())[rule]
        for cls in ast.walk(ast.parse(source)):
            if isinstance(cls, ast.ClassDef):
                for method in cls.body:
                    if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and method.name == 'get_structure':
                        if method.lineno in sites:
                            identities.append((path.relative_to(ROOT).as_posix(), cls.name))
    assert len(identities) == sum(baseline[rule].values())
    assert ('reveal/adapters/base.py', 'ResourceAdapter') in identities
    assert ('reveal/adapters/demo.py', 'DemoAdapter') in identities
    assert ('reveal/adapters/surface.py', 'SurfaceAdapter') not in identities
    surface_path = ROOT / 'reveal/adapters/surface.py'
    restored_sink = surface_path.read_text(encoding='utf-8').replace(
        'def get_structure(self)', 'def get_structure(self, **kwargs)')
    assert len(find_sites(restored_sink, 'reveal/adapters/surface.py')[rule]) == 1
    changed = dict(baseline)
    changed[rule] = {**baseline[rule], 'reveal/adapters/surface.py': 1}
    regressions, _ = compare(baseline, changed)
    assert (rule, 'reveal/adapters/surface.py', 0, 1) in regressions
    renamed = 'class Renamed:\n    def get_structure(receiver, **kwargs):\n        pass\n'
    assert len(find_sites(renamed, 'reveal/adapters/example.py')[rule]) == 1
    standalone = 'def get_structure(self, **kwargs):\n    pass\n'
    explicit = 'class Named:\n    def get_structure(self, depth=None):\n        pass\n'
    assert not find_sites(standalone + explicit, 'reveal/adapters/example.py')[rule]
