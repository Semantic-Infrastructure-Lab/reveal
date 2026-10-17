"""Hotspots binding keeps required child proof and pre-cap serious findings."""
import copy
import json
import sys
from pathlib import Path
from urllib.parse import quote

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.hotspots import HotspotsAdapter
from reveal.adapters.ast import AstAdapter
from reveal.adapters.stats import StatsAdapter


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path/'proj'
    root.mkdir()
    body = 'def critical(x):\n' + ''.join(f'    if x == {i}: x += 1\n' for i in range(22)) + '    return x\n'
    (root/'a.py').write_text(body, encoding='utf-8')
    return root


def argv(transport, query='', cli=()):
    return ['hotspots', 'proj', *cli] if transport == 'cli' else ['hotspots://proj'+query]


def equal_answers(left, right):
    left, right = copy.deepcopy(left), copy.deepcopy(right)
    if 'execution' in left:
        assert left['execution']['command'].startswith('reveal hotspots ')
        assert right['execution']['command'].startswith('reveal hotspots://')
        del left['execution']['command'], right['execution']['command']
    assert left == right


@pytest.mark.parametrize('cli,query', [([], ''), (['--top', '0'], '?top=0'),
    (['--top', '3.0'], '?top=3.0'), (['--top', '1e2'], '?top=1e2'),
    (['--min-complexity', '-1.0'], '?min_complexity=-1.0'),
    (['--functions-only'], '?functions_only=true'), (['--files-only'], '?files_only=true'),
    (['--functions-only', '--files-only'], '?functions_only=true&files_only=true')])
@pytest.mark.parametrize('provenance', [False, True])
def test_exact_json_parity(project, cli, query, provenance):
    flags = ['--provenance'] if provenance else []
    left = run('hotspots', 'proj', *cli, '--format', 'json', *flags)
    right = run('hotspots://proj'+query, '--format', 'json', *flags)
    assert left.returncode == right.returncode == 0, (left.stderr, right.stderr)
    if provenance:
        assert json.loads(left.stdout)['execution']['command'] == ' '.join(['reveal', 'hotspots', 'proj', *cli, '--format', 'json', *flags])
        assert json.loads(right.stdout)['execution']['command'] == ' '.join(['reveal', 'hotspots://proj'+query, '--format', 'json', *flags])
    equal_answers(json.loads(left.stdout), json.loads(right.stdout))


@pytest.mark.parametrize('transport', ['cli', 'uri'])
@pytest.mark.parametrize('format', ['text', 'json'])
@pytest.mark.parametrize('policy,expected', [(None, 0), ('none', 0), ('findings', 1)])
def test_pre_cap_findings_policy(project, transport, format, policy, expected):
    flags = ['--fail-on', policy] if policy else []
    result = run(*argv(transport, '?top=1', ['--top', '1']), '--format', format, *flags)
    assert result.returncode == expected, result.stderr
    if format == 'json':
        assert json.loads(result.stdout)['summary']['has_findings'] is True


@pytest.mark.parametrize('transport', ['cli', 'uri'])
@pytest.mark.parametrize('flags,query', [([], ''), (['--functions-only'], '?functions_only=true'),
    (['--files-only'], '?files_only=true'), (['--files-only', '--functions-only'], '?files_only=true&functions_only=true')])
def test_required_stats_failures_in_all_modes(project, monkeypatch, transport, flags, query):
    original = StatsAdapter.get_structure
    def answer(self, **kwargs):
        result = original(self, **kwargs)
        result.setdefault('meta', {})['warnings'] = [{'type': 'check_rules_failed', 'message': 'required checks unavailable'}]
        return result
    monkeypatch.setattr(StatsAdapter, 'get_structure', answer)
    result = run(*argv(transport, query, flags), '--format', 'json', '--fail-on', 'none')
    assert result.returncode == 3, result.stderr
    assert json.loads(result.stdout)['type'] == 'hotspots_scan'


@pytest.mark.parametrize('child,kind', [('stats', 'empty'), ('stats', 'summary'), ('stats', 'files'),
    ('stats', 'hotspots'), ('stats', 'boolean_score'), ('stats', 'nan_score'),
    ('ast', 'empty'), ('ast', 'results'), ('ast', 'count'), ('ast', 'boolean_count'),
    ('ast', 'boolean_complexity'), ('ast', 'nan_complexity'), ('ast', 'displayed')])
