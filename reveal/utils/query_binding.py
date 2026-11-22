"""Declared CLI/URI binding; legacy raw queries and exclusion/filter codecs stay separate."""

import argparse
import re
import stat
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Union
from urllib.parse import quote, unquote

from ..errors import RequestValidationError, UnreadControlError, UnsupportedOverrideError
from .query_parser import (SHARED_CONTROL_NAMES, LegacySpelling, ParamSpec, ParamValueError, QueryParams, ResourceSpec,
                           mark_query_keys, parse_query_params, peek_query_items, query_key,
                           query_key_recorder, whole_number)


def boolean_value(value: Any) -> bool:
    """Bare presence and explicit true/false are distinct; reject other spellings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ('true', 'false', 'yes', 'no', '1', '0'):
        return value.lower() in ('true', 'yes', '1')
    raise ValueError('expected true or false')


def switch_value(value: Any) -> bool:
    """The one on/off codec every switch reads (COMMAND_MODEL "Switches"): ``on``/``off`` in any case, or a boolean
    spelling ``boolean_value`` accepts; anything else is a ValueError."""
    if isinstance(value, str) and value.lower() in ('on', 'off'):
        return value.lower() == 'on'
    return boolean_value(value)


def legacy_switch(name: str, on: str, off: str) -> Callable[[Any], str]:
    """A legacy negative boolean (``no_churn``, ``no_imports``, ``summary_only``) as the canonical value it stands for:
    *on* when it is true, *off* when false (COMMAND_MODEL "Switches")."""
    def codec(value: Any) -> str:
        try:
            return on if boolean_value(value) else off
        except ValueError:
            raise ParamValueError(f'{name} must be a valid boolean, got {value!r}') from None
    return codec


def verbose_legacy(value: Any, replacement: str) -> LegacySpelling:
    """The legacy word ``verbose`` on the control it stands for (COMMAND_MODEL "Detail", BACK-2654 note #17):
    ``detail=full`` where it adds detail, the uncapping value of the cap it lifts elsewhere. ``verbose=false`` is the
    control's default. *replacement* is what the rejection of a non-boolean value teaches."""
    def codec(raw: Any) -> Any:
        try:
            return value if boolean_value(raw) else None
        except ValueError:
            raise ParamValueError(f'verbose must be a valid boolean, got {raw!r}: use {replacement}') from None
    return LegacySpelling('verbose', codec=codec)


def verbose_binding(declarations: Iterable[ParamSpec]) -> tuple:
    """(key, value) the global ``--verbose`` binds on a declared noun (rule 4, BACK-2654 note #17): the noun's own
    spelling ``verbose`` where a control declares it, otherwise ``detail=full``. A noun without either declaration
    rejects it, naming detail and its controls."""
    declarations = tuple(declarations)
    if any('verbose' in spec.spellings for spec in declarations):
        return 'verbose', True
    if any(spec.name == 'detail' for spec in declarations):
        return 'detail', 'full'
    raise RequestValidationError('--verbose is --detail full: ' + unsupported_controls_message(declarations, ['detail']))


def legacy_presence_value(value: Any) -> bool:
    """Legacy URI flags mean presence; typed False explicitly restores omission."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return True
    raise ValueError('expected a flag or boolean')


def string_value(value: Any) -> str:
    """A literal string, including empty text; never decode, trim or coerce it."""
    if not isinstance(value, str) or '\x00' in value:
        raise ValueError('expected a string without NUL')
    return value


def _list_parts(value: str) -> list[str]:
    # The empty query means no items; an empty member has no distinct comma encoding.
    if not value:
        return []
    parts = value.split(',')
    if any(not part for part in parts):
        raise ValueError('comma-percent lists cannot contain empty elements')
    return parts


def encode_param_value(spec: ParamSpec, value: Any) -> str:
    """Encode one explicitly declared value; never use form-style plus decoding.

    comma-percent encodes each nonempty item before joining; [] is ''. Empty
    members are rejected because that format cannot distinguish [] from [''].
    """
    if spec.uri_codec == 'raw':
        return str(value)
    if spec.uri_codec == 'percent':
        return quote(str(value), safe='')
    if spec.uri_codec == 'comma-percent':
        if not isinstance(value, (list, tuple)):
            raise ValueError('comma-percent values must be a list or tuple')
        items = list(value)
        if any(not isinstance(item, str) or not item for item in items):
            raise ValueError('comma-percent lists require nonempty string elements')
        return ','.join(quote(item, safe='') for item in items)
    raise ValueError(f'Unknown URI codec {spec.uri_codec!r}')


def _decode_value(spec: ParamSpec, value: Any) -> Any:
    if spec.uri_codec == 'raw' or not isinstance(value, str):
        return value
    if spec.uri_codec == 'percent':
        return unquote(value, encoding='utf-8', errors='strict')
    if spec.uri_codec == 'comma-percent':
        return [unquote(part, encoding='utf-8', errors='strict') for part in _list_parts(value)]
    raise ValueError(f'Unknown URI codec {spec.uri_codec!r}')


def _comparable(spec: ParamSpec, value: Any) -> Any:
    """A value as its control reads it, so two spellings of one value compare equal; a value the control
    rejects is rejected here, before the conflict check, so the message names the supported values."""
    return spec.validate(value) if value is not None else None


def _spellings_agree(spec: ParamSpec, values: list) -> bool:
    """Two spellings give one value: compared as the control reads it when a legacy spelling translates."""
    if len(values) < 2 or spec.repeatable:
        return True
    if spec.legacy:
        values = [_comparable(spec, value) for value in values]
    return all(type(other) is type(values[0]) and other == values[0] for other in values[1:])


def _accumulated(values: list) -> list:
    """A repeatable control's spellings combine: every value of each, in order."""
    return [item for value in values for item in (value if isinstance(value, (list, tuple)) else [value])]


def _distinct(items: Iterable[Any]) -> list:
    """*items* with each equal item kept once, first-seen order: an equal repeated term is one term, as an equal
    repeated scalar is accepted once (COMMAND_MODEL "Conflicting values"; Scott 2026-11-19, BACK-2715)."""
    kept: list = []
    for item in items:
        if item not in kept:
            kept.append(item)
    return kept


def _echo_query(source: str) -> str:
    """The request's query as it echoes in the answer: each equal ``key=value`` part once (BACK-2715)."""
    return '&'.join(_distinct(part for part in source.split('&') if part))


def _conflicting_spellings(spec: ParamSpec, present: list, spelled: Optional[Mapping[str, str]]) -> str:
    """Rule 1's conflict, naming each spelling as typed (*spelled*: key -> the flag that carried it)."""
    return f'{spec.name}: conflicting spellings: ' + ', '.join((spelled or {}).get(name, name) for name in present)


def _normalize_aliases(declarations: Iterable[ParamSpec], supplied: Mapping[str, Any],
                       spelled: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """Every spelling of a control has one value owner; mixed spellings cannot hide precedence. A legacy
    spelling's value is translated into the control's own (``rank=fan-in`` is ``sort=-fan-in``). A conflict names
    each spelling as the request typed it: *spelled* maps a key to the flag that carried it (the subcommand form);
    without it the key is what was typed (a URI key, an ``api.query`` keyword)."""
    result = dict(peek_query_items(supplied))
    for spec in declarations:
        present = [name for name in spec.spellings if name in result]
        if not present:
            continue
        values = [spec.canonical_value(name, result.pop(name)) for name in present]
        if spec.repeatable and len(values) > 1:  # an omitted spelling (None) adds no term
            values = [value for value in values if value is not None] or [None]
        if not _spellings_agree(spec, values):
            raise ValueError(_conflicting_spellings(spec, present, spelled))
        result[spec.name] = _accumulated(values) if spec.repeatable and len(values) > 1 else values[0]
    return result


def rebind_legacy(declarations: Iterable[ParamSpec], params: QueryParams, spelled: Iterable[str], *,
                  replacing: Iterable[str] = (), bound: bool = False) -> None:
    """A legacy word that changes another control's meaning in its request (``LegacySpelling.rebinds``): when the
    request spells it (*spelled*: the alias and legacy keys it typed) and selects an answer ``rebinds_when`` accepts,
    each first control's value moves to the second control (git ``type=ownership&limit=N`` is ``--scan-limit N``,
    BACK-2616). Called once the request's sources are joined: a URI's or typed keywords' preparation, a flag joining a
    URI, typed overrides. The second control, given too, is one setting (COMMAND_MODEL "Conflicting values"): equal
    values are one, different values raise ValueError naming both; a value a typed override gave (*replacing*)
    replaces the one it overrides. *bound*: the values are converted already (overrides), so the moved one is
    converted by its new control."""
    declarations, spelled, replacing = tuple(declarations), set(spelled), set(replacing)
    values = dict(peek_query_items(params))  # a routing check, not a read
    owners = {spec.name: spec for spec in declarations}
    for entry in (entry for spec in declarations for entry in spec.legacy if entry.rebinds and entry.name in spelled):
        if entry.rebinds_when is None or entry.rebinds_when(values):
            for source, target in entry.rebinds:
                if dict.get(params, source) is not None:
                    _move_value(params, owners[target], source, replacing, bound)


def _move_value(params: QueryParams, spec: ParamSpec, source: str, replacing: set, bound: bool) -> None:
    """``rebind_legacy``'s move of *source*'s value to *spec*'s control, under "Conflicting values"."""
    value, given = dict.get(params, source), dict.get(params, spec.name)
    del params[source]
    params._given.discard(source)
    params._given.add(spec.name)
    if given is not None:
        if (spec.name in replacing) != (source in replacing):
            if spec.name in replacing:
                return  # the override of the control it moves to stands
        elif _same_scalar(spec, given, value):
            return
        else:
            raise ValueError(_conflicting_spellings(spec, [source, spec.name], None))
    if bound:
        params.set_normalized(spec, _validate_binding(spec, value, 'typed'))
    else:
        params[spec.name] = value


def _prepare_repeated_params(declarations: tuple[ParamSpec, ...], source: str, params: QueryParams) -> None:
    """A repeatable control keeps every occurrence of every spelling, in query order (Markdown ``match`` and
    ``body-contains`` AND); a setting given twice with different values is an invalid request."""
    parts = [part.strip().partition('=') for part in source.split('&') if part.strip()]
    for spec in declarations:
        if not spec.repeatable:
            _reject_repeated_setting(spec, parts)
            continue
        if spec.role == 'filter-expression':  # its own terms are the expression list; its legacy words repeat too
            _keep_repeated_words(spec, parts, params)
            continue
        values = [spec.canonical_value(key, _decode_value(spec, value) if separator else True)
                  for key, separator, value in parts if key in spec.spellings]
        if values:
            for name in spec.spellings:
                dict.pop(params, name, None)
            params[spec.name] = values


def _keep_repeated_words(spec: ParamSpec, parts: list, params: QueryParams) -> None:
    """Every occurrence of a filter expression's legacy words (``min_lines`` twice is two terms)."""
    for word in spec.legacy_words:
        values = [value if separator else True for key, separator, value in parts if key == word]
        if values:
            params[word] = values


def _reject_repeated_setting(spec: ParamSpec, parts: list) -> None:
    """``?limit=1&limit=2``: one setting, two values (COMMAND_MODEL "Conflicting values"); equal values are one,
    compared as the control reads them (``?full=1&full=true``, a bare presence key beside ``=true``; BACK-2727)."""
    for name in spec.spellings:
        values = list(dict.fromkeys(value if separator else True for key, separator, value in parts if key == name))
        if len(values) > 1 and not _same_setting(spec, name, values):
            raise RequestValidationError(f'{name} is given twice with different values ({values[0]} and {values[1]}): '
                                         'a setting takes one value; give it once')


def _same_setting(spec: ParamSpec, name: str, values: list) -> bool:
    """Whether the spellings *values* of *name* state one value. A value that states none (``?last=maybe``,
    ``?matches=abc``) is compared as spelled, so its conflict or its value error is reported as before."""
    try:
        stated = [_stated_value(spec, name, value) for value in values]
    except ValueError:
        return False
    return all(type(other) is type(stated[0]) and other == stated[0] for other in stated[1:])


def _stated_value(spec: ParamSpec, name: str, value: Any) -> Any:
    """The value a spelling states, as "Conflicting values" compares it: a switch's or flag's on/off (a bare key is on,
    ``1``, ``true`` and ``yes`` are one value), a whole number's integer (``3`` and ``03``), otherwise the control's own
    value (a legacy word translated, a percent spelling decoded). Not a lossy codec's output: a legacy presence flag reads
    ``false`` as on and Claude's ``snippet`` clamps 3 and 7 to one value, yet each pair states two values (cell 1c)."""
    value = spec.canonical_value(name, _decode_value(spec, value))
    if spec.type in ('boolean', 'flag'):
        return switch_value(value)
    if spec.type == 'integer':
        return whole_number(value)
    return _comparable(spec, value)


def _same_selection(spec: ParamSpec, given: Any, first: str) -> bool:
    """``?flatten&view=flatten`` names one view twice, which is one setting (rule 5, COMMAND_MODEL "Conflicting
    values"); a different view still conflicts."""
    values = given if isinstance(given, (list, tuple)) else [given]
    try:
        return all(spec.validate(value) == spec.validate(first) for value in values)
    except (ValueError, RequestValidationError):
        return False


def _prepare_legacy_selectors(declarations: tuple[ParamSpec, ...], source: str, params: QueryParams) -> Dict[str, str]:
    """Opted-in first bare words select views; field=value remains dataset syntax."""
    first = source.partition('&')[0].lower()
    selected = {}
    for spec in declarations:
        if first not in spec.first_selectors:
            continue
        if spec.name in params and not _same_selection(spec, params[spec.name], first):
            raise RequestValidationError(f'{first} conflicts with {spec.name}')
        dict.pop(params, first, None)
        params[spec.name] = first
        selected[spec.name] = first
    return selected


def shared_name_is_legacy_field(declarations: Iterable[ParamSpec], name: str) -> bool:
    """Rule 8 until the cut (BACK-2654): on a noun whose where fields come from the data (open fields), a bare key
    named like a shared control the noun does not declare is a legacy spelling of the identical where term, noted
    from the one generated RETIREMENTS row family (``invocation.retirement_note``). A closed-field noun never read
    such a key as a field, so it has no legacy meaning there. At the cut this returns False everywhere: exit 2."""
    declarations = tuple(declarations)
    expression = next((spec for spec in declarations if spec.role == 'filter-expression'), None)
    return (name in SHARED_CONTROL_NAMES and expression is not None and bool(expression.open_fields)
            and not any(name in spec.spellings for spec in declarations))


def _prepare_expression_params(declarations, source, params, selectors, expression) -> tuple:
    """Fold explicit where= values and bare field keys into the expression list; return the folded keys and the
    bare keys that spell a shared control the noun does not declare. Such a key is that control, never a field (rule 8,
    BACK-2654), so the binder rejects it, except where it is a legacy field spelling until the cut
    (``shared_name_is_legacy_field``: the same term). A declared spelling folds as before (AST ``kind!=X``, and
    ``depth OP N``, the legacy word of where whose translation is the same term)."""
    known = {name for spec in declarations for name in spec.spellings}
    terms, folded, shared = [], [], []
    for index, part in enumerate(source.split('&')):
        if index == 0 and selectors:
            continue
        key, separator, value = part.strip().partition('=')
        if key == expression.name and separator:
            terms.append(unquote(value, encoding='utf-8', errors='strict'))
        elif key and key not in known and key not in _TRANSPORT_KEYS:  # the walk policy is never a field
            dict.pop(params, key, None)
            field = query_key(part)
            if (field in SHARED_CONTROL_NAMES and field not in known  # a declared one (AST kind!=X) folds as before
                    and not shared_name_is_legacy_field(declarations, field)):
                shared.append(field)
                continue
            terms.append(part.strip())
            folded.append(field)
    if terms:
        params[expression.name] = terms
    return tuple(folded), tuple(shared)


def _fields_clause(declarations: tuple[ParamSpec, ...]) -> str:
    expression = next((spec for spec in declarations if spec.role == 'filter-expression'), None)
    fields = (', '.join(expression.fields) or expression.open_fields) if expression is not None else ''
    return f"; fields (FIELD OP VALUE, bare or in {expression.name}=): {fields}" if expression and fields else ''


def _symbol_clause(declarations: tuple[ParamSpec, ...]) -> str:
    symbol = next((spec for spec in declarations if spec.names == 'symbol' and spec.role == 'operation'), None)
    if symbol is None:
        return ''
    flag = f' (--{symbol.name} NAME)' if symbol.cli else ''
    return f'. Use {symbol.name}=NAME{flag} for a supported per-symbol lookup; no equivalent filter is implied'


def _shared_name_clause(declarations: tuple[ParamSpec, ...], unknown: list) -> str:
    """A shared control name is never a bare field (rule 8): name the where spelling of a field so called."""
    expression = next((spec for spec in declarations if spec.role == 'filter-expression'), None)
    shared = [key for key in unknown if key in SHARED_CONTROL_NAMES]
    if expression is None or not expression.open_fields or not shared:  # a closed-field noun has no such field
        return ''
    return (f"; a shared control name is never a bare field: filter on a field so named with "
            f"{', '.join(f'{expression.name}={key}' for key in shared)} OP VALUE")


def unsupported_controls_message(declarations: Iterable[ParamSpec], unknown: Iterable[str]) -> str:
    """Rule 3's teaching (COMMAND_MODEL "Unsupported controls", BACK-2654): the keys a request named that the noun
    does not declare, then every control it does declare, its where fields and its per-symbol lookup."""
    declarations = tuple(declarations)
    unknown = list(dict.fromkeys(unknown))
    controls = ', '.join(spec.name for spec in declarations if not spec.flag_only) or '(none)'
    return (f"unsupported control{'s' if len(unknown) > 1 else ''} {', '.join(repr(key) for key in unknown)}; "
            f"supported controls: {controls}{_fields_clause(declarations)}{_symbol_clause(declarations)}"
            f"{_shared_name_clause(declarations, unknown)}")


def declared_spelling(declarations: Iterable[ParamSpec], word: str) -> Optional[str]:
    """The declared control a word spells (a name, spelling variant or legacy word; ``_`` and ``-`` alike), or None."""
    declarations = tuple(declarations)
    wanted = word.replace('_', '-')
    return next((spec.name for spec in declarations
                 if wanted in {key.replace('_', '-') for key in _declared_keys((spec,))}), None)


def _declared_keys(declarations: tuple[ParamSpec, ...]) -> set:
    """Every URI key a declaration spells: names, spelling variants and every legacy word (value-keyed and
    first-position selectors included)."""
    return {key for spec in declarations if not spec.flag_only
            for key in (*spec.spellings, *(entry.name for entry in spec.legacy))}


# The walk policy every transport splits off before binding (split_respect_gitignore); an adapter built directly
# receives it from its own CLI_QUERY_FLAGS fragment, which it accepts by definition (BACK-1361).
_TRANSPORT_KEYS = frozenset({'respect_gitignore'})
# A where term's field ends at its operator; a dotted path (lines.total) stays whole.
_FIELD_END = re.compile(r'[=<>!~]')


def _declared_field(key: str, fields: tuple) -> bool:
    """A field the noun declares, or a dotted path under a declared field or a declared record section (``lines.*``)."""
    head = key.split('.', 1)[0]
    return key in fields or ('.' in key and (head in fields or f'{head}.*' in fields))


def where_fields(params: QueryParams, expression: ParamSpec) -> list:
    """The field of every where term, written explicitly or folded from a bare key."""
    terms = params.get(expression.name) or ()  # a decoded where= value may hold a literal '&': one term, one field
    fields = (_FIELD_END.split(str(term).strip().lstrip('!'), 1)[0].strip() for term in terms)
    return [field for field in fields if field]


def _reject_unknown_keys(declarations: tuple[ParamSpec, ...], params: QueryParams, shared: tuple,
                         expression: Optional[ParamSpec]) -> None:
    """The one unknown-key check (rule 3): a key that is neither a declared control nor a declared field exits 2, and
    so does a bare key spelling a shared control the noun does not declare (rule 8; *shared*, never folded)."""
    known = _declared_keys(declarations) | _TRANSPORT_KEYS
    unknown = [*shared, *(key for key in dict.keys(params) if key not in known),
               *_unknown_where_fields(params, expression)]
    if unknown:
        raise RequestValidationError(unsupported_controls_message(declarations, unknown))


def _unknown_where_fields(params: Mapping[str, Any], expression: Optional[ParamSpec]) -> list:
    """The where terms' fields a closed-field expression does not declare (an open field set has no unknown field)."""
    if expression is None or not expression.fields or expression.open_fields:
        return []
    terms = QueryParams({expression.name: dict(peek_query_items(params)).get(expression.name)})  # not a read of params
    return [key for key in where_fields(terms, expression) if not _declared_field(key, expression.fields)]


def reject_unknown_where_fields(declarations: Iterable[ParamSpec], params: Mapping[str, Any]) -> None:
    """Rule 3 for every where term a request binds (BACK-2731): a field a closed-field noun does not declare exits 2
    with the one unknown-key message, whichever transport gave the term (``?where=``, ``--where`` on the subcommand or
    after a URI, a typed keyword or override), as the URI's own check does."""
    declarations = tuple(declarations)
    expression = next((spec for spec in declarations if spec.role == 'filter-expression'), None)
    unknown = _unknown_where_fields(params, expression)
    if unknown:
        raise RequestValidationError(unsupported_controls_message(declarations, unknown))


def _prepare_uri_params(declarations: tuple[ParamSpec, ...], source: str) -> QueryParams:
    """A declared expression-list owns the remaining raw DSL, including repeated bounds.

    Explicit where= values decode once; legacy expressions retain their existing codec.
    The domain's existing expression parser still owns their syntax and evaluation.
    """
    params = parse_query_params(source)
    _prepare_repeated_params(declarations, source, params)
    selectors = _prepare_legacy_selectors(declarations, source, params)
    expression = next((spec for spec in declarations if spec.role == 'filter-expression'), None)
    folded, shared = _prepare_expression_params(declarations, source, params, selectors, expression) \
        if expression else ((), ())
    _reject_unknown_keys(declarations, params, shared, expression)
    prepared = QueryParams(_normalize_aliases(declarations, params))
    prepared._aliases = {spec.name: spec.spellings[1:] for spec in declarations}
    prepared._folded = folded  # the bare field keys folded into where (a noun reading where reads them)
    prepared._selectors = selectors
    prepared._source_query = _echo_query(source)
    prepared._supplied_aliases = {alias for spec in declarations for alias in spec.spellings[1:]
                                  if alias in dict.keys(params)}
    prepared._given = set(dict.keys(prepared))
    for name, selector in selectors.items():
        prepared._aliases[name] += (selector,)
    rebind_legacy(declarations, prepared, prepared._supplied_aliases)
    return prepared


def prepare_declared_params(declarations: Iterable[ParamSpec],
                   source: Union[str, Mapping[str, Any]], transport: str, *,
                   spelled: Optional[Mapping[str, str]] = None) -> QueryParams:
    """*spelled*: for a typed source built from flags, the flag each key came from (see ``_normalize_aliases``)."""
    declarations = tuple(declarations)
    if transport == 'uri':
        if not isinstance(source, str):
            raise TypeError('URI parameters must be a raw query string')
        params = _prepare_uri_params(tuple(declarations), source)
        params._transport = transport
        return params
    if transport != 'typed':
        raise ValueError(f'Unknown parameter transport {transport!r}')
    if isinstance(source, str):
        raise TypeError('Typed parameters must be a mapping')
    return _prepare_typed_params(declarations, source, spelled)


def flag_conflicts_with_uri_message(flag: str, key: str, value: str) -> str:
    """Rule 1's message when a flag after a URI sets a scalar control the URI already sets differently: both named as
    typed, the flag and ``key=value`` (COMMAND_MODEL "Conflicting values")."""
    return f'{flag} conflicts with {key}={value} in the URI: {key} is set twice with different values; give it once'


def _uri_spelling(spec: ParamSpec, params: QueryParams) -> tuple:
    """(key, raw value) of the first query part that set *spec*, as the URI typed it (an alias or legacy word
    included), else the control's name and its prepared value."""
    for part in (getattr(params, '_source_query', None) or '').split('&'):
        key, _, value = part.partition('=')
        if part and query_key(part) in spec.spellings:
            return key, value
    return spec.name, dict.get(params, spec.name)


def _typed_flag(spec: ParamSpec, spelled: Optional[Mapping[str, str]]) -> str:
    """The flag that carried *spec* in a typed source (*spelled*: source key -> the flag typed)."""
    keys = (spec.name, *((spec.cli.dest,) if spec.cli and spec.cli.dest else ()), *legacy_flag_dests(spec),
            *spec.spellings)
    return next((spelled[key] for key in keys if spelled and key in spelled), '--' + spec.name.replace('_', '-'))


def _uri_terms(spec: ParamSpec, value: Any) -> tuple:
    """(prepared, query parts) for a typed value joining a URI's prepared params: a repeatable control's terms as the
    URI's preparation leaves them (decoded, one per term), a scalar as its raw URI value (decoded once, on binding); and
    the query parts that spell it, for the joined source query. A flag typed without its optional value (``True`` on a
    control that is not a boolean: ``--importers``) is the URI's bare key, as ``?importers`` parses."""
    if spec.repeatable:
        terms = list(value) if isinstance(value, (list, tuple)) else [value]
        spelled = [encode_param_value(spec, term) if spec.uri_codec == 'percent' else str(term) for term in terms]
        return terms, [f'{spec.name}={part}' for part in spelled]
    if value is True and spec.type != 'boolean':
        return True, [spec.name]
    raw = encode_param_value(spec, 'true' if value is True else 'false' if value is False else value)
    return raw, [f'{spec.name}={raw}']


def _same_scalar(spec: ParamSpec, uri_value: Any, typed_value: Any) -> bool:
    """Two values of one scalar control, compared as the control reads them; a value it rejects is compared as typed,
    so two different values name both spellings (rule 1) before either is rejected, and two equal ones are rejected
    once, when the request binds."""
    try:
        return bool(_comparable(spec, uri_value) == _comparable(spec, typed_value))
    except ValueError:
        return str(uri_value) == str(typed_value)


def join_uri_and_flags(declarations: Iterable[ParamSpec], uri_params: QueryParams, typed_params: QueryParams, *,
                       spelled: Optional[Mapping[str, str]] = None) -> QueryParams:
    """One request from a URI and the flags typed after it (COMMAND_MODEL "Flags after a URI", BACK-2673).

    *uri_params* and *typed_params* are the two sources prepared by ``prepare_declared_params`` ('uri' and 'typed').
    The answer is the URI's prepared params with every flag-given control joined under "Conflicting values": a control
    only a flag gives is added; a scalar both give once with equal values (compared as the control reads them) is one
    value; a scalar given two different values raises ValueError naming the flag as typed (*spelled*) and the URI's
    ``key=value``; a repeatable control combines, the URI's terms first. Flag values take the form the URI's own
    preparation gives (``_uri_terms``), so the result binds with transport 'uri' (``bind_prepared_params``), keeps the
    URI's metadata (folded bare keys,
    selectors) and records the joined query as its source. Bindings that read the selected answer (``--all``,
    ``--verbose``) apply after this join, so they see the URI's selection too."""
    declarations = tuple(declarations)
    joined = QueryParams(dict(peek_query_items(uri_params)))
    for name in ('_aliases', '_folded', '_selectors'):
        setattr(joined, name, getattr(uri_params, name))
    joined._supplied_aliases = set(uri_params._supplied_aliases) | set(typed_params._supplied_aliases)
    joined._given = set(uri_params._given)
    joined._transport = 'uri'
    query = [part for part in (getattr(uri_params, '_source_query', None) or '').split('&') if part]
    typed = dict(peek_query_items(typed_params))
    for spec in declarations:
        value = typed.get(spec.name)
        if value is None:
            continue
        if spec.flag_only:  # no URI spelling to meet or to echo in the joined query: kept as the flag gave it
            joined[spec.name] = value
            joined._given.add(spec.name)
            continue
        prepared, spelled_parts = _uri_terms(spec, value)
        if spec.name in dict.keys(joined) and not spec.repeatable:  # a routing check, not a read
            key, raw = _uri_spelling(spec, uri_params)
            if not _same_scalar(spec, _decode_value(spec, dict.get(joined, spec.name)), value):
                raise ValueError(flag_conflicts_with_uri_message(_typed_flag(spec, spelled), key, raw))
            continue
        given = dict.get(joined, spec.name)
        joined[spec.name] = _accumulated([given, prepared]) if spec.repeatable and given is not None else prepared
        joined._given.add(spec.name)
        query += spelled_parts
    joined._source_query = _echo_query('&'.join(query))
    rebind_legacy(declarations, joined, joined._supplied_aliases)
    return joined


def _prepare_typed_params(declarations: tuple, source: Mapping[str, Any],
                          spelled: Optional[Mapping[str, str]]) -> QueryParams:
    supplied = _normalize_aliases(declarations, source, spelled)
    params = QueryParams()
    params._aliases = {spec.name: spec.spellings[1:] for spec in declarations}
    params._supplied_aliases = {alias for spec in declarations for alias in spec.spellings[1:] if alias in source}
    for spec in declarations:
        destination = spec.cli.dest if spec.cli and spec.cli.dest else spec.name
        if destination in supplied:
            params[spec.name] = supplied[destination]
        elif spec.name in supplied:
            params[spec.name] = supplied[spec.name]
    params._given = {name for name, value in dict.items(params) if value is not None}  # an omitted flag is None
    rebind_legacy(declarations, params, params._supplied_aliases)
    from .query_parser import query_key_recorder
    query_key_recorder(*dict.keys(params))
    return params


def _validate_binding(spec: ParamSpec, raw: Any, transport: str) -> Any:
    decoded = _decode_value(spec, raw) if transport == 'uri' else raw
    if spec.uri_codec == 'comma-percent':
        if isinstance(decoded, str) or not isinstance(decoded, (list, tuple)):
            raise ValueError(f'{spec.name} must be a list of nonempty strings')
        if any(not isinstance(item, str) or not item for item in decoded):
            raise ValueError(f'{spec.name} lists require nonempty string elements')
    try:
        return spec.validate(decoded)
    except UnicodeDecodeError:
        raise
    except ValueError as exc:
        raise RequestValidationError(str(exc)) from exc


def bind_declared_params(specs: Iterable[ParamSpec], source: Union[str, Mapping[str, Any]],
                         *, transport: str, overrides: Optional[Mapping[str, Any]] = None,
                         validate: Optional[Callable[[QueryParams], None]] = None) -> QueryParams:
    """Validate supplied values without consuming them; conversion/decoding occurs once.

    CLI binding preserves original typed values. URI parsing retains legacy
    trimming/last-wins/presence rules and decodes only explicitly opted-in keys.
    Omitted controls remain omitted, so defaults do not become submitted flags.
    An optional owner validator checks original semantic constraints before typed overrides.
    Explicit typed overrides use canonical declaration names and apply only after
    original-source validation. They never undergo URI decoding or count as reads.
    """
    declarations = tuple(specs)
    params = prepare_declared_params(declarations, source, transport)
    params = bind_prepared_params(declarations, params, transport=transport)
    if validate is not None:
        validate(params)
    params = apply_declared_overrides(declarations, params, overrides)
    reject_two_answers(declarations, params)
    return params


def _selects(spec: ParamSpec, value: Any) -> bool:
    """Whether a supplied answer selector picks its answer: a switch when on, any other when given."""
    if value is None:
        return False
    if spec.type not in ('boolean', 'flag'):
        return True
    try:
        return bool(spec.validate(value))
    except ValueError:  # an invalid switch value is the binder's error, reported on its own
        return True


def selected_cap(declarations: Iterable[ParamSpec], query: Union[str, Mapping[str, Any]]) -> Optional[str]:
    """The cap of the answer *query* selects (a raw URI query, or a subcommand's typed values): the ``cap`` its answer
    selector declares, or None when the selected answer declares none (the noun's own ``--all`` declaration applies).
    Reading the query here is not using it."""
    supplied: Dict[str, Any] = {}
    if isinstance(query, str):
        for part in filter(None, query.split('&')):
            key, sep, value = part.partition('=')
            supplied.setdefault(unquote(key), unquote(value) if sep else True)
    else:
        supplied = dict(query)
    for spec in declarations:
        if spec.role == 'operation' and spec.cap:
            if any(_selects(spec, supplied[name]) for name in spec.spellings if name in supplied):
                return spec.cap
    return None


def reject_two_answers(declarations: Iterable[ParamSpec], params: Mapping[str, Any],
                       spelled: Iterable[str] = ()) -> None:
    """One answer per request (COMMAND_MODEL "One answer per request", BACK-2654): two controls that select the
    answer (role='operation': views, modes, rankings, legacy operations) are an invalid request naming both."""
    operations = [spec for spec in declarations if spec.role == 'operation']
    supplied = dict(peek_query_items(params))
    spelled = set(spelled) | set(getattr(params, '_supplied_aliases', set()))  # the URI's, and the CLI's flags
    picked = [next((name for name in spec.spellings[1:] if name in spelled), spec.name)  # as the caller spelled it
              for spec in operations if spec.name in supplied and _selects(spec, supplied[spec.name])]
    if len(picked) > 1:
        raise RequestValidationError(f'{picked[0]} and {picked[1]} select different answers: one answer per request; '
                                     'give one of ' + ', '.join(spec.name for spec in operations))


def answer_facets(declarations: Iterable[ParamSpec], params: Mapping[str, Any], result_type: str) -> tuple:
    """The names of the answer a request selects (COMMAND_MODEL "Applicability", BACK-2656): its predicted result
    type, then each operation it gives, as ``name`` and, for a valued one, ``name=value``; ``default`` when it gives
    none. A path that selects an answer is in the type (``git_file_history``, ``stats_file``)."""
    supplied = dict(peek_query_items(params))
    selections: list = []
    for spec in declarations:
        if spec.role == 'operation' and spec.name in supplied and _selects(spec, supplied[spec.name]):
            selections.append(spec.name)
            if spec.type not in ('boolean', 'flag'):
                selections.append(f'{spec.name}={supplied[spec.name]}')
    return (result_type, *(selections or ['default']))


def given_controls(params: Mapping[str, Any]) -> set:
    """The controls a request gave: the binder's record, or (a plain mapping) every key with a value."""
    given = getattr(params, '_given', None)
    return set(given) if given is not None else {key for key, value in peek_query_items(params) if value is not None}


def runtime_controls(declarations: Iterable[ParamSpec], params: Mapping[str, Any]) -> QueryParams:
    """The controls a bound request gives, as a noun's readers see them: an omitted control (None) is absent, and so is
    a legacy presence flag given off (a typed False restores omission: the controls whose codec is
    ``legacy_presence_value``, Claude's URI flags). Walking *params* here reads none of them. Reading a control here
    reads every spelling the request gave it, as on *params*: its legacy words (``filter`` for ``where``) and the bare
    field keys the binder folded into the where expression (``?session~=x``)."""
    declarations = tuple(declarations)
    presence = {spec.name for spec in declarations if spec.convert is legacy_presence_value}
    runtime = QueryParams({key: value for key, value in peek_query_items(params)
                           if value is not None and not (key in presence and value is False)})
    runtime._aliases = dict(getattr(params, '_aliases', {}))
    folded = tuple(getattr(params, '_folded', ()))
    expression = next((spec.name for spec in declarations if spec.role == 'filter-expression'), None)
    if folded and expression is not None:
        runtime._aliases[expression] = (*runtime._aliases.get(expression, ()), *folded)
    return runtime


def _reads(spec: ParamSpec, facets: tuple) -> bool:
    """An entry names the answer when every ``+`` part of it does (``claude_messages+default``: that type, no
    operation); empty answers: every answer."""
    return not spec.answers or any(set(entry.split('+')) <= set(facets) for entry in spec.answers)


def answer_reads(declarations: Iterable[ParamSpec], spec: ParamSpec, params: Mapping[str, Any],
                 result_type: Callable[[], str]) -> bool:
    """Whether the answer *params* select reads control *spec* (its declared answers; empty: every answer).
    *result_type* is asked only when the control declares its answers."""
    return not spec.answers or _reads(spec, answer_facets(tuple(declarations), params, result_type()))


def reject_unread_controls(declarations: Iterable[ParamSpec], params: Mapping[str, Any],
                           result_type: Callable[[], str]) -> None:
    """Applicability (COMMAND_MODEL, BACK-2656): a control given to an answer its declaration does not name is an
    invalid request, naming where it is read and the controls this answer reads. *result_type* predicts the selected
    answer's type before analysis; it is asked only when a given control declares its answers."""
    declarations = tuple(declarations)
    given = given_controls(params)
    scoped = _judged_controls(declarations, params, given)
    if scoped:
        facets = answer_facets(declarations, params, result_type())
        unread = [spec for spec in scoped if not _reads(spec, facets)]
        if unread:
            raise UnreadControlError(_unread_controls_message(declarations, unread, facets, params))
    unmet = [problem for spec in declarations if spec.requires and spec.name in given
             for problem in _unmet_requirements(declarations, spec, params)]
    if unmet:
        raise UnreadControlError('; '.join(unmet))


def _judged_controls(declarations: tuple, params: Mapping[str, Any], given: set) -> list:
    """The given controls that declare their answers. A presence flag given off (typed False, ``?flag=false`` where
    its codec reads off) selects nothing, as when omitted, so it is not judged (Codex last/tokens/goal)."""
    supplied = dict(peek_query_items(params))
    return [spec for spec in declarations if spec.answers and spec.role != 'operation' and spec.name in given
            and (spec.type != 'flag' or _selects(spec, supplied.get(spec.name)))]


def _unmet_requirements(declarations: tuple, spec: ParamSpec, params: Mapping[str, Any]) -> list:
    """Each ``requires`` entry of *spec* the request does not meet, as the message naming both. An entry is met when
    one of its ``|`` alternatives is: ``name=value`` by the given or default value, compared after the control's own
    conversion (``churn=on``); a bare ``name`` by that control being given (``filter|search``); ``!name`` by that
    control not being given (two ways to set one thing that never agree, BACK-2623)."""
    problems = []
    given = given_controls(params)
    for requirement in spec.requires:
        alternatives = requirement.split('|')
        if any(_requirement_met(declarations, alternative, params, given) for alternative in alternatives):
            continue
        if requirement.startswith('!'):
            other = next(declaration for declaration in declarations if declaration.name == requirement[1:])
            problems.append(f"control {_as_typed(params, spec.name)} cannot be combined with '{other.name}'; this "
                            f"request gives {other.name}={_bound_value(other, params)}: give one or the other")
            continue
        name, valued, wanted = requirement.partition('=')
        if len(alternatives) == 1 and valued:
            actual = _bound_value(next(declaration for declaration in declarations if declaration.name == name), params)
            problems.append(f"control {_as_typed(params, spec.name)} requires {requirement}; this request gives "
                            f"{name}={_shown(actual, wanted)}: give one or the other")
        else:
            problems.append(f"control {_as_typed(params, spec.name)} requires {' or '.join(alternatives)}; this "
                            f"request gives none of them: give one, or drop {spec.name}")
    return problems


def _requirement_met(declarations: tuple, alternative: str, params: Mapping[str, Any], given: set) -> bool:
    if alternative.startswith('!'):
        return alternative[1:] not in given
    name, valued, wanted = alternative.partition('=')
    if not valued:
        return name in given
    other = next(declaration for declaration in declarations if declaration.name == name)
    return bool(_bound_value(other, params) == other.validate(wanted))


def _bound_value(spec: ParamSpec, params: Mapping[str, Any]) -> Any:
    """The value *spec* has in *params* (its default when not given), converted, without counting it as read."""
    normalized = getattr(params, '_normalized', {}).get(spec.name)
    if normalized is not None and normalized[0] is spec:
        return normalized[1]
    return spec.validate(dict(peek_query_items(params)).get(spec.name))


def _shown(value: Any, like: str) -> str:
    """*value* spelled as the requirement spells its own (a switch's ``on``/``off``, a boolean's ``true``/``false``)."""
    if isinstance(value, bool):
        return ('on' if value else 'off') if like.lower() in ('on', 'off') else str(value).lower()
    return str(value)


def _folded_terms(params: Mapping[str, Any], name: str) -> list:
    """The terms of control *name* that arrived as bare field keys (``?bogus=1`` folds into ``where``), as typed."""
    folded = set(getattr(params, '_folded', ()))
    value = dict(peek_query_items(params)).get(name)
    if not folded or not isinstance(value, list):
        return []
    parts = (part.strip() for part in (getattr(params, '_source_query', None) or '').split('&'))
    return [part for part in parts if part and query_key(part) in folded and part in value]


def _label(spec: ParamSpec) -> str:
    """How a message names a control: a flag-only modifier has no URI key, so it is named by its flag (``--head``),
    the only way a request can spell it; every other control by its name."""
    return spec.cli.flags[0] if spec.flag_only and spec.cli is not None else spec.name


def _as_typed(params: Mapping[str, Any], name: str) -> str:
    """A control named canonically, followed by the bare field keys that spelled it (``'where' (bogus=1)``), so a
    disclosure names what the request said as well as the control it reached."""
    terms = _folded_terms(params, name)
    return f"'{name}'" + (f" ({', '.join(terms)})" if terms else '')


def _unread_controls_message(declarations: tuple, unread: list, facets: tuple, params: Mapping[str, Any]) -> str:
    """Named by the control, whatever spelling carried it: a URI key, a flag injected into the query (--limit can
    reach a URI as a legacy key) and a legacy flag all name one control; its retirement note names the old spelling.
    Bare field keys folded into the filter expression are named as typed beside it."""
    reads = ', '.join(_label(spec) for spec in declarations if spec.role != 'operation' and _reads(spec, facets))
    where = '; '.join(f"{_label(spec)} is read by: {', '.join(spec.answers)}" for spec in unread)
    several = len(unread) > 1
    named = ', '.join(repr(_label(spec)) if spec.flag_only else _as_typed(params, spec.name) for spec in unread)
    return (f"control{'s' if several else ''} {named} "
            f"{'are' if several else 'is'} not read by this answer ({', '.join(facets)}); {where}; "
            f"controls this answer reads: {reads or '(none)'}")


def unread_by_data_warning(params: Dict[str, Any], names: Iterable[str], reason: str) -> Optional[Dict[str, Any]]:
    """The one disclosure of a control only the data can show to be unread (COMMAND_MODEL "Applicability", Scott
    2026-11-18 Q2: JSON ``sort``/``limit``/``offset`` on a value that is not a list), shaped like the open field sets'
    ``unknown_filter_field``: a ``meta.warnings`` entry, exit 0. It counts the controls as read (the disclosure is
    their use), so the unused-input ledger does not name them a second time, bare field keys folded into one of them
    included; the message names those as typed. None when *names* is empty."""
    fields = list(dict.fromkeys(names))
    if not fields:
        return None
    named = ', '.join(_as_typed(params, field) for field in fields)
    mark_query_keys(params, *fields, *(query_key(term) for field in fields for term in _folded_terms(params, field)))
    return {'type': 'control_unread_by_data', 'code': 'control_unread_by_data', 'fields': fields,
            'message': f"{named} {'has' if len(fields) == 1 else 'have'} no effect on this data: {reason}"}


def declined_controls_warning(declarations: Iterable[ParamSpec], params: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """The given controls an answer that declined on the data never read (not applicable, exit 0: a patches scan with
    no test file, git outside a repository): only the data showed they had nothing to shape, so they are named in the
    one ``unread_by_data_warning`` (COMMAND_MODEL "Applicability", Q2), never by the unused-input ledger. A control the
    answer read before declining (git ``since``) and the operation selection that chose the answer are not named.
    None outside a dispatch that records reads (there the ledger names nothing either) or when nothing is left."""
    used = query_key_recorder()
    if used is None:
        return None
    given = given_controls(params)
    unread = [spec.name for spec in declarations
              if spec.name in given and spec.role != 'operation' and query_key(spec.name) not in used]
    return unread_by_data_warning(dict(params) if not isinstance(params, dict) else params, unread,
                                  'the answer does not apply to this target (see not_applicable)')


def withhold_flag_only(declarations: Iterable[ParamSpec], params: Dict[str, Any]) -> None:
    """Drop the flag-only modifiers from bound *params* once applicability has judged them: a CLI layer reads them
    from the namespace (``ParamSpec.flag_only``), and an adapter that hands its params on whole (Git's view readers)
    must not meet a key no URI can spell."""
    for spec in declarations:
        if spec.flag_only:
            dict.pop(params, spec.name, None)
            given: set = getattr(params, '_given', set())
            given.discard(spec.name)
            getattr(params, '_normalized', {}).pop(spec.name, None)


def reject_unsupported_overrides(declarations: Iterable[ParamSpec], overrides: Mapping[str, Any]) -> None:
    """A typed override that names no declared spelling of the noun (``_`` and ``-`` alike) is rule 3's invalid
    request, with the one shared message (BACK-2654). ``api.query`` reads it for a declared noun whose structure call
    takes the overrides itself; a bound noun's binder checks canonical names after alias translation
    (``apply_declared_overrides``) and raises the same error and message."""
    declarations = tuple(declarations)
    keys = {key.replace('-', '_') for key in _declared_keys(declarations)}
    unknown = [key for key in overrides if str(key).replace('-', '_') not in keys]
    if unknown:
        raise UnsupportedOverrideError(unsupported_controls_message(declarations, unknown))


def apply_declared_overrides(declarations: Iterable[ParamSpec], params: QueryParams,
                             overrides: Optional[Mapping[str, Any]]) -> QueryParams:
    """Apply typed overrides after original-source validation, without URI serialization."""
    declarations = tuple(declarations)
    if overrides is not None:
        if not isinstance(overrides, Mapping):
            raise TypeError('Declared parameter overrides must be a mapping')
        supplied = _normalize_aliases(declarations, overrides)
        names = {spec.name for spec in declarations if not spec.flag_only}
        unknown = [key for key in supplied if key not in names]
        if unknown:
            raise UnsupportedOverrideError(unsupported_controls_message(declarations, unknown))
        from .query_parser import query_key_recorder
        query_key_recorder(*supplied)
        for spec in declarations:
            if spec.name in supplied:
                raw = supplied[spec.name]
                (params._given.discard if raw is None else params._given.add)(spec.name)  # None: the default
                value = spec.validate(None) if raw is None else _validate_binding(spec, raw, 'typed')
                params.set_normalized(spec, value)
        _rebind_overrides(declarations, params, overrides, supplied)
        reject_unknown_where_fields(declarations, params)
    return params


def _rebind_overrides(declarations: tuple, params: QueryParams, overrides: Mapping[str, Any],
                      supplied: Mapping[str, Any]) -> None:
    """``rebind_legacy`` after typed overrides apply: a legacy word the URI or a keyword spelled; an overriding value
    replaces the one it overrides."""
    typed_words = {alias for spec in declarations for alias in spec.spellings[1:] if alias in overrides}
    rebind_legacy(declarations, params, set(params._supplied_aliases) | typed_words,
                  replacing=[name for name, raw in supplied.items() if raw is not None], bound=True)


def bind_prepared_params(declarations: Iterable[ParamSpec], params: QueryParams, *,
                         transport: str) -> QueryParams:
    """Convert a prepared source once, after its operation identity is resolved."""
    supplied = dict(peek_query_items(params))
    for spec in declarations:
        if spec.name not in supplied:
            if spec.required:
                raise ValueError(f'{spec.name} is required')
            continue
        if supplied[spec.name] is None:  # a legacy codec's "the default" (verbose=false): not given, as typed None is
            params._given.discard(spec.name)
            params.set_normalized(spec, spec.validate(None))
            continue
        value = _validate_binding(spec, supplied[spec.name], transport)
        if spec.repeatable and isinstance(value, list):
            value = _distinct(value)  # an equal repeated term is one term (BACK-2715)
        params.set_normalized(spec, value)
    reject_unknown_where_fields(declarations, params)
    return params


class ScalarOnceAction(argparse.Action):
    """A setting typed twice: equal values are one, different values are an invalid request naming both, whichever
    spellings carried them (COMMAND_MODEL "Conflicting values"; argparse alone keeps the last)."""

    def __init__(self, *args, translate=None, comparable=None, seen=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.translate = translate
        self.comparable = comparable or (lambda value: value)
        self.box = seen if seen is not None else {}  # shared by the actions that spell one control

    def _same(self, left, right):
        try:
            return self.comparable(left) == self.comparable(right)
        except ValueError:  # an invalid value is rejected by the binder; compare what was typed
            return left == right

    def __call__(self, parser, namespace, values, option_string=None):
        if self.translate is not None:
            try:
                values = self.translate(option_string, values)
            except ValueError:
                # Invalid values are rejected by the binder, preserving JSON
                # request diagnostics instead of an argparse-only usage dump.
                pass
        self._store(namespace, values, option_string)

    def _store(self, namespace, values, option_string):
        # What this control's spellings saw in this parse, kept off the namespace (an attribute would read as a flag).
        if self.box.get('namespace') is not namespace:
            self.box.clear()
            self.box.update(namespace=namespace, values={})
        previous = self.box['values']
        for flag, value in previous.items():
            if value == values or (flag != option_string and self._same(value, values)):
                continue  # one spelling compares as typed (as the URI does); two compare as the control reads them
            if flag != option_string:
                raise argparse.ArgumentError(self, f'conflicting spellings: {flag}, {option_string}')
            raise argparse.ArgumentError(self, f'given twice with different values: {flag} {value} and '
                                               f'{option_string} {values}; give it once')
        previous[option_string] = values
        setattr(namespace, self.dest, values)


def _add_legacy_cli_arguments(parser, spec):
    for flag, value in spec.cli_flags:
        option = '--' + flag
        if option not in parser._option_string_actions:
            parser.add_argument(option, action='store_true', default=argparse.SUPPRESS,
                                help=f'Legacy {option}: sets --{spec.name}={value}')


class _LegacyFlagAction(ScalarOnceAction):
    """An old flag generated from its legacy entry, kept under the legacy name as the URI key is: the binder
    translates it, so its value errors and conflicts read alike on both spellings. A flag that took no value stands
    for its entry's value; a repeatable control's legacy flag appends."""

    def __init__(self, *args, entry=None, repeatable=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.entry, self.repeatable = entry, repeatable

    def __call__(self, parser, namespace, values, option_string=None):
        value = self.entry.flag_value if self.nargs == 0 else values
        if self.repeatable:
            setattr(namespace, self.dest, [*(getattr(namespace, self.dest, None) or []), value])
            return
        self._store(namespace, value, option_string)


def _separate_legacy_flags(spec: ParamSpec) -> list:
    """The legacy entries whose old flag needs an argument of its own: no value, or a translation (the shared
    argument stores what it is given under the control's name)."""
    return [entry for entry in spec.legacy if entry.flag and entry.value is None and not entry.first
            and (entry.flag_value is not None or (spec.repeatable and entry.codec is not None))]


def legacy_flag_dests(spec: ParamSpec) -> Dict[str, str]:
    """The argparse dests of the legacy flags with arguments of their own -> the legacy name they carry."""
    return {entry.name: entry.name for entry in _separate_legacy_flags(spec)}


def flag_spellings(spec: ParamSpec) -> Dict[str, str]:
    """The key each of the control's generated arguments stores -> the flag that spells it (``add_declared_arguments``):
    its own argument's first flag, and each legacy flag with an argument of its own."""
    separate = {entry.name: entry.flag for entry in _separate_legacy_flags(spec)}
    own = [flag for flag in (spec.cli.flags if spec.cli is not None else ()) if flag not in separate.values()]
    return {**({(spec.cli.dest or spec.name): own[0]} if spec.cli is not None and own else {}), **separate}


def _add_legacy_flag_arguments(parser, spec) -> None:
    for entry in _separate_legacy_flags(spec):
        parser.add_argument(entry.flag, dest=entry.name, default=argparse.SUPPRESS, action=_LegacyFlagAction,
                            nargs=0 if entry.flag_value is not None else None, entry=entry,
                            repeatable=spec.repeatable, help=f'Legacy {entry.flag}: {spec.name}')


def convert_flag_only(specs: Iterable[ParamSpec], args: Any) -> None:
    """Store each applied flag-only modifier on the namespace converted, as the main parser's ``type=`` did, so the CLI
    layer that reads it (the router's slice) gets ``3`` and ``(2, 4)``. A value the control rejects stays as typed: the
    binder refuses it with the request's diagnostics, as it refuses any control's value."""
    for spec in specs:
        if spec.flag_only != 'applied' or spec.cli is None:  # a flag-only modifier always has its binding
            continue
        dest = spec.cli.dest or spec.name
        raw = getattr(args, dest, None)
        if raw is None:
            continue
        try:
            setattr(args, dest, spec.validate(raw))
        except ValueError:
            pass


def _owned_by_parser(parser, spec: ParamSpec) -> bool:
    """Whether *parser* already owns every flag of *spec*'s own argument (the main parser's ``--depth``, ``--range``,
    ``--head``, ``--tail``, which other path-read answers read): that argument is not generated again, and its value is
    the control's (the typed source reads the dest). An owned flag storing another destination would hand the control
    another control's value: a declaration error."""
    cli = spec.cli
    owned = [parser._option_string_actions.get(flag) for flag in cli.flags] if cli is not None else []
    if not owned or any(action is None for action in owned):
        return False
    dest = cli.dest or spec.name
    for flag, action in zip(cli.flags, owned):
        if action.dest != dest:
            raise ValueError(f'{spec.name}: {flag} is owned by the parser\'s {action.dest!r} argument, not {dest!r}')
    return True


def add_declared_arguments(parser: argparse.ArgumentParser, specs: Iterable[ParamSpec],
                           resource: Optional[ResourceSpec]) -> None:
    """Generate local arguments; global presentation/exclusion owners remain unchanged. *resource* None: no positional
    (the main parser's path read keeps its own, BACK-2627). A control whose flags the parser already owns keeps that
    argument (``_owned_by_parser``); a declared noun's parser owns none of its controls' flags."""
    if resource is not None:
        parser.add_argument(resource.name, nargs=None if resource.required else '?',
                            default=resource.cli_default)
    groups: Dict[str, Any] = {}
    for spec in specs:
        _add_legacy_cli_arguments(parser, spec)
        cli = spec.cli
        if cli is None:
            continue
        if _owned_by_parser(parser, spec):
            _add_legacy_flag_arguments(parser, spec)
            continue
        box: Dict[str, Any] = {}
        options: Dict[str, Any] = {'dest': cli.dest or spec.name, 'default': argparse.SUPPRESS,
                                   'required': cli.required, 'help': spec.description}
        if spec.cli_action is not None:
            options['action'] = spec.cli_action
        else:
            if cli.nargs != 0:
                options['action'] = ScalarOnceAction
                options['translate'] = spec.canonical_value
                options['comparable'] = spec.validate
                options['seen'] = box
            if cli.nargs is not None:
                options['nargs'] = cli.nargs
                if cli.nargs == '?':
                    options['const'] = cli.const
            if cli.metavar is not None:
                options['metavar'] = cli.metavar
        separate = {entry.flag for entry in _separate_legacy_flags(spec)}
        owner = parser
        if cli.exclusive:
            if cli.exclusive not in groups:
                groups[cli.exclusive] = parser.add_mutually_exclusive_group()
            owner = groups[cli.exclusive]
        owner.add_argument(*(flag for flag in spec.flags if flag not in separate), **options)
        _add_legacy_flag_arguments(parser, spec)


def _resource_exists(path: str) -> bool:
    if '\x00' in path:
        raise RequestValidationError('Resource path must not contain NUL')
    try:
        Path(path).expanduser().stat()
    except (FileNotFoundError, NotADirectoryError):
        return False
    return True


def _resource_exists_at(value: str, resolve: Optional[Callable[[str], str]]) -> bool:
    return _resource_exists(resolve(value) if resolve else value)


def bind_resource_path(spec: ResourceSpec, path: str, *, transport: str,
                       resolve: Optional[Callable[[str], str]] = None, validate_kind: bool = True) -> str:
    """Bind an already separated resource path; never split typed '?' filenames.

    Only declared URI resources opt in. An existing raw literal percent path
    wins over an existing decoded path. Decode once only when raw does not exist;
    encoded question marks and commas then work without reinterpreting old paths.
    Malformed percent escapes retain their literal spelling. Invalid encoded UTF-8
    and NUL reject the resource; permission/I/O failures propagate, never selecting
    a different file. The caller uses this path for validation, walking and scope.
    """
    if transport not in ('typed', 'uri'):
        raise ValueError(f'Unknown resource transport {transport!r}')
    default = spec.cli_default if transport == 'typed' else spec.uri_default
    value = str(path if path else default or '')
    if not value and spec.required:
        raise RequestValidationError(f'{spec.name} is required')
    if '\x00' in value:
        raise RequestValidationError('Resource path must not contain NUL')
    if transport == 'typed' or spec.uri_codec == 'raw':
        return _validate_resource_kind(spec, value, resolve, validate_kind)
    if spec.uri_codec != 'existing-path-first':
        raise ValueError(f'Unknown resource URI codec {spec.uri_codec!r}')
    if _resource_exists_at(value, resolve):
        return _validate_resource_kind(spec, value, resolve, validate_kind)
    try:
        decoded = unquote(value, encoding='utf-8', errors='strict')
    except UnicodeDecodeError as exc:
        raise RequestValidationError('Resource path contains invalid UTF-8 percent encoding') from exc
    chosen = decoded if _resource_exists_at(decoded, resolve) else value
    return _validate_resource_kind(spec, chosen, resolve, validate_kind)


def _validate_resource_kind(spec: ResourceSpec, value: str,
                            resolve: Optional[Callable[[str], str]], validate: bool = True) -> str:
    if spec.kind is None or not validate:
        return value
    target = resolve(value) if resolve else value
    mode = Path(target).expanduser().stat().st_mode
    matches = {'directory': stat.S_ISDIR, 'file': stat.S_ISREG}
    if spec.kind not in matches:
        raise ValueError(f'Unknown resource kind {spec.kind!r}')
    if not matches[spec.kind](mode):
        raise RequestValidationError(f'{spec.name} must be a {spec.kind}: {value}')
    return value
