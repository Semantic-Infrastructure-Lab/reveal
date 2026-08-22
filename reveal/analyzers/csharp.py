"""C# analyzer using tree-sitter."""

from typing import List, Optional

from ..core import node_children as _children
from ..core.treesitter_compat import _zero_arg
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.cs', name='C#', icon='#️⃣')
class CSharpAnalyzer(TreeSitterAnalyzer):
    """Analyze C# source files.

    Extracts classes, interfaces, methods automatically using tree-sitter.
    """
    language = 'csharp'

    # ── Interfaces (BACK-403 pt 2) ──────────────────────────────────────────
    # C# shares tree-sitter's 'interface_declaration'/'class_declaration' node
    # kinds with Java and TS, but its own heritage shape is a single 'base_list'
    # child holding every comma-separated base (no extends/implements split —
    # C#'s ': Base, IFoo' syntax doesn't distinguish them, verified via
    # `reveal file.cs --show-ast`). Previously interfaces were invisible to
    # get_structure() (not in CLASS_NODE_TYPES) and class/interface bases fell
    # through to the base class's TS-shaped dispatch, which looks for
    # 'class_heritage'/'extends_type_clause' — neither exists in C#'s grammar —
    # so bases always returned []. Interface extraction itself (BACK-1003) is
    # now handled generically and cached in TreeSitterAnalyzer._get_or_build_structure().

    def _extract_class_bases(self, node) -> List[str]:
        node_type = _zero_arg(node, 'kind')
        # BACK-797: 'record_declaration' shares the same 'base_list' heritage
        # shape as class/interface (`record Foo(...) : IBar { ... }`) — added
        # alongside CLASS_NODE_TYPES gaining 'record_declaration', otherwise
        # a record's bases would fall through to the TS-shaped base handler
        # below, which looks for 'class_heritage' (doesn't exist in C#) and
        # always returns [].
        if node_type in ('class_declaration', 'interface_declaration', 'record_declaration'):
            return self._extract_csharp_base_list(node)
        return super()._extract_class_bases(node)

    def _is_abstract_class_node(self, node) -> bool:
        # public abstract class Shape { ... } — C# emits each modifier keyword
        # as its own separate 'modifier' wrapper node (unlike Java's single
        # grouped 'modifiers' node), each containing one token child.
        for child in _children(node):
            if _zero_arg(child, 'kind') != 'modifier':
                continue
            for sub in _children(child):
                if _zero_arg(sub, 'kind') == 'abstract':
                    return True
        return False

    def _extract_decorators(self, node) -> List[str]:
        """C# attributes (BACK-1087, D1): each '[Foo]'/'[Foo(...)]' is its own
        'attribute_list' node, a direct child of the class/method node itself
        (one attribute_list per bracket group, unlike Java's single grouped
        'modifiers' wrapper) -- verified via direct tree-sitter parse of
        `[HttpGet] [Authorize] public void Bar() {}`.
        """
        return [
            self._get_node_text(child)
            for child in _children(node)
            if _zero_arg(child, 'kind') == 'attribute_list'
        ]

    def _extract_csharp_base_list(self, node) -> List[str]:
        # class Dog : Animal, IAnimal { ... }  /  interface IDerived : IBase { ... }
        base_list = next(
            (c for c in _children(node) if _zero_arg(c, 'kind') == 'base_list'), None
        )
        if base_list is None:
            return []
        names: List[str] = []
        for item in _children(base_list):
            name = self._csharp_base_item_name(item)
            if name:
                names.append(name)
        return names

    def _csharp_base_item_name(self, item) -> Optional[str]:
        kind = _zero_arg(item, 'kind')
        if kind == 'qualified_name':
            # BACK-797: a namespace-qualified base (`System.IDisposable`,
            # `MediaBrowser.Controller.Resolvers.ItemResolver<T>`) is a
            # DISTINCT tree-sitter-c-sharp node kind from bare `identifier` —
            # previously unhandled here, so _csharp_base_item_name fell
            # through to `return None` and the base was silently dropped
            # from `bases` entirely (not even the qualified text — gone).
            # Confirmed live on samples/csharp (Jellyfin):
            # `BaseVideoResolver<T> : MediaBrowser.Controller.Resolvers.
            # ItemResolver<T>` lost its only base, so a real abstract-class
            # implementer relationship (`ItemResolver<T>` is a genuine
            # project-local abstract class) was invisible to `contracts`.
            # `qualified_name` nests left-associatively (`Ns.Sub.Name` is
            # `qualified_name(qualified_name(Ns, Sub), Name)`) — the base's
            # own simple name is always the rightmost non-'.' child, which
            # may itself be a plain `identifier` or (for `Ns.Foo<T>`) a
            # `generic_name`; recurse to unwrap either.
            children = [c for c in _children(item) if _zero_arg(c, 'kind') != '.']
            return self._csharp_base_item_name(children[-1]) if children else None
        if kind == 'generic_name':
            # IFoo<T> — extract the base identifier, drop the type args
            ident = next(
                (g for g in _children(item) if _zero_arg(g, 'kind') == 'identifier'), None
            )
            return self._get_node_text(ident).strip() if ident is not None else None
        if kind in ('identifier', 'type_identifier'):
            return self._get_node_text(item).strip() or None
        return None
