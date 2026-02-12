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

        # Find identifier nodes (tree-sitter node type for names)
        identifier_nodes = analyzer._find_nodes_by_type('identifier')

        for node in identifier_nodes:
            # Extract the identifier text
            name = analyzer._get_node_text(node)

            # Filter out identifiers in assignment/definition contexts
            # We want to track usage, not definitions
            if self._is_usage_context(node):
                symbols.add(name)

            # Also handle member expression (foo.bar -> track 'foo')
            if node.parent and node.parent.type == 'member_expression':
                # Get root of member expression chain
                root = self._get_root_identifier(node.parent, analyzer)
                if root:
                    symbols.add(root)

        return symbols

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

    def _determine_call_type(self, node, analyzer) -> Optional[str]:
        """Determine if node is require() or dynamic import().

        Returns:
            'require', 'import', or None
        """
        for child in node.children:
            if child.type == 'identifier':
                text = analyzer._get_node_text(child)
                if text == 'require':
                    return 'require'
            elif child.type == 'import':
                return 'import'
        return None

    def _extract_module_path(self, node, analyzer) -> Optional[str]:
        """Extract module path from call arguments.

        Returns:
            Module path string or None
        """
        for child in node.children:
            if child.type == 'arguments':
                for arg in child.children:
                    if arg.type == 'string':
                        text = analyzer._get_node_text(arg)
                        return str(text).strip('"\'') if text is not None else None
        return None

    def _build_dynamic_import_statement(
        self, file_path: Path, line_number: int, module_path: str
    ) -> ImportStatement:
        """Build ImportStatement for dynamic import()."""
        return ImportStatement(
            file_path=file_path,
            line_number=line_number,
            module_name=module_path,
            imported_names=[],
            is_relative=module_path.startswith('.'),
            import_type='dynamic_import',
            alias=None
        )

    def _parse_destructured_names(self, left_side: str) -> List[str]:
        """Parse destructured import names from { foo, bar } pattern.

        Handles renaming: { foo: bar }
        """
        imported_names = []
        names_str = left_side.strip('{}')
        for name in names_str.split(','):
            name = name.strip()
            # Handle renaming: { foo: bar }
            if ':' in name:
                name = name.split(':')[0].strip()
            if name:
                imported_names.append(name)
        return imported_names

    def _extract_require_imported_names(self, node, analyzer) -> List[str]:
        """Extract imported names from require() variable declaration.

        Handles:
            const foo = require('module')           -> ['foo']
            const { foo, bar } = require('module')  -> ['foo', 'bar']
        """
        parent = node.parent
        if not parent or parent.type != 'variable_declarator':
            return []

        if not parent.children:
            return []

        left_side = analyzer._get_node_text(parent.children[0])

        # Destructured: { foo, bar }
        if left_side.startswith('{'):
            return self._parse_destructured_names(left_side)

        # Single assignment: foo
        return [left_side]

    def _build_require_import_statement(
        self, file_path: Path, line_number: int, module_path: str, imported_names: List[str]
    ) -> ImportStatement:
        """Build ImportStatement for CommonJS require()."""
        import_type = 'side_effect_require' if not imported_names else 'commonjs_require'

        return ImportStatement(
            file_path=file_path,
            line_number=line_number,
            module_name=module_path,
            imported_names=imported_names,
            is_relative=module_path.startswith('.'),
            import_type=import_type,
            alias=None
        )

    def _parse_require_call(self, node, file_path: Path, analyzer) -> Optional[ImportStatement]:
        """Parse CommonJS require() call using tree-sitter.

        Handles:
            const foo = require('module')
            const { foo, bar } = require('module')
            require('module')  // side-effect only
            await import('./module')  // dynamic import
        """
        # Determine call type
        func_name = self._determine_call_type(node, analyzer)
        if not func_name:
            return None

        # Extract module path
        module_path = self._extract_module_path(node, analyzer)
        if not module_path:
            return None

        line_number = node.start_point[0] + 1

        # Handle dynamic import
        if func_name == 'import':
            return self._build_dynamic_import_statement(file_path, line_number, module_path)

        # Handle CommonJS require
        imported_names = self._extract_require_imported_names(node, analyzer)
        return self._build_require_import_statement(file_path, line_number, module_path, imported_names)

    def _is_usage_context(self, node) -> bool:
        """Check if identifier node is in a usage context (not definition).

        Filters out:
        - Function/class/variable declarations
        - Parameter names
        - Assignment targets (left side)
        - Import names
        - Object property keys
        """
        if not node.parent:
            return True

        # Walk up the tree to check if we're inside an import statement
        current = node
        while current:
            if current.type == 'import_statement':
                return False
            current = current.parent

        parent_type = node.parent.type

        # Skip definition contexts
        if parent_type in ('function_declaration', 'class_declaration', 'method_definition',
                          'formal_parameters', 'required_parameter', 'optional_parameter',
                          'rest_parameter'):
            return False

        # For variable declarations, check if this is the identifier being declared
        if parent_type == 'variable_declarator':
            # First child is the name being declared
            if node.parent.children and node.parent.children[0] == node:
                return False

        # For member expressions like { key: value }, skip keys
        if parent_type == 'pair':
            # First child is the key
            if node.parent.children and node.parent.children[0] == node:
                return False

        # For import specifiers like { foo as bar }, both names are part of import
        if parent_type in ('import_specifier', 'namespace_import'):
            return False

        return True

    def _get_root_identifier(self, member_expr_node, analyzer) -> Optional[str]:
        """Extract root identifier from member expression chain.

        Examples:
            React.Component -> 'React'
            console.log -> 'console'
            foo.bar.baz -> 'foo'
        """
        # Walk up the member expression chain to find the root
        current = member_expr_node
        while current and current.type == 'member_expression':
            # Member expression has structure: object.property
            if current.children:
                current = current.children[0]  # Get 'object' part
            else:
                break

        # Current should now be an identifier
        if current and current.type == 'identifier':
            result = analyzer._get_node_text(current)
            return str(result) if result is not None else None

        return None

    def resolve_import(
        self,
        stmt: ImportStatement,
        base_path: Path
    ) -> Optional[Path]:
        """Resolve JavaScript/TypeScript import to file path.

        Args:
            stmt: Import statement to resolve
            base_path: Directory of the file containing the import

        Returns:
            Absolute path to the imported file, or None if not resolvable

        JavaScript module resolution:
        - Relative: './utils' -> ./utils.js, ./utils.ts, ./utils/index.js
        - Absolute: 'react', '@angular/core' -> node_modules (skip for cycles)
        - Extensions: .js, .jsx, .ts, .tsx, .mjs can be omitted
        """
        module_path = stmt.module_name

        # Skip absolute imports (node_modules packages)
        if not module_path.startswith('.'):
            return None

        # Resolve relative imports
        return self._resolve_relative_js(module_path, base_path)

    def _resolve_relative_js(self, module_path: str, base_path: Path) -> Optional[Path]:
        """Resolve relative JavaScript import to file path.

        Try in order:
        1. Exact path (if includes extension)
        2. With .js extension
        3. With .ts extension
        4. With .jsx extension
        5. With .tsx extension
        6. With .mjs extension
        7. As directory with index.js
        8. As directory with index.ts
        """
        # Clean up the path (remove leading ./)
        clean_path = module_path.lstrip('./')

        # Build target path
        target = base_path / clean_path

        # If path has extension, try exact match
        if '.' in clean_path.split('/')[-1]:
            if target.exists() and target.is_file():
                return target.resolve()
            return None

        # Try with common JavaScript extensions
        for ext in ['.js', '.ts', '.jsx', '.tsx', '.mjs']:
            file_path = base_path / f"{clean_path}{ext}"
            if file_path.exists() and file_path.is_file():
                return file_path.resolve()

        # Try as directory with index file
        for index_file in ['index.js', 'index.ts', 'index.jsx', 'index.tsx']:
            index_path = base_path / clean_path / index_file
            if index_path.exists() and index_path.is_file():
                return index_path.resolve()

        return None


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
