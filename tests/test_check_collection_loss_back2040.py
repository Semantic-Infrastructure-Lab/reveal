"""Existing Check consumers must disclose actual candidate enumeration loss."""
import json
import os
from pathlib import Path

import pytest

import reveal
from conftest import _run_reveal_direct as run
from reveal import mcp_server
from reveal.cli import file_checker as fc
from reveal.utils.path_utils import to_posix

pytestmark = pytest.mark.component
assert Path(reveal.__file__).resolve().is_relative_to(Path(__file__).resolve().parents[1])
LONG = 'LONG = ' + repr('x' * 200) + '\n'


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    return path


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'project'
    write(root / 'visible.py', 'VALUE = 1\n')
    write(root / 'included' / 'hidden.py', LONG)
    return root


@pytest.fixture
def collection_fault(monkeypatch):
    state = {'active': False, 'denied': set(), 'unknown': False,
             'events': [], 'collections': [], 'checked': [], 'attempts': []}
    real_collect, real_scandir, real_check = fc.collect_files_to_check, os.scandir, fc.check_and_collect_file
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')

    def collect(*args, **kwargs):
        state['active'] = True
        try:
            value = real_collect(*args, **kwargs)
            state['collections'].append(value)
            return value
        finally:
            state['active'] = False

    def scandir(path):
        if state['active']:
            state['attempts'].append(Path(path).resolve())
            if Path(path).resolve() in state['denied']:
                state['events'].append(Path(path).resolve())
                if state['unknown']:
                    raise PermissionError('actual unknown Check candidate collection denial')
                raise PermissionError(13, 'actual Check candidate collection denial', str(path))
        return real_scandir(path)

    def check(*args, **kwargs):
        assert not state['active'], 'fault scope must end before inner analyzers or rules run'
        result = real_check(*args, **kwargs)
        state['checked'].append((Path(args[0]), result))
        return result

    monkeypatch.setattr(fc, 'collect_files_to_check', collect)
    monkeypatch.setattr(os, 'scandir', scandir)
    monkeypatch.setattr(fc, 'check_and_collect_file', check)
    return state


def check(root, *flags):
    return run('check', str(root), '--select', 'E501', *flags)


def disclosure(data, root):
    notes = data['summary']['scan_disclosures']
    assert len(notes) == 1, notes
    text = notes[0]
    assert 'director' in text.lower() and 'incomplete' in text.lower()
    assert to_posix(root) in text and 'missing file population is unknown' in text
    return text


@pytest.mark.parametrize('population', ['child_zero', 'child_positive', 'root', 'unknown_root'])
def test_actual_collection_loss_overrides_clean_or_findings_exit(project, collection_fault, population):
    root = project
    if population == 'child_positive':
        write(root / 'visible.py', LONG)
    collection_fault.update(denied={root if 'root' in population else root / 'included'},
                            unknown=population == 'unknown_root')
    response = check(root, '--format', 'json')
    data = json.loads(response.stdout)
    survivors = 0 if 'root' in population else 1
    assert len(collection_fault['events']) == 1
    assert len(collection_fault['collections']) == 1
    assert len(collection_fault['collections'][0].files) == len(collection_fault['checked']) == survivors
    assert data['summary']['files_checked'] == survivors
    assert data['summary']['total_issues'] == (1 if population == 'child_positive' else 0)
    assert all(row[1][2]['status'] == 'ok' for row in collection_fault['checked'])
    assert response.returncode == 3, data
    message = disclosure(data, root)
    assert data['summary'].get('files_errored', 0) == data['summary'].get('files_degraded', 0) == 0
    if population == 'unknown_root':
        assert '0 identified directory' in message and '1 enumeration error event(s)' in message


