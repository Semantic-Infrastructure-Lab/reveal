"""URI adapter dispatch for reveal CLI.

Handles routing from URI schemes (env://, ast://, help://, etc.)
to the appropriate adapter + renderer pair.
"""

import logging
import os
import re
import sys
from argparse import Namespace
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Iterator, List, NoReturn, Optional, Tuple

from ...errors import NotApplicableError
from ...reveal_types import CONTRACT_VERSION, RevealResult
from ...utils import print_json_result, write_also_json
from ...display.formatting import print_truncations
from ...utils.results import (Outcome, ResultBuilder, echo_source, note_truncation, outcome_of,
                             slice_items, truncations_of)
from .flag_specs import exclude_fragment, inject_query_flags, strip_result_control_keys
from .ledger import FlagLedger, complete, delegate, ledger_of, mark, peek
from .formats import declared_output_formats, require_supported_format

logger = logging.getLogger(__name__)


@dataclass
class Answer:
    """One URI query's answer, before anything is printed (BACK-1554).

    ``kind`` is the call that produced ``result``: 'structure', 'element', 'check', or
    'router' when the router built it (the adapter raised, declined, or has no such
    element). ``emit`` prints it the way the CLI does and exits as its outcome says.
    handle_uri emits; stdin --batch reads ``result`` and aggregates, so both answer a URI
    through the same resolution.
    """
    result: Any
    kind: str
    emit: Callable[[], None]


class _Answered(Exception):
    """Ends resolution with a result the router built (_fail, _decline). _answer turns it
    into the query's Answer, so a query that stops early is answered like one that ends."""

    def __init__(self, result: RevealResult, detail: Optional[Callable[[], None]] = None):
        super().__init__(result.get('error') or result.get('reason'))
        self.result = result
        self.detail = detail


class UriUsageError(Exception):
    """The query is malformed before any adapter is chosen: no ``://``, an unknown scheme.
    handle_uri prints it on stderr and exits 1, like argparse (BACK-1553 decision);
    resolve_uri raises it, so a batch records it and goes on."""

    def __init__(self, message: str, hint: str = ''):
        super().__init__(message)
        self.message = message
        self.hint = hint


def _call_adapter(call: Callable[[], Any], scheme: str, resource: str,
                  adapter_class: Any = None) -> Any:
    """Run one call into an adapter; what it raises becomes a result like any returned one.

    Every call the router makes into an adapter goes through here: constructing it,
    --base-path, check(), get_element(), get_structure() and post_process(). A raise ends
    the query as a failed result (exit 1), and a NotApplicableError as a not-applicable one
    (exit 0, BACK-1210), so both read the same as a returned result: one stderr line, one
    JSON envelope, --also-json written. Each site used to catch for itself, print its own
    error line (three spellings) and hand-build its own envelope, so a raised error printed
    twice in text, carried contract_version 1.0 and source_type 'file', and wrote no
    --also-json (BACK-1553). The result leaves as an _Answered, not an exit, so stdin
    --batch gets it as a result too (BACK-1554).
    """
    try:
        return call()
    except NotApplicableError as e:
        _decline(scheme, resource, e.reason, adapter_class)
    except Exception as e:  # not silent: the query ends as a failed result (_fail)
        logger.debug('%s:// adapter call raised', scheme, exc_info=True)
        _fail(scheme, resource, _exception_message(e), adapter_class=adapter_class)


def _exception_message(e: Exception) -> str:
    """The error text for a raised exception. The router prints ``Error (scheme://): ``, so a
    message's own leading ``Error: `` (RevealError.__str__ adds one) is dropped. An exception
    with no message is named by its type: an empty ``error`` would read as success."""
    message = str(e).strip()
    if message.startswith('Error: '):
        message = message[len('Error: '):]
    return message or type(e).__name__


def _source_type_of(resource: str, adapter_class: Any = None) -> str:
    """What a result the router builds says its source is. Only an existing directory or file
    is known; anything else (a missing path, a ref, a host, an env var) is 'unknown', not
    the 'file' that auto-detection on a nonexistent path would claim."""
    path = resource.partition('?')[0]
    resolve = getattr(adapter_class, 'resource_path', None) if isinstance(adapter_class, type) else None
    if resolve is not None:  # calls:// path:name (BACK-1499)
        path = resolve(path)
    if path and os.path.isdir(path):
        return 'directory'
    if path and os.path.isfile(path):
        return 'file'
    return 'unknown'


