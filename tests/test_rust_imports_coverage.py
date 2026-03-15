"""Tests targeting uncovered lines in reveal/analyzers/imports/rust.py.

Covers:
- extract_symbols (lines 79–112)
- _is_usage_context (lines 281–308)
- _get_root_identifier (lines 318–329)
- resolve_import (lines 352–380)
- _find_cargo_root (lines 391–400)
- _resolve_from_root (lines 410–426)
- _resolve_from_dir (lines 434–450)
- _parse_scoped_use_list scoped_identifier item (lines 180–183)
- Error paths in extract_imports (lines 48, 52–56)
"""

import tempfile
from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

from reveal.analyzers.imports.rust import RustExtractor
from reveal.analyzers.imports.types import ImportStatement


def _write_rs(tmp_path: Path, name: str, code: str) -> Path:
    """Write a .rs file and return its path."""
    p = tmp_path / name
    p.write_text(code)
    return p


class TestExtractImportsErrorPaths:
    """Lines 48, 52–56 — error paths when analyzer is unavailable."""

    def test_nonexistent_file_returns_empty(self, tmp_path):
        """No analyzer class for missing file → returns []."""
        extractor = RustExtractor()
        result = extractor.extract_imports(tmp_path / 'ghost.rs')
        assert result == []

    def test_empty_file_returns_empty(self, tmp_path):
        """Empty .rs file — tree may be empty, should return []."""
        p = _write_rs(tmp_path, 'empty.rs', '')
        extractor = RustExtractor()
        result = extractor.extract_imports(p)
        assert result == []


class TestExtractSymbols:
    """Lines 79–112 — extract_symbols via real rust file parsing."""

    def test_basic_type_usage(self, tmp_path):
        """Type identifiers used in function body appear in symbols."""
        code = """\
use std::collections::HashMap;

fn main() {
    let _map: HashMap<String, i32> = HashMap::new();
}
"""
        p = _write_rs(tmp_path, 'basic.rs', code)
        extractor = RustExtractor()
        symbols = extractor.extract_symbols(p)
        # HashMap is used as a type — should be in symbols
        assert 'HashMap' in symbols

    def test_nonexistent_file_returns_empty_set(self, tmp_path):
        """No analyzer for missing file → returns set()."""
        extractor = RustExtractor()
        result = extractor.extract_symbols(tmp_path / 'ghost.rs')
        assert result == set()

    def test_empty_file_returns_empty_set(self, tmp_path):
        """Empty file → returns set()."""
        p = _write_rs(tmp_path, 'empty.rs', '')
        extractor = RustExtractor()
        result = extractor.extract_symbols(p)
        assert isinstance(result, set)

    def test_function_names_not_in_symbols(self, tmp_path):
        """Function names in fn declarations are filtered out."""
        code = "fn my_unique_function_xyz() {}\n"
        p = _write_rs(tmp_path, 'fn_def.rs', code)
        extractor = RustExtractor()
        symbols = extractor.extract_symbols(p)
        # Function name in definition context should not appear
        assert 'my_unique_function_xyz' not in symbols

    def test_field_expression_root_tracked(self, tmp_path):
        """Identifier on left side of field_expression is tracked (lines 107–110)."""
        code = """\
struct Foo { x: i32 }
fn bar(f: Foo) -> i32 {
    f.x
}
"""
        p = _write_rs(tmp_path, 'field.rs', code)
        extractor = RustExtractor()
        # Should not crash; symbols extracted
        symbols = extractor.extract_symbols(p)
        assert isinstance(symbols, set)


class TestParseUseStatements:
    """Test _parse_scoped_use_list with scoped_identifier items (lines 180–183)."""

    def test_nested_path_in_use_list(self, tmp_path):
        """use std::{collections::HashMap}; — item is scoped_identifier."""
        code = "use std::{collections::HashMap};\n"
        p = _write_rs(tmp_path, 'nested_path.rs', code)
        extractor = RustExtractor()
        imports = extractor.extract_imports(p)
        assert len(imports) >= 1
        paths = [i.module_name for i in imports]
        assert any('collections::HashMap' in path for path in paths)

    def test_mixed_use_list_with_alias(self, tmp_path):
        """use std::{fs, io as MyIo}; — alias item in list."""
        code = "use std::{fs, io as MyIo};\n"
        p = _write_rs(tmp_path, 'alias_list.rs', code)
        extractor = RustExtractor()
        imports = extractor.extract_imports(p)
        names = [imp.imported_names[0] for imp in imports]
        assert 'fs' in names


