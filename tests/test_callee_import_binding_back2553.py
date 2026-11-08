"""A call bound by an import resolves through that import (BACK-2553).

`calls://?callees=` stripped a call to its tail and looked the tail up among the project's
definitions before it looked at what the call's qualifier or bare name is bound to. So
`json.loads` inside `def loads` read as recursion, `join` imported from `os.path` resolved to
a project `join`, and `readFileSync` imported from 'fs' was "ambiguous among 4 definitions".
The import analysis the imports:// graph already builds records, per import, the file it
resolved to and the extractor's intra-project verdict; the resolver reads that.

Each test asserts the edge's target, not that an edge exists.
"""

from pathlib import Path
from typing import Dict

import pytest

from reveal.adapters.calls.adapter import CallsAdapter


def _tree(tmp_path: Path, files: Dict[str, str]) -> str:
    for name, text in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
    return str(tmp_path)


def _edges(path: str, root: str, depth: int = 1) -> Dict[str, dict]:
    """call text -> edge, for every edge the walk lists."""
    result = CallsAdapter(path, f'root={root}&depth={depth}').get_structure()
    assert result['type'] == 'calls_callees_recursive'
    return {e['call_expr']: e for level in result['levels'] for e in level['callees']}


def _target(edge: dict):
    """(file name, 'ambiguous' | 'external' | None) of an edge."""
    if edge.get('ambiguous'):
        return None, 'ambiguous'
    if not edge['resolved']:
        return None, 'external'
    return Path(edge['callee_file']).name, None


# --- Python: an external module's call is never the project's same-named function ---------------

def test_external_qualifier_is_not_the_enclosing_function(tmp_path):
    # Before: json.loads -> loads c.py (its one definition): false self-recursion.
    path = _tree(tmp_path, {'c.py': 'import json\n\ndef loads(s):\n    return json.loads(s)\n'})
    assert _target(_edges(path, 'loads')['json.loads']) == (None, 'external')


def test_external_qualifier_beats_the_same_file_definition_among_several(tmp_path):
    # Before: two `loads` definitions; the same-file one won for the qualified call.
    path = _tree(tmp_path, {'c.py': 'import json\n\ndef loads(s):\n    return json.loads(s)\n',
                            'e.py': 'def loads(s):\n    return s\n'})
    assert _target(_edges(path, 'c.py:loads')['json.loads']) == (None, 'external')


def test_external_named_import_is_not_a_project_function(tmp_path):
    # Before: join -> d.py:join, the wrong file (join comes from os.path).
    path = _tree(tmp_path, {'c.py': 'from os.path import join\n\ndef run(s):\n    return join(s, "x")\n',
                            'd.py': 'def join(a, b):\n    return a\n'})
    assert _target(_edges(path, 'run')['join']) == (None, 'external')


def test_external_named_import_is_not_ambiguous(tmp_path):
    path = _tree(tmp_path, {'c.py': 'from os.path import join\n\ndef run(s):\n    return join(s, "x")\n',
                            'd.py': 'def join(a, b):\n    return a\n',
                            'e.py': 'def join(a, b):\n    return b\n'})
    assert _target(_edges(path, 'run')['join']) == (None, 'external')


# --- Python controls: what must keep resolving ---------------------------------------------------

def test_in_tree_import_still_picks_its_file(tmp_path):
    path = _tree(tmp_path, {'c.py': 'from d import join\n\ndef run(s):\n    return join(s, "x")\n',
                            'd.py': 'def join(a, b):\n    return a\n',
                            'e.py': 'def join(a, b):\n    return b\n'})
    assert _target(_edges(path, 'run')['join']) == ('d.py', None)


def test_in_tree_absolute_import_the_old_symbol_map_missed(tmp_path):
    # app/sub/x.py imports `app.core`; the per-file symbol map resolved it against app/sub and
    # got None, so the call was ambiguous between the two `run` definitions.
    path = _tree(tmp_path, {'app/__init__.py': '', 'app/sub/__init__.py': '',
                            'app/core.py': 'def run():\n    pass\n',
                            'app/sub/x.py': 'from app.core import run\n\ndef go():\n    run()\n',
                            'other.py': 'def run():\n    pass\n'})
    edge = _edges(path, 'go')['run']
    assert _target(edge) == ('core.py', None)
    assert Path(edge['callee_file']).parent.name == 'app'


def test_local_definition_shadows_an_imported_name(tmp_path):
    # A bare call to a name the file both imports and defines reaches the file's own definition.
    path = _tree(tmp_path, {'c.py': ('from os.path import join\n\n'
                                     'def join(a, b):\n    return a\n\n'
                                     'def run(s):\n    return join(s, "x")\n')})
    assert _target(_edges(path, 'run')['join']) == ('c.py', None)


def test_unbound_name_keeps_the_unique_definition(tmp_path):
    path = _tree(tmp_path, {'c.py': 'import json\n\ndef run(s):\n    return helper(s)\n',
                            'd.py': 'def helper(a):\n    return a\n'})
    assert _target(_edges(path, 'run')['helper']) == ('d.py', None)


# --- TypeScript ----------------------------------------------------------------------------------

TS_SOURCE = ("import ts from 'typescript';\nimport { readFileSync } from 'fs';\n\n"
             "export function createProgram() {\n  ts.createProgram();\n  readFileSync('x');\n}\n")


