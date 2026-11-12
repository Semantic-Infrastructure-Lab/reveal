"""Bind existing Claude query controls before session reading; no new analysis engine."""
from typing import Any, Callable

from ...utils.query_binding import bind_declared_params, legacy_presence_value as presence, string_value as text
from ...utils.query_parser import ParamSpec, QueryParams, peek_query_items
from .schema import _SCHEMA_QUERY_PARAMS


PRESENCE_FLAGS = frozenset(('summary', 'errors', 'word', 'tokens', 'digest', 'full', 'raw', 'timeline'))


def patches(value):
    """The existing view enables patches only for the literal true spelling."""
    if isinstance(value, (bool, str)):
        return str(value).lower() == 'true'
    raise ValueError('expected a boolean or legacy string')


def snippet(value):
    """Retain the search owner's established fallback and 60–500 clamp."""
    try:
        return max(60, min(500, int(value)))
    except (ValueError, TypeError):
        return 120


def _spec(name, schema):
    convert: Callable[[Any], Any] = text
    if name in PRESENCE_FLAGS:
        convert = presence
    elif name == 'patches':
        convert = patches
    elif name in ('tail', 'last'):
        convert = int
    elif name == 'snippet':
        convert = snippet
    kind = 'integer' if name in ('tail', 'last') else schema['type']
    return ParamSpec(name, kind, schema['description'], None, convert,
                     examples=tuple(schema.get('examples', ())))


PARAM_SPECS = tuple(_spec(name, schema) for name, schema in _SCHEMA_QUERY_PARAMS.items()) + (
    ParamSpec('timeline', 'flag', 'Chronological message timeline (legacy query selector)', None, presence),
)


def bind_query(query, params):
    bound = bind_declared_params(PARAM_SPECS, query or '', transport='uri') if params is None else params
    # Presence readers must not mistake an explicit False/None override for a flag.
    runtime = QueryParams({key: value for key, value in peek_query_items(bound)
                           if value is not None and not (key in PRESENCE_FLAGS and value is False)})
    for spec in PARAM_SPECS:
        if spec.name in dict.keys(runtime):
            runtime.set_normalized(spec, dict.__getitem__(runtime, spec.name))
    return runtime
