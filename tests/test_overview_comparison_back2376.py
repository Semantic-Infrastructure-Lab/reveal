"""Overview comparison qualification and existing comparison proof controls."""

from copy import deepcopy
import json
from urllib.parse import quote

import pytest

pygit2 = pytest.importorskip('pygit2')

from conftest import _run_reveal_direct as run  # noqa: E402
from reveal.adapters.architecture import ArchitectureAdapter  # noqa: E402


def source(complexity):
    branches = ''.join(f'    if value == {n}:\n        return {n}\n' for n in range(complexity - 1))
    return 'from helper import VALUE\n\ndef choose(value):\n' + branches + '    return VALUE\n'


def make_repository(root, *, complexity=13, content=None):
    root.mkdir(parents=True, exist_ok=True)
    repo = pygit2.init_repository(str(root))
    content = content if content is not None else source(complexity) if complexity else 'VALUE = 1\n'
    (root / 'app.py').write_text(content, encoding='utf-8')
    (root / 'helper.py').write_text('VALUE = 1\n', encoding='utf-8')
    (root / '.gitignore').write_text('ignored.py\n', encoding='utf-8')
    repo.index.add_all()
    repo.index.write()
    signature = pygit2.Signature('fixture', 'fixture@example.invalid')
    oid = repo.create_commit('HEAD', signature, signature, 'comparison fixture', repo.index.write_tree(), [])
    repo.references.create('refs/tags/base+%26=é', oid)
    return root


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return make_repository(tmp_path / 'project space & percent%')


def invoke(root, *, noun='overview', transport='cli', ref='HEAD', top=None,
           query='', flags=(), format='json'):
    if transport == 'cli':
        argv = [noun, str(root), '--against', ref]
        if top is not None:
            argv += ['--top', str(top)]
    else:
        parameters = f'against={quote(ref, safe="")}'
        if top is not None:
            parameters += f'&top={top}'
        if query:
            parameters += '&' + query
        argv = [f'{noun}://{quote(root.as_posix(), safe="/.:" )}?{parameters}']
    return run(*argv, '--format', format, *flags)


def corrupt_proof(before, kind):
    result = deepcopy(before)
    analysis = result['analysis']
    if kind == 'basis':
        analysis.pop('basis')
    elif kind == 'unknown_basis':
        analysis['basis'] = 'unknown'
    elif kind == 'snapshots':
        analysis.pop('snapshots')
    elif kind == 'empty_snapshots':
        analysis['snapshots'] = {}
    elif kind in ('base', 'head'):
        analysis['snapshots'].pop(kind)
    elif kind in ('imports', 'complexity'):
        analysis['snapshots']['head'].pop(kind)
    elif kind == 'noncomplete_component':
        analysis['snapshots']['head']['complexity'] = 'incomplete'
    elif kind == 'unexpected_snapshots':
        analysis['snapshots'] = {'head': {'imports': 'complete', 'complexity': 'complete'}}
    else:
        raise AssertionError(f'unrecognized proof corruption: {kind}')
    return result


PROOF_CASES = [
    ('identical_tree', 'basis'), ('identical_tree', 'unknown_basis'),
    ('identical_tree', 'snapshots'), ('identical_tree', 'unexpected_snapshots'),
    ('snapshots', 'basis'), ('snapshots', 'unknown_basis'),
    ('snapshots', 'snapshots'), ('snapshots', 'empty_snapshots'),
    ('snapshots', 'base'), ('snapshots', 'head'),
    ('snapshots', 'imports'), ('snapshots', 'complexity'),
    ('snapshots', 'noncomplete_component'),
]


@pytest.mark.parametrize('basis,kind', PROOF_CASES)
@pytest.mark.parametrize('transport', ['cli', 'uri'])
def test_existing_comparison_rejects_lost_or_contradictory_proof(project, monkeypatch, basis, kind, transport):
    if basis == 'snapshots':
        with (project / 'app.py').open('a', encoding='utf-8') as stream:
            stream.write('\n# tracked edit forces snapshots\n')
    monkeypatch.setattr(ArchitectureAdapter, 'post_process', staticmethod(
        lambda result, args: corrupt_proof(result, kind)))
    response = invoke(project, noun='architecture', transport=transport)
    assert response.returncode == 3, (response.stdout, response.stderr)
    answer = json.loads(response.stdout)
    assert answer['type'] == 'architecture_diff'
    assert any(error['code'] == 'invalid_adapter_answer' for error in answer['meta']['errors'])


@pytest.mark.parametrize('basis', ['identical_tree', 'snapshots'])
@pytest.mark.parametrize('transport', ['cli', 'uri'])
def test_existing_valid_comparison_proof_stays_complete(project, basis, transport):
    if basis == 'snapshots':
        with (project / 'app.py').open('a', encoding='utf-8') as stream:
            stream.write('\n# tracked edit forces snapshots\n')
    response = invoke(project, noun='architecture', transport=transport)
    assert response.returncode == 0, (response.stdout, response.stderr)
    answer = json.loads(response.stdout)
    assert answer['analysis']['basis'] == basis and answer['analysis']['complete'] is True
    if basis == 'identical_tree':
        assert answer['analysis']['snapshots'] == {}
        assert answer['deltas']['complexity_centroid'] == {
            'base': None, 'head': None, 'change': 0.0, 'top_n': 20}
    else:
        assert answer['analysis']['snapshots'] == {
            side: {'imports': 'complete', 'complexity': 'complete'} for side in ('base', 'head')}
        assert answer['deltas']['complexity_centroid'] == {
            'base': 13.0, 'head': 13.0, 'change': 0.0, 'top_n': 20}
