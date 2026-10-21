"""Independent Calls consumers must retain required confidence-census loss."""
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.calls import CallsAdapter, confidence, index
from reveal.analyzers._capability_table import calls_extraction_confidence
from reveal.utils.exclusions import exclusion_scope
from reveal.utils.path_utils import census_for_path

pytestmark = pytest.mark.component


def _write(path, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding='utf-8')


def _project(root, children=1):
    (root / '.git').mkdir(parents=True)
    _write(root / 'visible.py', 'def target():\n    return 1\n\ndef caller():\n    return target()\n')
    paths = []
    for number in range(children):
        child = root / f'ruby_{number}'
        _write(child / 'domain.rb', f'def unrelated_{number}\n  1\nend\n')
        paths.append(child.resolve())
    return paths


@pytest.fixture
def fault(monkeypatch):
    state = {'active': False, 'denied': set(), 'unknown': False, 'events': [], 'censuses': [], 'collections': 0}
    real_census, real_scandir, real_collect = confidence.census_for_path, os.scandir, index.collect_structures

    def census(*args, **kwargs):
        state['active'] = True
        try:
            result = real_census(*args, **kwargs)
            state['censuses'].append(dict(result.per_language))
            return result
        finally:
            state['active'] = False

    def scandir(path):
        if state['active'] and Path(path).resolve() in state['denied']:
            state['events'].append(Path(path).resolve())
            if state['unknown']:
                raise PermissionError('independent unlocated census directory denial')
            raise PermissionError(13, 'independent census directory denial', str(path))
        return real_scandir(path)

    def collect(*args, **kwargs):
        state['collections'] += 1
        result = real_collect(*args, **kwargs)
        assert not result.traversal_failures  # Query producer remains healthy.
        return result

    monkeypatch.setattr(confidence, 'census_for_path', census)
    monkeypatch.setattr(os, 'scandir', scandir)
    monkeypatch.setattr(index, 'collect_structures', collect)
    return state


def _warning(data):
    warnings = [entry for entry in data['meta']['warnings'] if entry.get('unit') == 'directories']
    assert len(warnings) == 1, data['meta']
    assert 'confidence' not in data['meta']
    assert data['meta']['parse_mode'] == 'tree_sitter_partial'
    return warnings[0]


def _body(data):
    return {key: value for key, value in data.items() if key != 'meta'}


@pytest.mark.parametrize('unknown', [False, True])
def test_partial_mixed_language_census_cannot_silently_change_score_with_query_unchanged(tmp_path, fault, unknown):
    children = _project(tmp_path)
    adapter = CallsAdapter(str(tmp_path), 'target=target')
    clean = adapter.get_structure()
    assert fault['censuses'][-1] == {'python': 1, 'ruby': 1}
    assert clean['meta']['confidence'] == round(
        (calls_extraction_confidence('python') + calls_extraction_confidence('ruby')) / 2, 4)
    fault.update(denied=set(children), unknown=unknown)
    lost = adapter.get_structure()
    assert fault['events'] and fault['censuses'][-1] == {'python': 1}
    assert _body(lost) == _body(clean) and lost['total_callers'] == 1
    warning = _warning(lost)
    assert warning['count'] == (0 if unknown else 1)
    if unknown:
        assert warning['unknown_directory_events'] == 1
    fault['denied'] = set()
    assert adapter.get_structure() == clean


@pytest.mark.parametrize('unknown', [False, True])
def test_seven_real_census_losses_preserve_unknown_or_bounded_directory_display(tmp_path, fault, unknown):
    children = _project(tmp_path, children=7)
    clean = CallsAdapter(str(tmp_path), 'target=target').get_structure()
    fault.update(denied=set(children), unknown=unknown)
    result = CallsAdapter(str(tmp_path), 'target=target').get_structure()
    assert len(fault['events']) == 7
    assert _body(result) == _body(clean)
    warning = _warning(result)
    assert warning['count'] == (0 if unknown else 7)
    assert len(warning['directories']) == (0 if unknown else 5)
    if unknown:
        assert warning['unknown_directory_events'] == 7
    else:
        assert 'and 2 more' in warning['message']
    assert 'missing file population is unknown' in warning['message']


