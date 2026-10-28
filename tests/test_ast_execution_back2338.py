"""Qualified AST queries preserve owner evidence through the existing URI answer."""

import json
import subprocess
import sys

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.adapters.ast.adapter import AstAdapter
from reveal.adapters.ast.analysis import StructureList
from reveal.errors import NotApplicableError


@pytest.fixture
def root(tmp_path):
    (tmp_path / 'app.py').write_text(
        'def alpha():\n    return 1\n\ndef beta():\n    return 2\n', encoding='utf-8')
    return tmp_path


def run(root, query='', *options):
    return _run_reveal_direct(f'ast://{root}' + ('?' + query if query else ''), *options)


@pytest.mark.parametrize('query', ['name~=[', 'decorator~=(', 'name!~(', 'name~=' + 'a' * 300])
@pytest.mark.parametrize('output', ['text', 'json'])
def test_invalid_query_is_usage_with_useful_diagnostic(root, query, output):
    result = run(root, query, '--format', output)
    assert result.returncode == 2
    assert 'regex' in result.stderr.lower() or 'regular expression' in result.stderr.lower()
    if output == 'json':
        answer = json.loads(result.stdout)
        assert answer['error']
        assert answer['meta']['errors'][0]['code'] == 'invalid_request'
    else:
        assert 'Results:' not in result.stdout


def test_real_cli_invalid_query_and_declared_sibling_agree(root):
    for scheme, query in [('ast', 'name~=['), ('imports', 'lazy=bogus')]:
        result = subprocess.run(
            [sys.executable, '-m', 'reveal', f'{scheme}://{root}?{query}', '--format', 'json'],
            capture_output=True, text=True, encoding='utf-8', timeout=30)
        assert result.returncode == 2
        assert json.loads(result.stdout)['error']
        assert 'Traceback' not in result.stderr


def test_python_api_keeps_validation_exception(root):
    with pytest.raises(ValueError, match='Invalid regular expression'):
        api.query(f'ast://{root}?name~=[')


@pytest.mark.parametrize('options', [[], ['--fields', 'results'], ['--head', '0']])
def test_required_parse_loss_survives_projection(root, options):
    (root / 'broken.py').write_text('def broken(:\n', encoding='utf-8')
    result = run(root, '', '--format', 'json', *options)
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['results']


@pytest.mark.parametrize('error', [ValueError('ANALYSIS_VALUE_ERROR'), RuntimeError('ANALYSIS_FAILURE')])
def test_runtime_error_is_required_failure_not_usage(root, monkeypatch, error):
    def fail(self, **kwargs):
        raise error
    monkeypatch.setattr(AstAdapter, 'get_structure', fail)
    result = run(root, '', '--format', 'json')
    assert result.returncode == 3
    assert json.loads(result.stdout)['error'] == str(error)


def test_ordinary_missing_resource_is_usage(root):
    result = run(root / 'absent', '', '--format', 'json')
    assert result.returncode == 2
    assert 'Path not found' in json.loads(result.stdout)['error']


@pytest.mark.parametrize('query', ['name=absent', 'name=a*&limit=1', 'typo_key=unused', 'show=dict-heatmap',
                                   'show=dict-schemas', 'reveal_type=missing'])
