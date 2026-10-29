"""Compact overview is the ordinary answer in every supported transport."""
from copy import deepcopy
from dataclasses import replace
import errno
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
from urllib.parse import quote

import pytest

from conftest import _run_reveal_direct as run
from reveal import api
from reveal.adapters.overview import OverviewAdapter
from reveal.analyzers.imports import service
from reveal.analyzers.imports.types import ImportExtraction
from reveal.analyzers.imports.views import ImportView
from reveal.utils.results import AnalysisCompleteness
from test_overview_map_facts_back2374 import LANGUAGES


def write(root, name, text):
    file = root / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text, encoding='utf-8')
    return file


@pytest.fixture
def project(tmp_path):
    for n in range(8):
        write(tmp_path, f'pkg{n}/a.py', 'from .b import value\n')
        write(tmp_path, f'pkg{n}/b.py', 'from .a import value\nvalue = 1\n')
        write(tmp_path, f'entry{n}.py', f'from pkg{n}.b import value\n')
    return tmp_path


def answer(root, *flags, query=''):
    result = (run('overview', root, '--format', 'json', *flags) if any(flag in flags for flag in ('--no-imports', '--top'))
              else run(f'overview://{root.as_posix()}' + ('?' + query if query else ''),
                       '--format', 'json', *flags))
    return result, json.loads(result.stdout)


@pytest.mark.parametrize('top', [0, 1, 5, 20])
def test_bounded_text_json_and_cli_uri_api(project, top):
    uri, result = answer(project, query=f'top={top}')
    command = run('overview', project, '--top', str(top), '--format', 'json')
    assert uri.returncode == command.returncode == 0, (uri.stderr, command.stderr)
    assert json.loads(command.stdout) == result
    assert api.query(f'overview://{project.as_posix()}', top=top) == result
    assert result['map_status'] == 'complete'
    assert not {'stats', 'architecture', 'git_log', 'complex_functions'} & result.keys()
    assert result['scope']['total_code_files'] == 24
    assert {name: result['map'][name]['total'] for name in ('fan_in', 'entrypoints', 'components', 'cycles')} == {
        'fan_in': 16, 'entrypoints': 8, 'components': 9, 'cycles': 8}
    assert not any(key.startswith('skipped_') for key in result['scope'])
    for section in ('fan_in', 'entrypoints', 'components', 'cycles'):
        page = result['map'][section]
        assert page['returned'] == min(top, page['total'])
        assert len(page['rows']) == page['returned']
        assert page['total'] == page['returned'] + page['omitted']
    text = run('overview', project, '--top', str(top))
    assert text.returncode == 0, text.stderr
    assert f"showing {result['map']['components']['returned']} of 9 observed" in text.stdout
    assert 'Quality' not in text.stdout and 'Recent changes' not in text.stdout
    assert result['diagnostic_budget']['limit'] == min(max(top, 5), 50)
    if top >= 8:
        assert result['map']['fan_in']['rows'][0] == {'file': 'pkg0/b.py', 'fan_in': 2, 'fan_out': 1}
        assert result['map']['entrypoints']['rows'][0]['file'] == 'entry0.py'
        groups = {frozenset(cycle['members']['rows']) for cycle in result['map']['cycles']['rows']}
        assert groups == {frozenset((f'pkg{n}/a.py', f'pkg{n}/b.py')) for n in range(8)}
        assert all(cycle['path']['rows'][0] == cycle['path']['rows'][-1]
                   for cycle in result['map']['cycles']['rows'])


@pytest.mark.parametrize('flag', ['--all', '--verbose'])
def test_expansion_only_expands_map(project, flag):
    result, body = answer(project, flag, query='top=0')
    assert result.returncode == 0
    for section in ('fan_in', 'entrypoints', 'components', 'cycles'):
        assert body['map'][section]['omitted'] == 0
    assert body['diagnostic_budget']['limit'] == 50


def test_removed_owners_never_run(project, monkeypatch):
    from reveal.adapters.ast import AstAdapter
    from reveal.adapters.git import GitAdapter
    from reveal.adapters.stats import MetricsAdapter
    def forbidden(*args, **kwargs):
        raise AssertionError('overview invoked an assessment owner')
    monkeypatch.setattr(AstAdapter, 'get_structure', forbidden)
    monkeypatch.setattr(GitAdapter, 'get_metadata', forbidden)
    monkeypatch.setattr(GitAdapter, 'get_structure', forbidden)
    monkeypatch.setattr(MetricsAdapter, 'get_structure', forbidden)
    for flags in ((), ('--all',), ('--verbose',), ('--top', '0')):
        result, body = answer(project, *flags)
        assert result.returncode == 0 and body['map_status'] == 'complete'


