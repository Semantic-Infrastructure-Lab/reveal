"""Compatibility imports for the declared deps command."""

import argparse
from argparse import Namespace

from reveal.adapters.deps import (  # noqa: F401 - re-exported for back-compat
    DepsAdapter, DepsRenderer, _analyse_imports, _local_package_names,
    _run_base, _run_circular, _run_unused, _summarize_base_files,
)


def create_deps_parser() -> argparse.ArgumentParser:
    """Compatibility import; the adapter declaration owns the parser."""
    from ..routing.declared import create_declared_parser
    return create_declared_parser('deps')


def run_deps(args: Namespace) -> None:
    """Compatibility import; both spellings use the declared runner."""
    from ..routing.declared import run_declared_command
    run_declared_command('deps', args)
