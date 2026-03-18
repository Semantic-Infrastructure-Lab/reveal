"""reveal deps — dependency health dashboard."""

import argparse
import json
import subprocess
import sys
from argparse import Namespace
from collections import Counter
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

# Python stdlib module names (Python 3.10+, with fallback set for older versions)
try:
    import sys as _sys
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


def create_deps_parser() -> argparse.ArgumentParser:  # noqa: uncalled
    """Create parser for reveal deps subcommand."""
    from reveal.cli.parser import _build_global_options_parser
    parser = argparse.ArgumentParser(
        prog='reveal deps',
        parents=[_build_global_options_parser()],
        description='Dependency health dashboard: external packages, circular deps, unused imports.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  reveal deps               # Current directory\n"
            "  reveal deps ./src         # Specific directory\n"
            "  reveal deps . --no-unused # Skip unused imports section\n"
            "  reveal deps . --top 15    # Show top 15 items per section\n"
            "  reveal deps . --format json  # Machine-readable output\n"
        )
    )
    parser.add_argument(
        'path',
        nargs='?',
        default='.',
        help='Directory to analyse (default: current directory)'
    )
    parser.add_argument(
        '--top',
        metavar='N',
        type=int,
        default=10,
        help='Number of items to show in each section (default: 10)'
    )
    parser.add_argument(
        '--no-unused',
        action='store_true',
        help='Skip the unused imports section'
    )
    parser.add_argument(
        '--no-circular',
        action='store_true',
        help='Skip the circular dependencies section'
    )
    return parser


def run_deps(args: Namespace) -> None:  # noqa: uncalled
    """Run the dependency dashboard."""
    path = Path(args.path).resolve()
    if not path.exists():
        print(f"Error: path '{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)

    top = args.top
    no_unused = getattr(args, 'no_unused', False)
    no_circular = getattr(args, 'no_circular', False)

    base = _run_base(path)
    circular = {} if no_circular else _run_circular(path)
    unused = [] if no_unused else _run_unused(path)

    report = {
        'path': str(path),
        'base': base,
        'circular': circular,
        'unused': unused,
    }

    if args.format == 'json':
        print(json.dumps(report, indent=2, default=str))
        return

    _render_deps(report, top)

    # Exit 1 if there are circular deps or unused imports
    cycles = circular.get('count', 0)
    unused_count = len(unused)
    if cycles or unused_count:
        sys.exit(1)


# ── Data collectors ────────────────────────────────────────────────────────────

def _run_base(path: Path) -> Dict[str, Any]:
    """Fetch base import map via imports://."""
    try:
        result = subprocess.run(
            ['reveal', f'imports://{path}', '--format=json'],
            capture_output=True, text=True, timeout=120
        )
        if result.stdout.strip():
            return json.loads(result.stdout)
    except Exception:
        pass
    return {}


def _run_circular(path: Path) -> Dict[str, Any]:
    """Fetch circular dependency cycles via imports://?circular."""
    try:
        result = subprocess.run(
            ['reveal', f'imports://{path}?circular', '--format=json'],
            capture_output=True, text=True, timeout=60
        )
        if result.stdout.strip():
            return json.loads(result.stdout)
    except Exception:
        pass
    return {}


def _run_unused(path: Path) -> List[Dict[str, Any]]:
    """Fetch unused imports via imports://?unused."""
    try:
        result = subprocess.run(
            ['reveal', f'imports://{path}?unused', '--format=json'],
            capture_output=True, text=True, timeout=60
        )
        if result.stdout.strip():
            data = json.loads(result.stdout)
            return data.get('unused', [])
    except Exception:
        pass
    return []


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
                parts.append(str(Path(fp).relative_to(base_path)))
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
            rel = str(Path(filepath).relative_to(base_path))
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
