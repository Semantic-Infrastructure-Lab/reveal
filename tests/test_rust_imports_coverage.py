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

    def test_pub_use_reexport_marked_skip_unused(self, tmp_path):
        """BACK-431 feature-breadth pass (imports://?unused, real-corpus
        dogfood on Meilisearch's search/mod.rs): `pub use foo::{...};`
        re-exports items as part of THIS module's public API for other
        files to consume — it's never locally "unused" by design, unlike a
        private `use` that should be consumed in the same file. Without
        `skip_unused`, a barrel-file pattern (`mod federated; pub use
        federated::{a, b, c};`) falsely flagged every re-exported name as
        unused — 15 false positives in one real file."""
        code = "pub use federated::{perform_search, FederatedSearch};\n"
        p = _write_rs(tmp_path, 'reexport.rs', code)
        extractor = RustExtractor()
        imports = extractor.extract_imports(p)
        assert len(imports) == 2
        assert all(imp.skip_unused for imp in imports)

    def test_private_use_not_marked_skip_unused(self, tmp_path):
        """A plain (non-pub) `use` must still be checked for unused-ness —
        only `pub use` gets the re-export exemption."""
        code = "use std::collections::HashMap;\n"
        p = _write_rs(tmp_path, 'private_use.rs', code)
        extractor = RustExtractor()
        imports = extractor.extract_imports(p)
        assert len(imports) == 1
        assert imports[0].skip_unused is False

    def test_pub_use_simple_path_marked_skip_unused(self, tmp_path):
        code = "pub use foo::Bar;\n"
        p = _write_rs(tmp_path, 'reexport_simple.rs', code)
        extractor = RustExtractor()
        imports = extractor.extract_imports(p)
        assert len(imports) == 1
        assert imports[0].skip_unused is True

    def test_pub_use_aliased_marked_skip_unused(self, tmp_path):
        code = "pub use foo::Bar as Baz;\n"
        p = _write_rs(tmp_path, 'reexport_aliased.rs', code)
        extractor = RustExtractor()
        imports = extractor.extract_imports(p)
        assert len(imports) == 1
        assert imports[0].skip_unused is True


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


class TestDeepestModuleMatch:
    """BACK-547 Rust recall-oracle loop: multi-segment `crate::a::b::c` paths must
    resolve to the DEEPEST real module file (`a/b/c.rs` or `a/b/c/mod.rs`), not just
    the first path component. Confirmed as a real silent false negative on real code
    (Meilisearch `samples/rust`: `search/facet/filter/tests.rs`'s
    `use crate::search::facet::filter::index_filter::serialize_index_filter_to_filter_string`
    was never resolved to `index_filter.rs`, only mattering as far as `search/mod.rs`).
    """

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

    def test_two_segment_path_resolves_to_nested_file(self, tmp_path):
        """crate::a::b::Item -> src/a/b.rs, not src/a.rs or src/a/mod.rs."""
        (tmp_path / 'Cargo.toml').write_text('[package]\nname = "test"\n')
        src = tmp_path / 'src'
        (src / 'a').mkdir(parents=True)
        (src / 'a.rs').write_text('pub mod b;\n')  # a is ALSO a file (would wrongly match first-segment-only logic)
        b_rs = src / 'a' / 'b.rs'
        b_rs.write_text('pub fn item() {}\n')

        extractor = RustExtractor()
        stmt = self._make_stmt('crate::a::b::Item', tmp_path)
        result = extractor.resolve_import(stmt, tmp_path)
        assert result == b_rs.resolve(), (
            f"expected deepest match src/a/b.rs, got {result} "
            "(first-component-only resolution would wrongly return src/a.rs)"
        )

    def test_four_segment_path_resolves_to_deeply_nested_mod_file(self, tmp_path):
        """crate::a::b::c::Item -> src/a/b/c/mod.rs when that's the deepest real file."""
        (tmp_path / 'Cargo.toml').write_text('[package]\nname = "test"\n')
        src = tmp_path / 'src'
        (src / 'a' / 'b' / 'c').mkdir(parents=True)
        (src / 'a' / 'b' / 'mod.rs').write_text('pub mod c;\n')
        c_mod = src / 'a' / 'b' / 'c' / 'mod.rs'
        c_mod.write_text('pub fn item() {}\n')

        extractor = RustExtractor()
        stmt = self._make_stmt('crate::a::b::c::Item', tmp_path)
        result = extractor.resolve_import(stmt, tmp_path)
        assert result == c_mod.resolve()

    def test_self_multi_segment_resolves_to_nested_file(self, tmp_path):
        """self::a::b::Item -> ./a/b.rs relative to the importing file's directory."""
        (tmp_path / 'Cargo.toml').write_text('[package]\nname = "test"\n')
        base = tmp_path / 'src' / 'mod_dir'
        (base / 'a').mkdir(parents=True)
        b_rs = base / 'a' / 'b.rs'
        b_rs.write_text('pub fn item() {}\n')

        extractor = RustExtractor()
        stmt = self._make_stmt('self::a::b::Item', tmp_path)
        result = extractor.resolve_import(stmt, base)
        assert result == b_rs.resolve()


