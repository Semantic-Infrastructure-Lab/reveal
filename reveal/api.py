"""Public Python API for Reveal.

Provides programmatic access to Reveal's analysis without subprocess overhead.

Usage::

    from reveal import analyze, element, query, check

    # Analyze a Python file — returns structured dict
    result = analyze("myfile.py")
    for fn in result.get("functions", []):
        print(fn["name"], fn["line"])

    # Extract a specific named element
    func = element("myfile.py", "my_function")
    if func:
        print(func["content"])

    # Ask a noun, as `reveal calls myproject --callers main` does
    result = query("calls", "myproject", callers="main")

    # A resource is named by its URI and takes the same keywords
    history = query("git://myfile.py", view="history", limit=5)

    # Check code quality — returns list of Detection objects
    findings = check("myfile.py", select=["C", "M"])
    for f in findings:
        print(f.rule_code, f.message)
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def analyze(path: str, **kwargs: Any) -> Dict[str, Any]:
    """Get the structural overview of a file.

    Equivalent to ``reveal myfile.py`` at the CLI, but returns the raw data dict
    instead of rendering it to the terminal.

    Args:
        path: Path to the file to analyze.
        **kwargs: Additional keyword arguments forwarded to the analyzer's
            ``get_structure()`` method. ``head``, ``tail`` and ``range`` (1-indexed
            ``(start, end)``) are not forwarded: they cut each list of the result, as
            ``reveal FILE --head N`` does, and each cut is a ``meta.warnings`` entry.

    Returns:
        Dict with keys such as ``"functions"``, ``"classes"``, ``"imports"``,
        etc.  Exact keys depend on the file type and analyzer.

    Raises:
        FileNotFoundError: If *path* does not exist on disk.
        ValueError: If no analyzer is registered for this file type.

    Example::

        result = analyze("mymodule.py")
        for fn in result.get("functions", []):
            print(fn["name"], fn["line"])
    """
    from .registry import get_analyzer

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    analyzer_class = get_analyzer(str(file_path))
    if analyzer_class is None:
        raise ValueError(f"No analyzer available for: {path}")

    head, tail, range_ = (kwargs.pop(k, None) for k in ('head', 'tail', 'range'))
    if head or tail or range_:
        kwargs.setdefault('navigate', True)  # as the CLI tells markdown (StructureOptions)
    analyzer = analyzer_class(str(file_path))
    structure = analyzer.get_structure(**kwargs)
    analyzer.cut_structure(structure, head, tail, range_)
    return structure


def element(
    path: str,
    name: str,
    element_type: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Extract a named element (function, class, section, …) from a file.

    Equivalent to ``reveal myfile.py my_function`` at the CLI.

    Args:
        path: Path to the file.
        name: Name of the element to extract.
        element_type: Optional type hint (``"function"``, ``"class"``,
            ``"section"``, etc.).  When ``None`` the structure is searched
            first to determine the correct type, then common types are tried.

    Returns:
        An envelope whose ``"source"`` is the path and ``"content"`` the extracted code,
        with ``"line_start"``, ``"line_end"``, etc.,
        or ``None`` if the element was not found.

    Raises:
        FileNotFoundError: If *path* does not exist on disk.
        ValueError: If no analyzer is registered for this file type.

    Example::

        func = element("mymodule.py", "load_config")
        if func:
            print(func["content"])
    """
    from .registry import get_analyzer
    from .utils.results import ResultBuilder

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    analyzer_class = get_analyzer(str(file_path))
    if analyzer_class is None:
        raise ValueError(f"No analyzer available for: {path}")

    analyzer = analyzer_class(str(file_path))

    # Fast path: caller provided the type.
    if element_type:
        result = analyzer.extract_element(element_type, name)
        return dict(ResultBuilder.element(result, file_path)) if result is not None else None

    # Slower path: scan the structure to discover the element's type, then
    # use it for a precise extraction.  This avoids ambiguous matches.
    _SECTION_TO_TYPE: Dict[str, str] = {
        "functions": "function",
        "classes": "class",
        "methods": "method",
        "structs": "struct",
        "enums": "enum",
        "interfaces": "interface",
        "sections": "section",
        "variables": "variable",
        "tests": "test",
    }
    try:
        struct = analyzer.get_structure()
        for section_key, elem_type in _SECTION_TO_TYPE.items():
            for item in struct.get(section_key, []):
                if isinstance(item, dict) and item.get("name") == name:
                    result = analyzer.extract_element(elem_type, name)
                    if result is not None:
                        return dict(ResultBuilder.element(result, file_path))
    except Exception as e:  # boundary-ok: broad-except -- public element() returns None on a miss; a failing analyzer is logged at warning with the path and name rather than raised into the caller's lookup loop
        logger.warning("element() structure lookup failed for %s %r: %s", path, name, e)

    # Last resort: try common types in order.
    for elem_type in ("function", "class", "method", "struct", "enum",
                      "interface", "section", "variable", "test"):
        result = analyzer.extract_element(elem_type, name)
        if result is not None:
            return dict(ResultBuilder.element(result, file_path))

    return None


