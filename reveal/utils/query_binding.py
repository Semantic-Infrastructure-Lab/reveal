"""Declared CLI/URI binding; legacy raw queries and exclusion/filter codecs stay separate."""

import argparse
import stat
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Union
from urllib.parse import quote, unquote

from ..errors import RequestValidationError
from .query_parser import ParamSpec, QueryParams, ResourceSpec, parse_query_params, peek_query_items


def boolean_value(value: Any) -> bool:
    """Bare presence and explicit true/false are distinct; reject other spellings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ('true', 'false', 'yes', 'no', '1', '0'):
        return value.lower() in ('true', 'yes', '1')
    raise ValueError('expected true or false')


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


def _normalize_aliases(declarations: Iterable[ParamSpec], supplied: Mapping[str, Any]) -> Dict[str, Any]:
    """Every spelling of a control has one value owner; mixed spellings cannot hide precedence. A legacy
    spelling's value is translated into the control's own (``rank=fan-in`` is ``sort=-fan-in``)."""
    result = dict(peek_query_items(supplied))
    for spec in declarations:
        present = [name for name in spec.spellings if name in result]
        if not present:
            continue
        values = [spec.canonical_value(name, result.pop(name)) for name in present]
        if not _spellings_agree(spec, values):
            raise ValueError(f'{spec.name}: conflicting spellings: ' + ', '.join(present))
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
        if spec.role == 'filter-expression':
            continue
        values = [_decode_value(spec, value) if separator else True
                  for key, separator, value in parts if key in spec.spellings]
        if values:
            for name in spec.spellings:
                dict.pop(params, name, None)
            params[spec.name] = values


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


def _prepare_expression_params(declarations, source, params, selectors, expression) -> None:
    known = {name for spec in declarations for name in spec.spellings}
    terms = []
    for index, part in enumerate(source.split('&')):
        if index == 0 and selectors:
            continue
        key, separator, value = part.strip().partition('=')
        if key == expression.name and separator:
            terms.append(unquote(value, encoding='utf-8', errors='strict'))
        elif key and key not in known:
            terms.append(part.strip())
            dict.pop(params, key, None)
    if terms:
        params[expression.name] = terms


def _prepare_uri_params(declarations: tuple[ParamSpec, ...], source: str) -> QueryParams:
    """A declared expression-list owns the remaining raw DSL, including repeated bounds.

    Explicit where= values decode once; legacy expressions retain their existing codec.
    The domain's existing expression parser still owns their syntax and evaluation.
    """
    params = parse_query_params(source)
    _prepare_repeated_params(declarations, source, params)
    selectors = _prepare_legacy_selectors(declarations, source, params)
    expression = next((spec for spec in declarations if spec.role == 'filter-expression'), None)
    if expression is not None:
        _prepare_expression_params(declarations, source, params, selectors, expression)
    prepared = QueryParams(_normalize_aliases(declarations, params))
    prepared._aliases = {spec.name: spec.spellings[1:] for spec in declarations}
    prepared._selectors = selectors
    prepared._source_query = source
    prepared._supplied_aliases = {alias for spec in declarations for alias in spec.spellings[1:]
                                  if alias in dict.keys(params)}
    for name, selector in selectors.items():
        prepared._aliases[name] += (selector,)
    return prepared


def prepare_declared_params(declarations: Iterable[ParamSpec],
                   source: Union[str, Mapping[str, Any]], transport: str) -> QueryParams:
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
    supplied = _normalize_aliases(declarations, source)
    params = QueryParams()
    params._aliases = {spec.name: spec.spellings[1:] for spec in declarations}
    params._supplied_aliases = {alias for spec in declarations for alias in spec.spellings[1:] if alias in source}
    for spec in declarations:
        destination = spec.cli.dest if spec.cli and spec.cli.dest else spec.name
        if destination in supplied:
            params[spec.name] = supplied[destination]
        elif spec.name in supplied:
            params[spec.name] = supplied[spec.name]
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
    return apply_declared_overrides(declarations, params, overrides)


def _unsupported_override_message(declarations: Iterable[ParamSpec], unknown: list[str]) -> str:
    message = 'Unsupported declared parameter override(s): ' + ', '.join(repr(key) for key in unknown)
    symbol = next((spec.name for spec in declarations
                   if spec.names == 'symbol' and spec.role == 'operation'), None)
    if symbol is not None:
        message += f'. Use {symbol}=NAME for a supported per-symbol lookup; no equivalent filter is implied.'
    return message


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
            raise TypeError(_unsupported_override_message(declarations, unknown))
        from .query_parser import query_key_recorder
        query_key_recorder(*supplied)
        params._overrides.update(supplied)
        for spec in declarations:
            if spec.name in supplied:
                raw = supplied[spec.name]
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

    def __init__(self, *args, translate=None, comparable=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.translate = translate
        self.comparable = comparable or (lambda value: value)

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
        # What this option saw in this parse, kept on the action (a namespace attribute would read as a flag).
        seen = self.__dict__.get('_seen')
        if seen is None or seen[0] is not namespace:
            seen = self._seen = (namespace, {})
        previous = seen[1]
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
        options: Dict[str, Any] = {'dest': cli.dest or spec.name, 'default': argparse.SUPPRESS,
                                   'required': cli.required, 'help': spec.description}
        if spec.cli_action is not None:
            options['action'] = spec.cli_action
        else:
            if cli.nargs != 0:
                options['action'] = ScalarOnceAction
                options['translate'] = spec.canonical_value
                options['comparable'] = spec.validate
            if cli.nargs is not None:
                options['nargs'] = cli.nargs
                if cli.nargs == '?':
                    options['const'] = cli.const
            if cli.metavar is not None:
                options['metavar'] = cli.metavar
        parser.add_argument(*spec.flags, **options)


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
