"""A capped required import snapshot cannot supply architectural deltas."""

from dataclasses import replace
import json
from pathlib import Path

import pytest

pygit2 = pytest.importorskip('pygit2')

from conftest import _run_reveal_direct as run  # noqa: E402
from reveal.analyzers.imports import service  # noqa: E402
from reveal.diff import architecture_diff as diff  # noqa: E402
from reveal.mcp_server import _ToolFailure, reveal_query  # noqa: E402


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    repo = pygit2.init_repository(str(root))
    for name, source in {'a.py': 'import b\n', 'b.py': 'VALUE = 1\n'}.items():
        (root / name).write_text(source, encoding='utf-8')
    repo.index.add_all()
    repo.index.write()
    author = pygit2.Signature('fixture', 'fixture@example.invalid')
    repo.create_commit('HEAD', author, author, 'fixture', repo.index.write_tree(), [])
    return root


def dirty(root):
    with (root / 'a.py').open('a', encoding='utf-8') as stream:
        stream.write('# equivalent dirty snapshot\n')


def cap_snapshot(monkeypatch, root, side, evidence='both', limit=1):
    """Use actual bounded discovery, optionally retain only one authoritative cap record."""
    original = service.analyze
    observed = []

    def analyze(scope, **kwargs):
        selected = (scope.root.resolve() == root.resolve()) is (side == 'head')
        built = original(replace(scope, cap=limit) if selected else scope, **kwargs)
        if selected:
            observed.append((len(built.files.candidates), built.files.capped))
            if evidence == 'metadata':
                built = replace(built, files=replace(built.files, capped=False))
            elif evidence == 'files':
                built.analysis.resolution.capped = False
        return built

    monkeypatch.setattr(service, 'analyze', analyze)
    return observed


def invoke(root, scheme, transport, *flags):
    args = ([scheme, str(root), '--against', 'HEAD'] if transport == 'command'
            else [f'{scheme}://{root.as_posix()}?against=HEAD'])
    return run(*args, '--format', 'json', *flags)


@pytest.mark.parametrize('scheme', ['architecture', 'overview'])
@pytest.mark.parametrize('transport', ['command', 'uri'])
@pytest.mark.parametrize('side', ['base', 'head'])
@pytest.mark.parametrize('evidence', ['both', 'metadata', 'files'])
def test_real_capped_snapshot_rejects_comparison(project, monkeypatch, scheme, transport, side, evidence):
    dirty(project)
    observed = cap_snapshot(monkeypatch, project, side, evidence)
    response = invoke(project, scheme, transport)
    result = json.loads(response.stdout)
    assert observed == [(1, True)]
    assert response.returncode == 3, response.stdout
    assert result['analysis']['snapshots'][side] == {'imports': 'incomplete', 'complexity': 'complete'}
    other = 'head' if side == 'base' else 'base'
    assert result['analysis']['snapshots'][other] == {'imports': 'complete', 'complexity': 'complete'}
    assert result['analysis']['complete'] is False and result['deltas'] is None
    warnings = [w for w in result['meta']['warnings'] if w['type'] == 'scan_capped']
    assert len(warnings) == 1
    assert warnings[0]['snapshot'] == side and warnings[0]['component'] == 'imports'


@pytest.mark.parametrize('scheme', ['architecture', 'overview'])
@pytest.mark.parametrize('side', ['base', 'head'])
def test_cap_remains_failed_through_fields_provenance_and_mcp(project, monkeypatch, scheme, side):
    dirty(project)
    cap_snapshot(monkeypatch, project, side)
    response = invoke(project, scheme, 'uri', '--fields', 'analysis', '--provenance')
    result = json.loads(response.stdout)
    assert response.returncode == 3
    assert result['analysis']['complete'] is False
    assert result['execution']['command']
    assert any(w['type'] == 'scan_capped' for w in result['meta']['warnings'])
    answer = reveal_query(f'{scheme}://{project.as_posix()}?against=HEAD', provenance=True)
    assert isinstance(answer, _ToolFailure)
    assert 'comparison unavailable' in answer.lower()


@pytest.mark.parametrize('scheme', ['architecture', 'overview'])
@pytest.mark.parametrize('top', [0, 5])
def test_uncapped_exact_population_keeps_measured_comparison(project, monkeypatch, scheme, top):
    dirty(project)
    before = invoke(project, scheme, 'command', '--top', str(top))
    observed = cap_snapshot(monkeypatch, project, 'head', limit=2)
    after = invoke(project, scheme, 'command', '--top', str(top))
    assert observed == [(2, False)]
    assert before.returncode == after.returncode == 0
    assert json.loads(before.stdout) == json.loads(after.stdout)


def test_identical_tree_needs_no_import_scan_even_with_tiny_cap(project, monkeypatch):
    observed = cap_snapshot(monkeypatch, project, 'head')
    result = diff.run_architecture_diff(Path(project), 'HEAD')
    assert observed == []
    assert result['analysis'] == {'complete': True, 'basis': 'identical_tree', 'snapshots': {}}
    assert result['deltas']['complexity_centroid']['base'] is None
