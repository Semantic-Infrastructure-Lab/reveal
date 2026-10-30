"""Selected callable exits versus source-scope inventory (BACK-2389).

Hand-written source/expected sites; grammar acceptance is not compiler validation.
"""
import json

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.conformance

EXTENSIONS = {'python': 'py', 'javascript': 'js', 'kotlin': 'kt', 'ruby': 'rb',
              'cpp': 'cpp', 'go': 'go', 'java': 'java', 'csharp': 'cs', 'rust': 'rs',
              'lua': 'lua', 'php': 'php', 'swift': 'swift', 'dart': 'dart',
              'scala': 'scala', 'gdscript': 'gd', 'zig': 'zig', 'c': 'c',
              'typescript': 'ts', 'tsx': 'tsx'}

CASES = [('python', 'def outer(a):\n def inner():\n  return 1\n f = lambda: exit(2)\n return 3\n', [5]),
 ('javascript',
  'function outer(){\n'
  ' function inner(){return 1;}\n'
  ' const a=()=>{return 2;};\n'
  ' const b=function(){return 3;};\n'
  ' class C{m(){return 4;}}\n'
  ' return 5;\n'
  '}',
  [6]),
 ('kotlin',
  'fun outer(): Int {\n'
  ' fun inner(): Int { return 1 }\n'
  ' val f = fun(): Int { return 2 }\n'
  ' run { return 3 }\n'
  ' listOf(1).forEach { return@forEach }\n'
  ' return 4\n'
  '}',
  [4, 6]),
 ('ruby',
  'def outer\n'
  ' def inner\n'
  '  return 1\n'
  ' end\n'
  ' f = -> { return 2 }\n'
  ' g = lambda { return 3 }\n'
  ' p = proc { return 4 }\n'
  ' [1].each do\n'
  '  return 5\n'
  ' end\n'
  ' return 6\n'
  'end',
  [6, 7, 9, 11]),
 ('cpp',
  'int outer(){\n auto f=[](){return 1;};\n struct C{int m(){return 2;}};\n return 3;\n}',
  [4]),
 ('go', 'package p\nfunc outer() int {\n f:=func() int{return 1};\n _=f\n return 2\n}', [5]),
 ('java',
  'class C { int outer(){\n'
  ' class D {int inner(){return 1;}}\n'
  ' java.util.function.Supplier<Integer> f=()->{return 2;};\n'
  ' return 3;\n'
  '}}',
  [4]),
 ('csharp',
  'class C { int outer(){\n'
  ' int inner(){return 1;}\n'
  ' System.Func<int> f=()=>{return 2;};\n'
  ' return 3;\n'
  '}}',
  [4]),
 ('rust',
  'fn outer()->i32 {\n fn inner()->i32{return 1;}\n let f=||{return 2;};\n return 3;\n}',
  [4]),
 ('lua',
  'function outer()\n'
  ' local function inner() return 1 end\n'
  ' local f=function() return 2 end\n'
  ' return 3\n'
  'end',
  [4]),
 ('php',
  '<?php function outer(){\n'
  ' function inner(){return 1;}\n'
  ' $f=function(){return 2;};\n'
  ' $g=fn()=>exit(3);\n'
  ' return 4;\n'
  '}',
  [5]),
 ('swift',
  'func outer() -> Int {\n'
  ' func inner() -> Int {return 1}\n'
  ' let f = { () -> Int in return 2 }\n'
  ' return 3\n'
  '}',
  [4]),
 ('dart', 'int outer(){\n int inner(){return 1;}\n var f=(){return 2;};\n return 3;\n}', [4]),
 ('scala',
  'def outer(): Int = {\n def inner(): Int = {return 1}\n val f = () => {return 2}\n return 3\n}',
  [3, 4]),
 ('gdscript', 'func outer():\n var f = func():\n  return 1\n return 2\n', [4]),
 ('zig', 'fn outer() u8 {\n const C=struct {fn inner() u8 {return 1;}};\n return 2;\n}', [3]),
 ('c', 'int outer(void){\n if(1)return 1;\n return 2;\n}', [2, 3]),
 ('typescript', 'function outer():number{\n const f=()=>{return 1;};\n return 2;\n}', [3]),
 ('tsx', 'function outer():number{\n const f=()=>{return 1;};\n return 2;\n}', [3])]

