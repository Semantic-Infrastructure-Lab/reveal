"""Query string parsing: query params, filter expressions, QueryFilter dataclass."""

import re as _re  # noqa: F401 — imported for use by query_eval, kept here for consumers
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from urllib.parse import unquote
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Iterator, List, Mapping, Optional, Set, TextIO, Tuple, Union

# Characters that only appear in a *filter* key (e.g. `complexity>10`, `msg~=x`),
# never in a fixed param key. Used to distinguish the two in adapters that parse
# the same query string as both params and filters (stats://, git://).
_FILTER_OP_CHARS = frozenset('<>~!')

# BACK-1514 flag ledger: while a dispatch collects, a QueryKeyLog records which query keys an
# adapter's parsers were handed (seen) and which it used. A filter parser (parse_query_filters)
# uses every key it parses. parse_query_params and parse_result_control see their keys when
# they parse them and use one only when the adapter reads it (BACK-1537): git://FILE parses
# ?limit= for the views that honor it, and the file view never reads it. A key never used is
# what the ledger reports -- sqlite:// parses no query at all, so its keys are not even seen.
_KEY_END = _re.compile(r'[=<>!~.?]')


@dataclass
class QueryKeyLog:
    seen: Set[str]  # handed to some parser
    used: Set[str]  # read by the adapter (for a filter parser: parsed)
    warnings: List[dict] = field(default_factory=list)
    warnings_to_stderr: bool = True
    unused_warnings: Optional[Callable[[dict], List[dict]]] = None
    structured_emitted: bool = False


_KEY_LOG: ContextVar[Optional[QueryKeyLog]] = ContextVar('reveal_query_key_log', default=None)


def query_key(part: str) -> str:
    """The key of one ``&``-separated query part: ``limit=2`` -> ``limit``,
    ``complexity>10`` -> ``complexity``, ``!draft`` -> ``draft``."""
    return _KEY_END.split(part.strip().lstrip('!'), 1)[0].strip()


@contextmanager
def collect_query_keys(*, warnings_to_stderr: bool = True,
                       unused_warnings: Optional[Callable[[dict], List[dict]]] = None) -> Iterator[QueryKeyLog]:
    """Log the keys query parsers see and the adapter uses until the block exits."""
    log = QueryKeyLog(seen=set(), used=set(), warnings_to_stderr=warnings_to_stderr,
                      unused_warnings=unused_warnings)
    token = _KEY_LOG.set(log)
    try:
        yield log
    finally:
        _KEY_LOG.reset(token)


def attach_input_warnings(result):
    """Attach current dispatch diagnostics before the shared JSON writer emits the answer.

    The ledger supplies unused-input facts; parsers supply unknown-input facts.
    Keeping this in the query layer lets the writer use those producers without
    importing routing, and reuses the existing nested/request-local query scope.
    """
    log = _KEY_LOG.get()
    if log is None or not isinstance(result, dict):
        return result
    entries = list(log.warnings)
    # The dispatch owner decides whether this answer completed far enough
    # to judge unused input; parsing diagnostics remain independent of that policy.
    if log.unused_warnings is not None:
        entries.extend(log.unused_warnings(result))
    if not entries:
        return result
    meta = dict(result['meta']) if isinstance(result.get('meta'), dict) else {}
    warnings = list(meta['warnings']) if isinstance(meta.get('warnings'), list) else []
    for entry in entries:
        if entry not in warnings:
            warnings.append(entry)
    meta['warnings'] = warnings
    if not log.warnings_to_stderr:
        log.structured_emitted = True
    return {**result, 'meta': meta}


def note_query_parsed(query: str) -> None:
    """Record every key of ``query`` as seen and used. Call from a filter parser: its filters
    are the adapter's reads, so parsing a key is using it."""
    log = _KEY_LOG.get()
    if log is not None and query:
        keys = {query_key(part) for part in query.split('&') if part.strip()}
        log.seen.update(keys)
        log.used.update(keys)


def query_key_recorder(*seen: str) -> Optional[Set[str]]:
    """Record ``seen`` keys as parsed and return the used-keys set of the dispatch in progress
    (None outside one). A parser whose result is read later binds that set at parse time and
    adds each key the adapter reads."""
    log = _KEY_LOG.get()
    if log is None:
        return None
    log.seen.update(query_key(key) for key in seen)
    return log.used


