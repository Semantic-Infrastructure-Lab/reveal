"""Rust import (use statement) extraction.

Extracts use declarations from Rust source files.
"""

import re
from pathlib import Path
from typing import List, Set

from . import ImportStatement
from .base import LanguageExtractor, register_extractor


@register_extractor
class RustExtractor(LanguageExtractor):
    """Rust import extractor using regex parsing.

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
        """Extract all use declarations from Rust file.

        Args:
            file_path: Path to .rs file

        Returns:
            List of ImportStatement objects
        """
        try:
            content = file_path.read_text(encoding='utf-8')
        except (UnicodeDecodeError, FileNotFoundError):
            return []

        imports = []

        # Pattern: use path::to::module[::item];
        # Handles: use, pub use, pub(crate) use, etc.
        use_pattern = r'''
            ^\s*(?:pub\s*(?:\([^)]*\)\s*)?)?  # Optional pub or pub(crate)
            use\s+                             # use keyword
            ([\w:]+                            # Path (word chars and ::)
             (?:::\{[^}]+\}                    # Optional nested imports
             |::\*                             # OR glob import ::*
             )?                                # Make nested/glob optional
            )                                  # Capture the entire path
            (?:\s+as\s+(\w+))?                 # Optional 'as' alias
            \s*;                               # Semicolon
        '''

        for match in re.finditer(use_pattern, content, re.MULTILINE | re.VERBOSE):
            use_path = match.group(1)
            alias = match.group(2)
            line_number = content[:match.start()].count('\n') + 1

            # Check if this is a nested import: use std::{fs, io}
            if '::{' in use_path:
                # Extract base path and nested items
                base_match = re.match(r'([\w:]+)::\{([^}]+)\}', use_path)
                if base_match:
                    base_path = base_match.group(1)
                    nested_items = base_match.group(2)

                    # Create separate import for each nested item
                    for item in nested_items.split(','):
                        item = item.strip()
                        if not item:
                            continue

                        # Handle alias in nested import: {Read as R}
                        item_alias = None
                        if ' as ' in item:
                            item, item_alias = [x.strip() for x in item.split(' as ', 1)]

                        full_path = f"{base_path}::{item}"
                        imports.append(self._create_import(
                            file_path, line_number, full_path, item_alias, item
                        ))

                    continue  # Skip creating a single import for this line

            # Single import or glob import
            imports.append(self._create_import(
                file_path, line_number, use_path, alias
            ))

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
