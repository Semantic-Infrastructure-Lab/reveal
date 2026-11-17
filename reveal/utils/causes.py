"""The cause text of a failure: the one rule, below every module that reports one.

``path_utils.failure_of`` records a failure with it, and the analyzer and adapter registries, which
``path_utils`` itself imports, describe a plugin that did not load with it (BACK-2659).
"""


def failure_cause(error: BaseException) -> str:
    """``Type: message``. ``str(OSError)`` embeds the absolute filename (``[Errno 13] Permission denied:
    '/abs/dir'``), so an ``OSError`` with a ``strerror`` is described by its class and ``strerror``
    alone; an OSError without one keeps its message, which names no path of its own."""
    if isinstance(error, OSError) and error.strerror:
        return f'{type(error).__name__}: {error.strerror}'
    return f'{type(error).__name__}: {error}'
