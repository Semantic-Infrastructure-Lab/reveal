"""Actual I007 directory-loss regressions on existing rule/check/cache APIs."""
import json
import os
import pickle
import time
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal import mcp_server
from reveal.rules.imports import _dep_reconciliation as dep
from reveal.rules.imports.I007 import I007
from reveal.rules.scan_caches import get_scan_disclosures, init_scan_caches, preload_scan_caches
from reveal.utils.request_cache import request_started_ns, reset_request_caches, seal_request_caches

pytestmark = pytest.mark.component


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    aged = time.time_ns() - 60_000_000_000
    os.utime(path, ns=(aged, aged))
    return path


def project(root, language, *, declarations=True, already_used=False):
    if language == 'python':
        deps = 'dependencies=["requests","orjson"]\n' if declarations else ''
        manifest = write(root / 'pyproject.toml', '[project]\nname="probe"\nversion="0.0.0"\n' + deps)
        visible = 'import orjson\n' + ('import requests\n' if already_used else '')
        write(root / 'visible.py', visible)
        hidden = write(root / 'included_child' / 'usage.py', 'import requests\n')
        helper, used, missing, extension = dep.python_declared_unused, 'orjson', 'requests', '.py'
    else:
        deps = '[dependencies]\nserde="1"\nrand="0.8"\n' if declarations else ''
        manifest = write(root / 'Cargo.toml', '[package]\nname="probe"\nversion="0.0.0"\n' + deps)
        visible = 'use rand::Rng;\n' + ('use serde::Serialize;\n' if already_used else '')
        write(root / 'visible.rs', visible + 'fn healthy() {}\n')
        hidden = write(root / 'included_child' / 'usage.rs', 'use serde::Serialize;\n')
        helper, used, missing, extension = dep.rust_declared_unused, 'rand', 'serde', '.rs'
    return manifest, hidden, helper, used, missing, extension


@pytest.fixture
def fault(monkeypatch):
    state = {'active': False, 'mode': 'healthy', 'unknown': False, 'events': [], 'builds': []}
    real_scan, real_scandir, real_get = dep._scan_project_imports_uncached, os.scandir, dep.get_extractor

    def scan(*args, **kwargs):
        state['active'] = True
        try:
            result = real_scan(*args, **kwargs)
            state['builds'].append((Path(args[0]), result))
            return result
        finally:
            state['active'] = False
            if state['mode'] == 'transient':
                state['mode'] = 'healthy'  # repaired before the host's sealing walk

    def scandir(path):
        if state['active'] and state['mode'] in {'directory', 'transient'} and Path(path).name == 'included_child':
            state['events'].append(str(path))
            if state['unknown']:
                raise PermissionError('actual I007 unlocated directory loss')
            raise PermissionError(13, 'actual I007 directory loss', str(path))
        return real_scandir(path)

    def extractor(path):
        if state['active'] and state['mode'] == 'extractor' and Path(path).stem == 'usage':
            class FailedExtractor:
                def extract_imports(self, _path):
                    raise OSError('existing extractor-failure policy comparator')
            return FailedExtractor()
        return real_get(path)

    monkeypatch.setattr(dep, '_scan_project_imports_uncached', scan)
    monkeypatch.setattr(os, 'scandir', scandir)
    monkeypatch.setattr(dep, 'get_extractor', extractor)
    return state


def request(evaluate):
    started = request_started_ns()
    reset_request_caches()
    try:
        return evaluate()
    finally:
        seal_request_caches(started)


def disclosure(messages):
    assert len(messages) == 1, messages
    text = messages[0]
    assert 'I007' in text and 'missing file population is unknown' in text
    assert 'unused' in text.lower() and 'may' in text.lower()
    return text


