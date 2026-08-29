"""Utility functions for reveal."""

from .clipboard import copy_to_clipboard
from .formatting import format_size
from .json_utils import DateTimeEncoder, safe_json_dumps, print_json_result, set_provenance_enabled, write_also_json
from .breadcrumbs import (
    get_element_placeholder,
    get_file_type_from_analyzer,
    print_breadcrumbs,
)
from .patterns import Patterns, compile_pattern
from .path_utils import (
    find_file_in_parents,
    search_parents,
    find_project_root,
    get_relative_to_root,
)
from .updates import check_for_updates
from .parallel import grep_files
from .query import (
    coerce_value,
    parse_query_params,
    warn_unknown_query_params,
    parse_query_filters,
    QueryFilter,
    apply_filter,
    apply_filters,
)

__all__ = [
    'copy_to_clipboard',
    'format_size',
    'DateTimeEncoder',
    'safe_json_dumps',
    'print_json_result',
    'set_provenance_enabled',
    'write_also_json',
    'get_element_placeholder',
    'get_file_type_from_analyzer',
    'print_breadcrumbs',
    'Patterns',
    'compile_pattern',
    'find_file_in_parents',
    'search_parents',
    'find_project_root',
    'get_relative_to_root',
    'check_for_updates',
    'grep_files',
    'coerce_value',
    'parse_query_params',
    'warn_unknown_query_params',
    'parse_query_filters',
    'QueryFilter',
    'apply_filter',
    'apply_filters',
]
