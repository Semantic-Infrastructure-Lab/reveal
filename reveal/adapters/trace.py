"""trace:// adapter - execution narrative from an entry-point function.

Walks the call graph from a named entry point (BFS via calls:// machinery)
and builds a depth-indented narrative: each frame shows the function
location, its parameters, classified side-effects, and what it calls next.
Scan/render logic lives here (BACK-901/BACK-960); `cli/commands/trace.py` is
a thin argparse shim over this adapter, unchanged in its own CLI/MCP
contract (BACK-216/BACK-839 — `reveal trace` and the `reveal_trace` MCP
tool both keep working exactly as before).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from reveal.reveal_types import CONTRACT_VERSION

from .base import ResourceAdapter, register_adapter, register_renderer
from ..utils import print_json_result
from ..utils.query import parse_query_params
from ..utils.results import ResultBuilder


def _build_trace(path: str, root: str, depth: int) -> Dict[str, Any]:
    """Build a trace report: BFS call tree augmented with per-function info."""
    from reveal.adapters.calls.index import _lang_family, find_callees_recursive

    bfs = find_callees_recursive(path, root, depth=depth)
    func_index = _collect_function_index(path)

    # children map: name → ordered list of callee names
    children: Dict[str, List[str]] = {}
    # BACK-405: only trust a bare-name lookup in func_index for a callee that
    # the (language-scoped) BFS actually resolved, and only against the
    # language family(ies) it resolved through — otherwise a same-named
    # definition in an unrelated language (e.g. a Python `def write` next to
    # a C `write()` syscall) renders as if it were the real target.
    resolved_families: Dict[str, Set[str]] = {}
    for lvl in bfs.get('levels', []):
        for entry in lvl['callees']:
            caller = entry['caller']
            callee = entry['callee']
            children.setdefault(caller, [])
            if callee not in children[caller]:
                children[caller].append(callee)
            if entry['resolved']:
                resolved_families.setdefault(callee, set()).add(
                    _lang_family(entry['caller_file'])
                )

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
        candidates = func_index.get(name, [])
        if name == root:
            info = candidates[0] if candidates else {}
        else:
            families = resolved_families.get(name)
            info = (
                next((c for c in candidates if _lang_family(c['file']) in families), {})
                if families else {}
            )
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


def _collect_function_index(path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Scan all files under *path* via collect_structures and return name → [info, ...].

    Returns every same-named definition (not just the first) so callers can
    disambiguate by language family (BACK-405) instead of silently picking
    whichever definition happened to be scanned first.
    """
    from reveal.adapters.ast.analysis import collect_structures
    from reveal.adapters.ast.nav_effects import classify_call
    from reveal.registry import language_for_extension

    structures = collect_structures(path)
    index: Dict[str, List[Dict[str, Any]]] = {}

    for file_struct in structures:
        file_path = file_struct.get('file', '')
        language = language_for_extension(Path(file_path).suffix)
        for elem in file_struct.get('elements', []):
            if elem.get('category') not in ('functions', 'methods'):
                continue
            name = elem.get('name', '')
            if not name:
                continue
            index.setdefault(name, []).append({
                'file': file_path,
                'line': elem.get('line', 0),
                'params': _params_from_signature(elem.get('signature', ''), name),
                'effects': _effects_from_calls(elem.get('calls', []), classify_call, language),
            })

    return index


