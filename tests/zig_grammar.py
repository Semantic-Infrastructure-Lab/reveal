"""Which Zig grammar the installed tree-sitter-language-pack ships (BACK-2540).

Pack 1.25 replaced the Zig grammar: the legacy one (pack <= 1.24, also the CI floor) is
fieldless and PascalCase (`Decl`, `FnProto`, `SuffixExpr`), 1.25's is fielded and snake_case
(`function_declaration`, `call_expression`). reveal reads both. A test whose answer is the
same on both grammars asserts it unconditionally; one that pins a grammar-specific detail (a
raw node kind in a record, a nesting count) states both values through `by_grammar`, so each
pack's run checks its own. Delete this module once the pack floor reaches 1.25.
"""

from tree_sitter_language_pack import get_language


def _zig_kinds() -> frozenset:
    lang = get_language('zig')
    return frozenset(lang.node_kind_for_id(i) for i in range(lang.node_kind_count))


LEGACY_ZIG_GRAMMAR: bool = 'FnProto' in _zig_kinds()


def by_grammar(legacy, current):
    """`legacy` on the pack <= 1.24 grammar, `current` on pack 1.25's."""
    return legacy if LEGACY_ZIG_GRAMMAR else current
