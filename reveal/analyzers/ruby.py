"""Ruby analyzer using tree-sitter."""

from typing import List, Optional

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

    def _callee_name_ruby_call(self, call_node) -> Optional[str]:
        # Ruby: obj.method() / Class.static_call() / self.foo() / foo() —
        # tree-sitter-ruby's 'call' node is the SAME node kind Python's
        # plain call() uses, but a structurally different shape: a flat
        # (receiver?, '.', method, argument_list?) sibling list, not a
        # nested func-expression child. child(0) is therefore the
        # *receiver* whenever one is present (BACK-734-shaped bug,
        # discovered pre-flight for the calls-recall-oracle Ruby measurement
        # via a direct grammar dump: `obj.baz` gave calls=["obj"], dropping
        # the actual method name entirely; `self.instance_call` gave
        # calls=["self"]; `Qux.static_call` gave calls=["Qux"]). Use the
        # named 'receiver'/'method' fields directly, same fix shape as
        # Java's method_invocation (BACK-734).
        #
        # `rs.reason = x` (a pure attribute WRITE) parses its LHS as this
        # SAME 'call' node shape (receiver=rs, method=reason) wrapped in an
        # 'assignment' node — tree-sitter-ruby has no distinct ATTRASGN-like
        # node the way Ruby's own AST does. Left un-guarded, a setter write
        # counted as a "call" to the bare attribute name showed up as
        # false-positive edges against the calls-recall-oracle Ruby
        # measurement (which, matching Ruby's own AST, excludes pure writes)
        # — real corpus examples: ColorScheme#... writing `skip_publish`,
        # UserOption#set_defaults writing `mailing_list_mode_frequency`.
        # `+=`/`||=` (`operator_assignment`) is NOT excluded here: it reads
        # the attribute before writing it, so it's a genuine call, matching
        # real Ruby semantics.
        parent = call_node.parent()
        if parent is not None and _zero_arg(parent, 'kind') == 'assignment':
            left = parent.child_by_field_name('left')
            if (left is not None
                    and _zero_arg(left, 'start_byte') == _zero_arg(call_node, 'start_byte')):
                return None
        method_node = call_node.child_by_field_name('method')
        if method_node is None:
            return None
        method_text = self._get_node_text(method_node)
        receiver_node = call_node.child_by_field_name('receiver')
        if receiver_node is None:
            return method_text
        return f"{self._get_node_text(receiver_node)}.{method_text}"
