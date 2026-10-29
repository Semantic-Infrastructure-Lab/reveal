"""Identical trees prove zero change without measuring either centroid."""

import json

import pytest

pygit2 = pytest.importorskip('pygit2')

from conftest import _run_reveal_direct  # noqa: E402


def _source(complexity):
    branches = ''.join(f'    if value == {index}:\n        return {index}\n'
                       for index in range(complexity - 1))
    return 'def choose(value):\n' + branches + '    return -1\n'


def _repo(root, source):
    repo = pygit2.init_repository(str(root))
    (root / 'app.py').write_text(source, encoding='utf-8')
    repo.index.add('app.py')
    repo.index.write()
    signature = pygit2.Signature('fixture', 'fixture@example.invalid')
    repo.create_commit('HEAD', signature, signature, 'centroid fixture', repo.index.write_tree(), [])


def _invoke(root, transport, *, provenance=False, top=5, ref='HEAD', format='json'):
    if transport == 'command':
        arguments = ['architecture', str(root), '--against', ref, '--top', str(top)]
    else:
        arguments = [f'architecture://{root.as_posix()}?against={ref}&top={top}']
    return _run_reveal_direct(*arguments, '--format', format,
                              *(['--provenance'] if provenance else []))


@pytest.mark.parametrize('transport', ['command', 'uri'])
@pytest.mark.parametrize('provenance', [False, True])
@pytest.mark.parametrize('top,population', [(0, 4), (5, 20)])
def test_identical_tree_centroids_are_unmeasured(tmp_path, transport, provenance, top, population):
    _repo(tmp_path, _source(13))
    response = _invoke(tmp_path, transport, provenance=provenance, top=top)
    result = json.loads(response.stdout)
    assert response.returncode == 0
    assert result['analysis'] == {'complete': True, 'basis': 'identical_tree', 'snapshots': {}}
    assert ('execution' in result) is provenance
    assert result['deltas']['complexity_centroid'] == {
        'base': None, 'head': None, 'change': 0.0, 'top_n': population,
    }
    assert result['deltas']['fan_in'] == result['deltas']['fan_out'] == []
    assert result['deltas']['component_coupling'] == []
    assert result['deltas']['circular_groups'] == {'introduced': [], 'resolved': []}
    assert result['deltas']['entry_points'] == {'added': [], 'removed': []}


@pytest.mark.parametrize('transport', ['command', 'uri'])
@pytest.mark.parametrize('provenance', [False, True])
@pytest.mark.parametrize('base,head,change', [(13, 13, 0.0), (13, 23, 10.0), (0, 0, 0.0)])
def test_analyzed_centroids_remain_measurements(tmp_path, transport, provenance, base, head, change):
    _repo(tmp_path, _source(base) if base else 'VALUE = 1\n')
    # A tracked edit forces normal snapshots, including the unchanged and zero controls.
    source = _source(head) if head else 'VALUE = 1\n'
    (tmp_path / 'app.py').write_text(source + '\n# tracked working-tree edit\n', encoding='utf-8')
    response = _invoke(tmp_path, transport, provenance=provenance)
    result = json.loads(response.stdout)
    assert response.returncode == 0
    assert result['analysis']['complete'] is True
    assert result['analysis']['basis'] == 'snapshots'
    assert result['analysis']['snapshots'] == {
        'base': {'imports': 'complete', 'complexity': 'complete'},
        'head': {'imports': 'complete', 'complexity': 'complete'},
    }
    assert result['deltas']['complexity_centroid'] == {
        'base': float(base), 'head': float(head), 'change': change, 'top_n': 20,
    }


@pytest.mark.parametrize('transport', ['command', 'uri'])
@pytest.mark.parametrize('provenance', [False, True])
def test_missing_snapshot_evidence_still_rejects_deltas(tmp_path, transport, provenance):
    _repo(tmp_path, _source(13))
    (tmp_path / 'app.py').write_text('def broken(\n', encoding='utf-8')
    response = _invoke(tmp_path, transport, provenance=provenance)
    result = json.loads(response.stdout)
    assert response.returncode == 3
    assert result['analysis']['complete'] is False
    assert result['analysis']['basis'] == 'snapshots'
    assert result['analysis']['snapshots']['base'] == {'imports': 'complete', 'complexity': 'complete'}
    assert result['deltas'] is None


@pytest.mark.parametrize('transport', ['command', 'uri'])
def test_invalid_ref_still_exits_two(tmp_path, transport):
    _repo(tmp_path, _source(13))
    response = _invoke(tmp_path, transport, ref='missing-centroid-ref')
    result = json.loads(response.stdout)
    assert response.returncode == 2
    assert result['type'] == 'architecture_diff'
    assert result['error']


@pytest.mark.parametrize('transport', ['command', 'uri'])
def test_identical_text_explains_unmeasured_snapshots(tmp_path, transport):
    _repo(tmp_path, _source(13))
    response = _invoke(tmp_path, transport, format='text')
    assert response.returncode == 0
    assert 'is identical to HEAD, so neither snapshot was analyzed.' in response.stdout
    assert 'Complexity centroid' not in response.stdout
