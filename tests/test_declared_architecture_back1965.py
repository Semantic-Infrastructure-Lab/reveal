"""Architecture's ordinary and comparison operations share declared execution."""
import copy
import json
import sys
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
    if provenance:
        assert left['execution']['command'] == ' '.join(
            ['reveal', 'architecture', 'proj', *cli, '--format', 'json', *flags])
        assert right['execution']['command'] == ' '.join(
            ['reveal', 'architecture://proj' + query, '--format', 'json', *flags])
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


@pytest.mark.parametrize('filename', [
    'literal%26,é&=.py',
    pytest.param('literal?%26,é.py', marks=pytest.mark.skipif(
        sys.platform == 'win32', reason='Windows filenames cannot contain question marks')),
])
def test_regular_file_and_encoded_resource(project, filename):
    target = project / filename
    target.write_text('import os\n', encoding='utf-8')
    a = run('architecture', str(target), '--format', 'json')
    b = run('architecture://' + quote(str(target), safe='/'), '--format', 'json')
    assert a.returncode == b.returncode == 0
    equal_answers(json.loads(a.stdout), json.loads(b.stdout))


def test_comparison_guard_rejects_dropped_diagnostic():
    with pytest.raises(AssertionError):
        equal_answers({'meta': {'errors': [{'message': 'lost'}]}}, {'meta': {'errors': []}})


@pytest.mark.parametrize('mode', ['ordinary', 'diff'])
def test_invalid_request_text_and_artifact_failure(project, mode):
    cli = ['--against', 'no-such-ref'] if mode == 'diff' else ['--top', '-1']
    result = run('architecture', 'proj', *cli)
    assert result.returncode == 2
    assert 'Traceback' not in result.stderr
    cli = ['--against', 'HEAD'] if mode == 'diff' else []
    result = run('architecture', 'proj', *cli, '--also-json', str(project))
    assert result.returncode == 3
    assert 'artifact failed' in result.stderr
    result = run('architecture', 'proj', *cli, '--format', 'json', '--also-json', str(project))
    assert result.returncode == 0  # primary JSON keeps the existing mirror no-op
    assert json.loads(result.stdout)['type'].startswith('architecture')


@pytest.mark.parametrize('kind', ['operational', 'dependency', 'corrupt'])
def test_git_operational_failures_are_required_analysis(project, monkeypatch, kind):
    from reveal.diff import architecture_diff
    pygit2 = pytest.importorskip('pygit2')
    exc = {'operational': OSError('git unreadable'), 'dependency': ImportError('pygit2 unavailable'),
           'corrupt': pygit2.GitError('corrupt object') }[kind]
    def fail(path):
        raise exc
    monkeypatch.setattr(architecture_diff, '_open_repo', fail)
    for argv in (['architecture', 'proj', '--against', 'HEAD'], ['architecture://proj?against=HEAD']):
        result = run(*argv, '--format', 'json')
        assert result.returncode == 3
        assert json.loads(result.stdout)['type'] == 'architecture_diff'


@pytest.mark.parametrize('flag', ['--verbose'])
def test_ordinary_global_controls_have_exact_parity(project, flag):
    a = run('architecture', 'proj', flag, '--format', 'json')
    b = run('architecture://proj', flag, '--format', 'json')
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    equal_answers(json.loads(a.stdout), json.loads(b.stdout))


@pytest.mark.parametrize('flags', [[], ['--exclude', 'b.py'], ['--no-gitignore']])
def test_diff_actual_scope_and_fast_proof(project, flags):
    # Dirty contents exercise snapshots; a restored tree exercises the unchanged proof.
    for dirty in (True, False):
        if not dirty:
            (project / 'a.py').write_text('import os\n', encoding='utf-8')
        a = run('architecture', 'proj', '--against', 'HEAD', '--format', 'json', *flags)
        b = run('architecture://proj?against=HEAD', '--format', 'json', *flags)
        assert a.returncode == b.returncode == 0
        left, right = json.loads(a.stdout), json.loads(b.stdout)
        equal_answers(left, right)
        assert left['analysis']['complete']
        if not flags and not dirty:
            assert left['analysis']['basis'] == 'identical_tree'


def test_all_keeps_existing_transport_boundary_and_analysis(project, monkeypatch):
    seen = []
    monkeypatch.setattr('reveal.adapters.architecture._run_combined_analysis',
                        lambda adapter, path, limit: (seen.append(limit) or [], {}))
    rejected = run('architecture', 'proj', '--all')
    assert rejected.returncode == 2 and not rejected.stdout
    assert 'unrecognized arguments: --all' in rejected.stderr
    ordinary = run('architecture://proj', '--format', 'json')
    expanded_text = run('architecture://proj', '--all', '--format', 'json')
    assert ordinary.returncode == expanded_text.returncode == 0
    assert json.loads(ordinary.stdout) == json.loads(expanded_text.stdout)
    assert seen == [20, 20]


