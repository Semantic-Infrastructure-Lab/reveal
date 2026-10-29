"""Type evidence uses required source facts before variable or output selection."""
import builtins
import io
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.adapters.ast.adapter import AstAdapter
from reveal.utils.results import AnalysisCompleteness, ResultBuilder

SOURCE = 'def consume(config: dict):\n    return config\n'


def run(path, variable='config', *options):
    return _run_reveal_direct(f'ast://{path}?reveal_type={variable}', *options)


def answer(path, variable='config', *options):
    response = run(path, variable, '--format', 'json', *options)
    return response, json.loads(response.stdout)


@pytest.mark.parametrize('variable', ['config', 'absent'])
def test_genuine_recovery_is_incomplete_even_when_all_sources_recovered(tmp_path, variable):
    source = tmp_path / 'source.py'
    source.write_text(SOURCE, encoding='utf-8')
    healthy, clean = answer(source, variable)
    assert healthy.returncode == 0
    source.write_text(SOURCE + '\ndef broken(:\n', encoding='utf-8')
    partial, data = answer(source, variable)
    assert partial.returncode == 3
    assert data['type'] == 'ast_reveal_type' and data['results'] == clean['results']
    assert data['analysis'] == dict(candidate_files=1, analyzed_files=1, failed_files=0,
                                    recovered_files=1, unsupported_files=0, discovery_failures=0)
    assert AstAdapter.execution_facts(data).completeness is AnalysisCompleteness.INCOMPLETE
    assert 'confidence' not in data['meta']
    source.write_text(SOURCE, encoding='utf-8')
    restored, data = answer(source, variable)
    assert restored.returncode == 0 and data['results'] == clean['results']
    assert data['meta']['confidence'] == 1.0 and not data['meta']['warnings']


def test_actual_reader_loss_full_partial_context_only_and_restored(tmp_path, monkeypatch):
    blocked = tmp_path / 'blocked.py'
    blocked.write_text(SOURCE, encoding='utf-8')
    real_builtin, real_io = builtins.open, io.open
    events = []
    def deny(real):
        def open_file(file, *args, **kwargs):
            if isinstance(file, (str, Path)) and Path(file) == blocked:
                events.append(file)
                raise PermissionError(13, 'TYPE_READER_DENIED', str(blocked))
            return real(file, *args, **kwargs)
        return open_file
    monkeypatch.setattr(builtins, 'open', deny(real_builtin))
    monkeypatch.setattr(io, 'open', deny(real_io))
    accessor = getattr(blocked, '_accessor', None)
    if accessor is not None:
        monkeypatch.setattr(accessor, 'open', deny(real_io))
    failed, data = answer(tmp_path)
    assert events and failed.returncode == 3
    assert data['results'] == [] and 'confidence' not in data['meta']
    assert AstAdapter.execution_facts(data).completeness is AnalysisCompleteness.FAILED
    assert 'TYPE_READER_DENIED' in json.dumps(data['meta']['warnings'])
    (tmp_path / 'context.py').write_text('VALUE = 1\n', encoding='utf-8')
    partial, data = answer(tmp_path)
    assert partial.returncode == 3 and data['results'] == []
    assert AstAdapter.execution_facts(data).completeness is AnalysisCompleteness.INCOMPLETE
    (tmp_path / 'healthy.py').write_text(SOURCE, encoding='utf-8')
    partial, data = answer(tmp_path)
    assert partial.returncode == 3 and data['results']
    monkeypatch.undo()
    restored, data = answer(tmp_path)
    assert restored.returncode == 0 and len(data['results']) == 2


