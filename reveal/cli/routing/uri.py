"""URI adapter dispatch for reveal CLI.

Handles routing from URI schemes (env://, ast://, help://, etc.)
to the appropriate adapter + renderer pair.
"""

import logging
import os
import re
import sys
from typing import Any, List, Optional, TYPE_CHECKING
from urllib.parse import parse_qs

from ...errors import NotApplicableError
from ...utils import print_json_result, write_also_json
from .flag_specs import exclude_fragment, inject_query_flags, strip_result_control_keys
from .formats import declared_output_formats, require_supported_format

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

    # --sort/--limit/--since/--until/... become query fragments here (flag_specs.FLAG_SPECS);
    # a value already in the URI wins over the flag.
    resource = _inject_exclude_flag(resource, scheme, args)
    resource = inject_query_flags(resource, scheme, args)
    _warn_unsupported_structural_flags(resource, scheme, args)

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

    # BACK-1385: sort=/limit=/offset= typed on an adapter that cannot receive them would be glued
    # onto its resource ("Element '?limit=2' not found"). Strip them with the same warning every
    # other adapter gives an unsupported param, and run the query.
    resource, stripped_keys = strip_result_control_keys(resource, adapter_class)
    if stripped_keys:
        from ...utils.query_parser import warn_unknown_query_params
        schema = adapter_class.get_schema() if hasattr(adapter_class, 'get_schema') else None
        if isinstance(schema, dict):
            known = schema.get('query_params') or {}
            warn_unknown_query_params(dict.fromkeys(stripped_keys, True), known, adapter=scheme)
        else:  # no schema: do not claim "Valid params: (none)" (help://search takes search=)
            for key in stripped_keys:
                print(f"⚠ Unknown query param '{key}' for {scheme}:// — ignored.", file=sys.stderr)

    # Dispatch to scheme-specific handler. BACK-1257: the --exclude walk scope
    # _inject_exclude_flag published is process-global, so it must not outlive
    # this dispatch -- under the MCP server (one long-lived process, many
    # requests over different trees) a leaked scope would silently filter an
    # unrelated later query.
    # BACK-1386: ?respect_gitignore= (typed, or injected from --no-gitignore)
    # applies to every walker for this dispatch.
    from ...utils.exclusions import clear_active_exclusions
    from ...utils.gitignore import gitignore_scope, split_respect_gitignore
    resource, respect_gitignore = split_respect_gitignore(resource)
    try:
        with gitignore_scope(respect_gitignore):
            handle_adapter(adapter_class, scheme, resource, element, args)
    finally:
        clear_active_exclusions()


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
    # BACK-1266 follow-up (2026-09-02): pack:// already reads its own
    # ?exclude= (BACK-1196, same comma-separated format as overview's) all
    # the way through _collect_candidates -> _walk_files' own
    # should_skip_file() check -- which handles file-shaped patterns
    # (*.min.js), not just directory-shaped ones. It just never received the
    # CLI --exclude flag because this set predates BACK-1196 having its own
    # query param wired up.
    _EXCLUDE_AWARE_SCHEMES = {'overview', 'stats', 'pack'}
    exclude_values = list(getattr(args, 'exclude', None) or [])

    if exclude_values and scheme in _EXCLUDE_AWARE_SCHEMES and 'exclude=' not in resource:
        sep = '&' if '?' in resource else '?'
        resource = f"{resource}{sep}{exclude_fragment(exclude_values)}"

    # BACK-1257: every other path-walking scheme gets exclusion by publishing
    # the scope for the shared directory-pruning predicate (see
    # utils/exclusions.py), rather than 13+ per-adapter query params. Schemes
    # whose resource is not a filesystem path (env://, help://, git://,
    # sqlite://, ssl://, ...) never walk, so they keep the advisory.
    from pathlib import Path as _Path
    from ...utils.exclusions import set_active_exclusions
    # An empty resource (env://, help://) is not "the current directory" for
    # this purpose -- it means the scheme takes no path at all, so it must fall
    # through to the advisory rather than silently accepting a scope it will
    # never consult.
    target_str = resource.partition('?')[0]
    target = _Path(target_str) if target_str else None
    walk_root = None
    if target is not None and target.exists():
        walk_root = target if target.is_dir() else target.parent

    # BACK-1266: REVEAL_IGNORE / config.yaml 'ignore:' patterns were parsed
    # into RevealConfig and wired into _walk_code_files (the subcommand-form
    # walker `check` uses) under BACK-1201, but every URI-form adapter routes
    # directory pruning through is_skippable_dir instead -- which BACK-1257
    # taught to consult --exclude but not REVEAL_IGNORE, so the env var
    # stayed silently unhonored on ast:///calls:///hotspots:// etc. exactly
    # the way --exclude was before that fix. Merged in here, once at
    # dispatch, onto the same active-scope plumbing rather than a second
    # matcher. Discovered relative to the walk root (matching
    # _walk_code_files' own RevealConfig.get(start_path=...)), not cwd.
    from ...config import RevealConfig
    ignore_values = RevealConfig.get(start_path=walk_root).ignore_patterns()
    combined_values = exclude_values + [p for p in ignore_values if p not in exclude_values]

    if not combined_values:
        return resource
    if walk_root is not None:
        set_active_exclusions(walk_root, combined_values)
    elif exclude_values and scheme not in _EXCLUDE_AWARE_SCHEMES:
        print(
            f"Note: --exclude has no effect on {scheme}:// -- it does not walk a "
            f"filesystem tree. Pre-filter the target or scope to a narrower path.",
            file=sys.stderr,
        )
    return resource


