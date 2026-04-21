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

from .base import ResourceAdapter, register_adapter, register_renderer
from .help_data import load_help_data
from ..utils import safe_json_dumps
from ..analyzers.imports import ImportGraph, ImportStatement
from ..analyzers.imports.layers import load_layer_config
from ..utils.query import parse_query_params

_SCHEMA_QUERY_PARAMS = {
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
    },
    'rank': {
        'type': 'enum',
        'values': ['fan-in'],
        'description': 'Rank files by structural metric. fan-in: count of files that import each file (higher = more central; 0 = entry point or dead code)',
        'examples': ['imports://src?rank=fan-in', 'imports://src?rank=fan-in&top=20']
    },
    'top': {
        'type': 'integer',
        'description': 'Limit results for ?rank (default: all files)',
        'examples': ['imports://src?rank=fan-in&top=20']
    },
}

_SCHEMA_OUTPUT_TYPES = [
    {
        'type': 'imports',
        'description': 'Full import listing for all files in the codebase (default output)',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'imports'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'files': {'type': 'object'},
                'metadata': {'type': 'object'}
            }
        }
    },
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
    },
    {
        'type': 'fan_in_ranking',
        'description': 'Files ranked by fan-in (importer count) — high fan-in = core abstractions; zero fan-in = entry points or dead code',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'fan_in_ranking'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'total': {'type': 'integer'},
                'entries': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'file': {'type': 'string'},
                            'fan_in': {'type': 'integer'},
                            'fan_out': {'type': 'integer'},
                        }
                    }
                }
            }
        }
    }
]

_SCHEMA_EXAMPLE_QUERIES = [
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
        'description': 'Check layer violations (requires .reveal.yaml layers config)',
        'cli_flag': '?violations',
        'output_type': 'layer_violations'
    },
    {
        'uri': 'imports://src/main.py',
        'description': 'Analyze imports for a single file (no cycle detection)',
        'output_type': 'import_summary'
    },
    {
        'uri': 'imports://src?rank=fan-in',
        'description': 'Rank all files by fan-in — surface core abstractions and entry points',
        'output_type': 'fan_in_ranking'
    },
    {
        'uri': 'imports://src?rank=fan-in&top=20',
        'description': 'Top-20 files by fan-in',
        'output_type': 'fan_in_ranking'
    },
]

_SCHEMA_NOTES = [
    'Supports multiple languages via plugin architecture',
    'Circular dependencies can indicate architectural issues',
    'Layer violations require .reveal.yaml configuration',
    'Unused import detection works with Python, JavaScript, Go, etc.',
    'False positives: imports that trigger side effects (e.g. decorator-based registration) will be flagged as unused — these are intentional and safe to ignore',
    'Fan-in ranking covers static imports only — decorator-based registration and importlib dynamic imports are not captured',
]


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
        note = result.get('note', '')
        not_configured = count == 0 and note and 'requires' in note.lower()

        print(f"\n{'='*60}")
        if not_configured:
            print(f"Layer Violations: NOT CONFIGURED")
        else:
            print(f"Layer Violations: {count}")
        print(f"{'='*60}\n")

        if not_configured:
            print(f"  ℹ️  {note}\n")
            print(f"  Add layer rules to .reveal.yaml to enable this check.\n")
        elif count == 0:
            print(f"  ✅ {note or 'No violations found'}\n")
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

        display_path = result.get('source', resource)

        print(f"\n{'='*60}")
        print(f"Import Analysis: {display_path}")
        print(f"{'='*60}\n")
        print(f"  Total Files:   {total_files}")
        print(f"  Total Imports: {total_imports}")
        if total_files <= 1:
            print("  Cycles Found:  N/A (single-file scan — use imports://dir/ to detect cycles)")
        else:
            print(f"  Cycles Found:  {'❌ Yes' if has_cycles else '✅ No'}")
        print()
        print("Query options:")
        print(f"  reveal 'imports://{resource}?unused'       - Find unused imports")
        print(f"  reveal 'imports://{resource}?circular'     - Detect circular deps")
        print(f"  reveal 'imports://{resource}?violations'   - Check layer violations")
        print(f"  reveal 'imports://{resource}?rank=fan-in'  - Rank files by fan-in (core abstractions)")
        print()

    @staticmethod
    def _render_fan_in(result: dict, resource: str) -> None:
        """Render rank=fan-in output — files ranked by number of importers."""
        entries = result.get('entries', [])
        total = result.get('total', 0)
        source = result.get('source', resource)

        print(f"\nFan-in ranking: {source}")
        print(f"Files: {len(entries)} of {total}  (fan-in = number of files that import this file)")
        print()

        if not entries:
            print("  No import data found.")
            return

        source_path = Path(source) if source else None
        col_w = min(60, max(len(e['file']) for e in entries) - (len(source) + 1 if source_path else 0) + 2)
        col_w = max(col_w, 20)

        print(f"  {'FILE':<{col_w}}  {'FAN-IN':>7}  {'FAN-OUT':>8}")
        print(f"  {'-'*col_w}  {'-'*7}  {'-'*8}")
        for e in entries:
            fpath = e['file']
            if source_path:
                try:
                    fpath = str(Path(fpath).relative_to(source_path))
                except ValueError:
                    pass
            print(f"  {fpath:<{col_w}}  {e['fan_in']:>7}  {e['fan_out']:>8}")
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
            elif result_type == 'fan_in_ranking':
                ImportsRenderer._render_fan_in(result, resource)
            else:
                ImportsRenderer._render_import_summary(result, resource)
        else:
            print(safe_json_dumps(result))

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        """Render file-specific imports.

        Args:
            result: Element dict from ImportsAdapter.get_element()
            format: Output format ('text', 'json')
        """
        if format == 'json':
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


