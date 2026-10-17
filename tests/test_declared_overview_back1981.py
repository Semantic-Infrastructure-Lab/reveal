"""Both overview spellings preserve requested populations and execution facts."""
import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.overview import OverviewAdapter


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path/'proj'
    root.mkdir()
    for n in range(7):
        folder = root/f'pkg{n}'
        folder.mkdir()
        (folder/'a.py').write_text(f'def hot{n}(x):\n'+''.join(
            f'    if x == {i}: return {i}\n' for i in range(12))+'    return 0\n', encoding='utf-8')
    return root


def equal_answers(left, right):
    left, right = copy.deepcopy(left), copy.deepcopy(right)
    if 'execution' in left:
        del left['execution']['command'], right['execution']['command']
    assert left == right


def requests(cli=(), query=''):
    return (['overview', 'proj', '--no-git', *cli],
            ['overview://proj?no_git=true'+query])


@pytest.mark.parametrize('cli,query,count', [([], '', 5), (['--top', '0'], '&top=0', 0),
    (['--top', '3.0'], '&top=3.0', 3), (['--top', '3e0'], '&top=3e0', 3),
    (['--no-imports'], '&no_imports=true', 5)])
@pytest.mark.parametrize('provenance', [False, True])
def test_exact_parity_arrays_and_provenance(project, cli, query, count, provenance):
    flags = ['--provenance'] if provenance else []
    left_argv, right_argv = requests(cli, query)
    left_argv += ['--format', 'json', *flags]
    right_argv += ['--format', 'json', *flags]
    a, b = run(*left_argv), run(*right_argv)
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    left, right = json.loads(a.stdout), json.loads(b.stdout)
    assert left['type'] == right['type'] == 'overview'
    assert len(left['complex_functions']) == count
    assert len(left['stats']['hotspots']) == (7 if count == 0 else count)
    assert len(left['stats']['files']) == 7
    if provenance:
        assert left['execution']['command'] == ' '.join(['reveal', *left_argv])
        assert right['execution']['command'] == ' '.join(['reveal', *right_argv])
    equal_answers(left, right)


@pytest.mark.parametrize('flag', ['--all', '--verbose'])
@pytest.mark.parametrize('top', [None, 0, 2])
def test_expansion_flags_override_top_in_both_forms(project, flag, top):
    cli = [] if top is None else ['--top', str(top)]
    query = '' if top is None else '&top='+str(top)
    left, right = requests(cli, query)
    a, b = run(*left, flag, '--format', 'json'), run(*right, flag, '--format', 'json')
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    answer = json.loads(a.stdout)
    assert len(answer['complex_functions']) == len(answer['stats']['hotspots']) == 7
    equal_answers(answer, json.loads(b.stdout))
    a, b = run(*left, flag), run(*right, flag)
    assert a.returncode == b.returncode == 0 and a.stdout == b.stdout


@pytest.mark.parametrize('query,cli', [('top=-1', ['--top', '-1']), ('top=1.5', ['--top', '1.5']),
    ('top=true', ['--top', 'true']), ('top', None), ('no_git=garbage', None), ('no_imports=garbage', None)])
def test_invalid_values_are_canonical_usage(project, query, cli):
    cases = [['overview://proj?'+query]]
    if cli is not None:
        cases.append(['overview', 'proj', *cli])
    for argv in cases:
        result = run(*argv, '--format', 'json')
        assert result.returncode == 2, result.stderr
        assert json.loads(result.stdout)['type'] == 'overview'


@pytest.mark.parametrize('query', ['no_git=yes&no_imports=1', 'no_git=true&no_imports=true'])
def test_strict_true_boolean_spellings(project, query):
    a = run('overview', 'proj', '--no-git', '--no-imports', '--format', 'json')
    b = run('overview://proj?'+query, '--format', 'json')
    assert a.returncode == b.returncode == 0
    equal_answers(json.loads(a.stdout), json.loads(b.stdout))


