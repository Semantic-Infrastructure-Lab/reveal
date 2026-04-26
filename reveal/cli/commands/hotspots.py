"""reveal hotspots — identify high-complexity, low-quality files and functions."""

import argparse
import json
import os
import re
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, cast


def create_hotspots_parser() -> argparse.ArgumentParser:
    """Create parser for reveal hotspots subcommand."""
    from reveal.cli.parser import _build_global_options_parser
    parser = argparse.ArgumentParser(
        prog='reveal hotspots',
        parents=[_build_global_options_parser()],
        description='Identify high-complexity files and functions that need attention.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  reveal hotspots ./src              # Hotspots in a directory\n"
            "  reveal hotspots .                  # Entire project\n"
            "  reveal hotspots ./src --top 20     # Show top 20 files\n"
            "  reveal hotspots . --format json    # Machine-readable output\n"
            "  reveal hotspots . --functions-only # Only show complex functions\n"
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
        help='Number of hotspot files to show (default: 10)'
    )
    parser.add_argument(
        '--min-complexity',
        metavar='N',
        type=int,
        default=10,
        help='Minimum cyclomatic complexity to report (default: 10)'
    )
    parser.add_argument(
        '--functions-only',
        action='store_true',
        help='Show only complex functions, skip file-level hotspots'
    )
    parser.add_argument(
        '--files-only',
        action='store_true',
        help='Show only file-level hotspots, skip function analysis'
    )
    return parser


