"""Architecture's ordinary and comparison operations share declared execution."""
import copy
import json
from urllib.parse import quote

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.architecture import ArchitectureAdapter


@pytest.fixture
def project(tmp_path, monkeypatch):
    pygit2 = pytest.importorskip('pygit2')
    monkeypatch.chdir(tmp_path)
    root = tmp_path / 'proj'
    root.mkdir()
    repo = pygit2.init_repository(str(root))
    (root / 'a.py').write_text('import os\n', encoding='utf-8')
    (root / 'b.py').write_text('import a\n', encoding='utf-8')
    repo.index.add_all()
    repo.index.write()
    sig = pygit2.Signature('fixture', 'fixture@example.invalid')
    oid = repo.create_commit('HEAD', sig, sig, 'fixture', repo.index.write_tree(), [])
    repo.references.create('refs/tags/base+%26=é', oid)
    (root / 'a.py').write_text('import b\n', encoding='utf-8')
    return root


def equal_answers(left, right):
    left, right = copy.deepcopy(left), copy.deepcopy(right)
    if 'execution' in left:
        assert left['execution']['command'].startswith('reveal architecture ')
        assert right['execution']['command'].startswith('reveal architecture://')
        del left['execution']['command']
        del right['execution']['command']
    assert left == right


@pytest.mark.parametrize('cli,query,identity', [
    ([], '', 'architecture'),
    (['--top', '0'], '?top=0', 'architecture'),
    (['--top', '2', '--no-imports'], '?top=2&no_imports=true', 'architecture'),
    (['--against', 'HEAD'], '?against=HEAD', 'architecture_diff'),
    (['--against', 'HEAD', '--top', '0'], '?against=HEAD&top=0', 'architecture_diff'),
    (['--against', 'base+%26=é'], '?against=base%2B%2526%3D%C3%A9', 'architecture_diff'),
])
@pytest.mark.parametrize('provenance', [False, True])
def test_exact_json_parity(project, cli, query, identity, provenance):
    flags = ['--provenance'] if provenance else []
    a = run('architecture', 'proj', *cli, '--format', 'json', *flags)
    b = run('architecture://proj' + query, '--format', 'json', *flags)
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    left, right = json.loads(a.stdout), json.loads(b.stdout)
    assert left['type'] == right['type'] == identity
    equal_answers(left, right)
    assert 'has no effect' not in a.stderr + b.stderr


@pytest.mark.parametrize('mode', ['', '?against=HEAD'])
def test_text_and_artifact_parity(project, mode):
    cli = ['--against', 'HEAD'] if mode else []
    a = run('architecture', 'proj', *cli, '--also-json', 'a.json')
    b = run('architecture://proj' + mode, '--also-json', 'b.json')
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    assert a.stdout == b.stdout
    equal_answers(json.loads((project.parent / 'a.json').read_text(encoding='utf-8')),
                  json.loads((project.parent / 'b.json').read_text(encoding='utf-8')))


@pytest.mark.parametrize('query,cli', [
    ('against=', ['--against', '']),
    ('against', None),
    ('against=%FF', None),
    ('against=HEAD&top=-1', ['--against', 'HEAD', '--top', '-1']),
    ('against=HEAD&no_imports=false', None),
    ('against=HEAD&no_imports=true', ['--against', 'HEAD', '--no-imports']),
    ('against=HEAD&verbose=false', None),
    ('against=no-such-ref', ['--against', 'no-such-ref']),
])
def test_invalid_diff_keeps_resolved_identity(project, query, cli):
    cases = [['architecture://proj?' + query]]
    if cli is not None:
        cases.append(['architecture', 'proj', *cli])
    for args in cases:
        result = run(*args, '--format', 'json')
        assert result.returncode == 2, result.stderr
        answer = json.loads(result.stdout)
        assert answer['type'] == 'architecture_diff'
        assert answer['error']


@pytest.mark.parametrize('spelling', ['cli', 'uri'])
@pytest.mark.parametrize('kind', ['missing', 'nonrepo', 'verbose'])
def test_diff_request_rejection_before_analysis(project, spelling, kind):
    path = 'missing' if kind == 'missing' else '.' if kind == 'nonrepo' else 'proj'
    argv = ['architecture', path, '--against', 'HEAD'] if spelling == 'cli' else [f'architecture://{path}?against=HEAD']
    if kind == 'verbose':
        argv.append('--verbose')
    result = run(*argv, '--format', 'json')
    assert result.returncode == 2
    assert json.loads(result.stdout)['type'] == 'architecture_diff'


@pytest.mark.parametrize('mode', ['ordinary', 'diff'])
@pytest.mark.parametrize('kind', ['raised', 'wrong', 'empty', 'bare', 'postwrong', 'postempty'])
def test_required_answer_and_projection_failures(project, monkeypatch, mode, kind):
    from reveal.utils.results import ResultBuilder
    identity = 'architecture_diff' if mode == 'diff' else 'architecture'
    if kind.startswith('post'):
        monkeypatch.setattr(ArchitectureAdapter, 'post_process', staticmethod(
            lambda result, args: {} if kind == 'postempty' else
            ResultBuilder.create('wrong', 'proj')), raising=False)
    elif kind == 'raised':
        def failure(self, **kwargs):
            raise OSError('required input inaccessible')
        monkeypatch.setattr(ArchitectureAdapter, 'get_structure', failure)
    else:
        payload = {} if kind == 'empty' else {'error': 'missing evidence'} if kind == 'bare' else ResultBuilder.create('wrong', 'proj')
        monkeypatch.setattr(ArchitectureAdapter, 'get_structure', lambda self, **kw: payload)
    cli = ['--against', 'HEAD'] if mode == 'diff' else []
    query = '?against=HEAD' if mode == 'diff' else ''
    for argv in (['architecture', 'proj', *cli], ['architecture://proj' + query]):
        result = run(*argv, '--format', 'json', '--fail-on', 'none')
        assert result.returncode == 3, result.stderr
        assert json.loads(result.stdout)['type'] == identity


@pytest.mark.parametrize('kind', ['scope', 'imports', 'parse'])
def test_ordinary_missing_evidence_survives_projection(project, monkeypatch, kind):
    if kind == 'scope':
        def fail(*args):
            raise OSError('scope unavailable')
        monkeypatch.setattr('reveal.adapters.architecture.scope_dict_for_path', fail)
    elif kind == 'imports':
        from reveal.adapters.imports import ImportsAdapter
        build = ImportsAdapter._build_graph
        def lost(self, path, **kwargs):
            build(self, path, **kwargs)
            self.analysis.files_lost.append(path / 'a.py')
        monkeypatch.setattr(ImportsAdapter, '_build_graph', lost)
    else:
        (project / 'broken.py').write_text('def broken(:\n', encoding='utf-8')
    for argv in (['architecture', 'proj'], ['architecture://proj']):
        result = run(*argv, '--format', 'json', '--fields', 'facts')
        assert result.returncode == 3, result.stderr


def test_regular_file_and_encoded_resource(project):
    target = project / 'literal?%26,é.py'
    target.write_text('import os\n', encoding='utf-8')
    a = run('architecture', str(target), '--format', 'json')
    b = run('architecture://' + quote(str(target), safe='/'), '--format', 'json')
    assert a.returncode == b.returncode == 0
    equal_answers(json.loads(a.stdout), json.loads(b.stdout))


def test_comparison_guard_rejects_dropped_diagnostic():
    with pytest.raises(AssertionError):
        equal_answers({'meta': {'errors': [{'message': 'lost'}]}}, {'meta': {'errors': []}})
