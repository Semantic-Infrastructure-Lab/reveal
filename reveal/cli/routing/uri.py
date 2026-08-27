"""URI adapter dispatch for reveal CLI.

Handles routing from URI schemes (env://, ast://, help://, etc.)
to the appropriate adapter + renderer pair.
"""

import logging
import os
import re
import sys
from typing import Any, List, Optional, TYPE_CHECKING

from ...errors import NotApplicableError
from ...utils import print_json_result

if TYPE_CHECKING:
    from argparse import Namespace

logger = logging.getLogger(__name__)


def _emit_not_applicable_envelope(scheme: str, resource: str, reason: str, args: 'Namespace') -> None:
    """Emit a valid envelope for a query that genuinely does not apply to
    the target (BACK-1210) — e.g. testability:// with no tests, git://
    on a non-repo — exiting 0, not 1. This is a recorded result ("ran,
    nothing applicable, here's why"), not a failure to work around; a
    scripted batch consumer can no longer confuse it with a genuine
    adapter crash (which still exits 1 via _emit_adapter_error_envelope).
    Composes with BACK-1209's envelope fix: same shape, meta.applicable
    added.
    """
    from ...reveal_types import CONTRACT_VERSION
    from ...utils.results import ResultBuilder

    result = ResultBuilder.create(
        result_type=scheme,
        source=resource,
        contract_version=CONTRACT_VERSION,
        warnings=[{'code': 'not_applicable', 'message': reason}],
        applicable=False,
        reason=reason,
    )
    if getattr(args, 'format', 'text') == 'json':
        print_json_result(result)
    else:
        print(f"({scheme}://) not applicable: {reason}")


def _emit_adapter_error_envelope(scheme: str, resource: str, error_msg: str, args: 'Namespace') -> None:
    """Emit a valid Output Contract envelope for an adapter-error path instead
    of leaving stdout empty (BACK-1209). Adapters that raise instead of
    returning ResultBuilder.create_error() themselves (e.g. testability://,
    git://, diff://) previously left stdout at 0 bytes in both --format json
    and --format text, indistinguishable from a crashed/hung process to a
    scripted consumer globbing artifacts.
    """
    from ...utils.results import ResultBuilder

    result = ResultBuilder.create_error(
        result_type=scheme,
        source=resource,
        error=error_msg,
    )
    result['meta'] = ResultBuilder.create_meta(errors=[{'code': 'adapter_error', 'message': error_msg}])
    if getattr(args, 'format', 'text') == 'json':
        print_json_result(result)
    else:
        print(f"Error ({scheme}://): {error_msg} — adapter produced no result")


def _parse_text_headings(text: str) -> List[dict]:
    """Extract ATX headings from a markdown text string."""
    headings = []
    for i, line in enumerate(text.splitlines(), 1):
        m = re.match(r'^(#{1,6})\s+(.+)$', line)
        if m:
            headings.append({'line': i, 'level': len(m.group(1)), 'name': m.group(2).strip()})
    return headings


def _parse_text_links(text: str) -> List[dict]:
    """Extract markdown inline links [text](url) from a text string."""
    links = []
    for i, line in enumerate(text.splitlines(), 1):
        for m in re.finditer(r'\[([^\]]+)\]\(([^)\s]+)[^)]*\)', line):
            url = m.group(2).strip()
            ltype = ('email' if url.startswith('mailto:')
                     else 'external' if url.startswith(('http://', 'https://'))
                     else 'internal')
            links.append({'line': i, 'text': m.group(1), 'url': url, 'type': ltype})
    return links