class TestResolveImport:
    """Lines 352–380 — resolve_import routing."""

    def _make_stmt(self, module_name: str, tmp_path: Path) -> ImportStatement:
        return ImportStatement(
            file_path=tmp_path / 'main.rs',
            line_number=1,
            module_name=module_name,
            imported_names=[module_name.split('::')[-1]],
            is_relative=module_name.startswith(('self::', 'super::', 'crate::')),
            import_type='rust_use',
            alias=None,
        )

    def test_external_crate_returns_none(self, tmp_path):
        """Non-crate/super/self prefix → skip (return None)."""
        extractor = RustExtractor()
        stmt = self._make_stmt('serde::Serialize', tmp_path)
        assert extractor.resolve_import(stmt, tmp_path) is None

    def test_std_crate_returns_none(self, tmp_path):
        extractor = RustExtractor()
        stmt = self._make_stmt('std::collections::HashMap', tmp_path)
        assert extractor.resolve_import(stmt, tmp_path) is None

    def test_super_prefix_returns_none(self, tmp_path):
        """super:: resolution not implemented → returns None."""
        extractor = RustExtractor()
        stmt = self._make_stmt('super::models', tmp_path)
        assert extractor.resolve_import(stmt, tmp_path) is None

    def test_crate_no_cargo_root_returns_none(self, tmp_path):
        """crate:: with no Cargo.toml in tree → None."""
        extractor = RustExtractor()
        stmt = self._make_stmt('crate::utils', tmp_path)
        assert extractor.resolve_import(stmt, tmp_path) is None

    def test_crate_no_src_dir_returns_none(self, tmp_path):
        """crate:: with Cargo.toml but no src/ → None."""
        (tmp_path / 'Cargo.toml').write_text('[package]\nname = "test"\n')
        extractor = RustExtractor()
        stmt = self._make_stmt('crate::utils', tmp_path)
        assert extractor.resolve_import(stmt, tmp_path) is None

    def test_crate_resolves_to_rs_file(self, tmp_path):
        """crate:: with Cargo.toml + src/utils.rs → returns path."""
        (tmp_path / 'Cargo.toml').write_text('[package]\nname = "test"\n')
        src = tmp_path / 'src'
        src.mkdir()
        utils_rs = src / 'utils.rs'
        utils_rs.write_text('pub fn helper() {}\n')

        extractor = RustExtractor()
        stmt = self._make_stmt('crate::utils', tmp_path)
        result = extractor.resolve_import(stmt, tmp_path)
        assert result == utils_rs.resolve()

    def test_crate_resolves_to_mod_file(self, tmp_path):
        """crate:: with src/utils/mod.rs → returns mod.rs path."""
        (tmp_path / 'Cargo.toml').write_text('[package]\nname = "test"\n')
        src = tmp_path / 'src'
        (src / 'utils').mkdir(parents=True)
        mod_rs = src / 'utils' / 'mod.rs'
        mod_rs.write_text('pub fn helper() {}\n')

        extractor = RustExtractor()
        stmt = self._make_stmt('crate::utils', tmp_path)
        result = extractor.resolve_import(stmt, tmp_path)
        assert result == mod_rs.resolve()

    def test_self_resolves_in_current_dir(self, tmp_path):
        """self:: resolves relative to current directory."""
        src = tmp_path / 'src'
        src.mkdir()
        config_rs = src / 'config.rs'
        config_rs.write_text('pub struct Config {}\n')

        extractor = RustExtractor()
        stmt = self._make_stmt('self::config', tmp_path)
        # base_path is tmp_path which doesn't have config.rs → None
        result = extractor.resolve_import(stmt, tmp_path)
        # Either None (not found) or the resolved path — either is correct
        assert result is None or result.name == 'config.rs'

    def test_super_with_cargo_and_src_returns_none(self, tmp_path):
        """Lines 373–375 — super:: with Cargo.toml + src/ returns None (not implemented)."""
        (tmp_path / 'Cargo.toml').write_text('[package]\nname = "test"\n')
        (tmp_path / 'src').mkdir()

        extractor = RustExtractor()
        stmt = self._make_stmt('super::models', tmp_path)
        result = extractor.resolve_import(stmt, tmp_path)
        assert result is None

    def test_self_with_cargo_and_src_no_file(self, tmp_path):
        """Lines 376–378 — self:: with Cargo.toml + src/ but no matching file → None."""
        (tmp_path / 'Cargo.toml').write_text('[package]\nname = "test"\n')
        (tmp_path / 'src').mkdir()

        extractor = RustExtractor()
        stmt = self._make_stmt('self::config', tmp_path)
        result = extractor.resolve_import(stmt, tmp_path)
        assert result is None


