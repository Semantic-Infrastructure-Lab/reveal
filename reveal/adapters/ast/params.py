"""Declared AST controls; expressions continue through the existing AST filter parser."""

from dataclasses import replace
from typing import Tuple

from ...errors import RequestValidationError
from ...utils.query_binding import boolean_value, string_value
from ...utils.query_parser import (CliBinding, LegacySpelling, ParamSpec, QueryParams, legacy_slices, where_param,
                                   whole_number)
from ...utils.query_control import declared_result_control as result_control
from .queries import ALL_OP, format_query, parse_query, validate_filter_values, _condition

# The element listing (the default answer, and the retired calls view of it): the answer the row controls read. The
# Python-evidence answers (dict-heatmap, dict-schemas, reveal-type) read none of them (COMMAND_MODEL "Applicability").
_LISTING = ('ast_query',)
VIEWS = ('dict-heatmap', 'dict-schemas')


def _legacy_depth(value: object) -> str:
    """Bare ``depth=N`` is the where term on the element's nesting depth (``?depth>4`` folds unchanged and its field word
    depth is noted and spelled nesting_depth)."""
    return 'nesting_depth' if value is True else f'nesting_depth={value}'


# depth is a shared control name (graph hops): bare, it is never a field (rule 8); AST's legacy meaning, the nesting
# depth filter, is a legacy word of where with the same term, identical by construction (rule 16, BACK-2654).
# Retired fields note their row (Q2): calls/callee_of retired to the calls noun (BACK-2066); type is kind and depth is
# nesting_depth, the same filter (Q5, Q10; the element's JSON key stays depth, D16).
WHERE = replace(where_param('Filter expressions, ANDed; repeat --where for multiple bounds',
                            legacy=(LegacySpelling('depth', codec=_legacy_depth),),
                            open_fields='any element key the analyzer emits (name, complexity, line_count, ...), plus '
                                        'kind, lines, nesting_depth, decorator, param_type, return_type, has_annotations, '
                                        'callers',
                            retired_fields=('calls', 'callee_of', 'type', 'depth'),
                            field_words=(('type', 'kind'), ('depth', 'nesting_depth'))),
                answers=_LISTING)
KIND = ParamSpec('kind', 'string', 'Element kind (function, method, class, struct, import, interface, ...)',
                 None, string_value, legacy=(LegacySpelling('type', flag='--type'),), cli=CliBinding(('--kind',)),
                 answers=_LISTING)
# calls is a retired value (the within-file call graph retired to the calls noun), declared by its value-keyed entry:
# it answers until the cut on either spelling, each with its value row's note (value:ast.show=calls,
# value:ast.view=calls), and has no canonical form.
VIEW = ParamSpec('view', 'string', 'Answer view: dict-heatmap or dict-schemas (Python evidence)',
                 None, string_value, choices=VIEWS,
                 legacy=(LegacySpelling('show', flag='--show'), LegacySpelling('show', value='calls')), role='operation',
                 cli=CliBinding(('--view',)))
BUILTINS = ParamSpec('builtins', 'boolean', 'Include builtin calls in each element\'s calls list', False,
                     boolean_value, cli=CliBinding(('--builtins',), action='store_true'), answers=_LISTING)
# Names a variable: one with no occurrence in the analyzed Python files is a target that matches nothing (plan rule 9).
REVEAL_TYPE = ParamSpec('reveal-type', 'string', 'Type evidence for a variable (Python only)',
                        None, string_value, aliases=('reveal_type',), uri_codec='raw', role='operation', names='symbol',
                        cli=CliBinding(('--reveal-type',), dest='reveal_type'))
SORT = ParamSpec('sort', 'string', 'Sort field; prefix - for descending', None, string_value,
                 cli=CliBinding(('--sort',)), answers=_LISTING)
LIMIT = ParamSpec('limit', 'integer', 'Answer rows; 0 = no cap (every row, past the 200-result default)', None,
                  whole_number, minimum=0, zero_policy='no cap', cli_flags=(('all', '1000000'),),
                  cli=CliBinding(('--limit',)), answers=_LISTING)
OFFSET = ParamSpec('offset', 'integer', 'Answer rows skipped after sorting', 0, whole_number,
                   minimum=0, cli=CliBinding(('--offset',)), answers=_LISTING)
PARAM_SPECS: Tuple[ParamSpec, ...] = (WHERE, KIND, VIEW, BUILTINS, REVEAL_TYPE, SORT, LIMIT, OFFSET)
# --head/--tail/--range slice this noun's rows today: flag-only legacy modifiers until the cut, read by the answers named
# (BACK-2673; their notes are the flag:<noun>.<flag> RETIREMENTS rows).
PARAM_SPECS = (*PARAM_SPECS, *legacy_slices(head=(), tail=(), range=()))


def _and_field(query: dict, field: str, condition: dict) -> None:
    """AND *condition* onto *field*'s conditions in the parsed filter."""
    prior = query.get(field)
    conditions = [] if prior is None else (prior['value'] if prior['op'] == ALL_OP else [prior])
    added = condition['value'] if condition['op'] == ALL_OP else [condition]
    combined = conditions + added
    query[field] = combined[0] if len(combined) == 1 else {'op': ALL_OP, 'value': combined}


def ast_query(params: QueryParams):
    """The filter the analysis evaluates, keyed by the engine's fields: a canonical where field the engine knows under
    its retired word (kind is type, nesting_depth is depth) joins that word's conditions. A filter that can never match
    is an invalid request."""
    try:
        query = parse_query('&'.join(WHERE.read(params)))
        for old, new in WHERE.field_words:
            if new in query:
                _and_field(query, old, query.pop(new))
        kind = KIND.read(params)
        if kind is not None:
            _and_field(query, 'type', _condition('=', kind))
        validate_filter_values(query)
    except RequestValidationError:
        raise
    except ValueError as exc:  # the same invalid request on every transport, the Python URI path included (B8)
        raise RequestValidationError(str(exc)) from exc
    return query


def echo_query(query: dict) -> str:
    """The filter as the answer echoes it, on canonical fields (``kind==function``, ``nesting_depth>4``)."""
    return format_query(query, names=dict(WHERE.field_words))
