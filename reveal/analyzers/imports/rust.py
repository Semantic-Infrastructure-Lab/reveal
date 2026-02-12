"""Rust import (use statement) extraction using tree-sitter.

Previous implementation: 215 lines with tree-sitter + 2 regex patterns
Current implementation: 185 lines using pure tree-sitter AST extraction

Benefits:
- Eliminates all regex patterns (pub use prefix, scoped use parsing)
- Uses tree-sitter node types (scoped_identifier, use_as_clause, use_wildcard, scoped_use_list)
- More robust handling of complex Rust use syntax
"""

from pathlib import Path
from typing import List, Set, Optional

from . import ImportStatement
from .base import LanguageExtractor, register_extractor
from ...registry import get_analyzer


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

        Args:
            file_path: Path to .rs file

        Returns:
            List of ImportStatement objects
        """
        try:
            analyzer_class = get_analyzer(str(file_path))
            if not analyzer_class:
                return []

            analyzer = analyzer_class(str(file_path))
            if not analyzer.tree:
                return []

        except Exception:
            # Can't parse - return empty
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
        try:
            analyzer_class = get_analyzer(str(file_path))
            if not analyzer_class:
                return set()

            analyzer = analyzer_class(str(file_path))
            if not analyzer.tree:
                return set()

        except Exception:
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
            if node.parent and node.parent.type == 'field_expression':
                root = self._get_root_identifier(node.parent, analyzer)
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
        line_number = node.start_point[0] + 1

        # Find the main use clause (skip 'pub', 'use' keywords, ';')
        for child in node.children:
            if child.type == 'scoped_identifier':
                # Simple use: use std::collections::HashMap
                use_path = analyzer._get_node_text(child)
                return [self._create_import(file_path, line_number, use_path)]

            elif child.type == 'scoped_use_list':
                # Nested use: use std::{fs, io}
                return self._parse_scoped_use_list(child, file_path, line_number, analyzer)

            elif child.type == 'use_as_clause':
                # Aliased use: use std::io::Result as IoResult
                return self._parse_use_as_clause(child, file_path, line_number, analyzer)

            elif child.type == 'use_wildcard':
                # Glob use: use std::collections::*
                use_path = analyzer._get_node_text(child)
                return [self._create_import(file_path, line_number, use_path)]

        return []

    def _parse_scoped_use_list(self, node, file_path: Path, line_number: int, analyzer) -> List[ImportStatement]:
        """Parse scoped_use_list node: std::{fs, io}"""
        imports = []

        # Extract base path (before ::)
        base_path = None
        use_list_node = None

        for child in node.children:
            if child.type in ('identifier', 'scoped_identifier'):
                base_path = analyzer._get_node_text(child)
            elif child.type == 'use_list':
                use_list_node = child

        if not base_path or not use_list_node:
            return imports

        # Parse each item in the use_list
        for item in use_list_node.children:
            if item.type == 'identifier':
                # Simple item: fs
                item_name = analyzer._get_node_text(item)
                full_path = f"{base_path}::{item_name}"
                imports.append(self._create_import(
                    file_path, line_number, full_path, imported_name=item_name
                ))
            elif item.type == 'use_as_clause':
                # Aliased item: io as MyIo
                imports.extend(self._parse_nested_use_as(
                    item, file_path, line_number, analyzer, base_path
                ))
            elif item.type == 'scoped_identifier':
                # Nested path: collections::HashMap
                item_path = analyzer._get_node_text(item)
                full_path = f"{base_path}::{item_path}"
                imported_name = item_path.split('::')[-1]
                imports.append(self._create_import(
                    file_path, line_number, full_path, imported_name=imported_name
                ))

        return imports

    def _parse_use_as_clause(self, node, file_path: Path, line_number: int, analyzer) -> List[ImportStatement]:
        """Parse use_as_clause node: std::io::Result as IoResult"""
        use_path = None
        alias = None

        for child in node.children:
            if child.type == 'scoped_identifier':
                use_path = analyzer._get_node_text(child)
            elif child.type == 'identifier' and analyzer._get_node_text(child.prev_sibling or child) == 'as':
                alias = analyzer._get_node_text(child)

        if not use_path:
            return []

        return [self._create_import(file_path, line_number, use_path, alias)]

    def _parse_nested_use_as(self, node, file_path: Path, line_number: int, analyzer, base_path: str) -> List[ImportStatement]:
        """Parse use_as_clause within a scoped use list."""
        item_name = None
        alias = None

        for child in node.children:
            if child.type == 'identifier':
                if not item_name:
                    item_name = analyzer._get_node_text(child)
                else:
                    alias = analyzer._get_node_text(child)

        if not item_name:
            return []

        full_path = f"{base_path}::{item_name}"
        return [self._create_import(file_path, line_number, full_path, alias, item_name)]

    @staticmethod
    def _create_import(
        file_path: Path,
        line_number: int,
        use_path: str,
        alias: Optional[str] = None,
        imported_name: Optional[str] = None
    ) -> ImportStatement:
        """Create ImportStatement for a Rust use declaration.

        Args:
            file_path: Path to source file
            line_number: Line number of use statement
            use_path: Full use path (e.g., "std::collections::HashMap")
            alias: Optional alias from 'as' clause
            imported_name: For nested imports, the specific item imported

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
            alias=alias
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
        if not node.parent:
            return True

        # Walk up to check if inside use declaration
        current = node
        while current:
            if current.type == 'use_declaration':
                return False
            current = current.parent

        parent_type = node.parent.type

        # Skip definition contexts
        # Note: 'function_signature_item' removed - it was filtering return types as definitions
        # Parameter names are still filtered by 'parameters' and 'parameter'
        if parent_type in ('function_item', 'struct_item', 'enum_item', 'trait_item',
                          'type_item', 'impl_item', 'mod_item',
                          'parameters', 'parameter',
                          'field_declaration', 'field_identifier'):
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
        while current and current.type == 'field_expression':
            if current.children:
                current = current.children[0]  # Get value (left side)
            else:
                break

        # Should now be an identifier
        if current and current.type == 'identifier':
            return analyzer._get_node_text(current)

        return None

    def resolve_import(
        self,
        stmt: ImportStatement,
        base_path: Path
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
            # Relative to parent module - complex, skip for now
            return None
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

    def _resolve_from_root(self, path: str, src_dir: Path) -> Optional[Path]:
        """Resolve use path from crate root (src/).

        Examples:
            'utils' -> src/utils.rs or src/utils/mod.rs
            'models::User' -> src/models.rs or src/models/mod.rs (User is item in file)
        """
        # Take first component (module name)
        parts = path.split('::')
        if not parts:
            return None

        module_name = parts[0]

        # Try module_name.rs
        module_file = src_dir / f"{module_name}.rs"
        if module_file.exists():
            return module_file.resolve()

        # Try module_name/mod.rs
        mod_file = src_dir / module_name / 'mod.rs'
        if mod_file.exists():
            return mod_file.resolve()

        return None

    def _resolve_from_dir(self, path: str, module_dir: Path) -> Optional[Path]:
        """Resolve use path from current module directory.

        Examples:
            'config' -> ./config.rs or ./config/mod.rs
        """
        parts = path.split('::')
        if not parts:
            return None

        module_name = parts[0]

        # Try module_name.rs in current directory
        module_file = module_dir / f"{module_name}.rs"
        if module_file.exists():
            return module_file.resolve()

        # Try module_name/mod.rs
        mod_file = module_dir / module_name / 'mod.rs'
        if mod_file.exists():
            return mod_file.resolve()

        return None


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