@pytest.mark.parametrize('mode', ['ordinary', 'diff'])
def test_runtime_artifact_failure_preserves_primary_json(project, monkeypatch, mode):
    def fail(*args, **kwargs):
        raise OSError('requested artifact failed')
    monkeypatch.setattr('reveal.utils.json_utils.write_also_json', fail)
    query = '?against=HEAD' if mode == 'diff' else ''
    result = run('architecture://proj' + query, '--format', 'json')
    assert result.returncode == 3
    assert json.loads(result.stdout)['meta']['output_errors']


@pytest.mark.parametrize('mode', ['ordinary', 'diff'])
@pytest.mark.parametrize('incomplete,artifact_failure,expected', [
    (False, False, 0), (True, False, 3), (False, True, 3),
])
def test_closed_pipe_preserves_independent_failures(project, mode, incomplete, artifact_failure, expected):
    import os
    import subprocess
    if incomplete:
        (project / 'broken.py').write_text('def broken(:\n', encoding='utf-8')
    argv = [sys.executable, '-m', 'reveal', 'architecture', 'proj']
    if mode == 'diff':
        argv.extend(['--against', 'HEAD'])
    if artifact_failure:
        argv.extend(['--also-json', str(project)])
    with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env=os.environ.copy()) as process:
        process.stdout.close()
        code = process.wait(timeout=30)
        errors = process.stderr.read().decode('utf-8', errors='replace')
    assert code == expected, errors
    assert 'Traceback' not in errors


@pytest.mark.parametrize('incomplete', [False, True])
def test_postprocess_cannot_drop_required_comparison_proof(project, monkeypatch, incomplete):
    if incomplete:
        (project / 'broken.py').write_text('def broken(:\n', encoding='utf-8')
    def project_answer(result, args):
        return {key: value for key, value in result.items() if key != 'analysis'}
    monkeypatch.setattr(ArchitectureAdapter, 'post_process', staticmethod(project_answer), raising=False)
    result = run('architecture://proj?against=HEAD', '--format', 'json')
    assert result.returncode == 3, result.stderr
    assert json.loads(result.stdout)['type'] == 'architecture_diff'


@pytest.mark.parametrize('incomplete', [False, True])
def test_fields_projection_retains_preanalysis_facts(project, incomplete):
    if incomplete:
        (project / 'broken.py').write_text('def broken(:\n', encoding='utf-8')
    result = run('architecture://proj?against=HEAD', '--format', 'json', '--fields', 'deltas')
    assert result.returncode == (3 if incomplete else 0), result.stderr


@pytest.mark.parametrize('name,identity', [
    ('architecture', 'architecture'), ('architecture', 'architecture_diff'), ('surface', 'surface_scan'),
])
@pytest.mark.parametrize('phase', ['analysis', 'postprocess'])
@pytest.mark.parametrize('field', ['errors', 'warnings'])
@pytest.mark.parametrize('bad', [None, 7, ['unusable'], [{'code': 'retained', 'message': 'valid diagnostic'}, 'unusable']])
def test_malformed_trust_frame_is_canonical_failure(project, monkeypatch, name, identity, phase, field, bad):
    from reveal.adapters.surface import SurfaceAdapter
    from reveal.utils.results import ResultBuilder
    owner = ArchitectureAdapter if name == 'architecture' else SurfaceAdapter
    result = ResultBuilder.create(identity, 'proj', meta={field: bad},
                                  data={'analysis': {'complete': True}} if identity == 'architecture_diff' else {})
    if phase == 'analysis':
        monkeypatch.setattr(owner, 'get_structure', lambda self, **kwargs: result)
    else:
        monkeypatch.setattr(owner, 'post_process', staticmethod(lambda before, args: result), raising=False)
    query = '?against=HEAD' if identity == 'architecture_diff' else ''
    answer = run(name + '://proj' + query, '--format', 'json')
    assert answer.returncode == 3, answer.stderr
    payload = json.loads(answer.stdout)
    assert payload['type'] == identity
    assert any(e.get('code') == 'invalid_adapter_answer' for e in payload['meta']['errors'])
    if isinstance(bad, list) and bad and isinstance(bad[0], dict):
        assert bad[0] in payload['meta'][field]


@pytest.mark.parametrize('keep_proof,expected', [(False, 3), (True, 2)])
def test_postprocess_usage_cannot_hide_lost_required_proof(project, monkeypatch, keep_proof, expected):
    def process(result, args):
        if not keep_proof:
            result.pop('analysis')
        result['error'] = 'invalid entry'
        result['meta'] = {'errors': [{'code': 'invalid_request', 'message': 'invalid entry'}]}
        return result
    monkeypatch.setattr(ArchitectureAdapter, 'post_process', staticmethod(process), raising=False)
    answer = run('architecture://proj?against=HEAD', '--format', 'json')
    assert answer.returncode == expected, answer.stderr
