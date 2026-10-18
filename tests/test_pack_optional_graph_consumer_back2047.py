"""Independent consumers reject actual native loss in optional Pack graph signals."""
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.adapters import pack
from reveal.adapters.imports import ImportsAdapter

pytestmark = pytest.mark.component


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _project(root):
    _write(root / 'focus.py', 'import helper\n')
    _write(root / 'helper.py', 'def work():\n    return 1\n')
    _write(root / 'child' / 'source.py', 'import helper\n')
    _write(root / 'main.c', '#include "headers/hidden.inc"\n')
    _write(root / 'headers' / 'hidden.inc', 'int hidden(void);\n')


@pytest.fixture
def native_fault(monkeypatch):
    state = {'active': False, 'denied': None, 'unknown': False,
             'events': [], 'builds': [], 'crash': False}
    real_build, real_scandir = ImportsAdapter._build_graph, os.scandir

    def build(owner, *args, **kwargs):
        state['active'] = True
        try:
            if state['crash']:
                raise RuntimeError('actual optional construction boundary failure')
            result = real_build(owner, *args, **kwargs)
            # Observe actual retained facts, never manufacture graph diagnostics.
            state['builds'].append((owner, owner.integrity_warnings(Path(args[0]))))
            return result
        finally:
            state['active'] = False

    def scandir(path):
        if state['active'] and Path(path).resolve() == state['denied']:
            state['events'].append(Path(path).resolve())
            if state['unknown']:
                raise PermissionError('unlocated independent optional graph loss')
            raise PermissionError(13, 'independent optional graph loss', str(path))
        return real_scandir(path)

    monkeypatch.setattr(ImportsAdapter, '_build_graph', build)
    monkeypatch.setattr(os, 'scandir', scandir)
    return state


def _loss(root, state, profile):
    if profile in ('source', 'unknown-child', 'combined'):
        state['denied'] = (root / 'child').resolve()
    elif profile == 'inc-directory':
        state['denied'] = (root / 'headers').resolve()
    elif profile == 'unknown-root':
        state['denied'] = root.resolve()
    state['unknown'] = profile.startswith('unknown')
    if profile in ('parse', 'combined'):
        _write(root / 'bad.py', 'this is !!! invalid python\nimport os\n')


def _assert_native_loss(state, profile):
    assert state['builds'], state
    warnings = state['builds'][-1][1]
    if profile in ('parse', 'combined'):
        assert any(w['type'] == 'partial_parse' for w in warnings), warnings
    if profile != 'parse':
        assert state['events'], state
        directories = [w for w in warnings if w.get('unit') == 'directories']
        assert len(directories) == 1, warnings
        if profile.startswith('unknown'):
            assert directories[0]['count'] == 0
            assert directories[0]['unknown_directory_events'] > 0
    return warnings


@pytest.mark.parametrize('profile', ['source', 'inc-directory', 'unknown-child',
                                     'unknown-root', 'parse', 'combined'])
def test_native_loss_rejects_pair_and_clears_numeric_fallback_without_changing_protocol(
        tmp_path, native_fault, profile):
    _project(tmp_path)
    _loss(tmp_path, native_fault, profile)
    failures = []
    graph, scanned = pack._build_pack_import_graph(tmp_path, failures)
    warnings = _assert_native_loss(native_fault, profile)
    assert graph is None and scanned == set(), (graph, scanned, warnings)
    assert len(failures) == len(warnings)
    assert all(tmp_path.as_posix() in message for message in failures)
    assert all(w['message'] in '\n'.join(failures) for w in warnings)
    assert pack._fetch_fan_in(tmp_path, []) == {}
    assert pack._compute_graph_relevance(tmp_path, 'focus', []) == {}
    assert len(native_fault['builds']) == 3