class QueryParams(Dict[str, Any]):
    """``parse_query_params``' result: a dict that records the keys the adapter reads (BACK-1537).

    ``[]``, ``get``, ``in``, ``pop`` and ``setdefault`` record their key. Anything that walks the
    whole dict (iteration, ``keys``/``items``/``values``, ``**params``, JSON) records every key,
    so a consumer this class cannot see into never produces a false note. Code that only routes
    or validates keys walks them with ``peek_items`` and records what it applied with ``mark``.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._reads = query_key_recorder()
        self._aliases: Dict[str, Tuple[str, ...]] = {}
        self._selectors: Dict[str, str] = {}
        self._supplied_aliases: set[str] = set()
        self._folded: Tuple[str, ...] = ()  # bare field keys the binder folded into where
        self._source_query: Optional[str] = None
        self._overrides: set[str] = set()
        # The declared controls the request gave a value (an omitted typed flag arrives as None, an API override of
        # None selects the default): what the applicability check judges (COMMAND_MODEL "Applicability", BACK-2656).
        self._given: set[str] = set()
        self._transport = "typed"
        self._normalized: Dict[str, Tuple[Any, Any, Any]] = {}

    def declaration(self, name: str) -> Optional['ParamSpec']:
        """The declaration *name* was bound through, or None (not bound by a declaration, or changed since)."""
        entry = self._normalized.get(name)
        return entry[0] if entry else None

    def set_normalized(self, spec: 'ParamSpec', value: Any) -> None:
        """Remember one conversion; detect mutation without converting twice."""
        self[spec.name] = value
        snapshot = deepcopy(value) if isinstance(value, (list, tuple, dict)) else value
        self._normalized[spec.name] = (spec, value, snapshot)

    def __setitem__(self, key: str, value: Any) -> None:
        self._normalized.pop(key, None)
        super().__setitem__(key, value)

    def __delitem__(self, key: str) -> None:
        self._normalized.pop(key, None)
        super().__delitem__(key)

    def update(self, *args: Any, **kwargs: Any) -> None:
        for key, value in dict(*args, **kwargs).items():
            self[key] = value

    def clear(self) -> None:
        self._normalized.clear()
        super().clear()

    def __or__(self, other: Any) -> Any:
        return super().__or__(other)

    def __ior__(self, other: Any) -> Any:
        self.update(other)
        return self

    def popitem(self):
        self._mark_all()
        key, value = super().popitem()
        self._normalized.pop(key, None)
        return key, value

    def mark(self, *keys: str) -> None:
        """Count ``keys`` as used: applied, or already named in a warning."""
        if self._reads is not None:
            self._reads.update(query_key(key) for key in keys)
            self._reads.update(alias for key in keys for alias in self._aliases.get(key, ()))

    def _mark_all(self) -> None:
        if self._reads is not None:
            self.mark(*dict.keys(self))

    def peek_items(self) -> Iterator[Tuple[str, Any]]:
        """Walk the items without counting them as used."""
        return iter(list(dict.items(self)))

    def __getitem__(self, key: str) -> Any:
        self.mark(key)
        return super().__getitem__(key)

    def get(self, key: str, default: Any = None) -> Any:
        self.mark(key)
        return super().get(key, default)

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str):
            self.mark(key)
        return super().__contains__(key)

    def pop(self, key: str, *default: Any) -> Any:
        self.mark(key)
        self._normalized.pop(key, None)
        return super().pop(key, *default)

    def setdefault(self, key: str, default: Any = None) -> Any:
        self.mark(key)
        return super().setdefault(key, default)

    def __iter__(self) -> Iterator[str]:
        self._mark_all()
        return super().__iter__()

    def keys(self):
        self._mark_all()
        return super().keys()

    def items(self):
        self._mark_all()
        return super().items()

    def values(self):
        self._mark_all()
        return super().values()

    def copy(self) -> Dict[str, Any]:
        self._mark_all()
        if self._normalized:
            copied = QueryParams(dict.items(self))
            copied._reads = self._reads
            copied._normalized = self._normalized.copy()
            return copied
        return dict(dict.items(self))


def peek_query_items(params: Mapping[str, Any]) -> Iterator[Tuple[str, Any]]:
    """Walk a parsed query without counting its keys as used (a plain dict works too)."""
    return params.peek_items() if isinstance(params, QueryParams) else iter(list(params.items()))


def mark_query_keys(params: Dict[str, Any], *keys: str) -> None:
    """Count ``keys`` of a parsed query as used (a no-op for a plain dict)."""
    if isinstance(params, QueryParams):
        params.mark(*keys)


def whole_number(value: Any) -> int:
    """An integer control's value: 3, '3' and 3.0 are accepted; 1.5 is not (int() would cut it to 1), nor a bool
    (int(True) is 1: ``matches=False`` meant 0, every snippet; BACK-2727)."""
    if isinstance(value, bool):
        raise ValueError(f'{value} is not a whole number')
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f'{value} is not a whole number')
    return int(value)


def line_range(value: Any) -> Tuple[int, Optional[int]]:
    """``--range START-END`` as (start, end), 1-indexed; ``START-`` is open-ended (end None). A parsed pair is
    returned unchanged, so a value read twice converts once."""
    if isinstance(value, tuple):
        return value
    try:
        start_text, end_text = str(value).split('-')
        start = int(start_text)
        end = int(end_text) if end_text else None  # '300-' -> open-ended
    except ValueError:
        raise ParamValueError(f"range must be START-END or START- (1-indexed, e.g. 10-20 or 300-), got {value!r}") \
            from None
    if start < 1 or (end is not None and end < 1):
        raise ParamValueError("Range must be 1-indexed (start from 1)")
    if end is not None and start > end:
        raise ParamValueError("Range start must be <= end")
    return start, end


def nonnegative_display_limit(value: Any, name: str = 'top') -> int:
    """The one parser for a display limit (``--top`` / ``?top=``); zero shows none.

    '3', 3 and '3.0' are accepted (``whole_number``'s rule); 1.5, 'abc' and -1 raise a
    ValueError that names the parameter, the rule and the offending value.
    """
    try:
        limit = whole_number(float(value) if isinstance(value, str) else value)
    except (TypeError, ValueError, OverflowError):
        limit = -1
    if limit < 0:
        raise ValueError(f"{name} must be a non-negative integer (got {str(value)!r})")
    return limit


class ParamValueError(ValueError):
    """A converter's rejection whose message already names the parameter and what to type.

    ``ParamSpec.validate`` keeps it as written instead of its generic
    "must be a valid <type>" wording (a bare ``?target`` is not "a valid string, got True").
    """


def nonempty_scalar(value: Any) -> str:
    """A name-valued parameter: a string with a non-blank character and no NUL, never coerced
    (``123`` and ``true`` stay strings)."""
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise ValueError('expected a nonempty string without NUL')
    return value


def clamped_whole(value: Any, low: int, high: int) -> int:
    """A signed whole integer (``4``, ``'+3'``, ``'-2'``) clamped to ``low..high``.
    Booleans, fractions (``'1.5'``, ``'2.0'``), exponents and other text raise ValueError."""
    if type(value) is int:
        return max(low, min(value, high))
    if isinstance(value, str) and _re.fullmatch(r'[+-]?[0-9]+', value.strip()):
        return max(low, min(int(value), high))
    raise ValueError('expected a signed whole integer')


def cli_display_limit(value: str) -> int:
    """argparse ``type=`` for ``--top``: the shared parser, with the flag's own name in the message."""
    import argparse
    try:
        return nonnegative_display_limit(value, name='--top')
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


@dataclass(frozen=True)
class CliBinding:
    """Typed argument binding, separate from legacy fixed query fragments."""
    flags: Tuple[str, ...]
    dest: Optional[str] = None
    nargs: Optional[Union[str, int]] = None
    required: bool = False
    action: Optional[str] = None
    metavar: Optional[str] = None
    const: Any = None
    # Flags whose bindings share this name are mutually exclusive: argparse refuses two of them, exit 2 (``--head``,
    # ``--tail`` and ``--range`` select one slice).
    exclusive: str = ''


@dataclass(frozen=True)
class ResourceSpec:
    """A positional resource is not a query parameter; transports keep their defaults."""
    name: str = 'path'
    cli_default: Optional[str] = '.'
    uri_default: Optional[str] = '.'
    required: bool = False
    uri_codec: str = 'raw'
    kind: Optional[str] = None
    walks: bool = True
    filesystem: bool = True

    def schema(self) -> Dict[str, Any]:
        result = {'name': self.name, 'required': self.required,
                  'cli_default': self.cli_default, 'uri_default': self.uri_default,
                  'uri_codec': self.uri_codec}
        if not self.walks:
            result['walks'] = False
        if not self.filesystem:
            result['filesystem'] = False
        if self.kind is not None:
            result['kind'] = self.kind
        return result


@dataclass(frozen=True)
class LegacySpelling:
    """A retired spelling of the control it is declared on (COMMAND_MODEL rule "Spellings", BACK-2654).

    Keyed by ``name`` alone, or by ``name`` and ``value`` for a retired value (AST ``show=calls``); ``first`` marks
    a bare first query word (JSON's ``?schema``). ``codec`` translates the legacy raw value into the canonical
    control's value (identity when omitted) and may reject it; ``flag`` is the old CLI flag, which the declared
    parser generates. Notes come only from RETIREMENTS: an entry without a row is note-free.
    """
    name: str
    value: Optional[str] = None
    codec: Optional[Callable[[Any], Any]] = None
    flag: Optional[str] = None
    first: bool = False
    owner: str = ''  # the canonical control's name, bound by its ParamSpec
    # The old flag took no value (``--no-churn``): it stands for this legacy value. None: the flag takes one.
    flag_value: Any = None

    def translate(self, raw: Any) -> Dict[str, Any]:
        """The canonical controls the legacy value stands for."""
        if self.first:
            return {self.owner: self.name}
        return {self.owner: raw if self.codec is None else self.codec(raw)}


# The shared control names (COMMAND_MODEL "Shared control names", BACK-2654 rule 7): one name per idea on every noun.
# A noun declares the ones it supports; a bare URI key spelling one is that control, never a field filter (rule 8).
SHARED_CONTROL_NAMES = ('limit', 'offset', 'sort', 'where', 'match', 'detail', 'kind', 'depth', 'tests', 'since',
                        'until', 'against', 'view')


# The zero policies under which a cap's 0 means every row (Caps row): 'no cap' for a row cap, 'all' for a ranking or
# display top, 'uncapped' for Claude's pages. Any other policy (an output budget's 'empty page') keeps 0 literal.
UNCAPPING_ZEROS = frozenset({'no cap', 'all', 'uncapped'})


@dataclass(frozen=True)
class ParamSpec:
    """One declared query parameter; read explicitly where its value is applied.

    The converter owns legacy parsing policy; bounds and zero semantics are
    explicit rather than guessed from a parameter's name.
    """
    name: str
    type: str
    description: str
    default: Any
    convert: Callable[[Any], Any]
    examples: Tuple[str, ...] = ()
    minimum: Optional[int] = None
    zero_policy: Optional[str] = None
    cli_flags: Tuple[Tuple[str, str], ...] = ()
    choices: Tuple[Any, ...] = ()
    role: Optional[str] = None
    cli: Optional[CliBinding] = None
    uri_codec: str = 'raw'
    required: bool = False
    # What a value names: 'file' (a path under the scan) or 'symbol' (a definition name). A parameter that
    # names a target exits 2 when it matches nothing (surface plan rule 9), never a clean zero.
    names: Optional[str] = None
    # Spelling variants only (``scan_limit`` for ``scan-limit``): note-free. A different word is a ``legacy`` entry.
    aliases: Tuple[str, ...] = ()
    legacy: Tuple[LegacySpelling, ...] = ()
    # Selections and filters repeat and combine (where, match); settings are scalar. The CLI appends exactly
    # when this is set (COMMAND_MODEL rule "Conflicting values").
    repeatable: bool = False
    # A where control's filterable fields (COMMAND_MODEL "Bare URI keys"): a bare ``FIELD OP VALUE`` on one of
    # them is that where filter, and the unknown-key check names them. ``open_fields`` describes a field set the
    # data defines (Markdown frontmatter keys, JSON row keys; BACK-2654 note #14): every bare key there is a field.
    fields: Tuple[str, ...] = ()
    open_fields: str = ''
    # A where control's fields whose spelling retired: each has a ``param:<noun>.<field>`` RETIREMENTS row, which a bound
    # where term naming the field notes on every transport (COMMAND_MODEL "Retirement notes"; AST calls/callee_of).
    retired_fields: Tuple[str, ...] = ()
    # On an answer selector (role='operation'): the control that caps the rows of the answer it selects, which the
    # global --all lifts (Metrics' legacy hotspots ranking reads top). None: the noun's own --all declaration.
    cap: Optional[str] = None
    # The answers that read this control (COMMAND_MODEL "Applicability", BACK-2656); empty: every answer. Each entry
    # names an answer by its predicted result type (``stats_file``) or by the selection that picks it: an operation's
    # name (``hotspots``), ``name=value`` (``view=hotspots``) or ``default`` (no operation given); parts joined with
    # ``+`` name one answer by all of them (``claude_messages+default``: that type when no operation picks it, so not
    # Claude's tail slice of the same type). A control given to an answer that matches no entry is an invalid request,
    # refused before analysis.
    answers: Tuple[str, ...] = ()
    # The values of other controls this one needs, each ``name=value`` (``churn=on``: Metrics ``since`` bounds the churn
    # walk) or a bare ``name`` (that control given), with ``|`` between alternatives (``filter|search``: Codex ``since``
    # bounds a filtered or searched catalog). Given beside a different value of that control, or with none of the
    # alternatives, the request conflicts with itself: an invalid request naming both, refused before analysis by the
    # same check as ``answers`` (Scott 2026-11-18, BACK-2656).
    requires: Tuple[str, ...] = ()
    # A legacy modifier only the CLI ever spelled (``--head`` after a URI or on the subcommand; COMMAND_MODEL "Flags
    # after a URI", BACK-2673): the declared parser generates its flag, its retirement note is keyed by that flag
    # (``flag:<noun>.<flag>``) and applicability judges it like any control, but it is no URI key, no ``api.query``
    # keyword and no schema query parameter, so neither transport gains a spelling it never had. ``'applied'``: a CLI
    # layer reads it from the namespace, converted (the router slices on ``--head``); ``'inert'``: it never shaped an
    # answer, so its note is its whole effect and it counts as read once given (``--check`` on Claude).
    flag_only: str = ''

    def __post_init__(self) -> None:
        if self.flag_only not in ('', 'applied', 'inert'):
            raise ValueError(f"{self.name}: flag_only is '', 'applied' or 'inert', not {self.flag_only!r}")
        if self.flag_only and (self.cli is None or self.aliases or self.legacy):
            raise ValueError(f'{self.name}: a flag-only modifier has its flags and no other spelling')
        from dataclasses import replace
        object.__setattr__(self, 'legacy', tuple(entry if entry.owner else replace(entry, owner=self.name)
                                                 for entry in self.legacy))

    @property
    def zero_uncaps(self) -> bool:
        """Whether a zero value of this cap means every row (COMMAND_MODEL Caps row: ``--limit 0`` is uncapped)."""
        return self.zero_policy in UNCAPPING_ZEROS

    def row_cap(self, value: Any) -> Optional[int]:
        """The row cap *value* asks for: None (every row) for an absent value or a zero this cap declares uncapped,
        else the value as an int. A default is the caller's: ``LIMIT.row_cap(query.get('limit', 50))``."""
        if value is None or (self.zero_uncaps and int(value) == 0):
            return None
        return int(value)

    @property
    def legacy_words(self) -> Tuple[str, ...]:
        """The legacy entries keyed by name alone: other words for this control."""
        return tuple(entry.name for entry in self.legacy if entry.value is None and not entry.first)

    @property
    def spellings(self) -> Tuple[str, ...]:
        """Every URI key that spells this control: its name, spelling variants and legacy words."""
        return (self.name, *self.aliases, *self.legacy_words)

    @property
    def first_selectors(self) -> Tuple[str, ...]:
        return tuple(entry.name for entry in self.legacy if entry.first)

    def legacy_entry(self, spelling: str) -> Optional[LegacySpelling]:
        """The name-keyed legacy entry for *spelling* (or its old flag), or None."""
        return next((entry for entry in self.legacy if entry.value is None and not entry.first
                     and spelling in (entry.name, entry.flag)), None)

    def canonical_value(self, spelling: str, value: Any) -> Any:
        """*value* as this control's own: a legacy spelling's translation, otherwise unchanged."""
        entry = self.legacy_entry(spelling)
        if entry is None or value is None:
            return value
        if self.repeatable and isinstance(value, list):  # each repeat of a repeatable control's legacy word
            return [entry.translate(item)[self.name] for item in value]
        return entry.translate(value)[self.name]

    @property
    def flags(self) -> Tuple[str, ...]:
        """The CLI flags the declared parser generates: the control's own, then its legacy entries' old flags."""
        own = self.cli.flags if self.cli is not None else ()
        return (*own, *(entry.flag for entry in self.legacy if entry.flag and entry.flag not in own))

    @property
    def cli_action(self) -> Optional[str]:
        """The argparse action: ``append`` exactly when the control repeats."""
        if self.repeatable:
            return 'append'
        return self.cli.action if self.cli is not None else None

    def read(self, params: Dict[str, Any]) -> Any:
        raw = params.get(self.name)
        if isinstance(params, QueryParams):
            normalized = params._normalized.get(self.name)
            if normalized is not None and normalized[0] is self and normalized[1] is raw:
                if isinstance(raw, (list, tuple, dict)) and raw != normalized[2]:
                    raise ValueError(f'Normalized {self.name} changed; rebind parameters before use')
                return raw
        return self.validate(raw)

    def validate(self, raw: Any) -> Any:
        """Convert/check without claiming that the analysis applied the parameter."""
        if raw is None:
            if self.required:
                raise ValueError(f'{self.name} is required')
            value = self.default
        else:
            try:
                value = self.convert(raw)
            except (ParamValueError, UnicodeDecodeError):
                raise
            except (TypeError, ValueError):
                what = 'a whole number' if self.type == 'integer' else f'a valid {self.type}'
                raise ValueError(f'{self.name} must be {what}, got {raw!r}') from None
        if self.minimum is not None and value is not None and value < self.minimum:
            raise ValueError(f'{self.name} must be >= {self.minimum}')
        if self.choices and value is not None and value not in self.choices:  # an absent optional choice
            raise ValueError(f'{self.name} must be one of {self.choices!r}, got {value!r}')
        return value

    def schema(self) -> Dict[str, Any]:
        result = {'type': self.type, 'description': self.description,
                  'examples': list(self.examples), 'default': self.default}
        if self.aliases or self.legacy_words:
            result['aliases'] = list(self.aliases) + list(self.legacy_words)
        if self.first_selectors:
            result['legacy_first_selectors'] = list(self.first_selectors)
        if self.minimum is not None:
            result['minimum'] = self.minimum
        if self.zero_policy is not None:
            result['zero_policy'] = self.zero_policy
        if self.choices:
            result['choices'] = list(self.choices)
        if self.role is not None:
            result['role'] = self.role
        if self.names is not None:
            result['names'] = self.names
        if self.answers:
            result['answers'] = list(self.answers)
        if self.requires:
            result['requires'] = list(self.requires)
        if self.cli is not None:
            result['cli'] = {'flags': list(self.flags), 'dest': self.cli.dest or self.name,
                             'nargs': self.cli.nargs, 'required': self.cli.required,
                             'action': self.cli_action, 'metavar': self.cli.metavar}
            result['required'] = self.required
            result['uri_codec'] = self.uri_codec
        elif self.uri_codec != 'raw' or self.required:
            result['required'] = self.required
            result['uri_codec'] = self.uri_codec
        return result


_SLICE_MODIFIERS = {'head': ('integer', 'Legacy: the first N rows', whole_number, 'N'),
                    'tail': ('integer', 'Legacy: the last N rows', whole_number, 'N'),
                    'range': ('string', 'Legacy: rows START-END, 1-indexed (START- is open-ended)', line_range, 'START-END')}


def legacy_slices(**answers: Tuple[str, ...]) -> Tuple[ParamSpec, ...]:
    """The main parser's ``--head``/``--tail``/``--range`` as flag-only legacy modifiers of a noun whose rows they slice
    (Scott 2026-11-19, BACK-2706/BACK-2708; BACK-2673): one keyword per flag the noun keeps, its value the answers that
    read it (``()``: every answer). The router slices on the namespace (``uri._apply_head_tail_range``) or the adapter
    does; each flag's note is its ``flag:<noun>.<flag>`` RETIREMENTS row; two of them exit 2."""
    unknown = set(answers) - set(_SLICE_MODIFIERS)
    if unknown:
        raise ValueError(f'no legacy slice modifier {sorted(unknown)}')
    return tuple(ParamSpec(name, kind, description, None, convert, minimum=0 if kind == 'integer' else None,
                           flag_only='applied', answers=answers[name],
                           cli=CliBinding((f'--{name}',), metavar=metavar, exclusive='slice'))
                 for name, (kind, description, convert, metavar) in _SLICE_MODIFIERS.items() if name in answers)


def legacy_check() -> ParamSpec:
    """The main parser's ``--check``/``--lint`` on a noun whose answers it never changed (Scott 2026-11-19, BACK-2708
    ruling 2; BACK-2673): an inert flag-only modifier, so its ``flag:<noun>.--check`` note is its whole effect."""
    return ParamSpec('check', 'boolean', 'Legacy: no effect on this noun\'s answers (reveal check <path> checks files)',
                     False, bool, flag_only='inert', cli=CliBinding(('--check', '--lint'), action='store_true'))


def param_schema(specs: Iterable[ParamSpec]) -> Dict[str, Any]:
    """The query parameters: a flag-only modifier is none (``ParamSpec.flag_only``)."""
    return {spec.name: spec.schema() for spec in specs if not spec.flag_only}


def expression_list(value: Any) -> List[str]:
    """A where value: one expression or a list of nonempty ones, ANDed by the owning noun's parser."""
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, (list, tuple)) or any(not isinstance(v, str) or not v.strip() for v in values):
        raise ValueError('where requires one or more nonempty expressions')
    return list(values)


