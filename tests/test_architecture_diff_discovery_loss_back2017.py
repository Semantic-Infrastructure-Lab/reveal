"""Required resolution discovery loss cannot become architectural change evidence."""

import json
import os
from pathlib import Path

import pytest

pygit2 = pytest.importorskip('pygit2')

from conftest import _run_reveal_direct  # noqa: E402
from reveal.analyzers.imports import file_index  # noqa: E402
from reveal.diff import architecture_diff as diff  # noqa: E402
from reveal.mcp_server import _ToolFailure, reveal_query  # noqa: E402


def write(path, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding='utf-8')


def make_repo(root, *, survivors=True, kind='python'):
    repo = pygit2.init_repository(str(root))
    if kind == 'zero':
        write(root / 'empty.py', 'def empty():\n    return 1\n')
    elif kind == 'unsupported':
        write(root / 'script.sh', '#!/bin/sh\necho hello\n')
    else:
        write(root / 'included_child' / 'hidden.py', 'import os\nVALUE = 1\n\ndef hidden():\n    return VALUE\n')
        if survivors:
            write(root / 'visible.py', 'from included_child.hidden import VALUE\n\ndef visible():\n    return VALUE\n')
            write(root / 'stable.py', 'import json\n\ndef stable():\n    return 2\n')
    repo.index.add_all()
    repo.index.write()
    signature = pygit2.Signature('fixture', 'fixture@example.invalid')
    base = str(repo.create_commit('HEAD', signature, signature, 'clean fixture', repo.index.write_tree(), []))
    source = next(path for path in root.rglob('*') if path.suffix in ('.py', '.sh') and '.git' not in path.parts)
    with source.open('a', encoding='utf-8') as stream:
        stream.write('\n# behavior-neutral dirty fixture\n')
    return base


def selective_loss(monkeypatch, root, *, side='head', unknown=False):
    real_walk = file_index.walk_with_causes
    real_scandir = os.scandir
    active = []
    attempts = []

    def walk(*args, **kwargs):
        active.append(Path(args[0]))
        try:
            yield from real_walk(*args, **kwargs)
        finally:
            active.pop()

    def scandir(path):
        selected = active and ((active[-1] == root) is (side == 'head'))
        child = active[-1] / 'included_child' if selected else None
        if child is not None and Path(path) == child:
            attempts.append((active[-1], child))
            if unknown:
                raise PermissionError('controlled unknown resolution enumeration')
            raise PermissionError(13, 'controlled selective resolution denial', str(child))
        return real_scandir(path)

    monkeypatch.setattr(file_index, 'walk_with_causes', walk)
    monkeypatch.setattr(os, 'scandir', scandir)
    return attempts


def invoke(root, base, transport='command', *extra):
    arguments = (['architecture', str(root), '--against', base] if transport == 'command'
                 else [f'architecture://{root.as_posix()}?against={base}'])
    return _run_reveal_direct(*arguments, '--format', 'json', *extra)


@pytest.mark.parametrize('survivors', [False, True])
@pytest.mark.parametrize('transport', ['command', 'uri', 'mcp'])
def test_head_resolution_loss_rejects_deltas_with_healthy_base_and_structures(tmp_path, monkeypatch, survivors, transport):
    root = tmp_path / 'affected'
    base = make_repo(root, survivors=survivors)
    clean = json.loads(invoke(root, base).stdout)
    assert clean['analysis']['complete'] and clean['deltas'] == diff._empty_deltas(20)
    attempts = selective_loss(monkeypatch, root)
    if transport == 'mcp':
        answer = reveal_query(f'architecture://{root.as_posix()}?against={base}', provenance=True)
        assert attempts and all(snapshot == root for snapshot, _ in attempts)
        assert isinstance(answer, _ToolFailure)
        assert 'Architecture comparison unavailable' in answer
        return
    response = invoke(root, base, transport)
    result = json.loads(response.stdout)
    assert attempts and all(snapshot == root for snapshot, _ in attempts)
    states = result['analysis']['snapshots']
    assert states['base'] == {'imports':'complete', 'complexity':'complete'}
    assert states['head']['complexity'] == 'complete'
    assert states['head']['imports'] == 'incomplete'
    assert response.returncode == 3
    assert result['deltas'] is None and result['error']
    (warning,) = [entry for entry in result['meta']['warnings'] if entry.get('type') == 'analysis_incomplete']
    assert warning['snapshot'] == 'head' and warning['component'] == 'imports'
    assert warning['unit'] == 'directories' and warning['count'] == 1
    assert warning['directories'] == ['included_child']
    assert 'missing file population is unknown' in warning['message']


