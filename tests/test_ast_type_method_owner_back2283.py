"""BACK-2283: ``ast://?type=method`` selects methods only.

``owner`` names every container around a definition (it drives --outline nesting and the
``inner.f`` labels), so a free function in a Rust ``mod`` or a C++/TypeScript namespace and a
function nested in a method also carry one, and ``type=method`` returned them. A method is now
a function whose nearest enclosing definition is a type; ``owner`` itself is unchanged.
"""

import pytest

from reveal.adapters.ast.adapter import AstAdapter

SOURCES = {
    'm.py': (
        'class K:\n'
        '    def m(self):\n'
        '        def inner():\n'
        '            pass\n'
        '        class L:\n'
        '            def lm(self):\n'
        '                pass\n'
        '        return inner\n'
        '    class N:\n'
        '        def nm(self):\n'
        '            pass\n'
        '\n'
        'def top():\n'
        '    def nested():\n'
        '        pass\n'
    ),
    'a.rs': (
        'mod inner {\n'
        '    pub fn f() {}\n'
        '    pub struct Q;\n'
        '    impl Q { pub fn q(&self) {} }\n'
        '}\n'
        'struct S;\n'
        'impl S {\n'
        '    fn m(&self) {\n'
        '        fn helper() {}\n'
        '    }\n'
        '}\n'
        'trait T { fn d(&self) {} }\n'
        'fn free() {}\n'
    ),
    'c.cpp': 'namespace app {\nvoid nf() {}\nclass C {\npublic:\n  void cm() {}\n};\n}\n',
    'c.cs': 'namespace App {\nclass C {\n  void M() {\n  }\n}\n}\n',
    't.ts': (
        'namespace NS {\n'
        '  export function nsf() { return 1; }\n'
        '  export class Z { zm() { return 2; } }\n'
        '}\n'
        'class A {\n'
        '  m() {\n'
        '    function inm() { return 1; }\n'
        '    const arrow = () => 2;\n'
        '    return inm;\n'
        '  }\n'
        '}\n'
    ),
    'j.js': (
        'class A {\n'
        '  m() {\n'
        '    function inm() { return 1; }\n'
        '    return inm;\n'
        '  }\n'
        '}\n'
        'function Foo() {}\n'
        'Foo.prototype.bar = function () { return 1; };\n'
        '(function () {\n'
        '  Foo.prototype.baz = function () { return 2; };\n'
        '})();\n'
    ),
    'r.rb': 'module M\n  def mm; end\n  def self.ms; end\nend\nclass R\n  def rm; end\nend\n',
    'p.php': (
        '<?php\nnamespace App;\nfunction pf() {}\nclass P {\n  function pm() {\n'
        '    $c = new class { function am() {} };\n  }\n}\n'
    ),
    'k.kt': 'class Kt {\n  fun km() {\n    fun local() {}\n  }\n}\nfun top() {}\n',
    's.swift': 'class Sw {\n  func sm() {\n    func local() {}\n  }\n}\n',
    'd.dart': 'class D {\n  void dm() {\n    void local() {}\n  }\n}\nvoid top() {}\n',
    'o.scala': (
        'object O {\n  def om(): Int = 1\n}\nclass Sc {\n  def scm(): Int = {\n'
        '    def local(): Int = 2\n    local()\n  }\n}\n'
    ),
    'J.java': (
        'class J {\n  void jm() {\n'
        '    Runnable r = new Runnable() { public void run() {} };\n  }\n}\n'
    ),
    'g.go': 'package main\n\ntype T struct{}\n\nfunc (t T) M() int { return 1 }\n\nfunc F() int { return 2 }\n',
}

METHODS = {
    ('m.py', 'm'), ('m.py', 'lm'), ('m.py', 'nm'),
    ('a.rs', 'q'), ('a.rs', 'm'), ('a.rs', 'd'),
    ('c.cpp', 'cm'), ('c.cs', 'M'),
    ('t.ts', 'zm'), ('t.ts', 'm'),
    ('j.js', 'm'), ('j.js', 'bar'), ('j.js', 'baz'),
    ('r.rb', 'mm'), ('r.rb', 'ms'), ('r.rb', 'rm'),
    ('p.php', 'pm'), ('p.php', 'am'),
    ('k.kt', 'km'), ('s.swift', 'sm'), ('d.dart', 'dm'),
    ('o.scala', 'om'), ('o.scala', 'scm'),
    ('J.java', 'jm'), ('J.java', 'run'),
    ('g.go', 'M'),
}
# Functions that keep an owner (outline nesting, labels) but are not methods.
OWNED_NON_METHODS = {
    ('m.py', 'inner'): 'K',
    ('a.rs', 'f'): 'inner',
    ('a.rs', 'helper'): 'S',
    ('c.cpp', 'nf'): 'app',
    ('t.ts', 'nsf'): 'NS',
    ('t.ts', 'inm'): 'A',
    ('t.ts', 'arrow'): 'A',
    ('j.js', 'inm'): 'A',
    ('k.kt', 'local'): 'Kt',
    ('s.swift', 'local'): 'Sw',
    ('d.dart', 'local'): 'D',
    ('o.scala', 'local'): 'Sc',
}
FREE = {('m.py', 'top'), ('m.py', 'nested'), ('a.rs', 'free'), ('j.js', 'Foo'), ('p.php', 'pf'),
        ('k.kt', 'top'), ('d.dart', 'top'), ('g.go', 'F')}


@pytest.fixture(scope='module')
def tree(tmp_path_factory):
    root = tmp_path_factory.mktemp('back2283')
    for name, text in SOURCES.items():
        (root / name).write_text(text, encoding='utf-8')
    return root


def _rows(tree, query):
    results = AstAdapter(str(tree), query).get_structure()['results']
    return {(r['file'].replace('\\', '/').rsplit('/', 1)[-1], r['name']): r for r in results}


def test_type_method_is_methods_only(tree):
    assert set(_rows(tree, 'type=method')) == METHODS


def test_type_not_method_keeps_nested_and_namespace_functions(tree):
    rows = _rows(tree, 'type!=method')
    assert {key for key, row in rows.items() if row['category'] == 'functions'} == set(OWNED_NON_METHODS) | FREE


def test_owner_is_unchanged_for_non_methods(tree):
    """Negative control: owner still names the container (outline nesting, `inner.f` labels)."""
    rows = _rows(tree, 'type=function')
    assert {key: rows[key].get('owner') for key in OWNED_NON_METHODS} == OWNED_NON_METHODS
    assert rows[('m.py', 'lm')]['owner'] == 'K.L'
    assert rows[('a.rs', 'q')]['owner'] == 'inner.Q'


def test_type_function_still_lists_every_function(tree):
    """Negative control: type=function is not narrowed."""
    assert set(_rows(tree, 'type=function')) == METHODS | set(OWNED_NON_METHODS) | FREE
