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
here, or never parsed it at all. The shared JSON writer includes these facts in
``meta.warnings``; text dispatches print their notes on stderr. Process-global flags
(``cli.global_flags.PROCESS_GLOBAL_FLAGS``) are never reported.
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
from ...utils.results import outcome_of
from ...utils.query_parser import QueryKeyLog, collect_query_keys, query_key

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
                 subcommand: Optional[str] = None, view: Optional[str] = None):
        """``parser`` and ``subcommand`` for a ``reveal <subcommand>`` dispatch: flags are
        judged against that parser's defaults, and the note names the subcommand. ``view``
        names a bare-path view (``the file view``) for the same note without a URI scheme."""
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
        self.view = view
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
        self.scheme = subcommand or ''
        self.json_primary = getattr(args, 'format', 'text') == 'json'
        self._query_log: Optional[QueryKeyLog] = None
        self.query_warnings: List[dict] = []

    def track(self, args: Namespace) -> TrackedArgs:
        tracked = TrackedArgs(**vars(args))
        vars(tracked)[_LEDGER_ATTR] = self
        return tracked

    def delegate(self, dest: str, key: str) -> None:
        """``dest``'s value was injected into the query as ``key``."""
        self.delegated[dest] = key

    @contextmanager
    def dispatching(self, resource: str, scheme: str = '') -> Iterator[None]:
        """Run the adapter for ``resource`` (the final one, after injection)."""
        query = resource.partition('?')[2]
        self.query_keys = [query_key(p) for p in query.split('&') if query_key(p)]
        self.scheme = scheme or self.scheme
        typed = _query_values(query)
        for dest, value in self.set_flags.items():
            if dest not in self.delegated and str(value) in typed.get(dest, []):
                self.delegated[dest] = dest
        with collect_query_keys(warnings_to_stderr=not self.json_primary, unused_warnings=self._answer_warnings) as log:
            # Live sets let the JSON writer see facts after analysis/postprocessing,
            # before dispatch unwinds. The final snapshot still supports text reports.
            self.seen_keys, self.used_keys = log.seen, log.used
            self.query_warnings = log.warnings
            self._query_log = log
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
        if self._query_log is not None and self._query_log.structured_emitted:
            return
        out = stream if stream is not None else sys.stderr
        # JSON paths that bypass the shared writer must still disclose the
        # deferred parser warnings. Text parsers already printed theirs.
        if self.json_primary:
            for warning in self.query_warnings:
                print(warning['message'], file=out)
        for warning in self._notes(scheme):
            print(warning['message'], file=out)

    def _answer_warnings(self, result: dict) -> List[dict]:
        # Error exits never reported unused input: the operation did not get
        # a chance to apply it. Preserve that policy at this accounting owner.
        return self.warnings() if outcome_of(result) != 'failed' else []

    def warnings(self, scheme: str = '') -> List[dict]:
        """Structured unused-input facts, from the same accounting as the text report."""
        # The text recovery sentence names the CLI spelling; JSON facts must
        # answer alike for a typed command and its equivalent URI query.
        return [{**note, 'message': f"Input {', '.join(note['fields'])} has no effect for this operation."}
                for note in self._notes(scheme)]

    def _notes(self, scheme: str = '') -> List[dict]:
        from ..defaults import _option_names, option_names_of
        names = _option_names() if self.parser is None else option_names_of(self.parser)
        scheme = scheme or self.scheme
        return self._flag_warnings(names, scheme) + self._key_warnings(scheme)

    def _flag_warnings(self, names: Dict[str, str], scheme: str) -> List[dict]:
        flags = self.unused_flags()
        if exclusions_consulted():
            flags = [flag for flag in flags if flag != 'exclude']
        if not flags:
            return []
        fields = [names.get(dest, f'--{dest}') for dest in flags]
        spelled = ', '.join(fields)
        if self.subcommand:
            message = (f"Note: {spelled} has no effect on 'reveal {self.subcommand}' -- this "
                       f"subcommand does not use it.")
            return [_input_warning('unused_flag', fields, message)]
        if self.view:
            message = f"Note: {spelled} has no effect on {self.view} -- this view does not use it."
            return [_input_warning('unused_flag', fields, message)]
        parsed = [dest for dest in flags if self.delegated.get(dest) in self.seen_keys]
        warnings = self._unsupported_flags([dest for dest in flags if dest not in parsed], names, scheme)
        if parsed:
            fields = [names.get(dest, f'--{dest}') for dest in parsed]
            warnings.append(_input_warning('unused_flag', fields,
                f"Note: {', '.join(fields)} has no effect on this {scheme}:// query -- {_NOT_HERE}"))
        return warnings

    @staticmethod
    def _unsupported_flags(flags: List[str], names: Dict[str, str], scheme: str) -> List[dict]:
        if not flags:
            return []
        fields = [names.get(dest, f'--{dest}') for dest in flags]
        bare = [names.get(dest, f'--{dest}') for dest in flags if dest in _BARE_PATH_FLAGS]
        hint = f" Use a bare path scan (reveal <path> {' '.join(bare)}) instead." if bare else ''
        return [_input_warning('unused_flag', fields,
            f"Note: {', '.join(fields)} has no effect on {scheme}:// queries -- not supported "
            f"by this adapter.{hint}")]

    def _key_warnings(self, scheme: str) -> List[dict]:
        keys = self.unused_query_keys()
        unparsed = [key for key in keys if key not in self.seen_keys]
        unread = [key for key in keys if key in self.seen_keys]
        warnings = []
        for fields, message in (
            (unparsed, f"on {scheme}:// -- this adapter does not read it."),
            (unread, f"on this {scheme}:// query -- {_NOT_HERE}"),
        ):
            if fields:
                spelled = ', '.join(f"'{key}'" for key in fields)
                warnings.append(_input_warning('unused_query_param', fields,
                    f"Note: query param {spelled} has no effect {message}"))
        return warnings


def _input_warning(kind: str, fields: List[str], message: str) -> dict:
    return {'type': kind, 'code': kind, 'fields': fields, 'message': message}


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
