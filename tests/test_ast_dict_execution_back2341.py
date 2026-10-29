"""Dedicated dict modes classify real source loss before presentation."""

import io
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.ast.adapter import AstAdapter
from reveal.utils.results import AnalysisCompleteness, ResultBuilder

MODES = ['dict-heatmap', 'dict-schemas']
SOURCE = ''.join(
    f'def consume_{i}(config):\n    return config["one"] + config["two"] + config["three"]\n'
    for i in range(2))


def run(path, mode, *options):
    return _run_reveal_direct(f'ast://{path}?show={mode}', *options)


def answer(path, mode, *options):
    response = run(path, mode, '--format', 'json', *options)
    return response, json.loads(response.stdout)


@pytest.mark.parametrize('mode', MODES)
def test_genuine_syntax_loss_full_partial_and_restored(tmp_path, mode):
    source = tmp_path / 'broken.py'
    source.write_text(SOURCE, encoding='utf-8')
    healthy, clean = answer(tmp_path, mode)
    assert healthy.returncode == 0 and clean['results']
    source.write_text(SOURCE + '\ndef broken(:\n', encoding='utf-8')
    failed, data = answer(tmp_path, mode)
    assert failed.returncode == 3
    assert data['type'] == 'ast_' + mode.replace('-', '_')
    assert data['results'] == [] and 'confidence' not in data['meta']
    assert data['analysis'] == dict(candidate_files=1, analyzed_files=0, failed_files=1, discovery_failures=0)
    assert AstAdapter.execution_facts(data).completeness is AnalysisCompleteness.FAILED
    (tmp_path / 'context.py').write_text('VALUE = 1\n', encoding='utf-8')
    partial, data = answer(tmp_path, mode)
    assert partial.returncode == 3 and data['results'] == []
    assert AstAdapter.execution_facts(data).completeness is AnalysisCompleteness.INCOMPLETE
    source.write_text(SOURCE, encoding='utf-8')
    restored, data = answer(tmp_path, mode)
    assert restored.returncode == 0 and data['results'] == clean['results']
    assert data['meta']['confidence'] == 1.0 and not data['meta']['warnings']


@pytest.mark.parametrize('mode', MODES)
def test_actual_reader_loss_and_restoration(tmp_path, monkeypatch, mode):
    source = tmp_path / 'source.py'
    source.write_text(SOURCE, encoding='utf-8')
    real_open = io.open
    events = []
    def denied(file, *args, **kwargs):
        if isinstance(file, (str, Path)) and Path(file) == source:
            events.append(file)
            raise PermissionError(13, 'DICT_READER_DENIED', str(source))
        return real_open(file, *args, **kwargs)
    monkeypatch.setattr(io, 'open', denied)
    accessor = getattr(source, '_accessor', None)
    if accessor is not None:
        monkeypatch.setattr(accessor, 'open', denied)
    failed, data = answer(source, mode)
    assert events
    assert failed.returncode == 3
    assert 'confidence' not in data['meta'] and data['results'] == []
    assert 'DICT_READER_DENIED' in json.dumps(data['meta']['warnings'])
    monkeypatch.setattr(io, 'open', real_open)
    if accessor is not None:
        monkeypatch.setattr(accessor, 'open', real_open)
    restored, data = answer(source, mode)
    assert restored.returncode == 0 and data['results']


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('output', ['text', 'grep'])
def test_source_warning_visible_once_and_empty_is_scoped(tmp_path, mode, output):
    (tmp_path / 'broken.py').write_text('def broken(:\n', encoding='utf-8')
    result = run(tmp_path, mode, '--format', output)
    assert result.returncode == 3
    assert (result.stdout + result.stderr).count('required Python dict source file(s) could not be analyzed') == 1
    if output == 'text':
        assert 'analyzed portion' in result.stdout
    else:
        assert result.stdout == ''


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('options', [[], ['--fields', 'results'], ['--head', '0'], ['--max-items', '0']])
def test_partial_loss_precedes_projection(tmp_path, mode, options):
    (tmp_path / 'healthy.py').write_text(SOURCE, encoding='utf-8')
    (tmp_path / 'broken.py').write_text('def broken(:\n', encoding='utf-8')
    response, data = answer(tmp_path, mode, *options)
    assert response.returncode == 3
    assert isinstance(data['results'], list)


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('source', ['VALUE = 1\n', ''])
def test_healthy_zero_is_complete(tmp_path, mode, source):
    (tmp_path / 'healthy.py').write_text(source, encoding='utf-8')
    response, data = answer(tmp_path, mode)
    assert response.returncode == 0 and data['results'] == []
    assert AstAdapter.execution_facts(data).completeness is AnalysisCompleteness.COMPLETE


