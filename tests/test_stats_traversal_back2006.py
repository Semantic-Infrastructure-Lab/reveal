"""Stats directory loss survives empty populations, projections and required composition."""
import errno
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.ast import AstAdapter
from reveal.adapters.hotspots import HotspotsAdapter
from reveal.adapters.stats import StatsAdapter


def tree(root, *, survivor=True):
    child = root / 'included_child'
    child.mkdir()
    if survivor:
        (root / 'visible.py').write_text('def visible():\n    return 1\n', encoding='utf-8')
    (child / 'hidden.py').write_text('def hidden():\n    return 2\n', encoding='utf-8')
    return child


def deny_stats(monkeypatch, directories, *, named=True):
    """Inject actual scandir errors only while the real Stats collector executes."""
    real_scan = os.scandir
    from reveal.adapters.stats import adapter as stats_module
    real_find = stats_module.find_analyzable_files
    active = False
    attempts = []

    def find(*args, **kwargs):
        nonlocal active
        iterator = iter(real_find(*args, **kwargs))
        while True:
            active = True
            try:
                path = next(iterator)
            except StopIteration:
                return
            finally:
                active = False
            yield path

    def scan(path):
        if active and Path(path) in directories:
            attempts.append(Path(path))
            if named:
                raise PermissionError(errno.EACCES, 'controlled Stats child traversal failure', str(path))
            raise PermissionError('controlled Stats child traversal failure')
        return real_scan(path)

    monkeypatch.setattr(stats_module, 'find_analyzable_files', find)
    monkeypatch.setattr(os, 'scandir', scan)
    return attempts


def warnings(result):
    return [entry for entry in (result.get('meta') or {}).get('warnings', [])
            if entry.get('type') == 'analysis_incomplete']


@pytest.mark.parametrize('survivor', [True, False])
@pytest.mark.parametrize('query', ['', 'min_lines=999', 'limit=1&offset=1', 'summary_only=true'])
def test_stats_actual_discovery_loss_survives_zero_and_filtered_rows(tmp_path, monkeypatch, survivor, query):
    child = tree(tmp_path, survivor=survivor)
    adapter = StatsAdapter(str(tmp_path), query)
    clean = adapter.get_structure()
    assert not warnings(clean)
    with monkeypatch.context() as context:
        deny_stats(context, {child})
        failed = adapter.get_structure()
    if not survivor or query:
        assert failed.get('files', []) == []
    diagnostic, = warnings(failed)
    assert diagnostic['unit'] == 'directories' and diagnostic['count'] == 1
    assert diagnostic['directories'] == ['included_child']
    assert 'PermissionError' in diagnostic['message'] and 'files' not in diagnostic
    assert not any(w.get('type') == 'analysis_failed' for w in failed['meta']['warnings'])
    assert adapter.get_structure() == clean


@pytest.mark.parametrize('survivor', [True, False])
def test_required_owner_facts_retain_stats_loss_with_clean_ast(tmp_path, monkeypatch, survivor):
    child = tree(tmp_path, survivor=survivor)
    adapter = HotspotsAdapter(str(tmp_path), 'files_only=true')
    clean_ast = AstAdapter(str(tmp_path), 'complexity>9').get_structure()
    with monkeypatch.context() as context:
        deny_stats(context, {child})
        failed = adapter.get_structure()
        assert AstAdapter(str(tmp_path), 'complexity>9').get_structure() == clean_ast
    state = adapter.execution_facts(failed).completeness.value
    assert state == 'incomplete' if survivor else state in {'incomplete', 'failed'}
    assert warnings(failed)
    assert not warnings(adapter.get_structure())


@pytest.mark.parametrize('mode,cli,query', [
    ('default', [], ''),
    ('files', ['--files-only'], 'files_only=true'),
    ('functions', ['--functions-only'], 'functions_only=true'),
    ('both', ['--files-only', '--functions-only'], 'files_only=true&functions_only=true'),
])
@pytest.mark.parametrize('form', ['command', 'uri'])
@pytest.mark.parametrize('provenance', [False, True])
def test_hotspots_actual_cli_has_required_stats_loss_before_projection(tmp_path, monkeypatch, mode, cli, query, form, provenance):
    child = tree(tmp_path)
    argv = (['hotspots', str(tmp_path), *cli] if form == 'command'
            else [f'hotspots://{tmp_path}' + ('?' + query if query else '')])
    flags = ['--format', 'json', '--fields', 'path'] + (['--provenance'] if provenance else [])
    deny_stats(monkeypatch, {child})
    result = run(*argv, *flags)
    assert result.returncode == 3
    payload = json.loads(result.stdout)
    assert warnings(payload)
    if provenance:
        assert payload['execution']['command'] == ' '.join(['reveal', *argv, *flags])