@pytest.mark.parametrize('kind', ['scope', 'imports', 'parse', 'check', 'ast', 'git'])
def test_required_failure_survives_projection_and_postprocessing(project, monkeypatch, kind):
    if kind == 'parse':
        (project/'bad.py').write_text('def broken(:\n', encoding='utf-8')
    else:
        def fail(*args, **kwargs):
            raise OSError('exact required '+kind+' failure')
        target = {'scope': 'reveal.adapters.overview.scope_dict_for_path',
                  'imports': 'reveal.adapters.imports.ImportsAdapter._build_graph',
                  'check': 'reveal.rules.RuleRegistry.check_file',
                  'ast': 'reveal.adapters.ast.AstAdapter.get_structure',
                  'git': 'reveal.adapters.overview._resolve_git_root'}[kind]
        monkeypatch.setattr(target, fail)
    # Prove an output transformation cannot erase precomputed required facts.
    def clear_diagnostics(self, result, args):
        result['meta']['warnings'] = []
        result['meta']['errors'] = []
        return result
    monkeypatch.setattr(OverviewAdapter, 'post_process', clear_diagnostics, raising=False)
    for argv in (['overview', 'proj'], ['overview://proj']):
        full = run(*argv, '--format', 'json')
        assert full.returncode == 3, full.stderr
        result = run(*argv, '--format', 'json', '--fields', 'path')
        assert result.returncode == 3, result.stderr


@pytest.mark.parametrize('phase', ['answer', 'postprocess'])
@pytest.mark.parametrize('kind', ['empty', 'wrong', 'missing_stats', 'empty_scope', 'complex_type'])
def test_malformed_outer_answer_is_required_failure(project, monkeypatch, phase, kind):
    original = OverviewAdapter.get_structure
    def malformed(result):
        if kind == 'empty':
            return {}
        if kind == 'wrong':
            result['type'] = 'wrong'
        elif kind == 'missing_stats':
            result.pop('stats')
        elif kind == 'empty_scope':
            result['scope'] = {}
        else:
            result['complex_functions'] = None
        return result
    if phase == 'answer':
        monkeypatch.setattr(OverviewAdapter, 'get_structure', lambda self, **kw: malformed(original(self, **kw)))
    else:
        monkeypatch.setattr(OverviewAdapter, 'post_process', lambda self, result, args: malformed(result), raising=False)
    for argv in requests():
        result = run(*argv, '--format', 'json')
        assert result.returncode == 3, result.stderr
        answer = json.loads(result.stdout)
        assert answer['type'] == 'overview' and answer['error']


@pytest.mark.parametrize('transport', ['cli', 'uri'])
def test_artifacts_primary_json_noop_and_none_policy(project, transport):
    argv = requests()[transport == 'uri']
    path = project.parent/(transport+'.json')
    result = run(*argv, '--also-json', str(path), '--fail-on', 'none')
    assert result.returncode == 0, result.stderr
    assert len(json.loads(path.read_text(encoding='utf-8'))['complex_functions']) == 5
    result = run(*argv, '--also-json', str(project))
    assert result.returncode == 3 and 'artifact failed' in result.stderr
    result = run(*argv, '--format', 'json', '--also-json', str(project))
    assert result.returncode == 0 and json.loads(result.stdout)['type'] == 'overview'


@pytest.mark.parametrize('transport', ['cli', 'uri'])
@pytest.mark.parametrize('kind', ['missing', 'inaccessible'])
def test_resource_errors_keep_identity(project, monkeypatch, transport, kind):
    path = 'absent' if kind == 'missing' else 'proj'
    if kind == 'inaccessible':
        stat = Path.stat
        def inaccessible(self, *args, **kwargs):
            if str(self) in ('proj', str(project)):
                raise PermissionError('required overview access failure')
            return stat(self, *args, **kwargs)
        monkeypatch.setattr(Path, 'stat', inaccessible)
    argv = ['overview', path] if transport == 'cli' else ['overview://'+path]
    result = run(*argv, '--format', 'json')
    assert result.returncode == (2 if kind == 'missing' else 3), result.stderr
    assert json.loads(result.stdout)['type'] == 'overview'


@pytest.mark.parametrize('name', ['literal%26,é&=.py', pytest.param('literal?%26.py', marks=
    pytest.mark.skipif(sys.platform == 'win32', reason='Windows filenames cannot contain question marks'))])
