"""JavaScript/TypeScript import extraction using tree-sitter.

Previous implementation: Tree-sitter + 5 regex patterns for parsing
Current implementation: Pure tree-sitter AST extraction

Benefits:
- Eliminates all regex patterns (module path, namespace alias, type keyword, named imports, default import)
- Uses tree-sitter node types (import_clause, namespace_import, named_imports, import_specifier)
- More robust handling of TypeScript and ES6 syntax variations

Extracts import statements and require() calls from JavaScript and TypeScript files.
Uses tree-sitter for consistent parsing across all language analyzers.
"""

from pathlib import Path
from typing import List, Set, Optional

from . import ImportStatement
from .base import LanguageExtractor, register_extractor
from ...registry import get_analyzer


@register_extractor
class JavaScriptExtractor(LanguageExtractor):
    """JavaScript/TypeScript import extractor using pure tree-sitter parsing.

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
        """Parse ES6 import statement using tree-sitter AST.

        Tree-sitter provides structured nodes:
            import foo from 'module'                # import_clause with identifier
            import { foo, bar } from 'module'       # import_clause with named_imports
            import * as foo from 'module'           # import_clause with namespace_import
            import foo, { bar } from 'module'       # import_clause with both
            import 'module'                         # just string node (side-effect)
        """
        line_number = node.start_point[0] + 1

        # Extract module path from string node
        module_path = None
        for child in node.children:
            if child.type == 'string':
                # Get string content, strip quotes
                module_path = analyzer._get_node_text(child).strip('"\'')
                break

        if not module_path:
            return []

        # Determine import type and extract imported names
        imported_names = []
        import_type = 'es6_import'
        alias = None

        # Find import_clause node
        import_clause = None
        for child in node.children:
            if child.type == 'import_clause':
                import_clause = child
                break

        # Side-effect import: no import_clause
        if not import_clause:
            import_type = 'side_effect_import'
        else:
            # Parse import_clause children
            for child in import_clause.children:
                if child.type == 'namespace_import':
                    # import * as foo from 'module'
                    import_type = 'namespace_import'
                    imported_names = ['*']
                    # Extract alias (identifier after 'as')
                    for subchild in child.children:
                        if subchild.type == 'identifier':
                            alias = analyzer._get_node_text(subchild)

                elif child.type == 'named_imports':
                    # import { foo, bar } from 'module'
                    for subchild in child.children:
                        if subchild.type == 'import_specifier':
                            # Can be "foo" or "foo as bar"
                            spec_children = list(subchild.children)
                            if spec_children:
                                # First identifier is the imported name
                                imported_names.append(analyzer._get_node_text(spec_children[0]))

                elif child.type == 'identifier':
                    # Default import: import foo from 'module'
                    imported_names.insert(0, analyzer._get_node_text(child))
                    if import_type == 'es6_import':
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
        module_match = self.MODULE_PATH_PATTERN.search(call_text)
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