def _router_result(scheme: str, resource: str, adapter_class: Any = None, **fields: Any) -> RevealResult:
    """The result the router builds when an adapter gave none: it raised, declined, or has no
    such element. ``type`` is the scheme."""
    return ResultBuilder.create(
        result_type=scheme,
        source=resource,
        contract_version=CONTRACT_VERSION,
        source_type=_source_type_of(resource, adapter_class),
        **fields,
    )


def _fail(scheme: str, resource: str, message: str, *,
          adapter_class: Any = None, code: str = 'adapter_error',
          detail: Optional[Callable[[], None]] = None, **fields: Any) -> NoReturn:
    """End the query with an error result; emitted, it exits 1 (_emit_result).

    ``meta.errors`` carries the error once more with a code (``adapter_error`` for a raise,
    ``element_not_found``, ...), which is how JSON tells a router-built failure from one an
    adapter returned. ``detail`` prints hints after the error line, on stderr, in text only.
    """
    result = _router_result(scheme, resource, adapter_class,
                            errors=[{'code': code, 'message': message}], error=message, **fields)
    raise _Answered(result, detail)


def _decline(scheme: str, resource: str, reason: str, adapter_class: Any = None) -> NoReturn:
    """End the query 'not applicable' when it genuinely does not apply to the target
    (testability:// with no tests, git:// outside a repository): a recorded answer that
    exits 0, not a failure (BACK-1210)."""
    result = _router_result(scheme, resource, adapter_class,
                            warnings=[{'code': 'not_applicable', 'message': reason}],
                            applicable=False, reason=reason)
    raise _Answered(result)


def _answer(resolve: Callable[[], Answer], scheme: str, args: 'Namespace') -> Answer:
    """Run one resolution; a query it ended early (_Answered) is answered by the router's result."""
    try:
        return resolve()
    except _Answered as e:
        result, detail = e.result, e.detail  # `e` is unbound once the handler ends
    return Answer(result, 'router',
                  lambda: _emit_result(result, args, scheme, _render_router_result, detail=detail))


def _render_router_result(result: Any, output_format: str,
                          detail: Optional[Callable[[], None]] = None) -> None:
    """Render a result the router built. JSON is the envelope. Text says 'not applicable' on
    stdout, since that is the answer; for a failure it prints nothing on stdout, as for an
    error an adapter returns, because _emit_result has already printed the error line on
    stderr. BACK-1209 had a raised error also print a copy on stdout, so the error printed
    twice; its reason, a scripted consumer finding no artifact, is met by the JSON envelope
    and --also-json."""
    if output_format == 'json':
        print_json_result(result)
        return
    if outcome_of(result) == 'not_applicable':
        print(f"({result['type']}://) not applicable: {result['reason']}")
    elif detail is not None:
        detail()


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


def handle_uri(uri: str, element: Optional[str], args: 'Namespace',
               consumed: Iterable[str] = ()) -> None:
    """Answer a URI query (env://, ast://, ...) and print it.

    Args:
        uri: Full URI (e.g., env://, env://PATH)
        element: Optional element to extract
        args: Parsed command line arguments
        consumed: Flags the caller applied itself (``--stdin``), so the flag ledger does not
            report them as having no effect on the adapter
    """
    try:
        with _dispatch(uri, element, args, consumed) as (adapter_class, scheme, resource, args):
            handle_adapter(adapter_class, scheme, resource, element, args)
    except UriUsageError as e:
        print(f"Error: {e.message}", file=sys.stderr)
        if e.hint:
            print(e.hint, file=sys.stderr)
        sys.exit(1)


