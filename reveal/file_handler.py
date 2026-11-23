"""File handling operations.

This module is separate from cli.routing to avoid circular dependencies with adapters.

Nginx-specific file handlers live in reveal.adapters.nginx.handlers (BACK-097).
Nav-flag handlers (--outline, --varflow, --calls, etc.) live in reveal.nav_handlers
(BACK-306). Both groups are re-exported here for backward compatibility with existing
test imports.
"""

import os
import sys
from pathlib import Path
from typing import NoReturn, Optional, TYPE_CHECKING

from .core import tree_root
from .core.treesitter_compat import _zero_arg
from .utils.results import FailureCause, NavSourceFailure, execution_exit_code, failure_execution_facts

if TYPE_CHECKING:
    from argparse import Namespace

# Nginx handlers — canonical location is adapters/nginx/handlers.py. They return a
# FlagOutput; the _handle_* names below write it out (BACK-916), the helpers re-export.
# Resolved on first use (module __getattr__): importing the nginx package pulls in the
# ssl adapter and `cryptography`, which no other command needs at startup (BACK-1870).
if TYPE_CHECKING:
    from .adapters.nginx.handlers import FlagOutput

_NGINX_FLAG_HANDLERS = frozenset({
    '_handle_domain_extraction', '_handle_acme_roots_extraction', '_handle_check_acl',
    '_handle_validate_nginx_acme', '_handle_global_audit', '_handle_check_conflicts',
    '_handle_diagnose', '_handle_cpanel_certs', '_handle_extract_option',
})
_NGINX_REEXPORTS = frozenset({
    'FlagOutput', '_format_acl_col', '_format_acme_ssl_col', '_fetch_acme_ssl_data',
    '_resolve_log_path', '_load_disk_cert', '_load_live_cert', '_cert_match_label',
    '_format_disk_col', '_format_live_col', '_format_match_col',
})


def _write_flag_output(output: 'FlagOutput') -> None:
    """The one place an nginx flag handler's stdout, stderr and exit code leave the process."""
    if output.err:
        print(output.stderr, end='', file=sys.stderr)  # boundary-ok: print -- the flag-output seam
    if output.out:
        print(output.stdout, end='')  # boundary-ok: print -- the flag-output seam
    if output.code:
        sys.exit(output.code)  # boundary-ok: exit -- the flag-output seam


def _emitting(build):
    """A flag handler that writes what `build` returns."""
    def handler(*args, **kwargs) -> None:
        _write_flag_output(build(*args, **kwargs))
    handler.__name__ = build.__name__
    handler.__doc__ = build.__doc__
    return handler


def _nginx_flag_handler(name: str):
    """A _handle_* flag handler looked up on this module: a bare global name would not
    reach __getattr__, and a patched module attribute is still honoured."""
    return getattr(sys.modules[__name__], name)


def __getattr__(name: str):
    if name in _NGINX_FLAG_HANDLERS or name in _NGINX_REEXPORTS:
        from .adapters.nginx import handlers
        value = getattr(handlers, name)
        if name in _NGINX_FLAG_HANDLERS:
            value = _emitting(value)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Nav handlers — canonical location is reveal/nav_handlers.py (BACK-306).
# Re-exported for backward compat with tests that import from file_handler.
from .nav_handlers import (  # noqa: F401
    _IF_KEYWORDS,
    _CATCH_KEYWORDS,
    _resolve_range,
    _parse_line_range,
    _nav_json,
    _NavCtx,
    _nav_flow,
    _nav_varflow,
    _nav_narrow,
    _nav_calls,
    _nav_exits,
    _nav_deps,
    _nav_mutations,
    _nav_sideeffects,
    _nav_fanout,
    _nav_statewrites,
    _nav_keys,
    _nav_boundary,
    _nav_scope,
    _nav_around,
    ELEMENT_HANDLERS,
)
from reveal.utils.lines import split_lines


