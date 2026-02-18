"""imports:// adapter - Import graph analysis.

Analyze import relationships in codebases:
- List all imports in a directory
- Detect unused imports (?unused)
- Find circular dependencies (?circular)
- Validate layer violations (?violations)

Usage:
    reveal imports://src                     # All imports
    reveal 'imports://src?unused'            # Find unused
    reveal 'imports://src?circular'          # Find cycles
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional
from urllib.parse import urlparse

from .base import ResourceAdapter, register_adapter, register_renderer
from .help_data import load_help_data
from ..analyzers.imports import ImportGraph, ImportStatement


class ImportsRenderer:
    """Renderer for import analysis results."""

    @staticmethod
    def _render_unused_imports(result: dict, verbose: bool) -> None:
        """Render unused imports results."""
        count = result['count']
        print(f"\n{'='*60}")
        print(f"Unused Imports: {count}")
        print(f"{'='*60}\n")

        if count == 0:
            print("  ✅ No unused imports found!\n")
        else:
            if verbose:
                for imp in result['unused']:
                    print(f"  {imp['file']}:{imp['line']} - {imp['module']}")
            else:
                for imp in result['unused'][:10]:
                    print(f"  {imp['file']}:{imp['line']} - {imp['module']}")
                if count > 10:
                    print(f"\n  ... and {count - 10} more unused imports")
                    print(f"  Run with --verbose to see all {count} unused imports\n")

    @staticmethod
    def _render_circular_dependencies(result: dict, verbose: bool) -> None:
        """Render circular dependency results."""
        count = result['count']
        print(f"\n{'='*60}")
        print(f"Circular Dependencies: {count}")
        print(f"{'='*60}\n")

        if count == 0:
            print("  ✅ No circular dependencies found!\n")
        else:
            if verbose:
                for i, cycle in enumerate(result['cycles'], 1):
                    print(f"  {i}. {' -> '.join(cycle)}")
            else:
                for i, cycle in enumerate(result['cycles'][:5], 1):
                    print(f"  {i}. {' -> '.join(cycle)}")
                if count > 5:
                    print(f"\n  ... and {count - 5} more circular dependencies")
                    print(f"  Run with --verbose to see all {count} cycles\n")

    @staticmethod
    def _render_layer_violations(result: dict, verbose: bool) -> None:
        """Render layer violation results."""
        count = result['count']
        print(f"\n{'='*60}")
        print(f"Layer Violations: {count}")
        print(f"{'='*60}\n")

        if count == 0:
            print(f"  ✅ {result.get('note', 'No violations found')}\n")
        else:
            violations = result.get('violations', [])
            if verbose:
                for v in violations:
                    print(f"  {v['file']}:{v['line']} - {v['message']}")
            else:
                for v in violations[:10]:
                    print(f"  {v['file']}:{v['line']} - {v['message']}")
                if count > 10:
                    print(f"\n  ... and {count - 10} more violations")
                    print(f"  Run with --verbose to see all {count} violations\n")

    @staticmethod
    def _render_import_summary(result: dict, resource: str) -> None:
        """Render import analysis summary."""
        metadata = result.get('metadata', {})
        total_files = metadata.get('total_files', 0)
        total_imports = metadata.get('total_imports', 0)
        has_cycles = metadata.get('has_cycles', False)

        print(f"\n{'='*60}")
        print(f"Import Analysis: {resource}")
        print(f"{'='*60}\n")
        print(f"  Total Files:   {total_files}")
        print(f"  Total Imports: {total_imports}")
        if total_files <= 1:
            print(f"  Cycles Found:  N/A (single-file scan — use imports://dir/ to detect cycles)")
        else:
            print(f"  Cycles Found:  {'❌ Yes' if has_cycles else '✅ No'}")
        print()
        print(f"Query options:")
        print(f"  reveal 'imports://{resource}?unused'    - Find unused imports")
        print(f"  reveal 'imports://{resource}?circular'  - Detect circular deps")
        print(f"  reveal 'imports://{resource}?violations' - Check layer violations")
        print()

    @staticmethod
    def render_structure(result: dict, format: str = 'text', verbose: bool = False, resource: str = '.') -> None:
        """Render import analysis results.

        Args:
            result: Structure dict from ImportsAdapter.get_structure()
            format: Output format ('text', 'json')
            verbose: Show detailed results
            resource: Resource path for display
        """
        if format == 'json':
            from ..main import safe_json_dumps
            print(safe_json_dumps(result))
            return

        # Text format with progressive disclosure
        if 'type' in result:
            result_type = result['type']
            if result_type == 'unused_imports':
                ImportsRenderer._render_unused_imports(result, verbose)
            elif result_type == 'circular_dependencies':
                ImportsRenderer._render_circular_dependencies(result, verbose)
            elif result_type == 'layer_violations':
                ImportsRenderer._render_layer_violations(result, verbose)
            else:
                ImportsRenderer._render_import_summary(result, resource)
        else:
            from ..main import safe_json_dumps
            print(safe_json_dumps(result))

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        """Render file-specific imports.

        Args:
            result: Element dict from ImportsAdapter.get_element()
            format: Output format ('text', 'json')
        """
        if format == 'json':
            from ..main import safe_json_dumps
            print(safe_json_dumps(result))
            return

        # Text format - file imports
        print(f"Imports for: {result.get('file', 'unknown')}")
        imports = result.get('imports', [])
        if imports:
            for imp in imports:
                print(f"  • {imp['module']} (line {imp['line']})")
        else:
            print("  No imports found")

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render user-friendly errors."""
        print(f"Error analyzing imports: {error}", file=sys.stderr)