def resolve_uri(uri: str, args: 'Namespace', consumed: Iterable[str] = ()) -> Answer:
    """Answer a URI query without printing it (BACK-1554), for callers that aggregate
    several (stdin --batch). The same dispatch as handle_uri: the flag injection, the walk
    scope and the flag ledger, from_uri, the missing-path check, check() arguments, and
    element lookup, with a raise or a missing element as a failed result. Raises
    UriUsageError for a URI with no ``://`` or an unknown scheme.
    """
    with _dispatch(uri, None, args, consumed) as (adapter_class, scheme, resource, args):
        return resolve_adapter(adapter_class, _renderer_class_of(scheme), scheme, resource,
                               None, args)


@contextmanager
def _dispatch(uri: str, element: Optional[str], args: 'Namespace',
              consumed: Iterable[str]) -> Iterator[Tuple[type, str, str, 'Namespace']]:
    """Everything around one adapter dispatch: parse the URI, start its flag ledger, inject
    flags into the query, look up the adapter, and hold the walk scope while the body runs.
    Yields (adapter class, scheme, final resource, tracked args); the ledger reports when
    the body ends without an error exit."""
    if '://' not in uri:
        raise UriUsageError(f"Invalid URI format: {uri}")

    scheme, resource = uri.split('://', 1)

    # BACK-1514: every flag and query key the user set is used by this dispatch or named in
    # one note at the end (see ledger.py). A nested call shares the outer call's ledger.
    ledger = None
    if ledger_of(args) is None and isinstance(args, Namespace):
        ledger = FlagLedger(args)
        args = ledger.track(args)
        mark(args, *consumed)

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

    # Look up adapter from registry
    from ...adapters.base import get_adapter_class, list_supported_schemes
    # Import adapters package to trigger all registrations (single source of truth)
    from ... import adapters as _adapters  # noqa: F401

    adapter_class = get_adapter_class(scheme)
    if not adapter_class:
        schemes = ', '.join(f"{s}://" for s in list_supported_schemes())
        raise UriUsageError(f"Unsupported URI scheme: {scheme}://",
                            f"Supported schemes: {schemes}")

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
            if ledger is None:
                yield adapter_class, scheme, resource, args
            else:
                with ledger.dispatching(resource):
                    yield adapter_class, scheme, resource, args
                ledger.complete = True
    finally:
        clear_active_exclusions()
        if ledger is not None and ledger.complete:
            ledger.report(scheme)


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
    exclude_values = list(peek(args, 'exclude') or [])

    if exclude_values and scheme in _EXCLUDE_AWARE_SCHEMES and 'exclude=' not in resource:
        sep = '&' if '?' in resource else '?'
        resource = f"{resource}{sep}{exclude_fragment(exclude_values)}"
        delegate(args, 'exclude', 'exclude')

    # BACK-1257: every other path-walking scheme gets exclusion by publishing
    # the scope for the shared directory-pruning predicate (see
    # utils/exclusions.py), rather than 13+ per-adapter query params. Schemes
    # whose resource is not a filesystem path (env://, help://, git://,
    # sqlite://, ssl://, ...) never walk, so they keep the advisory.
    # BACK-1266: the scope also carries REVEAL_IGNORE / config 'ignore:'.
    from ...utils.exclusions import dispatch_scope, set_active_exclusions
    walk_root, combined_values = dispatch_scope(resource.partition('?')[0], exclude_values)

    if not combined_values:
        return resource
    if walk_root is not None:
        # Used only if a walk consults the scope (the ledger checks exclusions_consulted).
        set_active_exclusions(walk_root, combined_values)
    elif exclude_values and scheme not in _EXCLUDE_AWARE_SCHEMES:
        mark(args, 'exclude')
        print(
            f"Note: --exclude has no effect on {scheme}:// -- it does not walk a "
            f"filesystem tree. Pre-filter the target or scope to a narrower path.",
            file=sys.stderr,
        )
    return resource


