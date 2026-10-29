"""Real Trace call chains prove canonical API overlay admission."""
import copy
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.adapters.trace import TraceAdapter
from reveal.utils.query_parser import collect_query_keys, peek_query_items

SOURCE = ('def main():\n    first()\n\ndef first():\n    second()\n\ndef second():\n'
          '    third()\n\ndef third():\n    fourth()\n\ndef fourth():\n    return 1\n'
          '\ndef alternate():\n    return 2\n')


@pytest.fixture
def project(tmp_path):
    (tmp_path / 'app.py').write_text(SOURCE, encoding='utf-8')
    return tmp_path


def uri(root, query='from=main'):
    return f'trace://{root.as_posix()}' + ('?' + query if query else '')


def without_retirement(answer):
    answer = copy.deepcopy(answer)
    answer['meta']['warnings'] = [entry for entry in answer['meta'].get('warnings', [])
                                  if entry.get('code') != 'retired_spelling']
    if answer['meta'] == {'warnings': []}:
        answer.pop('meta')
    return answer


def test_api_depth_matches_working_uri_constructor_command_actual_frames(project):
    shallow = api.query(uri(project, 'from=main&depth=1'))
    expected = api.query(uri(project, 'from=main&depth=3'))
    constructor = TraceAdapter(str(project), params={'root': 'main', 'depth': 3}).get_structure()
    command = _run_reveal_direct('trace', str(project), '--from', 'main', '--depth', '3', '--format', 'json')
    assert command.returncode == 0
    assert expected == constructor == without_retirement(json.loads(command.stdout))
    assert len(expected['frames']) > len(shallow['frames'])
    assert api.query(uri(project, 'from=main&depth=1'), depth=3) == expected


def test_canonical_from_overlay_changes_actual_root(project):
    answer = api.query(uri(project), **{'from': 'alternate'})
    assert answer['root'] == 'alternate'
    assert answer['frames'][0]['name'] == 'alternate' and answer['frames'][0]['resolved']
    assert len(answer['frames']) == 1


@pytest.mark.parametrize('value,expected', [(0, 1), (-2, 1), (None, 2), (8, 5)])
def test_depth_zero_none_clamping_and_omission(project, value, expected):
    query = uri(project, 'from=main&depth=3')
    assert api.query(query)['depth'] == 3
    answer = api.query(query, depth=value)
    assert answer == api.query(uri(project, f'from=main&depth={expected}'))


