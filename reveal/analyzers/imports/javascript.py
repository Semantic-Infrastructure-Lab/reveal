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

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Set, Optional, Tuple

from .types import ImportStatement
from .base import ImportsDiskCache, LanguageExtractor, register_extractor
from ...registry import get_analyzer
from ...core import node_children as _children

logger = logging.getLogger(__name__)

# Cross-invocation disk cache (BACK-626, extending BACK-625 to JS/TS): same
# independent-reparse gap as PythonExtractor had -- extract_imports() does not
# share TreeSitterAnalyzer.get_structure()'s structure cache (BACK-535).
_IMPORTS_CACHE = ImportsDiskCache("javascript_imports")

# BACK-694: process-lifetime caches for tsconfig.json discovery/parsing.
# Keyed by directory (find) / tsconfig path (parsed aliases) so a project
# with thousands of files pays the walk-up + JSONC-parse cost once, not
# once per importing file.
_TSCONFIG_FIND_CACHE: Dict[str, Optional[Path]] = {}
_TSCONFIG_ALIAS_CACHE: Dict[str, Tuple[Optional[Path], Dict[str, List[str]]]] = {}

_JSONC_TOKEN_RE = re.compile(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*.*?\*/', re.DOTALL)
_TRAILING_COMMA_RE = re.compile(r',(\s*[}\]])')


def _strip_jsonc(text: str) -> str:
    """Strip // and /* */ comments from tsconfig.json's JSONC dialect, and
    drop trailing commas -- both are valid in tsconfig.json but not in
    strict JSON, and tsc/most editors accept them. String literals are
    matched and passed through verbatim so a comment marker inside a string
    is never mistaken for a real comment."""
    cleaned = []
    pos = 0
    for m in _JSONC_TOKEN_RE.finditer(text):
        cleaned.append(text[pos:m.start()])
        token = m.group(0)
        if token.startswith('"'):
            cleaned.append(token)
        # else: comment -- drop it
        pos = m.end()
    cleaned.append(text[pos:])
    return _TRAILING_COMMA_RE.sub(r'\1', ''.join(cleaned))


def _load_tsconfig_raw(path: Path) -> dict:
    """Parse one tsconfig.json's own compilerOptions (no `extends` chase)."""
    try:
        raw = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return {}
    try:
        data = json.loads(_strip_jsonc(raw))
    except (json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _find_tsconfig(start_dir: Path, stop_at: Optional[Path]) -> Optional[Path]:
    """Walk up from start_dir looking for tsconfig.json, never crossing
    above stop_at (the scan root passed in as search_paths[0] -- walking
    past it risks picking up an unrelated tsconfig.json from an enclosing
    directory outside the scanned project)."""
    key = f"{start_dir}|{stop_at}"
    if key in _TSCONFIG_FIND_CACHE:
        return _TSCONFIG_FIND_CACHE[key]
    current = start_dir.resolve()
    boundary = stop_at.resolve() if stop_at else None
    result = None
    while True:
        candidate = current / 'tsconfig.json'
        if candidate.is_file():
            result = candidate
            break
        if boundary is not None and current == boundary:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    _TSCONFIG_FIND_CACHE[key] = result
    return result


def _get_tsconfig_aliases(tsconfig_path: Path) -> Tuple[Optional[Path], Dict[str, List[str]]]:
    """(baseUrl, paths) declared directly in this tsconfig.json. Does NOT
    chase `extends` -- BACK-694's fix scope didn't require it for the
    corpora exercised (nest's tsconfig.json declares paths/baseUrl
    directly). A project whose *only* paths/baseUrl live in a base config
    reached via `extends` will still miss those aliases; a future BACK
    should walk the extends chain if that turns out to matter in practice."""
    key = str(tsconfig_path)
    if key in _TSCONFIG_ALIAS_CACHE:
        return _TSCONFIG_ALIAS_CACHE[key]
    data = _load_tsconfig_raw(tsconfig_path)
    co = data.get('compilerOptions')
    co = co if isinstance(co, dict) else {}
    paths = co.get('paths')
    paths = paths if isinstance(paths, dict) else {}
    base_url_raw = co.get('baseUrl')
    base_url: Optional[Path] = None
    if isinstance(base_url_raw, str):
        base_url = (tsconfig_path.parent / base_url_raw).resolve()
    elif paths:
        # `paths` without an explicit `baseUrl` resolves relative to the
        # tsconfig.json's own directory (TS default).
        base_url = tsconfig_path.parent.resolve()
    result = (base_url, paths)
    _TSCONFIG_ALIAS_CACHE[key] = result
    return result


def _match_tsconfig_path(module_path: str, base_url: Path, paths: Dict[str, List[str]]) -> List[Path]:
    """Candidate absolute targets (extension omitted) for module_path per
    tsconfig `paths`. Exact keys win outright; among wildcard (`@foo/*`)
    keys, the longest matching prefix wins, matching tsc's own resolution
    order."""
    if module_path in paths:
        return [base_url / target for target in paths[module_path]]

    best_key = None
    best_prefix_len = -1
    for key in paths:
        if '*' not in key:
            continue
        prefix, _, suffix = key.partition('*')
        if (module_path.startswith(prefix) and module_path.endswith(suffix)
                and len(module_path) >= len(prefix) + len(suffix)):
            if len(prefix) > best_prefix_len:
                best_prefix_len = len(prefix)
                best_key = (key, prefix, suffix)

    if not best_key:
        return []
    key, prefix, suffix = best_key
    matched = module_path[len(prefix): len(module_path) - len(suffix)] if suffix else module_path[len(prefix):]
    return [base_url / target.replace('*', matched) for target in paths[key]]


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

        Cached cross-invocation on disk (BACK-626), same pattern as
        PythonExtractor (BACK-625): a 2nd+ `reveal` command on an unchanged
        file skips the parse entirely.

        Args:
            file_path: Path to .js, .jsx, .ts, .tsx, .mjs, or .cjs file

        Returns:
            List of ImportStatement objects
        """
        return _IMPORTS_CACHE.get_or_compute(file_path, lambda: self._extract_imports_uncached(file_path))

    def _extract_imports_uncached(self, file_path: Path) -> List[ImportStatement]:
        try:
            analyzer_class = get_analyzer(str(file_path))
            if not analyzer_class:
                return []

            analyzer = analyzer_class(str(file_path))
            if not analyzer.tree:
                return []

        except Exception as e:
            logger.debug("extract_imports failed for %s: %s", file_path, e)
            return []

        imports = []

        # Extract ES6 import statements
        import_nodes = analyzer._find_nodes_by_type('import_statement')
        for node in import_nodes:
            imports.extend(self._parse_import_statement(node, file_path, analyzer))

        # Extract ES module re-exports: `export ... from '...'` (BACK-548).
        # Tree-sitter models these as export_statement, not import_statement, so
        # they were previously invisible to the import graph — a re-export barrel
        # (`export * from './x'`) never counted as importing './x', and depends://
        # systematically undercut the re-exported module's blast radius. A
        # re-export IS a dependency edge (the barrel pulls the module in to
        # re-expose it), so surface it as one.
        export_nodes = analyzer._find_nodes_by_type('export_statement')
        for node in export_nodes:
            result = self._parse_reexport_statement(node, file_path, analyzer)
            if result:
                imports.append(result)

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

        except Exception as e:
            logger.debug("extract_symbols failed for %s: %s", file_path, e)
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
            if node.parent() and node.parent().kind() == 'member_expression':
                # Get root of member expression chain
                root = self._get_root_identifier(node.parent(), analyzer)
                if root:
                    symbols.add(root)

        # TypeScript: type_identifier nodes appear in type annotation positions
        # (`: IFoo`, `<IFoo>`, `extends IFoo`). The _is_usage_context check is for
        # runtime identifiers; type positions are always usages, so we add them all.
        for node in analyzer._find_nodes_by_type('type_identifier'):
            symbols.add(analyzer._get_node_text(node))

        return symbols

    def _extract_module_path_from_import(self, node, analyzer) -> Optional[str]:
        """Extract module path from import statement node.

        Args:
            node: Import statement node
            analyzer: Analyzer instance for text extraction

        Returns:
            Module path or None
        """
        for child in _children(node):
            if child.kind() == 'string':
                # Get string content, strip quotes
                return str(analyzer._get_node_text(child)).strip("'\"")
        return None

    def _find_import_clause_node(self, node) -> Optional[Any]:
        """Find import_clause node in import statement.

        Args:
            node: Import statement node

        Returns:
            import_clause node or None
        """
        for child in _children(node):
            if child.kind() == 'import_clause':
                return child
        return None

    def _parse_named_imports_child(self, child, analyzer) -> list:
        """Extract imported names from a named_imports node."""
        names = []
        for subchild in _children(child):
            if subchild.kind() == 'import_specifier':
                spec_children = _children(subchild)
                if spec_children:
                    names.append(analyzer._get_node_text(spec_children[0]))
        return names

    def _parse_import_clause_data(self, import_clause, analyzer) -> tuple:
        """Parse import_clause to extract names, type, and alias.

        Args:
            import_clause: import_clause node
            analyzer: Analyzer instance

        Returns:
            Tuple of (imported_names, import_type, alias)
        """
        imported_names = []
        import_type = 'es6_import'
        alias = None

        for child in _children(import_clause):
            if child.kind() == 'namespace_import':
                import_type = 'namespace_import'
                imported_names = ['*']
                id_node = next((sc for sc in _children(child) if sc.kind() == 'identifier'), None)
                alias = analyzer._get_node_text(id_node) if id_node else None

            elif child.kind() == 'named_imports':
                # import { foo, bar } from 'module'
                imported_names.extend(self._parse_named_imports_child(child, analyzer))

            elif child.kind() == 'identifier':
                # Default import: import foo from 'module'
                imported_names.insert(0, analyzer._get_node_text(child))
                if import_type == 'es6_import':
                    import_type = 'default_import'

        return imported_names, import_type, alias

    def _parse_import_statement(self, node, file_path: Path, analyzer) -> List[ImportStatement]:
        """Parse ES6 import statement using tree-sitter AST.

        Tree-sitter provides structured nodes:
            import foo from 'module'                # import_clause with identifier
            import { foo, bar } from 'module'       # import_clause with named_imports
            import * as foo from 'module'           # import_clause with namespace_import
            import foo, { bar } from 'module'       # import_clause with both
            import 'module'                         # just string node (side-effect)
        """
        line_number = node.start_position().row + 1

        # Extract module path
        module_path = self._extract_module_path_from_import(node, analyzer)
        if not module_path:
            return []

        # Find and parse import_clause
        import_clause = self._find_import_clause_node(node)

        if not import_clause:
            # Side-effect import: no import_clause
            import_type = 'side_effect_import'
            imported_names = []
            alias = None
        else:
            imported_names, import_type, alias = self._parse_import_clause_data(import_clause, analyzer)

        return [ImportStatement(
            file_path=file_path,
            line_number=line_number,
            module_name=module_path,
            imported_names=imported_names,
            is_relative=module_path.startswith('.'),
            import_type=import_type,
            alias=alias,
            source_line=_line_text(analyzer, line_number),
        )]

    def _parse_reexport_statement(self, node, file_path: Path, analyzer) -> Optional[ImportStatement]:
        """Parse an ES module re-export `export ... from '...'` into an import edge (BACK-548).

        Only export_statements with a string source are re-exports; a local
        `export const x = 1` / `export function f(){}` has no source module and is
        skipped (returns None). Handled forms:
            export * from './x'              # star re-export (barrel)
            export * as ns from './x'        # namespace re-export
            export { a, b } from './x'       # named re-export
            export { a as c } from './x'     # aliased named re-export

        Marked skip_unused: a re-export is itself the usage (the barrel's public
        API — same rationale as the __init__.py re-export pattern), so it must not
        be flagged as an unused import.
        """
        module_path = self._extract_module_path_from_import(node, analyzer)
        if not module_path:
            return None  # local export (`export const ...`), not a re-export edge

        imported_names: List[str] = []
        for child in _children(node):
            kind = child.kind()
            if kind in ('*', 'namespace_export'):
                imported_names = ['*']
            elif kind == 'export_clause':
                for spec in _children(child):
                    if spec.kind() == 'export_specifier':
                        spec_children = _children(spec)
                        if spec_children:
                            imported_names.append(analyzer._get_node_text(spec_children[0]))

        line_number = node.start_position().row + 1
        return ImportStatement(
            file_path=file_path,
            line_number=line_number,
            module_name=module_path,
            imported_names=imported_names,
            is_relative=module_path.startswith('.'),
            import_type='re_export',
            alias=None,
            source_line=_line_text(analyzer, line_number),
            skip_unused=True,
        )

    def _determine_call_type(self, node, analyzer) -> Optional[str]:
        """Determine if node is require() or dynamic import().

        Returns:
            'require', 'import', or None
        """
        for child in _children(node):
            if child.kind() == 'identifier':
                text = analyzer._get_node_text(child)
                if text == 'require':
                    return 'require'
            elif child.kind() == 'import':
                return 'import'
        return None

    def _extract_module_path(self, node, analyzer) -> Optional[str]:
        """Extract module path from call arguments.

        Returns:
            Module path string or None
        """
        args_node = next((c for c in _children(node) if c.kind() == 'arguments'), None)
        if args_node:
            str_node = next((a for a in _children(args_node) if a.kind() == 'string'), None)
            if str_node:
                text = analyzer._get_node_text(str_node)
                return str(text).strip('"\'') if text is not None else None
        return None

    def _build_dynamic_import_statement(
        self, file_path: Path, line_number: int, module_path: str, analyzer=None
    ) -> ImportStatement:
        """Build ImportStatement for dynamic import()."""
        return ImportStatement(
            file_path=file_path,
            line_number=line_number,
            module_name=module_path,
            imported_names=[],
            is_relative=module_path.startswith('.'),
            import_type='dynamic_import',
            alias=None,
            source_line=_line_text(analyzer, line_number) if analyzer else "",
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
        parent = node.parent()
        if not parent or parent.kind() != 'variable_declarator':
            return []

        if not parent.child_count():
            return []

        left_side = analyzer._get_node_text(parent.child(0))

        # Destructured: { foo, bar }
        if left_side.startswith('{'):
            return self._parse_destructured_names(left_side)

        # Single assignment: foo
        return [left_side]

    def _build_require_import_statement(
        self, file_path: Path, line_number: int, module_path: str, imported_names: List[str], analyzer=None
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
            alias=None,
            source_line=_line_text(analyzer, line_number) if analyzer else "",
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

        line_number = node.start_position().row + 1

        # Handle dynamic import
        if func_name == 'import':
            return self._build_dynamic_import_statement(file_path, line_number, module_path, analyzer)

        # Handle CommonJS require
        imported_names = self._extract_require_imported_names(node, analyzer)
        return self._build_require_import_statement(file_path, line_number, module_path, imported_names, analyzer)

    def _is_usage_context(self, node) -> bool:
        """Check if identifier node is in a usage context (not definition).

        Filters out:
        - Function/class/variable declarations
        - Parameter names
        - Assignment targets (left side)
        - Import names
        - Object property keys
        """
        if not node.parent():
            return True

        parent_type = node.parent().kind()

        # Skip definition contexts
        if parent_type in ('function_declaration', 'class_declaration', 'method_definition',
                          'formal_parameters', 'required_parameter', 'optional_parameter',
                          'rest_parameter'):
            return False

        # For variable declarations, check if this is the identifier being declared
        if parent_type == 'variable_declarator':
            # First child is the name being declared
            _p = node.parent()
            if _p and _p.child_count() > 0 and _p.child(0).start_byte() == node.start_byte():
                return False

        # For member expressions like { key: value }, skip keys
        if parent_type == 'pair':
            # First child is the key
            _p = node.parent()
            if _p and _p.child_count() > 0 and _p.child(0).start_byte() == node.start_byte():
                return False

        # Import bindings — default (`import Foo from 'x'`, parent import_clause),
        # named (`{ foo as bar }`, parent import_specifier), and namespace
        # (`* as NS`, parent namespace_import) — are declarations, not usages.
        if parent_type in ('import_clause', 'import_specifier', 'namespace_import'):
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
        while current and current.kind() == 'member_expression':
            # Member expression has structure: object.property
            if _children(current):
                current = current.child(0)  # Get 'object' part
            else:
                break

        # Current should now be an identifier
        if current and current.kind() == 'identifier':
            result = analyzer._get_node_text(current)
            return str(result) if result is not None else None

        return None

    def resolve_import(
        self,
        stmt: ImportStatement,
        base_path: Path,
        search_paths: Optional[List[Path]] = None,
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

        BACK-694: a non-relative specifier is tried against the nearest
        tsconfig.json's `compilerOptions.paths`/`baseUrl` alias map before
        being declined -- in a workspace monorepo with no `node_modules`
        packages installed (e.g. pnpm/lerna), that alias map is the *only*
        way `@scope/pkg`-style cross-package imports resolve; a genuine npm
        dependency (no matching alias) still correctly returns None.
        """
        module_path = stmt.module_name

        if not module_path.startswith('.'):
            return self._resolve_via_tsconfig(module_path, base_path, search_paths)

        # Resolve relative imports
        return self._resolve_relative_js(module_path, base_path)

    def is_intra_project_import(
        self,
        stmt: ImportStatement,
        base_path: Path,
        search_paths: Optional[List[Path]] = None,
        project_namespaces: Optional[Set[str]] = None,
    ) -> Optional[bool]:
        """A relative specifier (`./x`, `../x`) is intra-project; a bare
        specifier (`react`, `@angular/core`) is an npm dependency (external)
        UNLESS it matches a tsconfig `paths` alias (BACK-694), in which case
        it's intra-project by the project's own configuration even when
        resolve_import ultimately can't find the target file -- that case
        must count as a real miss (honest-decline), not a silent external
        classification that hides the gap from confidence/known_limits."""
        module_path = stmt.module_name
        if module_path.startswith('.'):
            return True
        if self._tsconfig_alias_matches(module_path, base_path, search_paths):
            return True
        return False

    def _resolve_via_tsconfig(
        self, module_path: str, base_path: Path, search_paths: Optional[List[Path]],
    ) -> Optional[Path]:
        """Resolve a bare specifier via the nearest tsconfig.json's
        `paths`/`baseUrl` alias map. Returns None if no tsconfig is found,
        it declares no `paths`, or no alias matches -- all of which mean
        "genuine external dependency", not a resolution failure."""
        base_url, paths = self._tsconfig_aliases_for(base_path, search_paths)
        if base_url is None or not paths:
            return None
        for candidate_base in _match_tsconfig_path(module_path, base_url, paths):
            resolved = self._resolve_target_path(candidate_base)
            if resolved:
                return resolved
        return None

    def _tsconfig_alias_matches(
        self, module_path: str, base_path: Path, search_paths: Optional[List[Path]],
    ) -> bool:
        """Whether module_path matches a tsconfig `paths` alias pattern,
        independent of whether the aliased target actually resolves to a
        file on disk."""
        base_url, paths = self._tsconfig_aliases_for(base_path, search_paths)
        if base_url is None or not paths:
            return False
        return bool(_match_tsconfig_path(module_path, base_url, paths))

    @staticmethod
    def _tsconfig_aliases_for(
        base_path: Path, search_paths: Optional[List[Path]],
    ) -> Tuple[Optional[Path], Dict[str, List[str]]]:
        stop_at = search_paths[0] if search_paths else None
        tsconfig_path = _find_tsconfig(base_path, stop_at)
        if not tsconfig_path:
            return None, {}
        return _get_tsconfig_aliases(tsconfig_path)

    # TS ESM idiom: source imports use the compiled-output extension
    # (e.g. `./foo.js`) while the source file on disk is `.ts`/`.tsx`/`.mts`.
    _TS_ESM_EXTENSION_FALLBACKS = {
        '.js': ['.ts', '.tsx'],
        '.jsx': ['.tsx'],
        '.mjs': ['.mts'],
    }

    def _resolve_relative_js(self, module_path: str, base_path: Path) -> Optional[Path]:
        """Resolve relative JavaScript import to file path.

        Try in order:
        1. Exact path (if includes extension)
        2. If extension is .js/.jsx/.mjs, TS-ESM fallback (.ts/.tsx/.mts)
        3. With .js extension
        4. With .ts extension
        5. With .jsx extension
        6. With .tsx extension
        7. With .mjs extension
        8. As directory with index.js
        9. As directory with index.ts
        """
        # Strip a leading './' only — str.lstrip('./') strips *characters*,
        # not the prefix, so it was mangling '../foo' and '../../foo' into
        # bare 'foo' (every leading '.'/'/' character stripped), silently
        # resolving multi-level parent imports against the wrong directory.
        # '../' must be preserved so base_path / clean_path navigates up.
        clean_path = module_path[2:] if module_path.startswith('./') else module_path
        return self._resolve_target_path(base_path / clean_path)

    def _resolve_target_path(self, target: Path) -> Optional[Path]:
        """Resolve a target path (extension possibly omitted, or a directory
        implying an index file) to an actual file on disk. Shared by
        relative-import resolution and tsconfig `paths`-alias resolution
        (BACK-694) -- both land on "here's a path, extension/index unknown"
        and need the identical extension/TS-ESM/index-file cascade.

        Try in order:
        1. Exact path (if includes extension)
        2. If extension is .js/.jsx/.mjs, TS-ESM fallback (.ts/.tsx/.mts)
        3. With .js extension
        4. With .ts extension
        5. With .jsx extension
        6. With .tsx extension
        7. With .mjs extension
        8. As directory with index.js
        9. As directory with index.ts
        """
        # If path has extension, try exact match.
        # BACK-556: a bare '.' or '..' specifier (self/parent-directory
        # barrel import, e.g. `import { x } from '..'`) has a last path
        # segment that is ALL dots — '.' in that segment is true, but it's
        # not an extension, it's the whole directory reference. Treating it
        # as "has extension" made this branch return None before ever
        # reaching the directory/index-file resolution below, silently
        # dropping every bare '.'/'..' barrel import (confirmed on the VS
        # Code corpus: codeReferencing/citationManager.ts imports `from
        # '.'`, notebook-renderers/test/notebookRenderer.test.ts imports
        # `from '..'` — both missed before this fix).
        last_segment = target.name
        has_extension = '.' in last_segment and last_segment not in ('.', '..')
        if has_extension:
            if target.exists() and target.is_file():
                return target.resolve()

            # TS ESM idiom: `import './foo.js'` resolving to `foo.ts` on disk
            suffix = target.suffix
            if suffix in self._TS_ESM_EXTENSION_FALLBACKS:
                # String slicing, not Path.with_suffix(): with_suffix() strips
                # only the last dot-segment of the *whole* name, so a
                # multi-dot filename like 'foo.contribution.js' would lose
                # '.contribution' too (target.with_suffix('') -> 'foo', not
                # 'foo.contribution') — a real VS Code naming convention.
                stem_str = str(target)[: -len(suffix)]
                for fallback_ext in self._TS_ESM_EXTENSION_FALLBACKS[suffix]:
                    fallback_path = Path(stem_str + fallback_ext)
                    if fallback_path.exists() and fallback_path.is_file():
                        return fallback_path.resolve()

            # BACK-621: don't bail here. `has_extension` is a heuristic on the
            # last path segment containing a dot — it can't distinguish a real
            # extension from a dotted basename with the extension omitted
            # (e.g. './charts.constants' -> charts.constants.ts, or
            # './WelcomeScreen.Center' -> WelcomeScreen.Center.tsx, both real
            # Excalidraw import specifiers). Fall through to the same
            # extension-append / directory-index resolution used below for
            # specifiers with no dot at all, instead of returning None.

        # Try with common JavaScript extensions
        for ext in ['.js', '.ts', '.jsx', '.tsx', '.mjs']:
            file_path = Path(str(target) + ext)
            if file_path.exists() and file_path.is_file():
                return file_path.resolve()

        # Try as directory with index file
        for index_file in ['index.js', 'index.ts', 'index.jsx', 'index.tsx']:
            index_path = target / index_file
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
