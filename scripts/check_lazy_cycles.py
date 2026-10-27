#!/usr/bin/env python3
"""Lazy-import cycle ratchet for reveal's own package (BACK-2215).

`imports://reveal?circular` reads the load-time graph, which has no cycles; with
`&lazy=include` reveal's files form cycle groups that close only through
function-level imports (a deferred `from ..cli.x import y` inside a function). Nothing
stopped one more: a single deferred import in a renderer grew the largest group from
99 to 155 files in a day. The ratchet holds two numbers from
scripts/lazy_cycles_baseline.json:

- files_in_cycles: files in any lazy-inclusive cycle group; may only fall.
- edges: every lazy edge inside a cycle group, as (importer, imported) paths relative
  to the repo root. A lazy edge inside a group that is not listed fails, naming the
  file and the import line, so a new deferred upward import is caught at the change
  that adds it. A listed edge that no longer closes a cycle also fails, so the list
  shrinks with the code (run --update-baseline).

The graph is reveal's own (`ImportsAdapter`, lazy edges included). Group count is not
held: removing an edge can split one group into two.

Usage:
  python scripts/check_lazy_cycles.py                    # check (exit 1 on a regression or a stale list)
  python scripts/check_lazy_cycles.py --update-baseline  # rewrite; refuses a larger count or a new edge
"""
import argparse
import json
import sys
from pathlib import Path
from typing import List, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / 'scripts' / 'lazy_cycles_baseline.json'

Edge = Tuple[str, str]


def measure(package: Path = ROOT / 'reveal', base: Path = ROOT) -> Tuple[int, Set[Edge]]:
    """Files in lazy-inclusive cycle groups under *package* and the lazy edges inside those groups,
    spelled relative to *base*."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from reveal.adapters.imports import ImportsAdapter

    base = base.resolve()
    graph = ImportsAdapter(str(package), 'circular&lazy=include').analyze().graph
    files = 0
    edges: Set[Edge] = set()
    for group in graph.find_cycle_groups():
        members = set(group)
        files += len(group)
        for importer in group:
            for imported in graph._cycle_successors(importer):
                if imported in members and graph.is_lazy_edge(importer, imported):
                    edges.add((Path(importer).resolve().relative_to(base).as_posix(),
                               Path(imported).resolve().relative_to(base).as_posix()))
    return files, edges


def load_baseline() -> Tuple[int, Set[Edge]]:
    data = json.loads(BASELINE.read_text(encoding='utf-8'))
    return data['files_in_cycles'], {tuple(e) for e in data['edges']}


def _import_lines(edge: Edge) -> List[str]:
    """The function-level import statements in the importer that name the imported module (best effort)."""
    importer, imported = edge
    stem = Path(imported).stem if Path(imported).stem != '__init__' else Path(imported).parent.name
    source = ROOT / importer
    if not source.is_file():
        return []
    text = source.read_text(encoding='utf-8').split('\n')
    return [f'{importer}:{n}: {line.strip()}' for n, line in enumerate(text, 1)
            if line.startswith((' ', '\t')) and 'import' in line and stem in line]


def compare(files: int, edges: Set[Edge], base_files: int, base_edges: Set[Edge]) -> List[str]:
    problems = []
    if files > base_files:
        problems.append(f'files in lazy-import cycles rose: {base_files} -> {files}')
    for edge in sorted(edges - base_edges):
        where = _import_lines(edge) or [f'{edge[0]} -> {edge[1]}']
        problems.append('new lazy import inside a cycle group (import it the other way round, or move the '
                        'function down a layer): ' + '; '.join(where))
    gone = sorted(base_edges - edges)
    if gone or files < base_files:
        problems.append(f'baseline is stale ({len(gone)} listed edge(s) no longer close a cycle, files '
                        f'{base_files} -> {files}): run python scripts/check_lazy_cycles.py --update-baseline')
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--update-baseline', action='store_true')
    args = parser.parse_args(argv)
    files, edges = measure()
    base_files, base_edges = load_baseline() if BASELINE.exists() else (files, edges)
    if args.update_baseline:
        if files > base_files or edges - base_edges:
            print(f'refusing to raise the baseline: files {base_files} -> {files}, '
                  f'{len(edges - base_edges)} new edge(s)', file=sys.stderr)
            return 1
        rows = ',\n'.join(f'  {json.dumps(list(e))}' for e in sorted(edges))  # one edge per line: reviewable diffs
        BASELINE.write_text(f'{{\n "files_in_cycles": {files},\n "edges": [\n{rows}\n ]\n}}\n', encoding='utf-8')
        print(f'lazy-cycle baseline: {files} files, {len(edges)} in-cycle lazy edges')
        return 0
    problems = compare(files, edges, base_files, base_edges)
    for p in problems:
        print(p, file=sys.stderr)
    if not problems:
        print(f'lazy-cycle ratchet OK ({files} files in cycles, {len(edges)} in-cycle lazy edges)')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
