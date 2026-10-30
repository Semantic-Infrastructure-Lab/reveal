"""Overview comparison qualification and existing comparison proof controls."""

from copy import deepcopy
import json
from urllib.parse import quote

import pytest

pygit2 = pytest.importorskip('pygit2')

from conftest import _run_reveal_direct as run  # noqa: E402
from reveal import api  # noqa: E402
from reveal.adapters.architecture import ArchitectureAdapter  # noqa: E402
from reveal.adapters.overview import OverviewAdapter  # noqa: E402


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
        argv = [f'{noun}://{quote(root.as_posix(), safe="/.:")}?{parameters}']
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


@pytest.mark.parametrize('side', ['base', 'head'])
@pytest.mark.parametrize('transport', ['cli', 'uri'])
def test_existing_required_snapshot_loss_stays_incomplete(tmp_path, side, transport):
    root = make_repository(tmp_path / 'loss', content='def broken(\n' if side == 'base' else None)
    (root / 'app.py').write_text(source(13) if side == 'base' else 'def broken(\n', encoding='utf-8')
    response = invoke(root, noun='architecture', transport=transport)
    assert response.returncode == 3, (response.stdout, response.stderr)
    answer = json.loads(response.stdout)
    assert answer['analysis']['basis'] == 'snapshots'
    assert answer['analysis']['complete'] is False
    assert answer['deltas'] is None
    assert answer['analysis']['snapshots'][side]['complexity'] != 'complete'
    assert not any(error.get('code') == 'invalid_adapter_answer'
                   for error in answer.get('meta', {}).get('errors', []))


def canonical(response, code=0):
    assert response.returncode == code, (response.stdout, response.stderr)
    answer = json.loads(response.stdout)
    assert answer['type'] == 'overview_diff'
    return answer


def same_answer(left, right):
    left, right = deepcopy(left), deepcopy(right)
    if 'execution' in left:
        assert left['execution']['command'] and right['execution']['command']
        del left['execution']['command'], right['execution']['command']
    assert left == right


@pytest.mark.parametrize('ref', ['HEAD', 'base+%26=é'])
@pytest.mark.parametrize('top,population', [(0, 4), (2, 8), (5, 20)])
@pytest.mark.parametrize('provenance', [False, True])
def test_overview_comparison_exact_parity_and_live_head(project, ref, top, population, provenance):
    (project / 'app.py').write_text(source(23), encoding='utf-8')
    flags = ['--provenance'] if provenance else []
    left = canonical(invoke(project, ref=ref, top=top, flags=flags))
    right = canonical(invoke(project, transport='uri', ref=ref, top=top, flags=flags))
    same_answer(left, right)
    assert left['base_ref'] == ref and left['head_ref'] == 'working tree'
    assert left['path'] == left['source'] == project.as_posix()
    assert left['analysis']['basis'] == 'snapshots' and left['analysis']['complete'] is True
    assert left['deltas']['complexity_centroid'] == {
        'base': 13.0, 'head': 23.0, 'change': 10.0, 'top_n': population}


@pytest.mark.parametrize('transport', ['cli', 'uri'])
@pytest.mark.parametrize('top,population', [(0, 4), (5, 20)])
def test_overview_identical_tree_retains_unmeasured_centroids(project, transport, top, population):
    answer = canonical(invoke(project, transport=transport, top=top))
    assert answer['analysis'] == {'complete': True, 'basis': 'identical_tree', 'snapshots': {}}
    assert answer['head_ref'] == 'working tree'
    assert answer['deltas']['complexity_centroid'] == {
        'base': None, 'head': None, 'change': 0.0, 'top_n': population}
    text = invoke(project, transport=transport, top=top, format='text')
    assert text.returncode == 0
    assert 'neither snapshot was analyzed' in text.stdout
    assert 'Complexity centroid' not in text.stdout


@pytest.mark.parametrize('base,head', [(0, 0), (13, 13), (13, 23)])
def test_overview_analyzed_zero_unchanged_and_changed_are_measurements(tmp_path, base, head):
    root = make_repository(tmp_path / 'measurements', complexity=base)
    content = source(head) if head else 'VALUE = 1\n'
    (root / 'app.py').write_text(content + '\n# force real snapshots\n', encoding='utf-8')
    answer = canonical(invoke(root))
    assert answer['analysis']['basis'] == 'snapshots'
    assert answer['deltas']['complexity_centroid'] == {
        'base': float(base), 'head': float(head), 'change': float(head - base), 'top_n': 20}


