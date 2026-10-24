"""Required Calls input loss remains visible through existing consumer entrypoints."""

import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.ast.analysis import collect_structures, traversal_failed_warning
from reveal.adapters.calls import CallsAdapter
from reveal.adapters.calls import index as calls_index
from reveal.adapters.calls.adapter import CallsRenderer
from reveal.adapters.calls.confidence import build_meta
from reveal.adapters.calls.renderer import render_calls_structure
from reveal.utils.results import ResultBuilder


QUERIES = ('target=target', 'callees=visible', 'root=visible',
           'uncalled', 'rank=callers', 'modules')


def make_tree(root):
    root.mkdir()
    child = root / 'included_child'
    child.mkdir()
    (root / 'visible.py').write_text(
        'def visible():\n    return target()\n\ndef target():\n    return 1\n', encoding='utf-8')
    (child / 'hidden.py').write_text('def hidden():\n    return target()\n', encoding='utf-8')
    return child


def deny_child(monkeypatch, child):
    real = os.scandir

    def scandir(path):
        if Path(path) == child:
            raise PermissionError(13, 'controlled included child loss', str(child))
        return real(path)

    monkeypatch.setattr(os, 'scandir', scandir)


def loss_warning(result):
    return [w for w in result['meta']['warnings'] if w.get('type') == 'analysis_incomplete']


@pytest.mark.parametrize('query', QUERIES)
@pytest.mark.parametrize('empty', [False, True])
def test_actual_traversal_loss_reaches_all_query_envelopes(tmp_path, monkeypatch, query, empty):
    root = tmp_path / 'affected'
    child = make_tree(root)
    if empty:
        (root / 'visible.py').unlink()
    deny_child(monkeypatch, child)
    result = CallsAdapter(str(root), query).get_structure()
    (warning,) = loss_warning(result)
    assert warning['count'] == 1
    assert warning['unit'] == 'directories'
    assert warning['directories'] == ['included_child']
    assert 'PermissionError' in warning['message']
    assert 'missing file population is unknown' in warning['message']
    assert 'confidence' not in result['meta']
    assert result['meta']['parse_mode'] == 'tree_sitter_partial'
    assert 'analysis_traversal_failures' not in result
    assert 'analysis_skipped' not in result
    if query == 'target=target' and not empty:
        assert result['total_callers'] == 1
    if query == 'uncalled':
        heuristic = next(w['message'] for w in result['meta']['warnings'] if w.get('code') == 'W-CALLS-5')
        assert 'confidence above' not in heuristic
        assert 'not proof of dead code' in heuristic


@pytest.mark.parametrize('query', QUERIES)
def test_healthy_sibling_and_repaired_adapter_retain_clean_metadata(tmp_path, monkeypatch, query):
    root = tmp_path / 'affected'
    child = make_tree(root)
    sibling = tmp_path / 'sibling'
    make_tree(sibling)
    adapter = CallsAdapter(str(root), query)
    before = CallsAdapter(str(sibling), query).get_structure()
    with monkeypatch.context() as context:
        deny_child(context, child)
        adapter.get_structure()
        assert CallsAdapter(str(sibling), query).get_structure() == before
    repaired = adapter.get_structure()
    assert not loss_warning(repaired)
    assert repaired['meta']['parse_mode'] == 'tree_sitter_full'
    # ?modules' edges are imports' (BACK-1054 slice S5): its rule is edge_rule, not calls' extraction estimate.
    assert isinstance(repaired['meta']['confidence'], float) if query != 'modules' else 'confidence' not in repaired['meta']


def test_unknown_directory_event_with_zero_identified_directories_is_still_loss(tmp_path, monkeypatch):
    root = tmp_path / 'affected'
    make_tree(root)
    structures = collect_structures(str(root))
    structures.traversal_failures = [(None, 'OSError: unknown enumeration location')]
    monkeypatch.setattr(calls_index, 'collect_structures', lambda *a, **k: structures)
    result = CallsAdapter(str(root), 'callees=visible').get_structure()
    (warning,) = loss_warning(result)
    assert warning['count'] == 0
    assert warning['unknown_directory_events'] == 1
    assert 'confidence' not in result['meta']


