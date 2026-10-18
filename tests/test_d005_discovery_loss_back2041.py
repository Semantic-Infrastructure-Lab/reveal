"""Old-API semantic D005 directory-loss evidence; no proposed facts API required."""
import copy
import importlib
import json
import os
import time
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal import mcp_server
from reveal.cli import file_checker
from reveal.utils import request_cache
from reveal.utils.exclusions import exclusion_scope
from reveal.utils.query_control import ScanBudget

mod = importlib.import_module('reveal.rules.duplicates.D005')
pytestmark = pytest.mark.component
LITERAL = 'ROUTE_KEYS=["alpha","beta","gamma","delta","epsilon"]\n'


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    aged = time.time_ns() - 60_000_000_000
    os.utime(path, ns=(aged, aged))
    return path


def project(root, profile='threshold'):
    write(root / 'pyproject.toml', '[project]\nname="source-loss"\nversion="0.0.0"\n')
    checked = write(root / 'checked.py', LITERAL)
    if profile == 'cap':
        hidden = root / 'a_hidden'
        write(hidden / 'hidden.py', LITERAL)
        for n in range(3):
            write(root / 'z_tail' / f'tail{n}.py', LITERAL)
    else:
        hidden = root / 'included_child'
        for n in range(2 if profile == 'positive' else 1):
            text = LITERAL if profile != 'clean-zero' else f'OTHER_{n}=[10,11,12,13,{n+20}]\n'
            write(root / f'visible{n}.py', text)
        write(hidden / 'hidden.py', LITERAL if profile != 'clean-zero' else 'OTHER=[30,31,32,33,34]\n')
    return checked, hidden


@pytest.fixture
def fault(monkeypatch):
    state = {'active': False, 'enabled': False, 'root': None, 'unknown': False,
             'events': [], 'builds': [], 'parses': [], 'checks': [], 'stamps': [], 'failed_file': None}
    real_build, real_scandir, real_walk = mod._build_index, os.scandir, os.walk
    real_parse, real_file, real_check = mod.parse_python, mod._file_literals, file_checker.check_and_collect_file
    real_stamp = request_cache._tree_stamp

    def build(*args, **kwargs):
        state['active'] = True
        try:
            result = real_build(*args, **kwargs)
            state['builds'].append((Path(args[0]), copy.deepcopy(result.scan_budget)))
            return result
        finally:
            state['active'] = False

    def scandir(path):
        if state['active'] and state['enabled'] and (Path(path) == state['root'] or Path(path).name in {'included_child', 'a_hidden'}):
            state['events'].append(str(path))
            if state['unknown']:
                raise PermissionError('actual unnamed D005 source loss')
            raise PermissionError(13, 'actual D005 source loss', str(path))
        return real_scandir(path)

    def walk(*args, **kwargs):
        for root, dirs, files in real_walk(*args, **kwargs):
            if state['active']:
                dirs.sort(); files.sort()  # test-only real walk ordering: denial precedes cap
            yield root, dirs, files

    def parse(*args, **kwargs):
        result = real_parse(*args, **kwargs)
        if state['active']:
            state['parses'].append(str(args[1]))
        return result

    def file_literals(path, rule):
        if state['active'] and path == state['failed_file']:
            raise OSError('injected existing file-extraction comparator')
        return real_file(path, rule)

    def check(*args, **kwargs):
        result = real_check(*args, **kwargs)
        state['checks'].append(result[2])
        return result

    def stamp(*args, **kwargs):
        result = real_stamp(*args, **kwargs)
        state['stamps'].append((result, state['active']))
        return result

    # CI runs with the disk cache on (ci-local.sh forces it off): a warm entry from the clean run
    # would skip the parses this test counts.
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    monkeypatch.setattr(mod, '_build_index', build)
    monkeypatch.setattr(os, 'scandir', scandir)
    monkeypatch.setattr(os, 'walk', walk)
    monkeypatch.setattr(mod, 'parse_python', parse)
    monkeypatch.setattr(mod, '_file_literals', file_literals)
    monkeypatch.setattr(file_checker, 'check_and_collect_file', check)
    monkeypatch.setattr(request_cache, '_tree_stamp', stamp)
    return state


def native(root, *flags):
    return run('check', str(root), '--select', 'D005', *flags)


def budget(data):
    row, = [r for r in data['summary']['scan_budgets'] if r['rule'] == 'D005']
    return row


def directory_note(messages):
    notes = [text for text in messages if 'missing file population is unknown' in text]
    assert len(notes) == 1, messages
    assert 'D005' in notes[0] and ('literal' in notes[0].lower() or 'duplicate' in notes[0].lower())
    return notes[0]


