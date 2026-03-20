"""File handling operations.

This module is separate from cli.routing to avoid circular dependencies with adapters.

Nginx-specific file handlers live in reveal.cli.handlers_nginx (BACK-097).
Re-exported here for backward compatibility with existing test imports.
"""

import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace

# Nginx handlers — canonical location is handlers_nginx.py
from .handlers_nginx import (  # noqa: F401 — re-exported for backward compat
    _handle_domain_extraction,
    _handle_acme_roots_extraction,
    _handle_check_acl,
    _format_acl_col,
    _format_acme_ssl_col,
    _fetch_acme_ssl_data,
    _render_acme_json,
    _render_acme_text,
    _handle_validate_nginx_acme,
    _handle_global_audit,
    _handle_check_conflicts,
    _resolve_log_path,
    _render_diagnose_table,
    _handle_diagnose,
    _load_disk_cert,
    _load_live_cert,
    _cert_match_label,
    _format_disk_col,
    _format_live_col,
    _format_match_col,
    _handle_cpanel_certs,
    _handle_extract_option,
)


def _get_analyzer_or_exit(path: str, allow_fallback: bool):
    """Get analyzer for path or exit with error.

    Args:
        path: File path
        allow_fallback: Whether to allow fallback analyzers

    Returns:
        Analyzer instance

    Exits:
        With error code 1 if no analyzer found
    """
    from .registry import get_analyzer, get_all_analyzers  # noqa: I006 — circular avoidance
    from .errors import AnalyzerNotFoundError  # noqa: I006 — circular avoidance

    analyzer_class = get_analyzer(path, allow_fallback=allow_fallback)
    if not analyzer_class:
        # Find similar extensions for suggestions
        ext = Path(path).suffix
        similar_exts = None
        if ext:
            analyzers = get_all_analyzers()
            similar_exts = [e for e in analyzers.keys()
                          if ext.lower() in e.lower() or e.lower() in ext.lower()]

        # Create detailed error with suggestions
        error = AnalyzerNotFoundError(
            path=path,
            allow_fallback=allow_fallback,
            similar_extensions=similar_exts
        )

        print(str(error), file=sys.stderr)
        sys.exit(1)

    return analyzer_class(path)


def _build_file_cli_overrides(args: Optional['Namespace']) -> dict:
    """Build CLI overrides dictionary from args.

    Args:
        args: Argument namespace

    Returns:
        CLI overrides dict
    """
    cli_overrides = {}
    if args and getattr(args, 'no_breadcrumbs', False):
        cli_overrides['display'] = {'breadcrumbs': False}
    return cli_overrides


def handle_file(path: str, element: Optional[str], show_meta: bool,
                output_format: str, args: Optional['Namespace'] = None) -> None:
    """Handle file analysis.

    Args:
        path: File path
        element: Optional element to extract
        show_meta: Whether to show metadata only
        output_format: Output format ('text', 'json', 'grep')
        args: Full argument namespace (for filter options)
    """
    from .display import show_structure, show_metadata, extract_element  # noqa: I006 — circular avoidance
    from .config import RevealConfig  # noqa: I006 — circular avoidance

    # Get analyzer
    allow_fallback = not getattr(args, 'no_fallback', False) if args else True
    analyzer = _get_analyzer_or_exit(path, allow_fallback)

    # Load config with CLI overrides
    cli_overrides = _build_file_cli_overrides(args)
    config = RevealConfig.get(
        start_path=Path(path).parent if Path(path).is_file() else Path(path),
        cli_overrides=cli_overrides if cli_overrides else None
    )

    # Route to appropriate handler based on flags
    if show_meta:
        show_metadata(analyzer, output_format, config=config)
        return

    if args and getattr(args, 'extract', None):
        _handle_extract_option(analyzer, args.extract.lower(), args=args)
        return

    if args and getattr(args, 'check_acl', False):
        _handle_check_acl(analyzer)
        return

    if args and getattr(args, 'validate_nginx_acme', False):
        _handle_validate_nginx_acme(analyzer, args)
        return

    if args and getattr(args, 'global_audit', False):
        _handle_global_audit(analyzer, args)
        return

    if args and getattr(args, 'check_conflicts', False):
        _handle_check_conflicts(analyzer)
        return

    if args and getattr(args, 'cpanel_certs', False):
        _handle_cpanel_certs(analyzer)
        return

    if args and getattr(args, 'diagnose', False):
        _handle_diagnose(analyzer, log_path=getattr(args, 'log_path', None))
        return

    if args and getattr(args, 'validate_schema', None):
        from .checks import run_schema_validation  # noqa: I006 — circular avoidance
        run_schema_validation(analyzer, path, args.validate_schema, output_format, args)
        return

    if args and getattr(args, 'check', False):
        from .checks import run_pattern_detection  # noqa: I006 — circular avoidance
        run_pattern_detection(analyzer, path, output_format, args, config=config)
        return

    if element:
        extract_element(analyzer, element, output_format, config=config)
        return

    show_structure(analyzer, output_format, args, config=config)
