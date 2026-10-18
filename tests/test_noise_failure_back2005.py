"""Ambiguous noise needs evidence; failed inspection leaves normal descent eligible."""
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.trace import TraceAdapter
from reveal.utils.exclusions import exclusion_scope
from reveal.utils.path_utils import (
    ANALYSIS, EVIDENCE, RESOLUTION, _walk_code_files, is_noise_dir,
    walk_filter, walk_with_causes,
)


def tree(root, name='build'):
    child = root / name
    child.mkdir()
    (root / 'visible.py').write_text('def visible():\n    return 1\n', encoding='utf-8')
    (child / 'hidden.py').write_text('def hidden():\n    return 2\n', encoding='utf-8')
    return child


def denial(monkeypatch, child, error=PermissionError, *, once=False, named=True):
    real = os.scandir
    attempts = []

    def scandir(path):
        if Path(path) == child:
            attempts.append(path)
            if not once or len(attempts) == 1:
                if named:
                    raise error(13, 'controlled ambiguous directory inspection failure', str(child))
                raise error('controlled ambiguous directory inspection failure')
        return real(path)

    monkeypatch.setattr(os, 'scandir', scandir)
    return attempts


def warning(result):
    entries = (result.get('meta') or {}).get('warnings', [])
    return [entry for entry in entries if entry.get('type') == 'analysis_incomplete']


@pytest.mark.parametrize('name', ['build', 'dist'])
@pytest.mark.parametrize('entry', ['visible', 'hidden'])
@pytest.mark.parametrize('form', ['uri', 'command'])
@pytest.mark.parametrize('output', ['text', 'json'])
def test_actual_trace_preserves_persistent_noise_inspection_loss(tmp_path, monkeypatch, name, entry, form, output):
    child = tree(tmp_path, name)
    argv = ([f'trace://{tmp_path}?from={entry}'] if form == 'uri'
            else ['trace', str(tmp_path), '--from', entry])
    clean = run(*argv, '--format', output)
    assert clean.returncode == 0
    denial(monkeypatch, child)
    failed = run(*argv, '--format', output)
    assert failed.returncode == 3
    assert "Entry point 'hidden' not found" not in failed.stdout + failed.stderr
    if output == 'json':
        payload = json.loads(failed.stdout)
        diagnostic, = warning(payload)
        assert diagnostic['count'] == 1 and diagnostic['unit'] == 'directories'
        assert diagnostic['directories'] == [child.as_posix()]
        assert 'files' not in diagnostic
    else:
        assert (failed.stdout + failed.stderr).count('identified directory enumeration(s) failed') == 1


@pytest.mark.parametrize('entry,state', [('visible', 'incomplete'), ('hidden', 'failed')])
def test_adapter_reuse_keeps_survivor_and_lost_root_facts_honest(tmp_path, monkeypatch, entry, state):
    child = tree(tmp_path)
    adapter = TraceAdapter(str(tmp_path), f'from={entry}')
    clean = adapter.get_structure()
    with monkeypatch.context() as context:
        denial(context, child)
        failed = adapter.get_structure()
    assert adapter.execution_facts(failed).completeness.value == state
    assert not any(cause.value == 'invalid_request' for cause in adapter.execution_facts(failed).failures)
    assert warning(failed)
    assert adapter.get_structure() == clean


@pytest.mark.parametrize('name', ['build', 'dist'])
@pytest.mark.parametrize('error', [PermissionError, FileNotFoundError, OSError])
def test_failed_direct_inspection_is_not_positive_noise_evidence(tmp_path, monkeypatch, name, error):
    child = tree(tmp_path, name)
    denial(monkeypatch, child, error)
    assert is_noise_dir(tmp_path, name) is False


