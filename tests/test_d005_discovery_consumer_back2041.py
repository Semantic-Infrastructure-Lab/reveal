"""Independent D005 source-loss/accounting/cache consumers at existing APIs."""
import importlib
import json
import os
import time
from pathlib import Path

import pytest

import reveal
from conftest import _run_reveal_direct as run
from reveal.cli import file_checker as fc
from reveal.utils import request_cache
from reveal.utils.query_control import ScanBudget

rule = importlib.import_module('reveal.rules.duplicates.D005')
pytestmark = pytest.mark.component
assert Path(reveal.__file__).resolve().is_relative_to(Path(__file__).resolve().parents[1])
LITERAL = 'ROUTE_KEYS = ["alpha", "beta", "gamma", "delta", "epsilon"]\n'


def _write(path, content=LITERAL):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    aged = time.time_ns() - 60_000_000_000
    os.utime(path, ns=(aged, aged))
    return path


def _project(root, survivors=2):
    _write(root / 'pyproject.toml', '[project]\nname="d005-independent"\nversion="0.0.0"\n')
    checked = _write(root / 'checked.py')
    for index in range(survivors - 1):
        _write(root / f'visible{index}.py')
    hidden = _write(root / 'a_hidden' / 'hidden.py').parent
    return root, checked, hidden


@pytest.fixture
def project(tmp_path):
    return _project(tmp_path / 'project')


@pytest.fixture
def observed(monkeypatch):
    state = {'active': False, 'denied': set(), 'unknown': False, 'transient': False,
             'read_failures': set(), 'events': [], 'builds': [], 'collections': [], 'checks': [], 'stamps': []}
    real_build, real_scan, real_read, real_walk = rule._build_index, os.scandir, Path.read_text, os.walk
    real_collect, real_check, real_stamp = fc.collect_files_to_check, fc.check_and_collect_file, request_cache._tree_stamp
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')

    def build(root, instance):
        state['active'] = True
        try:
            result = real_build(root, instance)
            state['builds'].append((root, result))
            return result
        finally:
            state['active'] = False
            if state['transient']:
                state['denied'] = set()  # Actual build error ends before normal host sealing.

    def scandir(path):
        if state['active'] and Path(path).resolve() in state['denied']:
            state['events'].append(Path(path).resolve())
            if state['unknown']:
                raise PermissionError('actual unlocated independent D005 source loss')
            raise PermissionError(13, 'actual independent D005 source loss', str(path))
        return real_scan(path)

    def read_text(path, *args, **kwargs):
        if state['active'] and path.name in state['read_failures']:
            raise PermissionError(13, 'actual build-only literal read loss', str(path))
        return real_read(path, *args, **kwargs)

    def walk(*args, **kwargs):
        for root, dirs, files in real_walk(*args, **kwargs):
            if state['active']:
                dirs.sort()
                files.sort()  # Deterministic cap ordering only; real enumeration remains.
            yield root, dirs, files

    def collect(*args, **kwargs):
        assert not state['active']
        result = real_collect(*args, **kwargs)
        state['collections'].append(result)
        return result

    def checked(*args, **kwargs):
        assert not state['active']
        result = real_check(*args, **kwargs)
        state['checks'].append((Path(args[0]), result[0], result[2]))
        return result

    def stamp(root, *args, **kwargs):
        assert not state['active']
        result = real_stamp(root, *args, **kwargs)
        state['stamps'].append((root, result))
        return result

    monkeypatch.setattr(rule, '_build_index', build)
    monkeypatch.setattr(os, 'scandir', scandir)
    monkeypatch.setattr(Path, 'read_text', read_text)
    monkeypatch.setattr(os, 'walk', walk)
    monkeypatch.setattr(fc, 'collect_files_to_check', collect)
    monkeypatch.setattr(fc, 'check_and_collect_file', checked)
    monkeypatch.setattr(request_cache, '_tree_stamp', stamp)
    return state


def _check(root, *flags):
    return run('check', str(root), '--select', 'D005', *flags)


def _budget(data):
    row, = [row for row in data['summary']['scan_budgets'] if row['rule'] == 'D005']
    return row


def _directory_note(notes):
    matching = [note for note in notes if 'directory enumeration' in note]
    assert len(matching) == 1, notes
    note = matching[0]
    assert 'D005' in note and 'missing file population is unknown' in note
    return note