@pytest.mark.parametrize('query,flags,owner', [
    ('no_git=true', ['--no-git'], 'git://'), ('no_git=false', None, 'git://'),
    ('tests=include', ['--tests', 'include'], 'metrics://'),
    ('tests=exclude', ['--tests', 'exclude'], 'metrics://'),
])
def test_obsolete_controls_correct_the_caller(project, query, flags, owner):
    result = run(f'overview://{project.as_posix()}?{query}', '--format', 'json')
    assert result.returncode == 2 and owner in result.stdout + result.stderr
    if flags:
        result = run('overview', project, *flags, '--format', 'json')
        assert result.returncode == 2 and owner in result.stdout + result.stderr


def test_scope_only_omits_graph_without_manufactured_zeros(project, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('scope-only overview built a graph')
    monkeypatch.setattr(service, 'analyze', forbidden)
    result, body = answer(project, '--no-imports')
    assert result.returncode == 0
    assert body['map'] is None and body['map_status'] == 'not_requested'
    assert 'not requested' in body['reading_note']
    assert body['scope']['total_code_files'] == 24


def test_direct_api_missing_resource_is_not_empty_success(tmp_path):
    with pytest.raises(FileNotFoundError):
        api.query(f'overview://{(tmp_path / "missing").as_posix()}')


def test_direct_api_malformed_required_owner_is_failed(project, monkeypatch):
    monkeypatch.setattr(ImportView, 'fan_in', lambda self: {})
    body = api.query(f'overview://{project.as_posix()}')
    assert body['map_status'] == 'failed'
    assert OverviewAdapter.execution_facts(body).completeness is AnalysisCompleteness.FAILED


@pytest.mark.parametrize('kind', ['empty', 'supported_zero', 'unsupported'])
def test_empty_supported_zero_and_unsupported_are_distinct(tmp_path, kind):
    if kind == 'supported_zero':
        write(tmp_path, 'zero.py', 'VALUE = 1\n')
    elif kind == 'unsupported':
        write(tmp_path, 'source.ex', 'defmodule Source do\nend\n')
    result, body = answer(tmp_path)
    assert result.returncode == 0
    assert body['scope']['total_code_files'] == (kind != 'empty')
    metadata = body['map']['metadata']
    assert metadata['scanned_files'] == (kind == 'supported_zero')
    assert metadata['unsupported_extensions'] == ({'.ex': 1} if kind == 'unsupported' else {})
    assert body['map']['fan_in']['total'] == 0


def test_exclusions_have_entry_units_and_reachable_deeper_queries(project):
    result, body = answer(project, '--exclude', 'pkg0/**')
    assert result.returncode == 0
    assert body['scope']['total_code_files'] == 22
    assert body['scope']['hidden']['unit'] == 'entries'
    assert body['scope']['hidden']['by_cause']['exclude'] > 0
    for step in body['next_steps'][:4]:
        tokens = shlex.split(step['command'])
        response = run(*tokens[1:], '--format', 'json')
        assert response.returncode == 0, (step, response.stderr)
        assert 'pkg0/a.py' not in response.stdout


@pytest.mark.skipif(shutil.which('git') is None, reason='git not installed')
def test_navigation_keeps_explicit_scope_without_repeating_config_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', os.devnull)
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True, capture_output=True, timeout=10)
    write(tmp_path, '.gitignore', 'ignored/\n')
    write(tmp_path, '.reveal.yaml', 'ignore:\n  - configured.py\n')
    write(tmp_path, 'configured.py', 'VALUE=1\n')
    write(tmp_path, 'explicit.py', 'VALUE=1\n')
    write(tmp_path, 'ignored/a.py', 'from .b import value\n')
    write(tmp_path, 'ignored/b.py', 'value=1\n')
    result, body = answer(tmp_path, '--exclude', 'explicit.py', '--no-gitignore')
    assert result.returncode == 0 and body['scope']['total_code_files'] == 2
    for step in body['next_steps'][:4]:
        assert 'configured.py' not in step['command']
        tokens = shlex.split(step['command'])
        assert '--no-gitignore' in tokens and 'explicit.py' in tokens
        deeper = run(*tokens[1:], '--format', 'json')
        assert deeper.returncode == 0, deeper.stderr
        assert 'configured.py' not in deeper.stdout and 'explicit.py' not in deeper.stdout
    fan_in = json.loads(run(*shlex.split(body['next_steps'][0]['command'])[1:], '--format', 'json').stdout)
    assert any(row['file'] == 'ignored/b.py' and row['fan_in'] == 1 for row in fan_in['entries'])


