"""Call navigation: range_calls, helpers, render_range_calls."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional
from ...core import node_children as _children
from ...core.treesitter_compat import _zero_arg
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
        # GDScript's 'attribute_call' is deliberately excluded here even
        # though it's now a CALL_NODE_TYPES member (added for treesitter.py's
        # get_structure()/calls:// path, BACK-730 seventeenth language): the
        # dedicated `attribute`-chain scan below (_extract_gdscript_attribute_
        # calls) already visits every attribute_call in the enclosing chain
        # and reconstructs its FULL qualified callee (`x.field.method`, not
        # just the bare `method`). Without this guard, the generic per-node
        # check ALSO matches attribute_call directly during the same stack
        # walk, emitting a second, wrongly-bare duplicate entry for every
        # dotted GDScript call (caught by
        # test_calls_ignores_bare_property_access_in_chain regressing to
        # ['x.field.method', 'method'] instead of ['x.field.method']).
        if (
            node.kind() in call_node_types
            and node.kind() != 'attribute_call'
            and from_line <= line <= to_line
        ):
            callee = _extract_callee(node, get_text, call_node_types)
            # BACK-744: 'init_declarator' is a CALL_NODE_TYPES member for C++
            # direct-init (`ClassName obj(args);`) but is ALSO the node kind
            # for every other initialized declaration (`int y = 5;`,
            # `Foo obj2 = Foo(3, 4);`) — shapes _extract_callee correctly
            # returns None for (mirrors treesitter.py:_extract_calls_in_
            # function's `if name` guard). Without this check, every such
            # plain/copy-init declaration in C/C++ would emit a bogus
            # unknown-callee ('?') entry here, since this loop unconditionally
            # appended regardless of whether a callee was actually found.
            if callee:
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
        # Dart cascade (`recv\n  ..foo()\n  ..bar(x)`) is a THIRD, distinct
        # shape from the flat identifier+selector chain above: each cascaded
        # call is its own sibling `cascade_section` node (a sibling of the
        # base identifier/selector chain, not nested inside it), holding
        # `..`, a `cascade_selector` (the member name), then either an
        # `argument_part` directly (plain `..method(args)`) or a further
        # `unconditional_assignable_selector`/`argument_part` run for a
        # chained call after the cascade member (`..setup().finish()`) —
        # note these chained continuations are DIRECT children of
        # `cascade_section`, unlike the outer flat chain where they're
        # wrapped in a `selector` node. `_extract_dart_selector_calls` never
        # looks inside `cascade_section`/`cascade_selector` at all, so every
        # cascaded call was silently invisible to --calls/--sideeffects/
        # --boundary (BACK-723 Dart sideeffects-recall-oracle pre-flight
        # check) despite cascades being AppFlowy's dominant Flutter
        # builder-chain idiom (289 files use `..`). `cascade_section` is a
        # Dart-only kind name, so this is a no-op scan for every other
        # language.
        if _zero_arg(node, 'kind') == 'cascade_section':
            for call in _extract_dart_cascade_calls(node, get_text):
                if from_line <= call['line'] <= to_line:
                    results.append(call)
        stack.extend(reversed(_children(node)))

    # Python decorator arguments (`@validator(vol.Schema(...))`) are SIBLINGS
    # of func_node under decorated_definition, not part of func_node's own
    # subtree -- the stack walk above never sees them, mirroring
    # treesitter.py:_decorator_extra_calls's identical BACK-731 gap on the
    # calls:// side (confirmed on Home Assistant's helpers/data_entry_flow.py:
    # two `post` methods decorated `@RequestDataValidator(vol.Schema(...))`
    # were entirely invisible to --calls). Merged in unconditionally, not
    # range-filtered, same convention as the Dart signature-adjacent extras
    # above -- a decorator belongs to the whole function regardless of which
    # --calls sub-range was requested.
    parent = func_node.parent()
    if parent is not None and _zero_arg(parent, 'kind') == 'decorated_definition':
        seen_callees = {r['callee'] for r in results}
        for sibling in _children(parent):
            if _zero_arg(sibling, 'kind') != 'decorator':
                continue
            dec_stack = _children(sibling)
            while dec_stack:
                dnode = dec_stack.pop()
                if _zero_arg(dnode, 'kind') in call_node_types:
                    callee = _extract_callee(dnode, get_text, call_node_types)
                    if callee and callee not in seen_callees:
                        dline = dnode.start_position().row + 1
                        first_arg, has_more = _extract_first_arg(dnode, get_text)
                        results.append({
                            'line': dline, 'callee': callee,
                            'first_arg': first_arg, 'has_more_args': has_more,
                        })
                        seen_callees.add(callee)
                dec_stack.extend(_children(dnode))

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


def _extract_dart_cascade_calls(node: Any, get_text: Callable) -> List[Dict[str, Any]]:
    """Reconstruct call sites from a Dart `cascade_section`'s own children.

    `recv\n  ..foo()\n  ..bar(x)` parses each cascaded operation as its own
    `cascade_section` sibling of the base `identifier`/`selector` chain (not
    nested inside it), with the shape `.. cascade_selector(member)
    [argument_part | (unconditional_assignable_selector argument_part)*]` --
    a plain `..method(args)` cascade puts `argument_part` directly under
    `cascade_section`, while a chained call AFTER the cascade member
    (`..setup().finish()`) puts a further `unconditional_assignable_selector`/
    `argument_part` pair directly under `cascade_section` too (unlike the top-
    level flat chain, where continuations are wrapped in a `selector` node --
    see `_extract_dart_selector_calls`). A cascaded field WRITE
    (`..field = 3`, no `argument_part` at all) correctly emits nothing --
    it's not a call. Each `cascade_section` is walked independently (callers
    invoke this once per `cascade_section` node encountered), collapsing a
    chained continuation to `.member` same as every other chained-call
    convention in this file.
    """
    results: List[Dict[str, Any]] = []
    base_parts: List[str] = []
    for child in _children(node):
        kind = _zero_arg(child, 'kind')
        if kind == 'cascade_selector':
            sub = _children(child)
            name_node = next((c for c in sub if _zero_arg(c, 'kind') == 'identifier'), None)
            member = get_text(name_node).strip() if name_node else ''
            base_parts = [f'.{member}'] if member else []
        elif kind == 'argument_part':
            callee = ''.join(base_parts) if base_parts else None
            line = child.start_position().row + 1
            first_arg, has_more = _extract_first_arg(child, get_text)
            results.append({'line': line, 'callee': callee, 'first_arg': first_arg, 'has_more_args': has_more})
            base_parts = []
        elif kind in ('unconditional_assignable_selector', 'conditional_assignable_selector'):
            inner_sub = _children(child)
            if inner_sub and _zero_arg(inner_sub[0], 'kind') == 'index_selector':
                base_parts = []
            else:
                member = get_text(inner_sub[-1]).strip() if inner_sub else ''
                base_parts = (base_parts + [f'.{member}']) if base_parts and member else ([f'.{member}'] if member else [])
        else:
            # `=` (cascaded field write) or any other non-call continuation
            # resets chain state -- nothing left to attribute a later
            # argument_part to.
            if kind != '..':
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

    `@as(i32, 10)` / `@import("std")` / `@panic(...)` are `SuffixExpr` →
    [BUILTINIDENTIFIER, FnCallArguments] — a distinct leaf kind from a
    regular `IDENTIFIER` for Zig's `@`-prefixed compiler builtins. Without
    seeding `base_parts` for this kind too, `base_parts` stays empty and the
    `FnCallArguments` branch below computes `callee = None` (falsy,
    silently dropped downstream) — every builtin call was invisible to
    `calls://`, despite `@import` alone appearing in nearly every real Zig
    file (found via pre-flight AST dump before the JS/TSX successor
    measurement, BACK-730).
    """
    results: List[Dict[str, Any]] = []
    if not children:
        return results
    base_parts: List[str] = []
    rest = children[1:]
    if children[0].kind() in ('IDENTIFIER', 'BUILTINIDENTIFIER'):
        base_parts = [get_text(children[0])]
    elif _zero_arg(children[0], 'kind') == '.' and len(children) > 1 and _zero_arg(children[1], 'kind') == 'IDENTIFIER':
        # `.fixed(&buf)` — Zig's type-inferred enum-literal call syntax
        # (`var w: std.Io.Writer = .fixed(&buf)` / `= .init(...)`, a common
        # modern-Zig idiom relying on result-location type inference): a
        # bare `.` token directly followed by the name, never wrapped in
        # `FieldOrFnCall` the way a real receiver-qualified chain segment
        # is. Without unwrapping this pair first, `children[0]` is the `.`
        # token (matches no case below), `base_parts` stays empty, and the
        # `IDENTIFIER` is silently skipped by the loop (only
        # `FnCallArguments`/`FieldOrFnCall` are handled per iteration) —
        # found via the Zig calls-recall-oracle measurement (BACK-730/BACK-754), a
        # 208/209-miss target (`fixed`) traced to this exact pattern in
        # real Ghostty source.
        base_parts = [get_text(children[1])]
        rest = children[2:]
    for child in rest:
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

    # PHP: self::method() / parent::method() / static::method() /
    # Class::method() — scoped_call_expression is a DISTINCT node kind from
    # member_call_expression above, entirely absent from this dispatch
    # (BACK-740, the ast:// nav side of BACK-736's calls:// fix, found via
    # the nav_calls.py/treesitter.py dispatch-parity test, BACK-739). The
    # generic child(0) fallback below returns only the 'scope' node's text
    # (self/parent/static/ClassName), silently dropping the method name
    # entirely — confirmed live: `self::baz()` rendered as bare `self`, not
    # `self::baz`. Mirrors treesitter.py:_callee_name_php_scoped_call.
    if _zero_arg(call_node, 'kind') == 'scoped_call_expression':
        return _extract_php_scoped_call_callee(call_node, get_text)

    # Scala: new ClassName(args) / new ClassName[T](args) — a DISTINCT node
    # kind ('instance_expression') from PHP/C#'s object_creation_expression
    # above despite the identical source shape (BACK-718/BACK-720 Scala
    # sideeffects-recall-oracle). Emit the same "new <name>" text so the
    # exact same taxonomy pattern convention applies unchanged.
    if _zero_arg(call_node, 'kind') == 'instance_expression':
        return _extract_scala_instance_callee(call_node, get_text)

    # Scala: infix method calls (`a :: b`, `list map doubler`) parse to
    # 'infix_expression' — the `operator` field is the method name. Absent from
    # CALL_NODE_TYPES/this dispatch, every infix call was invisible to
    # calls:// and --calls/--sideeffects/--boundary (BACK-746). Mirrors
    # treesitter.py:_callee_name_scala_infix.
    if _zero_arg(call_node, 'kind') == 'infix_expression':
        return _extract_scala_infix_callee(call_node, get_text)

    # Swift: `<callee><TypeArgs>(args)` — generic function call or generic
    # type initializer, both parse to 'constructor_expression' rather than
    # call_expression (BACK-730 Swift pre-flight).
    if _zero_arg(call_node, 'kind') == 'constructor_expression':
        return _extract_swift_constructor_callee(call_node, get_text)

    # 'new_expression' is shared by C++ and JS/TS/TSX with two mutually
    # exclusive field shapes: C++ (`new ClassName(args)` / `new NS::Name(args)`)
    # puts the callee in a 'type' field; JS/TS/TSX (`new Foo()` / `new
    # ns.Foo()`) puts it in a 'constructor' field instead — a completely
    # different field name for the identical node kind, so C++'s handler
    # returned None for every JS/TS constructor call (found via the
    # calls-recall-oracle JS/TSX pre-flight dump, 13th language, BACK-730;
    # mirrors treesitter.py:_callee_name_new_expression). Dispatch
    # structurally on which field is populated.
    if _zero_arg(call_node, 'kind') == 'new_expression':
        if call_node.child_by_field_name('constructor') is not None:
            return _extract_js_new_callee(call_node, get_text)
        return _extract_cpp_new_callee(call_node, get_text)

    # C++ direct-initialization (`ClassName obj(args);`, no `new` keyword) —
    # 'init_declarator' with a bare `argument_list` in its 'value' field.
    # Mirrors treesitter.py:_callee_name_cpp_direct_init (BACK-744).
    if _zero_arg(call_node, 'kind') == 'init_declarator':
        return _extract_cpp_direct_init_callee(call_node, get_text)

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

    # Rust turbofish (`size_of::<u32>()`, `x.remap_types::<T>()`,
    # `E::error::<T>()`) parses as generic_function(path, '::',
    # type_arguments) — the path is the real callee, type_arguments is not.
    # `(f)(args)` parses callee as parenthesized_expression wrapping the
    # real expression. Both left the raw wrapper text (the turbofish suffix,
    # or the literal unmatchable "(f)") in the callee string before this
    # unwrap (BACK-741, the ast:// nav side of BACK-733's calls:// fix,
    # found via the nav_calls.py/treesitter.py dispatch-parity test,
    # BACK-739). Mirrors treesitter.py:_callee_name_from_node's identical
    # unwrap loop.
    while _zero_arg(callee_node, 'kind') in ('generic_function', 'parenthesized_expression'):
        inner = next(
            (c for c in _children(callee_node) if _zero_arg(c, 'kind') not in ('(', ')')),
            None,
        ) if _zero_arg(callee_node, 'kind') == 'parenthesized_expression' else callee_node.child(0)
        if inner is None:
            break
        callee_node = inner

    # Chained/IIFE call: `f(...)()` — the outer call's callee is itself a
    # bare call node (not wrapped in member-access, unlike the fluent-chain
    # case below). The inner call is already captured as its own edge by
    # the tree walk, so returning its raw text here would emit a second,
    # un-normalized entry for the same call site (BACK-732, the nav_calls.py
    # side of treesitter.py:_callee_name_from_node's identical fix — found
    # via Home Assistant's helpers/temperature.py display_temp(), which
    # calls TemperatureConverter.converter_factory(...)(temperature)). The
    # outer call has no nameable callee of its own.
    if call_node_types and _zero_arg(callee_node, 'kind') in call_node_types:
        return None

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