def _reject_missing_path(adapter_class: type, scheme: str, resource: str) -> None:
    """Fail the query when a path-taking adapter (RESOURCE_IS_PATH) is given a path that
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
    _fail(scheme, resource, f"Path not found: {path}", adapter_class=adapter_class)


def generic_adapter_handler(adapter_class: type, renderer_class: type[Any],
                           scheme: str, resource: str, element: Optional[str],
                           args: 'Namespace') -> None:
    """Answer a query on any adapter/renderer pair and print it.

    Args:
        adapter_class: The adapter class to instantiate
        renderer_class: The renderer class for output
        scheme: URI scheme (for building full URI if needed)
        resource: Resource part of URI
        element: Optional element to extract
        args: CLI arguments
    """
    # An unsupported --format is a usage error, so it comes before any adapter work. Check
    # mode renders through render_check, which declares no formats.
    if not _check_mode(adapter_class, args):
        require_supported_format(args, declared_output_formats(adapter_class), f"{scheme}://")
    resolve_adapter(adapter_class, renderer_class, scheme, resource, element, args).emit()


def resolve_adapter(adapter_class: type, renderer_class: type[Any], scheme: str,
                    resource: str, element: Optional[str], args: 'Namespace') -> Answer:
    """Answer a query on an adapter without printing it (see resolve_uri)."""
    return _answer(lambda: _resolve(adapter_class, renderer_class, scheme, resource, element, args),
                   scheme, args)


def _check_mode(adapter: Any, args: 'Namespace') -> bool:
    """Whether this query runs the adapter's check(): --check, or a flag the adapter
    lists in CHECK_IMPLIED_BY because it means nothing outside one (BACK-1593:
    `ssl://host --expiring-within 30`, the form the docs teach, was a no-op)."""
    if not hasattr(adapter, 'check'):
        return False
    implied = getattr(adapter, 'CHECK_IMPLIED_BY', ())
    implied = implied if isinstance(implied, tuple) else ()  # as _declared() does: a Mock has every attr
    return bool(peek(args, 'check', False)) or any(peek(args, flag) is not None for flag in implied)


def _resolve(adapter_class: type, renderer_class: type[Any], scheme: str, resource: str,
             element: Optional[str], args: 'Namespace') -> Answer:
    # Initialize adapter via from_uri.  Use _default_from_uri when adapter_class is
    # not a real type (e.g. a Mock callable in tests) or lacks from_uri.
    from ...adapters.base import _default_from_uri
    _reject_missing_path(adapter_class, scheme, resource)
    if isinstance(adapter_class, type) and hasattr(adapter_class, 'from_uri'):
        adapter = _call_adapter(lambda: adapter_class.from_uri(scheme, resource, element),
                                scheme, resource, adapter_class)
    else:
        adapter = _call_adapter(lambda: _default_from_uri(adapter_class, scheme, resource, element),
                                scheme, resource, adapter_class)

    # Apply --base-path override for adapters that support it (e.g., claude://)
    # REVEAL_CLAUDE_BASE_PATH env var acts as a persistent default for --base-path.
    path_override = peek(args, 'base_path') or os.environ.get('REVEAL_CLAUDE_BASE_PATH')
    if path_override and hasattr(adapter, 'reconfigure_base_path'):
        mark(args, 'base_path')
        from pathlib import Path as _Path
        _call_adapter(lambda: adapter.reconfigure_base_path(_Path(path_override)),
                      scheme, resource, adapter_class)

    if _check_mode(adapter, args):
        mark(args, 'check')
        return _check_answer(adapter, renderer_class, args, scheme, resource)

    # An adapter may carry the element inside its resource (diff://a.py:b.py/func).
    embedded = getattr(adapter, 'embedded_element', None)
    if not element and isinstance(embedded, str):
        element = embedded

    return _view_answer(adapter, renderer_class, scheme, resource, element, args)


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


def _handle_check_mode(adapter, renderer_class: type[Any], args: 'Namespace',
                       scheme: Optional[str] = None, resource: str = '') -> None:
    """Run check mode, print it and exit.

    Args:
        adapter: Initialized adapter with check() method
        renderer_class: Renderer for check results
        args: CLI arguments with check flags
        scheme: URI scheme, for the error result if check() raises
        resource: Resource part of the URI, likewise
    """
    _answer(lambda: _check_answer(adapter, renderer_class, args, scheme, resource),
            scheme or 'unknown', args).emit()


def _check_answer(adapter, renderer_class: type[Any], args: 'Namespace',
                  scheme: Optional[str] = None, resource: str = '') -> Answer:
    check_kwargs = _build_check_kwargs(adapter, args)
    result = _call_adapter(lambda: adapter.check(**check_kwargs),
                           scheme or 'unknown', resource, type(adapter))
    return Answer(result, 'check', lambda: _emit_check(result, adapter, renderer_class, args))


def _emit_check(result: Any, adapter, renderer_class: type[Any], args: 'Namespace') -> NoReturn:
    """Print a check result and exit with its own exit_code (EXIT_CODE_CONTRACT)."""
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
    complete(args)
    sys.exit(exit_code)


def _view_answer(adapter, renderer_class: type[Any], scheme: str,
                 resource: str, element: Optional[str], args: 'Namespace') -> Answer:
    """Answer with an element or the structure, as the adapter supports.

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
        return _element_answer(adapter, renderer_class, element, resource, args, scheme)
    return _structure_answer(adapter, renderer_class, args, scheme, resource)


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