def test_shell_safe_relative_navigation_is_executable(tmp_path, monkeypatch):
    root = tmp_path / "space ' quote & percent%"
    write(root, 'a.py', 'from b import value\n')
    write(root, 'b.py', 'value=1\n')
    monkeypatch.chdir(tmp_path)
    response = run('overview://' + quote(root.name, safe='/.:'), '--format', 'json')
    assert response.returncode == 0, response.stderr
    body = json.loads(response.stdout)
    for step in body['next_steps']:
        tokens = shlex.split(step['command'])
        deeper = run(*tokens[1:], '--format', 'json')
        assert deeper.returncode in (0, 1), (step, deeper.stderr)
        json.loads(deeper.stdout)


def test_all_excluded_is_disclosed_scope_empty(project):
    result, body = answer(project, '--exclude', '*.py')
    assert result.returncode == 0
    assert body['scope']['total_code_files'] == 0
    assert body['scope']['hidden']['by_cause']['exclude'] > 0
    assert len([w for w in body['meta']['warnings'] if w['type'] == 'scope_hidden']) == 1


def denied_child(monkeypatch, child):
    original = os.scandir
    def denied(path):
        if Path(path).resolve() == child.resolve():
            raise PermissionError(errno.EACCES, 'controlled enumeration denial', str(child))
        return original(path)
    monkeypatch.setattr(os, 'scandir', denied)


@pytest.mark.parametrize('survivor', [False, True])
@pytest.mark.parametrize('scope_only', [False, True])
def test_traversal_keeps_observed_census_and_honest_outcome(tmp_path, monkeypatch, survivor, scope_only):
    write(tmp_path, 'hidden/missing.py', 'VALUE=1\n')
    if survivor:
        write(tmp_path, 'seen.py', 'VALUE=1\n')
    denied_child(monkeypatch, tmp_path / 'hidden')
    result, body = answer(tmp_path, *(['--no-imports'] if scope_only else []))
    assert result.returncode == 3
    assert body['scope']['complete'] is False
    assert body['scope']['total_code_files'] == int(survivor)
    state = OverviewAdapter.execution_facts(body).completeness
    assert state is (AnalysisCompleteness.INCOMPLETE if survivor else AnalysisCompleteness.FAILED)
    projected = run('overview', tmp_path, '--format', 'json', '--fields', 'path',
                    *(['--no-imports'] if scope_only else []))
    assert projected.returncode == 3
    selected = json.loads(projected.stdout)
    if survivor or scope_only:
        assert 'map' not in selected
    assert any(w['type'] == 'analysis_incomplete' for w in selected['meta']['warnings'])


def test_capped_scan_remains_incomplete_at_top_zero_and_fields(project, monkeypatch):
    original = service.path_scope
    monkeypatch.setattr(service, 'path_scope', lambda root: original(root, cap=2))
    result, body = answer(project, query='top=0')
    assert result.returncode == 3
    budget = body['map']['metadata']['scan_budget']
    assert budget == {'scope': 'scan', 'limit': 2, 'total': 3, 'returned': 2, 'exact': False, 'capped': True}
    assert body['map_status'] == 'incomplete'
    assert all(body['map'][name]['rows'] == [] for name in ('fan_in', 'entrypoints', 'components', 'cycles'))
    projected = run('overview', project, '--format', 'json', '--fields', 'path')
    assert projected.returncode == 3
    selected = json.loads(projected.stdout)
    assert 'map' not in selected
    assert any(w['type'] == 'scan_capped' for w in selected['meta']['warnings'])


