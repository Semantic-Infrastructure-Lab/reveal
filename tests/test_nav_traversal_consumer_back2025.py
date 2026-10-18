"""Native consumers preserve actual transitive discovery evidence (BACK-2025)."""
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.ast import analysis, nav_effects

pytestmark = pytest.mark.component


@pytest.fixture
def discovery_fault(monkeypatch):
    state = {'active': False, 'denied': {}, 'events': [], 'attempts': []}
    real_collect, real_scandir = analysis.collect_structures, os.scandir

    def collect(*args, **kwargs):
        state['active'] = True
        try:
            result = real_collect(*args, **kwargs)
            state['events'] = list(result.traversal_failures)
            return result
        finally:
            state['active'] = False

    def scandir(path):
        target = Path(path).resolve()
        if state['active'] and target in state['denied']:
            state['attempts'].append(target)
            identified = state['denied'][target]
            if identified is None:
                raise PermissionError('consumer unlocated denial')
            raise PermissionError(13, 'consumer identified denial', str(identified))
        return real_scandir(path)

    monkeypatch.setattr(analysis, 'collect_structures', collect)
    monkeypatch.setattr(os, 'scandir', scandir)
    return state


def _cli(entry, flag, fmt='json', *extra):
    result = _run_reveal_direct(str(entry), 'entry', flag, '--transitive', '--format', fmt, *extra)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout) if fmt == 'json' else result.stdout


def _directory_note(value, fmt):
    notes = value['warnings'] if fmt == 'json' else value.splitlines()
    matching = [note for note in notes if 'directory enumeration(s) failed' in note]
    assert len(matching) == 1, value
    return matching[0]


@pytest.mark.parametrize('flag', ['--sideeffects', '--boundary'])
@pytest.mark.parametrize('fmt', ['json', 'text'])
def test_actual_events_deduplicate_identified_paths_but_preserve_unknown_population(tmp_path, discovery_fault, flag, fmt):
    entry = tmp_path / 'entry.py'
    entry.write_text('import os\ndef entry():\n    os.remove("own")\n', encoding='utf-8')
    directories = [tmp_path / f'blocked_{index}' for index in range(10)]
    for directory in directories:
        directory.mkdir()
        (directory / 'hidden.py').write_text('def hidden():\n    return 1\n', encoding='utf-8')
    clean = _cli(entry, flag, fmt)
    # Eight actual identified errors name seven distinct directories; two more
    # actual enumeration attempts lack a filename and must remain two events.
    discovery_fault['denied'] = {directory: directories[min(index, 6)] if index < 8 else None
                                for index, directory in enumerate(directories)}
    lost = _cli(entry, flag, fmt)
    assert len(discovery_fault['attempts']) == 10
    assert len(discovery_fault['events']) == 10
    note = _directory_note(lost, fmt)
    assert '7 identified directory enumeration(s) failed' in note
    assert '2 enumeration error event(s) had an unknown directory' in note
    assert 'and 2 more' in note
    for index in range(5):
        assert str(directories[index]) in note
    assert str(directories[5]) not in note and str(directories[6]) not in note
    assert 'os.remove' in str(lost)
    discovery_fault['denied'].clear()
    assert _cli(entry, flag, fmt) == clean


@pytest.mark.parametrize('flag', ['--sideeffects', '--boundary'])
@pytest.mark.parametrize('own_effect', [False, True])
def test_javascript_real_callee_loss_and_unclassified_calls(tmp_path, discovery_fault, flag, own_effect):
    child = tmp_path / 'child'
    child.mkdir()
    entry = tmp_path / 'entry.js'
    entry.write_text('function entry() {\n  helper();\n  mystery();\n' +
                     ('  console.log("own");\n' if own_effect else '') + '}\n', encoding='utf-8')
    (child / 'helper.js').write_text('function helper() { console.log("hidden"); }\n', encoding='utf-8')
    clean = _cli(entry, flag)
    assert any(row.get('hop') == 1 and row.get('callee') == 'console.log' for row in clean['findings'])
    discovery_fault['denied'][child] = child
    lost = _cli(entry, flag)
    assert discovery_fault['events']
    assert not any(row.get('hop', 0) > 0 for row in lost['findings'])
    assert any(row.get('callee') == 'console.log' for row in lost['findings']) == own_effect
    _directory_note(lost, 'json')
    text = _cli(entry, flag, 'text')
    _directory_note(text, 'text')
    if not own_effect:
        assert 'analyzed portion' in text and 'incomplete' in text
    discovery_fault['denied'].clear()
    assert _cli(entry, flag) == clean


@pytest.mark.parametrize('flag', ['--sideeffects', '--boundary'])
def test_range_and_depth_do_not_suppress_discovery_warning(tmp_path, discovery_fault, flag):
    entry = tmp_path / 'entry.py'
    entry.write_text('import os\ndef entry():\n    mystery()\n    os.remove("outside range")\n', encoding='utf-8')
    blocked = tmp_path / 'blocked'
    blocked.mkdir()
    (blocked / 'other.py').write_text('def other():\n    return 1\n', encoding='utf-8')
    clean = _cli(entry, flag, 'json', '--range', '3-3', '--depth', '1')
    assert not any(row.get('callee') for row in clean['findings'])
    discovery_fault['denied'][blocked] = blocked
    lost = _cli(entry, flag, 'json', '--range', '3-3', '--depth', '1')
    assert not any(row.get('callee') for row in lost['findings'])
    _directory_note(lost, 'json')
    text = _cli(entry, flag, 'text', '--range', '3-3', '--depth', '1')
    assert 'analyzed portion' in text
    _directory_note(text, 'text')
    discovery_fault['denied'].clear()
    assert _cli(entry, flag, 'json', '--range', '3-3', '--depth', '1') == clean


def test_plain_list_renderer_empty_and_unclassified_compatibility():
    assert nav_effects.render_effects_transitive([], 'entry', 2) == (
        'No classified side effects found in entry or its callees (--transitive, depth=2)')
    rows = [{'kind': None, 'callee': 'mystery', 'line': 3, 'first_arg': None,
             'has_more_args': False, 'hop': 0, 'chain': ['entry']}]
    assert nav_effects.render_effects_transitive(rows, 'entry', 2) == nav_effects.render_effects_transitive([], 'entry', 2)
    rendered = nav_effects.render_effects_transitive(rows, 'entry', 2, include_unclassified=True)
    assert 'mystery' in rendered and 'Warning:' not in rendered


@pytest.mark.parametrize('flag', ['--sideeffects', '--boundary'])
def test_flat_cli_never_attempts_transitive_inventory(tmp_path, discovery_fault, flag):
    entry = tmp_path / 'entry.py'
    entry.write_text('import os\ndef entry():\n    os.remove("own")\n', encoding='utf-8')
    def flat():
        response = _run_reveal_direct(str(entry), 'entry', flag, '--format', 'json')
        assert response.returncode == 0
        return response.stdout, response.stderr
    clean = flat()
    discovery_fault['denied'][tmp_path] = tmp_path
    assert flat() == clean
    assert not discovery_fault['attempts']
    assert 'directory enumeration(s) failed' not in clean[0]
