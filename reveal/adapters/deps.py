"""deps:// adapter - dependency health dashboard.

Scan/render logic lives here (BACK-901/BACK-956); `cli/commands/deps.py` is a
thin argparse shim over this adapter, matching the URI/adapter contract every
other capability follows.
"""

from __future__ import annotations

import sys as _sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from reveal.reveal_types import CONTRACT_VERSION

from .base import ResourceAdapter, register_adapter, register_renderer
from .imports import ImportsAdapter
from ..utils import print_json_result
from ..utils.query import parse_query_params
from ..utils.results import ResultBuilder

# Python stdlib module names (Python 3.10+, with fallback set for older versions)
try:
    _STDLIB: frozenset = getattr(_sys, 'stdlib_module_names', frozenset())
except Exception:
    _STDLIB = frozenset()

# Common stdlib top-level names as fallback
_STDLIB_FALLBACK = frozenset({
    'abc', 'ast', 'asyncio', 'builtins', 'collections', 'contextlib',
    'copy', 'dataclasses', 'datetime', 'enum', 'functools', 'gc',
    'glob', 'hashlib', 'http', 'importlib', 'inspect', 'io', 'itertools',
    'json', 'logging', 'math', 'multiprocessing', 'operator', 'os',
    'pathlib', 'pickle', 'platform', 're', 'shutil', 'signal', 'socket',
    'sqlite3', 'string', 'struct', 'subprocess', 'sys', 'tempfile',
    'threading', 'time', 'traceback', 'typing', 'unittest', 'urllib',
    'uuid', 'warnings', 'weakref', 'zipfile', 'zlib',
})

_KNOWN_STDLIB = _STDLIB | _STDLIB_FALLBACK


# ── Data collectors ────────────────────────────────────────────────────────────

def _run_base(adapter: 'DepsAdapter', path: Path) -> Dict[str, Any]:
    """Fetch base import map via ImportsAdapter."""
    return adapter.compose(ImportsAdapter, str(path), default={})


def _run_circular(adapter: 'DepsAdapter', path: Path) -> Dict[str, Any]:
    """Fetch circular dependency cycles via ImportsAdapter."""
    return adapter.compose(ImportsAdapter, str(path), default={}, query='circular')


def _run_unused(adapter: 'DepsAdapter', path: Path) -> List[Dict[str, Any]]:
    """Fetch unused imports via ImportsAdapter."""
    data = adapter.compose(ImportsAdapter, str(path), default={}, query='unused')
    return data.get('unused', [])


def _local_package_names(base_path: Path) -> frozenset:
    """Return top-level package names local to the scanned directory.

    Includes the directory's own name (for absolute self-imports like
    `from reveal.cli import ...` when scanning the reveal/ dir) and any
    immediate subdirectory that is a Python package (has __init__.py).
    """
    names = {base_path.name}
    try:
        for child in base_path.iterdir():
            if child.is_dir() and (child / '__init__.py').exists():
                names.add(child.name)
    except OSError:
        pass
    return frozenset(names)


def _analyse_imports(files: Dict[str, List[Dict[str, Any]]], base_path: Path) -> Dict[str, Any]:
    """Derive package counts and top importers from the raw files dict."""
    local_names = _local_package_names(base_path)
    external_counts: Counter = Counter()
    stdlib_counts: Counter = Counter()
    relative_count = 0
    importer_counts: Counter = Counter()
    total_imports = 0

    for filepath, imports in files.items():
        if not isinstance(imports, list):
            continue
        importer_counts[filepath] += len(imports)
        total_imports += len(imports)
        for imp in imports:
            if imp.get('is_relative'):
                relative_count += 1
                continue
            module = (imp.get('module') or '').split('.')[0]
            if not module:
                continue
            if module in local_names:
                relative_count += 1  # treat as internal
            elif module in _KNOWN_STDLIB:
                stdlib_counts[module] += 1
            else:
                external_counts[module] += 1

    # Top importers as relative paths
    top_importers = []
    for fp, count in importer_counts.most_common():
        try:
            rel = str(Path(fp).relative_to(base_path))
        except ValueError:
            rel = fp
        top_importers.append({'file': rel, 'count': count})

    return {
        'total_imports': total_imports,
        'total_files': len(files),
        'relative_count': relative_count,
        'external_packages': external_counts.most_common(),
        'stdlib_packages': stdlib_counts.most_common(),
        'top_importers': top_importers,
    }


