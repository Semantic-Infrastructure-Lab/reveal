"""Renderer for calls:// adapter output."""

import os
import sys
from typing import Any, Dict, List, Set, Tuple

from reveal.utils import print_json_result
from reveal.utils.warning_render import meta_warning_lines

_REQUIRED_LOSS_TYPES = frozenset({'analysis_failed', 'analysis_incomplete'})
# Printed above every view: what the answer lost, and what no measurement covers (W-CALLS-9/10).
_ALWAYS_SHOWN = _REQUIRED_LOSS_TYPES | {'not_measured'}


def render_calls_structure(data: Dict[str, Any], output_format: str) -> None:
    """Render calls:// adapter results.

    Args:
        data: Result dict from CallsAdapter.get_structure()
        output_format: 'text', 'json', or 'dot'
    """
    if output_format == 'json':
        print_json_result(data)
        return

    if data.get('query') == 'callees' and 'levels' in data:
        _render_callee_walk(data, output_format)
        return
    for line in meta_warning_lines({'meta': {'warnings': _leading_warnings(data)}}):
        print(line, file=sys.stderr if output_format == 'dot' else sys.stdout)

    if data.get('query') == 'callees_recursive':
        if output_format == 'dot':
            _render_callees_recursive_dot(data)
        else:
            _render_callees_recursive_text(data)
        return

    if data.get('query') == 'module_graph':
        if output_format == 'dot':
            _render_module_graph_dot(data)
        else:
            _render_module_graph_text(data)
        return

    if data.get('query') == 'callees':
        _render_callees_text(data)
        return

    if data.get('query') == 'rank_callers':
        _render_ranking_text(data)
        return

    if data.get('query') == 'uncalled':
        _render_uncalled_text(data)
        return

    if output_format == 'dot':
        _render_dot(data)
        return

    _render_text(data)


def _render_callee_walk(data: Dict[str, Any], output_format: str) -> None:
    """?callees=X&depth=N (or &detail): the tree prints every warning under its rule; dot puts them
    on stderr, as every dot view does."""
    if output_format != 'dot':
        _render_callee_walk_text(data)
        return
    for line in meta_warning_lines({'meta': {'warnings': data.get('meta', {}).get('warnings', [])}}):
        print(line, file=sys.stderr)
    _render_callees_recursive_dot(data)


