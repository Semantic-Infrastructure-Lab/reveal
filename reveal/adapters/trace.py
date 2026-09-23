"""trace:// adapter - execution narrative from an entry-point function.

Walks the call graph depth-first from a named entry point, one frame per
definition, and builds a depth-indented narrative: each frame shows the function
location, its parameters, classified side-effects, and what it calls next.
Scan/render logic lives here (BACK-901/BACK-960); `cli/commands/trace.py` is
a thin argparse shim over this adapter, unchanged in its own CLI/MCP
contract (BACK-216/BACK-839 — `reveal trace` and the `reveal_trace` MCP
tool both keep working exactly as before).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from reveal.reveal_types import CONTRACT_VERSION

from .base import ResourceAdapter, register_adapter, register_renderer
from ..utils import print_json_result
from ..utils.query import parse_query_params
from ..utils.results import ResultBuilder


def _build_trace(path: str, root: str, depth: int) -> Dict[str, Any]:
    """Build a trace report: a depth-first walk over *definitions* (file:line),
    frames in pre-order so each renders under its caller.

    Keyed by definition, not by name (BACK-1399): the old name-keyed BFS merged
    every same-named function into one frame, so two unrelated `run()`s
    reported each other's callees. `root` may be `path/to/file.py:name` to pick
    one definition; an ambiguous bare name traces each definition separately.
    """
    from reveal.adapters.ast.analysis import collect_structures

    index = _definition_index(collect_structures(path))
    file_filter, root_name = _split_root(root)
    roots = [d for d in index.get(root_name, []) if _path_matches(d['file'], file_filter)]

    warnings: List[str] = []
    if len(roots) > 1:
        where = ', '.join(f"{_relpath(d['file'], path)}:{d['line']}" for d in roots[:5])
        more = f" (+{len(roots) - 5} more)" if len(roots) > 5 else ''
        warnings.append(
            f"'{root_name}' has {len(roots)} definitions ({where}{more}); each is traced "
            f"separately -- pick one with --from <file>:{root_name}"
        )

    walker = _TraceWalker(index, depth)
    for defn in roots:
        walker.expand(root_name, defn, 0)
    frames = walker.frames or [_frame(root, None, 0)]
    if walker.ambiguous_names:
        warnings.append(
            f"{len(walker.ambiguous_names)} callee name(s) match several definitions and are "
            f"not expanded: {', '.join(sorted(walker.ambiguous_names)[:5])}"
        )

    return {
        'root': root,
        'path': path,
        'depth': depth,
        'frames': frames,
        'warnings': warnings,
        'total_resolved': walker.resolved,
        'total_unresolved': walker.unresolved,
    }


_ROOT_WITH_FILE = re.compile(r'^(?P<file>.+\.[A-Za-z0-9_+]+):(?P<name>[^:].*)$')
_MAX_EXTERNAL_NAME = 80


def _split_root(root: str) -> Tuple[str, str]:
    """`src/a.py:run` -> ('src/a.py', 'run'); `run` / `Foo::run` -> ('', name)."""
    m = _ROOT_WITH_FILE.match(root)
    return (m.group('file'), m.group('name')) if m else ('', root)


def _path_matches(file_path: str, file_filter: str) -> bool:
    if not file_filter:
        return True
    want = Path(file_filter)
    if want.is_absolute():
        return Path(file_path).resolve() == want.resolve()
    return Path(file_path).parts[-len(want.parts):] == want.parts


def _short_callee(call: str) -> str:
    """Display text for an unresolved callee: an anonymous class or lambda
    body is part of the call expression and must not become the name."""
    text = re.sub(r'\{.*\}', '{...}', ' '.join(call.split()), flags=re.S)
    return text if len(text) <= _MAX_EXTERNAL_NAME else text[:_MAX_EXTERNAL_NAME - 3] + '...'


def _frame(name: str, defn: Optional[Dict[str, Any]], depth: int) -> Dict[str, Any]:
    return {
        'name': name,
        'file': defn['file'] if defn else '',
        'line': defn['line'] if defn else 0,
        'params': defn['params'] if defn else [],
        'effects': defn['effects'] if defn else [],
        'calls': [],
        'depth': depth,
        'resolved': defn is not None,
        'ambiguous': False,
    }


class _TraceWalker:
    """Expands definitions depth-first; each definition gets one frame."""

    def __init__(self, index: Dict[str, List[Dict[str, Any]]], max_depth: int) -> None:
        self.index = index
        self.max_depth = max_depth
        self.frames: List[Dict[str, Any]] = []
        self.resolved = 0
        self.unresolved = 0
        self.ambiguous_names: Set[str] = set()
        self._expanded: Set[Tuple[str, int, str]] = set()
        self._leaf_names: Set[str] = set()
        self._symbol_maps: Dict[str, Dict[str, Optional[str]]] = {}

    def expand(self, name: str, defn: Dict[str, Any], depth: int) -> None:
        self._expanded.add((defn['file'], defn['line'], name))
        frame = _frame(name, defn, depth)
        self.frames.append(frame)
        if depth >= self.max_depth:
            return
        targets = []
        for call in defn['calls']:
            label, target = self._resolve(call, defn['file'])
            if label not in frame['calls']:
                frame['calls'].append(label)
                targets.append((label, target))
        for label, target in targets:
            if target is None:
                self.unresolved += 1
                self._leaf(label, depth + 1, resolved=False)
            elif isinstance(target, list):
                self.resolved += 1
                self.ambiguous_names.add(label)
                self._leaf(label, depth + 1, resolved=False, candidates=target)
            else:
                self.resolved += 1
                if (target['file'], target['line'], label) not in self._expanded:
                    self.expand(label, target, depth + 1)

    def _leaf(self, label: str, depth: int, resolved: bool,
              candidates: Optional[List[Dict[str, Any]]] = None) -> None:
        """External and ambiguous callees: one frame per name, never expanded."""
        if label in self._leaf_names:
            return
        self._leaf_names.add(label)
        frame = _frame(label, None, depth)
        frame['resolved'] = resolved
        if candidates:
            frame['ambiguous'] = True
            frame['candidates'] = [{'file': c['file'], 'line': c['line']} for c in candidates]
        self.frames.append(frame)

    def _resolve(self, call: str, caller_file: str) -> Tuple[str, Any]:
        """(label, target): target is one definition, a list of candidate
        definitions when the name is ambiguous, or None when external."""
        from reveal.adapters.calls.index import _bare_callee_name, _lang_family

        tail = _bare_callee_name(call)
        family = _lang_family(caller_file)
        candidates = [d for d in self.index.get(tail, [])
                      if not family or _lang_family(d['file']) == family]
        if not candidates:
            return _short_callee(call), None
        if len(candidates) == 1:
            return tail, candidates[0]
        return tail, self._disambiguate(call, tail, caller_file, candidates) or candidates

    def _disambiguate(self, call: str, tail: str, caller_file: str,
                      candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """The one candidate the caller's own file or its imports point at.
        A bare call prefers a same-file definition (it shadows imports); a
        qualified one (`strings.rtrim`, `h.run`) prefers the module it names."""
        qualifier = call.split('.')[0] if '.' in call else ''
        imported = self._symbol_map(caller_file).get(qualifier or tail)
        imported_path = Path(imported).resolve() if imported else None
        via_import = [c for c in candidates if imported_path and Path(c['file']).resolve() == imported_path]
        same_file = [c for c in candidates if c['file'] == caller_file]
        for group in ((via_import, same_file) if qualifier else (same_file, via_import)):
            if len(group) == 1:
                return group[0]
        return None

    def _symbol_map(self, file_path: str) -> Dict[str, Optional[str]]:
        if file_path not in self._symbol_maps:
            from reveal.adapters.ast.call_graph import build_symbol_map
            self._symbol_maps[file_path] = build_symbol_map(file_path)
        return self._symbol_maps[file_path]


def _definition_index(structures: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """name -> every definition of it: file, line, params, effects and calls
    (language builtins dropped, as in calls://)."""
    from reveal.adapters.ast.nav_effects import classify_call
    from reveal.adapters.calls.index import _lang_family
    from reveal.conventions import conventions_for
    from reveal.registry import language_for_extension

    index: Dict[str, List[Dict[str, Any]]] = {}
    for file_struct in structures:
        file_path = file_struct.get('file', '')
        language = language_for_extension(Path(file_path).suffix)
        builtins = conventions_for(_lang_family(file_path)).builtins
        for elem in file_struct.get('elements', []):
            # 'tests' so a Zig test block can be a root (BACK-663).
            if elem.get('category') not in ('functions', 'methods', 'tests'):
                continue
            name = elem.get('name', '')
            if not name:
                continue
            calls = elem.get('calls', [])
            index.setdefault(name, []).append({
                'file': file_path,
                'line': elem.get('line', 0),
                'params': _params_from_signature(elem.get('signature', ''), name),
                'effects': _effects_from_calls(calls, classify_call, language),
                'calls': [c for c in calls if c.split('.')[-1] not in builtins] if builtins else calls,
            })
    # collect_structures' file order is not stable; frames and candidates must be.
    for defs in index.values():
        defs.sort(key=lambda d: (d['file'], d['line']))
    return index


def _collect_function_index(path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Every definition under *path*, by name (see _definition_index)."""
    from reveal.adapters.ast.analysis import collect_structures
    return _definition_index(collect_structures(path))


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
    for warning in report.get('warnings', []):
        print(f"⚠ {warning}")
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

        if frame.get('ambiguous'):
            where = ', '.join(f"{_relpath(c['file'], path)}:{c['line']}" for c in frame['candidates'][:3])
            more = ', ...' if len(frame['candidates']) > 3 else ''
            marker = f"  [ambiguous: {len(frame['candidates'])} definitions -- {where}{more}]"
        else:
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
    HELP_CLUSTER = 'Code Analysis'

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
                'Depth-first walk, one frame per definition: two unrelated functions named run() are never merged',
                'from=<file>:<name> picks one definition; a bare name with several traces each and warns',
                'Callees with several same-named definitions resolve via the same file, then imports, else [ambiguous]',
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
                'from': {'type': 'string', 'description': 'Entry-point function to start the trace from (required); `<file>:<name>` picks one of several same-named definitions', 'examples': ['from=main', 'from=src/app.py:run']},
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
                {'uri': 'trace://src?from=main', 'description': 'Trace from main()', 'output_type': 'trace', 'task': 'debugging'},
            ],
            'notes': [
                'Frames are per definition (file:line), in call order. A callee name with several definitions resolves through the same file, then the caller\'s imports; otherwise it is marked ambiguous and not expanded (BACK-1399).',
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
