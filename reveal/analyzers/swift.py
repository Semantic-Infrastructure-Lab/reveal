"""Swift analyzer using tree-sitter."""

from typing import Any, Dict, List, Optional

from ..core import node_children as _children
from ..core.treesitter_compat import _zero_arg
from ..registry import register
from ..treesitter import TreeSitterAnalyzer, _NAME_KINDS


@register('.swift', name='Swift', icon='🦅')
class SwiftAnalyzer(TreeSitterAnalyzer):
    """Analyze Swift source files.

    Extracts classes, functions, protocols, structs automatically using tree-sitter.
    Supports iOS, macOS, and Swift-based applications.
    """
    language = 'swift'

    # ── Protocols (BACK-403 pt 2) ───────────────────────────────────────────
    # Swift's protocol is its interface concept, parsed as a distinct
    # 'protocol_declaration' node (like TS's 'interface_declaration'), so it was
    # invisible to get_structure() (not in CLASS_NODE_TYPES). Conformance/
    # inheritance for both classes and protocols is a list of
    # 'inheritance_specifier' children, each wrapping a 'user_type' →
    # 'type_identifier' (verified via `reveal file.swift --show-ast`) — the base
    # class's TS-shaped dispatch looks for 'class_heritage'/'extends_type_clause'
    # (neither exists in Swift), so bases always returned []. Swift has no
    # abstract-class keyword, so _is_abstract_class_node stays the base no-op:
    # the protocol is the only abstraction form. Note tree-sitter-swift emits
    # 'class_declaration' for class/struct/enum alike (distinguished by a token
    # child) — a struct/enum conforming to a protocol correctly reads as an
    # implementing type, consistent with the "concrete type with bases" model.

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, Any]:
        structure = super().get_structure(head=head, tail=tail, range=range, **kwargs)
        interfaces = self._extract_interface_declarations('protocol_declaration')
        if interfaces:
            if head or tail or range:
                interfaces = self._apply_semantic_slice(interfaces, head, tail, range)
            structure['interfaces'] = interfaces
        return structure

    def _extract_class_bases(self, node) -> List[str]:
        if _zero_arg(node, 'kind') in ('class_declaration', 'protocol_declaration'):
            return self._extract_swift_inheritance(node)
        return super()._extract_class_bases(node)

    def _extract_decorators(self, node) -> List[str]:
        """Swift attributes (BACK-1087, D1 Phase-2b): same shape as Java/Kotlin
        -- live in a 'modifiers' child of the class/method node itself, as an
        'attribute' child node (`@objc`, `@discardableResult`) -- verified via
        direct tree-sitter parse of `@objc\nclass Reporter: Batch {}`.
        """
        decorators: List[str] = []
        for child in _children(node):
            if _zero_arg(child, 'kind') != 'modifiers':
                continue
            for modifier in _children(child):
                if _zero_arg(modifier, 'kind') == 'attribute':
                    decorators.append(self._get_node_text(modifier))
        return decorators

    # ── extension declarations (BACK-8xx) ───────────────────────────────────
    # tree-sitter-swift parses `extension Foo: Protocol { ... }` as a
    # 'class_declaration' node (same kind as class/struct/enum, distinguished
    # only by a leading 'extension' token child) — so it's already walked by
    # the base class's CLASS_NODE_TYPES scan. But its name isn't a direct
    # `type_identifier` child the way `class Foo` / `struct Foo` are: it's
    # nested one level deeper, under a `user_type` child (the same shape
    # `_extract_swift_inheritance`'s conformance list already handles). Every
    # `_name_via_*` strategy in the shared base class's priority list only
    # looks at *direct* children, so `_get_node_name` returned None for every
    # extension — and `_extract_undecorated_classes` silently `continue`s on
    # any non-anonymous_class node with no name, dropping the ENTIRE
    # extension (not just its bases) from `classes`. Extension-based protocol
    # conformance (`extension SomeType: Drawable { ... }`) is a common Swift
    # idiom for adding conformance separately from a type's primary
    # declaration — this made all such conformances invisible to `contracts`.
    def _get_node_name(self, node) -> Optional[str]:
        if _zero_arg(node, 'kind') == 'class_declaration' and self._is_swift_extension(node):
            name = self._swift_extension_type_name(node)
            if name:
                return name
        return super()._get_node_name(node)

    def _is_swift_extension(self, node) -> bool:
        for child in _children(node):
            if _zero_arg(child, 'kind') == 'extension':
                return True
            if _zero_arg(child, 'kind') in ('class', 'struct', 'enum', 'actor'):
                return False
        return False

    def _swift_extension_type_name(self, node) -> Optional[str]:
        # extension Foo: Bar { ... }  ->  user_type -> type_identifier
        # extension Foo.Bar { ... }   ->  user_type -> user_type -> type_identifier
        # (nested type reference; last type_identifier is the extended type's
        # own simple name, matching how its primary declaration is named).
        for child in _children(node):
            if _zero_arg(child, 'kind') == 'user_type':
                type_identifiers: List[str] = []
                stack = [child]
                while stack:
                    n = stack.pop(0)
                    if _zero_arg(n, 'kind') == 'type_identifier':
                        text = self._get_node_text(n).strip()
                        if text:
                            type_identifiers.append(text)
                    stack.extend(_children(n))
                return type_identifiers[-1] if type_identifiers else None
        return None

    def _extract_swift_inheritance(self, node) -> List[str]:
        # class Circle: Base, Drawable  /  protocol Drawable: Shape
        # Each conformed/inherited type is a separate 'inheritance_specifier'
        # child wrapping a 'user_type' → 'type_identifier' (or a bare
        # 'type_identifier' in simpler grammars — both handled).
        names: List[str] = []
        for child in _children(node):
            if _zero_arg(child, 'kind') != 'inheritance_specifier':
                continue
            name = self._swift_specifier_name(child)
            if name:
                names.append(name)
        return names

    def _swift_specifier_name(self, specifier) -> Optional[str]:
        for child in _children(specifier):
            if _zero_arg(child, 'kind') == 'user_type':
                for sub in _children(child):
                    if _zero_arg(sub, 'kind') == 'type_identifier':
                        text = self._get_node_text(sub).strip()
                        if text:
                            return text
            elif _zero_arg(child, 'kind') == 'type_identifier':
                text = self._get_node_text(child).strip()
                if text:
                    return text
            elif _zero_arg(child, 'kind') == 'suppressed_constraint':
                # Suppressed-conformance / noncopyable-type syntax (Swift 5.9+):
                # `struct Foo: ~Copyable {}` parses as inheritance_specifier ->
                # suppressed_constraint -> ('~', type_identifier). Without this
                # branch the specifier is silently dropped; if `~Copyable` is a
                # type's ONLY conformance, bases ends up [] and the type vanishes
                # from 'contracts' implementers output entirely (BACK-829).
                # Report as '~Copyable' (not 'Copyable') so it reads as a
                # suppression rather than a normal conformance — distinct and
                # informative to consumers of bases.
                for sub in _children(child):
                    if _zero_arg(sub, 'kind') == 'type_identifier':
                        text = self._get_node_text(sub).strip()
                        if text:
                            return f'~{text}'
        return None

    # ── Node naming (BACK-918/BACK-915) ─────────────────────────────────────
    def _name_via_swift_operator_function(self, kids) -> Optional[str]:
        # Swift operator overload (`static func -(left: CGPoint, right:
        # CGPoint) -> CGPoint`, `static func *(...)`, `static func *=(...)`)
        # -- the "name" is a literal operator-symbol token whose tree-sitter
        # KIND literally IS the operator text (e.g. kind '-'), not an
        # identifier-family kind any `_name_via_*` strategy above
        # recognizes, and Swift's grammar has no wrapping parameter-list
        # node kind at all (`(`/`parameter`/`)` are direct siblings, not
        # nested under a `parameters`-kind node), so
        # `_name_via_param_adjacent` never even applies to Swift. Found via
        # the calls-recall-oracle Swift measurement (BACK-730, tenth
        # language): every operator overload (CGPoint/CGSize arithmetic --
        # a common idiom in any Swift codebase with custom geometry/value
        # types) was entirely absent from --outline/get_structure(), so
        # every call made from inside one had no caller scope to attribute
        # to at all. Same invisibility class as BACK-651 (C#
        # operator_declaration) and Ruby's `operator` node kind above --
        # here the symbol is a plain sibling token (no wrapping node), so
        # it's found positionally: the sibling immediately after the
        # literal `func` keyword child, only used as a last-resort fallback
        # (i.e. no earlier strategy already found a name).
        #
        # 'func' is NOT a Swift-exclusive node kind (Go and GDScript both
        # use it too) -- but this method is only reachable via SwiftAnalyzer
        # polymorphism now (BACK-918 push-down), so no language gate is
        # needed here the way the still-shared _name_via_scala_operator_
        # function requires one. Before this push-down, the unguarded
        # version on the shared base misnamed Go/GDScript anonymous func
        # literals (`func(y int) int {...}` reported as its own parameter
        # list text, `(y int)`) -- confirmed live and fixed as a byproduct
        # of this move, not a separate fix.
        for i, child in enumerate(kids):
            if _zero_arg(child, 'kind') == 'func' and i + 1 < len(kids):
                nxt = kids[i + 1]
                nxt_kind = _zero_arg(nxt, 'kind')
                if nxt_kind not in _NAME_KINDS and nxt_kind != '(':
                    return self._get_node_text(nxt)
        return None
