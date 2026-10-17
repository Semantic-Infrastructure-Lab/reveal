"""Trace retains typed collection evidence before indexing without migrating exits."""
import copy
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.ast import analysis
from reveal.adapters.trace import TraceAdapter, TraceRenderer, _build_trace, _render_trace


@pytest.fixture
def tree(tmp_path):
    (tmp_path/'ok.py').write_text('def main():\n    helper()\n    external_api()\n\ndef helper():\n    pass\n', encoding='utf-8')
    return tmp_path


def render(report, renderer=_render_trace):
    stream = StringIO()
    with patch('sys.stdout', stream):
        renderer(report)
    return stream.getvalue()


def typed(report, kind):
    return [entry for entry in report.get('meta', {}).get('warnings', []) if entry.get('type') == kind]


def test_actual_recovery_retains_exact_typed_warning_and_frames(tmp_path):
    (tmp_path/'app.ts').write_text('export function main() { const x = ; helper(); }\nexport function helper() { return 1; }\n', encoding='utf-8')
    structures = analysis.collect_structures(str(tmp_path))
    expected = analysis.parse_recovered_warning(structures)
    assert expected and expected['count'] == 1
    report = TraceAdapter(str(tmp_path), 'from=main').get_structure()
    assert typed(report, 'parse_recovered') == [expected]
    assert report['frames'][0]['resolved'] is True
    assert any(frame['name'] == 'helper' for frame in report['frames'])
    assert render(report).count(expected['message']) == 1


@pytest.fixture
def failed_tree(tree, monkeypatch):
    for i in range(7):
        (tree/f'bad{i}.py').write_text('def bad():\n    pass\n', encoding='utf-8')
    original = analysis.create_element_dict
    def fail(path, *args, **kwargs):
        if Path(path).name.startswith('bad'):
            raise OSError('required analyzer unavailable')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(analysis, 'create_element_dict', fail)
    return tree


def test_actual_failed_collection_keeps_exact_caps_once_and_reuse(failed_tree):
    structures = analysis.collect_structures(str(failed_tree))
    expected = analysis.analysis_skipped_warning(structures.skipped, None, 'their functions are missing from the trace')
    adapter = TraceAdapter(str(failed_tree), 'from=main')
    for _ in range(2):
        report = adapter.get_structure()
        assert typed(report, 'analysis_failed') == [expected]
        assert expected['count'] == 7 and len(expected['files']) == 5
        assert report['warnings'].count(expected['message']) == 1
        assert not report['meta'].get('errors')  # Known skipped files are not malformed evidence.
        assert report['frames'][0]['resolved']
        assert render(report).count(expected['message']) == 1


@pytest.mark.parametrize('kind', ['collection', 'skipped_missing', 'skipped_shape', 'skipped_entry',
    'file_row', 'file_name', 'elements_missing', 'elements_shape', 'element_row',
    'callable_name', 'callable_line', 'callable_calls', 'call_item'])
def test_malformed_evidence_is_attributed_without_losing_valid_frames(tree, monkeypatch, kind):
    structures = analysis.collect_structures(str(tree))
    bad = copy.deepcopy(structures[0])
    if kind == 'collection':
        malformed = None
    elif kind == 'skipped_missing':
        malformed = list(structures)
    else:
        malformed = analysis.StructureList(copy.deepcopy(structures))
        if kind == 'skipped_shape':
            malformed.skipped = None
        elif kind == 'skipped_entry':
            malformed.skipped = [('bad.py', 'OSError: known failure'), ('unusable',)]
        elif kind == 'file_row':
            malformed.append(None)
        elif kind == 'file_name':
            bad['file'] = True
            malformed.append(bad)
        elif kind == 'elements_missing':
            bad.pop('elements')
            malformed.append(bad)
        elif kind == 'elements_shape':
            bad['elements'] = None
            malformed.append(bad)
        else:
            row = copy.deepcopy(bad['elements'][0])
            if kind == 'element_row':
                row = None
            elif kind == 'callable_name':
                row['name'] = None
            elif kind == 'callable_line':
                row['line'] = True
            elif kind == 'callable_calls':
                row['calls'] = None
            else:
                row['calls'] = [None]
            malformed[0]['elements'].append(row)
    calls = []
    def collect(path):
        calls.append(path)
        return malformed
    monkeypatch.setattr(analysis, 'collect_structures', collect)
    report = TraceAdapter(str(tree), 'from=main').get_structure()
    assert len(calls) == 1
    errors = report['meta']['errors']
    assert errors and all(error['code'] == 'E_COMPOSE' for error in errors)
    assert all('collect_structures' in error['message'] and error['file'] for error in errors)
    if kind not in ('collection',):
        assert report['frames'][0]['resolved'], report
    if kind == 'skipped_entry':
        assert typed(report, 'analysis_failed')[0]['count'] == 1


