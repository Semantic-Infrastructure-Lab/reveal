"""Declared CLI/URI binding; legacy raw queries and exclusion/filter codecs stay separate."""

import argparse
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Union
from urllib.parse import quote, unquote

from .query_parser import ParamSpec, QueryParams, ResourceSpec, parse_query_params, peek_query_items


def boolean_value(value: Any) -> bool:
    """Bare presence and explicit true/false are distinct; reject other spellings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ('true', 'false', 'yes', 'no', '1', '0'):
        return value.lower() in ('true', 'yes', '1')
    raise ValueError('expected true or false')


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


def _source_params(declarations: tuple[ParamSpec, ...],
                   source: Union[str, Mapping[str, Any]], transport: str) -> QueryParams:
    if transport == 'uri':
        if not isinstance(source, str):
            raise TypeError('URI parameters must be a raw query string')
        return parse_query_params(source)
    if transport != 'typed':
        raise ValueError(f'Unknown parameter transport {transport!r}')
    if isinstance(source, str):
        raise TypeError('Typed parameters must be a mapping')
    supplied = dict(peek_query_items(source))
    params = QueryParams()
    for spec in declarations:
        destination = spec.cli.dest if spec.cli and spec.cli.dest else spec.name
        if destination in supplied:
            params[spec.name] = supplied[destination]
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
    return spec.validate(decoded)


def bind_declared_params(specs: Iterable[ParamSpec], source: Union[str, Mapping[str, Any]],
                         *, transport: str) -> QueryParams:
    """Validate supplied values without consuming them; conversion/decoding occurs once.

    CLI binding preserves original typed values. URI parsing retains legacy
    trimming/last-wins/presence rules and decodes only explicitly opted-in keys.
    Omitted controls remain omitted, so defaults do not become submitted flags.
    """
    declarations = tuple(specs)
    params = _source_params(declarations, source, transport)
    supplied = dict(peek_query_items(params))
    for spec in declarations:
        if spec.name not in supplied:
            if spec.required:
                raise ValueError(f'{spec.name} is required')
            continue
        value = _validate_binding(spec, supplied[spec.name], transport)
        params[spec.name] = value
        params._normalized[spec.name] = (spec, value)
    return params


def add_declared_arguments(parser: argparse.ArgumentParser, specs: Iterable[ParamSpec],
                           resource: ResourceSpec) -> None:
    """Generate local arguments; global presentation/exclusion owners remain unchanged."""
    parser.add_argument(resource.name, nargs=None if resource.required else '?',
                        default=resource.cli_default)
    for spec in specs:
        cli = spec.cli
        if cli is None:
            continue
        options: Dict[str, Any] = {'dest': cli.dest or spec.name, 'default': argparse.SUPPRESS,
                                   'required': cli.required, 'help': spec.description}
        if cli.action is not None:
            options['action'] = cli.action
        else:
            if cli.nargs is not None:
                options['nargs'] = cli.nargs
            if cli.metavar is not None:
                options['metavar'] = cli.metavar
        parser.add_argument(*cli.flags, **options)


def _resource_exists(path: str) -> bool:
    if '\x00' in path:
        raise ValueError('Resource path must not contain NUL')
    try:
        Path(path).expanduser().stat()
    except (FileNotFoundError, NotADirectoryError):
        return False
    return True


def bind_resource_path(spec: ResourceSpec, path: str, *, transport: str) -> str:
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
        raise ValueError(f'{spec.name} is required')
    if '\x00' in value:
        raise ValueError('Resource path must not contain NUL')
    if transport == 'typed' or spec.uri_codec == 'raw':
        return value
    if spec.uri_codec != 'existing-path-first':
        raise ValueError(f'Unknown resource URI codec {spec.uri_codec!r}')
    if _resource_exists(value):
        return value
    decoded = unquote(value, encoding='utf-8', errors='strict')
    return decoded if _resource_exists(decoded) else value
