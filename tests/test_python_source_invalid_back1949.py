"""Repeated BOMs are invalid Python file source, even when TS accepts them.

File-facing disclosure does not change direct parser normalization or best-effort
element extraction. Valid files must retain their existing parse workload.
"""
import ast
import json

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.ast import analysis
from reveal.analyzers.python import PythonAnalyzer
from reveal.treesitter import TreeSitterAnalyzer
from reveal.utils.parse_audit import capture_parses
from reveal.utils.pyparse import parse_python
from reveal.utils.results import outcome_of

pytestmark = pytest.mark.component

BOM = b'\xef\xbb\xbf'
CLEAN = 'é = "λ"\ndef café():\n    return "\ufeffπ"\n'
BARE = ('é = "λ"\ndef café():\n    try:\n        return "π"\n'
        '    except:\n        return None\n')
REASON = 'invalid Python source: unexpected U+FEFF after UTF-8 BOM (line 1:1)'


def _write(tmp_path, count=2, eol='\n', source=CLEAN):
    path = tmp_path / 'app.py'
    path.write_bytes(BOM * count + source.replace('\n', eol).encode('utf-8'))
    return path


@pytest.mark.parametrize('eol', ['\n', '\r\n'], ids=['lf', 'crlf'])
def test_repeated_bom_structure_is_failed_source_not_recovered(tmp_path, eol):
    path = _write(tmp_path, eol=eol)
    analyzer = PythonAnalyzer(str(path))
    for _ in range(2):
        structure = analyzer.get_structure()
        assert outcome_of(structure) == 'failed'
        assert structure['error'] == REASON
        assert structure['_has_errors'] is True
        assert structure['type'] == 'python_structure'
    assert analyzer.first_parse_error_position() == (1, 1)


@pytest.mark.parametrize('fmt', ['json', 'text'])
def test_file_structure_discloses_source_invalidity(tmp_path, fmt):
    result = _run_reveal_direct(_write(tmp_path), '--format', fmt)
    assert result.returncode == 1
    if fmt == 'json':
        payload = json.loads(result.stdout)
        assert payload['error'] == REASON
        assert 'parse_recovered' not in payload['meta']
    else:
        assert REASON in result.stdout + result.stderr
    assert 'Parse recovered' not in result.stdout + result.stderr
    assert 'infrastructure_failure' not in result.stdout
    assert 'network-requirements' not in result.stdout + result.stderr


@pytest.mark.parametrize('directory', [False, True], ids=['file', 'directory'])
@pytest.mark.parametrize('selected', [True, False], ids=['b001', 'default'])
@pytest.mark.parametrize('source,findings', [(CLEAN, []), (BARE, [('B001', 5, 5)])],
                         ids=['clean', 'finding'])
def test_checks_disclose_source_invalidity_and_preserve_partial_findings(
        tmp_path, monkeypatch, directory, selected, source, findings):
    monkeypatch.chdir(tmp_path)
    path = _write(tmp_path, source=source)
    target = tmp_path if directory else path
    flags = ['--select', 'B001'] if selected else []
    result = _run_reveal_direct('check', target, *flags, '--format', 'json')
    assert result.returncode == 3
    payload = json.loads(result.stdout)
    if directory:
        assert payload['summary']['files_degraded'] == 1
        assert payload['summary']['files_errored'] == 0
        (entry,) = payload['files']
        assert entry['status'] == 'warning'
        assert REASON in entry['detail']
    else:
        entry = payload
        assert REASON in entry['warning']
    assert [(d['rule_code'], d['line'], d['column']) for d in entry['detections']] == findings
    text = _run_reveal_direct('check', target, *flags)
    assert text.returncode == 3
    assert REASON in text.stdout
    assert '✅ No issues found' not in text.stdout
    assert 'Parse recovered' not in text.stdout


def test_invalidity_does_not_depend_on_structure_cache_or_build_a_diagnostic_tree(
        tmp_path, monkeypatch):
    path = _write(tmp_path)
    calls = []

    def cached_structure(self, **kwargs):
        calls.append(self.path)
        return {'functions': [{'name': 'stale', 'line': 1, 'line_end': 1}]}

    monkeypatch.setattr(TreeSitterAnalyzer, 'get_structure', cached_structure)
    for _ in range(2):
        analyzer = PythonAnalyzer(str(path))
        with capture_parses(tmp_path) as capture:
            assert outcome_of(analyzer.get_structure()) == 'failed'
            assert analyzer.first_parse_error_position() == (1, 1)
        assert capture.events == []
        assert analyzer._tree_parsed is False
    assert calls == []


