"""Required dict sources retain read/parse evidence before usage filtering."""
import io
from pathlib import Path

import pytest

from reveal.adapters.ast.adapter import AstAdapter
from reveal.analyzers import _python_dict_usage as usage

pytestmark = pytest.mark.component
SOURCE = 'def read(cfg: dict):\n    return cfg["a"] + cfg["b"] + cfg["c"]\n'


@pytest.mark.parametrize('loss', ['parse', 'read'])
def test_real_source_loss_is_not_a_confident_empty_answer(tmp_path, monkeypatch, loss):
    source = tmp_path / 'source.py'
    source.write_text(SOURCE, encoding='utf-8')
    assert len(usage.collect_dict_analysis(str(source))[0]) == 1
    real_open = io.open
    denied = []

    def reader(file, *args, **kwargs):
        if Path(file).resolve() == source.resolve():
            denied.append(file)
            raise PermissionError(13, 'reader denied', str(file))
        return real_open(file, *args, **kwargs)

    if loss == 'parse':
        source.write_text(SOURCE + 'def broken(\n', encoding='utf-8')
    else:
        monkeypatch.setattr(io, 'open', reader)
    result = AstAdapter(str(source), 'show=dict-heatmap').get_structure()
    assert result['total_results'] == 0
    if loss == 'read':
        assert denied, 'the actual Path.read_text reader must execute'
    assert result['meta'].get('confidence') != 1.0, result['meta']
    assert any(w['code'] == usage.DICT_SOURCE_WARNING_CODE for w in result['meta']['warnings'])


def _collect(path):
    evidence = usage.DictAnalysisEvidence()
    result = usage.collect_dict_analysis(str(path), evidence=evidence)
    assert type(result) is tuple and len(result) == 2
    assert all(type(part) is list for part in result)
    return result, evidence


@pytest.mark.parametrize('loss', ['parse', 'read'])
def test_collector_context_only_loss_and_reader_restoration(tmp_path, monkeypatch, loss):
    context = tmp_path / 'context.pyi'
    context.write_text('Config = dict\nKEY = "a"\n', encoding='utf-8')
    consumer = tmp_path / 'consumer.py'
    consumer.write_text('def read(cfg: Config):\n    return cfg[KEY]\n', encoding='utf-8')
    healthy, facts = _collect(tmp_path)
    assert len(healthy[0]) == 1 and healthy[0][0]['keys'] == ['a']
    assert (facts.candidate_files, facts.analyzed_files, facts.failed_files) == (2, 2, 0)
    real_open = io.open
    denied = []

    def reader(file, *args, **kwargs):
        if Path(file).resolve() == context.resolve():
            denied.append(file)
            raise PermissionError(13, 'reader denied', str(file))
        return real_open(file, *args, **kwargs)

    if loss == 'parse':
        context.write_text('Config = dict\nKEY = "a"\ndef broken(\n', encoding='utf-8')
    else:
        monkeypatch.setattr(io, 'open', reader)
    result, facts = _collect(tmp_path)
    assert result == ([], [])
    assert (facts.candidate_files, facts.analyzed_files, facts.failed_files) == (2, 1, 1)
    assert len(facts.diagnostics) == 1
    diagnostic = facts.diagnostics[0]
    assert diagnostic.file == context.as_posix() and diagnostic.stage == loss
    assert str(context) not in diagnostic.cause
    if loss == 'read':
        assert denied
        monkeypatch.setattr(io, 'open', real_open)
    context.write_text('Config = dict\nKEY = "a"\n', encoding='utf-8')
    restored, facts = _collect(tmp_path)
    assert restored == healthy
    assert (facts.candidate_files, facts.analyzed_files, facts.failed_files) == (2, 2, 0)
    assert facts.diagnostics == []


def test_collector_success_counts_context_without_usages_and_healthy_empty(tmp_path):
    (tmp_path / 'context.py').write_text('Config = dict\nKEY = "a"\n', encoding='utf-8')
    (tmp_path / 'other.js').write_text('let x = 1;\n', encoding='utf-8')
    result, facts = _collect(tmp_path)
    assert result == ([], [])
    assert (facts.candidate_files, facts.analyzed_files, facts.failed_files) == (1, 1, 0)
    assert facts.diagnostics == []
    assert usage.collect_dict_analysis(str(tmp_path)) == result


def test_collector_caps_diagnostics_but_counts_every_failed_source(tmp_path):
    for number in range(8):
        (tmp_path / f'broken_{number}.py').write_text('def broken(\n', encoding='utf-8')
    result, facts = _collect(tmp_path)
    assert result == ([], [])
    assert (facts.candidate_files, facts.analyzed_files, facts.failed_files) == (8, 0, 8)
    assert len(facts.diagnostics) == 5
    assert all(d.stage == 'parse' and 'SyntaxError' in d.cause for d in facts.diagnostics)
    assert all(str(tmp_path) not in d.cause for d in facts.diagnostics)


def test_parser_native_optional_module_and_serialized_failure_path(monkeypatch):
    monkeypatch.setattr(Path, 'read_text', lambda *a, **kw: 'def broken(\n')
    facts = usage.DictAnalysisEvidence()
    assert usage.parse_file('pkg\\broken.py', evidence=facts) is None
    assert usage.parse_file('pkg\\broken.py') is None
    assert facts.failed_files == 1 and facts.diagnostics[0].file == 'pkg/broken.py'
    assert facts.diagnostics[0].stage == 'parse'
