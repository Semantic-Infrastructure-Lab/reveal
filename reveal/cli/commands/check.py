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
            'Exit code 0 = no issues, 1 = issues found, 2 = usage error, '
            '3 = scan incomplete (a file could not be parsed/checked).'
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
        '--profile', type=str, metavar='NAME',
        help='Apply a named rule preset (e.g., maintenance, security, ci-strict). '
             'Use reveal --profiles to list available profiles.',
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
        '--exclude', action='append', metavar='PATTERN',
        help='Exclude files/directories matching pattern from analysis entirely '
             '(e.g., --exclude "*.min.js" --exclude "wp-includes/js/dist/*"). '
             'Repeatable. Excluded files are never parsed or checked (BACK-1042).',
    )
    parser.add_argument(
        '--respect-gitignore', action='store_true', default=True,
        help='Respect .gitignore rules when collecting files to check (default: enabled)',
    )
    parser.add_argument(
        '--no-gitignore', action='store_false', dest='respect_gitignore',
        help='Ignore .gitignore rules and check all files',
    )
    parser.add_argument(
        '--no-group', action='store_true', dest='no_group',
        help='Show every check result individually (disables collapsing repeated rules)',
    )
    parser.add_argument(
        '--severity', type=str, metavar='LEVEL',
        help='Minimum severity level to report: low, medium, high, critical. Default: show all',
    )
    parser.add_argument(
        '--limit', type=int, metavar='N', default=50,
        help='Cap text output to the first N files with issues, then print a "+N more files" '
             'summary footer instead of continuing (BACK-539; a large monorepo can otherwise '
             'print 100K+ lines). Set to 0 to disable the cap. Ignored for --format json.',
    )
    parser.add_argument(
        '--profile-rules', action='store_true', dest='profile_rules',
        help='Print a per-rule wall-time cost breakdown instead of the normal issue report '
             '(BACK-540): which rule(s) dominate check\'s cost on this tree. Runs serially, '
             'one real pass — use this instead of a manual --ignore RULE A/B or cProfile.',
    )
    parser.add_argument(
        '--rules', action='store_true',
        help='List all available quality rules',
    )
    parser.add_argument(
        '--explain', type=str, metavar='CODE',
        help='Explain a specific rule (e.g., "B001")',
    )
    parser.add_argument(
        '--max-items', type=int, metavar='N', dest='max_items',
        help='Stop after N violations total (budget mode) -- documented elsewhere as a '
             '"universal adapter option" but previously rejected by check specifically '
             '(BACK-1181). Same semantics as URI adapters\' --max-items: total_available '
             'is still reported so truncation is visible.',
    )
    parser.add_argument(
        '--max-snippet-chars', type=int, metavar='N', dest='max_snippet_chars',
        help='Truncate the embedded source-code excerpt (the 📝 line / JSON "context" '
             'field) to N characters (BACK-1181). rule/file/line/severity/suggestion are '
             'never truncated. See also --no-snippets to omit the excerpt entirely.',
    )
    parser.add_argument(
        '--no-snippets', action='store_true', dest='no_snippets',
        help='Omit the embedded source-code excerpt (the 📝 line / JSON "context" field) '
             'from violation output -- rule/file/line/severity/suggestion still print. For '
             'a compliance-sensitive engagement where the evidence output needs to be '
             'shareable without embedding actual source (BACK-1182).',
    )
    parser.add_argument(
        '--exit-zero', action='store_true', dest='exit_zero',
        help='Always exit 0 once the scan itself completed, regardless of findings or '
             'degraded/unparseable files -- moves "were there issues" into the JSON/text '
             'output only (meta/summary), matching how every other reveal adapter behaves. '
             'A genuine usage error (exit 2, e.g. bad arguments) still exits nonzero. '
             'Makes check safe to drop into a set -e / CI pipeline (BACK-1186).',
    )


