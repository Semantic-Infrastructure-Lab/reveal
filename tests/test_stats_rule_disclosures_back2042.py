"""Stats scoring reads no cross-file rule scan fact (BACK-2042, reversed by BACK-1884).

BACK-2042 made Stats qualify its scores with the scan-cap and discovery-loss notes of the rules
it ran (D005, I002, T006 ...). BACK-1884 counts the file-local rules only, so those rules no
longer run inside Stats: these tests keep the same real owner losses (denied directory, denied
read, cap, unparsable hidden file) and assert that none reaches a count, a score, a warning or
an exit code, while a crashed file-local rule still does (`check_rules_failed`).
"""
import importlib
import json
import os
import time
from pathlib import Path

import pytest

import reveal
from conftest import _run_reveal_direct as run, needs_forked_workers
from reveal.adapters.stats.adapter import StatsAdapter
from reveal.rules import RuleRegistry
from reveal.rules.bugs.B001 import B001
from reveal.rules.scan_caches import get_scan_disclosures
from reveal.utils.request_cache import request_started_ns, reset_request_caches, seal_request_caches

pytestmark = pytest.mark.component
assert Path(reveal.__file__).resolve().is_relative_to(Path(__file__).resolve().parents[1])
D005 = importlib.import_module('reveal.rules.duplicates.D005')
LITERAL = 'ROUTE_KEYS=["alpha","beta","gamma","delta","epsilon"]\n'


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    aged = time.time_ns() - 60_000_000_000
    os.utime(path, ns=(aged, aged))
    return path


def project(root, *, pool=False, disabled=None, malformed=False):
    write(root / 'pyproject.toml', '[project]\nname="probe"\nversion="0.0.0"\n')
    write(root / 'checked.py', LITERAL)
    write(root / 'other.py', LITERAL)
    write(root / 'included' / 'hidden.py', 'def broken(:\n' if malformed else LITERAL)
    if disabled:
        write(root / '.reveal.yaml', f'root: true\nrules:\n  disable: [{disabled}]\n')
    if pool:
        for number in range(20):
            write(root / f'plain{number}.py', 'VALUE=1\n')
    return root


@pytest.fixture
def observed(tmp_path, monkeypatch):
    state = {'active': False, 'mode': 'healthy', 'hidden': None, 'events': [], 'builds': []}
    log = tmp_path / 'native-events.jsonl'
    real_build, real_scan, real_read, real_rule, real_registry = (
        D005._build_index, os.scandir, Path.read_text, D005.D005.check, RuleRegistry.check_file)
    real_local = B001.check
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')
    monkeypatch.setenv('REVEAL_D005_MAX_FILES', '5000')
    monkeypatch.setenv('REVEAL_I002_MAX_FILES', '20000')
    monkeypatch.setenv('REVEAL_T006_MAX_FILES', '5000')

    def emit(row):
        row['pid'] = os.getpid()
        with log.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row) + '\n')

    def build(root, rule):
        state['active'] = True
        try:
            value = real_build(root, rule)
            state['builds'].append((root, value))
            return value
        finally:
            state['active'] = False

    def scandir(path):
        if state['active'] and state['mode'] == 'directory' and Path(path) == state['hidden']:
            state['events'].append(('directory', str(path)))
            raise PermissionError(13, 'actual Stats D005-only discovery denial', str(path))
        return real_scan(path)

    def read(path, *args, **kwargs):
        if state['active'] and state['mode'] == 'read' and path == state['hidden'] / 'hidden.py':
            state['events'].append(('read', str(path)))
            raise PermissionError(13, 'actual Stats D005-only read denial', str(path))
        return real_read(path, *args, **kwargs)

    def rule(self, *args, **kwargs):
        if state['mode'] == 'owner_crash':
            emit({'kind': 'owner_rule_exception', 'file': args[0]})
            raise RuntimeError('controlled crash of the cross-file rule')
        value = real_rule(self, *args, **kwargs)
        emit({'kind': 'D005_check', 'file': args[0], 'findings': len(value)})
        return value

    def local_rule(self, *args, **kwargs):
        if state['mode'] == 'controlled_crash':
            emit({'kind': 'controlled_rule_exception', 'file': args[0]})
            raise RuntimeError('controlled actual Registry rule-error boundary')
        return real_local(self, *args, **kwargs)

    def registry(cls, *args, **kwargs):
        ledger = kwargs.setdefault('coverage', [])
        value = real_registry(*args, **kwargs)
        emit({'kind': 'registry', 'file': args[0], 'coverage': [
            row for row in ledger if row['rule'] in ('D005', 'I002', 'T006')]})
        return value

    monkeypatch.setattr(D005, '_build_index', build)
    monkeypatch.setattr(os, 'scandir', scandir)
    monkeypatch.setattr(Path, 'read_text', read)
    monkeypatch.setattr(D005.D005, 'check', rule)
    monkeypatch.setattr(B001, 'check', local_rule)
    monkeypatch.setattr(RuleRegistry, 'check_file', classmethod(registry))
    state['log'] = log
    return state


