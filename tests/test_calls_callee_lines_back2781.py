"""BACK-2781: every ``calls --callees`` record says what each line is (the callees twin of BACK-2714).

A ``<module>`` definition said ``line``: its first call, where a function's record says its definition
line, in ``matches[]``, the walk's edges and ``definitions[]`` (two meanings in one field, D21). The
walk edge's ``caller_line``/``callee_line`` read as call lines but held definition lines. Now:

- a definition record (``matches[]``, ``definitions[]``, ``candidates[]``) keeps ``line``, the
  definition line; ``<module>``'s scope starts at line 1 (BACK-2714 ruling S2);
- a match carries ``call_lines_by_callee``: call text -> the sorted lines of its calls to it, keyed like
  ``calls`` (a name only rendered maps to ``[]``; its JSX lines are ``references[].line``);
- a walk edge names ``caller_def_line``/``callee_def_line`` and carries ``call_lines`` (a list, as on a
  callers record), plus ``reference_lines`` on a JSX edge: exactly the callers record of the same pair.

The lines come from the one call walk (the side table BACK-2714 stored with the structure).
"""
import json
import re

import pytest

from conftest import _run_reveal_direct
from reveal.api import query
from test_calls_call_lines_back2714 import (
    ALIASED, DEPTH_TWO, FAMILIES, JSX_OWNERS, _base, _cli_json, _cli_text, _family, _records, _write)

pytestmark = pytest.mark.component


def _matches(answer):
    """(file basename, function) -> match."""
    return {(_base(m['file']), m['function']): m for m in answer['matches']}


def _edges(answer):
    return [edge for level in answer['levels'] for edge in level['callees']]


# 1. Every family through `reveal calls DIR --callees NAME --format json`: one match per definition, its
# definition line and its call lines per callee, keyed exactly like `calls`.

@pytest.mark.parametrize('lang', sorted(FAMILIES))
def test_each_match_names_its_definition_line_and_its_call_lines_per_callee(tmp_path, lang):
    root, target, expected = _family(tmp_path, lang)
    file_name = FAMILIES[lang][0]
    got = {}
    for caller in expected:
        match = _matches(_cli_json('calls', str(root), '--callees', caller))[(file_name, caller)]
        by_callee = match.get('call_lines_by_callee')
        assert by_callee is not None and list(by_callee) == match['calls'], (caller, match)
        got[caller] = (match['line'], by_callee[target])
    assert got == expected


@pytest.mark.parametrize('lang', sorted(FAMILIES))
def test_each_function_match_keeps_its_calls_and_definition_line(tmp_path, lang):
    """Sibling: which names a definition calls, and a function's definition line, do not move."""
    root, target, expected = _family(tmp_path, lang)
    file_name = FAMILIES[lang][0]
    for caller, (def_line, _lines) in expected.items():
        match = _matches(_cli_json('calls', str(root), '--callees', caller))[(file_name, caller)]
        assert target in match['calls']
        if caller != '<module>':
            assert match['line'] == def_line


# 2. `<module>`'s definition line is 1, as the callers record says (BACK-2714 S2).

MODULE_FAMILIES = sorted(lang for lang in FAMILIES if '<module>' in FAMILIES[lang][3])


@pytest.mark.parametrize('lang', MODULE_FAMILIES)
def test_module_match_line_is_one(tmp_path, lang):
    root, target, expected = _family(tmp_path, lang)
    match = _matches(_cli_json('calls', str(root), '--callees', '<module>'))[(FAMILIES[lang][0], '<module>')]
    assert (match['line'], match.get('call_lines_by_callee', {}).get(target)) == (1, expected['<module>'][1])


@pytest.mark.parametrize('lang', MODULE_FAMILIES)
def test_module_match_still_lists_its_calls(tmp_path, lang):
    """Sibling: `<module>`'s calls do not move."""
    root, target, _ = _family(tmp_path, lang)
    match = _matches(_cli_json('calls', str(root), '--callees', '<module>'))[(FAMILIES[lang][0], '<module>')]
    assert target in match['calls']


def test_jsx_module_match_names_its_call_and_render_lines(tmp_path):
    root = _write(tmp_path / 'owners', {'p.tsx': JSX_OWNERS})
    match = _matches(_cli_json('calls', str(root), '--callees', '<module>'))[('p.tsx', '<module>')]
    assert (match['line'], match.get('call_lines_by_callee'), [r['line'] for r in match['references']]) == \
        (1, {'Btn': [15]}, [14])


