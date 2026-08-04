"""reveal surface — external boundary map for a codebase.

Thin argparse shim over the surface:// adapter (BACK-904); scan/render logic
lives in reveal/adapters/surface.py. Internal names are re-exported here for
backward compatibility with existing callers/tests.
"""

import argparse
import sys
from argparse import Namespace
from pathlib import Path

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

    query = f'type={type_filter}&source_only={"true" if source_only else "false"}'
    result = SurfaceAdapter(str(path), query).get_structure()

    if args.format == 'json':
        from reveal.utils.results import add_cli_contract_fields
        import json
        report = {
            k: v for k, v in result.items()
            if k not in ('contract_version', 'type', 'source', 'source_type', 'meta')
        }
        print(json.dumps(
            add_cli_contract_fields(report, result_type='surface', source=path),
            indent=2, default=str,
        ))
        return

    SurfaceRenderer.render_structure(result, format=args.format, top=top)
