"""Adapter initialization factory — canonical construction and legacy fallback.

These helpers are used by ResourceAdapter.from_uri and by the router when
initializing adapters that don't inherit ResourceAdapter (e.g. test doubles).
Each _try_* function returns (adapter_instance, error) — non-None adapter = success.

Built-in adapters accept positional resource and query arguments
(LEGACY_INIT = False, BACK-907) and construct via _canonical_init instead.
The 5-strategy try-chain below is reachable only for test doubles and
third-party/plugin adapters that subclass ResourceAdapter without opting in
(LEGACY_INIT defaults to True).
It is kept as an explicit, deprecated compatibility shim for that case
rather than deleted, so existing plugins don't break silently — see
_default_from_uri's one-time-per-class deprecation warning.
"""

from __future__ import annotations

import warnings
from typing import Any, Callable, Mapping, Optional, Set, Tuple

# Adapter classes already warned about LEGACY_INIT — one warning per class,
# not per call, so a hot loop through a legacy plugin adapter doesn't spam.
_legacy_init_warned: Set[type] = set()


def _is_constructor_error(exc: TypeError) -> bool:
    """Return True if TypeError originated inside a constructor body.

    A call-site TypeError (wrong number/type of arguments) is raised before
    Python enters the constructor frame — its traceback has only one frame.
    A TypeError raised inside __init__ has at least two frames (call site +
    constructor body).  Detecting this lets _default_from_uri propagate real
    constructor bugs rather than silently trying the next init pattern.
    """
    tb = exc.__traceback__
    return tb is not None and tb.tb_next is not None


def _try_no_args_init(adapter_class: type) -> Tuple[Any, Optional[Exception]]:
    """Try no-argument initialization (env://)."""
    try:
        return adapter_class(), None
    except (TypeError, ValueError, FileNotFoundError, IsADirectoryError):
        return None, None
    except ImportError as e:
        return None, e


def _try_query_parsing_init(adapter_class: type, resource: str) -> Tuple[Any, Optional[Exception]]:
    """Try query-parsing initialization (ast, json with ?query)."""
    if '?' not in resource:
        return None, None
    try:
        path, query = resource.split('?', 1)
        path = path or '.'
        return adapter_class(path, query), None
    except (TypeError, ValueError, FileNotFoundError, IsADirectoryError):
        return None, None
    except ImportError as e:
        return None, e


def _try_keyword_args_init(adapter_class: type, resource: str) -> Tuple[Any, Optional[Exception]]:
    """Try keyword arguments initialization (markdown with base_path/query)."""
    try:
        if '?' in resource:
            path_part, query = resource.split('?', 1)
            path = path_part.rstrip('/') if path_part else '.'
        else:
            path = resource.rstrip('/') if resource else '.'
            query = None
        return adapter_class(base_path=path, query=query), None
    except (TypeError, ValueError, FileNotFoundError, IsADirectoryError):
        return None, None
    except ImportError as e:
        return None, e


def _try_resource_arg_init(adapter_class: type, resource: str) -> Tuple[Any, Optional[Exception]]:
    """Try resource argument initialization (help, git, etc)."""
    if resource is None:
        return None, None
    try:
        if '?' not in resource:
            path = resource or '.'
            try:
                return adapter_class(path, None), None
            except (TypeError, ValueError, FileNotFoundError, IsADirectoryError):
                return adapter_class(resource), None
            except ImportError as e:
                return None, e
        else:
            return adapter_class(resource), None
    except (TypeError, ValueError, FileNotFoundError, IsADirectoryError) as e:
        return None, e
    except ImportError as e:
        return None, e


def _try_full_uri_init(adapter_class: type, scheme: str, resource: str,
                       element: Optional[str]) -> Tuple[Any, Optional[Exception]]:
    """Try full URI initialization (mysql, sqlite)."""
    try:
        full_uri = f"{scheme}://{resource}"
        if element and '://' in full_uri:
            full_uri = f"{full_uri}/{element}"
        return adapter_class(full_uri), None
    except (TypeError, ValueError, FileNotFoundError, IsADirectoryError) as e:
        return None, e
    except ImportError as e:
        return None, e


