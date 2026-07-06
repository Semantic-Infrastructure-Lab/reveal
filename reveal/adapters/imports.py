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

import os
import sys
from pathlib import Path
from typing import Callable, Dict, Any, List, Optional

from .base import ResourceAdapter, register_adapter, register_renderer
from .help_data import load_help_data
from ..utils import safe_json_dumps
from ..analyzers.imports import ImportGraph, ImportStatement
from ..analyzers.imports.layers import load_layer_config
from ..utils.query import parse_query_params
from ..defaults import SKIP_DIRECTORIES
from ..registry import get_code_extensions

_SKIP_DIRS = SKIP_DIRECTORIES

def _module_label(path: str) -> str:
    p = Path(path)
    return '/'.join(p.parts[-2:]) if p.name == '__init__.py' else p.name


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
    'entrypoints': {
        'type': 'flag',
        'description': 'List files with fan-in=0 — nothing imports them (entry points, scripts, or dead code); sorted by fan-out descending',
        'examples': ['imports://src?entrypoints']
    },
    'components': {
        'type': 'flag',
        'description': 'Score each directory as a component: cohesion (internal/outgoing imports), coupling (incoming), top bridge file',
        'examples': ['imports://src?components']
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
    },
    {
        'type': 'components',
        'description': 'Per-directory cohesion and coupling scores — validates directory-as-component hypothesis',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'components'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'total': {'type': 'integer'},
                'components': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'component': {'type': 'string'},
                            'files': {'type': 'integer'},
                            'internal': {'type': 'integer'},
                            'outgoing': {'type': 'integer'},
                            'incoming': {'type': 'integer'},
                            'cohesion': {'type': 'number'},
                            'top_bridge': {'type': ['string', 'null']},
                        }
                    }
                }
            }
        }
    },
    {
        'type': 'entrypoints',
        'description': 'Files with fan-in=0 — nothing imports them (entry points, scripts, or dead code)',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'entrypoints'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'total_scanned': {'type': 'integer'},
                'entries': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'file': {'type': 'string'},
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

        # A language with no import extractor (e.g. Kotlin, Swift, Scala) was
        # never analyzed at all — count == 0 in that case means "not checked,"
        # not "clean." Without this, the text renderer prints the same "✅ No
        # unused imports found!" for both cases, a false-confidence result
        # (BACK-431 feature-breadth pass); the JSON renderer already exposes
        # this via metadata.unsupported_extensions.
        unsupported = result.get('metadata', {}).get('unsupported_extensions') or {}
        if unsupported:
            exts = ', '.join(f'{ext} ({n} file{"s" if n != 1 else ""})' for ext, n in sorted(unsupported.items()))
            print(f"  ⚠ Not analyzed — no import extractor for: {exts}\n")

        # scanned_files (files with a working extractor), not total_files
        # (files with >=1 import statement) — a file can be fully, correctly
        # analyzed and still have zero imports (BACK-431: real WordPress
        # source with no `use`/`require` at all), and total_files would
        # wrongly read as "unchecked" in that case.
        analyzed_files = result.get('metadata', {}).get('scanned_files', 0)
        if count == 0 and analyzed_files > 0:
            print("  ✅ No unused imports found!\n")
        elif count == 0:
            pass
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
        """Render circular dependency groups (one entry per SCC)."""
        count = result['count']
        print(f"\n{'='*60}")
        print(f"Circular Dependencies: {count} cycle group{'s' if count != 1 else ''}")
        print(f"{'='*60}\n")

        if count == 0:
            print("  ✅ No circular dependencies found!\n")
            return

        groups = result['cycles']
        cycle_paths = result.get('cycle_paths', [])
        shown_groups = groups if verbose else groups[:5]
        shown_paths = cycle_paths[:len(shown_groups)] if cycle_paths else []
        for i, group in enumerate(shown_groups, 1):
            n = len(group)
            labels = [_module_label(p) for p in group]
            if verbose or n <= 4:
                label = ', '.join(labels)
            else:
                label = ', '.join(labels[:3]) + f'  [+{n - 3} more files]'
            print(f"  {i}. {n} file{'s' if n != 1 else ''}  {label}")
            if verbose and i - 1 < len(shown_paths):
                path_labels = [_module_label(p) for p in shown_paths[i - 1]]
                print(f"     cycle: {' → '.join(path_labels)}")
        if not verbose and count > 5:
            print(f"\n  ... and {count - 5} more groups")
            print(f"  Run with --verbose to see all {count} groups\n")
        if not verbose and cycle_paths:
            print(f"\n  Tip: add &verbose to see cycle edge sequences (A→B→C→A)")

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

        # Honesty note: recognized code files whose language has no import
        # extractor were scanned but contribute nothing — say so instead of
        # letting a low/zero count read as "clean".
        unsupported = metadata.get('unsupported_extensions') or {}
        if unsupported:
            skipped_total = sum(unsupported.values())
            exts = ', '.join(f"{ext} ({n})" for ext, n in unsupported.items())
            print(f"  ⚠️  {skipped_total} code file(s) skipped — no import support for: {exts}")
            print("      (these are not counted above; import graph excludes them)")
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
        print("  Note: static imports only — files loaded via dynamic dispatch")
        print("  (importlib, require(), Class.forName, autoload, etc.) show lower fan-in than actual.")
        print()

    @staticmethod
    def _render_entrypoints(result: dict, resource: str) -> None:
        """Render ?entrypoints output — files with fan-in=0 (nothing imports them)."""
        entries = result.get('entries', [])
        total_scanned = result.get('total_scanned', 0)
        source = result.get('source', resource)

        print(f"\nEntry points: {source}")
        print(f"Files: {len(entries)} of {total_scanned}  (fan-in=0: nothing imports these — entry points or dead code)")
        print()

        if not entries:
            print("  No entry points found (every file is imported by at least one other).")
            return

        source_path = Path(source) if source else None
        col_w = min(60, max(len(e['file']) for e in entries) - (len(source) + 1 if source_path else 0) + 2)
        col_w = max(col_w, 20)

        print(f"  {'FILE':<{col_w}}  {'FAN-OUT':>8}")
        print(f"  {'-'*col_w}  {'-'*8}")
        for e in entries:
            fpath = e['file']
            if source_path:
                try:
                    fpath = str(Path(fpath).relative_to(source_path))
                except ValueError:
                    pass
            print(f"  {fpath:<{col_w}}  {e['fan_out']:>8}")
        print()
        print("  Note: static imports only — files loaded via dynamic dispatch")
        print("  (importlib, require(), Class.forName, autoload, etc.) are false positives here.")
        print()

    @staticmethod
    def _render_components(result: dict, resource: str) -> None:
        """Render ?components output — per-directory cohesion and coupling scores."""
        components = result.get('components', [])
        source = result.get('source', resource)

        print(f"\nComponent analysis: {source}")
        print(f"Components: {len(components)}  (cohesion = internal imports ÷ outgoing imports from component)")
        print()

        if not components:
            print("  No components found.")
            return

        source_path = Path(source) if source else None

        def rel(p: str) -> str:
            if source_path:
                try:
                    return str(Path(p).relative_to(source_path))
                except ValueError:
                    pass
            return p

        col_w = max(max(len(rel(c['component'])) for c in components) + 2, 20)
        col_w = min(col_w, 55)

        print(f"  {'COMPONENT':<{col_w}}  {'FILES':>5}  {'INTERNAL':>8}  {'OUT':>5}  {'IN':>5}  {'COHESION':>9}")
        print(f"  {'-'*col_w}  {'-'*5}  {'-'*8}  {'-'*5}  {'-'*5}  {'-'*9}")

        for c in components:
            name = rel(c['component'])
            bridge = c.get('top_bridge')
            bridge_note = f"  ← {Path(bridge).name}" if bridge else ''
            cohesion_pct = f"{c['cohesion'] * 100:.0f}%"
            print(f"  {name:<{col_w}}  {c['files']:>5}  {c['internal']:>8}  {c['outgoing']:>5}  {c['incoming']:>5}  {cohesion_pct:>9}{bridge_note}")

        print()
        print("  Note: low cohesion = files import heavily outside this directory (may not be a real component)")
        print("  Note: static imports only — dynamic dispatch not captured")
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

        # verbose from query (?verbose) takes precedence over caller arg
        verbose = result.get('verbose', verbose)

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
            elif result_type == 'entrypoints':
                ImportsRenderer._render_entrypoints(result, resource)
            elif result_type == 'components':
                ImportsRenderer._render_components(result, resource)
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


# ── BACK-489 P1: parallel per-file extraction ───────────────────────────────
# `_build_graph`'s per-file work (import/symbol extraction + optional AST
# structure) is independent across files — an embarrassingly-parallel map whose
# only shared step is the cheap graph-assembly reduce that follows. On large
# repos this map is ~94% of `reveal architecture`'s cost and is otherwise
# single-threaded (see design/BACK489_ARCHITECTURE_PERF_FINDINGS_2026-07-06.md
# §8). We fan it out across processes (tree-sitter parsing is fork-safe;
# measured 4.6x on a 12-core box for a 852-file TS subset). Results are
# consumed in submission order (ProcessPoolExecutor.map preserves order), so
# the assembled graph and structure list are byte-identical to the serial path.
_PARALLEL_MIN_FILES = 200   # below this, pool startup/IPC outweighs the win
_PARALLEL_MAX_WORKERS = 16  # cap so huge core counts don't oversubscribe/thrash


def _parallel_worker_count(n_files: int) -> int:
    """Workers to use for `n_files`. 1 = run serially (no pool).

    `REVEAL_MAX_WORKERS` overrides everything (set to 1 to force the serial
    path — used by tests and for debugging); otherwise parallelize only above
    `_PARALLEL_MIN_FILES`, capped at `_PARALLEL_MAX_WORKERS` and the CPU count.
    """
    override = os.environ.get('REVEAL_MAX_WORKERS')
    if override:
        try:
            return max(1, int(override))
        except ValueError:
            pass
    if n_files < _PARALLEL_MIN_FILES:
        return 1
    return max(1, min(os.cpu_count() or 1, _PARALLEL_MAX_WORKERS))


def _extract_one_file(fp_str: str, want_structure: bool):
    """Extract imports/symbols (+ optional AST structure) for a single file.

    Module-level and picklable so it runs unchanged under a
    `ProcessPoolExecutor` (fork *or* spawn). Returns
    `(fp_str, imports_or_None, symbols_or_None, structure_or_None)`:
    `imports`/`symbols` are None when the file has no import extractor (mirrors
    the serial path only populating them for extractable files); `structure`
    is None when not requested or when analysis raised (mirrors the serial
    `collect_structure`'s try/except-to-None). Import extraction errors are NOT
    swallowed here — the serial path lets them propagate too.
    """
    fp = Path(fp_str)
    imports = symbols = structure = None
    extractor = get_extractor(fp)
    if extractor is not None:
        imports = extractor.extract_imports(fp)
        symbols = extractor.extract_symbols(fp)
        if hasattr(extractor, 'extract_exports'):
            symbols = symbols | extractor.extract_exports(fp)
    if want_structure:
        try:
            from .ast.analysis import analyze_file
            structure = analyze_file(fp_str)
        except Exception:
            structure = None
    return fp_str, imports, symbols, structure


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
        self._unsupported_extensions: Dict[str, int] = {}
        # Populated only when _build_graph is called with collect_structures=True
        # (reveal architecture) — per-file AST structures from the shared walk.
        self._structures: List[Dict[str, Any]] = []
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
        verbose = 'verbose' in query_params or kwargs.get('verbose', False)
        if 'unused' in query_params or kwargs.get('unused'):
            result = self._format_unused()
        elif 'circular' in query_params or kwargs.get('circular'):
            result = self._format_circular()
        elif 'violations' in query_params or kwargs.get('violations'):
            result = self._format_violations()
        elif query_params.get('rank') == 'fan-in':
            return self._format_fan_in()
        elif 'entrypoints' in query_params:
            return self._format_entrypoints()
        elif 'components' in query_params:
            return self._format_components()
        else:
            return self._format_all()
        if verbose:
            result['verbose'] = True
        return result

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
            # Files actually scanned with a working extractor — distinct from
            # total_files (files that happen to have >=1 import statement).
            # A file with a supported language but zero imports (common in
            # older procedural PHP/Ruby, found via real WordPress source
            # during the BACK-431 feature-breadth pass) legitimately has
            # total_files == 0 despite being fully, correctly analyzed; the
            # text renderer needs this count to tell "clean" from "unchecked."
            'scanned_files': len(self._scanned_files),
            'has_cycles': len(self._graph.find_cycle_groups()) > 0,
            'analyzer': 'imports',
            # Recognized code files whose language has no import extractor yet.
            'unsupported_extensions': dict(sorted(self._unsupported_extensions.items())),
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

    def _extract_files(self, candidates: List[Path], want_structure: bool):
        """Yield ``(Path, imports_or_None, symbols_or_None, structure_or_None)``
        per candidate file, in candidate order.

        Fans the independent per-file extraction out across processes when the
        repo is large enough to pay back pool startup (`_parallel_worker_count`);
        otherwise runs it inline. `ProcessPoolExecutor.map` preserves input
        order, so the caller's assembly is identical either way — and identical
        to the previous purely-serial implementation.
        """
        workers = _parallel_worker_count(len(candidates))
        if workers <= 1:
            for fp in candidates:
                fp_str, imports, symbols, structure = _extract_one_file(str(fp), want_structure)
                yield fp, imports, symbols, structure
            return

        from concurrent.futures import ProcessPoolExecutor
        from itertools import repeat

        n = len(candidates)
        # A few chunks per worker balances load without excessive IPC round-trips.
        chunksize = max(1, n // (workers * 8))
        paths = [str(fp) for fp in candidates]
        with ProcessPoolExecutor(max_workers=workers) as executor:
            for fp_str, imports, symbols, structure in executor.map(
                _extract_one_file, paths, repeat(want_structure), chunksize=chunksize
            ):
                yield Path(fp_str), imports, symbols, structure

    def _build_graph(
        self,
        target_path: Path,
        on_file_processed: Optional[Callable[[Path], None]] = None,
        collect_structures: bool = False,
    ) -> None:
        """Build import graph from target path (multi-language).

        Uses plugin-based architecture to automatically detect and use
        appropriate extractor for each file type.

        Only static imports are captured. Dynamic dispatch — Python's
        importlib.import_module, JS require(), Java Class.forName, Ruby autoload,
        and similar patterns — is invisible to this graph. All query modes
        (fan-in, entrypoints, unused, circular, violations) share this limitation.

        Per-file import/symbol extraction (and, when requested, AST structure
        analysis) is independent across files and runs in parallel across
        processes on large repos — see `_extract_one_file` / the module-level
        BACK-489 P1 note. The graph assembly that follows is a cheap serial
        reduce; results are consumed in file order so output is identical to a
        serial run.

        Args:
            target_path: Directory or file to analyze
            on_file_processed: Optional callback invoked once per code file
                (import-extractable or not), in deterministic file order, after
                that file's extraction. A lightweight per-file notification hook
                (structure is delivered via ``collect_structures`` below, not
                this callback).
            collect_structures: When True, also run AST structure analysis
                (`analyze_file`) on every code file during the same parallel
                pass and store the truthy results in ``self._structures`` — lets
                `reveal architecture` get per-file complexity structures without
                a second full-repo walk/parse. When False (default), no
                structure analysis is done.
        """
        supported_exts = frozenset(get_all_extensions())
        # Recognized-code extensions that lack an import extractor — used to warn
        # honestly (instead of a silent 0) when a scan hits, e.g., Swift or Scala.
        code_exts = get_code_extensions()
        unextractable: Dict[str, int] = {}
        files: List[Path] = []
        all_imports: List[ImportStatement] = []
        structures: List[Dict[str, Any]] = []

        # Phase 1 — discover candidate code files (serial, cheap: no parsing).
        # Preserves the original walk semantics exactly (skip-dirs, hidden dirs,
        # supported-or-code extension filter).
        #
        # BACK-491: during this same walk, build a `basename -> [full paths]`
        # index of *every* file under the tree (not just candidates — C/C++
        # include targets such as .inc/.tcc headers are not code-extension
        # files and must still be resolvable). Handed to include-resolving
        # extractors below so `#include` edge resolution is a dict lookup
        # instead of a full os.walk(root) per include. Built in walk order with
        # the same skip-dir/hidden filter, so it's byte-identical to the walk it
        # replaces in generic.py:resolve_import.
        candidates: List[Path] = []
        file_index: Dict[str, List[Path]] = {}
        if target_path.is_file():
            ext = target_path.suffix.lower()
            if target_path.suffix in supported_exts or ext in code_exts:
                candidates.append(target_path)
        else:
            for root, dirs, filenames in os.walk(str(target_path)):
                dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith('.')]
                for fname in filenames:
                    fp = Path(root) / fname
                    file_index.setdefault(fname, []).append(fp)
                    if fp.suffix in supported_exts or fp.suffix.lower() in code_exts:
                        candidates.append(fp)

        # Phase 2 — per-file extraction (parallel on large repos, else serial),
        # consumed in candidate order so assembly is deterministic.
        for fp, imports, symbols, structure in self._extract_files(candidates, collect_structures):
            if fp.suffix in supported_exts:
                files.append(fp)
                if imports is not None:
                    self._symbols_by_file[fp] = symbols
                    all_imports.extend(imports)
            else:
                ext = fp.suffix.lower()
                if ext in code_exts:
                    unextractable[ext] = unextractable.get(ext, 0) + 1
            if collect_structures and structure:
                structures.append(structure)
            if on_file_processed:
                on_file_processed(fp)

        self._scanned_files = set(files)
        self._unsupported_extensions = unextractable
        self._structures = structures

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
            # BACK-491: only C/C++ generic extractors resolve file-level include
            # edges (spec.resolve_includes) and can use the prebuilt index; other
            # languages' extractors keep their unchanged resolve_import signature.
            resolves_includes = getattr(getattr(extractor, 'spec', None), 'resolve_includes', False)
            for stmt in imports:
                # BACK-445: skip imports that can't cause a circular ImportError
                # at startup — matching the I002 circular-import rule's definition
                # (rules/imports/I002.py:_resolve_graph_dependencies):
                #   - TYPE_CHECKING imports never run at runtime
                #   - function-body (deferred/lazy) imports run only after all
                #     top-level code has finished importing — they are the
                #     standard pattern used to *break* cycles, so counting them
                #     as cycle edges reports phantom cycles (e.g. registry.py's
                #     lazy `from .analyzers.nginx import ...`, whose own comment
                #     says it exists "to avoid circular import").
                if stmt.is_type_checking or stmt.is_in_function:
                    continue

                if resolves_includes:
                    resolved = extractor.resolve_import(
                        stmt, base_path, search_paths=extra_paths, file_index=file_index)
                else:
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

    def _format_entrypoints(self) -> Dict[str, Any]:
        """Return files with fan-in=0 — nothing imports them.

        These are unambiguously entry points (CLIs, test runners, scripts) or dead code.
        Sorted by fan-out descending: high fan-out = likely real entry point; low = likely dead code.
        """
        if not self._graph:
            return self._build_response('entrypoints', entries=[], total_scanned=0)

        all_files = self._scanned_files | set(self._graph.files.keys()) | set(self._graph.reverse_deps.keys())
        entries = sorted(
            [
                {
                    'file': str(f),
                    'fan_out': len(self._graph.dependencies.get(f, set())),
                }
                for f in all_files
                if len(self._graph.reverse_deps.get(f, set())) == 0
            ],
            key=lambda e: (-e['fan_out'], e['file']),
        )

        return self._build_response('entrypoints', entries=entries, total_scanned=len(all_files))

    def _format_components(self) -> Dict[str, Any]:
        """Score each directory as a component using import graph cohesion.

        Groups scanned files by immediate parent directory. For each directory:
        - internal: import edges where both source and target are in this directory
        - outgoing: import edges leaving this directory
        - incoming: import edges arriving from outside this directory
        - cohesion: internal / (internal + outgoing) — fraction of imports that stay local
        - top_bridge: file in this directory with most outgoing cross-boundary edges

        High cohesion = well-encapsulated component.
        Low cohesion = files import heavily outside — may not be a real component.
        """
        from collections import defaultdict

        if not self._graph:
            return self._build_response('components', components=[], total=0)

        # Group scanned files by immediate parent — only analyze files within the scan root
        dir_files: dict = defaultdict(set)
        for f in self._scanned_files:
            dir_files[f.parent].add(f)

        components = []
        for directory, file_set in dir_files.items():
            internal = 0
            outgoing = 0
            incoming = 0
            bridge_counts: dict = defaultdict(int)

            for f in file_set:
                for dep in self._graph.dependencies.get(f, set()):
                    if dep in file_set:
                        internal += 1
                    else:
                        outgoing += 1
                        bridge_counts[f] += 1
                for src in self._graph.reverse_deps.get(f, set()):
                    if src not in file_set:
                        incoming += 1

            total_out = internal + outgoing
            cohesion = internal / total_out if total_out > 0 else 0.0
            top_bridge = str(max(bridge_counts, key=bridge_counts.get)) if bridge_counts else None

            components.append({
                'component': str(directory),
                'files': len(file_set),
                'internal': internal,
                'outgoing': outgoing,
                'incoming': incoming,
                'cohesion': round(cohesion, 3),
                'top_bridge': top_bridge,
            })

        # Sort: cohesion descending (best-structured first), files descending as tiebreak
        components.sort(key=lambda c: (-c['cohesion'], -c['files'], c['component']))

        return self._build_response('components', components=components, total=len(components))

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
        """Format circular dependency groups (one entry per SCC, not per simple path)."""
        if not self._graph:
            return {'cycles': []}

        groups = self._graph.find_cycle_groups()
        cycle_paths = [
            [str(p) for p in self._graph.find_cycle_path(group)]
            for group in groups
        ]

        return self._build_response(
            'circular_dependencies',
            cycles=[[str(p) for p in group] for group in groups],
            cycle_paths=cycle_paths,
            count=len(groups)
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