def test_actual_base_resolution_warning_does_not_leak_materialization_path(tmp_path, monkeypatch):
    root = tmp_path / 'affected'
    base = make_repo(root)
    attempts = selective_loss(monkeypatch, root, side='base')
    result = diff.run_architecture_diff(root, base)
    assert attempts and all(snapshot != root for snapshot, _ in attempts)
    (warning,) = [entry for entry in result['meta']['warnings'] if entry.get('type') == 'analysis_incomplete']
    assert warning['snapshot'] == 'base'
    assert warning['directories'] == ['included_child']
    assert 'PermissionError' in warning['causes'][0]
    assert 'reveal-archdiff-' not in json.dumps(warning)
    assert result['analysis']['snapshots']['head'] == {'imports':'complete', 'complexity':'complete'}
    assert result['analysis']['snapshots']['base']['imports'] == 'incomplete'
    assert result['deltas'] is None


@pytest.mark.parametrize('kind', ['zero', 'unsupported'])
def test_clean_zero_and_unsupported_language_keep_complete_empty_deltas(tmp_path, monkeypatch, kind):
    root = tmp_path / 'healthy'
    base = make_repo(root, kind=kind)
    before = invoke(root, base)
    attempts = selective_loss(monkeypatch, root)
    after = invoke(root, base)
    assert (before.returncode, before.stdout, before.stderr) == (after.returncode, after.stdout, after.stderr)
    assert attempts == []
    result = json.loads(after.stdout)
    assert result['analysis']['complete'] and result['deltas'] == diff._empty_deltas(20)
    if kind == 'unsupported':
        assert result['analysis']['unsupported_extensions'] == {'base':{'.sh':1}, 'head':{'.sh':1}}


def test_excluded_subtree_and_healthy_sibling_are_exactly_unchanged(tmp_path, monkeypatch):
    root, sibling = tmp_path / 'affected', tmp_path / 'sibling'
    base, sibling_base = make_repo(root), make_repo(sibling)
    before = invoke(root, base, 'command', '--exclude', 'included_child')
    sibling_before = invoke(sibling, sibling_base)
    attempts = selective_loss(monkeypatch, root)
    after = invoke(root, base, 'command', '--exclude', 'included_child')
    sibling_after = invoke(sibling, sibling_base)
    assert (before.returncode, before.stdout, before.stderr) == (after.returncode, after.stdout, after.stderr)
    assert (sibling_before.returncode, sibling_before.stdout, sibling_before.stderr) == (
        sibling_after.returncode, sibling_after.stdout, sibling_after.stderr)
    assert attempts == []


def test_mixed_actual_parse_and_discovery_loss_preserves_existing_failed_comparison(tmp_path, monkeypatch):
    root = tmp_path / 'affected'
    base = make_repo(root)
    write(root / 'bad.py', 'import math\nif (\n')
    attempts = selective_loss(monkeypatch, root)
    response = invoke(root, base)
    result = json.loads(response.stdout)
    assert attempts and response.returncode == 3
    assert result['deltas'] is None and not result['analysis']['complete']
    kinds = {warning.get('type') for warning in result['meta']['warnings']}
    assert {'analysis_incomplete', 'partial_parse', 'parse_recovered'} <= kinds
