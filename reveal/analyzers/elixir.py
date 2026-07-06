"""Elixir file analyzer."""

from typing import Any, Dict

from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.ex', name='Elixir', icon='')
@register('.exs', name='Elixir Script', icon='')
class ElixirAnalyzer(TreeSitterAnalyzer):
    """Elixir file analyzer.

    KNOWN BROKEN (BACK-480): this is a bare TreeSitterAnalyzer subclass with
    no Elixir-specific node taxonomy. Elixir's `defmodule`/`def` are macro-call
    shapes, not distinct node kinds like Python's `function_definition`, so the
    generic dispatch extracts zero functions/modules on real code — byte/line
    count only. Matches `reveal --languages` marking Elixir `[untested]`.
    See reveal/docs/development/ELIXIR_ANALYZER_GUIDE.md.

    The elixir tree-sitter grammar is bundled via tree-sitter-language-pack;
    no separate `pip install tree-sitter-elixir` is needed or correct.
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
