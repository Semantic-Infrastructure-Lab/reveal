"""deps:// adapter - dependency health dashboard.

Scan/render logic lives here (BACK-901/BACK-956); `cli/commands/deps.py` is a
thin argparse shim over this adapter, matching the URI/adapter contract every
other capability follows.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from reveal.reveal_types import CONTRACT_VERSION

from .base import ResourceAdapter, register_adapter, register_renderer
from .imports import ImportsAdapter
from ..analyzers.imports.classify import (
    classify_module as _classify_module,
    local_package_names as _local_package_names,
)
from ..utils import print_json_result
from ..utils.query import parse_query_params
from ..utils.results import ResultBuilder

# BACK-1190: the stdlib list, local-package heuristic, and classifier itself
# now live in reveal/analyzers/imports/classify.py -- shared with
# imports://'s own 'classification' field so the two adapters can't drift
# apart the way BACK-1193 found them having already done.


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


def _relativize_deps_paths(
    base: Dict[str, Any],
    circular: Dict[str, Any],
    unused: List[Dict[str, Any]],
    base_path: Path,
) -> None:
    """Relativize the file-path fields the text renderer already relativizes
    (`_render_circular`/`_render_unused`/`_analyse_imports`'s `to_relative_display`
    calls), but in the raw structures get_structure() serializes directly to
    JSON — those never routed through the text renderer, so `--format json`
    leaked absolute host paths (analyst's filesystem layout/username), same
    gap as overview.py's `_relativize_paths` fixes (BACK-1194 follow-up).
    Mutates in place.
    """
    from ..utils.path_utils import to_relative_display

    if base.get('source'):
        base['source'] = to_relative_display(base['source'], base_path)
    files = base.get('files')
    if isinstance(files, dict):
        base['files'] = {
            to_relative_display(fp, base_path): imports
            for fp, imports in files.items()
        }
    for key in ('cycles', 'cycle_paths'):
        groups = circular.get(key)
        if groups:
            circular[key] = [
                [to_relative_display(fp, base_path) for fp in group]
                for group in groups
            ]
    for imp in unused:
        if imp.get('file'):
            imp['file'] = to_relative_display(imp['file'], base_path)


def _tally_import(
    imp: Dict[str, Any], is_python_file: bool, local_names: frozenset,
    external_counts: Counter, stdlib_counts: Counter,
) -> bool:
    """Classify+count one import; returns True if it counts as internal."""
    if imp.get('is_relative') or imp.get('resolved'):
        return True  # syntactically relative, or resolved in-tree (BACK-1193)
    bucket, key = _classify_module(imp.get('module') or '', is_python_file, local_names)
    if bucket == 'external' and imp.get('classification') == 'intra_project':
        # BACK-1236: imports://'s own is_intra_project_import verdict (BACK-1234,
        # declared-namespace matching for Go/C#/Java/Kotlin/PHP) upgraded this
        # import past the name-only heuristic above -- honor that here too,
        # rather than still tallying it as an external package.
        return True
    if bucket == 'stdlib':
        stdlib_counts[key] += 1
    elif bucket == 'external':
        external_counts[key] += 1
    return bucket == 'internal'


def _analyse_imports(files: Dict[str, List[Dict[str, Any]]], base_path: Path) -> Dict[str, Any]:
    """Derive package counts and top importers from the raw files dict.

    BACK-1193: this classifier used to be Python-only in three ways — a
    ``__init__.py``-based local-package heuristic, an unconditional check
    against Python's own stdlib list, and a dot-only module split — applied
    unconditionally to all 18 languages reveal supports. On Ruby it reported
    local files and stdlib modules as "third-party" (`open3`, `fileutils`)
    and manufactured a bogus stdlib count from name collisions with Python
    (`json`, `socket`, ...). Fixed by classifying on resolution truth first:
    ``imports://``'s ``resolved`` field (BACK-1193, real in-tree file or
    None from ``resolve_import()``) is now the primary signal, with the
    ``__init__.py`` heuristic kept only as a fallback for imports resolution
    could not settle. Python-list stdlib is only ever checked for Python
    files — never fall back to Python's list for a non-Python import (task's
    own rule). Dart is the one other language classified as stdlib, because
    its ``dart:`` import prefix (`dart:async`, `dart:io`, ...) is a
    syntactic marker, not a name lookup that could collide the way a bare
    list-membership check would — same rule, no list needed.
    """
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
        is_python_file = filepath.endswith('.py')
        for imp in imports:
            if _tally_import(imp, is_python_file, local_names, external_counts, stdlib_counts):
                relative_count += 1

    # Top importers as relative paths (BACK-1194: shared resolve()-aware
    # helper — see to_relative_display()'s docstring for why the old
    # lexical-only relative_to() let absolute paths leak through on
    # relative CLI targets)
    from ..utils.path_utils import to_relative_display
    top_importers = []
    for fp, count in importer_counts.most_common():
        rel = to_relative_display(fp, base_path)
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
        f"{ext_pkgs} unresolved packages",
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
    # BACK-1193: honest label — these are modules resolve_import() could not
    # place in-tree. Most are real third-party packages, but an unresolved
    # local (load-path boundary, missing file_index coverage) lands here too.
    print(f"\nUnresolved packages (third-party or unresolved-local)  (top {len(shown)} by usage)")
    for pkg, count in shown:
        print(f"  {pkg:<30} {count:>4} use(s)")
    remaining = len(packages) - len(shown)
    if remaining > 0:
        print(f"  ... and {remaining} more")


def _render_circular(cycles: List, cycle_count: int, base_path: Path, top: int) -> None:
    if cycle_count == 0:
        return
    from ..utils.path_utils import to_relative_display
    print(f"\nCircular dependencies  ({cycle_count} cycle(s))")
    for cycle in cycles[:top]:
        # Shorten paths to relative
        parts = [to_relative_display(fp, base_path) for fp in cycle]
        print(f"  ❌ {' → '.join(parts)}")
    if cycle_count > top:
        print(f"  ... and {cycle_count - top} more  (run: reveal 'imports://. ?circular')")


def _render_unused(unused: List[Dict[str, Any]], base_path: Path, top: int) -> None:
    if not unused:
        return
    from ..utils.path_utils import to_relative_display
    count = len(unused)
    print(f"\nUnused imports  ({count} found)")
    for imp in unused[:top]:
        filepath = imp.get('file', '?')
        line = imp.get('line', '?')
        module = imp.get('module', '?')
        names = imp.get('names', [])
        rel = to_relative_display(filepath, base_path)
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
    HELP_CLUSTER = 'Code Analysis'

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
                'Unresolved (third-party or unresolved-local) package usage '
                'counts — stdlib separated out, Python only (BACK-1193)',
                'Circular dependency cycles',
                'Unused imports',
                'Top importers by file',
            ],
            'notes': [
                'Composed entirely from imports:// — not an independent scan.',
                'Not depends:// (one character apart) — deps:// is a dashboard '
                'over the whole tree; depends:// answers "who imports this one '
                'module" for a single target.',
                'BACK-1178: the CLI subcommand form (`reveal deps <path> --format '
                'json`) and this URI form intentionally carry different '
                'contract_version/meta envelopes — subcommand-form is frozen at '
                'v1.0 with no meta block (BACK-906, backward-compat guarantee for '
                'existing --format json consumers), URI-form is on v1.1 with a '
                'meta block (confidence/warnings/errors, BACK-885/891). The '
                'underlying data fields are otherwise the same.',
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
                {'uri': 'deps://src', 'description': 'Dependency dashboard for src/', 'output_type': 'deps_scan', 'task': 'quality'},
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
        _relativize_deps_paths(base, circular, unused, path)

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
