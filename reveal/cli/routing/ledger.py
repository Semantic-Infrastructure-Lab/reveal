"""Flag ledger (BACK-1514): a flag or query key the user sets is used, or the user is told.

Flags reach a URI adapter through several mechanisms: FLAG_SPECS query fragments,
get_structure parameter names, check() keyword arguments, the --exclude walk scope,
--head/--tail/--range and --max-items post-processing, the adapter's own
post_process(result, args), and the renderer. Each mechanism used to decide on its own
whether to mention a flag it could not apply, and most did not. So a flag argparse accepted
could vanish on one adapter and work on the next (45+ fixes in 0.122-0.129). The ledger makes
that decision once per dispatch: in handle_uri for URI, bare-path and MCP invocations, and in
``subcommand.dispatch_subcommand`` for the ``reveal <name>`` subcommands (BACK-1539), whose
defaults come from their own parser.

A flag the user set (its value differs from the parser default) counts as used when:

- code reads it from ``args`` during the dispatch. ``args`` is a ``TrackedArgs``, so reads by
  the adapter, the renderer and routing are recorded without any declaration;
- routing code that only *inspects* a flag, and may then not apply it, reads it with ``peek``
  and calls ``mark`` once it has applied the flag or printed a note about it; or
- its value was carried into the URI query (``reveal f.py --type function`` routes as
  ``ast://f.py?type=function``). The query key is then judged instead; or
- for ``--exclude`` published as the walk scope, a walk actually checked a path against it
  (``utils.exclusions.exclusions_consulted``). An adapter that never walks applied nothing.

A query key counts as used when the adapter read it (``utils.query_parser``): a filter parser
uses every key it parses, while ``parse_query_params`` and ``parse_result_control`` return
objects that record a key only when a view reads it (BACK-1537 -- git://FILE parses ?limit=
for its history view and the file view never reads it). Whatever is left when the dispatch
finishes gets one note, which says whether the adapter parsed the key and then left it unused
here, or never parsed it at all. Process-global flags (``cli.global_flags.PROCESS_GLOBAL_FLAGS``) are never reported.
A dispatch that ends in ``sys.exit`` after producing its result (check mode, a subcommand's
findings exit) calls ``complete`` first; an error exit reports nothing.
"""

from __future__ import annotations

import sys
from argparse import ArgumentParser, Namespace
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Set, TextIO
from urllib.parse import unquote_plus

from ...utils.exclusions import exclusions_consulted
from ...utils.query_parser import collect_query_keys, query_key

_LEDGER_ATTR = '_reveal_flag_ledger'
_NOT_FLAGS = frozenset({'path', 'element'})
# Flags that work on a bare path scan but have no URI meaning: the note says where they work.
_BARE_PATH_FLAGS = ('depth', 'ext', 'type', 'fast')
# The adapter parsed the key and no code on this query's path read it (git://FILE --limit).
_NOT_HERE = 'the adapter accepts it, but not for this view.'



class TrackedArgs(Namespace):
    """``args`` for one dispatch: a copy whose attribute reads are recorded in its ledger."""

    def __getattribute__(self, name: str) -> Any:
        if not name.startswith('_'):
            ledger = object.__getattribute__(self, '__dict__').get(_LEDGER_ATTR)
            if ledger is not None:
                ledger.used.add(name)
        return object.__getattribute__(self, name)


