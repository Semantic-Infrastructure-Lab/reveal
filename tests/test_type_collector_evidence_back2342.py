"""Required Python type sources disclose omissions and recovered uncertainty."""
import builtins
from pathlib import Path

import pytest

from reveal.adapters.ast.adapter import AstAdapter
from reveal.adapters.ast import nav_reveal_type as nav
from reveal.analyzers.python import PythonAnalyzer
from reveal.core.treesitter_compat import error_node_spans, tree_has_recovery_artifacts, tree_root

pytestmark = pytest.mark.component
SOURCE = 'def consume(target: dict):\n    return target\n'


@pytest.mark.parametrize('loss', ['recovery', 'read'])
def test_real_type_source_loss_has_no_unjustified_confidence(tmp_path, monkeypatch, loss):
    path = tmp_path / 'source.py'
    path.write_text(SOURCE, encoding='utf-8')
    assert len(nav.collect_type_evidence(str(path), 'target')) == 1
    real_open = builtins.open
    denied = []

    def reader(file, *args, **kwargs):
        if Path(file).resolve() == path.resolve():
            denied.append(file)
            raise PermissionError(13, 'reader denied', str(file))
        return real_open(file, *args, **kwargs)

    if loss == 'recovery':
        path.write_text(SOURCE + 'def broken(\n', encoding='utf-8')
        tree = PythonAnalyzer(str(path)).tree
        assert tree_has_recovery_artifacts(tree) and error_node_spans(tree_root(tree))
    else:
        monkeypatch.setattr(builtins, 'open', reader)
    result = AstAdapter(str(path), 'reveal_type=target').get_structure()
    assert result['total_results'] == (1 if loss == 'recovery' else 0)
    if loss == 'read':
        assert denied
        monkeypatch.setattr(builtins, 'open', real_open)
        assert len(nav.collect_type_evidence(str(path), 'target')) == 1
    assert result['meta'].get('confidence') != 1.0, result['meta']
    assert any(w['code'] == nav.TYPE_SOURCE_WARNING_CODE for w in result['meta']['warnings'])


def _collect(path, variable='target'):
    facts = nav.TypeAnalysisEvidence()
    rows = nav.collect_type_evidence(str(path), variable, source_evidence=facts)
    assert type(rows) is list
    assert facts.candidate_files == facts.analyzed_files + facts.failed_files
    assert facts.recovered_files <= facts.analyzed_files
    return rows, facts


@pytest.mark.parametrize('source,errors', [(SOURCE + 'def broken(\n', True), ('def foo(:\n    pass\n', False)])
@pytest.mark.parametrize('variable', ['target', 'absent'])
def test_actual_error_and_missing_recovery_before_variable_filter(tmp_path, source, errors, variable):
    path = tmp_path / 'source.pyi'
    path.write_text(source, encoding='utf-8')
    tree = PythonAnalyzer(str(path)).tree
    assert tree_has_recovery_artifacts(tree)
    assert bool(error_node_spans(tree_root(tree))) == errors
    rows, facts = _collect(path, variable)
    assert len(rows) == (1 if errors and variable == 'target' else 0)
    assert (facts.candidate_files, facts.analyzed_files, facts.failed_files, facts.recovered_files) == (1, 1, 0, 1)
    assert facts.diagnostics[0].stage == 'recovery'
    assert facts.diagnostics[0].file == path.as_posix()


def test_required_read_loss_with_healthy_zero_sibling_and_restoration(tmp_path, monkeypatch):
    bad = tmp_path / 'source.py'
    bad.write_text(SOURCE, encoding='utf-8')
    (tmp_path / 'empty.pyi').write_text('CONSTANT = 1\n', encoding='utf-8')
    healthy, _ = _collect(tmp_path)
    real_open = builtins.open
    denied = []

    def reader(file, *args, **kwargs):
        if Path(file).resolve() == bad.resolve():
            denied.append(file)
            raise PermissionError(13, 'reader denied', str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, 'open', reader)
    rows, facts = _collect(tmp_path)
    assert denied and rows == []
    assert (facts.candidate_files, facts.analyzed_files, facts.failed_files) == (2, 1, 1)
    assert facts.diagnostics[0].stage == 'read'
    assert str(bad) not in facts.diagnostics[0].cause
    monkeypatch.setattr(builtins, 'open', real_open)
    restored, facts = _collect(tmp_path)
    assert restored == healthy
    assert (facts.candidate_files, facts.analyzed_files, facts.failed_files) == (2, 2, 0)
    assert facts.diagnostics == []


def test_healthy_empty_directory_scope_and_native_default_calls(tmp_path, monkeypatch):
    (tmp_path / 'empty.py').write_text('CONSTANT = 1\n', encoding='utf-8')
    (tmp_path / 'empty.pyi').write_text('name: str\n', encoding='utf-8')
    (tmp_path / 'ignored.js').write_text('target = 1;\n', encoding='utf-8')
    rows, facts = _collect(tmp_path)
    assert rows == [] and facts.candidate_files == facts.analyzed_files == 2
    assert facts.unsupported_files == facts.recovered_files == facts.failed_files == 0
    calls = []
    original = nav._scan_file

    def positional(file, variable, output):
        calls.append(file)
        return original(file, variable, output)

    monkeypatch.setattr(nav, '_scan_file', positional)
    assert nav.collect_type_evidence(str(tmp_path), 'absent') == []
    assert len(calls) == 2


