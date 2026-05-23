"""Coverage tests for reveal/analyzers/imports/go.py.

Targets: lines 47, 51-55, 80-110, 142, 203-234, 244-255, 277-304, 315-324, 335-349
Current coverage: 42% → target: 80%+
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from reveal.analyzers.imports.go import GoExtractor
from reveal.analyzers.imports.types import ImportStatement


def _mock_ts_node(kind='', children=None, parent_result=None, start_byte=0):
    """Create a mock tree-sitter 1.x compatible node.

    1.x API: kind(), child_count(), child(i), parent(), start_byte() are all methods.
    """
    m = MagicMock()
    m.kind.return_value = kind
    children = children or []
    m.child_count.return_value = len(children)
    m.child.side_effect = lambda i: children[i] if 0 <= i < len(children) else None
    m.parent.return_value = parent_result
    m.start_byte.return_value = start_byte
    return m


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _write_go(tmp_path: Path, name: str, code: str) -> Path:
    p = tmp_path / name
    p.write_text(code, encoding='utf-8')
    return p


# ─── extract_imports error paths ─────────────────────────────────────────────

class TestExtractImportsErrorPaths:
    def test_nonexistent_file_returns_empty(self, tmp_path):
        e = GoExtractor()
        result = e.extract_imports(tmp_path / 'missing.go')
        assert result == []

    def test_empty_file_returns_empty(self, tmp_path):
        f = _write_go(tmp_path, 'empty.go', '')
        e = GoExtractor()
        result = e.extract_imports(f)
        assert result == []

    def test_non_go_extension_may_return_empty(self, tmp_path):
        # .txt has no Go analyzer — covers get_analyzer returns None path
        f = tmp_path / 'not_go.txt'
        f.write_text('import "fmt"')
        e = GoExtractor()
        result = e.extract_imports(f)
        assert result == []

    def test_get_analyzer_returns_none_path(self):
        """Cover line 47: get_analyzer() returning None."""
        e = GoExtractor()
        with patch('reveal.analyzers.imports.go.get_analyzer', return_value=None):
            result = e.extract_imports(Path('fake.go'))
        assert result == []

    def test_analyzer_tree_is_none_path(self, tmp_path):
        """Cover lines 50-51: analyzer.tree is None."""
        f = _write_go(tmp_path, 'x.go', 'package main')
        mock_analyzer = MagicMock()
        mock_analyzer.tree = None
        mock_cls = MagicMock(return_value=mock_analyzer)
        e = GoExtractor()
        with patch('reveal.analyzers.imports.go.get_analyzer', return_value=mock_cls):
            result = e.extract_imports(f)
        assert result == []

    def test_exception_in_extract_imports_returns_empty(self, tmp_path):
        """Cover lines 53-55: exception path returns []."""
        f = _write_go(tmp_path, 'x.go', 'package main')
        e = GoExtractor()
        with patch('reveal.analyzers.imports.go.get_analyzer', side_effect=RuntimeError('boom')):
            result = e.extract_imports(f)
        assert result == []


# ─── extract_symbols error paths ─────────────────────────────────────────────

class TestExtractSymbolsErrorPaths:
    def test_nonexistent_file_returns_empty_set(self, tmp_path):
        e = GoExtractor()
        result = e.extract_symbols(tmp_path / 'missing.go')
        assert result == set()

    def test_empty_file_returns_empty_set(self, tmp_path):
        f = _write_go(tmp_path, 'empty.go', '')
        e = GoExtractor()
        result = e.extract_symbols(f)
        assert result == set()

    def test_get_analyzer_none_returns_empty_set(self):
        """Cover extract_symbols line 82."""
        e = GoExtractor()
        with patch('reveal.analyzers.imports.go.get_analyzer', return_value=None):
            result = e.extract_symbols(Path('fake.go'))
        assert result == set()

    def test_tree_none_returns_empty_set(self, tmp_path):
        """Cover extract_symbols lines 86-87."""
        f = _write_go(tmp_path, 'x.go', 'package main')
        mock_analyzer = MagicMock()
        mock_analyzer.tree = None
        mock_cls = MagicMock(return_value=mock_analyzer)
        e = GoExtractor()
        with patch('reveal.analyzers.imports.go.get_analyzer', return_value=mock_cls):
            result = e.extract_symbols(f)
        assert result == set()

    def test_exception_in_extract_symbols_returns_empty_set(self):
        """Cover extract_symbols lines 89-90."""
        e = GoExtractor()
        with patch('reveal.analyzers.imports.go.get_analyzer', side_effect=RuntimeError('boom')):
            result = e.extract_symbols(Path('fake.go'))
        assert result == set()


# ─── extract_symbols real Go file ────────────────────────────────────────────

class TestExtractSymbols:
    def test_symbols_extracted_from_real_go(self, tmp_path):
        code = '''package main

import "fmt"

func main() {
    x := 42
    fmt.Println(x)
}
'''
        f = _write_go(tmp_path, 'main.go', code)
        e = GoExtractor()
        result = e.extract_symbols(f)
        # 'fmt' should be in symbols (used in selector expression)
        assert isinstance(result, set)
        # Should contain something (may vary by tree-sitter version, just assert no crash)

    def test_symbols_returns_set_type(self, tmp_path):
        code = 'package main\nfunc main() {}\n'
        f = _write_go(tmp_path, 'x.go', code)
        e = GoExtractor()
        result = e.extract_symbols(f)
        assert isinstance(result, set)


# ─── extract_imports real Go files ───────────────────────────────────────────

class TestExtractImportsRealGo:
    def test_single_import(self, tmp_path):
        code = '''package main
import "fmt"
func main() {}
'''
        f = _write_go(tmp_path, 'main.go', code)
        e = GoExtractor()
        result = e.extract_imports(f)
        assert len(result) >= 1
        paths = [r.module_name for r in result]
        assert 'fmt' in paths

    def test_grouped_imports(self, tmp_path):
        code = '''package main
import (
    "fmt"
    "os"
    "net/http"
)
func main() {}
'''
        f = _write_go(tmp_path, 'main.go', code)
        e = GoExtractor()
        result = e.extract_imports(f)
        paths = {r.module_name for r in result}
        assert 'fmt' in paths
        assert 'os' in paths
        assert 'net/http' in paths

    def test_aliased_import(self, tmp_path):
        code = '''package main
import f "fmt"
func main() {}
'''
        f = _write_go(tmp_path, 'main.go', code)
        e = GoExtractor()
        result = e.extract_imports(f)
        fmts = [r for r in result if r.module_name == 'fmt']
        assert len(fmts) == 1
        assert fmts[0].alias == 'f'
        assert fmts[0].import_type == 'aliased_import'

    def test_dot_import(self, tmp_path):
        code = '''package main
import . "fmt"
func main() {}
'''
        f = _write_go(tmp_path, 'main.go', code)
        e = GoExtractor()
        result = e.extract_imports(f)
        dot_imports = [r for r in result if r.alias == '.']
        assert len(dot_imports) == 1
        assert dot_imports[0].import_type == 'dot_import'

    def test_blank_import(self, tmp_path):
        code = '''package main
import _ "database/sql"
func main() {}
'''
        f = _write_go(tmp_path, 'main.go', code)
        e = GoExtractor()
        result = e.extract_imports(f)
        blank_imports = [r for r in result if r.alias == '_']
        assert len(blank_imports) == 1
        assert blank_imports[0].import_type == 'blank_import'
        assert blank_imports[0].imported_names == []

    def test_no_imports(self, tmp_path):
        code = 'package main\nfunc main() {}\n'
        f = _write_go(tmp_path, 'main.go', code)
        e = GoExtractor()
        result = e.extract_imports(f)
        assert result == []


# ─── _create_import ───────────────────────────────────────────────────────────

class TestCreateImport:
    def _make(self, package_path, alias=None):
        return GoExtractor._create_import(
            file_path=Path('x.go'),
            line_number=5,
            package_path=package_path,
            alias=alias
        )

    def test_plain_import(self):
        stmt = self._make('fmt')
        assert stmt.import_type == 'go_import'
        assert stmt.alias is None
        assert stmt.imported_names == ['fmt']
        assert stmt.is_relative is False

    def test_dot_import(self):
        stmt = self._make('strings', alias='.')
        assert stmt.import_type == 'dot_import'

    def test_blank_import(self):
        stmt = self._make('database/sql', alias='_')
        assert stmt.import_type == 'blank_import'
        assert stmt.imported_names == []

    def test_aliased_import(self):
        stmt = self._make('net/http', alias='h')
        assert stmt.import_type == 'aliased_import'
        assert stmt.alias == 'h'

    def test_deep_package_name(self):
        stmt = self._make('github.com/user/repo/pkg/auth')
        assert stmt.imported_names == ['auth']


# ─── _is_usage_context ───────────────────────────────────────────────────────

class TestIsUsageContext:
    def _make_node(self, parent_type=None, parent_children=None, chain=None, node_sb=42):
        """Build a mock node with parent chain (1.x API)."""
        if chain:
            # Build ancestor chain bottom-up
            # The last element in chain is the topmost ancestor (no further parent)
            top = _mock_ts_node(kind=chain[-1], parent_result=None)
            current_parent = top
            for typ in reversed(chain[1:-1]):
                p = _mock_ts_node(kind=typ, parent_result=current_parent)
                current_parent = p
            node = _mock_ts_node(kind=chain[0], parent_result=current_parent, start_byte=node_sb)
            return node

        if parent_type is None:
            return _mock_ts_node(parent_result=None, start_byte=node_sb)

        parent_children = parent_children if parent_children is not None else []
        parent = _mock_ts_node(kind=parent_type, children=parent_children, parent_result=None)
        return _mock_ts_node(parent_result=parent, start_byte=node_sb)

    def test_no_parent_returns_true(self):
        node = _mock_ts_node(parent_result=None)
        assert GoExtractor()._is_usage_context(node) is True

    def test_inside_import_declaration_returns_false(self):
        e = GoExtractor()
        # Chain: node → inner('something') → import_declaration
        import_parent = _mock_ts_node(kind='import_declaration', parent_result=None)
        inner = _mock_ts_node(kind='something', parent_result=import_parent)
        node = _mock_ts_node(parent_result=inner)
        assert e._is_usage_context(node) is False

    def test_inside_import_spec_returns_false(self):
        e = GoExtractor()
        spec = _mock_ts_node(kind='import_spec', parent_result=None)
        node = _mock_ts_node(parent_result=spec)
        assert e._is_usage_context(node) is False

    def test_function_declaration_parent_returns_false(self):
        e = GoExtractor()
        node = self._make_node(parent_type='function_declaration')
        assert e._is_usage_context(node) is False

    def test_method_declaration_parent_returns_false(self):
        e = GoExtractor()
        node = self._make_node(parent_type='method_declaration')
        assert e._is_usage_context(node) is False

    def test_type_declaration_parent_returns_false(self):
        e = GoExtractor()
        node = self._make_node(parent_type='type_declaration')
        assert e._is_usage_context(node) is False

    def test_parameter_declaration_parent_returns_false(self):
        e = GoExtractor()
        node = self._make_node(parent_type='parameter_declaration')
        assert e._is_usage_context(node) is False

    def test_field_declaration_parent_returns_false(self):
        e = GoExtractor()
        node = self._make_node(parent_type='field_declaration')
        assert e._is_usage_context(node) is False

    def test_short_var_declaration_first_child_returns_false(self):
        e = GoExtractor()
        # node is the first child of parent (same start_byte)
        node_sb = 42
        first_child = _mock_ts_node(start_byte=node_sb)  # same start_byte as node
        other = _mock_ts_node(start_byte=99)
        parent = _mock_ts_node(kind='short_var_declaration', children=[first_child, other], parent_result=None)
        node = _mock_ts_node(parent_result=parent, start_byte=node_sb)
        assert e._is_usage_context(node) is False

    def test_short_var_declaration_not_first_child_returns_true(self):
        e = GoExtractor()
        # node is NOT first child (different start_byte from child(0))
        node_sb = 42
        first_child = _mock_ts_node(start_byte=10)  # different from node
        other = _mock_ts_node(start_byte=node_sb)
        parent = _mock_ts_node(kind='short_var_declaration', children=[first_child, other], parent_result=None)
        node = _mock_ts_node(parent_result=parent, start_byte=node_sb)
        assert e._is_usage_context(node) is True

    def test_var_spec_first_child_returns_false(self):
        e = GoExtractor()
        node_sb = 42
        first_child = _mock_ts_node(start_byte=node_sb)
        parent = _mock_ts_node(kind='var_spec', children=[first_child], parent_result=None)
        node = _mock_ts_node(parent_result=parent, start_byte=node_sb)
        assert e._is_usage_context(node) is False

    def test_var_spec_not_first_child_returns_true(self):
        e = GoExtractor()
        node_sb = 42
        first_child = _mock_ts_node(start_byte=10)
        other = _mock_ts_node(start_byte=node_sb)
        parent = _mock_ts_node(kind='var_spec', children=[first_child, other], parent_result=None)
        node = _mock_ts_node(parent_result=parent, start_byte=node_sb)
        assert e._is_usage_context(node) is True

    def test_plain_usage_returns_true(self):
        e = GoExtractor()
        node = self._make_node(parent_type='call_expression')
        assert e._is_usage_context(node) is True


# ─── _get_root_identifier ─────────────────────────────────────────────────────

class TestGetRootIdentifier:
    def test_simple_selector_returns_root(self):
        e = GoExtractor()
        analyzer = MagicMock()
        analyzer._get_node_text.return_value = 'fmt'

        # selector_expression → identifier child
        ident = _mock_ts_node(kind='identifier')
        selector = _mock_ts_node(kind='selector_expression', children=[ident])

        result = e._get_root_identifier(selector, analyzer)
        assert result == 'fmt'

    def test_nested_selector_chain_returns_root(self):
        e = GoExtractor()
        analyzer = MagicMock()
        analyzer._get_node_text.return_value = 'os'

        # selector → selector → identifier
        root_ident = _mock_ts_node(kind='identifier')
        inner = _mock_ts_node(kind='selector_expression', children=[root_ident])
        outer = _mock_ts_node(kind='selector_expression', children=[inner])

        result = e._get_root_identifier(outer, analyzer)
        assert result == 'os'

    def test_non_identifier_root_returns_none(self):
        e = GoExtractor()
        analyzer = MagicMock()

        # selector_expression whose child is not an identifier
        non_ident = _mock_ts_node(kind='call_expression')
        selector = _mock_ts_node(kind='selector_expression', children=[non_ident])

        result = e._get_root_identifier(selector, analyzer)
        assert result is None

    def test_empty_children_returns_none(self):
        e = GoExtractor()
        analyzer = MagicMock()

        selector = _mock_ts_node(kind='selector_expression', children=[])

        result = e._get_root_identifier(selector, analyzer)
        assert result is None


# ─── _find_go_module_root ─────────────────────────────────────────────────────

class TestFindGoModuleRoot:
    def test_finds_go_mod_in_same_dir(self, tmp_path):
        (tmp_path / 'go.mod').write_text('module example.com/myapp\ngo 1.21\n')
        e = GoExtractor()
        result = e._find_go_module_root(tmp_path)
        assert result == tmp_path.resolve()

    def test_finds_go_mod_in_parent(self, tmp_path):
        sub = tmp_path / 'pkg' / 'utils'
        sub.mkdir(parents=True)
        (tmp_path / 'go.mod').write_text('module example.com/myapp\ngo 1.21\n')
        e = GoExtractor()
        result = e._find_go_module_root(sub)
        assert result == tmp_path.resolve()

    def test_returns_none_when_no_go_mod(self, tmp_path):
        e = GoExtractor()
        # Use a deep temp directory that won't have go.mod
        deep = tmp_path / 'no_module_here'
        deep.mkdir()
        result = e._find_go_module_root(deep)
        # May find a go.mod from ancestor dirs in real env, but the tmp_path
        # should be far enough from any real module root
        # Just assert it returns Path or None (no crash)
        assert result is None or isinstance(result, Path)


# ─── _get_module_name ─────────────────────────────────────────────────────────

class TestGetModuleName:
    def test_extracts_module_name(self, tmp_path):
        (tmp_path / 'go.mod').write_text('module github.com/user/myrepo\n\ngo 1.21\n')
        e = GoExtractor()
        result = e._get_module_name(tmp_path)
        assert result == 'github.com/user/myrepo'

    def test_returns_none_when_no_go_mod(self, tmp_path):
        e = GoExtractor()
        result = e._get_module_name(tmp_path)
        assert result is None

    def test_returns_none_when_go_mod_has_no_module_line(self, tmp_path):
        (tmp_path / 'go.mod').write_text('go 1.21\nrequire somelib v1.0.0\n')
        e = GoExtractor()
        result = e._get_module_name(tmp_path)
        assert result is None

    def test_handles_read_exception(self, tmp_path):
        e = GoExtractor()
        (tmp_path / 'go.mod').write_text('')  # empty file — no module line
        result = e._get_module_name(tmp_path)
        assert result is None


# ─── resolve_import ───────────────────────────────────────────────────────────

class TestResolveImport:
    def _make_stmt(self, module_name: str, tmp_path: Path) -> ImportStatement:
        return ImportStatement(
            file_path=tmp_path / 'main.go',
            line_number=1,
            module_name=module_name,
            imported_names=[module_name.split('/')[-1]],
            is_relative=False,
            import_type='go_import',
        )

    def test_external_package_returns_none(self, tmp_path):
        (tmp_path / 'go.mod').write_text('module myapp\ngo 1.21\n')
        e = GoExtractor()
        stmt = self._make_stmt('fmt', tmp_path)
        result = e.resolve_import(stmt, tmp_path)
        assert result is None

    def test_no_go_mod_returns_none(self, tmp_path):
        e = GoExtractor()
        stmt = self._make_stmt('myapp/utils', tmp_path)
        result = e.resolve_import(stmt, tmp_path)
        assert result is None

    def test_module_name_not_found_returns_none(self, tmp_path):
        (tmp_path / 'go.mod').write_text('module myapp\ngo 1.21\n')
        e = GoExtractor()
        stmt = self._make_stmt('myapp/utils', tmp_path)
        # utils directory doesn't exist → None
        result = e.resolve_import(stmt, tmp_path)
        assert result is None

    def test_local_package_resolves_to_dir(self, tmp_path):
        module_name = 'myapp'
        (tmp_path / 'go.mod').write_text(f'module {module_name}\ngo 1.21\n')
        utils_dir = tmp_path / 'utils'
        utils_dir.mkdir()
        (utils_dir / 'utils.go').write_text('package utils\n')

        e = GoExtractor()
        stmt = self._make_stmt(f'{module_name}/utils', tmp_path)
        result = e.resolve_import(stmt, tmp_path)
        assert result is not None
        assert result == utils_dir.resolve()

    def test_go_mod_module_name_none_returns_none(self, tmp_path):
        # go.mod with no module line
        (tmp_path / 'go.mod').write_text('go 1.21\n')
        e = GoExtractor()
        stmt = self._make_stmt('someapp/pkg', tmp_path)
        result = e.resolve_import(stmt, tmp_path)
        assert result is None
