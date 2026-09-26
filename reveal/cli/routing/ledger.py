"""Flag ledger (BACK-1514): a flag or query key the user sets is used, or the user is told.

Flags reach a URI adapter through several mechanisms: FLAG_SPECS query fragments,
get_structure parameter names, check() keyword arguments, the --exclude walk scope,
--head/--tail/--range and --max-items post-processing, the adapter's own
post_process(result, args), and the renderer. Each mechanism used to decide on its own
whether to mention a flag it could not apply, and most did not. So a flag argparse accepted
could vanish on one adapter and work on the next (45+ fixes in 0.122-0.129). The ledger makes
that decision once per dispatch, in handle_uri.

A flag the user set (its value differs from the parser default) counts as used when:

- code reads it from ``args`` during the dispatch. ``args`` is a ``TrackedArgs``, so reads by
  the adapter, the renderer and routing are recorded without any declaration;
- routing code that only *inspects* a flag, and may then not apply it, reads it with ``peek``
  and calls ``mark`` once it has applied the flag or printed a note about it; or
- its value was carried into the URI query (``reveal f.py --type function`` routes as
  ``ast://f.py?type=function``). The query key is then judged instead.

A query key counts as used when an adapter's query parser saw it
(``utils.query_parser.note_query_parsed``). Whatever is left when the dispatch finishes gets
one note. Process-global flags (``cli.global_flags.PROCESS_GLOBAL_FLAGS``) are never reported.

Not covered yet: the ``cli/commands/*`` subcommands, which build adapters directly.
"""

from __future__ import annotations

import sys
from argparse import Namespace
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Set, TextIO
from urllib.parse import parse_qs

from ...utils.query_parser import collect_parsed_query_keys, query_key

_LEDGER_ATTR = '_reveal_flag_ledger'
_NOT_FLAGS = frozenset({'path', 'element'})
# Flags that work on a bare path scan but have no URI meaning: the note says where they work.
_BARE_PATH_FLAGS = ('depth', 'ext', 'type', 'fast')


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

    def __init__(self, args: Namespace):
        from ..defaults import _parser_defaults
        from ..global_flags import PROCESS_GLOBAL_FLAGS
        from ..parser import _format_default

        # format's default comes from REVEAL_FORMAT per call; _parser_defaults is cached.
        defaults = {**_parser_defaults(), 'format': _format_default()}
        self.set_flags: Dict[str, Any] = {
            dest: getattr(args, dest) for dest, default in defaults.items()
            if dest not in _NOT_FLAGS and dest not in PROCESS_GLOBAL_FLAGS
            and hasattr(args, dest) and getattr(args, dest) != default}
        self.used: Set[str] = set()
        self.delegated: Dict[str, str] = {}  # dest -> the query key that carries its value
        self.query_keys: List[str] = []
        self.parsed_keys: Set[str] = set()
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
        typed = parse_qs(query, keep_blank_values=True)
        for dest, value in self.set_flags.items():
            if dest not in self.delegated and str(value) in typed.get(dest, []):
                self.delegated[dest] = dest
        with collect_parsed_query_keys() as parsed:
            try:
                yield
            finally:
                self.parsed_keys = set(parsed)

    def unused_flags(self) -> List[str]:
        return [dest for dest in self.set_flags
                if dest not in self.used
                and (dest not in self.delegated or self.delegated[dest] not in self.parsed_keys)]

    def unused_query_keys(self) -> List[str]:
        carried = set(self.delegated.values())
        seen: List[str] = []
        for key in self.query_keys:
            if key not in self.parsed_keys and key not in carried and key not in seen:
                seen.append(key)
        return seen

    def report(self, scheme: str, stream: Optional[TextIO] = None) -> None:
        from ..defaults import _option_names

        out = stream if stream is not None else sys.stderr
        names = _option_names()
        flags = self.unused_flags()
        if flags:
            spelled = ', '.join(names.get(dest, f'--{dest}') for dest in flags)
            bare = [names.get(d, f'--{d}') for d in flags if d in _BARE_PATH_FLAGS]
            hint = (f" Use a bare path scan (reveal <path> {' '.join(bare)}) instead."
                    if bare else '')
            print(f"Note: {spelled} has no effect on {scheme}:// queries -- not supported "
                  f"by this adapter.{hint}", file=out)
        keys = self.unused_query_keys()
        if keys:
            quoted = ', '.join(f"'{key}'" for key in keys)
            print(f"Note: query param {quoted} has no effect on {scheme}:// -- this adapter "
                  f"does not read it.", file=out)


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