def native_events(observed):
    return [json.loads(line) for line in observed['log'].read_text(encoding='utf-8').splitlines()]


def assert_no_scan_note(result):
    """No scan-cap or discovery-loss note of a cross-file rule, and the count states its rule."""
    warnings = result.get('meta', {}).get('warnings', [])
    assert not [w for w in warnings if w.get('type') == 'analysis_incomplete'], warnings
    assert not [w for w in warnings if w.get('rule')], warnings
    assert result['meta']['issue_count']['rule'] == 'file-local rules only'


@pytest.mark.parametrize('target', ['file', 'element', 'directory'])
@pytest.mark.parametrize('mode', ['directory', 'read', 'cap', 'hidden_parse'])
def test_cross_file_rule_owner_loss_never_reaches_stats_counts_or_scores(
        tmp_path, observed, monkeypatch, target, mode):
    root = project(tmp_path / 'project', malformed=mode == 'hidden_parse')
    observed.update(mode=mode, hidden=root / 'included')
    if mode == 'cap':
        monkeypatch.setenv('REVEAL_D005_MAX_FILES', '2')
    adapter = StatsAdapter(str(root / 'checked.py' if target == 'file' else root))
    result = adapter.get_element('checked.py') if target == 'element' else adapter.get_structure(code_only=True)
    # D005 never ran inside Stats: no index, no scan, so no denied read or directory, and nothing to disclose.
    assert observed['builds'] == [] and observed['events'] == []
    assert not get_scan_disclosures([root / 'checked.py'], ['D005'], None)
    events = native_events(observed)
    assert not [row for row in events if row['kind'] == 'D005_check']
    registry = [row for row in events if row['kind'] == 'registry']
    assert len(registry) == (3 if target == 'directory' else 1)
    assert all(row['coverage'] == [] for row in registry), 'no cross-file rule was even asked'
    # The duplicated literal is D005's finding. It was 1 issue and 98.0 before; it is not a local one.
    if target == 'element':
        assert result['quality']['score'] == 100.0 and result['quality']['local_check_issues'] == 0
    else:
        assert result['summary']['total_files'] == (3 if target == 'directory' else 1)
        checked = next(row for row in result['files'] if row['file'] == 'checked.py')
        assert checked['quality']['local_check_issues'] == 0 and checked['quality']['score'] == 100.0
        if mode == 'hidden_parse' and target == 'directory':
            assert next(row for row in result['files'] if row['file'] == 'included/hidden.py')['parse_degraded']
        else:
            assert all(row['quality']['local_check_issues'] == 0 for row in result['files'])
    assert not result.get('check_rules_failed')
    assert_no_scan_note(result)


@pytest.mark.parametrize('target', ['file', 'element'])
@pytest.mark.parametrize('output_format', ['text', 'json'])
def test_actual_public_stats_and_element_print_the_counting_rule_not_a_rule_disclosure(
        tmp_path, observed, target, output_format):
    root = project(tmp_path / 'project')
    observed.update(mode='read', hidden=root / 'included')
    args = [f'stats://{root}/checked.py'] if target == 'file' else [f'stats://{root}', 'checked.py']
    response = run(*args, '--format', output_format)
    assert observed['events'] == []
    assert response.returncode == 0
    if output_format == 'json':
        assert_no_scan_note(json.loads(response.stdout))
    else:
        assert 'D005' not in response.stdout and 'incomplete' not in response.stdout.lower(), response.stdout
        assert 'file-local rules only' in response.stdout, response.stdout