def uses_bound_query_call(adapter_class: type) -> bool:
    """Whether the class binds its query controls in its constructor and answers a zero-argument structure call. A
    class's own ``PARAM_SPECS`` with the canonical constructor is that declaration: its typed ``api.query`` keywords
    bind through the same binder and checks as its URI query (BACK-2656; a noun that declared its controls without the
    flag dropped or crashed on every keyword). ``BOUND_QUERY_CALL`` adopts it for a class that inherits its
    declaration (the retired ``stats://``, Architecture). Only a class's own declaration counts: a plugin subclass
    that inherits ``PARAM_SPECS`` keeps forwarding keywords to its structure call."""
    if not isinstance(adapter_class, type):
        return False
    own = adapter_class.__dict__
    return own.get('BOUND_QUERY_CALL') is True or (
        'PARAM_SPECS' in own and getattr(adapter_class, 'LEGACY_INIT', True) is False)


def scope_path_of(adapter_class: type, path: str) -> str:
    """The filesystem path a resource names: calls' `path:name` shorthand names `path` (BACK-1499).
    The adapter receives the resource as spelled; scope, the stat and `source` use this path."""
    resolve = getattr(adapter_class, 'resource_path', None)
    return str(resolve(path)) if resolve is not None else path


def predicted_result_type(adapter_class: type, params: Any, path: Optional[str] = None) -> str:
    """The type of the answer a request selects, known before analysis: ``result_type_for(params)`` (or the noun's
    ``RESULT_TYPE``), then, once the scope *path* is known, ``result_type_at(params, path)`` for an adapter whose
    type depends on what the path is (metrics answers a file with ``stats_file`` and a directory with
    ``stats_summary``); ``result_type_for`` cannot see the path."""
    select = getattr(adapter_class, 'result_type_for', None)
    result_type: str = select(params) if select is not None else getattr(adapter_class, 'RESULT_TYPE')
    refine = getattr(adapter_class, 'result_type_at', None)
    if path is not None and refine is not None:
        result_type = refine(params, path)
    return result_type


def answer_reads_control(adapter_class: type, name: str, selection: Any, path: Optional[str] = None) -> bool:
    """Whether the answer *selection* selects (a raw URI query, or a subcommand's typed values) reads control *name*,
    by the noun's own declarations (COMMAND_MODEL "Applicability"). A control that declares no answers, a noun that
    declares none, and a selection that does not bind (the request's own binding names that problem) read it."""
    if not _declares_applicability(adapter_class):
        return True
    declarations = getattr(adapter_class, 'PARAM_SPECS')
    spec = next((declaration for declaration in declarations if name in declaration.spellings), None)
    if spec is None or not spec.answers:
        return True
    from ..utils.query_binding import answer_reads, prepare_declared_params
    try:
        params = prepare_declared_params(declarations, selection, 'uri' if isinstance(selection, str) else 'typed')
    except ValueError:
        return True
    # An empty path is a path (codex:// names its catalog by it), as in the check's own prediction (_reject_unread_controls).
    scope = scope_path_of(adapter_class, path) if path is not None else None
    return answer_reads(declarations, spec, params, lambda: predicted_result_type(adapter_class, params, scope))