def where_param(description: str, examples: Tuple[str, ...] = (),
                legacy: Tuple['LegacySpelling', ...] = (), *,
                convert: Optional[Callable[[Any], Any]] = None, default: Any = (),
                fields: Tuple[str, ...] = (), open_fields: str = '', retired_fields: Tuple[str, ...] = ()) -> ParamSpec:
    """The one declaration of a noun's repeatable where (D18; AST, Metrics and Claude, BACK-2621/2654).

    Its role makes the binder fold bare URI operator keys (``?lines>50``) into the same list as
    explicit ``where=`` values and ``--where`` flags; the noun's own filter parser evaluates them.
    *convert* is a noun's own term validation (Claude's name predicates); *default* None means an
    omitted where is absent rather than an empty list. *fields* are its filterable fields, or *open_fields*
    describes a field set the data defines. *retired_fields* are fields whose spelling has a ``param:`` RETIREMENTS row of
    the noun: a term on one notes that row (the declared route's ``note_retired_where_fields``).
    """
    return ParamSpec('where', 'array', description, [] if default == () else default, convert or expression_list,
                     examples, role='filter-expression', repeatable=True, legacy=legacy, cli=CliBinding(('--where',)),
                     fields=fields, open_fields=open_fields, retired_fields=retired_fields)


