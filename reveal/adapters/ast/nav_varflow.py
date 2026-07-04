"""Variable flow tracking: VarFlowWalker, var_flow, all_var_flow, render_var_flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from ...core import node_children as _children
from .node_taxonomy import (
    FOR_NODES, FOR_EXPRESSION_NODES, FOR_EACH_NAME_VALUE_NODES,
    FOR_RANGE_LOOP_NODES, IF_WHILE_NODES, MATCH_EXPRESSION_NODES,
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
    # Scala for-comprehension generator (`x <- expr`) / binding (`x = expr`)
    # — no fields at all; a bare boolean guard (`if cond`, wrapped in its
    # own `guard` child) binds nothing. Found via real gitbucket source
    # (WebHookService.scala's callIssuesWebHook): `repoOwner <- users.get(...)`
    # was tracked but mislabeled READ instead of WRITE at its own binding
    # site (BACK-431 tier A real-corpus dogfood audit).
    'enumerator': _DeclShape(positional='_walk_scala_enumerator'),
}


def resolve_assignment_sides(n: Any, ntype: str) -> tuple:
    """Return (left, right) nodes for an assignment/augmented-assignment node.

    Most grammars expose 'left'/'right' fields directly. Lua's
    assignment_statement exposes no fields at all — targets are a positional
    'variable_list' child (supports multi-assign, `local ok, result =
    pcall(...)`), values an 'expression_list' (BACK-431 Issue G smoke-tier
    audit: without this fallback, `result` fell through to generic recursion
    and was mislabeled READ instead of WRITE, the same failure shape
    Kotlin/Scala had).

    Shared by VarFlowWalker._walk_assignment and nav_keys._walk (BACK-456) —
    previously nav_keys reimplemented only the fielded case and silently
    lacked this Lua fallback.
    """
    left = n.child_by_field_name('left')
    right = n.child_by_field_name('right')
    if left is None and right is None and ntype == 'assignment_statement':
        for child in _children(n):
            if child.kind() == 'variable_list':
                left = child
            elif child.kind() == 'expression_list':
                right = child
    return left, right


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
    own_name_pos: Optional[tuple] = None

    def walk(self, n: Any, c: str) -> None:
        ntype = n.kind()
        line = n.start_position().row + 1

        if n.end_position().row + 1 < self.from_line or line > self.to_line:
            return

        # Terminal-identifier matches and per-language "this name is not a
        # variable" exclusions (member access, JSX tags, annotations, Zig
        # suffix chains) are handled first; each fully consumes the node.
        if self._walk_exclusions(n, ntype, line, c):
            return

        self._dispatch(n, ntype, c)

    def _walk_exclusions(self, n: Any, ntype: str, line: int, c: str) -> bool:
        """Terminal-identifier match + per-language member-access/tag/annotation
        exclusions. Returns True when the node was fully handled (caller returns).

        This is the read/write-event mirror of the descent exclusions in
        _collect_identifier_names — direct --varflow queries reach var_flow()
        without going through that candidate pass, so the same "not a variable"
        knowledge has to be applied here too (BACK-431 feature-breadth pass)."""
        if ntype in ('identifier', 'variable_name', 'simple_identifier', 'IDENTIFIER') and self.get_text(n) == self.var_name:
            pos = (n.start_position().row, n.start_position().column)
            if pos == self.own_name_pos:
                return True
            if self.from_line <= line <= self.to_line:
                self.events.append({'kind': c, 'line': line, 'node': n})
            return True

        if ntype in _MEMBER_ACCESS_KINDS:
            # A member/method name (the non-base segment of `obj.field`/
            # `obj:method()`) is not an independent variable, even when its
            # text happens to collide with a real local elsewhere in scope
            # (found via real Kong source, kong/concurrency.lua: `opts.timeout`
            # falsely contributed a READ event to the unrelated `local
            # timeout = ...` variable one line away, BACK-431 feature-breadth
            # pass). _collect_identifier_names already excludes these from
            # --deps/--boundary's candidate-name pass; this mirrors that
            # exclusion for direct --varflow queries, which go straight to
            # var_flow() and never go through that candidate pass.
            children = _children(n)
            if children:
                self.walk(children[0], c)
            return True

        if ntype == 'SuffixExpr':
            # Zig's chain-of-any-length member access/calls live inside one
            # node's children rather than nesting (see
            # _zig_suffix_expr_walkable_children) — mirrors the
            # _MEMBER_ACCESS_KINDS exclusion above for --varflow's direct
            # queries (BACK-431 feature-breadth pass).
            for child in _zig_suffix_expr_walkable_children(_children(n)):
                self.walk(child, c)
            return True

        jsx_tag = _jsx_lowercase_tag_name_node(n, self.get_text)
        if jsx_tag is not None:
            # A lowercase JSX tag (`<div>`) is a string-like intrinsic, not a
            # variable — but attributes/attribute values on the same element
            # (`className={x}`) are real reads and must still be walked, so
            # this can't just `return` the way _MEMBER_ACCESS_KINDS does.
            # Mirrors _collect_identifier_names's exclusion for --varflow's
            # direct queries (BACK-431 feature-breadth pass). Compare by
            # position, not object identity — tree-sitter node wrappers are
            # not guaranteed stable across separate _children() calls.
            tag_pos = (jsx_tag.start_position().row, jsx_tag.start_position().column)
            for child in _children(n):
                pos = (child.start_position().row, child.start_position().column)
                if pos != tag_pos:
                    self.walk(child, c)
            return True

        java_annotation_name = _java_annotation_name_node(n)
        if java_annotation_name is not None:
            # `@Override`'s name is a type reference, not a variable — but
            # any `annotation_argument_list` (`@SuppressWarnings("x")`) must
            # still be walked. Mirrors the JSX-tag exclusion just above
            # (BACK-431 feature-breadth pass).
            name_pos = (java_annotation_name.start_position().row, java_annotation_name.start_position().column)
            for child in _children(n):
                pos = (child.start_position().row, child.start_position().column)
                if pos != name_pos:
                    self.walk(child, c)
            return True

        return False

    def _dispatch(self, n: Any, ntype: str, c: str) -> None:
        """Route a non-excluded node to its structural handler by grammar kind."""
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
        elif ntype in FOR_RANGE_LOOP_NODES:
            # C++ `for (T x : items)` — loop var is the 'declarator' field,
            # iterable is 'right' (BACK-450).
            self._walk_for(n, c, 'declarator', 'right')
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
        elif ntype == 'method_invocation' and n.child_by_field_name('object') is not None:
            # Java: same shape as Ruby's 'call' — 'object'/'name'/'arguments'
            # fields, only excluding the method 'name' when a real 'object'
            # receiver exists to preserve (mirrors the _collect_identifier_names
            # exclusion for direct --varflow queries, BACK-431 feature-breadth
            # pass, found via real Elasticsearch source).
            obj = n.child_by_field_name('object')
            arguments = n.child_by_field_name('arguments')
            self.walk(obj, c)
            if arguments is not None:
                self.walk(arguments, c)
        elif ntype == 'arguments':
            self._walk_arguments(n, c)
        elif ntype == 'field':
            self._walk_lua_field(n, c)
        else:
            for child in _children(n):
                self.walk(child, c)

    def _walk_lua_field(self, n: Any, c: str) -> None:
        """Lua table-constructor field: `{x}` (positional), `{[k] = v}`
        (computed key), or `{name = v}` (named key). Only the named-key form
        has a label to exclude — `identifier '=' identifier`, structurally
        identical to a real assignment. Positional and computed-key forms
        have no label at all; every child there is a genuine read. Without
        this, `{timeout = timeout}` double-counted a READ of `timeout` (once
        for the label, once for the value) — found via real Kong source,
        kong/concurrency.lua's `resty_lock:new` call (BACK-431
        feature-breadth pass).
        """
        children = _children(n)
        if (
            len(children) == 3
            and children[0].kind() in ('identifier', 'name')
            and children[1].kind() == '='
        ):
            self.walk(children[2], 'READ')
            return
        for child in children:
            self.walk(child, c)

    def _walk_arguments(self, n: Any, c: str) -> None:
        """Call-argument list. Scala's named argument (`f(x = value)`) parses
        as `assignment_expression` — identical to a real reassignment
        statement — so the generic recursion would misread the argument
        label as a WRITE to a same-named local (found via real gitbucket
        source, WebHookService.scala's callIssuesWebHook: `repository =
        ApiRepository(repository, ...)` inside a constructor call looked
        like the `repository` parameter was being reassigned, producing a
        bogus "first write" line for BACK-431 feature-breadth pass's --deps).
        The label is neither a read nor a write; only the value expression
        is a READ.
        """
        for child in _children(n):
            if child.kind() == 'assignment_expression':
                right = child.child_by_field_name('right')
                if right is not None:
                    self.walk(right, 'READ')
            else:
                self.walk(child, c)

    def _walk_assignment(self, n: Any, ntype: str, c: str) -> None:
        left, right = resolve_assignment_sides(n, ntype)
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

    def _walk_scala_enumerator(self, n: Any) -> None:
        """Scala for-comprehension `enumerator` — no fields at all. Three
        shapes share this node kind: `x <- expr` (generator binding), `x =
        expr` (value binding), and a bare boolean guard (`if cond`, wrapped
        in its own `guard` child) which binds nothing at all."""
        children = list(_children(n))
        if children and children[0].kind() == 'guard':
            self.walk(children[0], 'READ')
            return
        name = None
        op_idx = None
        for i, child in enumerate(children):
            if child.kind() in ('<-', '='):
                op_idx = i
                break
            if child.kind() == 'identifier' and name is None:
                name = child
        if op_idx is None:
            for child in children:
                self.walk(child, 'READ')
            return
        processed = {(name.start_byte(), name.end_byte())} if name else set()
        if name:
            self.walk(name, 'WRITE')
        for child in children[op_idx + 1:]:
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
        # Ruby also uses the 'call' node kind (shared label, unrelated
        # shape) — 'receiver'/'method'/'arguments' fields, not Python's
        # 'function'/'arguments'. Without this, a direct --varflow query
        # bypassing _collect_identifier_names's candidate pass would still
        # misread a Ruby method name as a read/write of a same-named local
        # (mirrors the Lua VarFlowWalker fix above, BACK-431 feature-breadth
        # pass).
        receiver = n.child_by_field_name('receiver')
        if receiver is not None:
            arguments = n.child_by_field_name('arguments')
            self.walk(receiver, c)
            if arguments is not None:
                self.walk(arguments, c)
            return

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
    # A scope's own declaration-site name (`function checkThing() {...}`) is
    # never itself a read/write, even when the same scope legitimately
    # references its own name elsewhere for recursion (`setTimeout(checkThing,
    # 10)`) — a real, separate occurrence that must still count. This gap is
    # language-agnostic (reproduced in plain Python too, not just JS) since
    # var_flow()/VarFlowWalker never consulted _declared_name_node at all,
    # unlike _collect_identifier_names's skip_positions (BACK-431
    # feature-breadth pass, found via real three.js source,
    # WebGLRenderer.checkMaterialsReady).
    name_node = _declared_name_node(func_node)
    own_name_pos = (
        (name_node.start_position().row, name_node.start_position().column)
        if name_node is not None and get_text(name_node) == var_name
        else None
    )
    walker = VarFlowWalker(
        var_name=var_name, from_line=from_line, to_line=to_line, get_text=get_text,
        own_name_pos=own_name_pos,
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
    'field_access',               # Java: obj.field (BACK-431 feature-breadth pass)
    'member_expression',          # JS/TS: obj.prop
    'selector_expression',        # Go: obj.Field
    'scoped_identifier',          # Rust: path::segment
    'navigation_expression',      # Kotlin: obj.member / obj.method() (BACK-431 feature-breadth pass)
    'dot_index_expression',       # Lua: obj.field (BACK-431 feature-breadth pass)
    'method_index_expression',    # Lua: obj:method() — colon call syntax (BACK-431 feature-breadth pass)
})

_JSX_TAG_KINDS = frozenset({
    'jsx_opening_element', 'jsx_closing_element', 'jsx_self_closing_element',
})


def _jsx_lowercase_tag_name_node(node: Any, get_text: Callable) -> Optional[Any]:
    """Return a JSX node's tag-name identifier, if it's a lowercase HTML
    intrinsic (`<div>`, `<fieldset>`) rather than a component reference.

    A lowercase tag is a string-like element name, not a variable — but it
    parses as a bare `identifier` with no distinguishing node kind, same as
    everything else. An uppercase tag (`<MyComp>`) IS a real component
    reference and must still be tracked; JSX's own lowercase/uppercase
    convention is the only signal. Found via real excalidraw source
    (Actions.tsx's SelectedShapeActions): `div`/`fieldset`/`legend` all read
    as bogus undefined variables (BACK-431 feature-breadth pass).
    """
    if node.kind() not in _JSX_TAG_KINDS:
        return None
    tag = next((c for c in _children(node) if c.kind() == 'identifier'), None)
    if tag is None:
        return None
    text = get_text(tag)
    return tag if text and text[0].islower() else None

_JAVA_ANNOTATION_KINDS = frozenset({'marker_annotation', 'annotation'})


def _java_annotation_name_node(node: Any) -> Optional[Any]:
    """Return a Java annotation's name identifier (`@Override` → `Override`),
    which is never a variable reference.

    `marker_annotation` (`@Override`) and `annotation` (`@SuppressWarnings(
    "unchecked")`) both parse as `['@', identifier, annotation_argument_list?]`
    — the identifier is the annotation type name, not a variable, but reads
    as one with no distinguishing signal from a real reference. Found via
    real Elasticsearch source (InternalEngine.java): `@Override` on the
    method under audit read as a bogus PARAM (BACK-431 feature-breadth
    pass). Any `annotation_argument_list` is left untouched by callers so
    its contents (rare, but possibly a real constant reference) still walk
    normally.
    """
    if node.kind() not in _JAVA_ANNOTATION_KINDS:
        return None
    return next((c for c in _children(node) if c.kind() == 'identifier'), None)


def _zig_suffix_expr_walkable_children(children: List[Any]) -> List[Any]:
    """Children of a Zig `SuffixExpr` that are real reads, not member names.

    `foo.bar.baz(x)` is one `SuffixExpr` node: [IDENTIFIER(foo),
    FieldOrFnCall(.bar), FieldOrFnCall(.baz, FnCallArguments(x))] — unlike
    every other language's single-base member access, a chain of any length
    lives inside ONE node's children rather than nesting. Keeps the base
    identifier and any call arguments (nested reads still matter); drops
    each `FieldOrFnCall`'s member-name IDENTIFIER, which is never an
    independent variable. Found via real Ghostty source (formatter.zig's
    cellStyle): `self.page.styles.get(...)` misread `page`/`styles`/`get`
    as three bogus undefined variables (BACK-431 feature-breadth pass).
    """
    result: List[Any] = []
    if children:
        result.append(children[0])
    for child in children[1:]:
        if child.kind() == 'FnCallArguments':
            result.append(child)
        elif child.kind() == 'FieldOrFnCall':
            for sub in _children(child):
                if sub.kind() == 'FnCallArguments':
                    result.append(sub)
    return result


def _declared_name_node(scope_node: Any) -> Optional[Any]:
    """Return the identifier node for scope_node's own declared name, if any.

    Most languages expose it directly via the 'name' field. C wraps it inside
    a chain of 'declarator' fields (function_declarator -> identifier).

    Kotlin's `function_declaration` (and similar fully fieldless grammars)
    exposes neither field, so without a fallback the function's own name
    reads as an ordinary identifier and every --deps/--boundary call reports
    it as an undefined "PARAM" of itself (BACK-431 feature-breadth pass,
    found via tivi's markSeasonWatched). Fall back to the first name-kind
    child, mirroring treesitter.py's `_get_node_name` PRIORITY 2b.
    """
    name = scope_node.child_by_field_name('name')
    if name is not None:
        return name
    node = scope_node.child_by_field_name('declarator')
    for _ in range(10):
        if node is None:
            break
        if node.kind() in ('identifier', 'variable_name', 'simple_identifier', 'IDENTIFIER'):
            return node
        node = node.child_by_field_name('declarator') or node.child_by_field_name('name')
    # Zig wraps a function in a fieldless 'Decl' node containing 'FnProto'
    # (name + params) as a sibling of the body — the name is FnProto's
    # child directly following the 'fn' keyword. Without this, a Zig
    # function's own name reads as a dependency on itself (BACK-431
    # feature-breadth pass, found via Ghostty's cellStyle), mirroring
    # ZigAnalyzer._get_node_name's '_extract_function_name' but usable here
    # without an analyzer instance.
    if scope_node.kind() == 'Decl':
        for child in _children(scope_node):
            if child.kind() == 'FnProto':
                fn_children = _children(child)
                for i, fc in enumerate(fn_children):
                    if fc.kind() == 'fn' and i + 1 < len(fn_children) and fn_children[i + 1].kind() == 'IDENTIFIER':
                        return fn_children[i + 1]
                break
    for child in _children(scope_node):
        if child.kind() in ('identifier', 'name', 'simple_identifier', 'property_identifier', 'IDENTIFIER'):
            return child
    return None


def _register_skip_positions(node: Any, skip_positions: set, get_text: Callable) -> None:
    """Record positions of names that look like identifiers but are not
    variables, so the terminal-identifier collector skips them: a parameter's
    Swift `external_name` (call-site argument label), a lowercase JSX tag, and a
    Java annotation's type name (BACK-431 feature-breadth pass)."""
    if node.kind() == 'parameter':
        external_name = node.child_by_field_name('external_name')
        if external_name is not None:
            skip_positions.add(
                (external_name.start_position().row, external_name.start_position().column)
            )
    jsx_tag = _jsx_lowercase_tag_name_node(node, get_text)
    if jsx_tag is not None:
        skip_positions.add((jsx_tag.start_position().row, jsx_tag.start_position().column))
    java_annotation_name = _java_annotation_name_node(node)
    if java_annotation_name is not None:
        skip_positions.add(
            (java_annotation_name.start_position().row, java_annotation_name.start_position().column)
        )


def _member_access_descent(node: Any) -> Optional[List[Any]]:
    """For a member-access-shaped node, return exactly the children to descend
    into (excluding the non-base member/method name), or None when `node` is
    not such a shape and should be walked generically.

    This is the candidate-name (--deps/--boundary) mirror of the same
    per-language exclusions VarFlowWalker._walk_exclusions applies for direct
    --varflow queries. Every branch here was found via real-corpus dogfood
    (BACK-431 feature-breadth pass); see the original inline comments preserved
    below for the exact source each idiom came from."""
    kind = node.kind()
    if kind in _MEMBER_ACCESS_KINDS:
        # `obj.field` / `obj:method()` — only the base object is a variable.
        children = _children(node)
        return children[:1]
    if kind in ('unconditional_assignable_selector', 'conditional_assignable_selector'):
        # Dart's member access (`.member`/`?.member`) holds only the trailing
        # selector; the base is a preceding sibling already visited. Descend
        # only into an `index_selector` (`[i]`, a real read target); a bare
        # `.`/`?.` + member-name is not a variable (real AppFlowy source,
        # `find.byWidgetPredicate(...)`).
        children = _children(node)
        if children and children[0].kind() == 'index_selector':
            return [children[0]]
        return []
    if kind == 'call' and node.child_by_field_name('receiver') is not None:
        # Ruby's `call` (`receiver.method(args)`) exposes receiver/method/
        # arguments fields; walk receiver + arguments but not the method name
        # (real Discourse source, `DB.query_single(...)[0].to_i`). A
        # receiver-less bare call falls through — its callee is itself a read.
        out = []
        receiver = node.child_by_field_name('receiver')
        arguments = node.child_by_field_name('arguments')
        if receiver is not None:
            out.append(receiver)
        if arguments is not None:
            out.append(arguments)
        return out
    if kind == 'method_invocation' and node.child_by_field_name('object') is not None:
        # Java's `method_invocation` — same shape as Ruby's `call`; skip the
        # `name` field only when a real `object` receiver is present (real
        # Elasticsearch source, `InternalEngine.refreshIfNeeded`). A bare call
        # has no object field and falls through, keeping its own name a read.
        out = []
        obj = node.child_by_field_name('object')
        arguments = node.child_by_field_name('arguments')
        if obj is not None:
            out.append(obj)
        if arguments is not None:
            out.append(arguments)
        return out
    if kind in ('prefix_expression', 'pattern'):
        # Swift's leading-dot implicit-member shorthand (`.someCase`) parses as
        # prefix_expression/pattern with a literal '.' first child — the name
        # after it is an enum case / static member, not a variable. Genuine
        # prefix operators (`!flag`, `-x`) have a named operator kind, and
        # `.some(let y)` has >2 children — both fall through to a generic walk.
        children = _children(node)
        if len(children) == 2 and children[0].kind() == '.':
            return []
        return None
    if kind == 'SuffixExpr':
        # Zig's flat member-access/call chain lives in one node's children.
        return _zig_suffix_expr_walkable_children(_children(node))
    return None


def _collect_identifier_names(
    scope_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
) -> frozenset:
    """Return the set of identifier names that appear in a line range.

    Excludes the enclosing scope's own declared name, the non-base segment
    of member/scoped-access expressions (BACK-402), and — BACK-431
    feature-breadth pass — two Swift-specific non-reads found via real-corpus
    dogfood (ios-oss AppDelegateViewModel.navigation): a parameter's
    `external_name` (the call-site argument label, e.g. `fromPushEnvelope` in
    `func f(fromPushEnvelope envelope: T)` — never bound inside the function
    body, only `envelope` is), and the bare-identifier form of Swift's
    leading-dot implicit-member shorthand (`.someCase`), which appears both
    as an enum-case switch pattern and as an inferred-type static member
    reference — neither is an independent variable.
    """
    names: set = set()
    name_node = _declared_name_node(scope_node)
    skip_positions: set = set()
    if name_node is not None:
        skip_positions.add((name_node.start_position().row, name_node.start_position().column))
    stack = list(reversed(_children(scope_node)))
    while stack:
        node = stack.pop()
        line = node.start_position().row + 1
        if node.end_position().row + 1 < from_line or line > to_line:
            continue
        if node.kind() in ('identifier', 'variable_name', 'simple_identifier', 'IDENTIFIER') and from_line <= line <= to_line:
            pos = (node.start_position().row, node.start_position().column)
            if pos not in skip_positions:
                text = get_text(node)
                if text:
                    names.add(text)
        _register_skip_positions(node, skip_positions, get_text)
        descent = _member_access_descent(node)
        if descent is not None:
            stack.extend(reversed(descent))
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
