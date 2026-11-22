"""Markdown controls bind directly; existing operations keep selection and source ownership."""
from typing import Any, Tuple

from ...utils.query_parser import (CliBinding, LegacySpelling, ParamSpec, ParamValueError, QueryParams, peek_query_items,
                                   legacy_slices)
from ...utils.query_binding import boolean_value
from ...utils.query import parse_query_filters
from ...utils.query_control import declared_result_control as result_control
from .query import parse_query


def strings(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, (list, tuple)) or any(not isinstance(item, str) for item in values):
        raise ValueError('expected strings')
    return [item for item in values if item]


def fields(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(',') if item.strip()]
    return strings(value)


def _selector(name: str, view: str):
    """A legacy selector switch (``?link-graph``, ``--lint``) as the view it stands for: true is that view, false is not
    given (the default listing)."""
    def codec(value: Any) -> Any:
        try:
            return view if boolean_value(value) else None
        except ValueError:
            raise ParamValueError(f'{name} must be a valid boolean, got {value!r}: use --view {view}') from None
    return codec


# The answers each control is read by (COMMAND_MODEL "Applicability", BACK-2656): the listing, the aggregate and lint read
# their own controls; the link graph and backlinks read none of these.
_LIST, _AGGREGATE, _LINT = 'markdown_query', 'markdown_aggregate', 'markdown_frontmatter_lint'
_FILTERED = (_LIST, _AGGREGATE)
WHERE = ParamSpec('where', 'array', 'Frontmatter expressions, ANDed; repeat for multiple constraints',
                  [], strings, role='filter-expression', repeatable=True, cli=CliBinding(('--where',)),
                  open_fields='any front matter key', answers=_FILTERED)
MATCH = ParamSpec('match', 'array', 'Body terms, ANDed; repeat to require multiple terms',
                  [], strings, legacy=(LegacySpelling('body-contains', flag='--body-contains'),), uri_codec='percent',
                  repeatable=True, cli=CliBinding(('--match',)), answers=_FILTERED)
VIEW = ParamSpec('view', 'string', 'Answer view: list, links, aggregate or lint', None, str,
                 choices=('list', 'links', 'aggregate', 'lint'), role='operation', cli=CliBinding(('--view',)),
                 legacy=(LegacySpelling('link-graph', codec=_selector('link-graph', 'links'), flag='--link-graph',
                                        flag_value=True),
                         LegacySpelling('lint', codec=_selector('lint', 'lint'), flag='--lint', flag_value=True)))
# aggregate=F is --view aggregate --field F: a legacy word of field that sets the view (ruling Q2-A).
FIELD = ParamSpec('field', 'string', 'Frontmatter field counted by the aggregate view', None, str,
                  legacy=(LegacySpelling('aggregate', codec=lambda raw: raw or None, flag='--aggregate',
                                         sets=(('view', 'aggregate'),)),),  # an empty value states nothing
                  cli=CliBinding(('--field',)), answers=(_AGGREGATE,))
# A backlinks target selects its own answer (COMMAND_MODEL "One answer per request"): beside a view it is two answers.
BACKLINKS = ParamSpec('backlinks', 'string', 'Reverse link target, relative to the scanned directory',
                      None, str, role='operation', cli=CliBinding(('--backlinks',)), uri_codec='percent')
LINT_FIELDS = ParamSpec('lint-fields', 'array', 'Required frontmatter fields for the lint view', None, fields,
                        aliases=('lint_fields',), cli=CliBinding(('--lint-fields',)), answers=(_LINT,))
FIELDS = ParamSpec('columns', 'array', 'Additional frontmatter fields displayed as listing columns', None, fields,
                   legacy=(LegacySpelling('fields'),), cli=CliBinding(('--columns',)), answers=(_LIST,))
EXPLAIN = ParamSpec('explain', 'boolean', 'Include per-term body relevance evidence', False, boolean_value,
                    cli=CliBinding(('--explain',), action='store_true'), answers=(_LIST,))
SORT = ParamSpec('sort', 'string', 'Frontmatter field; prefix - for descending', None, str,
                 cli=CliBinding(('--sort',)), answers=(_LIST,))
LIMIT = ParamSpec('limit', 'integer', 'Answer rows; 0 = no cap', None, int, minimum=0,
                  zero_policy='no cap', cli=CliBinding(('--limit',)), answers=(_LIST,))
OFFSET = ParamSpec('offset', 'integer', 'Answer rows skipped after sorting', 0, int, minimum=0,
                   cli=CliBinding(('--offset',)), answers=(_LIST,))
PARAM_SPECS: Tuple[ParamSpec, ...] = (WHERE, MATCH, VIEW, FIELD, BACKLINKS, LINT_FIELDS, FIELDS, EXPLAIN, SORT, LIMIT,
                                      OFFSET)
# --head/--tail/--range slice this noun's rows today: flag-only legacy modifiers until the cut, read by the answers named
# (BACK-2673; their notes are the flag:<noun>.<flag> RETIREMENTS rows).
_SLICED = ('markdown_query',)  # the list view; links, lint and aggregate have no rows to slice
PARAM_SPECS = (*PARAM_SPECS, *legacy_slices(head=_SLICED, tail=_SLICED, range=_SLICED))


def selected_view(params: Any, *, apply: bool = False) -> str:
    """The answer a bound request selects: its view (the legacy selectors are its spellings), else a backlinks target,
    else the listing."""
    values = params if apply else dict(peek_query_items(params))
    if values.get('view'):
        return str(values['view'])
    return 'backlinks' if values.get('backlinks') else 'list'


def result_type(params: Any) -> str:
    return {'links': 'markdown_link_graph', 'lint': 'markdown_frontmatter_lint',
            'backlinks': 'markdown_backlinks', 'aggregate': 'markdown_aggregate'}.get(selected_view(params), 'markdown_query')


def filter_state(params: QueryParams) -> tuple:
    text = '&'.join(WHERE.read(params))
    operators = text and any(op in text for op in ('>', '<', '!=', '~=', '!~', '..', '=='))
    return text, ([] if operators else parse_query(text)), (parse_query_filters(text) if operators else [])


def describe_request(params: QueryParams) -> str:
    """Stable request description across transports; never used as an invocation."""
    values = dict(peek_query_items(params))
    parts: list[str] = []
    for spec in PARAM_SPECS:
        if spec.name not in values:
            continue
        value = values[spec.name]
        sequence = value if isinstance(value, list) else [value]
        parts.extend(f'{spec.name}={item}' for item in sequence)
    return '&'.join(parts)


def validate_request(params: QueryParams, args=None) -> None:
    values = dict(peek_query_items(params))
    # Which answers read where, match, field and the rest is their declaration's (BACK-2656).
    if selected_view(params) == 'aggregate' and not values.get('field'):
        raise ValueError('aggregate view requires field')
    filter_state(params)
