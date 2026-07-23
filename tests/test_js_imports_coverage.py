"""Coverage tests for reveal/analyzers/imports/javascript.py.

Targets: 51, 55-59, 89-122, 138, 212, 262, 289, 303, 306, 350, 372-406,
         417-430, 451-458, 474-497
Current coverage: 62% → target: 85%+
"""

import json

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from reveal.analyzers.imports.javascript import JavaScriptExtractor
from reveal.analyzers.imports.types import ImportStatement


def _mock_ts_node(kind='', children=None, parent_result=None, start_byte=0):
    """Create a mock tree-sitter 1.x compatible node."""
    m = MagicMock()
    m.kind.return_value = kind
    children = children or []
    m.child_count.return_value = len(children)
    m.child.side_effect = lambda i: children[i] if 0 <= i < len(children) else None
    m.parent.return_value = parent_result
    m.start_byte.return_value = start_byte
    return m


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


# ─── ES module re-exports (barrels) — BACK-548 ───────────────────────────────

class TestReExports:
    def test_star_reexport_is_import_edge(self, tmp_path):
        code = "export * from './target';\n"
        f = _write_js(tmp_path, 'index.ts', code)
        result = JavaScriptExtractor().extract_imports(f)
        re = [r for r in result if r.import_type == 're_export']
        assert len(re) == 1
        assert re[0].module_name == './target'
        assert re[0].imported_names == ['*']
        assert re[0].is_relative is True

    def test_named_reexport_captures_source_names(self, tmp_path):
        code = "export { Foo, Bar } from './foo';\n"
        f = _write_js(tmp_path, 'index.ts', code)
        result = JavaScriptExtractor().extract_imports(f)
        re = [r for r in result if r.import_type == 're_export']
        assert len(re) == 1
        assert set(re[0].imported_names) == {'Foo', 'Bar'}

    def test_aliased_reexport_uses_source_name(self, tmp_path):
        # `Baz as Qux` — the name pulled FROM the module is Baz, not the alias.
        code = "export { Baz as Qux } from './baz';\n"
        f = _write_js(tmp_path, 'index.ts', code)
        result = JavaScriptExtractor().extract_imports(f)
        re = [r for r in result if r.import_type == 're_export']
        assert len(re) == 1
        assert re[0].imported_names == ['Baz']

    def test_namespace_reexport_is_import_edge(self, tmp_path):
        code = "export * as ns from './ns';\n"
        f = _write_js(tmp_path, 'index.ts', code)
        result = JavaScriptExtractor().extract_imports(f)
        re = [r for r in result if r.import_type == 're_export']
        assert len(re) == 1
        assert re[0].module_name == './ns'

    def test_local_export_is_not_an_import(self, tmp_path):
        # `export const` / `export function` have no source module — not an edge.
        code = "export const x = 1;\nexport function f() { return 2; }\n"
        f = _write_js(tmp_path, 'index.ts', code)
        result = JavaScriptExtractor().extract_imports(f)
        assert [r for r in result if r.import_type == 're_export'] == []

    def test_reexport_skips_unused_detection(self, tmp_path):
        # A re-export IS the usage (public API) — must not be flagged unused.
        code = "export * from './target';\n"
        f = _write_js(tmp_path, 'index.ts', code)
        result = JavaScriptExtractor().extract_imports(f)
        re = [r for r in result if r.import_type == 're_export']
        assert re[0].skip_unused is True


# ─── is_intra_project_import classification (honest-decline, BACK-547) ────────

class TestIsIntraProjectImport:
    def _stmt(self, module_name):
        return ImportStatement(
            file_path=Path('/p/a.ts'), line_number=1, module_name=module_name,
            imported_names=[], is_relative=module_name.startswith('.'),
            import_type='es6_import')

    def test_relative_is_intra_project(self):
        e = JavaScriptExtractor()
        assert e.is_intra_project_import(self._stmt('./util'), Path('/p')) is True
        assert e.is_intra_project_import(self._stmt('../lib/x'), Path('/p')) is True

    def test_bare_specifier_is_external(self):
        e = JavaScriptExtractor()
        assert e.is_intra_project_import(self._stmt('react'), Path('/p')) is False
        assert e.is_intra_project_import(self._stmt('@angular/core'), Path('/p')) is False


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
        node = _mock_ts_node(parent_result=None)
        analyzer = MagicMock()
        result = e._extract_require_imported_names(node, analyzer)
        assert result == []

    def test_parent_not_variable_declarator_returns_empty(self):
        e = JavaScriptExtractor()
        parent = _mock_ts_node(kind='expression_statement')
        node = _mock_ts_node(parent_result=parent)
        analyzer = MagicMock()
        result = e._extract_require_imported_names(node, analyzer)
        assert result == []

    def test_parent_no_children_returns_empty(self):
        e = JavaScriptExtractor()
        parent = _mock_ts_node(kind='variable_declarator', children=[])
        node = _mock_ts_node(parent_result=parent)
        analyzer = MagicMock()
        result = e._extract_require_imported_names(node, analyzer)
        assert result == []

    def test_destructured_const(self):
        e = JavaScriptExtractor()
        child = _mock_ts_node()
        parent = _mock_ts_node(kind='variable_declarator', children=[child])
        node = _mock_ts_node(parent_result=parent)
        analyzer = MagicMock()
        analyzer._get_node_text.return_value = '{ foo, bar }'
        result = e._extract_require_imported_names(node, analyzer)
        assert 'foo' in result
        assert 'bar' in result

    def test_single_name_const(self):
        e = JavaScriptExtractor()
        child = _mock_ts_node()
        parent = _mock_ts_node(kind='variable_declarator', children=[child])
        node = _mock_ts_node(parent_result=parent)
        analyzer = MagicMock()
        analyzer._get_node_text.return_value = 'fs'
        result = e._extract_require_imported_names(node, analyzer)
        assert result == ['fs']