# ── Renderers ──────────────────────────────────────────────────────────────────

def _render_summary(analysis: Dict[str, Any], cycle_count: int, unused_count: int) -> None:
    total_files = analysis['total_files']
    total_imports = analysis['total_imports']
    ext_pkgs = len(analysis['external_packages'])
    stdlib_pkgs = len(analysis['stdlib_packages'])

    parts = [
        f"{total_files:,} files",
        f"{total_imports:,} imports",
        f"{ext_pkgs} third-party packages",
        f"{stdlib_pkgs} stdlib packages",
    ]

    health_parts = []
    if cycle_count:
        health_parts.append(f"❌ {cycle_count} circular dep(s)")
    else:
        health_parts.append("✅ no circular deps")
    if unused_count:
        health_parts.append(f"⚠️  {unused_count} unused import(s)")

    print(f"\nSummary   {' · '.join(parts)}")
    if health_parts:
        print(f"Health    {' · '.join(health_parts)}")


def _render_external_packages(analysis: Dict[str, Any], top: int) -> None:
    packages = analysis['external_packages']
    if not packages:
        return
    shown = packages[:top]
    print(f"\nThird-party packages  (top {len(shown)} by usage)")
    for pkg, count in shown:
        print(f"  {pkg:<30} {count:>4} use(s)")
    remaining = len(packages) - len(shown)
    if remaining > 0:
        print(f"  ... and {remaining} more")


def _render_circular(cycles: List, cycle_count: int, base_path: Path, top: int) -> None:
    if cycle_count == 0:
        return
    print(f"\nCircular dependencies  ({cycle_count} cycle(s))")
    for cycle in cycles[:top]:
        # Shorten paths to relative
        parts = []
        for fp in cycle:
            try:
                parts.append(Path(fp).relative_to(base_path).as_posix())
            except ValueError:
                parts.append(fp)
        print(f"  ❌ {' → '.join(parts)}")
    if cycle_count > top:
        print(f"  ... and {cycle_count - top} more  (run: reveal 'imports://. ?circular')")


def _render_unused(unused: List[Dict[str, Any]], base_path: Path, top: int) -> None:
    if not unused:
        return
    count = len(unused)
    print(f"\nUnused imports  ({count} found)")
    for imp in unused[:top]:
        filepath = imp.get('file', '?')
        line = imp.get('line', '?')
        module = imp.get('module', '?')
        names = imp.get('names', [])
        try:
            rel = Path(filepath).relative_to(base_path).as_posix()
        except ValueError:
            rel = filepath
        name_str = f".{', '.join(names)}" if names else ''
        print(f"  ⚠️  {rel}:{line}  {module}{name_str}")
    if count > top:
        print(f"  ... and {count - top} more  (run: reveal 'imports://. ?unused')")


def _render_top_importers(analysis: Dict[str, Any], top: int) -> None:
    importers = analysis['top_importers']
    if not importers:
        return
    shown = importers[:top]
    max_count = shown[0]['count'] if shown else 1
    print(f"\nTop importers  (files with most dependencies)")
    for item in shown:
        f = item['file']
        c = item['count']
        bar_len = int(c / max_count * 15) if max_count else 0
        bar = '█' * bar_len
        print(f"  {f:<50} {c:>3}  {bar}")


def _render_next_steps() -> None:
    print("\nNext steps")
    print("  reveal 'imports://. ?circular'    # Full circular dep list")
    print("  reveal 'imports://. ?unused'      # All unused imports")
    print("  reveal 'imports://. ?violations'  # Layer violation check")
    print()


def _render_deps(report: Dict[str, Any], top: int) -> None:
    path_str = report['path']
    base = report['base']
    circular = report['circular']
    unused = report['unused']

    files = base.get('files', {})
    analysis = _analyse_imports(files, Path(path_str))

    cycles = circular.get('cycles', [])
    cycle_count = circular.get('count', 0)

    print()
    print(f"Dependencies: {path_str}")
    print("━" * 60)

    _render_summary(analysis, cycle_count, len(unused))
    _render_external_packages(analysis, top)
    _render_circular(cycles, cycle_count, Path(path_str), top)
    _render_unused(unused, Path(path_str), top)
    _render_top_importers(analysis, top)
    _render_next_steps()


