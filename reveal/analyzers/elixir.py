"""Elixir file analyzer.

Elixir has no dedicated ``function_definition``/``class_definition`` grammar
nodes the way Python or Java do — *everything* is a macro call. ``defmodule``,
``def``, ``defp``, ``defmacro``, ``defguard``, ``defdelegate`` all parse as a
``call`` node whose first child is an ``identifier`` naming the macro. The base
:class:`TreeSitterAnalyzer` dispatch keys off distinct node kinds, so out of the
box it extracted zero functions/modules on real Elixir — byte/line count only
(BACK-480). This analyzer teaches it Elixir's call-shaped definitions.
"""

from typing import Any, Dict, List, Optional

from ..core import node_children as _children
from ..registry import register
from ..treesitter import TreeSitterAnalyzer

# Macro calls that define a callable. Module-shaped macros are handled
# separately (they map to a "class", not a function).
_ELIXIR_DEF_KEYWORDS = frozenset({
    'def', 'defp', 'defmacro', 'defmacrop',
    'defguard', 'defguardp', 'defdelegate', 'defn',
})

# Module-shaped macros whose name is an ``alias`` (e.g. ``Foo.Bar``). ``defimpl``
# is intentionally excluded — its target is a ``for:``-qualified pair, not a
# single alias, so it needs a different name shape than defmodule/defprotocol.
_ELIXIR_MODULE_KEYWORDS = frozenset({'defmodule', 'defprotocol'})


@register('.ex', name='Elixir', icon='')
@register('.exs', name='Elixir Script', icon='')
class ElixirAnalyzer(TreeSitterAnalyzer):
    """Elixir file analyzer (BACK-480).

    Elixir definitions are ``call`` nodes (``def add(a, b) do … end`` parses as
    a call to the ``def`` macro), so function/module extraction is overridden to
    match on the leading macro keyword and read the defined name out of the
    call's ``arguments`` subtree. Modules (``defmodule``) surface as classes;
    ``def``/``defp``/``defmacro``/``defguard``/``defdelegate`` as functions.

    The elixir tree-sitter grammar is bundled via tree-sitter-language-pack; no
    separate ``pip install tree-sitter-elixir`` is needed or correct.
    """
    language = 'elixir'

    def get_structure(self, head=None, tail=None, range=None, **kwargs) -> Dict[str, Any]:
        """Extract Elixir code structure with output contract fields."""
        structure = super().get_structure(head=head, tail=tail, range=range, **kwargs)
        return {
            'contract_version': '1.0',
            'type': 'elixir_structure',
            'source': str(self.path),
            'source_type': 'file',
            **structure,
        }

    # --- Elixir-specific call-shaped definition extraction ---------------

    def _extract_functions(self) -> List[Dict[str, Any]]:
        """Extract def/defp/defmacro/defguard/defdelegate definitions.

        Each is a ``call`` whose first child is an ``identifier`` naming the
        defining macro; the function name lives in the call's ``arguments``.
        The whole ``call`` node is used as the function node so line span,
        complexity, and calls cover the full ``def … end`` (or ``def …, do:``)
        body.
        """
        functions: List[Dict[str, Any]] = []
        seen = set()  # (line, name) — a def can appear once per clause; dedup identical head+line
        for node in self._find_nodes_by_type('call'):
            keyword = self._elixir_call_keyword(node)
            if keyword not in _ELIXIR_DEF_KEYWORDS:
                continue
            name = self._elixir_definition_name(node)
            if not name:
                continue
            key = (node.start_position().row + 1, name)
            if key in seen:
                continue
            seen.add(key)
            functions.append(self._build_function_dict(node=node, name=name, decorators=[]))
        return functions

    def _extract_classes(self) -> List[Dict[str, Any]]:
        """Extract ``defmodule`` definitions as classes (Elixir's module unit)."""
        classes: List[Dict[str, Any]] = []
        seen = set()
        for node in self._find_nodes_by_type('call'):
            if self._elixir_call_keyword(node) not in _ELIXIR_MODULE_KEYWORDS:
                continue
            name = self._elixir_definition_name(node)
            if not name:
                continue
            key = (node.start_position().row + 1, name)
            if key in seen:
                continue
            seen.add(key)
            classes.append(self._build_class_dict(node=node, name=name, decorators=[]))
        return classes

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Resolve ``reveal file.ex <name>`` to a def/defmodule call.

        The base lookup keys off ``ELEMENT_TYPE_MAP`` node kinds, which never
        match Elixir's call-shaped definitions — so without this override
        ``reveal file.ex handle_call`` failed for a function ``--outline`` had
        just listed. Returns the first clause matching ``name`` (Elixir
        multi-clause defs share a name, like overloads in other languages).
        """
        if self.tree:
            for node in self._find_nodes_by_type('call'):
                keyword = self._elixir_call_keyword(node)
                if keyword not in _ELIXIR_DEF_KEYWORDS and keyword not in _ELIXIR_MODULE_KEYWORDS:
                    continue
                if self._elixir_definition_name(node) != name:
                    continue
                end_node = self._function_end_node(node)
                source = (
                    self._get_node_text(node) if end_node is node
                    else self._get_text_span(node.start_byte(), end_node.end_byte())
                )
                return {
                    'name': name,
                    'line_start': node.start_position().row + 1,
                    'line_end': end_node.end_position().row + 1,
                    'source': source,
                }
        return super().extract_element(element_type, name)

    def _elixir_call_keyword(self, call_node) -> Optional[str]:
        """The leading macro name of a ``call`` node (``def``, ``defmodule``, …),
        or None if the call doesn't start with a bare identifier."""
        kids = _children(call_node)
        if kids and kids[0].kind() == 'identifier':
            return self._get_node_text(kids[0])
        return None

    def _elixir_definition_name(self, call_node) -> Optional[str]:
        """Read the defined name out of a def/defmodule call's ``arguments``.

        Handles the shapes Elixir produces:
          * ``defmodule Foo.Bar do``      → ``arguments`` holds an ``alias``.
          * ``def zero_arg do``           → an ``identifier`` (no parens).
          * ``def f(a, b)`` / ``defdelegate other(x)`` → a ``call`` whose first
            ``identifier`` child is the name.
          * ``def f(x) when guard`` / ``defguard g(n) when …`` → a ``when``
            ``binary_operator`` whose left operand is one of the above.
        """
        args = next((c for c in _children(call_node) if c.kind() == 'arguments'), None)
        if args is None:
            return None
        target = next(iter(_children(args)), None)
        if target is None:
            return None
        # Unwrap a `head when guard` clause to its left (the head).
        if target.kind() == 'binary_operator':
            left = next(iter(_children(target)), None)
            if left is not None:
                target = left
        if target.kind() == 'alias':          # module name (Foo.Bar)
            return self._get_node_text(target)
        if target.kind() == 'identifier':     # zero-arg def
            return self._get_node_text(target)
        if target.kind() == 'call':           # name(args...)
            head = next((c for c in _children(target) if c.kind() == 'identifier'), None)
            if head is not None:
                return self._get_node_text(head)
        return None