def test_encoded_file_resource_and_source_spelling(project, name):
    path = project/name
    path.write_text('import os\n', encoding='utf-8')
    a = run('overview', str(path), '--no-git', '--format', 'json')
    b = run('overview://'+quote(str(path), safe='/')+'?no_git=true', '--format', 'json')
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    equal_answers(json.loads(a.stdout), json.loads(b.stdout))


def test_query_exclusion_boundary_and_global_flag_remain_distinct(project):
    a = run('overview://proj?no_git=true&top=20&exclude=pkg0', '--format', 'json')
    b = run('overview://proj?no_git=true&top=20', '--exclude', 'pkg0', '--format', 'json')
    assert a.returncode == b.returncode == 0
    left, right = json.loads(a.stdout), json.loads(b.stdout)
    assert left['stats']['summary']['total_files'] == right['stats']['summary']['total_files'] == 6
    assert any(f['name'] == 'hot0' for f in left['complex_functions'])
    assert all(f['name'] != 'hot0' for f in right['complex_functions'])


@pytest.mark.parametrize('partial,artifact,expected', [(False, False, 0), (True, False, 3), (False, True, 3)])
def test_closed_pipe_preserves_independent_required_failures(project, partial, artifact, expected):
    if partial:
        (project/'bad.py').write_text('def broken(:\n', encoding='utf-8')
    argv = [sys.executable, '-m', 'reveal', 'overview', 'proj', '--no-git']
    if artifact:
        argv += ['--also-json', str(project)]
    with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=os.environ.copy()) as process:
        process.stdout.close()
        code = process.wait(timeout=30)
        diagnostic = process.stderr.read().decode('utf-8', errors='replace')
    assert code == expected, diagnostic
    assert 'Traceback' not in diagnostic


def test_legacy_batch_stays_outside_declared_execution(project, monkeypatch):
    from io import StringIO
    (project/'bad.py').write_text('def broken(:\n', encoding='utf-8')
    monkeypatch.setattr(sys, 'stdin', StringIO('overview://proj?no_git=true\n'))
    result = run('--stdin', '--batch', '--format', 'json')
    assert result.returncode == 0
    entry, = json.loads(result.stdout)['results']
    assert entry['status'] == 'success'
    monkeypatch.setattr(sys, 'stdin', StringIO('overview://proj\n'))
    result = run('--stdin', '--batch', '--fail-on', 'none')
    assert result.returncode == 2


def test_exact_comparison_detects_lost_diagnostics():
    with pytest.raises(AssertionError):
        equal_answers({'meta': {'errors': [{'message': 'retain'}]}}, {'meta': {'errors': []}})


@pytest.mark.parametrize('kind', ['empty', 'excluded', 'unsupported', 'empty_python'])
def test_completed_empty_or_unsupported_populations_are_not_failed(project, monkeypatch, kind):
    if kind != 'excluded':
        import shutil
        for directory in project.iterdir():
            shutil.rmtree(directory)
    if kind == 'unsupported':
        (project/'x.hs').write_text('module X where\nf x = x\n', encoding='utf-8')
    elif kind == 'empty_python':
        (project/'x.py').write_text('', encoding='utf-8')
    flags = ['--exclude', '*'] if kind == 'excluded' else []
    for argv in requests():
        result = run(*argv, *flags, '--format', 'json')
        assert result.returncode == 0, result.stderr
        answer = json.loads(result.stdout)
        assert answer['architecture']['metadata']['files_failed_count'] == 0
        assert not answer.get('meta', {}).get('errors')


@pytest.mark.parametrize('query', ['no_git=no&no_imports=0', 'no_git=false&no_imports=false'])
def test_false_boolean_spellings_do_not_skip_requested_children(project, monkeypatch, query):
    seen = []
    monkeypatch.setattr('reveal.adapters.overview._resolve_git_root', lambda path: seen.append('git'))
    result = run('overview://proj?'+query, '--format', 'json')
    assert result.returncode == 0
    assert seen == ['git'] and json.loads(result.stdout)['architecture']['metadata']