def _noted_answer(scheme: str, uri: str, overrides: Dict[str, Any], answer):
    """Answer inside an invocation scope that notes every retired spelling the request uses, as the CLI does:
    RETIREMENTS is the one source (its scheme, parameters, values and typed keywords), and the notes reach the
    result's ``meta.warnings`` as the CLI's JSON carries them (BACK-2654; it used to note declared aliases only).
    A URI request that retires says it once, as the Python call that replaces it (BACK-2716): that note covers the
    per-key notes of the controls it renders. A request that says no request note (a resource URI with no query string)
    says each legacy keyword's own row: nothing else would."""
    from .cli.invocation import (Invocation, invocation_scope, note_uri_spelling, request_noted, retirement_note,
                                 uri_retirement_keys)
    from .utils.json_utils import attach_invocation_warnings
    by_request = request_noted(scheme)
    says_request = _says_request_note(scheme, uri)
    keys = uri_retirement_keys(uri) + [f'param:{scheme}.{key}' for key in overrides]
    with invocation_scope(Invocation.parse(['reveal', uri]), retirements_to_stderr=False, form='python'):
        for key in keys:
            (note_uri_spelling if by_request and says_request else retirement_note)(key)
        _note_retired_where_fields(scheme, uri, overrides)
        if by_request:
            _note_uri_request(scheme, uri, overrides)
        # The retirement notes and every config_warning this invocation recorded (BACK-2659).
        return attach_invocation_warnings(answer())


def _bound_uri_params(scheme: str, uri: str, overrides: Dict[str, Any]):
    """(declared adapter, resource, bound params, walk policy) of a declared noun's URI request with its keywords, bound
    as the answer's own path binds them; None for an undeclared scheme or a request binding rejects (the answer says
    why)."""
    from .cli.routing.declared import declared_adapter_class
    from .utils.gitignore import split_respect_gitignore
    from .utils.query_binding import apply_declared_overrides, prepare_declared_params
    adapter = declared_adapter_class(scheme)
    if adapter is None:
        return None
    # The walk policy is split off before binding, as the answer's own path does, and repeated as its flag.
    split, walk_policy = split_respect_gitignore(uri.partition('://')[2])
    resource, _, query = split.partition('?')
    try:
        params = apply_declared_overrides(adapter.PARAM_SPECS, prepare_declared_params(adapter.PARAM_SPECS, query, 'uri'),
                                          overrides)
    except (ValueError, TypeError):
        return None
    return adapter, resource, params, walk_policy


def _note_retired_where_fields(scheme: str, uri: str, overrides: Dict[str, Any]) -> None:
    """A where term on a retired field notes its row, as on the CLI (``note_retired_where_fields``, BACK-2613)."""
    bound = _bound_uri_params(scheme, uri, overrides)
    if bound is not None:
        from .cli.routing.declared import note_retired_where_fields
        note_retired_where_fields(scheme, bound[0].PARAM_SPECS, bound[2], 'uri')


