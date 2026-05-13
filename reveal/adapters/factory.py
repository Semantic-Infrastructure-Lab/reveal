"""Adapter initialization factory — try-chain constructor patterns for from_uri.

These helpers are used by ResourceAdapter.from_uri and by the router when
initializing adapters that don't inherit ResourceAdapter (e.g. test doubles).
Each _try_* function returns (adapter_instance, error) — non-None adapter = success.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple


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
    """Try no-argument initialization (env, python adapters)."""
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


def _default_from_uri(adapter_class: type, scheme: str, resource: str,
                      element: Optional[str]) -> Any:
    """Default try-chain initialization used by ResourceAdapter.from_uri.

    Available as a standalone function so the router can apply it to any
    adapter class (including test doubles that don't inherit ResourceAdapter).

    Raises:
        ImportError: If initialization failed due to a missing optional dependency.
        RuntimeError: If all initialization attempts failed.
    """
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
