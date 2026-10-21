"""Native check exits 3 when a requested artifact cannot be written (BACK-1939, D6).

The nine declared nouns already do (tests/test_declared_parity_back2053.py): a requested
artifact that fails is "requested output failed", exit 3, with the primary answer kept and the
failure disclosed once. check had two writers of its own (single file, directory) that warned
and kept the scan's exit, so a CI gate read 0 for a run whose machine artifact was never
written. The artifact owner is flag-agnostic (`write_requested_artifact`), so a later sink flag
inherits the policy; these tests drive it through today's `--also-json` spelling.

A directory path is the portable unwritable target (it cannot be opened as a file on any OS).
"""
import json
import os
import subprocess
import sys

import pytest

from reveal.utils.json_utils import write_requested_artifact

_BAD = "def f(x):\n    try:\n        return 1 / x\n    except:\n        pass\n"
_OK = "def f(x):\n    return x\n"
_FAILED = 'Requested JSON artifact failed'


def _reveal(cwd, *args, stdin=None):
    env = {**os.environ, 'REVEAL_DISK_CACHE': '0'}
    return subprocess.run([sys.executable, '-m', 'reveal', *args], cwd=cwd, capture_output=True,
                          text=True, env=env, timeout=120, check=False, encoding='utf-8', input=stdin)


@pytest.fixture(scope='module')
def tree(tmp_path_factory):
    root = tmp_path_factory.mktemp('check_artifact')
    for name, body in (('bad/bad.py', _BAD), ('ok/ok.py', _OK)):
        (root / name).parent.mkdir(exist_ok=True)
        (root / name).write_text(body, encoding='utf-8')
    (root / 'sink').mkdir()  # a directory: not writable as a file
    return root


# (label, target, findings exit when the artifact is fine)
TARGETS = [
    ('dir-clean', 'ok', 0),
    ('dir-findings', 'bad', 1),
    ('file-clean', 'ok/ok.py', 0),
    ('file-findings', 'bad/bad.py', 1),
]


@pytest.mark.parametrize('fmt', ['text', 'grep'])
@pytest.mark.parametrize('label, target, own_exit', TARGETS, ids=[t[0] for t in TARGETS])
def test_unwritable_artifact_exits_three_and_keeps_the_answer(tree, label, target, own_exit, fmt):
    alone = _reveal(tree, 'check', target, '--format', fmt)
    assert alone.returncode == own_exit, alone.stderr
    failed = _reveal(tree, 'check', target, '--format', fmt, '--also-json', 'sink')
    assert failed.returncode == 3, (failed.returncode, failed.stderr)
    assert failed.stdout == alone.stdout                              # primary answer, in full
    assert failed.stdout.strip() or (own_exit == 0 and fmt == 'grep')  # (a clean grep report is empty)
    assert failed.stderr.count(_FAILED) == 1                          # disclosed once
    assert 'could not write' not in failed.stderr                     # not the old warning
    assert 'Traceback' not in failed.stderr


@pytest.mark.parametrize('label, target, own_exit', TARGETS, ids=[t[0] for t in TARGETS])
def test_exit_zero_does_not_hide_the_artifact_failure(tree, label, target, own_exit):
    """Required output failure survives the legacy --exit-zero override (execution_exit_code)."""
    result = _reveal(tree, 'check', target, '--exit-zero', '--also-json', 'sink')
    assert result.returncode == 3, result.stderr
    assert result.stderr.count(_FAILED) == 1


def test_stdin_check_exits_three_on_an_unwritable_artifact(tree):
    result = _reveal(tree, '--stdin', '--check', '--also-json', 'sink', stdin='ok/ok.py\n')
    assert result.returncode == 3, (result.returncode, result.stderr)
    assert result.stderr.count(_FAILED) == 1


# Negative controls: nothing changes when the artifact is written.

@pytest.mark.parametrize('label, target, own_exit', TARGETS, ids=[t[0] for t in TARGETS])
def test_written_artifact_keeps_the_scan_exit_and_the_format_json_document(tree, tmp_path, label, target, own_exit):
    artifact = tmp_path / 'report.json'
    shown = _reveal(tree, 'check', target, '--output', f'json={artifact}')
    assert shown.returncode == own_exit, shown.stderr
    assert _FAILED not in shown.stderr
    primary = _reveal(tree, 'check', target, '--format', 'json')
    assert primary.returncode == own_exit
    assert json.loads(artifact.read_text(encoding='utf-8')) == json.loads(primary.stdout)


@pytest.mark.parametrize('label, target, own_exit', TARGETS, ids=[t[0] for t in TARGETS])
def test_json_primary_also_json_stays_a_no_op(tree, label, target, own_exit):
    """The artifact would equal the primary document, so --format json never writes (or fails) it."""
    result = _reveal(tree, 'check', target, '--format', 'json', '--also-json', 'sink')
    assert result.returncode == own_exit, result.stderr
    assert _FAILED not in result.stderr
    assert 'output_errors' not in json.loads(result.stdout).get('meta', {})


def test_artifact_failure_cannot_lower_a_degraded_scan(tree):
    """Scan incomplete is 3 already; the artifact failure adds its disclosure, not a different code."""
    broken = tree / 'broken.py'
    broken.write_text('def (:\n    return\n', encoding='utf-8')
    try:
        result = _reveal(tree, 'check', 'broken.py', '--also-json', 'sink')
    finally:
        broken.unlink()
    assert result.returncode == 3
    assert result.stderr.count(_FAILED) == 1


# The owner, flag-agnostic: any sink that hands it a writer gets the same disclosure shape.

def test_owner_records_the_failure_in_meta_output_errors(capsys):
    result = {'type': 'demo', 'meta': {}}

    def write():
        raise IsADirectoryError('sink')

    failure = write_requested_artifact(write, result)
    assert isinstance(failure, IsADirectoryError)
    assert result['meta']['output_errors'] == [
        {'code': 'artifact_write_failed', 'message': f'{_FAILED}: sink'}]
    assert capsys.readouterr().err == f'Error: {_FAILED}: sink\n'


def test_owner_is_silent_on_success(capsys):
    result = {'type': 'demo'}
    assert write_requested_artifact(lambda: None, result) is None
    assert 'meta' not in result and capsys.readouterr().err == ''
