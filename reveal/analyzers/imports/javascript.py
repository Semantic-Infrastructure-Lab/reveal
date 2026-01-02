"""JavaScript/TypeScript import extraction using tree-sitter.

Extracts import statements and require() calls from JavaScript and TypeScript files.
Uses tree-sitter for consistent parsing across all language analyzers.
"""

import re
from pathlib import Path
from typing import List, Set, Optional

from . import ImportStatement
from .base import LanguageExtractor, register_extractor
from ...base import get_analyzer


@register_extractor
class JavaScriptExtractor(LanguageExtractor):
    """JavaScript/TypeScript import extractor using tree-sitter parsing.

    Supports:
    - ES6 imports: import { foo } from 'module'
    - Default imports: import React from 'react'
    - Namespace imports: import * as utils from './utils'
    - Side-effect imports: import './styles.css'
    - CommonJS: const x = require('module')
    - Dynamic imports: await import('./module')
    """

    extensions = {'.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs'}
    language_name = 'JavaScript/TypeScript'

    def extract_imports(self, file_path: Path) -> List[ImportStatement]:
        """Extract all import statements from JavaScript/TypeScript file using tree-sitter.

        Args:
            file_path: Path to .js, .jsx, .ts, .tsx, .mjs, or .cjs file

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

        # Extract ES6 import statements
        import_nodes = analyzer._find_nodes_by_type('import_statement')
        for node in import_nodes:
            imports.extend(self._parse_import_statement(node, file_path, analyzer))

        # Extract CommonJS require() calls
        call_nodes = analyzer._find_nodes_by_type('call_expression')
        for node in call_nodes:
            result = self._parse_require_call(node, file_path, analyzer)
            if result:
                imports.append(result)

        return imports

    def extract_symbols(self, file_path: Path) -> Set[str]:
        """Extract symbols used in JavaScript/TypeScript file.

        Args:
            file_path: Path to source file

        Returns:
            Set of symbol names (currently empty - TODO: Phase 5.1)

        TODO: Implement symbol extraction using tree-sitter or regex
        """
        # TODO: Phase 5.1 - Implement JS/TS symbol extraction
        return set()

    def _parse_import_statement(self, node, file_path: Path, analyzer) -> List[ImportStatement]:
        """Parse ES6 import statement using tree-sitter.

        Handles:
            import foo from 'module'
            import { foo, bar } from 'module'
            import * as foo from 'module'
            import foo, { bar } from 'module'
            import 'module'  // side-effect only
        """
        import_text = analyzer._get_node_text(node)

        # Extract module path (always in quotes at end)
        # Pattern: from 'module' or from "module" or just 'module' for side-effects
        module_match = re.search(r'''['"]([^'"]+)['"]''', import_text)
        if not module_match:
            return []

        module_path = module_match.group(1)
        line_number = node.start_point[0] + 1

        # Determine import type and extract imported names
        imported_names = []
        import_type = 'es6_import'
        alias = None

        # Side-effect only: import './styles.css'
        if not ' from ' in import_text and not 'import(' in import_text:
            import_type = 'side_effect_import'

        # Namespace import: import * as foo from 'module'
        elif '* as ' in import_text:
            import_type = 'namespace_import'
            alias_match = re.search(r'\*\s+as\s+(\w+)', import_text)
            if alias_match:
                imported_names = ['*']
                alias = alias_match.group(1)

        # Named or default imports
        elif ' from ' in import_text:
            # Extract the part between 'import' and 'from'
            import_clause = import_text.split(' from ')[0]
            import_clause = import_clause.replace('import', '').strip()

            # Remove optional 'type' keyword (TypeScript)
            import_clause = re.sub(r'^type\s+', '', import_clause)

            # Named imports: { foo, bar }
            if '{' in import_clause:
                # Extract content from braces
                names_match = re.search(r'\{([^}]+)\}', import_clause)
                if names_match:
                    names_str = names_match.group(1)
                    for name in names_str.split(','):
                        name = name.strip()
                        if not name:
                            continue
                        # Handle 'foo as bar' - we want 'foo'
                        if ' as ' in name:
                            name = name.split(' as ')[0].strip()
                        imported_names.append(name)

                # Check for default import too: foo, { bar }
                default_match = re.match(r'(\w+)\s*,', import_clause)
                if default_match:
                    imported_names.insert(0, default_match.group(1))

            # Default import only: import foo from 'module'
            else:
                default_name = import_clause.strip()
                if default_name:
                    imported_names = [default_name]
                    import_type = 'default_import'

        return [ImportStatement(
            file_path=file_path,
            line_number=line_number,
            module_name=module_path,
            imported_names=imported_names,
            is_relative=module_path.startswith('.'),
            import_type=import_type,
            alias=alias
        )]

    def _parse_require_call(self, node, file_path: Path, analyzer) -> Optional[ImportStatement]:
        """Parse CommonJS require() call using tree-sitter.

        Handles:
            const foo = require('module')
            const { foo, bar } = require('module')
            require('module')  // side-effect only
            await import('./module')  // dynamic import
        """
        call_text = analyzer._get_node_text(node)

        # Check if this is a require() call
        is_require = call_text.startswith('require(')
        # Also check for dynamic import()
        is_dynamic_import = call_text.startswith('import(')

        if not is_require and not is_dynamic_import:
            return None

        # Extract module path from quotes
        module_match = re.search(r'''['"]([^'"]+)['"]''', call_text)
        if not module_match:
            return None

        module_path = module_match.group(1)
        line_number = node.start_point[0] + 1

        # For dynamic imports
        if is_dynamic_import:
            return ImportStatement(
                file_path=file_path,
                line_number=line_number,
                module_name=module_path,
                imported_names=[],
                is_relative=module_path.startswith('.'),
                import_type='dynamic_import',
                alias=None
            )

        # For require(), check if it's part of a variable declaration
        # We need to look at the parent node to see the assignment
        imported_names = []
        import_type = 'commonjs_require'

        # Try to find variable declaration parent
        parent = node.parent
        if parent and parent.type == 'variable_declarator':
            # Get the left side (identifier or pattern)
            if parent.children:
                left_side = analyzer._get_node_text(parent.children[0])

                # Destructured: { foo, bar }
                if left_side.startswith('{'):
                    names_str = left_side.strip('{}')
                    for name in names_str.split(','):
                        name = name.strip()
                        # Handle renaming: { foo: bar }
                        if ':' in name:
                            name = name.split(':')[0].strip()
                        if name:
                            imported_names.append(name)

                # Single assignment: foo
                else:
                    imported_names = [left_side]

        # Side-effect only if no assignment
        if not imported_names:
            import_type = 'side_effect_require'

        return ImportStatement(
            file_path=file_path,
            line_number=line_number,
            module_name=module_path,
            imported_names=imported_names,
            is_relative=module_path.startswith('.'),
            import_type=import_type,
            alias=None
        )


# Backward compatibility: Keep old function-based API
def extract_js_imports(file_path: Path) -> List[ImportStatement]:
    """Extract all import statements from JavaScript/TypeScript file.

    DEPRECATED: Use JavaScriptExtractor().extract_imports() instead.
    Kept for backward compatibility with existing code.
    """
    extractor = JavaScriptExtractor()
    return extractor.extract_imports(file_path)


__all__ = [
    'JavaScriptExtractor',
    'extract_js_imports',  # deprecated
]
