"""BACK-2064: a function-level (lazy, conditional) import is an importer edge.

Each fixture has one module ``a``, one importer ``b`` that imports it at file scope and
one importer ``c`` that imports it inside a function body. ``depends://`` (the reverse
graph) and ``imports://?rank=fan-in`` must both name ``b`` and ``c`` as importers of ``a``.

Measured on 93600af3: ``depends://`` finds the function-level importer in every language
below; ``imports://`` finds it in every language except Python, where
``analyzers/imports/service.py`` ``resolve_graph`` skips ``stmt.scope == 'local'`` (set only
by the Python extractor). That skip is BACK-445's: a lazy import cannot cause an
import-time cycle, so ``?circular`` must not count it. The fix BACK-2061 designs keeps the
edge, tagged lazy: cycles leave lazy edges out, fan-in and importers keep them. The
Python fan-in case is therefore a strict expected failure, and
``test_lazy_back_edge_is_not_a_cycle`` holds BACK-445's half of the contract.

Kotlin and Swift have no function-scope import: ``kotlinc`` says "expecting an element"
and ``swiftc`` "declaration is only valid at file scope" for one, so only their file-scope
importer is tested. Scala allows ``import`` in any block and is tested like the rest.
"""

import json

import pytest

from conftest import _run_reveal_direct
from reveal.utils.path_utils import to_posix

BACK_2061 = 'BACK-2061: resolve_graph drops function-level imports (BACK-445); fix = lazy tag'

# language -> (files, target, file-scope importers, function-level importers)
CASES = {
    'python': ({
        'a.py': 'X = 1\n',
        'b.py': 'import a\n',
        'c.py': 'def f():\n    import a\n    return a\n',
    }, 'a.py', ['b.py'], ['c.py']),
    'javascript': ({
        'a.js': 'export const x = 1;\n',
        'b.js': "import {x} from './a.js';\nexport const y = x;\n",
        'c.js': "export function f() { return import('./a.js'); }\n",
        'd.js': "function g() { return require('./a.js'); }\nmodule.exports = g;\n",
    }, 'a.js', ['b.js'], ['c.js', 'd.js']),
    'typescript': ({
        'a.ts': 'export const x = 1;\n',
        'b.ts': "import {x} from './a';\nexport const y = x;\n",
        'c.ts': "export function f() { return import('./a'); }\n",
    }, 'a.ts', ['b.ts'], ['c.ts']),
    'rust': ({
        'Cargo.toml': '[package]\nname = "fx"\nversion = "0.1.0"\nedition = "2021"\n',
        'src/main.rs': 'mod a;\nmod b;\nmod c;\nfn main() {}\n',
        'src/a.rs': 'pub fn x() {}\n',
        'src/b.rs': 'use crate::a::x;\npub fn g() { x(); }\n',
        'src/c.rs': 'pub fn f() {\n    use crate::a::x;\n    x();\n}\n',
    }, 'src/a.rs', ['src/b.rs'], ['src/c.rs']),
    'ruby': ({
        'a.rb': 'X = 1\n',
        'b.rb': "require_relative 'a'\n",
        'c.rb': "def f\n  require_relative 'a'\nend\n",
    }, 'a.rb', ['b.rb'], ['c.rb']),
    'php': ({
        'a.php': '<?php\nfunction x() {}\n',
        'b.php': "<?php\nrequire_once 'a.php';\n",
        'c.php': "<?php\nfunction f() { require_once 'a.php'; }\n",
    }, 'a.php', ['b.php'], ['c.php']),
    'lua': ({
        'a.lua': 'return {}\n',
        'b.lua': "local a = require('a')\nreturn a\n",
        'c.lua': "local function f() return require('a') end\nreturn f\n",
    }, 'a.lua', ['b.lua'], ['c.lua']),
    'zig': ({
        'a.zig': 'pub const x = 1;\n',
        'b.zig': 'const a = @import("a.zig");\npub const y = a.x;\n',
        'c.zig': 'pub fn f() void {\n    const a = @import("a.zig");\n    _ = a;\n}\n',
    }, 'a.zig', ['b.zig'], ['c.zig']),
    'gdscript': ({
        'a.gd': 'extends Node\nfunc x():\n\tpass\n',
        'b.gd': 'extends Node\nconst A = preload("res://a.gd")\n',
        'c.gd': 'extends Node\nfunc f():\n\tvar A = preload("res://a.gd")\n',
    }, 'a.gd', ['b.gd'], ['c.gd']),
    'scala': ({
        'pkg/A.scala': 'package pkg\n\nobject A {\n  val x = 1\n}\n',
        'B.scala': 'package app\n\nimport pkg.A\n\nobject B {\n  val y = A.x\n}\n',
        'C.scala': 'package app\n\nobject C {\n'
                   '  def f(): Int = {\n    import pkg.A\n    A.x\n  }\n}\n',
    }, 'pkg/A.scala', ['B.scala'], ['C.scala']),
    'kotlin': ({
        'pkg/A.kt': 'package pkg\n\nclass A {\n    val x = 1\n}\n',
        'B.kt': 'package app\n\nimport pkg.A\n\nval y = A().x\n',
    }, 'pkg/A.kt', ['B.kt'], []),
    'swift': ({
        'A.swift': 'public let x = 1\n',
        'B.swift': 'import A\n\npublic let y = x\n',
    }, 'A.swift', ['B.swift'], []),
}

