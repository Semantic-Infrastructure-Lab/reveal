"""The contracts spellings share binding, producer evidence and requested output."""
import copy
import json
import os
import subprocess
import sys
from urllib.parse import quote

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.contracts import ContractsAdapter


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / 'proj'
    root.mkdir()
    (root/'contract.py').write_text(
        'from abc import ABC, abstractmethod\nclass Contract(ABC):\n'
        ' @abstractmethod\n def go(self): pass\n' +
        ''.join(f'class Impl{i}(Contract):\n def go(self): return {i}\n' for i in range(8)),
        encoding='utf-8')
    (root/'contract.go').write_text('package p\ntype GoContract interface { Go() }\n', encoding='utf-8')
    return root


def equal_answers(left, right):
    left, right = copy.deepcopy(left), copy.deepcopy(right)
    if 'execution' in left:
        del left['execution']['command']
        del right['execution']['command']
    assert left == right


@pytest.mark.parametrize('cli,query,cap', [
    ([], '', 5), (['--abstract-only'], '?abstract_only=true', 5),
    (['--no-implementations'], '?implementations=false', 5),
    (['--impls', '0'], '?impls=0', 0), (['--impls', '3.0'], '?impls=3.0', 3),
    (['--impls', '20'], '?impls=20', 20),
])
@pytest.mark.parametrize('provenance', [False, True])
def test_exact_json_parity_including_ordered_polyglot_implementers(project, cli, query, cap, provenance):
    flags = ['--provenance'] if provenance else []
    left_argv = ['contracts', 'proj', *cli, '--format', 'json', *flags]
    right_argv = ['contracts://proj'+query, '--format', 'json', *flags]
    a, b = run(*left_argv), run(*right_argv)
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    left, right = json.loads(a.stdout), json.loads(b.stdout)
    assert left['type'] == right['type'] == 'contracts'
    assert left['impls_cap'] == right['impls_cap'] == cap
    if provenance:
        assert left['execution']['command'] == ' '.join(['reveal', *left_argv])
        assert right['execution']['command'] == ' '.join(['reveal', *right_argv])
    equal_answers(left, right)
    assert 'has no effect' not in a.stderr+b.stderr
    if '--no-implementations' not in cli:
        assert len(left['by_language']['python']['abcs'][0]['implementations']) == 8


@pytest.mark.parametrize('cli,query,cut', [([], '', True), (['--impls', '3.0'], '?impls=3.0', True),
                                          (['--impls', '0'], '?impls=0', False)])
def test_text_caps_and_human_artifacts_keep_full_arrays(project, cli, query, cut):
    a = run('contracts', 'proj', *cli, '--also-json', 'a.json')
    b = run('contracts://proj'+query, '--also-json', 'b.json')
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    assert a.stdout == b.stdout
    assert ('more' in a.stdout) is cut
    left = json.loads((project.parent/'a.json').read_text(encoding='utf-8'))
    right = json.loads((project.parent/'b.json').read_text(encoding='utf-8'))
    equal_answers(left, right)
    assert len(left['by_language']['python']['abcs'][0]['implementations']) == 8


@pytest.mark.parametrize('query,cli', [
    ('impls=-1', ['--impls', '-1']), ('impls=1.5', ['--impls', '1.5']),
    ('impls=1e3', ['--impls', '1e3']), ('impls=true', ['--impls', 'true']),
    ('impls', None), ('abstract_only=garbage', None), ('implementations=garbage', None),
])
def test_resolved_parameter_rejection_is_canonical_usage(project, query, cli):
    requests = [['contracts://proj?'+query]]
    if cli is not None:
        requests.append(['contracts', 'proj', *cli])
    for argv in requests:
        result = run(*argv, '--format', 'json')
        assert result.returncode == 2, result.stderr
        answer = json.loads(result.stdout)
        assert answer['type'] == 'contracts' and answer['error']


def test_parser_rejection_has_usage_and_empty_stdout(project):
    result = run('contracts', 'proj', '--impls')
    assert result.returncode == 2 and result.stdout == ''
    assert 'usage:' in result.stderr


