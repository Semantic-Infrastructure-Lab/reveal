"""reveal trace — execution narrative from an entry-point function.

Thin argparse shim over the trace:// adapter (BACK-901/BACK-960); BFS/render
logic lives in reveal/adapters/trace.py. Internal names are re-exported here
for backward compatibility with existing callers/tests, and — unchanged —
the reveal_trace MCP tool imports run_trace from this module directly.
"""

from __future__ import annotations

import argparse
import json
import sys
from argparse import Namespace
from pathlib import Path

from reveal.adapters.trace import (  # noqa: F401 - re-exported for back-compat
    TraceAdapter,
    TraceRenderer,
    _bfs_depth,
    _build_trace,
    _collect_function_index,
    _effects_from_calls,
    _params_from_signature,
    _relpath,
    _render_trace,
)


def create_trace_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='reveal trace',
        description=(
            'Walk the call graph from a named entry point and print a '
            'depth-indented execution narrative.  Each frame shows the '
            'function location, its parameters, classified side-effects, '
            'and what it calls next.'
        ),
    )
    parser.add_argument(
        'path', nargs='?', default='.',
        help='Source directory to analyse (default: .)',
    )
    parser.add_argument(
        '--from', dest='root', required=True, metavar='FUNC',
        help='Entry-point function to start the trace from',
    )
    parser.add_argument(
        '--depth', type=int, default=2, metavar='N',
        help='How many call levels to expand (1–5, default 2)',
    )
    parser.add_argument(
        '--format', choices=['text', 'json'], default='text',
        help='Output format: text (default) or json',
    )
    return parser


def run_trace(args: Namespace) -> None:
    path = Path(args.path).resolve()
    if not path.exists():
        print(f"reveal trace: path not found: {path}", file=sys.stderr)
        sys.exit(1)

    depth = max(1, min(args.depth if args.depth is not None else 2, 5))
    query = f'from={args.root}&depth={depth}'
    result = TraceAdapter(str(path), query).get_structure()

    if result['frames'] and not result['frames'][0]['resolved']:
        print(
            f"reveal trace: '{args.root}' not found in {path}\n"
            f"  Check spelling or run: reveal {path}",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.format == 'json':
        from reveal.utils.results import add_cli_contract_fields
        report = {
            k: v for k, v in result.items()
            if k not in ('contract_version', 'type', 'source', 'source_type', 'meta')
        }
        print(json.dumps(
            add_cli_contract_fields(report, result_type='trace', source=path),
            indent=2,
        ))
    else:
        TraceRenderer.render_structure(result, format=args.format)