def test_completed_empty_cut_warning_and_legacy_modes_stay_successful(root, query):
    result = run(root, query, '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['results'] is not None


def test_required_loss_from_owner_is_not_any_meta_error(root, monkeypatch):
    original = AstAdapter._collect_structures
    def partial(self):
        structures = original(self)
        assert isinstance(structures, StructureList)
        structures.skipped.append(('lost.py', 'PermissionError: unreadable'))
        return structures
    monkeypatch.setattr(AstAdapter, '_collect_structures', partial)
    result = run(root, '', '--format', 'json')
    assert result.returncode == 3
    assert json.loads(result.stdout)['results']


def test_decline_stays_nonerror(root, monkeypatch):
    def decline(self, **kwargs):
        raise NotApplicableError('not relevant')
    monkeypatch.setattr(AstAdapter, 'get_structure', decline)
    result = run(root, '', '--format', 'json')
    assert result.returncode == 0
    assert json.loads(result.stdout)['applicable'] is False


def test_legacy_sibling_failure_keeps_legacy_exit(root):
    result = _run_reveal_direct(f'stats://{root / "absent"}', '--format', 'json')
    assert result.returncode == 1
    assert json.loads(result.stdout)['error']


def test_requested_artifact_failure_still_outranks_complete_analysis(root):
    result = run(root, '', '--also-json', str(root))
    assert result.returncode == 3
    assert 'alpha' in result.stdout
    assert 'Error' in result.stderr


@pytest.mark.parametrize('query,qualified', [
    ('show=dict-heatmap', False), ('show=dict-schemas', False), ('reveal_type=x', False),
    ('show=dict-heatmap&show=functions', True), ('show=functions&show=dict-heatmap', False),
    ('reveal_type=x&reveal_type=', True), ('reveal_type=&reveal_type=x', False),
    ('show=&reveal_type=', True), ('show&reveal_type', True),
    ('show=dict%2Dheatmap', True), ('reveal_type%3Dx', True),
    (' show=dict-heatmap ', False),
])
def test_mode_selector_matches_actual_constructor_semantics(root, query, qualified):
    adapter = AstAdapter(str(root), query)
    dedicated = adapter.show_mode in ('dict-heatmap', 'dict-schemas') or bool(adapter.reveal_type_var)
    assert dedicated is not qualified
    assert (AstAdapter.uri_execution_facts(f'{root}?{query}') is not None) is qualified


def test_metadata_error_alone_is_not_required_loss(root, monkeypatch):
    original = AstAdapter.get_structure
    def answer(self, **kwargs):
        result = original(self, **kwargs)
        result['meta']['errors'].append({'code': 'optional_detail', 'message': 'optional evidence unavailable'})
        return result
    monkeypatch.setattr(AstAdapter, 'get_structure', answer)
    result = run(root, '', '--format', 'json')
    assert result.returncode == 0
    assert json.loads(result.stdout)['meta']['errors']


def test_returned_required_failure_survives_field_projection(root, monkeypatch):
    original = AstAdapter.get_structure
    def failed(self, **kwargs):
        result = original(self, **kwargs)
        result['error'] = 'required analysis failed'
        return result
    monkeypatch.setattr(AstAdapter, 'get_structure', failed)
    result = run(root, '', '--format', 'json', '--fields', 'results')
    assert result.returncode == 3
    assert json.loads(result.stdout)['results']


def test_renderer_failure_is_requested_output_failure(root, monkeypatch):
    from reveal.adapters.ast.renderer import AstRenderer
    def failed(*args, **kwargs):
        raise RuntimeError('RENDER_FAILED')
    monkeypatch.setattr(AstRenderer, 'render_structure', failed)
    result = run(root)
    assert result.returncode == 3
    assert 'Requested output failed: RENDER_FAILED' in result.stderr


def test_stat_permission_failure_is_analysis_not_absence(root, monkeypatch):
    from pathlib import Path
    original = Path.stat
    def denied(self, *args, **kwargs):
        if self == root:
            raise PermissionError('SOURCE_STAT_DENIED')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', denied)
    result = run(root, '', '--format', 'json')
    assert result.returncode == 3
    assert 'SOURCE_STAT_DENIED' in json.loads(result.stdout)['error']


def test_full_source_read_loss_differs_from_filtered_empty_and_partial(tmp_path, monkeypatch):
    import builtins
    from pathlib import Path
    from reveal.utils.results import AnalysisCompleteness
    blocked = tmp_path / 'blocked.py'
    blocked.write_text('def hidden(): pass\n', encoding='utf-8')
    original = builtins.open
    def denied(file, *args, **kwargs):
        if isinstance(file, (str, Path)) and Path(file) == blocked:
            raise PermissionError('SOURCE_READ_DENIED')
        return original(file, *args, **kwargs)
    monkeypatch.setattr(builtins, 'open', denied)
    failed = run(tmp_path, '', '--format', 'json')
    assert failed.returncode == 3
    result = json.loads(failed.stdout)
    assert result['total_files'] == 0
    assert AstAdapter.execution_facts(result).completeness is AnalysisCompleteness.FAILED
    (tmp_path / 'healthy.py').write_text('def present(): pass\n', encoding='utf-8')
    partial = run(tmp_path, 'name=absent', '--format', 'json')
    assert partial.returncode == 3
    result = json.loads(partial.stdout)
    assert result['total_files'] == 1 and result['results'] == []
    assert AstAdapter.execution_facts(result).completeness is AnalysisCompleteness.INCOMPLETE


@pytest.mark.parametrize('malformed', [
    {}, {'results': []}, {'total_files': 0, 'total_results': 0, 'displayed_results': 0, 'results': None},
    {'total_files': -1, 'total_results': 0, 'displayed_results': 0, 'results': []},
    {'total_files': 1, 'total_results': 0, 'displayed_results': 1, 'results': [{}]},
])
def test_malformed_success_cannot_be_clean_empty(root, monkeypatch, malformed):
    from reveal.utils.results import ResultBuilder
    monkeypatch.setattr(AstAdapter, 'get_structure', lambda self, **kwargs:
                        ResultBuilder.create('ast_query', self.path, data=malformed))
    result = run(root, '', '--format', 'json')
    assert result.returncode == 3
    assert json.loads(result.stdout)['error']


def test_runtime_invalid_request_code_does_not_reclassify_analysis(root, monkeypatch):
    from reveal.utils.results import ResultBuilder
    monkeypatch.setattr(AstAdapter, 'get_structure', lambda self, **kwargs:
                        ResultBuilder.create('ast_query', self.path, error='body failed',
                                             errors=[{'code': 'invalid_request', 'message': 'body failed'}]))
    result = run(root, '', '--format', 'json')
    assert result.returncode == 3


def test_nul_resource_is_structured_usage_from_library_transport(root):
    from contextlib import redirect_stderr, redirect_stdout
    from io import StringIO
    from reveal.cli.defaults import _default_args
    from reveal.cli.routing.uri import handle_uri
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err), pytest.raises(SystemExit) as failure:
        handle_uri(f'ast://{root}\x00invalid', None, _default_args(format='json'))
    assert failure.value.code == 2
    assert json.loads(out.getvalue())['error']
    assert 'Traceback' not in err.getvalue()


def test_non_nul_preparation_valueerror_is_required_failure(root, monkeypatch):
    def failed(*args):
        raise ValueError('SCOPE_PREPARATION_FAILED')
    monkeypatch.setattr('reveal.utils.exclusions.dispatch_scope', failed)
    result = run(root, '', '--format', 'json')
    assert result.returncode == 3
    assert json.loads(result.stdout)['error'] == 'SCOPE_PREPARATION_FAILED'


def test_missing_path_diagnostic_serializes_backslash_spelling():
    result = _run_reveal_direct('ast://missing_back2338\\absent.py', '--format', 'json')
    assert result.returncode == 2
    answer = json.loads(result.stdout)
    assert answer['error'] == 'Path not found: missing_back2338/absent.py'