@pytest.mark.parametrize('output', ['text', 'grep'])
@pytest.mark.parametrize('variable', ['config', 'absent'])
def test_recovery_disclosure_visible_once(tmp_path, output, variable):
    (tmp_path / 'source.py').write_text(SOURCE + '\ndef broken(:\n', encoding='utf-8')
    response = run(tmp_path, variable, '--format', output)
    assert response.returncode == 3
    text = response.stdout + response.stderr
    assert text.lower().count('analysis is incomplete') >= 1
    assert text.count('required Python type-evidence source') == 1
    if output == 'grep':
        assert 'incomplete' in response.stderr.lower()


@pytest.mark.parametrize('options', [[], ['--fields', 'results'], ['--head', '0'], ['--max-items', '0']])
def test_recovery_facts_precede_projection_and_cuts(tmp_path, options):
    (tmp_path / 'source.py').write_text(SOURCE + '\ndef broken(:\n', encoding='utf-8')
    response, data = answer(tmp_path, 'config', *options)
    assert response.returncode == 3 and isinstance(data['results'], list)


@pytest.mark.parametrize('source,variable', [('', 'config'), ('VALUE = 1\n', 'absent'), (SOURCE, 'absent')])
def test_healthy_zero_remains_complete(tmp_path, source, variable):
    (tmp_path / 'source.py').write_text(source, encoding='utf-8')
    response, data = answer(tmp_path, variable)
    assert response.returncode == 0 and data['results'] == []
    assert AstAdapter.execution_facts(data).completeness is AnalysisCompleteness.COMPLETE


@pytest.mark.parametrize('query,kind', [
    ('reveal_type=config', 'ast_reveal_type'), ('reveal_type=other&reveal_type=config', 'ast_reveal_type'),
    ('reveal_type=config&reveal_type=', 'ast_query'), ('reveal_type%3Dconfig', 'ast_query'),
    ('show=dict-heatmap&reveal_type=config', 'ast_dict_heatmap'),
])
def test_preconstruction_identity_and_missing_resource(tmp_path, query, kind):
    response = _run_reveal_direct(f'ast://{tmp_path / "absent"}?{query}', '--format', 'json')
    assert response.returncode == 2
    assert json.loads(response.stdout)['type'] == kind


@pytest.mark.parametrize('proof', [None, [], 'invalid', {},
    dict(candidate_files=True, analyzed_files=1, failed_files=0, recovered_files=0, unsupported_files=0, discovery_failures=0),
    dict(candidate_files=1, analyzed_files=0, failed_files=0, recovered_files=0, unsupported_files=0, discovery_failures=0),
    dict(candidate_files=1, analyzed_files=1, failed_files=0, recovered_files=2, unsupported_files=0, discovery_failures=0),
])
def test_malformed_source_proof_cannot_be_empty_success(tmp_path, monkeypatch, proof):
    monkeypatch.setattr(AstAdapter, 'get_structure', lambda self, **kwargs:
        ResultBuilder.create('ast_reveal_type', self.path,
            data={'var_name': 'config', 'total_results': 0, 'results': [], 'analysis': proof}))
    response, data = answer(tmp_path)
    assert response.returncode == 3 and data['error']
    assert data['type'] == 'ast_reveal_type'


@pytest.mark.parametrize('variable', [None, '', 1])
def test_malformed_variable_identity_fails(tmp_path, monkeypatch, variable):
    monkeypatch.setattr(AstAdapter, 'get_structure', lambda self, **kwargs:
        ResultBuilder.create('ast_reveal_type', self.path, data={
            'var_name': variable, 'total_results': 0, 'results': [], 'analysis': dict(
                candidate_files=0, analyzed_files=0, failed_files=0, recovered_files=0,
                unsupported_files=0, discovery_failures=0)}))
    response, data = answer(tmp_path)
    assert response.returncode == 3 and data['error']


def test_unavailable_python_analyzer_is_required_loss(tmp_path, monkeypatch):
    import reveal.registry
    (tmp_path / 'source.py').write_text(SOURCE, encoding='utf-8')
    monkeypatch.setattr(reveal.registry, 'get_analyzer', lambda path: None)
    response, data = answer(tmp_path)
    assert response.returncode == 3 and data['results'] == []
    assert AstAdapter.execution_facts(data).completeness is AnalysisCompleteness.FAILED