def _fail_element_not_found(adapter, element_name: str, section: Optional[str], resource: str,
                            scheme: Optional[str]) -> NoReturn:
    """Fail an element lookup that found nothing. The adapter's element names go in the
    result (``available_elements``) and, in text, on stderr after the error; help:// adds its
    way back into discovery. This exit used to print on stderr only, so ``--format json``
    got 0 bytes on stdout and --also-json was never written (BACK-1553)."""
    elements = list(adapter.list_elements()) if hasattr(adapter, 'list_elements') else []

    def detail() -> None:
        if elements:
            print(f"Available elements: {', '.join(elements)}", file=sys.stderr)
        if scheme == 'help':
            _print_help_not_found_hints(adapter, element_name, section)

    extra = {'available_elements': elements} if elements else {}
    _fail(scheme or 'unknown', resource, f"Element '{element_name}' not found",
          adapter_class=type(adapter), code='element_not_found', detail=detail, **extra)


def _render_element(adapter, renderer_class: type[Any], element: Optional[str],
                    resource: str, args: 'Namespace', scheme: Optional[str] = None) -> None:
    """Answer with a specific element from adapter and print it.

    Args:
        adapter: Adapter with get_element() method
        renderer_class: Renderer for element output
        element: Element name (or None to use resource)
        resource: Fallback element name if element is None
        args: CLI arguments
        scheme: URI scheme (used to tailor the not-found hint, e.g. help://)
    """
    _answer(lambda: _element_answer(adapter, renderer_class, element, resource, args, scheme),
            scheme or 'unknown', args).emit()


def _element_answer(adapter, renderer_class: type[Any], element: Optional[str],
                    resource: str, args: 'Namespace', scheme: Optional[str] = None) -> Answer:
    element_name = element if element else resource
    element_kwargs = {}
    section = getattr(args, 'section', None)
    if section:
        element_kwargs['section'] = section
    result = _call_adapter(lambda: adapter.get_element(element_name, **element_kwargs),
                           scheme or 'unknown', resource or '', type(adapter))
    if result is None:
        _fail_element_not_found(adapter, element_name, section, resource or '', scheme)

    # Apply --head/--tail to text-body content (BACK-355).
    # Probe canonical field names; first match wins.
    head = peek(args, 'head')
    tail = peek(args, 'tail')
    if (head or tail) and isinstance(result, dict):
        for field in ('content', 'body'):
            if field in result and isinstance(result[field], str):
                mark(args, 'head', 'tail')
                lines = result[field].splitlines()
                if head:
                    lines = lines[:head]
                else:
                    lines = lines[-tail:]
                result = {**result, field: '\n'.join(lines)}
                break

    return Answer(result, 'element', lambda: _emit_element(result, renderer_class, args, scheme))


def _emit_element(result: Any, renderer_class: type[Any], args: 'Namespace',
                  scheme: Optional[str]) -> None:
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

    _emit_result(result, args, scheme, renderer_class.render_element)


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