def _get_analyzer_or_exit(path: str, allow_fallback: bool, unreadable_exit_code: Optional[int] = None, *,
                          nav_source: bool = False):
    """Get analyzer for path or exit with error.

    Args:
        path: File path
        allow_fallback: Whether to allow fallback analyzers
        unreadable_exit_code: Exit code when the file exists but cannot be read; by default
            the D6 code of the read's cause (`check` passes 3, or 0 under --exit-zero)
        nav_source: Adopt authored source failure facts for a navigation request

    Returns:
        Analyzer instance

    Exits:
        2 if no analyzer reads the path or the file vanished before the read, 3 if it
        exists but cannot be read (BACK-2527), unless *unreadable_exit_code* is given
    """
    from .registry import get_analyzer  # noqa: I006 — circular avoidance
    from .errors import AnalyzerNotFoundError  # noqa: I006 — circular avoidance

    analyzer_class = get_analyzer(path, allow_fallback=allow_fallback)
    if not analyzer_class:
        # No "similar extensions" hint: a substring match named another language
        # ('.rs' for '.rst') and the reader cannot act on it (BACK-2492).
        error = AnalyzerNotFoundError(path=path, allow_fallback=allow_fallback)
        print(str(error), file=sys.stderr)
        # D6: a file no analyzer reads is an invalid resource (2), not findings (1).
        sys.exit(2)

    try:
        return analyzer_class(path)  # reads the file
    except OSError as e:
        # An unreadable file (chmod 000, a FIFO, a vanished mount) printed a raw
        # traceback, while a missing path got a clean error (BACK-1424).
        diagnostic = _source_read_diagnostic(e, path, nav_source)
        print(diagnostic, file=sys.stderr)
        facts = failure_execution_facts(_read_failure_cause(e, path))
        # D6: a required source that could not be read is 3, a vanished one 2; exit 1 is
        # a findings gate (BACK-2527).
        code = execution_exit_code(facts) if unreadable_exit_code is None else unreadable_exit_code
        if nav_source:
            raise NavSourceFailure(code, execution_facts=facts, public_diagnostic=diagnostic) from e
        sys.exit(code)


def _source_read_diagnostic(error: OSError, path: str, nav_source: bool) -> str:
    """Preserve legacy text while spelling the new public nav diagnostic safely."""
    from .utils.path_utils import failure_of, to_posix

    if nav_source:
        return f"Error: cannot read {to_posix(path)}: {error.strerror or failure_of(error).cause}"
    return f"Error: cannot read {path}: {error.strerror or error}"


def _read_failure_cause(error: OSError, path: str) -> FailureCause:
    """Only a missing requested filename establishes invalid source selection."""
    filename = error.filename
    if (isinstance(error, FileNotFoundError)
            and isinstance(filename, (str, bytes, os.PathLike))
            and Path(os.fsdecode(filename)) == Path(path)):
        return FailureCause.INVALID_REQUEST
    return FailureCause.ANALYSIS


def _build_file_cli_overrides(args: Optional['Namespace']) -> dict:
    """Build CLI overrides dictionary from args.

    Args:
        args: Argument namespace

    Returns:
        CLI overrides dict
    """
    cli_overrides = {}
    breadcrumbs = getattr(args, 'breadcrumbs', None) if args else None
    if breadcrumbs is not None:  # typed --breadcrumbs on|off overrides config, REVEAL_BREADCRUMBS and the TTY default
        cli_overrides['display'] = {'breadcrumbs': breadcrumbs}
    return cli_overrides


def element_request_of(path: str, element: Optional[str], args, *, before_binding=None):
    """The element request *args* give for *path* (``nav_params.bind_element_request``), or None. The one reading of the
    element declarations off a namespace (``declared.typed_source``): the file route binds through it at its entry, and
    a library caller of ``handle_file`` that passes a namespace only binds here. The code-element ``--outline`` is its
    legacy view word only for an element of a non-Markdown file (its ``target:nav.outline`` row,
    ``declared.element_request_source``). *before_binding* runs once the request is known to be an element request
    (the route's path and unsupported-control checks)."""
    from .cli.routing.declared import element_request_source
    from .nav_params import bind_element_request, element_request_given
    if args is None:
        return None
    source, spelled = element_request_source(path, element, args)
    if not element_request_given(source):
        return None
    if before_binding is not None:
        before_binding()
    return bind_element_request(source, spelled, path=path, element=element)