def _parse_text_frontmatter(text: str) -> Optional[dict]:
    """Extract YAML frontmatter (---...---) from a markdown text string.

    Returns {'data': dict, 'line_start': int, 'line_end': int, 'raw': str}
    or None if no frontmatter block is present at all.

    Raises:
        ValueError: a frontmatter block IS present but isn't valid YAML — a
            distinct case from "no frontmatter" (BACK-989: previously
            swallowed to None, indistinguishable from a doc that never had
            frontmatter — `reveal doc.md --frontmatter` told the user "No
            YAML frontmatter found" even when they had a block with a typo).
    """
    if not text.startswith('---'):
        return None
    end_match = re.search(r'\n---\s*\n', text[3:])
    if not end_match:
        return None
    yaml_content = text[3:end_match.start() + 3]
    try:
        import yaml
        data = yaml.safe_load(yaml_content)
    except Exception as e:
        raise ValueError(f"frontmatter block found but failed to parse as YAML: {e}") from e
    if not isinstance(data, dict):
        return None
    line_end = text[:end_match.start() + 3].count('\n') + 2
    return {'data': data, 'line_start': 1, 'line_end': line_end, 'raw': yaml_content.strip()}


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

    # Expand a leading ~/... in the resource path before dispatch. A single-quoted
    # 'scheme://~/dir?query' never reaches shell tilde expansion (the ? forces
    # quoting), and only some adapters called expanduser() themselves — centralize
    # it here so every scheme behaves consistently instead of adapter-by-adapter
    # opt-in. os.path.expanduser is a no-op unless the string leads with ~/~user,
    # so this is safe for non-path resources (env://VAR, help://topic, etc.).
    # Query string is left untouched so a literal '~' in a query value survives.
    _path_part, _sep, _query_part = resource.partition('?')
    resource = os.path.expanduser(_path_part) + _sep + _query_part

    # --grep is only implemented for file-path targets (routing/file.py).  Warn rather
    # than silently ignoring so users know their filter didn't apply (BACK-351).
    if getattr(args, 'grep', None):
        pipe_uri = uri if '?' not in uri else f"'{uri}'"
        print(
            f"Note: --grep is not supported for URI schemes. "
            f"Use: reveal {pipe_uri} | grep '{args.grep}'",
            file=sys.stderr,
        )

    # --links / --frontmatter apply to element retrieval (text-body content) only.
    # On markdown:// directory queries these flags have no effect — warn with
    # alternatives so users know their intent wasn't silently dropped (BACK-357).
    if scheme == 'markdown' and not element:
        if getattr(args, 'links', False):
            print(
                "Note: --links has no effect on markdown:// directory queries. "
                "For cross-file link analysis use: reveal 'markdown://dir?link-graph'",
                file=sys.stderr,
            )
        if getattr(args, 'frontmatter', False):
            print(
                "Note: --frontmatter has no effect on markdown:// directory queries "
                "(frontmatter is already the primary output). "
                "Use ?fields=field1,field2 to select specific frontmatter keys.",
                file=sys.stderr,
            )

    # Inject --sort/--desc CLI flags into URI query string for adapters that support them.
    # Skip injection if URI already has an explicit sort= param — URI takes precedence.
    sort_field = getattr(args, 'sort', None)
    if sort_field and 'sort=' not in resource:
        if getattr(args, 'desc', False) and not sort_field.startswith('-'):
            sort_field = f"-{sort_field}"
        sep = '&' if '?' in resource else '?'
        resource = f"{resource}{sep}sort={sort_field}"

    # Inject --limit into the URI query string for resource-adapter result
    # capping (BACK-1108). Only the URI form (?limit=N) actually reached
    # ResultControl -- the CLI flag was parsed, accepted, and silently
    # discarded for every URI-scheme target, a real ~200-result truncation
    # in a language-consistency study relied on the flag actually working.
    # --limit's argparse default (50) is shared with the unrelated `check`
    # text-output cap (file_checker.py), so a default value alone can't
    # distinguish "user asked for a cap" from "user didn't mention it" --
    # only inject when --limit was actually typed, detected via sys.argv
    # (same technique used for --help-all in parser.py). Skip injection if
    # the URI already has an explicit limit= param — URI takes precedence.
    if 'limit=' not in resource and any(
        a == '--limit' or a.startswith('--limit=') for a in sys.argv
    ):
        limit_value = getattr(args, 'limit', None)
        if limit_value is not None:
            sep = '&' if '?' in resource else '?'
            resource = f"{resource}{sep}limit={limit_value}"

    resource = _inject_exclude_flag(resource, scheme, args)
    resource = _inject_since_until_flags(resource, scheme, args)

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


