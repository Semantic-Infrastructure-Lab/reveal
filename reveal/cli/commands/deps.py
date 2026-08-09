"""reveal deps — dependency health dashboard.

Thin argparse shim over the deps:// adapter (BACK-901/BACK-956); scan/render
logic lives in reveal/adapters/deps.py. Internal names are re-exported here
for backward compatibility with existing callers/tests.
"""

import argparse
import sys
from argparse import Namespace
from pathlib import Path

from reveal.adapters.deps import (  # noqa: F401 - re-exported for back-compat
    DepsAdapter,
    DepsRenderer,
    _analyse_imports,
    _local_package_names,
    _render_circular,
    _render_deps,
    _render_external_packages,
    _render_next_steps,
    _render_summary,
    _render_top_importers,
    _render_unused,
    _run_base,
    _run_circular,
    _run_unused,
)


def create_deps_parser() -> argparse.ArgumentParser:
    """Create parser for reveal deps subcommand."""
    from reveal.cli.parser import _build_global_options_parser
    parser = argparse.ArgumentParser(
        prog='reveal deps',
        parents=[_build_global_options_parser()],
        description='Dependency health dashboard: external packages, circular deps, unused imports.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  reveal deps               # Current directory\n"
            "  reveal deps ./src         # Specific directory\n"
            "  reveal deps . --no-unused # Skip unused imports section\n"
            "  reveal deps . --top 15    # Show top 15 items per section\n"
            "  reveal deps . --format json  # Machine-readable output\n"
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
        help='Number of items to show in each section (default: 10)'
    )
    parser.add_argument(
        '--no-unused',
        action='store_true',
        help='Skip the unused imports section'
    )
    parser.add_argument(
        '--no-circular',
        action='store_true',
        help='Skip the circular dependencies section'
    )
    return parser


def run_deps(args: Namespace) -> None:
    """Run the dependency dashboard."""
    path = Path(args.path).resolve()
    if not path.exists():
        print(f"Error: path '{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)

    top = args.top
    no_unused = getattr(args, 'no_unused', False)
    no_circular = getattr(args, 'no_circular', False)

    query = (
        f'no_unused={"true" if no_unused else "false"}'
        f'&no_circular={"true" if no_circular else "false"}'
    )
    result = DepsAdapter(str(path), query).get_structure()

    circular = result['circular']
    unused = result['unused']

    if args.format == 'json':
        from reveal.utils.results import add_cli_contract_fields
        from reveal.utils.json_utils import attach_provenance
        import json
        report = {
            k: v for k, v in result.items()
            if k not in ('contract_version', 'type', 'source', 'source_type', 'meta')
        }
        print(json.dumps(
            attach_provenance(add_cli_contract_fields(report, result_type='deps', source=path)),
            indent=2, default=str,
        ))
        return

    DepsRenderer.render_structure(result, format=args.format, top=top)

    # Exit 1 if there are circular deps or unused imports
    cycles = circular.get('count', 0)
    unused_count = len(unused)
    if cycles or unused_count:
        sys.exit(1)