def test_validation_api_and_output_failures(tmp_path, monkeypatch):
    (tmp_path / 'source.py').write_text(SOURCE, encoding='utf-8')
    invalid = _run_reveal_direct(f'ast://{tmp_path}?reveal_type=config&limit=-1', '--format', 'json')
    assert invalid.returncode == 2 and json.loads(invalid.stdout)['type'] == 'ast_reveal_type'
    with pytest.raises(ValueError):
        api.query(f'ast://{tmp_path}?reveal_type=config&limit=-1')
    artifact = run(tmp_path, 'config', '--also-json', str(tmp_path))
    assert artifact.returncode == 3
    from reveal.adapters.ast.renderer import AstRenderer
    def fail(*args, **kwargs):
        raise RuntimeError('TYPE_OUTPUT_FAILED')
    monkeypatch.setattr(AstRenderer, 'render_structure', fail)
    output = run(tmp_path)
    assert output.returncode == 3 and 'Requested output failed: TYPE_OUTPUT_FAILED' in output.stderr


def test_foreign_language_and_optional_error_stay_advisory(tmp_path, monkeypatch):
    source = tmp_path / 'source.js'
    source.write_text('const value = 1;\n', encoding='utf-8')
    original = AstAdapter.get_structure
    def optional(self, **kwargs):
        data = original(self, **kwargs)
        data['meta']['errors'].append({'code': 'optional_detail', 'message': 'unavailable detail'})
        return data
    monkeypatch.setattr(AstAdapter, 'get_structure', optional)
    response, data = answer(source)
    assert response.returncode == 0 and data['meta']['confidence'] == 1.0
    assert data['meta']['errors'] and data['analysis']['unsupported_files'] == 1


def test_analysis_exception_decline_and_preparation_identity(tmp_path, monkeypatch):
    from reveal.errors import NotApplicableError
    original = AstAdapter.get_structure
    def fail(self, **kwargs):
        raise ValueError('TYPE_ANALYSIS_FAILED')
    monkeypatch.setattr(AstAdapter, 'get_structure', fail)
    response, data = answer(tmp_path)
    assert response.returncode == 3 and data['error'] == 'TYPE_ANALYSIS_FAILED'
    assert data['type'] == 'ast_reveal_type'
    def decline(self, **kwargs):
        raise NotApplicableError('type evidence does not apply')
    monkeypatch.setattr(AstAdapter, 'get_structure', decline)
    response, data = answer(tmp_path)
    assert response.returncode == 0 and data['applicable'] is False
    assert data['type'] == 'ast_reveal_type'
    monkeypatch.setattr(AstAdapter, 'get_structure', original)
    def preparation(*args):
        raise ValueError('TYPE_PREPARATION_FAILED')
    monkeypatch.setattr('reveal.utils.exclusions.dispatch_scope', preparation)
    response, data = answer(tmp_path)
    assert response.returncode == 3 and data['error'] == 'TYPE_PREPARATION_FAILED'
    assert data['type'] == 'ast_reveal_type'


def test_successful_artifact_equals_json_and_recovered_absence_is_scoped(tmp_path):
    source = tmp_path / 'source.py'
    source.write_text(SOURCE + '\ndef broken(:\n', encoding='utf-8')
    artifact = tmp_path / 'answer.json'
    response = run(source, 'absent', '--also-json', str(artifact))
    assert response.returncode == 3 and artifact.exists()
    data = json.loads(artifact.read_text(encoding='utf-8'))
    assert data['results'] == [] and data['analysis']['recovered_files'] == 1
    assert 'analyzed portion' in response.stdout
    direct, actual = answer(source, 'absent', '--also-json', str(artifact))
    assert direct.returncode == 3 and actual == data
