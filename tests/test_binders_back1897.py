"""Extraction inputs respect lexical binders (BACK-1897/BACK-1693)."""
import textwrap

import pytest

from reveal.adapters.ast.nav_boundary import collect_boundary
from reveal.adapters.ast.nav_exits import collect_deps, collect_mutations
from reveal.adapters.ast.nav_varflow import var_flow
from reveal.core import treesitter_parse as ts
from reveal.core.treesitter_compat import _zero_arg, iter_tree, tree_root, ts_parse


CLOSURES = [
    ('python', 'def target():\n    f = lambda y: y + free\n    consume(y)\n', {'free', 'consume', 'y'}),
    ('javascript', 'function target() {\n const f = (y) => y + free;\n consume(y);\n}', {'free', 'consume', 'y'}),
    ('java', 'class A { void target() {\n F f = (y) -> y + free;\n consume(y);\n}}', {'free', 'consume', 'y'}),
    ('rust', 'fn target() {\n let f = |y: i32| y + free;\n consume(y);\n}', {'free', 'consume', 'y'}),
    ('kotlin', 'fun target() {\n val f = { y: Int -> y + free }\n consume(y)\n}', {'free', 'consume', 'y'}),
    ('go', 'package p\nfunc target() {\n f := func(y int) int { return y + free }\n consume(y, f)\n}', {'free', 'consume', 'y'}),
]
CATCHES = [
    ('python', 'def target():\n    try:\n        work()\n    except Error as err:\n        consume(err, free)\n', {'work', 'Error', 'consume', 'free'}),
    ('javascript', 'function target() {\n try { work(); } catch(err) { consume(err, free); }\n}', {'work', 'consume', 'free'}),
    ('java', 'class A { void target() {\n try { work(); } catch(Exception err) { consume(err, free); }\n}}', {'work', 'consume', 'free'}),
    ('php', '<?php function target() {\n try { work(); } catch(Exception $err) { consume($err, $free); }\n}', {'$free'}),
]
LOOPS = [
    ('python', 'def target():\n    for y in items:\n        consume(y)\n', {'items', 'consume'}),
    ('javascript', 'function target() {\n for (const y of items) { consume(y); }\n}', {'items', 'consume'}),
    ('java', 'class A { void target() {\n for (Object y : items) { consume(y); }\n}}', {'items', 'consume'}),
    ('rust', 'fn target() {\n for y in items { consume(y); }\n}', {'items', 'consume'}),
    ('go', 'package p\nfunc target() {\n local := items\n for i, y := range local { consume(i,y) }\n}', {'items', 'consume'}),
]


def parsed(language, code):
    src = textwrap.dedent(code)
    data = src.encode('utf-8')
    root = tree_root(ts_parse(ts.get_parser(language), src))
    assert not _zero_arg(root, 'has_error'), src

    def text(node):
        return data[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')].decode('utf-8')

    scopes = {'function_definition', 'function_declaration', 'method_declaration', 'function_item'}
    scope = next(n for n in iter_tree(root) if _zero_arg(n, 'kind') in scopes)
    return scope, text, _zero_arg(scope, 'end_position').row + 1


@pytest.mark.parametrize('language,code,expected', CLOSURES + CATCHES + LOOPS)
def test_exact_inputs(language, code, expected):
    scope, text, end = parsed(language, code)
    deps = collect_deps(scope, 1, end, text)
    assert {d['var'] for d in deps} == expected
    assert collect_deps(scope, 1, end, text) == deps
    assert {d['var'] for d in collect_boundary(scope, 1, end, text, language)['inputs']} == expected


@pytest.mark.parametrize('language,code,expected', CLOSURES)
def test_closure_parameters_are_internal(language, code, expected):
    code = code.replace('consume(y)', 'consume(f)').replace('consume(y, f)', 'consume(f)')
    scope, text, end = parsed(language, code)
    assert {d['var'] for d in collect_deps(scope, 1, end, text)} == {'free', 'consume'}


def test_python_with_comprehension_walrus_and_annotations():
    code = '''\
def target(p: Foo):
    with factory(p) as fh:
        data = fh.read()
    values = [y + free for y in data if y]
    consume(y)
    if (w := source):
        consume(w)
'''
    scope, text, end = parsed('python', code)
    assert {d['var'] for d in collect_deps(scope, 1, end, text)} == {'p', 'factory', 'free', 'consume', 'y', 'source'}
    assert [(e['kind'], e['line']) for e in var_flow(scope, 'fh', 1, end, text)] == [('WRITE', 2), ('READ', 3)]
    assert [(e['kind'], e['line']) for e in var_flow(scope, 'w', 1, end, text)] == [('WRITE', 6), ('READ', 7)]
    assert collect_mutations(scope, 2, 3, text) == [{'var': 'data', 'last_write_line': 3, 'next_read_line': 4}]


def test_partial_closure_body_needs_parameter():
    scope, text, end = parsed('javascript', '''\
function target() {
 const f = (y) => {
   consume(y, free);
 };
 consume(f);
}
''')
    assert collect_deps(scope, 3, 3, text) == [
        {'var': 'consume', 'first_read_line': 3, 'first_write_line': None},
        {'var': 'free', 'first_read_line': 3, 'first_write_line': None},
        {'var': 'y', 'first_read_line': 3, 'first_write_line': None},
    ]
    assert collect_mutations(scope, 2, 4, text) == [{'var': 'f', 'last_write_line': 2, 'next_read_line': 5}]