def _exclude_patterns(value: Any) -> str:
    """Exclusion patterns: one comma-separated value, or every repeat of it (exclude repeats and combines)."""
    values = value if isinstance(value, (list, tuple)) else [value]
    for item in values:
        if isinstance(item, bool) or not isinstance(item, str) or not item.strip():
            raise ValueError('exclude requires a value')
    return ','.join(values)


def exclude_param() -> ParamSpec:
    """The one declaration of a walking noun's ``exclude`` (``--exclude`` fills it; split_exclude_param reads it)."""
    return ParamSpec('exclude', 'string', 'Exclusion patterns, comma-separated (.gitignore syntax); repeat to add more; '
                     '--exclude fills it', None, _exclude_patterns, role='scope', repeatable=True)


def param_cli_flags(specs: Iterable[ParamSpec]) -> Dict[str, str]:
    return {flag: f'{spec.name}={value}' for spec in specs for flag, value in spec.cli_flags}


def coerce_value(value: str) -> Union[bool, int, float, str]:
    """Coerce a string value to its appropriate type.

    BACK-1211: the literal strings '0'/'1' are coerced to bool here
    regardless of the field's real declared type (int/float/enum/string) --
    this function has no schema to consult, only the string shape. Harmless
    for int_param()-style consumers (bool is an int subclass), but a call
    site that does ``str(query_params.get(x) or default)`` expecting the
    original numeric/string representation gets ``str(False) == 'False'``
    instead of ``'0'`` -- confirmed live in pack's ?budget=0 (BACK-1180).
    A call site whose values could legitimately BE '0'/'1' (a numeric
    field, or an enum with those literal members) must special-case
    ``isinstance(value, bool)`` and recover via ``str(int(value))`` the way
    ``PackAdapter.get_structure()`` does for ?budget= -- see that call site
    for the exact pattern.
    """
    if not isinstance(value, str):
        return value

    if value.lower() in ('true', 'false', 'yes', 'no', '1', '0'):
        return value.lower() in ('true', 'yes', '1')

    try:
        if '.' in value:
            return float(value)
        return int(value)
    except ValueError:
        pass

    return value


