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
    UNLIMITED_TOP,
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
from reveal.cli.routing.flag_specs import exclude_fragment, inject_query_flags
from ..global_flags import add_gitignore_arguments


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
    parser.add_argument(
        '--all',
        action='store_true',
        help='Show every entry in each capped section (Languages, Hotspots, Entry '
             'points, Components) instead of --top N (BACK-1226). Same effect as '
             '--verbose here.'
    )
    parser.add_argument(
        '--exclude', action='append', metavar='PATTERN',
        help='Exclude files/directories matching pattern from analysis entirely '
             '(e.g., --exclude "*.min.js" --exclude "wp-includes/js/dist/*"). '
             'Repeatable. Applies to the stats/hotspots and scope sections '
             '(BACK-1042); the architecture and complex-functions sections '
             'do not yet honor it.',
    )
    add_gitignore_arguments(parser)
    return parser


def run_overview(args: Namespace) -> None:
    """Run the overview dashboard."""
    path = Path(args.path).resolve()
    if not path.exists():
        print(f"Error: path '{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)

    top = UNLIMITED_TOP if (getattr(args, 'all', False) or getattr(args, 'verbose', False)) else args.top
    no_git = getattr(args, 'no_git', False)
    no_imports = getattr(args, 'no_imports', False)

    # Same injection the overview:// URI form gets in handle_uri: --no-gitignore via the
    # adapter's declared CLI_QUERY_FLAGS, --exclude via the shared ?exclude= format.
    query = (
        f'?top={top}&no_git={"true" if no_git else "false"}'
        f'&no_imports={"true" if no_imports else "false"}'
    )
    query = inject_query_flags(query, 'overview', args)
    exclude = exclude_fragment(getattr(args, 'exclude', None))
    if exclude:
        query += f'&{exclude}'
    query = query[1:]
    result = OverviewAdapter(str(path), query).get_structure()

    if args.format == 'json':
        from reveal.utils.results import add_cli_contract_fields
        from reveal.utils.json_utils import attach_provenance
        # BACK-1178: keep the adapter's own 'contract_version' and 'meta'.
        # Stripping them made this subcommand emit a 1.0 envelope for the
        # same payload its uri:// form emits as 1.1 -- self-consistent (1.0
        # is the no-meta baseline) but a needless split for a consumer that
        # reaches the same data two ways. type/source/source_type are still
        # rebuilt below with the CLI-appropriate values.
        report = {
            k: v for k, v in result.items()
            if k not in ('type', 'source', 'source_type')
        }
        print(json.dumps(
            attach_provenance(add_cli_contract_fields(report, result_type='overview', source=path)),
            indent=2, default=str,
        ))
        return

    OverviewRenderer.render_structure(result, format=args.format, top=top)
