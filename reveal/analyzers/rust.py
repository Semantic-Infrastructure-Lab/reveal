"""Rust file analyzer - tree-sitter based."""

from typing import Any, Dict, List, Optional

from ..core import node_children as _children
from ..core import node_prev_sibling as _prev_sibling
from ..core.treesitter_compat import _zero_arg
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.rs', name='Rust', icon='')
class RustAnalyzer(TreeSitterAnalyzer):
    """Rust file analyzer.

    Full Rust support in 3 lines!
    """
    language = 'rust'

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, Any]:
        """BACK-1088: `trait` is Rust's interface declaration (`trait_item`) and was
        absent from the structure; collect it into `structure['interfaces']`."""
        structure = super().get_structure(head=head, tail=tail, range=range, **kwargs)
        interfaces = self._extract_interface_declarations('trait_item')
        if interfaces:
            if head or tail or range:
                interfaces = self._apply_semantic_slice(interfaces, head, tail, range)
            structure['interfaces'] = interfaces
        return structure

    def _extract_class_bases(self, node) -> List[str]:
        """Supertraits of a trait (`trait A: B + Debug`, the `trait_bounds` child);
        for a struct, the traits it implements (`impl Trait for A`)."""
        if _zero_arg(node, 'kind') == 'struct_item':
            return self._implemented_traits().get(self._get_node_name(node) or '', [])
        if _zero_arg(node, 'kind') == 'trait_item':
            for child in _children(node):
                if _zero_arg(child, 'kind') == 'trait_bounds':
                    return [self._get_node_text(b) for b in _children(child)
                            if _zero_arg(b, 'kind') in ('type_identifier', 'scoped_type_identifier',
                                                        'generic_type')]
        return super()._extract_class_bases(node)

    def _implemented_traits(self) -> Dict[str, List[str]]:
        """Map type name -> traits implemented via `impl Trait for Type` in this
        file (built once per analyzer). Generic args are dropped from the type
        name (`impl Tr for Foo<T>` -> `Foo`); the trait keeps its written path."""
        cached: Optional[Dict[str, List[str]]] = getattr(self, '_impl_trait_map', None)
        if cached is not None:
            return cached
        result: Dict[str, List[str]] = {}
        for impl in self._find_nodes_by_type('impl_item'):
            trait = impl.child_by_field_name('trait')
            target = impl.child_by_field_name('type')
            if trait is None or target is None:
                continue
            if _zero_arg(target, 'kind') == 'generic_type':
                target = target.child_by_field_name('type') or target
            trait_name = self._get_node_text(trait)
            bucket = result.setdefault(self._get_node_text(target), [])
            if trait_name not in bucket:
                bucket.append(trait_name)
        self._impl_trait_map = result
        return result

    def _is_trait_impl_method(self, node) -> bool:
        """BACK-1291: inside an `impl_item` that names a trait (`impl Display for A`),
        as opposed to an inherent `impl A`. Nested fns inside a method body stop at
        the first enclosing function so a helper isn't mistaken for a trait method."""
        parent = _zero_arg(node, 'parent')
        while parent is not None:
            kind = _zero_arg(parent, 'kind')
            if kind == 'impl_item':
                return parent.child_by_field_name('trait') is not None
            if kind == 'function_item':
                return False
            parent = _zero_arg(parent, 'parent')
        return False

    # Keywords a token tree can hold right before a `(...)` group (`match (a, b)`).
    _TOKEN_TREE_NON_CALLS = frozenset({
        'match', 'while', 'if', 'for', 'in', 'return', 'as', 'else', 'loop', 'let',
        'mut', 'ref', 'move', 'where', 'unsafe', 'async', 'await', 'dyn', 'impl', 'fn',
    })
    # Nested items get their own entries; attribute arguments (`cfg(all(...))`) are not calls.
    _TOKEN_TREE_SKIP = frozenset({
        'function_item', 'attribute_item', 'inner_attribute_item', 'macro_definition',
    })

    def _implicit_call_nodes(self, func_node) -> List[Any]:
        """BACK-1393: calls inside macro arguments (`format!("{}", h())`, `vec![k()]`,
        `assert_eq!(m(), 3)`). tree-sitter leaves those as a flat, unparsed token_tree
        with no call_expression, so an identifier directly followed by a `(...)` group
        is taken as a call. Best-effort: a tuple-struct pattern inside `matches!`
        (`Some(_)`) reads the same way."""
        found: List[Any] = []
        stack = list(_children(func_node))
        while stack:
            node = stack.pop()
            kind = _zero_arg(node, 'kind')
            if kind in self._TOKEN_TREE_SKIP:
                continue
            if kind == 'token_tree':
                self._token_tree_calls(node, found)
                continue
            stack.extend(_children(node))
        found.sort(key=lambda n: _zero_arg(n, 'start_byte'))
        return found

    def _token_tree_calls(self, tree, found: List[Any]) -> None:
        kids = _children(tree)
        for i, child in enumerate(kids):
            kind = _zero_arg(child, 'kind')
            if kind == 'token_tree':
                self._token_tree_calls(child, found)
            elif kind == 'identifier' and i + 1 < len(kids):
                group = kids[i + 1]
                if (_zero_arg(group, 'kind') == 'token_tree'
                        and self._get_node_text(group).startswith('(')
                        and self._get_node_text(child) not in self._TOKEN_TREE_NON_CALLS):
                    found.append(child)

    def _extract_decorators(self, node) -> List[str]:
        """Rust attributes (BACK-1087, D1 Phase-2b): unlike every other
        Phase-2a/2b language (Java/C#/Kotlin/Swift/PHP all attach annotations
        as a direct child), tree-sitter emits `#[derive(Debug)]` etc. as a
        PRECEDING SIBLING of the struct/fn/enum/impl/trait node it annotates,
        not a child of it -- verified via direct tree-sitter parse of
        `#[derive(Debug)]\nstruct Reporter { total: i32 }`. Walk backward
        through preceding siblings collecting consecutive 'attribute_item'
        nodes, stopping at the first non-attribute sibling (e.g. a comment
        means the run of attributes ended before this item).
        """
        decorators: List[str] = []
        sib = _prev_sibling(node)
        while sib is not None and _zero_arg(sib, 'kind') == 'attribute_item':
            decorators.insert(0, self._get_node_text(sib))
            sib = _prev_sibling(sib)
        return decorators
