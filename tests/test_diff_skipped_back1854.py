"""diff:// discloses a git-directory file it could not analyze (BACK-1854).

A blob the analyzer raised on was a log line and absent from that side's elements, so when
the other side analyzed it the tree diff reported its functions as added or removed.
"""
from unittest.mock import patch

from reveal.adapters.diff import DiffAdapter
from reveal.diff.structure_diff import element_categories


def _struct(funcs, skipped=None):
    return {'type': 'git_directory', 'functions': funcs, 'classes': [], 'imports': [],
            **({'skipped_files': skipped} if skipped else {})}


def _run(left, right):
    sides = {'git://HEAD~1/pkg': left, 'git://HEAD/pkg': right}
    with patch('reveal.adapters.diff.adapter.resolve_uri', side_effect=lambda uri, **kw: sides[uri]):
        return DiffAdapter('git://HEAD~1/pkg', 'git://HEAD/pkg').get_structure()


def _failed(result):
    return [w for w in result.get('meta', {}).get('warnings', []) if w.get('type') == 'analysis_failed']


def test_skipped_files_are_not_an_element_category():
    assert element_categories(_struct([], {'pkg/a.py': 'ValueError: boom'})) == [
        'functions', 'classes', 'imports']


def test_a_file_skipped_on_one_side_is_disclosed_with_the_resulting_added():
    left = _struct([], {'pkg/a.py': 'ValueError: boom'})
    right = _struct([{'name': 'f', 'file': 'a.py', 'line': 1}])
    result = _run(left, right)
    assert result['summary']['functions']['added'] == 1  # the misleading part
    (warning,) = _failed(result)
    assert warning['field'] == 'left' and warning['files'] == ['pkg/a.py']
    assert 'added or removed' in warning['message'] and 'ValueError' in warning['message']


def test_both_sides_clean_has_no_analysis_warning():
    result = _run(_struct([]), _struct([{'name': 'f', 'file': 'a.py', 'line': 1}]))
    assert not _failed(result)