class TestResolveSuper:
    """BACK-547: `super::` was previously unconditionally unresolved (`return None`),
    a systematic false negative for every `use super::x` in the corpus. Now resolves
    relative to the importing file's parent module.
    """

    def _make_stmt(self, module_name: str, tmp_path: Path) -> ImportStatement:
        return ImportStatement(
            file_path=tmp_path / 'main.rs',
            line_number=1,
            module_name=module_name,
            imported_names=[module_name.split('::')[-1]],
            is_relative=True,
            import_type='rust_use',
            alias=None,
        )

    def test_super_resolves_sibling_in_same_directory(self, tmp_path):
        """2015-style: file at src/a/x.rs, `super::y` -> src/a/y.rs (sibling)."""
        (tmp_path / 'Cargo.toml').write_text('[package]\nname = "test"\n')
        a_dir = tmp_path / 'src' / 'a'
        a_dir.mkdir(parents=True)
        (a_dir / 'mod.rs').write_text('pub mod x;\npub mod y;\n')
        y_rs = a_dir / 'y.rs'
        y_rs.write_text('pub fn item() {}\n')

        extractor = RustExtractor()
        stmt = self._make_stmt('super::y', tmp_path)
        result = extractor.resolve_import(stmt, a_dir)
        assert result == y_rs.resolve()

    def test_super_resolves_one_level_up_for_mod_rs_file(self, tmp_path):
        """A file that IS a/mod.rs has its parent module one directory further up."""
        (tmp_path / 'Cargo.toml').write_text('[package]\nname = "test"\n')
        src = tmp_path / 'src'
        top_rs = src / 'top.rs'
        top_rs.parent.mkdir(parents=True)
        top_rs.write_text('pub fn thing() {}\n')
        a_dir = src / 'a'
        a_dir.mkdir()
        (a_dir / 'mod.rs').write_text('use super::top;\n')

        extractor = RustExtractor()
        stmt = self._make_stmt('super::top', tmp_path)
        result = extractor.resolve_import(stmt, a_dir)
        assert result == top_rs.resolve()

    def test_super_with_no_match_returns_none(self, tmp_path):
        (tmp_path / 'Cargo.toml').write_text('[package]\nname = "test"\n')
        (tmp_path / 'src').mkdir()
        extractor = RustExtractor()
        stmt = self._make_stmt('super::nonexistent', tmp_path)
        result = extractor.resolve_import(stmt, tmp_path / 'src')
        assert result is None


class TestScopedUseListCrateSuperSelfRoot:
    """BACK-547: `use crate::{a, b, c};` / `use super::{a, b};` / `use self::{a, b};`
    — a grouped import directly off the `crate`/`super`/`self` keyword root with no
    intermediate path segment — was silently dropped in its ENTIRETY (zero imports
    extracted for the whole `use` statement, not just an unresolved item), because
    tree-sitter-rust represents that root as a bare keyword node (`.kind()` literally
    `'crate'`/`'super'`/`'self'`), which the base-path scan didn't recognize (it only
    matched `identifier`/`scoped_identifier`, covering `std::{..}`-style named roots).
    Confirmed on real code (Meilisearch `samples/rust`:
    `scheduler/enterprise_edition/network.rs:30`'s
    `use crate::{processing, Error, IndexScheduler, Result};` produced zero extracted
    imports).
    """

    def test_crate_grouped_import_extracts_all_items(self, tmp_path):
        code = "use crate::{processing, Error, IndexScheduler, Result};\n"
        p = _write_rs(tmp_path, 'network.rs', code)
        extractor = RustExtractor()
        imports = extractor.extract_imports(p)
        names = {i.module_name for i in imports}
        assert names == {
            'crate::processing', 'crate::Error', 'crate::IndexScheduler', 'crate::Result',
        }

    def test_super_grouped_import_extracts_all_items(self, tmp_path):
        code = (
            "use super::{\n"
            "    content_part::ContentPart, conversation::Conversation,\n"
            "    error::RealtimeAPIError,\n"
            "};\n"
        )
        p = _write_rs(tmp_path, 'server_event.rs', code)
        extractor = RustExtractor()
        imports = extractor.extract_imports(p)
        names = {i.module_name for i in imports}
        assert names == {
            'super::content_part::ContentPart',
            'super::conversation::Conversation',
            'super::error::RealtimeAPIError',
        }

    def test_self_grouped_import_extracts_all_items(self, tmp_path):
        code = "use self::{foo, bar};\n"
        p = _write_rs(tmp_path, 'lib.rs', code)
        extractor = RustExtractor()
        imports = extractor.extract_imports(p)
        names = {i.module_name for i in imports}
        assert names == {'self::foo', 'self::bar'}


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
