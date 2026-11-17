"""Independent consumers: Pack keeps a partial optional graph and names its actual native loss.

BACK-2047 rejected an incomplete graph to the name-heuristic fallback; BACK-2666 (COMMAND_MODEL
"Degraded input") keeps it, ranks by the files it read and names each loss once in meta.warnings."""
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.adapters import pack
from reveal.analyzers.imports import service as import_service
from reveal.analyzers.imports.diagnostics import integrity_warnings

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
    real_build, real_scandir = import_service.analyze, os.scandir

    def build(scope, *args, **kwargs):
        state['active'] = True
        try:
            if state['crash']:
                raise RuntimeError('actual optional construction boundary failure')
            result = real_build(scope, *args, **kwargs)
            # Observe actual retained facts, never manufacture graph diagnostics.
            state['builds'].append((result, integrity_warnings(result.analysis, scope.root)))
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

    monkeypatch.setattr(import_service, 'analyze', build)
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


# helper.py's importers the partial graph still reads: focus.py, and child/source.py unless child is lost;
# a denied root leaves no file in the graph.
_PARTIAL_FAN_IN = {'source': 1, 'unknown-child': 1, 'combined': 1, 'inc-directory': 2, 'parse': 2, 'unknown-root': 0}


def _directory_losses(answer):
    return [w for w in answer['meta'].get('warnings', []) if w.get('unit') == 'directories']


@pytest.mark.parametrize('profile', ['source', 'inc-directory', 'unknown-child',
                                     'unknown-root', 'parse', 'combined'])
def test_native_loss_rejects_pair_and_clears_numeric_fallback_without_changing_protocol(
        tmp_path, native_fault, profile):
    _project(tmp_path)
    _loss(tmp_path, native_fault, profile)
    failures, lost = [], []
    graph, scanned = pack._build_pack_import_graph(tmp_path, failures, losses=lost)
    warnings = _assert_native_loss(native_fault, profile)
    owner = native_fault['builds'][-1][0]
    # BACK-2666: the partial graph is kept; the loss travels with the analysis whose warnings are `warnings`.
    assert graph is owner.analysis.graph and scanned is owner.analysis.scanned_files, (graph, scanned, warnings)
    assert failures == [] and lost == [owner.analysis]
    fan_in = pack._fetch_fan_in(tmp_path, [])
    assert fan_in.get(str((tmp_path / 'helper.py').resolve()), 0) == _PARTIAL_FAN_IN[profile]
    relevance = pack._compute_graph_relevance(tmp_path, 'focus', [])
    assert (relevance.get(str((tmp_path / 'helper.py').resolve()), 0) > 0) is (profile != 'unknown-root')
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
    # A file the build parsed only through error recovery is degraded input, which every noun names
    # (COMMAND_MODEL 'Degraded input', BACK-2665); the kept graph's other losses are named too, each once (BACK-2666).
    expected = [[(tmp_path / 'bad.py').as_posix()]] if profile in ('parse', 'combined') else []
    meta_warnings = answer['meta'].get('warnings', [])
    assert [w['files'] for w in meta_warnings if w['type'] == 'parse_recovered'] == expected
    assert not any(w['type'] == 'partial_parse' for w in meta_warnings)
    directories = _directory_losses(answer)
    native_directories = [w for w in warnings if w.get('unit') == 'directories']
    assert len(directories) == len(native_directories) == (0 if profile == 'parse' else 1)
    assert all(native['message'] in mine['message'] for native, mine in zip(native_directories, directories))
    assert 'relevance_warning' not in answer['meta'], answer['meta']
    fan_in = {row['relative']: row['fan_in'] for row in answer['files']}
    assert fan_in['helper.py'] == _PARTIAL_FAN_IN[profile]
    relevance = {row['relative']: row['graph_relevance'] for row in answer['files']}
    assert relevance['helper.py'] > 0


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
    # The 'combined' loss includes a file parsed only through error recovery: degraded input is an
    # incomplete answer (exit 3) on every noun (COMMAND_MODEL 'Degraded input', BACK-2665).
    assert result.returncode == 3, result.stderr
    warnings = _assert_native_loss(native_fault, 'combined')
    assert len(native_fault['builds']) == 2
    if route.endswith('json'):
        answer = json.loads(result.stdout)
        assert answer['files'] and not answer.get('error')
        (recovered,) = [w for w in answer['meta']['warnings'] if w['type'] == 'parse_recovered']
        assert [f.rsplit('/', 1)[-1] for f in recovered['files']] == ['bad.py']
        assert not any(w['type'] == 'partial_parse' for w in answer['meta']['warnings'])
        assert 'relevance_warning' not in answer['meta']
        note = '\n'.join(w['message'] for w in answer['meta']['warnings'])
    else:
        assert 'focus.py' in result.stdout
        note = result.stdout + result.stderr
    # BACK-2666: the kept graph's directory loss is named once, and no "not computed completely" advisory.
    assert 'not computed completely' not in note, note
    directory = next(w for w in warnings if w.get('unit') == 'directories')
    assert note.count(directory['message']) == 1, note


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
    # BACK-2666: the kept graph's directory loss is a named loss, so the answer is incomplete (exit 3).
    assert result.returncode == 3 and 'focus.py' in result.stdout
    _assert_native_loss(native_fault, 'source')
    assert 'heuristics and recency only' not in result.stdout
    assert result.stdout.count('Optional import graph is incomplete') == 1


def test_specialized_tool_builds_requested_signals_and_names_optional_loss(tmp_path, native_fault):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_pack
    _project(tmp_path)
    _loss(tmp_path, native_fault, 'source')
    result = reveal_pack(str(tmp_path), budget=8000, content=False,
                         architecture=True, focus='focus')
    assert type(result) is str and 'focus.py' in result
    # Binding (BACK-2045): the specialized tool builds the requested signals like the other
    # spellings, keeps its ordinary packet, and names the optional loss.
    assert len(native_fault['builds']) == 2
    assert result.count('Optional import graph is incomplete') == 1, result