def test_typescript_external_default_and_named_imports(tmp_path):
    # Before: ts.createProgram -> the enclosing createProgram; readFileSync -> ambiguous (3 files).
    path = _tree(tmp_path, {'a.ts': TS_SOURCE,
                            'b.ts': 'export function readFileSync() {}\n',
                            'c.ts': 'export function readFileSync() {}\n',
                            'd.ts': 'export function readFileSync() {}\n'})
    edges = _edges(path, 'createProgram')
    assert _target(edges['ts.createProgram']) == (None, 'external')
    assert _target(edges['readFileSync']) == (None, 'external')


def test_typescript_relative_import_still_picks_its_file(tmp_path):
    path = _tree(tmp_path, {'a.ts': "import { readFileSync } from './b';\n\nexport function go() {\n  readFileSync('x');\n}\n",
                            'b.ts': 'export function readFileSync() {}\n',
                            'c.ts': 'export function readFileSync() {}\n'})
    assert _target(_edges(path, 'go')['readFileSync']) == ('b.ts', None)


# --- the answer does not depend on the cache -----------------------------------------------------

@pytest.mark.disk_cache
def test_cold_and_warm_import_analysis_give_the_same_edges(tmp_path):
    # The first walk builds and stores the import analysis; the second reads it back. The bindings
    # (resolved file, external verdict) must survive the round trip.
    path = _tree(tmp_path, {'c.py': 'import json\nfrom d import join\n\ndef loads(s):\n    return json.loads(join(s))\n',
                            'd.py': 'def join(a):\n    return a\n',
                            'e.py': 'def join(a):\n    return a\n\ndef loads(s):\n    return s\n'})
    cold = {call: _target(edge) for call, edge in _edges(path, 'c.py:loads').items()}
    warm = {call: _target(edge) for call, edge in _edges(path, 'c.py:loads').items()}
    assert cold == warm == {'json.loads': (None, 'external'), 'join': ('d.py', None)}


# --- the walk's root does not change the answer --------------------------------------------------

def test_a_file_root_resolves_like_its_directory(tmp_path):
    # A file root reads its directory's definitions; its calls must resolve the same way
    # (`reveal FILE NAME --effects --transitive` walks from the file).
    _tree(tmp_path, {'c.py': 'import json\nfrom os.path import join\n\ndef loads(s):\n    return json.loads(join(s))\n',
                     'd.py': 'def join(a):\n    return a\n'})
    edges = _edges(str(tmp_path / 'c.py'), 'loads')
    assert _target(edges['json.loads']) == (None, 'external')
    assert _target(edges['join']) == (None, 'external')


def test_a_subdirectory_root_reads_the_project_alias(tmp_path):
    # tsconfig `paths` live at the project root, above the walked directory. The import analysis
    # is the one imports:// builds (project root, focused on the directory), so `@lib/util` is
    # in-tree, not external.
    _tree(tmp_path, {'package.json': '{"name": "x"}\n',
                     'tsconfig.json': '{"compilerOptions": {"baseUrl": ".", "paths": {"@lib/*": ["src/lib/*"]}}}\n',
                     'src/app/a.ts': "import { helper } from '@lib/util';\nexport function go() {\n  helper();\n}\n",
                     'src/lib/util.ts': 'export function helper() {}\n',
                     'src/lib/other.ts': 'export function helper() {}\n'})
    assert _target(_edges(str(tmp_path / 'src'), 'go')['helper']) == ('util.ts', None)


# --- an import that binds no name binds nothing --------------------------------------------------

def test_a_cpp_include_does_not_bind_its_header_name(tmp_path):
    # `#include <array>` binds no name; `array.Size()` on a local variable is a project method
    # call, not a call into the header (it read as external).
    path = _tree(tmp_path, {'a.cpp': ('#include <array>\nstruct Arr { int Size(); };\n'
                                      'int Arr::Size() { return 0; }\n'
                                      'int run() {\n  Arr array;\n  return array.Size();\n}\n')})
    assert _target(_edges(path, 'run')['array.Size']) == ('a.cpp', None)


def test_a_ruby_require_does_not_bind_the_library_name(tmp_path):
    # Gemfile.lock lists csv, so the verdict for `require 'csv'` is external (as on Discourse).
    path = _tree(tmp_path, {'Gemfile.lock': 'GEM\n  remote: https://rubygems.org/\n  specs:\n    csv (3.3.0)\n',
                            'a.rb': ("require 'csv'\n\ndef each_line\nend\n\n"
                                     "def run(csv)\n  csv.each_line\nend\n")})
    assert _target(_edges(path, 'run')['csv.each_line']) == ('a.rb', None)


def test_a_resolved_bare_import_still_picks_its_file(tmp_path):
    # Zig binds the @import to a const named like the file; resolved in-tree, it picks the file
    # among same-named definitions (master did this; withholding the binding made 538 Zig sites
    # ambiguous).
    path = _tree(tmp_path, {'a.zig': 'const config = @import("config.zig");\npub fn run() void {\n    config.destroy();\n}\n',
                            'config.zig': 'pub fn destroy() void {}\n',
                            'other.zig': 'pub fn destroy() void {}\n'})
    assert _target(_edges(path, 'run')['config.destroy']) == ('config.zig', None)