def test_required_child_shape_before_projection(project, monkeypatch, child, kind):
    cls = StatsAdapter if child == 'stats' else AstAdapter
    original = cls.get_structure
    def answer(self, **kwargs):
        result = copy.deepcopy(original(self, **kwargs))
        if kind == 'empty':
            return {}
        if kind == 'summary':
            result['summary']['total_files'] = True
        elif kind in ('files', 'hotspots', 'results'):
            result.pop(kind)
        elif kind in ('boolean_score', 'nan_score'):
            result['files'][0]['quality']['score'] = True if kind == 'boolean_score' else float('nan')
        elif kind == 'count':
            result.pop('total_files')
        elif kind == 'boolean_count':
            result['total_results'] = True
        elif kind in ('boolean_complexity', 'nan_complexity'):
            result['results'][0]['complexity'] = True if kind == 'boolean_complexity' else float('nan')
        elif kind == 'displayed':
            result['displayed_results'] += 1
        return result
    monkeypatch.setattr(cls, 'get_structure', answer)
    result = run('hotspots://proj', '--format', 'json', '--fail-on', 'none')
    assert result.returncode == 3, result.stderr
    data = json.loads(result.stdout)
    assert data['type'] == 'hotspots_scan'
    assert any(e.get('code') == 'E_COMPOSE' for e in data['meta']['errors'])


@pytest.mark.parametrize('transport', ['cli', 'uri'])
@pytest.mark.parametrize('phase', ['analysis', 'postprocess'])
@pytest.mark.parametrize('kind', ['files', 'functions', 'summary', 'findings'])
def test_required_outer_proof(project, monkeypatch, transport, phase, kind):
    def corrupt(result):
        result = copy.deepcopy(result)
        if kind in ('files', 'functions'):
            result.pop('file_hotspots' if kind == 'files' else 'function_hotspots')
        elif kind == 'summary':
            result['summary'].pop('total_files')
        else:
            result['summary']['has_findings'] = 'false'
        return result
    original = HotspotsAdapter.get_structure
    if phase == 'analysis':
        monkeypatch.setattr(HotspotsAdapter, 'get_structure', lambda self, **kwargs: corrupt(original(self, **kwargs)))
    else:
        monkeypatch.setattr(HotspotsAdapter, 'post_process', lambda self, result, args: corrupt(result))
    result = run(*argv(transport), '--format', 'json')
    assert result.returncode == 3, result.stderr
    data = json.loads(result.stdout)
    assert data['error'] and data['type'] == 'hotspots_scan'


@pytest.mark.parametrize('transport', ['cli', 'uri'])
@pytest.mark.parametrize('policy,expected', [('none', 0), ('findings', 1)])
def test_findings_survive_fields_and_item_budget(project, transport, policy, expected):
    result = run(*argv(transport), '--format', 'json', '--fields', 'path', '--max-items', '0', '--fail-on', policy)
    assert result.returncode == expected, result.stderr
    assert 'summary' not in json.loads(result.stdout)


@pytest.mark.parametrize('query,cli', [('top=-1', ['--top', '-1']), ('top=1.5', ['--top', '1.5']),
    ('top', None), ('min_complexity=1.5', ['--min-complexity', '1.5']),
    ('min_complexity', None), ('functions_only=bad', None), ('files_only=bad', None)])
def test_invalid_parameters_canonical_usage(project, query, cli):
    requests = [['hotspots://proj?'+query]]
    if cli is not None:
        requests.append(['hotspots', 'proj', *cli])
    for request in requests:
        result = run(*request, '--format', 'json')
        assert result.returncode == 2, result.stderr
        assert json.loads(result.stdout)['type'] == 'hotspots_scan'


@pytest.mark.parametrize('name', ['space ,&=+é', 'literal%26', pytest.param('question?mark',
    marks=pytest.mark.skipif(sys.platform == 'win32', reason='Windows filenames cannot contain ?'))])
def test_original_resource_identity(project, name):
    root = project.parent/name
    root.mkdir()
    (root/'a.py').write_text('x = 1\n', encoding='utf-8')
    left = run('hotspots', name, '--format', 'json')
    right = run('hotspots://'+quote(name, safe=''), '--format', 'json')
    assert left.returncode == right.returncode == 0
    equal_answers(json.loads(left.stdout), json.loads(right.stdout))


