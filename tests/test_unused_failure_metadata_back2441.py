"""Unused names are file-local; whole-graph uncertainty survives as metadata (BACK-2441)."""
import json

import pytest

from conftest import _run_reveal_direct as run

pytestmark = pytest.mark.component


@pytest.fixture
def project(tmp_path):
    (tmp_path / '.git').mkdir()
    app = tmp_path / 'app'
    app.mkdir()
    (app / 'a.py').write_text('import outside\nimport os\n', encoding='utf-8')
    (tmp_path / 'outside.py').write_text('import app.a\n', encoding='utf-8')
    return app


def query(path, mode='unused', *flags):
    return run(f'imports://{path}?{mode}', '--format', 'json', *flags)


def break_outside(app):
    (app.parent / 'outside.py').write_text('x = (\n', encoding='utf-8')


def test_lost_outside_cycle_is_unknown_without_changing_any_unused_row(project):
    healthy = query(project)
    before = json.loads(healthy.stdout)
    assert healthy.returncode == 0 and before['metadata']['has_cycles'] is True
    break_outside(project)
    damaged = query(project)
    after = json.loads(damaged.stdout)
    assert damaged.returncode == 0
    assert after['unused'] == before['unused']
    assert sorted(row['unused_names'] for row in after['unused']) == [['os'], ['outside']]
    metadata = after['metadata']
    assert metadata['has_cycles'] is None
    assert metadata['files_failed_count'] == metadata['files_lost_count'] == 0
    assert metadata['files_failed'] == metadata['files_lost'] == []
    assert metadata['files_failed_outside_target_count'] == 1
    assert metadata['scanned_files'] == metadata['total_files'] == 1
    assert metadata['total_imports'] == 2
    assert any(d['parse']['status'] == 'partial' for d in metadata['extraction_diagnostics'].values())


def test_observed_cycle_survives_unrelated_outside_loss(project):
    (project.parent / 'broken.py').write_text('x = (\n', encoding='utf-8')
    response = query(project)
    body = json.loads(response.stdout)
    assert response.returncode == 0
    assert body['metadata']['has_cycles'] is True
    assert body['metadata']['files_failed_outside_target_count'] == 1
    assert body['count'] == 2


@pytest.mark.parametrize('flags', [(), ('--fields', 'unused'), ('--fields', 'metadata'),
                                   ('--head', '1'), ('--max-items', '1')])
@pytest.mark.parametrize('location,expected', [('outside', 0), ('inside', 3), ('root', 3)])
def test_output_projections_preserve_target_completeness(project, flags, location, expected):
    break_outside(project)
    target = project
    if location == 'inside':
        (project / 'broken.py').write_text('x = (\n', encoding='utf-8')
    elif location == 'root':
        target = project.parent
    response = query(target, 'unused', *flags)
    body = json.loads(response.stdout)
    assert response.returncode == expected
    assert body['type'] == 'unused_imports'
    if 'metadata' in body:
        assert body['metadata']['has_cycles'] is None
        assert body['metadata']['files_failed_count'] == (0 if location == 'outside' else 1)
    if 'unused' in body:
        assert body['unused']
        assert all(row['unused_names'] in (['os'], ['outside']) for row in body['unused'])


@pytest.mark.parametrize('policy,expected', [('none', 0), ('findings', 1)])
def test_outside_loss_does_not_override_target_findings_policy(project, policy, expected):
    break_outside(project)
    response = query(project, 'unused', '--fail-on', policy)
    assert response.returncode == expected
    assert json.loads(response.stdout)['count'] == 2


@pytest.mark.parametrize('mode', ['circular', 'importers', 'rank=fan-in'])
def test_whole_graph_consumers_still_require_outside_files(project, mode):
    break_outside(project)
    response = query(project, mode)
    assert response.returncode == 3
    assert json.loads(response.stdout)['metadata']['files_failed_count'] == 1


def test_scan_cap_is_not_mistaken_for_outside_only_failure(project):
    response = query(project, 'unused&max_files=1')
    assert response.returncode == 3
    assert json.loads(response.stdout)['metadata']['scan_budget']['capped']


@pytest.mark.parametrize('format', ['text', 'json'])
def test_requested_json_output_keeps_scope_and_write_failure_policy(project, tmp_path, format):
    break_outside(project)
    artifact = tmp_path / 'answer.json'
    uri = f'imports://{project}?unused'
    response = run(uri, '--format', format, '--output', f'json={artifact}')
    body = json.loads(artifact.read_text(encoding='utf-8'))
    assert response.returncode == 0
    assert body['metadata']['has_cycles'] is None
    assert body['metadata']['files_failed_outside_target_count'] == 1
    if format == 'json':
        assert body == json.loads(response.stdout)
    else:
        assert '1 file(s) outside this path' in response.stdout
    failed = run(uri, '--format', format, '--output', f'json={tmp_path}')
    assert failed.returncode == 3
    assert failed.stderr.count('Requested JSON artifact failed') == 1
    if format == 'json':
        result = json.loads(failed.stdout)
        assert result['unused'] == body['unused']
        assert result['meta']['output_errors'][0]['code'] == 'artifact_write_failed'
    else:
        assert 'Unused Imports: 2' in failed.stdout