# ─── _is_usage_context ───────────────────────────────────────────────────────

class TestIsUsageContext:
    def test_no_parent_returns_true(self):
        e = JavaScriptExtractor()
        node = _mock_ts_node(parent_result=None)
        assert e._is_usage_context(node) is True

    def test_default_import_binding_returns_false(self):
        # `import Foo from 'x'` — Foo's direct parent is import_clause in the
        # real tree-sitter-javascript grammar (verified against real parses;
        # BACK-489 perf fix — no deeper ancestor walk needed).
        e = JavaScriptExtractor()
        parent = _mock_ts_node(kind='import_clause', parent_result=None)
        node = _mock_ts_node(parent_result=parent)
        assert e._is_usage_context(node) is False

    def test_function_declaration_returns_false(self):
        e = JavaScriptExtractor()
        parent = _mock_ts_node(kind='function_declaration', parent_result=None)
        node = _mock_ts_node(parent_result=parent)
        assert e._is_usage_context(node) is False

    def test_class_declaration_returns_false(self):
        e = JavaScriptExtractor()
        parent = _mock_ts_node(kind='class_declaration', parent_result=None)
        node = _mock_ts_node(parent_result=parent)
        assert e._is_usage_context(node) is False

    def test_formal_parameters_returns_false(self):
        e = JavaScriptExtractor()
        parent = _mock_ts_node(kind='formal_parameters', parent_result=None)
        node = _mock_ts_node(parent_result=parent)
        assert e._is_usage_context(node) is False

    def test_variable_declarator_first_child_returns_false(self):
        e = JavaScriptExtractor()
        node_sb = 42
        first_child = _mock_ts_node(start_byte=node_sb)
        other = _mock_ts_node(start_byte=99)
        parent = _mock_ts_node(kind='variable_declarator', children=[first_child, other], parent_result=None)
        node = _mock_ts_node(parent_result=parent, start_byte=node_sb)
        assert e._is_usage_context(node) is False

    def test_variable_declarator_not_first_returns_true(self):
        e = JavaScriptExtractor()
        node_sb = 42
        first_child = _mock_ts_node(start_byte=10)
        other = _mock_ts_node(start_byte=node_sb)
        parent = _mock_ts_node(kind='variable_declarator', children=[first_child, other], parent_result=None)
        node = _mock_ts_node(parent_result=parent, start_byte=node_sb)
        assert e._is_usage_context(node) is True

    def test_pair_first_child_key_returns_false(self):
        e = JavaScriptExtractor()
        node_sb = 42
        first_child = _mock_ts_node(start_byte=node_sb)
        parent = _mock_ts_node(kind='pair', children=[first_child], parent_result=None)
        node = _mock_ts_node(parent_result=parent, start_byte=node_sb)
        assert e._is_usage_context(node) is False

    def test_import_specifier_returns_false(self):
        e = JavaScriptExtractor()
        parent = _mock_ts_node(kind='import_specifier', parent_result=None)
        node = _mock_ts_node(parent_result=parent)
        assert e._is_usage_context(node) is False

    def test_namespace_import_returns_false(self):
        e = JavaScriptExtractor()
        parent = _mock_ts_node(kind='namespace_import', parent_result=None)
        node = _mock_ts_node(parent_result=parent)
        assert e._is_usage_context(node) is False

    def test_call_expression_returns_true(self):
        e = JavaScriptExtractor()
        parent = _mock_ts_node(kind='call_expression', parent_result=None)
        node = _mock_ts_node(parent_result=parent)
        assert e._is_usage_context(node) is True


# ─── _get_root_identifier ─────────────────────────────────────────────────────

