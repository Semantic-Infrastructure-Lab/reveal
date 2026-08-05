"""reveal testability - correlate patch pressure with production boundaries.

Thin argparse shim over the testability:// adapter (BACK-901/BACK-959);
render logic and test-path resolution live in
reveal/adapters/testability.py. Internal names are re-exported here for
backward compatibility with existing callers/tests.
"""

from __future__ import annotations

import argparse
import json
import sys
from argparse import Namespace
from pathlib import Path
from typing import List

from reveal.adapters.testability import (  # noqa: F401 - re-exported for back-compat
    TestabilityAdapter,
    TestabilityRenderer,
    _render_boundary_hotspots,
    _render_patch_hotspots,
    _render_report,
    _resolve_test_paths,
)


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

    tests: List[str] | None = getattr(args, 'tests', None)
    query_parts = [
        f'top={max(0, int(args.top))}',
        f'min_patches={max(1, int(args.min_patches))}',
        f'min_categories={max(1, int(args.min_categories))}',
        f'include_unresolved={"true" if getattr(args, "include_unresolved", False) else "false"}',
    ]
    if tests:
        query_parts.append(f'tests={",".join(tests)}')
    query = '&'.join(query_parts)

    try:
        result = TestabilityAdapter(str(path), query).get_structure()
    except ValueError:
        print(
            "reveal testability: no tests found. Pass --tests <path>.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.format == 'json':
        from reveal.utils.results import add_cli_contract_fields
        print(json.dumps(
            add_cli_contract_fields(result, result_type='testability', source=path),
            indent=2, default=str,
        ))
        return

    _render_report(result)