# BACK-1202: --depth/--ext/--type/--fast have real, documented semantics for
# bare path scans (routing/file.py) but no URI adapter's get_structure()
# declares a matching parameter and none reads the matching query_params key
# either -- unlike --exclude/--since/--until/--respect-gitignore above, there
# is no adapter-side support to inject into, so the honest fix is a warning
# (same convention as the --grep/BACK-351 and markdown --links/BACK-357 notes
# in handle_uri()) rather than a silent drop or a guessed semantic.
# Compared against the parser's own default, so "was this actually typed" can be told
# apart from "left at default" (--depth 0 must count as set, not falsy).
_STRUCTURAL_FLAGS = ('depth', 'ext', 'type', 'fast')


def _warn_unsupported_structural_flags(resource: str, scheme: str, args: 'Namespace') -> None:
    """Warn when --depth/--ext/--type/--fast were explicitly set but this
    scheme's adapter has no way to honor them (BACK-1202).

    A flag whose value is already carried in the URI query is honored, not
    ignored: 'reveal file.py --type function' is routed as
    ast://file.py?type=function, and warning there told the user to run the
    very command they ran."""
    from ..defaults import _parser_defaults
    defaults = _parser_defaults()
    query = parse_qs(resource.partition('?')[2], keep_blank_values=True)
    ignored = [
        f'--{flag_name}' for flag_name in _STRUCTURAL_FLAGS
        if getattr(args, flag_name, defaults[flag_name]) != defaults[flag_name]
        and str(getattr(args, flag_name)) not in query.get(flag_name, [])
    ]
    if not ignored:
        return
    from ...adapters.base import get_adapter_class
    adapter_class = get_adapter_class(scheme)
    get_structure = getattr(adapter_class, 'get_structure', None) if adapter_class else None
    if get_structure is None:
        return
    import inspect
    try:
        params = inspect.signature(get_structure).parameters
    except (TypeError, ValueError):
        return
    still_ignored = [
        flag for flag in ignored
        if flag.lstrip('-') not in params
    ]
    if still_ignored:
        print(
            f"Note: {', '.join(still_ignored)} has no effect on {scheme}:// "
            f"queries -- not supported by this adapter. Use a bare path scan "
            f"(reveal <path> {' '.join(still_ignored)}) instead.",
            file=sys.stderr,
        )