def test_actual_grammar_acquisition_failure_then_unchanged_source_restoration(tmp_path, monkeypatch):
    import tree_sitter_language_pack as pack
    import reveal.core.treesitter_parse as parse
    import reveal.treesitter as treesitter
    path = tmp_path / 'source.py'
    path.write_text(SOURCE, encoding='utf-8')
    parse._parse_recent.cache_clear()
    treesitter._get_parse_cache().clear()
    real_parser = pack.get_parser
    attempts = []

    def unavailable(language):
        attempts.append(language)
        raise RuntimeError('grammar unavailable fixture')

    monkeypatch.setattr(pack, 'get_parser', unavailable)
    rows, facts = _collect(path)
    assert attempts and rows == []
    assert (facts.candidate_files, facts.analyzed_files, facts.failed_files) == (1, 0, 1)
    assert facts.diagnostics[0].stage == 'parse'
    assert str(path) not in facts.diagnostics[0].cause
    monkeypatch.setattr(pack, 'get_parser', real_parser)
    rows, facts = _collect(path)
    assert len(rows) == 1 and facts.analyzed_files == 1 and facts.failed_files == 0
    assert facts.diagnostics == []


@pytest.mark.parametrize('case', ['analyzer', 'tree'])
def test_unavailable_analyzer_and_missing_tree_feature_controls(tmp_path, monkeypatch, case):
    import reveal.registry as registry
    path = tmp_path / 'source.py'
    path.write_text(SOURCE, encoding='utf-8')

    class NoTree:
        def __init__(self, path):
            self.parse_error = f'private absolute filename: {path}'

        @property
        def tree(self):
            calls.append('tree')
            return None

    calls = []
    monkeypatch.setattr(registry, 'get_analyzer', lambda path: None if case == 'analyzer' else NoTree)
    rows, facts = _collect(path)
    assert rows == [] and facts.failed_files == facts.candidate_files == 1
    assert facts.diagnostics[0].stage == ('analyzer' if case == 'analyzer' else 'parse')
    assert calls == ([] if case == 'analyzer' else ['tree'])
    assert str(path) not in facts.diagnostics[0].cause


@pytest.mark.parametrize('suffix,source,count', [('.js', 'target = 1;\n', 0),
                                              ('.txt', '#!/usr/bin/env python\n' + SOURCE, 1)])
def test_nonpython_single_file_preserves_observations_outside_required_counts(tmp_path, suffix, source, count):
    path = tmp_path / ('source' + suffix)
    path.write_text(source, encoding='utf-8')
    original = nav.collect_type_evidence(str(path), 'target')
    assert len(original) == count
    rows, facts = _collect(path)
    assert rows == original
    assert facts.unsupported_files == 1
    assert facts.candidate_files == facts.analyzed_files == facts.failed_files == facts.recovered_files == 0
    assert facts.diagnostics == []


def test_diagnostic_cap_totals_and_observation_path_serialization(tmp_path, monkeypatch):
    import reveal.registry as registry
    for number in range(8):
        (tmp_path / f'source_{number}.py').write_text(SOURCE + 'def broken(\n', encoding='utf-8')
    _, facts = _collect(tmp_path)
    assert facts.analyzed_files == facts.recovered_files == 8
    assert len(facts.diagnostics) == 5
    assert all(str(tmp_path) not in diagnostic.cause for diagnostic in facts.diagnostics)
    real_analyzer = PythonAnalyzer(str(tmp_path / 'source_0.py'))
    monkeypatch.setattr(registry, 'get_analyzer', lambda path: lambda path: real_analyzer)
    facts = nav.TypeAnalysisEvidence()
    rows = []
    nav._scan_file('pkg\\source.py', 'target', rows, source_evidence=facts)
    assert rows[0]['file'] == facts.diagnostics[0].file == 'pkg/source.py'


def test_nonpython_unavailable_analyzer_stays_advisory(tmp_path, monkeypatch):
    import reveal.registry as registry
    path = tmp_path / 'source.data'
    path.write_text('content\n', encoding='utf-8')
    monkeypatch.setattr(registry, 'get_analyzer', lambda path: None)
    rows, facts = _collect(path)
    assert rows == [] and facts.unsupported_files == 1
    assert facts.candidate_files == facts.failed_files == 0 and facts.diagnostics == []


def test_one_source_walk_and_one_tree_property_read(tmp_path, monkeypatch):
    import reveal.registry as registry
    path = tmp_path / 'source.py'
    path.write_text(SOURCE, encoding='utf-8')
    analyzer = PythonAnalyzer(str(path))
    tree = analyzer.tree
    counts = {'walk': 0, 'tree': 0}
    walk = nav._walk_code_files

    def files(*args, **kwargs):
        counts['walk'] += 1
        return walk(*args, **kwargs)

    class SingleTree:
        _get_node_text = analyzer._get_node_text

        def __init__(self, path):
            pass

        @property
        def tree(self):
            counts['tree'] += 1
            return tree

    monkeypatch.setattr(nav, '_walk_code_files', files)
    monkeypatch.setattr(registry, 'get_analyzer', lambda path: SingleTree)
    rows, facts = _collect(tmp_path)
    assert len(rows) == 1 and facts.analyzed_files == 1
    assert counts == {'walk': 1, 'tree': 1}