def test_existing_file_loss_withholds_confidence_through_builder(tmp_path):
    result = ResultBuilder.create(
        result_type='calls_query', source=str(tmp_path), contract_version='1.1',
        data={}, **build_meta(str(tmp_path), skipped=[('lost.py', 'OSError: lost input')]))
    assert 'confidence' not in result['meta']
    assert result['meta']['parse_mode'] == 'tree_sitter_partial'
    assert any(w.get('type') == 'analysis_failed' for w in result['meta']['warnings'])


@pytest.mark.parametrize('query', QUERIES)
@pytest.mark.parametrize('empty', [False, True])
def test_text_required_loss_warning_is_visible_once(tmp_path, capsys, query, empty):
    root = tmp_path / 'source'
    make_tree(root)
    if empty:
        (root / 'visible.py').unlink()
        (root / 'included_child' / 'hidden.py').unlink()
    result = CallsAdapter(str(root), query).get_structure()
    warning = traversal_failed_warning([(str(root / 'included_child'), 'PermissionError: controlled loss')], root)
    result['meta']['warnings'].append(warning)
    render_calls_structure(result, 'text')
    captured = capsys.readouterr()
    assert (captured.out + captured.err).count(warning['message']) == 1


@pytest.mark.parametrize('query', ['target=target', 'root=visible', 'modules'])
@pytest.mark.parametrize('query_override', [False, True])
def test_dot_warning_uses_stderr_and_preserves_graph_stdout(tmp_path, capsys, query, query_override):
    root = tmp_path / 'source'
    make_tree(root)
    result = CallsAdapter(str(root), query + ('&format=dot' if query_override else '')).get_structure()
    warning = traversal_failed_warning([(None, 'OSError: controlled loss')], root)
    result['meta']['warnings'].append(warning)
    CallsRenderer.render_structure(result, 'json' if query_override else 'dot')
    captured = capsys.readouterr()
    assert captured.out.startswith('digraph ')
    assert captured.out.rstrip().endswith('}')
    assert warning['message'] not in captured.out
    assert captured.err.count(warning['message']) == 1


@pytest.mark.parametrize('extra', [(), ('--head', '1'), ('--tail', '1'), ('--fields', 'entries')])
@pytest.mark.parametrize('query_override', [False, True])
def test_cli_json_projections_and_artifact_preserve_loss(tmp_path, monkeypatch, extra, query_override):
    root = tmp_path / 'affected'
    child = make_tree(root)
    artifact = tmp_path / 'answer.json'
    deny_child(monkeypatch, child)
    output = _run_reveal_direct(
        f'calls://{root.as_posix()}?uncalled&top=1' + ('&format=json' if query_override else ''),
        '--format', 'text' if query_override else 'json',
        '--also-json', str(artifact), *extra)
    assert output.returncode == 3  # D6 since calls is declared (BACK-2066): known loss is incomplete analysis, 3
    result = json.loads(output.stdout)
    assert len(loss_warning(result)) == 1
    assert 'confidence' not in result['meta']
    if query_override:
        saved = json.loads(artifact.read_text(encoding='utf-8'))
        assert len(loss_warning(saved)) == 1
        assert 'confidence' not in saved['meta']
    else:
        # The shared artifact owner deliberately no-ops when global format is JSON.
        assert not artifact.exists()


@pytest.mark.parametrize('query', QUERIES)
def test_existing_file_loss_warning_is_visible_in_text(tmp_path, capsys, query):
    root = tmp_path / 'source'
    make_tree(root)
    result = CallsAdapter(str(root), query).get_structure()
    warning = next(w for w in build_meta(str(root), skipped=[('lost.py', 'OSError: lost input')])['warnings']
                   if w.get('type') == 'analysis_failed')
    result['meta']['warnings'].append(warning)
    render_calls_structure(result, 'text')
    captured = capsys.readouterr()
    assert (captured.out + captured.err).count(warning['message']) == 1
