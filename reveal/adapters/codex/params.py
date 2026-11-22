"""Codex query controls, bound before SQLite and JSONL session reads."""
from dataclasses import replace

from ...utils.query_binding import (bind_declared_params, boolean_value, legacy_switch, runtime_controls,
                                    string_value)
from ...utils.query_parser import (CliBinding, LegacySpelling, ParamSpec, ParamValueError, legacy_check,
                                   legacy_slices, nonnegative_display_limit, where_param, whole_number)
from ...utils.time_window import time_window_param
from ...utils.match_terms import TermValue, empty_term_message

# The answers each control is read by (COMMAND_MODEL "Applicability", BACK-2656): the path or --view selects most
# answers (qualification.selected_type); search and match select the content search. The selectors search and view
# (role='operation') are judged against the path instead (qualification.selection_error). since/until bound a filtered
# or searched catalog only, so they also require one of the three.
_LIST, _SEARCH = 'codex_session_list', 'codex_content_search'
# A session's answers by the view that names them (rulings Q3, Q4): the path's views (codex://UUID/tools), and the last
# agent message, token rows and goal that only the legacy ?last/?tokens/?goal selected. Each is --view NAME; the
# resource keeps its path, and a path view with a different --view is two answers (qualification.session_view).
PATH_VIEWS = {'messages': 'codex_messages', 'tools': 'codex_tools', 'errors': 'codex_errors', 'shell': 'codex_shell',
              'workflow': 'codex_workflow', 'timeline': 'codex_timeline', 'digest': 'codex_digest',
              'exchanges': 'codex_exchanges'}
QUERY_VIEWS = {'last': 'codex_messages', 'tokens': 'codex_tokens', 'goal': 'codex_goal'}
SESSION_VIEWS = {'overview': 'codex_session_overview', **PATH_VIEWS, **QUERY_VIEWS}

_MATCHES = ParamSpec('matches', 'integer', 'Snippets kept per session by a content search (0 = all)',
                     3, whole_number, ('codex://sessions/?match=auth&matches=10',
                                       'codex://sessions/?match=auth&matches=0'),
                     minimum=0, zero_policy='all', answers=(_SEARCH,), cli=CliBinding(('--matches',)))


def _session_substring(value):
    """Legacy ``filter=TEXT`` is ``where=session~=TEXT`` (ruling Q2, the Claude precedent): the same case-insensitive
    substring of the title or first user message."""
    return f'session~={string_value(value)}'


def _session_terms(value):
    """Codex's where terms: ``session~=TEXT`` only (the closed field ``session``). A term with no text is an empty term
    (COMMAND_MODEL "Empty match term", BACK-2736): ``?filter=`` is ``session~=``, so both exit 2 alike."""
    terms = [value] if isinstance(value, str) else value
    if not isinstance(terms, (list, tuple)) or any(not isinstance(term, str) for term in terms):
        raise ParamValueError('where requires session~=TEXT expressions')
    for term in terms:
        field, operator, text = term.partition('~=')
        if field.strip() != 'session' or not operator:
            raise ParamValueError('where supports session~=TEXT: a case-insensitive substring of the title or first '
                                  'user message')
        if not text.strip():
            raise ParamValueError(empty_term_message('session~=', "--where 'session~=TEXT'"))
    return list(terms)


def _terms(value):
    """Match terms: one string, or every repeat of a repeated match (rule 19), each a string."""
    return [string_value(item) for item in value] if isinstance(value, (list, tuple)) else [string_value(value)]


def _view_word(name):
    """Legacy ``?NAME`` (``last``, ``tokens``, ``goal``) is ``view=NAME`` (ruling Q4): bare, empty or a true spelling
    selects it; a typed False restores omission (BACK-2701). A false or malformed value
    used to select the answer as well; it now exits 2 naming the view (D18: unsupported spellings reject now)."""
    def codec(value):
        if value is False:
            return None
        if value is True or value == '':
            return name
        try:
            selects = boolean_value(value)
        except ValueError:
            selects = False
        if selects:
            return name
        raise ParamValueError(f'{name}={value!r} does not select an answer: use --view {name}')
    return codec


# The legacy words (filter, search, full, last, tokens, goal) are URI spellings only, with no flag: `reveal codex` never
# shipped them, so a flag would be born deprecated, and a --search flag would make ?search='s request note recommend a
# retiring spelling (COMMAND_MODEL "Retirement notes"). Each URI word keeps its param:codex row naming the canonical flag.
SEARCH = ParamSpec('search', 'string',
                   'Deprecated compatibility control; full-text search across session JSONL user_message and '
                   'agent_message payloads (its JSON query is the string given)', None,
                   TermValue('search', '--match TEXT'), role='operation')
# match is read by the content search it selects, not beside a legacy search (that answer reads search's own term).
MATCH = ParamSpec('match', 'array', 'Match text in session content (user and agent messages) on the catalog; repeat '
                  'to require every term in each session', None, _terms, uri_codec='percent', repeatable=True,
                  cli=CliBinding(('--match',)), answers=(f'{_SEARCH}+default',))
WHERE = replace(where_param('Session predicates, ANDed: session~=TEXT, a case-insensitive substring of the title or '
                            'first user message in the SQLite session index (not content search). A bare URI key with '
                            'its operator (?session~=TEXT) is the same filter',
                            legacy=(LegacySpelling('filter', codec=_session_substring),),
                            convert=_session_terms, default=None, fields=('session',)), answers=(_LIST,))
_BOUNDS, _BOUNDED_BY = (_LIST, _SEARCH), ('where|search|match',)
SINCE, UNTIL = (  # Codex's time bounds (COMMAND_MODEL "Time window", BACK-2728)
    time_window_param(name, description, answers=_BOUNDS, requires=_BOUNDED_BY)
    for name, description in (
        ('since', 'Lower-bound date on session updated_at; filtered/search views only'),
        ('until', 'Upper-bound date on session updated_at, the whole day included; filtered/search views only')))
KEY = ParamSpec('key', 'string', 'Dot-path config key lookup, applied after secret masking', None, string_value,
                answers=('codex_config',), cli=CliBinding(('--key',)))
VIEW = ParamSpec('view', 'string', 'A session answer: ' + ', '.join(SESSION_VIEWS) + '; a path view (/tools) is '
                 'the same selection', None, string_value, choices=tuple(SESSION_VIEWS),
                 role='operation', cli=CliBinding(('--view',)),
                 legacy=tuple(LegacySpelling(name, codec=_view_word(name)) for name in QUERY_VIEWS))
DETAIL = ParamSpec('detail', 'string', 'For /exchanges: full shows complete prompts and answers in text output (JSON '
                   'already contains full text); normal shows previews', None, string_value, choices=('normal', 'full'),
                   cli=CliBinding(('--detail',)), answers=('codex_exchanges',),
                   legacy=(LegacySpelling('full', codec=legacy_switch('full', 'full', 'normal')),))
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
PARAM_SPECS = (WHERE, SEARCH, MATCH, SINCE, UNTIL, KEY, VIEW, DETAIL, _MATCHES, LIMIT, OFFSET,
               *legacy_slices(head=_PAGED, tail=_PAGED, range=_PAGED), legacy_check())


def bind_query(query, params):
    bound = bind_declared_params(PARAM_SPECS, query or '', transport='uri') if params is None else params
    runtime = runtime_controls(PARAM_SPECS, bound)
    for spec in PARAM_SPECS:
        if spec.name in dict.keys(runtime):
            runtime.set_normalized(spec, dict.__getitem__(runtime, spec.name))
    return runtime
