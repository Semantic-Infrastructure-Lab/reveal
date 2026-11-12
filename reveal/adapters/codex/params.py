"""Existing Codex query controls, bound before SQLite and JSONL session reads."""
from ...utils.query_binding import bind_declared_params, boolean_value, legacy_presence_value, string_value
from ...utils.query_parser import ParamSpec, QueryParams, peek_query_items, whole_number

_MATCHES = ParamSpec('matches', 'integer', 'Snippets kept per session by ?search= (0 = all)',
                     3, whole_number, ('matches=10', 'matches=0'), minimum=0, zero_policy='all')
_FULL = ParamSpec('full', 'boolean',
                  'For /exchanges: show complete prompts and answers in text output; JSON already contains full text',
                  False, boolean_value, ('full', 'full=true', 'full=false'))
PRESENCE_FLAGS = frozenset(('last', 'tokens', 'goal'))
_STRINGS = {
    'filter': 'Metadata filter by title/first-message substring in the SQLite session index; not content search',
    'search': 'Full-text search across session JSONL user_message and agent_message payloads',
    'since': 'Lower-bound date on session updated_at (ISO 8601 or today); filtered/search views only',
    'until': 'Upper-bound date on session updated_at (ISO 8601); filtered/search views only',
    'key': 'Dot-path config key lookup, applied after secret masking',
}
_FLAGS = {
    'last': 'Last agent message in the selected session; not session-list pagination',
    'tokens': 'Per-request token breakdown, one row per API call',
    'goal': 'Selected thread goal objective and token budget from goals_1.sqlite',
}
PARAM_SPECS = (
    *(ParamSpec(name, 'string', description, None, string_value) for name, description in _STRINGS.items()),
    *(ParamSpec(name, 'flag', description, None, legacy_presence_value) for name, description in _FLAGS.items()),
    _MATCHES, _FULL,
)


def bind_query(query, params):
    bound = bind_declared_params(PARAM_SPECS, query or '', transport='uri') if params is None else params
    runtime = QueryParams({key: value for key, value in peek_query_items(bound)
                           if value is not None and not (key in PRESENCE_FLAGS and value is False)})
    for spec in PARAM_SPECS:
        if spec.name in dict.keys(runtime):
            runtime.set_normalized(spec, dict.__getitem__(runtime, spec.name))
    return runtime