def _inject_exclude_flag(resource: str, scheme: str, args: 'Namespace') -> str:
    """Inject --exclude into the URI query string for the URI-scheme adapters
    that actually consume ?exclude= (BACK-1187/BACK-1192): only overview://
    and stats:// read it (BACK-1042). Every other scheme accepted the CLI
    flag via argparse and silently discarded it before this fix -- "the
    caller believes the scope was applied" (BACK-1192's framing) is exactly
    the failure mode a DD scoping flag must never have. --exclude is
    action='append' (a list); ?exclude= takes one comma-separated value,
    matching BACK-1042's own format. Skip injection if the URI already has
    an explicit exclude= param -- URI takes precedence, same as --sort/--limit.
    """
    _EXCLUDE_AWARE_SCHEMES = {'overview', 'stats'}
    exclude_values = getattr(args, 'exclude', None)
    if not exclude_values:
        return resource
    if scheme in _EXCLUDE_AWARE_SCHEMES:
        if 'exclude=' not in resource:
            sep = '&' if '?' in resource else '?'
            resource = f"{resource}{sep}exclude={','.join(exclude_values)}"
    else:
        aware = '/'.join(f'{s}://' for s in sorted(_EXCLUDE_AWARE_SCHEMES))
        print(
            f"Note: --exclude has no effect on {scheme}:// -- only {aware} "
            f"support it. Pre-filter the target path or scope to a narrower directory.",
            file=sys.stderr,
        )
    return resource


def _inject_since_until_flags(resource: str, scheme: str, args: 'Namespace') -> str:
    """Inject --since/--until into the URI query string for git:// (BACK-1192).
    git:// already supports ?since=YYYY-MM-DD (an ergonomic date>= alias) and
    now ?until=YYYY-MM-DD (date<=, added alongside this fix) -- but nothing
    forwarded the global CLI flags into the query string, so `reveal
    'git://.' --since 2026-01-01` silently returned the unfiltered commit
    list. Skip injection if the URI already has an explicit since=/until=
    (or the raw date filter) -- URI takes precedence, same as --sort/--limit/
    --exclude. Only git:// consumes these; every other scheme gets a note,
    same remedy pattern as --exclude.
    """
    _SINCE_UNTIL_AWARE_SCHEMES = {'git'}
    since_value = getattr(args, 'since', None)
    until_value = getattr(args, 'until', None)
    if not (since_value or until_value):
        return resource
    if scheme in _SINCE_UNTIL_AWARE_SCHEMES:
        if since_value and 'since=' not in resource and 'date>' not in resource:
            sep = '&' if '?' in resource else '?'
            resource = f"{resource}{sep}since={since_value}"
        if until_value and 'until=' not in resource and 'date<' not in resource:
            sep = '&' if '?' in resource else '?'
            resource = f"{resource}{sep}until={until_value}"
    else:
        flag = '--since' if since_value else '--until'
        aware = '/'.join(f'{s}://' for s in sorted(_SINCE_UNTIL_AWARE_SCHEMES))
        print(
            f"Note: {flag} has no effect on {scheme}:// -- only {aware} support it.",
            file=sys.stderr,
        )
    return resource


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
        _emit_adapter_error_envelope(scheme, resource, str(e), args)
        sys.exit(1)
    except Exception as e:
        print(f"Error initializing {scheme}:// adapter: {e}", file=sys.stderr)
        _emit_adapter_error_envelope(scheme, resource, f"initializing {scheme}:// adapter: {e}", args)
        sys.exit(1)

    # Apply --base-path override for adapters that support it (e.g., claude://)
    # REVEAL_CLAUDE_BASE_PATH env var acts as a persistent default for --base-path.
    path_override = getattr(args, 'base_path', None) or os.environ.get('REVEAL_CLAUDE_BASE_PATH')
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
            print_json_result(result)
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
        _render_element(adapter, renderer_class, element, resource, args, scheme=scheme)
    else:
        _render_structure(adapter, renderer_class, args, scheme=scheme, resource=resource)