def run_check(args: Namespace) -> None:
    """Run check mode — canonical implementation.

    Called both by `reveal check <path>` (subcommand) and by the deprecated
    `--check` flag via handle_file_or_directory() in routing.py.
    Both paths end up here; logic lives exactly once.
    """
    from reveal.utils import check_for_updates
    check_for_updates()

    # BACK-1248: --also-json (BACK-1184) is only wired for the URI-adapter
    # render paths in cli/routing/uri.py -- `check` has no uri:// form and
    # this subcommand path never calls write_also_json(). Previously the
    # flag was silently accepted, no file was written, and stderr stayed
    # empty; the silence (not the limitation itself) was the defect, so
    # disclose it here rather than implementing full subcommand support.
    if getattr(args, 'also_json', None):
        print(
            f"Warning: --also-json has no effect on 'reveal check' — it only writes for "
            "URI-adapter queries (e.g. 'overview://path'). Use --format json instead.",
            file=sys.stderr,
        )

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

    # Resolve --profile into select/ignore before running checks
    profile_name = getattr(args, 'profile', None)
    if profile_name:
        from reveal.rules.profiles import resolve_profile
        from reveal.config import RevealConfig

        # Load project profiles from .reveal.yaml (if any) before resolving
        path_for_config = getattr(args, 'path', None) or '.'
        try:
            cfg = RevealConfig.get(start_path=Path(path_for_config))
            project_profiles = cfg._config.get('profiles') or None
        except Exception:
            project_profiles = None

        try:
            resolved = resolve_profile(profile_name, user_profiles=project_profiles)
        except KeyError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        # Profile values are lower-priority than explicit --select/--ignore
        if not args.select:
            args.select = ','.join(resolved['select'])
        if not args.ignore and resolved['ignore']:
            args.ignore = ','.join(resolved['ignore'])

    path_str = getattr(args, 'path', None)
    if not path_str:
        print("Error: path is required for reveal check", file=sys.stderr)
        sys.exit(1)

    # BACK-261: detect URI where a file path was expected
    import re as _re
    if _re.match(r'^[a-z][a-z0-9+\-.]+://', path_str):
        print(f"Error: '{path_str}' looks like a URI, not a file path.", file=sys.stderr)
        print(f"  Did you mean: reveal {path_str} --check", file=sys.stderr)
        sys.exit(1)

    path = Path(path_str)
    if not path.exists():
        print(f"Error: {path_str}: no such file or directory", file=sys.stderr)
        sys.exit(1)

    if path.is_dir():
        args.recursive = True
        if getattr(args, 'profile_rules', False):
            from reveal.cli.file_checker import handle_profile_rules
            handle_profile_rules(path, args)
        else:
            from reveal.cli.file_checker import handle_recursive_check
            handle_recursive_check(path, args)
    else:
        from reveal.file_handler import _get_analyzer_or_exit, _build_file_cli_overrides
        from reveal.checks import run_pattern_detection
        from reveal.config import RevealConfig
        allow_fallback = not getattr(args, 'no_fallback', False)
        analyzer = _get_analyzer_or_exit(str(path), allow_fallback)
        cli_overrides = _build_file_cli_overrides(args)
        config = RevealConfig.get(start_path=path.parent, cli_overrides=cli_overrides or None)
        violations, degraded = run_pattern_detection(
            analyzer, str(path), getattr(args, 'format', 'text'), args, config=config
        )
        # BACK-1099: a file that didn't parse cleanly (or a rule that raised)
        # means `violations` isn't a trustworthy signal -- "0 issues" here
        # can mean "clean" or "couldn't actually check it". Exit 3 makes
        # that distinguishable from clean (0) and from real issues (1) at
        # the shell level; see internal-docs/design/EXIT_CODE_CONTRACT.md.
        from reveal.cli.file_checker import check_exit_code
        sys.exit(check_exit_code(
            violations,
            files_degraded=1 if degraded else 0,
            exit_zero=getattr(args, 'exit_zero', False),
        ))
