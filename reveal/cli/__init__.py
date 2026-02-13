"""CLI infrastructure for reveal.

This package contains:
- parser.py: Argument parsing and validation
- handlers.py: Special mode handlers (--rules, --agent-help, --stdin, etc.)
- routing.py: URI and file routing logic
"""

from .parser import (
    create_argument_parser,
    build_help_epilog,
    validate_navigation_args,
)

from .handlers import (
    handle_list_supported,
    handle_languages,
    handle_adapters,
    handle_explain_file,
    handle_capabilities,
    handle_show_ast,
    handle_language_info,
    handle_agent_help,
    handle_agent_help_full,
    handle_rules_list,
    handle_schema,
    handle_explain_rule,
    handle_list_schemas,
    handle_stdin_mode,
    handle_decorator_stats,
)

from .handlers_scaffold import (
    handle_scaffold_adapter,
    handle_scaffold_analyzer,
    handle_scaffold_rule,
)

from .routing import (
    handle_uri,
    handle_adapter,
    handle_file_or_directory,
)

# Import from file_handler to avoid circular dependency
from ..file_handler import handle_file

__all__ = [
    # Parser
    'create_argument_parser',
    'build_help_epilog',
    'validate_navigation_args',
    # Handlers
    'handle_list_supported',
    'handle_languages',
    'handle_adapters',
    'handle_explain_file',
    'handle_capabilities',
    'handle_show_ast',
    'handle_language_info',
    'handle_agent_help',
    'handle_agent_help_full',
    'handle_rules_list',
    'handle_schema',
    'handle_explain_rule',
    'handle_list_schemas',
    'handle_stdin_mode',
    'handle_decorator_stats',
    # Scaffolding
    'handle_scaffold_adapter',
    'handle_scaffold_analyzer',
    'handle_scaffold_rule',
    # Routing
    'handle_uri',
    'handle_adapter',
    'handle_file_or_directory',
    'handle_file',
]