from ..analyzers.imports.base import get_extractor, get_all_extensions, get_supported_languages


@register_adapter('imports')
@register_renderer(ImportsRenderer)
class ImportsAdapter(ResourceAdapter):
    """Analyze import relationships in codebases."""

    def __init__(self):
        """Initialize imports adapter."""
        self._graph: Optional[ImportGraph] = None
        self._symbols_by_file: Dict[Path, set] = {}
        self._target_path: Optional[Path] = None

    def get_structure(self, uri: str = '', **kwargs) -> Dict[str, Any]:
        """Analyze imports in directory or file.

        Args:
            uri: imports:// URI (e.g., 'imports://src?unused')
            **kwargs: Additional parameters

        Returns:
            Dictionary with import analysis results
        """
        # Parse URI
        parsed = urlparse(uri if uri else 'imports://')

        # Handle both absolute and relative paths:
        # - imports:///absolute/path → netloc='', path='/absolute/path' → use path as-is
        # - imports://relative/path  → netloc='relative', path='/path' → combine netloc + path
        # - imports://. or imports:// → netloc='', path='' → use current dir
        if parsed.netloc:
            # Relative path with host component (imports://reveal/path)
            path_str = f"{parsed.netloc}{parsed.path}"
        elif parsed.path:
            # Absolute path (imports:///absolute/path)
            path_str = parsed.path
        else:
            # Default to current directory
            path_str = '.'

        # Parse query params - support both flag-style (?circular) and key-value (?circular=true)
        query_params: Dict[str, str | bool] = {}
        if parsed.query:
            for param in parsed.query.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    query_params[key] = value
                else:
                    query_params[param] = True

        # Resolve target path
        target_path = Path(path_str).resolve()

        if not target_path.exists():
            return {
                'error': f"Path not found: {path_str}",
                'uri': uri
            }

        # Extract imports and build graph
        self._target_path = target_path
        self._build_graph(target_path)

        # Handle query parameters
        if 'unused' in query_params or kwargs.get('unused'):
            return self._format_unused()
        elif 'circular' in query_params or kwargs.get('circular'):
            return self._format_circular()
        elif 'violations' in query_params or kwargs.get('violations'):
            return self._format_violations()
        else:
            return self._format_all()

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get imports for a specific file.

        Args:
            element_name: File name (e.g., 'main.py')
            **kwargs: Additional parameters

        Returns:
            Dictionary with imports for that file
        """
        if not self._graph:
            return None

        # Find matching file
        for file_path, imports in self._graph.files.items():
            if file_path.name == element_name:
                return {
                    'file': str(file_path),
                    'imports': [self._format_import(stmt) for stmt in imports],
                    'count': len(imports)
                }

        return None

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about import analysis."""
        if not self._graph:
            return {'status': 'not_analyzed'}

        return {
            'total_imports': self._graph.get_import_count(),
            'total_files': self._graph.get_file_count(),
            'has_cycles': len(self._graph.find_cycles()) > 0,
            'analyzer': 'imports',
            'version': '0.30.0'
        }

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for imports:// adapter.

        Returns JSON schema for AI agent integration.
        """
        return {
            'adapter': 'imports',
            'description': 'Import graph analysis for detecting unused imports, circular dependencies, and layer violations',
            'uri_syntax': 'imports://<path>[?query]',
            'query_params': {
                'unused': {
                    'type': 'flag',
                    'description': 'Find unused imports in codebase',
                    'examples': ['imports://src?unused']
                },
                'circular': {
                    'type': 'flag',
                    'description': 'Detect circular dependencies',
                    'examples': ['imports://src?circular']
                },
                'violations': {
                    'type': 'flag',
                    'description': 'Check for layer violations (requires config)',
                    'examples': ['imports://src?violations']
                }
            },
            'elements': {},  # File names can be used as elements
            'cli_flags': [
                '--verbose'  # Show detailed results
            ],
            'supports_batch': False,
            'supports_advanced': False,
            'supported_languages': get_supported_languages(),
            'output_types': [
                {
                    'type': 'import_summary',
                    'description': 'Overview of all imports in codebase',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'import_summary'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string'},
                            'metadata': {
                                'type': 'object',
                                'properties': {
                                    'total_files': {'type': 'integer'},
                                    'total_imports': {'type': 'integer'},
                                    'has_cycles': {'type': 'boolean'}
                                }
                            }
                        }
                    }
                },
                {
                    'type': 'unused_imports',
                    'description': 'List of unused imports with file locations',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'unused_imports'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string'},
                            'count': {'type': 'integer'},
                            'unused': {
                                'type': 'array',
                                'items': {
                                    'type': 'object',
                                    'properties': {
                                        'file': {'type': 'string'},
                                        'line': {'type': 'integer'},
                                        'module': {'type': 'string'}
                                    }
                                }
                            }
                        }
                    }
                },
                {
                    'type': 'circular_dependencies',
                    'description': 'Detected circular import cycles',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'circular_dependencies'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string'},
                            'count': {'type': 'integer'},
                            'cycles': {
                                'type': 'array',
                                'items': {
                                    'type': 'array',
                                    'items': {'type': 'string'}
                                }
                            }
                        }
                    }
                },
                {
                    'type': 'layer_violations',
                    'description': 'Architectural layer violations',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'layer_violations'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string'},
                            'count': {'type': 'integer'},
                            'violations': {
                                'type': 'array',
                                'items': {
                                    'type': 'object',
                                    'properties': {
                                        'file': {'type': 'string'},
                                        'line': {'type': 'integer'},
                                        'message': {'type': 'string'}
                                    }
                                }
                            }
                        }
                    }
                }
            ],
            'example_queries': [
                {
                    'uri': 'imports://src',
                    'description': 'Analyze all imports in src directory',
                    'output_type': 'import_summary'
                },
                {
                    'uri': 'imports://src?unused',
                    'description': 'Find unused imports',
                    'cli_flag': '?unused',
                    'output_type': 'unused_imports'
                },
                {
                    'uri': 'imports://src?circular',
                    'description': 'Detect circular dependencies',
                    'cli_flag': '?circular',
                    'output_type': 'circular_dependencies'
                },
                {
                    'uri': 'imports://src?violations',
                    'description': 'Check layer violations',
                    'cli_flag': '?violations',
                    'output_type': 'layer_violations'
                }
            ],
            'notes': [
                'Supports multiple languages via plugin architecture',
                'Circular dependencies can indicate architectural issues',
                'Layer violations require .reveal.yaml configuration',
                'Unused import detection works with Python, JavaScript, Go, etc.'
            ]
        }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for imports:// adapter.

        Help data loaded from reveal/adapters/help_data/imports.yaml
        to improve consistency and maintainability.
        """
        help_data = load_help_data('imports') or {}
        # Add dynamic supported languages to help data
        if help_data:
            help_data['supported_languages'] = get_supported_languages()
        return help_data

    def _build_graph(self, target_path: Path) -> None:
        """Build import graph from target path (multi-language).

        Uses plugin-based architecture to automatically detect and use
        appropriate extractor for each file type.

        Args:
            target_path: Directory or file to analyze
        """
        if target_path.is_file():
            files = [target_path]
        else:
            # Collect all supported file types using registry
            files = []
            for ext in get_all_extensions():
                pattern = f'*{ext}'
                files.extend(target_path.rglob(pattern))

        # Extract imports from all files using appropriate extractor
        all_imports = []
        for file_path in files:
            extractor = get_extractor(file_path)
            if not extractor:
                # Unknown file type, skip
                continue

            # Extract imports and symbols using language-specific extractor
            imports = extractor.extract_imports(file_path)
            symbols = extractor.extract_symbols(file_path)

            # Also extract exports (__all__) - imports listed in __all__ are re-exports
            # and should not be flagged as unused
            if hasattr(extractor, 'extract_exports'):
                exports = extractor.extract_exports(file_path)
                # Merge exports into symbols to prevent false positives
                symbols = symbols | exports

            self._symbols_by_file[file_path] = symbols
            all_imports.extend(imports)

        # Build graph
        self._graph = ImportGraph.from_imports(all_imports)

        # Resolve imports to build dependency edges (language-specific)
        for file_path, imports in self._graph.files.items():
            extractor = get_extractor(file_path)
            if not extractor:
                continue

            base_path = file_path.parent
            for stmt in imports:
                # Skip TYPE_CHECKING imports - they're type-checking only, not runtime
                # circular dependencies (this is a standard Python pattern to avoid real cycles)
                if stmt.is_type_checking:
                    continue

                resolved = extractor.resolve_import(stmt, base_path)
                # Skip self-references (e.g., logging.py importing stdlib logging
                # should not create logging.py → logging.py dependency)
                if resolved and resolved != file_path:
                    self._graph.add_dependency(file_path, resolved)
                    self._graph.resolved_paths[stmt.module_name] = resolved

    def _build_response(self, response_type: str, **data_fields) -> Dict[str, Any]:
        """Build standardized adapter response with common structure.

        Args:
            response_type: Type of response (e.g., 'imports', 'unused_imports')
            **data_fields: Data fields to include in response

        Returns:
            Standardized response dict with contract_version, type, source, etc.
        """
        response: Dict[str, Any] = {
            'contract_version': '1.0',
            'type': response_type,
            'source': str(self._target_path),
            'source_type': 'directory' if self._target_path and self._target_path.is_dir() else 'file',
        }
        response.update(data_fields)
        response['metadata'] = self.get_metadata()
        return response

    def _format_all(self) -> Dict[str, Any]:
        """Format all imports (default view)."""
        if not self._graph:
            return {'imports': []}

        imports_by_file = {
            str(file_path): [self._format_import(stmt) for stmt in imports]
            for file_path, imports in self._graph.files.items()
        }

        return self._build_response('imports', files=imports_by_file)

    def _format_unused(self) -> Dict[str, Any]:
        """Format unused imports."""
        if not self._graph:
            return {'unused': []}

        unused = self._graph.find_unused_imports(self._symbols_by_file)

        return self._build_response(
            'unused_imports',
            unused=[self._format_import(stmt) for stmt in unused],
            count=len(unused)
        )

    def _format_circular(self) -> Dict[str, Any]:
        """Format circular dependencies."""
        if not self._graph:
            return {'cycles': []}

        cycles = self._graph.find_cycles()

        return self._build_response(
            'circular_dependencies',
            cycles=[[str(path) for path in cycle] for cycle in cycles],
            count=len(cycles)
        )

    def _format_violations(self) -> Dict[str, Any]:
        """Format layer violations.

        Note: Requires .reveal.yaml configuration (Phase 4).
        For now, return placeholder.
        """
        return self._build_response(
            'layer_violations',
            violations=[],
            count=0,
            note='Layer violation detection requires .reveal.yaml configuration (coming in Phase 4)'
        )

    @staticmethod
    def _format_import(stmt: ImportStatement) -> Dict[str, Any]:
        """Format single import statement for output."""
        return {
            'file': str(stmt.file_path),
            'line': stmt.line_number,
            'module': stmt.module_name,
            'names': stmt.imported_names,
            'type': stmt.import_type,
            'is_relative': stmt.is_relative,
            'alias': stmt.alias
        }


__all__ = ['ImportsAdapter']
