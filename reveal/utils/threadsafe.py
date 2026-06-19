"""Thread-safety helpers for code paths that mix native objects with threads.

Reveal parses code with tree-sitter on the **main thread**. A tree-sitter
``Node`` is a PyO3 (Rust) object marked *unsendable*: it records its creating
thread and raises ``RuntimeError: ... is unsendable, but is being dropped on
another thread`` if it is ever destroyed on a different one.

Nodes themselves never cross threads, but they can linger as *cyclic* garbage
(held by frames, tracebacks, or caller locals — anything that needs the cyclic
collector rather than refcounting to free). Python's cyclic collector runs on
whichever thread happens to trip its allocation threshold. So when a rule opens
a ``ThreadPoolExecutor`` (e.g. L002's concurrent link checks), a worker thread
can run a GC pass that sweeps up a lingering main-thread Node and finalizes it
off-thread — surfacing the unsendable RuntimeError as benign-but-noisy
"Exception ignored" output.

``main_thread_gc`` closes that window: it sweeps existing cyclic garbage on the
main thread, then suspends automatic collection for the (short, I/O-bound) pool
so no worker thread can run one. Collection resumes — on the main thread — when
the block exits. Nothing is hidden: real leaks would still accumulate and be
collected safely on the main thread.
"""

from __future__ import annotations

import gc
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def main_thread_gc() -> Iterator[None]:
    """Keep cyclic GC on the main thread for the duration of the block.

    Use around a ``ThreadPoolExecutor`` (or any worker-thread fan-out) that runs
    while unsendable native objects — tree-sitter ``Node``s — may exist as cyclic
    garbage. Prevents a worker thread from finalizing them off-thread.

    Safe to nest and safe if GC was already disabled: the prior enabled/disabled
    state is restored on exit.
    """
    was_enabled = gc.isenabled()
    # Sweep any existing cyclic garbage (e.g. lingering Nodes) here, on the
    # main thread, before worker threads start allocating.
    gc.collect()
    gc.disable()
    try:
        yield
    finally:
        if was_enabled:
            gc.enable()