def _says_request_note(scheme: str, uri: str) -> bool:
    """Whether a URI request says the one request note: an analysis-only scheme always, any other scheme when the URI
    spells a query string (a bare resource URI is no retiring request)."""
    from .adapters.base import get_adapter_class
    return bool(uri.partition('?')[2]) or bool(getattr(get_adapter_class(scheme), 'ANALYSIS_ONLY', False))


def _note_uri_request(scheme: str, uri: str, overrides: Dict[str, Any]) -> None:
    """The one note of a retiring URI request (``_says_request_note``), rendered from the request the URI and its
    keywords bind. An invalid request is not noted: the answer raises it."""
    from .cli.invocation import request_note
    from .cli.routing.canonical import render_uri_request
    from .cli.routing.declared import create_declared_parser
    if not _says_request_note(scheme, uri):
        return
    bound = _bound_uri_params(scheme, uri, overrides)
    if bound is None:
        return
    adapter, resource, params, walk_policy = bound
    parser = create_declared_parser(scheme)
    try:
        request_note(scheme, lambda form: render_uri_request(form, scheme, resource, params, parser=parser,
                                                             adapter=adapter, walk_policy=walk_policy))
    except ValueError:
        return  # no canonical form (a control no flag spells, or one binding rejects): the answer says why, not this note


def _refuse_removed_controls(scheme: str, uri: str, overrides: Dict[str, Any]) -> None:
    """A control whose RETIREMENTS row says it was removed (no adapter reads it any more) is an unsupported control, and
    the refusal says why in the row's words (plan rule 7, BACK-2752): a URI key raises ``RequestValidationError`` and a
    typed keyword ``UnsupportedOverrideError``, as any key or keyword the noun does not declare does, before the request
    binds or names an element, so the generic list of supported controls never stands in for the reason. The CLI
    already refuses such a URI key with the row's text (``_note_retired_spellings``); no CLI flag spells a typed one."""
    from .cli.invocation import RETIREMENTS, uri_retirement_keys
    from .errors import RequestValidationError, UnsupportedOverrideError
    keys = [(key, RequestValidationError) for key in uri_retirement_keys(uri) if key.startswith('param:')]
    keys += [(f'param:{scheme.lower()}.{word}', UnsupportedOverrideError) for word in overrides]
    for key, error in keys:
        entry = RETIREMENTS.get(key)
        if entry is not None and entry.removed:
            raise error(f"unsupported control {key.partition('.')[2]!r}: {entry.text}")


def _walk_scope(adapter_class: Any, resource: str, bound: Any):
    """(walk root, patterns) a declared walking noun's URI request publishes for its walk (COMMAND_MODEL "Walk
    exclusion", BACK-2730): the ``exclude`` it bound, from the URI or a keyword, joined with REVEAL_IGNORE and config
    ``ignore`` as the CLI's routes join them (``dispatch_scope``); none when the request names no exclusion."""
    import os
    from .utils.exclusions import dispatch_scope
    from .utils.query_parser import peek_query_items, split_exclude_param
    spec = getattr(adapter_class, 'RESOURCE_SPEC', None)
    if spec is None or not spec.walks:
        return None, []
    value = dict(peek_query_items(getattr(bound, 'query_params', None) or {})).get('exclude')
    patterns = [pattern for item in (value if isinstance(value, (list, tuple)) else [value])
                for pattern in split_exclude_param(item)]
    if not patterns:
        return None, []
    from .adapters.factory import scope_path_of
    from .utils.query_binding import bind_resource_path
    path = resource.partition('?')[0] or getattr(adapter_class, 'CANONICAL_EMPTY_RESOURCE', '.')
    path = bind_resource_path(spec, path, transport='uri', resolve=getattr(adapter_class, 'resource_path', None),
                              validate_kind=False)
    return dispatch_scope(os.path.expanduser(scope_path_of(adapter_class, path)), patterns)