NO_FUNCTION_SCOPE_IMPORT = {
    'kotlin': 'Kotlin imports are file-header only: kotlinc rejects one in a function body '
              '("expecting an element") and tree-sitter parses it as an error',
    'swift': 'Swift imports are file-scope only: swiftc rejects one in a function body '
             '("declaration is only valid at file scope") and tree-sitter parses it as an error',
}

# imports:// languages whose function-level importer is dropped today, by task.
IMPORTS_KNOWN_DROPS = {'python': BACK_2061}


def _project(tmp_path, lang):
    files, target, top, lazy = CASES[lang]
    root = (tmp_path / lang).resolve()  # macOS tmp is /private/var
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return root, target, top, lazy


def _json(*args):
    out = _run_reveal_direct(*args, '--format', 'json')
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _depends_importers(root, target):
    """Files depends:// lists as importing ``target``; the scan root is pinned to the fixture."""
    r = to_posix(root)
    data = _json(f'depends://{r}/{target}?root={r}')
    return sorted(to_posix(d['file']) for d in data['dependents'])


def _fan_in(root):
    """{file: (fan_in, fan_out)} from imports://?rank=fan-in."""
    data = _json(f'imports://{to_posix(root)}?rank=fan-in')
    return {to_posix(e['file']): (e['fan_in'], e['fan_out']) for e in data['entries']}


def _imports_importers(root, target):
    """Files imports:// counts as importing ``target``.

    Every importer in a fixture imports only the target, so an importer is a file with
    fan-out; the target's fan-in must agree with that count.
    """
    ranks = _fan_in(root)
    importers = sorted(f for f, (_fan_in_, fan_out) in ranks.items() if fan_out)
    assert ranks[target][0] == len(importers), ranks
    return importers


ENGINES = {'depends': _depends_importers, 'imports': _imports_importers}


def _param(scope, lang, engine):
    marks = []
    if scope == 'function' and lang in NO_FUNCTION_SCOPE_IMPORT:
        marks.append(pytest.mark.skip(reason=NO_FUNCTION_SCOPE_IMPORT[lang]))
    elif scope == 'function' and engine == 'imports' and lang in IMPORTS_KNOWN_DROPS:
        marks.append(pytest.mark.xfail(
            strict=True, reason=IMPORTS_KNOWN_DROPS[lang], raises=AssertionError))
    return pytest.param(lang, engine, id=f'{lang}-{engine}', marks=marks)


def _params(scope):
    return [_param(scope, lang, engine) for lang in CASES for engine in ENGINES]


@pytest.mark.parametrize('lang,engine', _params('top'))
def test_file_scope_importer_is_found(tmp_path, lang, engine):
    root, target, top, _lazy = _project(tmp_path, lang)
    found = ENGINES[engine](root, target)
    assert set(top) <= set(found), found


@pytest.mark.parametrize('lang,engine', _params('function'))
def test_function_level_importer_is_found(tmp_path, lang, engine):
    root, target, top, lazy = _project(tmp_path, lang)
    assert lazy, 'positive control: the fixture has a function-level importer'
    assert ENGINES[engine](root, target) == sorted(top + lazy)


# BACK-445: `a` imports `b` at module level; `b` imports `a` back inside a function. The
# back-edge runs only after both modules finished importing, so it is no import cycle.
LAZY_BACK_EDGE = {'a.py': 'import b\nX = 1\n', 'b.py': 'def f():\n    import a\n    return a.X\n'}
EAGER_BACK_EDGE = {'a.py': 'import b\nX = 1\n', 'b.py': 'import a\n\n\ndef f():\n    return a.X\n'}


def _python_tree(root, files):
    root = root.resolve()
    root.mkdir()
    for rel, text in files.items():
        (root / rel).write_text(text, encoding='utf-8')
    return root


def _cycles(root):
    r = to_posix(root)
    circular = _json(f'imports://{r}?circular')
    ranked = _json(f'imports://{r}?rank=fan-in')
    return circular['count'], circular['metadata']['has_cycles'], ranked['metadata']['has_cycles']


def test_lazy_back_edge_is_not_a_cycle(tmp_path):
    root = _python_tree(tmp_path / 'lazy', LAZY_BACK_EDGE)
    assert _depends_importers(root, 'a.py') == ['b.py'], (
        'positive control: the lazy back-edge is real')
    assert _cycles(root) == (0, False, False)


def test_eager_back_edge_is_a_cycle(tmp_path):
    """Control for the control: the same shape with the back-edge at module level is a cycle."""
    root = _python_tree(tmp_path / 'eager', EAGER_BACK_EDGE)
    assert _cycles(root) == (1, True, True)
