"""Independent existing Check consumers must retain actual candidate collection loss."""
import json
import os
from pathlib import Path

import pytest

import reveal
from conftest import _run_reveal_direct as run
from reveal.cli import file_checker as fc

pytestmark = pytest.mark.component
assert Path(reveal.__file__).resolve().is_relative_to(Path(__file__).resolve().parents[1])
LONG = 'LONG = ' + repr('x' * 200) + '\n'


def _write(path, content='VALUE = 1\n'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    return path


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'project'
    _write(root / 'visible.py')
    hidden = _write(root / 'included' / 'hidden.py', LONG).parent
    return root, hidden


@pytest.fixture
def observed(monkeypatch):
    state = {'active': False, 'denied': set(), 'unknown': False,
             'walks': [], 'events': [], 'collections': [], 'checks': []}
    real_collect, real_scan, real_check = fc.collect_files_to_check, os.scandir, fc.check_and_collect_file

    def collect(*args, **kwargs):
        state['active'] = True
        try:
            result = real_collect(*args, **kwargs)
            state['collections'].append({'files': list(result.files), 'dirs': result.skipped_dirs,
                                         'gitignore': result.skipped_gitignore,
                                         'no_analyzer': result.skipped_no_analyzer})
            return result
        finally:
            state['active'] = False

    def scandir(path):
        if state['active']:
            state['walks'].append(Path(path).resolve())
            if Path(path).resolve() in state['denied']:
                state['events'].append(Path(path).resolve())
                if state['unknown']:
                    raise PermissionError('actual unlocated Check consumer candidate loss')
                raise PermissionError(13, 'actual Check consumer candidate loss', str(path))
        return real_scan(path)

    def checked(*args, **kwargs):
        assert not state['active'], 'Faults must remain collection-only'
        result = real_check(*args, **kwargs)
        state['checks'].append((Path(args[0]), result[0], result[2]))
        return result

    monkeypatch.setattr(fc, 'collect_files_to_check', collect)
    monkeypatch.setattr(fc, 'check_and_collect_file', checked)
    monkeypatch.setattr(os, 'scandir', scandir)
    return state


def _seven(project):
    root, first = project
    return [first] + [_write(root / f'included{index}' / 'hidden.py', LONG).parent for index in range(6)]


def _run(root, *flags):
    return run('check', str(root), '--select', 'E501', *flags)


@pytest.mark.parametrize('unknown', [False, True])
def test_all_actual_collection_events_reach_summary_without_fabricated_file_counts(project, observed, unknown):
    root, _ = project
    denied = _seven(project)
    observed.update(denied=set(denied), unknown=unknown)
    response = _run(root, '--format', 'json')
    data = json.loads(response.stdout)
    assert set(observed['events']) == set(denied) and len(observed['events']) == 7
    assert len(observed['collections']) == 1
    assert len(observed['walks']) == 8 and set(observed['walks']) == {root, *denied}
    assert len(observed['checks']) == 1 and observed['checks'][0][2]['status'] == 'ok'
    assert data['summary']['files_checked'] == data['scope']['total_code_files'] == 1
    assert data['summary']['files_errored'] == data['summary']['files_degraded'] == 0
    assert data['scope']['skipped_dirs'] == data['scope']['skipped_gitignore'] == 0
    assert response.returncode == 3, (response.stdout, response.stderr)
    note, = data['summary']['scan_disclosures']
    assert ('0 identified directory' if unknown else '7 identified directory') in note
    assert 'missing file population is unknown' in note
    assert ('7 enumeration error event(s)' if unknown else 'and 2 more') in note


@pytest.mark.parametrize('flags', [['--max-items', '0'], ['--severity', 'critical']])
def test_collection_loss_precedes_cut_or_severity_filtered_real_findings(project, observed, flags):
    root, hidden = project
    _write(root / 'visible.py', LONG)
    observed['denied'] = {hidden}
    response = _run(root, '--format', 'json', *flags)
    data = json.loads(response.stdout)
    assert observed['events'] == [hidden]
    assert observed['checks'][0][1] == 1 and observed['checks'][0][2]['status'] == 'ok'
    assert data['summary']['total_issues'] == (0 if '--severity' in flags else 1)
    assert all(not entry['detections'] for entry in data['files'])
    assert response.returncode == 3, (response.stdout, response.stderr)
    assert 'directory enumeration' in data['summary']['scan_disclosures'][0]


@pytest.mark.parametrize('output_format', ['text', 'grep'])
@pytest.mark.parametrize('exit_zero', [False, True])
def test_unknown_empty_collection_retains_warning_and_requested_artifact(project, observed, tmp_path, output_format, exit_zero):
    root, _ = project
    observed.update(denied={root}, unknown=True)
    artifact = tmp_path / 'answer.json'
    flags = ['--format', output_format, '--also-json', str(artifact)] + (['--exit-zero'] if exit_zero else [])
    response = _run(root, *flags)
    assert observed['events'] == [root] and observed['collections'][0]['files'] == []
    assert observed['checks'] == []
    assert response.returncode == (0 if exit_zero else 3), (response.stdout, response.stderr)
    assert 'unknown directory' in response.stdout + response.stderr
    assert 'No supported files found' not in response.stdout
    if output_format == 'grep':
        assert response.stdout == '' and 'directory enumeration' in response.stderr
    data = json.loads(artifact.read_text(encoding='utf-8'))
    assert data['files'] == [] and data['summary']['files_checked'] == 0
    assert data['summary']['files_errored'] == data['summary']['files_degraded'] == 0
    assert data['summary']['exit_code'] == (0 if exit_zero else 3)
    assert 'unknown directory' in data['summary']['scan_disclosures'][0]


@pytest.mark.parametrize('population', ['child-zero', 'root-unknown', 'child-positive', 'filtered'])
def test_ordinary_mcp_notes_disclose_loss_before_zero_or_positive_verdict(project, observed, population):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_check
    root, hidden = project
    if population in ('child-positive', 'filtered'):
        _write(root / 'visible.py', LONG)
    observed.update(denied={root} if population == 'root-unknown' else {hidden},
                    unknown=population == 'root-unknown')
    answer = reveal_check(str(root), select='E501', severity='critical' if population == 'filtered' else '')
    assert type(answer) is str, 'Check preserves ordinary incomplete MCP answers'
    assert len(observed['events']) == 1 and len(observed['collections']) == 1
    assert all(status['status'] == 'ok' for _, _, status in observed['checks'])
    assert 'directory enumeration' in answer, answer
    assert 'No files found' not in answer and 'No issues found.' not in answer
    if population == 'child-positive':
        assert answer.index('directory enumeration') < answer.index('[E501]')
        assert '1 issue found.' in answer
    else:
        assert 'No findings in the checked population; scan incomplete.' in answer


@pytest.mark.parametrize('unknown', [False, True])
def test_collection_loss_does_not_leak_across_persistent_repair_or_sibling_calls(project, observed, tmp_path, unknown):
    root, hidden = project
    sibling = tmp_path / 'sibling'
    _write(sibling / 'healthy.py')
    clean = _run(root, '--format', 'json')
    other = _run(sibling, '--format', 'json')
    observed.update(denied={root} if unknown else {hidden}, unknown=unknown)
    for _ in range(2):
        lost = _run(root, '--format', 'json')
        assert lost.returncode == 3, (lost.stdout, lost.stderr)
        assert 'directory enumeration' in json.loads(lost.stdout)['summary']['scan_disclosures'][0]
    observed['denied'] = set()
    repaired = _run(root, '--format', 'json')
    again = _run(sibling, '--format', 'json')
    assert (repaired.returncode, repaired.stdout, repaired.stderr) == (clean.returncode, clean.stdout, clean.stderr)
    assert (again.returncode, again.stdout, again.stderr) == (other.returncode, other.stdout, other.stderr)


@pytest.mark.parametrize('empty', [False, True])
def test_profiling_discloses_collection_loss_without_adopting_findings_exit(project, observed, empty):
    root, hidden = project
    observed.update(denied={root} if empty else {hidden}, unknown=True)
    response = _run(root, '--profile-rules')
    assert len(observed['events']) == 1
    assert response.returncode == 0
    assert 'directory enumeration' in response.stdout + response.stderr
    if empty:
        assert 'No supported files found' not in response.stdout
    else:
        assert 'Profiled 1 files' in response.stdout and 'E501' in response.stdout


@pytest.mark.parametrize('population', ['single-file', 'no-analyzer', 'policy-pruned', 'empty'])
def test_healthy_policy_and_unavailable_analyzer_controls_do_not_become_loss(project, observed, tmp_path, population):
    root, hidden = project
    target, flags = root, []
    if population == 'single-file':
        target = root / 'visible.py'
        observed['denied'] = {root}
    elif population == 'policy-pruned':
        observed['denied'] = {hidden}
        flags = ['--exclude', 'included/']
    else:
        target = tmp_path / population
        target.mkdir()
        if population == 'no-analyzer':
            _write(target / 'native.m', '@interface Native\n@end\n')
    response = _run(target, '--format', 'json', *flags)
    assert response.returncode == 0, (response.stdout, response.stderr)
    assert not observed['events']
    assert 'directory enumeration' not in response.stdout + response.stderr
    if population == 'no-analyzer':
        assert observed['collections'][0]['files'] == [] and observed['collections'][0]['no_analyzer'] == 1


@pytest.mark.parametrize('flags', [['--fields', 'files'], ['--format', 'grep', '--max-items', '0']])
def test_explicit_legacy_flag_limits_are_preserved(project, observed, flags):
    root, _ = project
    response = _run(root, *flags)
    if '--fields' in flags:
        assert response.returncode == 2 and observed['collections'] == []
        assert 'unrecognized arguments' in response.stderr
    else:
        assert response.returncode == 1
        assert ':E501:' in response.stdout
        assert 'Note: --max-items has no effect' in response.stderr
