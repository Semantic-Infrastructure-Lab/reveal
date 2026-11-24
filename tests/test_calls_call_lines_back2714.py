"""BACK-2714: every ``calls --callers`` record names its call sites.

A callers record said ``line``: a function caller's definition line, but a ``<module>`` caller's first
call site, so one field had two meanings (D21) and agents read a definition line as the call line
(celery ``build_tracer``: 880, 689, 43, 748 printed for calls on 949, 694, 90, 752). Each record now names
the definition line ``caller_def_line`` (what the calls gate matches on, BACK-730 note 2; ``<module>``'s
scope starts at line 1) and carries ``call_lines``, the sorted lines of that caller's calls to the name.
The text row leads with the first call line, further lines after it. The lines come from the one call
walk (``TreeSitterAnalyzer._complexity_depth_and_calls``) and live in an internal side table of the
structure cache entry, never in path-read JSON.
"""
import json
import os
import re

import pytest

from conftest import _run_reveal_direct
from reveal import treesitter as ts_mod
from reveal.adapters.ast import analysis
from reveal.adapters.calls.index import build_callers_index
from reveal.api import query

pytestmark = pytest.mark.component

# Each family: (file name, source, target, {caller: (caller_def_line, call_lines)}).
FAMILIES = {
    'python': ('m.py', (
        'def target(x=None):\n'        # 1
        '    return x\n'               # 2
        '\n'                           # 3
        '\n'                           # 4
        'def caller():\n'              # 5
        '    a = 1\n'                  # 6
        '    target()\n'               # 7
        '    b = 2\n'                  # 8
        '    target(a)\n'              # 9
        '\n'                           # 10
        '\n'                           # 11
        'class Box:\n'                 # 12
        '    def method(self):\n'      # 13
        '        return target()\n'    # 14
        '\n'                           # 15
        '\n'                           # 16
        'target()\n'                   # 17
        'target()\n'),                 # 18
        'target', {'caller': (5, [7, 9]), 'method': (13, [14]), '<module>': (1, [17, 18])}),
    'typescript': ('m.ts', (
        'export function target(x?: number): number {\n'   # 1
        '  return x ?? 0;\n'                                # 2
        '}\n'                                               # 3
        '\n'                                                # 4
        'export function caller(): void {\n'                # 5
        '  const a = 1;\n'                                  # 6
        '  target();\n'                                     # 7
        '  const b = 2;\n'                                  # 8
        '  target(a);\n'                                    # 9
        '}\n'                                               # 10
        '\n'                                                # 11
        'export const arrow = (): number => {\n'            # 12
        '  return target(\n'                                # 13
        '    1,\n'                                          # 14
        '  );\n'                                            # 15
        '};\n'                                              # 16
        '\n'                                                # 17
        'class Box {\n'                                     # 18
        '  method(): number {\n'                            # 19
        '    return target();\n'                            # 20
        '  }\n'                                             # 21
        '  field = target();\n'                             # 22
        '}\n'                                               # 23
        '\n'                                                # 24
        'target();\n'                                       # 25
        'target();\n'),                                     # 26
        'target', {'caller': (5, [7, 9]), 'arrow': (12, [13]), 'method': (19, [20]), 'field': (22, [22]),
                   '<module>': (1, [25, 26])}),
    'go': ('m.go', (
        'package m\n'                      # 1
        '\n'                               # 2
        'func target(x int) int {\n'       # 3
        '\treturn x\n'                     # 4
        '}\n'                              # 5
        '\n'                               # 6
        'func caller() {\n'                # 7
        '\ta := 1\n'                       # 8
        '\ttarget(a)\n'                    # 9
        '\tb := 2\n'                       # 10
        '\ttarget(b)\n'                    # 11
        '}\n'                              # 12
        '\n'                               # 13
        'type Box struct{}\n'              # 14
        '\n'                               # 15
        'func (b Box) method() int {\n'    # 16
        '\treturn target(3)\n'             # 17
        '}\n'),                            # 18
        'target', {'caller': (7, [9, 11]), 'method': (16, [17])}),
    'rust': ('m.rs', (
        'fn target(x: i32) -> i32 {\n'          # 1
        '    x\n'                               # 2
        '}\n'                                   # 3
        '\n'                                    # 4
        'fn caller() {\n'                       # 5
        '    let a = 1;\n'                      # 6
        '    target(a);\n'                      # 7
        '    let b = 2;\n'                      # 8
        '    println!("{}", target(b));\n'      # 9: a call inside a macro's token tree
        '}\n'                                   # 10
        '\n'                                    # 11
        'struct Box;\n'                         # 12
        '\n'                                    # 13
        'impl Box {\n'                          # 14
        '    fn method(&self) -> i32 {\n'       # 15
        '        target(3)\n'                   # 16
        '    }\n'                               # 17
        '}\n'),                                 # 18
        'target', {'caller': (5, [7, 9]), 'method': (15, [16])}),
    'java': ('M.java', (
        'class M {\n'                            # 1
        '    static int target(int x) {\n'       # 2
        '        return x;\n'                    # 3
        '    }\n'                                # 4
        '\n'                                     # 5
        '    static void caller() {\n'           # 6
        '        int a = 1;\n'                   # 7
        '        target(a);\n'                   # 8
        '        int b = 2;\n'                   # 9
        '        target(b);\n'                   # 10
        '    }\n'                                # 11
        '\n'                                     # 12
        '    int method() {\n'                   # 13
        '        return target(3);\n'            # 14
        '    }\n'                                # 15
        '}\n'),                                  # 16
        'target', {'caller': (6, [8, 10]), 'method': (13, [14])}),
    'ruby': ('m.rb', (
        'def target(x = nil)\n'    # 1
        '  x\n'                    # 2
        'end\n'                    # 3
        '\n'                       # 4
        'def caller\n'             # 5
        '  a = 1\n'                # 6
        '  target(a)\n'            # 7
        '  b = 2\n'                # 8
        '  target\n'               # 9: a bare, argument-less call
        'end\n'                    # 10
        '\n'                       # 11
        'class Box\n'              # 12
        '  def method\n'           # 13
        '    target(3)\n'          # 14
        '  end\n'                  # 15
        'end\n'                    # 16
        '\n'                       # 17
        'target(4)\n'              # 18
        'target(5)\n'),            # 19
        'target', {'caller': (5, [7, 9]), 'method': (13, [14]), '<module>': (1, [18, 19])}),
    'php': ('m.php', (
        '<?php\n'                              # 1
        'function target($x = null) {\n'       # 2
        '    return $x;\n'                     # 3
        '}\n'                                  # 4
        '\n'                                   # 5
        'function caller() {\n'                # 6
        '    $a = 1;\n'                        # 7
        '    target($a);\n'                    # 8
        '    $b = 2;\n'                        # 9
        '    target($b);\n'                    # 10
        '}\n'                                  # 11
        '\n'                                   # 12
        'class Box {\n'                        # 13
        '    public function method() {\n'     # 14
        '        return target(3);\n'          # 15
        '    }\n'                              # 16
        '}\n'                                  # 17
        '\n'                                   # 18
        'target(4);\n'                         # 19
        'target(5);\n'),                       # 20
        'target', {'caller': (6, [8, 10]), 'method': (14, [15]), '<module>': (1, [19, 20])}),
    'c': ('m.c', (
        'int target(int x) {\n'    # 1
        '    return x;\n'          # 2
        '}\n'                      # 3
        '\n'                       # 4
        'void caller(void) {\n'    # 5
        '    int a = 1;\n'         # 6
        '    target(a);\n'         # 7
        '    int b = 2;\n'         # 8
        '    target(b);\n'         # 9
        '}\n'                      # 10
        '\n'                       # 11
        'int other(void) {\n'      # 12
        '    return target(3);\n'  # 13
        '}\n'),                    # 14
        'target', {'caller': (5, [7, 9]), 'other': (12, [13])}),
    'dart': ('m.dart', (
        'int target([int x = 0]) {\n'     # 1
        '  return x;\n'                   # 2
        '}\n'                             # 3
        '\n'                              # 4
        'int paramDefault() => 1;\n'      # 5
        '\n'                              # 6
        'class Box {\n'                   # 7
        '  final int v;\n'                # 8
        '  Box(int a)\n'                  # 9
        '      : v = target(a) {\n'       # 10: a constructor initializer list
        '    target(2);\n'                # 11
        '  }\n'                           # 12
        '\n'                              # 13
        '  void method({int x = 0}) {\n'  # 14
        '    target(x);\n'                # 15
        '    target(x);\n'                # 16
        '  }\n'                           # 17
        '}\n'),                           # 18
        'target', {'Box': (9, [10, 11]), 'method': (14, [15, 16])}),
    'jsx': ('m.jsx', (
        'export function Target(props) {\n'   # 1
        '  return null;\n'                    # 2
        '}\n'                                 # 3
        '\n'                                  # 4
        'export function Owner() {\n'         # 5
        '  const v = Target({});\n'           # 6
        '  return (\n'                        # 7
        '    <div>\n'                         # 8
        '      <Target a={1} />\n'            # 9
        '      {Target({})}\n'                # 10
        '    </div>\n'                        # 11
        '  );\n'                              # 12
        '}\n'                                 # 13
        '\n'                                  # 14
        'export function OnlyRenders() {\n'   # 15
        '  return <Target />;\n'              # 16: rendered, never called
        '}\n'                                 # 17
        '\n'                                  # 18
        'Target({});\n'),                     # 19
        'Target', {'Owner': (5, [6, 10]), 'OnlyRenders': (15, []), '<module>': (1, [19])}),
}


