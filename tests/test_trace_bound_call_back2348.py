"""Retired Trace binds API controls without changing its evidence or lifetime."""
import inspect
import json
from types import SimpleNamespace
from urllib.parse import quote

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.adapters.trace import TraceAdapter
from reveal.adapters.factory import uses_bound_query_call
from reveal.utils.results import AnalysisCompleteness, FailureCause

SOURCE = ('def main():\n    first()\n'
          'def first():\n    second()\n'
          'def second():\n    third()\n'
          'def third():\n    return 1\n'
          'def other():\n    finish()\n'
          'def finish():\n    return 2\n')


@pytest.fixture
def project(tmp_path):
    (tmp_path / 'chain.py').write_text(SOURCE, encoding='utf-8')
    return tmp_path


def query(project, controls='from=main&depth=1', **kwargs):
    return api.query(f'trace://{project}?{controls}', **kwargs)


def names(result):
    return [frame['name'] for frame in result['frames']]


def test_api_depth_override_changes_actual_frames(project):
    deep = query(project, 'from=main&depth=3')
    assert 'third' in names(deep) and 'third' not in names(query(project))
    overridden = query(project, depth=3)
    assert overridden['depth'] == 3 and overridden['frames'] == deep['frames']


def test_api_canonical_from_override_changes_actual_root(project):
    result = query(project, **{'from': 'other'})
    assert result['root'] == 'other' and names(result) == ['other', 'finish']


@pytest.mark.parametrize('value', ['bad', '1.5', '2.0', '1e3', True, False])
def test_invalid_typed_depth_rejects_with_valid_required_selector(project, value):
    with pytest.raises(ValueError, match='depth'):
        query(project, depth=value)


@pytest.mark.parametrize('kwargs', [{'root': 'other'}, {'from_': 'other'}, {'unexpected': 1}])
def test_noncanonical_api_names_reject(project, kwargs):
    with pytest.raises(TypeError, match=next(iter(kwargs))):
        query(project, **kwargs)


@pytest.mark.parametrize('method', ['get_structure', '_get_structure'])
def test_direct_public_and_private_method_kwargs_reject(project, method):
    adapter = TraceAdapter(str(project), 'from=main')
    with pytest.raises(TypeError, match='depth'):
        getattr(adapter, method)(depth=3)


def test_depth_none_zero_omission_and_clamps_preserve_policy(project):
    assert query(project)['depth'] == 1
    assert query(project, depth=None)['depth'] == 2
    assert query(project, depth=0)['depth'] == 1
    assert query(project, depth=-2)['depth'] == 1
    assert query(project, depth=99)['depth'] == 5
    assert query(project, 'from=main')['depth'] == 2


def test_required_original_selector_and_invalid_uri_validate_before_overlay(project):
    with pytest.raises(ValueError, match='from is required'):
        api.query(f'trace://{project}', **{'from': 'main'})
    with pytest.raises(ValueError, match='depth'):
        query(project, 'from=main&depth=bad', depth=3)
    with pytest.raises(ValueError, match='from'):
        query(project, 'from=', **{'from': 'main'})


def test_working_constructor_and_uri_siblings_keep_frames_and_retirement(project):
    native = TraceAdapter(str(project), params={'root': 'main', 'depth': 3}).get_structure()
    assert native['depth'] == 3 and 'third' in names(native)
    response = _run_reveal_direct(f'trace://{project}?from=main&depth=3', '--format', 'json')
    assert response.returncode == 0
    data = json.loads(response.stdout)
    assert data['frames'] == native['frames']
    assert any(w.get('code') == 'retired_spelling' for w in data['meta']['warnings'])


def test_construct_once_and_api_overrides_do_not_mutate_reused_params(project, monkeypatch):
    adapter = TraceAdapter(str(project), 'from=main&depth=1')
    before = adapter.get_structure()
    params = dict(dict.items(adapter.query_params))
    original = TraceAdapter.__init__
    calls = []
    def construct(self, resource, query=None, *, params=None):
        calls.append((resource, query, params))
        original(self, resource, query, params=params)
    monkeypatch.setattr(TraceAdapter, '__init__', construct)
    assert query(project, depth=3)['depth'] == 3
    assert len(calls) == 1 and calls[0][0] == str(project)
    assert adapter.get_structure() == before and dict(dict.items(adapter.query_params)) == params


def test_once_percent_uri_selector_and_typed_literal_selector(project):
    filename = 'literal%20+name.py'
    (project / filename).write_text('def special():\n    return 1\n', encoding='utf-8')
    selector = filename + ':special'
    uri = query(project, 'from=' + quote(selector, safe=''))
    typed = query(project, **{'from': selector})
    assert uri['root'] == typed['root'] == selector
    assert typed['frames'] == uri['frames'] and typed['frames'][0]['resolved']


def test_absent_root_and_lost_source_recover_on_reused_adapter(project, monkeypatch):
    from reveal.adapters.ast import analysis
    absent = query(project, 'from=absent')
    assert not absent['frames'][0]['resolved']
    assert TraceAdapter.execution_facts(absent).failures == frozenset({FailureCause.INVALID_REQUEST})
    adapter = TraceAdapter(str(project), 'from=main&depth=3')
    clean = adapter.get_structure()
    original = analysis.create_element_dict
    def fail(*args, **kwargs):
        raise OSError('TRACE_REQUIRED_SOURCE_UNAVAILABLE')
    with monkeypatch.context() as fault:
        fault.setattr(analysis, 'create_element_dict', fail)
        result = adapter.get_structure()
        assert TraceAdapter.execution_facts(result).completeness is AnalysisCompleteness.FAILED
        warning, = [w for w in result['meta']['warnings'] if w.get('type') == 'analysis_failed']
        assert warning['count'] == 1 and warning['files'] == [(project / 'chain.py').as_posix()]
    assert analysis.create_element_dict is original
    assert adapter.get_structure() == clean
    assert adapter.composed_meta() is None


def test_custom_subclass_factory_is_not_inherited_adoption(project, monkeypatch):
    class Plugin(TraceAdapter):
        @classmethod
        def from_uri(cls, scheme, resource, element=None):
            return SimpleNamespace(get_structure=lambda **kwargs: {'resource': resource, 'kwargs': kwargs})
    monkeypatch.setattr('reveal.adapters.base.get_adapter_class', lambda scheme: Plugin)
    assert api.query('plugin://literal?path', root='custom') == {
        'resource': 'literal?path', 'kwargs': {'root': 'custom'}}
    assert not uses_bound_query_call(Plugin)


def test_actual_callables_and_siblings(project):
    assert uses_bound_query_call(TraceAdapter)
    assert list(inspect.signature(TraceAdapter.get_structure).parameters) == ['self']
    assert list(inspect.signature(TraceAdapter._get_structure).parameters) == ['self']
    assert {spec.name for spec in TraceAdapter.PARAM_SPECS} == {'from', 'depth'}
    assert api.query(f'surface://{project}', type='env')['total'] == 0
    assert api.query(f'contracts://{project}', abstract_only=True)['total_contracts'] == 0
    assert api.query(f'ast://{project}?type=function')['results']


def test_explicit_typed_from_none_rejects(project):
    with pytest.raises(ValueError, match='from'):
        query(project, **{'from': None})
