"""Compatibility exports for trace; execution belongs to the declared owner."""
import argparse
from argparse import Namespace

from reveal.adapters.trace import (  # noqa: F401 -- existing helper import compatibility
    TraceAdapter, TraceRenderer, _build_trace, _collect_function_index,
    _effects_from_calls, _params_from_signature, _relpath, _render_trace,
)


def create_trace_parser() -> argparse.ArgumentParser:
    """Compatibility import; the trace declaration owns the parser."""
    from ..routing.declared import create_declared_parser
    return create_declared_parser('trace')


def run_trace(args: Namespace) -> None:
    """Compatibility import; both public spellings use the common runner."""
    from ..routing.declared import run_declared_command
    run_declared_command('trace', args)
