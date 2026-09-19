"""Ruby analyzer using tree-sitter."""

from typing import Any, List, Optional

from ..core import node_children as _children
from ..core.treesitter_compat import _zero_arg
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.rb', name='Ruby', icon='💎')
class RubyAnalyzer(TreeSitterAnalyzer):
    """Analyze Ruby source files.

    Extracts classes, methods, modules automatically using tree-sitter.
    """
    language = 'ruby'
    IMPORTS_VIA_EXTRACTOR = True  # BACK-1089

    # ── Class bases (BACK-645) ──────────────────────────────────────────────
    # `class Foo < Bar` / `class Foo < ActiveSupport::Logger::SimpleFormatter`
    # previously fell through to the base class's Python-shaped
    # _extract_class_bases dispatch (looks for an 'argument_list' child —
    # Ruby's grammar has none), silently returning []. Real shape (verified
    # via `reveal file.rb --show-ast`): a 'superclass' child wrapping either a
    # bare 'constant' or a dotted-path 'scope_resolution' node — both cases
    # captured by taking the whole child's text (a nested scope_resolution
    # already renders its full 'A::B::C' text as one node).

    def _extract_class_bases(self, node) -> List[str]:
        if _zero_arg(node, 'kind') != 'class':
            return super()._extract_class_bases(node)
        for child in _children(node):
            if _zero_arg(child, 'kind') == 'superclass':
                for item in _children(child):
                    if _zero_arg(item, 'kind') in ('constant', 'scope_resolution'):
                        text = self._get_node_text(item).strip()
                        return [text] if text else []
        return []

    # ── Callee naming (BACK-915 slice 4) ──────────────────────────────────────
    # Reached via an explicit `self.language == 'ruby'` guard in
    # treesitter.py's _get_callee_name (Ruby's 'call' node kind is the SAME
    # kind Python's plain call() uses, so it can't be table-driven by kind
    # alone) — not through the general dispatch table, so this has no
    # no-op stub sibling on the base class the way the table-driven hooks do.

    # ── Paren-less calls (BACK-1297) ───────────────────────────────────────
    # A receiver-less, argument-less call (`used`) is a bare `identifier`, not
    # a `call` node — indistinguishable from a local variable read by syntax
    # alone, so every helper called that way read as uncalled. Approximation:
    # an identifier in value position that is never bound in the enclosing
    # method (parameter, assignment target, block/for/rescue variable) is a
    # method call. Flow-insensitive on purpose; misses at worst a call shadowed
    # by a same-named local. Nested defs are their own scope and are skipped.

    _RUBY_BINDING_PARENTS = frozenset({
        'method_parameters', 'block_parameters', 'lambda_parameters',
        'optional_parameter', 'keyword_parameter', 'splat_parameter',
        'hash_splat_parameter', 'block_parameter', 'destructured_parameter',
        'left_assignment_list', 'rest_assignment', 'exception_variable',
        'for', 'pattern', 'as_pattern',
    })
    _RUBY_SCOPE_NODES = frozenset({'method', 'singleton_method'})

    def _implicit_call_nodes(self, func_node) -> List[Any]:
        idents: List[tuple] = []
        bound: set = set()
        stack = list(_children(func_node))
        while stack:
            node = stack.pop()
            kind = _zero_arg(node, 'kind')
            if kind in self._RUBY_SCOPE_NODES:
                continue
            if kind == 'identifier':
                parent = _zero_arg(node, 'parent')
                pkind = _zero_arg(parent, 'kind') if parent is not None else None
                name = self._get_node_text(node)
                if pkind in self._RUBY_SCOPE_NODES:
                    continue  # the method's own name
                if pkind in self._RUBY_BINDING_PARENTS or self._is_assignment_target(parent, node):
                    bound.add(name)
                elif pkind == 'call':
                    # `foo.bar` / `baz 1`: handled as a `call` node already.
                    if parent.child_by_field_name('receiver') is not None or \
                            parent.child_by_field_name('method') is not None:
                        continue
                else:
                    idents.append((name, node))
            stack.extend(reversed(_children(node)))
        return [node for name, node in idents if name not in bound]

    @staticmethod
    def _is_assignment_target(parent, node) -> bool:
        if parent is None or _zero_arg(parent, 'kind') not in ('assignment', 'operator_assignment'):
            return False
        left = parent.child_by_field_name('left')
        return left is not None and _zero_arg(left, 'start_byte') == _zero_arg(node, 'start_byte')

    # ── Node naming (BACK-918/BACK-915) ─────────────────────────────────────
    def _name_via_ruby_special_name(self, kids) -> Optional[str]:
        # `def action_key=(val)` / `def [](k)` / `def ===(other)` — the name
        # is a distinct grammar node kind, not `identifier`: `setter` for
        # assignment-style methods (whose own text is already the full
        # "name=" form) and `operator` for operator-overload-style methods
        # (`[]`, `[]=`, `===`, `<=>`, `+`, ...; whose own text is already the
        # bare symbol). Found via the calls-recall-oracle Ruby measurement
        # (BACK-730, sixth language): setter/operator-named methods were
        # entirely absent from --outline/get_structure(), so every call made
        # FROM inside one had no caller name to attribute to, showing up as
        # residual missed edges in an otherwise ~99% recall run (real corpus
        # examples: WatchedWord#action_key=, TagGroup#parent_tag_name=,
        # Topic#title=, Onebox::Engine#===). Same invisibility class as
        # BACK-651 (C# operator_declaration) and BACK-724 (GDScript
        # constructor_definition) — a name-shaped child whose KIND, not an
        # identifier/name-kind child of it, carries the name.
        for child in kids:
            if _zero_arg(child, 'kind') in ('setter', 'operator'):
                return self._get_node_text(child)
        return None
