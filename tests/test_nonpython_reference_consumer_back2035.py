"""Non-Python reference read loss is query-local required file evidence."""
import copy
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.calls import confidence, index, references
from reveal.adapters.calls.adapter import CallsAdapter
from reveal.utils import request_cache

pytestmark = pytest.mark.component


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _project(root):
    _write(root / 'worker.c', 'void target(void) {}\nvoid unused(void) {}\n')
    _write(root / 'registration.c', 'void target(void);\nvoid (*table[])(void) = {target};\nvoid registrar(void) {}\n')
    return (root / 'registration.c').resolve()


@pytest.fixture
def fault(monkeypatch):
    state = {'active': False, 'denied': set(), 'mode': 'known', 'events': [], 'passes': [],
             'collections': [], 'indexes': [], 'censuses': [], 'preexisting': []}
    real_count, real_read = references._count_occurrences, Path.read_text
    real_collect, real_build, real_census = index.collect_structures, index.build_callers_index, confidence.language_census

    def count(*args, **kwargs):
        state['passes'].append(str(args[0]))
        state['active'] = True
        try:
            return real_count(*args, **kwargs)
        finally:
            state['active'] = False

    def read(path, *args, **kwargs):
        if state['active'] and path.resolve() in state['denied']:
            state['events'].append(path.resolve())
            if state['mode'] == 'unknown':
                raise PermissionError('independent reference read loss')
            if state['mode'] == 'wrong-filename':
                raise PermissionError(13, 'independent reference read loss', 'unrelated-file.c')
            raise PermissionError(13, 'independent reference read loss', str(path))
        return real_read(path, *args, **kwargs)

    def collect(*args, **kwargs):
        value = real_collect(*args, **kwargs)
        # Supplied existing diagnostic metadata tests first-cause ownership; body is native.
        value.skipped.extend(state['preexisting'])
        state['collections'].append((value, copy.deepcopy(list(value)),
                                     copy.deepcopy(value.skipped), copy.deepcopy(value.traversal_failures)))
        return value

    def build(*args, **kwargs):
        value = real_build(*args, **kwargs)
        state['indexes'].append((value, copy.deepcopy(dict(value)), copy.deepcopy(value.skipped),
                                copy.deepcopy(value.traversal_failures)))
        return value

    def census(*args, **kwargs):
        value = real_census(*args, **kwargs)
        state['censuses'].append(value)
        return value

    monkeypatch.setattr(references, '_count_occurrences', count)
    monkeypatch.setattr(Path, 'read_text', read)
    monkeypatch.setattr(index, 'collect_structures', collect)
    monkeypatch.setattr(index, 'build_callers_index', build)
    monkeypatch.setattr(confidence, 'language_census', census)
    return state


def _warning(result):
    warnings = [entry for entry in result['meta']['warnings'] if entry.get('type') == 'analysis_failed']
    assert len(warnings) == 1, result['meta']
    assert result['meta']['parse_mode'] == 'tree_sitter_partial' and 'confidence' not in result['meta']
    assert not any(entry.get('unit') == 'directories' for entry in result['meta']['warnings'])
    assert 'analysis_skipped' not in result and 'analysis_traversal_failures' not in result
    return warnings[0]


def _unchanged(fault):
    for structures, body, skipped, directories in fault['collections']:
        assert list(structures) == body and structures.skipped == skipped and structures.traversal_failures == directories
    for caller_index, body, skipped, directories in fault['indexes']:
        assert dict(caller_index) == body and caller_index.skipped == skipped and caller_index.traversal_failures == directories


@pytest.mark.parametrize('mode', ['known', 'unknown', 'wrong-filename'])
def test_single_definition_file_still_requires_sibling_reference_read_and_uses_attempted_path(tmp_path, fault, mode):
    denied = _project(tmp_path)
    owner = CallsAdapter(str(tmp_path / 'worker.c'), 'uncalled=true')
    clean = owner.get_structure()
    assert {entry['name'] for entry in clean['entries']} == {'unused'}
    fault.update(denied={denied}, mode=mode, events=[], censuses=[])
    result = owner.get_structure()
    assert fault['events'] == [denied] and fault['censuses'] == [{'c': 1}]
    assert result['total_defined'] == 2 and {entry['name'] for entry in result['entries']} == {'target', 'unused'}
    warning = _warning(result)
    assert warning['count'] == 1 and 'registration.c' in str(warning)
    assert 'PermissionError' in warning['message']
    assert 'incorrect' in warning['message'].lower() or 'false positive' in warning['message'].lower()
    assert 'unrelated-file.c' not in str(warning.get('files', []))
    _unchanged(fault)
    fault['denied'] = set()
    assert owner.get_structure() == clean


