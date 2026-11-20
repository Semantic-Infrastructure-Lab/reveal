"""Bind existing Claude query controls before session reading; no new analysis engine."""
from dataclasses import replace
from typing import Any, Callable

from ...utils.query_binding import bind_declared_params, legacy_presence_value as presence, string_value as text
from ...utils.query_parser import CliBinding, LegacySpelling, ParamSpec, ParamValueError, QueryParams, where_param, peek_query_items, nonnegative_display_limit, nonempty_scalar, legacy_slices
from .schema import _SCHEMA_QUERY_PARAMS
from .resources import SESSION_VIEW_NAMES
from .pagination import PAGE_SPECS
from .controls import LEVELLED_TYPES


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
        raise ParamValueError('where requires session~=TEXT expressions')
    for term in terms:
        if not term:
            continue
        session = term.partition('~=')
        tool = term.partition('==')
        if session[0].strip() == 'session' and session[1]:
            continue
        if tool[0].strip() == 'tool' and tool[1] and tool[2]:
            continue
        raise ParamValueError('where supports session~=TEXT on catalogs or tool==NAME on workflows')
    return [term for term in terms if term]


def _last_count(value):
    """Legacy ``last`` is tail's other spelling: ``last=N`` is ``tail=N``, and bare ``last`` or ``last=0`` is one turn."""
    count = 1 if value is True or value == '' else int(value)
    return str(count or 1)


def _session_substring(value):
    """Legacy ``filter=TEXT`` is ``where=session~=TEXT``: the same case-insensitive session-name substring."""
    return f'session~={text(value)}'


def _terms(value):
    """Match terms: one string, or every repeat of a repeated match (rule 19), each a string."""
    return [text(item) for item in value] if isinstance(value, (list, tuple)) else [text(value)]


# The answers that read each control (COMMAND_MODEL "Applicability", BACK-2656): the predicted result type of the path
# and its selectors, with ``+default`` or ``+view=messages`` where tail's slice answers the same type without reading
# it. The selectors keep their roles and name the answer they select (Scott 2026-11-18, Q5); tools and errors combine
# into the filtered results. A control given to any other answer is refused before analysis.
_MESSAGES = ('claude_messages+default', 'claude_messages+view=messages')  # /messages and view=messages, not tail
_CATALOGS = ('claude_session_list', 'claude_cross_session_search')
ANSWERS = {
    'errors': ('claude_errors', 'claude_filtered_results'),
    'tools': ('claude_tool_calls', 'claude_filtered_results'),
    'tokens': ('claude_token_breakdown',), 'digest': ('claude_digest',), 'timeline': ('claude_timeline',),
    'contains': (*_MESSAGES, 'claude_filtered_results'),
    'since': (*_CATALOGS, 'claude_file_sessions', 'claude_history'), 'until': _CATALOGS,
    'word': ('claude_cross_session_search',), 'snippet': ('claude_cross_session_search',),
    'project': ('claude_history',), 'key': ('claude_settings', 'claude_config'), 'patches': ('claude_files',),
    'full': ('claude_exchanges', 'claude_message_range', 'claude_assistant_messages'),
    'raw': ('claude_user_messages', 'claude_assistant_messages'),
    # the answers with detail levels, the analytics and raw role records a level selects among them
    'detail': tuple(sorted(LEVELLED_TYPES)),
    'where': ('claude_session_list', 'claude_workflow'),
    # the reader match reaches on each resource: a search, the narrative turns, the tool results or the workflow rows
    'match': (*_CATALOGS[1:], 'claude_history', 'claude_memory', 'claude_plans', 'claude_agents',
              'claude_search_results', *_MESSAGES, 'claude_filtered_results', 'claude_workflow'),
}
PAGE_ANSWERS = (*(kind for kind in PAGE_SPECS if kind != 'claude_messages'), *_MESSAGES)


def _spec(name, schema):
    convert: Callable[[Any], Any] = text
    if name in PRESENCE_FLAGS:
        convert = presence
    elif name == 'patches':
        convert = patches
    elif name == 'tail':
        convert = int
    elif name == 'snippet':
        convert = snippet
    kind = 'integer' if name == 'tail' else schema['type']
    retired = {'summary', 'search', 'contains', 'tail', 'full', 'raw'}
    cli = None if name in retired else CliBinding(('--' + name,), action='store_true' if kind == 'flag' else None)
    description = ('Deprecated compatibility control; ' if name in retired else '') + schema['description']
    # tail, search and summary answer differently from any canonical request (a chronological slice; a session-wide
    # search or the overview analytics in place of the path's view): legacy operations that select the answer, last
    # being tail's other spelling (COMMAND_MODEL "Legacy operations", BACK-2654 notes #9 and #12). contains, full and
    # raw are standalone too, but filter or detail the answer: no role.
    role = 'operation' if name in ('tail', 'search', 'summary') else None
    legacy = (LegacySpelling('last', codec=_last_count),) if name == 'tail' else ()
    return ParamSpec(name, kind, description, None, convert,
                     examples=tuple(schema.get('examples', ())), cli=cli, role=role, legacy=legacy,
                     answers=ANSWERS.get(name, ()))


