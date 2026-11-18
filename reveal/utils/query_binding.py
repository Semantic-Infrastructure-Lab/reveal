"""Declared CLI/URI binding; legacy raw queries and exclusion/filter codecs stay separate."""

import argparse
import re
import stat
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Union
from urllib.parse import quote, unquote

from ..errors import RequestValidationError, UnsupportedOverrideError
from .query_parser import (SHARED_CONTROL_NAMES, LegacySpelling, ParamSpec, ParamValueError, QueryParams, ResourceSpec,
                           mark_query_keys, parse_query_params, peek_query_items, query_key)


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
    """``?limit=1&limit=2``: one setting, two values (COMMAND_MODEL "Conflicting values"); equal values are one."""
    for name in spec.spellings:
        values = list(dict.fromkeys(value if separator else True for key, separator, value in parts if key == name))
        if len(values) > 1:
            raise RequestValidationError(f'{name} is given twice with different values ({values[0]} and {values[1]}): '
                                         'a setting takes one value; give it once')


def _prepare_legacy_selectors(declarations: tuple[ParamSpec, ...], source: str, params: QueryParams) -> Dict[str, str]:
    """Opted-in first bare words select views; field=value remains dataset syntax."""
    first = source.partition('&')[0].lower()
    selected = {}
    for spec in declarations:
        if first not in spec.first_selectors:
            continue
        if spec.name in params:
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
        elif key and key not in known:
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
    controls = ', '.join(spec.name for spec in declarations) or '(none)'
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
    return {key for spec in declarations for key in (*spec.spellings, *(entry.name for entry in spec.legacy))}


# The walk policy every transport splits off before binding (split_respect_gitignore); an adapter built directly
# receives it from its own CLI_QUERY_FLAGS fragment, which it accepts by definition (BACK-1361).
_TRANSPORT_KEYS = frozenset({'respect_gitignore'})
# A where term's field ends at its operator; a dotted path (lines.total) stays whole.
_FIELD_END = re.compile(r'[=<>!~]')


def _declared_field(key: str, fields: tuple) -> bool:
    """A field the noun declares, or a dotted path under a declared field or a declared record section (``lines.*``)."""
    head = key.split('.', 1)[0]
    return key in fields or ('.' in key and (head in fields or f'{head}.*' in fields))


def _where_fields(params: QueryParams, expression: ParamSpec) -> list:
    """The field of every where term, written explicitly or folded from a bare key."""
    terms = params.get(expression.name) or ()  # a decoded where= value may hold a literal '&': one term, one field
    fields = (_FIELD_END.split(str(term).strip().lstrip('!'), 1)[0].strip() for term in terms)
    return [field for field in fields if field]


def _reject_unknown_keys(declarations: tuple[ParamSpec, ...], params: QueryParams, shared: tuple,
                         expression: Optional[ParamSpec]) -> None:
    """The one unknown-key check (rule 3): a key that is neither a declared control nor a declared field exits 2, and
    so does a bare key spelling a shared control the noun does not declare (rule 8; *shared*, never folded)."""
    known = _declared_keys(declarations) | _TRANSPORT_KEYS
    unknown = [*shared, *(key for key in dict.keys(params) if key not in known)]
    if expression is not None and expression.fields and not expression.open_fields:
        unknown += [key for key in _where_fields(params, expression) if not _declared_field(key, expression.fields)]
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
    prepared._source_query = source
    prepared._supplied_aliases = {alias for spec in declarations for alias in spec.spellings[1:]
                                  if alias in dict.keys(params)}
    prepared._given = set(dict.keys(prepared))
    for name, selector in selectors.items():
        prepared._aliases[name] += (selector,)
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


def _reads(spec: ParamSpec, facets: tuple) -> bool:
    return not spec.answers or bool(set(spec.answers).intersection(facets))


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
    scoped = [spec for spec in declarations if spec.answers and spec.role != 'operation' and spec.name in given]
    if not scoped:
        return
    facets = answer_facets(declarations, params, result_type())
    unread = [spec for spec in scoped if not _reads(spec, facets)]
    if unread:
        raise RequestValidationError(_unread_controls_message(declarations, unread, facets, params))


def _folded_terms(params: Mapping[str, Any], name: str) -> list:
    """The terms of control *name* that arrived as bare field keys (``?bogus=1`` folds into ``where``), as typed."""
    folded = set(getattr(params, '_folded', ()))
    value = dict(peek_query_items(params)).get(name)
    if not folded or not isinstance(value, list):
        return []
    parts = (part.strip() for part in (getattr(params, '_source_query', None) or '').split('&'))
    return [part for part in parts if part and query_key(part) in folded and part in value]


def _as_typed(params: Mapping[str, Any], name: str) -> str:
    """A control named canonically, followed by the bare field keys that spelled it (``'where' (bogus=1)``), so a
    disclosure names what the request said as well as the control it reached."""
    terms = _folded_terms(params, name)
    return f"'{name}'" + (f" ({', '.join(terms)})" if terms else '')


def _unread_controls_message(declarations: tuple, unread: list, facets: tuple, params: Mapping[str, Any]) -> str:
    """Named by the control, whatever spelling carried it: a URI key, a flag injected into the query (--limit can
    reach a URI as a legacy key) and a legacy flag all name one control; its retirement note names the old spelling.
    Bare field keys folded into the filter expression are named as typed beside it."""
    reads = ', '.join(spec.name for spec in declarations if spec.role != 'operation' and _reads(spec, facets))
    where = '; '.join(f"{spec.name} is read by: {', '.join(spec.answers)}" for spec in unread)
    several = len(unread) > 1
    return (f"control{'s' if several else ''} {', '.join(_as_typed(params, spec.name) for spec in unread)} "
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
        names = {spec.name for spec in declarations}
        unknown = [key for key in supplied if key not in names]
        if unknown:
            raise UnsupportedOverrideError(unsupported_controls_message(declarations, unknown))
        from .query_parser import query_key_recorder
        query_key_recorder(*supplied)
        params._overrides.update(supplied)
        for spec in declarations:
            if spec.name in supplied:
                raw = supplied[spec.name]
                (params._given.discard if raw is None else params._given.add)(spec.name)  # None: the default
                value = spec.validate(None) if raw is None else _validate_binding(spec, raw, 'typed')
                params.set_normalized(spec, value)
    return params


def bind_prepared_params(declarations: Iterable[ParamSpec], params: QueryParams, *,
                         transport: str) -> QueryParams:
    """Convert a prepared source once, after its operation identity is resolved."""
    supplied = dict(peek_query_items(params))
    for spec in declarations:
        if spec.name not in supplied:
            if spec.required:
                raise ValueError(f'{spec.name} is required')
            continue
        value = _validate_binding(spec, supplied[spec.name], transport)
        params.set_normalized(spec, value)
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


def add_declared_arguments(parser: argparse.ArgumentParser, specs: Iterable[ParamSpec],
                           resource: ResourceSpec) -> None:
    """Generate local arguments; global presentation/exclusion owners remain unchanged."""
    parser.add_argument(resource.name, nargs=None if resource.required else '?',
                        default=resource.cli_default)
    for spec in specs:
        _add_legacy_cli_arguments(parser, spec)
        cli = spec.cli
        if cli is None:
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
        parser.add_argument(*(flag for flag in spec.flags if flag not in separate), **options)
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
