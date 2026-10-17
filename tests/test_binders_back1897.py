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


def test_python_builtins_are_classified_separately():
    scope, text, end = parsed('python', '''\
def target(p):
    print(str(p))
    return open(p), ValueError(p)
''')
    result = collect_boundary(scope, 1, end, text, 'python')
    assert result['inputs'] == [{'var': 'p', 'first_read_line': 1, 'first_write_line': None}]
    assert result.get('builtins') == [
        {'var': 'print', 'first_read_line': 2, 'first_write_line': None, 'classification': 'builtin'},
        {'var': 'str', 'first_read_line': 2, 'first_write_line': None, 'classification': 'builtin'},
        {'var': 'ValueError', 'first_read_line': 3, 'first_write_line': None, 'classification': 'builtin'},
        {'var': 'open', 'first_read_line': 3, 'first_write_line': None, 'classification': 'builtin'},
    ]


@pytest.mark.parametrize('prefix,signature', [
    ('', 'open'),
    ('open = custom\n', ''),
    ('def open(p):\n    return p\n', ''),
    ('from custom import open\n', ''),
])
def test_explicit_builtin_shadows_remain_inputs(prefix, signature):
    scope, text, end = parsed('python', prefix + f'def target({signature}):\n    return open(path)\n')
    # Select target when the negative control declares a same-named helper.
    if prefix.startswith('def'):
        root = _zero_arg(scope, 'parent')
        scope = next(n for n in iter_tree(root) if _zero_arg(n, 'kind') == 'function_definition'
                     and text(n.child_by_field_name('name')) == 'target')
        end = _zero_arg(scope, 'end_position').row + 1
    result = collect_boundary(scope, 1, end, text, 'python')
    assert {d['var'] for d in result['inputs']} == {'open', 'path'}
    assert result.get('builtins', []) == []


@pytest.mark.parametrize('language,code,expected', [
    ('javascript', 'function target() { console.log(free); }', {'console', 'free'}),
    ('java', 'class A { void target() { log.info(free); }}', {'log', 'free'}),
])
def test_runtime_globals_are_not_guessed_builtins(language, code, expected):
    scope, text, end = parsed(language, code)
    result = collect_boundary(scope, 1, end, text, language)
    assert {d['var'] for d in result['inputs']} == expected
    assert result.get('builtins', []) == []


def test_builtin_classification_reaches_text_and_json(tmp_path):
    import json
    from conftest import _run_reveal_direct
    from reveal.adapters.ast.nav_boundary import render_boundary
    from reveal.adapters.ast.nav_exits import render_deps

    code = 'def target(p):\n    print(str(p))\n'
    scope, text, end = parsed('python', code)
    report = collect_boundary(scope, 1, end, text, 'python')
    assert render_boundary(report, 1, end) == (
        'INPUTS (undefined reads):\n  p                               first read L1\n\n'
        'BUILTINS:\n  print                           first read L2\n'
        '  str                             first read L2\n\n'
        'EFFECTS:\n  none in L1–L2')
    deps = collect_deps(scope, 1, end, text, language='python')
    assert [line.split()[0] for line in render_deps(deps, 1, end).split('\n')] == ['PARAM', 'BUILTIN', 'BUILTIN']
    path = tmp_path / 'binders.py'
    path.write_text(code, encoding='utf-8')
    for flag, kind in [('--deps', 'dep'), ('--boundary', 'input')]:
        proc = _run_reveal_direct(str(path), 'target', flag, '--format', 'json')
        assert proc.returncode == 0, proc.stderr
        result = json.loads(proc.stdout)
        assert [(item['kind'], item['var']) for item in result['findings']] == [
            (kind, 'p'), ('builtin', 'print'), ('builtin', 'str')]


def test_closure_local_writes_do_not_create_outer_mutations():
    scope, text, end = parsed('javascript', '''\
function target() {
 const f = (y) => y + free;
 consume(y, f);
}
''')
    assert collect_mutations(scope, 2, 2, text) == [
        {'var': 'f', 'last_write_line': 2, 'next_read_line': 3}]
    assert [(e['kind'], e['line']) for e in var_flow(scope, 'y', 1, end, text)] == [
        ('WRITE', 2), ('READ', 2), ('READ', 3)]


def test_comprehension_iterables_and_filters_have_lexical_owners():
    scope, text, end = parsed('python', '''\
def target():
    values = [y + z + free for y in y for z in y if z]
    consume(y, z)
''')
    assert {d['var'] for d in collect_deps(scope, 1, end, text)} == {'consume', 'free', 'y', 'z'}
    assert collect_mutations(scope, 2, 2, text) == []


def test_python_closure_default_is_evaluated_in_outer_scope():
    scope, text, end = parsed('python', '''\
def target():
    f = lambda y=seed: y + free
    consume(f)
''')
    assert {d['var'] for d in collect_deps(scope, 1, end, text)} == {'seed', 'free', 'consume'}


