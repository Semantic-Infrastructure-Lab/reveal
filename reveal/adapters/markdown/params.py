"""Markdown controls bind directly; existing operations keep selection and source ownership."""
from typing import Any

from ...utils.query_parser import CliBinding, ParamSpec, QueryParams, peek_query_items
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


WHERE = ParamSpec('where', 'array', 'Frontmatter expressions, ANDed; repeat for multiple constraints',
                  [], strings, role='filter-expression', cli=CliBinding(('--where',), action='append'))
MATCH = ParamSpec('match', 'array', 'Body terms, ANDed; repeat to require multiple terms',
                  [], strings, aliases=('body-contains',), uri_codec='percent',
                  cli=CliBinding(('--match', '--body-contains'), action='append'))
VIEW = ParamSpec('view', 'string', 'Answer view: list, links, aggregate (or legacy lint)',
                 None, str, choices=('list', 'links', 'aggregate', 'lint'), cli=CliBinding(('--view',)))
FIELD = ParamSpec('field', 'string', 'Frontmatter field counted by the aggregate view', None, str,
                  cli=CliBinding(('--field',)))
BACKLINKS = ParamSpec('backlinks', 'string', 'Reverse link target, relative to the scanned directory',
                      None, str, cli=CliBinding(('--backlinks',)), uri_codec='percent')
AGGREGATE = ParamSpec('aggregate', 'string', 'Legacy aggregate field; use --view aggregate --field FIELD',
                      None, str, cli=CliBinding(('--aggregate',)))
LINKS = ParamSpec('link-graph', 'boolean', 'Legacy link graph selector; use --view links', False,
                  boolean_value, aliases=('link_graph',), cli=CliBinding(('--link-graph',), action='store_true'))
LINT = ParamSpec('lint', 'boolean', 'Legacy frontmatter lint selector', False, boolean_value,
                 cli=CliBinding(('--lint',), action='store_true'))
LINT_FIELDS = ParamSpec('lint-fields', 'array', 'Required frontmatter fields for legacy lint', None, fields,
                        cli=CliBinding(('--lint-fields',)))
FIELDS = ParamSpec('columns', 'array', 'Additional frontmatter fields displayed as listing columns', None, fields,
                   aliases=('fields',), cli=CliBinding(('--columns',)))
EXPLAIN = ParamSpec('explain', 'boolean', 'Include per-term body relevance evidence', False, boolean_value,
                    cli=CliBinding(('--explain',), action='store_true'))
SORT = ParamSpec('sort', 'string', 'Frontmatter field; prefix - for descending', None, str,
                 cli=CliBinding(('--sort',)))
LIMIT = ParamSpec('limit', 'integer', 'Answer rows; zero is an empty page', None, int, minimum=0,
                  zero_policy='empty page', cli=CliBinding(('--limit',)))
OFFSET = ParamSpec('offset', 'integer', 'Answer rows skipped after sorting', 0, int, minimum=0,
                   cli=CliBinding(('--offset',)))
PARAM_SPECS = (WHERE, MATCH, VIEW, FIELD, BACKLINKS, AGGREGATE, LINKS, LINT, LINT_FIELDS,
               FIELDS, EXPLAIN, SORT, LIMIT, OFFSET)


def _enabled(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.lower() in ('true', 'yes', '1'))


def selected_view(params: Any, *, apply: bool = False) -> str:
    values = params if apply else dict(peek_query_items(params))
    if values.get('view'):
        return str(values['view'])
    if _enabled(values.get('link-graph')):
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
        if view not in ('list', 'aggregate') and (values.get('where') or values.get('match')):
            raise ValueError('where/match require the list or aggregate view')
    if view == 'aggregate' and not (values.get('field') or values.get('aggregate')):
        raise ValueError('aggregate view requires field')
    if values.get('field') and view != 'aggregate':
        raise ValueError('field requires the aggregate view')
    filter_state(params)