def _extract_scala_instance_callee(node: Any, get_text: Callable) -> Optional[str]:
    """Scala `instance_expression`: `new <type_identifier|generic_type|
    field_expression>(args)`. Emits "new <name>" — the same convention
    `_extract_object_creation_callee` already established for PHP/C#'s
    `object_creation_expression`, so existing 'new <name>'-shaped taxonomy
    patterns work unchanged once a Scala entry uses them. Handles the three
    real shapes seen in GitBucket's corpus: a bare type (`new File(...)`), a
    parameterized type (`new ArrayList[String](...)`), and a fully-qualified
    type (`new java.io.File(...)`, trailing segment only).
    """
    for child in _children(node):
        if _zero_arg(child, 'kind') in _SCALA_TYPE_KINDS:
            name = _scala_simple_type_name(child, get_text)
            if name:
                return f"new {name}"
    return None


# Scala type-node kinds that can appear as the constructed type in an
# instance_expression (mirror of treesitter._SCALA_TYPE_KINDS).
_SCALA_TYPE_KINDS = frozenset({
    'type_identifier', 'generic_type', 'stable_type_identifier', 'field_expression',
})


def _scala_simple_type_name(type_node: Any, get_text: Callable) -> Optional[str]:
    """Simple (last) name of a Scala constructor type, unwrapping generics
    (`new Array[Byte]`), qualified paths (`new java.io.File`, BACK-747), and
    qualified generics (`new scala.Array[Byte]`). Mirror of
    treesitter._scala_simple_type_name."""
    kind = _zero_arg(type_node, 'kind')
    if kind == 'type_identifier':
        return get_text(type_node).strip() or None
    if kind == 'generic_type':
        base = next((c for c in _children(type_node)
                     if _zero_arg(c, 'kind') in _SCALA_TYPE_KINDS), None)
        return _scala_simple_type_name(base, get_text) if base is not None else None
    if kind == 'stable_type_identifier':
        names = [c for c in _children(type_node)
                 if _zero_arg(c, 'kind') == 'type_identifier']
        return (get_text(names[-1]).strip() or None) if names else None
    if kind == 'field_expression':
        text = get_text(type_node).strip()
        return text.split('.')[-1] if text else None
    return None