@pytest.mark.parametrize('owner, want', [('Two', (7, {'Btn': [8, 11]}, [10])), ('One', (6, {'Btn': []}, [6]))])
def test_jsx_owner_match_names_call_lines_and_render_lines_apart(tmp_path, owner, want):
    root = _write(tmp_path / 'owners', {'p.tsx': JSX_OWNERS})
    match = _matches(_cli_json('calls', str(root), '--callees', owner))[('p.tsx', owner)]
    assert (match['line'], match.get('call_lines_by_callee'), [r['line'] for r in match['references']]) == want


# 3. Depth 2: every edge names its definition lines and carries its call lines.

def _walk(tmp_path, name, files=None):
    root, _, _ = _family(tmp_path, 'python')
    _write(root, files or DEPTH_TWO)
    return _cli_json('calls', str(root), '--callees', name, '--depth', '2')


def test_walk_edges_name_definition_lines_and_call_lines(tmp_path):
    edges = _edges(_walk(tmp_path, 'outer'))
    assert [(e['caller'], e['callee'], e.get('caller_def_line'), e.get('call_lines'), e.get('callee_def_line'),
             'caller_line' in e or 'callee_line' in e) for e in edges] == [
        ('outer', 'caller', 4, [6, 7], 5, False),
        ('caller', 'target', 5, [7, 9], 1, False)]


def test_walk_edge_set_and_totals_are_unchanged(tmp_path):
    """Sibling: which edges the walk finds, and its totals, do not move."""
    answer = _walk(tmp_path, 'outer')
    assert [(e['caller'], e['callee'], e['resolved'], e['expanded']) for e in _edges(answer)] == [
        ('outer', 'caller', True, True), ('caller', 'target', True, False)]
    assert (answer['total_edges'], answer['total_resolved'], answer['total_unresolved']) == (2, 2, 0)


def test_module_walk_edge_and_definition_start_at_line_one(tmp_path):
    answer = _walk(tmp_path, '<module>')
    module_edges = [(e.get('caller_def_line'), e.get('call_lines'), e.get('callee_def_line'))
                    for e in _edges(answer) if e['caller'] == '<module>']
    assert module_edges == [(1, [17, 18], 1)]
    assert [(d['name'], d['line']) for d in answer['definitions']] == [('<module>', 1), ('target', 1)]


def test_module_walk_finds_the_same_edges(tmp_path):
    """Sibling: the `<module>` walk's edges and definitions by name."""
    answer = _walk(tmp_path, '<module>')
    assert [(e['caller'], e['callee'], e['resolved']) for e in _edges(answer)] == [('<module>', 'target', True)]
    assert sorted(d['name'] for d in answer['definitions']) == ['<module>', 'target']


def test_jsx_walk_edge_carries_call_lines_and_reference_lines(tmp_path):
    root = _write(tmp_path / 'owners', {'p.tsx': JSX_OWNERS})
    for name, want in (('Two', (7, [8, 11], [10], 'call_and_jsx_reference')),
                       ('One', (6, [], [6], 'jsx_reference')),
                       ('<module>', (1, [15], [14], 'call_and_jsx_reference'))):
        edge = next(e for e in _edges(_cli_json('calls', str(root), '--callees', name, '--depth', '2'))
                    if e['caller'] == name)
        assert (edge.get('caller_def_line'), edge.get('call_lines'), edge.get('reference_lines'),
                edge['relationship']) == want, name


# 4. Twin: a walk edge's call lines are the callers record's call lines for the same (caller, call text).

@pytest.mark.parametrize('lang', sorted(FAMILIES))
def test_walk_edge_call_lines_equal_the_callers_record(tmp_path, lang):
    root, target, _ = _family(tmp_path, lang)
    callers = _records(_cli_json('calls', str(root), '--callers', target))
    for record in callers:
        edge = next(e for e in _edges(_cli_json('calls', str(root), '--callees', record['caller'], '--depth', '2'))
                    if e['caller'] == record['caller'] and e['call_expr'] == record['call_expr'])
        assert (edge.get('caller_def_line'), edge.get('call_lines'), edge.get('reference_lines')) == \
            (record['caller_def_line'], record['call_lines'], record.get('reference_lines')), record


@pytest.mark.parametrize('lang', sorted(FAMILIES))
def test_every_callers_record_has_a_walk_edge(tmp_path, lang):
    """Sibling: each caller of the target walks an edge with the same call text today."""
    root, target, _ = _family(tmp_path, lang)
    for record in _records(_cli_json('calls', str(root), '--callers', target)):
        assert any(e['caller'] == record['caller'] and e['call_expr'] == record['call_expr']
                   for e in _edges(_cli_json('calls', str(root), '--callees', record['caller'], '--depth', '2')))