def _write(root, files):
    root.mkdir(parents=True, exist_ok=True)
    for name, source in files.items():
        (root / name).write_text(source, encoding='utf-8')
    return root


def _family(tmp_path, lang):
    name, source, target, expected = FAMILIES[lang]
    return _write(tmp_path / lang, {name: source}), target, expected


def _cli_json(*args):
    result = _run_reveal_direct(*args, '--format', 'json')
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _cli_text(*args):
    result = _run_reveal_direct(*args)
    assert result.returncode == 0, result.stderr
    return result.stdout


def _records(answer):
    return [rec for level in answer['levels'] for rec in level['callers']]


def _lines(records):
    """caller -> (caller_def_line, call_lines, whether the record still says `line`)."""
    return {rec['caller']: (rec.get('caller_def_line'), rec.get('call_lines'), 'line' in rec) for rec in records}


def _base(path):
    return path.replace('\\', '/').rsplit('/', 1)[-1]


# 1. Every family through `reveal calls DIR --callers NAME --format json`.

@pytest.mark.parametrize('lang', sorted(FAMILIES))
def test_each_record_names_its_definition_line_and_its_call_lines(tmp_path, lang):
    root, target, expected = _family(tmp_path, lang)
    answer = _cli_json('calls', str(root), '--callers', target)
    assert _lines(_records(answer)) == {caller: (*want, False) for caller, want in expected.items()}


