"""Call navigation: range_calls, helpers, render_range_calls."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence
from . import node_children as _children
from .treesitter_compat import _zero_arg
from .callees.gdscript import attribute_sites as gdscript_attribute_sites
from .callees import callee_name_from_node, extract_by_kind, is_misparsed_call, CHAIN_COLLAPSE


def _generic_call_hits(
    node: Any, call_node_types: frozenset, get_text: Callable, from_line: int, to_line: int,
) -> List[Dict[str, Any]]:
    # GDScript's 'attribute_call' is deliberately excluded here even
    # though it's now a CALL_NODE_TYPES member (added for treesitter.py's
    # get_structure()/calls:// path, BACK-730 seventeenth language): the
    # dedicated `attribute`-chain scan (_gdscript_attribute_hits) already
    # visits every attribute_call in the enclosing chain and reconstructs
    # its FULL qualified callee (`x.field.method`, not just the bare
    # `method`). Without this guard, the generic per-node check ALSO
    # matches attribute_call directly during the same stack walk, emitting
    # a second, wrongly-bare duplicate entry for every dotted GDScript call
    # (caught by test_calls_ignores_bare_property_access_in_chain
    # regressing to ['x.field.method', 'method'] instead of
    # ['x.field.method']).
    line = _zero_arg(node, 'start_position').row + 1
    in_range = from_line <= line <= to_line
    node_kind = _zero_arg(node, 'kind')
    # Dart's 'argument_part' is excluded for the same reason: _dart_selector_hits /
    # _dart_cascade_hits already emit each call with its qualified callee, and
    # this generic path read the `(args)` node's own text -- a junk `()` callee
    # duplicated onto every Dart call (BACK-1279 agreement probe).
    if not (node_kind in call_node_types and node_kind not in ('attribute_call', 'argument_part') and in_range):
        return []
    callee = _extract_callee(node, get_text, call_node_types)
    # BACK-744: 'init_declarator' is a CALL_NODE_TYPES member for C++
    # direct-init (`ClassName obj(args);`) but is ALSO the node kind for
    # every other initialized declaration (`int y = 5;`, `Foo obj2 =
    # Foo(3, 4);`) — a shape _extract_callee correctly returns None for
    # (mirrors the `if name` guard in
    # treesitter.py:_complexity_depth_and_calls). Without this check, every such plain/copy-init declaration
    # in C/C++ would emit a bogus unknown-callee ('?') entry here.
    if not callee:
        return []
    first_arg, has_more = _extract_first_arg(node, get_text)
    return [{'line': line, 'callee': callee, 'first_arg': first_arg, 'has_more_args': has_more}]


def _dart_selector_hits(
    children: List[Any], get_text: Callable, from_line: int, to_line: int,
) -> List[Dict[str, Any]]:
    # Dart has no call-expression wrapper node at all — `obj.method(x)`
    # parses as a bare `identifier` followed by flat sibling `selector`
    # nodes (`.method`, then `(x)`), so it's invisible to the generic
    # node-kind check regardless of what's in call_node_types. `selector`
    # is a Dart-only kind name (no-op scan elsewhere), so this is safe to
    # run unconditionally. Found via real AppFlowy source
    # (createNewPageInSpace) — every call in the function, including
    # `find.byWidgetPredicate(...)` and 8 others, was silently invisible
    # to --calls (BACK-431 feature-breadth pass).
    if not any(_zero_arg(c, 'kind') == 'selector' for c in children):
        return []
    hits = _extract_dart_selector_calls(children, get_text)
    return [call for call in hits if from_line <= call['line'] <= to_line]


def _zig_suffix_hits(
    node: Any, children: List[Any], get_text: Callable, from_line: int, to_line: int,
) -> List[Dict[str, Any]]:
    # Zig has no call-expression wrapper node either — `foo(x)` /
    # `a.b.c(x)` parse as one `SuffixExpr` holding [IDENTIFIER, then
    # either a bare `FnCallArguments` or a run of `FieldOrFnCall`
    # children (`.member` or `.method(args)`)]. `SuffixExpr` is a
    # Zig-only kind name, so this is a no-op scan for every other
    # language. Found via real Ghostty source (formatter.zig's
    # cellStyle): `cell.hasStyling()` and `self.page.styles.get(...)`
    # were both silently invisible to --calls (BACK-431 feature-breadth
    # pass).
    if _zero_arg(node, 'kind') != 'SuffixExpr':
        return []
    hits = _extract_zig_suffix_calls(children, get_text)
    return [call for call in hits if from_line <= call['line'] <= to_line]


def _gdscript_attribute_hits(
    node: Any, children: List[Any], get_text: Callable, from_line: int, to_line: int,
) -> List[Dict[str, Any]]:
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
    if not (_zero_arg(node, 'kind') == 'attribute' and
            any(_zero_arg(c, 'kind') == 'attribute_call' for c in children)):
        return []
    hits = _extract_gdscript_attribute_calls(children, get_text, node)
    return [call for call in hits if from_line <= call['line'] <= to_line]


def _dart_cascade_hits(
    node: Any, get_text: Callable, from_line: int, to_line: int,
) -> List[Dict[str, Any]]:
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
    if _zero_arg(node, 'kind') != 'cascade_section':
        return []
    hits = _extract_dart_cascade_calls(node, get_text)
    return [call for call in hits if from_line <= call['line'] <= to_line]


def _decorator_arg_hits(
    func_node: Any, call_node_types: frozenset, get_text: Callable, seen_callees: set,
) -> List[Dict[str, Any]]:
    # Python decorator arguments (`@validator(vol.Schema(...))`) are
    # SIBLINGS of func_node under decorated_definition, not part of
    # func_node's own subtree -- the main stack walk never sees them,
    # mirroring treesitter.py:_decorator_extra_calls's identical BACK-731
    # gap on the calls:// side (confirmed on Home Assistant's
    # helpers/data_entry_flow.py: two `post` methods decorated
    # `@RequestDataValidator(vol.Schema(...))` were entirely invisible to
    # --calls). Merged in unconditionally, not range-filtered, same
    # convention as the Dart signature-adjacent extras above -- a
    # decorator belongs to the whole function regardless of which
    # --calls sub-range was requested.
    parent = _zero_arg(func_node, 'parent')
    if parent is None or _zero_arg(parent, 'kind') != 'decorated_definition':
        return []
    hits: List[Dict[str, Any]] = []
    for sibling in _children(parent):
        if _zero_arg(sibling, 'kind') != 'decorator':
            continue
        dec_stack = _children(sibling)
        while dec_stack:
            dnode = dec_stack.pop()
            if _zero_arg(dnode, 'kind') in call_node_types:
                callee = _extract_callee(dnode, get_text, call_node_types)
                if callee and callee not in seen_callees:
                    dline = _zero_arg(dnode, 'start_position').row + 1
                    first_arg, has_more = _extract_first_arg(dnode, get_text)
                    hits.append({
                        'line': dline, 'callee': callee,
                        'first_arg': first_arg, 'has_more_args': has_more,
                    })
                    seen_callees.add(callee)
            dec_stack.extend(_children(dnode))
    return hits


def range_calls(
    func_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
    call_node_types: Optional[frozenset] = None,
    implicit_nodes: Sequence[Any] = (),
) -> List[Dict[str, Any]]:
    """Return call sites within a line range.

    `implicit_nodes` are call sites that are not call-expression nodes (Ruby's
    paren-less `helper`), supplied by the analyzer's `_implicit_call_nodes`
    hook so this path agrees with structure/calls:// (BACK-1299).

    Each item is a dict:
        line      -- 1-indexed line of the call
        callee    -- callee name string
        first_arg -- text of the first argument (or None)
    """
    if call_node_types is None:
        from ..treesitter import CALL_NODE_TYPES  # noqa: PLC0415
        call_node_types = CALL_NODE_TYPES

    results: List[Dict[str, Any]] = []
    stack = list(reversed(_children(func_node)))
    while stack:
        node = stack.pop()
        line = _zero_arg(node, 'start_position').row + 1
        if _zero_arg(node, 'end_position').row + 1 < from_line or line > to_line:
            continue
        children = _children(node)
        results.extend(_generic_call_hits(node, call_node_types, get_text, from_line, to_line))
        results.extend(_dart_selector_hits(children, get_text, from_line, to_line))
        results.extend(_zig_suffix_hits(node, children, get_text, from_line, to_line))
        results.extend(_gdscript_attribute_hits(node, children, get_text, from_line, to_line))
        results.extend(_dart_cascade_hits(node, get_text, from_line, to_line))
        stack.extend(reversed(children))

    for node in implicit_nodes:
        line = _zero_arg(node, 'start_position').row + 1
        if from_line <= line <= to_line:
            results.append({'line': line, 'callee': get_text(node).strip(),
                            'first_arg': None, 'has_more_args': False})

    seen_callees = {r['callee'] for r in results}
    results.extend(_decorator_arg_hits(func_node, call_node_types, get_text, seen_callees))

    results.sort(key=lambda r: r['line'])
    return results


_DART_MEMBER_SELECTORS = ('unconditional_assignable_selector', 'conditional_assignable_selector')


def _dart_extend_receiver(base_parts: List[str], member_node: Any, get_text: Callable) -> List[str]:
    """Append a `.member` (or `?.member`) selector to the callee text so far;
    an index selector (`a[0]`) ends the chain."""
    inner_sub = _children(member_node)
    if inner_sub and _zero_arg(inner_sub[0], 'kind') == 'index_selector':
        return []
    member = get_text(inner_sub[-1]).strip() if inner_sub else ''
    if not member:
        return []
    return base_parts + [f'.{member}'] if base_parts else [f'.{member}']


def _extract_dart_selector_calls(children: List[Any], get_text: Callable) -> List[Dict[str, Any]]:
    """Reconstruct call sites from Dart's flat identifier+selector siblings.

    `obj.method(x, y).other()` parses as siblings:
    `identifier(obj) selector(.method) selector((x,y)) selector(.other)
    selector(())` — with no enclosing node naming "the call". Walk the
    sibling list left to right, accumulating the callee text through
    `.member` selectors, and emit one entry per `argument_part` selector.
    Chained calls (whose callee text was reset by a prior call) collapse to
    `.member`, mirroring every other language's chained-call convention.

    The receiver may be an `identifier`, `this` or `super`, and after `this` /
    `super` the `.member` is a BARE sibling (no `selector` wrapper) -- so
    `super.initState()` had no callee at all and rendered as `?` (found by the
    corpus agreement sweep; mirrors analyzers/dart.py's `_dart_qualifier_in`).
    """
    results: List[Dict[str, Any]] = []
    base_parts: List[str] = []
    for child in children:
        kind = _zero_arg(child, 'kind')
        if kind in ('identifier', 'this', 'super'):
            base_parts = [get_text(child)]
            continue
        if kind in _DART_MEMBER_SELECTORS:
            base_parts = _dart_extend_receiver(base_parts, child, get_text)
            continue
        if kind != 'selector':
            base_parts = []
            continue
        sel_children = _children(child)
        if not sel_children:
            continue
        inner = sel_children[0]
        inner_kind = _zero_arg(inner, 'kind')
        if inner_kind == 'argument_part':
            callee = ''.join(base_parts) if base_parts else None
            line = _zero_arg(child, 'start_position').row + 1
            first_arg, has_more = _extract_first_arg(inner, get_text)
            results.append({'line': line, 'callee': callee, 'first_arg': first_arg, 'has_more_args': has_more})
            base_parts = []
        elif inner_kind in _DART_MEMBER_SELECTORS:
            base_parts = _dart_extend_receiver(base_parts, inner, get_text)
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
            line = _zero_arg(child, 'start_position').row + 1
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
    if _zero_arg(children[0], 'kind') in ('IDENTIFIER', 'BUILTINIDENTIFIER'):
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
        kind = _zero_arg(child, 'kind')
        if kind == 'FnCallArguments':
            callee = ''.join(base_parts) if base_parts else None
            line = _zero_arg(child, 'start_position').row + 1
            first_arg, has_more = _extract_first_arg(child, get_text)
            results.append({'line': line, 'callee': callee, 'first_arg': first_arg, 'has_more_args': has_more})
            base_parts = []
        elif kind == 'FieldOrFnCall':
            seg_children = _children(child)
            names = [c for c in seg_children if _zero_arg(c, 'kind') == 'IDENTIFIER']
            args = next(
                (c for c in seg_children if _zero_arg(c, 'kind') == 'FnCallArguments'), None
            )
            member = get_text(names[0]).strip() if names else ''
            if args is not None:
                callee = (
                    ''.join(base_parts) + f'.{member}' if base_parts and member
                    else (f'.{member}' if member else None)
                )
                line = _zero_arg(child, 'start_position').row + 1
                first_arg, has_more = _extract_first_arg(args, get_text)
                results.append({'line': line, 'callee': callee, 'first_arg': first_arg, 'has_more_args': has_more})
                base_parts = []
            elif member:
                base_parts = base_parts + [f'.{member}'] if base_parts else [f'.{member}']
    return results


def _extract_gdscript_attribute_calls(children: List[Any], get_text: Callable, attribute: Any) -> List[Dict[str, Any]]:
    """Nav projection of GDScript `attribute` call sites (see core/callees/gdscript.py)."""
    results: List[Dict[str, Any]] = []
    for site in gdscript_attribute_sites(attribute, get_text):
        first_arg, has_more = _extract_first_arg(site.node, get_text)
        results.append({'line': _zero_arg(site.node, 'start_position').row + 1,
                        'callee': site.dotted or None,
                        'first_arg': first_arg, 'has_more_args': has_more})
    return results


def _extract_callee(
    call_node: Any,
    get_text: Callable,
    call_node_types: Optional[frozenset] = None,
) -> Optional[str]:
    """Extract callee name from a call expression node."""
    if not _zero_arg(call_node, 'child_count'):
        return None

    # Call-shaped nodes that are really other syntax (C++ mfp declaration, BACK-745)
    if is_misparsed_call(_zero_arg(call_node, 'kind'), call_node):
        return None

    # Language-specific call shapes shared with the analyzer path (PHP, Java, Scala,
    # Swift, ...): one implementation in core/callees, fluent chains collapse for nav.
    handled, name = extract_by_kind(
        _zero_arg(call_node, 'kind'), call_node, get_text,
        call_node_types=call_node_types, chain_receiver=CHAIN_COLLAPSE,
    )
    if handled:
        return name

    # Everything else (identifier, member access, splat, turbofish, parenthesized,
    # chained/IIFE) is the language-neutral tail shared with the analyzer path
    # (BACK-1279). Nav collapses fluent chains to `.prop` (BACK-415).
    return callee_name_from_node(
        call_node.child(0), get_text,
        call_node_types=call_node_types, chain_receiver=CHAIN_COLLAPSE,
    )


# Node kinds that hold a call's argument list. `value_arguments` (Kotlin/Swift, one
# level down inside `call_suffix`) and `FnCallArguments` (Zig) were missing, so nav
# never reported a first argument for those languages.
_ARG_CONTAINER_KINDS = (
    'argument_list', 'arguments', 'call_arguments', 'value_arguments', 'FnCallArguments',
    # Rust macro_invocation's argument container (e.g. `tracing::debug!("msg", x)`'s
    # `("msg", x)`) -- not an argument_list, but shaped the same way for this purpose.
    'token_tree',
)


def _arg_container(call_node: Any) -> Any:
    """The argument-list node of a call, or `call_node` itself when it already is one."""
    if _zero_arg(call_node, 'kind') in _ARG_CONTAINER_KINDS:
        return call_node
    for child in _children(call_node):
        kind = _zero_arg(child, 'kind')
        if kind in _ARG_CONTAINER_KINDS:
            return child
        if kind == 'call_suffix':  # Kotlin/Swift: call_expression > call_suffix > value_arguments
            for inner in _children(child):
                if _zero_arg(inner, 'kind') in _ARG_CONTAINER_KINDS:
                    return inner
    return None


def _extract_first_arg(call_node: Any, get_text: Callable) -> tuple:
    """Extract the first argument and whether more args follow."""
    container = _arg_container(call_node)
    if container is None:
        return None, False
    real_args = [
        c for c in _children(container)
        if _zero_arg(c, 'kind') not in ('(', ')', ',', 'comment')
        and _zero_arg(c, 'is_named')
    ]
    if not real_args:
        return None, False
    text = get_text(real_args[0]).splitlines()[0].strip()
    if len(text) > 40:
        text = text[:37] + '...'
    return text, len(real_args) > 1


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