def _handle_outline_mode(result: dict, args: 'Namespace', text_field: Optional[str], label: Any) -> bool:
    """--outline: render heading hierarchy in place of normal output (BACK-356)."""
    if not (getattr(args, 'outline', False) and text_field):
        return False
    from pathlib import Path as _Path
    from reveal.display.outline import build_heading_hierarchy, render_outline
    hierarchy = build_heading_hierarchy(_parse_text_headings(result[text_field]))
    if hierarchy:
        render_outline(hierarchy, _Path(str(label)))
    else:
        print(f"No headings found in {label}", file=sys.stderr)
    return True


def _handle_links_mode(result: dict, args: 'Namespace', text_field: Optional[str], label: Any) -> bool:
    """--links: render extracted links in place of normal output (BACK-357)."""
    if not (getattr(args, 'links', False) and text_field):
        return False
    from pathlib import Path as _Path
    from reveal.display.formatting import _format_links
    links = _parse_text_links(result[text_field])
    link_type = getattr(args, 'link_type', None)
    if link_type:
        links = [lnk for lnk in links if lnk['type'] == link_type]
    domain = getattr(args, 'domain', None)
    if domain:
        links = [lnk for lnk in links if domain.lower() in lnk.get('url', '').lower()]
    if links:
        _format_links(links, _Path(str(label)), getattr(args, 'format', 'text'))
    else:
        print(f"No links found in {label}", file=sys.stderr)
    return True


def _handle_frontmatter_mode(result: dict, args: 'Namespace', text_field: Optional[str], label: Any) -> bool:
    """--frontmatter: render parsed YAML frontmatter in place of normal output (BACK-357)."""
    if not (getattr(args, 'frontmatter', False) and text_field):
        return False
    from reveal.display.formatting import _format_frontmatter
    try:
        fm = _parse_text_frontmatter(result[text_field])
    except ValueError as e:
        print(f"Error: {label} has a frontmatter block that failed to parse: {e}", file=sys.stderr)
        return True
    if fm is not None:
        _format_frontmatter(fm)
    else:
        print(f"No YAML frontmatter found in {label}", file=sys.stderr)
    return True


# Registry of alternate element-rendering modes (BACK-360). Each handler inspects
# its own args flag and returns True if it rendered output (caller should stop),
# False to fall through to the next handler / normal rendering. Order matters only
# in that the flags are mutually exclusive in the CLI parser, so at most one fires.
_ELEMENT_RENDER_MODES = [
    _handle_outline_mode,
    _handle_links_mode,
    _handle_frontmatter_mode,
]


def _print_help_not_found_hints(adapter, element_name: str, section: Optional[str]) -> None:
    """Route a lost agent back into discovery on an unknown help:// topic.

    Two distinct cases, distinguished so the hint is never misleading:

    * **Section-extraction attempt** (`help://<known-topic>/<heading>`): the base
      topic exists but positional `/section` syntax isn't supported — point at the
      real `--section` flag with the intended heading (BACK-654).
    * **Mistyped / unknown topic** (everything else): suggest the closest known
      topics and the two discovery entry points, instead of a nonsensical
      `--section` retry of the same bogus string (BACK-692). Dead-ending here — the
      one moment an agent is most lost — is the worst place to offer no way back.
    """
    help_topics = getattr(adapter, 'help_topics', {})
    base = element_name.split('/', 1)[0]

    if '/' in element_name and base in help_topics and not section:
        heading = element_name.split('/', 1)[1]
        print(
            f"Hint: help:// needs an explicit flag for section extraction — try "
            f"reveal 'help://{base}' --section {heading!r}",
            file=sys.stderr,
        )
        return

    if hasattr(adapter, 'suggest_topics'):
        matches = adapter.suggest_topics(element_name)
        if matches:
            print(
                f"Hint: did you mean {' or '.join(repr(m) for m in matches)}?",
                file=sys.stderr,
            )
    print(
        "Lost? reveal 'help://quick' for orientation, or reveal 'help://' for the full index.",
        file=sys.stderr,
    )


