"""Contracts binds typed controls while preserving implementer-cap metadata."""
import inspect
import json
from types import SimpleNamespace

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.adapters.contracts import ContractsAdapter, ContractsRenderer
from reveal.adapters.factory import uses_bound_query_call
from reveal.utils.query_parser import collect_query_keys

SOURCE = ('from abc import ABC, abstractmethod\nfrom dataclasses import dataclass\n'
          'class Base(ABC):\n    @abstractmethod\n    def go(self): ...\n'
          '@dataclass\nclass Data:\n    value: int\n' + ''.join(
              f'class Impl{i}(Base):\n    def go(self): return {i}\n' for i in range(8)))


@pytest.fixture
def project(tmp_path):
    (tmp_path / 'models.py').write_text(SOURCE, encoding='utf-8')
    return tmp_path


def query(project, controls='', **kwargs):
    return api.query(f'contracts://{project}' + ('?' + controls if controls else ''), **kwargs)


def implementations(result):
    return result['abcs'][0].get('implementations', [])


def test_api_abstract_only_changes_actual_contract_records(project):
    result = query(project, abstract_only=True)
    assert result['total_contracts'] == 1
    assert result['dataclasses'] == [] and result['abcs'][0]['name'] == 'Base'


def test_api_implementations_false_removes_actual_edges(project):
    assert len(implementations(query(project))) == 8
    result = query(project, implementations=False)
    assert implementations(result) == [] and result['total_contracts'] == 2


@pytest.mark.parametrize('value', [-1, True, False, '1.5', '1e3', 'bad'])
def test_invalid_typed_impls_rejects(project, value):
    with pytest.raises(ValueError, match='impls'):
        query(project, impls=value)


def test_unknown_api_keywords_reject(project):
    with pytest.raises(TypeError, match='nonsense'):
        query(project, nonsense=True)


def test_direct_method_keywords_reject(project):
    adapter = ContractsAdapter(str(project))
    with pytest.raises(TypeError, match='abstract_only'):
        adapter.get_structure(abstract_only=True)


def test_false_none_and_omission_preserve_uri_precedence(project):
    assert query(project, 'abstract_only=true')['total_contracts'] == 1
    assert query(project, 'abstract_only=true', abstract_only=False)['total_contracts'] == 2
    assert query(project, 'abstract_only=true', abstract_only=None)['total_contracts'] == 2
    assert implementations(query(project, 'implementations=false')) == []
    assert len(implementations(query(project, 'implementations=false', implementations=None))) == 8
    assert len(implementations(query(project, 'implementations=false', implementations=True))) == 8


def test_zero_none_omission_and_impls_consumption_preserve_cap_contract(project):
    assert query(project, 'impls=1')['impls_cap'] == 1
    assert query(project, 'impls=1', impls=None)['impls_cap'] == 5
    with collect_query_keys() as keys:
        result = query(project, impls=0)
        assert result['impls_cap'] == 0 and 'impls' in keys.used
    assert len(implementations(result)) == 8
    text = ContractsRenderer.render_structure(result, 'text')
    assert 'Impl7' in text and 'more' not in text
    cut = query(project, impls=1)
    assert len(implementations(cut)) == 8
    text = ContractsRenderer.render_structure(cut, 'text')
    assert 'Impl1' not in text and 'and 7 more' in text


def test_invalid_uri_cannot_be_shadowed_by_valid_typed_override(project):
    with pytest.raises(ValueError, match='impls'):
        query(project, 'impls=-1', impls=0)


def test_working_constructor_and_uri_siblings(project):
    native = ContractsAdapter(str(project), params={'abstract_only': True, 'implementations': False,
                                                   'impls': 0}).get_structure()
    assert native['total_contracts'] == 1 and implementations(native) == [] and native['impls_cap'] == 0
    for argv in [(f'contracts://{project}?abstract_only=true&implementations=false&impls=0',),
                 ('contracts', str(project), '--abstract-only', '--no-implementations', '--impls', '0')]:
        response = _run_reveal_direct(*argv, '--format', 'json')
        assert response.returncode == 0
        assert json.loads(response.stdout) == native


def test_single_construction_and_reused_adapter_params_are_not_mutated(project, monkeypatch):
    adapter = ContractsAdapter(str(project), 'abstract_only=true&impls=1')
    before = adapter.get_structure()
    params = dict(dict.items(adapter.query_params))
    original = ContractsAdapter.__init__
    calls = []
    def construct(self, resource, query=None, *, params=None):
        calls.append((resource, query, params))
        original(self, resource, query, params=params)
    monkeypatch.setattr(ContractsAdapter, '__init__', construct)
    assert query(project, abstract_only=True, impls=0)['total_contracts'] == 1
    assert len(calls) == 1 and calls[0][0] == str(project)
    assert adapter.get_structure() == before and dict(dict.items(adapter.query_params)) == params


@pytest.mark.parametrize('spelling', ['plus+path', 'percent%26path'])
def test_literal_api_resources_keep_existing_codec(project, spelling):
    path = project / spelling
    path.mkdir()
    (path / 'models.py').write_text(SOURCE, encoding='utf-8')
    assert query(path, abstract_only=True)['total_contracts'] == 1


def test_custom_subclass_from_uri_and_plugin_kwargs_stay_legacy(project, monkeypatch):
    class Plugin(ContractsAdapter):
        @classmethod
        def from_uri(cls, scheme, resource, element=None):
            return SimpleNamespace(get_structure=lambda **kwargs: {'resource': resource, 'kwargs': kwargs})
    monkeypatch.setattr('reveal.adapters.base.get_adapter_class', lambda scheme: Plugin)
    assert api.query('plugin://literal?resource', arbitrary=False) == {
        'resource': 'literal?resource', 'kwargs': {'arbitrary': False}}
    assert not uses_bound_query_call(Plugin)


def test_actual_callable_and_declarations_adopt_existing_protocol():
    assert uses_bound_query_call(ContractsAdapter)
    assert list(inspect.signature(ContractsAdapter.get_structure).parameters) == ['self']
    assert 'from_uri' not in ContractsAdapter.__dict__
    specs = {spec.name: spec for spec in ContractsAdapter.PARAM_SPECS}
    assert set(specs) == {'abstract_only', 'implementations', 'impls'}
    assert specs['impls'].role == 'presentation'


def test_surface_and_ordinary_ast_siblings_keep_their_behavior(project):
    assert api.query(f'surface://{project}', type='env')['total'] == 0
    ordinary = api.query(f'ast://{project}?type=class')
    assert ordinary['type'] == 'ast_query' and ordinary['results']