@pytest.mark.parametrize('query,kind,qualified', [
    ('show=dict-heatmap', 'ast_dict_heatmap', True),
    ('show=dict-schemas&reveal_type=x', 'ast_dict_schemas', True),
    ('show=dict-heatmap&show=functions', 'ast_query', True),
    ('show=functions&show=dict-schemas', 'ast_dict_schemas', True),
    ('show=dict%2Dheatmap', 'ast_query', True),
    ('show=&reveal_type=', 'ast_query', True),
    ('reveal_type=x', 'ast_reveal_type', False),
])
def test_mode_identity_before_construction(tmp_path, query, kind, qualified):
    response = _run_reveal_direct(f'ast://{tmp_path / "absent"}?{query}', '--format', 'json')
    data = json.loads(response.stdout)
    assert response.returncode == (2 if qualified else 1)
    assert data['type'] == (kind if qualified else 'ast')


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('malformed', [
    {}, {'results': [], 'total_results': 0},
    *[{'results': [], 'total_results': 0, 'analysis': proof} for proof in (
        None, [], 'invalid',
        dict(candidate_files=-1, analyzed_files=0, failed_files=0, discovery_failures=0),
        dict(candidate_files='1', analyzed_files=1, failed_files=0, discovery_failures=0))],
    {'results': [], 'total_results': 0, 'analysis': dict(candidate_files=1, analyzed_files=0, failed_files=0, discovery_failures=0)},
    {'results': [], 'total_results': 0, 'analysis': dict(candidate_files=True, analyzed_files=1, failed_files=0, discovery_failures=0)},
])
def test_malformed_required_dict_answer_fails(tmp_path, monkeypatch, mode, malformed):
    monkeypatch.setattr(AstAdapter, 'get_structure', lambda self, **kwargs:
                        ResultBuilder.create('ast_' + mode.replace('-', '_'), self.path, data=malformed))
    response, data = answer(tmp_path, mode)
    assert response.returncode == 3
    assert data['error'] and data['type'] == 'ast_' + mode.replace('-', '_')


@pytest.mark.parametrize('mode', MODES)
def test_requested_artifact_failure_outranks_healthy_dict(tmp_path, mode):
    (tmp_path / 'healthy.py').write_text(SOURCE, encoding='utf-8')
    response = run(tmp_path, mode, '--also-json', str(tmp_path))
    assert response.returncode == 3 and 'Error' in response.stderr


def test_unadopted_type_and_ordinary_siblings(tmp_path):
    (tmp_path / 'broken.py').write_text('def broken(:\n', encoding='utf-8')
    ordinary = _run_reveal_direct(f'ast://{tmp_path}', '--format', 'json')
    legacy = _run_reveal_direct(f'ast://{tmp_path}?reveal_type=absent', '--format', 'json')
    assert ordinary.returncode == 3
    assert legacy.returncode == 0 and json.loads(legacy.stdout)['type'] == 'ast_reveal_type'


@pytest.mark.parametrize('mode', MODES)
def test_invalid_request_and_preparation_failure_keep_mode_identity(tmp_path, mode, monkeypatch):
    invalid = _run_reveal_direct(f'ast://{tmp_path}?show={mode}&limit=-1', '--format', 'json')
    assert invalid.returncode == 2
    assert json.loads(invalid.stdout)['type'] == 'ast_' + mode.replace('-', '_')
    def failed(*args):
        raise ValueError('DICT_PREPARATION_FAILED')
    monkeypatch.setattr('reveal.utils.exclusions.dispatch_scope', failed)
    response, data = answer(tmp_path, mode)
    assert response.returncode == 3 and data['error'] == 'DICT_PREPARATION_FAILED'
    assert data['type'] == 'ast_' + mode.replace('-', '_')


@pytest.mark.parametrize('mode', MODES)
def test_analysis_exception_and_output_failure_keep_their_meaning(tmp_path, mode, monkeypatch):
    (tmp_path / 'healthy.py').write_text(SOURCE, encoding='utf-8')
    original = AstAdapter.get_structure
    def failed(self, **kwargs):
        raise ValueError('DICT_ANALYSIS_FAILED')
    monkeypatch.setattr(AstAdapter, 'get_structure', failed)
    response, data = answer(tmp_path, mode)
    assert response.returncode == 3 and data['error'] == 'DICT_ANALYSIS_FAILED'
    assert data['type'] == 'ast_' + mode.replace('-', '_')
    monkeypatch.setattr(AstAdapter, 'get_structure', original)
    from reveal.adapters.ast.renderer import AstRenderer
    def output_failed(*args, **kwargs):
        raise RuntimeError('DICT_RENDER_FAILED')
    monkeypatch.setattr(AstRenderer, 'render_structure', output_failed)
    response = run(tmp_path, mode)
    assert response.returncode == 3 and 'Requested output failed: DICT_RENDER_FAILED' in response.stderr


@pytest.mark.parametrize('mode', MODES)
def test_optional_error_and_foreign_language_are_advisory(tmp_path, mode, monkeypatch):
    (tmp_path / 'foreign.js').write_text('function example() {}\n', encoding='utf-8')
    original = AstAdapter.get_structure
    def optional(self, **kwargs):
        result = original(self, **kwargs)
        result['meta']['errors'].append({'code': 'optional_detail', 'message': 'unavailable detail'})
        return result
    monkeypatch.setattr(AstAdapter, 'get_structure', optional)
    response, data = answer(tmp_path, mode)
    assert response.returncode == 0 and data['meta']['confidence'] == 1.0
    assert data['meta']['errors'] and data['results'] == []
