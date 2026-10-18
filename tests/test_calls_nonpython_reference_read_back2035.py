"""Late non-Python reference reads retain query-local file loss, not cached source loss."""
import copy
import json
import os
import time
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.calls import CallsAdapter, confidence, index, references
from reveal.mcp_server import reveal_query
from reveal.utils import request_cache
from reveal.utils.exclusions import exclusion_scope

pytestmark = pytest.mark.component


def project(root, *, zero=False):
    root.mkdir()
    definitions = 'void target(void) {}\n' + ('' if zero else 'void unused(void) {}\n')
    (root / 'worker.c').write_text(definitions, encoding='utf-8')
    registrar = 'int main(void) { return 0; }\n' if zero else 'void registrar(void) {}\n'
    file = root / 'registration.c'
    file.write_text('void target(void);\nvoid (*table[])(void) = {target};\n' + registrar, encoding='utf-8')
    aged = time.time_ns() - 60_000_000_000  # request-cache stamps skip files newer than the request; Windows' clock is coarse
    for source in (root / 'worker.c', file):
        os.utime(source, ns=(aged, aged))
    return file


def names(result):
    return {row['name'] for row in result['entries']}


def fault(monkeypatch, target, *, kind='named'):
    real_count, real_read = references._count_occurrences, Path.read_text
    real_collect, real_census = index.collect_structures, confidence.language_census
    state = {'active': False, 'enabled': True, 'events': [], 'passes': [], 'sources': [], 'censuses': []}

    def count(*args, **kwargs):
        state['active'] = True
        state['passes'].append(str(args[0]))
        try:
            return real_count(*args, **kwargs)
        finally:
            state['active'] = False

    def read(path, *args, **kwargs):
        if state['enabled'] and state['active'] and path == target:
            state['events'].append(str(path))
            if kind == 'unknown':
                raise PermissionError('controlled non-Python reference read')
            if kind == 'empty':
                raise PermissionError()
            raise PermissionError(13, 'controlled non-Python reference read', str(path))
        return real_read(path, *args, **kwargs)

    def collect(*args, **kwargs):
        value = real_collect(*args, **kwargs)
        state['sources'].append((value, copy.deepcopy(list(value)), list(value.skipped), list(value.traversal_failures)))
        return value

    def census(*args, **kwargs):
        value = real_census(*args, **kwargs)
        state['censuses'].append(value)
        return value

    monkeypatch.setattr(references, '_count_occurrences', count)
    monkeypatch.setattr(Path, 'read_text', read)
    monkeypatch.setattr(index, 'collect_structures', collect)
    monkeypatch.setattr(confidence, 'language_census', census)
    return state


def file_warning(result):
    warnings = [w for w in result['meta']['warnings'] if w.get('type') == 'analysis_failed']
    assert len(warnings) == 1
    warning = warnings[0]
    assert warning['count'] == 1 and warning['files'][0].endswith('registration.c')
    assert 'PermissionError' in warning['message']
    assert 'incorrect' in warning['message'].lower() or 'false positive' in warning['message'].lower()
    assert not any(w.get('type') == 'analysis_incomplete' for w in result['meta']['warnings'])
    assert 'confidence' not in result['meta'] and result['meta']['parse_mode'] == 'tree_sitter_partial'
    assert 'analysis_skipped' not in result and 'analysis_traversal_failures' not in result
    assert not result.get('error')
    return warning


def healthy_sources(state):
    assert state['sources']
    for value, contents, skipped, directories in state['sources']:
        assert list(value) == contents and value.skipped == skipped == []
        assert value.traversal_failures == directories == []
        assert {Path(row['file']).name for row in value} == {'worker.c', 'registration.c'}


@pytest.mark.parametrize('file_scope', [False, True])
@pytest.mark.parametrize('zero', [False, True])
def test_actual_late_read_changes_uncalled_classification_but_not_source_evidence(tmp_path, monkeypatch, file_scope, zero):
    root = tmp_path / 'affected'; registration = project(root, zero=zero)
    path = root / 'worker.c' if file_scope else root
    clean = CallsAdapter(str(path), 'uncalled=true').get_structure()
    assert 'target' not in names(clean)
    if zero:
        assert clean['entries'] == []  # main is an entrypoint, but keeps registration.c in the source set.
    state = fault(monkeypatch, registration)
    result = CallsAdapter(str(path), 'uncalled=true').get_structure()
    assert state['events'] == [str(registration)] and len(state['passes']) == 2
    healthy_sources(state)
    assert state['censuses'] == [{'c': 1 if file_scope else 2}]
    assert result['total_defined'] == clean['total_defined']
    assert names(result) == names(clean) | {'target'}
    file_warning(result)


@pytest.mark.parametrize('kind', ['unknown', 'empty'])
def test_attempted_reference_file_remains_known_when_oserror_has_no_filename(tmp_path, monkeypatch, kind):
    root = tmp_path / 'affected'; registration = project(root)
    state = fault(monkeypatch, registration, kind=kind)
    result = CallsAdapter(str(root), 'uncalled=true').get_structure()
    assert state['events'] == [str(registration)]
    file_warning(result)


