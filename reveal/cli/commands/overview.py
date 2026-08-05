"""reveal overview — one-glance codebase dashboard.

Thin argparse shim over the overview:// adapter (BACK-901/BACK-958); scan/
render logic lives in reveal/adapters/overview.py. Internal names are
re-exported here for backward compatibility with existing callers/tests.
"""

import argparse
import json
import sys
from argparse import Namespace
from pathlib import Path

from reveal.adapters.overview import (  # noqa: F401 - re-exported for back-compat
    AstAdapter,
    GitAdapter,
    ImportsAdapter,
    OverviewAdapter,
    OverviewRenderer,
    StatsAdapter,
    _NON_CODE_EXT_LABELS,
    _age_label,
    _is_test_file,
    _language_breakdown,
    _relpath,
    _render_architecture,
    _render_codebase_stats,
    _render_complex_functions,
    _render_git_log,
    _render_hotspots,
    _render_language_breakdown,
    _render_next_steps,
    _render_overview,
    _render_quality_pulse,
    _resolve_git_root,
    _run_complex_functions,
    _run_git_log,
    _run_imports_analysis,
    _run_scope,
    _run_stats,
)


def create_overview_parser() -> argparse.ArgumentParser:
    """Create parser for reveal overview subcommand."""
    from reveal.cli.parser import _build_global_options_parser
    parser = argparse.ArgumentParser(
        prog='reveal overview',
        parents=[_build_global_options_parser()],
        description='One-glance codebase dashboard: languages, quality, hotspots, recent activity.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  reveal overview               # Current directory\n"
            "  reveal overview ./src         # Specific directory\n"
            "  reveal overview . --no-git    # Skip git history section\n"
            "  reveal overview . --format json  # Machine-readable output\n"
        )
    )
    parser.add_argument(
        'path',
        nargs='?',
        default='.',
        help='Directory to summarise (default: current directory)'
    )
    parser.add_argument(
        '--no-git',
        action='store_true',
        help='Skip the recent git activity section'
    )
    parser.add_argument(
        '--no-imports',
        action='store_true',
        help='Skip import graph analysis (architecture section)'
    )
    parser.add_argument(
        '--top',
        metavar='N',
        type=int,
        default=5,
        help='Number of items to show in each section (default: 5)'
    )
    return parser


def run_overview(args: Namespace) -> None:
    """Run the overview dashboard."""
    path = Path(args.path).resolve()
    if not path.exists():
        print(f"Error: path '{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)

    top = args.top
    no_git = getattr(args, 'no_git', False)
    no_imports = getattr(args, 'no_imports', False)

    query = (
        f'top={top}&no_git={"true" if no_git else "false"}'
        f'&no_imports={"true" if no_imports else "false"}'
    )
    result = OverviewAdapter(str(path), query).get_structure()

    if args.format == 'json':
        from reveal.utils.results import add_cli_contract_fields
        report = {
            k: v for k, v in result.items()
            if k not in ('contract_version', 'type', 'source', 'source_type', 'meta')
        }
        print(json.dumps(
            add_cli_contract_fields(report, result_type='overview', source=path),
            indent=2, default=str,
        ))
        return

    OverviewRenderer.render_structure(result, format=args.format, top=top)
