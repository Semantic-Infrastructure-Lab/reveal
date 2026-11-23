"""A third-party plugin adapter that declares nothing: the undeclared example of the registry tests (BACK-2214).

Every core noun binds its query through its declarations since diff:// was declared (BACK-2214). The schemes still
undeclared retire at the cut (classify://, depends://) or leave core for reveal-ops (plan D4, D13), so after the cut
the undeclared path a test must keep covering is a plugin's. This adapter stands for one: canonical construction
(``LEGACY_INIT = False``), no ``PARAM_SPECS``, no ``RESOURCE_SPEC``, no result-control handling
(``HONORS_RESULT_CONTROL = False``: a typed ``?limit=``/``?sort=`` is stripped with a note), an answer of its own, and
an element for any name (a positional element reaches ``get_element``).
The ``undeclared_plugin`` fixture registers it for one test (in-process runs: ``_run_reveal_direct``, ``api.query``,
``inject_query_flags``) and the registry is restored after.
"""
import pytest

from reveal.adapters.base import ResourceAdapter
from reveal.adapters.registry import _ADAPTER_REGISTRY, _RENDERER_REGISTRY
from reveal.reveal_types import CONTRACT_VERSION
from reveal.utils.results import ResultBuilder

SCHEME = 'undeclared'
RESULT_TYPE = 'undeclared_answer'


class UndeclaredPluginAdapter(ResourceAdapter):
    """Answers its resource back; reads no query key and no control."""
    LEGACY_INIT = False
    HONORS_RESULT_CONTROL = False
    CANONICAL_EMPTY_RESOURCE = ''

    def __init__(self, resource: str = '', query=None):
        self.resource = resource

    @staticmethod
    def get_help():
        return {'name': SCHEME, 'description': 'A test plugin that declares no control'}

    @staticmethod
    def get_schema():
        return {'adapter': SCHEME, 'description': 'A test plugin that declares no control',
                'uri_syntax': f'{SCHEME}://RESOURCE', 'query_params': {}, 'elements': {}, 'cli_flags': [],
                'output_types': [{'type': RESULT_TYPE}], 'example_queries': [], 'notes': []}

    def get_structure(self, **kwargs):
        return ResultBuilder.create(result_type=RESULT_TYPE, source=f'{SCHEME}://{self.resource}',
                                    source_type='runtime', contract_version=CONTRACT_VERSION,
                                    data={'resource': self.resource})

    def get_element(self, element_name, **kwargs):
        """Any name is an element: a positional element answers it (``undeclared://x NAME``)."""
        return {'name': element_name}


class UndeclaredPluginRenderer:
    """JSON through the shared writer, so the invocation's notes reach ``meta.warnings`` as on every renderer."""
    @staticmethod
    def render_structure(result, format='text'):
        _render(result, format, 'resource')

    @staticmethod
    def render_element(result, format='text'):
        _render(result, format, 'name')


def _render(result, format, field):
    if format == 'json':
        from reveal.utils.json_utils import print_json_result
        print_json_result(result)
    else:
        print(result.get(field, ''))


@pytest.fixture
def undeclared_plugin(monkeypatch):
    """Register the plugin for one test; yields its scheme."""
    monkeypatch.setitem(_ADAPTER_REGISTRY, SCHEME, UndeclaredPluginAdapter)
    monkeypatch.setitem(_RENDERER_REGISTRY, SCHEME, UndeclaredPluginRenderer)
    return SCHEME