def test_verbose_lifts_caps_but_all_preserves_explicit_top(project):
    for i in range(12):
        (project/f'f{i}.py').write_text((project/'a.py').read_text(encoding='utf-8'), encoding='utf-8')
    left = run('hotspots', 'proj', '--top', '1', '--verbose', '--format', 'json')
    right = run('hotspots://proj?top=1', '--verbose', '--format', 'json')
    assert left.returncode == right.returncode == 0
    a, b = json.loads(left.stdout), json.loads(right.stdout)
    equal_answers(a, b)
    assert len(a['file_hotspots']) == len(a['function_hotspots']) == 13
    capped = run('hotspots://proj?top=1', '--all', '--format', 'json')
    assert len(json.loads(capped.stdout)['function_hotspots']) == 1
    assert run('hotspots', 'proj', '--all').returncode == 2


@pytest.mark.parametrize('transport', ['cli', 'uri'])
def test_partial_precedes_findings_and_projection(project, transport):
    (project/'broken.py').write_text('def broken(\n', encoding='utf-8')
    result = run(*argv(transport), '--format', 'json', '--fields', 'path', '--fail-on', 'findings')
    assert result.returncode == 3, result.stderr


@pytest.mark.parametrize('transport', ['cli', 'uri'])
def test_artifact_failure_keeps_primary_json(project, monkeypatch, transport):
    def fail(*args, **kwargs):
        raise OSError('requested artifact unavailable')
    monkeypatch.setattr('reveal.utils.json_utils.write_also_json', fail)
    result = run(*argv(transport), '--format', 'json', '--also-json', 'missing/result.json')
    assert result.returncode == 3, result.stderr
    answer = json.loads(result.stdout)
    assert answer['type'] == 'hotspots_scan' and answer['summary']['has_findings']
    assert answer['meta']['output_errors']


@pytest.mark.parametrize('transport', ['cli', 'uri'])
def test_human_artifact_and_primary_json_noop(project, transport):
    target = project.parent/f'{transport}.json'
    result = run(*argv(transport), '--also-json', str(target))
    assert result.returncode == 0, result.stderr
    assert json.loads(target.read_text(encoding='utf-8'))['summary']['has_findings']
    target.unlink()
    result = run(*argv(transport), '--format', 'json', '--also-json', str(target))
    assert result.returncode == 0 and not target.exists()


def test_optional_warnings_and_complete_zero_do_not_fail(project, monkeypatch):
    (project/'a.py').write_text('x = 1\n', encoding='utf-8')
    original = HotspotsAdapter.get_structure
    def answer(self, **kwargs):
        result = original(self, **kwargs)
        result['meta'] = {'warnings': [{'type': 'churn_unavailable', 'message': 'optional'},
            {'type': 'test_convention_unknown', 'message': 'optional'}, {'type': 'custom', 'message': 'unknown'}], 'confidence': 0.0}
        return result
    monkeypatch.setattr(HotspotsAdapter, 'get_structure', answer)
    result = run('hotspots://proj', '--format', 'json', '--fail-on', 'findings')
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('partial,artifact,policy,expected', [(False, False, 'none', 0),
    (False, False, 'findings', 1), (True, False, 'none', 3), (False, True, 'none', 3)])
def test_real_closed_pipe(project, partial, artifact, policy, expected):
    import os
    import subprocess
    if partial:
        (project/'broken.py').write_text('def broken(\n', encoding='utf-8')
    request = [sys.executable, '-m', 'reveal', 'hotspots', 'proj', '--fail-on', policy]
    if artifact:
        request.extend(['--also-json', str(project)])
    with subprocess.Popen(request, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=os.environ.copy()) as process:
        process.stdout.close()
        code = process.wait(timeout=30)
        errors = process.stderr.read().decode('utf-8', errors='replace')
    assert code == expected, errors
    assert 'Traceback' not in errors


def test_legacy_batch_gate_boundary(project):
    result = run('hotspots://proj', '--batch', '--fail-on', 'findings')
    assert result.returncode == 2 and not result.stdout


@pytest.mark.parametrize('policy,expected', [('none', 0), ('findings', 1)])
def test_uri_head_retains_preprojection_findings(project, policy, expected):
    (project/'b.py').write_text((project/'a.py').read_text(encoding='utf-8'), encoding='utf-8')
    result = run('hotspots://proj', '--format', 'json', '--head', '1', '--fail-on', policy)
    assert result.returncode == expected, result.stderr
    assert len(json.loads(result.stdout)['function_hotspots']) == 1


