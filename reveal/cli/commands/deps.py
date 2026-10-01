"""reveal deps — dependency health dashboard.

Thin argparse shim over the deps:// adapter (BACK-901/BACK-956); scan/render
logic lives in reveal/adapters/deps.py. Internal names are re-exported here
for backward compatibility with existing callers/tests.
"""

import argparse
import sys
from argparse import Namespace
from functools import partial
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
from ..global_flags import add_exclude_argument, add_gitignore_arguments
from ..routing.ledger import complete
from ..routing.subcommand import emit_subcommand_result


def create_deps_parser() -> argparse.ArgumentParser:
    """Create parser for reveal deps subcommand."""
    from reveal.cli.parser import _build_global_options_parser
    parser = argparse.ArgumentParser(
        prog='reveal deps',
        parents=[_build_global_options_parser()],
        description='Dependency health dashboard: external packages, circular deps, unused imports. '
                    'Exit code 0 = clean, 1 = circular dependencies or unused imports found (or a missing path).',
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
    parser.add_argument(
        '--summary-only',
        action='store_true',
        help=(
            "JSON output only: omit base.files (the full per-file import "
            "graph) and replace it with total_files/total_imports counts. "
            "circular/unused are unaffected. base.files dominates deps.json "
            "size (BACK-1040, e.g. 2.5MB of a 2.6MB file on a real repo) "
            "and is rarely what a caller wanting the dep-health signal "
            "(circular/unused) actually needs."
        )
    )
    add_exclude_argument(parser)
    add_gitignore_arguments(parser)
    return parser


def _summarize_base_files(result: dict) -> dict:
    """--summary-only (BACK-1040): replace base.files, the bulk of deps JSON on a real
    repo, with its file and import counts. circular/unused are left as they are."""
    base = result.get('base')
    if not isinstance(base, dict) or not isinstance(base.get('files'), dict):
        return result
    files = base['files']
    summary = {k: v for k, v in base.items() if k != 'files'}
    summary['total_files'] = len(files)
    summary['total_imports'] = sum(len(v) for v in files.values())
    return {**result, 'base': summary}


def run_deps(args: Namespace) -> None:
    """Run the dependency dashboard."""
    path = Path(args.path)  # as the user named it, like the URI form (BACK-1366)
    if not path.exists():
        print(f"Error: path '{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)

    # BACK-1362: --verbose was declared (inherited from the global options
    # parser) but never read here, so it silently did nothing -- same
    # "lift the default cap" meaning --verbose already has on overview/ast/
    # hotspots URIs (BACK-1226/1379).
    from reveal.adapters.overview import UNLIMITED_TOP
    top = UNLIMITED_TOP if getattr(args, 'verbose', False) else args.top
    no_unused = getattr(args, 'no_unused', False)
    no_circular = getattr(args, 'no_circular', False)

    query = (
        f'no_unused={"true" if no_unused else "false"}'
        f'&no_circular={"true" if no_circular else "false"}'
    )
    result = DepsAdapter(str(path), query).get_structure()

    circular = result['circular']
    unused = result['unused']

    if args.format == 'json' and getattr(args, 'summary_only', False):
        result = _summarize_base_files(result)
    emit_subcommand_result(result, args, name='deps', source=path, render=partial(
        DepsRenderer.render_structure, format=args.format, top=top))
    if args.format == 'json':
        return  # the findings exit below applies to text/grep only, as it always has

    # Exit 1 if there are circular deps or unused imports
    cycles = circular.get('count', 0)
    unused_count = len(unused)
    if cycles or unused_count:
        complete(args)  # a findings exit, not an error: the flag ledger still reports
        sys.exit(1)