def _canonical_init(adapter_class: type, resource: str, *, params: Optional[Any] = None,
                    overrides: Optional[Mapping[str, Any]] = None) -> Any:
    """Construct a canonically-migrated adapter directly (BACK-907).

    Canonical signature is __init__(self, resource='', query=None, **kwargs).
    Splits resource on '?' the same way _try_query_parsing_init does, then
    calls the constructor once — no try-chain, no guessing, and any error
    raised inside __init__ propagates to the caller unmodified. Optional typed
    overrides bind after validating the URI query and reach the constructor as
    params, with URI resource paths using the adapter's declared codec. Legacy
    URI construction honors an explicitly declared resource codec; undeclared
    resources and already-bound typed paths keep their original spelling.
    Already-bound params and overrides are mutually exclusive.

    An empty resource defaults to adapter_class.CANONICAL_EMPTY_RESOURCE
    (see adapters/base.py) — '.' for path-based adapters (bare ast:// means
    "current directory"), '' for connection-string adapters (bare sqlite://
    must stay empty so the adapter's own validation/fallback fires instead
    of misreading '.' as a literal path/host).
    """
    if params is not None and overrides is not None:
        raise TypeError('params and overrides cannot be supplied together')
    if params is not None:
        # Already-bound input keeps literal '?' paths out of URI serialization.
        def construct() -> Any:
            if not getattr(adapter_class, 'SOURCE_BEFORE_CONTROLS', False):  # that adapter binds (and reads) them itself
                from ..utils.query_binding import withhold_flag_only
                withhold_flag_only(getattr(adapter_class, 'PARAM_SPECS', ()), params)
            return adapter_class(resource, params=params)
        return _built(adapter_class, resource, lambda: params, construct)
    empty_default = getattr(adapter_class, 'CANONICAL_EMPTY_RESOURCE', '.')
    if resource and '?' in resource:
        path, query = resource.split('?', 1)
        path = path or empty_default
    else:
        path = resource or empty_default
        query = None
    if overrides is not None:
        return _built_with_overrides(adapter_class, path, query, overrides, empty_default)
    spec = getattr(adapter_class, 'RESOURCE_SPEC', None)
    if spec is not None:
        from ..utils.query_binding import bind_resource_path
        path = bind_resource_path(spec, path, transport='uri',
                                  resolve=getattr(adapter_class, 'resource_path', None))
    from ..utils.query_binding import bind_declared_params
    # The adapter binds its own query; the check reads the same binding first, only when a control declares answers.
    return _built(adapter_class, path,
                  lambda: bind_declared_params(getattr(adapter_class, 'PARAM_SPECS'), query or '', transport='uri'),
                  lambda: adapter_class(path, query))


def _built_with_overrides(adapter_class: type, path: str, query: Optional[str], overrides: Mapping[str, Any],
                          empty_default: str) -> Any:
    """Typed overrides bind after validating the URI query, then reach the constructor as params."""
    from ..utils.query_binding import bind_declared_params, bind_resource_path
    from ..utils.query_parser import ResourceSpec
    spec = getattr(adapter_class, 'RESOURCE_SPEC', ResourceSpec(uri_default=empty_default))
    path = bind_resource_path(spec, path, transport='uri', resolve=getattr(adapter_class, 'resource_path', None))
    if getattr(adapter_class, 'SOURCE_BEFORE_CONTROLS', False):
        return _built(adapter_class, path, dict, lambda: adapter_class(path, query, overrides=overrides))
    validate = getattr(adapter_class, 'validate_original_request', None)

    def original(bound: Any) -> None:
        # The URI's own controls are judged as a request of their own before typed overrides, on every noun that
        # declares applicability, so an override cannot hide an invalid request (COMMAND_MODEL "Applicability",
        # Scott 2026-11-18, BACK-2692; Claude's own checks, BACK-2617). A valid URI an override then changes
        # (``search=None``) is an ordinary override.
        if validate:
            validate(bound, path)
        if overrides:
            _reject_unread_controls(adapter_class, bound, path)

    bound = bind_declared_params(getattr(adapter_class, 'PARAM_SPECS'), query or '', transport='uri',
                                 overrides=overrides, validate=original)
    return _built(adapter_class, path, lambda: bound, lambda: adapter_class(path, params=bound))


def _built(adapter_class: type, path: str, bound: Callable[[], Any], construct: Callable[[], Any]) -> Any:
    """Applicability (COMMAND_MODEL, BACK-2656), once for every transport: the CLI's declared dispatch, ``api.query``,
    the generic URI route and MCP all construct a declared adapter here. A control the selected answer does not read
    is an invalid request, raised before the adapter is built (*bound* gives the bound params), so before any analysis.
    A source that must be read before its controls bind (``SOURCE_BEFORE_CONTROLS``: JSON) binds them in its
    constructor, so the check reads that binding right after construction, still before the adapter answers."""
    if getattr(adapter_class, 'SOURCE_BEFORE_CONTROLS', False):
        adapter = construct()
        _reject_unread_controls(adapter_class, getattr(adapter, 'query_params', {}), path)
        return adapter
    if _declares_applicability(adapter_class):
        _reject_unread_controls(adapter_class, bound(), path)
    return construct()