@pytest.mark.parametrize('name', ['build', 'dist'])
def test_transient_inspection_failure_recovers_through_normal_descent(tmp_path, monkeypatch, name):
    child = tree(tmp_path, name)
    clean = TraceAdapter(str(tmp_path), 'from=hidden').get_structure()
    attempts = denial(monkeypatch, child, once=True)
    assert TraceAdapter(str(tmp_path), 'from=hidden').get_structure() == clean
    assert len(attempts) == 2  # inspection then normal descent


@pytest.mark.parametrize('purpose', [ANALYSIS, EVIDENCE, RESOLUTION])
def test_failure_does_not_become_policy_hidden_cause(tmp_path, monkeypatch, purpose):
    child = tree(tmp_path)
    denial(monkeypatch, child)
    assert walk_filter(tmp_path, purpose)(child, True) is None


@pytest.mark.parametrize('purpose', [ANALYSIS, EVIDENCE])
def test_ordinary_descent_owns_failure_and_policy_counts(tmp_path, monkeypatch, purpose):
    child = tree(tmp_path)
    hidden, errors = [], []
    denial(monkeypatch, child)
    found = list(_walk_code_files(tmp_path, purpose=purpose, on_error=errors.append,
                                 on_hidden=lambda *args: hidden.append(args)))
    assert found == [tmp_path / 'visible.py']
    assert hidden == []
    assert len(errors) == 1 and errors[0].filename == str(child)


@pytest.mark.parametrize('purpose', [ANALYSIS, EVIDENCE, RESOLUTION])
def test_transient_resolution_and_evidence_walks_recover(tmp_path, monkeypatch, purpose):
    child = tree(tmp_path)
    denial(monkeypatch, child, once=True)
    found = ([path for path, cause in walk_with_causes(tmp_path, purpose) if cause is None]
             if purpose is RESOLUTION else list(_walk_code_files(tmp_path, purpose=purpose)))
    assert set(found) == {tmp_path / 'visible.py', child / 'hidden.py'}


def test_missing_direct_predicate_and_disappearing_listed_child(tmp_path, monkeypatch):
    assert is_noise_dir(tmp_path, 'build') is False
    child = tree(tmp_path)
    errors, hidden = [], []
    denial(monkeypatch, child, FileNotFoundError)
    assert list(_walk_code_files(tmp_path, on_error=errors.append,
                                on_hidden=lambda *args: hidden.append(args))) == [tmp_path / 'visible.py']
    assert len(errors) == 1 and isinstance(errors[0], FileNotFoundError)
    assert hidden == []


def test_unknown_directory_error_is_not_counted_as_known_missing_files(tmp_path, monkeypatch):
    child = tree(tmp_path)
    denial(monkeypatch, child, named=False)
    result = TraceAdapter(str(tmp_path), 'from=visible').get_structure()
    diagnostic, = warning(result)
    assert diagnostic['count'] == 0 and diagnostic['directories'] == []
    assert diagnostic['unknown_directory_events'] == 1
    assert 'files' not in diagnostic


def test_single_file_and_explicit_exclusion_siblings_are_exactly_unchanged(tmp_path, monkeypatch):
    child = tree(tmp_path)
    single = f'trace://{tmp_path / "visible.py"}?from=visible'
    scoped = f'trace://{tmp_path}?from=hidden'
    before_single = run(single, '--format', 'json')
    before_excluded = run(scoped, '--exclude', 'build', '--format', 'json')
    denial(monkeypatch, child)
    after_single = run(single, '--format', 'json')
    after_excluded = run(scoped, '--exclude', 'build', '--format', 'json')
    for before, after in [(before_single, after_single), (before_excluded, after_excluded)]:
        assert (before.returncode, before.stdout, before.stderr) == (after.returncode, after.stdout, after.stderr)


def test_evidence_ignores_exclusion_but_analysis_and_resolution_keep_policy(tmp_path, monkeypatch):
    child = tree(tmp_path)
    denial(monkeypatch, child)
    with exclusion_scope(tmp_path, ['build']):
        assert walk_filter(tmp_path, ANALYSIS)(child, True) == 'exclude'
        assert walk_filter(tmp_path, RESOLUTION)(child, True) == 'exclude'
        assert walk_filter(tmp_path, EVIDENCE)(child, True) is None