@pytest.mark.parametrize('language', ['python', 'rust'])
@pytest.mark.parametrize('already_used', [False, True])
def test_modern_check_directory_loss_is_disclosed_and_incomplete_before_findings(tmp_path, fault, language, already_used):
    manifest, hidden, _helper, used, missing, _ext = project(tmp_path, language, already_used=already_used)
    clean = run('check', str(manifest), '--select', 'I007', '--format', 'json')
    assert clean.returncode == 0 and json.loads(clean.stdout)['total'] == 0
    dep._evict_root(tmp_path)  # explicitly fresh loss and repair controls, not a host-lifetime claim
    fault['mode'] = 'directory'
    lost = run('check', str(manifest), '--select', 'I007', '--format', 'json')
    data = json.loads(lost.stdout)
    assert fault['events'] == [str(hidden.parent)]
    observed = fault['builds'][-1][1]
    assert used in observed.names and observed.skipped == ()
    assert (missing in observed.names) == already_used
    assert data['total'] == (0 if already_used else 1)
    dep._evict_root(tmp_path); fault['mode'] = 'healthy'
    repaired = run('check', str(manifest), '--select', 'I007', '--format', 'json')
    assert repaired.returncode == 0 and repaired.stdout == clean.stdout
    assert lost.returncode == 3
    disclosure(data['scan_disclosures'])


@pytest.mark.parametrize('language', ['python', 'rust'])
@pytest.mark.parametrize('unknown', [False, True])
def test_partial_memo_replays_directory_disclosure_for_rule_and_existing_getter(tmp_path, fault, language, unknown):
    manifest, hidden, helper, used, missing, _ext = project(tmp_path, language)
    fault.update(mode='directory', unknown=unknown)
    first = I007(); detections = first.check(str(manifest), None, '')
    assert [d.context.split(': ')[-1] for d in detections] == [missing]
    assert fault['events'] == [str(hidden.parent)] and fault['builds'][-1][1].names == {used}
    before = len(fault['builds'])
    second = I007(); assert second.check(str(manifest), None, '') == detections
    assert len(fault['builds']) == before  # useful partial memo in the same invocation
    assert helper(tmp_path).skipped == ()
    assert len(first.outcomes) == len(second.outcomes) == 1
    assert first.outcomes == second.outcomes and first.outcomes[0]['status'] == 'unavailable'
    text = disclosure(get_scan_disclosures([manifest], ['I007'], None))
    assert 'unlocated' in text if unknown else 'included_child' in text
    assert len(fault['builds']) == before


@pytest.mark.parametrize('language', ['python', 'rust'])
def test_transient_build_loss_repairs_next_normal_decorated_request_without_clear(tmp_path, fault, language):
    root = tmp_path / 'project'; sibling = tmp_path / 'sibling'
    manifest, hidden, _helper, _used, missing, extension = project(root, language)
    sibling_manifest, *_ = project(sibling, language)
    clean = mcp_server.reveal_check(str(manifest), select='I007')
    sibling_clean = mcp_server.reveal_check(str(sibling_manifest), select='I007')
    # Actual edit invalidates healthy memo through the normal validator, no manual clear.
    write(root / ('added' + extension), 'x = 1\n' if language == 'python' else 'fn added() {}\n')
    fault['mode'] = 'transient'
    lost = mcp_server.reveal_check(str(manifest), select='I007')
    assert missing in lost and fault['events'] == [str(hidden.parent)]
    assert fault['mode'] == 'healthy'
    before = len(fault['builds'])
    repaired = mcp_server.reveal_check(str(manifest), select='I007')
    assert mcp_server.reveal_check(str(sibling_manifest), select='I007') == sibling_clean
    assert repaired == clean
    assert len(fault['builds']) == before + 1
    assert 'missing file population is unknown' in lost


