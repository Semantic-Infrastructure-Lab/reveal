"""Resolve an element name to its definition node -- one resolver for every by-name surface.

BACK-1400: `reveal file NAME` (display/element.py), `reveal file NAME --boundary`
and every other nav flag (file_handler.py), and MCP `reveal_element` each did
their own lookup, and all of them silently returned the first match:

- a bare name defined twice (`A.pop` / `B.pop`, Java overloads, Go
  `heapData.Pop` / `Heap.Pop`) gave the first one with no hint the others
  existed;
- `Parent.member` stopped at the first node named `Parent`, so Rust `Foo.bar`
  hit the fieldless `struct Foo` and never reached `impl Foo`;
- C++ out-of-line `FileAccess::get_file_as_bytes` answered only to its full
  `::` spelling -- neither the advertised `FileAccess.get_file_as_bytes` nor
  the bare name found it;
- type declarations other than class/struct (Java enum, Rust trait, Swift
  protocol, ...) were neither a bare-name target nor a `Parent`.

This module finds *every* definition a name could mean. Callers keep choosing
one the way they always have (`pick_best_candidate`), and the full candidate
list travels with the result (`describe_candidates`) so each surface can say
the name was ambiguous and how to address each definition.
"""

from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional, Sequence, Tuple

from .core import node_children as _children
from .core.node_taxonomy import (
    CLASS_NODES, MEMBER_CONTAINER_NODES, TYPE_DECL_NODES,
)
from .core.treesitter_compat import _zero_arg
from .treesitter import CHILD_NODE_TYPES, FUNCTION_NODE_TYPES

# Bare-name tier for type declarations. Kept ahead of functions (display's
# long-standing order) so `reveal A.java Foo` is the class, not its
# constructor; TYPE_DECL_NODES joins it so a Java enum beats its constructor too.
TYPE_TIER: Tuple[str, ...] = tuple(sorted(CLASS_NODES | TYPE_DECL_NODES))


@dataclass
class Resolution:
    """The definition a name resolved to, plus every definition it could mean.

    `tiers` is set for a bare-name resolution: checking whether a candidate's
    qualified name is itself an unambiguous address must search the same node
    kinds, or a C `stat` would read as unique beside a `struct stat` that
    display extraction does disclose.
    """
    node: Any
    candidates: List[Any] = field(default_factory=list)
    tiers: Optional[Sequence[Sequence[str]]] = None

    @property
    def ambiguous(self) -> bool:
        return len(self.candidates) > 1


def _start_line(node) -> int:
    return _zero_arg(node, 'start_position').row + 1


def _end_node(analyzer, node):
    return getattr(analyzer, '_function_end_node', lambda n: n)(node)


def _span(node) -> Tuple[int, int]:
    """Node identity. Not `is`: walking `children` builds fresh wrapper objects
    for the same node on every call; only _find_nodes_by_type's are cached."""
    return _zero_arg(node, 'start_byte'), _zero_arg(node, 'end_byte')


def _in_tree_order(nodes: Iterable[Any]) -> List[Any]:
    """Dedupe by span and sort by position -- deterministic regardless of the
    set-derived iteration order of the node-kind tuples that produced them."""
    seen = {}
    for node in nodes:
        seen.setdefault(_span(node), node)
    return [seen[key] for key in sorted(seen)]


def name_matches(node_name: Optional[str], wanted: str) -> bool:
    """`wanted` names this definition: exactly, or as the trailing segments of
    a C++ out-of-line qualified name (`get_file_as_bytes` and
    `FileAccess::get_file_as_bytes` both name `FileAccess::get_file_as_bytes`)."""
    if not node_name:
        return False
    return node_name == wanted or node_name.endswith('::' + wanted)


