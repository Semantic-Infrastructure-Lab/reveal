"""Coverage tests for reveal/analyzers/imports/javascript.py.

Targets: 51, 55-59, 89-122, 138, 212, 262, 289, 303, 306, 350, 372-406,
         417-430, 451-458, 474-497
Current coverage: 62% → target: 85%+
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from reveal.analyzers.imports.javascript import JavaScriptExtractor
from reveal.analyzers.imports.types import ImportStatement


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _write_js(tmp_path: Path, name: str, code: str) -> Path:
    p = tmp_path / name
    p.write_text(code, encoding='utf-8')
    return p


# ─── extract_imports error paths ─────────────────────────────────────────────

class TestExtractImportsErrorPaths:
    def test_nonexistent_file_returns_empty(self, tmp_path):
        e = JavaScriptExtractor()
        result = e.extract_imports(tmp_path / 'missing.js')
        assert result == []

    def test_empty_file_returns_empty(self, tmp_path):
        f = _write_js(tmp_path, 'empty.js', '')
        e = JavaScriptExtractor()
        result = e.extract_imports(f)
        assert result == []

    def test_get_analyzer_none_returns_empty(self):
        """Cover line 51: get_analyzer returns None."""
        e = JavaScriptExtractor()
        with patch('reveal.analyzers.imports.javascript.get_analyzer', return_value=None):
            result = e.extract_imports(Path('fake.js'))
        assert result == []

    def test_tree_none_returns_empty(self, tmp_path):
        """Cover lines 54-55: analyzer.tree is None."""
        f = _write_js(tmp_path, 'x.js', 'const x = 1;')
        mock_analyzer = MagicMock()
        mock_analyzer.tree = None
        mock_cls = MagicMock(return_value=mock_analyzer)
        e = JavaScriptExtractor()
        with patch('reveal.analyzers.imports.javascript.get_analyzer', return_value=mock_cls):
            result = e.extract_imports(f)
        assert result == []

    def test_exception_returns_empty(self):
        """Cover lines 57-59: exception path."""
        e = JavaScriptExtractor()
        with patch('reveal.analyzers.imports.javascript.get_analyzer', side_effect=RuntimeError('boom')):
            result = e.extract_imports(Path('fake.js'))
        assert result == []


# ─── extract_symbols error paths ─────────────────────────────────────────────

class TestExtractSymbolsErrorPaths:
    def test_nonexistent_file_returns_empty_set(self, tmp_path):
        e = JavaScriptExtractor()
        result = e.extract_symbols(tmp_path / 'missing.js')
        assert result == set()

    def test_empty_file_returns_empty_set(self, tmp_path):
        f = _write_js(tmp_path, 'empty.js', '')
        e = JavaScriptExtractor()
        result = e.extract_symbols(f)
        assert result == set()

    def test_get_analyzer_none_returns_empty_set(self):
        """Cover extract_symbols line 92."""
        e = JavaScriptExtractor()
        with patch('reveal.analyzers.imports.javascript.get_analyzer', return_value=None):
            result = e.extract_symbols(Path('fake.js'))
        assert result == set()

    def test_tree_none_returns_empty_set(self, tmp_path):
        """Cover extract_symbols lines 95-96."""
        f = _write_js(tmp_path, 'x.js', 'const x = 1;')
        mock_analyzer = MagicMock()
        mock_analyzer.tree = None
        mock_cls = MagicMock(return_value=mock_analyzer)
        e = JavaScriptExtractor()
        with patch('reveal.analyzers.imports.javascript.get_analyzer', return_value=mock_cls):
            result = e.extract_symbols(f)
        assert result == set()

    def test_exception_returns_empty_set(self):
        """Cover extract_symbols lines 98-99."""
        e = JavaScriptExtractor()
        with patch('reveal.analyzers.imports.javascript.get_analyzer', side_effect=RuntimeError('boom')):
            result = e.extract_symbols(Path('fake.js'))
        assert result == set()


# ─── extract_symbols real JS files ───────────────────────────────────────────

class TestExtractSymbols:
    def test_symbols_from_real_js(self, tmp_path):
        code = '''import React from 'react';
const Component = () => {
    return React.createElement('div', null);
};
'''
        f = _write_js(tmp_path, 'comp.jsx', code)
        e = JavaScriptExtractor()
        result = e.extract_symbols(f)
        assert isinstance(result, set)

    def test_returns_set_type(self, tmp_path):
        code = 'const x = 1;\n'
        f = _write_js(tmp_path, 'x.js', code)
        e = JavaScriptExtractor()
        result = e.extract_symbols(f)
        assert isinstance(result, set)


# ─── extract_imports real JS files ───────────────────────────────────────────

class TestExtractImportsRealJS:
    def test_es6_default_import(self, tmp_path):
        code = "import React from 'react';\n"
        f = _write_js(tmp_path, 'main.js', code)
        e = JavaScriptExtractor()
        result = e.extract_imports(f)
        assert len(result) >= 1
        modules = {r.module_name for r in result}
        assert 'react' in modules

    def test_es6_named_imports(self, tmp_path):
        code = "import { useState, useEffect } from 'react';\n"
        f = _write_js(tmp_path, 'main.js', code)
        e = JavaScriptExtractor()
        result = e.extract_imports(f)
        reacts = [r for r in result if r.module_name == 'react']
        assert len(reacts) == 1
        assert 'useState' in reacts[0].imported_names or reacts[0].import_type == 'es6_import'

    def test_es6_namespace_import(self, tmp_path):
        code = "import * as Utils from './utils';\n"
        f = _write_js(tmp_path, 'main.js', code)
        e = JavaScriptExtractor()
        result = e.extract_imports(f)
        ns_imports = [r for r in result if r.import_type == 'namespace_import']
        assert len(ns_imports) == 1
        assert ns_imports[0].is_relative is True

    def test_side_effect_import(self, tmp_path):
        code = "import './styles.css';\n"
        f = _write_js(tmp_path, 'main.js', code)
        e = JavaScriptExtractor()
        result = e.extract_imports(f)
        se_imports = [r for r in result if r.import_type == 'side_effect_import']
        assert len(se_imports) == 1

    def test_commonjs_require(self, tmp_path):
        code = "const fs = require('fs');\n"
        f = _write_js(tmp_path, 'main.js', code)
        e = JavaScriptExtractor()
        result = e.extract_imports(f)
        requires = [r for r in result if r.import_type == 'commonjs_require']
        assert len(requires) >= 1

    def test_no_imports(self, tmp_path):
        code = 'const x = 1;\nfunction foo() { return x; }\n'
        f = _write_js(tmp_path, 'x.js', code)
        e = JavaScriptExtractor()
        result = e.extract_imports(f)
        assert result == []

    def test_relative_import_is_relative(self, tmp_path):
        code = "import helper from './helper';\n"
        f = _write_js(tmp_path, 'main.js', code)
        e = JavaScriptExtractor()
        result = e.extract_imports(f)
        assert len(result) >= 1
        assert result[0].is_relative is True

    def test_typescript_file(self, tmp_path):
        code = "import { Component } from '@angular/core';\n"
        f = _write_js(tmp_path, 'app.ts', code)
        e = JavaScriptExtractor()
        result = e.extract_imports(f)
        assert len(result) >= 1


# ─── _parse_destructured_names ────────────────────────────────────────────────

class TestParseDestructuredNames:
    def test_simple_destructure(self):
        e = JavaScriptExtractor()
        result = e._parse_destructured_names('{ foo, bar }')
        assert 'foo' in result
        assert 'bar' in result

    def test_renamed_destructure(self):
        e = JavaScriptExtractor()
        result = e._parse_destructured_names('{ foo: bar }')
        assert 'foo' in result
        assert 'bar' not in result

    def test_single_name(self):
        e = JavaScriptExtractor()
        result = e._parse_destructured_names('{ foo }')
        assert result == ['foo']

    def test_empty_braces(self):
        e = JavaScriptExtractor()
        result = e._parse_destructured_names('{}')
        assert result == []


# ─── _extract_require_imported_names ─────────────────────────────────────────

class TestExtractRequireImportedNames:
    def test_no_parent_returns_empty(self):
        e = JavaScriptExtractor()
        node = MagicMock()
        node.parent = None
        analyzer = MagicMock()
        result = e._extract_require_imported_names(node, analyzer)
        assert result == []

    def test_parent_not_variable_declarator_returns_empty(self):
        e = JavaScriptExtractor()
        node = MagicMock()
        node.parent = MagicMock()
        node.parent.type = 'expression_statement'
        analyzer = MagicMock()
        result = e._extract_require_imported_names(node, analyzer)
        assert result == []

    def test_parent_no_children_returns_empty(self):
        e = JavaScriptExtractor()
        node = MagicMock()
        node.parent = MagicMock()
        node.parent.type = 'variable_declarator'
        node.parent.children = []
        analyzer = MagicMock()
        result = e._extract_require_imported_names(node, analyzer)
        assert result == []

    def test_destructured_const(self):
        e = JavaScriptExtractor()
        node = MagicMock()
        node.parent = MagicMock()
        node.parent.type = 'variable_declarator'
        child = MagicMock()
        node.parent.children = [child]
        analyzer = MagicMock()
        analyzer._get_node_text.return_value = '{ foo, bar }'
        result = e._extract_require_imported_names(node, analyzer)
        assert 'foo' in result
        assert 'bar' in result

    def test_single_name_const(self):
        e = JavaScriptExtractor()
        node = MagicMock()
        node.parent = MagicMock()
        node.parent.type = 'variable_declarator'
        child = MagicMock()
        node.parent.children = [child]
        analyzer = MagicMock()
        analyzer._get_node_text.return_value = 'fs'
        result = e._extract_require_imported_names(node, analyzer)
        assert result == ['fs']


# ─── _is_usage_context ───────────────────────────────────────────────────────

class TestIsUsageContext:
    def test_no_parent_returns_true(self):
        e = JavaScriptExtractor()
        node = MagicMock()
        node.parent = None
        assert e._is_usage_context(node) is True

    def test_inside_import_statement_returns_false(self):
        e = JavaScriptExtractor()
        node = MagicMock()
        inner = MagicMock()
        inner.type = 'something'
        import_anc = MagicMock()
        import_anc.type = 'import_statement'
        import_anc.parent = None
        inner.parent = import_anc
        node.parent = inner
        assert e._is_usage_context(node) is False

    def test_function_declaration_returns_false(self):
        e = JavaScriptExtractor()
        node = MagicMock()
        parent = MagicMock()
        parent.type = 'function_declaration'
        parent.parent = None
        node.parent = parent
        assert e._is_usage_context(node) is False

    def test_class_declaration_returns_false(self):
        e = JavaScriptExtractor()
        node = MagicMock()
        parent = MagicMock()
        parent.type = 'class_declaration'
        parent.parent = None
        node.parent = parent
        assert e._is_usage_context(node) is False

    def test_formal_parameters_returns_false(self):
        e = JavaScriptExtractor()
        node = MagicMock()
        parent = MagicMock()
        parent.type = 'formal_parameters'
        parent.parent = None
        node.parent = parent
        assert e._is_usage_context(node) is False

    def test_variable_declarator_first_child_returns_false(self):
        e = JavaScriptExtractor()
        node = MagicMock()
        parent = MagicMock()
        parent.type = 'variable_declarator'
        parent.parent = None
        parent.children = [node, MagicMock()]
        node.parent = parent
        assert e._is_usage_context(node) is False

    def test_variable_declarator_not_first_returns_true(self):
        e = JavaScriptExtractor()
        node = MagicMock()
        other = MagicMock()
        parent = MagicMock()
        parent.type = 'variable_declarator'
        parent.parent = None
        parent.children = [other, node]
        node.parent = parent
        assert e._is_usage_context(node) is True

    def test_pair_first_child_key_returns_false(self):
        e = JavaScriptExtractor()
        node = MagicMock()
        parent = MagicMock()
        parent.type = 'pair'
        parent.parent = None
        parent.children = [node]
        node.parent = parent
        assert e._is_usage_context(node) is False

    def test_import_specifier_returns_false(self):
        e = JavaScriptExtractor()
        node = MagicMock()
        parent = MagicMock()
        parent.type = 'import_specifier'
        parent.parent = None
        node.parent = parent
        assert e._is_usage_context(node) is False

    def test_namespace_import_returns_false(self):
        e = JavaScriptExtractor()
        node = MagicMock()
        parent = MagicMock()
        parent.type = 'namespace_import'
        parent.parent = None
        node.parent = parent
        assert e._is_usage_context(node) is False

    def test_call_expression_returns_true(self):
        e = JavaScriptExtractor()
        node = MagicMock()
        parent = MagicMock()
        parent.type = 'call_expression'
        parent.parent = None
        node.parent = parent
        assert e._is_usage_context(node) is True


# ─── _get_root_identifier ─────────────────────────────────────────────────────

class TestGetRootIdentifier:
    def test_simple_member_expr_returns_root(self):
        e = JavaScriptExtractor()
        analyzer = MagicMock()
        analyzer._get_node_text.return_value = 'React'

        ident = MagicMock()
        ident.type = 'identifier'

        member = MagicMock()
        member.type = 'member_expression'
        member.children = [ident]

        result = e._get_root_identifier(member, analyzer)
        assert result == 'React'

    def test_chained_member_expr(self):
        e = JavaScriptExtractor()
        analyzer = MagicMock()
        analyzer._get_node_text.return_value = 'foo'

        root = MagicMock()
        root.type = 'identifier'

        inner = MagicMock()
        inner.type = 'member_expression'
        inner.children = [root]

        outer = MagicMock()
        outer.type = 'member_expression'
        outer.children = [inner]

        result = e._get_root_identifier(outer, analyzer)
        assert result == 'foo'

    def test_non_identifier_root_returns_none(self):
        e = JavaScriptExtractor()
        analyzer = MagicMock()

        non_ident = MagicMock()
        non_ident.type = 'call_expression'

        member = MagicMock()
        member.type = 'member_expression'
        member.children = [non_ident]

        result = e._get_root_identifier(member, analyzer)
        assert result is None

    def test_empty_children_returns_none(self):
        e = JavaScriptExtractor()
        analyzer = MagicMock()

        member = MagicMock()
        member.type = 'member_expression'
        member.children = []

        result = e._get_root_identifier(member, analyzer)
        assert result is None

    def test_none_text_returns_none(self):
        e = JavaScriptExtractor()
        analyzer = MagicMock()
        analyzer._get_node_text.return_value = None

        ident = MagicMock()
        ident.type = 'identifier'

        member = MagicMock()
        member.type = 'member_expression'
        member.children = [ident]

        result = e._get_root_identifier(member, analyzer)
        assert result is None


# ─── resolve_import ───────────────────────────────────────────────────────────

class TestResolveImport:
    def _make_stmt(self, module_name: str, tmp_path: Path) -> ImportStatement:
        return ImportStatement(
            file_path=tmp_path / 'main.js',
            line_number=1,
            module_name=module_name,
            imported_names=[],
            is_relative=module_name.startswith('.'),
            import_type='es6_import',
        )

    def test_absolute_import_returns_none(self, tmp_path):
        e = JavaScriptExtractor()
        stmt = self._make_stmt('react', tmp_path)
        result = e.resolve_import(stmt, tmp_path)
        assert result is None

    def test_scoped_package_returns_none(self, tmp_path):
        e = JavaScriptExtractor()
        stmt = self._make_stmt('@angular/core', tmp_path)
        result = e.resolve_import(stmt, tmp_path)
        assert result is None

    def test_relative_resolves_js(self, tmp_path):
        utils = tmp_path / 'utils.js'
        utils.write_text('export const foo = 1;')
        e = JavaScriptExtractor()
        stmt = self._make_stmt('./utils', tmp_path)
        result = e.resolve_import(stmt, tmp_path)
        assert result == utils.resolve()

    def test_relative_resolves_ts(self, tmp_path):
        service = tmp_path / 'service.ts'
        service.write_text('export class Service {}')
        e = JavaScriptExtractor()
        stmt = self._make_stmt('./service', tmp_path)
        result = e.resolve_import(stmt, tmp_path)
        assert result == service.resolve()

    def test_relative_resolves_index_js(self, tmp_path):
        pkg_dir = tmp_path / 'components'
        pkg_dir.mkdir()
        index = pkg_dir / 'index.js'
        index.write_text('export * from "./Button";')
        e = JavaScriptExtractor()
        stmt = self._make_stmt('./components', tmp_path)
        result = e.resolve_import(stmt, tmp_path)
        assert result == index.resolve()

    def test_relative_not_found_returns_none(self, tmp_path):
        e = JavaScriptExtractor()
        stmt = self._make_stmt('./nonexistent', tmp_path)
        result = e.resolve_import(stmt, tmp_path)
        assert result is None


# ─── _resolve_relative_js ────────────────────────────────────────────────────

class TestResolveRelativeJs:
    def test_exact_path_with_extension(self, tmp_path):
        f = tmp_path / 'utils.js'
        f.write_text('export const x = 1;')
        e = JavaScriptExtractor()
        result = e._resolve_relative_js('./utils.js', tmp_path)
        assert result == f.resolve()

    def test_exact_path_not_found_returns_none(self, tmp_path):
        e = JavaScriptExtractor()
        result = e._resolve_relative_js('./missing.js', tmp_path)
        assert result is None

    def test_resolves_jsx(self, tmp_path):
        f = tmp_path / 'Button.jsx'
        f.write_text('export const Button = () => {};')
        e = JavaScriptExtractor()
        result = e._resolve_relative_js('./Button', tmp_path)
        assert result == f.resolve()

    def test_resolves_tsx(self, tmp_path):
        f = tmp_path / 'App.tsx'
        f.write_text('export const App = () => <div />;')
        e = JavaScriptExtractor()
        result = e._resolve_relative_js('./App', tmp_path)
        assert result == f.resolve()

    def test_resolves_mjs(self, tmp_path):
        f = tmp_path / 'module.mjs'
        f.write_text('export const x = 1;')
        e = JavaScriptExtractor()
        result = e._resolve_relative_js('./module', tmp_path)
        assert result == f.resolve()

    def test_resolves_index_ts(self, tmp_path):
        pkg = tmp_path / 'auth'
        pkg.mkdir()
        idx = pkg / 'index.ts'
        idx.write_text('export * from "./service";')
        e = JavaScriptExtractor()
        result = e._resolve_relative_js('./auth', tmp_path)
        assert result == idx.resolve()

    def test_no_match_returns_none(self, tmp_path):
        e = JavaScriptExtractor()
        result = e._resolve_relative_js('./nope', tmp_path)
        assert result is None