@pytest.mark.parametrize('flag', ['--head', '--max-items'])
def test_uri_budget_controls_disclose_no_sliceable_overview_list(project, flag):
    base = run('overview://proj?no_git=true', '--format', 'json')
    result = run('overview://proj?no_git=true', flag, '1', '--format', 'json')
    assert result.returncode == 0, result.stderr
    a, b = json.loads(base.stdout), json.loads(result.stdout)
    assert a['complex_functions'] == b['complex_functions']
    assert a['stats']['hotspots'] == b['stats']['hotspots']
    assert flag in result.stderr and ('no effect' in result.stderr or 'no list to slice' in result.stderr)


@pytest.mark.parametrize('transport', ['cli', 'uri'])
@pytest.mark.parametrize('position', ['before', 'after'])
def test_only_none_policy_is_supported(project, transport, position):
    argv = requests()[transport == 'uri']
    for policy, expected in [('none', 0), ('findings', 2)]:
        request = ['--fail-on', policy, *argv] if position == 'before' else [*argv, '--fail-on', policy]
        result = run(*request, '--format', 'json')
        assert result.returncode == expected, result.stderr


def test_typed_binder_declaration_defaults_and_roles():
    from reveal.utils.query_binding import bind_declared_params
    from reveal.utils.query_parser import collect_query_keys
    specs = OverviewAdapter.PARAM_SPECS
    schema = OverviewAdapter.get_schema()
    assert schema['execution_policy'] == {'default_fail_on': 'none', 'fail_on': ['none']}
    assert 'execution' not in schema
    assert [(s.name, s.role) for s in specs] == [('top', 'analysis'), ('no_git', 'analysis'), ('no_imports', 'analysis')]
    with collect_query_keys() as keys:
        params = bind_declared_params(specs, {}, transport='typed')
        assert dict(params) == {} and keys.used == set()
        assert [s.read(params) for s in specs] == [5, False, False]
    for value in [True, False, 1.5]:
        with pytest.raises(ValueError):
            bind_declared_params(specs, {'top': value}, transport='typed')