def _extract_scala_infix_callee(node: Any, get_text: Callable) -> Optional[str]:
    """Scala `infix_expression`: `a :: b` / `list map doubler` /
    `xs filterNot q`. The `operator` field is the method name — an
    `identifier` (alphabetic infix) or `operator_identifier` (symbolic).
    Emit the bare name. Mirrors treesitter.py:_callee_name_scala_infix
    (BACK-746)."""
    op = node.child_by_field_name('operator')
    if op is not None:
        text = get_text(op).strip()
        if text:
            return text
    kids = _children(node)
    if len(kids) >= 3:
        text = get_text(kids[1]).strip()
        if text:
            return text
    return None


def _extract_php_scoped_call_callee(node: Any, get_text: Callable) -> Optional[str]:
    """PHP `scoped_call_expression`: self::method() / parent::method() /
    static::method() / Class::method(). The 'scope' field is either a
    'relative_scope' node (self/parent/static keyword) or a plain 'name'
    node (a class constant); 'name' is the method being called (BACK-740,
    mirrors treesitter.py:_callee_name_php_scoped_call exactly).
    """
    scope_node = node.child_by_field_name('scope')
    name_node = node.child_by_field_name('name')
    if name_node is None:
        return None
    name_text = get_text(name_node).strip()
    if not name_text:
        return None
    if scope_node is None:
        return name_text
    scope_text = get_text(scope_node).strip()
    return f"{scope_text}::{name_text}" if scope_text else name_text