@pytest.mark.parametrize('transport', ['adapter', 'mcp'])
def test_query_local_loss_never_poisons_healthy_sealed_index_and_repairs_without_clears(tmp_path, monkeypatch, transport):
    root = tmp_path / 'affected'; registration = project(root)
    sibling = tmp_path / 'sibling'; project(sibling)
    reveal_query(f'calls://{root}?target=target')
    warm = index._INDEX_CACHE[str(root)][1]
    stamp_key = (index.__name__ + '.callers', str(root))
    stamp = request_cache._STAMPS[stamp_key]
    adapter = CallsAdapter(str(root), 'uncalled=true')

    def invoke(path):
        if transport == 'adapter':
            return adapter.get_structure() if path == root else CallsAdapter(str(path), 'uncalled=true').get_structure()
        wire = reveal_query(f'calls://{path}?uncalled=true', provenance=True)
        assert type(wire) is str
        value = json.loads(wire); value.pop('execution', None)
        return value

    clean, sibling_clean = invoke(root), invoke(sibling)
    state = fault(monkeypatch, registration)
    lost, persistent = invoke(root), invoke(root)
    assert state['events'] == [str(registration), str(registration)] and lost == persistent
    healthy_sources(state)
    assert index._INDEX_CACHE[str(root)][1] is warm
    assert request_cache._STAMPS[stamp_key] == stamp
    assert warm.skipped == [] and warm.traversal_failures == []
    # Recovery precedes the expected red disclosure assertion, guarding query-local lifetime.
    assert invoke(sibling) == sibling_clean
    state['enabled'] = False
    assert invoke(root) == clean
    file_warning(lost)


@pytest.mark.parametrize('view', ['text', 'json', 'projection', 'artifact'])
def test_public_legacy_zero_discloses_late_file_loss_before_cuts(tmp_path, monkeypatch, view):
    root = tmp_path / 'affected'; registration = project(root)
    state = fault(monkeypatch, registration)
    artifact = tmp_path / 'answer.json'
    flags = ['--provenance']
    if view in {'text', 'artifact'}:
        flags += ['--format', 'text']
        if view == 'artifact':
            flags += ['--also-json', str(artifact)]
    else:
        flags += ['--format', 'json']
        if view == 'projection':
            flags += ['--fields', 'entries,total_uncalled', '--max-items', '0']
    response = run(f'calls://{root}?uncalled=true&top=1', *flags)
    assert state['events'] and response.returncode == 0
    if view == 'text':
        assert response.stdout.count('could not be analyzed completely') == 1
        assert 'registration.c' in response.stdout
        assert 'incorrect' in response.stdout.lower() or 'false positive' in response.stdout.lower()
    else:
        result = json.loads(artifact.read_text(encoding='utf-8') if view == 'artifact' else response.stdout)
        file_warning(result)
        assert result['execution']
        if view == 'projection':
            assert result['entries'] == []


@pytest.mark.parametrize('query', ['target=target', 'callees=registrar', 'root=registrar', 'rank=callers', 'modules=true'])
def test_other_query_modes_do_not_invent_an_unattempted_reference_failure(tmp_path, monkeypatch, query):
    root = tmp_path / 'affected'; registration = project(root)
    clean = CallsAdapter(str(root), query).get_structure()
    state = fault(monkeypatch, registration)
    assert CallsAdapter(str(root), query).get_structure() == clean
    assert state['passes'] == state['events'] == []


def test_no_candidates_means_no_reference_read_or_diagnostic(tmp_path, monkeypatch):
    root = tmp_path / 'affected'; root.mkdir(); file = root / 'main.c'
    file.write_text('int main(void) { return 0; }\n', encoding='utf-8')
    clean = CallsAdapter(str(root), 'uncalled=true').get_structure()
    state = fault(monkeypatch, file)
    result = CallsAdapter(str(root), 'uncalled=true').get_structure()
    assert result == clean and result['entries'] == []
    assert state['passes'] == state['events'] == []


def test_excluded_reference_file_is_not_missing_required_input(tmp_path, monkeypatch):
    root = tmp_path / 'affected'; registration = project(root)
    with exclusion_scope(root, ['registration.c']):
        clean = CallsAdapter(str(root), 'uncalled=true').get_structure()
        state = fault(monkeypatch, registration)
        result = CallsAdapter(str(root), 'uncalled=true').get_structure()
    assert result == clean and 'target' in names(result)
    assert state['events'] == []


def test_existing_helper_positional_shapes_and_healthy_reference_result_remain(tmp_path):
    root = tmp_path / 'affected'; registration = project(root)
    result = references.non_python_referenced_names(
        [str(root / 'worker.c'), str(registration)], {'c': {'target'}}, {('c', 'target'): 1}, {})
    assert result == {'c': {'target'}}
    occurrences = {}
    assert references._count_occurrences(str(registration), 'c', {'target'}, {}, occurrences) is None
    assert occurrences == {('c', 'target'): 1}
