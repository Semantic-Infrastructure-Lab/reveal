"""reveal check subcommand — run quality rules on code.

Canonical implementation of check mode. The deprecated `--check` flag in the
main parser emits a hint and delegates here, so the logic lives exactly once.

Usage:
    reveal check ./src              # directory (recursive)
    reveal check file.py            # single file
    reveal check ./src --select B   # only bug rules
    reveal check ./src --format json
"""

import sys
import argparse
from pathlib import Path
from argparse import Namespace


def create_check_parser() -> argparse.ArgumentParser:
    """Create a standalone argument parser for `reveal check`.

    Uses _build_global_options_parser() via parents= so the check subcommand
    automatically inherits --format, --copy, --verbose, --no-breadcrumbs, etc.
    """
    from reveal.cli.parser import _build_global_options_parser
    global_opts = _build_global_options_parser()
    parser = argparse.ArgumentParser(
        prog='reveal check',
        parents=[global_opts],
        description=(
            'Run reveal quality rules on a file or directory.\n\n'
            'Checks for bugs, security issues, complexity problems, and more.\n'
            'Exit code 0 = no issues, 1 = issues found.'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Examples:\n'
            '  reveal check ./src                  # check directory (recursive)\n'
            '  reveal check file.py                # check single file\n'
            '  reveal check ./src --select B,S     # bugs and security only\n'
            '  reveal check ./src --format json    # machine-readable output\n'
            '  reveal check ./src --only-failures  # hide passing checks\n'
            '\n'
            'Rule categories: B=Bugs, C=Complexity, I=Imports, M=Maintainability,\n'
            '                 R=Refactoring, S=Security, T=Types\n'
            '\n'
            'See also: reveal check --rules   (list all rules)\n'
            '          reveal check --explain B001'
        ),
    )
    add_arguments(parser)
    return parser


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add check-specific arguments to the subcommand parser."""
    parser.add_argument('path', nargs='?', help='File or directory to check')
    parser.add_argument(
        '--select', type=str, metavar='RULES',
        help='Select specific rules or categories (e.g., "B,S,T" or "B001,S701"). '
             'Categories: B=Bugs, C=Complexity, I=Imports, M=Maintainability, '
             'R=Refactoring, S=Security, T=Types',
    )
    parser.add_argument(
        '--ignore', type=str, metavar='RULES',
        help='Ignore specific rules or categories (e.g., "E501" or "C")',
    )
    parser.add_argument(
        '--only-failures', action='store_true',
        help='Only show failed/warning checks (hide healthy results)',
    )
    parser.add_argument(
        '--recursive', '-r', action='store_true',
        help='Process directory recursively (default: on for directories)',
    )
    parser.add_argument(
        '--advanced', action='store_true',
        help='Run advanced checks (enables deeper validation)',
    )
    parser.add_argument(
        '--config', type=str, metavar='FILE',
        help='Config file (.reveal.yaml or pyproject.toml)',
    )
    parser.add_argument(
        '--no-group', action='store_true', dest='no_group',
        help='Show every check result individually (disables collapsing repeated rules)',
    )
    parser.add_argument(
        '--rules', action='store_true',
        help='List all available quality rules',
    )
    parser.add_argument(
        '--explain', type=str, metavar='CODE',
        help='Explain a specific rule (e.g., "B001")',
    )


def run_check(args: Namespace) -> None:
    """Run check mode — canonical implementation.

    Called both by `reveal check <path>` (subcommand) and by the deprecated
    `--check` flag via handle_file_or_directory() in routing.py.
    Both paths end up here; logic lives exactly once.
    """
    from reveal.utils import check_for_updates
    check_for_updates()

    # Introspection flags exit early
    if getattr(args, 'rules', False):
        from reveal.cli.handlers import handle_rules_list
        from reveal import __version__
        handle_rules_list(__version__)
        return

    if getattr(args, 'explain', None):
        from reveal.cli.handlers import handle_explain_rule
        handle_explain_rule(args.explain)
        return

    path_str = getattr(args, 'path', None)
    if not path_str:
        print("Error: path is required for reveal check", file=sys.stderr)
        sys.exit(1)

    path = Path(path_str)
    if not path.exists():
        print(f"Error: {path_str}: no such file or directory", file=sys.stderr)
        sys.exit(1)

    if path.is_dir():
        from reveal.cli.file_checker import handle_recursive_check
        args.recursive = True
        handle_recursive_check(path, args)
    else:
        # Single-file check: bridge into handle_file() which routes on args.check
        args.check = True
        from reveal.file_handler import handle_file
        handle_file(str(path), None, False, getattr(args, 'format', 'text'), args)