def _apply_budget_constraints(result: dict, args: 'Namespace', adapter=None,
                              scheme: Optional[str] = None) -> dict:
    """Apply --max-items/--max-snippet-chars to a URI result's lists.

    Each list the adapter declares is cut and disclosed on its own, as --head's are
    (BACK-1497). A result with several lists (hotspots:// file and function hotspots,
    reveal:// analyzers/adapters/rules) was left whole, and the ledger said the flag had
    no effect where --head cut every list (BACK-1498). ``meta.budget`` and its cursor
    belong to a one-list result: a cursor is an offset into one list.
    """
    if not isinstance(result, dict):
        return result

    fields = _budget_list_fields(result, adapter)
    max_items = peek(args, 'max_items')
    if not fields or (max_items is None and peek(args, 'max_snippet_chars') is None):
        return result

    from reveal.utils.query import apply_budget_limits

    mark(args, 'max_items', 'max_snippet_chars')
    for field in fields:
        budget_result = apply_budget_limits(
            result[field], max_items=max_items,
            truncate_strings=peek(args, 'max_snippet_chars'))
        total = len(result[field])
        result[field] = budget_result['items']
        if budget_result['meta']['truncated']:
            _record_cut(result, field, total, 'max_items', sole=len(fields) == 1)
            if len(fields) == 1:
                result['meta']['budget'] = budget_result['meta']
    if len(fields) > 1 and max_items is not None:
        print(f"Note: --max-items applied to each of {', '.join(fields)} -- "
              f"{scheme or 'this'}:// returns several lists.", file=sys.stderr)
    return result


def _record_cut(result: dict, field: str, total: int, cause: str, sole: bool) -> None:
    """Disclose a cut the router made to ``result[field]`` (BACK-1059).

    ``--max-items`` and ``--head/--tail/--range`` slice a list after the adapter built its
    counts, so the result said "45 results" while holding 3, and text renderers showed
    the 3 as complete. The cut becomes a ``note_truncation`` entry, which the router
    prints; a sole list's ``displayed_results`` is corrected to what is left.
    """
    shown = len(result[field])
    note_truncation(result, field, shown, total, cause)
    if sole and shown < total and isinstance(result.get('displayed_results'), int):
        result['displayed_results'] = shown