@pytest.mark.parametrize('query', ['min_lines=99', 'summary_only=true', 'limit=1&offset=1'])
def test_filter_summary_and_pagination_carry_no_rule_loss_and_keep_the_counting_rule(
        tmp_path, observed, monkeypatch, query):
    root = project(tmp_path / 'project')
    monkeypatch.setenv('REVEAL_D005_MAX_FILES', '2')
    result = StatsAdapter(str(root), query).get_structure(code_only=True)
    assert len([row for row in native_events(observed) if row['kind'] == 'registry']) == 3
    assert not get_scan_disclosures([root / 'checked.py'], ['D005'], None)
    if query == 'min_lines=99':
        assert result['summary']['total_files'] == 0 and result['files'] == []
    if query == 'summary_only=true':
        assert 'files' not in result
    assert_no_scan_note(result)


@pytest.mark.parametrize('code', ['I002', 'T006'])
def test_other_cross_file_rule_caps_do_not_reach_stats(tmp_path, observed, monkeypatch, code):
    root = project(tmp_path / code)
    monkeypatch.setenv(f'REVEAL_{code}_MAX_FILES', '2')
    result = StatsAdapter(str(root / 'checked.py')).get_structure()
    registry = [row for row in native_events(observed) if row['kind'] == 'registry']
    assert registry and all(row['coverage'] == [] for row in registry), f'{code} was asked for'
    assert not get_scan_disclosures([root / 'checked.py'], [code], None), f'{code} built an index'
    assert_no_scan_note(result)


@pytest.mark.parametrize('target', ['file', 'element', 'directory'])
def test_controlled_file_local_rule_crash_keeps_counts_and_score_direction_distinct(tmp_path, observed, target):
    root = project(tmp_path / 'project')
    observed['mode'] = 'controlled_crash'
    adapter = StatsAdapter(str(root / 'checked.py' if target == 'file' else root))
    result = adapter.get_element('checked.py') if target == 'element' else adapter.get_structure(code_only=True)
    assert any(row['kind'] == 'controlled_rule_exception' for row in native_events(observed))
    assert not get_scan_disclosures([root / 'checked.py'], ['D005'], None)
    warnings = [row for row in result.get('meta', {}).get('warnings', []) if row.get('type') == 'check_rules_failed']
    assert warnings, result
    assert 'counts' in warnings[0]['message'] and 'lower bound' in warnings[0]['message']
    assert 'optimistic' in warnings[0]['message'], warnings[0]


@pytest.mark.parametrize('target', ['file', 'directory'])
def test_a_crash_of_the_cross_file_rule_is_not_a_stats_failure(tmp_path, observed, target):
    """Negative control: the owner is not run, so its crash is not a check_rules_failed."""
    root = project(tmp_path / 'project')
    observed['mode'] = 'owner_crash'
    adapter = StatsAdapter(str(root / 'checked.py' if target == 'file' else root))
    result = adapter.get_structure(code_only=True)
    assert not [row for row in native_events(observed) if row['kind'] == 'owner_rule_exception']
    assert not [row for row in result.get('meta', {}).get('warnings', [])
                if row.get('type') == 'check_rules_failed']
    assert not result.get('check_rules_failed')


@needs_forked_workers
@pytest.mark.real_worker_pool
@pytest.mark.parametrize('mode', ['directory', 'cap', 'disabled_cap'])
def test_actual_pool_runs_file_local_rules_only_and_builds_no_index(
        tmp_path, observed, monkeypatch, mode):
    root = project(tmp_path / 'project', pool=True, disabled='D005' if mode == 'disabled_cap' else None)
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '2')
    monkeypatch.setenv('REVEAL_D005_MAX_FILES', '2' if 'cap' in mode else '5000')
    observed.update(mode=mode, hidden=root / 'included')
    result = StatsAdapter(str(root)).get_structure(code_only=True)
    events = native_events(observed)
    assert result['summary']['total_files'] == 23
    assert observed['builds'] == [] and observed['events'] == [], 'the parent preloaded an index'
    assert not get_scan_disclosures([root / 'checked.py'], ['D005'], None)
    registry = [row for row in events if row['kind'] == 'registry']
    assert len(registry) == 23 and any(row['pid'] != os.getpid() for row in registry)
    assert [row for row in events if row['kind'] == 'D005_check'] == []
    assert all(row['coverage'] == [] for row in registry)
    assert not result.get('meta', {}).get('warnings')
    assert all(row['quality']['local_check_issues'] == 0 for row in result['files'])