# `?exclude=` carries a list of glob patterns inside one query value: ',' separates
# patterns and '&'/'=' delimit query params, so a pattern containing any of them (or a
# literal '%') is percent-escaped on the way in and decoded on the way out (BACK-1380).
_EXCLUDE_ESCAPES = (('%', '%25'), (',', '%2C'), ('&', '%26'), ('=', '%3D'))


def join_exclude_patterns(patterns: Iterable[str]) -> str:
    """Encode exclude patterns as one ``?exclude=`` value; inverse of split_exclude_param."""
    encoded = []
    for pattern in patterns:
        for char, escape in _EXCLUDE_ESCAPES:
            pattern = pattern.replace(char, escape)
        encoded.append(pattern)
    return ','.join(encoded)


def split_exclude_param(value: Any) -> List[str]:
    """Decode an ``?exclude=`` value into its patterns (empty entries dropped)."""
    if not value or value is True:
        return []
    patterns = []
    for part in str(value).split(','):
        for char, escape in reversed(_EXCLUDE_ESCAPES):
            part = part.replace(escape, char).replace(escape.lower(), char)
        if part:
            patterns.append(part)
    return patterns


def parse_query_params(query: str, coerce: bool = False) -> QueryParams:
    """Parse URL query string into parameter dictionary. A key counts as used by the flag
    ledger once the adapter reads it (``QueryParams``), not when it is parsed."""
    params = QueryParams()
    if not query:
        return params

    for part in query.split('&'):
        part = part.strip()
        if not part:
            continue

        if '=' in part:
            key, value_str = part.split('=', 1)
            key = key.strip()
            value_str = value_str.strip()
            value: Union[bool, int, float, str] = coerce_value(value_str) if coerce else value_str
            params[key] = value
        else:
            params[part] = True

    query_key_recorder(*dict.keys(params))
    return params