@pytest.mark.parametrize('count', [0, 1])
@pytest.mark.parametrize('eol', ['\n', '\r\n'], ids=['lf', 'crlf'])
def test_valid_source_preserves_unicode_extraction_and_parse_work(tmp_path, count, eol):
    path = _write(tmp_path, count=count, eol=eol)
    analyzer = PythonAnalyzer(str(path))
    with capture_parses(tmp_path) as capture:
        structure = analyzer.get_structure()
        assert analyzer.get_structure() == structure
    assert outcome_of(structure) == 'ok'
    assert [(f['name'], f['line'], f['line_end']) for f in structure['functions']] == [('café', 2, 3)]
    assert not structure.get('_has_errors')
    assert [(e.parser, e.domain) for e in capture.events if e.event == 'request'] == [
        ('treesitter:python', 'fullsource')]
    assert len([e for e in capture.events if e.event == 'artifact']) == 1
    with capture_parses(tmp_path) as checked_capture:
        checked = _run_reveal_direct('check', path, '--select', 'B001', '--format', 'json')
    assert checked.returncode == 0
    assert json.loads(checked.stdout)['detections'] == []
    assert [(e.parser, e.domain) for e in checked_capture.events
            if e.event == 'request' and e.scope == 'target'] == [('python.ast', 'fullsource')]
    assert len([e for e in checked_capture.events
                if e.event == 'artifact' and e.scope == 'target']) == 1
    extracted = _run_reveal_direct(path, 'café', '--format', 'json')
    assert extracted.returncode == 0
    assert json.loads(extracted.stdout) == {
        'name': 'café', 'line_start': 2, 'line_end': 3,
        'source': 'def café():\n    return "\ufeffπ"'}


def test_repeated_bom_extraction_remains_best_effort(tmp_path):
    result = _run_reveal_direct(_write(tmp_path), 'café', '--format', 'json')
    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        'name': 'café', 'line_start': 2, 'line_end': 3,
        'source': 'def café():\n    return "\ufeffπ"'}


@pytest.mark.parametrize('count', [0, 1])
def test_supported_compatibility_and_direct_parser_semantics_stay_owned(tmp_path, count):
    source = 'try:\n    pass\nexcept ValueError, TypeError:\n    pass\n'
    analyzer = PythonAnalyzer(str(_write(tmp_path, count=count, source=source)))
    tree = parse_python(analyzer.content, analyzer.path)
    assert isinstance(tree.body[0], ast.Try)
    assert isinstance(tree.body[0].handlers[0].type, ast.Tuple)
    assert isinstance(parse_python('\ufeff' + CLEAN), ast.Module)
    with pytest.raises(SyntaxError, match='U\\+FEFF'):
        parse_python('\ufeff\ufeff' + CLEAN)


def test_ordinary_syntax_recovery_remains_recovery(tmp_path):
    path = _write(tmp_path, count=1, source='def ok():\n    pass\ndef broken(:\n')
    structure = PythonAnalyzer(str(path)).get_structure()
    assert structure['_has_errors'] is True
    assert outcome_of(structure) == 'ok'
    shown = _run_reveal_direct(path, '--format', 'json')
    assert json.loads(shown.stdout)['meta']['parse_recovered'] is True
    checked = _run_reveal_direct('check', path, '--select', 'B001', '--format', 'json')
    assert checked.returncode == 3
    warning = json.loads(checked.stdout)['warning']
    assert 'did not parse cleanly' in warning
    assert 'UTF-8 BOM' not in warning


@pytest.mark.parametrize('outline', [False, True])
def test_ast_failed_source_uses_omission_channel_and_releases_buffers(tmp_path, monkeypatch, outline):
    path = _write(tmp_path)
    released = []
    original_release = analysis._release_buffers

    def release(analyzer):
        original_release(analyzer)
        released.append((analyzer.content, analyzer.lines, analyzer._content_bytes))

    monkeypatch.setattr(analysis, '_release_buffers', release)
    assert analysis.analyze_file_outcome(str(path), outline=outline) == (None, REASON)
    assert released == [('', [], None)]


@pytest.mark.parametrize('query', ['', '?name=café'])
def test_ast_query_discloses_repeated_bom_as_failure_not_recovery(tmp_path, query):
    path = _write(tmp_path)
    result = _run_reveal_direct(f'ast://{tmp_path}{query}', '--format', 'json')
    payload = json.loads(result.stdout)
    warnings = payload['meta']['warnings']
    (warning,) = [w for w in warnings if w['type'] == 'analysis_failed']
    assert warning['count'] == 1
    assert warning['files'] == [path.as_posix()]
    assert not [w for w in warnings if w['type'] == 'parse_recovered']
    assert REASON in result.stderr


def test_explicit_xml_failure_is_not_flattened_as_recovery(tmp_path):
    path = tmp_path / 'broken.xml'
    path.write_text('<root>', encoding='utf-8')
    structure, failure = analysis.analyze_file_outcome(str(path))
    assert structure is None
    assert failure == 'XML parse error: no element found: line 1, column 6'


def test_ast_ordinary_recovery_keeps_surviving_elements(tmp_path):
    path = _write(tmp_path, count=0, source='def ok():\n    pass\ndef broken(:\n')
    structure, failure = analysis.analyze_file_outcome(str(path))
    assert failure is None
    assert structure['parse_recovered'] is True
    assert [(e['name'], e['line']) for e in structure['elements']] == [('ok', 1), ('broken', 3)]