def _query_noun(noun: str, target: Optional[str], controls: Dict[str, Any]) -> Dict[str, Any]:
    """The noun form, in one host request and invocation log as the URI form (and an MCP tool call) is."""
    from .cli.routing.typed import answer_typed_request
    from .utils.invocation_log import log_scope
    from .utils.request_cache import host_request
    _refuse_removed_controls(noun, f'{noun}://', controls)
    with host_request(), log_scope(to_stderr=False):
        return answer_typed_request(noun, target, controls)


def _legacy_element(adapter_class: Any, scheme: str, element_name: Optional[str]) -> Optional[str]:
    """The RETIREMENTS row of a positional element a declared noun still answers until the cut, or None. A declared
    noun reads no positional element: the CLI's refusal, before the adapter is built, never in get_element (V020: a
    missing element is None there); plugin subclasses keep forwarding (BACK-2687). A scheme whose element is a legacy
    spelling (``target:SCHEME.element``: help://, reveal://) answers it through get_element with its note (BACK-2767)."""
    from .adapters.factory import uses_bound_query_call
    if not element_name or not uses_bound_query_call(adapter_class):
        return None
    from .cli.invocation import element_retirement
    legacy = element_retirement(scheme)
    if legacy is None:
        from .adapters.base import unread_element_message
        from .errors import RequestValidationError
        raise RequestValidationError(unread_element_message(adapter_class, scheme, element_name))
    return legacy