def _split_top_level_commas(text: str) -> List[str]:
    """Split on commas that are not nested inside (), [] or {}.

    Type annotations routinely contain commas (`dict[str, str]`,
    `Callable[[int], None]`, `tuple[int, ...]`), so a naive `str.split(',')`
    over a parameter list fabricates phantom parameters.
    """
    parts: List[str] = []
    depth = 0
    current: List[str] = []
    for ch in text:
        if ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth = max(0, depth - 1)
        if ch == ',' and depth == 0:
            parts.append(''.join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append(''.join(current))
    return parts


def _params_from_signature(signature: str, func_name: str) -> List[str]:
    """Extract parameter names from a function signature string.

    Signature format from tree-sitter: '(param1: Type, *args) -> ReturnType'
    or just '(param1, param2)'. A parameter's type annotation or default can
    itself contain commas, parens and brackets (`dict[str, str]`,
    `Callable[[], None]`, `x=foo()`), so the list is delimited by the paren
    that matches the opening one — not the first close-paren — and split on
    top-level commas only. A naive `split('(',1)[1].split(')',1)[0]` +
    `split(',')` produced phantom params like `str] | None` from
    `error_...placeholders: dict[str, str] | None` and truncated on any
    default containing `)`.
    """
    start = signature.find('(')
    if start == -1:
        return []
    depth = 0
    end = -1
    for i in range(start, len(signature)):
        ch = signature[i]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                end = i
                break
    inner = signature[start + 1:end] if end != -1 else signature[start + 1:]
    params = []
    for part in _split_top_level_commas(inner):
        name = part.strip().lstrip('*').split(':')[0].split('=')[0].strip()
        if name and name not in ('self', 'cls', '/', ''):
            params.append(name)
    return params


def _effects_from_calls(calls: List[str], classify_call, language=None) -> List[str]:
    """Return deduplicated effect labels for a function's call list."""
    effects: List[str] = []
    seen: Set[str] = set()
    for callee in calls:
        kind = classify_call(callee, language)
        if kind:
            label = f"{kind}:{callee.split('.')[-1]}"
            if label not in seen:
                seen.add(label)
                effects.append(label)
    return effects


def _relpath(file_str: str, base: str) -> str:
    try:
        return os.path.relpath(file_str, base)
    except ValueError:
        return file_str


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


class TraceRenderer:
    """Renderer for trace:// results."""

    @staticmethod
    def render_structure(result: Dict[str, Any], format: str = 'text') -> None:
        if format == 'json':
            print_json_result(result)
            return
        _render_trace(result)

    @staticmethod
    def render_error(error: Exception) -> None:
        print(f"Error building trace: {error}")


@register_adapter('trace')
@register_renderer(TraceRenderer)
class TraceAdapter(ResourceAdapter):
    """Adapter walking the call graph from a named entry point and building
    a depth-indented execution narrative (BFS via calls:// machinery)."""

    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907

    def __init__(self, resource: str, query: Optional[str] = None):
        self.path = str(Path(resource).expanduser())
        self.query_params = parse_query_params(query or '', coerce=True)
        self._warn_unknown_query_params(self.query_params)  # BACK-507

    @staticmethod
    def get_help() -> Dict[str, Any]:
        return {
            'name': 'trace',
            'description': 'Walk the call graph from a named entry point and print a depth-indented execution narrative.',
            'syntax': 'trace://<path>?from=<FUNC>[&depth=2]',
            'examples': [
                {'uri': "trace://src?from=main", 'description': 'Trace from main(), depth 2'},
                {'uri': "trace://src?from=handle_request&depth=4", 'description': 'Trace 4 levels deep'},
            ],
            'features': [
                'BFS call-graph walk via the same machinery as calls://',
                'Each frame: file/line, parameters, classified side-effects, and what it calls next',
                'Unresolved (external/stdlib) callees marked [external]',
            ],
            'notes': [
                'depth is clamped to 1-5.',
                'A same-named definition in an unrelated language is not conflated with the real target (BACK-405).',
            ],
            'see_also': [
                'reveal trace <path> --from <FUNC> - CLI subcommand form',
                "reveal_trace MCP tool - same narrative, MCP-native",
            ],
            'output_formats': ['text', 'json'],
        }

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            'adapter': 'trace',
            'description': 'Execution narrative: BFS call-graph walk from a named entry point',
            'uri_syntax': 'trace://<path>?from=<FUNC>&depth=2',
            'query_params': {
                'from': {'type': 'string', 'description': 'Entry-point function to start the trace from (required)', 'examples': ['from=main']},
                'depth': {'type': 'integer', 'description': 'How many call levels to expand (clamped 1-5, default 2)', 'examples': ['depth=4']},
            },
            'elements': {},
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': [
                {
                    'type': 'trace',
                    'description': 'Depth-indented call-graph frames from the entry point',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'root': {'type': 'string'},
                            'frames': {'type': 'array'},
                        },
                    },
                },
            ],
            'example_queries': [
                {'uri': 'trace://src?from=main', 'description': 'Trace from main()', 'output_type': 'trace'},
            ],
            'notes': [
                'Built on calls:// BFS machinery (find_callees_recursive) — not an independent scan.',
            ],
        }

    def get_structure(self, **kwargs: Any) -> Dict[str, Any]:
        root = self.query_params.get('from')
        if not root:
            raise ValueError("trace:// requires a 'from' query param naming the entry-point function")
        depth_raw = self.query_params.get('depth')
        depth = max(1, min(int(depth_raw) if depth_raw is not None else 2, 5))

        report = _build_trace(self.path, str(root), depth)

        return ResultBuilder.create(
            result_type='trace',
            source=self.path,
            contract_version=CONTRACT_VERSION,
            data=report,
        )
