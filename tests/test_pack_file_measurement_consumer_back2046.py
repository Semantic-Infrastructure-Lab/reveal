"""Independent Pack FILE loss through existing public output and selection paths."""
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters import pack
from reveal.cli.commands import pack as shim

pytestmark = pytest.mark.component


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'project'
    bad = write(root / 'core' / 'worker.py', 'def execute():\n    return 1\n')
    healthy = write(root / 'other.py', 'VALUE=2\n')
    return root, bad, healthy


@pytest.fixture
def observed(monkeypatch):
    state = {'active': False, 'read_denied': set(), 'stat_denied': set(), 'dir_denied': set(),
             'unknown_filename': False, 'reads': [], 'stats': [], 'directory': [], 'collections': 0}
    real_collect, real_read, real_stat, real_scan = pack._collect_candidates, Path.read_text, Path.stat, os.scandir
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')

    def collect(*args, **kwargs):
        state['active'] = True
        state['collections'] += 1
        try:
            return real_collect(*args, **kwargs)
        finally:
            state['active'] = False

    def fail(path, operation):
        state[operation].append(path)
        if state['unknown_filename']:
            raise PermissionError('actual unlocated Pack candidate FILE measurement loss')
        raise PermissionError(13, 'actual Pack candidate FILE measurement loss', str(path))

    def read(path, *args, **kwargs):
        if state['active'] and path in state['read_denied']:
            fail(path, 'reads')
        return real_read(path, *args, **kwargs)

    def stat(path, *args, **kwargs):
        if state['active'] and path in state['stat_denied']:
            fail(path, 'stats')
        return real_stat(path, *args, **kwargs)

    def scandir(path):
        if state['active'] and Path(path) in state['dir_denied']:
            state['directory'].append(Path(path))
            raise PermissionError(13, 'actual independent Pack directory loss', str(path))
        return real_scan(path)

    monkeypatch.setattr(pack, '_collect_candidates', collect)
    monkeypatch.setattr(shim, '_collect_candidates', collect)  # Existing specialized compatibility import.
    monkeypatch.setattr(Path, 'read_text', read)
    monkeypatch.setattr(Path, 'stat', stat)
    monkeypatch.setattr(os, 'scandir', scandir)
    return state


def invoke(*args):
    try:
        return run(*args)
    except OSError as exc:
        pytest.fail(f'Pack must retain candidate FILE loss and useful siblings instead of aborting: {exc}')


def file_note(data, path):
    notes = [entry for entry in data['meta'].get('warnings', []) if 'measurement' in entry.get('message', '').lower()]
    assert len(notes) == 1, data['meta']
    assert path.as_posix() in json.dumps(notes, ensure_ascii=False)
    assert notes[0].get('unit') != 'directories'
    return notes[0]


@pytest.mark.parametrize('view', ['native-json', 'uri-json', 'uri-fields', 'uri-cap0', 'uri-artifact'])
def test_token_pack_unknown_lines_remain_explicit_through_public_views(project, observed, tmp_path, view):
    root, bad, _ = project
    observed['read_denied'] = {bad}
    artifact = tmp_path / 'answer.json'
    args = ['pack', str(root)] if view == 'native-json' else ['pack://' + str(root)]
    if view == 'uri-artifact':
        args += ['--also-json', str(artifact)]
    else:
        args += ['--format', 'json']
    if view == 'uri-fields':
        args += ['--fields', 'files,meta']
    if view == 'uri-cap0':
        args += ['--max-items', '0']
    response = invoke(*args)
    assert observed['reads'] == [bad] and observed['collections'] == 1
    assert response.returncode == 0, (response.stdout, response.stderr)
    data = json.loads(artifact.read_text(encoding='utf-8') if view == 'uri-artifact' else response.stdout)
    assert data['meta']['total_candidates'] == data['meta']['selected'] == 2
    assert data['meta']['used_tokens_approx'] == 9 and data['meta']['used_lines'] is None
    file_note(data, bad)
    if view == 'uri-cap0':
        assert data['files'] == []
    else:
        row = next(row for row in data['files'] if row['path'] == bad.as_posix())
        assert row['lines'] is None and row['size'] == 28 and row['tokens_approx'] == 7
    if view == 'uri-artifact':
        assert 'None lines' not in response.stdout and ('unavailable' in response.stdout.lower() or 'unknown' in response.stdout.lower())


@pytest.mark.parametrize('budget', ['1-lines', '0-lines', '-1-lines'])
def test_line_budget_excludes_unknown_cost_and_preserves_known_selected_total(project, observed, budget):
    root, bad, healthy = project
    observed['read_denied'] = {bad}
    response = invoke('pack://' + str(root) + '?budget=' + budget, '--format', 'json')
    assert observed['reads'] == [bad] and response.returncode == 0
    data = json.loads(response.stdout)
    expected = int(budget == '1-lines')
    assert data['meta']['selected'] == expected and data['meta']['used_lines'] == expected
    assert data['meta']['total_candidates'] == data['meta']['selected'] + data['meta']['skipped'] == 2
    assert data['meta'].get('line_budget_incomplete') is True
    assert [row['path'] for row in data['files']] == ([healthy.as_posix()] if expected else [])
    file_note(data, bad)