@pytest.mark.parametrize('profile', ['inc-directory', 'parse', 'combined'])
def test_two_requested_signals_keep_primary_rows_and_deduplicate_native_causes(
        tmp_path, native_fault, profile):
    _project(tmp_path)
    _loss(tmp_path, native_fault, profile)
    # Candidate enumeration stays healthy; only actual Imports builds are denied.
    answer = pack.PackAdapter(str(tmp_path),
                              'budget=8000&architecture=true&focus=focus').get_structure()
    warnings = _assert_native_loss(native_fault, profile)
    assert len(native_fault['builds']) == 2
    assert {'focus.py', 'helper.py', 'child/source.py', 'main.c'} <= {
        row['relative'] for row in answer['files']}
    assert answer['meta']['selected'] == answer['meta']['total_candidates']
    assert not answer.get('error')
    assert not answer['meta'].get('warnings')  # Optional loss is not required inventory loss.
    note = answer['meta'].get('relevance_warning', '')
    assert 'not computed completely' in note and 'unavailable or incomplete' in note, answer
    assert 'heuristics and recency only' in note
    assert all(note.count(w['message']) == 1 for w in warnings), note
    assert all(row['fan_in'] == row['graph_relevance'] == 0 for row in answer['files'])


@pytest.mark.parametrize('route', ['native-text', 'native-json', 'uri-json'])
def test_public_legacy_success_reports_optional_fallback_with_healthy_candidates(
        tmp_path, native_fault, route):
    _project(tmp_path)
    _loss(tmp_path, native_fault, 'combined')
    if route.startswith('native'):
        args = ['pack', str(tmp_path), '--budget', '8000', '--architecture', '--focus', 'focus']
    else:
        args = ['pack://' + tmp_path.as_posix() + '?budget=8000&architecture=true&focus=focus']
    if route.endswith('json'):
        args += ['--format', 'json']
    result = _run_reveal_direct(*args)
    assert result.returncode == 0, result.stderr
    warnings = _assert_native_loss(native_fault, 'combined')
    assert len(native_fault['builds']) == 2
    if route.endswith('json'):
        answer = json.loads(result.stdout)
        assert answer['files'] and not answer.get('error')
        note = answer['meta'].get('relevance_warning', '')
    else:
        assert 'focus.py' in result.stdout
        note = result.stdout + result.stderr
    assert 'not computed completely' in note and 'unavailable or incomplete' in note, note
    assert all(note.count(w['message']) == 1 for w in warnings), note


def test_healthy_pair_identity_and_empty_seed_keep_old_interfaces(tmp_path, native_fault):
    _project(tmp_path)
    graph, scanned = pack._build_pack_import_graph(tmp_path, [])
    owner, warnings = native_fault['builds'][-1]
    assert not warnings
    assert graph is owner.analysis.graph and scanned is owner.analysis.scanned_files
    assert pack._fetch_fan_in(tmp_path, [])[str(tmp_path / 'helper.py')] > 0
    assert pack._compute_graph_relevance(tmp_path, 'focus', [])
    assert pack._compute_graph_relevance(tmp_path, 'no-such-seed', []) == {}
    before = len(native_fault['builds'])
    assert pack._compute_graph_relevance(tmp_path, None, []) == {}
    assert len(native_fault['builds']) == before


def test_existing_raised_failure_stays_typed_optional_pair(tmp_path, native_fault):
    _project(tmp_path)
    native_fault['crash'] = True
    failures = []
    assert pack._build_pack_import_graph(tmp_path, failures) == (None, set())
    assert failures == ['RuntimeError: actual optional construction boundary failure']


def test_uri_text_visibility_is_existing_binding_residual(tmp_path, native_fault):
    _project(tmp_path)
    _loss(tmp_path, native_fault, 'source')
    result = _run_reveal_direct('pack://' + tmp_path.as_posix() +
                                '?budget=8000&architecture=true&focus=focus')
    assert result.returncode == 0 and 'focus.py' in result.stdout
    _assert_native_loss(native_fault, 'source')
    assert 'heuristics and recency only' not in result.stdout


def test_specialized_tool_keeps_existing_no_graph_build_route(tmp_path, native_fault):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_pack
    _project(tmp_path)
    _loss(tmp_path, native_fault, 'source')
    result = reveal_pack(str(tmp_path), budget=8000, content=False,
                         architecture=True, focus='focus')
    assert type(result) is str and 'focus.py' in result
    assert native_fault['builds'] == [] and native_fault['events'] == []