def _reject_missing_path(adapter_class: type, scheme: str, resource: str, args: 'Namespace') -> None:
    """Exit 1 when a path-taking adapter (RESOURCE_IS_PATH) is given a path that
    does not exist (BACK-1321). One shared check instead of per-adapter ones, so
    a typo'd path can no longer read as a clean empty result with exit 0."""
    if getattr(adapter_class, 'RESOURCE_IS_PATH', False) is not True:
        return
    path = resource.partition('?')[0]
    resolve = getattr(adapter_class, 'resource_path', None)  # BACK-1499: calls:// path:name
    if resolve is not None:
        path = resolve(path)
    if not path or os.path.exists(path):
        return
    msg = f"Path not found: {path}"
    print(f"Error ({scheme}://): {msg}", file=sys.stderr)
    if getattr(args, 'format', 'text') == 'json':
        _emit_adapter_error_envelope(scheme, resource, msg, args)
    sys.exit(1)


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
    _reject_missing_path(adapter_class, scheme, resource, args)
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

    # An adapter may carry the element inside its resource (diff://a.py:b.py/func).
    embedded = getattr(adapter, 'embedded_element', None)
    if not element and isinstance(embedded, str):
        element = embedded

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
    add_if_supported('severity')
    add_if_supported('only_failures')

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
    write_also_json(result, args)

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
    require_supported_format(args, declared_output_formats(type(adapter)), f"{scheme}://")

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


def _adapter_error_text(e: Exception, scheme: Optional[str]) -> str:
    """One-line ``Error (scheme://): msg`` text; multi-line messages print bare."""
    error_msg = str(e)
    if '\n' in error_msg:
        return f"Error: {error_msg}"
    scheme_hint = f" ({scheme}://)" if scheme else ""
    return f"Error{scheme_hint}: {error_msg}"


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
    try:
        result = adapter.get_element(element_name, **element_kwargs)
    except NotApplicableError as e:
        _emit_not_applicable_envelope(scheme or 'unknown', resource, e.reason, args)
        return
    except Exception as e:
        print(_adapter_error_text(e, scheme), file=sys.stderr)
        _emit_adapter_error_envelope(scheme or 'unknown', resource or '', str(e), args)
        sys.exit(1)

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

    write_also_json(result, args)
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

    # Any get_structure() param whose name matches an args attribute is filled from it
    # (BACK-354); nothing to hand-maintain when a CLI flag is added.
    _skip = {'uri', 'self'}
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


def _budget_list_fields(result: dict, adapter=None) -> list[str]:
    """The sliceable list fields present on a structure result.

    Adapter declares them via BUDGET_LIST_FIELD (one name, or a tuple for a result
    with several lists, e.g. hotspots://); falls back to probing for adapters that
    predate it (transition period only). A declared field missing from this result
    (another mode's shape) yields nothing -- never a guess at other lists (BACK-1497).
    """
    declared = getattr(adapter, 'BUDGET_LIST_FIELD', None) if adapter is not None else None
    if declared:
        names = ((declared,) if isinstance(declared, str)
                 else tuple(declared) if isinstance(declared, (tuple, list)) else ())
        return [name for name in names if isinstance(result.get(name), list)]
    for field_name in ['items', 'results', 'checks', 'commits', 'files']:
        if isinstance(result.get(field_name), list):
            return [field_name]
    return []


def _find_budget_list_field(result: dict, adapter=None) -> Optional[str]:
    """The one list --max-items/--max-snippet-chars apply to; None when a result has
    several (BACK-1498 tracks budgeting those)."""
    fields = _budget_list_fields(result, adapter)
    return fields[0] if len(fields) == 1 else None


def _apply_budget_constraints(result: dict, args: 'Namespace', adapter=None) -> dict:
    """Apply budget constraints to result list fields."""
    if not isinstance(result, dict):
        return result

    list_field = _find_budget_list_field(result, adapter)
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


def _slice_items(items: list, head, tail, range_) -> list:
    if head:
        return items[:head]
    if tail:
        return items[-tail:]
    start, end = range_
    return items[max(start - 1, 0):end]