@pytest.mark.parametrize('query', ['abstract_only=false', 'abstract_only=0', 'implementations=true', 'implementations=1'])
def test_explicit_boolean_controls_match_default(project, query):
    a = run('contracts', 'proj', '--format', 'json')
    b = run('contracts://proj?'+query, '--format', 'json')
    assert a.returncode == b.returncode == 0
    equal_answers(json.loads(a.stdout), json.loads(b.stdout))


@pytest.mark.parametrize('filename', ['literal%26,é&=.py', pytest.param('literal?%26,é.py', marks=
    pytest.mark.skipif(sys.platform == 'win32', reason='Windows filenames cannot contain question marks'))])
def test_encoded_regular_file_resource(project, filename):
    target = project/filename
    target.write_text('from abc import ABC\nclass Contract(ABC): pass\n', encoding='utf-8')
    a = run('contracts', str(target), '--format', 'json')
    b = run('contracts://'+quote(str(target), safe='/'), '--format', 'json')
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    equal_answers(json.loads(a.stdout), json.loads(b.stdout))
    assert json.loads(a.stdout)['total_contracts'] == 1


def test_literal_percent_resource_has_existing_path_precedence(project):
    literal, decoded = project.parent/'literal%26', project.parent/'literal&'
    literal.mkdir()
    decoded.mkdir()
    (literal/'contract.py').write_text('from abc import ABC\nclass Contract(ABC): pass\n', encoding='utf-8')
    a = run('contracts', str(literal), '--format', 'json')
    b = run('contracts://'+str(literal), '--format', 'json')
    assert a.returncode == b.returncode == 0
    equal_answers(json.loads(a.stdout), json.loads(b.stdout))
    assert json.loads(a.stdout)['total_contracts'] == 1


@pytest.mark.parametrize('flags', [[], ['--exclude', 'contract.go'], ['--no-gitignore']])
def test_real_scope_and_gitignore_parity(project, flags):
    (project/'.gitignore').write_text('ignored.py\n', encoding='utf-8')
    (project/'ignored.py').write_text('from abc import ABC\nclass Ignored(ABC): pass\n', encoding='utf-8')
    a = run('contracts', 'proj', '--format', 'json', *flags)
    b = run('contracts://proj', '--format', 'json', *flags)
    assert a.returncode == b.returncode == 0
    equal_answers(json.loads(a.stdout), json.loads(b.stdout))
    assert json.loads(a.stdout)['total_contracts'] == (3 if '--no-gitignore' in flags else 1 if '--exclude' in flags else 2)


@pytest.mark.parametrize('kind', ['clean', 'empty', 'unsupported'])
def test_default_resource_and_disclosed_empty_inventory_are_complete(project, monkeypatch, kind):
    if kind != 'clean':
        for file in project.iterdir():
            file.unlink()
    if kind == 'unsupported':
        (project/'source.lua').write_text('local value = 1\n', encoding='utf-8')
    monkeypatch.chdir(project)
    a = run('contracts', '--format', 'json', '--fail-on', 'none')
    b = run('contracts://', '--format', 'json', '--fail-on', 'none')
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    equal_answers(json.loads(a.stdout), json.loads(b.stdout))
    assert json.loads(a.stdout)['total_contracts'] == (2 if kind == 'clean' else 0)