from ..analyzers.imports.base import get_extractor, get_all_extensions, get_supported_languages  # noqa: E402


@register_adapter('imports')
@register_renderer(ImportsRenderer)
class ImportsAdapter(ResourceAdapter):
    """Analyze import relationships in codebases."""

    def __init__(self, path: str = '.', query: Optional[str] = None):
        """Initialize imports adapter.

        Args:
            path: Directory or file path to analyze (e.g., 'src', '/abs/path')
            query: Query string portion (e.g., 'unused', 'circular=true')
        """
        self._graph: Optional[ImportGraph] = None
        self._symbols_by_file: Dict[Path, set] = {}
        self._scanned_files: set = set()
        # Handle both absolute and relative paths:
        # - netloc component from URI parsing (imports://relative/path → 'relative/path')
        # - absolute path (imports:///absolute/path → '/absolute/path')
        self._target_path: Optional[Path] = Path(path).resolve() if path else None
        self._query_params = parse_query_params(query or '')

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Analyze imports in directory or file.

        Args:
            **kwargs: Additional parameters (unused, circular, violations flags)

        Returns:
            Dictionary with import analysis results
        """
        target_path = self._target_path or Path('.').resolve()
        query_params = self._query_params

        if not target_path.exists():
            return {
                'error': f"Path not found: {target_path}",
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
        elif query_params.get('rank') == 'fan-in':
            return self._format_fan_in()
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
            'analyzer': 'imports'
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
            'query_params': _SCHEMA_QUERY_PARAMS,
            'elements': {},
            'cli_flags': ['--verbose'],
            'supports_batch': False,
            'supports_advanced': False,
            'supported_languages': get_supported_languages(),
            'output_types': _SCHEMA_OUTPUT_TYPES,
            'example_queries': _SCHEMA_EXAMPLE_QUERIES,
            'notes': _SCHEMA_NOTES,
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

    def _extract_file_imports_and_symbols(self, file_path, extractor):
        """Extract imports and symbols from a single file using its extractor."""
        imports = extractor.extract_imports(file_path)
        symbols = extractor.extract_symbols(file_path)
        if hasattr(extractor, 'extract_exports'):
            exports = extractor.extract_exports(file_path)
            symbols = symbols | exports
        return imports, symbols

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
            # Single walk filtered by extension — avoids one rglob per extension (~100 walks).
            supported_exts = frozenset(get_all_extensions())
            files = [f for f in target_path.rglob('*') if f.is_file() and f.suffix in supported_exts]

        self._scanned_files = set(files)

        # Extract imports from all files using appropriate extractor
        all_imports = []
        for file_path in files:
            extractor = get_extractor(file_path)
            if not extractor:
                continue
            imports, symbols = self._extract_file_imports_and_symbols(file_path, extractor)
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
            # Pass project root as an extra search path so absolute intra-project
            # imports resolve (e.g., `from db.session import X` from `api/routes.py`
            # finds `db/session.py` under the project root, not just under `api/`).
            extra_paths = [target_path] if target_path.is_dir() and target_path != base_path else []
            for stmt in imports:
                # Skip TYPE_CHECKING imports - they're type-checking only, not runtime
                # circular dependencies (this is a standard Python pattern to avoid real cycles)
                if stmt.is_type_checking:
                    continue

                resolved = extractor.resolve_import(stmt, base_path, search_paths=extra_paths)
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

    def _format_fan_in(self) -> Dict[str, Any]:
        """Rank files by fan-in (number of other files that import them).

        High fan-in = core abstractions (base classes, shared utils).
        Zero fan-in = entry points or dead code.
        """
        if not self._graph:
            return self._build_response('fan_in_ranking', entries=[], total=0)

        top_param = self._query_params.get('top')
        top = int(top_param) if top_param else None

        # Union: all scanned files + files that appear as import targets (may live outside scan root)
        all_files = self._scanned_files | set(self._graph.files.keys()) | set(self._graph.reverse_deps.keys())
        entries = sorted(
            [
                {
                    'file': str(f),
                    'fan_in': len(self._graph.reverse_deps.get(f, set())),
                    'fan_out': len(self._graph.dependencies.get(f, set())),
                }
                for f in all_files
            ],
            key=lambda e: (-e['fan_in'], -e['fan_out'], e['file']),
        )

        total = len(entries)
        if top:
            entries = entries[:top]

        return self._build_response('fan_in_ranking', entries=entries, total=total)

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
        """Format layer violations using .reveal.yaml layer rules."""
        layer_config = load_layer_config(self._target_path)

        if layer_config is None:
            return self._build_response(
                'layer_violations',
                violations=[],
                count=0,
                note='Layer violation detection requires .reveal.yaml configuration'
            )

        project_root = self._target_path if self._target_path.is_dir() else self._target_path.parent
        violations = []

        for from_file, to_files in self._graph.dependencies.items():
            for to_file in to_files:
                result = layer_config.check_import(from_file, to_file, project_root)
                if result is not None:
                    layer_name, reason = result
                    violations.append({
                        'from_file': str(from_file.relative_to(project_root) if from_file.is_relative_to(project_root) else from_file),
                        'to_file': str(to_file.relative_to(project_root) if to_file.is_relative_to(project_root) else to_file),
                        'layer': layer_name,
                        'reason': reason or f'{layer_name} layer violation',
                    })

        return self._build_response(
            'layer_violations',
            violations=violations,
            count=len(violations),
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
