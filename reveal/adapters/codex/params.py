"""Existing Codex query controls, bound before SQLite and JSONL session reads."""
from ...utils.query_binding import (bind_declared_params, boolean_value, legacy_presence_value, runtime_controls,
                                    string_value)
from ...utils.query_parser import (CliBinding, ParamSpec, legacy_check, legacy_slices, nonnegative_display_limit,
                                   whole_number)

# The answers each control is read by (COMMAND_MODEL "Applicability", BACK-2656): the path selects most answers
# (qualification.selected_type); search selects the content search and last/tokens/goal a session's last message, token
# breakdown or goal (Q5: they keep their roles and name the answer they select). since/until bound a filtered or
# searched catalog only, so they also require one of the two.
_LIST, _SEARCH = 'codex_session_list', 'codex_content_search'
_MATCHES = ParamSpec('matches', 'integer', 'Snippets kept per session by ?search= (0 = all)',
                     3, whole_number, ('codex://sessions/?search=auth&matches=10', 'codex://sessions/?search=auth&matches=0'),
                     minimum=0, zero_policy='all', answers=(_SEARCH,), cli=CliBinding(('--matches',)))
_FULL = ParamSpec('full', 'boolean',
                  'For /exchanges: show complete prompts and answers in text output; JSON already contains full text',
                  False, boolean_value, ('codex://019e5cc5/exchanges?full', 'codex://019e5cc5/exchanges?full=false'),
                  answers=('codex_exchanges',), cli=CliBinding(('--full',), action='store_true'))
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
FILTER, SEARCH, SINCE, UNTIL, KEY = (
    ParamSpec(name, 'string', description, None, string_value, answers=answers, requires=requires,
              cli=CliBinding((f'--{name}',)))
    for name, (description, answers, requires) in _STRINGS.items())
# The selectors a session's answer is picked by, in the order the router honours them: each names the one answer it
# selects (``answers``), which the predictor reads.
SELECTING_FLAGS = LAST, TOKENS, GOAL = tuple(
    ParamSpec(name, 'flag', description, None, legacy_presence_value, answers=(selects,),
              cli=CliBinding((f'--{name}',), action='store_true'))
    for name, (description, selects) in _FLAGS.items())
# The answers that hold a list of rows (CodexAdapter.BUDGET_LIST_FIELD): the shared --limit/--offset page them, and the
# legacy --head/--tail/--range slice them (ruling Q6; COMMAND_MODEL Caps: --limit 0 is uncapped).
PAGE_FIELDS = {
    'codex_session_list': 'sessions', 'codex_content_search': 'sessions', 'codex_history': 'entries',
    'codex_memories': 'memories', 'codex_rules': 'rules', 'codex_skills': 'skills', 'codex_plugins': 'plugins',
    'codex_messages': 'messages', 'codex_tools': 'tools', 'codex_errors': 'errors', 'codex_workflow': 'events',
    'codex_timeline': 'events', 'codex_exchanges': 'exchanges', 'codex_tokens': 'token_turns',
}
_PAGED = tuple(PAGE_FIELDS)
LIMIT = ParamSpec('limit', 'integer', 'Answer rows of a list answer; zero is uncapped; source/input budgets are unchanged',
                  None, lambda value: nonnegative_display_limit(value, name='limit'), minimum=0,
                  zero_policy='uncapped', cli=CliBinding(('--limit',)), answers=_PAGED)
OFFSET = ParamSpec('offset', 'integer', 'Answer rows of a list answer skipped before --limit', None,
                   lambda value: nonnegative_display_limit(value, name='offset'), minimum=0,
                   cli=CliBinding(('--offset',)), answers=_PAGED)
# --head/--tail/--range slice the rows of every list answer today, after the URI or on the subcommand: flag-only legacy
# modifiers until the cut (their notes are the flag:codex.<flag> rows); --check/--lint never changed an answer.
PARAM_SPECS = (FILTER, SEARCH, SINCE, UNTIL, KEY, *SELECTING_FLAGS, _MATCHES, _FULL, LIMIT, OFFSET,
               *legacy_slices(head=_PAGED, tail=_PAGED, range=_PAGED), legacy_check())


def bind_query(query, params):
    bound = bind_declared_params(PARAM_SPECS, query or '', transport='uri') if params is None else params
    runtime = runtime_controls(PARAM_SPECS, bound)
    for spec in PARAM_SPECS:
        if spec.name in dict.keys(runtime):
            runtime.set_normalized(spec, dict.__getitem__(runtime, spec.name))
    return runtime