def _extract_swift_constructor_callee(node: Any, get_text: Callable) -> Optional[str]:
    """Swift `constructor_expression`: `constructed_type<TypeArgs>` field
    (a `user_type` wrapping a `type_identifier` plus `type_arguments`) +
    `constructor_suffix` args. Covers BOTH a generic function call
    (`identity<Int>(5)`) and a generic type initializer (`Array<Int>()`) —
    unlike Scala/PHP's `object_creation_expression`/`instance_expression`,
    this node is not always semantically a construction, so it emits the
    bare callee name (`identity`, `Array`) with no "new " prefix, matching
    the plain call_expression convention instead.
    """
    constructed = node.child_by_field_name('constructed_type')
    if constructed is None:
        return None
    if _zero_arg(constructed, 'kind') == 'user_type':
        base = next(
            (c for c in _children(constructed) if _zero_arg(c, 'kind') == 'type_identifier'),
            None,
        )
        if base is not None:
            name = get_text(base).strip()
            if name:
                return name
    text = get_text(constructed).strip()
    if text:
        return text.split('<')[0].strip() or None
    return None


def _extract_js_new_callee(node: Any, get_text: Callable) -> Optional[str]:
    """JS/TS/TSX `new_expression`: `new ClassName(args)` / `new ns.ClassName(args)`.
    Emits "new <name>" — same convention as `_extract_cpp_new_callee`. The
    callee lives in a 'constructor' field (identifier, or member_expression
    for a dotted form), unlike C++'s 'type' field on the same node kind.
    """
    ctor_node = node.child_by_field_name('constructor')
    if ctor_node is None:
        return None
    kind = _zero_arg(ctor_node, 'kind')
    if kind == 'identifier':
        name = get_text(ctor_node).strip()
        return f"new {name}" if name else None
    if kind == 'member_expression':
        prop = None
        for child in _children(ctor_node):
            if _zero_arg(child, 'kind') == 'property_identifier':
                prop = child
        if prop is not None:
            name = get_text(prop).strip()
            return f"new {name}" if name else None
    return None