def _answer(tmp_path, language, source, flag='--returns', element='outer'):
    path = tmp_path / ('sample.' + EXTENSIONS[language])
    path.write_text(source, encoding='utf-8')
    response = _run_reveal_direct(path, element, flag, '--format', 'json')
    assert response.returncode == 0, (response.stdout, response.stderr)
    return json.loads(response.stdout)


@pytest.mark.parametrize('language,source,lines', CASES, ids=[c[0] for c in CASES])
@pytest.mark.parametrize('flag', ['--exits', '--returns', '--flowto'])
def test_named_callable_excludes_independent_nested_bodies(tmp_path, language, source, lines, flag):
    answer = _answer(tmp_path, language, source, flag)
    assert [row['line'] for row in answer['findings']] == lines


def test_nested_python_definition_evaluation_is_retained(tmp_path):
    source = ('def outer():\n @exit(1)\n def inner(a=exit(2)):\n  return 3\n'
              ' f=lambda a=exit(4): exit(5)\n class C:\n  raise ValueError()\n'
              '  def m(self):\n   return 6\n return 7\n')
    answer = _answer(tmp_path, 'python', source)
    assert [(r['line'], r['text']) for r in answer['findings']] == [
        (2, 'exit(1)'), (3, 'exit(2)'), (5, 'exit(4)'),
        (7, 'raise ValueError()'), (10, 'return 7'),
    ]


@pytest.mark.parametrize('flag', ['--exits', '--returns'])
def test_literal_source_region_keeps_multiple_callable_inventory(tmp_path, flag):
    source = 'def outer(a):\n def inner():\n  return 1\n if a:\n  return 2\n return 3\n'
    answer = _answer(tmp_path, 'python', source, flag, ':1-6')
    assert [r['line'] for r in answer['findings']] == [3, 5, 6]


def test_single_line_region_preserves_its_narrow_selection(tmp_path):
    source = 'def outer(a):\n def inner():\n  return 1\n if a:\n  return 2\n return 3\n'
    answer = _answer(tmp_path, 'python', source, element=':6')
    assert [r['line'] for r in answer['findings']] == [6]


def test_named_class_is_source_inventory_not_one_callable(tmp_path):
    source = 'class C:\n def first(self):\n  return 1\n def second(self):\n  return 2\n'
    answer = _answer(tmp_path, 'python', source, element='C')
    assert [r['line'] for r in answer['findings']] == [3, 5]


def test_own_python_declaration_defaults_are_not_function_execution(tmp_path):
    source = 'def outer(a=exit(1)):\n return a\n'
    answer = _answer(tmp_path, 'python', source)
    assert [(r['line'], r['text']) for r in answer['findings']] == [(2, 'return a')]


@pytest.mark.parametrize('language', ['javascript', 'typescript', 'tsx'])
def test_own_invocation_defaults_and_nested_deferred_defaults_differ(tmp_path, language):
    source = ('function outer(a=exit(1)){\n const inner=(b=exit(2))=>exit(3);\n'
              ' return a;\n}')
    answer = _answer(tmp_path, language, source)
    assert [(r['line'], r['text']) for r in answer['findings']] == [
        (1, 'exit(1)'), (3, 'return a;'),
    ]


def test_nested_js_computed_name_is_formation_but_its_parameters_are_deferred(tmp_path):
    source = ('function outer(){\n class C {\n [exit(1)](a=exit(2)){return 3;}\n }\n'
              ' return 4;\n}')
    answer = _answer(tmp_path, 'javascript', source)
    assert [(r['line'], r['text']) for r in answer['findings']] == [
        (3, 'exit(1)'), (5, 'return 4;'),
    ]


def test_nested_cpp_capture_is_formation_but_parameter_and_body_are_deferred(tmp_path):
    source = ('int outer(){\n auto f=[x=(exit(1),0)](int a=(exit(2),0)){\n'
              ' return 3;\n };\n return 4;\n}')
    answer = _answer(tmp_path, 'cpp', source)
    assert [(r['line'], r['text']) for r in answer['findings']] == [
        (2, 'exit(1)'), (5, 'return 4;'),
    ]


