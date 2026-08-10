"""Kotlin analyzer using tree-sitter."""

from typing import Any, Dict, List, Optional, Set

from ..core import node_children as _children
from ..core.treesitter_compat import _zero_arg
from ..registry import register
from ..treesitter import TreeSitterAnalyzer

# BACK-738 shape 1: `@Composable (() -> Unit)`-style parenthesized annotated
# function-type parameters trip a fwcd/tree-sitter-kotlin grammar ambiguity
# (no upstream fix as of 2026-08 -- see BACK-738 notes #4-#8; BACK-1001
# tracks the separate shapes that ARE fixed upstream but not yet vendored).
# The malformed parameter's ERROR node cascades and swallows the entire
# enclosing declaration, which then collapses to a single top-level ERROR
# node instead of its normal fun/class/interface/object *_declaration node
# -- invisible to _find_nodes_by_type() and silently dropped from
# --outline/architecture/calls:// with zero warning. Confirmed via
# --show-ast: the ERROR node's leading children are always
# [modifiers?, <declaration keyword>, <identifier>, ...] -- that fingerprint
# is what recovery below keys off of.
_KOTLIN_ERROR_DECLARATION_KEYWORDS = {'fun', 'class', 'interface', 'object'}


@register('.kt', name='Kotlin', icon='🔷')
@register('.kts', name='Kotlin Script', icon='📜')
class KotlinAnalyzer(TreeSitterAnalyzer):
    """Analyze Kotlin source files.

    Extracts classes, functions, interfaces automatically using tree-sitter.
    Supports both .kt (Kotlin) and .kts (Kotlin Script) files.
    """
    language = 'kotlin'

    # ── Interfaces (BACK-403 pt 2) ──────────────────────────────────────────
    # Unlike Java/C#/TS, Kotlin has no distinct interface node kind: an
    # interface parses as a 'class_declaration' carrying an 'interface' token
    # child (a regular class carries a 'class' token; an enum class carries both
    # 'enum' and 'class') — verified via `reveal file.kt --show-ast`. So every
    # interface was already extracted, but mislabelled as a class. We repartition
    # here: after the base walk populates structure['classes'] with all
    # class_declarations, interface-flavoured ones are moved into an
    # 'interfaces' bucket so the contracts classifier sees them as contracts,
    # not concrete implementations. Bases (for both classes and interfaces) are a
    # list of 'delegation_specifier' children, each wrapping either a 'user_type'
    # (plain supertype) or a 'constructor_invocation' → 'user_type' (superclass
    # constructor call). Abstract classes carry a 'modifiers' → 'abstract' token.

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, Any]:
        structure = super().get_structure(head=head, tail=tail, range=range, **kwargs)
        interface_lines = self._interface_declaration_lines()
        if interface_lines:
            classes = structure.get('classes', [])
            remaining: List[Dict[str, Any]] = []
            interfaces: List[Dict[str, Any]] = []
            for cls in classes:
                if cls.get('line') in interface_lines:
                    # An interface can't be abstract-modified; drop the stray flag if
                    # the base walk happened to set one so it renders as a contract.
                    cls.pop('is_abstract', None)
                    interfaces.append(cls)
                else:
                    remaining.append(cls)
            if interfaces:
                structure['classes'] = remaining
                structure['interfaces'] = interfaces
        self._recover_error_declarations(structure)
        return structure

    def _recover_error_declarations(self, structure: Dict[str, Any]) -> None:
        """Recover BACK-738 shape-1 declarations swallowed by an ERROR node.

        Only outermost ERROR nodes (not ones nested inside another ERROR --
        those are just sub-fragments of an already-handled cascade) that are
        led by [modifiers?, declaration-keyword, identifier] are recovered:
        that exact fingerprint is confirmed (via --show-ast, BACK-738 notes
        #4/#6) to be this grammar defect specifically, so a false positive
        misrecovering some unrelated parse error is not a realistic risk.
        Anything else under an outermost ERROR node is left unrecovered but
        still reported via structure['parse_warnings'] -- silently staying
        dropped with no signal at all is the exact failure mode this ticket
        is about (cf. BACK-1016's composite-adapter silent-failure fix).
        """
        error_nodes = self._find_nodes_by_type('ERROR')
        if not error_nodes:
            return

        # Node identity/id() is NOT stable across separate parent-chain
        # walks in this tree-sitter binding (see treesitter_compat.py's
        # start_byte-based sibling matching for the same reason) -- each
        # access can hand back a fresh wrapper object for the same
        # underlying node. Match ERROR ancestors by start_byte instead.
        error_starts = {_zero_arg(n, 'start_byte') for n in error_nodes}
        recovered = {'functions': [], 'classes': [], 'interfaces': []}
        parse_warnings: List[Dict[str, Any]] = []

        for node in error_nodes:
            if self._is_nested_error(node, error_starts):
                continue  # a fragment of an already-handled outer ERROR

            line = node.start_position().row + 1
            match = self._match_kotlin_error_declaration(node)
            if match is None:
                parse_warnings.append({
                    'type': 'unrecovered_parse_error',
                    'line': line,
                    'message': (
                        'Kotlin grammar parse error (tree-sitter ERROR node); '
                        'the enclosing declaration may be missing from this '
                        "file's structure (BACK-738)"
                    ),
                })
                continue

            keyword, name = match
            line_end = node.end_position().row + 1
            entry: Dict[str, Any] = {
                'line': line,
                'line_end': line_end,
                'name': name,
                'recovered_from_error': True,
            }
            if keyword == 'fun':
                entry.update({
                    'signature': '',
                    'line_count': line_end - line + 1,
                    'code_line_count': 0,
                    'depth': 0,
                    'complexity': 0,
                    'decorators': [],
                    'calls': [],
                })
                recovered['functions'].append(entry)
            else:
                entry.update({'decorators': [], 'bases': []})
                recovered['interfaces' if keyword == 'interface' else 'classes'].append(entry)

            parse_warnings.append({
                'type': 'recovered_parse_error',
                'line': line,
                'message': (
                    f"Recovered '{name}' from a Kotlin grammar parse error "
                    '(BACK-738 shape 1: @Composable-style annotated '
                    'function-type parameter) -- name/line only, other '
                    'details (params, body, bases, calls) may be incomplete'
                ),
            })

        for category, entries in recovered.items():
            if entries:
                structure[category] = structure.get(category, []) + entries
        if parse_warnings:
            # A dict, not a bare list: build_hierarchy() (reveal/display/
            # outline.py) treats every list-of-dicts category as a set of
            # navigable outline nodes, which would render these warnings as
            # bogus nameless entries. Wrapping keeps it available to JSON/
            # programmatic consumers (and future confidence-signal wiring,
            # cf. BACK-738 note #4's adapter.py:209 confidence=1.0 gap)
            # without corrupting --outline.
            existing = structure.get('parse_warnings', {}).get('items', [])
            structure['parse_warnings'] = {'items': existing + parse_warnings}

    @staticmethod
    def _is_nested_error(node, error_starts: Set[int]) -> bool:
        ancestor = _zero_arg(node, 'parent')
        while ancestor is not None:
            if ancestor.kind() == 'ERROR' and _zero_arg(ancestor, 'start_byte') in error_starts:
                return True
            ancestor = _zero_arg(ancestor, 'parent')
        return False

    def _match_kotlin_error_declaration(self, error_node) -> Optional[tuple]:
        """Return (keyword, name) if `error_node` starts with a recognizable
        [modifiers?, declaration-keyword, identifier] prefix, else None."""
        children = _children(error_node)
        idx = 0
        if idx < len(children) and children[idx].kind() == 'modifiers':
            idx += 1
        if idx >= len(children) or children[idx].kind() not in _KOTLIN_ERROR_DECLARATION_KEYWORDS:
            return None
        keyword = children[idx].kind()
        idx += 1
        if idx >= len(children) or children[idx].kind() not in ('simple_identifier', 'type_identifier'):
            return None
        name = self._get_node_text(children[idx]).strip()
        if not name:
            return None
        return keyword, name

    def _interface_declaration_lines(self) -> Set[int]:
        """Start lines of class_declaration nodes that are actually interfaces.

        A Kotlin interface is a class_declaration whose direct children include
        an 'interface' token (regular/enum classes have a 'class' token instead).
        """
        lines: Set[int] = set()
        for node in self._find_nodes_by_type('class_declaration'):
            for child in _children(node):
                if child.kind() == 'interface':
                    lines.add(node.start_position().row + 1)
                    break
        return lines

    def _get_class_node_types(self) -> List[str]:
        # BACK-805: Kotlin `object Foo : Bar { ... }` / `companion object : Bar
        # { ... }` singleton declarations parse to their OWN node kinds
        # (`object_declaration` / `companion_object`), never `class_declaration`
        # — confirmed via `--show-ast` on `object Registry : Drawable { }`.
        # Neither was in the shared CLASS_NODE_TYPES (which lists only
        # `class_declaration` for Kotlin), so a named object implementing an
        # interface/extending a class was entirely invisible to
        # get_structure()['classes'], --outline, AND the `contracts`
        # implementer classifier — the same "whole declaration silently
        # dropped" shape as Swift's BACK-804 `extension Foo: Protocol`
        # finding. `object_declaration` only (not `companion_object`, whose
        # optional name and "Companion"-default make it a separate, lower-
        # value follow-up not needed by this corpus — see the Kotlin recall
        # oracle README's Decision section) is added here, Kotlin-scoped via
        # this override rather than editing the shared CLASS_NODE_TYPES, so
        # no other language's class extraction is touched.
        return list(super()._get_class_node_types()) + ['object_declaration']

    def _extract_class_bases(self, node) -> List[str]:
        if _zero_arg(node, 'kind') in ('class_declaration', 'object_declaration'):
            return self._extract_kotlin_delegation(node)
        return super()._extract_class_bases(node)

    def _extract_kotlin_delegation(self, node) -> List[str]:
        # class Circle : Base(), Drawable  /  interface Drawable : Shape
        names: List[str] = []
        for child in _children(node):
            if child.kind() != 'delegation_specifier':
                continue
            name = self._kotlin_delegation_name(child)
            if name:
                names.append(name)
        return names

    def _kotlin_delegation_name(self, specifier) -> Optional[str]:
        for child in _children(specifier):
            if child.kind() == 'constructor_invocation':
                # Base() — the invoked supertype is a nested user_type
                name = self._kotlin_user_type_name(child)
                if name:
                    return name
            elif child.kind() == 'user_type':
                return self._kotlin_first_type_identifier(child)
            elif _zero_arg(child, 'kind') == 'explicit_delegation':
                # BACK-805: `class Foo(...) : Bar by delegateExpr` — Kotlin's
                # interface-delegation-by-object language feature. Confirmed
                # via `--show-ast`: this is a THIRD delegation_specifier
                # shape, distinct from a plain `user_type` (no-parens
                # interface) and a `constructor_invocation` (superclass
                # constructor call) — a `delegation_specifier` wrapping an
                # `explicit_delegation` node whose own children are
                # `[user_type, 'by', <delegate expression>]`. Neither
                # existing branch above matched this node kind at all, so
                # every `by`-delegated interface was silently dropped from
                # `bases` — the whole class, not just this one base, then
                # became invisible to `contracts` (no bases -> not an
                # implementer) whenever `by`-delegation was its ONLY
                # supertype clause. Confirmed live and non-vacuous: 25+
                # files in samples/kotlin (Tivi) use this idiom, e.g.
                # `class ShowStore(...) : Store<Long, TiviShow> by
                # storeBuilder(...)`. The delegate expression itself
                # (`storeBuilder(...)`) is irrelevant to `bases` — only the
                # user_type being delegated TO matters.
                name = None
                for sub in _children(child):
                    if _zero_arg(sub, 'kind') == 'user_type':
                        name = self._kotlin_first_type_identifier(sub)
                        break
                if name:
                    return name
            elif _zero_arg(child, 'kind') == 'function_type':
                # class Foo(...) : () -> T — a bare function-type supertype has
                # no identifiable base name (it's structural, not nominal), but
                # dropping it silently vanishes the whole delegation clause (and
                # any sibling bases) from bases. Report the literal source text
                # ('() -> T') as a synthetic name so the class still shows up in
                # contracts/implementers output (BACK-830).
                text = self._get_node_text(child).strip()
                if text:
                    return text
        return None

    def _kotlin_user_type_name(self, container) -> Optional[str]:
        for child in _children(container):
            if child.kind() == 'user_type':
                return self._kotlin_first_type_identifier(child)
        return None

    def _kotlin_first_type_identifier(self, user_type) -> Optional[str]:
        # Take only the leading type_identifier (the base name); skip nested
        # type_arguments so a generic supertype List<Foo> yields 'List', not 'Foo'.
        for child in _children(user_type):
            if child.kind() == 'type_identifier':
                text = self._get_node_text(child).strip()
                if text:
                    return text
        return None

    def _is_abstract_class_node(self, node) -> bool:
        # abstract class Base { ... } — unlike Java's flat 'modifiers' → 'abstract',
        # Kotlin wraps it a level deeper: 'modifiers' → 'inheritance_modifier' →
        # 'abstract' token (verified via --show-ast). Scan the modifiers subtree
        # for the token so the exact wrapper kind doesn't have to be hard-coded.
        for child in _children(node):
            if child.kind() != 'modifiers':
                continue
            for sub in _children(child):
                if sub.kind() == 'abstract':
                    return True
                for leaf in _children(sub):
                    if leaf.kind() == 'abstract':
                        return True
        return False
