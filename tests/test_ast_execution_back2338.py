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
