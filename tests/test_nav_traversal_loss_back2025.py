"""Actual transitive discovery loss must survive native collection and rendering."""
import builtins
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.ast import nav_boundary, nav_effects
from reveal.adapters.calls import index as calls_index
from reveal.core.treesitter_compat import _zero_arg
from reveal.file_handler import _find_element_node
from reveal.registry import get_analyzer
from reveal.utils.exclusions import exclusion_scope

pytestmark = pytest.mark.component


def _tree(root, surviving=False, pure=False):
    root.mkdir(parents=True, exist_ok=True)
    child = root / 'included_child'
    child.mkdir()
    entry = root / 'entry.py'
    body = '    helper()\n' + ('    os.remove("visible")\n' if surviving else '')
    entry.write_text('import os\nfrom included_child.helper import helper\n\ndef entry():\n' + body, encoding='utf-8')
    child.joinpath('helper.py').write_text('import os\n\ndef helper():\n' +
                                          ('    return 1\n' if pure else '    os.remove("hidden")\n'), encoding='utf-8')
    return entry


@pytest.fixture
def fault(monkeypatch):
    state = {'active': False, 'deny': None, 'unknown': False, 'unreadable': None,
             'attempts': 0, 'records': []}
    real_collect, real_scandir, real_open = calls_index.collect_structures, os.scandir, builtins.open

    def collect(*args, **kwargs):
        state['active'] = True
        try:
            result = real_collect(*args, **kwargs)
            state['records'].append(result)
            return result
        finally:
            state['active'] = False

    def scandir(path):
        if state['active'] and state['deny'] == Path(path).resolve():
            state['attempts'] += 1
            if state['unknown']:
                raise PermissionError('controlled unknown discovery loss')
            raise PermissionError(13, 'controlled discovery loss', str(path))
        return real_scandir(path)

    def read(file, *args, **kwargs):
        if state['active'] and isinstance(file, (str, os.PathLike)) and Path(file).resolve() == state['unreadable']:
            raise PermissionError(13, 'controlled file read loss', str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(calls_index, 'collect_structures', collect)
    monkeypatch.setattr(os, 'scandir', scandir)
    monkeypatch.setattr(builtins, 'open', read)
    return state


def _cli(entry, flag, fmt='text', transitive=True, depth=2):
    args = [str(entry), 'entry', flag]
    if transitive:
        args += ['--transitive', '--depth', str(depth)]
    response = _run_reveal_direct(*args, '--format', fmt)
    assert response.returncode == 0, response.stderr
    return json.loads(response.stdout) if fmt == 'json' else response.stdout


def _raw(entry, boundary=False):
    analyzer = get_analyzer(str(entry))(str(entry))
    node = _find_element_node(analyzer, 'entry')
    assert node is not None
    end = getattr(analyzer, '_function_end_node', lambda value: value)(node)
    first = _zero_arg(node, 'start_position').row + 1
    last = _zero_arg(end, 'end_position').row + 1
    collector = nav_boundary.collect_boundary_transitive if boundary else nav_effects.collect_effects_transitive
    value = collector(str(entry), 'entry', node, first, last, analyzer._get_node_text,
                      language=analyzer.language, depth=2)
    rendered = (nav_boundary.render_boundary_transitive(value, 'entry', first, last, 2)
                if boundary else nav_effects.render_effects_transitive(value, 'entry', 2))
    return value, rendered


def _directory_notes(warnings):
    return [warning for warning in warnings if 'directory enumeration(s) failed' in warning]


@pytest.mark.parametrize('flag', ['--sideeffects', '--boundary'])
@pytest.mark.parametrize('fmt', ['text', 'json'])
@pytest.mark.parametrize('case', ['hidden', 'surviving', 'pure', 'root', 'unknown'])
def test_actual_directory_loss_disclosed_and_empty_claim_scoped(tmp_path, fault, flag, fmt, case):
    entry = _tree(tmp_path, surviving=case in ('surviving', 'root'), pure=case == 'pure')
    clean = _cli(entry, flag, fmt)
    fault.update(deny=(tmp_path if case == 'root' else tmp_path / 'included_child').resolve(),
                 unknown=case == 'unknown')
    lost = _cli(entry, flag, fmt)
    assert fault['attempts'] and fault['records'][-1].traversal_failures
    if fmt == 'json':
        notes = _directory_notes(lost['warnings'])
        assert len(notes) == 1, lost
        assert 'missing' in notes[0]
        if case in ('surviving', 'root'):
            assert any(row.get('callee') == 'os.remove' for row in lost['findings'])
    else:
        assert lost.count('directory enumeration(s) failed') == 1, lost
        if case in ('hidden', 'pure', 'unknown'):
            assert 'analyzed portion' in lost and 'incomplete' in lost, lost
        else:
            assert 'os.remove' in lost
    fault['deny'] = None
    assert _cli(entry, flag, fmt) == clean


@pytest.mark.parametrize('boundary', [False, True])
@pytest.mark.parametrize('surviving', [False, True])
def test_direct_native_renderer_discloses_real_loss_and_carrier_retains_events(tmp_path, fault, boundary, surviving):
    entry = _tree(tmp_path, surviving=surviving)
    clean, _ = _raw(entry, boundary)
    clean_rows = clean['effects'] if boundary else clean
    assert sum(bool(row['kind']) for row in clean_rows) == 1 + surviving
    fault['deny'] = (tmp_path / 'included_child').resolve()
    lost, rendered = _raw(entry, boundary)
    rows = lost['effects'] if boundary else lost
    assert sum(bool(row['kind']) for row in rows) == surviving
    assert fault['records'][-1].traversal_failures
    # Existing direct rendering is the semantic failure, not merely a missing attribute.
    assert rendered.count('directory enumeration(s) failed') == 1, rendered
    events = lost.get('traversal_failures', ()) if boundary else getattr(lost, 'traversal_failures', ())
    assert list(events) == list(fault['records'][-1].traversal_failures)


@pytest.mark.parametrize('flag', ['--sideeffects', '--boundary'])
@pytest.mark.parametrize('fmt', ['text', 'json'])
def test_real_file_read_note_preserved_once_with_independent_directory_loss(tmp_path, fault, flag, fmt):
    entry = _tree(tmp_path)
    unreadable = tmp_path / 'unreadable.py'
    unreadable.write_text('def unrelated():\n    return 1\n', encoding='utf-8')
    fault['unreadable'] = unreadable.resolve()
    file_only = _cli(entry, flag, fmt)
    old_notes = file_only['warnings'] if fmt == 'json' else file_only.splitlines()
    old_file_note = next(note for note in old_notes if 'could not be analyzed' in note)
    assert not _directory_notes(old_notes)
    fault['deny'] = (tmp_path / 'included_child').resolve()
    mixed = _cli(entry, flag, fmt)
    notes = mixed['warnings'] if fmt == 'json' else mixed.splitlines()
    assert notes.count(old_file_note) == 1
    assert len(_directory_notes(notes)) == 1, mixed
    assert fault['records'][-1].skipped and fault['records'][-1].traversal_failures


@pytest.mark.parametrize('flag', ['--sideeffects', '--boundary'])
def test_clean_repair_sibling_flat_and_explicit_exclusion_are_exact(tmp_path, fault, flag):
    entry = _tree(tmp_path / 'project')
    sibling = _tree(tmp_path / 'sibling')
    clean = _cli(entry, flag, 'json')
    sibling_clean = _cli(sibling, flag, 'json')
    flat_clean = _cli(entry, flag, 'json', transitive=False)
    with exclusion_scope(entry.parent, ['included_child']):
        excluded = _cli(entry, flag, 'json')
    fault['deny'] = (entry.parent / 'included_child').resolve()
    assert _cli(sibling, flag, 'json') == sibling_clean
    assert _cli(entry, flag, 'json', transitive=False) == flat_clean
    before = fault['attempts']
    with exclusion_scope(entry.parent, ['included_child']):
        assert _cli(entry, flag, 'json') == excluded
    assert fault['attempts'] == before
    fault['deny'] = None
    assert _cli(entry, flag, 'json') == clean


@pytest.mark.parametrize('flag', ['--sideeffects', '--boundary'])
def test_file_only_note_and_depth_one_stay_exact(tmp_path, fault, flag):
    entry = _tree(tmp_path)
    unreadable = tmp_path / 'unreadable.py'
    unreadable.write_text('def unrelated():\n    return 1\n', encoding='utf-8')
    fault['unreadable'] = unreadable.resolve()
    first = _cli(entry, flag)
    assert first.count('could not be analyzed') == 1
    assert 'directory enumeration(s) failed' not in first
    assert _cli(entry, flag) == first
    shallow = _cli(entry, flag, 'json', depth=1)
    assert not any(row.get('hop', 0) > 1 for row in shallow['findings'])