@pytest.mark.parametrize('value', [False, True, '1.5', '1e2'])
def test_invalid_depth_rejects_before_analysis(project, monkeypatch, value):
    from reveal.adapters import trace
    original = trace._build_trace
    calls = []
    def build(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(trace, '_build_trace', build)
    with pytest.raises(ValueError, match='depth'):
        api.query(uri(project), depth=value)
    assert calls == []


@pytest.mark.parametrize('key', ['root', 'from_', 'nonsense'])
def test_api_rejects_noncanonical_aliases_and_unknowns(project, key):
    with pytest.raises(TypeError, match=key):
        api.query(uri(project), **{key: 'alternate'})


def test_original_uri_validates_before_override_and_selector_stays_required(project):
    with pytest.raises(ValueError, match='depth'):
        api.query(uri(project, 'from=main&depth=1.5'), depth=3)
    with pytest.raises(ValueError, match='from'):
        api.query(uri(project, ''), **{'from': 'main'})
    with pytest.raises(ValueError, match='from'):
        api.query(uri(project), **{'from': None})


def test_direct_method_rejects_constructor_alias_remains_supported(project):
    adapter = TraceAdapter(str(project), params={'root': 'main', 'depth': 1})
    with pytest.raises(TypeError, match='depth'):
        adapter.get_structure(depth=3)
    assert adapter.get_structure()['depth'] == 1


def test_typed_percent_selector_is_literal_and_api_resource_codec_unchanged(project):
    path = project / 'literal%20+name.py'
    path.write_text('def literal_entry():\n    return 1\n', encoding='utf-8')
    entry = path.name + ':literal_entry'
    answer = api.query(uri(project), **{'from': entry})
    assert answer['root'] == entry and answer['frames'][0]['resolved']
    decoded = project / 'literal space'
    decoded.mkdir()
    (decoded / 'app.py').write_text(SOURCE, encoding='utf-8')
    encoded = project / 'literal%20space'
    answer = api.query(uri(encoded), depth=1)
    assert answer['source'] == encoded.as_posix()
    assert not answer['frames'][0]['resolved']


def test_constructs_once_inside_host_request_and_preserves_carrier(project, monkeypatch):
    from reveal.adapters import trace
    from reveal.utils.request_cache import in_host_request
    original_init, original_build = TraceAdapter.__init__, trace._build_trace
    initialized, requests = [], []
    def initialize(self, *args, **kwargs):
        initialized.append(True)
        original_init(self, *args, **kwargs)
    def build(*args, **kwargs):
        requests.append(in_host_request())
        return original_build(*args, **kwargs)
    with collect_query_keys() as keys:
        owner = TraceAdapter(str(project), 'from=main&depth=1')
        before = list(peek_query_items(owner.query_params))
        clean = owner.get_structure()
        assert {'from', 'depth'} <= keys.used
        monkeypatch.setattr(TraceAdapter, '__init__', initialize)
        monkeypatch.setattr(trace, '_build_trace', build)
        assert api.query(uri(project), depth=3)['depth'] == 3
        assert initialized == requests == [True]
        assert owner.get_structure() == clean
        assert list(peek_query_items(owner.query_params)) == before


def test_reused_composition_diagnostics_clear_after_real_reader_repair(project, monkeypatch):
    import builtins
    from pathlib import Path
    original = builtins.open
    denied = []
    def opened(file, *args, **kwargs):
        if isinstance(file, (str, Path)) and Path(file) == project / 'app.py':
            denied.append(True)
            raise PermissionError('TRACE_READER_DENIED')
        return original(file, *args, **kwargs)
    owner = TraceAdapter(str(project), 'from=main')
    clean = owner.get_structure()
    with monkeypatch.context() as context:
        context.setattr(builtins, 'open', opened)
        first = owner.get_structure()
        assert denied and first['meta']['warnings']
        assert owner.get_structure() == first
    assert owner.get_structure() == clean


def test_custom_subclass_structure_and_element_forwarding_remain(project, monkeypatch):
    from reveal.adapters import base
    class Plugin(TraceAdapter):
        @classmethod
        def from_uri(cls, scheme, resource, element=None):
            return cls(resource, 'from=main')
        def get_structure(self, **kwargs):
            return {'received': kwargs}
        def get_element(self, name, **kwargs):
            return {'name': name, 'received': kwargs}
    original = base.get_adapter_class
    monkeypatch.setattr(base, 'get_adapter_class', lambda scheme: Plugin if scheme == 'trace-plugin' else original(scheme))
    assert api.query(f'trace-plugin://{project.as_posix()}', root=False) == {'received': {'root': False}}
    assert api.query(f'trace-plugin://{project.as_posix()}', element_name='entry', depth=0) == {
        'name': 'entry', 'received': {'depth': 0}}


def test_trace_nested_and_interrupted_composition_restore_diagnostic_lifetime(project, monkeypatch):
    owner = TraceAdapter(str(project), 'from=main')
    clean = owner.get_structure()
    outer_warning = {'type': 'outer_control', 'message': 'outer analysis warning'}
    with owner.composition_run():
        owner.fold_meta({'warnings': [outer_warning]})
        assert owner.get_structure() == clean
        assert owner.composed_meta()['warnings'] == [outer_warning]
    assert owner.composed_meta() is None
    def interrupted():
        owner.record_composed_error('trace_control', project, OSError('interrupted source'))
        raise RuntimeError('TRACE_INTERRUPTED')
    with monkeypatch.context() as context:
        context.setattr(owner, '_get_structure', interrupted)
        with pytest.raises(RuntimeError, match='TRACE_INTERRUPTED'):
            owner.get_structure()
    assert owner.composed_meta() is None
    assert owner.get_structure() == clean
