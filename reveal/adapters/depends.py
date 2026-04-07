"""depends:// adapter — Inverse module dependency graph.

Answer "what depends on this module?" by inverting the import graph.

Usage:
    reveal depends://src/utils.py          # Who imports utils.py?
    reveal depends://src/models/           # Who imports anything in models/?
    reveal 'depends://src?top=20'          # Most-imported files
    reveal 'depends://src?format=dot'      # GraphViz output
"""

import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

from .base import ResourceAdapter, register_adapter, register_renderer
from ..utils import safe_json_dumps
from ..analyzers.imports import ImportGraph, ImportStatement
from ..analyzers.imports.base import get_extractor, get_all_extensions, get_supported_languages
from ..utils.query import parse_query_params
from ..utils.path_utils import find_project_root

_SCHEMA_QUERY_PARAMS = {
    'top': {
        'type': 'integer',
        'description': 'Limit to the N most-imported files',
        'examples': ["depends://src?top=10"],
    },
    'format': {
        'type': 'string',
        'description': 'Output format: text (default) or dot (GraphViz)',
        'examples': ["depends://src?format=dot"],
    },
}

_SCHEMA_OUTPUT_TYPES = [
    {
        'type': 'module_dependents',
        'description': 'List of files that import the target module(s)',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'module_dependents'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'target': {'type': 'string'},
                'dependents': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'file': {'type': 'string'},
                            'line': {'type': 'integer'},
                            'module': {'type': 'string'},
                            'names': {'type': 'array', 'items': {'type': 'string'}},
                            'type': {'type': 'string'},
                            'is_relative': {'type': 'boolean'},
                            'alias': {'type': 'string'},
                        },
                    },
                },
                'count': {'type': 'integer'},
            },
        },
    },
    {
        'type': 'dependency_summary',
        'description': 'Most-imported modules in a directory',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'dependency_summary'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'modules': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'module': {'type': 'string'},
                            'dependent_count': {'type': 'integer'},
                            'dependents': {'type': 'array', 'items': {'type': 'string'}},
                        },
                    },
                },
            },
        },
    },
]

_SCHEMA_EXAMPLE_QUERIES = [
    {
        'uri': 'depends://src/utils.py',
        'description': 'Show all files that import utils.py',
        'output_type': 'module_dependents',
    },
    {
        'uri': 'depends://src/models/',
        'description': 'Show everything that imports any module in models/',
        'output_type': 'dependency_summary',
    },
    {
        'uri': "depends://src?top=10",
        'description': 'The 10 most-imported modules in src (high coupling candidates)',
        'output_type': 'dependency_summary',
    },
    {
        'uri': "depends://src?format=dot",
        'description': 'Full reverse dependency graph in GraphViz DOT format',
        'output_type': 'dependency_summary',
    },
]

_SCHEMA_NOTES = [
    'Inverts the import graph built by imports:// — same language support, same resolution',
    'Dynamic imports (importlib.import_module, __import__) are not tracked',
    'TYPE_CHECKING-only imports are excluded from edges (intentional)',
    'Results are conservative: false negatives possible, never false positives',
    'Use ?top=N on a directory to find high-coupling modules (many dependents = high impact if changed)',
    'Use depends://file.py to do impact analysis before refactoring a module',
]


