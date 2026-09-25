"""BACK-1473: the documented diff://a.py:b.py/element form.

help://schemas/diff shows `diff://app.py:old.py/handle_request`, but the element suffix
was parsed as part of the right-hand path ("No analyzer found for file: b.py/foo").
"""
import subprocess
import sys

import pytest

from reveal.adapters.diff import DiffAdapter
from reveal.adapters.diff.parsing import split_trailing_element

LEFT = "def foo():\n    return 1\n\n\ndef bar():\n    return 2\n"
RIGHT = "def foo(x):\n    return x\n\n\ndef bar():\n    return 2\n"


@pytest.fixture
def two_files(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text(LEFT, encoding='utf-8')
    (tmp_path / "b.py").write_text(RIGHT, encoding='utf-8')
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.py").write_text(RIGHT, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run_reveal(cwd, *args):
    return subprocess.run(
        [sys.executable, '-m', 'reveal.main'] + list(args),
        capture_output=True, text=True, encoding='utf-8', cwd=cwd,
    )


class TestSplitTrailingElement:
    def test_file_then_element(self, two_files):
        assert split_trailing_element("b.py/foo") == ("b.py", "foo")

    def test_dotted_method_element(self, two_files):
        assert split_trailing_element("b.py/Cls.method") == ("b.py", "Cls.method")

    def test_existing_path_is_never_split(self, two_files):
        assert split_trailing_element("sub/c.py") == ("sub/c.py", None)

    def test_directory_child_is_not_an_element(self, two_files):
        assert split_trailing_element("sub/missing.py") == ("sub/missing.py", None)

    def test_uri_right_side_is_left_alone(self, two_files):
        assert split_trailing_element("git://b.py@HEAD~1/foo") == ("git://b.py@HEAD~1/foo", None)


class TestAdapterEmbeddedElement:
    def test_element_split_off_right_uri(self, two_files):
        adapter = DiffAdapter("a.py:b.py/foo")
        assert (adapter.left_uri, adapter.right_uri, adapter.embedded_element) == ("a.py", "b.py", "foo")

    def test_plain_two_file_form_has_no_element(self, two_files):
        adapter = DiffAdapter("a.py:sub/c.py")
        assert (adapter.right_uri, adapter.embedded_element) == ("sub/c.py", None)


class TestCli:
    def test_documented_element_form_runs(self, two_files):
        r = run_reveal(two_files, "diff://a.py:b.py/foo")
        assert r.returncode == 0, r.stderr
        assert "Element Diff: foo" in r.stdout
        assert "No analyzer found" not in r.stderr

    def test_positional_element_still_works(self, two_files):
        r = run_reveal(two_files, "diff://a.py:b.py", "foo")
        assert r.returncode == 0, r.stderr
        assert "Element Diff: foo" in r.stdout

    def test_no_element_is_still_a_structure_diff(self, two_files):
        r = run_reveal(two_files, "diff://a.py:sub/c.py")
        assert r.returncode == 0, r.stderr
        assert "Structure Diff" in r.stdout
