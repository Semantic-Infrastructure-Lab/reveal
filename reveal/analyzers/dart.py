"""Dart analyzer using tree-sitter."""

from typing import List, Optional

from ..core import node_children as _children
from ..core import node_next_sibling as _next_sibling
from ..core.treesitter_compat import _zero_arg
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.dart', name='Dart', icon='🎯')
class DartAnalyzer(TreeSitterAnalyzer):
    """Analyze Dart source files.

    Extracts classes, functions, widgets automatically using tree-sitter.
    Supports Flutter and Dart-based applications.
    """
    language = 'dart'

    # ── Class bases (BACK-645) ──────────────────────────────────────────────
    # `class Foo extends Bar implements Baz, Qux { ... }` previously fell
    # through to the base class's Python-shaped _extract_class_bases dispatch
    # (looks for an 'argument_list' child — Dart's grammar has none), silently
    # returning []. Real shape (verified via `reveal file.dart --show-ast`):
    # Dart's 'class_definition' node kind collides with Python's/Scala's (all
    # three use the same tree-sitter node name), so this only fires for
    # actual Dart files via the per-analyzer language dispatch. Two separate
    # wrapper children — 'superclass' (extends) and 'interfaces' (implements)
    # — each hold direct 'type_identifier' children; a generic superclass
    # like 'extends Bar<T>' still exposes 'Bar' as a direct child with 'T'
    # nested one level deeper inside 'type_arguments', so the direct-children
    # filter naturally excludes the type parameter.

    def _extract_class_bases(self, node) -> List[str]:
        if _zero_arg(node, 'kind') != 'class_definition':
            return super()._extract_class_bases(node)
        bases = []
        for child in _children(node):
            if _zero_arg(child, 'kind') in ('superclass', 'interfaces'):
                for item in _children(child):
                    if _zero_arg(item, 'kind') == 'type_identifier':
                        text = self._get_node_text(item).strip()
                        if text:
                            bases.append(text)
        return bases

    # ── Signature-adjacent calls (BACK-760/BACK-764) ─────────────────────────
    def _dart_merge_signature_extra_calls(self, node, calls: List[str]) -> List[str]:
        """Merge calls found in a Dart signature node's OWN
        signature-adjacent children into its calls list: a constructor's
        initializer list (`: super(...), x = y, assert(cond)`) and ANY
        signature's `formal_parameter_list` DEFAULT VALUES (`{int x =
        paramDefault()}`) -- see `_build_function_dict`'s call site for
        why both live outside `body_node` entirely (BACK-760/BACK-764).

        Safe to call unconditionally (including when `body_node` already
        equals `node` itself, e.g. a bodyless `const` constructor): the
        `seen`-based dedup below makes a redundant re-walk of already-
        included calls harmless, and the kind check up front makes this a
        no-op for every non-Dart-signature node.
        """
        if _zero_arg(node, 'kind') not in (
            'function_signature', 'constructor_signature', 'factory_constructor_signature',
            'getter_signature', 'setter_signature', 'constant_constructor_signature',
        ):
            return calls
        extra: List[str] = []
        for child in _children(node):
            if _zero_arg(child, 'kind') == 'formal_parameter_list':
                _, _, param_calls = self._complexity_depth_and_calls(child)
                extra.extend(param_calls)
        sibling = _next_sibling(node)
        if sibling is not None and _zero_arg(sibling, 'kind') == 'initializers':
            _, _, init_calls = self._complexity_depth_and_calls(sibling)
            extra.extend(init_calls)
        if not extra:
            return calls
        seen = set(calls)
        merged = list(calls)
        for name in extra:
            if name not in seen:
                merged.append(name)
                seen.add(name)
        return merged

    # ── Constructor naming (BACK-760) ────────────────────────────────────────
    def _dart_constructor_name(self, node) -> Optional[str]:
        """Dart `ClassName(...)` / `ClassName.named(...)` /
        `factory ClassName.make(...)` -- 'constructor_signature'/
        'factory_constructor_signature'. Kids are a flat
        [('factory')?, identifier(Class), ('.', identifier(named))?,
        formal_parameter_list]. Dart's 'formal_parameter_list' isn't a
        member of `_PARAM_LIST_KINDS` (BACK-413's set is JS/Go/Java/C#-
        shaped, never audited against Dart), so PRIORITY-2's param-adjacent
        strategy never applies here, and PRIORITY-2b's first-identifier scan
        (`_name_via_identifier_kind`) would grab ONLY the class name --
        `Dog.named` and `Dog.fromJson` would both collapse to bare "Dog",
        indistinguishable from the unnamed default constructor and from
        each other. Returns 'Class' for the unnamed/default form or
        'Class.named' when a named/factory segment is present (BACK-760).
        """
        idents = [c for c in _children(node) if _zero_arg(c, 'kind') == 'identifier']
        if not idents:
            return None
        if len(idents) == 1:
            return self._get_node_text(idents[0])
        return f"{self._get_node_text(idents[0])}.{self._get_node_text(idents[1])}"

    # ── Callee naming (BACK-760) ─────────────────────────────────────────────
    def _callee_name_dart_new_expression(self, call_node) -> Optional[str]:
        """Dart `new Foo(...)` / `new List<int>.from(...)` -- 'new_expression'
        with NO named fields (Dart's grammar never uses fields): flat
        children `new`, type_identifier (the class), optional type_arguments
        (generics, ignored), optional '.' + identifier (named constructor),
        'arguments'. Same flat shape as `_callee_name_dart_flat_type_call`
        handles for constructor_invocation/const_object_expression, just
        prefixed with an explicit 'new' keyword instead of being bare or
        'const'-prefixed -- the shared extractor already ignores whatever
        leading token precedes the type_identifier, so it applies unchanged.
        """
        return self._callee_name_dart_flat_type_call(call_node)

    def _callee_name_dart_flat_type_call(self, call_node) -> Optional[str]:
        """Shared extractor for Dart's flat type-then-arguments call shapes:
        'constructor_invocation' (`List<int>.from(...)`, `Map<K,V>()`) and
        'const_object_expression' (`const Duration(milliseconds: 300)`,
        `const EdgeInsets.all(8)`). Both have the identical flat child
        layout modulo a leading token this extractor ignores (nothing for
        constructor_invocation, a 'const_builtin' token for
        const_object_expression): a type_identifier (the class, e.g.
        'List'/'Duration'), an optional type_arguments node (generic
        params, ignored -- same "don't let a generic suffix leak into the
        callee name" discipline as Rust's turbofish fix, BACK-733), an
        optional '.' + identifier (a NAMED constructor, e.g. 'from'/'all'),
        and 'arguments'. Returns 'List.from' for a named constructor or
        bare 'List'/'Duration' for the unnamed/default one (BACK-760).
        """
        base = None
        named = None
        seen_dot = False
        for child in _children(call_node):
            kind = _zero_arg(child, 'kind')
            if kind == 'type_identifier' and base is None:
                base = self._get_node_text(child).strip()
            elif kind == '.':
                seen_dot = True
            elif kind == 'identifier' and seen_dot and named is None:
                named = self._get_node_text(child).strip()
        if not base:
            return None
        return f"{base}.{named}" if named else base

    def _callee_name_dart_argument_part(self, call_node) -> Optional[str]:
        """Dart `foo()` / `obj.method()` / `this.foo()` / `Class.static()` /
        `obj?.method()` / `obj!.method()` / cascaded `..method()` --
        'argument_part' (the '(args)' selector that marks a call site).

        Unlike every other dotted-call node in this program (Java's
        method_invocation, Ruby's/GDScript's receiver-qualified nodes),
        Dart's grammar has NO node that wraps "receiver + call" together at
        all: a call is just the primary expression (identifier/`this`)
        followed by a flat run of SIBLING 'selector' nodes -- one per `.foo`
        segment, one per `(args)` call, one per bare `!`/`?.` operator. This
        node (the 'argument_part') only ever holds its own arguments; the
        qualifier, if any, is the selector immediately preceding this one's
        wrapping 'selector' in that flat sibling list, and the ultimate base
        (`obj`/`this`/`Class`) is whatever precedes that.

        Reconstructs one level of "receiver.method" (enough for
        `_bare_callee_name`'s last-segment split to resolve correctly for
        chains of any depth, matching every prior language's precedent that
        a full multi-segment reconstruction isn't required for recall).
        `!` (null-assertion) selectors are transparently skipped when
        walking backward for the receiver, since they carry no name.
        A cascade (`..method()`) has no adjacent receiver at all (the cascade
        target is the base expression of the whole cascade chain, not a
        structurally-local sibling) -- returns the bare method name only,
        same "no receiver available, bare name still resolves" convention
        as BACK-732's Python IIFE quirk. (BACK-760)
        """
        parent = _zero_arg(call_node, 'parent')
        if parent is None:
            return None
        parent_kind = _zero_arg(parent, 'kind')

        if parent_kind == 'cascade_section':
            for sib in _children(parent):
                if _zero_arg(sib, 'kind') == 'cascade_selector':
                    text = self._get_node_text(sib).strip()
                    return text or None
            return None

        if parent_kind != 'selector':
            return None

        container = _zero_arg(parent, 'parent')
        if container is None:
            return None
        siblings = _children(container)

        # Node equality isn't reliable across the tree-sitter 1.x binding
        # (BACK-573), so locate `parent`'s position among its own siblings
        # by matching start_byte instead of identity/`in`.
        target_start = _zero_arg(parent, 'start_byte')
        idx = None
        for i, sib in enumerate(siblings):
            if _zero_arg(sib, 'kind') == 'selector' and _zero_arg(sib, 'start_byte') == target_start:
                idx = i
                break
        if idx is None or idx == 0:
            return None

        def _is_bang_selector(node) -> bool:
            kids = _children(node)
            return len(kids) == 1 and _zero_arg(kids[0], 'kind') == '!'

        def _qualifier_identifier(qual_node) -> Optional[str]:
            for sub in _children(qual_node):
                if _zero_arg(sub, 'kind') == 'identifier':
                    return self._get_node_text(sub).strip()
            return None

        def _qualifier_in(node, depth: int = 0) -> Optional[str]:
            # A `.foo`/`?.foo` qualifier is USUALLY wrapped in its own
            # 'selector' node (the common case, siblings of a plain
            # identifier/this primary at container top level) -- but
            # `super.foo` puts it as a BARE direct sibling with no
            # 'selector' wrapper at all (verified live: `super.plainInit()`
            # has NO 'selector' around its 'unconditional_assignable_
            # selector'), and any unary-prefixed call (`await
            # x.foo()`/`await super.foo()`) nests the WHOLE receiver+
            # qualifier chain one level deeper inside the unary node
            # (`await_expression`'s own children are `[await, super,
            # unconditional_assignable_selector]` -- no 'selector' wrapper
            # there either). Both found via the Dart calls-recall-oracle
            # measurement (BACK-730): `super.initialize(...)`/`await
            # super.initialize(...)` (a common override-delegation idiom)
            # were silently dropped, not just misattributed. Recurses into
            # a wrapper node's LAST child (bounded depth) to find a nested
            # qualifier, matching Dart's actual "primary + trailing
            # selector-like suffixes, sometimes nested one level under a
            # prefix keyword" shape rather than assuming one fixed depth.
            if depth > 4:
                return None
            kind = _zero_arg(node, 'kind')
            if kind in ('unconditional_assignable_selector', 'conditional_assignable_selector'):
                return _qualifier_identifier(node)
            if kind == 'selector':
                kids = _children(node)
                if len(kids) == 1:
                    return _qualifier_in(kids[0], depth + 1)
                return None
            if kind in ('argument_part', 'arguments', 'identifier', 'this', 'super'):
                return None
            kids = _children(node)
            return _qualifier_in(kids[-1], depth + 1) if kids else None

        j = idx - 1
        while j >= 0 and _zero_arg(siblings[j], 'kind') == 'selector' and _is_bang_selector(siblings[j]):
            j -= 1

        if j < 0:
            return None

        prior = siblings[j]
        prior_kind = _zero_arg(prior, 'kind')

        if prior_kind == 'selector':
            prior_kids = _children(prior)
            if len(prior_kids) == 1 and _zero_arg(prior_kids[0], 'kind') in (
                'unconditional_assignable_selector', 'conditional_assignable_selector',
            ):
                method = _qualifier_identifier(prior_kids[0])
                if not method:
                    return None
                k = j - 1
                while k >= 0 and _zero_arg(siblings[k], 'kind') == 'selector' and _is_bang_selector(siblings[k]):
                    k -= 1
                if k >= 0 and _zero_arg(siblings[k], 'kind') in ('identifier', 'this', 'super'):
                    receiver = self._get_node_text(siblings[k]).strip()
                    if receiver:
                        return f"{receiver}.{method}"
                return method
            # Some other selector shape precedes this call (e.g. the call is
            # invoked on the result of a preceding call, `compute()?.process()`
            # -- `compute`'s own 'argument_part' selector sits here, not a
            # property qualifier) -- no clean receiver, structural precedent
            # (BACK-732) says a bare name is the right fallback, not a miss.
            return None

        if prior_kind in ('unconditional_assignable_selector', 'conditional_assignable_selector'):
            # `super.foo()` -- the qualifier is a BARE sibling, no 'selector'
            # wrapper (see `_qualifier_in`'s docstring above).
            method = _qualifier_identifier(prior)
            if not method:
                return None
            k = j - 1
            while k >= 0 and _zero_arg(siblings[k], 'kind') == 'selector' and _is_bang_selector(siblings[k]):
                k -= 1
            if k >= 0 and _zero_arg(siblings[k], 'kind') in ('identifier', 'this', 'super'):
                receiver = self._get_node_text(siblings[k]).strip()
                if receiver:
                    return f"{receiver}.{method}"
            return method

        if prior_kind in ('identifier', 'this'):
            text = self._get_node_text(prior).strip()
            return text or None

        # `await x.foo()` / `await super.foo()` -- the receiver+qualifier
        # chain is nested one level inside the unary `await_expression`
        # (or a similar prefix-operator node), not a flat sibling of this
        # call's own selector at all. No clean receiver reconstruction
        # attempted here (the base is nested too, not a plain adjacent
        # sibling) -- bare method name only, same "no receiver available,
        # bare name still resolves" convention as the cascade/computed-
        # target cases above.
        return _qualifier_in(prior)
