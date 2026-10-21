"""An independent Calls confidence census cannot silently lose required directories."""
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.calls import CallsAdapter
from reveal.adapters.calls import confidence
from reveal.analyzers._capability_table import calls_extraction_confidence
from reveal.utils.exclusions import exclusion_scope
from reveal.utils.path_utils import census_for_path

pytestmark = pytest.mark.component
MODES = ['target=leaf', 'callees=entry', 'root=entry', 'uncalled&top=1', 'rank=callers&top=1', 'modules']


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def project(root, *, empty=False):
    (root / '.git').mkdir(parents=True)
    child = root / 'included_child'
    if empty:
        write(root / 'plain.py', 'VALUE = 1\n')
        write(child / 'plain.py', 'VALUE = 2\n')
    else:
        write(root / 'leaf.py', 'def leaf():\n    return 1\n')
        write(root / 'entry.py', 'from leaf import leaf\n\ndef entry():\n    return leaf()\n')
        write(child / 'hidden.py', 'from leaf import leaf\n\ndef hidden():\n    return leaf()\n')
    return child


def fault(monkeypatch, paths, *, unknown=False, combined=False):
    state = {'active': False, 'events': [], 'censuses': []}
    real_census = confidence.census_for_path
    real_scandir = os.scandir

    def census(*args, **kwargs):
        previous = state['active']; state['active'] = True
        try:
            result = real_census(*args, **kwargs)
            state['censuses'].append(dict(result.per_language))
            return result
        finally:
            state['active'] = previous

    def scandir(path):
        if Path(path) in paths and (state['active'] or combined):
            label = 'census' if state['active'] else 'query'
            state['events'].append((label, str(path)))
            if unknown:
                raise PermissionError('controlled Calls ' + label + ' unlocated enumeration loss')
            raise PermissionError(13, 'controlled Calls ' + label + ' enumeration loss', str(path))
        return real_scandir(path)

    monkeypatch.setattr(confidence, 'census_for_path', census)
    monkeypatch.setattr(os, 'scandir', scandir)
    return state


def directory_warning(result):
    entries = [entry for entry in result['meta']['warnings']
               if entry.get('type') == 'analysis_incomplete' and entry.get('unit') == 'directories']
    assert len(entries) == 1
    return entries[0]


def observations(result):
    return {key: value for key, value in result.items() if key != 'meta'}


@pytest.mark.parametrize('query', MODES)
@pytest.mark.parametrize('scope', ['root', 'child'])
def test_actual_census_loss_all_modes_preserves_healthy_query_observations(tmp_path, monkeypatch, query, scope):
    root = tmp_path / 'affected'; child = project(root)
    baseline = CallsAdapter(str(root), query).get_structure()
    assert baseline['meta']['confidence'] == calls_extraction_confidence('python')
    state = fault(monkeypatch, {root if scope == 'root' else child})
    result = CallsAdapter(str(root), query).get_structure()
    assert state['events'] and all(label == 'census' for label, _ in state['events'])
    assert observations(result) == observations(baseline)
    assert state['censuses'] == ([{}] if scope == 'root' else [{'python': 2}])
    assert 'confidence' not in result['meta']
    assert result['meta']['parse_mode'] == 'tree_sitter_partial'
    entry = directory_warning(result)
    assert entry['count'] == 1 and 'PermissionError' in entry['message']
    assert 'missing file population is unknown' in entry['message']
    assert 'analysis_traversal_failures' not in result


@pytest.mark.parametrize('empty', [False, True])
def test_actual_unknown_census_event_is_loss_even_without_named_directory(tmp_path, monkeypatch, empty):
    root = tmp_path / 'affected'; project(root, empty=empty)
    clean = CallsAdapter(str(root), 'target=leaf').get_structure()
    fault(monkeypatch, {root}, unknown=True)
    result = CallsAdapter(str(root), 'target=leaf').get_structure()
    # Complete and empty, the clean answer says nothing defines or calls leaf (BACK-2066,
    # decision d); with a census event lost the absence is not claimed.
    assert ('error' in clean) is empty and 'error' not in result
    assert observations(result) == {k: v for k, v in observations(clean).items() if k != 'error'}
    entry = directory_warning(result)
    assert entry['count'] == 0 and entry['unknown_directory_events'] == 1
    assert 'confidence' not in result['meta']