def test_overview_comparison_retains_actual_cycle_and_entrypoint_deltas(project):
    (project / 'helper.py').write_text('from app import choose\nVALUE = 1\n', encoding='utf-8')
    answer = canonical(invoke(project))
    assert answer['deltas']['circular_groups'] == {'introduced': [['app.py', 'helper.py']], 'resolved': []}
    assert answer['deltas']['entry_points'] == {'added': [], 'removed': ['app.py']}
    assert answer['edge_rule'] and answer['edge_rule_sections']


@pytest.mark.parametrize('side', ['base', 'head'])
@pytest.mark.parametrize('transport', ['cli', 'uri'])
@pytest.mark.parametrize('fields', [(), ('--fields', 'deltas')])
def test_overview_required_snapshot_loss_survives_projection(tmp_path, side, transport, fields):
    root = make_repository(tmp_path / 'loss', content='def broken(\n' if side == 'base' else None)
    (root / 'app.py').write_text(source(13) if side == 'base' else 'def broken(\n', encoding='utf-8')
    answer = canonical(invoke(root, transport=transport, flags=fields), 3)
    assert answer['analysis']['complete'] is False and answer['analysis']['basis'] == 'snapshots'
    assert answer['deltas'] is None and answer['error']
    assert answer['analysis']['snapshots'][side]['complexity'] != 'complete'


@pytest.mark.parametrize('transport', ['cli', 'uri'])
@pytest.mark.parametrize('kind', ['ref', 'resource', 'nonrepo'])
def test_overview_invalid_comparison_is_canonical_usage(project, transport, kind):
    root = project / 'missing' if kind == 'resource' else project.parent if kind == 'nonrepo' else project
    answer = canonical(invoke(root, transport=transport, ref='missing-ref' if kind == 'ref' else 'HEAD'), 2)
    assert answer['error']
    assert all(error['code'] == 'invalid_request' for error in answer['meta']['errors'])


@pytest.mark.parametrize('query', ['against', 'against=', 'against=%FF', 'against=HEAD&top=-1'])
def test_overview_malformed_uri_still_resolves_comparison_identity(project, query):
    response = run(f'overview://{quote(project.as_posix(), safe="/.:")}?{query}', '--format', 'json')
    assert canonical(response, 2)['error']


@pytest.mark.parametrize('control', ['no_imports', 'all', 'verbose'])
@pytest.mark.parametrize('value', ['true', 'false'])
def test_overview_comparison_rejects_explicit_ordinary_uri_controls(project, control, value):
    assert canonical(invoke(project, transport='uri', query=f'{control}={value}'), 2)['error']


@pytest.mark.parametrize('flag', ['--no-imports', '--all', '--verbose', '--no-git'])
def test_overview_comparison_rejects_ordinary_cli_controls(project, flag):
    assert canonical(invoke(project, flags=[flag]), 2)['error']


@pytest.mark.parametrize('control', ['no_imports', 'all', 'verbose'])
@pytest.mark.parametrize('value', [False, True])
def test_api_comparison_controls_reject_before_map_or_engine(project, monkeypatch, control, value):
    from reveal.adapters import overview
    from reveal.diff import architecture_diff
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError('incompatible comparison reached analysis')
    monkeypatch.setattr(overview, '_run_scope', forbidden)
    monkeypatch.setattr(overview, '_run_imports_analysis', forbidden)
    monkeypatch.setattr(architecture_diff, 'run_architecture_diff', forbidden)
    with pytest.raises(ValueError):
        api.query(f'overview://{project.as_posix()}?against=HEAD', **{control: value})
    assert calls == []


@pytest.mark.parametrize('control', ['all', 'verbose'])
def test_direct_owner_comparison_controls_cannot_bypass_validation(project, monkeypatch, control):
    from reveal.adapters import overview
    def forbidden(*args, **kwargs):
        raise AssertionError('direct incompatible comparison reached census')
    monkeypatch.setattr(overview, '_run_scope', forbidden)
    with pytest.raises(ValueError):
        OverviewAdapter(str(project), 'against=HEAD').get_structure(**{control: True})


def test_api_none_resets_operation_and_typed_top_overrides_uri(project, monkeypatch):
    from reveal.diff import architecture_diff
    ordinary = api.query(f'overview://{project.as_posix()}')
    original = architecture_diff.run_architecture_diff
    def forbidden(*args, **kwargs):
        raise AssertionError('None reset selected comparison')
    monkeypatch.setattr(architecture_diff, 'run_architecture_diff', forbidden)
    assert api.query(f'overview://{project.as_posix()}?against=HEAD', against=None) == ordinary
    monkeypatch.setattr(architecture_diff, 'run_architecture_diff', original)
    result = api.query(f'overview://{project.as_posix()}?against=HEAD&top=5', top=0)
    assert result['type'] == 'overview_diff'
    assert result['deltas']['complexity_centroid']['top_n'] == 4


