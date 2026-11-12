"""Bind existing Claude query controls before session reading; no new analysis engine."""
from typing import Any, Callable

from ...utils.query_binding import bind_declared_params, legacy_presence_value as presence, string_value as text
from ...utils.query_parser import CliBinding, ParamSpec, QueryParams, peek_query_items, nonnegative_display_limit, nonempty_scalar
from .schema import _SCHEMA_QUERY_PARAMS
from .resources import SESSION_VIEW_NAMES


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


def name_predicates(value):
    terms = [value] if isinstance(value, str) else value
    if not isinstance(terms, (list, tuple)) or any(not isinstance(term, str) for term in terms):
        raise ValueError('where requires session~=TEXT expressions')
    for term in terms:
        field, separator, _ = term.partition('~=')
        if term and (field.strip() != 'session' or not separator):
            raise ValueError('where supports only session~=TEXT (case-insensitive literal substring)')
    return [term for term in terms if term]


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
    ParamSpec('limit', 'integer', 'Answer rows; zero is uncapped; source/input budgets are unchanged', None,
              lambda value: nonnegative_display_limit(value, name='limit'), minimum=0, zero_policy='uncapped'),
    ParamSpec('offset', 'integer', 'Answer rows skipped after sorting', None,
              lambda value: nonnegative_display_limit(value, name='offset'), minimum=0),
    ParamSpec('sort', 'string', 'Answer row field; prefix - for descending; supported fields depend on the selected reader', None, nonempty_scalar),
    ParamSpec('where', 'array', 'Session catalog names only: repeat session~=TEXT for case-insensitive literal substring constraints, ANDed',
              None, name_predicates, uri_codec='percent', role='name-predicate',
              cli=CliBinding(('--where',), action='append')),
    ParamSpec('timeline', 'flag', 'Chronological message timeline (legacy query selector)', None, presence),
    ParamSpec('detail', 'string', 'summary, normal, full or raw; levels are qualified by the existing reader', None, text, choices=('summary', 'normal', 'full', 'raw')),
    ParamSpec('view', 'string', 'Existing session answer: ' + ', '.join(SESSION_VIEW_NAMES), None, text, choices=SESSION_VIEW_NAMES),
    ParamSpec('match', 'string', 'Match text in this resource: session content, narrative messages, tool results, cross-session content, workspace lists or history; unsupported views reject',
              None, text, uri_codec='percent'),
)


def bind_request(query, params, resource=''):
    bound = bind_declared_params(PARAM_SPECS, query or '', transport='uri') if params is None else params
    # Presence readers must not mistake an explicit False/None override for a flag.
    runtime = QueryParams({key: value for key, value in peek_query_items(bound)
                           if value is not None and not (key in PRESENCE_FLAGS and value is False)})
    from .controls import apply_view, apply_detail, apply_match, validate_where_scope
    resource = apply_view(runtime, resource)
    apply_detail(runtime, resource)
    apply_match(runtime, resource)
    validate_where_scope(runtime, resource)
    from .pagination import validate_page_scope
    validate_page_scope(runtime, resource)
    for spec in PARAM_SPECS:
        if spec.name in dict.keys(runtime):
            runtime.set_normalized(spec, dict.__getitem__(runtime, spec.name))
    return resource, runtime


def bind_query(query, params, resource=''):
    """Compatibility entry point for callers that only need the runtime parameters."""
    return bind_request(query, params, resource)[1]
