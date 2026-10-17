"""Compatibility imports for the declared architecture command."""

import argparse
from argparse import Namespace

from reveal.adapters.architecture import (  # noqa: F401 - re-exported for back-compat
    ArchitectureAdapter,
    _build_next_commands,
    _compute_risks,
    _format_imports_data,
    _is_test_file,
    _relpath,
    _run_combined_analysis,
    _run_complex_functions,
    _run_imports_analysis,
    _run_scope,
)
from ...rendering.adapters.architecture import ArchitectureRenderer


def create_architecture_parser() -> argparse.ArgumentParser:
    """Compatibility import; the adapter declaration owns the parser."""
    from ..routing.declared import create_declared_parser
    return create_declared_parser('architecture')


def run_architecture(args: Namespace) -> None:
    """Compatibility import; both spellings use the declared runner."""
    from ..routing.declared import run_declared_command
    run_declared_command('architecture', args)
