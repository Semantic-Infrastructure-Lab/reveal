"""Pack rejects native incomplete optional graph signals to advisory fallback."""
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters import pack
from reveal.adapters.imports import ImportsAdapter

pytestmark = pytest.mark.component


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode('utf-8'))  # sizes below are LF byte counts on every platform
    return path


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'project'
    write(root / 'core' / 'worker.py', 'def execute():\n    return 1\n')
    write(root / 'included' / 'helper.py', 'from core import worker\n')
    return root


@pytest.fixture
def observed(monkeypatch):
    state = {'active': False, 'denied': None, 'unknown': False, 'builds': [], 'events': []}
    real_build, real_scan = ImportsAdapter._build_graph, os.scandir
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')

    def build(self, *args, **kwargs):
        state['active'] = True
        try:
            result = real_build(self, *args, **kwargs)
            state['builds'].append({'graph': self.analysis.graph, 'scanned': self.analysis.scanned_files,
                                    'warnings': self.integrity_warnings(Path(args[0])),
                                    'failed': list(self.analysis.files_failed)})
            return result
        finally:
            state['active'] = False

    def scandir(path):
        if state['active'] and Path(path) == state['denied']:
            state['events'].append(Path(path))
            if state['unknown']:
                raise PermissionError('actual unlocated optional Pack graph source loss')
            raise PermissionError(13, 'actual optional Pack graph source loss', str(path))
        return real_scan(path)

    monkeypatch.setattr(ImportsAdapter, '_build_graph', build)
    monkeypatch.setattr(os, 'scandir', scandir)
    return state


def configure(root, observed, loss):
    if loss in ('child', 'named-root', 'unknown-root', 'combined-known', 'combined-unknown'):
        observed['denied'] = root if loss.endswith('root') else root / 'included'
    observed['unknown'] = loss in ('unknown-root', 'combined-unknown')
    if loss in ('parse', 'combined-known', 'combined-unknown'):
        write(root / 'bad.py', 'this is !!! invalid python\nimport os\n')


def assert_native_loss(observed, loss):
    assert len(observed['builds']) == 1
    native = observed['builds'][0]
    assert native['graph'] is not None and native['warnings']
    types = {warning['type'] for warning in native['warnings']}
    if loss in ('parse', 'combined-known', 'combined-unknown'):
        assert native['failed'] and 'partial_parse' in types
    if loss != 'parse':
        assert observed['events'] == [observed['denied']]
        directory = next(w for w in native['warnings'] if w.get('unit') == 'directories')
        assert directory['count'] == (0 if observed['unknown'] else 1)
        if observed['unknown']:
            assert directory['unknown_directory_events'] == 1
    return native


@pytest.mark.parametrize('loss', ['child', 'named-root', 'unknown-root', 'parse', 'combined-known', 'combined-unknown'])
@pytest.mark.parametrize('with_sink', [False, True])
def test_existing_graph_pair_rejects_native_partial_input_without_new_protocol(project, observed, loss, with_sink):
    configure(project, observed, loss)
    failures = []
    graph, scanned = pack._build_pack_import_graph(project, failures if with_sink else None)
    native = assert_native_loss(observed, loss)
    assert (graph, scanned) == (None, set()), 'Optional numeric ranks must not use a native incomplete graph'
    if with_sink:
        assert len(failures) == len(native['warnings'])
        for warning in native['warnings']:
            assert any(project.as_posix() in message and warning['message'] in message for message in failures)


@pytest.mark.parametrize('helper', ['fan-in', 'relevance'])
def test_existing_numeric_helpers_fall_back_with_one_native_graph_build(project, observed, helper):
    configure(project, observed, 'child')
    failures = []
    scores = (pack._fetch_fan_in(project, failures) if helper == 'fan-in'
              else pack._compute_graph_relevance(project, 'worker', failures))
    native = assert_native_loss(observed, 'child')
    assert scores == {} and isinstance(scores, dict)
    assert len(failures) == 1 and native['warnings'][0]['message'] in failures[0]