class DepsRenderer:
    """Renderer for deps:// results."""

    @staticmethod
    def render_structure(result: Dict[str, Any], format: str = 'text', top: int = 10) -> None:
        if format == 'json':
            print_json_result(result)
            return
        _render_deps(result, top)

    @staticmethod
    def render_error(error: Exception) -> None:
        print(f"Error scanning deps: {error}")


@register_adapter('deps')
@register_renderer(DepsRenderer)
class DepsAdapter(ResourceAdapter):
    """Adapter for the dependency health dashboard: external packages,
    circular deps, unused imports — composed from imports://."""

    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907

    def __init__(self, resource: str, query: Optional[str] = None):
        self.path = str(Path(resource).expanduser())
        self.query_params = parse_query_params(query or '', coerce=True)
        self._warn_unknown_query_params(self.query_params)  # BACK-507

    @staticmethod
    def get_help() -> Dict[str, Any]:
        return {
            'name': 'deps',
            'description': 'Dependency health dashboard: external packages, circular deps, unused imports.',
            'syntax': 'deps://<path>[?top=10&no_unused=true&no_circular=true]',
            'examples': [
                {'uri': 'deps://src', 'description': 'Dependency dashboard for src/'},
                {'uri': 'deps://.?top=15', 'description': 'Top 15 items per section'},
                {'uri': 'deps://.?no_unused=true', 'description': 'Skip the unused-imports section'},
            ],
            'features': [
                'Third-party package usage counts (stdlib separated out)',
                'Circular dependency cycles',
                'Unused imports',
                'Top importers by file',
            ],
            'notes': [
                'Composed entirely from imports:// — not an independent scan.',
            ],
            'see_also': [
                'reveal deps <path> - CLI subcommand form',
            ],
            'output_formats': ['text', 'json'],
        }

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            'adapter': 'deps',
            'description': 'Dependency health dashboard (external packages, circular deps, unused imports)',
            'uri_syntax': 'deps://<path>?top=10&no_unused=true&no_circular=true',
            'query_params': {
                'top': {'type': 'integer', 'description': 'Number of items to show per section', 'examples': ['top=15']},
                'no_unused': {'type': 'boolean', 'description': 'Skip the unused-imports section', 'examples': ['no_unused=true']},
                'no_circular': {'type': 'boolean', 'description': 'Skip the circular-dependencies section', 'examples': ['no_circular=true']},
            },
            'elements': {},
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': [
                {
                    'type': 'deps_scan',
                    'description': 'Base import map, circular-dependency cycles, and unused imports',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'base': {'type': 'object'},
                            'circular': {'type': 'object'},
                            'unused': {'type': 'array'},
                        },
                    },
                },
            ],
            'example_queries': [
                {'uri': 'deps://src', 'description': 'Dependency dashboard for src/', 'output_type': 'deps_scan'},
            ],
            'notes': [
                'Composed from three imports:// queries (base, ?circular, ?unused) — not an independent scan.',
            ],
        }

    def get_structure(self, **kwargs: Any) -> Dict[str, Any]:
        path = Path(self.path)
        no_unused = str(self.query_params.get('no_unused', False)).lower() == 'true'
        no_circular = str(self.query_params.get('no_circular', False)).lower() == 'true'

        base = _run_base(self, path)
        circular = {} if no_circular else _run_circular(self, path)
        unused = [] if no_unused else _run_unused(self, path)

        report = {
            'path': str(path),
            'base': base,
            'circular': circular,
            'unused': unused,
        }

        meta = self.composed_meta()
        return ResultBuilder.create(
            result_type='deps_scan',
            source=self.path,
            contract_version=CONTRACT_VERSION,
            data=report,
            warnings=meta.get('warnings') if meta else None,
            errors=meta.get('errors') if meta else None,
            confidence=meta.get('confidence') if meta else None,
        )
