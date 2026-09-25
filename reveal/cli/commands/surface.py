"""reveal surface — external boundary map for a codebase.

Thin argparse shim over the surface:// adapter (BACK-904); scan/render logic
lives in reveal/adapters/surface.py. Internal names are re-exported here for
backward compatibility with existing callers/tests.
"""

import argparse
import sys
from argparse import Namespace
from pathlib import Path

from reveal.adapters.ast.surface_matrix import CATEGORIES
from reveal.adapters.surface import (  # noqa: F401 - re-exported for back-compat
    SurfaceAdapter,
    SurfaceRenderer,
    _CPP_SCANNER,
    _SURFACE_LABELS,
    _SURFACE_SCANNERS,
    _SurfaceScanner,
    _collect_source_files,
    _is_test_dir,
    _is_test_file,
    _load_scanner,
    _render_entry,
    _render_report,
    _scan_surface,
    _supported_coverage_languages,
)
from ..global_flags import add_gitignore_arguments


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
            "  reveal surface . --by dir --depth 2     # Which layers touch which boundary kinds\n"
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
        help=f"Filter to one surface type: {', '.join(CATEGORIES)}"
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
    parser.add_argument(
        '--by',
        choices=['dir'],
        default='',
        help='Group entries: dir = per-directory counts by category (which layer owns which boundary)'
    )
    parser.add_argument(
        '--depth',
        metavar='N',
        type=int,
        default=0,
        help='With --by dir: roll directories up to their first N path segments (default 0: full directory)'
    )
    add_gitignore_arguments(parser)
    return parser


def run_surface(args: Namespace) -> None:
    path = Path(args.path).resolve()
    if not path.exists():
        print(f"Error: path '{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)

    type_filter = getattr(args, 'type', '')
    top = getattr(args, 'top', None)
    source_only = getattr(args, 'source_only', False)

    by = getattr(args, 'by', '')
    depth = getattr(args, 'depth', 0)

    query = f'type={type_filter}&source_only={"true" if source_only else "false"}&by={by}&depth={depth}'
    result = SurfaceAdapter(str(path), query).get_structure()

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
            attach_provenance(add_cli_contract_fields(report, result_type='surface', source=path)),
            indent=2, default=str,
        ))
        return

    SurfaceRenderer.render_structure(result, format=args.format, top=top)