@pytest.mark.parametrize('view', ['cli-json', 'uri-json', 'cli-text'])
def test_public_pack_retains_healthy_primary_measurements_and_advisory_outcome(project, observed, view):
    configure(project, observed, 'child')
    if view == 'uri-json':
        args = ['pack://' + str(project) + '?architecture=true', '--format', 'json']
    else:
        args = ['pack', str(project), '--architecture']
        if view == 'cli-json':
            args += ['--format', 'json']
    response = run(*args)
    native = assert_native_loss(observed, 'child')
    assert response.returncode == 0, (response.stdout, response.stderr)
    if view.endswith('json'):
        data = json.loads(response.stdout)
        assert data['type'] == 'pack' and data['meta']['total_candidates'] == data['meta']['selected'] == 2
        assert sorted((row['size'], row['lines'], row['tokens_approx']) for row in data['files']) == [(24, 1, 6), (28, 2, 7)]
        assert all(row['fan_in'] == 0 and row['graph_relevance'] == 0 for row in data['files'])
        assert not any(w.get('type') == 'analysis_incomplete' for w in data['meta'].get('warnings', []))
        warning = data['meta'].get('relevance_warning', '')
    else:
        assert 'Selected 2 of 2 files' in response.stdout
        warning = response.stderr
    assert native['warnings'][0]['message'] in warning and project.as_posix() in warning
    assert 'not computed completely' in warning and 'heuristics and recency' in warning


def test_both_requested_signals_keep_existing_two_builds_and_deduplicate_original_causes(project, observed):
    configure(project, observed, 'combined-known')
    result = pack.PackAdapter(str(project), 'architecture=true&focus=worker').get_structure()
    assert len(observed['builds']) == 2 and observed['events'] == [project / 'included'] * 2
    assert all(len(native['warnings']) == 2 for native in observed['builds'])
    assert result['meta']['total_candidates'] == result['meta']['selected'] == 3
    assert all(row['fan_in'] == 0 and row['graph_relevance'] == 0 for row in result['files'])
    warning = result['meta'].get('relevance_warning', '')
    for entry in observed['builds'][0]['warnings']:
        assert warning.count(entry['message']) == 1
    assert 'fan-in and graph-relevance not computed completely' in warning


@pytest.mark.parametrize('empty_graph', [False, True])
def test_healthy_graph_and_scanned_objects_retain_exact_pair_identity(project, observed, empty_graph):
    if empty_graph:
        (project / 'included' / 'helper.py').write_text('VALUE=1\n', encoding='utf-8')
    failures = []
    graph, scanned = pack._build_pack_import_graph(project, failures)
    native, = observed['builds']
    assert graph is native['graph'] and scanned is native['scanned']
    assert len(scanned) == 2 and native['warnings'] == [] and failures == []
    assert (graph.get_import_count() == 0) is empty_graph


def test_no_seed_and_unrequested_focus_do_not_manufacture_failure(project, observed):
    failures = []
    assert pack._compute_graph_relevance(project, None, failures) == {} and observed['builds'] == []
    assert pack._compute_graph_relevance(project, 'no_matching_seed', failures) == {}
    assert len(observed['builds']) == 1 and failures == [] and observed['events'] == []


def test_existing_raised_construction_failure_keeps_typed_cause_and_pair(project, monkeypatch):
    def failed(*args, **kwargs):
        raise RuntimeError('controlled existing construction failure')
    monkeypatch.setattr(ImportsAdapter, '_build_graph', failed)
    failures = []
    assert pack._build_pack_import_graph(project, failures) == (None, set())
    assert failures == ['RuntimeError: controlled existing construction failure']
    result = pack.PackAdapter(str(project), 'architecture=true').get_structure()
    assert result['meta']['selected'] == 2 and failures[0] in result['meta']['relevance_warning']


def test_specialized_mcp_and_uri_text_existing_presentation_are_not_migrated(project, observed):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_pack
    configure(project, observed, 'child')
    specialized = reveal_pack(str(project), architecture=True, focus='worker', content=False)
    assert type(specialized) is str and 'Selected 2 of 2 files' in specialized
    assert observed['builds'] == observed['events'] == []  # Existing specialized helper bypass.
    response = run('pack://' + str(project) + '?architecture=true')
    assert len(observed['builds']) == 1 and observed['events'] == [project / 'included']
    assert response.returncode == 0 and 'Selected 2 of 2 files' in response.stdout
    # Binding closed the visibility gap (BACK-2045): URI text now carries the advisory on stderr,
    # exactly as the command always did, with the original cause.
    assert 'directory enumeration' in response.stderr and 'directory enumeration' not in response.stdout
