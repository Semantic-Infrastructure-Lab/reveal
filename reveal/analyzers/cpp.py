"""C++ file analyzer - tree-sitter based."""

from typing import List, Optional

from ..core import node_children as _children
from ..core.treesitter_compat import _zero_arg
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.cpp', '.cc', '.cxx', '.hpp', '.hh', '.h++', name='C++', icon='⚙️')
class CppAnalyzer(TreeSitterAnalyzer):
    """C++ file analyzer.

    Full C++ support with automatic extraction:
    - Functions
    - Classes
    - Structs
    - Namespaces
    - Templates
    - Includes
    - Element extraction
    """
    language = 'cpp'

    # ── Class bases (BACK-645) ──────────────────────────────────────────────
    # `class Foo final : public Bar, private ns::Baz { ... }` previously fell
    # through to the base class's Python/TS-shaped _extract_class_bases
    # dispatch (neither 'argument_list' nor 'class_heritage' exist in C++'s
    # grammar), silently returning []. Real shape (verified via
    # `reveal file.cpp --show-ast`): a 'base_class_clause' child wrapping
    # 'type_identifier' (unqualified) or 'qualified_identifier' (namespaced,
    # e.g. 'ns::Bar') entries, interleaved with 'access_specifier' tokens
    # (public/private/protected) that are skipped here — bases are recorded
    # regardless of access level, matching every other language's behavior.

    def _extract_class_bases(self, node) -> List[str]:
        if _zero_arg(node, 'kind') != 'class_specifier':
            return super()._extract_class_bases(node)
        for child in _children(node):
            if _zero_arg(child, 'kind') == 'base_class_clause':
                bases = []
                for item in _children(child):
                    if _zero_arg(item, 'kind') in ('type_identifier', 'qualified_identifier'):
                        text = self._get_node_text(item).strip()
                        if text:
                            bases.append(text)
                return bases
        return []

    # ── Callee naming (BACK-915 slice 4) ──────────────────────────────────────

    def _callee_name_cpp_new(self, call_node) -> Optional[str]:
        # C++: new ClassName(args) / new NS::ClassName(args) — new_expression.
        # A DISTINCT node kind from PHP's object_creation_expression above
        # despite the identical source shape (BACK-730 C++ pre-flight,
        # calls-recall-oracle 11th candidate). child(0) is the literal 'new'
        # token, so the generic _callee_name_generic fallback returned the
        # bare keyword "new" as the callee, not the class name — and unlike
        # Swift's constructor_expression (rescued by _bare_callee_name's
        # generic-suffix stripping since its raw text still carries the real
        # name), "new" has no '<' to strip, so this needed its own dispatch
        # case, same shape as PHP's `new ClassName()` handling.
        type_node = call_node.child_by_field_name('type')
        if type_node is None:
            return None
        kind = _zero_arg(type_node, 'kind')
        if kind == 'qualified_identifier':
            text = self._get_node_text(type_node).strip()
            if text:
                return f"new {text.split('::')[-1]}"
        text = self._get_node_text(type_node).strip()
        return f"new {text}" if text else None

    def _is_cpp_member_function_pointer_misparse(self, call_node) -> bool:
        """True if `call_node` is actually a member-function-pointer
        declaration/assignment misparsed as a call (BACK-745).

        `void (Base::*mfp)() = &Base::plain;` (a pointer-to-member-function
        variable, no typedef) has no dedicated node shape in tree-sitter-cpp
        -- it parses as NESTED call_expression nodes instead:
        `call_expression(call_expression(primitive_type 'void',
        argument_list('Base::*mfp')), argument_list())`. The inner call's
        'arguments' field holds `qualified_identifier(Base, ::,
        pointer_type_declarator(*, mfp))` -- `Base::*mfp` is a declarator,
        not a valid call-argument expression, so a `pointer_type_declarator`
        anywhere in a call's argument list is a reliable, narrow signal that
        this is the mfp-declaration misparse rather than a real call (no
        legitimate C++ call can have a bare pointer-to-member declarator as
        an argument). Confirmed live via tree_sitter_language_pack: without
        this check, the inner call's generic callee fallback returned the
        primitive type keyword itself ("void") as a garbage callee, and
        (independently, BACK-732) the outer call's callee-is-a-call fallback
        returned the inner call's raw, un-normalized source text.
        """
        args = call_node.child_by_field_name('arguments')
        if args is None:
            return False
        stack = _children(args)
        while stack:
            n = stack.pop()
            if _zero_arg(n, 'kind') == 'pointer_type_declarator':
                return True
            stack.extend(_children(n))
        return False

    def _callee_name_cpp_direct_init(self, call_node) -> Optional[str]:
        """C++ direct-initialization: `ClassName obj(args);`,
        `std::vector<int> v(10);` — `init_declarator` with a bare
        `argument_list` in its 'value' field (no `new` keyword, no
        call-expression wrapper at all).

        `init_declarator` is shared with every OTHER language/shape that
        merely assigns a value (`int y = 5;`, whose 'value' field is a
        `number_literal` or `call_expression`, already handled by the
        generic call_expression dispatch) — checking 'value' is literally
        an `argument_list` node is what isolates the direct-init shape
        from plain declarations (`int x;`, no 'value' field at all) and
        copy-init (`Foo obj2 = Foo(3, 4);`) alike (BACK-744).

        The callee name is NOT on this node — it's the TYPE, which lives
        on the *parent* `declaration` node's 'type' field (`init_declarator`
        only holds the variable name + args). A qualified type
        (`std::vector<int>`) collapses to its trailing `::`-segment only,
        matching `_callee_name_cpp_new`'s convention for `new NS::Name(...)`.
        No "new " prefix — unlike heap allocation, direct-init has no `new`
        keyword in the source to echo.

        `init_declarator` is also in CALL_NODE_TYPES for plain C and
        Objective-C (they share the node kind for ordinary `int x = 5;`
        declarations) — the base class's default (treesitter.py) stays a
        real no-op instead of falling through to the generic callee-name
        resolver so a C/Obj-C variable declaration never gets misreported
        as a call; only C++ files (this override) attempt the shape check
        below.
        """
        value_node = call_node.child_by_field_name('value')
        if value_node is None or _zero_arg(value_node, 'kind') != 'argument_list':
            return None
        decl_node = _zero_arg(call_node, 'parent')
        if decl_node is None:
            return None
        type_node = decl_node.child_by_field_name('type')
        if type_node is None:
            return None
        kind = _zero_arg(type_node, 'kind')
        if kind not in ('type_identifier', 'qualified_identifier'):
            return None
        text = self._get_node_text(type_node).strip()
        if not text:
            return None
        return text.split('::')[-1] if kind == 'qualified_identifier' else text