def _render_element(adapter, renderer_class: type[Any], element: Optional[str],
                    resource: str, args: 'Namespace', scheme: Optional[str] = None) -> None:
    """Render a specific element from adapter.

    Args:
        adapter: Adapter with get_element() method
        renderer_class: Renderer for element output
        element: Element name (or None to use resource)
        resource: Fallback element name if element is None
        args: CLI arguments
        scheme: URI scheme (used to tailor the not-found hint, e.g. help://)
    """
    element_name = element if element else resource
    element_kwargs = {}
    section = getattr(args, 'section', None)
    if section:
        element_kwargs['section'] = section
    result = adapter.get_element(element_name, **element_kwargs)

    if result is None:
        print(f"Error: Element '{element_name}' not found", file=sys.stderr)
        # Try to show available elements if adapter provides them
        if hasattr(adapter, 'list_elements'):
            elements = adapter.list_elements()
            print(f"Available elements: {', '.join(elements)}", file=sys.stderr)
        if scheme == 'help':
            _print_help_not_found_hints(adapter, element_name, section)
        sys.exit(1)

    # Apply --head/--tail to text-body content (BACK-355).
    # Probe canonical field names; first match wins.
    head = getattr(args, 'head', None)
    tail = getattr(args, 'tail', None)
    if (head or tail) and isinstance(result, dict):
        for field in ('content', 'body'):
            if field in result and isinstance(result[field], str):
                lines = result[field].splitlines()
                if head:
                    lines = lines[:head]
                else:
                    lines = lines[-tail:]
                result = {**result, field: '\n'.join(lines)}
                break

    # --outline / --links / --frontmatter: alternate rendering modes on text-body
    # content (BACK-356, BACK-357), dispatched via the _ELEMENT_RENDER_MODES
    # registry (BACK-360). At most one fires since the CLI flags are mutually
    # exclusive.
    if isinstance(result, dict):
        _text_field = next(
            (f for f in ('content', 'body') if f in result and isinstance(result[f], str)),
            None,
        )
        _label = result.get('topic') or result.get('source') or result.get('name') or _text_field

        for _mode in _ELEMENT_RENDER_MODES:
            if _mode(result, args, _text_field, _label):
                return

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

    # Auto-discover: any get_structure() param whose name matches an args attribute
    # and hasn't already been populated above — eliminates the need to hand-maintain
    # param_mapping for every new CLI flag (BACK-354).
    _skip = set(param_mapping.values()) | {'uri', 'self'}
    for param_name, param in sig.parameters.items():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if param_name in _skip or param_name in kwargs:
            continue
        value = getattr(args, param_name, None)
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
    except NotApplicableError as e:
        # BACK-1210: the query genuinely doesn't apply to this target (no
        # tests, not a git repo) -- a recorded result, not a failure.
        _emit_not_applicable_envelope(scheme or 'unknown', resource or '', e.reason, args)
        return
    except Exception as e:
        error_msg = str(e)
        if '\n' in error_msg:
            print(f"Error: {error_msg}", file=sys.stderr)
        else:
            scheme_hint = f" ({scheme}://)" if scheme else ""
            print(f"Error{scheme_hint}: {error_msg}", file=sys.stderr)
        _emit_adapter_error_envelope(scheme or 'unknown', resource or '', error_msg, args)
        sys.exit(1)

    # Apply post-processing
    result = _apply_field_selection(result, args)
    result = _apply_budget_constraints(result, args, adapter)
    post_process = getattr(type(adapter), 'post_process', None)
    if post_process is not None:
        try:
            result = adapter.post_process(result, args)
        except NotApplicableError as e:
            _emit_not_applicable_envelope(scheme or 'unknown', resource or '', e.reason, args)
            return
        except Exception as e:
            error_msg = str(e)
            if '\n' in error_msg:
                print(f"Error: {error_msg}", file=sys.stderr)
            else:
                scheme_hint = f" ({scheme}://)" if scheme else ""
                print(f"Error{scheme_hint}: {error_msg}", file=sys.stderr)
            _emit_adapter_error_envelope(scheme or 'unknown', resource or '', error_msg, args)
            sys.exit(1)

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
