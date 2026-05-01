"""URI adapter dispatch for reveal CLI.

Handles routing from URI schemes (env://, ast://, help://, etc.)
to the appropriate adapter + renderer pair.
"""

import logging
import sys
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace

logger = logging.getLogger(__name__)


def handle_uri(uri: str, element: Optional[str], args: 'Namespace') -> None:
    """Handle URI-based resources (env://, ast://, etc.).

    Args:
        uri: Full URI (e.g., env://, env://PATH)
        element: Optional element to extract
        args: Parsed command line arguments
    """
    if '://' not in uri:
        print(f"Error: Invalid URI format: {uri}", file=sys.stderr)
        sys.exit(1)

    scheme, resource = uri.split('://', 1)

    # Inject --sort/--desc CLI flags into URI query string for adapters that support them.
    # Skip injection if URI already has an explicit sort= param — URI takes precedence.
    sort_field = getattr(args, 'sort', None)
    if sort_field and 'sort=' not in resource:
        if getattr(args, 'desc', False) and not sort_field.startswith('-'):
            sort_field = f"-{sort_field}"
        sep = '&' if '?' in resource else '?'
        resource = f"{resource}{sep}sort={sort_field}"

    # Look up adapter from registry
    from ...adapters.base import get_adapter_class, list_supported_schemes
    # Import adapters package to trigger all registrations (single source of truth)
    from ... import adapters as _adapters  # noqa: F401

    adapter_class = get_adapter_class(scheme)
    if not adapter_class:
        print(f"Error: Unsupported URI scheme: {scheme}://", file=sys.stderr)
        schemes = ', '.join(f"{s}://" for s in list_supported_schemes())
        print(f"Supported schemes: {schemes}", file=sys.stderr)
        sys.exit(1)

    # Dispatch to scheme-specific handler
    handle_adapter(adapter_class, scheme, resource, element, args)


def generic_adapter_handler(adapter_class: type, renderer_class: type[Any],
                           scheme: str, resource: str, element: Optional[str],
                           args: 'Namespace') -> None:
    """Generic handler for adapters with registered renderers.

    This is the new simplified handler that works with any adapter/renderer pair.
    Replaces the need for scheme-specific handlers in most cases.

    Args:
        adapter_class: The adapter class to instantiate
        renderer_class: The renderer class for output
        scheme: URI scheme (for building full URI if needed)
        resource: Resource part of URI
        element: Optional element to extract
        args: CLI arguments
    """
    # Initialize adapter via from_uri.  Use _default_from_uri when adapter_class is
    # not a real type (e.g. a Mock callable in tests) or lacks from_uri.
    from ...adapters.base import _default_from_uri
    try:
        if isinstance(adapter_class, type) and hasattr(adapter_class, 'from_uri'):
            adapter = adapter_class.from_uri(scheme, resource, element)
        else:
            adapter = _default_from_uri(adapter_class, scheme, resource, element)
    except ImportError as e:
        renderer_class.render_error(e)
        sys.exit(1)
    except Exception as e:
        print(f"Error initializing {scheme}:// adapter: {e}", file=sys.stderr)
        sys.exit(1)

    # Apply --base-path override for adapters that support it (e.g., claude://)
    path_override = getattr(args, 'base_path', None)
    if path_override and hasattr(adapter, 'reconfigure_base_path'):
        from pathlib import Path as _Path
        try:
            adapter.reconfigure_base_path(_Path(path_override))
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    # Handle --check mode if requested
    if getattr(args, 'check', False) and hasattr(adapter, 'check'):
        _handle_check_mode(adapter, renderer_class, args)
        return  # check mode exits directly

    # Render element or structure based on adapter type
    _handle_rendering(adapter, renderer_class, scheme, resource, element, args)


def _build_check_kwargs(adapter, args: 'Namespace') -> dict:
    """Build kwargs for adapter.check() by inspecting signature.

    Args:
        adapter: Adapter with check() method
        args: CLI arguments

    Returns:
        Dict of kwargs to pass to check()
    """
    import inspect

    sig = inspect.signature(adapter.check)
    kwargs = {}
    has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())

    # Helper to add param if supported
    def add_if_supported(param_name, arg_name=None):
        arg_name = arg_name or param_name
        if (has_var_keyword or param_name in sig.parameters) and hasattr(args, arg_name):
            value = getattr(args, arg_name)
            if value is not None:
                # Split comma-separated strings
                if param_name in ('select', 'ignore') and isinstance(value, str):
                    value = value.split(',')
                kwargs[param_name] = value

    add_if_supported('select')
    add_if_supported('ignore')
    add_if_supported('advanced')
    add_if_supported('validate_nginx')
    add_if_supported('local_certs')
    add_if_supported('expiring_within')
    add_if_supported('probe_http')

    return kwargs