def test_catch_shadow_does_not_hide_outer_free_read():
    scope, text, end = parsed('javascript', '''\
function target() {
 try { work(); } catch(err) { consume(err); }
 consume(err);
}
''')
    assert {d['var'] for d in collect_deps(scope, 1, end, text)} == {'work', 'consume', 'err'}
    assert collect_mutations(scope, 2, 2, text) == []


def test_enclosing_parameter_shadows_builtin():
    scope, text, end = parsed('python', '''\
def target(open):
    f = lambda p: open(p)
    consume(f)
''')
    inner = next(n for n in iter_tree(scope) if _zero_arg(n, 'kind') == 'lambda')
    result = collect_boundary(inner, 2, 2, text, 'python')
    assert {d['var'] for d in result['inputs']} == {'open'}
    assert result.get('builtins', []) == []


@pytest.mark.parametrize('params,body,expected', [
    ('y = fallback', 'y', {'fallback'}),
    ('{y = fallback, z: a = other}, b = seed', 'y+a+b+free', {'fallback', 'other', 'seed', 'free'}),
])
def test_javascript_parameter_defaults_are_outer_reads(params, body, expected):
    scope, text, end = parsed('javascript', f'function target() {{\n const f = ({params}) => {body};\n consume(f);\n}}')
    assert {d['var'] for d in collect_deps(scope, 1, end, text)} == expected | {'consume'}


@pytest.mark.parametrize('code,expected', [
    ('def target():\n    consume(y)\n    f = lambda y: y + free\n', {'consume', 'y', 'free'}),
    ('def target():\n    f = lambda y: (lambda z: y + z + free)\n    consume(y, z, f)\n', {'consume', 'y', 'z', 'free'}),
    ('def target():\n    values = [y for y in y]\n    consume(values)\n', {'consume', 'y'}),
])
def test_nested_and_earlier_external_reads_keep_owners(code, expected):
    scope, text, end = parsed('python', code)
    assert {d['var'] for d in collect_deps(scope, 1, end, text)} == expected


@pytest.mark.parametrize('declaration', ['const', 'let'])
@pytest.mark.parametrize('operator', ['of', 'in'])
def test_js_lexical_loop_does_not_hide_outer_reads(declaration, operator):
    scope, text, end = parsed('javascript', f'''\
function target() {{
 for ({declaration} y {operator} items) {{
   const f = () => consume(y, captured);
   f();
 }}
 consume(y);
}}
''')
    assert collect_deps(scope, 1, end, text) == [
        {'var': 'items', 'first_read_line': 2, 'first_write_line': None},
        {'var': 'captured', 'first_read_line': 3, 'first_write_line': None},
        {'var': 'consume', 'first_read_line': 3, 'first_write_line': None},
        {'var': 'y', 'first_read_line': 6, 'first_write_line': None},
    ]
    assert collect_mutations(scope, 2, 5, text) == []
    assert collect_deps(scope, 1, end, text) == collect_deps(scope, 1, end, text)


@pytest.mark.parametrize('initializer', ['let y = seed', 'const y = seed'])
def test_js_c_style_loop_lexical_initializer(initializer):
    scope, text, end = parsed('javascript', f'''\
function target() {{
 for ({initializer}; y < limit; consume(y)) {{
   consume(y, captured);
 }}
 consume(y);
}}
''')
    assert {d['var'] for d in collect_deps(scope, 1, end, text)} == {'seed', 'limit', 'consume', 'captured', 'y'}
    assert collect_mutations(scope, 2, 4, text) == []


@pytest.mark.parametrize('loop', ['for (var y of items)', 'for (var y in items)',
                                 'for (var y = items; y < limit; y++)'])
def test_js_var_loop_remains_function_binding(loop):
    scope, text, end = parsed('javascript', f'''\
function target() {{
 {loop} {{ consume(y); }}
 consume(y);
}}
''')
    expected = {'items', 'consume'} | ({'limit'} if 'limit' in loop else set())
    assert {d['var'] for d in collect_deps(scope, 1, end, text)} == expected
    assert collect_mutations(scope, 2, 2, text) == [
        {'var': 'y', 'last_write_line': 2, 'next_read_line': 3}]


@pytest.mark.parametrize('prefix,signature,expected', [
    ('', 'y', {'y', 'items', 'consume'}),
    (' const y = source;\n', '', {'source', 'items', 'consume'}),
])
def test_js_loop_shadow_preserves_parameter_or_local(prefix, signature, expected):
    scope, text, end = parsed('javascript', f'''\
function target({signature}) {{
{prefix} for (const y of items) {{ consume(y); }}
 consume(y);
}}
''')
    assert {d['var'] for d in collect_deps(scope, 1, end, text)} == expected