# 5. Text rows name the call lines beside the callee; a header's line is the definition line.

def _row(text, start):
    return next(line.strip() for line in text.splitlines() if line.strip().startswith(start))


def test_depth_one_rows_name_their_call_lines(tmp_path):
    root, _, _ = _family(tmp_path, 'python')
    assert _row(_cli_text('calls', str(root), '--callees', 'caller'), '→ target') == '→ target [lines 7, 9]'
    assert _row(_cli_text('calls', str(root), '--callees', 'method'), '→ target') == '→ target [line 14]'


def test_depth_one_jsx_rows_name_call_and_render_lines(tmp_path):
    root = _write(tmp_path / 'owners', {'p.tsx': JSX_OWNERS})
    assert _row(_cli_text('calls', str(root), '--callees', 'Two'), '→ Btn') == \
        '→ Btn (includes JSX reference) [call lines 8, 11, JSX line 10]'
    assert _row(_cli_text('calls', str(root), '--callees', 'One'), '→ Btn') == '→ Btn (JSX reference) [JSX line 6]'


def test_module_header_names_line_one(tmp_path):
    root, _, _ = _family(tmp_path, 'python')
    text = _cli_text('calls', str(root), '--callees', '<module>')
    assert re.search(r'm\.py:1  <module>$', next(line for line in text.splitlines() if line.endswith('  <module>'))), text


def test_function_header_keeps_its_definition_line(tmp_path):
    """Sibling: a function's header already names its definition line."""
    root, _, _ = _family(tmp_path, 'python')
    text = _cli_text('calls', str(root), '--callees', 'caller')
    assert re.search(r'm\.py:5  caller$', next(line for line in text.splitlines() if line.endswith('  caller'))), text


def test_walk_rows_name_call_lines_and_the_callee_definition(tmp_path):
    root, _, _ = _family(tmp_path, 'python')
    _write(root, DEPTH_TWO)
    text = _cli_text('calls', str(root), '--callees', 'outer', '--depth', '2')
    assert re.search(r'^→ caller \[lines 6, 7\]  \S*m\.py:5$', _row(text, '→ caller')), text
    assert re.search(r'^→ target \[lines 7, 9\]  \S*m\.py:1$', _row(text, '→ target')), text
    module = _cli_text('calls', str(root), '--callees', '<module>', '--depth', '2')
    assert re.search(r'^<module>  \S*m\.py:1$', _row(module, '<module>')), module
    assert re.search(r'^→ target \[lines 17, 18\]  \S*m\.py:1$', _row(module, '→ target')), module


def test_walk_root_row_keeps_its_definition_line(tmp_path):
    """Sibling: a function root's row already names its definition line."""
    root, _, _ = _family(tmp_path, 'python')
    _write(root, DEPTH_TWO)
    text = _cli_text('calls', str(root), '--callees', 'outer', '--depth', '2')
    assert re.search(r'^outer  \S*n\.py:4$', _row(text, 'outer')), text


# 6. The text walk keys a definition by (file, line, name): two definitions on one line no longer
# recurse (K-B1), and `<module>` at line 1 beside a function on line 1 prints each once.

ONE_LINE = {'one.js': 'function a() { b(); } function b() { c(); } function c() { return 1; }\n'}


def test_walk_text_with_two_definitions_on_one_line(tmp_path):
    root = _write(tmp_path / 'oneline', ONE_LINE)
    result = _run_reveal_direct('calls', str(root), '--callees', 'a', '--depth', '3')
    assert result.returncode == 0, result.stderr
    rows = [line.strip() for line in result.stdout.splitlines() if line.strip().startswith('→')]
    assert [re.sub(r'  \S*one\.js:', '  one.js:', row) for row in rows] == \
        ['→ b [line 1]  one.js:1', '→ c [line 1]  one.js:1']


def test_walk_json_with_two_definitions_on_one_line(tmp_path):
    """Sibling: the same walk in JSON answers today."""
    root = _write(tmp_path / 'oneline', ONE_LINE)
    answer = _cli_json('calls', str(root), '--callees', 'a', '--depth', '3')
    assert [(e['caller'], e['callee']) for e in _edges(answer)] == [('a', 'b'), ('b', 'c')]


