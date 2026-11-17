"""What one invocation records for its answer, beside the answer itself.

A retired spelling's note and a configuration problem are each said once per invocation, however
many places meet them (the config of the walk root and of the cwd are two loads of one missing
``REVEAL_CONFIG``). The log lives here, below the CLI, so code at any layer can record into the
invocation that runs it without importing ``cli/``. ``cli.invocation.invocation_scope`` opens it
for the CLI and ``reveal.api``; the MCP server opens one per tool call.

A recorded warning is a ``meta.warnings`` entry. Every JSON document the invocation builds carries
it (``json_utils.attach_invocation_warnings``), and that is its one home when the answer is JSON
(COMMAND_MODEL "Transports"). Otherwise the outermost scope prints it on stderr once, after the
answer, when the host asked for stderr; a host that did not (MCP, the library API) returns it in
its result instead.
"""

import sys
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Iterator, List, Optional, Tuple


class InvocationLog:
    """The facts one invocation recorded. ``to_stderr`` is False for a host (MCP, the library
    API) that returns them in its result instead of printing them."""

    def __init__(self, to_stderr: bool = True) -> None:
        self.to_stderr = to_stderr
        self.noted: Dict[str, Any] = {}      # note-stage retired spellings, by RETIREMENTS key
        self.recorded: Dict[str, Any] = {}   # phase7-stage retired spellings, recorded only
        self.warnings: Dict[Tuple[str, str], Dict[str, Any]] = {}  # meta.warnings entries, by (code, message)
        self.attached: set = set()           # keys of warnings some JSON document carried
        self.json_answer = False             # the answer is a JSON document (CLI --format json)


_LOG: ContextVar[Optional[InvocationLog]] = ContextVar('reveal_invocation_log', default=None)


def current_log() -> Optional[InvocationLog]:
    """The log of the invocation being run, or None outside one (a plain library call)."""
    return _LOG.get()


@contextmanager
def log_scope(to_stderr: bool = True) -> Iterator[InvocationLog]:
    """Open a log for the code it runs. A scope inside another joins the open log (an MCP tool
    call's invocation runs inside the call's log), so a fact is recorded once. The outermost scope
    restores the previous state on exit, after printing what no JSON answer carried."""
    joined = _LOG.get()
    if joined is not None:
        yield joined
        return
    log = InvocationLog(to_stderr)
    token = _LOG.set(log)
    try:
        yield log
    finally:
        _LOG.reset(token)
        if log.to_stderr:
            for entry in unreported_warnings(log):
                print(f"warning: {entry['message']}", file=sys.stderr)  # boundary-ok: print -- the one stderr line of an invocation warning no JSON answer carried


def record_warning(entry: Dict[str, Any], log: Optional[InvocationLog] = None) -> bool:
    """Record a ``meta.warnings`` *entry* in the running invocation (or in *log*), once per (code,
    message). False outside any invocation: the caller logs it instead, as a library call always did."""
    log = log if log is not None else _LOG.get()
    if log is None:
        return False
    log.warnings.setdefault((entry['code'], entry['message']), entry)
    return True


def invocation_warnings() -> List[Dict[str, Any]]:
    """The warnings recorded so far, for a JSON document; each is then counted as carried."""
    log = _LOG.get()
    if log is None:
        return []
    log.attached.update(log.warnings)
    return list(log.warnings.values())


def unreported_warnings(log: Optional[InvocationLog] = None) -> List[Dict[str, Any]]:
    """The warnings the answer did not carry: all of them unless the answer is JSON, else the ones
    recorded after the last JSON document was built."""
    log = log if log is not None else _LOG.get()
    if log is None:
        return []
    return [entry for key, entry in log.warnings.items() if not (log.json_answer and key in log.attached)]


def answer_is_json(is_json: bool) -> None:
    """The entry point states the answer's format once it is parsed."""
    log = _LOG.get()
    if log is not None:
        log.json_answer = is_json


@contextmanager
def task_log() -> Iterator[InvocationLog]:
    """The log a pool task records into: its worker's (``open_worker_log``), else, for a pool
    started without that initializer or an executor that runs the task in the caller, the open
    one, else a silent one for this task only, so a task never leaves a log behind in its thread."""
    log = _LOG.get()
    if log is not None:
        yield log
        return
    own = InvocationLog(to_stderr=False)
    token = _LOG.set(own)
    try:
        yield own
    finally:
        _LOG.reset(token)


def open_worker_log() -> None:
    """A pool worker records into a log of its own that is never printed: its parent states the
    invocation's warnings, so the worker's process (spawn, forkserver) never prints them a
    second time, unprefixed, outside the answer."""
    _LOG.set(InvocationLog(to_stderr=False))
