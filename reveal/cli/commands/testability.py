"""reveal testability - correlate patch pressure with production boundaries."""

from __future__ import annotations

import argparse
import json
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List


def create_testability_parser() -> argparse.ArgumentParser:
    from reveal.cli.parser import _build_global_options_parser

    parser = argparse.ArgumentParser(
        prog='reveal testability',
        parents=[_build_global_options_parser()],
        description='Find testability pressure by joining test patch usage with production boundary fan-out.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  reveal testability src --tests tests\n"
            "  reveal testability . --tests tests integration_tests --top 20\n"
            "  reveal testability src --tests tests --format json\n"
            "  reveal patches://tests?group=target  # raw patch scan\n"
        ),
    )
    parser.add_argument(
        'path',
        nargs='?',
        default='.',
        help='Production source path to analyze (default: current directory)',
    )
    parser.add_argument(
        '--tests',
        nargs='+',
        help='Test paths to scan. Defaults to tests/, test/, or spec/ under the source root.',
    )
    parser.add_argument(
        '--top',
        type=int,
        default=20,
        help='Maximum patch and boundary groups to show (default: 20)',
    )
    parser.add_argument(
        '--min-patches',
        type=int,
        default=3,
        help='Minimum patches for a target group (default: 3)',
    )
    parser.add_argument(
        '--min-categories',
        type=int,
        default=3,
        help='Minimum boundary categories for unpatched functions (default: 3)',
    )
    parser.add_argument(
        '--include-unresolved',
        action='store_true',
        help='Include low-count unresolved patch targets in text/JSON results',
    )
    return parser


def run_testability(args: Namespace) -> None:
    path = Path(args.path).resolve()
    if not path.exists():
        print(f"reveal testability: path not found: {path}", file=sys.stderr)
        sys.exit(1)

    test_paths = _resolve_test_paths(path, getattr(args, 'tests', None))
    if not test_paths:
        print(
            "reveal testability: no tests found. Pass --tests <path>.",
            file=sys.stderr,
        )
        sys.exit(1)

    from reveal.testability.report import build_testability_report

    report = build_testability_report(
        str(path),
        [str(p) for p in test_paths],
        top=max(0, int(args.top)),
        min_patches=max(1, int(args.min_patches)),
        min_categories=max(1, int(args.min_categories)),
        include_unresolved=bool(getattr(args, 'include_unresolved', False)),
    )

    if args.format == 'json':
        print(json.dumps(report, indent=2, default=str))
        return

    _render_report(report)


def _resolve_test_paths(src_path: Path, tests: List[str] | None) -> List[Path]:
    if tests:
        return [Path(t).expanduser().resolve() for t in tests if Path(t).expanduser().exists()]

    roots = []
    candidates = []
    if src_path.is_dir():
        candidates.append(src_path)
        candidates.append(src_path.parent)
    else:
        candidates.append(src_path.parent)

    for root in candidates:
        for name in ('tests', 'test', 'spec'):
            candidate = root / name
            if candidate.exists():
                roots.append(candidate.resolve())
    return sorted(set(roots))


def _render_report(report: Dict[str, Any]) -> None:
    print(f"Testability: {report.get('source')}")
    tests = ', '.join(report.get('tests', []))
    print(f"Tests: {tests}")
    print("-" * 50)
    summary = report.get('summary', {})
    print(
        f"Patch uses: {summary.get('total_patch_uses', 0)}  "
        f"Patch targets: {summary.get('total_patch_targets', 0)}"
    )
    print()

    _render_patch_hotspots(report.get('patch_hotspots', []))
    _render_boundary_hotspots(report.get('boundary_hotspots', []))

    print("Summary")
    print(f"  {summary.get('patch_groups_reported', 0)} patch hotspot(s) reported")
    print(f"  {summary.get('boundary_profiles_reported', 0)} boundary hotspot(s) reported")


def _render_patch_hotspots(rows: List[Dict[str, Any]]) -> None:
    print("Production Patch Hotspots")
    if not rows:
        print("  none above threshold")
        print()
        return
    for row in rows:
        print()
        print(f"  {row.get('key')}")
        print(
            f"    patched {row.get('patch_count', 0)} times across "
            f"{row.get('test_count', 0)} test(s)"
        )
        categories = row.get('boundary_categories') or []
        if categories:
            print(f"    boundary categories: {', '.join(categories)}")
        profiles = row.get('related_profiles') or []
        if profiles:
            print("    related production functions:")
            for profile in profiles[:3]:
                print(
                    f"      {profile.get('file')}::{profile.get('function')} "
                    f"(cx {profile.get('complexity')}, line {profile.get('line')})"
                )
        print(f"    suggestion: {row.get('suggestion')}")
    print()


def _render_boundary_hotspots(rows: List[Dict[str, Any]]) -> None:
    print("Boundary Fan-Out Hotspots")
    if not rows:
        print("  none above threshold")
        print()
        return
    for row in rows:
        print()
        print(f"  {row.get('file')}::{row.get('function')}")
        print(f"    complexity: {row.get('complexity')}  lines: {row.get('lines')}")
        print(f"    categories: {', '.join(row.get('categories', []))}")
        if row.get('patch_count'):
            print(f"    related patch pressure: {row.get('patch_count')} patches")
        print(f"    suggestion: {row.get('suggestion')}")
    print()
