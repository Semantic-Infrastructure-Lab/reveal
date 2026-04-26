"""reveal trace — execution narrative from an entry-point function."""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


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

    depth = max(1, min(args.depth, 5))
    report = _build_trace(str(path), args.root, depth)

    if report['frames'] and not report['frames'][0]['resolved']:
        print(
            f"reveal trace: '{args.root}' not found in {path}\n"
            f"  Check spelling or run: reveal {path}",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.format == 'json':
        print(json.dumps(report, indent=2))
    else:
        _render_trace(report)


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def _build_trace(path: str, root: str, depth: int) -> Dict[str, Any]:
    """Build a trace report: BFS call tree augmented with per-function info."""
    from reveal.adapters.calls.index import find_callees_recursive

    bfs = find_callees_recursive(path, root, depth=depth)
    func_index = _collect_function_index(path)

    # children map: name → ordered list of callee names
    children: Dict[str, List[str]] = {}
    for lvl in bfs.get('levels', []):
        for entry in lvl['callees']:
            caller = entry['caller']
            callee = entry['callee']
            children.setdefault(caller, [])
            if callee not in children[caller]:
                children[caller].append(callee)

    # BFS visit order so frames render root-first, then level 1, level 2 …
    visited_order: List[str] = [root]
    seen: Set[str] = {root}
    for lvl in bfs.get('levels', []):
        for entry in lvl['callees']:
            callee = entry['callee']
            if callee not in seen:
                seen.add(callee)
                visited_order.append(callee)

    frames = []
    for name in visited_order:
        info = func_index.get(name, {})
        level = _bfs_depth(name, root, bfs)
        frame: Dict[str, Any] = {
            'name': name,
            'file': info.get('file', ''),
            'line': info.get('line', 0),
            'params': info.get('params', []),
            'effects': info.get('effects', []),
            'calls': children.get(name, []),
            'depth': level,
            'resolved': bool(info),
        }
        frames.append(frame)

    return {
        'root': root,
        'path': path,
        'depth': depth,
        'frames': frames,
        'total_resolved': bfs.get('total_resolved', 0),
        'total_unresolved': bfs.get('total_unresolved', 0),
    }


def _bfs_depth(name: str, root: str, bfs: Dict[str, Any]) -> int:
    if name == root:
        return 0
    for lvl in bfs.get('levels', []):
        for entry in lvl['callees']:
            if entry['callee'] == name:
                return lvl['level']
    return -1


def _collect_function_index(path: str) -> Dict[str, Dict[str, Any]]:
    """Scan all Python files under *path* and return name → info dict."""
    from reveal.adapters.ast.analysis import collect_structures

    structures = collect_structures(path)
    index: Dict[str, Dict[str, Any]] = {}
    file_trees: Dict[str, ast.Module] = {}

    for file_struct in structures:
        file_path = file_struct.get('file', '')
        if not file_path.endswith('.py'):
            continue
        if file_path not in file_trees:
            try:
                source = Path(file_path).read_text(encoding='utf-8', errors='ignore')
                file_trees[file_path] = ast.parse(source)
            except (OSError, SyntaxError):
                continue

        tree = file_trees[file_path]
        func_nodes: Dict[str, ast.FunctionDef] = {
            n.name: n  # type: ignore[misc]
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        for elem in file_struct.get('elements', []):
            if elem.get('category') not in ('functions', 'methods'):
                continue
            name = elem.get('name', '')
            if not name or name in index:
                continue
            node = func_nodes.get(name)
            params: List[str] = []
            effects: List[str] = []
            if node:
                params = [a.arg for a in node.args.args if a.arg != 'self']
                effects = _extract_effects(node)
            index[name] = {
                'file': file_path,
                'line': elem.get('line', 0),
                'params': params,
                'effects': effects,
            }

    return index


def _extract_effects(func_node: ast.FunctionDef) -> List[str]:  # type: ignore[type-arg]
    """Return deduplicated effect labels for classified call sites in *func_node*."""
    from reveal.adapters.ast.nav_effects import classify_call

    effects: List[str] = []
    seen: Set[str] = set()
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call):
            continue
        callee = _call_name(node.func)
        if not callee:
            continue
        kind = classify_call(callee)
        if kind:
            label = f"{kind}:{callee.split('.')[-1]}"
            if label not in seen:
                seen.add(label)
                effects.append(label)
    return effects


def _call_name(node: ast.expr) -> Optional[str]:  # type: ignore[type-arg]
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        obj = _call_name(node.value)
        return f"{obj}.{node.attr}" if obj else node.attr
    return None


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_trace(report: Dict[str, Any]) -> None:
    root = report['root']
    path = report['path']
    depth = report['depth']
    frames = report['frames']
    total_r = report['total_resolved']
    total_u = report['total_unresolved']

    print(f"Trace: {root}  (depth {depth})")
    print(f"Project: {path}")
    print(f"Resolved: {total_r}  External/unresolved: {total_u}")
    print()

    if not frames:
        print(f"  No functions found for '{root}'.")
        return

    for frame in frames:
        d = frame['depth']
        indent = '  ' * d
        name = frame['name']

        loc = ''
        if frame['file']:
            rel = _relpath(frame['file'], path)
            loc = f"  [{rel}:{frame['line']}]" if frame['line'] else f"  [{rel}]"

        marker = '' if frame['resolved'] else '  [external]'
        print(f"{indent}{name}{loc}{marker}")

        inner = indent + '  '
        if frame['params']:
            print(f"{inner}params:  {', '.join(frame['params'])}")
        if frame['effects']:
            print(f"{inner}effects: {', '.join(frame['effects'])}")
        if frame['calls']:
            print(f"{inner}calls:   {', '.join(frame['calls'])}")
        print()


def _relpath(file_str: str, base: str) -> str:
    try:
        return os.path.relpath(file_str, base)
    except ValueError:
        return file_str