@pytest.mark.parametrize('fmt', ['text', 'grep'])
@pytest.mark.parametrize('all_lost', [False, True])
def test_human_grep_and_sidecar_disclose_even_before_no_survivor_branch(
        project, collection_fault, tmp_path, fmt, all_lost):
    root = project
    collection_fault['denied'] = {root if all_lost else root / 'included'}
    artifact = tmp_path / 'answer.json'
    response = check(root, '--format', fmt, '--also-json', str(artifact))
    assert len(collection_fault['events']) == 1
    assert response.returncode == 3, (response.stdout, response.stderr)
    assert artifact.exists()
    data = json.loads(artifact.read_text(encoding='utf-8'))
    disclosure(data, root)
    assert data['summary']['files_checked'] == (0 if all_lost else 1)
    if fmt == 'grep':
        assert response.stdout == ''
        assert 'director' in response.stderr.lower() and to_posix(root).lower() in response.stderr.lower()
    else:
        assert 'scan incomplete' in response.stdout.lower()
        assert '✅ No issues found' not in response.stdout
        assert 'No supported files found' not in response.stdout


@pytest.mark.parametrize('view', ['cut_zero', 'severity_hidden', 'provenance', 'exit_zero'])
def test_original_collection_facts_survive_presentation_and_exit_zero(project, collection_fault, view):
    write(project / 'visible.py', LONG)
    collection_fault['denied'] = {project / 'included'}
    flags = {'cut_zero': ['--max-items', '0'], 'severity_hidden': ['--severity', 'critical'],
             'provenance': ['--provenance'], 'exit_zero': ['--exit-zero']}[view]
    response = check(project, '--format', 'json', *flags)
    data = json.loads(response.stdout)
    assert len(collection_fault['events']) == len(collection_fault['checked']) == 1
    assert data['summary']['total_issues'] == (0 if view == 'severity_hidden' else 1)
    assert response.returncode == (0 if view == 'exit_zero' else 3), data
    disclosure(data, project)
    if view == 'cut_zero':
        assert data['summary']['items_truncated']
        assert len(data['files']) == 1 and data['files'][0]['issues'] == 1
        assert data['files'][0]['detections'] == []
    if view == 'provenance':
        assert 'execution' in data


@pytest.mark.parametrize('unknown', [False, True])
def test_seven_actual_enumeration_events_never_become_false_clean_or_lost_file_count(
        tmp_path, collection_fault, unknown):
    root = tmp_path / 'many'
    write(root / 'visible.py', 'VALUE=1\n')
    denied = {write(root / f'blocked{i}' / 'hidden.py', LONG).parent for i in range(7)}
    collection_fault.update(denied=denied, unknown=unknown)
    response = check(root, '--format', 'json')
    data = json.loads(response.stdout)
    assert set(collection_fault['events']) == denied and len(collection_fault['events']) == 7
    assert len(collection_fault['checked']) == data['summary']['files_checked'] == 1
    assert response.returncode == 3, data
    message = disclosure(data, root)
    assert data['summary']['files_errored'] == 0
    if unknown:
        assert '0 identified directory' in message and '7 enumeration error event(s)' in message
    else:
        assert '7 identified directory' in message and 'and 2 more' in message


@pytest.mark.parametrize('all_lost', [False, True])
def test_profile_discloses_collection_loss_without_changing_timing_exit_policy(project, collection_fault, all_lost):
    collection_fault['denied'] = {project if all_lost else project / 'included'}
    response = check(project, '--profile-rules')
    assert len(collection_fault['events']) == 1
    assert response.returncode == 0  # Profiling is not Check's findings/outcome mode.
    assert 'director' in (response.stdout + response.stderr).lower()
    assert 'incomplete' in (response.stdout + response.stderr).lower()
    if all_lost:
        assert 'No supported files found' not in response.stdout
    else:
        assert 'Profiled 1 files, 0 issues' in response.stdout and 'E501' in response.stdout


