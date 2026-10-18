"""reveal pack — token-budgeted context snapshot for LLM consumption.

Thin argparse shim over the pack:// adapter. Scan/rank logic lives in
reveal/adapters/pack.py; presentation lives in rendering/adapters/pack.py.
Scan helpers and the MCP string formatter remain available here for
reveal_pack and existing callers; text rendering belongs to PackRenderer.
"""

import argparse
from argparse import Namespace

from reveal.adapters.pack import (  # noqa: F401 - re-exported for back-compat
    PackAdapter,
    _apply_budget,
    _build_pack_import_graph,
    _collect_candidates,
    _collect_file_contents,
    _compute_graph_relevance,
    _compute_priority,
    _count_lines,
    _fetch_fan_in,
    _get_changed_files,
    _get_file_raw_content,
    _get_file_structure,
    _parse_budget,
    _walk_files,
)
from ...rendering.adapters.pack import (  # noqa: F401 - MCP helper re-export
    PackRenderer, _format_pack_result,
)


def create_pack_parser() -> argparse.ArgumentParser:
    """Compatibility import; the adapter declaration owns the parser."""
    from ..routing.declared import create_declared_parser
    return create_declared_parser('pack')


def run_pack(args: Namespace) -> None:
    """Compatibility import; both spellings use the declared runner."""
    from ..routing.declared import run_declared_command
    run_declared_command('pack', args)
