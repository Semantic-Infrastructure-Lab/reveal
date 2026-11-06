"""Directory --grep discloses a file it could not read instead of skipping it (BACK-2520).

``reveal DIR --grep PAT`` dropped an unreadable file, still counted it in ``files_searched``,
printed no warning and exited 0: a search that missed matches read as complete.
"""
import json
import os
import subprocess
import sys
from argparse import Namespace

import pytest

from reveal import grep_handler
from reveal.cli.routing.grep import handle_grep_directory

TEXT = 'def good():\n    return good\n'


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """ok.py and locked.py hold the same two hits; locked.py cannot be read."""
    (tmp_path / 'ok.py').write_text(TEXT, encoding='utf-8')
    (tmp_path / 'locked.py').write_text(TEXT, encoding='utf-8')
    real = grep_handler._read_lines

    def read(fpath):
        if fpath.name == 'locked.py':
            raise PermissionError(13, 'Permission denied', str(fpath))
        return real(fpath)

    monkeypatch.setattr(grep_handler, '_read_lines', read)
    return tmp_path


def _run(path, pattern, output_format):
    try:
        handle_grep_directory(str(path), pattern, Namespace(format=output_format))
    except SystemExit as stop:
        return stop.code
    return 0


def test_result_counts_only_files_read_and_names_the_lost_one(tree):
    result = grep_handler.grep_directory(str(tree), 'good', Namespace(format='json'))
    assert result['total_hits'] == 2 and result['files_matched'] == 1
    assert result['files_searched'] == 1  # locked.py was not searched
    [warning] = result['meta']['warnings']
    assert warning['type'] == 'analysis_failed'
    assert warning['files'] == ['locked.py'] and warning['count'] == 1
    assert 'PermissionError' in warning['message']


@pytest.mark.parametrize('output_format', ['text', 'json'])
def test_incomplete_search_exits_3_and_says_so(tree, capsys, output_format):
    assert _run(tree, 'good', output_format) == 3
    out = capsys.readouterr().out
    if output_format == 'json':
        assert json.loads(out)['meta']['warnings'][0]['files'] == ['locked.py']
    else:
        assert '2 hits across 1 file' in out
        assert 'could not be analyzed completely (PermissionError)' in out and 'locked.py' in out


def test_no_match_with_a_lost_file_is_not_a_clean_zero(tree, capsys):
    assert _run(tree, 'absent', 'text') == 3
    out = capsys.readouterr().out
    assert 'No matches found in 1 file.' in out and 'locked.py' in out


def test_mcp_grep_returns_the_answer_with_the_loss_named(tree):
    """MCP keeps stdout over the exit code, so its client sees both the hits and the loss."""
    from reveal.mcp_server import reveal_grep
    out = reveal_grep(str(tree), 'good')
    assert 'ok.py' in out and 'could not be analyzed completely' in out and 'locked.py' in out


def test_readable_tree_stays_clean(tmp_path, capsys):
    """Positive control: nothing lost, no warning, exit 0."""
    (tmp_path / 'ok.py').write_text(TEXT, encoding='utf-8')
    result = grep_handler.grep_directory(str(tmp_path), 'good', Namespace(format='json'))
    assert 'meta' not in result and result['files_searched'] == 1
    assert _run(tmp_path, 'good', 'text') == 0
    assert 'could not be analyzed' not in capsys.readouterr().out


@pytest.mark.skipif(sys.platform == 'win32' or not hasattr(os, 'geteuid') or os.geteuid() == 0,
                    reason='chmod 000 does not block reads on Windows or for root')
def test_cli_with_a_real_unreadable_file(tmp_path):
    (tmp_path / 'ok.py').write_text(TEXT, encoding='utf-8')
    locked = tmp_path / 'locked.py'
    locked.write_text(TEXT, encoding='utf-8')
    locked.chmod(0)
    try:
        proc = subprocess.run([sys.executable, '-m', 'reveal', str(tmp_path), '--grep', 'good',
                               '--format', 'json'], capture_output=True, text=True,
                              encoding='utf-8', timeout=120)
    finally:
        locked.chmod(0o644)
    assert proc.returncode == 3, proc.stderr
    assert json.loads(proc.stdout)['meta']['warnings'][0]['files'] == ['locked.py']