@pytest.mark.parametrize('lang', sorted(FAMILIES))
def test_the_callers_set_and_count_are_unchanged(tmp_path, lang):
    """Sibling: which callers answer, and how many, does not move."""
    root, target, expected = _family(tmp_path, lang)
    answer = _cli_json('calls', str(root), '--callers', target)
    assert sorted((_base(rec['file']), rec['caller']) for rec in _records(answer)) == \
        sorted((FAMILIES[lang][0], caller) for caller in expected)
    assert answer['total_callers'] == len(expected)


# 3. `<module>` and class-field scopes.

def test_module_caller_def_line_is_one_and_its_call_lines_are_the_calls(tmp_path):
    root, target, _ = _family(tmp_path, 'python')
    module = next(r for r in _records(_cli_json('calls', str(root), '--callers', target)) if r['caller'] == '<module>')
    assert (module.get('caller_def_line'), module['call_lines'], 'line' in module) == (1, [17, 18], False)


def test_class_field_call_lines_keep_their_value(tmp_path):
    """Sibling: a class field already named its call lines."""
    root, target, _ = _family(tmp_path, 'typescript')
    field = next(r for r in _records(_cli_json('calls', str(root), '--callers', target)) if r['caller'] == 'field')
    assert field['call_lines'] == [22] and field['caller_kind'] == 'class_field'


