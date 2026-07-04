"""Variable flow tracking: VarFlowWalker, var_flow, all_var_flow, render_var_flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from ...core import node_children as _children
from .node_taxonomy import (
    FOR_NODES, FOR_EXPRESSION_NODES, FOR_EACH_NAME_VALUE_NODES,
    IF_WHILE_NODES, MATCH_EXPRESSION_NODES,
)


@dataclass(frozen=True)
class _DeclShape:
    """One grammar's declaration-with-initializer node shape (BACK-431 Issue C).

    Replaces a growing elif chain of per-language branches with one table:
    the knowledge "Rust declares via `let_declaration` with fields
    `pattern`/`value`" is data, not control flow. Mirrors the precedent set
    by ``_ImportSpec``/``_GenericTreeSitterImportExtractor``.

    write_field/read_field name the node's own tree-sitter fields for the
    declared name / initializer, when the grammar exposes them at all.
    missing_name/missing_value name a VarFlowWalker method to call when the
    corresponding field lookup returns None — either because the grammar
    never has that field (Kotlin's fieldless `property_declaration`) or
    only sometimes does (C#'s valueless `variable_declarator`). positional
    names a method that owns the whole node when the grammar exposes no
    fields at all (Dart/GDScript/Zig); write_field/read_field are unused
    in that case.
    """

    write_field: Optional[str] = None
    read_field: Optional[str] = None
    missing_name: Optional[str] = None
    missing_value: Optional[str] = None
    positional: Optional[str] = None


_DECL_SHAPES: Dict[str, _DeclShape] = {
    # C#/Java/JS/TS declaration-with-initializer: `var x = f();`, `let x =
    # f();`, `final int x = f();` (BACK-411). C#'s variable_declarator omits
    # the 'value' field entirely for valueless decls.
    'variable_declarator': _DeclShape(
        write_field='name', read_field='value', missing_value='_csharp_missing_value',
    ),
    # Swift `var x = f()`/`let x = f()` shares variable_declarator's name/value
    # shape. Kotlin's node of the same name exposes no fields at all — the
    # identifier is wrapped in a positional 'variable_declaration' child
    # (BACK-431 Issue G smoke-tier audit).
    'property_declaration': _DeclShape(
        write_field='name', read_field='value', missing_name='_kotlin_missing_name',
    ),
    # Go `x := f()` (BACK-411).
    'short_var_declaration': _DeclShape(write_field='left', read_field='right'),
    # Rust `let x = f();` (BACK-411).
    'let_declaration': _DeclShape(write_field='pattern', read_field='value'),
    # Scala `val x = f()` / `var x = f()` — same pattern/value shape as Rust
    # (BACK-431 Issue G smoke-tier audit).
    'val_definition': _DeclShape(write_field='pattern', read_field='value'),
    'var_definition': _DeclShape(write_field='pattern', read_field='value'),
    # C/C++ `int x = f();` (found via BACK-422 conformance-matrix pilot).
    'init_declarator': _DeclShape(write_field='declarator', read_field='value'),
    # Dart `final x = f();` / `var x = f();` — no fields at all (BACK-431
    # Issue G smoke-tier audit).
    'initialized_variable_definition': _DeclShape(positional='_walk_dart_var_decl'),
    # GDScript `var x = f()` — no fields; declared name is a 'name' leaf
    # (BACK-431 Issue G smoke-tier audit).
    'variable_statement': _DeclShape(positional='_walk_gdscript_var_decl'),
    # Zig `const x = f();` / `var x = f();` — no fields at all (BACK-431
    # Issue G smoke-tier audit).
    'VarDecl': _DeclShape(positional='_walk_zig_var_decl'),
}


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
        ntype = n.kind()
        line = n.start_position().row + 1

        if n.end_position().row + 1 < self.from_line or line > self.to_line:
            return

        if ntype in ('identifier', 'variable_name', 'simple_identifier', 'IDENTIFIER') and self.get_text(n) == self.var_name:
            if self.from_line <= line <= self.to_line:
                self.events.append({'kind': c, 'line': line, 'node': n})
            return

        if ntype in ('assignment', 'augmented_assignment',
                     'assignment_expression', 'augmented_assignment_expression',
                     'assignment_statement', 'compound_assignment_expr'):
            self._walk_assignment(n, ntype, c)
        elif ntype == 'named_expression':
            self._walk_named_expression(n)
        elif ntype in _DECL_SHAPES:
            # Declaration-with-initializer, table-driven across all covered
            # grammars (BACK-431 Issue C) — see _DECL_SHAPES for per-language
            # field names and fallback strategies.
            self._walk_decl_shape(n, _DECL_SHAPES[ntype])
        elif ntype in FOR_NODES:
            # for_statement / C#/PHP foreach_statement / JS-TS for_in_statement —
            # all share the 'left'/'right' field shape (BACK-431).
            self._walk_for(n, c, 'left', 'right')
        elif ntype in FOR_EXPRESSION_NODES:
            # Rust `for x in y { }` uses pattern/value fields, not left/right
            # (BACK-430) — same shape as for_statement, different field names.
            self._walk_for(n, c, 'pattern', 'value')
        elif ntype in FOR_EACH_NAME_VALUE_NODES:
            # Java `for (T x : items)` — loop var is the 'name' field, iterable
            # is 'value' (BACK-431).
            self._walk_for(n, c, 'name', 'value')
        elif ntype == 'with_statement':
            self._walk_with(n, c)
        elif ntype in IF_WHILE_NODES:
            # Rust's `if`/`if let`/`while` produce `if_expression`/
            # `while_expression`, not `if_statement`/`while_statement`
            # (BACK-427, BACK-430) — the grammar is expression-oriented
            # throughout, but both use the same 'condition'/'body' fields.
            self._walk_if_while(n, c)
        elif ntype in MATCH_EXPRESSION_NODES:
            # Rust `match x { ... }` (BACK-430) — the scrutinee is a READ,
            # the arms (body) walk normally like any other block.
            self._walk_match(n, c)
        elif ntype == 'call':
            self._walk_call(n, c)
        else:
            for child in _children(n):
                self.walk(child, c)

    def _walk_assignment(self, n: Any, ntype: str, c: str) -> None:
        left = n.child_by_field_name('left')
        right = n.child_by_field_name('right')
        if left is None and right is None and ntype == 'assignment_statement':
            # Lua's assignment_statement exposes no fields at all — targets
            # are a positional 'variable_list' child (supports multi-assign,
            # `local ok, result = pcall(...)`), values an 'expression_list'
            # (BACK-431 Issue G smoke-tier audit: without this, `result` fell
            # through to the generic recursion below and was mislabeled READ
            # instead of WRITE, the same failure shape Kotlin/Scala had).
            for child in _children(n):
                if child.kind() == 'variable_list':
                    left = child
                elif child.kind() == 'expression_list':
                    right = child
        is_augmented = ntype in ('augmented_assignment', 'augmented_assignment_expression',
                                  'compound_assignment_expr')
        if not is_augmented:
            # Some grammars (e.g. C#) unify `=`/`+=`/etc. into one node kind
            # and expose the operator as a field instead; detect it there.
            op = n.child_by_field_name('operator')
            if op is not None:
                is_augmented = self.get_text(op) != '='
            elif n.child_count() == 3 and not n.child(1).is_named() and n.child(1).kind() != '=':
                # Go's assignment_statement has no 'operator' field at all —
                # the operator is just the unnamed middle child token.
                is_augmented = True
        if left:
            if is_augmented:
                self.walk(left, 'READ')
            self.walk(left, 'WRITE')
        if right:
            self.walk(right, 'READ')
        processed = {
            (left.start_byte(), left.end_byte()) if left else None,
            (right.start_byte(), right.end_byte()) if right else None,
        }
        for child in _children(n):
            if (child.start_byte(), child.end_byte()) not in processed:
                self.walk(child, c)

    def _walk_decl_shape(self, n: Any, shape: _DeclShape) -> None:
        """Declaration-with-initializer: declared name is a WRITE, initializer is a READ.

        Table-driven per _DECL_SHAPES (BACK-431 Issue C) — one method for
        every field-based grammar shape, plus dispatch to a positional
        fallback for grammars with no fields at all.
        """
        if shape.positional:
            getattr(self, shape.positional)(n)
            return

        name = n.child_by_field_name(shape.write_field)
        value = n.child_by_field_name(shape.read_field)
        if name is None and shape.missing_name:
            name = getattr(self, shape.missing_name)(n)
        if value is None and shape.missing_value:
            value = getattr(self, shape.missing_value)(n, name)

        processed = {
            (name.start_byte(), name.end_byte()) if name else None,
            (value.start_byte(), value.end_byte()) if value else None,
        }
        if name:
            self.walk(name, 'WRITE')
        if value:
            self.walk(value, 'READ')
        for child in _children(n):
            if (child.start_byte(), child.end_byte()) not in processed:
                self.walk(child, 'READ')

    @staticmethod
    def _kotlin_missing_name(n: Any) -> Optional[Any]:
        """Kotlin's `property_declaration` (`val x = f()`) exposes no fields
        at all — unlike Swift's node of the same name, which has
        'name'/'value'. The declared identifier is wrapped in a positional
        `variable_declaration` child; without this, the name falls through
        to the generic "unprocessed children are READ" branch and every
        Kotlin declaration is silently mislabeled as a read instead of a
        write (BACK-431 Issue G smoke-tier audit)."""
        for child in _children(n):
            if child.kind() == 'variable_declaration':
                return child
        return None

    @staticmethod
    def _csharp_missing_value(n: Any, name: Optional[Any]) -> Optional[Any]:
        """C#'s variable_declarator has no 'value' field — the initializer
        is just the last named child that isn't the name (after '=')."""
        name_range = (name.start_byte(), name.end_byte()) if name else None
        value = None
        for child in _children(n):
            if not child.is_named():
                continue
            if name_range is not None and (child.start_byte(), child.end_byte()) == name_range:
                continue
            value = child
        return value

    def _walk_dart_var_decl(self, n: Any) -> None:
        """Dart `initialized_variable_definition` — no fields; the declared
        name is the first bare 'identifier' child, everything after '=' is
        the initializer."""
        children = list(_children(n))
        name = None
        eq_idx = None
        for i, child in enumerate(children):
            if child.kind() == '=':
                eq_idx = i
                break
            if child.kind() == 'identifier' and name is None:
                name = child
        processed = {(name.start_byte(), name.end_byte())} if name else set()
        if name:
            self.walk(name, 'WRITE')
        if eq_idx is not None:
            for child in children[eq_idx + 1:]:
                if (child.start_byte(), child.end_byte()) not in processed:
                    self.walk(child, 'READ')

    def _walk_gdscript_var_decl(self, n: Any) -> None:
        """GDScript `variable_statement` — 'name' leaf child is the declared
        identifier, checked directly since it isn't in the generic terminal
        identifier-match kinds."""
        name = None
        value = None
        for child in _children(n):
            if child.kind() == 'name':
                name = child
            elif child.kind() not in ('var', 'const', '='):
                value = child
        if name is not None and self.get_text(name) == self.var_name:
            line = name.start_position().row + 1
            if self.from_line <= line <= self.to_line:
                self.events.append({'kind': 'WRITE', 'line': line, 'node': name})
        if value is not None:
            self.walk(value, 'READ')

    def _walk_zig_var_decl(self, n: Any) -> None:
        """Zig `VarDecl` — no fields; name is the first IDENTIFIER child."""
        name = None
        for child in _children(n):
            if child.kind() == 'IDENTIFIER':
                name = child
                break
        processed = {(name.start_byte(), name.end_byte())} if name else set()
        if name:
            self.walk(name, 'WRITE')
        for child in _children(n):
            if (child.start_byte(), child.end_byte()) not in processed:
                self.walk(child, 'READ')

    def _walk_named_expression(self, n: Any) -> None:
        if _children(n):
            self.walk(n.child(0), 'WRITE')
            for child in _children(n)[1:]:
                self.walk(child, 'READ')

    def _walk_for(self, n: Any, c: str, left_field: str = 'left', right_field: str = 'right') -> None:
        left = n.child_by_field_name(left_field)
        right = n.child_by_field_name(right_field)
        body = n.child_by_field_name('body')
        processed: set = set()
        if left:
            processed.add((left.start_byte(), left.end_byte()))
            self.walk(left, 'WRITE')
        if right:
            processed.add((right.start_byte(), right.end_byte()))
            self.walk(right, 'READ')
        if body:
            processed.add((body.start_byte(), body.end_byte()))
            self.walk(body, 'READ')
        for child in _children(n):
            if (child.start_byte(), child.end_byte()) not in processed:
                self.walk(child, c)

    def _walk_with(self, n: Any, c: str) -> None:
        for child in _children(n):
            if child.kind() == 'with_clause':
                for item in _children(child):
                    if item.kind() == 'with_item':
                        value = item.child_by_field_name('value')
                        alias = item.child_by_field_name('alias')
                        if value:
                            self.walk(value, 'READ')
                        if alias:
                            self.walk(alias, 'WRITE')
                    else:
                        self.walk(item, c)
            elif child.kind() == 'as_pattern':
                children = _children(child)
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
            processed.add((cond.start_byte(), cond.end_byte()))
            self.walk(cond, 'READ/COND')
        for child in _children(n):
            if (child.start_byte(), child.end_byte()) not in processed:
                self.walk(child, c)

    def _walk_match(self, n: Any, c: str) -> None:
        value = n.child_by_field_name('value')
        processed: set = set()
        if value:
            processed.add((value.start_byte(), value.end_byte()))
            self.walk(value, 'READ')
        for child in _children(n):
            if (child.start_byte(), child.end_byte()) not in processed:
                self.walk(child, c)

    def _expand_dict_writes(self, dict_node: Any, via: str) -> None:
        """Emit one WRITE event per key in a dict literal `{key: val, ...}`."""
        for pair in _children(dict_node):
            if pair.kind() == 'pair':
                key_node = pair.child_by_field_name('key')
                val_node = pair.child_by_field_name('value')
                if key_node:
                    key_text = self.get_text(key_node)
                    kline = key_node.start_position().row + 1
                    if self.from_line <= kline <= self.to_line:
                        self.events.append({
                            'kind': 'WRITE',
                            'line': kline,
                            'node': key_node,
                            'text': f'{self.var_name}[{key_text}]  ← {self.var_name}.{via}()',
                        })
                if val_node:
                    self.walk(val_node, 'READ')
            elif pair.kind() not in ('{', '}', ','):
                self.walk(pair, 'READ')

    def _walk_call(self, n: Any, c: str) -> None:
        """Detect var_name.update({...}) and .setdefault(k, v) — expand to per-key WRITEs."""
        func = n.child_by_field_name('function')
        args = n.child_by_field_name('arguments')

        if func and func.kind() == 'attribute':
            obj = func.child_by_field_name('object')
            attr = func.child_by_field_name('attribute')
            if obj and self.get_text(obj) == self.var_name and attr:
                method = self.get_text(attr)
                obj_line = obj.start_position().row + 1
                if self.from_line <= obj_line <= self.to_line:
                    self.events.append({'kind': 'READ', 'line': obj_line, 'node': obj})

                if method == 'update' and args:
                    for arg in _children(args):
                        if arg.kind() == 'dictionary':
                            self._expand_dict_writes(arg, 'update')
                        elif arg.kind() not in (',', '(', ')'):
                            self.walk(arg, 'READ')
                elif method == 'setdefault' and args:
                    arg_nodes = [ch for ch in _children(args) if ch.kind() not in (',', '(', ')')]
                    if arg_nodes:
                        key_node = arg_nodes[0]
                        key_text = self.get_text(key_node)
                        kline = key_node.start_position().row + 1
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
                        for child in _children(args):
                            self.walk(child, 'READ')
                return

        for child in _children(n):
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
    events.sort(key=lambda e: (e['line'], e['node'].start_position().column))
    seen: set = set()
    unique = []
    for ev in events:
        key = (ev['line'], ev['node'].start_position().column, ev['kind'])
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


# Member/scoped-access node kinds where only the leftmost (base object) child
# is a real variable reference — the rightmost child is an attribute/field/
# member name, not an independent identifier. BACK-402.
_MEMBER_ACCESS_KINDS = frozenset({
    'attribute',                  # Python: obj.attr
    'member_access_expression',   # C#: obj.Member
    'field_expression',           # C, Rust: obj.field
    'member_expression',          # JS/TS: obj.prop
    'selector_expression',        # Go: obj.Field
    'scoped_identifier',          # Rust: path::segment
})


def _declared_name_node(scope_node: Any) -> Optional[Any]:
    """Return the identifier node for scope_node's own declared name, if any.

    Most languages expose it directly via the 'name' field. C wraps it inside
    a chain of 'declarator' fields (function_declarator -> identifier).
    """
    name = scope_node.child_by_field_name('name')
    if name is not None:
        return name
    node = scope_node.child_by_field_name('declarator')
    for _ in range(10):
        if node is None:
            return None
        if node.kind() in ('identifier', 'variable_name', 'simple_identifier'):
            return node
        node = node.child_by_field_name('declarator') or node.child_by_field_name('name')
    return None


def _collect_identifier_names(
    scope_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
) -> frozenset:
    """Return the set of identifier names that appear in a line range.

    Excludes the enclosing scope's own declared name and the non-base segment
    of member/scoped-access expressions (BACK-402) — neither is a real
    external variable reference.
    """
    names: set = set()
    name_node = _declared_name_node(scope_node)
    skip_pos = (
        (name_node.start_position().row, name_node.start_position().column)
        if name_node is not None else None
    )
    stack = list(reversed(_children(scope_node)))
    while stack:
        node = stack.pop()
        line = node.start_position().row + 1
        if node.end_position().row + 1 < from_line or line > to_line:
            continue
        if node.kind() in ('identifier', 'variable_name', 'simple_identifier') and from_line <= line <= to_line:
            pos = (node.start_position().row, node.start_position().column)
            if pos != skip_pos:
                text = get_text(node)
                if text:
                    names.add(text)
        if node.kind() in _MEMBER_ACCESS_KINDS:
            children = _children(node)
            if children:
                stack.append(children[0])
            continue
        stack.extend(reversed(_children(node)))
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
        full_to = scope_node.end_position().row + 1

    names = _collect_identifier_names(scope_node, from_line, to_line, get_text)
    result: Dict[str, List[Dict[str, Any]]] = {}
    for name in sorted(names):
        events = var_flow(scope_node, name, full_from, full_to, get_text)
        if events:
            result[name] = events
    return result
