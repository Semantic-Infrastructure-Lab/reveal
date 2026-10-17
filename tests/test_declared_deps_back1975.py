"""Deps binding retains owner proof and findings before presentation."""
import copy
import json
import sys
from pathlib import Path
from urllib.parse import quote

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.deps import DepsAdapter


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path/'proj'
    root.mkdir()
    (root/'a.py').write_text('import os\n', encoding='utf-8')
    (root/'b.py').write_text('import sys\n', encoding='utf-8')
    return root


def argv(transport, query='', cli=()):
    return ['deps', 'proj', *cli] if transport == 'cli' else ['deps://proj'+query]


def equal_answers(left, right):
    left, right = copy.deepcopy(left), copy.deepcopy(right)
    if 'execution' in left:
        assert left['execution']['command'].startswith('reveal deps ')
        assert right['execution']['command'].startswith('reveal deps://')
        del left['execution']['command'], right['execution']['command']
    assert left == right


@pytest.mark.parametrize('cli,query', [
    ([], ''), (['--top', '0'], '?top=0'), (['--top', '3.0'], '?top=3.0'),
    (['--top', '1e2'], '?top=1e2'), (['--no-unused'], '?no_unused=true'),
    (['--no-circular'], '?no_circular=true'),
    (['--summary-only'], '?summary_only=true'),
])
@pytest.mark.parametrize('provenance', [False, True])
def test_exact_json_parity(project, cli, query, provenance):
    flags = ['--provenance'] if provenance else []
    left = run('deps', 'proj', *cli, '--format', 'json', *flags)
    right = run('deps://proj'+query, '--format', 'json', *flags)
    assert left.returncode == right.returncode == 0, (left.stderr, right.stderr)
    a, b = json.loads(left.stdout), json.loads(right.stdout)
    assert a['type'] == b['type'] == 'deps_scan'
    if provenance:
        assert a['execution']['command'] == ' '.join(['reveal', 'deps', 'proj', *cli, '--format', 'json', *flags])
        assert b['execution']['command'] == ' '.join(['reveal', 'deps://proj'+query, '--format', 'json', *flags])
    equal_answers(a, b)


@pytest.mark.parametrize('transport', ['cli', 'uri'])
@pytest.mark.parametrize('format', ['text', 'json'])
@pytest.mark.parametrize('policy,expected', [(None, 0), ('none', 0), ('findings', 1)])
def test_domain_findings_policy_ignores_text_cap(project, transport, format, policy, expected):
    flags = ['--fail-on', policy] if policy else []
    result = run(*argv(transport, '?top=0', ['--top', '0']), '--format', format, *flags)
    assert result.returncode == expected, result.stderr
    if format == 'json':
        assert json.loads(result.stdout)['analysis']['findings']['unused'] == 2