def filter_expression(key: str, value: Any) -> str:
    """One parsed query item as the filter text it was written as; the inverse of
    ``parse_query_params`` for an adapter that routes some keys to ``parse_query_filters``.

    A part with no ``=`` (``lines>50``, ``date>2026-01-01``, ``email!~@x``) parses as a bare key
    whose value is True, so the key alone is the expression; rebuilding it as ``key=True`` puts
    ``=True`` into the compared value. ``complexity>=5`` parses as key ``complexity>`` with value
    ``5`` and rebuilds as written.
    """
    return key if value is True else f'{key}={value}'


def warn_unknown_query_params(
    query_params: Dict[str, Any],
    known_keys: Optional[Iterable[str]],
    *,
    adapter: str = '',
    skip_filter_keys: bool = False,
    stream: Optional[TextIO] = None,
) -> List[str]:
    """Disclose query params an adapter doesn't recognize, as text or a dispatch JSON warning.

    Closed-param adapters read a fixed key set via ``.get()`` and silently
    ignore everything else, so a typo'd or unsupported param (the BACK-507
    repro ``stats://?complexity=true``) returns a valid-looking-but-wrong
    result with no signal. This surfaces that: it emits one stderr warning per
    unrecognized key and returns the list, but does *not* raise — the result is
    still produced (a warning contract, not an error contract). A JSON dispatch
    retains the diagnostic for its shared writer instead of printing a suffix.

    Args:
        query_params: parsed ``{key: value}`` dict from ``parse_query_params``.
        known_keys: the adapter's recognized param names (its closed set,
            usually ``get_schema()['query_params'].keys()``). None means unknown
            vocabulary: disclose the ignored key without claiming a valid-key set.
        adapter: scheme name for the message (e.g. ``'stats'``).
        skip_filter_keys: for *mixed* adapters (``stats://``, ``git://``) that
            parse the same query string as both params and filters — skip any
            key carrying a filter operator (``< > ~ !``), since those are filter
            expressions (``complexity>10``), not fixed params, and are handled
            by the filter parser.
        stream: output stream (defaults to ``sys.stderr``; injectable for tests).

    Returns:
        The list of unrecognized keys (empty if all recognized).
    """
    out = stream if stream is not None else sys.stderr
    known = set(known_keys or ())
    unknown = []
    for key, _ in peek_query_items(query_params):  # validating is not reading
        if key in known:
            continue
        if skip_filter_keys and any(c in _FILTER_OP_CHARS for c in key):
            continue  # a filter expression, not a fixed param — handled elsewhere
        unknown.append(key)

    if unknown:
        mark_query_keys(query_params, *unknown)  # named here, so the ledger need not repeat it
        prefix = f"{adapter}://" if adapter else "this resource"
        valid = ', '.join(sorted(known)) if known else '(none)'
        for key in unknown:
            _warn_unknown_query_param(key, prefix, valid if known_keys is not None else None, out)

    return unknown