@pytest.mark.parametrize('profile', ['positive', 'threshold', 'clean-zero', 'root-known', 'root-unknown'])
def test_native_actual_source_loss_keeps_outer_population_healthy_and_own_count_inexact(tmp_path, fault, profile):
    checked, hidden = project(tmp_path, profile)
    clean = native(tmp_path, '--format', 'json'); clean_data = json.loads(clean.stdout)
    assert budget(clean_data)['exact'] and clean_data['summary']['total_issues'] == (0 if profile == 'clean-zero' else (4 if profile == 'positive' else 3))
    mod._evict_root(tmp_path)
    fault.update(enabled=True, root=tmp_path if profile.startswith('root-') else None,
                 unknown=profile == 'root-unknown')
    lost = native(tmp_path, '--format', 'json'); data = json.loads(lost.stdout)
    assert fault['events'] == [str(tmp_path if profile.startswith('root-') else hidden)]
    assert data['scope'] == clean_data['scope']
    assert all(status == {'status': 'ok'} for status in fault['checks'])
    expected = 0 if profile.startswith('root-') else (3 if profile == 'positive' else 2)
    row = budget(data)
    assert row['total'] == row['returned'] == row['analyzed_files'] == expected
    assert row['failed_files'] == 0 and not row['skipped']
    assert len(fault['parses']) == budget(clean_data)['analyzed_files'] + expected
    fault['enabled'] = False; mod._evict_root(tmp_path)
    repair = native(tmp_path, '--format', 'json')
    assert repair.returncode == clean.returncode and repair.stdout == clean.stdout
    assert row['exact'] is False
    assert lost.returncode == 3
    directory_note(data['summary']['scan_disclosures'])


@pytest.mark.parametrize('view', ['text', 'cap-zero', 'artifact', 'severity', 'grep', 'exit-zero'])
def test_public_cuts_filters_artifact_and_grep_cannot_hide_source_loss(tmp_path, fault, view):
    _checked, hidden = project(tmp_path, 'positive')
    artifact = tmp_path.parent / (tmp_path.name + '-artifact.json')
    flags = ['--format', 'grep' if view == 'grep' else ('text' if view in {'text', 'artifact'} else 'json')]
    if view == 'cap-zero': flags += ['--max-items', '0']
    if view == 'artifact': flags += ['--also-json', str(artifact)]
    if view == 'severity': flags += ['--severity', 'high']
    if view == 'exit-zero': flags += ['--exit-zero']
    # First establish the exact existing flag route reaches a valid clean result.
    control = native(tmp_path, *flags)
    assert control.returncode in {0, 1}
    mod._evict_root(tmp_path); fault['enabled'] = True
    answer = native(tmp_path, *flags)
    assert fault['events'] == [str(hidden)] and all(s == {'status': 'ok'} for s in fault['checks'])
    assert answer.returncode == (0 if view == 'exit-zero' else 3)
    if view == 'grep':
        assert 'missing file population' not in answer.stdout
        assert all(':D005:' in line for line in answer.stdout.splitlines())
        assert answer.stderr.count('missing file population is unknown') == 1
    elif view in {'text', 'artifact'}:
        assert answer.stdout.count('missing file population is unknown') == 1
        if view == 'artifact': directory_note(json.loads(artifact.read_text(encoding='utf-8'))['summary']['scan_disclosures'])
    else:
        data = json.loads(answer.stdout)
        directory_note(data['summary']['scan_disclosures'])
        assert budget(data)['exact'] is False
        if view == 'severity': assert data['summary']['total_issues'] == 0


@pytest.mark.parametrize('profile', ['positive', 'threshold'])
def test_build_only_transient_loss_recovers_next_normal_host_request_without_clear(tmp_path, fault, profile):
    root = tmp_path / 'project'; checked, hidden = project(root, profile)
    sibling = tmp_path / 'sibling'; sibling_checked, _ = project(sibling, profile)
    clean = mcp_server.reveal_check(str(checked), select='D005')
    sibling_clean = mcp_server.reveal_check(str(sibling_checked), select='D005')
    sibling_index = mod._project_index[sibling]
    write(root / 'added.py', 'VALUE=1\n')  # actual edit, normal validator invalidates clean memo
    fault['enabled'] = True
    lost = mcp_server.reveal_check(str(checked), select='D005')
    assert fault['events'] == [str(hidden)]
    partial = mod._project_index[root]
    fault['enabled'] = False; before = len(fault['builds'])
    repaired = mcp_server.reveal_check(str(checked), select='D005')
    warm = mcp_server.reveal_check(str(checked), select='D005')
    assert mcp_server.reveal_check(str(sibling_checked), select='D005') == sibling_clean
    assert mod._project_index[sibling] is sibling_index
    assert all(value and not active for value, active in fault['stamps'])
    assert repaired == clean
    assert warm == repaired and len(fault['builds']) == before + 1
    assert mod._project_index[root] is not partial
    assert 'missing file population is unknown' in lost


