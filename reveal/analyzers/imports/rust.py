"""Rust import (use statement) extraction using tree-sitter.

Extracts use declarations from Rust source files.
Uses tree-sitter for consistent parsing across all language analyzers.
"""

import re
from pathlib import Path
from typing import List, Set

from . import ImportStatement
from .base import LanguageExtractor, register_extractor
from ...base import get_analyzer


@register_extractor
class RustExtractor(LanguageExtractor):
    """Rust import extractor using tree-sitter parsing.

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
            Set of symbol names (currently empty - TODO: Phase 5.1)

        TODO: Implement symbol extraction using tree-sitter or regex
        """
        # TODO: Phase 5.1 - Implement Rust symbol extraction
        return set()

    def _parse_use_declaration(self, node, file_path: Path, analyzer) -> List[ImportStatement]:
        """Parse a Rust use_declaration node.

        Handles:
            use std::collections::HashMap;
            use std::{fs, io};
            use std::io::Result as IoResult;
            use std::collections::*;
        """
        use_text = analyzer._get_node_text(node)
        line_number = node.start_point[0] + 1

        # Check for nested/scoped imports: use std::{fs, io}
        if '::{' in use_text:
            return self._parse_scoped_use(use_text, line_number, file_path)

        # Single use statement
        # Pattern: use path::to::module[::*] [as alias];
        # Remove 'pub', 'pub(crate)', etc. and 'use' keyword
        use_text = re.sub(r'^\s*(?:pub\s*(?:\([^)]*\)\s*)?)?use\s+', '', use_text)
        use_text = use_text.rstrip(';').strip()

        # Check for alias
        alias = None
        if ' as ' in use_text:
            use_path, alias = use_text.split(' as ', 1)
            use_path = use_path.strip()
            alias = alias.strip()
        else:
            use_path = use_text

        return [self._create_import(file_path, line_number, use_path, alias)]

    def _parse_scoped_use(self, use_text: str, line_number: int, file_path: Path) -> List[ImportStatement]:
        """Parse nested/scoped use statement: use std::{fs, io}."""
        imports = []

        # Extract base path and nested items
        # Pattern: use base::path::{item1, item2 as alias2}
        match = re.match(r'(?:pub\s*(?:\([^)]*\)\s*)?)?use\s+([\w:]+)::\{([^}]+)\}', use_text)
        if not match:
            return imports

        base_path = match.group(1)
        nested_items = match.group(2)

        # Parse each nested item
        for item in nested_items.split(','):
            item = item.strip()
            if not item:
                continue

            # Check for alias in nested item
            item_alias = None
            if ' as ' in item:
                item_name, item_alias = item.split(' as ', 1)
                item_name = item_name.strip()
                item_alias = item_alias.strip()
            else:
                item_name = item

            # Create full path
            full_path = f"{base_path}::{item_name}"

            imports.append(self._create_import(
                file_path, line_number, full_path, item_alias, item_name
            ))

        return imports

    @staticmethod
    def _create_import(
        file_path: Path,
        line_number: int,
        use_path: str,
        alias: str = None,
        imported_name: str = None
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
