"""Variable flow tracking: VarFlowWalker, var_flow, all_var_flow, render_var_flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class VarFlowWalker:
    """Recursive var-flow walker with write/condition context propagation.

    Promotes the nested-closure structure of the original _walk_var into
    independently-testable methods while preserving identical semantics.
    """

    var_name: str
    from_line: int
    to_line: int
    get_text: Callable
    events: List[Dict[str, Any]] = field(default_factory=list)

    def walk(self, n: Any, c: str) -> None:
        ntype = n.type
        line = n.start_point[0] + 1

        if n.end_point[0] + 1 < self.from_line or line > self.to_line:
            return

        if ntype in ('identifier', 'variable_name') and self.get_text(n) == self.var_name:
            if self.from_line <= line <= self.to_line:
                self.events.append({'kind': c, 'line': line, 'node': n})
            return

        if ntype in ('assignment', 'augmented_assignment',
                     'assignment_expression', 'augmented_assignment_expression'):
            self._walk_assignment(n, ntype, c)
        elif ntype == 'named_expression':
            self._walk_named_expression(n)
        elif ntype in ('for_statement', 'foreach_statement'):
            self._walk_for(n, c)
        elif ntype == 'with_statement':
            self._walk_with(n, c)
        elif ntype in ('if_statement', 'elif_clause', 'while_statement'):
            self._walk_if_while(n, c)
        elif ntype == 'call':
            self._walk_call(n, c)
        else:
            for child in n.children:
                self.walk(child, c)

    def _walk_assignment(self, n: Any, ntype: str, c: str) -> None:
        left = n.child_by_field_name('left')
        right = n.child_by_field_name('right')
        if left:
            if ntype in ('augmented_assignment', 'augmented_assignment_expression'):
                self.walk(left, 'READ')
            self.walk(left, 'WRITE')
        if right:
            self.walk(right, 'READ')
        processed = {
            (left.start_byte, left.end_byte) if left else None,
            (right.start_byte, right.end_byte) if right else None,
        }
        for child in n.children:
            if (child.start_byte, child.end_byte) not in processed:
                self.walk(child, c)

    def _walk_named_expression(self, n: Any) -> None:
        if n.children:
            self.walk(n.children[0], 'WRITE')
            for child in n.children[1:]:
                self.walk(child, 'READ')

    def _walk_for(self, n: Any, c: str) -> None:
        left = n.child_by_field_name('left')
        right = n.child_by_field_name('right')
        body = n.child_by_field_name('body')
        processed: set = set()
        if left:
            processed.add((left.start_byte, left.end_byte))
            self.walk(left, 'WRITE')
        if right:
            processed.add((right.start_byte, right.end_byte))
            self.walk(right, 'READ')
        if body:
            processed.add((body.start_byte, body.end_byte))
            self.walk(body, 'READ')
        for child in n.children:
            if (child.start_byte, child.end_byte) not in processed:
                self.walk(child, c)

    def _walk_with(self, n: Any, c: str) -> None:
        for child in n.children:
            if child.type == 'with_clause':
                for item in child.children:
                    if item.type == 'with_item':
                        value = item.child_by_field_name('value')
                        alias = item.child_by_field_name('alias')
                        if value:
                            self.walk(value, 'READ')
                        if alias:
                            self.walk(alias, 'WRITE')
                    else:
                        self.walk(item, c)
            elif child.type == 'as_pattern':
                children = child.children
                if children:
                    self.walk(children[0], 'READ')
                    if len(children) > 2:
                        self.walk(children[-1], 'WRITE')
            else:
                self.walk(child, c)

    def _walk_if_while(self, n: Any, c: str) -> None:
        cond = n.child_by_field_name('condition')
        processed: set = set()
        if cond:
            processed.add((cond.start_byte, cond.end_byte))
            self.walk(cond, 'READ/COND')
        for child in n.children:
            if (child.start_byte, child.end_byte) not in processed:
                self.walk(child, c)

    def _expand_dict_writes(self, dict_node: Any, via: str) -> None:
        """Emit one WRITE event per key in a dict literal `{key: val, ...}`."""
        for pair in dict_node.children:
            if pair.type == 'pair':
                key_node = pair.child_by_field_name('key')
                val_node = pair.child_by_field_name('value')
                if key_node:
                    key_text = self.get_text(key_node)
                    kline = key_node.start_point[0] + 1
                    if self.from_line <= kline <= self.to_line:
                        self.events.append({
                            'kind': 'WRITE',
                            'line': kline,
                            'node': key_node,
                            'text': f'{self.var_name}[{key_text}]  ← {self.var_name}.{via}()',
                        })
                if val_node:
                    self.walk(val_node, 'READ')
            elif pair.type not in ('{', '}', ','):
                self.walk(pair, 'READ')

    def _walk_call(self, n: Any, c: str) -> None:
        """Detect var_name.update({...}) and .setdefault(k, v) — expand to per-key WRITEs."""
        func = n.child_by_field_name('function')
        args = n.child_by_field_name('arguments')

        if func and func.type == 'attribute':
            obj = func.child_by_field_name('object')
            attr = func.child_by_field_name('attribute')
            if obj and self.get_text(obj) == self.var_name and attr:
                method = self.get_text(attr)
                obj_line = obj.start_point[0] + 1
                if self.from_line <= obj_line <= self.to_line:
                    self.events.append({'kind': 'READ', 'line': obj_line, 'node': obj})

                if method == 'update' and args:
                    for arg in args.children:
                        if arg.type == 'dictionary':
                            self._expand_dict_writes(arg, 'update')
                        elif arg.type not in (',', '(', ')'):
                            self.walk(arg, 'READ')
                elif method == 'setdefault' and args:
                    arg_nodes = [ch for ch in args.children if ch.type not in (',', '(', ')')]
                    if arg_nodes:
                        key_node = arg_nodes[0]
                        key_text = self.get_text(key_node)
                        kline = key_node.start_point[0] + 1
                        if self.from_line <= kline <= self.to_line:
                            self.events.append({
                                'kind': 'WRITE',
                                'line': kline,
                                'node': key_node,
                                'text': f'{self.var_name}[{key_text}]  ← {self.var_name}.setdefault()',
                            })
                        for val_node in arg_nodes[1:]:
                            self.walk(val_node, 'READ')
                else:
                    if args:
                        for child in args.children:
                            self.walk(child, 'READ')
                return

        for child in n.children:
            self.walk(child, c)


def var_flow(
    func_node: Any,
    var_name: str,
    from_line: int,
    to_line: int,
    get_text: Callable,
) -> List[Dict[str, Any]]:
    """Return all reads and writes of var_name within a line range.

    Each event is a dict:
        kind  -- 'WRITE', 'READ/COND', or 'READ'
        line  -- 1-indexed line number of the identifier
        node  -- the identifier tree-sitter node
    """
    walker = VarFlowWalker(
        var_name=var_name, from_line=from_line, to_line=to_line, get_text=get_text
    )
    walker.walk(func_node, 'READ')
    events = walker.events
    events.sort(key=lambda e: (e['line'], e['node'].start_point[1]))
    seen: set = set()
    unique = []
    for ev in events:
        key = (ev['line'], ev['node'].start_point[1], ev['kind'])
        if key not in seen:
            seen.add(key)
            unique.append(ev)
    return unique


def render_var_flow(
    var_name: str,
    events: List[Dict[str, Any]],
    content_lines: List[str],
) -> str:
    """Render a var_flow result as text."""
    if not events:
        return f'No references to {var_name!r} found in range'

    lines = []
    for ev in events:
        kind = ev['kind']
        lineno = ev['line']
        if 'text' in ev:
            snippet = ev['text']
        else:
            snippet = content_lines[lineno - 1].strip() if lineno <= len(content_lines) else ''
            if len(snippet) > 80:
                snippet = snippet[:77] + '...'
        lines.append(f'{kind:<10}L{lineno}:  {snippet}')
    return '\n'.join(lines)


def _collect_identifier_names(
    scope_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
) -> frozenset:
    """Return the set of identifier names that appear in a line range."""
    names: set = set()
    stack = list(reversed(scope_node.children))
    while stack:
        node = stack.pop()
        line = node.start_point[0] + 1
        if node.end_point[0] + 1 < from_line or line > to_line:
            continue
        if node.type in ('identifier', 'variable_name') and from_line <= line <= to_line:
            text = get_text(node)
            if text:
                names.add(text)
        stack.extend(reversed(node.children))
    return frozenset(names)


def all_var_flow(
    scope_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
    full_from: int = 1,
    full_to: Optional[int] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Collect var_flow events for every identifier that appears in a line range."""
    if full_to is None:
        full_to = scope_node.end_point[0] + 1

    names = _collect_identifier_names(scope_node, from_line, to_line, get_text)
    result: Dict[str, List[Dict[str, Any]]] = {}
    for name in sorted(names):
        events = var_flow(scope_node, name, full_from, full_to, get_text)
        if events:
            result[name] = events
    return result
