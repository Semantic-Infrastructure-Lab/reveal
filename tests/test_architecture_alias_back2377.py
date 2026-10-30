"""The retired architecture spelling shares Overview binding, proof and presentation."""
from copy import deepcopy
import json
from urllib.parse import quote

import pytest

from conftest import _run_reveal_direct as run
from reveal import api
from reveal.adapters.architecture import ArchitectureAdapter
from reveal.adapters.overview import OverviewAdapter
from reveal.rendering.adapters.architecture import ArchitectureRenderer
from reveal.rendering.adapters.overview import OverviewRenderer


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / 'project & percent%'
    for number in range(7):
        folder = root / f'pkg{number}'
        folder.mkdir(parents=True)
        (folder / 'module.py').write_text('VALUE = 1\n', encoding='utf-8')
    return root


def uri(project, query=''):
    return f'architecture://{quote(project.as_posix(), safe="/:")}' + ('?' + query if query else '')


def test_alias_inherits_the_operation_and_owns_bound_call_declaration():
    assert ArchitectureAdapter.__bases__ == (OverviewAdapter,)
    assert ArchitectureAdapter.__dict__['BOUND_QUERY_CALL'] is True
    for name in ('__init__', 'get_structure', 'result_type_for', 'execution_facts',
                 'answer_requirement_error', 'validate_request'):
        assert name not in ArchitectureAdapter.__dict__
    assert issubclass(ArchitectureRenderer, OverviewRenderer)


@pytest.mark.parametrize('transport', ['cli', 'uri'])
@pytest.mark.parametrize('top', [0, 2, 5])
def test_canonical_map_and_one_central_retirement_note(project, transport, top):
    argv = ['architecture', str(project), '--top', str(top)] if transport == 'cli' else [uri(project, f'top={top}')]
    response = run(*argv, '--format', 'json')
    assert response.returncode == 0, response.stderr
    result = json.loads(response.stdout)
    assert result['type'] == 'overview' and result['map_status'] == 'complete'
    assert result['map']['components']['total'] == 7
    assert result['map']['components']['returned'] == top
    notes = [w for w in result['meta']['warnings'] if w.get('code') == 'retired_spelling']
    assert len(notes) == 1
    assert notes[0]['field'] == ('subcommand:architecture' if transport == 'cli' else 'scheme:architecture')
    assert notes[0]['stage'] == 'note'
    assert 'overview' in notes[0]['replacement']
    assert 'facts' not in result and 'risks' not in result


def test_api_typed_precedence_none_reset_and_expansion(project):
    assert api.query(uri(project, 'top=0'), top=2)['map']['components']['returned'] == 2
    assert api.query(uri(project, 'top=0'), top=None)['map']['components']['returned'] == 5
    assert api.query(uri(project, 'no_imports=true'), no_imports=False)['map_status'] == 'complete'
    scope_only = api.query(uri(project), no_imports=True)
    assert scope_only['map_status'] == 'not_requested' and scope_only['map'] is None
    assert api.query(uri(project, 'all=true'), all=False)['map']['components']['returned'] == 5
    assert api.query(uri(project), all=True)['map']['components']['returned'] == 7
    assert api.query(uri(project, 'against=HEAD'), against=None)['type'] == 'overview'


@pytest.mark.parametrize('kwargs', [{'top': True}, {'no_imports': 'maybe'}, {'top': -1}])
def test_invalid_typed_controls_reject(project, kwargs):
    with pytest.raises(ValueError):
        api.query(uri(project), **kwargs)


def test_schema_spells_alias_but_describes_canonical_outputs():
    schema = ArchitectureAdapter.get_schema()
    assert schema['adapter'] == 'architecture'
    assert {row['type'] for row in schema['output_types']} == {'overview', 'overview_diff'}
    assert schema['query_params'] == OverviewAdapter.get_schema()['query_params']
    assert all(example['uri'].startswith('architecture://') for example in schema['example_queries'])
    help_data = ArchitectureAdapter.get_help()
    assert help_data['name'] == 'architecture'
    assert all(example['uri'].startswith('architecture://') for example in help_data['examples'])


def test_renderer_uses_canonical_map_and_artifact(project):
    artifact = project / 'answer.json'
    response = run('architecture', str(project), '--output', f'json={artifact}')
    assert response.returncode == 0, response.stderr
    assert 'Overview:' in response.stdout and 'Code scope' in response.stdout
    assert 'Architecture Brief' not in response.stdout
    assert json.loads(artifact.read_text(encoding='utf-8'))['type'] == 'overview'


def test_final_map_proof_and_fields_retain_failure(project, monkeypatch):
    def corrupt(result, args):
        result = deepcopy(result)
        result['map'].pop('rules')
        return result
    monkeypatch.setattr(ArchitectureAdapter, 'post_process', staticmethod(corrupt))
    response = run('architecture', str(project), '--format', 'json', '--fields', 'scope')
    assert response.returncode == 3
    result = json.loads(response.stdout)
    assert result['type'] == 'overview'
    assert result['scope']['total_code_files'] == 7
    assert any(error['code'] == 'invalid_adapter_answer' for error in result['meta']['errors'])


@pytest.fixture
def repository(project):
    pygit2 = pytest.importorskip('pygit2')
    repo = pygit2.init_repository(str(project))
    repo.index.add_all()
    repo.index.write()
    signature = pygit2.Signature('fixture', 'fixture@example.invalid')
    repo.create_commit('HEAD', signature, signature, 'base', repo.index.write_tree(), [])
    return project


@pytest.mark.parametrize('transport', ['cli', 'uri', 'api'])
def test_comparison_retains_canonical_identity_and_snapshot_proof(repository, transport):
    if transport == 'api':
        result = api.query(uri(repository), against='HEAD')
    else:
        argv = ['architecture', str(repository), '--against', 'HEAD'] if transport == 'cli' else [uri(repository, 'against=HEAD')]
        response = run(*argv, '--format', 'json')
        assert response.returncode == 0, response.stderr
        result = json.loads(response.stdout)
    assert result['type'] == 'overview_diff'
    assert result['analysis']['basis'] == 'identical_tree'
    assert result['analysis']['complete'] is True and result['analysis']['snapshots'] == {}
    assert ArchitectureAdapter.execution_facts(result) == OverviewAdapter.execution_facts(result)


def test_final_comparison_proof_cannot_be_removed(repository, monkeypatch):
    def corrupt(result, args):
        result = deepcopy(result)
        result['analysis'].pop('basis')
        return result
    monkeypatch.setattr(ArchitectureAdapter, 'post_process', staticmethod(corrupt))
    response = run('architecture', str(repository), '--against', 'HEAD', '--format', 'json', '--fields', 'deltas')
    assert response.returncode == 3
    result = json.loads(response.stdout)
    assert result['type'] == 'overview_diff'
    assert any(error['code'] == 'invalid_adapter_answer' for error in result['meta']['errors'])