def pick_best_candidate(candidates, analyzer=None):
    """Disambiguate multiple same-named nodes (overloads, abstract+override
    pairs) by preferring one with a real 'block'-kind body over a bodyless
    signature (abstract/interface) or an expression-bodied one (BACK-650).

    Falls back to the first tree-order candidate when every candidate is
    equally block-bodied (true overloads with no signal to disambiguate) or
    equally bodyless -- same shape as the pre-fix behavior for that case.

    BACK-729: Dart's `function_signature`/`function_body` pair are disjoint
    SIBLINGS, not parent/child (see treesitter.py:_function_end_node's
    docstring) -- the plain 'block'-child scan below can never see a Dart
    method's real body, so an interface+impl same-name pair (e.g. an
    abstract `int parse(String input);` and its concrete override) always
    fell through to the first tree-order candidate, which is the bodyless
    abstract signature (found live: `reveal file.dart parse` resolved to
    the 1-line abstract declaration, never the implementation). When an
    analyzer with `_function_end_node` is available, resolve each
    candidate's paired body first -- for Dart this walks to the sibling
    `function_body`; for every other language `_function_end_node` is a
    no-op (returns the same node), so this changes nothing for them.
    """
    if len(candidates) == 1:
        return candidates[0]
    end_node = getattr(analyzer, '_function_end_node', None)
    for node in candidates:
        if end_node is not None:
            body = end_node(node)
            if body is not node and _zero_arg(body, 'kind') == 'function_body':
                return node
        if any(_zero_arg(child, 'kind') == 'block' for child in _children(node)):
            return node
    return candidates[0]


def _resolution(analyzer, candidates: List[Any]) -> Optional[Resolution]:
    if not candidates:
        return None
    return Resolution(node=pick_best_candidate(candidates, analyzer), candidates=candidates)


# ---------------------------------------------------------------------------
# Bare names
# ---------------------------------------------------------------------------

def resolve_bare_name(analyzer, name: str,
                      tiers: Sequence[Sequence[str]]) -> Optional[Resolution]:
    """Resolve a bare name against node-kind tiers; the first tier with a match
    supplies the pick (so `Foo` in Java is the class, not its constructor).

    Candidates are every same-named definition in *any* tier except those
    nested inside the pick. A class's own constructor is part of what you got
    and is not disclosed. A same-named definition elsewhere is disclosed even
    in another tier, e.g. a Rust `struct EmbedderOptions` in a sibling module
    of the `enum EmbedderOptions` that won.
    """
    per_tier = [
        _in_tree_order(
            node for kind in kinds for node in analyzer._find_nodes_by_type(kind)
            if name_matches(analyzer._get_node_name(node), name)
        )
        for kinds in tiers
    ] + [_in_tree_order(nodes) for nodes in _unnamed_kind_matches(analyzer, name)]
    winning = next((matches for matches in per_tier if matches), None)
    if winning is None:
        return None
    chosen = pick_best_candidate(winning, analyzer)
    start, end = _span(chosen)
    candidates = _in_tree_order(
        node for matches in per_tier for node in matches
        if _span(node) == (start, end) or not (start <= _span(node)[0] and _span(node)[1] <= end)
    )
    return Resolution(node=chosen, candidates=candidates, tiers=tiers)


def _unnamed_kind_matches(analyzer, name: str) -> List[List[Any]]:
    """The two last tiers: definitions whose node kind carries no name, so no
    kind tier can see them. JS-family function values named by their parent
    (`const f = () => {}`, class-field arrows -- BACK-431/527) come first, then
    test-callback labels the outline lists (`describe(foo)`, Zig `test "x"` --
    BACK-530/661). Hooks are optional, looked up by name on any analyzer."""
    tiers = []
    for hook in ('_find_named_function_values', '_find_named_test_callbacks'):
        find_all = getattr(analyzer, hook, None)
        tiers.append(list(find_all(name)) if find_all is not None else [])
    return tiers


# ---------------------------------------------------------------------------
# Parent.member
# ---------------------------------------------------------------------------

def _base_type_name(analyzer, type_node) -> Optional[str]:
    """`Foo` from a Rust impl's type/trait field: `Foo`, `Foo<T>`, `a::b::Foo`."""
    kind = _zero_arg(type_node, 'kind')
    if kind == 'generic_type':
        inner = type_node.child_by_field_name('type')
        return _base_type_name(analyzer, inner) if inner is not None else None
    if kind in ('scoped_type_identifier', 'scoped_identifier'):
        inner = type_node.child_by_field_name('name')
        return analyzer._get_node_text(inner) if inner is not None else None
    if kind in ('type_identifier', 'identifier', 'primitive_type'):
        return analyzer._get_node_text(type_node)
    return None


