"""BACK-1632, BACK-1649: --outline nested by line ranges alone, so a member defined
outside its type's lines (Go receiver methods, Rust impl methods) listed flat at the
top level, and a member on the same line as its container (`namespace NS { class K
{ go() {} } }`) nested under the wrong owner: NS > go(), K.

Analyzers now record each item's owner from the tree (`owner`, the same answer
`reveal FILE Parent.child` resolves by), and the outline nests by it.
"""

import pytest

from reveal.display.outline import build_hierarchy
from reveal.registry import get_analyzer


def _tree(tmp_path, name, source):
    """The outline as nested (name, [children]) pairs, in display order."""
    path = tmp_path / name
    path.write_text(source, encoding='utf-8')
    analyzer = get_analyzer(str(path))(str(path))
    structure = {k: v for k, v in analyzer.get_outline().items() if k != 'imports'}

    def shape(items):
        return [(item['name'], shape(item['children'])) for item in items]
    return shape(build_hierarchy(structure))


@pytest.mark.parametrize('name, source, expected', [
    # Go: a method belongs to its receiver's type, wherever it is declared.
    ('a.go', 'package p\n\ntype Batch struct{ n int }\n\n'
             'func (b *Batch) Run() int { return b.n }\n\nfunc helper() {}\n',
     [('Batch', [('Run', [])]), ('helper', [])]),
    # Rust: an impl method belongs to the impl's Self type, not to the trait.
    ('a.rs', 'struct Batch { n: i32 }\nimpl Batch {\n    fn run(&self) -> i32 { self.n }\n}\n'
             'trait Summary { fn summarize(&self) -> i32; }\n'
             'impl Summary for Batch {\n    fn summarize(&self) -> i32 { 0 }\n}\nfn helper() {}\n',
     [('Batch', [('run', []), ('summarize', [])]), ('Summary', []), ('helper', [])]),
    # Rust: an impl for a type this file does not define stays top-level.
    ('ext.rs', 'impl Missing {\n    fn g() {}\n}\n', [('g', [])]),
    # TypeScript: a class on its namespace's line, a method on its class's line.
    ('one.ts', 'namespace NS { export class K { go() {} } }\n',
     [('NS', [('K', [('go', [])])])]),
    ('two.ts', 'namespace NS {\n  export class K { go() {} }\n}\n',
     [('NS', [('K', [('go', [])])])]),
    # Rust: nested modules on one line.
    ('m.rs', 'mod outer { pub mod inner { pub fn deep() {} } }\n',
     [('outer', [('inner', [('deep', [])])])]),
])
def test_outline_nests_by_owner(tmp_path, name, source, expected):
    assert _tree(tmp_path, name, source) == expected


def test_nested_function_keeps_its_enclosing_function(tmp_path):
    """The tree's owner of `inner` is class A (functions aren't member containers);
    the line parent `m` sits inside A, so it stays the closer parent."""
    source = ('class A:\n    def m(self):\n        def inner():\n            pass\n'
              '        return inner\n')
    assert _tree(tmp_path, 'a.py', source) == [('A', [('m', [('inner', [])])])]


def test_owner_is_in_the_structure(tmp_path):
    path = tmp_path / 'a.go'
    path.write_text('package p\ntype B struct{}\nfunc (b B) Run() {}\nfunc f() {}\n',
                    encoding='utf-8')
    functions = get_analyzer(str(path))(str(path)).get_structure()['functions']
    assert {f['name']: f.get('owner') for f in functions} == {'Run': 'B', 'f': None}
