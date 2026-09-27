"""Subcommand dispatch (BACK-1539): what handle_uri gives a URI, given once to ``reveal <name>``.

The ``cli/commands/*`` runners build their adapters directly, so the URI plumbing never
reached them: ``REVEAL_IGNORE`` pruned ``surface://`` but not ``reveal surface``, and a flag a
subcommand's parser accepted but its runner never read (``reveal surface --verbose``) was
dropped without a word, while the same flag on the URI form got a ledger note. Every
subcommand already enters through one call site (``main._prepare``, from the one Invocation,
BACK-1058); this is the seam behind it, so a cross-cutting concern lands here once instead of
in 15 runners.

What it does not unify, deliberately: the runners keep their own output contracts (a JSON
``type`` named for the subcommand, ``deps``/``hotspots`` exiting 1 on findings as a CI gate --
EXIT_CODE_CONTRACT). Both forms share one parse-and-dispatch path (``main._dispatch_and_run``),
not one handler.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from typing import Callable

from ...utils.exclusions import dispatch_scope, exclusion_scope
from .ledger import FlagLedger, peek


def dispatch_subcommand(name: str, parser: ArgumentParser,
                        runner: Callable[[Namespace], None], args: Namespace) -> None:
    """Run ``reveal <name>`` with the flag ledger and the dispatch walk scope.

    Flags are judged against ``parser``'s own defaults. The scope is ``--exclude`` plus
    REVEAL_IGNORE, rooted at the subcommand's ``path`` (``review``: ``target``) when that is
    an existing path. A ``review`` git range, ``health``'s several targets or a ``scaffold``
    name has no walk root, so nothing is published. A runner that exits after producing its
    result (a findings exit code) calls ``ledger.complete(args)`` first; an error exit reports
    nothing, since the flags never got the chance to apply.
    """
    ledger = FlagLedger(args, parser=parser, subcommand=name)
    args = ledger.track(args)
    target = peek(args, 'path') or peek(args, 'target')
    walk_root, patterns = dispatch_scope(str(target) if target else '', peek(args, 'exclude'))
    try:
        with exclusion_scope(walk_root, patterns), ledger.dispatching(''):
            runner(args)
        ledger.complete = True
    finally:
        if ledger.complete:
            ledger.report()
