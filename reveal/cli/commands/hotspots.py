"""reveal hotspots — identify high-complexity, low-quality files and functions.

Thin argparse shim over the hotspots:// adapter (BACK-901/BACK-955); scanning
lives in reveal/adapters/hotspots.py and rendering in
reveal/rendering/adapters/hotspots.py. Scan helpers remain available here
for existing callers.
"""

import argparse
from argparse import Namespace

from reveal.adapters.hotspots import (  # noqa: F401 - re-exported for back-compat
    HotspotsAdapter,
    _build_test_name_index,
    _camel_to_snake,
    _is_covered,
    _run_file_hotspots,
    _run_function_hotspots,
)
from ...rendering.adapters.hotspots import HotspotsRenderer


def create_hotspots_parser() -> argparse.ArgumentParser:
    """Compatibility import; the adapter declaration owns the parser."""
    from ..routing.declared import create_declared_parser
    return create_declared_parser('hotspots')


def run_hotspots(args: Namespace) -> None:
    """Compatibility import; both spellings use the declared runner."""
    from ..routing.declared import run_declared_command
    run_declared_command('hotspots', args)