# 4. The text row leads with the first call line.

def _row(text, caller):
    return next(line.strip() for line in text.splitlines() if f'  {caller}  (' in line)


def test_text_row_leads_with_the_first_call_line(tmp_path):
    root, target, _ = _family(tmp_path, 'python')
    text = _cli_text('calls', str(root), '--callers', target)
    assert re.search(r'm\.py:7  caller  \(calls target\) \[lines 7, 9\]$', _row(text, 'caller')), text
    assert re.search(r'm\.py:14  method  \(calls target\)$', _row(text, 'method')), text


def test_text_row_of_a_module_is_unchanged(tmp_path):
    """Sibling: a `<module>` row already led with its first call."""
    root, target, _ = _family(tmp_path, 'python')
    text = _cli_text('calls', str(root), '--callers', target)
    assert re.search(r'm\.py:17  <module>  \(calls target\) \[lines 17, 18\]$', _row(text, '<module>')), text


# 5. Depth 2: every level's records carry their call lines; later hops still look up by definition.

DEPTH_TWO = {
    'n.py': ('from m import caller\n'   # 1
             '\n'                       # 2
             '\n'                       # 3
             'def outer():\n'           # 4
             '    x = 0\n'              # 5
             '    caller()\n'           # 6
             '    caller()\n'           # 7
             '\n'                       # 8
             '\n'                       # 9
             'def outer2():\n'          # 10
             '    return caller()\n'),  # 11
}


def _depth_two(tmp_path):
    root, target, _ = _family(tmp_path, 'python')
    _write(root, DEPTH_TWO)
    answer = _cli_json('calls', str(root), '--callers', target, '--depth', '2')
    return {level['level']: {rec['caller']: rec for rec in level['callers']} for level in answer['levels']}


def test_level_two_records_carry_their_call_lines(tmp_path):
    levels = _depth_two(tmp_path)
    assert _lines(levels[1].values())['caller'] == (5, [7, 9], False)
    assert _lines(levels[2].values()) == {'outer': (4, [6, 7], False), 'outer2': (10, [11], False)}


def test_level_two_still_resolves_the_caller_by_its_definition(tmp_path):
    """Sibling: the depth-2 identity is the reached caller's definition site (BACK-730)."""
    outer = _depth_two(tmp_path)[2]['outer']
    assert outer['target_resolution'] == 'resolved'
    assert outer['target_line'] == 5


# 6. One caller reached through an import alias and the original name: one record, both lines.

ALIASED = {
    'm.py': 'def target():\n    return 1\n',
    'n.py': ('from m import target\n'       # 1
             'from m import target as t\n'  # 2
             '\n'                           # 3
             '\n'                           # 4
             'def f():\n'                   # 5
             '    target()\n'               # 6
             '    t()\n'),                  # 7
}


def test_alias_and_original_calls_merge_into_one_record(tmp_path):
    root = _write(tmp_path / 'proj', ALIASED)
    records = _records(_cli_json('calls', str(root), '--callers', 'target'))
    assert [(r['caller'], r.get('call_lines')) for r in records] == [('f', [6, 7])]


def test_ranking_merges_the_alias_and_original_lines_too(tmp_path):
    root = _write(tmp_path / 'proj', ALIASED)
    entry = next(e for e in _cli_json('calls', str(root), '--sort=-callers')['entries'] if e['name'] == 'target')
    assert (entry['caller_count'], [(r['caller'], r['call_lines']) for r in entry['callers']]) == (1, [('f', [6, 7])])


