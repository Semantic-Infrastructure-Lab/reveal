"""Stderr logging configuration for reveal's own logger.

Lives outside main.py so worker processes can configure themselves without
importing the CLI. BACK-1231: the handler that supplies the "WARNING: " prefix
was installed only by main(), which a ProcessPoolExecutor worker never runs.
Under the `fork` start method the child inherits the already-installed handler
and the prefix survives, which is why this was invisible on Linux/CPython<=3.13;
under `spawn` (macOS, Windows) and `forkserver` (CPython 3.14+ Linux default)
the child starts with no handlers, logging.lastResort takes over, and every
warning raised inside a worker reaches stderr as a bare unprefixed message.
"""

import logging
import sys


def configure_stderr_logging() -> None:
    """Give reveal's own logger.warning()+ calls a visible severity prefix.

    Without this, nothing under the CLI ever calls logging.basicConfig(),
    so Python's handler-of-last-resort takes over and prints just the bare
    message -- not even a generic "WARNING:" tag, let alone one a consumer
    could grep for (BACK-1231). Scoped to the 'reveal' logger, not root, so
    embedding reveal as a library doesn't have its host process's logging
    configuration overridden by importing this CLI module. Propagation is
    left at its default (True) -- disabling it would silently break any
    caller (including reveal's own test suite's caplog/assertLogs) that
    listens for 'reveal.*' records via the root logger.
    """
    reveal_logger = logging.getLogger('reveal')
    if reveal_logger.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    reveal_logger.addHandler(handler)
    reveal_logger.setLevel(logging.WARNING)


def worker_bootstrap(inner=None, inner_args=()) -> None:
    """ProcessPoolExecutor initializer: configure logging, then run *inner*.

    BACK-1231: every pool in reveal needs the logging setup, and several
    already pass an initializer to seed their own caches. Composing here keeps
    one initializer per pool rather than making each site choose between the
    two. *inner* must be module-level so it stays picklable under spawn and
    forkserver, which is where this matters -- under fork the whole thing is
    inherited anyway.
    """
    configure_stderr_logging()
    if inner is not None:
        inner(*inner_args)
