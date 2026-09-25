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

from ..utils.gitignore import set_gitignore_enabled
from ..utils.json_utils import set_provenance_enabled


def apply_global_flags(args: Namespace) -> None:
    """Apply flags whose effect is process-global state, from a parsed ``args``."""
    set_provenance_enabled(bool(getattr(args, 'provenance', False)))
    # BACK-1386: --no-gitignore reaches every walker, not only the three
    # adapters that used to declare it.
    set_gitignore_enabled(getattr(args, 'respect_gitignore', True) is not False)
