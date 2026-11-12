"""D001 and D002 do not compare two functions that occupy the same lines (BACK-2500).

Bodies are read by the structure's line range (``_bodies.extract_function_body``), so a function
declared inside another on the same lines (minified JavaScript: ``function T(a){function g(b){...``)
gets the same extracted text as its parent. D001 called that pair identical and named the finding's
own line as the earlier occurrence ("'g' identical to 'T' (line 1)" at line 1); D002 called it ~100%
similar. The rule census (scripts/rule_census.py) found four on a pinned corpus. Real duplicates on
their own lines stay findings.
"""
from conftest import _run_reveal_direct


def findings(tmp_path, name, text, rules='D001,D002'):
    f = tmp_path / name
    f.write_bytes(text.encode('utf-8'))
    result = _run_reveal_direct('check', f, '--select', rules, '--severity', 'low')
    return [line for line in result.stdout.splitlines() if ' D00' in line]


NESTED_SHORT = ('function T(a) { function g(b) { var w = b * 2;\n'
                '  return w + 1; } var u = g(a) * 3; return u + 4; }\n')

NESTED_LONG = ('function T(a) { function g(b) { var w = b * 2;\n'
               + ''.join(f'  if (w > {i * 10}) {{ w = w - {i}; }}\n' for i in range(1, 10))
               + '  return w + 1; } var u = g(a) * 3; return u + 4; }\n')


def test_d001_does_not_compare_a_function_with_one_on_the_same_lines(tmp_path):
    assert findings(tmp_path, 'n.js', NESTED_SHORT, 'D001') == []


def test_d002_does_not_compare_a_function_with_one_on_the_same_lines(tmp_path):
    assert findings(tmp_path, 'q.js', NESTED_LONG, 'D002') == []


def test_real_duplicates_on_their_own_lines_are_still_d001(tmp_path):
    text = ('function a(x) {\n  var y = x * 2;\n  return y + 1;\n}\n'
            'function b(x) {\n  var y = x * 2;\n  return y + 1;\n}\n')
    hits = findings(tmp_path, 'dup.js', text, 'D001')
    assert len(hits) == 1 and "'b' identical to 'a' (line 1)" in hits[0], hits


def test_real_near_duplicates_on_their_own_lines_are_still_d002(tmp_path):
    body = ''.join(f'  if (w > {i * 10}) {{ w = w - {i}; }}\n' for i in range(1, 10))
    text = (f'function a(w) {{\n{body}  return w + 1;\n}}\n'
            f'function b(w) {{\n{body}  return w + 2;\n}}\n')
    hits = findings(tmp_path, 'near.js', text, 'D002')
    assert len(hits) == 1 and "'b'" in hits[0] and "'a'" in hits[0], hits