def test_alias_and_original_are_one_caller(tmp_path):
    """Sibling: the (file, caller) dedupe already counted one caller."""
    root = _write(tmp_path / 'proj', ALIASED)
    assert _cli_json('calls', str(root), '--callers', 'target')['total_callers'] == 1


# 7. Calls outside the body proper: a Python decorator argument, a Rust macro, a bare Ruby call.

DECORATED = (
    'def target(x=None):\n'    # 1
    '    return x\n'           # 2
    '\n'                       # 3
    '\n'                       # 4
    'def deco(f):\n'           # 5
    '    return f\n'           # 6
    '\n'                       # 7
    '\n'                       # 8
    '@deco(target())\n'        # 9
    'def decorated():\n'       # 10
    '    target()\n'           # 11
)


def test_decorator_argument_calls_carry_their_line(tmp_path):
    # Asserts the decorated function's lines only; whether <module> also claims line 9 is BACK-2782.
    root = _write(tmp_path / 'proj', {'d.py': DECORATED})
    decorated = next(r for r in _records(_cli_json('calls', str(root), '--callers', 'target'))
                     if r['caller'] == 'decorated')
    assert (decorated.get('caller_def_line'), decorated.get('call_lines')) == (9, [9, 11])


@pytest.mark.parametrize('lang', ['rust', 'ruby'])
def test_macro_and_bare_calls_carry_their_line(tmp_path, lang):
    root, target, _ = _family(tmp_path, lang)
    caller = next(r for r in _records(_cli_json('calls', str(root), '--callers', target)) if r['caller'] == 'caller')
    assert caller.get('call_lines') == [7, 9]


def test_calls_outside_the_body_are_still_found(tmp_path):
    """Sibling: the walk already named these callees."""
    root = _write(tmp_path / 'proj', {'d.py': DECORATED})
    _family(tmp_path / 'proj', 'rust')
    _family(tmp_path / 'proj', 'ruby')
    callees = {(_base(m['file']), m['function']): m['calls'] for m in
               _cli_json('calls', str(root), '--callees', 'decorated')['matches']}
    assert 'target' in callees[('d.py', 'decorated')]
    assert {('d.py', 'decorated'), ('m.rs', 'caller'), ('m.rb', 'caller')} <= \
        {(_base(r['file']), r['caller']) for r in _records(_cli_json('calls', str(root), '--callers', 'target'))}


# 8. The --sort=-callers ranking's caller records follow the same rule.

def test_ranking_callers_name_their_lines(tmp_path):
    root, _, expected = _family(tmp_path, 'python')
    entry = next(e for e in _cli_json('calls', str(root), '--sort=-callers')['entries'] if e['name'] == 'target')
    assert _lines(entry['callers']) == {caller: (*want, False) for caller, want in expected.items()}
    text = _cli_text('calls', str(root), '--sort=-callers')
    row = next(line.strip() for line in text.splitlines() if line.rstrip().endswith('  caller') or '  caller [' in line)
    assert re.search(r'm\.py:7  caller \[lines 7, 9\]$', row), text


def test_ranking_count_is_unchanged(tmp_path):
    """Sibling: the ranked count is the callers query's count."""
    root, _, expected = _family(tmp_path, 'python')
    entry = next(e for e in _cli_json('calls', str(root), '--sort=-callers')['entries'] if e['name'] == 'target')
    assert entry['caller_count'] == len(expected)


# 9. The Python API gives the CLI's records.

def test_api_query_gives_the_cli_records_with_call_lines(tmp_path):
    root, target, _ = _family(tmp_path, 'go')
    api = query('calls', str(root), callers=target)
    cli = _cli_json('calls', str(root), '--callers', target)
    assert _records(api) == _records(cli)
    assert _lines(_records(api))['caller'] == (7, [9, 11], False)


def test_api_query_and_cli_agree_on_the_callers(tmp_path):
    """Sibling: the API already answered with the CLI's callers."""
    root, target, _ = _family(tmp_path, 'go')
    api = query('calls', str(root), callers=target)
    cli = _cli_json('calls', str(root), '--callers', target)
    assert [r['caller'] for r in _records(api)] == [r['caller'] for r in _records(cli)] == ['caller', 'method']