def _build_render_opts(renderer_class: type[Any], args: 'Namespace', query_params: Optional[dict] = None) -> dict:
    """Build render options by inspecting renderer signature.

    Args:
        renderer_class: Renderer class
        args: CLI arguments
        query_params: Optional URI query params (e.g. from adapter.query_params); CLI args take precedence

    Returns:
        Dict of options to pass to render method
    """
    import inspect

    if not hasattr(renderer_class, 'render_check'):
        return {}

    render_sig = inspect.signature(renderer_class.render_check)
    opts = {}

    # Map CLI args to render options
    for opt_name in ['only_failures', 'summary', 'expiring_within']:
        if opt_name in render_sig.parameters and hasattr(args, opt_name):
            value = getattr(args, opt_name)
            if value is not None:
                opts[opt_name] = value

    # Merge URI query params as base defaults — CLI args already set above take precedence
    if query_params:
        for opt_name in ['only_failures', 'summary', 'expiring_within']:
            if opt_name not in opts and opt_name in render_sig.parameters:
                raw = query_params.get(opt_name) or query_params.get(opt_name.replace('_', '-'))
                if raw is not None:
                    opts[opt_name] = raw if not isinstance(raw, bool) else raw

    return opts


def _handle_check_mode(adapter, renderer_class: type[Any], args: 'Namespace') -> None:
    """Execute check mode and exit.

    Args:
        adapter: Initialized adapter with check() method
        renderer_class: Renderer for check results
        args: CLI arguments with check flags
    """
    import json

    # Build check kwargs and execute
    check_kwargs = _build_check_kwargs(adapter, args)
    result = adapter.check(**check_kwargs)

    # Render check results
    if hasattr(renderer_class, 'render_check'):
        adapter_qp = getattr(adapter, 'query_params', {})
        render_opts = _build_render_opts(renderer_class, args, query_params=adapter_qp)
        renderer_class.render_check(result, args.format, **render_opts)
    else:
        # Fallback to generic JSON rendering
        if args.format == 'json':
            print(json.dumps(result, indent=2))
        else:
            print(result)

    # Exit with appropriate code
    if isinstance(result, dict):
        exit_code = result.get('exit_code', 0)
    else:
        logger.warning("check() returned non-dict result; treating as pass (exit 0)")
        exit_code = 0
    sys.exit(exit_code)


def _handle_rendering(adapter, renderer_class: type[Any], scheme: str,
                      resource: str, element: Optional[str], args: 'Namespace') -> None:
    """Render element or structure based on adapter capabilities.

    Args:
        adapter: Initialized adapter
        renderer_class: Renderer class for output
        scheme: URI scheme
        resource: Resource part of URI
        element: Optional element to extract
        args: CLI arguments
    """
    # Get element or structure based on adapter capabilities
    # Adapters with render_element (env, python, help) support element-based access
    # Others (ast, json, stats) always use get_structure() unless element explicitly provided
    supports_elements = hasattr(renderer_class, 'render_element')

    # Adapters where resource is part of element namespace (not initialization path)
    # For these, `scheme://RESOURCE` means "get element RESOURCE"
    # For others, `scheme://RESOURCE` means "analyze path RESOURCE"
    resource_is_element = getattr(adapter.__class__, 'ELEMENT_NAMESPACE_ADAPTER', False)

    if supports_elements and (element or (resource and resource_is_element)):
        _render_element(adapter, renderer_class, element, resource, args)
    else:
        _render_structure(adapter, renderer_class, args, scheme=scheme, resource=resource)


def _render_element(adapter, renderer_class: type[Any], element: Optional[str],
                    resource: str, args: 'Namespace') -> None:
    """Render a specific element from adapter.

    Args:
        adapter: Adapter with get_element() method
        renderer_class: Renderer for element output
        element: Element name (or None to use resource)
        resource: Fallback element name if element is None
        args: CLI arguments
    """
    element_name = element if element else resource
    result = adapter.get_element(element_name)

    if result is None:
        print(f"Error: Element '{element_name}' not found", file=sys.stderr)
        # Try to show available elements if adapter provides them
        if hasattr(adapter, 'list_elements'):
            elements = adapter.list_elements()
            print(f"Available elements: {', '.join(elements)}", file=sys.stderr)
        sys.exit(1)

    renderer_class.render_element(result, args.format)