@pytest.mark.parametrize('form', ['command', 'uri'])
@pytest.mark.parametrize('survivor', [True, False])
def test_actual_text_and_json_artifact_preserve_stats_diagnostic(tmp_path, monkeypatch, form, survivor):
    child = tree(tmp_path, survivor=survivor)
    argv = (['hotspots', str(tmp_path), '--files-only'] if form == 'command'
            else [f'hotspots://{tmp_path}?files_only=true'])
    artifact = tmp_path / 'answer.json'
    deny_stats(monkeypatch, {child})
    result = run(*argv, '--also-json', str(artifact))
    assert result.returncode == 3
    assert (result.stdout + result.stderr).count('identified directory enumeration(s) failed') == 1
    diagnostic, = warnings(json.loads(artifact.read_text(encoding='utf-8')))
    assert diagnostic['count'] == 1


# stats:// stays on the legacy URI route until the cut and keeps exit 0; metrics is a declared noun
# (BACK-2146), so the same directory loss is an incomplete answer: exit 3 on the D6 outcome policy.
@pytest.mark.parametrize('scheme,exit_code', [('stats', 0), ('metrics', 3)])
@pytest.mark.parametrize('output', ['text', 'json'])
def test_direct_stats_discloses_and_exits_by_its_route(tmp_path, monkeypatch, output, scheme, exit_code):
    child = tree(tmp_path)
    deny_stats(monkeypatch, {child})
    result = run(f'{scheme}://{tmp_path}?churn=false', '--format', output)
    assert result.returncode == exit_code
    if output == 'json':
        assert json.loads(result.stdout)['summary']['total_files'] == 1
        assert warnings(json.loads(result.stdout))
    else:
        assert (result.stdout + result.stderr).count('identified directory enumeration(s) failed') == 1


def test_directory_file_and_element_transitions_cannot_leak_loss(tmp_path, monkeypatch):
    child = tree(tmp_path)
    adapter = StatsAdapter(str(tmp_path))
    file = tmp_path / 'visible.py'
    clean_file = StatsAdapter(str(file)).get_structure()
    with monkeypatch.context() as context:
        deny_stats(context, {child})
        assert warnings(adapter.get_structure())
        adapter.path = file
        assert adapter.get_structure() == clean_file
        adapter.path = tmp_path
        assert not warnings(adapter.get_element('visible.py'))
        assert warnings(adapter.get_structure(summary_only=True))
    adapter.path = file
    assert adapter.get_structure() == clean_file
    adapter.path = tmp_path
    assert not warnings(adapter.get_structure())


def test_unknown_directory_and_capped_known_directory_counts_are_separate(tmp_path, monkeypatch):
    directories = set()
    for index in range(7):
        child = tmp_path / f'child{index}'
        child.mkdir()
        (child / 'hidden.py').write_text('VALUE=1\n', encoding='utf-8')
        directories.add(child)
    with monkeypatch.context() as context:
        deny_stats(context, directories)
        result = StatsAdapter(str(tmp_path)).get_structure()
    diagnostic, = warnings(result)
    assert diagnostic['count'] == 7 and diagnostic['unit'] == 'directories'
    # BACK-2249: the cause no longer carries the path, so five directories lost to one error are one cause
    assert len(diagnostic['directories']) == 5 and diagnostic['causes'] == ['PermissionError: controlled Stats child traversal failure']
    with monkeypatch.context() as context:
        deny_stats(context, directories, named=False)
        unknown, = warnings(StatsAdapter(str(tmp_path)).get_structure())
    assert unknown['count'] == 0 and unknown['directories'] == []
    assert unknown['unknown_directory_events'] == 7
    assert 'files' not in unknown