class TestGetRootIdentifier:
    def test_simple_member_expr_returns_root(self):
        e = JavaScriptExtractor()
        analyzer = MagicMock()
        analyzer._get_node_text.return_value = 'React'

        ident = _mock_ts_node(kind='identifier')
        member = _mock_ts_node(kind='member_expression', children=[ident])

        result = e._get_root_identifier(member, analyzer)
        assert result == 'React'

    def test_chained_member_expr(self):
        e = JavaScriptExtractor()
        analyzer = MagicMock()
        analyzer._get_node_text.return_value = 'foo'

        root = _mock_ts_node(kind='identifier')
        inner = _mock_ts_node(kind='member_expression', children=[root])
        outer = _mock_ts_node(kind='member_expression', children=[inner])

        result = e._get_root_identifier(outer, analyzer)
        assert result == 'foo'

    def test_non_identifier_root_returns_none(self):
        e = JavaScriptExtractor()
        analyzer = MagicMock()

        non_ident = _mock_ts_node(kind='call_expression')
        member = _mock_ts_node(kind='member_expression', children=[non_ident])

        result = e._get_root_identifier(member, analyzer)
        assert result is None

    def test_empty_children_returns_none(self):
        e = JavaScriptExtractor()
        analyzer = MagicMock()

        member = _mock_ts_node(kind='member_expression', children=[])

        result = e._get_root_identifier(member, analyzer)
        assert result is None

    def test_none_text_returns_none(self):
        e = JavaScriptExtractor()
        analyzer = MagicMock()
        analyzer._get_node_text.return_value = None

        ident = _mock_ts_node(kind='identifier')
        member = _mock_ts_node(kind='member_expression', children=[ident])

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

    def test_parent_relative_resolves_one_level_up(self, tmp_path):
        """BACK-549: '../foo' must navigate up, not collapse to 'foo'."""
        sibling_dir = tmp_path / 'a'
        sibling_dir.mkdir()
        target = tmp_path / 'shared.js'
        target.write_text('export const x = 1;')
        e = JavaScriptExtractor()
        stmt = self._make_stmt('../shared', sibling_dir)
        result = e.resolve_import(stmt, sibling_dir)
        assert result == target.resolve()

    def test_parent_relative_resolves_two_levels_up(self, tmp_path):
        """BACK-549: '../../foo' (the dominant idiom in deep trees like
        VS Code's src/vs/...) must navigate up two levels, not collapse."""
        nested_dir = tmp_path / 'a' / 'b'
        nested_dir.mkdir(parents=True)
        target = tmp_path / 'nls.js'
        target.write_text('export const x = 1;')
        e = JavaScriptExtractor()
        stmt = self._make_stmt('../../nls', nested_dir)
        result = e.resolve_import(stmt, nested_dir)
        assert result == target.resolve()

    def test_bare_dot_resolves_own_directory_index(self, tmp_path):
        """BACK-556: `import { x } from '.'` (bare current-directory barrel,
        no path segment at all) must resolve to this directory's index.ts —
        same idiom as './dir', just with an empty dir name. Real example:
        VS Code copilot extension's codeReferencing/citationManager.ts
        imports its own barrel via `from '.'`."""
        pkg_dir = tmp_path / 'pkg'
        pkg_dir.mkdir()
        index = pkg_dir / 'index.ts'
        index.write_text('export const x = 1;')
        sibling = pkg_dir / 'citationManager.ts'
        sibling.write_text('// importer')
        e = JavaScriptExtractor()
        stmt = self._make_stmt('.', pkg_dir)
        result = e.resolve_import(stmt, pkg_dir)
        assert result == index.resolve()

    def test_bare_dotdot_resolves_parent_directory_index(self, tmp_path):
        """BACK-556: `import { x } from '..'` (bare parent-directory barrel)
        must resolve to the parent directory's index.ts. Real example: VS
        Code notebook-renderers extension's test/notebookRenderer.test.ts
        imports `{ activate } from '..'`."""
        pkg_dir = tmp_path / 'pkg'
        pkg_dir.mkdir()
        index = pkg_dir / 'index.ts'
        index.write_text('export const activate = () => {};')
        test_dir = pkg_dir / 'test'
        test_dir.mkdir()
        e = JavaScriptExtractor()
        stmt = self._make_stmt('..', test_dir)
        result = e.resolve_import(stmt, test_dir)
        assert result == index.resolve()


# ─── tsconfig paths/baseUrl alias resolution (BACK-694) ───────────────────────

class TestTsconfigPathsResolution:
    """A bare specifier (`@utils/helper`) is a plain npm dependency UNLESS
    it matches a tsconfig.json `compilerOptions.paths` alias, in which case
    it's intra-project by the project's own configuration -- even when the
    aliased target doesn't actually exist on disk (honest-decline: a real
    miss, not a silent external classification)."""

    def _stmt(self, module_name: str, base_path: Path) -> ImportStatement:
        return ImportStatement(
            file_path=base_path / 'main.ts', line_number=1, module_name=module_name,
            imported_names=[], is_relative=module_name.startswith('.'),
            import_type='es6_import')

    def _write_tsconfig(self, root: Path, paths: dict, base_url: str = '.') -> None:
        root.mkdir(parents=True, exist_ok=True)
        (root / 'tsconfig.json').write_text(
            '{\n  "compilerOptions": {\n'
            f'    "baseUrl": "{base_url}",\n'
            f'    "paths": {json.dumps(paths)}\n'
            '  }\n}\n')

    def test_alias_resolves_to_real_file(self, tmp_path):
        """Positive: '@utils/helper' -> src/utils/helper.ts via paths alias."""
        self._write_tsconfig(tmp_path, {'@utils/*': ['src/utils/*']})
        target = tmp_path / 'src' / 'utils' / 'helper.ts'
        target.parent.mkdir(parents=True)
        target.write_text('export const helper = 1;')
        src_dir = tmp_path / 'src'

        e = JavaScriptExtractor()
        stmt = self._stmt('@utils/helper', src_dir)
        assert e.resolve_import(stmt, src_dir, search_paths=[tmp_path]) == target.resolve()
        assert e.is_intra_project_import(stmt, src_dir, search_paths=[tmp_path]) is True

    def test_alias_matches_but_target_missing_is_honest_decline(self, tmp_path):
        """A specifier matching a paths alias whose target file doesn't
        exist must still count as intra-project (a real miss) rather than
        being silently classified external -- the exact safety net BACK-694
        found broken."""
        self._write_tsconfig(tmp_path, {'@utils/*': ['src/utils/*']})
        src_dir = tmp_path / 'src'
        src_dir.mkdir(parents=True)

        e = JavaScriptExtractor()
        stmt = self._stmt('@utils/gone', src_dir)
        assert e.resolve_import(stmt, src_dir, search_paths=[tmp_path]) is None
        assert e.is_intra_project_import(stmt, src_dir, search_paths=[tmp_path]) is True

    def test_genuine_npm_import_unaffected_by_tsconfig(self, tmp_path):
        """Negative: a real npm dependency with no matching alias is still
        correctly classified external, even with a tsconfig.json present."""
        self._write_tsconfig(tmp_path, {'@utils/*': ['src/utils/*']})
        src_dir = tmp_path / 'src'
        src_dir.mkdir(parents=True)

        e = JavaScriptExtractor()
        stmt = self._stmt('react', src_dir)
        assert e.resolve_import(stmt, src_dir, search_paths=[tmp_path]) is None
        assert e.is_intra_project_import(stmt, src_dir, search_paths=[tmp_path]) is False

    def test_longest_wildcard_prefix_wins(self, tmp_path):
        """tsc resolution order: among overlapping wildcard keys, the
        longest matching prefix wins ('@app/utils/*' over '@app/*')."""
        self._write_tsconfig(tmp_path, {
            '@app/*': ['src/generic/*'],
            '@app/utils/*': ['src/utils/*'],
        })
        specific = tmp_path / 'src' / 'utils' / 'helper.ts'
        specific.parent.mkdir(parents=True)
        specific.write_text('export const helper = 1;')
        generic = tmp_path / 'src' / 'generic' / 'utils' / 'helper.ts'
        generic.parent.mkdir(parents=True)
        generic.write_text('export const helper = 2;')
        src_dir = tmp_path / 'src'

        e = JavaScriptExtractor()
        stmt = self._stmt('@app/utils/helper', src_dir)
        assert e.resolve_import(stmt, src_dir, search_paths=[tmp_path]) == specific.resolve()

    def test_tsconfig_search_bounded_by_search_paths(self, tmp_path):
        """_find_tsconfig must not climb above search_paths[0] (the scan
        root) -- an unrelated tsconfig.json in an enclosing directory
        outside the scanned project must not apply."""
        outer = tmp_path / 'outer'
        scan_root = outer / 'project'
        src_dir = scan_root / 'src'
        self._write_tsconfig(outer, {'@utils/*': ['unrelated/*']})
        src_dir.mkdir(parents=True)

        e = JavaScriptExtractor()
        stmt = self._stmt('@utils/helper', src_dir)
        # No tsconfig.json inside scan_root itself -> alias map must not be
        # found by climbing past scan_root into outer/.
        assert e.resolve_import(stmt, src_dir, search_paths=[scan_root]) is None
        assert e.is_intra_project_import(stmt, src_dir, search_paths=[scan_root]) is False