def _warn_unknown_query_param(key: str, prefix: str, valid: Optional[str], out: TextIO) -> None:
    """One warning fact, rendered as text or retained for the dispatch's JSON writer."""
    message = f"⚠ Unknown query param '{key}' for {prefix} — ignored."
    if valid is not None:
        message += f" Valid params: {valid}"
    log = _KEY_LOG.get()
    if log is not None:
        log.warnings.append({'type': 'unknown_query_param', 'code': 'unknown_query_param',
                             'fields': [key], 'message': message})
    if log is None or log.warnings_to_stderr:
        print(message, file=out)


REGEX_MAX_LEN = 200


def check_regex_pattern(field: str, op: str, pattern: str) -> None:
    """Reject a ``~=``/``!~`` pattern that can never match, so it fails instead of reading as an empty answer."""
    if len(pattern) > REGEX_MAX_LEN:
        raise ValueError(
            f"Regex for {field}{op} is too long ({len(pattern)} characters, limit {REGEX_MAX_LEN}): {pattern[:40]!r}..."
        )
    try:
        _re.compile(pattern)
    except _re.error as exc:
        raise ValueError(f"Invalid regular expression for {field}{op}{pattern}: {exc}") from exc


@dataclass
class QueryFilter:
    """Represents a single filter condition.

    Attributes:
        field: Field name to filter on
        op: Operator (>, <, >=, <=, =, !=, ~=, .., ?, !, *)
        value: Target value for comparison (str or coerced type)
    """
    field: str
    op: str
    value: Union[bool, int, float, str]

    VALID_OPERATORS = {'=', '>', '<', '>=', '<=', '!=', '~=', '!~', '..', '?', '!', '*', '=='}

    def __post_init__(self):
        if self.op == '==':
            self.op = '='

        if self.op not in self.VALID_OPERATORS:
            raise ValueError(f"Invalid operator: {self.op}. Must be one of {sorted(self.VALID_OPERATORS)}")
        if self.op in ('~=', '!~'):
            check_regex_pattern(self.field, self.op, str(self.value))


