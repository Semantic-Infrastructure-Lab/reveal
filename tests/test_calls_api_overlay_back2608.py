"""Calls binds canonical API overlays before choosing its operation."""
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.api import query
from reveal.adapters.calls.adapter import CallsAdapter


@pytest.fixture
def project(tmp_path):
    (tmp_path / 'app.py').write_text(
        'def sink(a=1): return a\ndef middle(): return sink()\ndef top(): return middle()\n',
        encoding='utf-8')
    return tmp_path


def ask(project, controls='', **kwargs):
    return query(f'calls://{project.as_posix()}' + ('?' + controls if controls else ''), **kwargs)


@pytest.mark.parametrize('mode,name,control,value', [
    ('callers', 'sink', 'depth', 2), ('callees', 'top', 'depth', 2),
    ('callees', 'top', 'detail', True), ('rank', 'callers', 'top', 1)])
def test_actual_answers_equal_uri_and_generated_cli(project, mode, name, control, value):
    controls = f'{mode}={name}&{control}={str(value).lower()}'
    expected = ask(project, controls)
    assert ask(project, **{mode: name, control: value}) == expected
    command = ['calls', str(project), f'--{mode}', name, f'--{control}']
    if value is not True:
        command.append(str(value))
    cli = _run_reveal_direct(*command, '--format', 'json')
    assert cli.returncode == 0, cli.stderr
    assert json.loads(cli.stdout) == expected
    if mode == 'callers':
        assert expected['depth'] == 2 and expected['total_callers'] == 2
    elif mode == 'rank':
        assert len(expected['entries']) == 1


@pytest.mark.parametrize('value,expected', [(0, 1), (None, 1), (2, 2)])
def test_depth_overrides_and_defaults(project, value, expected):
    assert ask(project, 'callers=sink&depth=3', depth=value) == ask(project, f'callers=sink&depth={expected}')


def test_false_zero_and_none_are_effective(project):
    assert ask(project, 'rank=callers&top=1', top=0) == ask(project, 'rank=callers&top=0')
    assert ask(project, 'callees=top&detail=true', detail=False) == ask(project, 'callees=top')
    assert ask(project, 'callees=top&detail=true', detail=None) == ask(project, 'callees=top')
    assert ask(project, 'uncalled=true', uncalled=False, callers='sink') == ask(project, 'callers=sink')
    assert ask(project, 'callers=sink', callers=None, callees='top') == ask(project, 'callees=top')


@pytest.mark.parametrize('kwargs,exception,match', [
    ({'unknown': True}, TypeError, 'unknown'), ({'depth': True}, ValueError, 'depth'),
    ({'depth': '1.5'}, ValueError, 'depth'), ({'top': -1}, ValueError, 'top'),
    ({'callees': 'top'}, ValueError, 'one mode'), ({'detail': True}, ValueError, 'detail')])
def test_invalid_and_contradictory_controls_reject(project, kwargs, exception, match):
    with pytest.raises(exception, match=match):
        ask(project, 'callers=sink', **kwargs)


def test_overlay_mode_validates_after_binding_but_uri_values_validate_first(project):
    # The URI mode forbids detail; the effective overlay changes the mode and permits it.
    assert ask(project, 'callers=sink&detail=true', callers=None, callees='top') == ask(project, 'callees=top&detail')
    with pytest.raises(ValueError, match='depth'):
        ask(project, 'callers=sink&depth=bad', depth=2)
    with pytest.raises(TypeError, match='depth'):
        CallsAdapter(str(project), 'callers=sink').get_structure(depth=2)


def test_repeated_requests_see_edit_and_preserve_required_loss(project, monkeypatch):
    assert ask(project, callers='sink')['total_callers'] == 1
    (project / 'app.py').write_text('def sink(): return 1\ndef other(): return 2\n', encoding='utf-8')
    assert ask(project, callers='sink')['total_callers'] == 0
    import builtins
    original = builtins.open
    denied = []
    def opened(file, *args, **kwargs):
        if isinstance(file, (str, Path)) and Path(file) == project / 'app.py':
            denied.append(True)
            raise PermissionError('SOURCE_DENIED')
        return original(file, *args, **kwargs)
    (project / 'app.py').write_text('def sink(): return 3\n', encoding='utf-8')
    monkeypatch.setattr(builtins, 'open', opened)
    answer = ask(project, callers='sink')
    assert denied
    assert any(w.get('type') == 'analysis_failed' and 'PermissionError' in str(w) and 'incomplete' in w.get('message', '')
               for w in answer['meta']['warnings']), answer


def test_plugin_dispatch_remains_class_local(project, monkeypatch):
    from reveal.adapters import base
    class Plugin(CallsAdapter):
        @classmethod
        def from_uri(cls, scheme, resource, element=None):
            return cls(str(project), 'callers=sink')
        def get_structure(self, **kwargs):
            return kwargs
        def get_element(self, name, **kwargs):
            return {'name': name, **kwargs}
    original = base.get_adapter_class
    monkeypatch.setattr(base, 'get_adapter_class', lambda scheme: Plugin if scheme == 'plugin' else original(scheme))
    assert query('plugin://x', arbitrary=False) == {'arbitrary': False}
    assert query('plugin://x', element_name='sink', arbitrary=0) == {'name': 'sink', 'arbitrary': 0}
