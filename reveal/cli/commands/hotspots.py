"""reveal hotspots — identify high-complexity, low-quality files and functions.

Thin argparse shim over the hotspots:// adapter (BACK-901/BACK-955); scan/
render logic lives in reveal/adapters/hotspots.py. Internal names are
re-exported here for backward compatibility with existing callers/tests.
"""

import argparse
import sys
from argparse import Namespace
from functools import partial
from pathlib import Path

from reveal.adapters.hotspots import (  # noqa: F401 - re-exported for back-compat
    HotspotsAdapter,
    HotspotsRenderer,
    _build_test_name_index,
    _camel_to_snake,
    _is_covered,
    _render_file_hotspots,
    _render_function_hotspots,
    _render_report,
    _render_summary,
    _run_file_hotspots,
    _run_function_hotspots,
)
from ..global_flags import add_exclude_argument, add_gitignore_arguments
from ..routing.ledger import complete
from ..routing.subcommand import emit_subcommand_result


def create_hotspots_parser() -> argparse.ArgumentParser:
    """Create parser for reveal hotspots subcommand."""
    from reveal.cli.parser import _build_global_options_parser
    parser = argparse.ArgumentParser(
        prog='reveal hotspots',
        parents=[_build_global_options_parser()],
        description='Identify high-complexity files and functions that need attention. '
                    'Exit code 0 = nothing serious, 1 = a file below quality 70 or a function above '
                    'complexity 20 (or a missing path).',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  reveal hotspots ./src              # Hotspots in a directory\n"
            "  reveal hotspots .                  # Entire project\n"
            "  reveal hotspots ./src --top 20     # Top 20 files and top 20 functions\n"
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
        help='Number of hotspots to show per list (default: 10; 0 = all)'
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
    add_exclude_argument(parser)
    add_gitignore_arguments(parser)
    return parser


def run_hotspots(args: Namespace) -> None:
    """Run the hotspots analysis."""
    path = Path(args.path)  # as the user named it, like the URI form (BACK-1366)
    if not path.exists():
        print(f"Error: path '{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)

    # BACK-1362: --verbose was declared (inherited from the global options
    # parser) but never read here, so it silently did nothing -- give it the
    # same "lift the cap" meaning hotspots://...?all=true already has (the
    # subcommand has no --all of its own).
    from reveal.adapters.overview import UNLIMITED_TOP
    top = UNLIMITED_TOP if getattr(args, 'verbose', False) or args.top <= 0 else args.top  # 0 = no cap (BACK-1505)
    min_cx = args.min_complexity
    functions_only = getattr(args, 'functions_only', False)
    files_only = getattr(args, 'files_only', False)

    query = (
        f'top={top}&min_complexity={min_cx}'
        f'&functions_only={"true" if functions_only else "false"}'
        f'&files_only={"true" if files_only else "false"}'
    )
    # The --exclude/REVEAL_IGNORE walk scope is published by the subcommand seam
    # (cli/routing/subcommand.py), as handle_uri publishes it for hotspots://.
    adapter = HotspotsAdapter(str(path), query)
    result = adapter.get_structure()

    file_hotspots = result['file_hotspots']
    fn_hotspots = result['function_hotspots']

    emit_subcommand_result(result, args, name='hotspots', source=path, render=partial(
        HotspotsRenderer.render_structure, format=args.format, top=top, test_index=adapter.test_index))
    if args.format == 'json':
        return  # the findings exit below applies to text/grep only, as it always has

    # Exit with non-zero if there are serious hotspots (quality < 70 or complexity > 20)
    serious_files = [h for h in file_hotspots if h.get('quality_score', 100) < 70]
    serious_fns = [f for f in fn_hotspots if f.get('complexity', 0) > 20]
    if serious_files or serious_fns:
        complete(args)  # a findings exit, not an error: the flag ledger still reports
        sys.exit(1)
