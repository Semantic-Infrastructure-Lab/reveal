"""Registry-wide, oracle-free import invariants (BACK-1096)."""
import pytest

from reveal.adapters.imports import ImportsAdapter
from reveal.analyzers.imports.base import _EXTRACTOR_REGISTRY, get_extractor
from reveal.registry import get_analyzer
from reveal.rules.imports.I002 import I002, _extract_imports_for_file, _graph_cache

pytestmark = [pytest.mark.component, pytest.mark.disk_cache]

# At least one real syntax fixture for every registered extractor class, plus TS.
CASES = {
    '.py': ('import os\n', 'def broken(\n', '# comment\n'),
    '.js': ("import fs from 'fs';\n", 'function broken(\n', '// comment\n'),
    '.ts': ("import fs from 'fs';\n", 'function broken(\n', '// comment\n'),
    '.go': ('package demo\nimport "fmt"\n', 'func broken( { {{{\n', '// comment\n'),
    '.rs': ('use std::fmt;\n', 'fn broken(\n', '// comment\n'),
    '.zig': ('const std = @import("std");\n', 'pub fn broken(\n', '// comment\n'),
    '.c': ('#include "util.h"\n', 'int broken(\n', '// comment\n'),
    '.cpp': ('#include "util.h"\n', 'int broken(\n', '// comment\n'),
    '.java': ('import java.util.List;\n', 'class Broken { int x = + ; @@\n', '// comment\n'),
    '.cs': ('using System;\n', 'class Broken {\n', '// comment\n'),
    '.php': ("<?php\nrequire 'util.php';\n", 'function broken(\n', '// comment\n'),
    '.rb': ("require 'json'\n", 'def broken(\n', '# comment\n'),
    '.swift': ('import Foundation\n', 'func broken(\n', '// comment\n'),
    '.kt': ('import java.util.List\n', 'fun broken(\n', '// comment\n'),
    '.scala': ('import scala.util.Try\n', 'def broken(\n', '// comment\n'),
    '.dart': ("import 'dart:io';\n", 'void broken(\n', '// comment\n'),
    '.gd': ('extends "util.gd"\n', 'func broken(\n', '# comment\n'),
    '.lua': ('local util = require("util")\n', 'function broken(\n', '-- comment\n'),
}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')
    _graph_cache.clear()
    yield
    _graph_cache.clear()


def claims(imports):
    return [(s.line_number, s.module_name, s.imported_names, s.import_type) for s in imports]


def test_every_registered_extractor_has_an_invariant_fixture():
    covered = {_EXTRACTOR_REGISTRY[ext] for ext in CASES}
    assert covered == set(_EXTRACTOR_REGISTRY.values())


@pytest.mark.parametrize('suffix', CASES)
def test_imports_survive_unrelated_error_copy_and_comment(tmp_path, suffix):
    clean, broken, comment = CASES[suffix]
    prefix = tmp_path / ('clean' + suffix)
    prefix.write_text(clean, encoding='utf-8')
    extractor = get_extractor(prefix)
    imports = extractor.extract_imports(prefix)
    assert imports and not extractor.parse_failed, 'positive control must contain valid imports'
    expected = claims(imports)
    for name, source, partial in (('copy', clean, False), ('comment', clean + comment, False),
                                  ('partial', clean + broken, True)):
        path = tmp_path / (name + suffix)
        path.write_text(source, encoding='utf-8')
        extractor = get_extractor(path)
        recovered = extractor.extract_imports(path)
        assert claims(recovered) == expected, 'unrelated syntax must not erase recovered imports'
        assert extractor.parse_failed is partial
        # Citation integrity: every claimed module occurs on its claimed source line.
        lines = source.splitlines()
        for statement in recovered:
            assert statement.file_path == path
            assert statement.module_name in lines[statement.line_number - 1]
        analyzer = get_analyzer(str(path))(str(path))
        assert analyzer.tree and analyzer.has_parse_errors() is partial
        worker_imports, failed = _extract_imports_for_file(str(path))
        assert claims(worker_imports) == expected and failed is partial
        adapter = ImportsAdapter(resource=str(path))
        adapter._build_graph(path)
        assert claims(adapter.analysis.graph.files[path]) == expected
        assert bool(adapter.analysis.files_failed) is partial


def test_renaming_python_package_preserves_cycle_count(tmp_path):
    counts = []
    for name in ('alpha', 'renamed'):
        root = tmp_path / name
        root.mkdir()
        (root / 'pyproject.toml').write_text('[project]\nname="probe"\n', encoding='utf-8')
        (root / 'a.py').write_text('import b\n', encoding='utf-8')
        (root / 'b.py').write_text('import a\n', encoding='utf-8')
        adapter = ImportsAdapter(resource=str(root))
        adapter._build_graph(root)
        rule_graph = I002()._build_import_graph(root)
        adapter_count = len(adapter.analysis.graph.find_cycle_groups())
        assert adapter_count == len(rule_graph.find_cycle_groups()) == 1
        counts.append(adapter_count)
    assert counts == [1, 1]


@pytest.mark.parametrize('suffix,body,used', [
    ('.py', 'print(os.getcwd())\n', 'os'),
    ('.js', "fs.readFile('x');\n", 'fs'),
    ('.go', 'func keep() { fmt.Println("x") }\n', 'fmt'),
    ('.rs', 'fn keep() { fmt::Error; }\n', 'fmt'),
])
def test_partial_parse_preserves_symbols_where_supported(tmp_path, suffix, body, used):
    clean, broken, _ = CASES[suffix]
    clean_path = tmp_path / ('symbols' + suffix)
    clean_path.write_text(clean + body, encoding='utf-8')
    extractor = get_extractor(clean_path)
    before = extractor.extract_symbols(clean_path)
    assert used in before and not extractor.parse_failed
    partial_path = tmp_path / ('partial_symbols' + suffix)
    partial_path.write_text(clean + body + broken, encoding='utf-8')
    extractor = get_extractor(partial_path)
    after = extractor.extract_symbols(partial_path)
    assert before <= after and extractor.parse_failed
