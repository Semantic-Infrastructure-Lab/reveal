"""reveal surface — external boundary map for a codebase."""

import argparse
import json
import os
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List

from ...defaults import SKIP_DIRECTORIES
from ...utils.path_utils import detect_non_python_language

# Canonical skip set lives in reveal.defaults (shared by every directory walk).
_SKIP_DIRS: frozenset = SKIP_DIRECTORIES

# Test directory names pruned by --source-only (prefix-match covers tests/, testing/, etc.)
_TEST_DIR_PREFIX = 'test'
_TEST_DIR_NAMES: frozenset = frozenset({'__tests__', 'spec', 'specs'})

# Test file patterns pruned by --source-only
_TEST_FILE_PY_NAMES: frozenset = frozenset({'conftest.py'})
_TEST_FILE_TS_INFIX = ('.test.', '.spec.')

_SURFACE_LABELS = {
    'cli': 'CLI commands / arguments',
    'http': 'HTTP routes',
    'mcp': 'MCP tool registrations',
    'env': 'Environment variables',
    'network': 'Network I/O (imports)',
    'db': 'Database / storage (imports)',
    'sdk': 'External SDK (imports)',
    'fs': 'Filesystem writes',
    'subprocess': 'Subprocess / shell execution',
}


def create_surface_parser() -> argparse.ArgumentParser:
    from reveal.cli.parser import _build_global_options_parser
    parser = argparse.ArgumentParser(
        prog='reveal surface',
        parents=[_build_global_options_parser()],
        description='Map every external surface the system touches: CLI, HTTP routes, env vars, network, filesystem writes.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  reveal surface ./src                    # All surfaces in src/\n"
            "  reveal surface .                        # Entire project\n"
            "  reveal surface . --top 20               # Top 20 entries per category\n"
            "  reveal surface . --format json\n"
            "  reveal surface . --type env             # Only env vars\n"
            "  reveal surface . --source-only          # Production code only (exclude tests)\n"
            "  reveal surface . --source-only --type sdk  # SDK egress, production only\n"
        )
    )
    parser.add_argument(
        'path',
        nargs='?',
        default='.',
        help='Directory to scan (default: current directory)'
    )
    parser.add_argument(
        '--type',
        metavar='TYPE',
        default='',
        help='Filter to one surface type: cli, http, mcp, env, network, fs, db, sdk'
    )
    parser.add_argument(
        '--top',
        metavar='N',
        type=int,
        default=None,
        help='Show only the top N entries per surface type (default: all)'
    )
    parser.add_argument(
        '--source-only',
        action='store_true',
        default=False,
        help='Exclude test files and directories from the scan (test_*.py, *_test.py, conftest.py, tests/, __tests__/, *.test.ts, *.spec.ts, etc.)'
    )
    return parser


