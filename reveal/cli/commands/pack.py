"""reveal pack — token-budgeted context snapshot for LLM consumption.

Thin argparse shim over the pack:// adapter (BACK-901/BACK-961); scan/rank/
render logic lives in reveal/adapters/pack.py. Internal names are
re-exported here for backward compatibility with existing callers/tests —
including the reveal_pack MCP tool, which imports five of these functions
directly (_parse_budget, _get_changed_files, _collect_candidates,
_apply_budget, _format_pack_result) and is untouched by this refactor.
"""

import sys
from argparse import Namespace
from functools import partial
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
from ..global_flags import add_exclude_argument, add_gitignore_arguments
from ..routing.subcommand import emit_subcommand_result


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
            "Prioritization order:\n"
            "  1. Changed files (with --since; git diff vs ref)\n"
            "  2. Entry points and root config (main.py, index.js, package.json, etc.)\n"
            "  3. Files matching --focus, and files tied to them by imports\n"
            "  4. Key directories (api/, core/, models/, auth/, ...) and, with\n"
            "     --architecture, widely imported files\n"
            "  5. Other files (fills remaining budget); tests, vendor and docs last\n"
            "  Ties go to the most recently modified file.\n"
            "\n"
            "--budget counts the raw size of the files selected, not the output.\n"
            "With --content: changed files are shown raw (first 500 lines), key files\n"
            "as structure, and the remaining selected files by name only.\n"
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
        help='Emit content for the selected files: changed files raw (first 500 lines), key files as structure, the rest by name only.'
    )
    parser.add_argument(
        '--architecture',
        action='store_true',
        default=False,
        help='Boost high fan-in (core abstraction) files; prepend architecture brief before content.'
    )
    add_exclude_argument(parser)
    add_gitignore_arguments(parser)
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

    emit_subcommand_result(result, args, name='pack', source=path, render=partial(
        PackRenderer.render_structure, format=args.format, verbose=args.verbose,
        architecture=architecture, content=emit_content,
    ))
