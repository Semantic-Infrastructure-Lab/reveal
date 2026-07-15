"""Call navigation: range_calls, helpers, render_range_calls."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional
from ...core import node_children as _children
from .node_taxonomy import MEMBER_ACCESS_NODES as _MEMBER_ACCESS_KINDS

# _MEMBER_ACCESS_KINDS: promoted to node_taxonomy.MEMBER_ACCESS_NODES
# (BACK-478 move 1 step 2). This used to be an independent copy missing
# 'field_access' (Java), 'navigation_expression' (Kotlin/Swift), and Lua's
# 'dot_index_expression'/'method_index_expression' — a live bug: the
# fluent-chain callee collapse below (BACK-415, `a().b().c()` -> callee
# ".c" not the whole chain text) silently never fired for those languages,
# so `builder.setName(x).setValue(y).build()` rendered the outer call's
# callee as the entire chain's source text instead of ".build".


def range_calls(
    func_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
    call_node_types: Optional[frozenset] = None,
) -> List[Dict[str, Any]]:
    """Return call sites within a line range.

    Each item is a dict:
        line      -- 1-indexed line of the call
        callee    -- callee name string
        first_arg -- text of the first argument (or None)
    """
    if call_node_types is None:
        from ...treesitter import CALL_NODE_TYPES  # noqa: PLC0415
        call_node_types = CALL_NODE_TYPES

    results: List[Dict[str, Any]] = []
    stack = list(reversed(_children(func_node)))
    while stack:
        node = stack.pop()
        line = node.start_position().row + 1
        if node.end_position().row + 1 < from_line or line > to_line:
            continue
        if node.kind() in call_node_types and from_line <= line <= to_line:
            callee = _extract_callee(node, get_text, call_node_types)
            first_arg, has_more = _extract_first_arg(node, get_text)
            results.append({'line': line, 'callee': callee, 'first_arg': first_arg, 'has_more_args': has_more})
        # Dart has no call-expression wrapper node at all — `obj.method(x)`
        # parses as a bare `identifier` followed by flat sibling `selector`
        # nodes (`.method`, then `(x)`), so it's invisible to the node-kind
        # check above regardless of what's in call_node_types. `selector` is
        # a Dart-only kind name (no-op scan elsewhere), so this is safe to
        # run unconditionally. Found via real AppFlowy source
        # (createNewPageInSpace) — every call in the function, including
        # `find.byWidgetPredicate(...)` and 8 others, was silently invisible
        # to --calls (BACK-431 feature-breadth pass).
        children = _children(node)
        if any(c.kind() == 'selector' for c in children):
            for call in _extract_dart_selector_calls(children, get_text):
                if from_line <= call['line'] <= to_line:
                    results.append(call)
        # Zig has no call-expression wrapper node either — `foo(x)` /
        # `a.b.c(x)` parse as one `SuffixExpr` holding [IDENTIFIER, then
        # either a bare `FnCallArguments` or a run of `FieldOrFnCall`
        # children (`.member` or `.method(args)`)]. `SuffixExpr` is a
        # Zig-only kind name, so this is a no-op scan for every other
        # language. Found via real Ghostty source (formatter.zig's
        # cellStyle): `cell.hasStyling()` and
        # `self.page.styles.get(...)` were both silently invisible to
        # --calls (BACK-431 feature-breadth pass).
        if node.kind() == 'SuffixExpr':
            for call in _extract_zig_suffix_calls(children, get_text):
                if from_line <= call['line'] <= to_line:
                    results.append(call)
        # GDScript's dotted method call (`x.size()`, `x.a().b()`) has no
        # dedicated call node either — it's folded into the same `attribute`
        # node Python-style plain attribute access uses (`x.field`), as a
        # flat run of `.` tokens and either bare `identifier` (plain
        # property) or `attribute_call` (identifier + arguments) segments.
        # `attribute_call` isn't a member of CALL_NODE_TYPES for any
        # language, so this whole shape was invisible to --calls. Bare
        # `foo(x)` (the plain `call` node, shared with Python) already
        # worked — only the dotted form was blind, which is most real
        # GDScript call sites. Found via real godot-demo-projects source
        # (ik_fabrik.gd's chain_backward): `bone_nodes[...].normalized()`
        # and 4 others were silently invisible (BACK-431 feature-breadth
        # pass).
        if node.kind() == 'attribute' and any(c.kind() == 'attribute_call' for c in children):
            for call in _extract_gdscript_attribute_calls(children, get_text):
                if from_line <= call['line'] <= to_line:
                    results.append(call)
        stack.extend(reversed(_children(node)))

    results.sort(key=lambda r: r['line'])
    return results


def _extract_dart_selector_calls(children: List[Any], get_text: Callable) -> List[Dict[str, Any]]:
    """Reconstruct call sites from Dart's flat identifier+selector siblings.

    `obj.method(x, y).other()` parses as siblings:
    `identifier(obj) selector(.method) selector((x,y)) selector(.other)
    selector(())` — with no enclosing node naming "the call". Walk the
    sibling list left to right, accumulating the callee text through
    `.member` selectors, and emit one entry per `argument_part` selector.
    Chained calls (whose callee text was reset by a prior call) collapse to
    `.member`, mirroring every other language's chained-call convention.
    """
    results: List[Dict[str, Any]] = []
    base_parts: List[str] = []
    for child in children:
        kind = child.kind()
        if kind == 'identifier':
            base_parts = [get_text(child)]
            continue
        if kind != 'selector':
            base_parts = []
            continue
        sel_children = _children(child)
        if not sel_children:
            continue
        inner = sel_children[0]
        inner_kind = inner.kind()
        if inner_kind == 'argument_part':
            callee = ''.join(base_parts) if base_parts else None
            line = child.start_position().row + 1
            first_arg, has_more = _extract_first_arg(inner, get_text)
            results.append({'line': line, 'callee': callee, 'first_arg': first_arg, 'has_more_args': has_more})
            base_parts = []
        elif inner_kind in ('unconditional_assignable_selector', 'conditional_assignable_selector'):
            inner_sub = _children(inner)
            if inner_sub and inner_sub[0].kind() == 'index_selector':
                base_parts = []
            else:
                member = get_text(inner_sub[-1]).strip() if inner_sub else ''
                base_parts = (base_parts + [f'.{member}']) if base_parts and member else ([f'.{member}'] if member else [])
        else:
            base_parts = []
    return results


def _extract_zig_suffix_calls(children: List[Any], get_text: Callable) -> List[Dict[str, Any]]:
    """Reconstruct call sites from Zig's single-node `SuffixExpr` children.

    `foo(x)` is `SuffixExpr` → [IDENTIFIER, FnCallArguments] (bare call);
    `a.b.c(x)` is `SuffixExpr` → [IDENTIFIER, FieldOrFnCall(.b),
    FieldOrFnCall(.c, FnCallArguments)] — a run of dot segments, each
    optionally carrying its own call arguments, all under one node (unlike
    Dart's flat siblings, but equally invisible to a plain node-kind check
    since there's still no wrapper naming "the call" itself).
    """
    results: List[Dict[str, Any]] = []
    if not children:
        return results
    base_parts: List[str] = []
    if children[0].kind() == 'IDENTIFIER':
        base_parts = [get_text(children[0])]
    for child in children[1:]:
        kind = child.kind()
        if kind == 'FnCallArguments':
            callee = ''.join(base_parts) if base_parts else None
            line = child.start_position().row + 1
            first_arg, has_more = _extract_first_arg(child, get_text)
            results.append({'line': line, 'callee': callee, 'first_arg': first_arg, 'has_more_args': has_more})
            base_parts = []
        elif kind == 'FieldOrFnCall':
            seg_children = _children(child)
            names = [c for c in seg_children if c.kind() == 'IDENTIFIER']
            args = next((c for c in seg_children if c.kind() == 'FnCallArguments'), None)
            member = get_text(names[0]).strip() if names else ''
            if args is not None:
                callee = (
                    ''.join(base_parts) + f'.{member}' if base_parts and member
                    else (f'.{member}' if member else None)
                )
                line = child.start_position().row + 1
                first_arg, has_more = _extract_first_arg(args, get_text)
                results.append({'line': line, 'callee': callee, 'first_arg': first_arg, 'has_more_args': has_more})
                base_parts = []
            elif member:
                base_parts = base_parts + [f'.{member}'] if base_parts else [f'.{member}']
    return results


def _extract_gdscript_attribute_calls(children: List[Any], get_text: Callable) -> List[Dict[str, Any]]:
    """Reconstruct call sites from GDScript's flat `attribute` chain.

    `x.a().b` and `x.size()` both live inside one `attribute` node: a base
    `identifier` followed by a run of `.` tokens paired with either a bare
    `identifier` (plain property, no call) or `attribute_call` (identifier +
    arguments — a real call). Same flat-chain-in-one-node shape as Dart's
    `selector`/Zig's `SuffixExpr`, just GDScript's own node-kind names.
    """
    results: List[Dict[str, Any]] = []
    if not children:
        return results
    base_parts: List[str] = []
    if children[0].kind() == 'identifier':
        base_parts = [get_text(children[0])]
    for child in children[1:]:
        kind = child.kind()
        if kind == 'identifier':
            member = get_text(child).strip()
            if member:
                base_parts = base_parts + [f'.{member}'] if base_parts else [f'.{member}']
        elif kind == 'attribute_call':
            seg_children = _children(child)
            name_node = next((c for c in seg_children if c.kind() == 'identifier'), None)
            member = get_text(name_node).strip() if name_node else ''
            callee = (
                ''.join(base_parts) + f'.{member}' if base_parts and member
                else (f'.{member}' if member else None)
            )
            line = child.start_position().row + 1
            first_arg, has_more = _extract_first_arg(child, get_text)
            results.append({'line': line, 'callee': callee, 'first_arg': first_arg, 'has_more_args': has_more})
            base_parts = []
        # '.' tokens are skipped implicitly (unnamed, never match either branch)
    return results


def _extract_callee(
    call_node: Any,
    get_text: Callable,
    call_node_types: Optional[frozenset] = None,
) -> Optional[str]:
    """Extract callee name from a call expression node."""
    if not call_node.child_count():
        return None

    # PHP: $obj->method(args) — emit "<receiver>-><name>" so taxonomy patterns
    # like '->execute', '->fetch', '->prepare' can match.
    if call_node.kind() == 'member_call_expression':
        return _extract_member_call_callee(call_node, get_text)

    # PHP: new ClassName(args) — emit "new <name>" so taxonomy patterns
    # like 'new pdo' can match.
    if call_node.kind() == 'object_creation_expression':
        return _extract_object_creation_callee(call_node, get_text)

    # Java: method_invocation is a flat node `[object? . name argument_list]` —
    # child(0) is only the *object* (`Files`, `path`), so the old logic dropped
    # the method name entirely (`Files.createDirectories()` → "Files",
    # `path.resolveIndex()` → "path"). Rebuild the receiver-qualified callee so
    # the effect taxonomy and calls:// see `Files.createDirectories` /
    # `path.resolveIndex` (BACK-416).
    if call_node.kind() == 'method_invocation':
        return _extract_java_method_invocation_callee(call_node, get_text, call_node_types)

    # Ruby: `call` exposes 'receiver'/'method'/'arguments' fields directly
    # rather than nesting `receiver.method` inside its own member-access
    # node like most grammars — the generic child(0) fallback below grabs
    # only the receiver, dropping the method name entirely
    # (`DB.query_single(sql)` rendered as the nonsensical `DB(sql)`, found
    # via real Discourse source, BACK-431 feature-breadth pass). A
    # receiver-less call (`puts(x)`) has no method field to separate out,
    # so it falls through to the generic path unchanged.
    if call_node.kind() == 'call' and call_node.child_by_field_name('receiver') is not None:
        return _extract_ruby_call_callee(call_node, get_text, call_node_types)

    callee_node = call_node.child(0)

    # Chained/fluent call: `rimrafUnlink(x).catch(...)`, `fetch(x).then(...).catch(...)`.
    # The callee is a member-access whose *receiver* is itself a call, so its raw
    # text folds the entire (possibly multi-line, 150+ char) chain into one bogus
    # "callee" name — which then pollutes trace/calls:// and mis-fires the
    # side-effect taxonomy (BACK-415). The receiver call is already captured as
    # its own edge by the tree walk, so collapse the outer callee to just its
    # trailing `.<property>` rather than the whole chain. Non-chained member
    # calls (`obj.method`) are left receiver-qualified — the taxonomy needs that.
    if (
        call_node_types
        and callee_node.kind() in _MEMBER_ACCESS_KINDS
        and _receiver_contains_call(callee_node, call_node_types)
    ):
        prop = _trailing_property_name(callee_node, get_text)
        if prop:
            return f".{prop}"
        # Fall through to a sanitized single-line form if no clean property found.
        first_line = get_text(callee_node).lstrip('*').strip().splitlines()[0].strip()
        return first_line or None

    text = get_text(callee_node).lstrip('*').strip()
    if callee_node.kind() == 'list_splat':
        for child in _children(callee_node):
            t = get_text(child).lstrip('*').strip()
            if t:
                return t
    return text if text else None


def _receiver_contains_call(member_node: Any, call_node_types: frozenset) -> bool:
    """True if a member-access node's receiver subtree contains a nested call.

    The trailing property child (e.g. `.catch`) is skipped — we only care whether
    the *object* being accessed is itself a call result (chained/fluent call).
    """
    named = [c for c in _children(member_node) if c.is_named()]
    # The last named child is the property/field being accessed; the receiver is
    # everything before it. Only scan the receiver for nested calls.
    for child in named[:-1] if len(named) > 1 else named:
        stack = [child]
        while stack:
            node = stack.pop()
            if node.kind() in call_node_types:
                return True
            stack.extend(_children(node))
    return False


def _trailing_property_name(member_node: Any, get_text: Callable) -> Optional[str]:
    """Return the trailing property/field identifier text of a member-access node."""
    named = [c for c in _children(member_node) if c.is_named()]
    if not named:
        return None
    trailing = named[-1]
    # Kotlin/Swift's navigation_expression wraps the name in its own
    # 'navigation_suffix' node (['.', simple_identifier]) rather than exposing
    # the identifier as a direct child — using its text as-is doubles the
    # leading dot the caller already prepends (BACK-478 move 1 step 2: found
    # while migrating this file onto the shared MEMBER_ACCESS_NODES family,
    # which made Kotlin/Swift chains reach this function for the first time).
    if trailing.kind() == 'navigation_suffix':
        suffix_named = [c for c in _children(trailing) if c.is_named()]
        if not suffix_named:
            return None
        trailing = suffix_named[-1]
    prop = get_text(trailing).strip()
    # Guard against a multi-line / call-bearing trailing node (shouldn't happen
    # for a plain property, but keep the output a clean single token).
    if not prop or '\n' in prop or '(' in prop:
        return None
    return prop


def _extract_member_call_callee(node: Any, get_text: Callable) -> Optional[str]:
    """PHP member_call_expression: <receiver> (->|?->) <name> <arguments>."""
    receiver_text: Optional[str] = None
    method_name: Optional[str] = None
    seen_arrow = False
    for child in _children(node):
        if child.kind() in ('->', '?->'):
            seen_arrow = True
            continue
        if child.kind() == 'arguments':
            break
        if not seen_arrow:
            if receiver_text is None:
                receiver_text = get_text(child).strip()
        else:
            if child.kind() == 'name':
                method_name = get_text(child).strip()
                break
    if receiver_text and method_name:
        return f"{receiver_text}->{method_name}"
    if method_name:
        return f"->{method_name}"
    return None


def _extract_object_creation_callee(node: Any, get_text: Callable) -> Optional[str]:
    """`object_creation_expression`: PHP's `new <name|qualified_name>(args)`
    and C#'s `new <identifier|generic_name>(args) { initializer }` share
    this exact node-kind name despite unrelated internal shapes — without a
    C# case, `new Dictionary<K, V>() { ... }` fell through with no callee at
    all, rendering as the placeholder `?(...)` in --calls (found via real
    Jellyfin source, EncodingHelper.cs's GetH26xOrAv1Encoder, BACK-431
    feature-breadth pass). C#'s generic type collapses to its base name
    (`Dictionary`, not `Dictionary<K, V>`) to match plain `new Foo()`.
    """
    for child in _children(node):
        if child.kind() in ('name', 'qualified_name'):
            class_name = get_text(child).strip()
            if class_name:
                return f"new {class_name}"
        if child.kind() == 'identifier':
            class_name = get_text(child).strip()
            if class_name:
                return f"new {class_name}"
        if child.kind() == 'generic_name':
            base = next((c for c in _children(child) if c.kind() == 'identifier'), None)
            if base is not None:
                class_name = get_text(base).strip()
                if class_name:
                    return f"new {class_name}"
    return None


def _extract_java_method_invocation_callee(
    node: Any,
    get_text: Callable,
    call_node_types: Optional[frozenset],
) -> Optional[str]:
    """Java method_invocation: `[object? . name argument_list]` → `object.name`.

    Emits the receiver-qualified callee (`Files.createDirectories`,
    `path.resolveIndex`) so the taxonomy and calls:// see the method name, not
    just the object. Chained calls (`a.b().c()`) whose object is itself a call
    collapse to `.name` (the inner call is captured separately), mirroring the
    member-access handling in _extract_callee (BACK-415/BACK-416).
    """
    children = _children(node)
    arg_idx = next(
        (i for i, c in enumerate(children) if c.kind() == 'argument_list'),
        len(children),
    )
    pre = children[:arg_idx]
    if not pre:
        return None
    name = get_text(pre[-1]).strip()
    # Qualified form: [object, '.', name]
    if len(pre) >= 3 and pre[-2].kind() in ('.', '?.'):
        obj_node = pre[0]
        if call_node_types and _subtree_contains_call(obj_node, call_node_types):
            return f".{name}" if name else None
        obj_text = get_text(obj_node).strip()
        if obj_text and name:
            return f"{obj_text}.{name}"
    return name or None


def _extract_ruby_call_callee(
    node: Any,
    get_text: Callable,
    call_node_types: Optional[frozenset],
) -> Optional[str]:
    """Ruby `call`: fielded `receiver`/`method`/`arguments` → `receiver.method`.

    Chained calls (`a.b.c`) whose receiver is itself a call collapse to
    `.method` (the inner call is captured separately), mirroring the
    member-access handling in _extract_callee (BACK-415/416/BACK-431).
    """
    receiver = node.child_by_field_name('receiver')
    method = node.child_by_field_name('method')
    if method is None:
        return None
    name = get_text(method).strip()
    if not name:
        return None
    if call_node_types and _subtree_contains_call(receiver, call_node_types):
        return f".{name}"
    receiver_text = get_text(receiver).strip()
    if not receiver_text or '\n' in receiver_text or len(receiver_text) > 40:
        return f".{name}"
    return f"{receiver_text}.{name}"


def _subtree_contains_call(node: Any, call_node_types: frozenset) -> bool:
    """True if any node in the subtree rooted at *node* is a call."""
    stack = [node]
    while stack:
        cur = stack.pop()
        if cur.kind() in call_node_types:
            return True
        stack.extend(_children(cur))
    return False


def _extract_first_arg(call_node: Any, get_text: Callable) -> tuple:
    """Extract the first argument and whether more args follow."""
    for child in _children(call_node):
        # 'token_tree': Rust macro_invocation's argument container (e.g.
        # `tracing::debug!("msg", x)`'s `("msg", x)`) -- not an
        # argument_list, but shaped the same way for this purpose.
        if child.kind() in ('argument_list', 'arguments', 'call_arguments', 'token_tree'):
            real_args = [
                c for c in _children(child)
                if c.kind() not in ('(', ')', ',', 'comment') and c.is_named()
            ]
            if not real_args:
                return None, False
            text = get_text(real_args[0]).splitlines()[0].strip()
            if len(text) > 40:
                text = text[:37] + '...'
            return text, len(real_args) > 1
    return None, False


def render_range_calls(
    calls: List[Dict[str, Any]],
    from_line: int,
    to_line: int,
) -> str:
    """Render a range_calls result as text."""
    if not calls:
        return f'No calls found in L{from_line}→L{to_line}'

    lines = []
    for call in calls:
        callee = call['callee'] or '?'
        if call['first_arg']:
            arg_part = f'({call["first_arg"]}, ...)' if call['has_more_args'] else f'({call["first_arg"]})'
        else:
            arg_part = '(...)'
        lines.append(f'L{call["line"]}:  {callee}{arg_part}')
    return '\n'.join(lines)