@pytest.mark.parametrize('name', ['node_modules', '.git', '__pycache__'])
def test_reserved_noise_is_never_inspected(tmp_path, monkeypatch, name):
    child = tree(tmp_path, name)
    attempts = denial(monkeypatch, child)
    assert is_noise_dir(tmp_path, name)
    assert list(_walk_code_files(tmp_path)) == [tmp_path / 'visible.py']
    assert attempts == []


@pytest.mark.parametrize('mode', ['iterator', 'entry'])
def test_inspection_iteration_or_entry_io_loss_can_recover_on_descent(tmp_path, monkeypatch, mode):
    child = tree(tmp_path)
    real = os.scandir
    calls = []

    class Entry:
        def __init__(self, value):
            self.value = value
            self.name = value.name

        def is_file(self):
            raise PermissionError(13, 'controlled entry inspection failure', str(child / self.name))

    class Scan:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __iter__(self):
            if mode == 'iterator':
                raise OSError(5, 'controlled iterator inspection failure', str(child))
            with real(child) as entries:
                yield from (Entry(entry) for entry in entries)

    def scandir(path):
        if Path(path) == child:
            calls.append(path)
            if len(calls) == 1:
                return Scan()
        return real(path)

    monkeypatch.setattr(os, 'scandir', scandir)
    assert set(_walk_code_files(tmp_path)) == {tmp_path / 'visible.py', child / 'hidden.py'}
    assert len(calls) == 2


def test_unexpected_inspection_bug_still_escapes(tmp_path, monkeypatch):
    child = tree(tmp_path)

    def bug(path):
        raise RuntimeError('controlled unexpected inspection bug')

    monkeypatch.setattr(os, 'scandir', bug)
    with pytest.raises(RuntimeError, match='controlled unexpected inspection bug'):
        is_noise_dir(tmp_path, child.name)


def test_first_inspection_loss_conservatively_includes_nested_generated_source(tmp_path, monkeypatch):
    child = tmp_path / 'build'
    (child / 'lib').mkdir(parents=True)
    generated = child / 'lib' / 'generated.py'
    generated.write_text('VALUE = 1\n', encoding='utf-8')
    assert list(_walk_code_files(tmp_path)) == []  # established no-top-level-source policy
    errors = []
    attempts = denial(monkeypatch, child, once=True)
    assert list(_walk_code_files(tmp_path, on_error=errors.append)) == [generated]
    assert len(attempts) == 2 and errors == []  # full descent recovered; population broadened


def test_listed_child_really_disappears_before_inspection(tmp_path, monkeypatch):
    child = tree(tmp_path)
    real = os.scandir
    attempts = []

    def scandir(path):
        if Path(path) == child:
            attempts.append(path)
            if len(attempts) == 1:
                (child / 'hidden.py').unlink()
                child.rmdir()
        return real(path)

    errors, hidden = [], []
    monkeypatch.setattr(os, 'scandir', scandir)
    assert list(_walk_code_files(tmp_path, on_error=errors.append,
                                on_hidden=lambda *args: hidden.append(args))) == [tmp_path / 'visible.py']
    assert len(attempts) == 2
    assert len(errors) == 1 and isinstance(errors[0], FileNotFoundError)
    assert Path(errors[0].filename) == child
    assert hidden == []


@pytest.mark.parametrize('name', ['env', 'venv'])
def test_known_virtualenv_markers_preserve_noise_without_inspection(tmp_path, monkeypatch, name):
    child = tree(tmp_path, name)
    (child / 'pyvenv.cfg').write_text('home=python\n', encoding='utf-8')
    attempts = denial(monkeypatch, child)
    assert is_noise_dir(tmp_path, name)
    assert list(_walk_code_files(tmp_path)) == [tmp_path / 'visible.py']
    assert attempts == []
