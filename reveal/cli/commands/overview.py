"""reveal overview — one-glance codebase dashboard.

Thin argparse shim over the overview:// adapter (BACK-901/BACK-958); scan/
render logic lives in reveal/adapters/overview.py. Internal names are
re-exported here for backward compatibility with existing callers/tests.
"""

import argparse
from argparse import Namespace

from reveal.adapters.overview import (  # noqa: F401 - re-exported for back-compat
    AstAdapter,
    GitAdapter,
    ImportsAdapter,
    OverviewAdapter,
    OverviewRenderer,
    StatsAdapter,
    UNLIMITED_TOP,
    _NON_CODE_EXT_LABELS,
    _age_label,
    _is_test_file,
    _language_breakdown,
    _relpath,
    _render_architecture,
    _render_codebase_stats,
    _render_complex_functions,
    _render_git_log,
    _render_hotspots,
    _render_language_breakdown,
    _render_next_steps,
    _render_overview,
    _render_quality_pulse,
    _resolve_git_root,
    _run_complex_functions,
    _run_git_log,
    _run_imports_analysis,
    _run_scope,
    _run_stats,
)
def create_overview_parser() -> argparse.ArgumentParser:
    """Compatibility import; the adapter declaration owns the parser."""
    from ..routing.declared import create_declared_parser
    return create_declared_parser('overview')


def run_overview(args: Namespace) -> None:
    """Compatibility import; both spellings use the declared runner."""
    from ..routing.declared import run_declared_command
    run_declared_command('overview', args)