@pytest.mark.parametrize('empty_file', [False, True])
def test_valid_empty_collection_does_not_fabricate_failure(tree, monkeypatch, empty_file):
    structures = analysis.StructureList([{'file': str(tree/'empty.py'), 'elements': []}] if empty_file else [])
    monkeypatch.setattr(analysis, 'collect_structures', lambda path: structures)
    report = TraceAdapter(str(tree), 'from=absent').get_structure()
    assert not report.get('meta', {}).get('errors')
    assert not report.get('meta', {}).get('warnings')
    assert report['frames'][0]['resolved'] is False


def test_renderer_deduplicates_exact_messages_only_and_never_mutates_json(tree):
    report = TraceAdapter(str(tree), 'from=main').get_structure()
    report['warnings'] = ['mirrored warning', 'legacy warning']
    report['meta'] = {'warnings': [
        {'type': 'analysis_failed', 'message': 'mirrored warning'},
        {'type': 'analysis_failed', 'message': 'nonmirrored required warning'},
        {'type': 'custom', 'message': 'unknown warning'},
    ], 'errors': [{'code': 'E_COMPOSE', 'message': 'required error'}]}
    before = copy.deepcopy(report)
    for renderer in (_render_trace, TraceRenderer.render_structure):
        output = render(report, renderer)
        for message in ('mirrored warning', 'legacy warning', 'nonmirrored required warning', 'unknown warning', 'required error'):
            assert output.count(message) == 1
        assert report == before


@pytest.mark.parametrize('transport', ['cli', 'uri'])
def test_canonical_text_prints_typed_diagnostics_once_with_legacy_exit(failed_tree, transport):
    request = ['trace', str(failed_tree), '--from', 'main'] if transport == 'cli' else ['trace://'+str(failed_tree)+'?from=main']
    result = run(*request)
    assert result.returncode == 0
    assert result.stdout.count('7 file(s) could not be analyzed') == 1


@pytest.mark.parametrize('transport,expected', [('cli', 1), ('uri', 0)])
def test_unknown_root_keeps_legacy_exit_policy(tree, transport, expected):
    request = ['trace', str(tree), '--from', 'absent'] if transport == 'cli' else ['trace://'+str(tree)+'?from=absent']
    assert run(*request, '--format', 'json').returncode == expected


def test_collection_raise_keeps_existing_exception_boundary(tree, monkeypatch):
    def fail(path):
        raise PermissionError('whole collection inaccessible')
    monkeypatch.setattr(analysis, 'collect_structures', fail)
    with pytest.raises(PermissionError, match='whole collection inaccessible'):
        _build_trace(str(tree), 'main', 2)


def test_recovered_evidence_does_not_contaminate_reused_adapter(tmp_path):
    source = tmp_path/'app.ts'
    source.write_text('export function main() { const x = ; }\n', encoding='utf-8')
    adapter = TraceAdapter(str(tmp_path), 'from=main')
    assert typed(adapter.get_structure(), 'parse_recovered')
    source.write_text('export function main() { return 1; }\n', encoding='utf-8')
    assert not typed(adapter.get_structure(), 'parse_recovered')