def test_walk_text_with_module_and_a_function_on_line_one(tmp_path):
    root = _write(tmp_path / 'owners', {'p.tsx': JSX_OWNERS})
    result = _run_reveal_direct('calls', str(root), '--callees', '<module>', '--depth', '2')
    assert result.returncode == 0, result.stderr
    rows = [line.strip() for line in result.stdout.splitlines() if line.strip().startswith('→')]
    assert re.search(r'^<module>  \S*p\.tsx:1$', _row(result.stdout, '<module>')), result.stdout
    assert len(rows) == 1 and re.search(
        r'^→ Btn \(includes JSX reference\) \[call line 15, JSX line 14\]  \S*p\.tsx:1$', rows[0]), result.stdout


# 7. Builtins: hidden from `calls` and from `call_lines_by_callee` alike; --builtins keeps both.

BUILTINS = {'b.py': ('def caller():\n'    # 1
                     '    print(1)\n'     # 2
                     '    x = len([])\n'  # 3
                     '    helper()\n'     # 4
                     '\n'                 # 5
                     '\n'                 # 6
                     'def helper():\n'    # 7
                     '    return 1\n')}   # 8


def test_builtins_are_hidden_from_call_lines_too(tmp_path):
    root = _write(tmp_path / 'b', BUILTINS)
    hidden = _cli_json('calls', str(root), '--callees', 'caller')['matches'][0]
    shown = _cli_json('calls', str(root), '--callees', 'caller', '--builtins')['matches'][0]
    assert hidden.get('call_lines_by_callee') == {'helper': [4]}
    assert shown.get('call_lines_by_callee') == {'print': [2], 'len': [3], 'helper': [4]}


def test_builtins_hidden_count_is_unchanged(tmp_path):
    """Sibling: the builtins switch already filtered `calls`."""
    root = _write(tmp_path / 'b', BUILTINS)
    answer = _cli_json('calls', str(root), '--callees', 'caller')
    assert (answer['matches'][0]['calls'], answer['_builtins_hidden']) == (['helper'], 2)


# 8. An import alias and the original name are two call texts: one key and one edge each.

def test_alias_and_original_have_their_own_call_lines(tmp_path):
    root = _write(tmp_path / 'proj', ALIASED)
    match = _matches(_cli_json('calls', str(root), '--callees', 'f'))[('n.py', 'f')]
    assert match.get('call_lines_by_callee') == {'target': [6], 't': [7]}
    edges = _edges(_cli_json('calls', str(root), '--callees', 'f', '--depth', '2'))
    assert [(e['call_expr'], e.get('call_lines'), e.get('callee_def_line')) for e in edges] == \
        [('target', [6], 1), ('t', [7], 1)]


def test_alias_and_original_are_two_calls(tmp_path):
    """Sibling: two call texts were two calls already."""
    root = _write(tmp_path / 'proj', ALIASED)
    assert _cli_json('calls', str(root), '--callees', 'f')['total_calls'] == 2


# 9. The Python API gives the CLI's answer, call lines included.

def test_api_query_gives_the_cli_callees_with_call_lines(tmp_path):
    root, _, _ = _family(tmp_path, 'python')
    api = query('calls', str(root), callees='caller', depth=2)
    cli = _cli_json('calls', str(root), '--callees', 'caller', '--depth', '2')
    assert (api['matches'], api['levels'], api['definitions']) == (cli['matches'], cli['levels'], cli['definitions'])
    assert api['matches'][0].get('call_lines_by_callee') == {'target': [7, 9]}
    assert [e.get('call_lines') for e in _edges(api)] == [[7, 9]]


def test_api_query_and_cli_agree_on_the_callees(tmp_path):
    """Sibling: the API already answered with the CLI's edges."""
    root, _, _ = _family(tmp_path, 'python')
    api = query('calls', str(root), callees='caller', depth=2)
    cli = _cli_json('calls', str(root), '--callees', 'caller', '--depth', '2')
    assert [(e['caller'], e['callee']) for e in _edges(api)] == [(e['caller'], e['callee']) for e in _edges(cli)] == \
        [('caller', 'target')]


# 10. trace (deprecated, works until 1.0) reads the same definitions: `<module>`'s frame is line 1.

def _frames(root, name):
    result = _run_reveal_direct(f'trace://{root}?from={name}', '--format', 'json')
    assert result.returncode == 0, result.stderr
    return [(frame['name'], frame['line']) for frame in json.loads(result.stdout)['frames']]


def test_trace_module_frame_is_line_one(tmp_path):
    root, _, _ = _family(tmp_path, 'python')
    assert _frames(root, '<module>')[0] == ('<module>', 1)


def test_trace_function_frames_keep_their_definition_lines(tmp_path):
    """Sibling: function frames already name their definition lines."""
    root, _, _ = _family(tmp_path, 'python')
    assert _frames(root, 'caller') == [('caller', 5), ('target', 1)]
