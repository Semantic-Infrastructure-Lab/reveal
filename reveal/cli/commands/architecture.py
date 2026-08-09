"""reveal architecture — targeted architectural brief for a directory.

Thin argparse shim over the architecture:// adapter (BACK-901/BACK-957);
brief scan/render logic lives in reveal/adapters/architecture.py. The
`--against <ref>` git-diff branch stays here — it delegates to the dedicated
reveal.diff.architecture_diff module and has its own contract/tests
independent of the main brief. Internal names are re-exported here for
backward compatibility with existing callers/tests.
"""
import argparse
import json
import sys
from argparse import Namespace
from pathlib import Path

from reveal.adapters.architecture import (  # noqa: F401 - re-exported for back-compat
    ArchitectureAdapter,
    ArchitectureRenderer,
    _build_next_commands,
    _compute_risks,
    _format_imports_data,
    _is_test_file,
    _relpath,
    _render_brief,
    _render_components,
    _render_core_abstractions,
    _render_entry_points,
    _render_next_commands,
    _render_risks,
    _run_combined_analysis,
    _run_complex_functions,
    _run_imports_analysis,
    _run_scope,
)


def create_architecture_parser() -> argparse.ArgumentParser:
    from reveal.cli.parser import _build_global_options_parser
    parser = argparse.ArgumentParser(
        prog='reveal architecture',
        parents=[_build_global_options_parser()],
        description=(
            'Architectural brief for a directory: entry points, core abstractions, '
            'risks, and suggested next commands.'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  reveal architecture src/              # Brief for a subdirectory\n"
            "  reveal architecture .                 # Whole project\n"
            "  reveal architecture src/ --format json  # Machine-readable output\n"
            "  reveal architecture src/ --no-imports   # Skip import graph analysis\n"
        ),
    )
    parser.add_argument(
        'path',
        nargs='?',
        default='.',
        help='Directory to analyze (default: current directory)',
    )
    parser.add_argument(
        '--no-imports',
        action='store_true',
        help='Skip import graph analysis',
    )
    parser.add_argument(
        '--top',
        metavar='N',
        type=int,
        default=5,
        help='Number of items to show per section (default: 5)',
    )
    parser.add_argument(
        '--against',
        metavar='REF',
        default=None,
        help=(
            'Diff architecture against a git ref (branch, tag, or commit). '
            'Base = REF (materialized read-only via git), head = the current '
            'working tree. Deltas are only meaningful for graph-backed '
            'languages (Python/JS/TS/Go/Rust/C/C++ today) — see BACK-487/488.'
        ),
    )
    return parser


def run_architecture(args: Namespace) -> None:
    path = Path(args.path).resolve()
    if not path.exists():
        print(f"Error: path '{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)

    against = getattr(args, 'against', None)
    if against:
        _run_architecture_diff(path, against, args)
        return

    top = args.top
    no_imports = getattr(args, 'no_imports', False)

    query = f'top={top}&no_imports={"true" if no_imports else "false"}'
    result = ArchitectureAdapter(str(path), query).get_structure()

    if args.format == 'json':
        from reveal.utils.results import add_cli_contract_fields
        from reveal.utils.json_utils import attach_provenance
        report = {
            k: v for k, v in result.items()
            if k not in ('contract_version', 'type', 'source', 'source_type', 'meta')
        }
        print(json.dumps(
            attach_provenance(add_cli_contract_fields(report, result_type='architecture', source=path)),
            indent=2, default=str,
        ))
        return

    ArchitectureRenderer.render_structure(result, format=args.format, top=top, no_imports=no_imports)


def _run_architecture_diff(path: Path, against: str, args: Namespace) -> None:
    """BACK-441: `reveal architecture <path> --against <ref>` branch.

    Delegates all diff logic to reveal.diff.architecture_diff — see that
    module for the materialization + delta-computation implementation.
    """
    from reveal.diff.architecture_diff import run_architecture_diff, render_diff_brief

    try:
        report = run_architecture_diff(path, against, top_n=max(args.top, 1) * 4)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.format == 'json':
        from reveal.utils.results import add_cli_contract_fields
        from reveal.utils.json_utils import attach_provenance
        print(json.dumps(
            attach_provenance(add_cli_contract_fields(report, result_type='architecture_diff', source=path)),
            indent=2, default=str,
        ))
        return

    render_diff_brief(report)
