"""JavaScript/TypeScript import extraction.

Extracts import statements and require() calls from JavaScript and TypeScript files.
Supports ES6 imports, CommonJS require(), and dynamic import().
"""

import re
from pathlib import Path
from typing import List, Set

from . import ImportStatement
from .base import LanguageExtractor, register_extractor


@register_extractor
class JavaScriptExtractor(LanguageExtractor):
    """JavaScript/TypeScript import extractor using regex parsing.

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
        """Extract all import statements from JavaScript/TypeScript file.

        Args:
            file_path: Path to .js, .jsx, .ts, .tsx, .mjs, or .cjs file

        Returns:
            List of ImportStatement objects
        """
        try:
            content = file_path.read_text(encoding='utf-8')
        except (UnicodeDecodeError, FileNotFoundError):
            return []

        imports = []

        # Extract ES6 imports
        imports.extend(self._extract_es6_imports(file_path, content))

        # Extract CommonJS require()
        imports.extend(self._extract_require_imports(file_path, content))

        # Extract dynamic import()
        imports.extend(self._extract_dynamic_imports(file_path, content))

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

    @staticmethod
    def _extract_es6_imports(file_path: Path, content: str) -> List[ImportStatement]:
        """Extract ES6 import statements.

        Patterns:
            import foo from 'module'
            import { foo, bar } from 'module'
            import * as foo from 'module'
            import foo, { bar } from 'module'
            import 'module'  // side-effect only
        """
        imports = []

        # Match import statements (handles multiline)
        # Pattern: import ... from 'module' or import ... from "module"
        pattern = r'''
            ^\s*import\s+                     # import keyword
            (?:                                # non-capturing group
                (?:type\s+)?                   # optional 'type' keyword (TypeScript)
                (?:
                    (\{[^}]+\})|               # named imports { foo, bar }
                    (\*\s+as\s+\w+)|           # namespace import * as foo
                    (\w+)|                     # default import foo
                    ((?:\w+\s*,\s*)?           # default + named: foo, { bar }
                     \{[^}]+\})
                )\s*
                from\s+
            )?                                 # from clause is optional for side-effects
            ['"]([^'"]+)['"]                  # module path in quotes
        '''

        for match in re.finditer(pattern, content, re.MULTILINE | re.VERBOSE):
            module_path = match.group(5)  # Module path is always the last group

            # Determine line number
            line_number = content[:match.start()].count('\n') + 1

            # Determine imported names
            imported_names = []
            import_type = 'es6_import'
            alias = None

            # Named imports: { foo, bar }
            if match.group(1):
                # Extract names from { foo, bar as baz }
                names_str = match.group(1).strip('{}')
                for name in names_str.split(','):
                    name = name.strip()
                    # Handle 'foo as bar'
                    if ' as ' in name:
                        name = name.split(' as ')[0].strip()
                    if name:
                        imported_names.append(name)

            # Namespace import: * as foo
            elif match.group(2):
                import_type = 'namespace_import'
                # Extract alias from '* as foo'
                alias_match = re.search(r'\*\s+as\s+(\w+)', match.group(2))
                if alias_match:
                    imported_names = ['*']
                    alias = alias_match.group(1)

            # Default import: foo
            elif match.group(3):
                imported_names = [match.group(3)]
                import_type = 'default_import'

            # Default + named: foo, { bar }
            elif match.group(4):
                names_str = match.group(4)
                # Parse both default and named
                parts = names_str.split('{')
                if parts[0].strip():
                    imported_names.append(parts[0].strip().rstrip(','))
                if len(parts) > 1:
                    for name in parts[1].strip('}').split(','):
                        name = name.strip()
                        if ' as ' in name:
                            name = name.split(' as ')[0].strip()
                        if name:
                            imported_names.append(name)

            # Side-effect only: import './styles.css'
            else:
                import_type = 'side_effect_import'

            imports.append(ImportStatement(
                file_path=file_path,
                line_number=line_number,
                module_name=module_path,
                imported_names=imported_names,
                is_relative=module_path.startswith('.'),
                import_type=import_type,
                alias=alias
            ))

        return imports

    @staticmethod
    def _extract_require_imports(file_path: Path, content: str) -> List[ImportStatement]:
        """Extract CommonJS require() statements.

        Patterns:
            const foo = require('module')
            const { foo, bar } = require('module')
            require('module')  // side-effect only
        """
        imports = []

        # Pattern: require('module') or require("module")
        pattern = r'''
            (?:
                (?:const|let|var)\s+          # variable declaration
                (?:
                    (\w+)|                     # single assignment: foo
                    \{([^}]+)\}                # destructured: { foo, bar }
                )\s*=\s*
            )?
            require\s*\(\s*['"]([^'"]+)['"]\s*\)  # require('module')
        '''

        for match in re.finditer(pattern, content, re.VERBOSE):
            module_path = match.group(3)
            line_number = content[:match.start()].count('\n') + 1

            imported_names = []
            import_type = 'commonjs_require'

            # Single assignment: const foo = require('module')
            if match.group(1):
                imported_names = [match.group(1)]

            # Destructured: const { foo, bar } = require('module')
            elif match.group(2):
                for name in match.group(2).split(','):
                    name = name.strip()
                    # Handle renaming: { foo: bar }
                    if ':' in name:
                        name = name.split(':')[0].strip()
                    if name:
                        imported_names.append(name)

            # Side-effect only: require('module')
            else:
                import_type = 'side_effect_require'

            imports.append(ImportStatement(
                file_path=file_path,
                line_number=line_number,
                module_name=module_path,
                imported_names=imported_names,
                is_relative=module_path.startswith('.'),
                import_type=import_type,
                alias=None
            ))

        return imports

    @staticmethod
    def _extract_dynamic_imports(file_path: Path, content: str) -> List[ImportStatement]:
        """Extract dynamic import() expressions.

        Patterns:
            import('./module')
            await import('./module')
            const mod = await import('./module')
        """
        imports = []

        # Pattern: import('module') or import("module")
        pattern = r"import\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"

        for match in re.finditer(pattern, content):
            module_path = match.group(1)
            line_number = content[:match.start()].count('\n') + 1

            imports.append(ImportStatement(
                file_path=file_path,
                line_number=line_number,
                module_name=module_path,
                imported_names=[],
                is_relative=module_path.startswith('.'),
                import_type='dynamic_import',
                alias=None
            ))

        return imports


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
