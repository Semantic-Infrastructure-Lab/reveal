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
from urllib.parse import urlparse, parse_qs

from .base import ResourceAdapter, register_adapter
from ..analyzers.imports import ImportGraph, ImportStatement
from ..analyzers.imports.python import extract_python_imports, extract_python_symbols
from ..analyzers.imports.resolver import resolve_python_import


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
        query_params = parse_qs(parsed.query)

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
                    'command': 'reveal imports://src',
                    'description': 'List all imports in src directory'
                },
                {
                    'command': "reveal 'imports://src?unused'",
                    'description': 'Find unused imports'
                },
                {
                    'command': "reveal 'imports://src?circular'",
                    'description': 'Detect circular dependencies'
                },
                {
                    'command': 'reveal imports://src/main.py',
                    'description': 'Show imports for single file'
                }
            ],
            'query_parameters': {
                'unused': 'Find imports that are never used',
                'circular': 'Detect circular dependencies',
                'violations': 'Check layer violations (requires .reveal.yaml)'
            },
            'supported_languages': ['Python'],
            'status': 'beta'
        }

    def _build_graph(self, target_path: Path) -> None:
        """Build import graph from target path.

        Args:
            target_path: Directory or file to analyze
        """
        if target_path.is_file():
            files = [target_path]
        else:
            files = list(target_path.rglob('*.py'))

        # Extract imports from all Python files
        all_imports = []
        for file_path in files:
            imports = extract_python_imports(file_path)
            all_imports.extend(imports)

            # Also extract symbols for unused detection
            symbols = extract_python_symbols(file_path)
            self._symbols_by_file[file_path] = symbols

        # Build graph
        self._graph = ImportGraph.from_imports(all_imports)

        # Resolve imports to build dependency edges
        for file_path, imports in self._graph.files.items():
            base_path = file_path.parent

            for stmt in imports:
                resolved = resolve_python_import(stmt, base_path)
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
