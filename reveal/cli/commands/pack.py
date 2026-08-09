"""reveal pack — token-budgeted context snapshot for LLM consumption.

Thin argparse shim over the pack:// adapter (BACK-901/BACK-961); scan/rank/
render logic lives in reveal/adapters/pack.py. Internal names are
re-exported here for backward compatibility with existing callers/tests —
including the reveal_pack MCP tool, which imports five of these functions
directly (_parse_budget, _get_changed_files, _collect_candidates,
_apply_budget, _format_pack_result) and is untouched by this refactor.
"""

import json
import sys
from argparse import Namespace
from pathlib import Path
import argparse

from reveal.adapters.pack import (  # noqa: F401 - re-exported for back-compat
    PackAdapter,
    PackRenderer,
    _apply_budget,
    _build_pack_import_graph,
    _collect_candidates,
    _collect_file_contents,
    _compute_graph_relevance,
    _compute_priority,
    _count_lines,
    _emit_content_section,
    _fetch_fan_in,
    _format_file_line,
    _format_pack_content,
    _format_pack_file_groups,
    _format_pack_header,
    _format_pack_result,
    _get_changed_files,
    _get_file_raw_content,
    _get_file_structure,
    _parse_budget,
    _print_file_line,
    _print_pack_file_groups,
    _print_pack_header,
    _render_architecture_brief,
    _render_pack,
    _walk_files,
)


def create_pack_parser() -> argparse.ArgumentParser:
    """Create parser for reveal pack subcommand."""
    from reveal.cli.parser import _build_global_options_parser
    parser = argparse.ArgumentParser(
        prog='reveal pack',
        parents=[_build_global_options_parser()],
        description='Curate a token-budgeted context snapshot for LLM consumption.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  reveal pack ./src                      # Default 2000-token budget\n"
            "  reveal pack ./src --budget 4000        # 4000-token budget\n"
            "  reveal pack ./src --budget 500-lines   # 500-line budget\n"
            "  reveal pack ./src --focus auth         # Emphasize auth module\n"
            "  reveal pack ./src --since main         # PR review: changed files first\n"
            "  reveal pack ./src --since HEAD~3       # Changes since 3 commits ago\n"
            "  reveal pack ./src --content            # Emit structure content (agent-ready)\n"
            "  reveal pack ./src --content --since main --budget 8000  # Full agent context\n"
            "  reveal pack ./src --format json        # Structured output for tooling\n"
            "  reveal pack ./src --architecture       # Boost core abstractions; show architecture brief\n"
            "\n"
            "Prioritization order (with --since):\n"
            "  1. Changed files (git diff vs ref)\n"
            "  2. Entry points (main.py, index.js, etc.)\n"
            "  3. High-complexity files\n"
            "  4. Recently modified files\n"
            "  5. Other files (fills remaining budget)\n"
        )
    )
    parser.add_argument(
        'path',
        metavar='PATH',
        help='Directory or file to pack'
    )
    parser.add_argument(
        '--budget',
        metavar='N[=tokens|-lines]',
        default='2000',
        help='Token or line budget (e.g., 2000, 4000, 500-lines). Default: 2000 tokens'
    )
    parser.add_argument(
        '--focus',
        metavar='TOPIC',
        help='Emphasize files matching this name pattern (e.g., auth, api, models)'
    )
    parser.add_argument(
        '--since',
        metavar='REF',
        help='Git ref to diff against (e.g., main, HEAD~3). Changed files are boosted to top priority.'
    )
    parser.add_argument(
        '--content',
        action='store_true',
        default=False,
        help='Emit reveal structure output for each selected file (agent-ready context, not just file list).'
    )
    parser.add_argument(
        '--architecture',
        action='store_true',
        default=False,
        help='Boost high fan-in (core abstraction) files; prepend architecture brief before content.'
    )
    return parser


def run_pack(args: Namespace) -> None:
    """Run the pack workflow."""
    path = Path(args.path)
    if not path.exists():
        print(f"Error: {args.path}: not found", file=sys.stderr)
        sys.exit(1)

    focus = getattr(args, 'focus', None)
    since = getattr(args, 'since', None)
    architecture = getattr(args, 'architecture', False)
    emit_content = getattr(args, 'content', False)

    query_parts = [f'budget={args.budget}']
    if focus:
        query_parts.append(f'focus={focus}')
    if since:
        query_parts.append(f'since={since}')
    query_parts.append(f'content={"true" if emit_content else "false"}')
    query_parts.append(f'architecture={"true" if architecture else "false"}')
    query = '&'.join(query_parts)

    adapter = PackAdapter(str(path), query)
    result = adapter.get_structure()

    if since and adapter.since_error:
        print(f"Warning: --since: {adapter.since_error}", file=sys.stderr)
    if adapter.relevance_warning:
        print(f"Warning: {adapter.relevance_warning}", file=sys.stderr)

    if args.format == 'json':
        from reveal.utils.results import add_cli_contract_fields
        from reveal.utils.json_utils import attach_provenance
        # Note: unlike other migrated commands, 'meta' is NOT stripped here —
        # PackAdapter.get_structure() never passes parse_mode/confidence/
        # warnings/errors to ResultBuilder.create(), so ResultBuilder never
        # injects its own envelope 'meta' key. The 'meta' key present in
        # `result` is always pack's own selection-metadata dict (real data),
        # not a contract artifact — stripping it would silently drop it.
        report = {
            k: v for k, v in result.items()
            if k not in ('contract_version', 'type', 'source', 'source_type')
        }
        print(json.dumps(
            attach_provenance(add_cli_contract_fields(report, result_type='pack', source=path)),
            indent=2, default=str,
        ))
        return

    PackRenderer.render_structure(
        result, format=args.format, verbose=args.verbose,
        architecture=architecture, content=emit_content,
    )
