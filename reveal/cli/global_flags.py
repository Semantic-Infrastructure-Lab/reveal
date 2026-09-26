"""Post-parse hook for global flags that set process-wide state (BACK-1378).

Reveal has two CLI entry paths (main.py's subcommand dispatch and ``_main_impl``) plus the
MCP server. A global flag applied in only one of them is silently dropped in the others;
--provenance was exactly that (BACK-1034, fixed by copying the call). Every path calls this
one function right after it has a parsed ``args``.

--copy is not here: it must wrap the whole run (tee stdout, copy on exit), so
main._dispatch_and_run applies it around both entry paths.
"""

from __future__ import annotations

from argparse import Namespace
from typing import Any

from ..utils.gitignore import set_gitignore_enabled
from ..utils.json_utils import set_provenance_enabled


# Flags in effect for every command once parsed: applied by apply_global_flags below, or, for
# --copy, around the whole run. The flag ledger (BACK-1514) never reports them as unused.
PROCESS_GLOBAL_FLAGS = frozenset({'provenance', 'respect_gitignore', 'copy'})


def add_gitignore_arguments(parser: Any) -> None:
    """--respect-gitignore / --no-gitignore, for every parser whose command walks a tree.

    One declaration so the spelling, default and help cannot drift between the
    main parser and the subcommands; apply_global_flags() is what honors it.
    """
    parser.add_argument('--respect-gitignore', action='store_true', default=True,
                        help='Skip files git ignores (default: enabled; tracked files are never skipped)')
    parser.add_argument('--no-gitignore', action='store_false', dest='respect_gitignore',
                        help='Include files git ignores')


_EXCLUDE_HELP = ('Exclude files/directories matching pattern from analysis entirely '
                 '(e.g., --exclude "*.min.js" --exclude "vendor/"). Repeatable. Patterns are '
                 'relative to the analysed path; REVEAL_IGNORE patterns are added to them.')


def add_exclude_argument(parser: Any, help: str = _EXCLUDE_HELP) -> None:
    """--exclude, for every parser whose command walks a tree (BACK-1517).

    One declaration so the spelling and action cannot drift. What honors it is the walk
    scope each dispatch publishes (``utils.exclusions.dispatch_scope``): handle_uri for
    URIs, ``cli/routing/subcommand.py`` for subcommands. A command that accepts it and
    never walks gets a flag-ledger note, not silence.
    """
    parser.add_argument('--exclude', action='append', metavar='PATTERN', help=help)


def apply_global_flags(args: Namespace) -> None:
    """Apply flags whose effect is process-global state, from a parsed ``args``."""
    set_provenance_enabled(bool(getattr(args, 'provenance', False)))
    # BACK-1386: --no-gitignore reaches every walker, not only the three
    # adapters that used to declare it.
    set_gitignore_enabled(getattr(args, 'respect_gitignore', True) is not False)
