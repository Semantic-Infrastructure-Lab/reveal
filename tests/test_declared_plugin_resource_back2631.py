"""A registered replacement does not inherit a scheme's generated contract."""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.base import ResourceAdapter, get_adapter_class
from reveal.adapters.registry import _ADAPTER_REGISTRY, _RENDERER_REGISTRY
from reveal.utils.query_parser import ParamSpec, parse_query_params
from reveal.utils.results import ResultBuilder


@pytest.mark.parametrize('scheme', ['ast', 'legacy_resource_fixture'])
def test_registered_legacy_adapter_with_specs_keeps_legacy_resource_dispatch(monkeypatch, tmp_path, scheme):
    get_adapter_class('ast')  # Load the builtin before installing the replacement.

    class LegacyAdapter(ResourceAdapter):
        LEGACY_INIT = False
        RESOURCE_SPEC = None
        PARAM_SPECS = (ParamSpec('limit', 'integer', 'legacy limit', 10, int),)
        RESULT_TYPE = 'legacy_plugin'

        def __init__(self, resource='', query=None):
            self.resource = resource
            self.params = parse_query_params(query or '')

        def get_structure(self, **kwargs):
            return ResultBuilder.create('legacy_plugin', self.resource, source_type='directory',
                                        data={'limit': int(self.params.get('limit', 10))})

    class Renderer:
        @staticmethod
        def render_structure(result, format='text'):
            print(json.dumps(result))

    monkeypatch.setitem(_ADAPTER_REGISTRY, scheme, LegacyAdapter)
    monkeypatch.setitem(_RENDERER_REGISTRY, scheme, Renderer)
    result = _run_reveal_direct(f'{scheme}://{tmp_path.as_posix()}?limit=2', '--format', 'json')
    assert result.returncode == 0, result.stderr
    answer = json.loads(result.stdout)
    assert answer['type'] == 'legacy_plugin' and answer['limit'] == 2
    assert answer['source'] == tmp_path.as_posix()