def _resolve_func_node(analyzer, element: str):
    """Resolve the function/scope node for nav flags that need an element.

    For named functions: returns the function node directly.
    For flat/procedural files: falls back to root_node when the element is a
    line reference (:N or :N-M), enabling nav flags on files without top-level
    function definitions.

    Returns:
        (func_node, func_start, func_end) or exits with an error message.
    """
    from .display.element import _parse_element_syntax  # noqa: I006
    from .element_resolve import ambiguity_note, describe_candidates  # noqa: I006
    from .utils.path_utils import to_posix
    resolution = _resolve_element(analyzer, element) if element else None
    func_node = resolution.node if resolution is not None else None
    # BACK-1400: say which definition the nav flag is analyzing when the name
    # has several; stderr, so --format json stdout stays parseable.
    if resolution is not None and resolution.ambiguous:
        for line in ambiguity_note(analyzer.path, element, describe_candidates(analyzer, resolution, element)):
            print(line, file=sys.stderr)
    if func_node is None:
        syntax = _parse_element_syntax(element) if element else None
        if syntax and syntax['type'] == 'line':
            func_node = tree_root(analyzer.tree)
            func_start = syntax['start_line']
            func_end = (
                syntax['end_line']
                if syntax.get('end_line')
                else len(split_lines(analyzer.content))
            )
        else:
            diagnostic = (
                f'Error: could not find function or method {element!r} in {to_posix(analyzer.path)}\n'
                '  Use `reveal <file>` to list available elements.\n'
                '  For methods, use Class.method syntax (e.g., MyClass.my_method).'
            )
            # Same code as the plain element miss: a named target that matches nothing (BACK-2492).
            _fail_nav(2, FailureCause.INVALID_REQUEST, diagnostic)
    else:
        func_start = _zero_arg(func_node, 'start_position').row + 1
        # Dart's grammar splits a function into sibling `function_signature`
        # + `function_body` nodes rather than nesting the body inside one
        # function node (see TreeSitterAnalyzer._function_end_node) — every
        # nav flag walks func_node's own subtree, so without this swap they'd
        # walk only the one-line signature and see the body as empty, no
        # matter what func_end says.
        end_node = getattr(analyzer, '_function_end_node', lambda n: n)(func_node)
        func_end = _zero_arg(end_node, 'end_position').row + 1
        if end_node is not func_node:
            func_node = end_node
    return func_node, func_start, func_end


def _dispatch_nav(analyzer, element: str, output_format: str, args, request=None) -> None:
    """Answer the bound element request (*request*, or the one *args* give) with its handler.

    Requires a TreeSitterAnalyzer with a parsed tree.  Exits with an error
    message if the file type is not tree-sitter analysable.
    """
    from .treesitter import TreeSitterAnalyzer  # noqa: I006
    if request is None:
        request = element_request_of(analyzer.path, element, args)
    line_view = request.operation in ('scope', 'around')
    handler = ELEMENT_HANDLERS.get(request.answer)
    # Every element view renders text and JSON only; grep and typed used to print the text answer (BACK-2627 E12).
    from .cli.routing.formats import DEFAULT_OUTPUT_FORMATS, require_supported_format
    require_supported_format(args, DEFAULT_OUTPUT_FORMATS, 'element views')
    output_format = getattr(args, 'format', output_format)
    if not line_view:
        _validate_nav_request(analyzer, handler, args)

    if not isinstance(analyzer, TreeSitterAnalyzer) or not analyzer.tree:
        from .errors import NavRequestValidationError
        from .utils.path_utils import to_posix
        # An invalid request (D6): exit 2, no longer 1 (BACK-2627 E9).
        raise NavRequestValidationError(
            f'element views need a code file tree-sitter can parse; {to_posix(analyzer.path)} is not one. '
            f'Use `reveal {to_posix(analyzer.path)}` to inspect its structure.')
    _note_untested_tier(analyzer)

    as_json = output_format == 'json'

    # --scope and --around operate on a line reference, not a func node.
    if request.operation == 'scope':
        _nav_scope(analyzer, element, as_json)
        return
    if request.operation == 'around':
        _nav_around(analyzer, element, as_json, request.value)
        return

    func_node, func_start, func_end = _resolve_func_node(analyzer, element)
    _require_selected_lines(analyzer, element, request)
    if 'outline' in request.spelled:  # the code-element --outline, once its element resolves
        from .cli.invocation import retirement_note
        retirement_note('target:nav.outline')
    ctx = _NavCtx(
        func_node=func_node,
        element=element,
        analyzer=analyzer,
        as_json=as_json,
        request=request,
        func_start=func_start,
        func_end=func_end,
        depth=request.nesting_depth,
        get_text=analyzer._get_node_text,
    )

    if handler is not None:
        _run_nav_handler(handler, ctx)


