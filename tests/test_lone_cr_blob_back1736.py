"""BACK-1736: element source read from a git blob must use the analyzer's line numbers.

The analyzer reads a file in text mode, where universal newlines turn a lone ``\\r`` into a line
break. A git blob is decoded raw and split at ``\\n`` only (BACK-1722), so with a lone ``\\r`` above
an element the slice ``[line-1:line_end]`` was one line late:

- ``reveal 'diff://git://m.py@HEAD:m.py' target`` called an unchanged function MODIFIED (the git
  side's body lost its ``def`` line);
- ``reveal 'git://m.py?type=history&element=target'`` missed a commit that changed only the
  ``def`` line (both slices skipped it).

Negative controls: the same files with LF and with CRLF line ends behave as before.
"""

import json
import subprocess
import sys

import pytest

pygit2 = pytest.importorskip('pygit2')

LONE_CR = b'x = 1\r# note\ndef target():\n    return 2\n'
LF = LONE_CR.replace(b'\r', b'\n')
CRLF = LF.replace(b'\n', b'\r\n')


def _reveal(cwd, *args):
    return subprocess.run([sys.executable, '-m', 'reveal', *args], cwd=cwd,
                          capture_output=True, text=True, encoding='utf-8', timeout=60)


def _repo(path, *versions):
    """A repo with one commit per version of m.py; the working tree holds the last one.

    ``* -text`` keeps git from converting line ends (Windows runners set core.autocrlf).
    """
    path.mkdir()
    repo = pygit2.init_repository(str(path))
    (path / '.gitattributes').write_bytes(b'* -text\n')
    author = pygit2.Signature('Test', 'test@example.com')
    parents = []
    for data in versions:
        (path / 'm.py').write_bytes(data)
        repo.index.add_all()
        repo.index.write()
        tree = repo.index.write_tree()
        parents = [repo.create_commit('HEAD', author, author, 'c', tree, parents)]
    return path


def _element_diff(repo_dir):
    proc = _reveal(repo_dir, 'diff://git://m.py@HEAD:m.py', 'target', '--format', 'json')
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _history(repo_dir):
    proc = _reveal(repo_dir, 'git://m.py?type=history&element=target', '--format', 'json')
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_unchanged_element_beside_lone_cr_is_unchanged(tmp_path):
    result = _element_diff(_repo(tmp_path / 'r', LONE_CR))
    assert result['change'] == 'unchanged', result.get('changes')


def test_history_sees_def_line_change_beside_lone_cr(tmp_path):
    renamed = LONE_CR.replace(b'target()', b'target(a)')
    result = _history(_repo(tmp_path / 'r', LONE_CR, renamed))
    assert result['count'] == 2


@pytest.mark.parametrize('data', [LF, CRLF], ids=['lf', 'crlf'])
def test_lf_and_crlf_element_diff_is_unchanged(tmp_path, data):
    assert _element_diff(_repo(tmp_path / 'r', data))['change'] == 'unchanged'


@pytest.mark.parametrize('data', [LF, CRLF], ids=['lf', 'crlf'])
def test_lf_and_crlf_history_sees_def_line_change(tmp_path, data):
    renamed = data.replace(b'target()', b'target(a)')
    assert _history(_repo(tmp_path / 'r', data, renamed))['count'] == 2


def test_real_body_change_is_still_modified(tmp_path):
    repo_dir = _repo(tmp_path / 'r', LONE_CR)
    (repo_dir / 'm.py').write_bytes(LONE_CR.replace(b'return 2', b'return 3'))
    result = _element_diff(repo_dir)
    assert result['change'] == 'modified'
    assert result['changes']['body'] == {'old': 'def target():\n    return 2',
                                         'new': 'def target():\n    return 3'}


def test_normalize_newlines_values():
    from reveal.utils.lines import normalize_newlines
    assert normalize_newlines('a\r\nb\rc\nd') == 'a\nb\nc\nd'
    assert normalize_newlines('a\r\r\nb') == 'a\n\nb'
    assert normalize_newlines('') == ''
    assert normalize_newlines('no breaks') == 'no breaks'