def _try_parse_negation_filter(part: str) -> Optional[QueryFilter]:
    """Try to parse negation filter (!field)."""
    if part.startswith('!'):
        field = part[1:].strip()
        if field:
            return QueryFilter(field, '!', '')
    return None


def _filter_value(text: str, percent_decode_values: bool) -> str:
    """Trim query spelling, then decode one value without touching query delimiters."""
    value = text.strip()
    return unquote(value, encoding='utf-8', errors='strict') if percent_decode_values else value


def _equality_spelled_once(part: str) -> str:
    """*part* with a ``==`` operator written as ``=`` (BACK-2662), so it gets ``=``'s wildcard and range handling.

    ``==`` is the operator only as the term's first ``=`` and not the tail of ``!=``, ``~=``, ``<=`` or ``>=``: a
    value that contains ``==`` (``hash=abc==``) keeps it, and ``name!==x`` stays ``!=`` with value ``=x``.
    """
    eq = part.find('=')
    if eq > 0 and part.startswith('==', eq) and part[eq - 1] not in '!~<>':
        return part[:eq] + part[eq + 1:]
    return part


def _try_parse_two_char_operators(
    part: str, coerce_numeric: bool, percent_decode_values: bool = False,
) -> Optional[QueryFilter]:
    """Try to parse two-character operators (>=, <=, !=, ~=, !~).

    Also handles reversed/doubled forms: => -> >=, =< -> <=, =>= -> >=, =<= -> <=.
    """
    for op in ['>=', '<=', '!=', '~=', '!~']:
        if op in part:
            field, value_str = part.split(op, 1)
            field = field.strip()
            # Strip a spurious trailing = left by =>=, =<= patterns (e.g. field=>=10 -> field>=10)
            if field.endswith('='):
                field = field[:-1].strip()
            value_str = _filter_value(value_str, percent_decode_values)

            value: Union[bool, int, float, str]
            if coerce_numeric and op not in ('~=', '!~'):
                value = coerce_value(value_str)
            else:
                value = value_str

            return QueryFilter(field, op, value)
    return None


def _parse_equals_special_cases(field: str, value: str) -> Optional[QueryFilter]:
    """Parse special cases for = operator (wildcards, ranges)."""
    if '*' in value:
        return QueryFilter(field, '*', value)

    if '..' in value:
        return QueryFilter(field, '..', value)

    return None


def _try_parse_single_char_operators(
    part: str, coerce_numeric: bool, percent_decode_values: bool = False,
) -> Optional[QueryFilter]:
    """Try to parse single-character operators (>, <, =).

    Also handles reversed forms: => -> >=, =< -> <= (field=trailing-= stripped, op promoted).
    """
    for op in ['>', '<', '=']:
        if op not in part:
            continue
        field, value = part.split(op, 1)
        field = field.strip()
        value = _filter_value(value, percent_decode_values)
        # Detect reversed-operator typos: field=>val or field=<val
        # The trailing = on the field means the user wrote => or =< instead of >= or <=
        if op in ('>', '<') and field.endswith('='):
            field = field[:-1].strip()
            op = '>=' if op == '>' else '<='
        if op == '=':
            special_filter = _parse_equals_special_cases(field, value)
            if special_filter:
                return special_filter
        final_value: Union[bool, int, float, str] = coerce_value(value) if coerce_numeric else value
        return QueryFilter(field, op, final_value)
    return None


def parse_query_filters(
    query: str,
    coerce_numeric: bool = True,
    support_existence: bool = True,
    record: bool = True,
    *,
    percent_decode_values: bool = False,
) -> List[QueryFilter]:
    """Parse query string into list of QueryFilter objects.

    Supports operators: >, <, >=, <=, =, ==, !=, ~=, .., ?, !

    Optional percent decoding applies once to values after structural splitting;
    fields and literal plus signs stay unchanged. The default retains raw values.

    Parsing a filter counts its key as used (the flag ledger). ``record=False`` marks the
    keys only as parsed, for an adapter that applies its filters to some targets and not
    others: it calls ``note_query_parsed`` when it does apply them (json:// filters arrays,
    never an object, BACK-1542).
    """
    if not query:
        return []
    if record:
        note_query_parsed(query)
    else:
        query_key_recorder(*(part for part in query.split('&') if part.strip()))

    filters = []
    parts = query.split('&')

    for part in parts:
        part = part.strip()
        if not part:
            continue

        parsed_filter = None

        if support_existence:
            parsed_filter = _try_parse_negation_filter(part)
            if parsed_filter:
                filters.append(parsed_filter)
                continue

        part = _equality_spelled_once(part)
        parsed_filter = _try_parse_two_char_operators(part, coerce_numeric, percent_decode_values)
        if parsed_filter:
            filters.append(parsed_filter)
            continue

        parsed_filter = _try_parse_single_char_operators(part, coerce_numeric, percent_decode_values)
        if parsed_filter:
            filters.append(parsed_filter)
            continue

        if support_existence:
            filters.append(QueryFilter(part, '?', ''))

    return filters