def container_names(analyzer, node) -> Tuple[str, ...]:
    """Names a member container answers to as the `Parent` of `Parent.member`.

    A Rust impl answers to its Self type first and its trait second:
    `_get_node_name` returns whichever `type_identifier` comes first, which is
    the trait for `impl Trait for Type` but the Self type for
    `impl path::Trait for Type`, so it can't be used here.
    """
    if _zero_arg(node, 'kind') == 'impl_item':
        names = []
        for field_name in ('type', 'trait'):
            part = node.child_by_field_name(field_name)
            base = _base_type_name(analyzer, part) if part is not None else None
            if base and base not in names:
                names.append(base)
        return tuple(names)
    name = analyzer._get_node_name(node)
    return (name,) if name else ()


def _member_nodes(analyzer, container, child_name: str, direct: bool) -> List[Any]:
    """Member definitions named `child_name` under `container`.

    direct=True stops at nested containers, so `Outer.m` is Outer's own `m`,
    not `Outer.Inner.m`. direct=False is the old whole-subtree search, kept as
    the fallback so Ruby `Module.method` (method inside a class inside the
    module) and methods of nested classes still resolve when nothing direct does.
    """
    found: List[Any] = []
    stack = list(reversed(_children(container)))
    while stack:
        node = stack.pop()
        kind = _zero_arg(node, 'kind')
        if kind in CHILD_NODE_TYPES:
            if analyzer._get_node_name(node) == child_name:
                found.append(node)
                continue
        if direct and kind in MEMBER_CONTAINER_NODES:
            continue
        stack.extend(reversed(_children(node)))
    return found


def go_receiver_type_name(analyzer, method_node) -> Optional[str]:
    """The receiver's type identifier of a Go method_declaration (`*Batch` -> Batch)."""
    for child in _children(method_node):
        if _zero_arg(child, 'kind') != 'parameter_list':
            continue
        for param in _children(child):
            if _zero_arg(param, 'kind') != 'parameter_declaration':
                continue
            for part in _children(param):
                kind = _zero_arg(part, 'kind')
                if kind == 'type_identifier':
                    return analyzer._get_node_text(part)
                if kind == 'pointer_type':
                    for inner in _children(part):
                        if _zero_arg(inner, 'kind') == 'type_identifier':
                            return analyzer._get_node_text(inner)
        # Only the first parameter_list is the receiver.
        break
    return None


def _go_receiver_methods(analyzer, parent_name: str, child_name: str) -> List[Any]:
    """Go `func (b *Batch) Run()` is a top-level method_declaration, not an AST
    child of the Batch struct (BACK-451) -- matched by receiver type instead."""
    if getattr(analyzer, 'language', None) != 'go':
        return []
    return [
        node for node in analyzer._find_nodes_by_type('method_declaration')
        if analyzer._get_node_name(node) == child_name
        and go_receiver_type_name(analyzer, node) == parent_name
    ]


def _out_of_line_definitions(analyzer, parent_name: str, child_name: str) -> List[Any]:
    """C++ `Vector<T> Foo::bar(...) {}` outside the class body: its name is the
    qualified `Foo::bar`, and no class node contains it."""
    suffix = f'{parent_name}::{child_name}'
    return [
        node for kind in FUNCTION_NODE_TYPES for node in analyzer._find_nodes_by_type(kind)
        if name_matches(analyzer._get_node_name(node), suffix)
    ]


def resolve_member(analyzer, parent_name: str, child_name: str) -> Optional[Resolution]:
    """Resolve `Parent.member` across every container named Parent.

    Searches all same-named containers (Rust splits a type across a struct and
    any number of impl blocks; a Python file can reuse a class name), then C++
    out-of-line definitions and Go receiver methods.
    """
    containers = [
        node for kind in MEMBER_CONTAINER_NODES for node in analyzer._find_nodes_by_type(kind)
        if parent_name in container_names(analyzer, node)
    ]
    members: List[Any] = []
    for direct in (True, False):
        members = [m for c in containers for m in _member_nodes(analyzer, c, child_name, direct)]
        if members:
            break
    members += _out_of_line_definitions(analyzer, parent_name, child_name)
    members += _go_receiver_methods(analyzer, parent_name, child_name)
    return _resolution(analyzer, _in_tree_order(members))