@pytest.mark.parametrize('view', ['projection', 'sidecar', 'query_dot'])
def test_existing_cli_cuts_and_formats_cannot_hide_census_only_loss(tmp_path, fault, view):
    root = tmp_path / 'project'
    _project(root)
    fault['denied'] = {root.resolve()}
    uri = f'calls://{root.as_posix()}?target=target'
    artifact = tmp_path / 'answer.json'
    if view == 'projection':
        flags = ['--format', 'json', '--fields', 'levels,total_callers', '--max-items', '0', '--provenance']
    elif view == 'sidecar':
        uri += '&format=json'
        flags = ['--format', 'text', '--also-json', str(artifact), '--provenance']
    else:
        uri += '&format=dot'
        flags = ['--format', 'text']
    result = run(uri, *flags)
    assert result.returncode == 3, result.stderr  # D6 since calls is declared (BACK-2066): known loss is incomplete analysis, 3
    assert fault['events'] and fault['censuses'][-1] == {}
    if view == 'query_dot':
        assert result.stdout.startswith('digraph ')
        assert result.stderr.count('missing file population is unknown') == 1
        assert 'directory enumeration(s) failed' not in result.stdout
    else:
        data = json.loads(result.stdout)
        assert data['total_callers'] == 1
        _warning(data)
        assert data['execution']['command'].startswith('reveal calls://')
        if view == 'sidecar':
            assert json.loads(artifact.read_text(encoding='utf-8')) == data
        else:
            assert data['levels'] == []


@pytest.mark.parametrize('provenance', [False, True])
def test_warm_healthy_index_still_requires_fresh_census_on_normal_host_requests(tmp_path, fault, provenance):
    pytest.importorskip('mcp')
    from reveal.mcp_server import _ToolFailure, reveal_query
    root = tmp_path / 'project'
    children = _project(root)
    sibling = tmp_path / 'sibling'
    _project(sibling)
    uri = f'calls://{root.as_posix()}?target=target'
    sibling_uri = f'calls://{sibling.as_posix()}?target=target'

    def query(value):
        response = reveal_query(value, provenance=provenance)
        assert type(response) is str and not isinstance(response, _ToolFailure)
        return response

    def stable(text):
        # execution.git.dirty reads the process checkout, which other workers write to (BACK-2059)
        return {key: value for key, value in json.loads(text).items() if key != 'execution'} if provenance else text

    clean, sibling_clean = query(uri), query(sibling_uri)
    # A second clean request normally seals the retained index for actual reuse.
    assert stable(query(uri)) == stable(clean)
    retained = index._INDEX_CACHE[str(root)][1]
    collected = fault['collections']
    before_census = len(fault['censuses'])
    fault['denied'] = set(children)
    lost = query(uri)
    assert index._INDEX_CACHE[str(root)][1] is retained
    assert fault['collections'] == collected
    assert len(fault['censuses']) == before_census + 1
    assert 'missing file population is unknown' in lost
    assert stable(query(sibling_uri)) == stable(sibling_clean)
    fault['denied'] = set()
    assert stable(query(uri)) == stable(clean)


def test_empty_unmeasured_and_single_file_default_contracts_stay_clean(tmp_path):
    empty = tmp_path / 'empty'
    empty.mkdir()
    unknown = tmp_path / 'unknown'
    _write(unknown / 'notes.txt', 'No supported source in this scope.\n')
    for root in (empty, unknown):
        result = CallsAdapter(str(root), 'target=target').get_structure()
        assert result['meta']['confidence'] == 0.85
        assert result['meta']['parse_mode'] == 'tree_sitter_full'
        assert not any(entry.get('unit') == 'directories' for entry in result['meta']['warnings'])
    source = tmp_path / 'single.py'
    _write(source, 'VALUE = 1\n')
    census = census_for_path(source, [], True)
    assert census.per_language == {'python': 1}
    assert confidence.language_census(str(source)) == {'python': 1}
    assert confidence.language_census(str(tmp_path / 'missing')) == {}


def test_intentional_exclusion_and_sibling_omit_no_required_census_events(tmp_path, fault):
    root = tmp_path / 'project'
    children = _project(root)
    sibling = tmp_path / 'sibling'
    _project(sibling)
    sibling_clean = CallsAdapter(str(sibling), 'target=target').get_structure()
    with exclusion_scope(root, ['ruby_0']):
        clean = CallsAdapter(str(root), 'target=target').get_structure()
        fault['denied'] = set(children)
        assert CallsAdapter(str(root), 'target=target').get_structure() == clean
        assert not fault['events']
    assert CallsAdapter(str(sibling), 'target=target').get_structure() == sibling_clean


def test_public_missing_path_retains_resource_guard(tmp_path):
    result = run(f'calls://{(tmp_path / "missing").as_posix()}?target=target', '--format', 'json')
    assert result.returncode != 0
    assert 'Path not found' in result.stderr + result.stdout