@pytest.mark.parametrize('language', ['python', 'rust'])
def test_existing_preload_worker_transfer_and_getter_keep_actual_directory_facts(tmp_path, fault, language):
    manifest, hidden, _helper, used, missing, _extension = project(tmp_path, language)
    fault['mode'] = 'directory'
    caches = preload_scan_caches([manifest], tmp_path, ['I007'], None)
    assert fault['events'] == [str(hidden.parent)]
    assert fault['builds'][-1][1].names == {used}
    encoded = pickle.dumps(caches)
    expected = get_scan_disclosures([manifest], ['I007'], None)
    dep._scan_cache.clear()  # simulate existing worker initializer in a clean owner
    fault['mode'] = 'healthy'; before = len(fault['builds'])
    init_scan_caches(pickle.loads(encoded))
    actual = I007(); result = actual.check(str(manifest), None, '')
    assert [d.context.split(': ')[-1] for d in result] == [missing]
    assert len(fault['builds']) == before
    disclosure(expected)
    assert get_scan_disclosures([manifest], ['I007'], None) == expected


@pytest.mark.parametrize('language', ['python', 'rust'])
def test_healthy_host_cache_and_original_pair_protocols_remain_compatible(tmp_path, fault, language):
    manifest, _hidden, helper, used, missing, ext = project(tmp_path, language)
    first = request(lambda: helper(tmp_path)); cache = dep._scan_cache[tmp_path]
    before = len(fault['builds'])
    second = request(lambda: helper(tmp_path))
    assert second == first and dep._scan_cache[tmp_path] is cache
    assert len(fault['builds']) == before
    assert isinstance(first, dep.DeclaredUnused) and first == (frozenset(), ())
    unused, skipped = first
    assert unused == frozenset() and skipped == () and first._fields == ('unused', 'skipped')
    assert first._asdict() == {'unused': frozenset(), 'skipped': ()}
    scanned = dep._scan_project_imports_uncached(tmp_path, frozenset({ext}), str.lower, '.' if language == 'python' else '::')
    names, skipped = scanned
    assert isinstance(scanned, dep.ProjectImports) and names == {used, missing} and skipped == ()
    assert scanned._fields == ('names', 'skipped') and scanned[0] == names
    assert get_scan_disclosures([manifest], ['I007'], None) == []


@pytest.mark.parametrize('language', ['python', 'rust'])
def test_zero_declarations_no_scan_or_disclosure(tmp_path, fault, language):
    manifest, _hidden, helper, *_ = project(tmp_path, language, declarations=False)
    fault['mode'] = 'directory'
    result = helper(tmp_path)
    response = run('check', str(manifest), '--select', 'I007', '--format', 'json')
    assert result == (frozenset(), ()) and fault['events'] == fault['builds'] == []
    assert response.returncode == 0 and json.loads(response.stdout)['total'] == 0
    assert get_scan_disclosures([manifest], ['I007'], None) == []


def test_requirements_duplicate_and_unselected_preload_do_not_scan(tmp_path, fault):
    manifest, _hidden, *_ = project(tmp_path, 'python')
    requirements = write(tmp_path / 'requirements.txt', 'requests\n')
    fault['mode'] = 'directory'
    rule = I007(); assert rule.check(str(requirements), None, '') == [] and rule.outcomes == []
    preload_scan_caches([manifest], tmp_path, ['E501'], None)
    assert fault['builds'] == fault['events'] == []
    assert get_scan_disclosures([requirements], ['I007'], None) == []


@pytest.mark.parametrize('language', ['python', 'rust'])
def test_skipped_source_only_existing_public_policy_is_separate_control(tmp_path, fault, language):
    manifest, hidden, _helper, _used, missing, _ext = project(tmp_path, language)
    fault['mode'] = 'extractor'  # deliberate existing extractor API comparator; no directory failure
    rule = I007(); found = rule.check(str(manifest), None, '')
    assert [d.context.split(': ')[-1] for d in found] == [missing]
    assert len(rule.outcomes) == 1 and rule.outcomes[0]['status'] == 'unavailable'
    assert str(hidden) in rule.outcomes[0]['reason']
    response = run('check', str(manifest), '--select', 'I007', '--format', 'json')
    data = json.loads(response.stdout)
    assert response.returncode == 1 and data['total'] == 1 and data['scan_disclosures'] == []
    assert fault['events'] == [] and get_scan_disclosures([manifest], ['I007'], None) == []
