"""BACK-1834: calls:// presentation residuals from the Sprint 4 review (slice 3, F6/F7/F10).

F7  callers text names the call line and the JSX line of a name that is both called and
    rendered; callees text labels a reference-only callee `JSX reference`.
F6  `<module>` callees report the first call line (what callers report), not 1.
F10 `--sideeffects --transitive` labels a hop that only renders a component.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.calls.index import find_callees, find_callers

pytestmark = pytest.mark.component

PRES = (
    'export function Btn() { return null; }\n'         # 1
    'export function App() {\n'                          # 2
    '  Btn();\n'                                         # 3
    '  return <div><Btn/><Btn/></div>;\n'                # 4
    '}\n'                                                # 5
    'export function One() { return <Btn/>; }\n'         # 6
    'export function Two() {\n'                          # 7
    '  return <div>\n'                                   # 8
    '    <Btn/>\n'                                       # 9
    '  </div>;\n'                                        # 10
    '}\n'                                                # 11
    '<Btn/>;\n'                                          # 12
    'Btn();\n'                                           # 13
)


def _text(tmp_path, query):
    result = _run_reveal_direct('calls://' + str(tmp_path) + '?' + query)
    assert result.returncode == 0, result.stderr
    return result.stdout


def _row(text, caller):
    return next(line for line in text.splitlines() if f'  {caller}  (' in line)


def _pres(tmp_path):
    (tmp_path / 'p.tsx').write_text(PRES, encoding='utf-8')


def test_callers_text_names_the_call_line_and_the_jsx_line(tmp_path):
    _pres(tmp_path)
    text = _text(tmp_path, 'target=Btn')
    assert _row(text, 'App').endswith('(calls and JSX reference to Btn) [call line 3, JSX line 4]')
    assert _row(text, '<module>').endswith('(calls and JSX reference to Btn) [call line 13, JSX line 12]')


def test_callers_json_carries_the_call_line_of_a_function_that_also_renders(tmp_path):
    _pres(tmp_path)
    app = next(r for r in find_callers(str(tmp_path), 'Btn')['levels'][0]['callers'] if r['caller'] == 'App')
    assert app['relationship'] == 'call_and_jsx_reference'
    assert app['call_lines'] == [3] and app['reference_lines'] == [4]


def test_a_single_jsx_line_is_singular(tmp_path):
    _pres(tmp_path)
    text = _text(tmp_path, 'target=Btn')
    assert _row(text, 'One').endswith('(JSX reference to Btn) [JSX line 6]')
    assert _row(text, 'Two').endswith('(JSX reference to Btn) [JSX line 9]')


def test_plain_call_locations_keep_their_format(tmp_path):
    """Negative control: a name that is only called prints as before."""
    (tmp_path / 'a.py').write_text(
        'def helper(): return 1\n'            # 1
        'def once(): return helper()\n'       # 2
        'helper()\n'                          # 3
        'helper()\n', encoding='utf-8')       # 4
    text = _text(tmp_path, 'target=helper')
    assert _row(text, 'once').endswith('(calls helper)')
    assert _row(text, '<module>').endswith('(calls helper) [lines 3, 4]')


def test_callees_text_labels_reference_only_and_mixed_callees(tmp_path):
    (tmp_path / 'c.tsx').write_text(
        'function Both() { return null; }\n'
        'function Only() { return null; }\n'
        'function plain() { return 1; }\n'
        'function App() {\n'
        '  Both(); plain();\n'
        '  return <div><Both/><Only/></div>;\n'
        '}\n', encoding='utf-8')
    text = _text(tmp_path, 'callees=App')
    assert '→ Only (JSX reference)' in text
    assert '→ Both (includes JSX reference)' in text
    assert any(line.strip() == '→ plain' for line in text.splitlines())


def test_callees_of_a_module_report_the_first_call_line(tmp_path):
    (tmp_path / 's.py').write_text(
        'def helper():\n    return 1\n\n\nhelper()\nhelper()\n', encoding='utf-8')
    (tmp_path / 'a.jsx').write_text(
        'function Button() { return null; }\n'
        'function helper() { return 1; }\n'
        'export default function () { return <Button/>; }\n'
        '\n\n'
        'helper();\n', encoding='utf-8')
    matches = find_callees(str(tmp_path), '<module>')['matches']
    by_name = {m['file'].replace('\\', '/').rsplit('/', 1)[-1]: m['line'] for m in matches}
    assert by_name == {'s.py': 5, 'a.jsx': 6}
    callers = find_callers(str(tmp_path), 'helper')['levels'][0]['callers']
    assert {r['file'].replace('\\', '/').rsplit('/', 1)[-1]: r['line'] for r in callers
            if r['caller'] == '<module>'} == {'s.py': 5, 'a.jsx': 6}


def test_callees_of_a_function_keep_the_definition_line(tmp_path):
    """Negative control: only `<module>` moves to a call line."""
    (tmp_path / 's.py').write_text('def helper(): return 1\n\n\ndef run():\n    return helper()\n',
                                   encoding='utf-8')
    match = find_callees(str(tmp_path), 'run')['matches'][0]
    assert match['line'] == 4


EFFECT_CHILD = (
    'export function Child(u: string) {\n'
    '  fetch(u);\n'
    '  return <div/>;\n'
    '}\n'
    'export function helper(u: string) {\n'
    '  fetch(u);\n'
    '}\n'
    'export function Render() {\n'
    '  return <Child/>;\n'
    '}\n'
    'export function Call() {\n'
    '  helper("x");\n'
    '  return null;\n'
    '}\n'
)


def _transitive(tmp_path, element, *extra):
    path = tmp_path / 'd.tsx'
    path.write_text(EFFECT_CHILD, encoding='utf-8')
    return _run_reveal_direct(str(path), element, '--sideeffects', '--transitive', *extra)


def test_transitive_labels_a_render_hop(tmp_path):
    result = _transitive(tmp_path, 'Render')
    assert result.returncode == 0, result.stderr
    assert '[hop 1] via Render → <Child/> (JSX render)' in result.stdout
    data = json.loads(_transitive(tmp_path, 'Render', '--format', 'json').stdout)
    hops = [f for f in data['findings'] if f.get('hop') == 1]
    assert hops and all(f['chain'] == ['Render', '<Child/>'] for f in hops)


def test_transitive_call_hop_is_not_labelled_as_render(tmp_path):
    """Negative control: a real call keeps the plain chain."""
    result = _transitive(tmp_path, 'Call')
    assert '[hop 1] via Call → helper' in result.stdout
    assert 'JSX render' not in result.stdout
    data = json.loads(_transitive(tmp_path, 'Call', '--format', 'json').stdout)
    assert [f['chain'] for f in data['findings'] if f.get('hop') == 1] == [['Call', 'helper']]
