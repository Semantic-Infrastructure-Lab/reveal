"""Compatibility exports for testability; execution belongs to its declared owner."""
import argparse
from argparse import Namespace

from reveal.adapters.testability import (  # noqa: F401 -- existing helper imports
    TestabilityAdapter, TestabilityRenderer, _resolve_test_paths,
)
from reveal.rendering.adapters.testability import testability_text  # noqa: F401


def create_testability_parser() -> argparse.ArgumentParser:
    """Build the parser from the testability declaration."""
    from ..routing.declared import create_declared_parser
    return create_declared_parser('testability')


def run_testability(args: Namespace) -> None:
    """Run either spelling through the common declared boundary."""
    from ..routing.declared import run_declared_command
    run_declared_command('testability', args)
