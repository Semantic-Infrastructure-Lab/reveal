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


def add_gitignore_arguments(parser: Any) -> None:
    """--respect-gitignore / --no-gitignore, for every parser whose command walks a tree.

    One declaration so the spelling, default and help cannot drift between the
    main parser and the subcommands; apply_global_flags() is what honors it.
    """
    parser.add_argument('--respect-gitignore', action='store_true', default=True,
                        help='Skip files git ignores (default: enabled; tracked files are never skipped)')
    parser.add_argument('--no-gitignore', action='store_false', dest='respect_gitignore',
                        help='Include files git ignores')


def apply_global_flags(args: Namespace) -> None:
    """Apply flags whose effect is process-global state, from a parsed ``args``."""
    set_provenance_enabled(bool(getattr(args, 'provenance', False)))
    # BACK-1386: --no-gitignore reaches every walker, not only the three
    # adapters that used to declare it.
    set_gitignore_enabled(getattr(args, 'respect_gitignore', True) is not False)