def resolve_path(analyzer, dotted: str) -> Optional[Resolution]:
    """Resolve `Parent.member` or a deeper `Outer.Inner.member`.

    A deeper path resolves its last `Parent.member` pair, then keeps the
    candidates whose qualified name is that whole path. So
    `Doc.Metadata.isMetadata` picks the nested enum's method, and a qualified
    name printed in a candidate list is itself an address.
    """
    parts = dotted.split('.')
    if len(parts) < 2 or not all(parts):
        return None
    resolution = resolve_member(analyzer, parts[-2], parts[-1])
    if resolution is None or len(parts) == 2:
        return resolution
    return _resolution(analyzer, [
        node for node in resolution.candidates
        if _qualifies(qualified_name(analyzer, node), dotted)
    ])


def _qualifies(qualname: str, dotted: str) -> bool:
    """`dotted` is this qualified name or its trailing segments
    (`Inner.m` qualifies `Outer.Inner.m`)."""
    return qualname == dotted or qualname.endswith('.' + dotted)


# ---------------------------------------------------------------------------
# Describing candidates
# ---------------------------------------------------------------------------

def qualified_name(analyzer, node, fallback: str = '?') -> str:
    """Human label for a definition: `A.pop`, `heapData.Pop`, `FileAccess::get`.
    `fallback` names a node whose kind carries no name (a JS arrow value)."""
    name = analyzer._get_node_name(node) or fallback
    if '::' in name:
        return name
    if _zero_arg(node, 'kind') == 'method_declaration' and getattr(analyzer, 'language', None) == 'go':
        receiver = go_receiver_type_name(analyzer, node)
        return f'{receiver}.{name}' if receiver else name
    parts = [name]
    parent = _zero_arg(node, 'parent')
    while parent is not None:
        if _zero_arg(parent, 'kind') in MEMBER_CONTAINER_NODES:
            names = container_names(analyzer, parent)
            if names:
                parts.insert(0, names[0])
        parent = _zero_arg(parent, 'parent')
    return '.'.join(parts)


def _resolves_uniquely_to(analyzer, address: str, node, tiers) -> bool:
    """`address` resolves to exactly `node` and nothing else."""
    if '.' in address:
        resolution = resolve_path(analyzer, address)
    else:
        resolution = resolve_bare_name(analyzer, address, tiers or (FUNCTION_NODE_TYPES, TYPE_TIER))
    return resolution is not None and not resolution.ambiguous and _span(resolution.node) == _span(node)


def describe_candidates(analyzer, resolution: Resolution, element: str) -> List[dict]:
    """JSON-safe candidate list: qualified name, span, whether it was chosen, and
    an `address` that selects exactly that definition.

    The address is the qualified name when that name re-resolves to this one
    definition only, else the definition's exact `:START-END` span. The span
    is what Java overloads need, since they share a qualified name, and it
    means the same thing to element extraction and to nav flags. A bare
    `:START` would not: nav flags read it as "line START to end of file".
    """
    described = []
    for node in resolution.candidates:
        name = qualified_name(analyzer, node, fallback=element.rsplit('.', 1)[-1])
        start = _start_line(node)
        end = _zero_arg(_end_node(analyzer, node), 'end_position').row + 1
        address = name if _resolves_uniquely_to(analyzer, name, node, resolution.tiers) else f':{start}-{end}'
        described.append({
            'name': name,
            'line_start': start,
            'line_end': end,
            'address': address,
            'selected': _span(node) == _span(resolution.node),
        })
    return described


def ambiguity_note(path: str, element: str, candidates: Sequence[dict]) -> List[str]:
    """Lines telling the reader `element` matched several definitions, which one
    they got, and an address that picks each one unambiguously."""
    chosen = next((c for c in candidates if c.get('selected')), candidates[0])
    lines = [
        f"Note: '{element}' matches {len(candidates)} definitions; showing "
        f"{chosen['name']} (line {chosen['line_start']}). To pick one:"
    ]
    for c in candidates:
        address = c.get('address') or f":{c['line_start']}-{c['line_end']}"
        label = f"line {c['line_start']}" if address == c['name'] else f"{c['name']}, line {c['line_start']}"
        lines.append(f"  reveal {path} {address}   # {label}")
    return lines
