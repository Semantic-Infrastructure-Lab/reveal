"""BACK-2613 S4: ast text -- the standing caveats' one-line pointer (BACK-2599, ruling Q9) and the sorted order (B9).

Q9: the two standing caveats ast prints on every matching answer, ``complexity_is_unweighted`` (a query that filters on
complexity) and ``degraded_language_conformance`` (rows in a language below tier1-verified), print in text as the one
``Rules:`` pointer of ``utils/warning_render.rule_text_lines``; their full text stays in JSON ``meta.warnings``.
Request-specific warnings (a misspelled kind, a sort field that sorted nothing) stay visible in the text.

B9: text must not contradict the answer's order. Rows sorted across files print in the sorted order with the file on
each row instead of regrouped by file; an answer whose rows already come file by file keeps the grouped layout.
"""
import json

import pytest

from conftest import _run_reveal_in

A_PY = '''def alpha():
    pass

def beta(x):
    if x:
        return 1
    return 2

def delta():
    pass
'''
B_PY = '''def helper():
    pass

def test_one():
    if 1:
        pass
'''
C_DART = '''int add(int a, int b) {
  if (a > b) {
    return a;
  }
  return b;
}
'''
POINTER = 'Rules: --format json (meta.warnings)'
MCCABE = 'complexity is McCabe cyclomatic complexity'
DEGRADED = 'below tier1-verified conformance'


@pytest.fixture
def tree(tmp_path):
    pkg = tmp_path / 'pkg'
    pkg.mkdir()
    (pkg / 'a.py').write_text(A_PY, encoding='utf-8')
    (pkg / 'b.py').write_text(B_PY, encoding='utf-8')
    return tmp_path


@pytest.fixture
def mixed(tree):
    (tree / 'pkg' / 'c.dart').write_text(C_DART, encoding='utf-8')
    return tree


def text(tree, *argv):
    result = _run_reveal_in(tree, *argv)
    return result.returncode, result.stdout, result.stderr


def answer(tree, *argv):
    result = _run_reveal_in(tree, *argv, '--format', 'json')
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def warning_types(document):
    return [w.get('type') for w in (document.get('meta') or {}).get('warnings') or []]


# --- Q9: the standing caveats are one pointer line in text, full text in JSON ------------------------------------

@pytest.mark.parametrize('argv', [
    ('ast', 'pkg', '--where', 'complexity>1'),
    ('ast://pkg?complexity>1',),
])
def test_complexity_caveat_is_the_pointer_in_text(tree, argv):
    code, out, _ = text(tree, *argv)
    assert code == 0
    assert out.splitlines().count(POINTER) == 1, out
    assert MCCABE not in out, out


def test_complexity_caveat_full_text_stays_in_json(tree):
    document = answer(tree, 'ast', 'pkg', '--where', 'complexity>1')
    caveat = [w for w in document['meta']['warnings'] if w.get('type') == 'complexity_is_unweighted']
    assert len(caveat) == 1 and MCCABE in caveat[0]['message'], document['meta']


def test_degraded_language_caveat_is_the_pointer_in_text(mixed):
    code, out, _ = text(mixed, 'ast', 'pkg')
    assert code == 0
    assert out.splitlines().count(POINTER) == 1, out
    assert DEGRADED not in out and '--language-info' not in out, out
    assert 'add' in out


def test_degraded_language_caveat_full_text_stays_in_json(mixed):
    document = answer(mixed, 'ast', 'pkg')
    caveat = [w for w in document['meta']['warnings'] if w.get('type') == 'degraded_language_conformance']
    assert len(caveat) == 1 and DEGRADED in caveat[0]['message'], document['meta']


def test_both_caveats_share_one_pointer(mixed):
    code, out, _ = text(mixed, 'ast', 'pkg', '--where', 'complexity>1')
    assert code == 0
    assert out.splitlines().count(POINTER) == 1, out
    assert MCCABE not in out and DEGRADED not in out, out


def test_zero_rows_still_point_to_the_caveat(tree):
    code, out, _ = text(tree, 'ast', 'pkg', '--where', 'complexity>99')
    assert code == 0
    assert 'No matches found.' in out
    assert out.splitlines().count(POINTER) == 1, out
    assert MCCABE not in out, out


def test_request_specific_warning_stays_beside_the_pointer(tree):
    code, out, _ = text(tree, 'ast', 'pkg', '--kind', 'functoin', '--where', 'complexity>1')
    assert code == 0
    assert out.splitlines().count(POINTER) == 1, out
    assert "No scanned element has type 'functoin'" in out, out
    assert MCCABE not in out, out


def test_unknown_sort_field_stays_visible(tree):
    code, out, err = text(tree, 'ast', 'pkg', '--sort', 'bogus_field')
    assert code == 0
    assert 'bogus_field' in out + err
    assert POINTER not in out


def test_no_standing_caveat_no_pointer(tree):
    code, out, _ = text(tree, 'ast', 'pkg', '--kind', 'function')
    assert code == 0
    assert 'Rules:' not in out, out


def test_json_is_unchanged_by_the_pointer(mixed):
    document = answer(mixed, 'ast', 'pkg', '--where', 'complexity>1')
    assert 'Rules' not in json.dumps(document)
    assert {'complexity_is_unweighted', 'degraded_language_conformance'} <= set(warning_types(document))


# --- B9: text follows the answer's order ------------------------------------------------------------------------

def _text_row_names(out, names):
    """The element names in the text body, in printed order (rows only, not headers)."""
    found = []
    for line in out.splitlines():
        for name in names:
            if line.rstrip().split(' [')[0].endswith(f' {name}'):
                found.append(name)
    return found


@pytest.mark.parametrize('argv', [
    ('ast', 'pkg', '--sort=-name', '--kind', 'function'),
    ('ast://pkg?sort=-name&kind=function',),
])
def test_sorted_text_prints_rows_in_the_answer_order(tree, argv):
    document = answer(tree, *argv)
    order = [row['name'] for row in document['results']]
    assert order == ['test_one', 'helper', 'delta', 'beta', 'alpha']
    code, out, _ = text(tree, *argv)
    assert code == 0
    assert _text_row_names(out, order) == order, out


def test_sorted_text_names_the_file_on_each_row(tree):
    argv = ('ast', 'pkg', '--sort=-name', '--kind', 'function')
    rows = answer(tree, *argv)['results']
    _, out, _ = text(tree, *argv)
    lines = out.splitlines()
    for row in rows:
        printed = [line for line in lines if line.rstrip().split(' [')[0].endswith(f" {row['name']}")]
        assert len(printed) == 1 and row['file'] in printed[0], (row, out)
    assert not any(line.startswith('File: ') for line in lines), out


def test_unsorted_listing_keeps_the_file_groups(tree):
    _, out, _ = text(tree, 'ast', 'pkg', '--kind', 'function')
    lines = out.splitlines()
    assert [line for line in lines if line.startswith('File: ')] == ['File: pkg/a.py', 'File: pkg/b.py'], out
    assert _text_row_names(out, ['alpha', 'beta', 'delta', 'helper', 'test_one']) == [
        'alpha', 'beta', 'delta', 'helper', 'test_one']


def test_sort_within_one_file_keeps_the_group_in_sorted_order(tree):
    argv = ('ast', 'pkg/a.py', '--sort=-name', '--kind', 'function')
    order = [row['name'] for row in answer(tree, *argv)['results']]
    assert order == ['delta', 'beta', 'alpha']
    _, out, _ = text(tree, *argv)
    assert [line for line in out.splitlines() if line.startswith('File: ')] == ['File: pkg/a.py'], out
    assert _text_row_names(out, order) == order, out