@pytest.mark.parametrize('lost', [False, True])
def test_loss_details_bounded_after_full_proof(project, monkeypatch, lost):
    original = service.analyze
    def loss(scope, **kwargs):
        built = original(scope, **kwargs)
        for n in range(53):
            file = scope.root / f'failed{n:02}.py'
            built.analysis.files_failed.append(file)
            if lost:
                built.analysis.files_lost.append(file)
            built.analysis.extractions[file] = ImportExtraction(parse_failed=True, worker_lost=lost,
                diagnostics={'parse': {'status': 'unavailable' if lost else 'partial',
                    'reason': f'exact cause {n}', 'spans': list(range(100))}})
        return built
    monkeypatch.setattr(service, 'analyze', loss)
    result, body = answer(project, query='top=0')
    assert result.returncode == 3 and body['map_status'] == 'incomplete'
    metadata = body['map']['metadata']
    assert metadata['files_failed_count'] == 53
    assert metadata['files_lost_count'] == (53 if lost else 0)
    assert len(metadata['files_failed']) == 5
    assert metadata['extraction_diagnostics_count'] == 53
    assert len(metadata['extraction_diagnostics']) == 5
    assert all(len(cause['parse']['spans']) == 5 for cause in metadata['extraction_diagnostics'].values())
    cuts = {w['field']: w for w in body['meta']['warnings'] if w['type'] == 'truncated'}
    assert cuts['map.metadata.extraction_diagnostics']['total'] == 53
    assert cuts['map.metadata.files_failed']['total'] == 53
    assert all(len(w.get('files', [])) <= 5 for w in body['meta']['warnings'])
    artifact = project / 'answer.json'
    rendered = run('overview', project, '--top', '0', '--output', f'json={artifact}', '--fields', 'path')
    assert rendered.returncode == 3
    assert json.loads(artifact.read_text(encoding='utf-8'))['path'] == project.as_posix()


@pytest.mark.parametrize('owner', ['fan_in', 'entrypoints', 'components', 'circular', 'get_metadata'])
def test_malformed_required_producer_is_failed_with_scope_survivors(project, monkeypatch, owner):
    monkeypatch.setattr(ImportView, owner, lambda self: {})
    result, body = answer(project)
    assert result.returncode == 3 and body['map_status'] == 'failed'
    assert body['scope']['total_code_files'] == 24
    assert OverviewAdapter.execution_facts(body).completeness is AnalysisCompleteness.FAILED


@pytest.mark.parametrize('language', LANGUAGES)
def test_conformance_scope_and_map_are_qualified(language):
    fixtures = Path(__file__).parent / 'fixtures'
    root = (fixtures / ('smoke' if language == 'tsx' else 'conformance') / language).resolve()
    result, body = answer(root, query='top=0')
    assert result.returncode in (0, 3), result.stderr
    assert body['scope']['total_code_files'] >= 1
    assert body['map_status'] != 'failed'
    assert body['map']['metadata']['scan_budget']['returned'] >= 1
    assert OverviewAdapter(str(root)).answer_requirement_error(body, 'overview') is None


def test_final_proof_validator_does_not_consume_query_controls(project):
    from reveal.utils.query_parser import peek_query_items
    adapter = OverviewAdapter(str(project), 'no_imports=true')
    body = adapter.get_structure()
    before = list(peek_query_items(adapter.query_params))
    assert adapter.answer_requirement_error(body, 'overview') is None
    assert list(peek_query_items(adapter.query_params)) == before


@pytest.mark.parametrize('damage', ['row', 'entry_filter', 'rule', 'budget', 'diagnostics', 'new_error',
                                  'unsupported_count', 'distinct_rules',
                                  'hidden', 'counting_rule', 'language_count', 'reading_note'])
def test_postprocessing_cannot_erase_required_map_proof(project, monkeypatch, damage):
    def corrupt(result, args):
        if damage == 'row':
            result['map']['fan_in']['rows'][0] = None
        elif damage == 'entry_filter':
            result['map'].pop('entry_point_filter')
        elif damage == 'rule':
            result['map']['rules'] = {}
        elif damage == 'budget':
            result['map']['metadata']['scan_budget']['returned'] = 'not a count'
        elif damage == 'diagnostics':
            result['map']['metadata'].pop('extraction_diagnostics_count')
        elif damage == 'unsupported_count':
            result['map']['metadata']['unsupported_extensions'] = {'.ex': -1}
        elif damage == 'distinct_rules':
            result['map']['rules']['edge_rule_sections'] = {}
        elif damage == 'new_error':
            result['map'].pop('entry_point_filter')
            result['meta'] = {'errors': [{'code': 'invented', 'message': 'postprocess error'}]}
        elif damage == 'reading_note':
            result.pop('reading_note')
        else:
            result['scope'].pop(damage)
        return result
    monkeypatch.setattr(OverviewAdapter, 'post_process', staticmethod(corrupt), raising=False)
    result, body = answer(project)
    assert result.returncode == 3
    assert body.get('error') or any(e['code'] == 'E_REQUIRED_ANSWER' for e in body.get('meta', {}).get('errors', []))