@pytest.mark.parametrize('unknown', [False, True])
def test_seven_build_only_errors_preserve_observed_budget_and_outer_population(project, observed, unknown):
    root, _, hidden = project
    denied = {hidden, *[_write(root / f'blocked{index}' / 'hidden.py').parent for index in range(6)]}
    observed.update(denied=denied, unknown=unknown)
    response = _check(root, '--format', 'json')
    data = json.loads(response.stdout)
    row = _budget(data)
    assert set(observed['events']) == denied and len(observed['events']) == 7
    assert len(observed['builds']) == len(observed['collections']) == 1
    assert data['summary']['files_checked'] == len(observed['checks']) == 10  # Nine Python + TOML.
    assert all(status['status'] == 'ok' for _, _, status in observed['checks'])
    assert (row['total'], row['returned'], row['analyzed_files'], row['failed_files']) == (2, 2, 2, 0)
    assert row['exact'] is False, row
    assert response.returncode == 3
    note = _directory_note(data['summary']['scan_disclosures'])
    assert root.as_posix() in note
    assert ('0 identified directory' if unknown else '7 identified directory') in note
    assert ('7 enumeration error event(s)' if unknown else 'and 2 more') in note


@pytest.mark.parametrize('view', ['cap0', 'severity', 'text-artifact', 'grep-artifact', 'exit-zero'])
def test_surviving_cluster_and_source_loss_are_not_hidden_by_consumer_views(tmp_path, observed, view):
    root, _, hidden = _project(tmp_path / 'positive', survivors=3)
    observed['denied'] = {hidden}
    artifact = tmp_path / 'answer.json'
    flags = {'cap0': ['--format', 'json', '--max-items', '0'],
             'severity': ['--format', 'json', '--severity', 'critical'],
             'text-artifact': ['--also-json', str(artifact)],
             'grep-artifact': ['--format', 'grep', '--also-json', str(artifact)],
             'exit-zero': ['--format', 'json', '--exit-zero']}[view]
    response = _check(root, *flags)
    assert observed['events'] == [hidden]
    assert all(status['status'] == 'ok' for _, _, status in observed['checks'])
    assert response.returncode == (0 if view == 'exit-zero' else 3), (response.stdout, response.stderr)
    data = json.loads(artifact.read_text(encoding='utf-8') if 'artifact' in view else response.stdout)
    assert data['summary']['total_issues'] == (0 if view == 'severity' else 3)
    assert _budget(data)['total'] == 3 and _budget(data)['exact'] is False
    _directory_note(data['summary']['scan_disclosures'])
    if view == 'cap0':
        assert all(not row['detections'] for row in data['files'])
    if view == 'grep-artifact':
        assert response.stdout.count(':D005:') == 3
        assert 'directory enumeration' in response.stderr and 'directory enumeration' not in response.stdout


@pytest.mark.parametrize('unknown', [False, True])
def test_empty_source_index_is_still_incomplete_in_ordinary_mcp_answer(project, observed, unknown):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_check
    root, checked, _ = project
    observed.update(denied={root}, unknown=unknown)
    answer = reveal_check(str(checked), select='D005')
    assert observed['events'] == [root] and rule._project_index[root] == {}
    assert type(answer) is str
    note = _directory_note(answer.splitlines())
    assert root.as_posix() in note
    assert 'No findings in the checked population; scan incomplete.' in answer
    assert 'No issues found.' not in answer


@pytest.mark.parametrize('unknown_root', [False, True])
def test_transient_loss_before_healthy_seal_rebuilds_next_request_without_clears(tmp_path, observed, unknown_root):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_check
    root, checked, hidden = _project(tmp_path / 'primary')
    sibling, sibling_file, _ = _project(tmp_path / 'sibling')
    baseline = reveal_check(str(checked), select='D005')
    other = reveal_check(str(sibling_file), select='D005')
    sibling_index = rule._project_index[sibling]
    _write(root / 'added.py', 'VALUE=1\n')  # Ordinary tree edit invalidates the previously healthy index.
    before = len(observed['builds'])
    observed.update(denied={root} if unknown_root else {hidden}, unknown=unknown_root, transient=True)
    lost = reveal_check(str(checked), select='D005')
    partial = rule._project_index[root]
    assert len(observed['builds']) == before + 1 and len(observed['events']) == 1
    assert observed['denied'] == set() and observed['stamps']
    assert all(stamp is not None for _, stamp in observed['stamps'])
    repaired = reveal_check(str(checked), select='D005')
    assert len(observed['builds']) == before + 2, 'A healthy seal must not validate a lost-source index'
    assert rule._project_index[root] is not partial
    assert repaired == baseline and 'directory enumeration' in lost
    warm = rule._project_index[root]
    assert reveal_check(str(checked), select='D005') == baseline
    assert rule._project_index[root] is warm and len(observed['builds']) == before + 2
    assert reveal_check(str(sibling_file), select='D005') == other
    assert rule._project_index[sibling] is sibling_index