def query(
    uri: str,
    element_name: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Ask a noun about a target, or query a resource by its URI; returns the answer as a dict.

    ``query("calls", "src", callers="main")`` is ``reveal calls src --callers main --format json``: the same
    answer, run through the CLI's own dispatch, returned instead of printed (BACK-2717). Each keyword is the
    noun's long flag with ``-`` written as ``_`` (``test_framework=``; ``--from`` is ``**{"from": NAME}``); a
    flag that takes no value takes True. ``query("git://app.py@main", view="history", limit=5)`` names a resource by
    its URI.

    Args:
        uri: A noun (``"calls"``, ``"imports"``, ``"ast"``, ``"metrics"``, ``"overview"``...), or the URI of a
            resource, ``scheme://resource``: ``"git://app.py@main"``, ``"claude://session/NAME"``,
            ``"sqlite://app.db/users"``, ``"json://data.json/key"``, ``"help://quick"``. A URI query
            (``?callers=main``) is the older spelling of the noun's keywords.
        element_name: With a noun, its target, the CLI's positional (``"src"``; omitted, the noun's default,
            usually ``"."``). With a URI, an element for an adapter whose ``get_element`` reads one (plugins and
            undeclared adapters); a declared noun reads no element and refuses it as an invalid request
            (``RequestValidationError``) naming the URI form, as at the CLI.
        **kwargs: With a noun, its flags as keywords (above): an unknown keyword raises
            ``UnsupportedOverrideError``; an invalid request (a value outside its choices, a control the
            answer does not read, a target that matches nothing, a path that does not exist) raises
            ``RequestValidationError`` with the CLI's message, where the CLI exits 2; a failed analysis raises
            its cause, or ``AnalysisFailedError`` (its ``result`` is the CLI's document), where the CLI exits 3.
            An incomplete answer and findings are returned and say so in themselves, as the CLI's JSON does.
            Output options (``format``, ``output``, ``fail_on``) are not keywords: the answer itself is returned.
            With a URI: typed query controls. On a declared noun they bind as its URI query keys do and meet
            the same checks before analysis: an unknown keyword raises
            ``UnsupportedOverrideError``, and one the selected answer does not read raises
            ``UnreadControlError`` (OUTPUT_CONTRACT, "Ignored inputs"). Plugins and undeclared adapters
            forward them to ``get_structure()`` or ``get_element()``.
            Surface accepts type, source_only, by, depth and top; Contracts accepts
            abstract_only, implementations and implementations_limit; Trace accepts from and depth.
            AST accepts where (a string or list of ANDed expressions), kind, view,
            builtins, reveal-type, sort, limit and offset, using the existing AST parser.
            Calls accepts its declared mode and analysis/presentation controls; mode
            validation uses the effective URI plus typed overrides. Imports accepts its
            declared view modes and analysis/presentation controls (False is not selected).
            Metrics accepts its declared controls (view, hotspots, top, code_only, the min_/max_
            thresholds, churn, since, no_merges, tests, summary_only, sort, limit and offset);
            operator filters such as lines>50 stay in the URI.
            Trace requires a valid URI from selector first; use dictionary expansion
            for its canonical from keyword. Explicit values override
            validated URI controls; None selects the declared default.

    Each call is one host request with the MCP server's evidence lifetime: an edit
    made between two calls is seen by the second, and an unchanged tree's indexes are
    reused. Calls are serialized across threads.

    Returns:
        The answer dict; for a noun, the CLI's JSON document for the same request.

    Raises:
        ValueError: If the first argument is neither a noun nor a URI, or the URI's scheme is not supported.
        ImportError: If an optional dependency required by the adapter is missing.
        RequestValidationError: A ValueError for a request a declared noun cannot answer as written: an
            element, an unread control (``UnreadControlError``) or an unsupported keyword; with a noun, every
            request the CLI exits 2 on.
        TypeError: If a declared noun gets an unsupported keyword (``UnsupportedOverrideError`` is both).
        AnalysisFailedError: With a noun, a failed analysis that raised no cause of its own (the CLI's exit 3).

    Example::

        callers = query("calls", "src", callers="process_order", depth=2)
        biggest = query("ast", "src", kind="function", sort="-lines", limit=5)
        sessions = query("claude", "sessions")
        history = query("git://app.py", view="history", limit=5)
    """
    from . import adapters as _adapters  # noqa: F401 — triggers adapter registrations
    from .adapters.base import _default_from_uri, get_adapter_class

    if "://" not in uri:
        return _query_noun(uri, element_name, kwargs)

    from .utils.gitignore import gitignore_scope, split_respect_gitignore

    scheme, resource = uri.split("://", 1)
    # BACK-1386: same ?respect_gitignore= handling as the CLI's handle_uri.
    resource, respect_gitignore = split_respect_gitignore(resource)
    adapter_class = get_adapter_class(scheme)
    if adapter_class is None:
        from .cli.invocation import current_schemes
        supported = ", ".join(f"{s}://" for s in current_schemes())
        raise ValueError(
            f"Unsupported URI scheme: {scheme}://\n"
            f"Supported schemes: {supported}"
        )

    _refuse_removed_controls(scheme, uri, kwargs)
    from .adapters.factory import _canonical_init, uses_bound_query_call
    legacy_element = _legacy_element(adapter_class, scheme, element_name)

    from .utils.request_cache import host_request
    from .utils.invocation_log import log_scope
    from .cli.routing.uri import _echo_source

    def _spelled(result: Dict[str, Any]) -> Dict[str, Any]:
        """``source`` as the caller named the target, as the CLI's URI route reports it (BACK-1366)."""
        _echo_source(result, adapter_class, resource)
        return result

    # One host request, as an MCP tool call is: owner-registered caches (the calls
    # indexes among them) are reset or revalidated against the tree first (BACK-2093).
    # One invocation log for the whole call, so a config problem met while the adapter is
    # built reaches the answer as the CLI's JSON carries it (BACK-2659).
    with host_request(), log_scope(to_stderr=False), gitignore_scope(respect_gitignore):
        if uses_bound_query_call(adapter_class) and legacy_element is None:
            bound = _canonical_init(adapter_class, resource, overrides=kwargs)
            def bound_answer(bound=bound):
                from .utils.exclusions import exclusion_scope
                with exclusion_scope(*_walk_scope(adapter_class, resource, bound)):  # the URI's exclude (BACK-2730)
                    result = bound.get_structure()
                facts_of = getattr(type(bound), 'execution_facts', None)
                if callable(facts_of) and isinstance(result, dict):
                    # The CLI's order: the incomplete marker, then the retirement notes (COMMAND_MODEL 'Transports').
                    from .utils.results import note_incomplete
                    note_incomplete(result, facts_of(result))
                return result
            bound_result: Dict[str, Any] = _noted_answer(scheme, uri, kwargs, bound_answer)
            return _spelled(bound_result)
        # Only a class's own declaration adopts the check, as with BOUND_QUERY_CALL: a plugin subclass that inherits
        # PARAM_SPECS keeps forwarding its keywords to its own structure call.
        declarations = vars(adapter_class).get('PARAM_SPECS') if isinstance(adapter_class, type) else None
        if (not element_name or legacy_element) and kwargs and declarations is not None:
            # A declared noun whose structure call takes the overrides itself: an undeclared one is the same invalid
            # request, with the same message, as on a bound noun (rule 3, BACK-2654).
            from .utils.query_binding import reject_unsupported_overrides
            reject_unsupported_overrides(declarations, kwargs)
        if isinstance(adapter_class, type) and hasattr(adapter_class, "from_uri"):
            adapter = adapter_class.from_uri(scheme, resource, element_name)
        else:
            adapter = _default_from_uri(adapter_class, scheme, resource, element_name)

        if element_name:
            def element_answer():
                if legacy_element:
                    from .cli.invocation import retirement_note
                    retirement_note(legacy_element)  # inside the scope, so it reaches meta.warnings
                return adapter.get_element(element_name, **kwargs)
            result = _noted_answer(scheme, uri, kwargs, element_answer)
            if result is None:
                raise ValueError(f"Element {element_name!r} not found in {uri}")
            return _spelled(result)

        structure: Dict[str, Any] = _noted_answer(scheme, uri, kwargs, lambda: adapter.get_structure(**kwargs))
        return _spelled(structure)


def check(
    path: str,
    select: Optional[List[str]] = None,
    ignore: Optional[List[str]] = None,
) -> List:
    """Run quality checks on a file.

    Equivalent to ``reveal check myfile.py`` at the CLI, but returns a list of
    :class:`~reveal.rules.base.Detection` objects instead of printing them.

    Args:
        path: Path to the file to check.
        select: Rule codes or prefixes to include (e.g. ``["C", "M101"]``).
            When ``None`` all applicable rules run.
        ignore: Rule codes or prefixes to exclude (e.g. ``["E501"]``).

    Returns:
        List of :class:`~reveal.rules.base.Detection` objects.  Each has
        ``.rule_code``, ``.message``, ``.line``, ``.column``, ``.severity``,
        and ``.suggestion`` attributes.  Call ``.to_dict()`` for JSON-safe output.

    Each call is one host request, like :func:`query`: an edit made between two calls is
    seen by the second, including by project-wide rules such as I002.

    Raises:
        FileNotFoundError: If *path* does not exist on disk.

    Example::

        findings = check("mymodule.py", ignore=["E501"])
        errors = [f for f in findings if f.severity.value == "high"]
    """
    from .registry import get_analyzer
    from .rules import RuleRegistry
    from .utils.request_cache import host_request

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    path_str = str(file_path)
    content = file_path.read_text(encoding="utf-8", errors="replace")

    # One host request, as query() and an MCP tool call are: project-wide rule memos
    # (I002's import graph among them) are revalidated against the tree first (BACK-2093).
    with host_request():
        # Obtain structure if possible — rules use it for semantic analysis
        structure_data: Optional[Dict[str, Any]] = None
        analyzer_class = get_analyzer(path_str)
        if analyzer_class is not None:
            try:
                analyzer = analyzer_class(path_str)
                structure_data = analyzer.get_structure()
            except Exception as e:  # boundary-ok: broad-except -- public check() skips one file's structure and says so at warning; an analyzer is arbitrary per-language code
                logger.warning("check() get_structure failed for %s: %s", path_str, e)

        return RuleRegistry.check_file(
            path_str, structure_data, content, select=select, ignore=ignore
        )