def _declares_applicability(adapter_class: type) -> bool:
    """A noun's own ``PARAM_SPECS`` (as ``api.query``'s unsupported-control check reads it), or the declaration a
    retired spelling adopts with a class-local ``BOUND_QUERY_CALL`` (``uses_bound_query_call``: ``stats://``,
    Architecture), with a control that names its answers or the values of others it requires: only then is there an
    applicability check to run. A plugin subclass that inherits the declaration keeps its own behaviour."""
    if not isinstance(adapter_class, type):
        return False
    own = vars(adapter_class)
    adopted = 'PARAM_SPECS' in own or own.get('BOUND_QUERY_CALL') is True
    declarations = getattr(adapter_class, 'PARAM_SPECS', None) if adopted else None
    return any(getattr(spec, 'answers', ()) or getattr(spec, 'requires', ()) for spec in declarations or ())


def _reject_unread_controls(adapter_class: type, params: Any, path: str) -> None:
    if not _declares_applicability(adapter_class):
        return
    from ..utils.query_binding import reject_unread_controls
    reject_unread_controls(getattr(adapter_class, 'PARAM_SPECS'), params,
                           lambda: predicted_result_type(adapter_class, params, scope_path_of(adapter_class, path)))


def _default_from_uri(adapter_class: type, scheme: str, resource: str,
                      element: Optional[str]) -> Any:
    """Default try-chain initialization used by ResourceAdapter.from_uri.

    Available as a standalone function so the router can apply it to any
    adapter class (including test doubles that don't inherit ResourceAdapter).

    Adapters that opt into the canonical signature (LEGACY_INIT = False,
    see adapters/base.py) skip the try-chain entirely — see _canonical_init.
    Reaching the try-chain below now means either a test double or a
    third-party plugin adapter that hasn't migrated (BACK-948); a
    deprecation warning fires once per adapter_class in that case.

    Raises:
        ImportError: If initialization failed due to a missing optional dependency.
        RuntimeError: If all initialization attempts failed.
    """
    if not getattr(adapter_class, 'LEGACY_INIT', True):
        return _canonical_init(adapter_class, resource)

    if adapter_class not in _legacy_init_warned:
        _legacy_init_warned.add(adapter_class)
        class_name = getattr(adapter_class, '__qualname__', None) or repr(adapter_class)
        module_name = getattr(adapter_class, '__module__', '')
        full_name = f"{module_name}.{class_name}" if module_name else class_name
        warnings.warn(
            f"{full_name} is using reveal's deprecated 5-strategy constructor "
            "try-chain (LEGACY_INIT defaults to True). Migrate __init__ to the "
            "canonical signature __init__(self, resource='', query=None, "
            "**kwargs) and set LEGACY_INIT = False to opt out of the try-chain "
            "and its guessing overhead. See reveal/adapters/base.py for the "
            "contract.",
            DeprecationWarning,
            stacklevel=3,
        )

    if resource:
        init_attempts = [
            lambda: _try_query_parsing_init(adapter_class, resource),
            lambda: _try_resource_arg_init(adapter_class, resource),
            lambda: _try_keyword_args_init(adapter_class, resource),
            lambda: _try_no_args_init(adapter_class),
            lambda: _try_full_uri_init(adapter_class, scheme, resource, element),
        ]
    else:
        init_attempts = [
            lambda: _try_no_args_init(adapter_class),
            lambda: _try_query_parsing_init(adapter_class, resource),
            lambda: _try_keyword_args_init(adapter_class, resource),
            lambda: _try_resource_arg_init(adapter_class, resource),
            lambda: _try_full_uri_init(adapter_class, scheme, resource, element),
        ]

    init_error: Optional[Exception] = None
    for attempt in init_attempts:
        adapter, error = attempt()
        if adapter is not None:
            return adapter
        if error is not None:
            # TypeError that originated inside the constructor body (not a
            # call-site signature mismatch) is a real bug — propagate it
            # immediately rather than silently trying the next init pattern.
            if isinstance(error, TypeError) and _is_constructor_error(error):
                raise error
            init_error = error

    if isinstance(init_error, ImportError):
        raise init_error
    raise RuntimeError(
        f"Could not initialize {scheme}:// adapter: {init_error}"
    )