def test_clean_zero_and_excluded_single_file_siblings_are_exactly_unchanged(tmp_path, monkeypatch):
    child = tree(tmp_path)
    file = tmp_path / 'visible.py'
    before_file = run(f'stats://{file}', '--format', 'json')
    before_excluded = run(f'stats://{tmp_path}?exclude=included_child', '--format', 'json')
    deny_stats(monkeypatch, {child})
    for uri, before in [(f'stats://{file}', before_file),
                        (f'stats://{tmp_path}?exclude=included_child', before_excluded)]:
        after = run(uri, '--format', 'json')
        assert (after.returncode, after.stdout, after.stderr) == (before.returncode, before.stdout, before.stderr)
    empty = tmp_path / 'empty'
    empty.mkdir()
    result = StatsAdapter(str(empty)).get_structure()
    assert result['summary']['total_files'] == 0 and not warnings(result)


def test_finder_keeps_old_positional_controls_and_optional_error_callback(tmp_path, monkeypatch):
    from reveal.adapters.stats.analysis import find_analyzable_files
    child = tree(tmp_path)
    real = os.scandir

    def denied(path):
        if Path(path) == child:
            raise PermissionError(errno.EACCES, 'controlled finder loss', str(child))
        return real(path)

    monkeypatch.setattr(os, 'scandir', denied)
    assert list(find_analyzable_files(tmp_path, False, False, None, {})) == [tmp_path / 'visible.py']
    errors = []
    assert list(find_analyzable_files(tmp_path, False, False, None, {}, on_error=errors.append)) == [tmp_path / 'visible.py']
    assert len(errors) == 1 and Path(errors[0].filename) == child
    with pytest.raises(TypeError):
        find_analyzable_files(tmp_path, False, False, None, {}, errors.append)


def test_root_loss_is_distinct_from_clean_empty(tmp_path, monkeypatch):
    tree(tmp_path)
    deny_stats(monkeypatch, {tmp_path})
    result = StatsAdapter(str(tmp_path)).get_structure()
    assert result['summary']['total_files'] == 0
    diagnostic, = warnings(result)
    assert diagnostic['count'] == 1 and diagnostic['unit'] == 'directories'
    assert 'controlled Stats child traversal failure' in diagnostic['message']


def test_gitignore_policy_skips_do_not_become_io_loss(tmp_path, monkeypatch):
    child = tree(tmp_path)
    (tmp_path / '.gitignore').write_text('included_child/\n', encoding='utf-8')
    clean = StatsAdapter(str(tmp_path)).get_structure()
    with monkeypatch.context() as context:
        attempts = deny_stats(context, {child})
        assert StatsAdapter(str(tmp_path)).get_structure() == clean
    assert attempts == []
    with monkeypatch.context() as context:
        deny_stats(context, {child})
        included = StatsAdapter(str(tmp_path), 'respect_gitignore=false').get_structure()
    assert warnings(included)


def test_single_file_error_return_resets_directory_state(tmp_path, monkeypatch):
    from reveal.adapters.stats import adapter as stats_module
    child = tree(tmp_path)
    adapter = StatsAdapter(str(tmp_path))
    with monkeypatch.context() as context:
        deny_stats(context, {child})
        assert warnings(adapter.get_structure())
    adapter.path = tmp_path / 'visible.py'
    with monkeypatch.context() as context:
        context.setattr(stats_module, 'analyze_file', lambda *args: {
            'analysis_failed': 'PermissionError: controlled file loss', 'path': str(adapter.path)})
        result = adapter.get_structure()
    assert result['error'] and not warnings(result)
    assert adapter._traversal_failures == []
    adapter.path = tmp_path
    assert not warnings(adapter.get_structure())


def test_review_hotspots_sibling_folds_directory_warning(tmp_path, monkeypatch):
    from reveal.cli.commands.review import _run_hotspots
    child = tree(tmp_path)
    notes = []
    deny_stats(monkeypatch, {child})
    assert _run_hotspots(tmp_path, warnings=notes) == []  # no serious observations
    diagnostic, = [note for note in notes if note.get('type') == 'analysis_incomplete']
    assert diagnostic['count'] == 1 and diagnostic['message'].startswith('hotspots: ')