@pytest.mark.parametrize('transport', ['cli', 'uri'])
def test_policy_before_noun_or_uri_and_skip_controls(project, transport):
    request = argv(transport, '?no_unused=true&no_circular=true', ['--no-unused', '--no-circular'])
    result = run('--fail-on', 'findings', *request, '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['analysis']['findings'] == {}


@pytest.mark.parametrize('transport', ['cli', 'uri'])
@pytest.mark.parametrize('format', ['text', 'json'])
def test_summary_primary_json_only_and_artifacts(project, transport, format):
    target = project.parent/(transport+'-'+format+'.json')
    result = run(*argv(transport, '?summary_only=true', ['--summary-only']),
                 '--format', format, '--also-json', str(target))
    assert result.returncode == 0, result.stderr
    if format == 'json':
        answer = json.loads(result.stdout)
        assert 'files' not in answer['base']
        assert answer['base']['total_files'] == answer['base']['total_imports'] == 2
        assert not target.exists()  # The established primary-JSON mirror no-op.
    else:
        assert 'has no effect' in result.stderr
        answer = json.loads(target.read_text(encoding='utf-8'))
        assert len(answer['base']['files']) == 2
    assert answer['analysis']['findings']['unused'] == 2


def malformed(result, kind):
    result = copy.deepcopy(result)
    analysis = result['analysis']
    base = analysis['components']['base']
    if kind == 'missing':
        result.pop('analysis')
    elif kind == 'nonobject':
        result['analysis'] = []
    elif kind == 'complete_type':
        analysis['complete'] = 'true'
    elif kind == 'missing_component':
        analysis['components'].pop('base')
    elif kind == 'unknown_state':
        base['completeness'] = 'not_started'
    elif kind == 'missing_counts':
        base.pop('files_failed_count')
    elif kind == 'unknown_complete_count':
        base['files_failed_count'] = None
    elif kind == 'boolean_count':
        base['files_failed_count'] = True
    elif kind == 'negative_count':
        base['files_failed_count'] = -1
    elif kind == 'lost_exceeds':
        base['files_lost_count'] = 1
    elif kind == 'positive_complete_count':
        base['files_failed_count'] = 1
    elif kind == 'missing_findings':
        analysis.pop('findings')
    elif kind == 'unknown_complete_findings':
        analysis['findings']['unused'] = None
    elif kind == 'negative_findings':
        analysis['findings']['unused'] = -1
    elif kind == 'extra_findings':
        analysis['findings']['invented'] = 1
    elif kind == 'extra_component':
        analysis['components']['invented'] = copy.deepcopy(base)
    elif kind == 'aggregate_disagrees':
        analysis['complete'] = False
    elif kind == 'bad_skipped':
        result['skipped'] = ['base']
    return result


@pytest.mark.parametrize('transport', ['cli', 'uri'])
@pytest.mark.parametrize('phase', ['analysis', 'postprocess'])
@pytest.mark.parametrize('kind', ['missing', 'nonobject', 'complete_type', 'missing_component',
                                 'unknown_state', 'missing_counts', 'unknown_complete_count',
                                 'boolean_count', 'negative_count', 'lost_exceeds', 'positive_complete_count',
                                 'missing_findings', 'unknown_complete_findings', 'negative_findings',
                                 'extra_findings', 'extra_component', 'aggregate_disagrees', 'bad_skipped'])
def test_required_proof_cannot_be_missing_or_contradictory(project, monkeypatch, transport, phase, kind):
    original = DepsAdapter.get_structure
    if phase == 'analysis':
        def answer(self, **kwargs):
            return malformed(original(self, **kwargs), kind)
        monkeypatch.setattr(DepsAdapter, 'get_structure', answer)
    else:
        monkeypatch.setattr(DepsAdapter, 'post_process', lambda self, result, args: malformed(result, kind))
    result = run(*argv(transport), '--format', 'json', '--fail-on', 'none')
    assert result.returncode == 3, result.stderr
    data = json.loads(result.stdout)
    assert data['type'] == 'deps_scan' and data['error']
    assert any(e.get('code') == 'invalid_adapter_answer' for e in data['meta']['errors'])


@pytest.mark.parametrize('transport', ['cli', 'uri'])
@pytest.mark.parametrize('kind', ['returned', 'raised', 'postraised', 'postNone', 'meta_error'])
def test_returned_and_raised_required_failures(project, monkeypatch, transport, kind):
    original = DepsAdapter.get_structure
    if kind.startswith('post'):
        def process(self, result, args):
            if kind == 'postNone':
                return None
            raise OSError('postprocess inaccessible')
        monkeypatch.setattr(DepsAdapter, 'post_process', process)
    else:
        def answer(self, **kwargs):
            if kind == 'raised':
                raise OSError('required graph inaccessible')
            result = original(self, **kwargs)
            if kind == 'returned':
                result['error'] = 'returned graph failure'
            else:
                result.setdefault('meta', {})['errors'] = [{'code': 'invalid_request', 'message': 'producer error after analysis'}]
            return result
        monkeypatch.setattr(DepsAdapter, 'get_structure', answer)
    result = run(*argv(transport), '--format', 'json', '--fail-on', 'none')
    assert result.returncode == 3, result.stderr
    assert json.loads(result.stdout)['type'] == 'deps_scan'


@pytest.mark.parametrize('transport', ['cli', 'uri'])
@pytest.mark.parametrize('policy', ['none', 'findings'])
def test_partial_real_analysis_wins_over_findings_and_projection(project, transport, policy):
    (project/'broken.py').write_text('import pathlib\ndef broken(\n', encoding='utf-8')
    result = run(*argv(transport, '?summary_only=true', ['--summary-only']), '--format', 'json',
                 '--fields', 'base', '--fail-on', policy)
    assert result.returncode == 3, result.stderr
    assert 'base' in json.loads(result.stdout)


@pytest.mark.parametrize('transport', ['cli', 'uri'])
def test_complete_findings_gate_survives_summary_and_field_projection(project, transport):
    result = run(*argv(transport, '?summary_only=true', ['--summary-only']), '--format', 'json',
                 '--fields', 'base', '--fail-on', 'findings')
    assert result.returncode == 1, result.stderr
    answer = json.loads(result.stdout)
    assert set(answer) == {'base'}
    assert answer['base']['total_files'] == 2 and 'files' not in answer['base']


@pytest.mark.parametrize('query,cli', [('top=-1', ['--top', '-1']), ('top=1.5', ['--top', '1.5']),
                                    ('top=bad', ['--top', 'bad']), ('top', None),
                                    ('no_unused=bad', None), ('no_circular=bad', None), ('summary_only=bad', None)])
def test_invalid_bound_parameters_are_canonical_usage(project, query, cli):
    cases = [['deps://proj?'+query]]
    if cli is not None:
        cases.append(['deps', 'proj', *cli])
    for request in cases:
        result = run(*request, '--format', 'json')
        assert result.returncode == 2, result.stderr
        assert json.loads(result.stdout)['type'] == 'deps_scan'


@pytest.mark.parametrize('transport', ['cli', 'uri'])
def test_missing_and_inaccessible_resources_keep_canonical_identity(project, monkeypatch, transport):
    missing = ['deps', 'missing'] if transport == 'cli' else ['deps://missing']
    result = run(*missing, '--format', 'json')
    assert result.returncode == 2
    assert json.loads(result.stdout)['type'] == 'deps_scan'
    stat = Path.stat
    def inaccessible(self, *args, **kwargs):
        if str(self) in ('proj', str(project)):
            raise PermissionError('required resource inaccessible')
        return stat(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', inaccessible)
    result = run(*argv(transport), '--format', 'json')
    assert result.returncode == 3
    assert json.loads(result.stdout)['type'] == 'deps_scan'


@pytest.mark.parametrize('name', ['space ,&=+é', 'literal%26',
                                 pytest.param('question?mark', marks=pytest.mark.skipif(
                                     sys.platform == 'win32', reason='Windows filenames cannot contain ?'))])
def test_original_typed_paths_and_encoded_uri_paths_match(project, name):
    root = project.parent/name
    root.mkdir()
    (root/'a.py').write_text('import os\n', encoding='utf-8')
    left = run('deps', name, '--format', 'json')
    right = run('deps://'+quote(name, safe=''), '--format', 'json')
    assert left.returncode == right.returncode == 0
    equal_answers(json.loads(left.stdout), json.loads(right.stdout))


def test_scope_ignores_and_excludes_match(project):
    (project/'ignored.py').write_text('import pathlib\n', encoding='utf-8')
    (project/'.gitignore').write_text('ignored.py\n', encoding='utf-8')
    for flags in (['--exclude', 'b.py'], ['--no-gitignore'], ['--exclude', 'a.py', '--no-gitignore']):
        left = run('deps', 'proj', *flags, '--format', 'json')
        right = run('deps://proj', *flags, '--format', 'json')
        assert left.returncode == right.returncode == 0
        equal_answers(json.loads(left.stdout), json.loads(right.stdout))


def test_existing_presentation_boundaries_and_sibling_surface(project):
    assert run('deps', 'proj', '--all').returncode == 2
    full = run('deps://proj?top=0', '--all')
    verbose = run('deps', 'proj', '--top', '0', '--verbose')
    uri_verbose = run('deps://proj?top=0', '--verbose')
    assert full.returncode == verbose.returncode == uri_verbose.returncode == 0
    assert full.stdout == verbose.stdout == uri_verbose.stdout
    assert 'os' in full.stdout and 'sys' in full.stdout
    assert run('surface', 'proj', '--top', '0', '--format', 'json').returncode == 0


@pytest.mark.parametrize('transport', ['cli', 'uri'])
def test_artifact_failure_does_not_replace_primary_json(project, monkeypatch, transport):
    def fail(*args, **kwargs):
        raise OSError('injected requested artifact failure')
    monkeypatch.setattr('reveal.utils.json_utils.write_also_json', fail)
    result = run(*argv(transport), '--format', 'json', '--also-json', 'missing-parent/result.json')
    assert result.returncode == 3, result.stderr
    data = json.loads(result.stdout)
    assert data['type'] == 'deps_scan' and data['analysis']['findings']['unused'] == 2
    assert data['meta']['output_errors']


@pytest.mark.parametrize('transport', ['cli', 'uri'])
def test_human_requested_artifact_invalid_parent_fails(project, transport):
    result = run(*argv(transport), '--also-json', 'missing-parent/result.json')
    assert result.returncode == 3, result.stderr
    assert 'Requested JSON artifact failed' in result.stderr


def test_legacy_batch_rejects_explicit_gate(project):
    result = run('deps://proj', '--batch', '--fail-on', 'findings')
    assert result.returncode == 2 and not result.stdout


def test_valid_harmless_warning_and_complete_zero_are_not_incomplete(project, monkeypatch):
    for file in project.glob('*.py'):
        file.write_text('value = 1\n', encoding='utf-8')
    original = DepsAdapter.get_structure
    def answer(self, **kwargs):
        result = original(self, **kwargs)
        result['meta'] = {'warnings': [{'type': 'custom', 'message': 'harmless'}], 'confidence': 0.0}
        return result
    monkeypatch.setattr(DepsAdapter, 'get_structure', answer)
    result = run('deps://proj', '--format', 'json', '--fail-on', 'findings')
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('partial,artifact,policy,expected', [
    (False, False, 'none', 0), (False, False, 'findings', 1),
    (True, False, 'none', 3), (False, True, 'none', 3),
])
def test_closed_pipe_preserves_independent_facts(project, partial, artifact, policy, expected):
    import os
    import subprocess
    import sys
    if partial:
        (project/'broken.py').write_text('def broken(\n', encoding='utf-8')
    request = [sys.executable, '-m', 'reveal', 'deps', 'proj', '--fail-on', policy]
    if artifact:
        request.extend(['--also-json', str(project)])
    with subprocess.Popen(request, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env=os.environ.copy()) as process:
        process.stdout.close()
        code = process.wait(timeout=30)
        errors = process.stderr.read().decode('utf-8', errors='replace')
    assert code == expected, errors
    assert 'Traceback' not in errors
