"""reveal hotspots — identify high-complexity, low-quality files and functions.

Thin argparse shim over the hotspots:// adapter (BACK-901/BACK-955); scan/
render logic lives in reveal/adapters/hotspots.py. Internal names are
re-exported here for backward compatibility with existing callers/tests.
"""

import argparse
import sys
from argparse import Namespace
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

    query = (
        f'top={top}&min_complexity={min_cx}'
        f'&functions_only={"true" if functions_only else "false"}'
        f'&files_only={"true" if files_only else "false"}'
    )
    adapter = HotspotsAdapter(str(path), query)
    result = adapter.get_structure()

    file_hotspots = result['file_hotspots']
    fn_hotspots = result['function_hotspots']

    if args.format == 'json':
        from reveal.utils.results import add_cli_contract_fields
        from reveal.utils.json_utils import attach_provenance
        import json
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
            attach_provenance(add_cli_contract_fields(report, result_type='hotspots', source=path)),
            indent=2, default=str,
        ))
        return

    HotspotsRenderer.render_structure(result, format=args.format, top=top, test_index=adapter.test_index)

    # Exit with non-zero if there are serious hotspots (quality < 70 or complexity > 20)
    serious_files = [h for h in file_hotspots if h.get('quality_score', 100) < 70]
    serious_fns = [f for f in fn_hotspots if f.get('complexity', 0) > 20]
    if serious_files or serious_fns:
        sys.exit(1)
