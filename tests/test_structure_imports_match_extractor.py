"""BACK-1089: the outline/ast:// import list and imports:// must agree.

Two extraction paths over the same source used to disagree with no cross-check:
Ruby/GDScript/Lua/Zig/CommonJS/PHP outlined 0 imports while imports:// found them,
and Go's `import (...)` block counted as one. Analyzers whose imports are not a
plain node kind now route through the imports:// extractor; this pins agreement
for every conformance fixture language so a new path can't drift silently.
"""

from pathlib import Path

import pytest

from reveal.analyzers.imports.base import get_extractor
from reveal.registry import get_analyzer

FIXTURES = sorted(Path(__file__).parent.glob('fixtures/conformance/*/sample.*'))


@pytest.mark.parametrize('fixture', FIXTURES, ids=lambda p: p.parent.name)
def test_structure_import_count_matches_extractor(fixture):
    extractor = get_extractor(fixture)
    if extractor is None:
        pytest.skip('no imports extractor for this language')
    structure = get_analyzer(str(fixture))(str(fixture)).get_structure()
    assert len(structure.get('imports', [])) == len(extractor.extract_imports(fixture))


def _structure_imports(tmp_path, name, code):
    path = tmp_path / name
    path.write_text(code, encoding='utf-8')
    structure = get_analyzer(str(path))(str(path)).get_structure()
    return [(i['line'], i['content']) for i in structure.get('imports', [])]


def test_ruby_require_calls_are_imports(tmp_path):
    got = _structure_imports(tmp_path, 'a.rb', "require 'json'\nrequire_relative 'b'\nclass A; end\n")
    assert [line for line, _ in got] == [1, 2]


def test_lua_require_is_an_import(tmp_path):
    got = _structure_imports(tmp_path, 'a.lua', 'local json = require("cjson")\nlocal M = {}\nreturn M\n')
    assert [line for line, _ in got] == [1]


def test_gdscript_preload_is_an_import(tmp_path):
    got = _structure_imports(tmp_path, 'a.gd', 'const U = preload("res://u.gd")\nfunc f(): pass\n')
    assert [line for line, _ in got] == [1]


def test_zig_import_builtin_is_listed(tmp_path):
    got = _structure_imports(tmp_path, 'a.zig', 'const std = @import("std");\npub fn main() void {}\n')
    assert got == [(1, 'const std = @import("std");')]


def test_go_grouped_import_lists_each_package(tmp_path):
    got = _structure_imports(tmp_path, 'a.go',
                             'package p\n\nimport (\n\t"fmt"\n\t"os"\n\tstr "strings"\n)\n\nfunc f() {}\n')
    assert [line for line, _ in got] == [4, 5, 6]


def test_commonjs_require_is_listed_for_javascript(tmp_path):
    got = _structure_imports(tmp_path, 'a.js', "const fs = require('fs');\nmodule.exports = {};\n")
    assert [line for line, _ in got] == [1]


def test_language_without_extractor_flag_keeps_node_kind_path(tmp_path):
    got = _structure_imports(tmp_path, 'a.py', 'import os\nfrom sys import path\n')
    assert [line for line, _ in got] == [1, 2]
