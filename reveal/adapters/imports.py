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

from pathlib import Path
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse

from .base import ResourceAdapter, register_adapter
from ..analyzers.imports import ImportGraph, ImportStatement
from ..analyzers.imports.base import get_extractor, get_all_extensions, get_supported_languages


@register_adapter('imports')
class ImportsAdapter(ResourceAdapter):
    """Analyze import relationships in codebases."""

    def __init__(self):
        """Initialize imports adapter."""
        self._graph: Optional[ImportGraph] = None
        self._symbols_by_file: Dict[Path, set] = {}

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
        path_str = parsed.path or '.'

        # Parse query params - support both flag-style (?circular) and key-value (?circular=true)
        query_params = {}
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
                'error': f"Path not found: {target_path}",
                'uri': uri
            }

        # Extract imports and build graph
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
            'version': '0.28.0'
        }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for imports:// adapter."""
        return {
            'name': 'imports',
            'description': 'Import graph analysis for detecting unused imports, circular dependencies, and layer violations',
            'uri_scheme': 'imports://<path>',
            'examples': [
                {
                    'uri': 'reveal imports://src',
                    'description': 'List all imports in src directory'
                },
                {
                    'uri': "reveal 'imports://src?unused'",
                    'description': 'Find unused imports'
                },
                {
                    'uri': "reveal 'imports://src?circular'",
                    'description': 'Detect circular dependencies'
                },
                {
                    'uri': 'reveal imports://src/main.py',
                    'description': 'Show imports for single file'
                }
            ],
            'query_parameters': {
                'unused': 'Find imports that are never used',
                'circular': 'Detect circular dependencies',
                'violations': 'Check layer violations (requires .reveal.yaml)'
            },
            'supported_languages': get_supported_languages(),
            'status': 'beta'
        }

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
                resolved = extractor.resolve_import(stmt, base_path)
                if resolved:
                    self._graph.add_dependency(file_path, resolved)
                    self._graph.resolved_paths[stmt.module_name] = resolved

    def _format_all(self) -> Dict[str, Any]:
        """Format all imports (default view)."""
        if not self._graph:
            return {'imports': []}

        imports_by_file = {}
        for file_path, imports in self._graph.files.items():
            imports_by_file[str(file_path)] = [
                self._format_import(stmt) for stmt in imports
            ]

        return {
            'type': 'imports',
            'files': imports_by_file,
            'metadata': self.get_metadata()
        }

    def _format_unused(self) -> Dict[str, Any]:
        """Format unused imports."""
        if not self._graph:
            return {'unused': []}

        unused = self._graph.find_unused_imports(self._symbols_by_file)

        return {
            'type': 'unused_imports',
            'unused': [self._format_import(stmt) for stmt in unused],
            'count': len(unused),
            'metadata': self.get_metadata()
        }

    def _format_circular(self) -> Dict[str, Any]:
        """Format circular dependencies."""
        if not self._graph:
            return {'cycles': []}

        cycles = self._graph.find_cycles()

        return {
            'type': 'circular_dependencies',
            'cycles': [
                [str(path) for path in cycle]
                for cycle in cycles
            ],
            'count': len(cycles),
            'metadata': self.get_metadata()
        }

    def _format_violations(self) -> Dict[str, Any]:
        """Format layer violations.

        Note: Requires .reveal.yaml configuration (Phase 4).
        For now, return placeholder.
        """
        return {
            'type': 'layer_violations',
            'violations': [],
            'count': 0,
            'note': 'Layer violation detection requires .reveal.yaml configuration (coming in Phase 4)',
            'metadata': self.get_metadata()
        }

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