def run_surface(args: Namespace) -> None:
    path = Path(args.path).resolve()
    if not path.exists():
        print(f"Error: path '{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)

    type_filter = getattr(args, 'type', '')
    top = getattr(args, 'top', None)
    source_only = getattr(args, 'source_only', False)
    report = _scan_surface(path, type_filter=type_filter, source_only=source_only)

    if args.format == 'json':
        print(json.dumps(report, indent=2, default=str))
        return

    _render_report(report, top=top)


def _scan_surface(path: Path, type_filter: str = '', source_only: bool = False) -> Dict[str, Any]:
    from reveal.adapters.ast.nav_surface import scan_file_surface
    from reveal.adapters.ast.nav_surface_ts import scan_file_surface_ts
    py_files, ts_files = _collect_source_files(path, source_only=source_only)
    surfaces: Dict[str, List[Dict[str, Any]]] = {
        k: [] for k in ('cli', 'http', 'mcp', 'env', 'network', 'db', 'sdk', 'fs', 'subprocess')
    }

    unsupported_language = ''
    if not py_files and not ts_files:
        unsupported_language = detect_non_python_language(path)

    for file_path in py_files:
        for cat, entries in scan_file_surface(str(file_path)).items():
            surfaces[cat].extend(entries)

    for file_path in ts_files:
        for cat, entries in scan_file_surface_ts(str(file_path)).items():
            surfaces[cat].extend(entries)

    if type_filter:
        surfaces = {k: v for k, v in surfaces.items() if k == type_filter}

    total = sum(len(v) for v in surfaces.values())
    return {
        'path': str(path),
        'total': total,
        'surfaces': surfaces,
        'unsupported_language': unsupported_language,
        '_meta': {
            'analysis_kind': 'surface-scan',
            'confidence': 'medium',
            'known_limits': [
                'taxonomy covers common libraries only — project-specific clients not detected',
                'dynamic surface registrations (e.g. plugin-loaded routes) not tracked',
                *(['test files excluded (--source-only)'] if source_only else []),
            ],
        },
    }


def _is_test_dir(name: str) -> bool:
    return name.startswith(_TEST_DIR_PREFIX) or name in _TEST_DIR_NAMES


def _is_test_file(fpath: Path) -> bool:
    name = fpath.name
    stem = fpath.stem
    suffix = fpath.suffix
    if suffix == '.py':
        return name.startswith('test_') or stem.endswith('_test') or name in _TEST_FILE_PY_NAMES
    if suffix in ('.ts', '.tsx', '.js', '.jsx'):
        return any(infix in name for infix in _TEST_FILE_TS_INFIX)
    return False


def _collect_source_files(path: Path, source_only: bool = False):
    """Return (py_files, ts_files) lists for the given path."""
    _PY_EXTS = frozenset({'.py'})
    _TS_EXTS = frozenset({'.ts', '.tsx'})

    if path.is_file():
        if path.suffix in _PY_EXTS:
            return [path], []
        if path.suffix in _TS_EXTS:
            return [], [path]
        return [], []

    py_files: List[Path] = []
    ts_files: List[Path] = []
    for root, dirs, filenames in os.walk(str(path)):
        dirs[:] = [
            d for d in dirs
            if d not in _SKIP_DIRS and not d.startswith('.')
            and not (source_only and _is_test_dir(d))
        ]
        for fname in filenames:
            fpath = Path(os.path.join(root, fname))
            if source_only and _is_test_file(fpath):
                continue
            if fpath.suffix in _PY_EXTS:
                py_files.append(fpath)
            elif fpath.suffix in _TS_EXTS:
                ts_files.append(fpath)
    return py_files, ts_files


def _render_report(report: Dict[str, Any], top: int = None) -> None:
    path = report['path']
    total = report['total']
    surfaces = report['surfaces']

    print()
    print(f"Surface: {path}")
    print("━" * 50)
    print(f"Total surface entries: {total}")
    if top is not None:
        print(f"Showing top {top} per category  (use --top N or omit for all)")
    print()

    if total == 0:
        lang = report.get('unsupported_language', '')
        if lang:
            print(f"  reveal surface currently supports Python and TypeScript.")
            print(f"  No Python or TypeScript files found — detected {lang}.")
        else:
            print("  No external surfaces detected.")
        print()
        print("ℹ Taxonomy-based — project-specific clients outside known libraries not detected.")
        print()
        return

    for key, label in _SURFACE_LABELS.items():
        entries = surfaces.get(key, [])
        if not entries:
            continue
        shown = entries[:top] if top is not None else entries
        truncated = len(entries) - len(shown)
        print(f"{label} ({len(entries)}):")
        for entry in shown:
            _render_entry(key, entry)
        if truncated:
            print(f"  … {truncated} more (use --top {len(entries)} or --type {key} to see all)")
        print()

    print("ℹ Taxonomy-based — project-specific clients outside known libraries not detected.")
    print()


def _render_entry(surface_type: str, entry: Dict[str, Any]) -> None:
    file_path = entry.get('file', '')
    line = entry.get('line', '')
    loc = f"  {file_path}:{line}" if file_path else ''

    if surface_type == 'cli':
        kind = entry.get('type', '')
        name = entry.get('name', '?')
        if kind == 'argument':
            print(f"  {name}{loc}")
        elif kind == 'subcommand':
            print(f"  subcommand: {name}{loc}")
        else:
            print(f"  @{entry.get('decorator', '?')}  {name}{loc}")

    elif surface_type == 'http':
        method = entry.get('methods', 'ANY')
        path_ = entry.get('path', '?')
        name = entry.get('name', '?')
        print(f"  {method}  {path_}  → {name}{loc}")

    elif surface_type == 'mcp':
        name = entry.get('name', '?')
        print(f"  {name}{loc}")

    elif surface_type == 'env':
        name = entry.get('name', '?')
        print(f"  {name}{loc}")

    elif surface_type in ('network', 'db', 'sdk'):
        name = entry.get('name', '?')
        print(f"  import {name}{loc}")

    elif surface_type == 'fs':
        name = entry.get('name', '?')
        target = entry.get('target', '?')
        if target and target != '?':
            print(f"  {name}({target}){loc}")
        else:
            print(f"  {name}{loc}")

    elif surface_type == 'subprocess':
        name = entry.get('name', '?')
        print(f"  {name}{loc}")