@pytest.mark.parametrize('transport', ['cli', 'uri'])
@pytest.mark.parametrize('kind', ['returned', 'raised', 'postraised', 'postNone', 'meta_error'])
def test_required_returned_and_raised_failures(project, monkeypatch, transport, kind):
    original = HotspotsAdapter.get_structure
    if kind.startswith('post'):
        def process(self, result, args):
            if kind == 'postNone':
                return None
            raise OSError('postprocess inaccessible')
        monkeypatch.setattr(HotspotsAdapter, 'post_process', process)
    else:
        def answer(self, **kwargs):
            if kind == 'raised':
                raise OSError('required analysis inaccessible')
            result = original(self, **kwargs)
            if kind == 'returned':
                result['error'] = 'returned required failure'
            else:
                result.setdefault('meta', {})['errors'] = [{'code': 'invalid_request', 'message': 'producer failed'}]
            return result
        monkeypatch.setattr(HotspotsAdapter, 'get_structure', answer)
    result = run(*argv(transport), '--format', 'json', '--fail-on', 'none')
    assert result.returncode == 3, result.stderr
    assert json.loads(result.stdout)['type'] == 'hotspots_scan'


@pytest.mark.parametrize('warning', ['parse_degraded', 'analysis_failed', 'parse_recovered'])
def test_required_ast_diagnostics_and_files_only_skip(project, monkeypatch, warning):
    original = AstAdapter.get_structure
    calls = []
    def answer(self, **kwargs):
        calls.append(True)
        result = original(self, **kwargs)
        result.setdefault('meta', {})['warnings'] = [{'type': warning, 'message': 'required parse did not complete'}]
        return result
    monkeypatch.setattr(AstAdapter, 'get_structure', answer)
    assert run('hotspots://proj', '--format', 'json').returncode == 3
    calls.clear()
    result = run('hotspots://proj?files_only=true', '--format', 'json')
    assert result.returncode == 0 and calls == []


def test_composed_exception_once_and_instance_reuse(project, monkeypatch):
    adapter = HotspotsAdapter('proj', 'functions_only=true')
    original = AstAdapter.get_structure
    def fail(self, **kwargs):
        raise OSError('AST inaccessible')
    monkeypatch.setattr(AstAdapter, 'get_structure', fail)
    failed = adapter.get_structure()
    errors = failed['meta']['errors']
    assert len(errors) == 1 and errors[0]['code'] == 'E_COMPOSE'
    assert 'AST inaccessible' in errors[0]['message']
    monkeypatch.setattr(AstAdapter, 'get_structure', original)
    complete = adapter.get_structure()
    assert not complete.get('meta', {}).get('errors')
    assert complete['summary']['has_findings'] is True


@pytest.mark.parametrize('transport', ['cli', 'uri'])
def test_missing_and_inaccessible_resources(project, monkeypatch, transport):
    missing = ['hotspots', 'missing'] if transport == 'cli' else ['hotspots://missing']
    result = run(*missing, '--format', 'json')
    assert result.returncode == 2
    assert json.loads(result.stdout)['type'] == 'hotspots_scan'
    stat = Path.stat
    def inaccessible(self, *args, **kwargs):
        if str(self) in ('proj', str(project)):
            raise PermissionError('required resource inaccessible')
        return stat(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', inaccessible)
    result = run(*argv(transport), '--format', 'json')
    assert result.returncode == 3
    assert json.loads(result.stdout)['type'] == 'hotspots_scan'


@pytest.mark.parametrize('flags', [['--exclude', 'a.py'], ['--no-gitignore'], ['--exclude', 'a.py', '--no-gitignore']])
def test_scope_and_no_gitignore_parity(project, flags):
    (project/'.gitignore').write_text('a.py\n', encoding='utf-8')
    left = run('hotspots', 'proj', *flags, '--format', 'json')
    right = run('hotspots://proj', *flags, '--format', 'json')
    assert left.returncode == right.returncode == 0
    equal_answers(json.loads(left.stdout), json.loads(right.stdout))


@pytest.mark.parametrize('parameter', ['top', 'min_complexity'])
@pytest.mark.parametrize('value', [True, False, 1.5, float('nan'), float('inf')])
def test_typed_numeric_evidence_rejects_booleans_and_fractions(parameter, value):
    with pytest.raises(ValueError):
        HotspotsAdapter('.', params={parameter: value})
