"""Real contract records establish declared API overlay compatibility."""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.adapters.contracts import ContractsAdapter
from reveal.utils.query_parser import collect_query_keys, peek_query_items

SOURCE = ('from abc import ABC, abstractmethod\nfrom dataclasses import dataclass\n'
          'class Contract(ABC):\n @abstractmethod\n def go(self): pass\n'
          '@dataclass\nclass Record:\n value: int\n' +
          ''.join(f'class Impl{i}(Contract):\n def go(self): return {i}\n' for i in range(8)))


@pytest.fixture
def project(tmp_path):
    (tmp_path / 'contract.py').write_text(SOURCE, encoding='utf-8')
    return tmp_path


def uri(root, query=''):
    return f'contracts://{root.as_posix()}' + ('?' + query if query else '')


def test_abstract_only_api_matches_working_uri_constructor_command(project):
    expected = api.query(uri(project, 'abstract_only=true'))
    constructor = ContractsAdapter(str(project), params={'abstract_only': True}).get_structure()
    command = _run_reveal_direct('contracts', str(project), '--abstract-only', '--format', 'json')
    assert command.returncode == 0
    assert expected == constructor == json.loads(command.stdout)
    assert expected['dataclasses'] == [] and expected['abcs'][0]['name'] == 'Contract'
    assert api.query(uri(project), abstract_only=True) == expected


@pytest.mark.parametrize('raw,override,has_record', [('true', False, True), ('false', True, False), ('true', None, True)])
def test_abstract_boolean_none_and_omission_precedence(project, raw, override, has_record):
    original = api.query(uri(project, 'abstract_only=' + raw))
    assert bool(original['dataclasses']) is (raw == 'false')
    answer = api.query(uri(project, 'abstract_only=' + raw), abstract_only=override)
    assert bool(answer['dataclasses']) is has_record


@pytest.mark.parametrize('raw,override,count', [('true', False, 0), ('false', True, 8), ('false', None, 8)])
def test_implementation_overlay_changes_actual_observations(project, raw, override, count):
    answer = api.query(uri(project, 'implementations=' + raw), implementations=override)
    assert len(answer['abcs'][0]['implementations']) == count


@pytest.mark.parametrize('value,cap', [(0, 0), (1, 1), (None, 5)])
def test_impls_overlay_preserves_full_arrays_and_cap_metadata(project, value, cap):
    answer = api.query(uri(project, 'impls=2'), impls=value)
    assert answer['impls_cap'] == cap
    assert len(answer['abcs'][0]['implementations']) == 8


@pytest.mark.parametrize('value', [-1, True, '1e3'])
def test_invalid_typed_impls_rejects_before_analysis(project, monkeypatch, value):
    from reveal.adapters import contracts
    original = contracts._scan_contracts
    calls = []
    def scan(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(contracts, '_scan_contracts', scan)
    with pytest.raises(ValueError, match='impls'):
        api.query(uri(project), impls=value)
    assert calls == []


def test_invalid_uri_cannot_be_shadowed_and_unknown_api_keyword_rejects(project):
    with pytest.raises(ValueError, match='impls'):
        api.query(uri(project, 'impls=-1'), impls=0)
    with pytest.raises(TypeError, match='nonsense'):
        api.query(uri(project), nonsense=True)


def test_direct_method_keywords_reject_constructor_stays_supported(project):
    adapter = ContractsAdapter(str(project), params={'abstract_only': True})
    with pytest.raises(TypeError, match='abstract_only'):
        adapter.get_structure(abstract_only=False)
    assert adapter.get_structure()['dataclasses'] == []


def test_overlay_constructs_once_inside_host_request(project, monkeypatch):
    from reveal.adapters import contracts
    from reveal.utils.request_cache import in_host_request
    initialize, scan = ContractsAdapter.__init__, contracts._scan_contracts
    constructed, active = [], []
    def init(self, *args, **kwargs):
        constructed.append(True)
        initialize(self, *args, **kwargs)
    def analyze(*args, **kwargs):
        active.append(in_host_request())
        return scan(*args, **kwargs)
    monkeypatch.setattr(ContractsAdapter, '__init__', init)
    monkeypatch.setattr(contracts, '_scan_contracts', analyze)
    answer = api.query(uri(project), abstract_only=True)
    assert answer['dataclasses'] == []
    assert constructed == active == [True]


def test_bound_carrier_and_existing_impls_read_accounting_remain(project):
    with collect_query_keys() as keys:
        adapter = ContractsAdapter(str(project), 'abstract_only=true&impls=0')
        before = list(peek_query_items(adapter.query_params))
        assert not keys.used
        first = adapter.get_structure()
        assert 'impls' in keys.used and first['impls_cap'] == 0
        api.query(uri(project), abstract_only=False, impls=1)
        assert adapter.get_structure() == first
        assert list(peek_query_items(adapter.query_params)) == before


def test_unknown_uri_and_raw_api_resource_policy_remain(project, capsys):
    assert api.query(uri(project, 'nonsense=true'))['total_contracts'] > 0
    assert "Unknown query param 'nonsense'" in capsys.readouterr().err
    decoded = project / 'literal space'
    decoded.mkdir()
    (decoded / 'contract.py').write_text(SOURCE, encoding='utf-8')
    encoded = project / 'literal%20space'
    answer = api.query(uri(encoded), abstract_only=True)
    assert answer['total_contracts'] == 0 and answer['source'] == encoded.as_posix()
    adapter = ContractsAdapter(str(project) + '?literal%26+', params={'impls': 0})
    assert adapter.path == str(project) + '?literal%26+'


def test_custom_plugin_structure_and_element_forwarding_remain(project, monkeypatch):
    from reveal.adapters import base
    class Plugin(ContractsAdapter):
        @classmethod
        def from_uri(cls, scheme, resource, element=None):
            return cls(resource)
        def get_structure(self, **kwargs):
            return {'received': kwargs}
        def get_element(self, element, **kwargs):
            return {'element': element, 'received': kwargs}
    original = base.get_adapter_class
    monkeypatch.setattr(base, 'get_adapter_class', lambda scheme: Plugin if scheme == 'contracts-plugin' else original(scheme))
    assert api.query(f'contracts-plugin://{project.as_posix()}', nonsense=False) == {'received': {'nonsense': False}}
    assert api.query(f'contracts-plugin://{project.as_posix()}', element_name='entry', impls=0) == {
        'element': 'entry', 'received': {'impls': 0}}
