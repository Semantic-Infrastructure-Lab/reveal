"""BACK-1636: namespace and module containers were invisible to the outline and to
element extraction: Rust `mod`, PHP `namespace`, C# `namespace` (Ruby's `module` was
BACK-1629). `reveal m.rs outer` said "not found" and the module's functions listed flat.

They are declaration categories now (Modules for Rust, Namespaces for PHP and C#, as
TypeScript's `namespace NS {}` already was), and a type nested in any container
resolves as `Parent.Child` (`App.K`, `Outer.Inner`), which no language did.
"""

import os
import subprocess
import sys

import pytest

from reveal.registry import get_analyzer


def _reveal(cwd, *argv):
    env = dict(os.environ, PYTHONIOENCODING='utf-8', REVEAL_NO_UPDATE_CHECK='1')
    return subprocess.run([sys.executable, '-m', 'reveal', *argv], cwd=cwd, env=env,
                          capture_output=True, text=True, encoding='utf-8', timeout=60)


# (file name, source, category, names in it)
_SOURCES = [
    ('m.rs', 'mod outer {\n    pub struct S;\n    impl S { fn go(&self) {} }\n'
             '    pub mod inner { pub fn deep() {} }\n    fn free() {}\n}\nmod ext;\n',
     'modules', ['outer', 'inner', 'ext']),
    ('braced.php', '<?php\nnamespace App {\nclass K { function f() {} }\n}\n',
     'namespaces', ['App']),
    ('plain.php', '<?php\nnamespace App\\Models;\nclass K { function f() {} }\n',
     'namespaces', ['App\\Models']),
    ('global.php', '<?php\nnamespace {\nfunction g() {}\n}\n', 'namespaces', []),
    ('block.cs', 'namespace App.Models {\n    class K { void Go() {} }\n}\n',
     'namespaces', ['App.Models']),
    ('scoped.cs', 'namespace App;\nclass K { void Go() {} }\n', 'namespaces', ['App']),
]


@pytest.mark.parametrize('name, source, category, names', _SOURCES,
                         ids=[s[0] for s in _SOURCES])
def test_container_is_a_declaration_category(tmp_path, name, source, category, names):
    path = tmp_path / name
    path.write_text(source, encoding='utf-8')
    analyzer_class = get_analyzer(str(path))
    structure = analyzer_class(str(path)).get_structure()
    assert [entry['name'] for entry in structure.get(category, [])] == names


# (file name, source, element, first line printed)
_EXTRACTIONS = [
    ('m.rs', _SOURCES[0][1], 'outer', 'mod outer {'),
    ('m.rs', _SOURCES[0][1], 'outer.free', 'fn free() {}'),
    ('m.rs', _SOURCES[0][1], 'outer.S', 'pub struct S;'),
    ('m.rs', _SOURCES[0][1], 'outer.inner.deep', 'pub fn deep() {}'),
    ('braced.php', _SOURCES[1][1], 'App', 'namespace App {'),
    ('braced.php', _SOURCES[1][1], 'App.K', 'class K'),
    ('block.cs', _SOURCES[4][1], 'App.Models', 'namespace App.Models {'),
    ('scoped.cs', _SOURCES[5][1], 'App', 'namespace App;'),
    ('ns.ts', 'namespace NS {\n  export class K { go() { return 1; } }\n}\n', 'NS.K', 'class K'),
    ('nest.py', 'class Outer:\n    class Inner:\n        def m(self):\n            pass\n',
     'Outer.Inner', 'class Inner:'),
]


@pytest.mark.parametrize('name, source, element, first', _EXTRACTIONS,
                         ids=[f'{e[0]}:{e[2]}' for e in _EXTRACTIONS])
def test_container_and_its_nested_types_extract_by_name(tmp_path, name, source, element, first):
    (tmp_path / name).write_text(source, encoding='utf-8')
    run = _reveal(tmp_path, name, element)
    assert run.returncode == 0, run.stderr
    assert first in run.stdout


def test_impl_block_is_not_a_second_answer_for_a_nested_struct(tmp_path):
    """`outer.S` is the struct; the `impl S` beside it has no name of its own."""
    (tmp_path / 'm.rs').write_text(_SOURCES[0][1], encoding='utf-8')
    run = _reveal(tmp_path, 'm.rs', 'outer.S')
    assert run.returncode == 0, run.stderr
    assert 'impl S' not in run.stdout and 'matches' not in run.stderr


@pytest.mark.parametrize('name, source, kind, first', [
    ('m.rs', _SOURCES[0][1], 'module', 'outer'),
    ('scoped.cs', _SOURCES[5][1], 'namespace', 'App'),
])
def test_type_filter_takes_the_singular(tmp_path, name, source, kind, first):
    (tmp_path / name).write_text(source, encoding='utf-8')
    run = _reveal(tmp_path, name, '--type', kind)
    assert run.returncode == 0, run.stderr
    assert first in run.stdout and 'No matches' not in run.stdout