@pytest.mark.parametrize('unknown', [False, True])
def test_full_actual_directory_sequence_has_public_disclosure_before_display_cap(tmp_path, fault, unknown):
    checked, hidden = project(tmp_path)
    for n in range(6): write(tmp_path / f'part{n}' / 'included_child' / 'copy.py', LITERAL)
    fault.update(enabled=True, unknown=unknown)
    assert mod.D005().check(str(checked), None, '') == []
    assert len(fault['events']) == 7 and len(fault['parses']) == 2
    note = directory_note(mod.get_scan_disclosures([checked]))
    if unknown:
        assert '0 identified directory' in note and '7 enumeration error event(s)' in note
    else:
        assert '7 identified directory' in note and 'and 2 more' in note


def test_loss_before_cap_preserves_real_lookahead_and_adds_directory_reason(tmp_path, fault, monkeypatch):
    checked, hidden = project(tmp_path, 'cap')
    monkeypatch.setenv('REVEAL_D005_MAX_FILES', '2'); fault['enabled'] = True
    assert mod.D005().check(str(checked), None, '') == []
    assert fault['events'] == [str(hidden)] and fault['parses'] == []
    row, = mod.get_scan_budgets([checked])
    assert (row['total'], row['returned'], row['exact']) == (3, 2, False)
    assert row['analyzed_files'] == row['failed_files'] == 0 and row['skipped']
    notes = mod.get_scan_disclosures([checked])
    assert sum('exceeds 2 .py files' in text for text in notes) == 1
    directory_note(notes)


def test_file_failure_and_directory_loss_remain_separate_observed_accounting(tmp_path, fault):
    checked, hidden = project(tmp_path, 'positive')
    fault.update(enabled=True, failed_file=tmp_path / 'visible0.py')
    assert mod.D005().check(str(checked), None, '') == []
    assert fault['events'] == [str(hidden)]
    row, = mod.get_scan_budgets([checked])
    assert (row['total'], row['returned'], row['analyzed_files'], row['failed_files']) == (3, 3, 2, 1)
    notes = mod.get_scan_disclosures([checked])
    assert any('1 file(s)' in text and 'not analyzed' in text for text in notes)
    directory_note(notes)
    assert row['exact'] is False


def test_existing_three_positional_constructor_and_mapping_protocol_are_unchanged():
    index = mod.LiteralIndex(ScanBudget(2), 2, True)
    assert isinstance(index, dict) and index == {} and list(index) == []
    assert index.scan_budget == {'scope': 'scan', 'total': 3, 'returned': 2, 'exact': False,
                                 'limit': 2, 'analyzed_files': 0, 'failed_files': 0, 'skipped': True}
    assert index.disclosures == []


def test_cap_only_validated_memo_reuse_and_disclosure_are_preserved(tmp_path, fault, monkeypatch):
    checked, _ = project(tmp_path, 'cap')
    monkeypatch.setenv('REVEAL_D005_MAX_FILES', '2')
    first = mcp_server.reveal_check(str(checked), select='D005'); artifact = mod._project_index[tmp_path]
    before = len(fault['builds'])
    second = mcp_server.reveal_check(str(checked), select='D005')
    assert first == second and 'exceeds 2 .py files' in first
    assert mod._project_index[tmp_path] is artifact and len(fault['builds']) == before
    assert fault['events'] == []


@pytest.mark.parametrize('policy', ['report-exclude', 'gitignore'])
def test_existing_evidence_scope_is_preserved(tmp_path, fault, policy):
    checked, hidden = project(tmp_path)
    if policy == 'report-exclude':
        with exclusion_scope(tmp_path, ['included_child']):
            assert len(mod.D005().check(str(checked), None, '')) == 1
    else:
        write(tmp_path / '.gitignore', 'included_child/\n'); fault['enabled'] = True
        assert mod.D005().check(str(checked), None, '') == []
        assert fault['events'] == []
    row, = mod.get_scan_budgets([checked])
    assert row['exact'] and row['failed_files'] == 0
    assert mod.get_scan_disclosures([checked]) == []


def test_existing_file_extraction_failure_is_exact_enumeration_control(tmp_path, fault):
    checked, hidden = project(tmp_path)
    fault['failed_file'] = hidden / 'hidden.py'  # explicit extractor seam injection, not natural read proof
    assert mod.D005().check(str(checked), None, '') == []
    row, = mod.get_scan_budgets([checked])
    assert (row['total'], row['returned'], row['analyzed_files'], row['failed_files']) == (3, 3, 2, 1)
    assert row['exact'] and not row['skipped'] and fault['events'] == []
    assert any('hidden.py' in text and 'OSError' in text for text in mod.get_scan_disclosures([checked]))


def test_existing_check_fields_route_rejects_before_discovery(tmp_path, fault):
    project(tmp_path)
    fault['enabled'] = True
    answer = native(tmp_path, '--format', 'json', '--fields', 'summary')
    assert answer.returncode == 2 and '--fields' in answer.stderr
    assert fault['builds'] == fault['events'] == []
