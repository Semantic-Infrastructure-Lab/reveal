"""reveal surface — external boundary map for a codebase."""

import argparse
import importlib
import json
import os
import sys
from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List

from ...registry import _is_cpp_header_content
from ...capabilities import capability_tiers_for
from ...utils.path_utils import (
    census_and_coverage_for_path,
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
    collected = _collect_source_files(path, source_only=source_only)
    surfaces: Dict[str, List[Dict[str, Any]]] = {
        k: [] for k in ('cli', 'http', 'mcp', 'env', 'network', 'db', 'sdk', 'fs', 'subprocess')
    }

    unsupported_language = ''
    if not any(collected.values()):
        unsupported_language = detect_non_python_language(path)

    # BACK-518: a handful of stray supported-language files (e.g. 15 .py tooling
    # scripts in a 1,300-file Lua repo) used to be silently presented as the
    # whole project's surface. Assess how much of the tree is actually in a
    # language `surface` analyzes so _render_report can warn on the substitution.
    # BACK-884: one walk produces both `coverage` (gated to surface's
    # supported-language set, BACK-518) and the broader per-language `scope`
    # census below.
    census, coverage = census_and_coverage_for_path(path, _supported_coverage_languages())
    scope = census.to_scope_dict(capability_tiers=capability_tiers_for(census.language_extensions))

    for spec, file_list in collected.items():
        if not file_list:
            continue
        scan_fn = _load_scanner(spec)
        for file_path in file_list:
            for cat, entries in scan_fn(str(file_path)).items():
                surfaces[cat].extend(entries)

    if type_filter:
        surfaces = {k: v for k, v in surfaces.items() if k == type_filter}

    total = sum(len(v) for v in surfaces.values())
    return {
        'path': str(path),
        'total': total,
        'surfaces': surfaces,
        'unsupported_language': unsupported_language,
        'coverage': coverage.to_scope_dict('surface'),
        'scope': scope,
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
    if suffix in ('.cpp', '.cc', '.cxx', '.hpp', '.hxx', '.hh', '.h'):
        return stem.endswith('_test') or stem.endswith('_tests') or stem.startswith('test_')
    return False


@dataclass(frozen=True)
class _SurfaceScanner:
    """One language's surface-scan registration: which extensions it claims
    and where its `scan_file_surface_*(path) -> Dict[category, entries]`
    function lives. Single source of truth for "what languages does surface
    scan" — file-collection, dispatch, and assess_language_coverage()'s
    supported set all derive from this one list so they can't silently
    diverge by position (BACK-888/BACK-903; design doc
    BACK884_COVERAGE_CENSUS_UNIFICATION finding #3)."""
    extensions: frozenset
    module: str
    func: str


# Registration order does not matter — lookup is by extension, not position.
_SURFACE_SCANNERS: tuple = (
    _SurfaceScanner(frozenset({'.py'}), 'reveal.adapters.ast.nav_surface', 'scan_file_surface'),
    _SurfaceScanner(frozenset({'.ts', '.tsx', '.js', '.jsx'}), 'reveal.adapters.ast.nav_surface_ts', 'scan_file_surface_ts'),
    _SurfaceScanner(frozenset({'.java'}), 'reveal.adapters.ast.nav_surface_java', 'scan_file_surface_java'),
    _SurfaceScanner(frozenset({'.cs'}), 'reveal.adapters.ast.nav_surface_csharp', 'scan_file_surface_csharp'),
    _SurfaceScanner(frozenset({'.php'}), 'reveal.adapters.ast.nav_surface_php', 'scan_file_surface_php'),
    _SurfaceScanner(frozenset({'.swift'}), 'reveal.adapters.ast.nav_surface_swift', 'scan_file_surface_swift'),
    _SurfaceScanner(frozenset({'.kt', '.kts'}), 'reveal.adapters.ast.nav_surface_kotlin', 'scan_file_surface_kotlin'),
    _SurfaceScanner(frozenset({'.rb'}), 'reveal.adapters.ast.nav_surface_ruby', 'scan_file_surface_ruby'),
    _SurfaceScanner(frozenset({'.go'}), 'reveal.adapters.ast.nav_surface_go', 'scan_file_surface_go'),
    _SurfaceScanner(frozenset({'.rs'}), 'reveal.adapters.ast.nav_surface_rust', 'scan_file_surface_rust'),
    _SurfaceScanner(frozenset({'.cpp', '.cc', '.cxx', '.hpp', '.hxx', '.hh'}), 'reveal.adapters.ast.nav_surface_cpp', 'scan_file_surface_cpp'),
)

# `.h` defaults to C in the registry (BACK-630) — content-sniffed C++ headers
# route here explicitly rather than through extension lookup.
_CPP_SCANNER = next(s for s in _SURFACE_SCANNERS if '.cpp' in s.extensions)


def _load_scanner(spec: '_SurfaceScanner') -> Callable[[str], Dict[str, List[Dict[str, Any]]]]:
    return getattr(importlib.import_module(spec.module), spec.func)


def _supported_coverage_languages() -> frozenset:
    """Registry language keys surface can scan, derived from _SURFACE_SCANNERS."""
    from ...registry import language_for_extension
    langs = set()
    for spec in _SURFACE_SCANNERS:
        for ext in spec.extensions:
            lang = language_for_extension(ext)
            if lang:
                langs.add(lang)
    return frozenset(langs)


def _collect_source_files(path: Path, source_only: bool = False) -> Dict['_SurfaceScanner', List[Path]]:
    """Map each registered scanner to the files under `path` it should scan."""

    def _scanner_for(fpath: Path):
        suffix = fpath.suffix
        for spec in _SURFACE_SCANNERS:
            if suffix in spec.extensions:
                return spec
        # BACK-630: `.h` defaults to C in the registry — only route it into the
        # cpp scanner when content-sniffed as C++ (header-only classes/templates),
        # same marker set the registry uses for single-file analyzer selection.
        if suffix == '.h' and _is_cpp_header_content(str(fpath)):
            return _CPP_SCANNER
        return None

    buckets: Dict[_SurfaceScanner, List[Path]] = {spec: [] for spec in _SURFACE_SCANNERS}

    if path.is_file():
        spec = _scanner_for(path)
        if spec is not None:
            buckets[spec].append(path)
        return buckets

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
            spec = _scanner_for(fpath)
            if spec is not None:
                buckets[spec].append(fpath)
    return buckets


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
                print("  reveal surface currently supports Python, TypeScript, JavaScript, Java, C#, PHP, Swift, Kotlin, Ruby, Go, Rust, and C++.")
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