class DependsRenderer:
    """Renderer for depends:// results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text', verbose: bool = False, resource: str = '.') -> None:
        if format == 'json':
            print(safe_json_dumps(result))
            return

        result_type = result.get('type')
        if result_type == 'module_dependents':
            DependsRenderer._render_dependents(result, verbose)
        elif result_type == 'dependency_summary':
            fmt = result.get('_format', 'text')
            if fmt == 'dot':
                DependsRenderer._render_dot(result)
            else:
                DependsRenderer._render_summary(result, verbose, resource)
        else:
            print(safe_json_dumps(result))

    @staticmethod
    def _render_dependents(result: dict, verbose: bool) -> None:
        target = result.get('target', 'unknown')
        dependents = result.get('dependents', [])
        count = result.get('count', 0)

        print(f"\n{'='*60}")
        print(f"Dependents of: {target}")
        print(f"{'='*60}\n")

        if not dependents:
            print("  No dependents found (nothing imports this module)")
            print()
            return

        print(f"  {count} file(s) import this module:\n")
        for dep in dependents:
            file_path = dep.get('file', '')
            line = dep.get('line', 0)
            names = dep.get('names', [])
            import_type = dep.get('type', '')
            alias = dep.get('alias')

            if import_type == 'star_import':
                what = '*'
            elif names:
                what = ', '.join(names[:5])
                if len(names) > 5:
                    what += f', … (+{len(names) - 5} more)'
            else:
                what = dep.get('module', '')

            alias_str = f' as {alias}' if alias else ''
            print(f"  {file_path}:{line}  ← {what}{alias_str}")

        print()
        if not verbose:
            print(f"  Tip: reveal depends://{target} --verbose  for full import detail")
            print()

    @staticmethod
    def _render_summary(result: dict, verbose: bool, resource: str) -> None:
        modules = result.get('modules', [])
        source = result.get('source', resource)

        print(f"\n{'='*60}")
        print(f"Reverse Dependency Summary: {source}")
        print(f"{'='*60}\n")

        if not modules:
            print("  No internal imports found.")
            print()
            return

        total = sum(m['dependent_count'] for m in modules)
        print(f"  {len(modules)} module(s) imported internally ({total} total import edges)\n")

        for m in modules:
            count = m['dependent_count']
            mod = m['module']
            bar = '█' * min(count, 20)
            print(f"  {count:3d}  {bar}  {mod}")
            if verbose:
                for dep in m.get('dependents', []):
                    print(f"         ← {dep}")

        print()
        print(f"  Tip: reveal depends://<module>  for full importer list")
        print()

    @staticmethod
    def _render_dot(result: dict) -> None:
        modules = result.get('modules', [])
        print('digraph depends {')
        print('  rankdir=LR;')
        print('  node [shape=box fontname="monospace" fontsize=10];')
        for m in modules:
            target = m['module'].replace('"', '\\"')
            for dep in m.get('dependents', []):
                src = dep.replace('"', '\\"')
                print(f'  "{src}" -> "{target}";')
        print('}')

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        if format == 'json':
            print(safe_json_dumps(result))
            return
        DependsRenderer._render_dependents(result, verbose=True)

    @staticmethod
    def render_error(error: Exception) -> None:
        print(f"Error: {error}", file=sys.stderr)


@register_adapter('depends')
@register_renderer(DependsRenderer)
class DependsAdapter(ResourceAdapter):
    """Inverse module dependency graph — who imports this module?

    Builds the same import graph as imports:// but queries it in reverse:
    given a target module (or directory), returns the set of files that
    depend on it.
    """

    def __init__(self, path: str = '.', query: Optional[str] = None):
        """Initialize depends adapter.

        Args:
            path: File or directory to find dependents for
            query: Query string (e.g., 'top=10', 'format=dot')
        """
        self._graph: Optional[ImportGraph] = None
        self._symbols_by_file: Dict[Path, set] = {}
        self._target_path: Optional[Path] = Path(path).resolve() if path else None
        self._query_params = parse_query_params(query or '')

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Build import graph and return reverse-dependency view.

        Returns:
            - module_dependents if target is a specific file
            - dependency_summary if target is a directory
        """
        target_path = self._target_path or Path('.').resolve()

        if not target_path.exists():
            return {'error': f"Path not found: {target_path}"}

        # For a specific file target: scan from project root so ALL importers
        # (not just siblings) are discovered.
        # For a directory target: same — scan from project root so files outside
        # the directory that import into it are visible.
        project_root = find_project_root(target_path) or (
            target_path if target_path.is_dir() else target_path.parent
        )
        self._target_path = target_path
        self._build_graph(project_root)

        fmt = self._query_params.get('format', 'text')
        if not isinstance(fmt, str):
            fmt = 'text'
        top_n_raw = self._query_params.get('top')
        top_n = int(top_n_raw) if top_n_raw else None

        if target_path.is_file():
            return self._format_file_dependents(target_path)
        else:
            return self._format_directory_summary(target_path, top_n=top_n, fmt=fmt)

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get dependents for a specific module by name.

        Args:
            element_name: File name (e.g., 'utils.py')
        """
        if not self._graph:
            return None

        for file_path in self._graph.reverse_deps:
            if file_path.name == element_name:
                return self._format_file_dependents(file_path)

        return None

    def get_metadata(self) -> Dict[str, Any]:
        if not self._graph:
            return {'status': 'not_analyzed'}
        return {
            'total_files_scanned': self._graph.get_file_count(),
            'total_import_edges': sum(len(v) for v in self._graph.reverse_deps.values()),
            'analyzer': 'depends',
        }

    # ── Graph building (mirrors ImportsAdapter._build_graph) ──────────────

    def _build_graph(self, scan_root: Path) -> None:
        """Build import graph from scan_root."""
        if scan_root.is_file():
            files = [scan_root]
        else:
            supported_exts = frozenset(get_all_extensions())
            files = [f for f in scan_root.rglob('*') if f.is_file() and f.suffix in supported_exts]

        all_imports: List[ImportStatement] = []
        for file_path in files:
            extractor = get_extractor(file_path)
            if not extractor:
                continue
            imports = extractor.extract_imports(file_path)
            all_imports.extend(imports)

        self._graph = ImportGraph.from_imports(all_imports)

        # Resolve to build dependency (and reverse_deps) edges
        for file_path, imports in self._graph.files.items():
            extractor = get_extractor(file_path)
            if not extractor:
                continue

            base_path = file_path.parent
            extra_paths = [scan_root] if scan_root.is_dir() and scan_root != base_path else []
            for stmt in imports:
                if stmt.is_type_checking:
                    continue
                resolved = extractor.resolve_import(stmt, base_path, search_paths=extra_paths)
                if resolved and resolved != file_path:
                    self._graph.add_dependency(file_path, resolved)
                    self._graph.resolved_paths[stmt.module_name] = resolved

    # ── Formatters ─────────────────────────────────────────────────────────

    def _format_file_dependents(self, target: Path) -> Dict[str, Any]:
        """Format all files that import `target`."""
        if not self._graph:
            return {'error': 'Graph not built'}

        importer_files: Set[Path] = self._graph.reverse_deps.get(target, set())

        # Gather the actual ImportStatements pointing to target
        dependents = []
        for importer in sorted(importer_files):
            stmts = self._graph.files.get(importer, [])
            for stmt in stmts:
                resolved = self._graph.resolved_paths.get(stmt.module_name)
                if resolved == target:
                    dependents.append(_format_import_stmt(stmt))

        # If we couldn't match via resolved_paths, fall back to raw importer list
        if not dependents and importer_files:
            for importer in sorted(importer_files):
                dependents.append({'file': str(importer), 'line': 0, 'module': '', 'names': [], 'type': 'unknown', 'is_relative': False, 'alias': None})

        return {
            'contract_version': '1.0',
            'type': 'module_dependents',
            'source': str(self._target_path),
            'source_type': 'file',
            'target': str(target),
            'dependents': dependents,
            'count': len(dependents),
            'metadata': self.get_metadata(),
        }

    def _format_directory_summary(self, directory: Path, top_n: Optional[int], fmt: str) -> Dict[str, Any]:
        """Format most-imported modules in directory, sorted by dependent count."""
        if not self._graph:
            return {'error': 'Graph not built'}

        # Only include modules that live inside the directory
        modules = []
        for target, importers in self._graph.reverse_deps.items():
            if not _path_is_under(target, directory):
                continue
            modules.append({
                'module': str(target),
                'dependent_count': len(importers),
                'dependents': sorted(str(p) for p in importers),
            })

        modules.sort(key=lambda m: m['dependent_count'], reverse=True)

        if top_n:
            modules = modules[:top_n]

        result = {
            'contract_version': '1.0',
            'type': 'dependency_summary',
            'source': str(self._target_path),
            'source_type': 'directory',
            '_format': fmt,
            'modules': modules,
            'metadata': self.get_metadata(),
        }
        return result

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            'adapter': 'depends',
            'description': 'Inverse module dependency graph — who imports this module?',
            'uri_syntax': 'depends://<path>[?query]',
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
        return {
            'name': 'depends',
            'description': 'Inverse module dependency graph — who imports this module?',
            'syntax': 'depends://<path>[?<query>]',
            'examples': _SCHEMA_EXAMPLE_QUERIES,
            'notes': _SCHEMA_NOTES,
            'supported_languages': get_supported_languages(),
        }


# ── Helpers ────────────────────────────────────────────────────────────────

def _format_import_stmt(stmt: ImportStatement) -> Dict[str, Any]:
    return {
        'file': str(stmt.file_path),
        'line': stmt.line_number,
        'module': stmt.module_name,
        'names': stmt.imported_names,
        'type': stmt.import_type,
        'is_relative': stmt.is_relative,
        'alias': stmt.alias,
    }


def _path_is_under(path: Path, directory: Path) -> bool:
    """True if path is inside directory (or is directory itself)."""
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False