def test_actual_loss_before_real_cap_keeps_cap_lookahead_and_separate_directory_note(project, observed, monkeypatch):
    root, _, hidden = project
    for index in range(3):
        _write(root / 'z_tail' / f'tail{index}.py')
    observed['denied'] = {hidden}
    monkeypatch.setenv('REVEAL_D005_MAX_FILES', '2')
    response = _check(root, '--format', 'json')
    data = json.loads(response.stdout)
    row = _budget(data)
    assert observed['events'] == [hidden], 'Fixture must reach actual denial before cap'
    assert (row['total'], row['returned'], row['analyzed_files'], row['failed_files']) == (3, 2, 0, 0)
    assert row['exact'] is False and row['skipped'] is True and response.returncode == 3
    _directory_note(data['summary']['scan_disclosures'])


def test_six_actual_file_read_failures_cannot_hide_directory_loss_behind_example_cap(project, observed):
    root, _, hidden = project
    for index in range(6):
        _write(root / f'bad{index}.py')
    observed.update(denied={hidden}, read_failures={f'bad{index}.py' for index in range(6)})
    response = _check(root, '--format', 'json')
    data = json.loads(response.stdout)
    row = _budget(data)
    assert observed['events'] == [hidden] and row['failed_files'] == 6 and row['analyzed_files'] == 2
    assert row['total'] == row['returned'] == 8
    assert all(status['status'] == 'ok' for _, _, status in observed['checks'])
    _directory_note(data['summary']['scan_disclosures'])
    assert row['exact'] is False and response.returncode == 3


def test_original_constructor_is_dict_compatible():
    value = rule.LiteralIndex(ScanBudget(2), 2, True)
    value['literal'] = [('file.py', 1, 'KEYS')]
    assert dict(value) == {'literal': [('file.py', 1, 'KEYS')]}
    assert value.scan_budget['total'] == 3 and value.scan_budget['returned'] == 2
    assert value.scan_budget['exact'] is False and value.disclosures == []


@pytest.mark.parametrize('policy', ['gitignore', 'noise', 'report-exclude'])
def test_policy_omissions_and_evidence_report_exclusion_remain_distinct(project, observed, policy):
    root, checked, hidden = project
    flags = []
    if policy == 'gitignore':
        _write(root / '.gitignore', 'a_hidden/\n')
    elif policy == 'noise':
        hidden.rename(root / 'node_modules')
    else:
        flags = ['--exclude', 'a_hidden/']
    response = _check(root, '--format', 'json', *flags)
    data = json.loads(response.stdout)
    row = _budget(data)
    assert observed['events'] == [] and row['exact'] is True
    assert row['total'] == (3 if policy == 'report-exclude' else 2)
    assert response.returncode == (1 if policy == 'report-exclude' else 0)
    assert not any('directory enumeration' in note for note in data['summary']['scan_disclosures'])
    assert rule.get_scan_budgets([checked])[0]['total'] == row['total']


@pytest.mark.parametrize('file_failure', [False, True])
def test_cap_only_or_file_failure_only_index_keeps_validated_warm_reuse(project, observed, monkeypatch, file_failure):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_check
    root, checked, _ = project
    if file_failure:
        observed['read_failures'] = {'visible0.py'}
    else:
        monkeypatch.setenv('REVEAL_D005_MAX_FILES', '2')
    first = reveal_check(str(checked), select='D005')
    index = rule._project_index[root]
    count = len(observed['builds'])
    second = reveal_check(str(checked), select='D005')
    assert second == first and rule._project_index[root] is index and len(observed['builds']) == count
    assert observed['events'] == []
    assert index.scan_budget['exact'] is file_failure
    assert index.scan_budget['failed_files'] == int(file_failure)


def test_unselected_rule_and_existing_unsupported_fields_do_not_build_index(project, observed):
    root, _, hidden = project
    observed['denied'] = {hidden}
    unsupported = _check(root, '--fields', 'summary')
    assert unsupported.returncode == 2 and observed['builds'] == []
    healthy = run('check', str(root), '--select', 'E501', '--format', 'json')
    assert healthy.returncode == 0 and observed['builds'] == observed['events'] == []