def _apply_head_tail_range(result: dict, args: 'Namespace', adapter=None,
                           scheme: Optional[str] = None) -> dict:
    """Apply --head/--tail/--range to a directory-shaped URI structure result.

    BACK-1204: these flags already worked on bare-file structural listings
    (display/structure.py cuts the analyzer's result, BACK-1548) and
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

    head = peek(args, 'head')
    tail = peek(args, 'tail')
    range_ = peek(args, 'range')
    if not (head or tail or range_):
        return result

    fields = _budget_list_fields(result, adapter)
    flag = '--head' if head else '--tail' if tail else '--range'
    if not fields:
        # A declared field this result lacks: the adapter may apply the flag itself (claude://
        # reads args.head in post_process); if nothing does, the ledger's note says so.
        if getattr(adapter, 'BUDGET_LIST_FIELD', None) is None:
            mark(args, 'head', 'tail', 'range')
            print(f"Note: {flag} has no effect on {scheme or 'this'}:// -- its result has no "
                  f"list to slice.", file=sys.stderr)
        return result
    mark(args, 'head', 'tail', 'range')
    cause = flag.lstrip('-')
    for field in fields:
        total = len(result[field])
        result[field] = slice_items(result[field], head, tail, range_)
        _record_cut(result, field, total, cause, sole=len(fields) == 1)
    if len(fields) > 1:
        print(f"Note: {flag} applied to each of {', '.join(fields)} -- {scheme or 'this'}:// "
              f"returns several lists.", file=sys.stderr)
    return result


def _render_structure(adapter, renderer_class: type[Any], args: 'Namespace',
                      scheme: Optional[str] = None, resource: Optional[str] = None) -> None:
    """Answer with the full structure from adapter and print it.

    Args:
        adapter: Adapter with get_structure() method
        renderer_class: Renderer for structure output
        args: CLI arguments with optional filter parameters
        scheme: Optional URI scheme (for adapters that need full URI)
        resource: Optional resource string (for adapters that need full URI)
    """
    _answer(lambda: _structure_answer(adapter, renderer_class, args, scheme, resource),
            scheme or 'unknown', args).emit()


def _structure_answer(adapter, renderer_class: type[Any], args: 'Namespace',
                      scheme: Optional[str] = None, resource: Optional[str] = None) -> Answer:
    # Build adapter kwargs
    structure_kwargs = _build_adapter_kwargs(adapter, args, scheme, resource)

    # Get structure from adapter
    scheme_name, source = scheme or 'unknown', resource or ''
    result = _call_adapter(lambda: adapter.get_structure(**structure_kwargs),
                           scheme_name, source, type(adapter))

    # Apply post-processing
    result = _apply_field_selection(result, args)
    result = _apply_head_tail_range(result, args, adapter, scheme)
    result = _apply_budget_constraints(result, args, adapter, scheme)
    post_process = getattr(type(adapter), 'post_process', None)
    if post_process is not None:
        processed = result
        result = _call_adapter(lambda: adapter.post_process(processed, args),
                               scheme_name, source, type(adapter))

    _echo_source(result, type(adapter), resource)

    # Add available elements if adapter supports discovery
    if hasattr(adapter, 'get_available_elements'):
        available_elements = adapter.get_available_elements()
        if available_elements:
            result['available_elements'] = available_elements

    return Answer(result, 'structure',
                  lambda: _emit_result(result, args, scheme, renderer_class.render_structure,
                                       **_render_structure_top_kwargs(renderer_class, args)))


def _echo_source(result: Any, adapter_class: type, resource: Optional[str]) -> None:
    """Report ``source`` as the user named the target, for every adapter (BACK-1366)."""
    spelled = (resource or '').partition('?')[0]
    resource_path = getattr(adapter_class, 'resource_path', None)  # calls:// path:name
    echo_source(result, resource_path(spelled) if resource_path and spelled else spelled)


def _emit_result(result: Any, args: 'Namespace', scheme: Optional[str], render, **render_kwargs) -> None:
    """Render a URI result and turn its outcome into the exit code (BACK-1059).

    Every printed URI result, for the CLI and MCP alike, ends here (the emit of a
    structure, element or router-built Answer), so this is the one place a result's outcome
    becomes the exit code and the one place its error is reported; stdin --batch reads the
    same outcome from the unprinted Answer (BACK-1554). Before it, each adapter or renderer decided
    for itself: an error result from calls://, codex://, claude:// or json:// rendered and
    exited 0, which reads as success to a script or agent, and some text renderers dropped
    the error entirely (codex:// with no DB rendered "Codex Sessions: 0 total").

    The error line comes before the render, so renderers add only detail (an example, the
    valid names) and never print the error themselves. The exit comes after it, so
    --format json still prints the whole error envelope. A truncated result exits 0; what
    it left out is printed after the render (print_truncations).
    """
    outcome = announce_outcome(result, f"{scheme or 'unknown'}://")
    write_also_json(result, args)
    render(result, args.format, **render_kwargs)
    conclude_outcome(result, outcome, args.format)


def announce_outcome(result: Any, label: str) -> Outcome:
    """A result's outcome; a failed one's error goes to stderr here, once (BACK-1059).

    `label` names what failed: `<scheme>://` for a URI, the path for a file view."""
    outcome = outcome_of(result)
    if outcome == 'failed':
        print(f"Error ({label}): {result['error']}", file=sys.stderr)
    return outcome


def conclude_outcome(result: Any, outcome: Outcome, output_format: str) -> None:
    """After the render: print what a truncated result left out; exit 1 on a failed one."""
    if outcome == 'truncated':
        print_truncations(result, output_format)
    if outcome == 'failed':
        sys.exit(1)


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
    if peek(args, 'all', False) or peek(args, 'verbose', False):
        mark(args, 'all', 'verbose')
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
    generic_adapter_handler(adapter_class, _renderer_class_of(scheme), scheme, resource,
                            element, args)


def _renderer_class_of(scheme: str) -> type[Any]:
    from ...adapters.base import get_renderer_class
    renderer_class = get_renderer_class(scheme)
    if not renderer_class:
        # This shouldn't happen if adapter is properly registered
        print(f"Error: No renderer registered for scheme '{scheme}'", file=sys.stderr)
        print("This is a bug - adapter is registered but renderer is not.", file=sys.stderr)
        sys.exit(1)
    return renderer_class