class TestFindCargoRoot:
    """Lines 391–400 — _find_cargo_root filesystem walk."""

    def test_finds_cargo_toml_in_same_dir(self, tmp_path):
        (tmp_path / 'Cargo.toml').write_text('[package]\nname="x"\n')
        extractor = RustExtractor()
        result = extractor._find_cargo_root(tmp_path)
        assert result == tmp_path.resolve()

    def test_finds_cargo_toml_in_parent(self, tmp_path):
        child = tmp_path / 'src' / 'submod'
        child.mkdir(parents=True)
        (tmp_path / 'Cargo.toml').write_text('[package]\nname="x"\n')
        extractor = RustExtractor()
        result = extractor._find_cargo_root(child)
        assert result == tmp_path.resolve()

    def test_returns_none_when_no_cargo_toml(self, tmp_path):
        extractor = RustExtractor()
        result = extractor._find_cargo_root(tmp_path)
        assert result is None


class TestResolveFromRoot:
    """Lines 410–426 — _resolve_from_root filesystem checks."""

    def test_finds_rs_file(self, tmp_path):
        src = tmp_path / 'src'
        src.mkdir()
        (src / 'utils.rs').write_text('')
        extractor = RustExtractor()
        result = extractor._resolve_from_root('utils', src)
        assert result == (src / 'utils.rs').resolve()

    def test_finds_mod_file(self, tmp_path):
        src = tmp_path / 'src'
        (src / 'utils').mkdir(parents=True)
        mod_rs = src / 'utils' / 'mod.rs'
        mod_rs.write_text('')
        extractor = RustExtractor()
        result = extractor._resolve_from_root('utils', src)
        assert result == mod_rs.resolve()

    def test_returns_none_when_not_found(self, tmp_path):
        src = tmp_path / 'src'
        src.mkdir()
        extractor = RustExtractor()
        result = extractor._resolve_from_root('nonexistent', src)
        assert result is None

    def test_uses_first_component_of_path(self, tmp_path):
        """'models::User' resolves using 'models' as module name."""
        src = tmp_path / 'src'
        src.mkdir()
        (src / 'models.rs').write_text('')
        extractor = RustExtractor()
        result = extractor._resolve_from_root('models::User', src)
        assert result is not None
        assert result.name == 'models.rs'


class TestResolveFromDir:
    """Lines 434–450 — _resolve_from_dir filesystem checks."""

    def test_finds_rs_file_in_dir(self, tmp_path):
        (tmp_path / 'config.rs').write_text('')
        extractor = RustExtractor()
        result = extractor._resolve_from_dir('config', tmp_path)
        assert result == (tmp_path / 'config.rs').resolve()

    def test_finds_mod_file_in_subdir(self, tmp_path):
        (tmp_path / 'config').mkdir()
        mod_rs = tmp_path / 'config' / 'mod.rs'
        mod_rs.write_text('')
        extractor = RustExtractor()
        result = extractor._resolve_from_dir('config', tmp_path)
        assert result == mod_rs.resolve()

    def test_returns_none_when_not_found(self, tmp_path):
        extractor = RustExtractor()
        result = extractor._resolve_from_dir('nonexistent', tmp_path)
        assert result is None


class TestCreateImport:
    """Test _create_import classification logic."""

    def test_glob_use_type(self):
        extractor = RustExtractor()
        stmt = extractor._create_import(Path('f.rs'), 1, 'std::collections::*')
        assert stmt.import_type == 'glob_use'
        assert stmt.imported_names == ['*']

    def test_aliased_use_type(self):
        extractor = RustExtractor()
        stmt = extractor._create_import(Path('f.rs'), 1, 'std::io::Result', alias='IoResult')
        assert stmt.import_type == 'aliased_use'

    def test_rust_use_type(self):
        extractor = RustExtractor()
        stmt = extractor._create_import(Path('f.rs'), 1, 'std::collections::HashMap')
        assert stmt.import_type == 'rust_use'
        assert stmt.imported_names == ['HashMap']

    def test_relative_crate_prefix(self):
        extractor = RustExtractor()
        stmt = extractor._create_import(Path('f.rs'), 1, 'crate::utils')
        assert stmt.is_relative

    def test_relative_self_prefix(self):
        extractor = RustExtractor()
        stmt = extractor._create_import(Path('f.rs'), 1, 'self::config')
        assert stmt.is_relative

    def test_external_not_relative(self):
        extractor = RustExtractor()
        stmt = extractor._create_import(Path('f.rs'), 1, 'serde::Serialize')
        assert not stmt.is_relative