@pytest.mark.parametrize('kind', ['recovered', 'shared', 'native', 'allfailed'])
def test_required_producer_evidence_survives_fields_projection(project, monkeypatch, kind):
    from reveal.adapters.ast import analysis, nav_surface_common
    if kind == 'recovered':
        (project/'broken.py').write_text('def broken(:\n', encoding='utf-8')
    else:
        def fail(*args, **kwargs):
            raise OSError('exact required producer failure')
        if kind in ('shared', 'allfailed'):
            monkeypatch.setattr(analysis, 'create_element_dict', fail)
        if kind in ('native', 'allfailed'):
            monkeypatch.setattr(nav_surface_common, 'get_tree', fail)
    for argv in (['contracts', 'proj'], ['contracts://proj']):
        full = run(*argv, '--format', 'json', '--fail-on', 'none')
        assert full.returncode == 3, full.stderr
        answer = json.loads(full.stdout)
        assert answer['type'] == 'contracts'
        assert answer.get('recovered_files') if kind == 'recovered' else answer['meta']['errors']
        projected = run(*argv, '--format', 'json', '--fields', 'total_contracts', '--fail-on', 'none')
        assert projected.returncode == 3


@pytest.mark.parametrize('kind', ['raised', 'wrong', 'empty', 'bare', 'postwrong', 'postempty'])
def test_required_answer_failures_keep_identity(project, monkeypatch, kind):
    from reveal.utils.results import ResultBuilder
    if kind.startswith('post'):
        monkeypatch.setattr(ContractsAdapter, 'post_process', staticmethod(
            lambda result, args: {} if kind == 'postempty' else ResultBuilder.create('wrong', 'proj')), raising=False)
    elif kind == 'raised':
        def fail(self, **kwargs):
            raise OSError('required contracts unavailable')
        monkeypatch.setattr(ContractsAdapter, 'get_structure', fail)
    else:
        payload = {} if kind == 'empty' else {'error': 'missing evidence'} if kind == 'bare' else ResultBuilder.create('wrong', 'proj')
        monkeypatch.setattr(ContractsAdapter, 'get_structure', lambda self, **kwargs: payload)
    for argv in (['contracts', 'proj'], ['contracts://proj']):
        result = run(*argv, '--format', 'json', '--fail-on', 'none')
        assert result.returncode == 3, result.stderr
        assert json.loads(result.stdout)['type'] == 'contracts'


@pytest.mark.parametrize('spelling', ['cli', 'uri'])
def test_artifact_failure_and_json_primary_noop(project, spelling):
    argv = ['contracts', 'proj'] if spelling == 'cli' else ['contracts://proj']
    result = run(*argv, '--also-json', str(project))
    assert result.returncode == 3 and 'artifact failed' in result.stderr
    result = run(*argv, '--format', 'json', '--also-json', str(project))
    assert result.returncode == 0
    assert json.loads(result.stdout)['total_contracts'] == 2


def test_runtime_artifact_failure_keeps_parseable_primary(project, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError('runtime artifact failure')
    monkeypatch.setattr('reveal.utils.json_utils.write_also_json', fail)
    result = run('contracts://proj', '--format', 'json')
    assert result.returncode == 3
    assert json.loads(result.stdout)['meta']['output_errors'][0]['code'] == 'artifact_write_failed'


def test_renderer_failure_is_required_output(project, monkeypatch):
    from reveal.rendering.adapters.contracts import ContractsRenderer
    def fail(*args, **kwargs):
        raise OSError('requested text unavailable')
    monkeypatch.setattr(ContractsRenderer, 'render_structure', fail)
    result = run('contracts', 'proj')
    assert result.returncode == 3 and 'requested text unavailable' in result.stderr


@pytest.mark.parametrize('incomplete,artifact_failure,expected', [(False, False, 0), (True, False, 3), (False, True, 3)])
def test_closed_stdout_preserves_independent_failure(project, incomplete, artifact_failure, expected):
    if incomplete:
        (project/'broken.py').write_text('def broken(:\n', encoding='utf-8')
    argv = [sys.executable, '-m', 'reveal', 'contracts', 'proj']
    if artifact_failure:
        argv.extend(['--also-json', str(project)])
    with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=os.environ.copy()) as process:
        process.stdout.close()
        code = process.wait(timeout=30)
        errors = process.stderr.read().decode('utf-8', errors='replace')
    assert code == expected, errors
    assert 'Traceback' not in errors