def _note_untested_tier(analyzer) -> None:
    """D13, X15: an untested code language or a fallback grammar answers every element view with one warning naming
    its tier (verified and smoke-tested languages keep their own disclosures). It joins the invocation's warnings, so
    a JSON answer carries it in ``meta.warnings`` and text prints it once on stderr."""
    from .capabilities import CONFORMANCE_UNTESTED, get_capability
    from .utils.invocation_log import record_warning

    capability = get_capability(analyzer)
    if capability is not None and capability.conformance_level != CONFORMANCE_UNTESTED:
        return
    if capability is not None:
        message = (f'Code navigation is untested for {capability.language} (no conformance fixtures): '
                   'treat this answer as unverified.')
    else:
        language = getattr(analyzer, 'language', None) or type(analyzer).__name__
        message = (f'{language} is read with a fallback grammar and code navigation is untested for it: '
                   'treat this answer as unverified.')
    record_warning({'type': 'navigation_warning', 'code': 'navigation_untested', 'message': message})


def _require_selected_lines(analyzer, element: str, request) -> None:
    """Plan rule 9 for lines (X14): a line element, ``--range`` or ``--callsites`` range that selects no line of the
    file, or a reversed line element, is an invalid request naming what it searched, not an empty answer (E3)."""
    from .display.element import _parse_element_syntax  # noqa: I006
    from .errors import NavRequestValidationError
    from .nav_handlers import callsites_lines
    from .utils.path_utils import to_posix

    total = len(split_lines(analyzer.content))
    syntax = _parse_element_syntax(element) if element else None
    selections = []
    if syntax is not None and syntax['type'] == 'line':
        start, end = syntax['start_line'], syntax.get('end_line')
        if end is not None and end < start:
            raise NavRequestValidationError(
                f'line range {element} is reversed: give :START-END with START <= END.')
        selections.append((element, start))
    if request.range is not None:
        selections.append((f'--range {request.range[0]}-{request.range[1] or ""}', request.range[0]))
    lines = callsites_lines(request.value) if request.operation == 'callsites' else None
    if lines is not None:
        selections.append((f'--callsites {lines[0]}-{lines[1] or ""}', lines[0]))
    for spelling, start in selections:
        if start > total:
            raise NavRequestValidationError(
                f'{spelling} selects no line: {to_posix(analyzer.path)} has {total} lines.')


def _fail_nav(code: int, cause: 'FailureCause', diagnostic: str) -> 'NoReturn':
    """Print a nav diagnostic and raise the authored failure CLI and MCP both report."""
    print(diagnostic, file=sys.stderr)
    raise NavSourceFailure(code, execution_facts=failure_execution_facts(cause), public_diagnostic=diagnostic)


def _run_nav_handler(handler, ctx) -> None:
    """Run one element-flag handler; an analysis too deeply nested to follow fails with exit 3."""
    try:
        handler(ctx)
    except RecursionError:
        # BACK-2529: the variable-flow walkers recurse once per syntax level, so a few hundred
        # nested calls (generated parsers) exhaust the interpreter's limit. D6: the request was
        # valid and the required analysis failed; say so instead of printing a traceback.
        from .utils.path_utils import to_posix
        diagnostic = (
            f'Error: {_requested_nav_flag(ctx.request)} could not analyze {ctx.element!r} in '
            f'{to_posix(ctx.analyzer.path)}: its code is nested deeper than the analysis can follow '
            "(the interpreter's recursion limit).\n"
            '  No answer is printed because it would be incomplete.'
        )
        _fail_nav(3, FailureCause.ANALYSIS, diagnostic)