class FlagLedger:
    """Flags and query keys the user set for one dispatch, and which of them were used."""

    def __init__(self, args: Namespace, parser: Optional[ArgumentParser] = None,
                 subcommand: Optional[str] = None):
        """``parser`` and ``subcommand`` for a ``reveal <subcommand>`` dispatch: flags are
        judged against that parser's defaults, and the note names the subcommand."""
        from ..defaults import _parser_defaults, option_defaults_of
        from ..global_flags import PROCESS_GLOBAL_FLAGS
        from ..parser import _format_default

        if parser is None:
            # format's default comes from REVEAL_FORMAT per call; _parser_defaults is cached.
            defaults = {**_parser_defaults(), 'format': _format_default()}
        else:  # built for this call, so its format default is already current
            defaults = option_defaults_of(parser)
        self.parser = parser
        self.subcommand = subcommand
        self.set_flags: Dict[str, Any] = {
            dest: getattr(args, dest) for dest, default in defaults.items()
            if dest not in _NOT_FLAGS and dest not in PROCESS_GLOBAL_FLAGS
            and hasattr(args, dest) and getattr(args, dest) != default}
        self.used: Set[str] = set()
        self.delegated: Dict[str, str] = {}  # dest -> the query key that carries its value
        self.query_keys: List[str] = []
        self.seen_keys: Set[str] = set()  # handed to a query parser
        self.used_keys: Set[str] = set()  # read by the adapter
        self.complete = False

    def track(self, args: Namespace) -> TrackedArgs:
        tracked = TrackedArgs(**vars(args))
        vars(tracked)[_LEDGER_ATTR] = self
        return tracked

    def delegate(self, dest: str, key: str) -> None:
        """``dest``'s value was injected into the query as ``key``."""
        self.delegated[dest] = key

    @contextmanager
    def dispatching(self, resource: str) -> Iterator[None]:
        """Run the adapter for ``resource`` (the final one, after injection)."""
        query = resource.partition('?')[2]
        self.query_keys = [query_key(p) for p in query.split('&') if query_key(p)]
        typed = _query_values(query)
        for dest, value in self.set_flags.items():
            if dest not in self.delegated and str(value) in typed.get(dest, []):
                self.delegated[dest] = dest
        with collect_query_keys() as log:
            try:
                yield
            finally:
                self.seen_keys, self.used_keys = set(log.seen), set(log.used)
                if exclusions_consulted():  # a walk applied the --exclude scope
                    self.used.add('exclude')

    def unused_flags(self) -> List[str]:
        return [dest for dest in self.set_flags
                if dest not in self.used
                and (dest not in self.delegated or self.delegated[dest] not in self.used_keys)]

    def unused_query_keys(self) -> List[str]:
        carried = set(self.delegated.values())
        seen: List[str] = []
        for key in self.query_keys:
            if key not in self.used_keys and key not in carried and key not in seen:
                seen.append(key)
        return seen

    def report(self, scheme: str = '', stream: Optional[TextIO] = None) -> None:
        from ..defaults import _option_names, option_names_of

        out = stream if stream is not None else sys.stderr
        names = _option_names() if self.parser is None else option_names_of(self.parser)
        flags = self.unused_flags()
        spelled = ', '.join(names.get(dest, f'--{dest}') for dest in flags)
        if flags and self.subcommand:
            print(f"Note: {spelled} has no effect on 'reveal {self.subcommand}' -- this "
                  f"subcommand does not use it.", file=out)
        elif flags:
            parsed = [d for d in flags if self.delegated.get(d) in self.seen_keys]
            self._report_flags([d for d in flags if d not in parsed], names, scheme, out)
            if parsed:
                spelled = ', '.join(names.get(dest, f'--{dest}') for dest in parsed)
                print(f"Note: {spelled} has no effect on this {scheme}:// query -- {_NOT_HERE}",
                      file=out)
        self._report_keys(scheme, out)

    @staticmethod
    def _report_flags(flags: List[str], names: Dict[str, str], scheme: str, out: TextIO) -> None:
        """Flags no parser saw: the adapter does not support them at all."""
        if not flags:
            return
        spelled = ', '.join(names.get(dest, f'--{dest}') for dest in flags)
        bare = [names.get(d, f'--{d}') for d in flags if d in _BARE_PATH_FLAGS]
        hint = f" Use a bare path scan (reveal <path> {' '.join(bare)}) instead." if bare else ''
        print(f"Note: {spelled} has no effect on {scheme}:// queries -- not supported "
              f"by this adapter.{hint}", file=out)

    def _report_keys(self, scheme: str, out: TextIO) -> None:
        keys = self.unused_query_keys()
        unparsed = ', '.join(f"'{key}'" for key in keys if key not in self.seen_keys)
        unread = ', '.join(f"'{key}'" for key in keys if key in self.seen_keys)
        if unparsed:
            print(f"Note: query param {unparsed} has no effect on {scheme}:// -- this adapter "
                  f"does not read it.", file=out)
        if unread:
            print(f"Note: query param {unread} has no effect on this {scheme}:// query -- "
                  f"{_NOT_HERE}", file=out)


def _query_values(query: str) -> Dict[str, List[str]]:
    """Each query key's values, read the way the query parser keys them (``query_key``).

    ``parse_qs`` split ``name~=load`` into key ``name~``, so ``reveal f.py --name load``
    (routed as ``ast://f.py?name~=load``) never matched its flag and drew a false
    "no effect" note while the filter applied (BACK-1604).
    """
    values: Dict[str, List[str]] = {}
    for part in query.split('&'):
        key = query_key(part)
        if key:
            rest = part.strip().lstrip('!')[len(key):].lstrip('=<>!~')
            values.setdefault(key, []).append(unquote_plus(rest))
    return values


def ledger_of(args: Any) -> Optional[FlagLedger]:
    if isinstance(args, TrackedArgs):
        return vars(args).get(_LEDGER_ATTR)
    return None


def peek(args: Any, dest: str, default: Any = None) -> Any:
    """Read a flag without counting it as used: for code that inspects a flag and may then
    not apply it. Call ``mark`` once it has applied the flag or printed a note about it."""
    if isinstance(args, TrackedArgs):
        return vars(args).get(dest, default)
    return getattr(args, dest, default)


def mark(args: Any, *dests: str) -> None:
    """Count ``dests`` as used: applied, or already the subject of a note."""
    ledger = ledger_of(args)
    if ledger is not None:
        ledger.used.update(dests)


def delegate(args: Any, dest: str, key: str) -> None:
    ledger = ledger_of(args)
    if ledger is not None:
        ledger.delegate(dest, key)


def complete(args: Any) -> None:
    """The dispatch produced its result (check mode exits through sys.exit after this)."""
    ledger = ledger_of(args)
    if ledger is not None:
        ledger.complete = True