def test_legacy_stdin_batch_remains_outside_declared_policy(project, monkeypatch):
    from io import StringIO
    monkeypatch.setattr(sys, 'stdin', StringIO('contracts://proj\n'))
    result = run('--stdin', '--batch', '--format', 'json', '--fail-on', 'none')
    assert result.returncode == 2 and '--fail-on' in result.stderr


def test_exact_comparison_detects_dropped_diagnostic():
    with pytest.raises(AssertionError):
        equal_answers({'meta': {'errors': [{'message': 'retain'}]}}, {'meta': {'errors': []}})


@pytest.mark.parametrize('spelling', ['cli', 'uri'])
@pytest.mark.parametrize('position', ['before', 'after'])
def test_none_policy_supported_on_each_side_of_resolved_request(project, spelling, position):
    argv = ['contracts', 'proj'] if spelling == 'cli' else ['contracts://proj']
    argv = ['--fail-on', 'none', *argv] if position == 'before' else [*argv, '--fail-on', 'none']
    result = run(*argv, '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['total_contracts'] == 2


def test_missing_resource_is_structured_usage_in_both_forms(project):
    for argv in (['contracts', 'absent'], ['contracts://absent']):
        result = run(*argv, '--format', 'json')
        assert result.returncode == 2, result.stderr
        answer = json.loads(result.stdout)
        assert answer['type'] == 'contracts' and answer['error']


def test_legacy_stdin_batch_keeps_legacy_partial_success_policy(project, monkeypatch):
    from io import StringIO
    (project/'broken.py').write_text('def broken(:\n', encoding='utf-8')
    monkeypatch.setattr(sys, 'stdin', StringIO('contracts://proj\n'))
    result = run('--stdin', '--batch', '--format', 'json')
    assert result.returncode == 0
    entry, = json.loads(result.stdout)['results']
    assert entry['status'] == 'success'
    assert entry['data']['recovered_files']


def test_harmless_warning_does_not_make_completed_scan_fail(project, monkeypatch):
    original = ContractsAdapter.get_structure
    def observed(self, **kwargs):
        result = original(self, **kwargs)
        result['meta']['warnings'].append({'type': 'informational', 'message': 'harmless observation'})
        return result
    monkeypatch.setattr(ContractsAdapter, 'get_structure', observed)
    for argv in (['contracts', 'proj'], ['contracts://proj']):
        result = run(*argv, '--format', 'json', '--fail-on', 'none')
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)['meta']['warnings'][-1]['message'] == 'harmless observation'


@pytest.mark.parametrize('transport', ['cli', 'uri'])
def test_inaccessible_contracts_resource_is_canonical_analysis_failure(project, monkeypatch, transport):
    from pathlib import Path
    stat = Path.stat
    def inaccessible(self, *args, **kwargs):
        if str(self) in ('proj', str(project)):
            raise PermissionError('injected contracts access failure')
        return stat(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', inaccessible)
    argv = ['contracts', 'proj'] if transport == 'cli' else ['contracts://proj']
    result = run(*argv, '--format', 'json')
    assert result.returncode == 3, result.stderr
    answer = json.loads(result.stdout)
    assert answer['type'] == 'contracts'
    assert answer['meta']['errors'][0]['code'] == 'analysis'
    assert 'injected contracts access failure' in answer['error']


@pytest.mark.parametrize('provenance', [False, True])
def test_flat_single_language_exact_parity_and_arrays(project, provenance):
    (project/'contract.go').unlink()
    flags = ['--provenance'] if provenance else []
    left_argv = ['contracts', 'proj', '--format', 'json', *flags]
    right_argv = ['contracts://proj', '--format', 'json', *flags]
    a, b = run(*left_argv), run(*right_argv)
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    left, right = json.loads(a.stdout), json.loads(b.stdout)
    assert 'by_language' not in left and 'by_language' not in right
    assert len(left['abcs'][0]['implementations']) == 8
    if provenance:
        assert left['execution']['command'] == ' '.join(['reveal', *left_argv])
        assert right['execution']['command'] == ' '.join(['reveal', *right_argv])
    equal_answers(left, right)
