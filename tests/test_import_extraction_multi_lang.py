"""Regression tests for generic multi-language import extraction (BACK-475).

`TreeSitterAnalyzer._extract_imports()` (treesitter.py) walks a fixed
`IMPORT_NODE_TYPES` node-kind list shared across every tree-sitter language.
Same disease as BACK-474 (class/struct/impl ancestor chain): a language's
real import node kind is missing from the shared list, so its imports are
silently absent from `get_structure()['imports']` — not an empty result on
an import-free file, but a *wrong* empty result on a file full of imports.
"""

import os
import tempfile

from reveal.analyzers.php import PhpAnalyzer
from reveal.analyzers.kotlin import KotlinAnalyzer
from reveal.analyzers.dart import DartAnalyzer


def _get_structure(analyzer_cls, suffix, code):
    with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False, encoding='utf-8') as f:
        f.write(code)
        f.flush()
        temp_path = f.name
    try:
        analyzer = analyzer_cls(temp_path)
        return analyzer.get_structure()
    finally:
        os.unlink(temp_path)


class TestPhpImportExtraction:
    def test_namespace_use_declaration_is_extracted(self):
        code = '''<?php
namespace App;

use App\\Models\\User;
use App\\Services\\{Foo, Bar};

class Widget {}
'''
        structure = _get_structure(PhpAnalyzer, '.php', code)
        imports = structure.get('imports', [])
        assert len(imports) == 2, f"expected 2 'use' imports, got: {imports}"


class TestKotlinImportExtraction:
    def test_import_header_is_extracted(self):
        code = '''package com.example

import kotlin.math.PI
import java.util.List

class Widget {}
'''
        structure = _get_structure(KotlinAnalyzer, '.kt', code)
        imports = structure.get('imports', [])
        assert len(imports) == 2, f"expected 2 imports, got: {imports}"


class TestDartImportExtraction:
    def test_library_import_is_extracted_and_export_is_not(self):
        code = '''import 'dart:core';
import 'package:foo/foo.dart';
export 'package:foo/public.dart';

class Widget {}
'''
        structure = _get_structure(DartAnalyzer, '.dart', code)
        imports = structure.get('imports', [])
        assert len(imports) == 2, f"expected 2 imports (not the export), got: {imports}"