# 12. A JSX owner's call lines come from the one call walk too (C4, ruling S5). The walk credits
# `Two` with the call inside its closure `cb` (line 8, the documented closure bleed that already puts
# `Btn` in `Two`'s calls); the second owner of JSX call lines (`jsx_owner_call_sites`) credited that
# call to `cb` alone, so `Two` named `Btn` as a callee but only line 11 as its call.

JSX_OWNERS = (
    'export function Btn() { return null; }\n'   # 1
    'export function App() {\n'                  # 2
    '  Btn();\n'                                 # 3
    '  return <div><Btn/><Btn/></div>;\n'        # 4
    '}\n'                                        # 5
    'export function One() { return <Btn/>; }\n'  # 6: rendered, never called
    'export function Two() {\n'                  # 7
    '  const cb = () => Btn();\n'                # 8: a call in Two's closure
    '  return <div>\n'                           # 9
    '    <Btn/>\n'                               # 10
    '    {Btn()}\n'                              # 11
    '  </div>;\n'                                # 12
    '}\n'                                        # 13
    '<Btn/>;\n'                                  # 14
    'Btn();\n')                                  # 15


def _jsx_owners(tmp_path):
    root = _write(tmp_path / 'owners', {'p.tsx': JSX_OWNERS})
    return root, {r['caller']: r for r in _records(_cli_json('calls', str(root), '--callers', 'Btn'))}


def test_a_jsx_owner_names_every_call_the_walk_credits_it_with(tmp_path):
    _, records = _jsx_owners(tmp_path)
    two = records['Two']
    assert (two['caller_def_line'], two['call_lines'], two['reference_lines'], two['relationship']) == \
        (7, [8, 11], [10], 'call_and_jsx_reference')


def test_a_jsx_owner_text_row_leads_with_its_first_walk_call(tmp_path):
    root, _ = _jsx_owners(tmp_path)
    text = _cli_text('calls', str(root), '--callers', 'Btn')
    assert re.search(r'p\.tsx:8  Two  \(calls and JSX reference to Btn\) \[call lines 8, 11, JSX line 10\]$',
                     _row(text, 'Two')), text


def test_jsx_only_owners_and_plain_callers_keep_their_lines(tmp_path):
    """Sibling: a name only rendered keeps its JSX lines, a caller with no JSX and an owner with no
    closure call keep their call lines, and the callers set does not move."""
    root, records = _jsx_owners(tmp_path)
    assert {name: (r['caller_def_line'], r['call_lines'], r.get('reference_lines'), r.get('relationship'))
            for name, r in records.items() if name != 'Two'} == {
        'App': (2, [3], [4], 'call_and_jsx_reference'),
        'One': (6, [], [6], 'jsx_reference'),
        'cb': (8, [8], None, None),
        '<module>': (1, [15], [14], 'call_and_jsx_reference')}
    assert sorted(records) == ['<module>', 'App', 'One', 'Two', 'cb']
    text = _cli_text('calls', str(root), '--callers', 'Btn')
    assert re.search(r'p\.tsx:6  One  \(JSX reference to Btn\) \[JSX line 6\]$', _row(text, 'One')), text
    assert re.search(r'p\.tsx:8  cb  \(calls Btn\)$', _row(text, 'cb')), text


# Every call source's record has call lines, inside its own span, in every language the matrix covers.

CONFORMANCE = os.path.join(os.path.dirname(__file__), 'fixtures', 'conformance')
CONFORMANCE_LANGS = sorted(d for d in os.listdir(CONFORMANCE) if os.path.isdir(os.path.join(CONFORMANCE, d))
                           and any(f.startswith('sample.') for f in os.listdir(os.path.join(CONFORMANCE, d))))


