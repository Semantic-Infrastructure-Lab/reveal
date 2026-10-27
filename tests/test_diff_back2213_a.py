"""diff:// element paths and directory diffs (BACK-2213 lane A, F25/F26).

F25: ``diff://l.py:r.py/K.m`` said "Element 'K.m' not found" although ``reveal r.py K.m``
extracts it; ``find_element`` compared the bare name only.
F26: a directory diff dropped the file from added/removed entries (JSON had no ``file``)
and the text listed same-named changes from different files with nothing to tell them apart.
"""

import contextlib
import io

from reveal.adapters.diff.adapter import DiffAdapter
from reveal.adapters.diff.resolution import find_element, resolve_uri
from reveal.rendering.diff import render_diff

LEFT = "class K:\n    def m(self):\n        return 1\n\n\nclass J:\n    def m(self):\n        return 3\n"
RIGHT = "class K:\n    def m(self):\n        x = 2\n        return x\n\n\nclass J:\n    def m(self):\n        return 3\n"


def _pair(tmp_path):
    left, right = tmp_path / 'l.py', tmp_path / 'r.py'
    left.write_text(LEFT, encoding='utf-8')
    right.write_text(RIGHT, encoding='utf-8')
    return left, right


def test_find_element_matches_owner_dot_name(tmp_path):
    left, _ = _pair(tmp_path)
    structure = resolve_uri(str(left))
    assert find_element(structure, 'K.m')['line'] == 2
    assert find_element(structure, 'J.m')['line'] == 7
    assert find_element(structure, 'K.nope') is None


def test_element_diff_with_class_dot_method(tmp_path):
    left, right = _pair(tmp_path)
    result = DiffAdapter(f'{left}:{right}').get_element('K.m')
    assert result['change'] == 'modified'
    # J.m only moved down a line: a move, not a modification (BACK-2281)
    moved = DiffAdapter(f'{left}:{right}').get_element('J.m')
    assert moved['change'] == 'unchanged' and set(moved['moved']) == {'line', 'line_end'}


def _dirs(tmp_path):
    for side, body in (('d1', 'def keep():\n    return 1\n\ndef gone():\n    return 0\n'),
                       ('d2', 'def keep():\n    return 1\n\ndef newf(a):\n    return a\n')):
        for name in ('x.py', 'sub/m.py'):
            path = tmp_path / side / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding='utf-8')
    return tmp_path / 'd1', tmp_path / 'd2'


def test_directory_diff_entries_carry_their_file(tmp_path):
    d1, d2 = _dirs(tmp_path)
    result = DiffAdapter(f'{d1}/:{d2}/').get_structure()
    entries = {(e['type'], e['name'], e.get('file')) for e in result['diff']['functions']}
    assert entries == {('added', 'newf', 'x.py'), ('added', 'newf', 'sub/m.py'),
                       ('removed', 'gone', 'x.py'), ('removed', 'gone', 'sub/m.py')}


def test_directory_diff_text_names_the_file(tmp_path):
    d1, d2 = _dirs(tmp_path)
    result = DiffAdapter(f'{d1}/:{d2}/').get_structure()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        render_diff(result, 'text', is_element=False)
    text = out.getvalue()
    assert '+ newf  (x.py)' in text and '+ newf  (sub/m.py)' in text
    assert '- gone  (x.py)' in text and '- gone  (sub/m.py)' in text


def test_same_named_methods_of_two_classes_do_not_collide(tmp_path):
    """Keyed by bare name, J.m replaced K.m and the K.m change was never reported."""
    left, right = _pair(tmp_path)
    result = DiffAdapter(f'{left}:{right}').get_structure()
    assert [(e['type'], e['name']) for e in result['diff']['functions']] == [('modified', 'K.m')]
    assert 'file' not in result['diff']['functions'][0]  # a file diff has no per-entry file
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        render_diff(result, 'text', is_element=False)
    assert '  ~ K.m\n' in out.getvalue()
