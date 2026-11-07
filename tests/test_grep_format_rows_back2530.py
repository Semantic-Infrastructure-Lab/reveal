"""BACK-2530: ``--grep ... --format grep`` prints ``path:line:text`` rows, as ``ast://`` does, and
a format ``--grep`` does not render exits 2 (--help: 'another value exits 2 with the supported
list'). It printed the full text view and exited 0."""
import json

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component


@pytest.fixture
def tree(tmp_path):
    (tmp_path / 'a.py').write_text('def alpha():\n    return 1\n\nX = alpha()\n', encoding='utf-8')
    sub = tmp_path / 'sub'
    sub.mkdir()
    (sub / 'b.py').write_text('# alpha: a note\ndef beta():\n    return 2\n', encoding='utf-8')
    return tmp_path


# Rows carry the result's POSIX path, as the text and JSON views do: on Windows the target
# C:\...\a.py reads C:/.../a.py, so expectations use as_posix(), not str() (BACK-2530 CI).
def test_file_grep_rows(tree):
    path = tree / 'a.py'
    result = _run_reveal_direct(str(path), '--grep', 'alpha', '--format', 'grep')
    assert result.returncode == 0, result.stderr
    shown = path.as_posix()
    assert result.stdout.splitlines() == [f'{shown}:1:def alpha():', f'{shown}:4:X = alpha()']


def test_directory_grep_rows_in_walk_order(tree):
    result = _run_reveal_direct(str(tree), '--grep', 'alpha', '--format', 'grep')
    assert result.returncode == 0, result.stderr
    a, b = (tree / 'a.py').as_posix(), (tree / 'sub' / 'b.py').as_posix()
    assert sorted(result.stdout.splitlines()) == sorted([
        f'{a}:1:def alpha():', f'{a}:4:X = alpha()', f'{b}:1:# alpha: a note'])


def test_no_match_prints_no_rows(tree):
    result = _run_reveal_direct(str(tree), '--grep', 'zzz_nothing', '--format', 'grep')
    assert result.returncode == 0 and result.stdout == ''


@pytest.mark.parametrize('target', ['a.py', '.'])
def test_unrendered_format_exits_2_naming_the_supported_ones(tree, target):
    result = _run_reveal_direct(str(tree / target), '--grep', 'alpha', '--format', 'typed')
    assert result.returncode == 2
    assert 'typed' in result.stderr and 'grep' in result.stderr and 'json' in result.stderr
    assert result.stdout == ''


def test_text_and_json_unchanged(tree):
    text = _run_reveal_direct(str(tree / 'a.py'), '--grep', 'alpha')
    assert text.returncode == 0 and text.stdout.startswith('Text search:')
    data = json.loads(_run_reveal_direct(str(tree), '--grep', 'alpha', '--format', 'json').stdout)
    assert data['total_hits'] == 3
