"""BACK-1492: element diff must see body-only edits, and adapter errors must not traceback.

`reveal diff://a.py:b.py foo` compared signature/line count/complexity only, so
`return 1` -> `return 10` reported "identical in both resources". A failing
get_element also escaped as a raw traceback instead of the one-line adapter error
that the structure path prints.
"""
import subprocess
import sys

import pytest

from reveal.adapters.diff import DiffAdapter
from reveal.adapters.diff.resolution import read_element_source

ONE = "def foo():\n    return 1\n"
TEN = "def foo():\n    return 10\n"


@pytest.fixture
def files(tmp_path):
    (tmp_path / "a.py").write_text(ONE, encoding='utf-8')
    (tmp_path / "b.py").write_text(TEN, encoding='utf-8')
    (tmp_path / "same.py").write_text(ONE, encoding='utf-8')
    return tmp_path


def run_reveal(cwd, *args):
    return subprocess.run(
        [sys.executable, '-m', 'reveal.main'] + list(args),
        capture_output=True, text=True, encoding='utf-8', cwd=cwd,
    )


class TestBodyComparison:
    def test_body_only_change_is_modified(self, files):
        result = DiffAdapter(f"{files}/a.py:{files}/b.py").get_element("foo")
        assert result['type'] == 'modified'
        assert result['changes']['body'] == {
            'old': "def foo():\n    return 1", 'new': "def foo():\n    return 10"}

    def test_identical_bodies_stay_unchanged(self, files):
        result = DiffAdapter(f"{files}/a.py:{files}/same.py").get_element("foo")
        assert result['type'] == 'unchanged'
        assert 'identical' in result['message']

    def test_structural_change_keeps_body_change_too(self, files):
        (files / "c.py").write_text("def foo(x):\n    return x\n", encoding='utf-8')
        result = DiffAdapter(f"{files}/a.py:{files}/c.py").get_element("foo")
        assert result['type'] == 'modified'
        assert {'signature', 'body'} <= set(result['changes'])

    def test_unreadable_source_does_not_claim_identical(self, files, monkeypatch):
        monkeypatch.setattr('reveal.adapters.diff.adapter.read_element_source',
                            lambda uri, elem: None)
        result = DiffAdapter(f"{files}/a.py:{files}/same.py").get_element("foo")
        assert result['type'] == 'unchanged'
        assert 'body not compared' in result['message']
        assert 'identical' not in result['message']

    def test_cli_text_shows_unified_diff(self, files):
        proc = run_reveal(files, 'diff://a.py:b.py', 'foo')
        assert proc.returncode == 0, proc.stderr
        assert 'MODIFIED' in proc.stdout
        assert '-    return 1' in proc.stdout and '+    return 10' in proc.stdout


class TestReadElementSource:
    def test_plain_path_and_file_scheme(self, files):
        elem = {'line': 1, 'line_end': 2}
        expected = "def foo():\n    return 1"
        assert read_element_source(str(files / "a.py"), elem) == expected
        assert read_element_source(f"file://{files}/a.py", elem) == expected

    def test_missing_line_info_or_file_or_scheme_is_none(self, files):
        assert read_element_source(str(files / "a.py"), {}) is None
        assert read_element_source(str(files / "nope.py"), {'line': 1, 'line_end': 2}) is None
        assert read_element_source("env://", {'line': 1, 'line_end': 2}) is None


class TestGitSource:
    def test_git_ref_bodies_are_compared(self, tmp_path):
        pytest.importorskip('pygit2')
        env = {'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t',
               'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@t'}

        def git(*a):
            subprocess.run(['git', *a], cwd=tmp_path, check=True, capture_output=True,
                           env={**__import__('os').environ, **env})

        git('init', '-q')
        (tmp_path / "m.py").write_text(ONE, encoding='utf-8')
        git('add', 'm.py')
        git('commit', '-qm', 'a')
        (tmp_path / "m.py").write_text(TEN, encoding='utf-8')
        git('commit', '-qam', 'b')
        proc = run_reveal(tmp_path, 'diff://git://m.py@HEAD~1:git://m.py@HEAD', 'foo')
        assert proc.returncode == 0, proc.stderr
        assert 'MODIFIED' in proc.stdout and '+    return 10' in proc.stdout


class TestElementErrors:
    def test_missing_file_is_a_clean_error_not_a_traceback(self, files):
        proc = run_reveal(files, 'diff://nonexist.py:b.py', 'foo')
        assert proc.returncode == 1
        assert 'Traceback' not in proc.stderr
        assert 'Error (diff://)' in proc.stderr

    def test_missing_file_json_has_error_envelope(self, files):
        proc = run_reveal(files, 'diff://nonexist.py:b.py', 'foo', '--format', 'json')
        assert proc.returncode == 1
        assert 'Traceback' not in proc.stderr
        assert '"adapter_error"' in proc.stdout