def _extract_cpp_new_callee(node: Any, get_text: Callable) -> Optional[str]:
    """C++ `new_expression`: `new <type_identifier|qualified_identifier>(args)`.
    Emits "new <name>" — the same convention `_extract_object_creation_callee`
    already established for PHP/C#'s `object_creation_expression`. A
    qualified type (`new NS::Other(...)`) collapses to its trailing segment
    only (`Other`), matching Scala's field_expression handling for
    fully-qualified constructor types.
    """
    type_node = node.child_by_field_name('type')
    if type_node is None:
        return None
    kind = _zero_arg(type_node, 'kind')
    if kind == 'type_identifier':
        name = get_text(type_node).strip()
        if name:
            return f"new {name}"
    if kind == 'qualified_identifier':
        text = get_text(type_node).strip()
        if text:
            return f"new {text.split('::')[-1]}"
    return None


def _extract_cpp_direct_init_callee(node: Any, get_text: Callable) -> Optional[str]:
    """C++ direct-initialization: `ClassName obj(args);`, `std::vector<int> v(10);`
    — an `init_declarator` whose 'value' field is a bare `argument_list`
    (no `new` keyword, no call-expression wrapper at all). Distinct from
    plain declaration (`int x;`, no 'value' field) and copy-init
    (`Foo obj2 = Foo(3, 4);`, whose 'value' field is a `call_expression`,
    already visible via the ordinary call_expression dispatch) — checking
    the 'value' field's kind is what isolates this shape (BACK-744).

    The callee name lives on the *parent* `declaration` node's 'type'
    field, not on this node — `init_declarator` only holds the variable
    name + args. No "new " prefix, unlike `_extract_cpp_new_callee` —
    there's no `new` keyword in the source to echo. Mirrors
    treesitter.py:_callee_name_cpp_direct_init.
    """
    value_node = node.child_by_field_name('value')
    if value_node is None or _zero_arg(value_node, 'kind') != 'argument_list':
        return None
    decl_node = _zero_arg(node, 'parent')
    if decl_node is None:
        return None
    type_node = decl_node.child_by_field_name('type')
    if type_node is None:
        return None
    kind = _zero_arg(type_node, 'kind')
    if kind not in ('type_identifier', 'qualified_identifier'):
        return None
    text = get_text(type_node).strip()
    if not text:
        return None
    return text.split('::')[-1] if kind == 'qualified_identifier' else text


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