def test_warm_sealed_source_index_survives_query_loss_persistent_and_repair_without_mutation(tmp_path, fault):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_query
    denied = _project(tmp_path)
    uri = 'calls://' + tmp_path.as_posix()
    reveal_query(uri + '?target=target', provenance=True)
    cache_key = str(tmp_path)
    warm = index._INDEX_CACHE[cache_key][1]
    stamp_key = (index.__name__ + '.callers', cache_key)
    stamp = request_cache._STAMPS[stamp_key]
    clean = json.loads(reveal_query(uri + '?uncalled=true', provenance=True))
    clean.pop('execution', None)
    fault['denied'] = {denied}
    packets = []
    for _ in range(2):
        raw = reveal_query(uri + '?uncalled=true', provenance=True)
        assert type(raw) is str
        result = json.loads(raw)
        result.pop('execution', None)
        assert index._INDEX_CACHE[cache_key][1] is warm and request_cache._STAMPS[stamp_key] == stamp
        packets.append(result)
        _warning(result)
    assert packets[0] == packets[1] and len(fault['events']) == 2
    _unchanged(fault)
    fault['denied'] = set()
    repaired = json.loads(reveal_query(uri + '?uncalled=true', provenance=True))
    repaired.pop('execution', None)
    assert repaired == clean and index._INDEX_CACHE[cache_key][1] is warm


def test_preexisting_same_path_first_cause_is_not_duplicated_or_replaced(tmp_path, fault):
    denied = _project(tmp_path)
    # Existing diagnostic uses a normalized-equivalent spelling; actual body remains native.
    first = (str(tmp_path / 'unused_component' / '..' / 'registration.c'), 'first supplied source diagnostic')
    fault.update(preexisting=[first], denied={denied})
    result = CallsAdapter(str(tmp_path), 'uncalled=true').get_structure()
    assert fault['events'] == [denied]
    warning = _warning(result)
    assert warning['count'] == 1 and 'first supplied source diagnostic' in str(warning)
    assert 'independent reference read loss' not in str(warning)
    assert 'incorrect' in warning['message'].lower() or 'false positive' in warning['message'].lower()
    _unchanged(fault)


def test_two_actual_file_losses_retain_file_population_and_do_not_mutate_native_sources(tmp_path, fault):
    first = _project(tmp_path)
    second = (tmp_path / 'registration_two.c').resolve()
    _write(second, 'void unused(void);\nvoid (*other[])(void) = {unused};\nvoid registrar_two(void) {}\n')
    fault.update(denied={first, second}, mode='unknown')
    result = CallsAdapter(str(tmp_path), 'uncalled=true&top=1').get_structure()
    assert set(fault['events']) == {first, second}
    assert result['total_uncalled'] == 4 and len(result['entries']) == 1
    warning = _warning(result)
    assert warning['count'] == 2 and 'registration.c' in str(warning) and 'registration_two.c' in str(warning)
    assert fault['censuses'] == [{'c': 3}]
    _unchanged(fault)


def test_public_cuts_and_text_sidecar_preserve_zero_display_file_diagnostic_and_legacy_zero(tmp_path, fault):
    denied = _project(tmp_path)
    fault.update(denied={denied}, mode='unknown')
    uri = 'calls://' + tmp_path.as_posix() + '?uncalled=true'
    response = run(uri, '--fields', 'entries', '--max-items', '0', '--format', 'json', '--provenance')
    assert response.returncode == 0 and fault['events'] == [denied]
    result = json.loads(response.stdout)
    assert result['entries'] == []
    _warning(result)
    artifact = tmp_path / 'answer.json'
    text = run(uri, '--max-items', '0', '--also-json', str(artifact))
    assert text.returncode == 0 and artifact.exists()
    saved = json.loads(artifact.read_text(encoding='utf-8'))
    _warning(saved)
    assert (text.stdout + text.stderr).count('file(s) could not be analyzed') == 1
    assert 'incorrect' in text.stdout.lower() or 'false positive' in text.stdout.lower()


@pytest.mark.parametrize('query', ['target=target', 'callees=registrar', 'rank=callers', 'modules=true'])
def test_other_modes_never_consult_reference_read_channel(tmp_path, fault, query):
    denied = _project(tmp_path)
    owner = CallsAdapter(str(tmp_path), query)
    clean = owner.get_structure()
    fault['denied'] = {denied}
    assert owner.get_structure() == clean and not fault['events'] and not fault['passes']
    assert fault['censuses'] == [{'c': 2}, {'c': 2}]


def test_no_candidates_never_invents_failed_reference_read(tmp_path, fault):
    file = tmp_path / 'main.c'
    _write(file, 'int main(void) { return 0; }\n')
    fault['denied'] = {file.resolve()}
    result = CallsAdapter(str(tmp_path), 'uncalled=true').get_structure()
    assert result['total_uncalled'] == 0 and not fault['events'] and not fault['passes']
    assert not any(entry.get('type') == 'analysis_failed' for entry in result['meta']['warnings'])