def request(call):
    started = request_started_ns()
    reset_request_caches()
    try:
        return call()
    finally:
        seal_request_caches(started)


def test_same_adapter_answers_alike_whether_or_not_a_rule_owner_loses_files(tmp_path, observed):
    root = project(tmp_path / 'project')
    sibling = project(tmp_path / 'sibling')
    adapter = StatsAdapter(str(root))
    observed.update(mode='directory', hidden=root / 'included')
    lost = request(lambda: adapter.get_structure(code_only=True))
    assert observed['events'] == [] and not get_scan_disclosures([root / 'checked.py'], ['D005'], None)
    observed['mode'] = 'healthy'
    repaired = request(lambda: adapter.get_structure(code_only=True))
    assert repaired == lost, 'a denied directory in a rule owner scan changed the answer'
    assert request(lambda: adapter.get_structure(code_only=True)) == repaired
    other = request(lambda: StatsAdapter(str(sibling)).get_structure(code_only=True))
    assert not other.get('meta', {}).get('warnings')
    assert repaired['summary']['avg_quality_score'] == 100.0
    assert_no_scan_note(lost)


@pytest.mark.parametrize('code', ['D005', 'I002', 'T006'])
def test_disabled_rule_controls_are_not_scan_loss(tmp_path, observed, monkeypatch, code):
    root = project(tmp_path / code, disabled=code)
    monkeypatch.setenv(f'REVEAL_{code}_MAX_FILES', '2')
    result = StatsAdapter(str(root / 'checked.py')).get_structure()
    assert not get_scan_disclosures([root / 'checked.py'], [code], None)
    assert not result.get('meta', {}).get('warnings')
    ledger = next(row for row in native_events(observed) if row['kind'] == 'registry')['coverage']
    assert ledger == [], 'a cross-file rule is not asked, so it is not even recorded as disabled'


def test_genuine_empty_stats_is_not_incomplete(tmp_path, observed):
    root = tmp_path / 'empty'; root.mkdir()
    result = StatsAdapter(str(root)).get_structure(code_only=True)
    assert result['summary']['total_files'] == 0 and not result.get('meta', {}).get('warnings')
    assert observed['events'] == observed['builds'] == []


def test_all_rules_disabled_ignores_unused_existing_preloaded_cap(tmp_path, observed, monkeypatch):
    from reveal.rules.scan_caches import preload_scan_caches
    root = project(tmp_path / 'disabled_all')
    write(root / '.reveal.yaml', 'root: true\nrules:\n  enabled: false\n')
    monkeypatch.setenv('REVEAL_D005_MAX_FILES', '2')
    files = [root / 'checked.py', root / 'other.py', root / 'included' / 'hidden.py']
    preload_scan_caches(files, root, None, None)
    assert len(observed['builds']) == 1 and get_scan_disclosures(files, ['D005'], None)
    result = StatsAdapter(str(root / 'checked.py')).get_structure()
    assert result['files'][0]['quality']['local_check_issues'] == 0
    assert not result.get('meta', {}).get('warnings')
    assert not any(row['kind'] == 'D005_check' for row in native_events(observed))
    ledger = next(row for row in native_events(observed) if row['kind'] == 'registry')['coverage']
    assert ledger and all(row['status'] == 'skipped' for row in ledger)


def test_plain_legacy_metrics_mock_return_pair_remains_compatible(tmp_path, observed):
    from unittest.mock import patch
    from reveal.adapters.stats import metrics
    root = project(tmp_path / 'pair')
    pair = ({'critical': 0, 'high': 0, 'medium': 0, 'low': 0}, [])
    with patch.object(metrics, '_count_local_check_issues', return_value=pair):
        result = StatsAdapter(str(root / 'checked.py')).get_structure()
    assert result['files'][0]['quality']['local_check_issues'] == 0
    assert not result.get('meta', {}).get('warnings')