@pytest.mark.parametrize('population', ['partial_zero', 'partial_positive', 'all_lost', 'unknown_root'])
def test_decorated_check_keeps_ordinary_incomplete_narrative_even_with_no_survivors(
        project, collection_fault, population):
    if population == 'partial_positive':
        write(project / 'visible.py', LONG)
    collection_fault.update(denied={project if population in ('all_lost', 'unknown_root') else project / 'included'},
                            unknown=population == 'unknown_root')
    answer = mcp_server.reveal_check(str(project), select='E501')
    assert type(answer) is str and len(collection_fault['events']) == 1
    assert len(collection_fault['checked']) == (0 if population in ('all_lost', 'unknown_root') else 1)
    assert 'director' in answer.lower() and 'incomplete' in answer.lower(), answer
    assert to_posix(project) in answer and 'missing file population is unknown' in answer
    assert 'No files found' not in answer and 'No issues found.' not in answer
    if population == 'partial_positive':
        assert 'E501' in answer and '1 issue found.' in answer
    else:
        assert 'No findings in the checked population' in answer


@pytest.mark.parametrize('channel', ['native', 'decorated'])
def test_loss_and_repair_are_isolated_in_same_process_without_clears(project, collection_fault, channel):
    sibling = project.parent / 'sibling'
    write(sibling / 'clean.py', 'VALUE=1\n')
    invoke = (lambda path: check(path, '--format', 'json').stdout) if channel == 'native' else (
        lambda path: mcp_server.reveal_check(str(path), select='E501'))
    clean, sibling_clean = invoke(project), invoke(sibling)
    collection_fault['denied'] = {project / 'included'}
    lost = invoke(project)
    assert len(collection_fault['events']) == 1
    collection_fault['denied'] = set()
    assert invoke(project) == clean and invoke(sibling) == sibling_clean
    assert 'incomplete' in lost.lower(), lost


@pytest.mark.parametrize('population', ['empty', 'no_analyzer', 'exclude', 'gitignore', 'noise'])
def test_existing_empty_and_policy_omissions_are_not_enumeration_failures(tmp_path, collection_fault, population):
    root = tmp_path / population
    root.mkdir()
    flags = []
    if population == 'no_analyzer':
        write(root / 'native.m', 'int main(void) { return 0; }\n')
    elif population not in ('empty', 'no_analyzer'):
        write(root / 'visible.py', 'VALUE=1\n')
        hidden = root / ('node_modules' if population == 'noise' else 'included')
        write(hidden / 'hidden.py', LONG)
        collection_fault['denied'] = {hidden}
        if population == 'exclude':
            flags = ['--exclude', 'included/']
        elif population == 'gitignore':
            write(root / '.gitignore', 'included/\n')
    response = check(root, '--format', 'json', *flags)
    data = json.loads(response.stdout)
    assert response.returncode == 0 and collection_fault['events'] == []
    assert data['summary']['total_issues'] == 0 and not data['summary'].get('scan_disclosures')
    assert data['summary']['files_checked'] == (0 if population in ('empty', 'no_analyzer') else 1)
    collection = collection_fault['collections'][0]
    if population == 'no_analyzer':
        assert collection.skipped_no_analyzer == 1
    if population in ('exclude', 'gitignore', 'noise'):
        assert collection.skipped_dirs == 1


def test_historical_five_positional_collection_and_three_positional_collector_shapes(tmp_path):
    result = fc.FileCollectionResult([], 1, 2, 3, {})
    assert result.files == [] and result.skipped_gitignore == 1 and result.skipped_no_analyzer == 2
    assert result.skipped_dirs == 3 and result.no_analyzer_by_language == {}
    assert fc.collect_files_to_check(tmp_path, False, []).files == []


@pytest.mark.parametrize('empty', [False, True])
def test_profile_healthy_timing_and_empty_message_remain_legacy_zero(project, collection_fault, tmp_path, empty):
    target = tmp_path / 'empty_profile' if empty else project
    if empty:
        target.mkdir()
    response = check(target, '--profile-rules')
    assert response.returncode == 0 and collection_fault['events'] == []
    if empty:
        assert response.stdout == f'No supported files found in {to_posix(target)}\n'
    else:
        assert 'Profiled 2 files, 1 issues' in response.stdout and 'E501' in response.stdout
        assert 'incomplete' not in response.stdout + response.stderr