@pytest.mark.parametrize('element,lines', [(':6', [6]), (':2', [3, 5, 6]), (':1-6', [3, 5, 6])])
def test_scope_metadata_follows_resolved_node_for_source_ranges(tmp_path, element, lines):
    source = 'def outer(a):\n def inner():\n  return 1\n if a:\n  return 2\n return 3\n'
    answer = _answer(tmp_path, 'python', source, element=element)
    assert [r['line'] for r in answer['findings']] == lines
    assert answer['meta']['exit_scope']['mode'] == 'source_scope'
    assert answer['meta']['exit_scope']['reason'] == 'source_root_inventory'


def test_named_aggregate_metadata_names_source_inventory(tmp_path):
    answer = _answer(tmp_path, 'python', 'class C:\n def first(self):\n  return 1\n', element='C')
    assert answer['meta']['exit_scope']['mode'] == 'source_scope'
    assert answer['meta']['exit_scope']['reason'] == 'aggregate_scope_inventory'


def test_owned_gate_chains_keep_outer_declaration_condition(tmp_path):
    source = ('def outer(a):\n if a:\n  def inner(x=exit(1)):\n   return 2\n'
              ' return 3\n')
    answer = _answer(tmp_path, 'python', source)
    assert [(r['text'], r['gates']) for r in answer['findings']] == [
        ('exit(1)', [{'line': 2, 'text': 'a'}]), ('return 3', []),
    ]


def test_nested_js_field_initializers_distinguish_formation_and_instance_execution(tmp_path):
    source = ('function outer(){\n class C {\n [exit(1)] = exit(2);\n'
              ' static x = exit(3);\n }\n return 4;\n}')
    answer = _answer(tmp_path, 'javascript', source)
    assert [r['text'] for r in answer['findings']] == ['exit(1)', 'exit(3)', 'return 4;']


def test_nested_swift_capture_is_formation_but_its_body_is_deferred(tmp_path):
    source = ('func outer() -> Int {\n let f = { [x = exit(1)] () -> Int in\n'
              ' return 2\n }\n return 3\n}')
    answer = _answer(tmp_path, 'swift', source)
    assert [r['text'] for r in answer['findings']] == ['exit(1)', 'return 3']


@pytest.mark.parametrize('expression,uncertain', [
    ('(exit(x) for x in [1, 2])', ['exit(x)']),
    ('[exit(x) for x in [1, 2]]', []),
    ('(x for x in exit(1))', []),
    ('(x for x in [1] for y in exit(2) if exit(3))', ['exit(2)', 'exit(3)']),
    ('((y for y in exit(1)) for x in [1])', ['exit(1)']),
    ('(x for x in (exit(y) for y in [1]))', ['exit(y)']),
])
def test_generator_deferred_regions_are_not_confident_outer_execution(tmp_path, expression, uncertain):
    source = 'def outer():\n g = ' + expression + '\n return g\n'
    answer = _answer(tmp_path, 'python', source)
    assert answer['meta']['exit_scope']['mode'] == 'selected_callable'
    sites = answer['meta']['exit_scope'].get('unresolved_sites', [])
    assert [s['text'] for s in sites] == uncertain
    assert all('generator' in s['cause'].lower() for s in sites)
    warnings = answer['meta'].get('warnings', [])
    assert bool([w for w in warnings if w['type'] == 'ownership_unresolved']) == bool(uncertain)


@pytest.mark.parametrize('expression,uncertain', [
    ('async { return 1; }', ['return 1']),
    ('{ return 1; }', []),
])
def test_rust_async_block_candidates_do_not_claim_enclosing_execution(tmp_path, expression, uncertain):
    source = 'fn outer()->i32 {\n let pending = ' + expression + ';\n return 2;\n}'
    answer = _answer(tmp_path, 'rust', source)
    assert [r['text'] for r in answer['findings']] == ['return 1', 'return 2']
    sites = answer['meta']['exit_scope'].get('unresolved_sites', [])
    assert [s['text'] for s in sites] == uncertain
    assert all('async' in s['cause'].lower() for s in sites)
