"""Go import extraction.

Extracts import declarations from Go source files.
"""

import re
from pathlib import Path
from typing import List

from . import ImportStatement


def extract_go_imports(file_path: Path) -> List[ImportStatement]:
    """Extract all import declarations from Go file.

    Args:
        file_path: Path to .go file

    Returns:
        List of ImportStatement objects

    Handles:
        - Single imports: import "fmt"
        - Grouped imports: import ( "fmt" "os" )
        - Aliased imports: import f "fmt"
        - Dot imports: import . "fmt"
        - Blank imports: import _ "database/sql/driver"
    """
    try:
        content = file_path.read_text(encoding='utf-8')
    except (UnicodeDecodeError, FileNotFoundError):
        return []

    imports = []

    # Extract single-line imports: import "package"
    single_pattern = r'^\s*import\s+(?:(\w+|\.|_)\s+)?"([^"]+)"'
    for match in re.finditer(single_pattern, content, re.MULTILINE):
        alias = match.group(1)  # Could be identifier, '.', or '_'
        package_path = match.group(2)
        line_number = content[:match.start()].count('\n') + 1

        imports.append(_create_go_import(
            file_path, line_number, package_path, alias
        ))

    # Extract grouped imports: import ( ... )
    grouped_pattern = r'import\s*\(\s*([^)]+)\)'
    for block_match in re.finditer(grouped_pattern, content, re.DOTALL):
        block_content = block_match.group(1)
        block_start_line = content[:block_match.start()].count('\n') + 1

        # Find each import line within the block
        import_pattern = r'^\s*(?:(\w+|\.|_)\s+)?"([^"]+)"'
        for line_match in re.finditer(import_pattern, block_content, re.MULTILINE):
            alias = line_match.group(1)
            package_path = line_match.group(2)
            # Calculate line number within block
            lines_before = block_content[:line_match.start()].count('\n')
            line_number = block_start_line + lines_before

            imports.append(_create_go_import(
                file_path, line_number, package_path, alias
            ))

    return imports


def _create_go_import(file_path: Path, line_number: int, package_path: str, alias: str = None) -> ImportStatement:
    """Create ImportStatement for a Go import.

    Args:
        file_path: Path to source file
        line_number: Line number of import
        package_path: Package path (e.g., "fmt", "github.com/user/pkg")
        alias: Optional alias (identifier, '.', or '_')

    Returns:
        ImportStatement object
    """
    # Determine import type based on alias
    if alias == '.':
        import_type = 'dot_import'  # Imports into current namespace
    elif alias == '_':
        import_type = 'blank_import'  # Side-effect only
    elif alias:
        import_type = 'aliased_import'
    else:
        import_type = 'go_import'

    # Go imports are never relative (no ./ syntax)
    # Internal packages start with module name, external from domain
    is_relative = False

    # Extract package name from path for imported_names
    # e.g., "github.com/user/pkg" → "pkg"
    package_name = package_path.split('/')[-1]
    imported_names = [package_name] if not alias == '_' else []

    return ImportStatement(
        file_path=file_path,
        line_number=line_number,
        module_name=package_path,
        imported_names=imported_names,
        is_relative=is_relative,
        import_type=import_type,
        alias=alias
    )


__all__ = [
    'extract_go_imports',
]