@pytest.mark.parametrize('query', ['against=', 'against=%FF'])
def test_api_valid_override_cannot_rescue_invalid_original_uri(project, query):
    with pytest.raises(ValueError):
        api.query(f'overview://{project.as_posix()}?{query}', against='HEAD')


@pytest.mark.parametrize('transport', ['cli', 'uri', 'api'])
def test_ordinary_overview_never_calls_comparison_engine(project, monkeypatch, transport):
    from reveal.diff import architecture_diff
    def forbidden(*args, **kwargs):
        raise AssertionError('ordinary map invoked comparison engine')
    monkeypatch.setattr(architecture_diff, 'run_architecture_diff', forbidden)
    if transport == 'api':
        answer = api.query(f'overview://{project.as_posix()}')
    else:
        argv = ['overview', str(project)] if transport == 'cli' else [f'overview://{project.as_posix()}']
        response = run(*argv, '--format', 'json')
        assert response.returncode == 0, response.stderr
        answer = json.loads(response.stdout)
    assert answer['type'] == 'overview' and answer['map_status'] == 'complete'


@pytest.mark.parametrize('ref,expected', [('HEAD', 0), ('missing-ref', 2)])
@pytest.mark.parametrize('transport', ['cli', 'uri'])
def test_comparison_never_calls_ordinary_map_collectors(project, monkeypatch, ref, expected, transport):
    from reveal.adapters import overview
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError('comparison invoked ordinary map owner')
    monkeypatch.setattr(overview, '_run_scope', forbidden)
    monkeypatch.setattr(overview, '_run_imports_analysis', forbidden)
    canonical(invoke(project, transport=transport, ref=ref), expected)
    assert calls == []


@pytest.mark.parametrize('basis,kind', PROOF_CASES)
def test_overview_comparison_uses_required_proof_guard(project, monkeypatch, basis, kind):
    if basis == 'snapshots':
        (project / 'app.py').write_text(source(23), encoding='utf-8')
    monkeypatch.setattr(OverviewAdapter, 'post_process', staticmethod(
        lambda result, args: corrupt_proof(result, kind)))
    answer = canonical(invoke(project), 3)
    assert any(error['code'] == 'invalid_adapter_answer' for error in answer['meta']['errors'])


@pytest.mark.parametrize('transport', ['cli', 'uri'])
def test_comparison_artifact_fields_and_output_failure_keep_outcomes(project, tmp_path, transport):
    (project / 'app.py').write_text(source(23), encoding='utf-8')
    artifact = tmp_path / 'comparison.json'
    answer = canonical(invoke(project, transport=transport, flags=['--output', f'json={artifact}']))
    assert json.loads(artifact.read_text(encoding='utf-8')) == answer
    selected = canonical(invoke(project, transport=transport, flags=['--fields', 'deltas']))
    assert selected['deltas'] == answer['deltas']
    assert 'analysis' not in selected  # explicit payload selection retains the independently captured outcome
    failed = canonical(invoke(project, transport=transport, flags=['--output', f'json={tmp_path}']), 3)
    assert failed['meta']['output_errors']


@pytest.mark.parametrize('flags', [('--head', '1'), ('--max-items', '1'), ('--exclude', 'app.py')])
def test_comparison_controls_preserve_population_and_symmetric_policy(project, flags):
    (project / 'app.py').write_text(source(23), encoding='utf-8')
    left = canonical(invoke(project, flags=flags))
    right = canonical(invoke(project, transport='uri', flags=flags))
    same_answer(left, right)
    centroid = left['deltas']['complexity_centroid']
    assert centroid['top_n'] == 20
    assert centroid['base'] == (0.0 if '--exclude' in flags else 13.0)
    assert centroid['head'] == (0.0 if '--exclude' in flags else 23.0)


def test_comparison_gitignore_policy_selects_live_ignored_files(project):
    (project / 'ignored.py').write_text('from app import choose\n', encoding='utf-8')
    ignored = canonical(invoke(project))
    assert ignored['analysis']['basis'] == 'identical_tree'
    included = canonical(invoke(project, flags=['--no-gitignore']))
    uri = canonical(invoke(project, transport='uri', query='respect_gitignore=false'))
    same_answer(included, uri)
    assert included['analysis']['basis'] == 'snapshots'
    assert any(row['file'] == 'app.py' and row['head'] == 1 for row in included['deltas']['fan_in'])


def test_overview_schema_declares_comparison_without_a_second_mode():
    schema = OverviewAdapter.get_schema()
    assert schema['query_params']['against']['role'] == 'operation'
    assert schema['query_params']['against']['uri_codec'] == 'percent'
    assert {'overview', 'overview_diff'} <= {output['type'] for output in schema['output_types']}
    assert 'section' not in schema['query_params']
