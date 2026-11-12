"""Bare path forms exit 2 for an invalid resource, like `check` does (BACK-2492).

D6: exit 1 means a findings gate matched. A missing path, a file no analyzer reads and a
named element that is not in the file are invalid resources (plan rule 9), so they exit 2,
the code `reveal check <missing>` already returns.
"""

from conftest import _run_reveal_in
import pytest


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding='utf-8')
    return path


def test_missing_path_exits_2(tmp_path):
    result = _run_reveal_in(tmp_path, 'no_such_file.py')
    assert result.returncode == 2
    assert 'no_such_file.py not found' in result.stderr


@pytest.mark.parametrize('scheme', ['git', 'markdown', 'json', 'codex'])
def test_uri_only_noun_names_working_spelling(tmp_path, scheme):
    result = _run_reveal_in(tmp_path, scheme, 'src with spaces')
    assert result.returncode == 2
    assert f'{scheme}://src with spaces' in result.stderr
    assert 'URI noun' in result.stderr
    assert 'Running from' not in result.stderr


def test_existing_directory_named_for_a_scheme_stays_a_path(tmp_path):
    (tmp_path / 'git').mkdir()
    result = _run_reveal_in(tmp_path, 'git')
    assert result.returncode == 0
    assert 'URI noun' not in result.stderr


def test_missing_path_exits_2_like_check(tmp_path):
    bare = _run_reveal_in(tmp_path, 'no_such_file.py')
    check = _run_reveal_in(tmp_path, 'check', 'no_such_file.py')
    assert (bare.returncode, check.returncode) == (2, 2)


def test_missing_element_exits_2_and_lists_names(tmp_path):
    _write(tmp_path, 'mod.py', 'def present():\n    return 1\n')
    result = _run_reveal_in(tmp_path, 'mod.py', 'absent')
    assert result.returncode == 2
    assert "Element 'absent' not found" in result.stderr
    assert 'present' in result.stderr


def test_unsupported_file_exits_2(tmp_path):
    _write(tmp_path, 'README.rst', 'Title\n=====\n')
    result = _run_reveal_in(tmp_path, 'README.rst')
    assert result.returncode == 2
    assert 'No analyzer found' in result.stderr


def test_unsupported_file_names_no_other_language(tmp_path):
    _write(tmp_path, 'README.rst', 'Title\n=====\n')
    result = _run_reveal_in(tmp_path, 'README.rst')
    assert 'Similar supported extensions' not in result.stderr
    assert '.rs' not in result.stderr.replace('.rst', '')


def test_present_element_still_exits_0(tmp_path):
    _write(tmp_path, 'mod.py', 'def present():\n    return 1\n')
    result = _run_reveal_in(tmp_path, 'mod.py', 'present')
    assert result.returncode == 0
    assert 'return 1' in result.stdout


def test_missing_element_with_a_nav_flag_exits_2_like_without(tmp_path):
    _write(tmp_path, 'mod.py', 'def present():\n    return 1\n')
    codes = {flag: _run_reveal_in(tmp_path, 'mod.py', 'absent', *flag).returncode
             for flag in [(), ('--effects',), ('--boundary',), ('--exits',)]}
    assert set(codes.values()) == {2}, codes
