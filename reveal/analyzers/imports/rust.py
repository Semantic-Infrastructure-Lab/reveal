"""Rust import (use statement) extraction using tree-sitter.

Previous implementation: 215 lines with tree-sitter + 2 regex patterns
Current implementation: 185 lines using pure tree-sitter AST extraction

Benefits:
- Eliminates all regex patterns (pub use prefix, scoped use parsing)
- Uses tree-sitter node types (scoped_identifier, use_as_clause, use_wildcard, scoped_use_list)
- More robust handling of complex Rust use syntax
"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import FrozenSet, List, Set, Optional, Tuple
from ...core import node_children as _children, node_prev_sibling as _prev_sibling
from ...core.treesitter_compat import _zero_arg

logger = logging.getLogger(__name__)

from .types import ImportStatement
from .base import ImportsDiskCache, LanguageExtractor, register_extractor

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore  # Python < 3.11 fallback

# Rust's own "stdlib" — always external, no Cargo.toml needed. `core`/`alloc`
# are the no_std subsets of `std`; all three are equally never a dependency
# or an in-tree crate.
_RUST_STD_CRATES = frozenset({'std', 'core', 'alloc'})

# Cross-invocation disk cache (BACK-626, extending BACK-625 to Rust): same
# independent-reparse gap as PythonExtractor had -- extract_imports() does not
# share TreeSitterAnalyzer.get_structure()'s structure cache (BACK-535).
_IMPORTS_CACHE = ImportsDiskCache("rust_imports")


def _line_text(analyzer, line_number: int) -> str:
    """Full source line for a 1-indexed line number, or "" if out of range.

    BACK-432: I005/I001's noqa detection read ImportStatement.source_line,
    which every non-Python extractor left at its default "" — silently
    blind to duplicate-import detection and source-line-based suppression
    comments for Go/Rust/JS despite advertising support for them.
    """
    idx = line_number - 1
    if 0 <= idx < len(analyzer.lines):
        return analyzer.lines[idx].rstrip()
    return ""


@register_extractor
class RustExtractor(LanguageExtractor):
    """Rust import extractor using pure tree-sitter parsing.

    Supports:
    - Simple use: use std::collections::HashMap
    - Nested use: use std::{fs, io}
    - Glob use: use std::collections::*
    - Aliased use: use std::io::Result as IoResult
    - Self/super/crate use: use self::module, use super::module
    - External crates: use serde::Serialize
    """

    extensions = {'.rs'}
    language_name = 'Rust'

    def extract_imports(self, file_path: Path) -> List[ImportStatement]:
        """Extract all use declarations from Rust file using tree-sitter.

        Cached cross-invocation on disk (BACK-626), same pattern as
        PythonExtractor (BACK-625).

        Args:
            file_path: Path to .rs file

        Returns:
            List of ImportStatement objects
        """
        return _IMPORTS_CACHE.get_or_compute(file_path, lambda: self._extract_imports_uncached(file_path))

    def _extract_imports_uncached(self, file_path: Path) -> List[ImportStatement]:
        analyzer = self._get_tree_analyzer(file_path)
        if not analyzer:
            return []

        imports = []

        # Find all use_declaration nodes
        use_nodes = analyzer._find_nodes_by_type('use_declaration')
        for node in use_nodes:
            imports.extend(self._parse_use_declaration(node, file_path, analyzer))

        return imports

    def extract_symbols(self, file_path: Path) -> Set[str]:
        """Extract symbols used in Rust file.

        Args:
            file_path: Path to source file

        Returns:
            Set of symbol names referenced in the file

        Used for detecting unused imports by comparing imported names
        with actually-used symbols.
        """
        analyzer = self._get_tree_analyzer(file_path)
        if not analyzer:
            return set()

        symbols = set()

        # Find identifier and type_identifier nodes
        # Note: Rust tree-sitter uses 'type_identifier' for type names (Result, HashMap, etc.)
        # and 'identifier' for variable/function names
        identifier_nodes = analyzer._find_nodes_by_type('identifier')
        type_identifier_nodes = analyzer._find_nodes_by_type('type_identifier')

        for node in identifier_nodes + type_identifier_nodes:
            name = analyzer._get_node_text(node)

            # Filter out definition contexts
            if self._is_usage_context(node):
                symbols.add(name)

            # Handle field expressions (foo.bar -> track 'foo')
            if (
                _zero_arg(node, 'parent')
                and _zero_arg(_zero_arg(node, 'parent'), 'kind') == 'field_expression'
            ):
                root = self._get_root_identifier(_zero_arg(node, 'parent'), analyzer)
                if root:
                    symbols.add(root)

        return symbols

    def _parse_use_declaration(self, node, file_path: Path, analyzer) -> List[ImportStatement]:
        """Parse a Rust use_declaration node using tree-sitter AST.

        Tree-sitter provides structured nodes:
            use std::collections::HashMap;        # scoped_identifier
            use std::{fs, io};                    # scoped_use_list
            use std::io::Result as IoResult;     # use_as_clause
            use std::collections::*;              # use_wildcard
        """
        line_number = _zero_arg(node, 'start_position').row + 1

        # `pub use foo::Bar;` re-exports Bar as part of this module's public
        # API for OTHER files to consume — it's never "locally unused" by
        # design, unlike a private `use` that should be consumed in this
        # same file or else is genuinely dead. Without this, every re-export
        # barrel file (a common Rust pattern: `mod foo; pub use foo::{...};`)
        # falsely reported every re-exported name as unused (BACK-431
        # feature-breadth pass, found via real Meilisearch source,
        # search/mod.rs re-exporting its `federated` submodule's public API —
        # 15 false positives in one file).
        is_reexport = any(
            _zero_arg(child, 'kind') == 'visibility_modifier' for child in _children(node)
        )

        # Find the main use clause (skip 'pub', 'use' keywords, ';')
        for child in _children(node):
            if _zero_arg(child, 'kind') == 'scoped_identifier':
                # Simple use: use std::collections::HashMap
                use_path = analyzer._get_node_text(child)
                return [self._create_import(
                    file_path, line_number, use_path, skip_unused=is_reexport,
                    source_line=_line_text(analyzer, line_number),
                )]

            elif _zero_arg(child, 'kind') == 'scoped_use_list':
                # Nested use: use std::{fs, io}
                return self._parse_scoped_use_list(child, file_path, line_number, analyzer, is_reexport)

            elif _zero_arg(child, 'kind') == 'use_as_clause':
                # Aliased use: use std::io::Result as IoResult
                return self._parse_use_as_clause(child, file_path, line_number, analyzer, is_reexport)

            elif _zero_arg(child, 'kind') == 'use_wildcard':
                # Glob use: use std::collections::*
                use_path = analyzer._get_node_text(child)
                return [self._create_import(
                    file_path, line_number, use_path, skip_unused=is_reexport,
                    source_line=_line_text(analyzer, line_number),
                )]

        return []

    def _parse_scoped_use_list(
        self, node, file_path: Path, line_number: int, analyzer, is_reexport: bool = False
    ) -> List[ImportStatement]:
        """Parse scoped_use_list node: std::{fs, io}

        BACK-XXX: `use crate::{a, b, c};` / `use super::{a, b};` / `use self::{a, b};`
        — a grouped-import directly off the `crate`/`super`/`self` path root with no
        intermediate segment — has tree-sitter-rust represent that root as a bare
        keyword node whose `.kind()` is literally `'crate'`/`'super'`/`'self'` (not
        `'identifier'` or `'scoped_identifier'`, which only cover `std::{..}`-style
        named-crate/module roots). The base-path scan below only matched
        identifier/scoped_identifier, so it silently found no `base_path`, returned
        an empty list, and the ENTIRE `use` statement's imports vanished with no
        error — confirmed on real code (Meilisearch `samples/rust`:
        `scheduler/enterprise_edition/network.rs:30`'s
        `use crate::{processing, Error, IndexScheduler, Result};` produced zero
        extracted imports, so `processing.rs` never counted this file as a dependent).
        """
        imports: List[ImportStatement] = []

        # Extract base path (before ::)
        base_path = None
        use_list_node = None

        for child in _children(node):
            if _zero_arg(child, 'kind') in (
                'identifier', 'scoped_identifier', 'crate', 'super', 'self'
            ):
                base_path = analyzer._get_node_text(child)
            elif _zero_arg(child, 'kind') == 'use_list':
                use_list_node = child

        if not base_path or not use_list_node:
            return imports

        return self._parse_use_list_items(
            use_list_node, base_path, file_path, line_number, analyzer, is_reexport
        )

    def _parse_use_list_items(
        self, use_list_node, base_path: str, file_path: Path, line_number: int, analyzer,
        is_reexport: bool = False
    ) -> List[ImportStatement]:
        """Parse the items of a `use_list` node given the dotted `base_path` accumulated
        so far, recursing into any nested group.

        BACK-669 (ripgrep second-corpus loop, github.com/BurntSushi/ripgrep): a
        `use_list` item can itself be a nested `scoped_use_list` —
        `base::{sub::{x, y}, other::z}` — which is exactly the idiomatic Rust
        `pub use crate::{error::{Error, ErrorKind}, matcher::{...}};` re-export shape
        (near-ubiquitous in ripgrep's crate `lib.rs` files — every one of the 16
        importer files behind BACK-669's 44 missed edges used this shape). This loop
        previously only matched `identifier`/`use_as_clause`/`scoped_identifier` item
        kinds; a nested `scoped_use_list` item fell through unmatched and its entire
        subtree's imports vanished silently — the same "whole item disappears, no
        error" failure shape BACK-558 already fixed for the `crate`/`super`/`self`-as-
        list-root case, one grouping level deeper. Recursing (rather than
        special-casing exactly one extra level) closes it for arbitrarily deep
        nesting, not just two.
        """
        imports: List[ImportStatement] = []

        for item in _children(use_list_node):
            if _zero_arg(item, 'kind') == 'identifier':
                # Simple item: fs
                item_name = analyzer._get_node_text(item)
                full_path = f"{base_path}::{item_name}"
                imports.append(self._create_import(
                    file_path, line_number, full_path, imported_name=item_name, skip_unused=is_reexport,
                    source_line=_line_text(analyzer, line_number),
                ))
            elif _zero_arg(item, 'kind') == 'use_as_clause':
                # Aliased item: io as MyIo
                imports.extend(self._parse_nested_use_as(
                    item, file_path, line_number, analyzer, base_path, is_reexport
                ))
            elif _zero_arg(item, 'kind') == 'scoped_identifier':
                # Nested path: collections::HashMap
                item_path = analyzer._get_node_text(item)
                full_path = f"{base_path}::{item_path}"
                imported_name = item_path.split('::')[-1]
                imports.append(self._create_import(
                    file_path, line_number, full_path, imported_name=imported_name, skip_unused=is_reexport,
                    source_line=_line_text(analyzer, line_number),
                ))
            elif _zero_arg(item, 'kind') == 'scoped_use_list':
                # Nested group: sub::{x, y} - recurse with the combined base path.
                nested_base = None
                nested_list = None
                for nc in _children(item):
                    if _zero_arg(nc, 'kind') in (
                        'identifier', 'scoped_identifier', 'crate', 'super', 'self'
                    ):
                        nested_base = analyzer._get_node_text(nc)
                    elif _zero_arg(nc, 'kind') == 'use_list':
                        nested_list = nc
                if nested_base and nested_list:
                    imports.extend(self._parse_use_list_items(
                        nested_list, f"{base_path}::{nested_base}", file_path, line_number, analyzer,
                        is_reexport,
                    ))

        return imports

    def _parse_use_as_clause(
        self, node, file_path: Path, line_number: int, analyzer, is_reexport: bool = False
    ) -> List[ImportStatement]:
        """Parse use_as_clause node: std::io::Result as IoResult"""
        use_path = None
        alias = None

        for child in _children(node):
            if _zero_arg(child, 'kind') == 'scoped_identifier':
                use_path = analyzer._get_node_text(child)
            elif (_zero_arg(child, 'kind') == 'identifier' and
                    analyzer._get_node_text(_prev_sibling(child) or child) == 'as'):
                alias = analyzer._get_node_text(child)

        if not use_path:
            return []

        return [self._create_import(
            file_path, line_number, use_path, alias, skip_unused=is_reexport,
            source_line=_line_text(analyzer, line_number),
        )]

    def _parse_nested_use_as(
        self, node, file_path: Path, line_number: int, analyzer, base_path: str, is_reexport: bool = False
    ) -> List[ImportStatement]:
        """Parse use_as_clause within a scoped use list."""
        item_name = None
        alias = None

        for child in _children(node):
            if _zero_arg(child, 'kind') == 'identifier':
                if not item_name:
                    item_name = analyzer._get_node_text(child)
                else:
                    alias = analyzer._get_node_text(child)

        if not item_name:
            return []

        full_path = f"{base_path}::{item_name}"
        return [self._create_import(
            file_path, line_number, full_path, alias, item_name, skip_unused=is_reexport,
            source_line=_line_text(analyzer, line_number),
        )]

    @staticmethod
    def _create_import(
        file_path: Path,
        line_number: int,
        use_path: str,
        alias: Optional[str] = None,
        imported_name: Optional[str] = None,
        skip_unused: bool = False,
        source_line: str = "",
    ) -> ImportStatement:
        """Create ImportStatement for a Rust use declaration.

        Args:
            file_path: Path to source file
            line_number: Line number of use statement
            use_path: Full use path (e.g., "std::collections::HashMap")
            alias: Optional alias from 'as' clause
            imported_name: For nested imports, the specific item imported
            skip_unused: True for `pub use` re-exports, never locally "unused"

        Returns:
            ImportStatement object
        """
        # Determine if relative (self::, super::, crate::)
        is_relative = use_path.startswith(('self::', 'super::', 'crate::'))

        # Determine import type
        if use_path.endswith('::*'):
            import_type = 'glob_use'
            module_name = use_path  # Keep ::* in module_name
            imported_names = ['*']
        elif alias:
            import_type = 'aliased_use'
            module_name = use_path
            imported_names = [imported_name or use_path.split('::')[-1]]
        else:
            import_type = 'rust_use'
            module_name = use_path
            # Extract the final item (what's actually imported)
            imported_names = [imported_name or use_path.split('::')[-1]]

        return ImportStatement(
            file_path=file_path,
            line_number=line_number,
            module_name=module_name,
            imported_names=imported_names,
            is_relative=is_relative,
            import_type=import_type,
            alias=alias,
            skip_unused=skip_unused,
            source_line=source_line,
        )

    def _is_usage_context(self, node) -> bool:
        """Check if identifier is in a usage context (not definition).

        Filters out:
        - Function/struct/enum/trait declarations
        - Parameter names
        - Field names in struct definitions
        - Variable bindings (let statements)
        - Use statement names
        """
        if not _zero_arg(node, 'parent'):
            return True

        # Walk up to check if inside use declaration
        current = node
        while current:
            if _zero_arg(current, 'kind') == 'use_declaration':
                return False
            current = _zero_arg(current, 'parent')

        parent_type = _zero_arg(_zero_arg(node, 'parent'), 'kind')

        # Skip definition contexts
        # Note: 'function_signature_item' removed - it was filtering return types as definitions
        # Parameter names are still filtered by 'parameters' and 'parameter'
        # Note: 'field_declaration' is deliberately NOT skipped. A struct
        # field's *type* identifier (`pub user_provided: RoaringBitmap`) has
        # field_declaration as its parent, and that type is a real usage of the
        # imported name (BACK-420). The field *name* is a separate 'field_identifier'
        # node (still skipped below), and extract_symbols only walks
        # identifier/type_identifier, so dropping field_declaration cannot let a
        # field name leak in as a false usage.
        if parent_type in ('function_item', 'struct_item', 'enum_item', 'trait_item',
                          'type_item', 'impl_item', 'mod_item',
                          'parameters', 'parameter',
                          'field_identifier'):
            return False

        # For let bindings (let x = ...)
        if parent_type == 'let_declaration':
            # Pattern on left side of = is a definition
            # This is simplified - Rust patterns can be complex
            return False

        return True

    def _get_root_identifier(self, field_expr_node, analyzer):
        """Extract root identifier from field expression chain.

        Examples:
            io::Result -> 'io'
            std::collections::HashMap -> 'std'
        """
        # Walk up field expression chain to find root
        current = field_expr_node
        while current and _zero_arg(current, 'kind') == 'field_expression':
            if _children(current):
                current = current.child(0)  # Get value (left side)
            else:
                break

        # Should now be an identifier
        if current and _zero_arg(current, 'kind') == 'identifier':
            return analyzer._get_node_text(current)

        return None

    def resolve_import(
        self,
        stmt: ImportStatement,
        base_path: Path,
        search_paths: Optional[List[Path]] = None,
    ) -> Optional[Path]:
        """Resolve Rust use statement to file path.

        Args:
            stmt: Import statement to resolve
            base_path: Directory of the file containing the import

        Returns:
            Absolute path to the module file, or None if not resolvable

        Rust module resolution:
        - crate:: = project root (Cargo.toml location)
        - super:: = parent module
        - self:: = current module
        - External crates: std, external dependencies (skip for cycles)
        - Module file: either name.rs or name/mod.rs
        """
        use_path = stmt.module_name

        # Skip external crates (don't start with crate/super/self)
        if not use_path.startswith(('crate::', 'super::', 'self::')):
            # External crate (std, serde, etc.) - skip
            return None

        # Find crate root (Cargo.toml location)
        crate_root = self._find_cargo_root(base_path)
        if not crate_root:
            return None

        # Determine src directory (usually src/, but could be custom)
        src_dir = crate_root / 'src'
        if not src_dir.exists():
            return None

        # Resolve based on prefix
        if use_path.startswith('crate::'):
            # Absolute from crate root
            return self._resolve_from_root(use_path[7:], src_dir)  # Remove 'crate::'
        elif use_path.startswith('super::'):
            # Relative to parent module.
            return self._resolve_super(use_path[7:], base_path)  # Remove 'super::'
        elif use_path.startswith('self::'):
            # Relative to current module
            return self._resolve_from_dir(use_path[6:], base_path)  # Remove 'self::'

        return None

    def _find_cargo_root(self, start_path: Path) -> Optional[Path]:
        """Find Cargo.toml file by walking up directory tree.

        Args:
            start_path: Directory to start search from

        Returns:
            Directory containing Cargo.toml, or None if not found
        """
        current = start_path.resolve()

        # Walk up until we find Cargo.toml or hit filesystem root
        while current != current.parent:
            cargo_toml = current / 'Cargo.toml'
            if cargo_toml.exists():
                return current
            current = current.parent

        return None

    def is_intra_project_import(
        self,
        stmt: ImportStatement,
        base_path: Path,
        search_paths: Optional[List[Path]] = None,
        project_namespaces: Optional[Set[str]] = None,
    ) -> Optional[bool]:
        """A `crate::`/`super::`/`self::` use path (``stmt.is_relative``) is
        unambiguously intra-project. Everything else (a bare crate name --
        ``use serde::Deserialize``, or a Rust 2018+ own-crate reference by
        name, e.g. an integration test's ``use mylib::Config``) needs
        Cargo.toml to tell apart (BACK-1189):

          1. ``std``/``core``/``alloc`` are always ``False`` -- no manifest
             needed.
          2. Otherwise find the nearest Cargo.toml (same walk
             :meth:`_find_cargo_root` already does for resolution) and
             check its ``[package].name`` (the crate's own name, referenced
             this way from its own integration tests) and its
             dependency tables. A ``path = "..."`` dependency is a sibling
             crate in the same tree (a workspace member), not external, so
             its name counts as local, not a real dependency name.
          3. Anything else (a `git`/version-only dependency this
             particular Cargo.toml doesn't list, e.g. inherited via
             ``[workspace.dependencies]`` + ``dep.workspace = true``) stays
             ``None`` -- honest under-classification, never a guess.
        """
        if stmt.is_relative:
            return True
        top_level = stmt.module_name.split('::')[0]
        if not top_level:
            return None
        if top_level in _RUST_STD_CRATES:
            return False
        crate_root = self._find_cargo_root(base_path)
        if crate_root is None:
            return None
        local_names, external_names = _rust_crate_inventory(crate_root)
        if top_level in local_names:
            return True
        if top_level in external_names:
            return False
        return None

    @staticmethod
    def _deepest_module_match(parts: List[str], base_dir: Path) -> Optional[Path]:
        """Find the DEEPEST existing module file matching a prefix of `parts`.

        BACK-XXX: A `use` path like `crate::search::facet::filter::index_filter::foo`
        names a real *file* only down to wherever the last actual module boundary is
        (here, `search/facet/filter/index_filter.rs`) — everything after that is an
        item name (function/struct/const), not a further directory. The previous
        implementation only ever consumed `parts[0]`, so any path with 2+ module
        segments before the item name silently resolved to the wrong (too-shallow)
        file or nothing at all — a confirmed silent false negative on real code
        (Meilisearch `samples/rust`: `search/facet/filter/tests.rs`'s
        `use crate::search::facet::filter::index_filter::serialize_index_filter_to_filter_string`
        was never counted as a dependent of `index_filter.rs`).

        Rust supports BOTH module-per-file (`a/b.rs`) and module-per-directory
        (`a/b/mod.rs`) at every level, so both forms are tried at every prefix depth,
        starting from the longest prefix (most specific) and shortening until a real
        file is found. This mirrors Go's package-directory fallback (BACK-553) and
        TS's index-vs-dir handling (BACK-556) — same shape of bug, different language.
        """
        for n in range(len(parts), 0, -1):
            prefix = parts[:n]
            module_file = base_dir.joinpath(*prefix).with_suffix('.rs')
            if module_file.exists():
                return module_file.resolve()
            mod_file = base_dir.joinpath(*prefix, 'mod.rs')
            if mod_file.exists():
                return mod_file.resolve()
        return None

    def _resolve_from_root(self, path: str, src_dir: Path) -> Optional[Path]:
        """Resolve use path from crate root (src/).

        Examples:
            'utils' -> src/utils.rs or src/utils/mod.rs
            'models::User' -> src/models.rs or src/models/mod.rs (User is item in file)
            'search::facet::filter::index_filter::foo' ->
                src/search/facet/filter/index_filter.rs (deepest real module file)
        """
        parts = path.split('::')
        if not parts:
            return None
        return self._deepest_module_match(parts, src_dir)

    def _resolve_from_dir(self, path: str, module_dir: Path) -> Optional[Path]:
        """Resolve use path from current module directory.

        Examples:
            'config' -> ./config.rs or ./config/mod.rs
            'a::b::Item' -> ./a/b.rs or ./a/b/mod.rs (deepest real module file)
        """
        parts = path.split('::')
        if not parts:
            return None
        return self._deepest_module_match(parts, module_dir)

    def _resolve_super(self, path: str, current_file_dir: Path) -> Optional[Path]:
        """Resolve `super::path` — relative to the PARENT module of the current file.

        Rust's two valid module-declaration styles give two different parent-module
        locations for a file at `<dir>/<name>.rs`:
        - 2018+-style ("mod-per-file"): `<dir>/<name>.rs` is a submodule of the module
          whose own file is `<dir>/<parent_name>.rs` (a *sibling* of `<dir>`, one level
          up) — e.g. `search/facet.rs` and `search/facet/x.rs` co-exist; `super::` from
          `x.rs` means "look in `search/facet` first" i.e. this file's own directory.
        - 2015-style ("mod-per-directory"): `<dir>/mod.rs` IS the parent module file,
          and siblings in the same `<dir>` (e.g. `<dir>/x.rs`) reach their parent via
          `<dir>` itself too.
        In both styles, the parent module's own namespace for resolving further `::`
        segments is `current_file_dir` (this file's own directory) UNLESS this file
        *is* a `mod.rs`, in which case its parent module's namespace is one directory
        further up (`current_file_dir.parent`).
        """
        parts = path.split('::')
        if not parts:
            return None
        bases = [current_file_dir]
        if current_file_dir != current_file_dir.parent:
            bases.append(current_file_dir.parent)
        for base in bases:
            result = self._deepest_module_match(parts, base)
            if result:
                return result
        return None


# ---------------------------------------------------------------------------
# BACK-1189: Cargo.toml-informed crate inventory for is_intra_project_import.
# Cached per crate root -- see the equivalent Python cache's comment
# (analyzers/imports/python.py) for why: a directory's worth of Cargo.toml
# parsing repeated across every unresolved `use` in a large crate is real,
# measured overhead, not a hypothetical one.
# ---------------------------------------------------------------------------

def _dependency_table_names(table: dict) -> Tuple[Set[str], Set[str]]:
    """Split one Cargo.toml dependency table (``[dependencies]``,
    ``[dev-dependencies]``, ``[build-dependencies]``) into (local, external)
    crate-identifier names. A ``path = "..."`` entry is a sibling crate in
    the same tree (a workspace member) -- local, not a real dependency --
    everything else (a bare version string, or a table with ``version``/
    ``git``/``workspace`` but no ``path``) is a real external dependency."""
    local: Set[str] = set()
    external: Set[str] = set()
    for name, spec in (table or {}).items():
        ident = name.replace('-', '_')
        if isinstance(spec, dict) and 'path' in spec:
            local.add(ident)
        else:
            external.add(ident)
    return local, external


@lru_cache(maxsize=256)
def _rust_crate_inventory(crate_root: Path) -> Tuple[FrozenSet[str], FrozenSet[str]]:
    """(local crate-identifier names, external dependency names) for the
    crate rooted at *crate_root* -- the manifest inventory that upgrades
    ``is_intra_project_import``'s honest ``None`` for a bare crate-name use
    path into a real verdict (BACK-1189)."""
    local: Set[str] = set()
    external: Set[str] = set()
    try:
        with open(crate_root / 'Cargo.toml', 'rb') as f:
            data = tomllib.load(f)
    except (OSError, ValueError):
        return frozenset(), frozenset()

    package_name = ((data.get('package') or {}).get('name'))
    if package_name:
        # Own crate, referenced by name -- the common integration-test shape
        # (tests/*.rs uses `use mylib::Config;`, not `crate::Config`).
        local.add(package_name.replace('-', '_'))

    for table_name in ('dependencies', 'dev-dependencies', 'build-dependencies'):
        table_local, table_external = _dependency_table_names(data.get(table_name) or {})
        local.update(table_local)
        external.update(table_external)

    return frozenset(local), frozenset(external)


# Backward compatibility: Keep old function-based API
def extract_rust_imports(file_path: Path) -> List[ImportStatement]:
    """Extract all use declarations from Rust file.

    DEPRECATED: Use RustExtractor().extract_imports() instead.
    Kept for backward compatibility with existing code.
    """
    extractor = RustExtractor()
    return extractor.extract_imports(file_path)


__all__ = [
    'RustExtractor',
    'extract_rust_imports',  # deprecated
]
