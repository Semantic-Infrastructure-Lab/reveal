"""Callee effects identify their hand-written source sites in both nav views."""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.utils.path_utils import to_posix

pytestmark = pytest.mark.component


@pytest.fixture
def sources(tmp_path):
    files = {
        'root.py': ('import left\nimport right\nimport logging\nstate = {}\n'
                    'def entry(key):\n    logging.info("own")\n    state[key] = 1\n'
                    '    left.send()\n    right.send()\n'),
        'left.py': ('import requests\ndef send():\n    requests.get("same")\n'
                    '    finish()\ndef finish():\n    logging.info("deep")\n'),
        'right.py': 'import requests\ndef send():\n    requests.get("same")\n',
    }
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding='utf-8')
    return tmp_path


def _run(target, flag, *extra):
    result = _run_reveal_direct(target, 'entry', flag, *extra)
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.mark.parametrize('flag', ['--sideeffects', '--boundary'])
@pytest.mark.parametrize('relative', [False, True])
def test_callee_sources_and_depth_order(sources, monkeypatch, flag, relative):
    monkeypatch.chdir(sources.parent)
    prefix = sources.name if relative else to_posix(sources.resolve())
    target = f'{prefix}/root.py'
    data = json.loads(_run(target, flag, '--transitive', '--depth', '2', '--format', 'json'))
    children = [row for row in data['findings'] if row.get('hop', 0) > 0]
    assert [(row.get('file'), row['line'], row['callee'], row['hop'], row['chain']) for row in children] == [
        (f'{prefix}/left.py', 3, 'requests.get', 1, ['entry', 'send']),
        (f'{prefix}/right.py', 3, 'requests.get', 1, ['entry', 'send']),
        (f'{prefix}/left.py', 6, 'logging.info', 2, ['entry', 'send', 'finish']),
    ]
    assert [{k: v for k, v in row.items() if k != 'file'} for row in children[:2]][0] == {k: v for k, v in children[1].items() if k != 'file'}
    text = _run(target, flag, '--transitive', '--depth', '2')
    sites = [f'[{prefix}/{name}:{line}]' for name, line in [('left.py', 3), ('right.py', 3), ('left.py', 6)]]
    assert all(site in text for site in sites)
    assert [text.index(site) for site in sites] == sorted(text.index(site) for site in sites)
    own = [row for row in data['findings'] if row.get('hop') == 0]
    assert own and all('file' not in row for row in own)
    ordinary = json.loads(_run(target, flag, '--format', 'json'))
    assert own == [{**row, 'hop': 0, 'chain': ['entry']} for row in ordinary['findings'] if 'callee' in row]
    assert all('file' not in row for row in ordinary['findings'])
    own_text = _run(target, flag)
    assert f'[{prefix}/root.py:' not in text and '[' + prefix not in own_text
    if relative:
        assert to_posix(sources.resolve()) not in json.dumps(data)
        assert to_posix(sources.resolve()) not in text


@pytest.mark.parametrize('flag', ['--sideeffects', '--boundary'])
def test_backslash_callee_paths_serialize_in_json_and_text(sources, monkeypatch, flag):
    from reveal.adapters.ast import nav, nav_boundary, nav_effects

    real = nav_effects.collect_effects_transitive

    def backslash_sources(*args, **kwargs):
        effects = real(*args, **kwargs)
        for effect in effects:
            if effect.get('hop', 0) > 0:
                effect['file'] = 'pkg\\' + effect['file'].replace('\\', '/').rsplit('/', 1)[-1]
        return effects

    monkeypatch.setattr(nav, 'collect_effects_transitive', backslash_sources)
    monkeypatch.setattr(nav_boundary, 'collect_effects_transitive', backslash_sources)
    target = str(sources / 'root.py')
    data = json.loads(_run(target, flag, '--transitive', '--format', 'json'))
    assert [(row.get('file'), row['line']) for row in data['findings'] if row.get('hop', 0) > 0] == [
        ('pkg/left.py', 3), ('pkg/right.py', 3), ('pkg/left.py', 6)]
    text = _run(target, flag, '--transitive')
    assert '[pkg/left.py:3]' in text and '[pkg/right.py:3]' in text and '[pkg/left.py:6]' in text
    assert 'pkg\\' not in text


@pytest.mark.parametrize('flag', ['--sideeffects', '--boundary'])
@pytest.mark.parametrize('relative', [False, True])
def test_native_text_identifies_each_same_line_source(sources, monkeypatch, flag, relative):
    monkeypatch.chdir(sources.parent)
    prefix = sources.name if relative else to_posix(sources.resolve())
    text = _run(f'{prefix}/root.py', flag, '--transitive')
    assert f'requests.get("same") [{prefix}/left.py:3]' in text
    assert f'requests.get("same") [{prefix}/right.py:3]' in text


@pytest.mark.parametrize('flag', ['--sideeffects', '--boundary'])
def test_root_and_ordinary_records_keep_existing_shape(sources, flag):
    target = str(sources / 'root.py')
    ordinary = json.loads(_run(target, flag, '--format', 'json'))
    transitive = json.loads(_run(target, flag, '--transitive', '--format', 'json'))
    own = [row for row in transitive['findings'] if row.get('hop') == 0]
    assert own == [{**row, 'hop': 0, 'chain': ['entry']} for row in ordinary['findings'] if 'callee' in row]
    assert all('file' not in row for row in ordinary['findings'] + own)
    assert [row for row in transitive['findings'] if 'hop' not in row] == [
        row for row in ordinary['findings'] if 'callee' not in row]


@pytest.mark.parametrize('flag', ['--sideeffects', '--boundary'])
def test_absolute_discovered_sources_keep_relative_target_privacy(sources, monkeypatch, flag):
    from pathlib import Path
    from reveal.adapters.calls import index as calls_index

    monkeypatch.chdir(sources.parent)
    real_walk = calls_index.walk_callees

    def absolute_sources(*args, **kwargs):
        walk = real_walk(*args, **kwargs)
        frontier = list(walk.roots)
        seen = set()
        while frontier:
            node = frontier.pop()
            if id(node) in seen:
                continue
            seen.add(id(node))
            for _, child in node.edges:
                if child is not None:
                    child.file = str(Path(child.file).resolve())
                    frontier.append(child)
        return walk

    monkeypatch.setattr(calls_index, 'walk_callees', absolute_sources)
    target = f'{sources.name}/root.py'
    data = json.loads(_run(target, flag, '--transitive', '--format', 'json'))
    assert [(row.get('file'), row['line']) for row in data['findings'] if row.get('hop', 0) > 0] == [
        (f'{sources.name}/left.py', 3), (f'{sources.name}/right.py', 3), (f'{sources.name}/left.py', 6)]
    text = _run(target, flag, '--transitive')
    assert f'[{sources.name}/left.py:3]' in text and f'[{sources.name}/right.py:3]' in text
    assert to_posix(sources.resolve()) not in text
    assert to_posix(sources.resolve()) not in json.dumps(data)
