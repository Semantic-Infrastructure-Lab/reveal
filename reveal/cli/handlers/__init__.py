"""Special mode handlers for reveal CLI.

These handlers implement --rules, --agent-help, --stdin, and other
special modes that exit early without processing files.

This package is split into focused submodules:
- introspection.py  -- informational flags (--rules, --adapters, --agent-help, etc.)
- batch.py          -- stdin/batch processing (--stdin, --batch)
- decorators.py     -- decorator statistics (--decorator-stats)
"""

from .introspection import (
    handle_list_supported,
    handle_languages,
    handle_adapters,
    handle_explain_file,
    handle_capabilities,
    handle_show_ast,
    handle_language_info,
    handle_agent_help,
    handle_agent_help_full,
    handle_schema,
    _get_schema_v1,
    handle_rules_list,
    handle_explain_rule,
    handle_discover,
    handle_list_schemas,
    _normalize_patterns,
)

from .batch import (
    handle_stdin_mode,
    _passes_ext_filter,
    _process_stdin_uri,
    _process_stdin_file,
    _collect_ssl_check_result,
    _render_ssl_batch_results,
    _collect_batch_result,
    _aggregate_batch_stats,
    _group_results_by_scheme,
    _filter_batch_display_results,
    _determine_batch_overall_status,
    _get_status_indicator,
    _render_batch_text_output,
    _calculate_batch_exit_code,
    _render_batch_results,
)

from .decorators import (
    handle_decorator_stats,
    _collect_decorator_counts,
    _extract_decorators_from_file,
    _categorize_decorators,
    _print_decorator_category,
    _collect_file_decorators,
    _scan_python_files,
)

# Backward compatibility aliases (private names used in main.py)
_handle_list_supported = handle_list_supported
_handle_agent_help = handle_agent_help
_handle_agent_help_full = handle_agent_help_full
_handle_rules_list = handle_rules_list
_handle_explain_rule = handle_explain_rule
_handle_stdin_mode = handle_stdin_mode
_handle_decorator_stats = handle_decorator_stats

__all__ = [
    # Introspection
    '_get_schema_v1',
    '_normalize_patterns',
    'handle_list_supported',
    'handle_languages',
    'handle_adapters',
    'handle_explain_file',
    'handle_capabilities',
    'handle_show_ast',
    'handle_language_info',
    'handle_agent_help',
    'handle_agent_help_full',
    'handle_schema',
    'handle_rules_list',
    'handle_explain_rule',
    'handle_discover',
    'handle_list_schemas',
    # Batch
    'handle_stdin_mode',
    '_passes_ext_filter',
    '_process_stdin_uri',
    '_process_stdin_file',
    '_collect_ssl_check_result',
    '_render_ssl_batch_results',
    '_collect_batch_result',
    '_aggregate_batch_stats',
    '_group_results_by_scheme',
    '_filter_batch_display_results',
    '_determine_batch_overall_status',
    '_get_status_indicator',
    '_render_batch_text_output',
    '_calculate_batch_exit_code',
    '_render_batch_results',
    # Decorators
    'handle_decorator_stats',
    '_collect_decorator_counts',
    '_extract_decorators_from_file',
    '_categorize_decorators',
    '_print_decorator_category',
    '_collect_file_decorators',
    '_scan_python_files',
    # Compat aliases
    '_handle_list_supported',
    '_handle_agent_help',
    '_handle_agent_help_full',
    '_handle_rules_list',
    '_handle_explain_rule',
    '_handle_stdin_mode',
    '_handle_decorator_stats',
]
