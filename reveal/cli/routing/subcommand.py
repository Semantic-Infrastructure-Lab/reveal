"""Subcommand dispatch (BACK-1539): what handle_uri gives a URI, given once to ``reveal <name>``.

The ``cli/commands/*`` runners build their adapters directly, so the URI plumbing never
reached them: ``REVEAL_IGNORE`` pruned ``surface://`` but not ``reveal surface``, and a flag a
subcommand's parser accepted but its runner never read (``reveal surface --verbose``) was
dropped without a word, while the same flag on the URI form got a ledger note. Every
subcommand already enters through one call site (``main._prepare``, from the one Invocation,
BACK-1058); this is the seam behind it, so a cross-cutting concern lands here once instead of
in 15 runners.

A runner's result leaves through ``emit_subcommand_result``, the subcommand twin of the URI
router's ``_emit_result``: one place a result's outcome is acted on, so ``reveal overview``
says what ``overview://`` says about a failed or cut answer (BACK-1059, BACK-1544).

What it does not unify, deliberately: the runners keep their own output contracts (a JSON
``type`` named for the subcommand, ``deps``/``hotspots`` exiting 1 on findings as a CI gate --
EXIT_CODE_CONTRACT). Both forms share one parse-and-dispatch path (``main._dispatch_and_run``),
not one handler.
"""

from __future__ import annotations

import json
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Any, Callable, Dict, Union

from ...display.formatting import print_truncations
from ...utils.exclusions import dispatch_scope, exclusion_scope
from ...utils.json_utils import attach_provenance
from ...utils.path_utils import to_posix
from ...utils.results import add_cli_contract_fields, outcome_of
from .ledger import FlagLedger, peek

# The adapter's own identity keys: a subcommand re-states them with its own name and the
# resolved path it was given. contract_version and meta stay (BACK-1178).
_ADAPTER_IDENTITY_KEYS = ('type', 'source', 'source_type')


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


def emit_subcommand_result(result: Dict[str, Any], args: Namespace, *, name: str,
                           source: Union[str, Path], render: Callable[[Dict[str, Any]], None],
                           source_type: str = 'directory') -> None:
    """Print a subcommand's result and act on its outcome, as ``_emit_result`` does for a URI.

    Each runner printed its own JSON envelope or rendered its own text, and none asked
    whether the answer was failed or cut. Once ``render_meta_warnings`` left cut lists to
    the router, ``reveal overview`` stopped saying its complex-function list was cut, and
    ``reveal hotspots`` never had said so, while their URI forms did (BACK-1544).

    - JSON: the result under the subcommand's own envelope (``type`` = *name*, ``source``
      = *source* as the user named it, POSIX -- BACK-1366), keeping the adapter's
      ``contract_version`` and ``meta``, where a cut is already recorded.
    - Other formats: ``render(result)``, then each cut list once (``print_truncations``).
    - A failed result (top-level ``error``) is reported on stderr and exits 1, after the
      output, as the URI form does.

    It returns otherwise, so a runner still applies its own findings exit
    (EXIT_CODE_CONTRACT).
    """
    outcome = outcome_of(result)
    if outcome == 'failed':
        print(f"Error (reveal {name}): {result['error']}", file=sys.stderr)
    if args.format == 'json':
        report = {k: v for k, v in result.items() if k not in _ADAPTER_IDENTITY_KEYS}
        print(json.dumps(
            attach_provenance(add_cli_contract_fields(
                report, result_type=name, source=to_posix(source), source_type=source_type,
            )),
            indent=2, default=str,
        ))
    else:
        render(result)
        if outcome == 'truncated':
            print_truncations(result, args.format)
    if outcome == 'failed':
        sys.exit(1)