def run_hotspots(args: Namespace) -> None:
    """Run the hotspots analysis."""
    path = Path(args.path).resolve()
    if not path.exists():
        print(f"Error: path '{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)

    top = args.top
    min_cx = args.min_complexity
    functions_only = getattr(args, 'functions_only', False)
    files_only = getattr(args, 'files_only', False)

    file_hotspots: List[Dict[str, Any]] = []
    fn_hotspots: List[Dict[str, Any]] = []

    if not functions_only:
        file_hotspots = _run_file_hotspots(path, top)
    if not files_only:
        fn_hotspots = _run_function_hotspots(path, min_cx, top)

    test_index: Optional[Set[str]] = None
    if not files_only:
        test_index = _build_test_name_index(path)
        for fn in fn_hotspots:
            fn_name = fn.get('name', '')
            module_name = Path(fn.get('file', '')).stem
            fn['has_test_hint'] = fn_name in test_index or module_name in test_index

    report = {
        'path': str(path),
        'file_hotspots': file_hotspots,
        'function_hotspots': fn_hotspots,
    }

    if args.format == 'json':
        print(json.dumps(report, indent=2, default=str))
        return

    _render_report(report, top, test_index=test_index)

    # Exit with non-zero if there are serious hotspots (quality < 70 or complexity > 20)
    serious_files = [h for h in file_hotspots if h.get('quality_score', 100) < 70]
    serious_fns = [f for f in fn_hotspots if f.get('complexity', 0) > 20]
    if serious_files or serious_fns:
        sys.exit(1)


def _run_file_hotspots(path: Path, top: int) -> List[Dict[str, Any]]:
    """Fetch file-level hotspots via stats://."""
    try:
        result = subprocess.run(
            ['reveal', f'stats://{path}?hotspots=true', '--format=json'],
            capture_output=True, text=True, timeout=60
        )
        if result.stdout.strip():
            data = json.loads(result.stdout)
            hotspots = data.get('hotspots', [])
            return cast(List[Dict[str, Any]], hotspots[:top])
        return []
    except Exception:
        return []


def _run_function_hotspots(path: Path, min_complexity: int, top: int) -> List[Dict[str, Any]]:
    """Fetch high-complexity functions via ast://."""
    try:
        result = subprocess.run(
            ['reveal',
             f'ast://{path}?complexity>{min_complexity - 1}&sort=-complexity&limit={top}',
             '--format=json'],
            capture_output=True, text=True, timeout=60
        )
        if result.stdout.strip():
            data = json.loads(result.stdout)
            results = data.get('results', data.get('elements', []))
            return cast(List[Dict[str, Any]], results[:top])
        return []
    except Exception:
        return []


def _render_report(report: Dict[str, Any], top: int, test_index: Optional[Set[str]] = None) -> None:
    """Render hotspots as human-readable text."""
    path = report['path']
    file_hotspots = report['file_hotspots']
    fn_hotspots = report['function_hotspots']

    print()
    print(f"Hotspots: {path}")
    print("━" * 50)

    if not file_hotspots and not fn_hotspots:
        print("\nNo hotspots found ✅  Code quality looks good.")
        print()
        return

    _render_file_hotspots(file_hotspots, top)
    _render_function_hotspots(fn_hotspots, test_index=test_index)
    _render_summary(file_hotspots, fn_hotspots)


def _render_file_hotspots(hotspots: List[Dict[str, Any]], top: int) -> None:
    if not hotspots:
        return
    print(f"\nFile hotspots (top {min(len(hotspots), top)} by severity):")
    for h in hotspots:
        name = h.get('file', '?')
        quality = h.get('quality_score', '?')
        score = h.get('hotspot_score', 0)
        issues = h.get('issues', [])
        details = h.get('details', {})
        lines = details.get('lines', '')

        # Quality indicator
        if isinstance(quality, (int, float)):
            if quality < 70:
                icon = '❌'
            elif quality < 85:
                icon = '⚠️ '
            else:
                icon = '💡'
        else:
            icon = '  '

        lines_str = f"  {lines}L" if lines else ''
        print(f"  {icon} {name}")
        print(f"      quality: {quality}/100  score: {score}{lines_str}")
        if issues:
            print(f"      issues: {', '.join(issues)}")

        # Suggest next command
        print(f"      → reveal {name}")


def _render_function_hotspots(fns: List[Dict[str, Any]], test_index: Optional[Set[str]] = None) -> None:
    if not fns:
        return
    has_coverage_info = test_index is not None
    print("\nComplex functions:")
    if has_coverage_info:
        print("  (✅ = test found  ⚪ = no test found)")
    for fn in fns:
        name = fn.get('name', '?')
        cx = fn.get('complexity', '?')
        loc = fn.get('file', '')
        line = fn.get('line', '')
        line_count = fn.get('line_count', '')

        # Complexity indicator
        if isinstance(cx, int) and cx >= 20:
            icon = '❌'
        elif isinstance(cx, int) and cx >= 15:
            icon = '⚠️ '
        else:
            icon = '💡'

        # Test coverage heuristic
        if has_coverage_info:
            module_name = Path(loc).stem if loc else ''
            covered = name in test_index or module_name in test_index  # type: ignore[operator]
            cov = '✅' if covered else '⚪'
            cov_str = f' {cov}'
        else:
            cov_str = ''

        loc_str = f"  {loc}" if loc else ''
        lc_str = f"  ({line_count}L)" if line_count else ''
        print(f"  {icon}{cov_str} {name}  complexity: {cx}{lc_str}{loc_str}:{line}")


def _build_test_name_index(path: Path) -> Set[str]:
    """Heuristic: collect base names covered by test_* functions or test_<module>.py files."""
    names: Set[str] = set()
    pattern = re.compile(r'^\s*def\s+test_(\w+)', re.MULTILINE)
    for candidate in ('tests', 'test', 'spec'):
        test_dir = path / candidate
        if not test_dir.is_dir():
            continue
        for root, dirs, files in os.walk(str(test_dir)):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for fname in files:
                if not fname.endswith('.py'):
                    continue
                if fname.startswith('test_'):
                    names.add(fname[5:-3])  # test_liquidity_sweep.py → liquidity_sweep
                try:
                    content = Path(os.path.join(root, fname)).read_text(errors='replace')
                    names.update(m.group(1) for m in pattern.finditer(content))
                except OSError:
                    pass
    return names


def _render_summary(file_hotspots: List[Dict[str, Any]], fn_hotspots: List[Dict[str, Any]]) -> None:
    critical_files = sum(1 for h in file_hotspots if h.get('quality_score', 100) < 70)
    critical_fns = sum(1 for f in fn_hotspots if f.get('complexity', 0) > 20)
    total = len(file_hotspots) + len(fn_hotspots)

    print()
    if critical_files or critical_fns:
        parts = []
        if critical_files:
            parts.append(f"{critical_files} critical file(s)")
        if critical_fns:
            parts.append(f"{critical_fns} critical function(s)")
        print(f"Summary: {total} hotspot(s) — {', '.join(parts)} need immediate attention ❌")
    else:
        print(f"Summary: {total} hotspot(s) — no critical issues, review when convenient ⚠️")
    print()
