"""Markdown controls bind directly; existing operations keep selection and source ownership."""
from typing import Any

from ...utils.query_parser import CliBinding, LegacySpelling, ParamSpec, QueryParams, peek_query_items
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
VIEW = ParamSpec('view', 'string', 'Answer view: list, links, aggregate (or legacy lint)',
                 None, str, choices=('list', 'links', 'aggregate', 'lint'), role='operation', cli=CliBinding(('--view',)))
FIELD = ParamSpec('field', 'string', 'Frontmatter field counted by the aggregate view', None, str,
                  cli=CliBinding(('--field',)), answers=(_AGGREGATE,))
BACKLINKS = ParamSpec('backlinks', 'string', 'Reverse link target, relative to the scanned directory',
                      None, str, cli=CliBinding(('--backlinks',)), uri_codec='percent')
AGGREGATE = ParamSpec('aggregate', 'string', 'Legacy aggregate field; use --view aggregate --field FIELD',
                      None, str, cli=CliBinding(('--aggregate',)))
LINKS = ParamSpec('link-graph', 'boolean', 'Legacy link graph selector; use --view links', False,
                  boolean_value, aliases=('link_graph',), cli=CliBinding(('--link-graph',), action='store_true'))
LINT = ParamSpec('lint', 'boolean', 'Legacy frontmatter lint selector', False, boolean_value,
                 cli=CliBinding(('--lint',), action='store_true'))
LINT_FIELDS = ParamSpec('lint-fields', 'array', 'Required frontmatter fields for legacy lint', None, fields,
                        cli=CliBinding(('--lint-fields',)), answers=(_LINT,))
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
PARAM_SPECS = (WHERE, MATCH, VIEW, FIELD, BACKLINKS, AGGREGATE, LINKS, LINT, LINT_FIELDS,
               FIELDS, EXPLAIN, SORT, LIMIT, OFFSET)


def _enabled(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.lower() in ('true', 'yes', '1'))


def selected_view(params: Any, *, apply: bool = False) -> str:
    values = params if apply else dict(peek_query_items(params))
    if values.get('view'):
        return str(values['view'])
    if any(_enabled(values.get(name)) for name in LINKS.spellings):
        return 'links'
    if _enabled(values.get('lint')):
        return 'lint'
    if values.get('backlinks'):
        return 'backlinks'
    return 'aggregate' if values.get('aggregate') else 'list'


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
    view = selected_view(params)
    if values.get('view'):
        selectors = ('link-graph', 'lint', 'backlinks', 'aggregate')
        if any(values.get(key) for key in selectors):
            raise ValueError('view conflicts with a legacy selector or backlinks target')
    # Which answers read where, match, field and the rest is their declaration's (BACK-2656).
    if view == 'aggregate' and not (values.get('field') or values.get('aggregate')):
        raise ValueError('aggregate view requires field')
    filter_state(params)