def test_generated_cli_budget_is_disclosed_without_slicing(project):
    result = run('overview', 'proj', '--no-git', '--max-items', '1', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert len(json.loads(result.stdout)['complex_functions']) == 5
    assert '--max-items' in result.stderr and 'no effect' in result.stderr


def test_absent_resource_defaults_match_and_parser_missing_value_is_usage(project, monkeypatch):
    monkeypatch.chdir(project)
    a = run('overview', '--no-git', '--format', 'json')
    b = run('overview://?no_git=true', '--format', 'json')
    assert a.returncode == b.returncode == 0
    equal_answers(json.loads(a.stdout), json.loads(b.stdout))
    result = run('overview', '--top')
    assert result.returncode == 2 and result.stdout == '' and 'usage:' in result.stderr


@pytest.mark.parametrize('warning', ['churn_unavailable', 'informational', 'truncated'])
def test_optional_warnings_and_low_confidence_do_not_imply_required_failure(project, monkeypatch, warning):
    original = OverviewAdapter.get_structure
    def observed(self, **kwargs):
        result = original(self, **kwargs)
        result['meta']['confidence'] = 0.0
        result['meta']['warnings'].append({'type': warning, 'message': 'optional observation'})
        return result
    monkeypatch.setattr(OverviewAdapter, 'get_structure', observed)
    for argv in requests():
        result = run(*argv, '--format', 'json')
        assert result.returncode == 0, result.stderr


def test_import_failed_count_is_required_even_without_parent_warning(project, monkeypatch):
    from reveal.adapters.overview import _run_imports_analysis
    def failed(adapter, path):
        result = _run_imports_analysis(adapter, path)
        result['metadata'].update(files_failed_count=1, files_failed=['pkg0/a.py'])
        return result
    monkeypatch.setattr('reveal.adapters.overview._run_imports_analysis', failed)
    for argv in requests():
        full = run(*argv, '--format', 'json')
        assert full.returncode == 3, full.stderr
        result = run(*argv, '--format', 'json', '--fields', 'path')
        assert result.returncode == 3, result.stderr


def test_no_git_and_no_imports_skip_only_their_owners(project, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError('explicitly skipped owner ran')
    monkeypatch.setattr('reveal.adapters.overview._resolve_git_root', unexpected)
    monkeypatch.setattr('reveal.adapters.overview._run_imports_analysis', unexpected)
    a = run('overview', 'proj', '--no-git', '--no-imports', '--format', 'json')
    b = run('overview://proj?no_git=true&no_imports=true', '--format', 'json')
    assert a.returncode == b.returncode == 0
    answer = json.loads(a.stdout)
    assert answer['architecture'] == {} and answer['git_log'] == []
    assert len(answer['complex_functions']) == 5 and answer['stats']['summary']['total_files'] == 7
    equal_answers(answer, json.loads(b.stdout))


@pytest.mark.parametrize('phase', ['answer', 'postprocess'])
@pytest.mark.parametrize('with_error', [False, True])
def test_producer_error_label_cannot_reclassify_analysis_as_usage(project, monkeypatch, phase, with_error):
    original = OverviewAdapter.get_structure
    def observed(result):
        result['meta']['errors'].append({'code': 'invalid_request', 'message': 'required producer failed'})
        if with_error:
            result['error'] = 'required producer failed'
        return result
    if phase == 'answer':
        monkeypatch.setattr(OverviewAdapter, 'get_structure', lambda self, **kw: observed(original(self, **kw)))
    else:
        monkeypatch.setattr(OverviewAdapter, 'post_process', lambda self, result, args: observed(result), raising=False)
    for argv in requests():
        result = run(*argv, '--format', 'json')
        assert result.returncode == 3, result.stderr
        assert json.loads(result.stdout)['type'] == 'overview'


@pytest.mark.parametrize('with_error', [False, True])
def test_returned_producer_error_facts_are_analysis_failure(project, with_error):
    from reveal.utils.results import AnalysisCompleteness, FailureCause
    result = OverviewAdapter(str(project), 'no_git=true').get_structure()
    result['meta']['errors'].append({'code': 'invalid_request', 'message': 'required producer failed'})
    if with_error:
        result['error'] = 'required producer failed'
    facts = OverviewAdapter.execution_facts(result)
    assert facts.completeness in (AnalysisCompleteness.INCOMPLETE, AnalysisCompleteness.FAILED)
    assert FailureCause.INVALID_REQUEST not in facts.failures


@pytest.mark.parametrize('phase', ['answer', 'postprocess'])
@pytest.mark.parametrize('skip', [False, True])
@pytest.mark.parametrize('copied', [False, True])
def test_erased_architecture_is_valid_only_when_requested_skip(project, monkeypatch, phase, skip, copied):
    original = OverviewAdapter.get_structure
    def erase(result):
        if copied:
            result = copy.deepcopy(result)
        result['architecture'] = {}
        return result
    if phase == 'answer':
        monkeypatch.setattr(OverviewAdapter, 'get_structure', lambda self, **kw: erase(original(self, **kw)))
    else:
        monkeypatch.setattr(OverviewAdapter, 'post_process', lambda self, result, args: erase(result), raising=False)
    for argv in requests(['--no-imports'] if skip else [], '&no_imports=true' if skip else ''):
        result = run(*argv, '--format', 'json')
        assert result.returncode == (0 if skip else 3), result.stderr
        answer = json.loads(result.stdout)
        if not skip:
            assert answer['error'] and any(e['code'] == 'invalid_adapter_answer' for e in answer['meta']['errors'])


@pytest.mark.parametrize('skip', [False, True])
def test_owner_answer_requirement_does_not_consume_bound_query(project, skip):
    from reveal.utils.query_parser import collect_query_keys
    result = OverviewAdapter(str(project), 'no_git=true'+('&no_imports=true' if skip else '')).get_structure()
    with collect_query_keys() as keys:
        adapter = OverviewAdapter(str(project), params={'no_imports': skip})
        before = set(keys.used)
        assert adapter.answer_requirement_error(result, 'overview') is None
        assert keys.used == before


def test_existing_static_sibling_hook_accepts_class_and_instance():
    from reveal.adapters.architecture import ArchitectureAdapter
    from reveal.cli.routing.declared import qualify_declared_answer
    from reveal.utils.results import ResultBuilder
    result = ResultBuilder.create('architecture_diff', '.', data={'analysis': {'complete': True}})
    assert qualify_declared_answer(result, ArchitectureAdapter, '.', 'architecture_diff') is result
    assert qualify_declared_answer(result, ArchitectureAdapter('.'), '.', 'architecture_diff') is result
