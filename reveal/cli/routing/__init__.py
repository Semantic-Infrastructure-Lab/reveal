"""URI and file routing for reveal CLI.

This module handles dispatching to the correct handler based on:
- URI scheme (env://, ast://, help://, python://, json://, reveal://, etc.)
- File type (determined by extension)
- Directory handling

All URI adapters now use the renderer-based system (Phase 4 complete).

This package is split into focused submodules:
- uri.py   -- adapter/URI dispatch (handle_uri, generic_adapter_handler, etc.)
- file.py  -- file/directory dispatch (handle_file_or_directory, guards, etc.)
"""

import logging

logger = logging.getLogger(__name__)

from .uri import (
    handle_uri,
    generic_adapter_handler,
    handle_adapter,
    _build_check_kwargs,
    _build_render_opts,
    _handle_check_mode,
    _handle_rendering,
    _render_element,
    _build_adapter_kwargs,
    _apply_field_selection,
    _apply_budget_constraints,
    _render_structure,
)

from .file import (
    handle_file_or_directory,
    _parse_file_line_syntax,
    _validate_path_exists,
    _stat_one_file,
    _collect_dir_stats,
    _render_dir_meta_text,
    _show_directory_meta,
    _parse_ext_arg,
    _build_ast_query_from_flags,
    _guard_hotspots_flag,
    _guard_nginx_flags,
    _guard_ssl_flags,
    _guard_related_flags,
    _handle_directory_path,
    _handle_file_path,
)

# Re-export handle_file for backward compatibility
# (tests import it as `from reveal.cli.routing import handle_file`)
from ...file_handler import handle_file  # noqa: F401, E402

__all__ = [
    # URI dispatch
    'handle_uri',
    'generic_adapter_handler',
    'handle_adapter',
    '_build_check_kwargs',
    '_build_render_opts',
    '_handle_check_mode',
    '_handle_rendering',
    '_render_element',
    '_build_adapter_kwargs',
    '_apply_field_selection',
    '_apply_budget_constraints',
    '_render_structure',
    # File/directory dispatch
    'handle_file_or_directory',
    '_parse_file_line_syntax',
    '_validate_path_exists',
    '_stat_one_file',
    '_collect_dir_stats',
    '_render_dir_meta_text',
    '_show_directory_meta',
    '_parse_ext_arg',
    '_build_ast_query_from_flags',
    '_guard_hotspots_flag',
    '_guard_nginx_flags',
    '_guard_ssl_flags',
    '_guard_related_flags',
    '_handle_directory_path',
    '_handle_file_path',
    # Compat
    'handle_file',
]
