"""reveal surface — external boundary map for a codebase.

Thin argparse shim over the surface:// adapter (BACK-904); scan/render logic
lives in reveal/adapters/surface.py. Internal names are re-exported here for
backward compatibility with existing callers/tests.
"""

import argparse
from argparse import Namespace

from reveal.adapters.surface import (  # noqa: F401 - re-exported for back-compat
    SurfaceAdapter,
    SurfaceRenderer,
    _CPP_SCANNER,
    _SURFACE_LABELS,
    _SURFACE_SCANNERS,
    _SurfaceScanner,
    _collect_source_files,
    _is_test_dir,
    _is_test_file,
    _load_scanner,
    _scan_surface,
    _supported_coverage_languages,
)


def create_surface_parser() -> argparse.ArgumentParser:
    """Compatibility import; the adapter declaration owns the parser."""
    from ..routing.declared import create_declared_parser
    return create_declared_parser('surface')


def run_surface(args: Namespace) -> None:
    """Compatibility import; both public spellings use the common runner."""
    from ..routing.declared import run_declared_command
    run_declared_command('surface', args)
