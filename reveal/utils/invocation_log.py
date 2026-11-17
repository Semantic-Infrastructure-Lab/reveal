"""What one invocation records for its answer, beside the answer itself.

A retired spelling's note is said once per invocation, however many places parse the spelling.
The log lives here, below the CLI, so code at any layer can record into the invocation that runs
it without importing ``cli/``. ``cli.invocation.invocation_scope`` opens it for the CLI, for
``reveal.api`` and for every MCP tool call.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Iterator, Optional


class InvocationLog:
    """The facts one invocation recorded. ``to_stderr`` is False for a host (MCP, the library
    API) that returns them in its result instead of printing them."""

    def __init__(self, to_stderr: bool = True) -> None:
        self.to_stderr = to_stderr
        self.noted: Dict[str, Any] = {}      # note-stage retired spellings, by RETIREMENTS key
        self.recorded: Dict[str, Any] = {}   # phase7-stage retired spellings, recorded only


_LOG: ContextVar[Optional[InvocationLog]] = ContextVar('reveal_invocation_log', default=None)


def current_log() -> Optional[InvocationLog]:
    """The log of the invocation being run, or None outside one (a plain library call)."""
    return _LOG.get()


@contextmanager
def log_scope(to_stderr: bool = True) -> Iterator[InvocationLog]:
    """Open a fresh log for the code it runs and restore the previous one on exit."""
    log = InvocationLog(to_stderr)
    token = _LOG.set(log)
    try:
        yield log
    finally:
        _LOG.reset(token)
