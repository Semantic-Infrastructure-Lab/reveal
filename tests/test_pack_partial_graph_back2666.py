"""Pack keeps a partial import graph and discloses the loss (BACK-2666; COMMAND_MODEL "Degraded input").

``pack --architecture``/``--focus`` threw away the whole Imports graph on any loss (a file read only through
error recovery, a directory it could not list, an unreadable file, a lost worker) and ranked by file names,
with the cause only in the advisory ``meta.relevance_warning``. overview:// keeps the same graph and names the
loss. Pack now does too: fan-in and relevance come from the files the graph read, each loss is named once in
``meta.warnings`` and the answer is incomplete (exit 3).
"""
import json
import os
import sys
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.analyzers.imports import service as import_service

pytestmark = pytest.mark.component


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'project'
    _write(root / 'focus.py', 'import helper\n')
    _write(root / 'helper.py', 'def work():\n    return 1\n')
    _write(root / 'child' / 'source.py', 'import helper\n')
    return root


@pytest.fixture
def deny_during_build(monkeypatch):
    """Deny one directory to the import build only: Pack's own candidate walk still lists it."""
    state = {'active': False, 'denied': None}
    real_build, real_scandir = import_service.analyze, os.scandir

    def build(scope, *args, **kwargs):
        state['active'] = True
        try:
            return real_build(scope, *args, **kwargs)
        finally:
            state['active'] = False

    def scandir(path):
        if state['active'] and Path(path).resolve() == state['denied']:
            raise PermissionError(13, 'graph-only loss', str(path))
        return real_scandir(path)

    monkeypatch.setattr(import_service, 'analyze', build)
    monkeypatch.setattr(os, 'scandir', scandir)
    return state


def _pack(root, *flags):
    result = _run_reveal_direct('pack', root.as_posix(), *flags, '--format', 'json')
    return result.returncode, json.loads(result.stdout)


def _fan_in(answer):
    return {row['relative']: row.get('fan_in') for row in answer['files']}


def _warnings(answer, kind):
    return [w for w in answer['meta'].get('warnings', []) if w.get('type') == kind]


def test_graph_only_directory_loss_keeps_the_partial_graph(project, deny_during_build):
    deny_during_build['denied'] = (project / 'child').resolve()
    code, answer = _pack(project, '--architecture')
    assert _fan_in(answer)['helper.py'] == 1  # focus.py's import; child/source.py's is the missing one
    (loss,) = _warnings(answer, 'analysis_incomplete')[:1]
    assert loss['directories'] == ['child'] and 'import graph' in loss['message']
    assert code == 3
    assert 'relevance_warning' not in answer['meta']


def test_recovered_file_keeps_the_graph_and_is_named_once(project):
    _write(project / 'bad.py', 'import helper\nthis is !!! invalid python\n')
    code, answer = _pack(project, '--architecture')
    assert _fan_in(answer)['helper.py'] >= 2
    (recovered,) = _warnings(answer, 'parse_recovered')
    assert [Path(f).name for f in recovered['files']] == ['bad.py']
    assert code == 3
    assert 'relevance_warning' not in answer['meta']


def test_focus_relevance_comes_from_the_partial_graph(project, deny_during_build):
    deny_during_build['denied'] = (project / 'child').resolve()
    code, answer = _pack(project, '--focus', 'focus')
    relevance = {row['relative']: row.get('graph_relevance', 0) for row in answer['files']}
    assert relevance.get('helper.py', 0) > 0  # reached from focus.py through the graph
    assert code == 3 and 'relevance_warning' not in answer['meta']


def test_lost_worker_keeps_the_graph_and_is_a_loss(project, monkeypatch):
    real_build = import_service.analyze

    def build(scope, *args, **kwargs):
        built = real_build(scope, *args, **kwargs)
        # The record a dead pool worker leaves: the file is failed and lost, with no extraction.
        lost = next(p for p in built.analysis.scanned_files if Path(p).name == 'source.py')
        built.analysis.files_failed.append(lost)
        built.analysis.files_lost.append(lost)
        return built
    monkeypatch.setattr(import_service, 'analyze', build)
    code, answer = _pack(project, '--architecture')
    assert _fan_in(answer)['helper.py'] >= 1
    (lost,) = _warnings(answer, 'worker_lost')
    assert code == 3
    assert 'relevance_warning' not in answer['meta']


@pytest.mark.skipif(sys.platform == 'win32' or (hasattr(os, 'geteuid') and os.geteuid() == 0),
                    reason='mode 000 directories are POSIX-only, and root lists them')
def test_directory_both_walks_lose_is_named_once(project):
    hidden = project / 'child'
    hidden.chmod(0)
    try:
        code, answer = _pack(project, '--architecture')
    finally:
        hidden.chmod(0o755)
    losses = _warnings(answer, 'analysis_incomplete')
    named = [d for w in losses for d in w.get('directories', [])]
    assert named == ['child'], losses
    assert _fan_in(answer)['helper.py'] == 1
    assert code == 3


def test_clean_tree_is_unchanged(project):
    """Control: no loss, no warning, exit 0, fan-in from the whole graph."""
    code, answer = _pack(project, '--architecture')
    assert _fan_in(answer)['helper.py'] == 2
    assert not answer['meta'].get('warnings') and code == 0


def test_plain_pack_still_says_signals_were_not_computed(project):
    """Control: an unrequested signal keeps its advisory."""
    code, answer = _pack(project)
    assert 'not computed' in answer['meta']['relevance_warning'] and code == 0


def test_graph_only_loss_does_not_relabel_the_candidates(project, deny_during_build):
    """The import graph's directory loss leaves Pack's candidate walk whole: the text keeps "files"."""
    deny_during_build['denied'] = (project / 'child').resolve()
    result = _run_reveal_direct('pack', project.as_posix(), '--architecture')
    assert result.returncode == 3
    assert 'Selected 3 of 3 files' in result.stdout and 'observed eligible' not in result.stdout
    assert result.stdout.count('Optional import graph is incomplete') == 1


@pytest.mark.skipif(sys.platform == 'win32' or (hasattr(os, 'geteuid') and os.geteuid() == 0),
                    reason='mode 000 files are POSIX-only, and root reads them')
def test_unreadable_file_both_reads_lose_is_named_once(project):
    hidden = project / 'child' / 'source.py'
    hidden.chmod(0)
    try:
        code, answer = _pack(project, '--architecture')
    finally:
        hidden.chmod(0o644)
    named = [Path(f).name for w in answer['meta'].get('warnings', [])
             if w.get('type') in ('file_measurement_failed', 'analysis_failed') for f in w.get('files', [])]
    assert named == ['source.py'], answer['meta'].get('warnings')
    assert _fan_in(answer)['helper.py'] == 1
    assert code == 3
