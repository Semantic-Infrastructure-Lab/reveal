"""Existing-API Pack FILE measurement failures must not become measured zero."""
import importlib
import json
import os
from pathlib import Path

import pytest

import reveal
from conftest import _run_reveal_direct as run
from reveal.adapters import pack
from reveal.cli.commands import pack as shim
from reveal.mcp_server import reveal_pack
from reveal.rendering.adapters.pack import PackRenderer

pytestmark = pytest.mark.component
assert Path(reveal.__file__).resolve().is_relative_to(Path(__file__).resolve().parents[1])


@pytest.fixture
def measured(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    root.mkdir()
    core = root / 'core.py'
    core.write_text('def core():\n    return 1\n', encoding='utf-8')
    healthy = root / 'healthy.py'
    healthy.write_text('VALUE=1\n', encoding='utf-8')
    state = dict(active=False, stat=set(), read=set(), directories=set(), unknown=False,
                 events=[], raw=[])
    collect, stat, read, scan = pack._collect_candidates, Path.stat, Path.read_text, os.scandir

    def candidates(*args, **kwargs):
        state['active'] = True
        try:
            result = collect(*args, **kwargs)
            state['raw'].extend(result)
            return result
        finally:
            state['active'] = False

    def failure(operation, path):
        state['events'].append((operation, path))
        if state['unknown']:
            return PermissionError('actual unlocated Pack FILE measurement denial')
        return PermissionError(13, f'actual Pack {operation} measurement denial', str(path))

    def file_stat(*args, **kwargs):
        if state['active'] and args[0] in state['stat']:
            raise failure('stat', args[0])
        return stat(*args, **kwargs)

    def file_read(*args, **kwargs):
        if state['active'] and args[0] in state['read']:
            raise failure('line_count', args[0])
        return read(*args, **kwargs)

    def scandir(*args, **kwargs):
        if state['active'] and Path(args[0]) in state['directories']:
            raise failure('directory', Path(args[0]))
        return scan(*args, **kwargs)

    monkeypatch.setattr(pack, '_collect_candidates', candidates)
    monkeypatch.setattr(shim, '_collect_candidates', candidates)
    monkeypatch.setattr(Path, 'stat', file_stat)
    monkeypatch.setattr(Path, 'read_text', file_read)
    monkeypatch.setattr(os, 'scandir', scandir)
    return root, core, healthy, state


def native(root, query=''):
    try:
        return pack.PackAdapter(str(root), query).get_structure()
    except OSError as exc:
        return {'baseline_exception': f'{type(exc).__name__}: {exc}'}


def file_note(result, name='core.py'):
    notes = [n for n in result.get('meta', {}).get('warnings', [])
             if n.get('type') == 'file_measurement_failed']
    assert notes, ('Real file measurement loss must reach the existing Pack result', result)
    assert all(n.get('unit') != 'directories' for n in notes)
    assert name in str(notes) and 'PermissionError' in str(notes)
    return notes


@pytest.mark.parametrize('loss', ['one', 'init', 'all', 'all_unlocated'])
def test_actual_candidate_stat_loss_preserves_siblings_or_marks_unavailable(measured, loss):
    root, core, healthy, state = measured
    if loss == 'init':
        target = root / 'pkg' / '__init__.py'
        target.parent.mkdir()
        target.write_text('# tiny\n', encoding='utf-8')
        state['stat'] = {target}
    else:
        state['stat'] = {core, healthy} if loss.startswith('all') else {core}
    state['unknown'] = loss == 'all_unlocated'
    result = native(root)
    assert state['events'] and all(op == 'stat' for op, _ in state['events'])
    assert 'baseline_exception' not in result, 'One unmeasured file must not abort healthy Pack observations'
    file_note(result, '__init__.py' if loss == 'init' else 'core.py')
    meta = result['meta']
    assert meta['total_candidates'] == (0 if loss.startswith('all') else 2 if loss == 'init' else 1)
    assert meta['selected'] + meta['skipped'] == meta['total_candidates']
    text = PackRenderer.render_structure(result)
    if loss.startswith('all'):
        assert 'unavailable' in text.lower() or 'not measured' in text.lower()
        assert 'fit within budget' not in text.lower()
    else:
        assert 'observed' in text.lower()


@pytest.mark.parametrize('mode', ['tokens', 'line1', 'line0', 'line_negative', 'all_line', 'token_skip'])
def test_actual_unknown_line_cost_never_fits_as_zero_or_becomes_exact_subtotal(measured, mode):
    root, core, healthy, state = measured
    state['read'] = {core, healthy} if mode == 'all_line' else {core}
    budget = dict(tokens='1000', line1='1-lines', line0='0-lines',
                  line_negative='-1-lines', all_line='1-lines', token_skip='2')[mode]
    result = native(root, f'budget={budget}&content=true')
    assert state['events'] and all(op == 'line_count' for op, _ in state['events'])
    raw = next(row for row in state['raw'] if row['relative'] == 'core.py')
    assert raw['size'] == core.stat().st_size and raw['tokens_approx'] > 0
    assert raw['lines'] is None, 'Actual read failure is unknown cost, not measured zero'
    file_note(result)
    meta = result['meta']
    assert meta['total_candidates'] == 2
    assert meta['selected'] + meta['skipped'] == 2
    if mode == 'tokens':
        assert meta['selected'] == 2 and meta['used_lines'] is None
        assert 'core()' in next(c['content'] for c in result['content'] if c['file'] == 'core.py')
        text = PackRenderer.render_structure(result, verbose=True)
        assert 'None' not in text and ('unavailable' in text.lower() or '?' in text)
    elif mode == 'token_skip':
        assert [r['relative'] for r in result['files']] == ['healthy.py']
        assert meta['used_lines'] == 1
    else:
        assert meta['line_budget_incomplete'] is True
        assert [r['relative'] for r in result['files']] == (['healthy.py'] if mode == 'line1' else [])
        assert meta['used_lines'] == (1 if mode == 'line1' else 0)
        if not result['files']:
            text = PackRenderer.render_structure(result)
            assert 'unavailable' in text.lower() or 'unknown' in text.lower()


@pytest.mark.parametrize('spelling', ['command', 'uri'])
@pytest.mark.parametrize('format', ['text', 'json'])
def test_real_read_loss_is_visible_in_both_public_forms_with_legacy_zero(measured, spelling, format):
    root, core, healthy, state = measured
    state['read'] = {core}
    args = ['pack', root, '--budget', '1-lines'] if spelling == 'command' else [f'pack://{root}?budget=1-lines']
    response = run(*args, '--format', format, '--verbose')
    assert state['events'] and all(op == 'line_count' for op, _ in state['events'])
    assert response.returncode == 3
    if format == 'json':
        result = json.loads(response.stdout)
        file_note(result)
        assert result['meta']['line_budget_incomplete'] is True
        assert len(result['files']) == 1
    else:
        assert 'PermissionError' in response.stdout and 'core.py' in response.stdout
        assert 'unavailable' in response.stdout.lower() or 'unknown' in response.stdout.lower()


@pytest.mark.parametrize('format', ['text', 'json'])
def test_all_stat_loss_public_answer_explains_measurement_unavailability(measured, format):
    root, core, healthy, state = measured
    state['stat'] = {core, healthy}
    response = run(f'pack://{root}', '--format', format)
    assert state['events'] and all(op == 'stat' for op, _ in state['events'])
    assert response.returncode == 3, 'lost FILE measurement is incomplete work (D6, BACK-2045)'
    if format == 'json':
        result = json.loads(response.stdout)
        file_note(result)
        assert result['meta']['total_candidates'] == 0
    else:
        assert 'fit within budget' not in response.stdout.lower()
        assert 'unavailable' in response.stdout.lower() and 'PermissionError' in response.stdout


def test_supported_uri_artifact_and_global_cut_retain_pre_cut_file_disclosure(measured, tmp_path):
    root, core, healthy, state = measured
    state['read'] = {core}
    destination = tmp_path / 'pack.json'
    response = run(f'pack://{root}?budget=1000', '--max-items', '0', '--also-json', destination)
    assert state['events'] and destination.exists()
    assert response.returncode == 3
    result = json.loads(destination.read_text(encoding='utf-8'))
    file_note(result)
    assert result['files'] == [] and result['meta']['total_candidates'] == 2


@pytest.mark.parametrize('fault', ['stat', 'read'])
def test_decorated_specialized_defaults_retain_useful_content_and_file_notes(measured, fault):
    root, core, healthy, state = measured
    state[fault] = {core}
    try:
        result = reveal_pack(str(root))
        raised = False
    except OSError as exc:
        result, raised = str(exc), True
    assert state['events']
    assert not raised, 'Actual candidate stat loss must not abort the healthy specialized Pack'
    assert not isinstance(result, importlib.import_module('reveal.mcp_server')._ToolFailure)
    assert '~8000 tokens budget' in result and 'CONTENT' in result
    assert 'PermissionError' in result and 'core.py' in result
    if fault == 'read':
        assert 'core()' in result and ('unavailable' in result.lower() or '?' in result)
    else:
        assert 'Selected 1 of 1 observed' in result


def test_file_and_directory_measurement_failures_remain_distinct(measured):
    root, core, healthy, state = measured
    child = root / 'included'
    child.mkdir()
    (child / 'hidden.py').write_text('X=3\n', encoding='utf-8')
    state['directories'] = {child}
    state['stat'] = {core, healthy}
    result = native(root)
    assert {op for op, _ in state['events']} == {'directory', 'stat'}
    assert 'baseline_exception' not in result
    file_note(result)
    directory = [n for n in result['meta']['warnings'] if n.get('unit') == 'directories']
    assert len(directory) == 1 and directory[0]['directories'] == ['included']
    text = run(f'pack://{root}').stdout
    assert text.count('PermissionError') >= 2 and 'fit within budget' not in text.lower()


def test_legacy_default_count_lines_zero_and_genuine_no_newline_are_unchanged(measured):
    root, core, healthy, state = measured
    state['active'] = True
    state['read'] = {core}
    try:
        assert pack._count_lines(core) == 0
    finally:
        state['active'] = False
    assert state['events'] == [('line_count', core)]
    core.write_text('NO_NEWLINE=1', encoding='utf-8')
    assert pack._count_lines(core) == 0


def test_default_six_positional_candidate_helper_still_raises_stat_failure(measured):
    root, core, healthy, state = measured
    state['stat'] = {core}
    with pytest.raises(PermissionError):
        pack._collect_candidates(root, None, None, None, None, None)
    assert state['events'] == [('stat', core)]


def test_old_priority_and_budget_helper_shapes_remain_native(measured):
    root, core, healthy, state = measured
    score = pack._compute_priority(core, core.relative_to(root), None)
    assert score == 2.0
    candidates = pack._collect_candidates(root, None, None, None, None, None)
    result = pack._apply_budget(candidates, 1000, None, root)
    assert isinstance(result, tuple) and len(result) == 2
    assert len(result[0]) == 2 and result[1]['used_lines'] == 3
    assert state['events'] == []


def test_clean_zero_byte_and_no_newline_costs_are_not_measurement_loss(measured):
    root, core, healthy, state = measured
    core.write_text('', encoding='utf-8')
    healthy.write_text('X', encoding='utf-8')
    result = native(root, 'budget=0-lines')
    assert result['meta']['selected'] == 2 and result['meta']['used_lines'] == 0
    assert not result['meta'].get('warnings') and not result['meta'].get('line_budget_incomplete')
    assert all(row['lines'] == 0 for row in result['files']) and state['events'] == []


@pytest.mark.parametrize('directory_loss', [False, True])
def test_mixed_stat_and_unknown_line_cost_empty_answer_does_not_claim_budget_fit(measured, directory_loss):
    root, core, healthy, state = measured
    state['stat'] = {core}
    state['read'] = {healthy}
    if directory_loss:
        child = root / 'included'
        child.mkdir()
        (child / 'hidden.py').write_text('X=3\n', encoding='utf-8')
        state['directories'] = {child}
    result = native(root, 'budget=1-lines')
    operations = {operation for operation, _ in state['events']}
    assert operations == ({'stat', 'line_count', 'directory'} if directory_loss else {'stat', 'line_count'})
    assert result['meta']['total_candidates'] == result['meta']['skipped'] == 1
    assert result['meta']['selected'] == result['meta']['used_lines'] == 0
    assert result['meta']['line_budget_incomplete'] is True
    note, = file_note(result)
    assert set(note['operations']) == {'stat', 'line_count'}
    assert healthy.as_posix() in str(note)
    directories = [n for n in result['meta']['warnings'] if n.get('unit') == 'directories']
    assert len(directories) == int(directory_loss)
    text = PackRenderer.render_structure(result)
    assert 'observed' in text.lower()
    assert 'fit within budget' not in text.lower(), 'Unknown remaining line cost cannot prove budget exclusion'
    assert 'unavailable' in text.lower() or 'unknown' in text.lower()