def _requested_nav_flag(request) -> str:
    """The element flag as the request spelled it, for a diagnostic (BACK-2529): the flag that carried the selected
    operation or view (the binder's record), else its canonical spelling."""
    params = request.params
    spelled = request.spelled
    implied = getattr(params, '_implied_by', None) or {}
    name = request.operation or 'view'
    word = implied.get(name) or next((alias for alias in getattr(params, '_supplied_aliases', ())
                                      if alias in _spellings_of(name)), None)
    if word:
        return str(spelled.get(word, f'--{word}'))
    return f'--{name}' if request.operation else f'--view {request.view}'


def _spellings_of(name: str) -> tuple:
    from .nav_params import ELEMENT_VIEW_SPECS
    return next((spec.spellings for spec in ELEMENT_VIEW_SPECS if spec.name == name), ())


def _validate_nav_request(analyzer, handler, args) -> None:
    """Reject only declared unsupported analysis and invalid structural depth."""
    from .capabilities import CONFORMANCE_STRUCTURE_ONLY, VARFLOW_NOT_APPLICABLE, get_capability
    from .errors import NavRequestValidationError
    from .utils.path_utils import to_posix

    capability = get_capability(analyzer)
    if capability is not None and capability.conformance_level == CONFORMANCE_STRUCTURE_ONLY:
        raise NavRequestValidationError(
            f'Code navigation analysis is unavailable for {capability.language} (structure-only). '
            f'Use `reveal {to_posix(analyzer.path)}` to inspect file structure.'
        )
    if capability is not None and capability.varflow == VARFLOW_NOT_APPLICABLE:
        # A data or document format has no functions to analyze: decline as structure-only does (BACK-2627 X15),
        # where Markdown/JSON/YAML/TOML/GraphQL/Protobuf answered an empty or invented view with exit 0.
        raise NavRequestValidationError(
            f'Code navigation analysis does not apply to {capability.language} files (not code). '
            f'Use `reveal {to_posix(analyzer.path)}` to inspect file structure.'
        )


def _resolve_element(analyzer, element: str):
    """Resolve a function/method name for nav flags to an element_resolve.Resolution.

    Supports bare names ('my_func') and Class.method syntax ('MyClass.my_method').
    Functions before types: a nav flag on `Foo` in Java means the method or
    constructor, not the class body. JS-family `const f = (...) => {}` values
    and test-callback labels come last (element_resolve._unnamed_kind_matches).
    Returns None when nothing named matches.
    """
    from .element_resolve import (  # noqa: I006
        TYPE_TIER, resolve_bare_name, resolve_path, resolve_scope_qualified,
    )
    from .treesitter import ELEMENT_TYPE_MAP  # noqa: I006

    if '.' in element:
        return resolve_path(analyzer, element)
    return (resolve_bare_name(analyzer, element, (ELEMENT_TYPE_MAP['function'], TYPE_TIER))
            or resolve_scope_qualified(analyzer, element))


def _find_element_node(analyzer, element: str):
    """Find and return the tree-sitter node for a named function/method.

    Supports bare names ('my_func') and Class.method syntax ('MyClass.my_method').
    Returns the node or None if not found. An ambiguous name returns the same
    pick element extraction shows; _resolve_func_node reports the others.
    """
    resolution = _resolve_element(analyzer, element)
    return resolution.node if resolution is not None else None


def _dispatch_special_flags(analyzer, path: str, output_format: str, args, config) -> bool:
    """Handle flags that short-circuit normal file analysis.

    Returns True if a flag was matched and handled (caller should return
    immediately).  Returns False if none matched and normal routing should
    continue.
    """
    if getattr(args, 'extract', None):
        _nginx_flag_handler('_handle_extract_option')(analyzer, args.extract.lower(), args=args)
        return True

    if getattr(args, 'check_acl', False):
        _nginx_flag_handler('_handle_check_acl')(analyzer)
        return True

    if getattr(args, 'validate_nginx_acme', False):
        _nginx_flag_handler('_handle_validate_nginx_acme')(analyzer, args)
        return True

    if getattr(args, 'global_audit', False):
        _nginx_flag_handler('_handle_global_audit')(analyzer, args)
        return True

    if getattr(args, 'check_conflicts', False):
        _nginx_flag_handler('_handle_check_conflicts')(analyzer)
        return True

    if getattr(args, 'cpanel_certs', False):
        _nginx_flag_handler('_handle_cpanel_certs')(analyzer, args=args)
        return True

    if getattr(args, 'diagnose', False):
        _nginx_flag_handler('_handle_diagnose')(analyzer, log_path=getattr(args, 'log_path', None))
        return True

    if getattr(args, 'validate_schema', None):
        from .checks import run_schema_validation  # noqa: I006 — circular avoidance
        run_schema_validation(analyzer, path, args.validate_schema, output_format, args)
        return True

    return False


