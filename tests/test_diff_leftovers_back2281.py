"""diff:// leftovers (BACK-2281).

1. A directory diff keyed imports by their text across the whole tree: ``import sys`` added
   to two files counted once (``Imports: +1``) and the entry named no file.
2. An element diff called a function MODIFIED when only its position changed (an edit above it
   pushed it down), while the structure diff already ignores moves.
"""

import contextlib
import io

from reveal.adapters.diff.adapter import DiffAdapter
from reveal.rendering.diff import render_diff


def _tree(root, files):
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return root


def _text(result, is_element=False):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        render_diff(result, 'text', is_element=is_element)
    return out.getvalue()


# --- 1. directory diff imports ------------------------------------------------------------

def test_directory_diff_counts_an_import_added_in_two_files_twice(tmp_path):
    d1 = _tree(tmp_path / 'd1', {'x.py': 'x = 1\n', 'sub/m.py': 'y = 1\n'})
    d2 = _tree(tmp_path / 'd2', {'x.py': 'import sys\nx = 1\n', 'sub/m.py': 'import sys\ny = 1\n'})
    result = DiffAdapter(f'{d1}/:{d2}/').get_structure()
    assert result['summary']['imports']['added'] == 2
    entries = {(e['type'], e['content'], e.get('file')) for e in result['diff']['imports']}
    assert entries == {('added', 'import sys', 'x.py'), ('added', 'import sys', 'sub/m.py')}
    text = _text(result)
    assert 'import sys  (x.py)' in text and 'import sys  (sub/m.py)' in text


def test_directory_diff_import_moved_between_files_is_added_and_removed(tmp_path):
    d1 = _tree(tmp_path / 'd1', {'x.py': 'import os\n', 'y.py': 'z = 1\n'})
    d2 = _tree(tmp_path / 'd2', {'x.py': 'z = 1\n', 'y.py': 'import os\n'})
    result = DiffAdapter(f'{d1}/:{d2}/').get_structure()
    entries = {(e['type'], e['content'], e.get('file')) for e in result['diff']['imports']}
    assert entries == {('added', 'import os', 'y.py'), ('removed', 'import os', 'x.py')}


def test_file_diff_imports_unchanged(tmp_path):
    """Negative control: a two-file diff keeps its import entries as they were (no file key)."""
    left = tmp_path / 'l.py'
    right = tmp_path / 'r.py'
    left.write_text('import os\n', encoding='utf-8')
    right.write_text('import os\nimport sys\n', encoding='utf-8')
    result = DiffAdapter(f'{left}:{right}').get_structure()
    assert result['diff']['imports'] == [{'type': 'added', 'content': 'import sys', 'line': 2}]
    assert result['summary']['imports'] == {'added': 1, 'removed': 0}


# --- 2. element diff of a moved function --------------------------------------------------

LEFT = 'class J:\n    def m(self):\n        return 1\n'
MOVED = '# added\n\n\nclass J:\n    def m(self):\n        return 1\n'
EDITED = '# added\n\n\nclass J:\n    def m(self):\n        x = 1\n        return x\n'


def _element(tmp_path, right_text, name='J.m'):
    left, right = tmp_path / 'l.py', tmp_path / 'r.py'
    left.write_text(LEFT, encoding='utf-8')
    right.write_text(right_text, encoding='utf-8')
    return DiffAdapter(f'{left}:{right}').get_element(name)


def test_element_that_only_moved_is_unchanged(tmp_path):
    result = _element(tmp_path, MOVED)
    assert result['change'] == 'unchanged'
    assert result['moved'] == {'line': {'old': 2, 'new': 5}, 'line_end': {'old': 3, 'new': 6}}
    text = _text(result, is_element=True)
    assert 'UNCHANGED' in text and 'MODIFIED' not in text
    assert 'moved from line 2 to line 5' in text


def test_element_that_moved_and_changed_is_still_modified(tmp_path):
    """Negative control: a real edit plus a move stays MODIFIED and lists both."""
    result = _element(tmp_path, EDITED)
    assert result['change'] == 'modified'
    assert {'line', 'line_end', 'line_count'} <= set(result['changes'])


def test_moved_element_with_a_body_only_edit_is_modified_and_lists_the_move(tmp_path):
    """Negative control: a source-only edit (same shape) on a moved element is MODIFIED."""
    result = _element(tmp_path, MOVED.replace('return 1', 'return 10'))
    assert result['change'] == 'modified'
    assert set(result['changes']) == {'line', 'line_end', 'body'}
    assert 'moved' not in result and 'message' not in result


def test_identical_element_is_unchanged_without_a_move(tmp_path):
    """Negative control: same place, same body."""
    result = _element(tmp_path, LEFT)
    assert result['change'] == 'unchanged'
    assert 'moved' not in result
