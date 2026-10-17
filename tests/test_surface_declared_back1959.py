"""Surface opts into the declared binder, preserving legacy constructor dispatch."""
import pytest

from reveal.adapters.factory import _canonical_init
from reveal.adapters.surface import SurfaceAdapter
from reveal.utils.query_parser import QueryParams, collect_query_keys


def test_factory_typed_resource_does_not_split_question_mark():
    class Target:
        def __init__(self, resource, query=None, *, params=None):
            self.resource, self.query, self.params = resource, query, params

    params = QueryParams({'depth': 0})
    bound = _canonical_init(Target, 'literal?name%26,a', params=params)
    assert bound.resource == 'literal?name%26,a' and bound.query is None
    assert bound.params is params
    legacy = _canonical_init(Target, 'old-path?depth=2')
    assert legacy.resource == 'old-path' and legacy.query == 'depth=2'


def test_surface_declaration_exports_complete_binding_schema():
    assert SurfaceAdapter.RESULT_TYPE == 'surface_scan'
    assert SurfaceAdapter.RESOURCE_SPEC.uri_codec == 'existing-path-first'
    specs = {spec.name: spec for spec in SurfaceAdapter.PARAM_SPECS}
    assert specs['top'].role == 'presentation' and specs['top'].default is None
    schema = SurfaceAdapter.get_schema()
    assert schema['resource'] == SurfaceAdapter.RESOURCE_SPEC.schema()
    for name, declaration in specs.items():
        assert schema['query_params'][name] == declaration.schema()
    assert specs['depth'].minimum == 0 and 'env' in specs['type'].choices


def test_surface_typed_and_uri_inputs_share_scanner_result(tmp_path):
    source = tmp_path / 'code,a%26.py'
    source.write_text('import os\nVALUE = os.getenv("BINDING_TEST")\n', encoding='utf-8')
    typed = SurfaceAdapter(str(source), params={'type': 'env', 'source_only': False, 'depth': 0})
    uri = SurfaceAdapter(str(source), 'type=env&source_only=false&depth=0')
    assert typed.get_structure() == uri.get_structure()
    assert typed.get_structure()['total'] == 1


@pytest.mark.parametrize('query', ['type=0', 'type=typo', 'depth=1.5', 'depth=-1', 'source_only=garbage'])
def test_surface_rejects_malformed_values_at_declared_boundary(tmp_path, query):
    with pytest.raises(ValueError):
        SurfaceAdapter(str(tmp_path), query)


@pytest.mark.parametrize('value,expected', [('yes', True), ('1', True), ('no', False), ('0', False),
                                          ('true', True), ('false', False)])
def test_surface_boolean_spellings_are_shared(tmp_path, value, expected):
    adapter = SurfaceAdapter(str(tmp_path), 'source_only='+value)
    declaration = next(spec for spec in SurfaceAdapter.PARAM_SPECS if spec.name == 'source_only')
    assert declaration.read(adapter.query_params) is expected


def test_surface_presentation_top_is_not_consumed_by_analysis(tmp_path):
    with collect_query_keys() as log:
        adapter = SurfaceAdapter(str(tmp_path), 'type=env&top=0')
        assert not log.used
        result = adapter.get_structure()
        assert result['type'] == 'surface_scan'
        assert 'type' in log.used and 'top' not in log.used
        top = next(spec for spec in SurfaceAdapter.PARAM_SPECS if spec.name == 'top')
        assert top.read(adapter.query_params) == 0 and 'top' in log.used