@pytest.mark.parametrize('lang', CONFORMANCE_LANGS)
def test_every_called_record_has_call_lines_inside_its_caller(lang):
    index = build_callers_index(os.path.join(CONFORMANCE, lang))
    spans = {(_base(s['file']), e['name'], e['line']): e.get('line_count', 1)
             for s in analysis.collect_structures(os.path.join(CONFORMANCE, lang)) for e in s['elements']}
    checked = 0
    for records in index.values():
        for rec in records:
            if rec.get('relationship') == 'jsx_reference':
                continue
            lines = rec.get('call_lines')
            assert lines, f'{lang}: {rec["caller"]} calls {rec["call_expr"]} with no call line: {rec}'
            assert lines == sorted(set(lines)), rec
            if rec.get('caller_kind') is None:
                count = spans[(_base(rec['file']), rec['caller'], rec['caller_def_line'])]
                assert all(rec['caller_def_line'] <= n < rec['caller_def_line'] + count for n in lines), rec
            checked += 1
    assert checked, f'{lang}: the sample must call something'


def test_conformance_samples_have_callers():
    """Sibling: every matrix language indexes callers today."""
    for lang in CONFORMANCE_LANGS:
        assert any(build_callers_index(os.path.join(CONFORMANCE, lang)).values()), lang


# 10. Cache: a stored full structure entry without the call-line table is rebuilt.

@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    ts_mod._get_parse_cache().clear()
    yield
    ts_mod._get_parse_cache().clear()


@pytest.fixture
def walks(monkeypatch):
    """Invocations of the one call walk: a structure cache hit walks nothing."""
    counted = []
    real = ts_mod.TreeSitterAnalyzer._complexity_depth_and_calls

    def counting(self, *args, **kwargs):
        counted.append(os.path.basename(str(self.path)))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(ts_mod.TreeSitterAnalyzer, '_complexity_depth_and_calls', counting)
    return counted


def _scan(root):
    ts_mod._get_parse_cache().clear()
    return {os.path.basename(s['file']): s for s in analysis.collect_structures(str(root))}


def _stored_entry(path):
    from reveal.core import disk_cache
    from reveal.registry import get_analyzer
    analyzer = get_analyzer(str(path))(str(path))
    key = analyzer._structure_fingerprint()
    return key, disk_cache.get(ts_mod._STRUCTURE_CACHE_NAMESPACE, key)


@pytest.mark.disk_cache
def test_an_entry_stored_without_call_lines_is_rebuilt(tmp_path, isolated_cache, walks):
    from reveal.core import disk_cache
    root, target, _ = _family(tmp_path, 'python')
    _scan(root)
    key, entry = _stored_entry(root / 'm.py')
    assert isinstance(entry, dict), 'the full scan must store a structure entry'
    disk_cache.put(ts_mod._STRUCTURE_CACHE_NAMESPACE, key,
                   {k: v for k, v in entry.items() if k != '_function_call_lines'})
    walks.clear()
    _scan(root)
    assert walks, 'an entry stored before call lines were recorded must be rebuilt, not served'
    caller = next(r for r in build_callers_index(str(root))[target] if r['caller'] == 'caller')
    assert caller.get('call_lines') == [7, 9]


@pytest.mark.disk_cache
def test_a_complete_entry_is_a_hit(tmp_path, isolated_cache, walks):
    """Sibling: an unchanged tree is served from the cache and walks nothing."""
    root, _, _ = _family(tmp_path, 'python')
    first = _scan(root)
    walks.clear()
    assert _scan(root) == first
    assert walks == []


# 11. Guard: path-read JSON and the public structure never carry the walk's lines.

def test_path_read_json_and_structure_carry_no_call_lines(tmp_path):
    root, _, _ = _family(tmp_path, 'python')
    answer = _cli_json(str(root / 'm.py'))
    assert 'call_lines' not in json.dumps(answer)
    from reveal.registry import get_analyzer
    structure = get_analyzer(str(root / 'm.py'))(str(root / 'm.py')).get_structure()
    assert '_function_call_lines' not in structure
    assert not any('call_lines' in item for items in structure.values() if isinstance(items, list)
                   for item in items if isinstance(item, dict))