def test_unknown_line_cost_excluded_by_token_size_does_not_null_selected_healthy_total(project, observed):
    root, bad, healthy = project
    observed['read_denied'] = {bad}
    response = invoke('pack://' + str(root) + '?budget=2', '--format', 'json')
    data = json.loads(response.stdout)
    assert observed['reads'] == [bad] and response.returncode == 0
    assert [row['path'] for row in data['files']] == [healthy.as_posix()]
    assert data['meta']['used_lines'] == 1 and 'line_budget_incomplete' not in data['meta']
    file_note(data, bad)


@pytest.mark.parametrize('seam', ['native-verbose', 'uri-text', 'specialized'])
def test_all_stat_loss_reports_unavailable_measurements_instead_of_budget_exclusion(project, observed, seam):
    root, bad, healthy = project
    observed.update(stat_denied={bad, healthy}, unknown_filename=True)
    if seam == 'specialized':
        pytest.importorskip('mcp')
        from reveal.mcp_server import reveal_pack
        try:
            text = reveal_pack(str(root))
        except OSError as exc:
            pytest.fail(f'Ordinary Pack MCP must disclose unavailable measurements: {exc}')
        assert type(text) is str
    else:
        args = ['pack', str(root), '--verbose'] if seam == 'native-verbose' else ['pack://' + str(root)]
        response = invoke(*args)
        assert response.returncode == 0
        text = response.stdout + response.stderr
    assert set(observed['stats']) == {bad, healthy} and observed['collections'] == 1
    assert 'measurement' in text.lower() and 'unavailable' in text.lower()
    assert 'No files fit within budget.' not in text
    assert bad.as_posix() in text and healthy.as_posix() in text


def test_stat_loss_and_directory_loss_remain_independent_before_projection(project, observed):
    root, bad, healthy = project
    hidden = write(root / 'included' / 'hidden.py', 'HIDDEN=1\n').parent
    observed.update(stat_denied={bad}, dir_denied={hidden})
    response = invoke('pack://' + str(root), '--format', 'json', '--max-items', '0')
    assert response.returncode == 0 and observed['stats'] == [bad] and observed['directory'] == [hidden]
    data = json.loads(response.stdout)
    assert data['meta']['total_candidates'] == data['meta']['selected'] == 1 and data['files'] == []
    file_note(data, bad)
    directories = [w for w in data['meta']['warnings'] if w.get('unit') == 'directories']
    assert len(directories) == 1 and directories[0]['count'] == 1
    assert data['meta']['used_lines'] == 1 and healthy.as_posix() not in json.dumps(directories)


def test_stat_loss_survivor_count_is_qualified_as_observed_measurements(project, observed):
    root, bad, _ = project
    observed['stat_denied'] = {bad}
    response = invoke('pack', str(root), '--verbose')
    assert observed['stats'] == [bad] and response.returncode == 0
    assert 'Selected 1 of 1' in response.stdout
    assert 'observed' in response.stdout.lower() or 'measured' in response.stdout.lower()
    assert 'measurement' in response.stdout.lower() + response.stderr.lower()


def test_specialized_default_keeps_healthy_content_and_unknown_lines_visible(project, observed):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_pack
    root, bad, _ = project
    observed['read_denied'] = {bad}
    text = reveal_pack(str(root))
    assert observed['reads'] == [bad] and observed['collections'] == 1
    assert type(text) is str and '[~8000 tokens budget]' in text and 'CONTENT' in text and 'execute' in text
    assert 'measurement' in text.lower() and ('unavailable' in text.lower() or 'unknown' in text.lower())
    assert 'None lines' not in text and 'unreadable:' not in text


@pytest.mark.parametrize('budget,expected', [('0', 1), ('0-lines', 2), ('-1', 0)])
def test_real_zero_cost_and_no_final_newline_stay_clean(tmp_path, observed, budget, expected):
    root = tmp_path / 'zero'
    write(root / 'empty.py', '')
    write(root / 'no_newline.py', 'VALUE=1')
    response = invoke('pack://' + str(root) + '?budget=' + budget, '--format', 'json')
    data = json.loads(response.stdout)
    assert response.returncode == 0 and len(data['files']) == expected
    assert data['meta']['used_lines'] == 0 and not data['meta'].get('warnings')
    assert 'line_budget_incomplete' not in data['meta']
    assert observed['reads'] == observed['stats'] == observed['directory'] == []


def test_direct_count_lines_keeps_historical_integer_fallback(tmp_path):
    no_newline = write(tmp_path / 'one.py', 'VALUE=1')
    assert pack._count_lines(no_newline) == 0
    assert pack._count_lines(tmp_path / 'absent.py') == 0
