"""reveal surface — external boundary map for a codebase."""

import argparse
import json
import os
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List

_SKIP_DIRS: frozenset = frozenset({
    '__pycache__', '.git', '.tox', '.venv', 'venv', 'env',
    'node_modules', '.mypy_cache', '.pytest_cache', 'dist', 'build',
})

_SURFACE_LABELS = {
    'cli': 'CLI commands / arguments',
    'http': 'HTTP routes',
    'mcp': 'MCP tool registrations',
    'env': 'Environment variables',
    'network': 'Network I/O (imports)',
    'db': 'Database / storage (imports)',
    'sdk': 'External SDK (imports)',
    'fs': 'Filesystem writes',
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
            "  reveal surface ./src          # All surfaces in src/\n"
            "  reveal surface .              # Entire project\n"
            "  reveal surface . --format json\n"
            "  reveal surface . --type env   # Only env vars\n"
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
    return parser


def run_surface(args: Namespace) -> None:
    path = Path(args.path).resolve()
    if not path.exists():
        print(f"Error: path '{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)

    type_filter = getattr(args, 'type', '')
    report = _scan_surface(path, type_filter=type_filter)

    if args.format == 'json':
        print(json.dumps(report, indent=2, default=str))
        return

    _render_report(report)


def _scan_surface(path: Path, type_filter: str = '') -> Dict[str, Any]:
    from reveal.adapters.ast.nav_surface import scan_file_surface
    py_files = _collect_python_files(path)
    surfaces: Dict[str, List[Dict[str, Any]]] = {
        k: [] for k in ('cli', 'http', 'mcp', 'env', 'network', 'db', 'sdk', 'fs')
    }

    for file_path in py_files:
        for cat, entries in scan_file_surface(str(file_path)).items():
            surfaces[cat].extend(entries)

    if type_filter:
        surfaces = {k: v for k, v in surfaces.items() if k == type_filter}

    total = sum(len(v) for v in surfaces.values())
    return {
        'path': str(path),
        'total': total,
        'surfaces': surfaces,
    }


def _collect_python_files(path: Path) -> List[Path]:
    if path.is_file() and path.suffix == '.py':
        return [path]
    files: List[Path] = []
    for root, dirs, filenames in os.walk(str(path)):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith('.')]
        for fname in filenames:
            if fname.endswith('.py'):
                files.append(Path(os.path.join(root, fname)))
    return files


def _render_report(report: Dict[str, Any]) -> None:
    path = report['path']
    total = report['total']
    surfaces = report['surfaces']

    print()
    print(f"Surface: {path}")
    print("━" * 50)
    print(f"Total surface entries: {total}")
    print()

    if total == 0:
        print("  No external surfaces detected.")
        print()
        return

    for key, label in _SURFACE_LABELS.items():
        entries = surfaces.get(key, [])
        if not entries:
            continue
        print(f"{label} ({len(entries)}):")
        for entry in entries:
            _render_entry(key, entry)
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
        print(f"  {name}({target}){loc}")