def _build_adapter_kwargs(adapter, args: 'Namespace', scheme: Optional[str] = None, resource: Optional[str] = None) -> dict:
    """Build kwargs for adapter.get_structure() by inspecting signature.

    Args:
        adapter: Adapter instance
        args: CLI arguments
        scheme: Optional URI scheme
        resource: Optional resource string

    Returns:
        Dict of kwargs to pass to get_structure()
    """
    import inspect

    if not hasattr(adapter, 'get_structure'):
        return {}

    sig = inspect.signature(adapter.get_structure)
    kwargs = {}

    # URI parameter - reconstruct full URI for adapters that need it
    if 'uri' in sig.parameters and scheme and resource is not None:
        kwargs['uri'] = f"{scheme}://{resource}"

    # Map CLI args to adapter params (only if param exists and value is not None)
    param_mapping = {
        'hotspots': 'hotspots',
        'code_only': 'code_only',
        'min_lines': 'min_lines',
        'max_lines': 'max_lines',
        'min_complexity': 'min_complexity',
        'max_complexity': 'max_complexity',
        'min_functions': 'min_functions',
        'dns_verified': 'dns_verified',
        'only_failures': 'only_failures',
        'summary': 'summary',
        'user': 'user',
        'check_live': 'check_live',
        'check_orphans': 'check_orphans',
        'check_duplicates': 'check_duplicates',
        'audit': 'audit',
        'probe_http': 'probe_http',
        'probe': 'probe',
    }

    for arg_name, param_name in param_mapping.items():
        if param_name in sig.parameters:
            value = getattr(args, arg_name, None)
            if value is not None:
                kwargs[param_name] = value

    return kwargs


def _apply_field_selection(result: dict, args: 'Namespace') -> dict:
    """Apply field selection if --fields specified."""
    if hasattr(args, 'fields') and args.fields:
        from reveal.display.formatting import filter_fields
        fields = [f.strip() for f in args.fields.split(',')]
        return filter_fields(result, fields)
    return result


def _apply_budget_constraints(result: dict, args: 'Namespace', adapter=None) -> dict:
    """Apply budget constraints to result list fields."""
    if not isinstance(result, dict):
        return result

    # Adapter declares which field is budget-limitable; fall back to probing for
    # adapters that predate BUDGET_LIST_FIELD (transition period only).
    declared = getattr(adapter, 'BUDGET_LIST_FIELD', None) if adapter is not None else None
    if declared:
        list_field = declared if (declared in result and isinstance(result[declared], list)) else None
    else:
        list_field = None
        for field_name in ['items', 'results', 'checks', 'commits', 'files']:
            if field_name in result and isinstance(result[field_name], list):
                list_field = field_name
                break

    if not list_field:
        return result

    from reveal.utils.query import apply_budget_limits

    budget_result = apply_budget_limits(
        result[list_field],
        max_items=getattr(args, 'max_items', None),
        truncate_strings=getattr(args, 'max_snippet_chars', None)
    )

    # Update result with budget-limited items
    result[list_field] = budget_result['items']
    if budget_result['meta']['truncated']:
        # Merge budget metadata
        if 'meta' in result and isinstance(result['meta'], dict):
            result['meta']['budget'] = budget_result['meta']
        else:
            result['meta'] = budget_result['meta']

    return result


def _render_structure(adapter, renderer_class: type[Any], args: 'Namespace',
                      scheme: Optional[str] = None, resource: Optional[str] = None) -> None:
    """Render full structure from adapter.

    Args:
        adapter: Adapter with get_structure() method
        renderer_class: Renderer for structure output
        args: CLI arguments with optional filter parameters
        scheme: Optional URI scheme (for adapters that need full URI)
        resource: Optional resource string (for adapters that need full URI)
    """
    # Build adapter kwargs
    structure_kwargs = _build_adapter_kwargs(adapter, args, scheme, resource)

    # Get structure from adapter
    try:
        result = adapter.get_structure(**structure_kwargs)
    except Exception as e:
        error_msg = str(e)
        if '\n' in error_msg:
            print(f"Error: {error_msg}", file=sys.stderr)
        else:
            scheme_hint = f" ({scheme}://)" if scheme else ""
            print(f"Error{scheme_hint}: {error_msg}", file=sys.stderr)
        sys.exit(1)

    # Apply post-processing
    result = _apply_field_selection(result, args)
    result = _apply_budget_constraints(result, args, adapter)
    post_process = getattr(type(adapter), 'post_process', None)
    if post_process is not None:
        result = adapter.post_process(result, args)

    # Add available elements if adapter supports discovery
    if hasattr(adapter, 'get_available_elements'):
        available_elements = adapter.get_available_elements()
        if available_elements:
            result['available_elements'] = available_elements

    renderer_class.render_structure(result, args.format)


def handle_adapter(adapter_class: type, scheme: str, resource: str,
                   element: Optional[str], args: 'Namespace') -> None:
    """Handle adapter-specific logic for different URI schemes.

    All adapters now use the renderer-based system with generic handler.

    Args:
        adapter_class: The adapter class to instantiate
        scheme: URI scheme (env, ast, etc.)
        resource: Resource part of URI
        element: Optional element to extract
        args: CLI arguments
    """
    # Get renderer for this adapter
    from ...adapters.base import get_renderer_class
    renderer_class = get_renderer_class(scheme)

    if not renderer_class:
        # This shouldn't happen if adapter is properly registered
        print(f"Error: No renderer registered for scheme '{scheme}'", file=sys.stderr)
        print("This is a bug - adapter is registered but renderer is not.", file=sys.stderr)
        sys.exit(1)

    # Use generic handler for all adapters
    generic_adapter_handler(adapter_class, renderer_class, scheme, resource, element, args)