PARAM_SPECS = tuple(_spec(name, schema) for name, schema in _SCHEMA_QUERY_PARAMS.items()) + (
    ParamSpec('limit', 'integer', 'Answer rows; zero is uncapped; source/input budgets are unchanged', None,
              lambda value: nonnegative_display_limit(value, name='limit'), minimum=0, zero_policy='uncapped', cli=CliBinding(('--limit',)),
              answers=PAGE_ANSWERS),
    ParamSpec('offset', 'integer', 'Answer rows skipped after sorting', None,
              lambda value: nonnegative_display_limit(value, name='offset'), minimum=0, cli=CliBinding(('--offset',)),
              answers=PAGE_ANSWERS),
    ParamSpec('sort', 'string', 'Answer row field; prefix - for descending; supported fields depend on the selected reader', None, nonempty_scalar, cli=CliBinding(('--sort',)),
              answers=PAGE_ANSWERS),
    # The shared where declaration with Claude's evaluator (rule 13): a bare ?session~=TEXT is the same filter.
    replace(where_param('Reader-specific predicates, ANDed: catalog session~=TEXT substrings or workflow tool==NAME '
                        'exact equality; case-insensitive. A bare URI key with its operator (?session~=TEXT) is the same '
                        'filter', legacy=(LegacySpelling('filter', codec=_session_substring),), convert=name_predicates,
                        default=None, fields=('session', 'tool')), answers=ANSWERS['where']),
    ParamSpec('timeline', 'flag', 'Chronological message timeline (legacy query selector)', None, presence, cli=CliBinding(('--timeline',), action='store_true'),
              answers=ANSWERS['timeline']),
    ParamSpec('detail', 'string', 'summary, normal, full or raw; levels are qualified by the existing reader', None, text, choices=('summary', 'normal', 'full', 'raw'), cli=CliBinding(('--detail',)),
              answers=ANSWERS['detail']),
    ParamSpec('view', 'string', 'Existing session answer: ' + ', '.join(SESSION_VIEW_NAMES), None, text, choices=SESSION_VIEW_NAMES, role='operation', cli=CliBinding(('--view',))),
    ParamSpec('match', 'array', 'Match text in this resource: session content, narrative messages, tool results, workflow tool/detail text, cross-session content, workspace lists or history; repeat to require every term in each row (a message, turn, tool result, entry, session, file or workflow row); unsupported views reject',
              None, _terms, uri_codec='percent', repeatable=True, cli=CliBinding(('--match',)), answers=ANSWERS['match']),
)
# --head/--tail/--range slice this noun's rows today: flag-only legacy modifiers until the cut, read by the answers named
# (BACK-2673; their notes are the flag:<noun>.<flag> RETIREMENTS rows).
PARAM_SPECS = (*PARAM_SPECS, *legacy_slices(
    head=('claude_workflow', 'claude_session_list', 'claude_messages', 'claude_message_range',
          'claude_cross_session_search', 'claude_history', 'claude_filtered_results'),
    range=('claude_workflow', 'claude_messages', 'claude_message_range', 'claude_filtered_results')))


def translate_request(query, params, resource=''):
    """The resource and the runtime controls a request selects, before Claude's own request checks: a view becomes
    its path, a detail level its legacy control, match the reader's search, contains or match. The answer predictor
    reads this, so a request the checks will refuse still names the answer it selects."""
    bound = bind_declared_params(PARAM_SPECS, query or '', transport='uri') if params is None else params
    # Presence readers must not mistake an explicit False/None override for a flag.
    runtime = QueryParams({key: value for key, value in peek_query_items(bound)
                           if value is not None and not (key in PRESENCE_FLAGS and value is False)})
    runtime._aliases = dict(getattr(bound, '_aliases', {}))  # reading where reads legacy filter (last: tail)
    folded = tuple(getattr(bound, '_folded', ()))
    if folded:  # and a bare ?session~=TEXT folded into it
        runtime._aliases['where'] = (*runtime._aliases.get('where', ()), *folded)
    from .controls import apply_view, apply_detail, apply_match
    resource = apply_view(runtime, resource)
    apply_detail(runtime, resource)
    apply_match(runtime, resource)
    return resource, runtime


def bind_request(query, params, resource=''):
    """Translate the request, then Claude's checks that are not applicability (each control's declared ``answers``
    is, judged by the shared check before construction): an operation on a resource it cannot answer, a where term
    naming another answer's field, a sort field or ``key``'s single value on a page request."""
    resource, runtime = translate_request(query, params, resource)
    from .controls import validate_where_scope, validate_selectors
    from .pagination import validate_page_scope
    validate_selectors(runtime, resource)
    validate_where_scope(runtime, resource)
    validate_page_scope(runtime, resource)
    for spec in PARAM_SPECS:
        if spec.name in dict.keys(runtime):
            runtime.set_normalized(spec, dict.__getitem__(runtime, spec.name))
    return resource, runtime


def bind_query(query, params, resource=''):
    """Compatibility entry point for callers that only need the runtime parameters."""
    return bind_request(query, params, resource)[1]