def test_scan_wide_unchecked_language_census_remains_disclosed(project):
    (project.parent / 'Outside.java').write_text('import java.util.List;\nclass Outside {}\n', encoding='utf-8')
    break_outside(project)
    response = query(project)
    body = json.loads(response.stdout)
    assert response.returncode == 0
    assert body['metadata']['unused_not_checked_extensions'] == {'.java': 1}
    assert body['metadata']['scanned_files'] == 1
    assert body['count'] == 2


def test_zero_unused_text_does_not_claim_clean_for_in_target_parse_loss(project):
    (project / 'a.py').write_text('print("ok")\n', encoding='utf-8')
    (project / 'broken.py').write_text('x = (\n', encoding='utf-8')
    response = run(f'imports://{project}?unused')
    assert response.returncode == 3
    assert 'No unused imports observed' in response.stdout
    assert 'analysis is incomplete' in response.stdout
    assert '✅ No unused imports found' not in response.stdout
    assert 'could not be fully analyzed' in response.stdout


def test_zero_unused_text_discloses_outside_loss_without_marking_target_incomplete(project):
    (project / 'a.py').write_text('print("ok")\n', encoding='utf-8')
    break_outside(project)
    response = run(f'imports://{project}?unused')
    assert response.returncode == 0
    assert 'No unused imports found' in response.stdout
    assert '1 file(s) outside this path could not be fully analyzed' in response.stdout


@pytest.mark.parametrize('inside', [False, True])
def test_worker_loss_is_scoped_without_disappearing_from_diagnostics(project, monkeypatch, inside):
    from concurrent.futures.process import BrokenProcessPool
    from reveal.analyzers.imports import extraction

    (project.parent / 'outside.py').write_text('VALUE = 1\n', encoding='utf-8')
    target = project / 'lost.py' if inside else project.parent / 'outside.py'
    target.write_text('import sys\n', encoding='utf-8')
    original = extraction.extract_files

    def lose_one(candidates, structure_reader, inputs=None):
        for row in original(candidates, structure_reader, inputs):
            if row[0] == target:
                loss = extraction.lost_extraction(BrokenProcessPool('controlled worker loss'))
                row = (row[0], None, None, None, loss, None, None)
            yield row

    monkeypatch.setattr(extraction, 'extract_files', lose_one)
    response = query(project)
    body = json.loads(response.stdout)
    assert response.returncode == (3 if inside else 0)
    metadata = body['metadata']
    assert metadata['files_lost_count'] == metadata['files_failed_count'] == int(inside)
    assert metadata['files_failed_outside_target_count'] == int(not inside)
    assert metadata['has_cycles'] is None
    assert any('controlled worker loss' in d['parse']['reason']
               for d in metadata['extraction_diagnostics'].values())


@pytest.mark.parametrize('inside', [False, True])
def test_api_and_cli_use_the_same_unprojected_completeness_facts(project, inside):
    from reveal import api
    from reveal.adapters.imports import ImportsAdapter
    from reveal.utils.results import AnalysisCompleteness

    break_outside(project)
    if inside:
        (project / 'broken.py').write_text('x = (\n', encoding='utf-8')
    body = api.query(f'imports://{project}?unused')
    facts = ImportsAdapter.execution_facts(body)
    assert facts.completeness is (AnalysisCompleteness.INCOMPLETE if inside else AnalysisCompleteness.COMPLETE)
    assert facts.findings
    response = query(project)
    cli = json.loads(response.stdout)
    assert cli['metadata'] == body['metadata']
    assert cli['unused'] == body['unused']


def test_outside_directory_discovery_loss_is_still_required(project, monkeypatch):
    from test_imports_discovery_loss_back2014 import deny_child, discovery_warning

    hidden = project.parent / 'hidden'
    hidden.mkdir()
    (hidden / 'other.py').write_text('import os\n', encoding='utf-8')
    deny_child(monkeypatch, hidden)
    response = query(project, 'unused', '--fields', 'unused')
    assert response.returncode == 3
    warning = discovery_warning(json.loads(response.stdout))
    assert warning['count'] == 1
    assert 'PermissionError' in warning['message']