# ─── tsconfig `extends` chain resolution (BACK-705) ────────────────────────
#
# A project whose paths/baseUrl live in a shared base config (a common
# monorepo pattern -- "extends": "./tsconfig.base.json") was previously
# treated as declaring none at all: _get_tsconfig_aliases only ever read
# the ONE file it was pointed at, never chasing `extends`. Found on the
# `nest` second-corpus overfit-guard measurement (BACK-669 note #10):
# residual gap after BACK-694/BACK-698, 81.21% recall.

class TestTsconfigExtendsChain:

    def _stmt(self, module_name: str, base_path: Path) -> ImportStatement:
        return ImportStatement(
            file_path=base_path / 'main.ts', line_number=1, module_name=module_name,
            imported_names=[], is_relative=module_name.startswith('.'),
            import_type='es6_import')

    def test_paths_inherited_from_extended_base_config(self, tmp_path):
        """Leaf tsconfig.json declares no paths/baseUrl of its own -- both
        must be inherited from the base config it extends."""
        (tmp_path / 'tsconfig.base.json').write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@app/*": ["src/*"]}}}')
        (tmp_path / 'tsconfig.json').write_text(
            '{"extends": "./tsconfig.base.json", "compilerOptions": {"target": "es2020"}}')
        target = tmp_path / 'src' / 'util.ts'
        target.parent.mkdir(parents=True)
        target.write_text('export const helper = 1;')
        src_dir = tmp_path / 'src'

        e = JavaScriptExtractor()
        stmt = self._stmt('@app/util', src_dir)
        assert e.resolve_import(stmt, src_dir, search_paths=[tmp_path]) == target.resolve()
        assert e.is_intra_project_import(stmt, src_dir, search_paths=[tmp_path]) is True

    def test_extends_without_json_suffix_resolves(self, tmp_path):
        """TS convention: an extends entry with no .json suffix gets one
        appended ("./tsconfig.base" -> tsconfig.base.json)."""
        (tmp_path / 'tsconfig.base.json').write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@app/*": ["src/*"]}}}')
        (tmp_path / 'tsconfig.json').write_text('{"extends": "./tsconfig.base"}')
        target = tmp_path / 'src' / 'util.ts'
        target.parent.mkdir(parents=True)
        target.write_text('export const helper = 1;')
        src_dir = tmp_path / 'src'

        e = JavaScriptExtractor()
        stmt = self._stmt('@app/util', src_dir)
        assert e.resolve_import(stmt, src_dir, search_paths=[tmp_path]) == target.resolve()

    def test_leaf_paths_override_base_entirely(self, tmp_path):
        """A leaf config's OWN paths REPLACE the base's outright (TS's own
        per-key override semantics), rather than merging with it."""
        (tmp_path / 'tsconfig.base.json').write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@base/*": ["base_src/*"]}}}')
        (tmp_path / 'tsconfig.json').write_text(
            '{"extends": "./tsconfig.base.json", '
            '"compilerOptions": {"baseUrl": ".", "paths": {"@app/*": ["src/*"]}}}')
        src_dir = tmp_path / 'src'
        src_dir.mkdir(parents=True)

        e = JavaScriptExtractor()
        # The base-only alias must NOT be visible once the leaf declares its own.
        base_stmt = self._stmt('@base/x', src_dir)
        assert e.is_intra_project_import(base_stmt, src_dir, search_paths=[tmp_path]) is False

    def test_multi_level_extends_chain(self, tmp_path):
        """Leaf -> mid -> root, three files deep; paths live on the root."""
        (tmp_path / 'tsconfig.root.json').write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@app/*": ["src/*"]}}}')
        (tmp_path / 'tsconfig.mid.json').write_text(
            '{"extends": "./tsconfig.root.json"}')
        (tmp_path / 'tsconfig.json').write_text(
            '{"extends": "./tsconfig.mid.json"}')
        target = tmp_path / 'src' / 'util.ts'
        target.parent.mkdir(parents=True)
        target.write_text('export const helper = 1;')
        src_dir = tmp_path / 'src'

        e = JavaScriptExtractor()
        stmt = self._stmt('@app/util', src_dir)
        assert e.resolve_import(stmt, src_dir, search_paths=[tmp_path]) == target.resolve()

    def test_extends_cycle_does_not_hang(self, tmp_path):
        """Two configs extending each other must not infinite-loop."""
        (tmp_path / 'a.json').write_text('{"extends": "./b.json"}')
        (tmp_path / 'b.json').write_text('{"extends": "./a.json"}')
        (tmp_path / 'tsconfig.json').write_text('{"extends": "./a.json"}')
        src_dir = tmp_path / 'src'
        src_dir.mkdir(parents=True)

        e = JavaScriptExtractor()
        stmt = self._stmt('@app/util', src_dir)
        # No paths declared anywhere in the cycle -- must decline cleanly,
        # not hang or raise.
        assert e.is_intra_project_import(stmt, src_dir, search_paths=[tmp_path]) is False

    def test_package_name_extends_is_ignored_not_crashed(self, tmp_path):
        """A node_modules package-name extends (no node_modules resolution
        in reveal's buildless design) must be skipped cleanly, not crash --
        the leaf config's own paths (if any) still apply."""
        (tmp_path / 'tsconfig.json').write_text(
            '{"extends": "@tsconfig/node18/tsconfig.json", '
            '"compilerOptions": {"baseUrl": ".", "paths": {"@app/*": ["src/*"]}}}')
        target = tmp_path / 'src' / 'util.ts'
        target.parent.mkdir(parents=True)
        target.write_text('export const helper = 1;')
        src_dir = tmp_path / 'src'

        e = JavaScriptExtractor()
        stmt = self._stmt('@app/util', src_dir)
        assert e.resolve_import(stmt, src_dir, search_paths=[tmp_path]) == target.resolve()


# ─── tsconfig project `references` fallback (BACK-773) ─────────────────────
#
# TS project `references` is a DIFFERENT linkage than `extends`: it declares
# a build-ordering dependency, not config inheritance. Real monorepos (Nest)
# exploit it anyway -- a dev-facing tsconfig.json with no paths/baseUrl of
# its own `references` a sibling tsconfig.build.json that holds the real
# path map, and tsc/ts-node resolve through it in practice. Found on the
# `nest` corpus re-measurement after BACK-772 shipped: recall stayed flat at
# 81.21% because BACK-772's exports-map fix and this gap are independent --
# neither one masks the other. Root cause: `_find_tsconfig` only ever
# discovers a file literally named tsconfig.json, and `_get_tsconfig_aliases`
# only ever chased `extends`, so a `references`-only sibling's paths were
# invisible outright.

class TestTsconfigReferences:

    def _stmt(self, module_name: str, base_path: Path) -> ImportStatement:
        return ImportStatement(
            file_path=base_path / 'main.ts', line_number=1, module_name=module_name,
            imported_names=[], is_relative=module_name.startswith('.'),
            import_type='es6_import')

    def test_paths_found_via_sibling_referenced_build_config(self, tmp_path):
        """tsconfig.json has no paths of its own and does not `extends` the
        config that has them -- it only `references` it (Nest's own
        pattern: tsconfig.json -> tsconfig.build.json). paths/baseUrl must
        still be found."""
        (tmp_path / 'tsconfig.json').write_text(
            '{"references": [{"path": "./tsconfig.build.json"}]}')
        (tmp_path / 'tsconfig.build.json').write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@app/*": ["src/*"]}}}')
        target = tmp_path / 'src' / 'util.ts'
        target.parent.mkdir(parents=True)
        target.write_text('export const helper = 1;')
        src_dir = tmp_path / 'src'

        e = JavaScriptExtractor()
        stmt = self._stmt('@app/util', src_dir)
        assert e.resolve_import(stmt, src_dir, search_paths=[tmp_path]) == target.resolve()
        assert e.is_intra_project_import(stmt, src_dir, search_paths=[tmp_path]) is True

    def test_extends_chain_paths_win_over_references(self, tmp_path):
        """If the `extends` chain already supplies paths, `references` is
        never even consulted -- extends stays the primary, higher-priority
        path."""
        (tmp_path / 'tsconfig.base.json').write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@app/*": ["src/*"]}}}')
        (tmp_path / 'tsconfig.json').write_text(
            '{"extends": "./tsconfig.base.json", '
            '"references": [{"path": "./tsconfig.build.json"}]}')
        (tmp_path / 'tsconfig.build.json').write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@other/*": ["lib/*"]}}}')
        target = tmp_path / 'src' / 'util.ts'
        target.parent.mkdir(parents=True)
        target.write_text('export const helper = 1;')
        src_dir = tmp_path / 'src'

        e = JavaScriptExtractor()
        assert e.resolve_import(self._stmt('@app/util', src_dir), src_dir,
                                 search_paths=[tmp_path]) == target.resolve()
        # The references-only sibling's alias must not leak through.
        assert e.is_intra_project_import(self._stmt('@other/x', src_dir), src_dir,
                                          search_paths=[tmp_path]) is False

    def test_references_entry_naming_a_directory_resolves_its_tsconfig(self, tmp_path):
        """A `references[].path` may name a directory (implying its
        tsconfig.json inside), not just a file directly."""
        (tmp_path / 'tsconfig.json').write_text(
            '{"references": [{"path": "./build"}]}')
        build_dir = tmp_path / 'build'
        build_dir.mkdir()
        (build_dir / 'tsconfig.json').write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@app/*": ["../src/*"]}}}')
        target = tmp_path / 'src' / 'util.ts'
        target.parent.mkdir(parents=True)
        target.write_text('export const helper = 1;')
        src_dir = tmp_path / 'src'

        e = JavaScriptExtractor()
        stmt = self._stmt('@app/util', src_dir)
        assert e.resolve_import(stmt, src_dir, search_paths=[tmp_path]) == target.resolve()

    def test_multiple_references_first_with_paths_wins(self, tmp_path):
        """Several references entries -- the first one (in declared order)
        that actually supplies paths wins, matching the extends chain's own
        first-match-wins semantics."""
        (tmp_path / 'tsconfig.json').write_text(
            '{"references": [{"path": "./empty.json"}, {"path": "./tsconfig.build.json"}]}')
        (tmp_path / 'empty.json').write_text('{"compilerOptions": {"target": "es2020"}}')
        (tmp_path / 'tsconfig.build.json').write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@app/*": ["src/*"]}}}')
        target = tmp_path / 'src' / 'util.ts'
        target.parent.mkdir(parents=True)
        target.write_text('export const helper = 1;')
        src_dir = tmp_path / 'src'

        e = JavaScriptExtractor()
        stmt = self._stmt('@app/util', src_dir)
        assert e.resolve_import(stmt, src_dir, search_paths=[tmp_path]) == target.resolve()

    def test_references_cycle_does_not_hang(self, tmp_path):
        """A references entry pointing back at the referring config (or a
        cycle among references) must not infinite-loop."""
        (tmp_path / 'tsconfig.json').write_text(
            '{"references": [{"path": "./a.json"}]}')
        (tmp_path / 'a.json').write_text('{"references": [{"path": "./tsconfig.json"}]}')
        src_dir = tmp_path / 'src'
        src_dir.mkdir(parents=True)

        e = JavaScriptExtractor()
        stmt = self._stmt('@app/util', src_dir)
        assert e.is_intra_project_import(stmt, src_dir, search_paths=[tmp_path]) is False

    def test_no_references_and_no_extends_paths_declines_cleanly(self, tmp_path):
        """No paths anywhere (no extends, no references, no own paths) --
        must decline cleanly rather than crash or hang."""
        (tmp_path / 'tsconfig.json').write_text('{"compilerOptions": {"target": "es2020"}}')
        src_dir = tmp_path / 'src'
        src_dir.mkdir(parents=True)

        e = JavaScriptExtractor()
        stmt = self._stmt('@app/util', src_dir)
        assert e.is_intra_project_import(stmt, src_dir, search_paths=[tmp_path]) is False


# ─── package.json exports-map resolution (BACK-772) ────────────────────────
#
# The other real way a monorepo cross-package import resolves with no
# node_modules installed: a workspace member's own package.json `exports`
# map, independent of the consumer's tsconfig `paths` (BACK-694/705). Filed
# as the residual gap left after the `nest` corpus's tsconfig-extends fix
# (BACK-705, 81.21% recall).

class TestWorkspaceExportsMap:

    def _stmt(self, module_name: str, base_path: Path, import_type: str = 'es6_import') -> ImportStatement:
        return ImportStatement(
            file_path=base_path / 'main.ts', line_number=1, module_name=module_name,
            imported_names=[], is_relative=module_name.startswith('.'),
            import_type=import_type)

    def _write_workspace(self, root: Path, exports: dict, globs=None) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        (root / 'package.json').write_text(json.dumps(
            {'name': 'monorepo-root', 'private': True, 'workspaces': globs or ['packages/*']}))
        pkg_dir = root / 'packages' / 'utils'
        pkg_dir.mkdir(parents=True)
        (pkg_dir / 'package.json').write_text(json.dumps({'name': '@myorg/utils', 'exports': exports}))
        return pkg_dir

    def test_subpath_export_resolves_to_real_file(self, tmp_path):
        pkg_dir = self._write_workspace(tmp_path, {'./helpers': './dist/helpers.js'})
        (pkg_dir / 'dist').mkdir()
        target = pkg_dir / 'dist' / 'helpers.js'
        target.write_text('export function helper() {}')
        base = tmp_path / 'apps' / 'web'
        base.mkdir(parents=True)

        e = JavaScriptExtractor()
        stmt = self._stmt('@myorg/utils/helpers', base)
        assert e.resolve_import(stmt, base, search_paths=[tmp_path]) == target.resolve()
        assert e.is_intra_project_import(stmt, base, search_paths=[tmp_path]) is True

    def test_root_export_bare_package_specifier(self, tmp_path):
        pkg_dir = self._write_workspace(tmp_path, {'.': './dist/index.js'})
        (pkg_dir / 'dist').mkdir()
        target = pkg_dir / 'dist' / 'index.js'
        target.write_text('export default {};')
        base = tmp_path / 'apps' / 'web'
        base.mkdir(parents=True)

        e = JavaScriptExtractor()
        stmt = self._stmt('@myorg/utils', base)
        assert e.resolve_import(stmt, base, search_paths=[tmp_path]) == target.resolve()

    def test_wildcard_subpath_export(self, tmp_path):
        pkg_dir = self._write_workspace(tmp_path, {'./features/*': './dist/features/*.js'})
        (pkg_dir / 'dist' / 'features').mkdir(parents=True)
        target = pkg_dir / 'dist' / 'features' / 'foo.js'
        target.write_text('export function foo() {}')
        base = tmp_path / 'apps' / 'web'
        base.mkdir(parents=True)

        e = JavaScriptExtractor()
        stmt = self._stmt('@myorg/utils/features/foo', base)
        assert e.resolve_import(stmt, base, search_paths=[tmp_path]) == target.resolve()

    def test_conditional_export_prefers_require_for_commonjs_require(self, tmp_path):
        pkg_dir = self._write_workspace(tmp_path, {
            '.': {'require': './dist/index.cjs', 'import': './dist/index.mjs', 'default': './dist/index.js'},
        })
        (pkg_dir / 'dist').mkdir()
        cjs = pkg_dir / 'dist' / 'index.cjs'
        cjs.write_text('module.exports = {};')
        mjs = pkg_dir / 'dist' / 'index.mjs'
        mjs.write_text('export default {};')
        base = tmp_path / 'apps' / 'web'
        base.mkdir(parents=True)

        e = JavaScriptExtractor()
        require_stmt = self._stmt('@myorg/utils', base, import_type='commonjs_require')
        import_stmt = self._stmt('@myorg/utils', base, import_type='es6_import')
        assert e.resolve_import(require_stmt, base, search_paths=[tmp_path]) == cjs.resolve()
        assert e.resolve_import(import_stmt, base, search_paths=[tmp_path]) == mjs.resolve()

    def test_negated_workspace_glob_excludes_package(self, tmp_path):
        """Real npm/pnpm workspace syntax: a `!`-prefixed glob entry excludes
        matching directories from workspace-member discovery."""
        pkg_dir = self._write_workspace(
            tmp_path, {'.': './dist/index.js'}, globs=['packages/*', '!packages/utils'])
        (pkg_dir / 'dist').mkdir()
        (pkg_dir / 'dist' / 'index.js').write_text('export default {};')
        base = tmp_path / 'apps' / 'web'
        base.mkdir(parents=True)

        e = JavaScriptExtractor()
        stmt = self._stmt('@myorg/utils', base)
        assert e.resolve_import(stmt, base, search_paths=[tmp_path]) is None
        assert e.is_intra_project_import(stmt, base, search_paths=[tmp_path]) is False

    def test_unmatched_specifier_is_genuine_external_dependency(self, tmp_path):
        self._write_workspace(tmp_path, {'.': './dist/index.js'})
        base = tmp_path / 'apps' / 'web'
        base.mkdir(parents=True)

        e = JavaScriptExtractor()
        stmt = self._stmt('react', base)
        assert e.resolve_import(stmt, base, search_paths=[tmp_path]) is None
        assert e.is_intra_project_import(stmt, base, search_paths=[tmp_path]) is False

    def test_pnpm_workspace_yaml_packages_list(self, tmp_path):
        """pnpm monorepos declare members in pnpm-workspace.yaml, not
        package.json `workspaces` (npm/yarn-only field)."""
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / 'package.json').write_text(json.dumps({'name': 'monorepo-root', 'private': True}))
        (tmp_path / 'pnpm-workspace.yaml').write_text('packages:\n  - "packages/*"\n')
        pkg_dir = tmp_path / 'packages' / 'utils'
        pkg_dir.mkdir(parents=True)
        (pkg_dir / 'package.json').write_text(json.dumps({'name': '@myorg/utils', 'exports': {'.': './index.js'}}))
        target = pkg_dir / 'index.js'
        target.write_text('export default {};')
        base = tmp_path / 'apps' / 'web'
        base.mkdir(parents=True)

        e = JavaScriptExtractor()
        stmt = self._stmt('@myorg/utils', base)
        assert e.resolve_import(stmt, base, search_paths=[tmp_path]) == target.resolve()

    def test_no_workspace_declaration_declines_cleanly(self, tmp_path):
        """A single-package repo (no `workspaces` field, no pnpm-workspace.yaml)
        has no workspace members to match against -- must decline, not crash."""
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / 'package.json').write_text(json.dumps({'name': 'standalone-app'}))
        base = tmp_path / 'src'
        base.mkdir(parents=True)

        e = JavaScriptExtractor()
        stmt = self._stmt('@myorg/utils', base)
        assert e.resolve_import(stmt, base, search_paths=[tmp_path]) is None


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

    def test_one_level_parent_navigates_up(self, tmp_path):
        """BACK-549: str.lstrip('./') stripped '../' entirely (character-set
        strip, not prefix strip), collapsing '../shared' to 'shared' and
        resolving in the wrong directory."""
        sibling_dir = tmp_path / 'a'
        sibling_dir.mkdir()
        target = tmp_path / 'shared.js'
        target.write_text('export const x = 1;')
        e = JavaScriptExtractor()
        result = e._resolve_relative_js('../shared', sibling_dir)
        assert result == target.resolve()

    def test_two_level_parent_navigates_up(self, tmp_path):
        """BACK-549: '../../nls' — the dominant relative-import idiom in
        deeply-nested real trees (e.g. VS Code's src/vs/**) — must resolve
        two directories up, not collapse to a same-directory 'nls' lookup."""
        nested_dir = tmp_path / 'a' / 'b'
        nested_dir.mkdir(parents=True)
        target = tmp_path / 'nls.js'
        target.write_text('export const x = 1;')
        e = JavaScriptExtractor()
        result = e._resolve_relative_js('../../nls', nested_dir)
        assert result == target.resolve()

    def test_parent_with_subdirectory_navigates_up_then_down(self, tmp_path):
        """BACK-549: '../common/cursor/x' must go up one level, then back
        down through common/cursor/, not collapse to 'common/cursor/x'
        resolved in the original directory."""
        nested_dir = tmp_path / 'browser'
        nested_dir.mkdir()
        target_dir = tmp_path / 'common' / 'cursor'
        target_dir.mkdir(parents=True)
        target = target_dir / 'cursorColumnSelection.js'
        target.write_text('export const x = 1;')
        e = JavaScriptExtractor()
        result = e._resolve_relative_js('../common/cursor/cursorColumnSelection', nested_dir)
        assert result == target.resolve()

    def test_js_extension_falls_back_to_ts(self, tmp_path):
        """BACK-410: TS ESM idiom — `import './position.js'` resolves to position.ts."""
        f = tmp_path / 'position.ts'
        f.write_text('export const x = 1;')
        e = JavaScriptExtractor()
        result = e._resolve_relative_js('./position.js', tmp_path)
        assert result == f.resolve()

    def test_js_extension_falls_back_to_tsx(self, tmp_path):
        f = tmp_path / 'App.tsx'
        f.write_text('export const App = () => <div />;')
        e = JavaScriptExtractor()
        result = e._resolve_relative_js('./App.js', tmp_path)
        assert result == f.resolve()

    def test_jsx_extension_falls_back_to_tsx(self, tmp_path):
        f = tmp_path / 'Button.tsx'
        f.write_text('export const Button = () => {};')
        e = JavaScriptExtractor()
        result = e._resolve_relative_js('./Button.jsx', tmp_path)
        assert result == f.resolve()

    def test_mjs_extension_falls_back_to_mts(self, tmp_path):
        f = tmp_path / 'module.mts'
        f.write_text('export const x = 1;')
        e = JavaScriptExtractor()
        result = e._resolve_relative_js('./module.mjs', tmp_path)
        assert result == f.resolve()

    def test_js_extension_prefers_literal_js_over_ts_fallback(self, tmp_path):
        js_file = tmp_path / 'position.js'
        js_file.write_text('export const x = 1;')
        ts_file = tmp_path / 'position.ts'
        ts_file.write_text('export const x = 2;')
        e = JavaScriptExtractor()
        result = e._resolve_relative_js('./position.js', tmp_path)
        assert result == js_file.resolve()

    def test_js_extension_falls_back_to_ts_with_multidot_filename(self, tmp_path):
        """BACK-549: 'foo.contribution.js' -> 'foo.contribution.ts', a real
        VS Code naming convention. Path.with_suffix('') on the target only
        strips the LAST dot-segment of the whole name, so chaining
        with_suffix('') then with_suffix('.ts') mangled 'automations
        .contribution.js' into 'automations.ts' (silently dropping
        '.contribution'), not 'automations.contribution.ts'."""
        f = tmp_path / 'automations.contribution.ts'
        f.write_text('export const x = 1;')
        e = JavaScriptExtractor()
        result = e._resolve_relative_js('./automations.contribution.js', tmp_path)
        assert result == f.resolve()

    def test_js_extension_no_ts_file_returns_none(self, tmp_path):
        e = JavaScriptExtractor()
        result = e._resolve_relative_js('./missing.js', tmp_path)
        assert result is None

    def test_dotted_basename_with_extension_omitted_resolves(self, tmp_path):
        """BACK-621: './charts.constants' -> charts.constants.ts, a real
        Excalidraw naming convention (also 'WelcomeScreen.Center',
        'subset-shared.chunk'). `has_extension` only checks whether the last
        path segment contains a dot at all, so a dotted basename with the
        real extension omitted was misjudged as already having one, tried
        only literal 'charts.constants' + the narrow .js/.jsx/.mjs TS-ESM
        fallback map, then bailed with None — never reaching the plain
        extension-append/directory-index resolution used for extensionless
        specifiers. Found via an independent oracle diff against real
        Excalidraw imports (0 false positives, 9/9 misses this exact shape)."""
        f = tmp_path / 'charts.constants.ts'
        f.write_text('export const X = 1;')
        e = JavaScriptExtractor()
        result = e._resolve_relative_js('./charts.constants', tmp_path)
        assert result == f.resolve()

    def test_dotted_basename_with_extension_omitted_resolves_tsx(self, tmp_path):
        """Same BACK-621 shape, resolving to .tsx instead of .ts."""
        f = tmp_path / 'WelcomeScreen.Center.tsx'
        f.write_text('export const Center = () => {};')
        e = JavaScriptExtractor()
        result = e._resolve_relative_js('./WelcomeScreen.Center', tmp_path)
        assert result == f.resolve()

    def test_dotted_basename_no_matching_file_returns_none(self, tmp_path):
        """The BACK-621 fallthrough must not start over-matching: a dotted
        basename with genuinely no backing file at any extension still
        returns None."""
        e = JavaScriptExtractor()
        result = e._resolve_relative_js('./no.such.module', tmp_path)
        assert result is None
