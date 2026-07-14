"""reveal surface — external boundary map for a codebase."""

import argparse
import json
import os
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List

from ...utils.path_utils import (
    assess_language_coverage,
    detect_non_python_language,
    is_skippable_dir,
)

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
    from reveal.adapters.ast.nav_surface_java import scan_file_surface_java
    from reveal.adapters.ast.nav_surface_csharp import scan_file_surface_csharp
    from reveal.adapters.ast.nav_surface_php import scan_file_surface_php
    from reveal.adapters.ast.nav_surface_swift import scan_file_surface_swift
    from reveal.adapters.ast.nav_surface_kotlin import scan_file_surface_kotlin
    from reveal.adapters.ast.nav_surface_ruby import scan_file_surface_ruby
    from reveal.adapters.ast.nav_surface_go import scan_file_surface_go
    from reveal.adapters.ast.nav_surface_rust import scan_file_surface_rust
    from reveal.adapters.ast.nav_surface_cpp import scan_file_surface_cpp
    collected = _collect_source_files(path, source_only=source_only)
    (py_files, ts_files, java_files, cs_files, php_files, swift_files,
     kt_files, rb_files, go_files, rs_files, cpp_files) = collected
    surfaces: Dict[str, List[Dict[str, Any]]] = {
        k: [] for k in ('cli', 'http', 'mcp', 'env', 'network', 'db', 'sdk', 'fs', 'subprocess')
    }

    unsupported_language = ''
    if not any(collected):
        unsupported_language = detect_non_python_language(path)

    # BACK-518: a handful of stray supported-language files (e.g. 15 .py tooling
    # scripts in a 1,300-file Lua repo) used to be silently presented as the
    # whole project's surface. Assess how much of the tree is actually in a
    # language `surface` analyzes so _render_report can warn on the substitution.
    coverage = assess_language_coverage(
        path, {'python', 'typescript', 'tsx', 'java', 'csharp', 'php', 'swift', 'kotlin', 'ruby', 'go', 'rust', 'cpp'})

    scanners = (
        (py_files, scan_file_surface),
        (ts_files, scan_file_surface_ts),
        (java_files, scan_file_surface_java),
        (cs_files, scan_file_surface_csharp),
        (php_files, scan_file_surface_php),
        (swift_files, scan_file_surface_swift),
        (kt_files, scan_file_surface_kotlin),
        (rb_files, scan_file_surface_ruby),
        (go_files, scan_file_surface_go),
        (rs_files, scan_file_surface_rust),
        (cpp_files, scan_file_surface_cpp),
    )
    for file_list, scanner in scanners:
        for file_path in file_list:
            for cat, entries in scanner(str(file_path)).items():
                surfaces[cat].extend(entries)

    if type_filter:
        surfaces = {k: v for k, v in surfaces.items() if k == type_filter}

    total = sum(len(v) for v in surfaces.values())
    return {
        'path': str(path),
        'total': total,
        'surfaces': surfaces,
        'unsupported_language': unsupported_language,
        'coverage': {
            'total_code_files': coverage.total_code_files,
            'analyzed_files': coverage.analyzed_files,
            'dominant_language': coverage.dominant_language,
            'dominant_count': coverage.dominant_count,
            'dominant_supported': coverage.dominant_supported,
            'warning': coverage.warning_line('surface'),
        },
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
    if suffix in ('.java', '.cs'):
        return stem.endswith('Test') or stem.endswith('Tests')
    if suffix == '.rb':
        return stem.endswith('_spec') or stem.endswith('_test') or name == 'spec_helper.rb'
    if suffix == '.go':
        return stem.endswith('_test')
    if suffix == '.rs':
        return stem.endswith('_test') or stem.endswith('_tests') or name == 'tests.rs'
    if suffix in ('.cpp', '.cc', '.cxx', '.hpp', '.hxx', '.hh'):
        return stem.endswith('_test') or stem.endswith('_tests') or stem.startswith('test_')
    return False


def _collect_source_files(path: Path, source_only: bool = False):
    """Return (py, ts, java, cs, php, swift, kotlin, ruby, go, rust, cpp) file lists for the given path."""
    _EXT_BUCKETS = (
        (frozenset({'.py'}), 0),
        (frozenset({'.ts', '.tsx'}), 1),
        (frozenset({'.java'}), 2),
        (frozenset({'.cs'}), 3),
        (frozenset({'.php'}), 4),
        (frozenset({'.swift'}), 5),
        (frozenset({'.kt', '.kts'}), 6),
        (frozenset({'.rb'}), 7),
        (frozenset({'.go'}), 8),
        (frozenset({'.rs'}), 9),
        (frozenset({'.cpp', '.cc', '.cxx', '.hpp', '.hxx', '.hh'}), 10),
    )

    def _bucket_for(suffix: str):
        for exts, idx in _EXT_BUCKETS:
            if suffix in exts:
                return idx
        return None

    buckets: List[List[Path]] = [[] for _ in _EXT_BUCKETS]

    if path.is_file():
        idx = _bucket_for(path.suffix)
        if idx is not None:
            buckets[idx].append(path)
        return tuple(buckets)

    for root, dirs, filenames in os.walk(str(path)):
        dirs[:] = [
            d for d in dirs
            if not is_skippable_dir(Path(root), d) and not d.startswith('.')
            and not (source_only and _is_test_dir(d))
        ]
        for fname in filenames:
            fpath = Path(os.path.join(root, fname))
            if source_only and _is_test_file(fpath):
                continue
            idx = _bucket_for(fpath.suffix)
            if idx is not None:
                buckets[idx].append(fpath)
    return tuple(buckets)


def _render_report(report: Dict[str, Any], top: int = None) -> None:
    path = report['path']
    total = report['total']
    surfaces = report['surfaces']

    print()
    print(f"Surface: {path}")
    print("━" * 50)
    # BACK-518: warn when reveal only understood a minority of the tree — the
    # results (total>0) are a supported-language subset, or the emptiness
    # (total==0) is a false-clean on a mostly-unsupported repo, not a real
    # "no surfaces" verdict. The coverage warning is the authoritative signal
    # and supersedes the legacy detect_non_python_language decline below.
    warning = report.get('coverage', {}).get('warning', '')
    if warning:
        print(warning)
        print()
    print(f"Total surface entries: {total}")
    if top is not None:
        print(f"Showing top {top} per category  (use --top N or omit for all)")
    print()

    if total == 0:
        if not warning:
            lang = report.get('unsupported_language', '')
            if lang:
                print("  reveal surface currently supports Python, TypeScript, Java, C#, PHP, Swift, Kotlin, Ruby, Go, Rust, and C++.")
                print(f"  No supported files found — detected {lang}.")
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
        elif kind == 'main':
            print(f"  entrypoint: {name}{loc}")
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