def test_query_and_census_directory_events_share_formatter_without_dropping_either_cause(tmp_path, monkeypatch):
    root = tmp_path / 'affected'; child = project(root)
    state = fault(monkeypatch, {child}, combined=True)
    result = CallsAdapter(str(root), 'target=leaf').get_structure()
    assert {label for label, _ in state['events']} == {'query', 'census'}
    entry = directory_warning(result)
    assert entry['count'] == 1 and entry['directories'] == ['included_child']
    assert any('controlled Calls census enumeration loss' in cause for cause in entry['causes'])
    assert any('controlled Calls query enumeration loss' in cause for cause in entry['causes'])


@pytest.mark.parametrize('view', ['text', 'json', 'dot', 'artifact'])
def test_actual_public_output_discloses_census_loss_once(tmp_path, monkeypatch, view):
    root = tmp_path / 'affected'; project(root)
    fault(monkeypatch, {root})
    uri = 'calls://' + str(root) + '?target=leaf'
    if view == 'dot':
        uri += '&format=dot'
    artifact = tmp_path / 'calls.json'
    flags = ['--format', 'json'] if view == 'json' else []
    if view == 'artifact':
        flags += ['--also-json', str(artifact)]
    response = run(uri, *flags)
    assert response.returncode == 3  # D6 since calls is declared (BACK-2066): known loss is incomplete analysis, 3
    if view in {'json', 'artifact'}:
        data = json.loads(response.stdout if view == 'json' else artifact.read_text(encoding='utf-8'))
        assert data['total_callers'] == 2 and 'confidence' not in data['meta']
        directory_warning(data)
    else:
        assert (response.stdout + response.stderr).count('missing file population is unknown') == 1
        if view == 'dot':
            assert response.stdout.startswith('digraph ') and 'PermissionError' in response.stderr
            assert 'PermissionError' not in response.stdout


@pytest.mark.parametrize('provenance', [False, True])
def test_normal_decorated_requests_repair_census_score_and_keep_sibling_exact(tmp_path, monkeypatch, provenance):
    pytest.importorskip('mcp')
    from reveal.mcp_server import _ToolFailure, reveal_query
    root = tmp_path / 'affected'; project(root)
    sibling = tmp_path / 'sibling'; project(sibling)
    uri = 'calls://' + str(root) + '?target=leaf'
    sibling_uri = 'calls://' + str(sibling) + '?target=leaf'
    def query(target):
        result = reveal_query(target, provenance=provenance)
        assert type(result) is str and not isinstance(result, _ToolFailure)
        return result
    clean = query(uri); sibling_clean = query(sibling_uri)
    with monkeypatch.context() as context:
        fault(context, {root})
        lost = query(uri)
        assert 'missing file population is unknown' in lost
        assert query(sibling_uri) == sibling_clean
        if provenance:
            data = json.loads(lost)
            assert data['total_callers'] == 2 and 'confidence' not in data['meta']
            assert data['execution']['command'].startswith('reveal calls://')
    assert query(uri) == clean


def test_clean_empty_single_file_and_default_census_shapes_remain_compatible(tmp_path):
    empty = tmp_path / 'empty'; empty.mkdir()
    result = CallsAdapter(str(empty), 'target=leaf').get_structure()
    assert result['meta']['confidence'] == 0.85 and result['meta']['parse_mode'] == 'tree_sitter_full'
    assert confidence.language_census(str(empty)) == {}
    assert confidence.language_census(str(tmp_path / 'missing')) == {}
    file = write(tmp_path / 'single.py', 'def leaf():\n    return 1\n')
    assert confidence.language_census(str(file)) == {'python': 1}
    assert census_for_path(file, [], True).per_language == {'python': 1}


def test_unqualified_nonwalk_oserror_keeps_existing_fallback_without_directory_mislabel(tmp_path, monkeypatch):
    file = write(tmp_path / 'single.py', 'VALUE = 1\n')
    def fail(*args, **kwargs):
        raise PermissionError(13, 'controlled non-enumeration file/stat/config failure', str(file))
    monkeypatch.setattr(confidence, 'census_for_path', fail)
    assert confidence.language_census(str(file)) == {}
    result = confidence.build_meta(str(file))
    assert result['confidence'] == 0.85 and result['parse_mode'] == 'tree_sitter_full'
    assert not any(entry.get('unit') == 'directories' for entry in result['warnings'])


def test_excluded_and_noise_directories_are_policy_omissions_not_census_errors(tmp_path, monkeypatch):
    root = tmp_path / 'affected'; child = project(root)
    noise = root / 'node_modules'; write(noise / 'hidden.py', 'VALUE = 1\n')
    with exclusion_scope(root, ['included_child']):
        clean = CallsAdapter(str(root), 'target=leaf').get_structure()
        state = fault(monkeypatch, {child, noise})
        assert CallsAdapter(str(root), 'target=leaf').get_structure() == clean
        assert not state['events']