def _apply_head_tail_range(result: dict, args: 'Namespace', adapter=None,
                           scheme: Optional[str] = None) -> dict:
    """Apply --head/--tail/--range to a directory-shaped URI structure result.

    BACK-1204: these flags already worked on bare-file structural listings
    (display/formatting.py forwards them into analyzer.get_structure()) and
    on element/text-body retrieval (BACK-355, uri.py's _render_element), but
    were a silent no-op specifically on a URI adapter's structure()-level
    list results (e.g. ast://<dir>'s 'results' field) -- confirmed live:
    'reveal ast://. --head 1 --format json' returned len(results)=200
    unchanged with or without --head 1. Mirrors _apply_budget_constraints's
    field-discovery (BUDGET_LIST_FIELD / probe fallback) since it's the same
    "which field is the sliceable list" question.

    BACK-1497: an adapter whose result holds several lists (hotspots:// file +
    function hotspots, reveal:// analyzers/adapters/rules) declares them all in
    BUDGET_LIST_FIELD and each is sliced. An adapter that declares nothing and has no
    probe-able list says the flag had no effect instead of returning unchanged in
    silence; one that declares a field this result lacks stays silent, since it may
    apply the flag itself (claude:// does, in post_process).
    """
    if not isinstance(result, dict):
        return result

    head = getattr(args, 'head', None)
    tail = getattr(args, 'tail', None)
    range_ = getattr(args, 'range', None)
    if not (head or tail or range_):
        return result

    fields = _budget_list_fields(result, adapter)
    flag = '--head' if head else '--tail' if tail else '--range'
    if not fields:
        if getattr(adapter, 'BUDGET_LIST_FIELD', None) is None:
            print(f"Note: {flag} has no effect on {scheme or 'this'}:// -- its result has no "
                  f"list to slice.", file=sys.stderr)
        return result
    for field in fields:
        result[field] = _slice_items(result[field], head, tail, range_)
    if len(fields) > 1:
        print(f"Note: {flag} applied to each of {', '.join(fields)} -- {scheme or 'this'}:// "
              f"returns several lists.", file=sys.stderr)
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
        print(_adapter_error_text(e, scheme), file=sys.stderr)
        _emit_adapter_error_envelope(scheme or 'unknown', resource or '', str(e), args)
        sys.exit(1)

    # Apply post-processing
    result = _apply_field_selection(result, args)
    result = _apply_head_tail_range(result, args, adapter, scheme)
    result = _apply_budget_constraints(result, args, adapter)
    post_process = getattr(type(adapter), 'post_process', None)
    if post_process is not None:
        try:
            result = adapter.post_process(result, args)
        except NotApplicableError as e:
            _emit_not_applicable_envelope(scheme or 'unknown', resource or '', e.reason, args)
            return
        except Exception as e:
            print(_adapter_error_text(e, scheme), file=sys.stderr)
            _emit_adapter_error_envelope(scheme or 'unknown', resource or '', str(e), args)
            sys.exit(1)

    # Add available elements if adapter supports discovery
    if hasattr(adapter, 'get_available_elements'):
        available_elements = adapter.get_available_elements()
        if available_elements:
            result['available_elements'] = available_elements

    write_also_json(result, args)
    renderer_class.render_structure(result, args.format, **_render_structure_top_kwargs(renderer_class, args))


def _render_structure_top_kwargs(renderer_class: type, args: 'Namespace') -> dict:
    """Forward --all/--verbose to render_structure() for overview:// only (BACK-1226).

    render_structure(result, args.format) never passed args.top/all/verbose through
    for ANY URI-invoked renderer, so overview://'s per-section caps (Components,
    Entry points, Language, Hotspots) were unreachable via --all/--verbose and even
    via a working ?top=N query string (the resolved top never left get_structure()).

    Scoped to renderers that declare ACCEPTS_TOP (only OverviewRenderer) rather than fixed generically: sibling
    renderers declare differently-typed/shaped 'top' params (hotspots.py top:int=10,
    deps.py top:int=10, architecture.py top:int=5 plus a second no_imports param,
    contracts.py/trace.py have no top param at all) that were never designed to
    receive a value from here, and forwarding blind would either crash them or
    silently change behavior nobody asked this ticket to touch.
    """
    if getattr(renderer_class, 'ACCEPTS_TOP', False) is not True:
        return {}
    if getattr(args, 'all', False) or getattr(args, 'verbose', False):
        from ...adapters.overview import UNLIMITED_TOP
        return {'top': UNLIMITED_TOP}
    return {}

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
