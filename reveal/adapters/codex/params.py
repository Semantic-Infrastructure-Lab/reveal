"""Existing Codex query controls, bound before SQLite and JSONL session reads."""
from ...utils.query_binding import (bind_declared_params, boolean_value, legacy_presence_value, runtime_controls,
                                    string_value)
from ...utils.query_parser import ParamSpec, whole_number

# The answers each control is read by (COMMAND_MODEL "Applicability", BACK-2656): the path selects most answers
# (qualification.selected_type); search selects the content search and last/tokens/goal a session's last message, token
# breakdown or goal (Q5: they keep their roles and name the answer they select). since/until bound a filtered or
# searched catalog only, so they also require one of the two.
_LIST, _SEARCH = 'codex_session_list', 'codex_content_search'
_MATCHES = ParamSpec('matches', 'integer', 'Snippets kept per session by ?search= (0 = all)',
                     3, whole_number, ('codex://sessions/?search=auth&matches=10', 'codex://sessions/?search=auth&matches=0'),
                     minimum=0, zero_policy='all', answers=(_SEARCH,))
_FULL = ParamSpec('full', 'boolean',
                  'For /exchanges: show complete prompts and answers in text output; JSON already contains full text',
                  False, boolean_value, ('codex://019e5cc5/exchanges?full', 'codex://019e5cc5/exchanges?full=false'),
                  answers=('codex_exchanges',))
_BOUNDS = (_LIST, _SEARCH)
_STRINGS = {  # name -> (description, the answers that read it, the controls it requires)
    'filter': ('Metadata filter by title/first-message substring in the SQLite session index; not content search',
               (_LIST,), ()),
    'search': ('Full-text search across session JSONL user_message and agent_message payloads', (_SEARCH,), ()),
    'since': ('Lower-bound date on session updated_at (ISO 8601 or today); filtered/search views only', _BOUNDS,
              ('filter|search',)),
    'until': ('Upper-bound date on session updated_at (ISO 8601); filtered/search views only', _BOUNDS,
              ('filter|search',)),
    'key': ('Dot-path config key lookup, applied after secret masking', ('codex_config',), ()),
}
_FLAGS = {
    'last': ('Last agent message in the selected session; not session-list pagination', 'codex_messages'),
    'tokens': ('Per-request token breakdown, one row per API call', 'codex_tokens'),
    'goal': ('Selected thread goal objective and token budget from goals_1.sqlite', 'codex_goal'),
}
PARAM_SPECS = (
    *(ParamSpec(name, 'string', description, None, string_value, answers=answers, requires=requires)
      for name, (description, answers, requires) in _STRINGS.items()),
    *(ParamSpec(name, 'flag', description, None, legacy_presence_value, answers=(selects,))
      for name, (description, selects) in _FLAGS.items()),
    _MATCHES, _FULL,
)


def bind_query(query, params):
    bound = bind_declared_params(PARAM_SPECS, query or '', transport='uri') if params is None else params
    runtime = runtime_controls(PARAM_SPECS, bound)
    for spec in PARAM_SPECS:
        if spec.name in dict.keys(runtime):
            runtime.set_normalized(spec, dict.__getitem__(runtime, spec.name))
    return runtime