def _refuse_meta_beside(request) -> None:
    """D3/U1 at the library entry: ``show_meta`` (``--meta``) is a control no element view reads."""
    if request is None:
        return
    from .errors import NavRequestValidationError
    from .nav_params import ELEMENT_VIEW_SPECS
    from .utils.query_binding import unsupported_controls_message
    raise NavRequestValidationError(unsupported_controls_message(ELEMENT_VIEW_SPECS, ['--meta']))


def _whole_file_element(analyzer, request) -> str:
    """The whole-file (flat) element view's element: a full-file line range, so _dispatch_nav falls back to root_node.
    --scope and --around require a line reference: the one check says so, exit 2 (BACK-2627 E9). `reveal file.py
    --outline` (no element) is no element request: show_structure renders the file outline."""
    if request.operation in ('scope', 'around'):
        from .nav_handlers import _single_line_ref
        _single_line_ref(None, f'--{request.operation}')
    return f':1-{len(split_lines(analyzer.content))}'


def handle_file(path: str, element: Optional[str], show_meta: bool,
                output_format: str, args: Optional['Namespace'] = None, *, element_request=None) -> None:
    """Handle file analysis.

    Args:
        path: File path
        element: Optional element to extract
        show_meta: Whether to show metadata only
        output_format: Output format ('text', 'json', 'grep')
        args: Full argument namespace (for filter options)
        element_request: The bound element request (the file route binds it at its entry); a caller that passes only
            a namespace has it bound here (``element_request_of``).
    """
    from .display import show_structure, show_metadata, extract_element  # noqa: I006 — circular avoidance
    from .config import RevealConfig  # noqa: I006 — circular avoidance

    request = element_request if element_request is not None else element_request_of(path, element, args)

    allow_fallback = getattr(args, 'fallback', None) is not False if args else True
    analyzer = _get_analyzer_or_exit(path, allow_fallback, nav_source=request is not None)

    cli_overrides = _build_file_cli_overrides(args)
    config = RevealConfig.get(
        start_path=Path(path).parent if Path(path).is_file() else Path(path),
        cli_overrides=cli_overrides if cli_overrides else None
    )

    if show_meta:
        _refuse_meta_beside(request)
        show_metadata(analyzer, output_format, config=config)
        return

    if args and _dispatch_special_flags(analyzer, path, output_format, args, config):
        return

    if request is not None and not element:
        element = _whole_file_element(analyzer, request)

    if element:
        if request is not None:
            _dispatch_nav(analyzer, element, output_format, args, request)
            return
        # A Markdown section has no control flow; its outline is its headings.
        from .display.element import _is_markdown  # noqa: I006
        if args is not None and getattr(args, 'outline', False) and _is_markdown(analyzer):
            extract_element(analyzer, element, output_format, section_outline=True, depth=getattr(args, 'depth', None))
            return
        cut = tuple(getattr(args, flag, None) if args else None for flag in ('head', 'tail', 'range'))
        extract_element(analyzer, element, output_format, config=config, cut=cut)
        return

    # Capture producer facts before display cuts and use the existing D6 output boundary.
    from .cli.routing.uri import _emit_result, announce_outcome  # noqa: I006 — circular avoidance
    from .display.structure import _render_file_structure
    from argparse import Namespace

    def emit(structure, facts):
        announce_outcome(structure, path)
        def render(result, format):
            _render_file_structure(analyzer, result, format, args, config)
        _emit_result(structure, args or Namespace(format=output_format), 'file', render,
                     execution_facts=facts, default_fail_on='none', announce_error=False,
                     renderer_owns_json=True)

    show_structure(analyzer, output_format, args, config=config, emit=emit)
