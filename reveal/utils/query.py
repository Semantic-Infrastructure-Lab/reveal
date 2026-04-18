"""Re-export shim — preserves backward-compat imports from utils.query.

Split into focused modules (BACK-184):
  query_parser.py  — coerce_value, parse_query_params, QueryFilter, parse_query_filters
  query_eval.py    — compare_values, apply_filter, apply_filters
  query_control.py — ResultControl, parse_result_control, apply_result_control, apply_budget_limits
"""

from .query_parser import (  # noqa: F401
    coerce_value,
    parse_query_params,
    QueryFilter,
    _try_parse_negation_filter,
    _try_parse_two_char_operators,
    _parse_equals_special_cases,
    _try_parse_single_char_operators,
    parse_query_filters,
)
from .query_eval import (  # noqa: F401
    _handle_range_operator,
    _handle_wildcard_operator,
    _REGEX_MAX_LEN,
    _handle_regex_operator,
    _handle_equality_operator,
    _ORDERED_OPS,
    _apply_ordered_op,
    _handle_numeric_operator,
    _handle_none_comparison,
    _dispatch_comparison,
    compare_values,
    apply_filter,
    apply_filters,
)
from .query_control import (  # noqa: F401
    ResultControl,
    _apply_sort_param,
    _apply_control_param,
    parse_result_control,
    _safe_numeric,
    _detect_value_types,
    _create_sort_key,
    _apply_sorting,
    _apply_offset_and_limit,
    apply_result_control,
    apply_budget_limits,
    _truncate_string_values,
    _truncate_dict_strings,
)