def _leading_warnings(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The warnings printed above a view: what the answer lost and what no measurement covers, plus
    scope_hidden for the per-definition callees view, which prints no caveat of its own (BACK-2065)."""
    warnings: List[Dict[str, Any]] = data.get('meta', {}).get('warnings', [])
    shown_types = _ALWAYS_SHOWN | ({'scope_hidden'} if data.get('query') == 'callees' else frozenset())
    return [w for w in warnings if w.get('type') in shown_types]


def _render_text(data: Dict[str, Any]) -> None:
    if 'error' in data and 'target' not in data:  # the router reports the error (BACK-1059)
        if 'example' in data:
            print(f"Example: {data['example']}", file=__import__('sys').stderr)
        return
    target = data.get('target', '?')
    depth = data.get('depth', 1)
    total = data.get('total_callers', 0)
    levels = data.get('levels', [])
    path = data.get('path', '.')

    print(f"Callers of: {target}")
    print(f"Project:    {path}")
    if depth > 1:
        print(f"Depth:      {depth}")
    print(f"Total:      {total}")
    print()

    if not levels:
        print(f"  No callers found for '{target}'.")
        hint = data.get('hint')
        if hint:
            print(f"\n  Hint: {hint}")
        print()
        # BACK-1198: language-aware dispatch caveat, computed per-request.
        for w in data.get('meta', {}).get('warnings', []):
            if w.get('type') not in _ALWAYS_SHOWN:
                print(f"⚠ {w['message']}")
        return

    for lvl in levels:
        level_num = lvl['level']
        callers = lvl['callers']
        if depth > 1:
            label = "Direct callers" if level_num == 1 else f"Level {level_num} callers"
            print(f"{label}:")
        for rec in callers:
            file_path = rec['file']  # relative path from project root
            caller = rec['caller']
            line = rec['line']
            call_expr = rec.get('call_expr', rec.get('callee', target))
            verb = {'jsx_reference': 'JSX reference to',
                    'call_and_jsx_reference': 'calls and JSX reference to'}.get(rec.get('relationship'), 'calls')
            print(f"  {file_path}:{line}  {caller}  ({verb} {call_expr}){_site_locations(rec)}")
        if depth > 1:
            print()


def _line_list(label: str, lines: List[int]) -> str:
    return f"{label}{'line' if len(lines) == 1 else 'lines'} {', '.join(map(str, lines))}"


def _site_locations(rec: Dict[str, Any]) -> str:
    """` [call line 3, JSX line 4]`: each kind of site named; a lone call site needs none."""
    calls = sorted(set(rec.get('call_lines', [])))
    references = sorted(set(rec.get('reference_lines', [])))
    if references:
        parts = ([_line_list('call ', calls)] if calls else []) + [_line_list('JSX ', references)]
        return f" [{', '.join(parts)}]"
    return f" [{_line_list('', calls)}]" if len(calls) > 1 else ''


def _render_callees_text(data: Dict[str, Any]) -> None:
    target = data.get('target', '?')
    total = data.get('total_calls', 0)
    matches = data.get('matches', [])
    path = data.get('path', '.')
    builtins_hidden = data.get('_builtins_hidden', 0)

    print(f"Callees of: {target}")
    print(f"Project:    {path}")
    print(f"Total:      {total} call(s) across {len(matches)} definition(s)")
    if builtins_hidden:
        print(f"            ({builtins_hidden} builtin(s) hidden — use ?builtins=true to include)")
    print()

    if not matches:
        print(f"  No definition of '{target}' found.")
        return

    for match in matches:
        file_path = match['file']
        line = match['line']
        calls = match.get('calls', [])
        print(f"  {file_path}:{line}  {target}")
        if calls:
            references = {r['callee'] for r in match.get('references', [])}
            reference_only = set(match.get('reference_only_calls', []))
            for callee in calls:
                suffix = (' (JSX reference)' if callee in reference_only
                          else ' (includes JSX reference)' if callee in references else '')
                print(f"    → {callee}{suffix}")
        else:
            print(f"    (no calls detected)")
        print()


def _render_callee_walk_text(data: Dict[str, Any]) -> None:
    """?callees=X&depth=N (or &detail): a depth-indented tree from each definition of X, its rule, and
    every warning the answer carries."""
    from reveal.analyzers.imports.service import edge_rule_lines
    target = data.get('target', '?')
    definitions = data.get('definitions', [])
    roots = [d for d in definitions if d['level'] == 0]
    print(f"Callees of: {target}  (depth {data.get('depth', 1)})")
    print(f"Project:    {data.get('path', '.')}")
    print(f"Total:      {data.get('total_edges', 0)} call edges: {data.get('total_resolved', 0)} resolved "
          f"({data.get('total_ambiguous', 0)} ambiguous), {data.get('total_unresolved', 0)} external/unresolved, "
          f"from {len(roots)} definition(s)")
    if data.get('_builtins_hidden'):
        print(f"            ({data['_builtins_hidden']} builtin(s) hidden at level 1 — use ?builtins=true to include)")
    for line in edge_rule_lines({'edge_rule': data.get('walk_rule')}):  # the one Rule: renderer
        print(line)
    for line in meta_warning_lines({'meta': {'warnings': data.get('meta', {}).get('warnings', [])}}):
        print(line)
    print()
    if not roots:
        print(f"  No definition of '{target}' found.")
        return
    edges: Dict[Any, List[Dict[str, Any]]] = {}
    for level in data.get('levels', []):
        for edge in level['callees']:
            edges.setdefault((edge['caller_file'], edge['caller_line']), []).append(edge)
    tree = _WalkTree(edges, {(d['file'], d['line']): d for d in definitions})
    for root in roots:
        for line in tree.lines(root, '  ', ''):
            print(line)
        print()


class _WalkTree:
    """Pre-order lines of the callee walk: an edge whose target is expanded elsewhere says where."""

    def __init__(self, edges: Dict[Any, List[Dict[str, Any]]], definitions: Dict[Any, Dict[str, Any]]):
        self.edges, self.definitions = edges, definitions
        self.printed: Set[Tuple[Any, Any]] = set()

    def lines(self, node: Dict[str, Any], pad: str, label: str) -> List[str]:
        key = (node['file'], node['line'])
        self.printed.add(key)
        out = [f"{pad}{label or node['name']}  {node['file']}:{node['line']}"]
        if 'params' in node:
            out.append(f"{pad}    params: {', '.join(node['params']) or '(none)'}")
            out.append(f"{pad}    effects: {', '.join(node['effects']) or '(none)'}")
        children = self.edges.get(key, [])
        if node['expanded'] and not children:
            out.append(f"{pad}  (no calls detected)")
        for edge in children:
            out.extend(self._edge_lines(edge, pad + '  '))
        return out

    def _edge_lines(self, edge: Dict[str, Any], pad: str) -> List[str]:
        label = '→ ' + edge['callee'] + {'jsx_reference': ' (JSX reference)', 'call_and_jsx_reference':
                                          ' (includes JSX reference)'}.get(edge.get('relationship', ''), '')
        if edge.get('ambiguous'):
            where = ', '.join(f"{os.path.basename(c['file'])}:{c['line']}" for c in edge['candidates'][:5])
            return [f"{pad}{label}  [ambiguous: {len(edge['candidates'])} definitions -- {where}]"]
        if not edge['resolved']:
            return [f"{pad}{label}  [external]"]
        key = (edge['callee_file'], edge['callee_line'])
        target = self.definitions.get(key)
        if edge.get('expanded') and target is not None:
            return self.lines(target, pad, label)
        mark = ''
        if target is not None and target['expanded']:
            mark = '  (expanded above)' if key in self.printed else '  (expanded below)'
        return [f"{pad}{label}  {edge['callee_file']}:{edge['callee_line']}{mark}"]


def _render_ranking_text(data: Dict[str, Any]) -> None:
    """Render rank=callers output — most-called functions sorted by in-degree."""
    path = data.get('path', '.')
    total = data.get('total_unique_callees', 0)
    entries = data.get('entries', [])

    print(f"Most-called functions: {path}")
    print(f"Ranking by:            caller count (in-degree)")
    # Counted, not the requested top=: --head/--tail/--range may slice entries after
    # ranking (--tail is not a "top"), and top=10 of 3 callees shows 3 (BACK-1497).
    print(f"Showing:               {len(entries)} of {total} unique callees")
    print()

    if not entries:
        print("  No call data found. Does the path contain Python files with function calls?")
        return

    for entry in entries:
        name = entry['name']
        count = entry['caller_count']
        callers = entry.get('callers', [])
        plural = 'caller' if count == 1 else 'callers'
        print(f"  {name}  ({count} {plural})")
        for rec in callers[:5]:  # show up to 5 callers per entry
            file_path = rec['file']
            caller = rec['caller']
            line = rec['line']
            print(f"    {file_path}:{line}  {caller}")
        if len(callers) > 5:
            print(f"    … and {len(callers) - 5} more")
        print()


def _render_uncalled_text(data: Dict[str, Any]) -> None:
    """Render ?uncalled output — functions/methods with no callers."""
    path = data.get('path', '.')
    total_defined = data.get('total_defined', 0)
    total_uncalled = data.get('total_uncalled', 0)
    test_excluded = data.get('test_entrypoints_excluded', 0)
    entries = data.get('entries', [])
    # BACK-1198: language-aware dispatch caveat + the "uncalled is a derived
    # signal" warning, both computed per-request by the adapter.
    warnings = data.get('meta', {}).get('warnings', [])

    print(f"Dead code candidates: {path}")
    print(f"Total defined:        {total_defined} functions/methods")
    if entries and len(entries) < total_uncalled:
        print(f"Uncalled:             {total_uncalled}  (showing top {len(entries)})")
    else:
        print(f"Uncalled:             {total_uncalled}")
    if test_excluded:
        print(f"Note: excluded {test_excluded} test-runner entrypoint(s) "
              f"([Fact]/@Test/test_*, etc.) — add ?test-framework=true to include")
    # BACK-1198: print the caveats near the number they qualify — previously
    # this rendered ~2,235 lines below the count on a large uncalled list,
    # past where anyone reading the header would see it.
    for w in warnings:
        if w.get('type') not in _ALWAYS_SHOWN:
            print(f"⚠ {w['message']}")
    print()

    if not entries:
        print("  No uncalled functions found.")
        return

    for entry in entries:
        name = entry['name']
        file_path = entry['file']
        line = entry['line']
        category = entry.get('category', 'functions')
        kind = 'method' if category == 'methods' else 'function'
        private_tag = ', private' if entry.get('is_private') else ''
        print(f"  {file_path}:{line}  {name}  ({kind}{private_tag})")


def _render_callees_recursive_text(data: Dict[str, Any]) -> None:
    root = data.get('root', '?')
    depth = data.get('depth', 2)
    path = data.get('path', '.')
    levels = data.get('levels', [])
    total_resolved = data.get('total_resolved', 0)
    total_unresolved = data.get('total_unresolved', 0)

    print(f"Callees of: {root}  (recursive, depth {depth})")
    print(f"Project:    {path}")
    total_edges = data.get('total_edges', total_resolved + total_unresolved)
    print(f"Total:      {total_edges} call edges: {total_resolved} resolved, {total_unresolved} external/unresolved")
    print()

    if not levels:
        print(f"  No callees found for '{root}'.")
        return

    for lvl in levels:
        level_num = lvl['level']
        label = "Direct callees" if level_num == 1 else f"Level {level_num} callees"
        print(f"{label}:")
        for entry in lvl['callees']:
            caller = entry['caller']
            callee = entry['callee']
            resolved = entry['resolved']
            file_path = entry.get('caller_file', '')
            line = entry.get('caller_line', '')
            status = '✓' if resolved else '✗ [external]'
            if resolved and not entry.get('ambiguous') and level_num < depth and entry.get('expanded') is False:
                # BACK-2096: the target was reached by an earlier edge; its callees are listed there.
                status = '✓ (already expanded)'
            if entry.get('ambiguous'):
                # BACK-1442: several definitions match and none is the
                # caller's own or imported one -- listed, not expanded.
                where = ', '.join(f"{os.path.basename(c['file'])}:{c['line']}" for c in entry['candidates'][:5])
                status = f"? [ambiguous: {len(entry['candidates'])} definitions -- {where}]"
            loc = f"  {file_path}:{line}" if file_path else ''
            print(f"  {caller} → {callee}  {status}{loc}")
        print()


def _render_callees_recursive_dot(data: Dict[str, Any]) -> None:
    root = data.get('root', data.get('target', '?'))  # ?root, or the ?callees walk
    levels = data.get('levels', [])

    print("digraph calls {")
    print('  rankdir=LR;')
    print(f'  node [shape=box fontname="monospace"];')
    print(f'  "{root}" [style=filled fillcolor=lightblue];')

    edges: set = set()
    for lvl in levels:
        for entry in lvl['callees']:
            caller = entry['caller']
            callee = entry['callee']
            edge = (caller, callee)
            if edge not in edges:
                edges.add(edge)
                style = '' if entry['resolved'] else ' [style=dashed color=gray]'
                print(f'  "{caller}" -> "{callee}"{style};')

    print("}")


def _render_module_graph_text(data: Dict[str, Any]) -> None:
    path = data.get('path', '.')
    nodes = data.get('nodes', [])
    edges = data.get('edges', [])
    total_nodes = data.get('total_nodes', 0)
    total_edges = data.get('total_edges', 0)

    print(f"Module dependency graph: {path}")
    print(f"Nodes (modules):         {total_nodes}")
    print(f"Edges (dependencies):    {total_edges}")
    print()

    if not edges:
        print("  No cross-module dependencies found.")
        print("  Tip: ensure imports resolve within the project root, or use ?external=true")
        return

    print("Dependencies (sorted by call count):")
    for edge in edges:
        frm = edge['from']
        to = edge['to']
        count = edge['call_count']
        calls_str = f"  ({count} call{'s' if count != 1 else ''})"
        print(f"  {frm} → {to}{calls_str}")


def _render_module_graph_dot(data: Dict[str, Any]) -> None:
    path = data.get('path', '.')
    edges = data.get('edges', [])

    # Shorten file paths to relative where possible
    def _short(p: str) -> str:
        try:
            import os
            rel = os.path.relpath(p, path)
            return rel if not rel.startswith('..') else p
        except ValueError:
            return p

    print("digraph modules {")
    print('  rankdir=LR;')
    print(f'  node [shape=box fontname="monospace"];')

    seen_edges: set = set()
    for edge in edges:
        frm = _short(edge['from'])
        to = _short(edge['to'])
        count = edge['call_count']
        key = (frm, to)
        if key not in seen_edges:
            seen_edges.add(key)
            label = f' [label="{count}"]' if count > 1 else ''
            print(f'  "{frm}" -> "{to}"{label};')

    print("}")


def _render_dot(data: Dict[str, Any]) -> None:
    """Render call graph in Graphviz dot format."""
    target = data.get('target', '?')
    levels = data.get('levels', [])

    print("digraph calls {")
    print('  rankdir=LR;')
    print(f'  node [shape=box fontname="monospace"];')

    edges = set()
    for lvl in levels:
        for rec in lvl['callers']:
            caller = rec['caller']
            callee = rec.get('callee', target)
            edge = (caller, callee)
            if edge not in edges:
                edges.add(edge)
                print(f'  "{caller}" -> "{callee}";')

    print("}")
