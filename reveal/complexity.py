"""Cyclomatic complexity and nesting depth metrics for AST nodes.

Standalone functions — no TreeSitterAnalyzer dependency — so the check/review
flow can import this without pulling the full analyzer base class into scope.
"""

from .core import node_children as _children
from .core.treesitter_compat import _zero_arg


# Cyclomatic-complexity taxonomy. This is a SEPARATE concern from the nav
# control-flow taxonomy (reveal/adapters/ast/node_taxonomy.py): complexity also
# counts boolean operators, ternaries, and language-specific conditionals
# (Ruby unless/until/when, elsif) that never open a nav scope, and it treats an
# infinite `loop` as nesting-but-not-a-decision. So it can't just import the nav
# composites wholesale. But the control-flow kinds it DOES share (if/while/for/
# match/case families) must stay in step with node_taxonomy or they drift
# exactly the way BACK-427/430 did — Rust while/loop/match and Java/JS for-each
# were all missing here. The tie is enforced by
# tests/adapters/test_node_taxonomy.py::TestComplexityCoversFamilies, which
# fails if node_taxonomy grows a loop/conditional/match kind this file omits.
_DECISION_TYPES = frozenset({
    # Conditionals
    'if_statement', 'if_expression', 'if', 'IfStatement',
    'elif_clause', 'elsif', 'elseif_clause', 'else_if_clause', 'elseif_statement',  # lua
    'case_statement',
    # Bare `case` is NOT a decision kind: JS/Python arms wrap a `case` keyword
    # token (double-count), and Ruby's `case` container is not a branch --
    # its `when` arms are (BACK-1289).
    'when',
    'switch_case',
    'unless',
    # Ruby statement modifiers (`x if cond`, `x unless cond`) are branches — each
    # adds a decision — but they wrap a single statement and do NOT nest (see
    # _NESTING_TYPES). Counting them fixes prior under-counting of guard-clause
    # Ruby (BACK-500).
    'if_modifier', 'unless_modifier',
    # Loops (each iteration is a branch). for-each variants share this role:
    # C#/PHP foreach_statement, JS/TS for_in_statement, Java
    # enhanced_for_statement, Rust for_expression (BACK-431).
    'for_statement', 'for_expression', 'for',
    'foreach_statement', 'for_in_statement', 'enhanced_for_statement',
    'while_statement', 'while_expression', 'while',
    'until',
    'do_statement',
    # Boolean operators
    'boolean_operator',
    'and', 'or',
    'logical_and', 'logical_or',
    # Ternary
    'conditional_expression', 'ternary_expression',
    'conditional',  # ruby `a ? b : c`
    'IfExpr',  # zig `const x = if (c) a else b` (statements: IfStatement)
    # Exception handling
    'except_clause', 'catch_clause', 'catch_block',  # kotlin
    'rescue',
    # Pattern matching — Python match_statement/case_clause and Rust
    # match_expression/match_arm (BACK-431).
    # Match arms are the decisions, not the container (see _NOT_DECISION_CONTAINERS).
    # GDScript arms are `pattern_section`.
    'case_clause', 'match_arm', 'pattern_section',
    # Zig `switch (x) { .a => ..., .b => ... }` (BACK-431 Issue G tier B).
    'SwitchProng',
    # Kotlin `when (x) { ... }`, Swift `switch x { case ... }`, and PHP
    # `switch ($x) { case ... }` — each arm/entry is its own decision, same
    # role as SwitchProng/match_arm (BACK-431 tier A real-corpus dogfood
    # audit).
    'when_entry', 'switch_entry', 'case_statement', 'guard_statement',  # swift guard
    # C# / Dart switch-EXPRESSION arms (BACK-1301); the default arm is excluded
    # by `is_decision`, like every other language's default.
    'switch_expression_arm', 'switch_expression_case',
    # Go switch / type-switch / select arms (BACK-1298); `default_case` excluded.
    'expression_case', 'type_case', 'communication_case',
})

# Match containers are nesting (see _NESTING_TYPES) but NOT decisions: their arms
# are. Counting both scored a 3-arm Python/Rust match 5, not 4. Kept as a named set
# so tests/adapters/test_node_taxonomy.py can subtract exactly these from the
# "every match kind is a decision" drift guard instead of weakening it.
_NOT_DECISION_CONTAINERS = frozenset({'match_statement', 'match_expression'})

# Java/C#/Dart have no dedicated arm node that is also a decision kind: their
# `case` arms exist only as a bare `case` keyword token under one of these
# parents (`default` is a different token kind, so it stays uncounted). Bare
# `case` is otherwise NOT a decision (BACK-1289: it double-counted JS/Python
# arms and Ruby's container), so count it only in these contexts. Removing it
# outright made a 2-case Java/C#/Dart switch score 1 -- found by the corpus
# complexity sweep, not by unit tests.
_CASE_TOKEN_PARENTS = frozenset({'switch_label', 'switch_section', 'case_builtin'})

# Short-circuit / null-coalescing / early-exit operators (BACK-1316, BACK-1325). Unlike
# Python's `and`/`or` (dedicated node kinds, in _DECISION_TYPES), most grammars expose
# these only as an anonymous operator TOKEN under some node, and the same token also
# appears where it is NOT a decision (C++ `int&& x` / `auto&& y` are rvalue-reference
# declarators; `||=`/`&&=`/`??=` are distinct tokens, uncounted like radon/lizard;
# `try` / `catch` are keywords under their own statement nodes almost everywhere).
# So each token counts only under the parents listed for it. An allow-list, not a
# deny-list: an unlisted grammar undercounts (visible in the per-construct probe
# table) instead of silently overcounting. Add a language's parent kind here plus a
# row in tests/test_complexity_constructs.py.
_LOGICAL_PARENTS = frozenset({
    'binary_expression',                              # js ts go java c cpp cs rs php
    'binary',                                         # ruby
    'conjunction_expression', 'disjunction_expression',  # kotlin swift
    'elvis_expression',                               # kotlin `?:`
    'logical_and_operator', 'logical_or_operator',    # dart
    'if_null_expression',                             # dart `??`
    'nil_coalescing_expression',                      # swift `??`
})
_OPERATOR_TOKEN_PARENTS = {
    '&&': _LOGICAL_PARENTS, '||': _LOGICAL_PARENTS,
    '??': _LOGICAL_PARENTS, '?:': _LOGICAL_PARENTS,
    # Zig `a orelse b` / `a catch b` are `BitwiseOp` tokens.
    'orelse': frozenset({'BitwiseOp'}), 'catch': frozenset({'BitwiseOp'}),
    # Explicit early-exit-on-failure sites: Zig `try x` is a `try` token under `PrefixOp`;
    # Rust `x?` is a `?` token under `try_expression`. The node KIND `try_expression` is
    # not usable -- Kotlin/Swift/Scala use it for a plain try block / `try` keyword, which
    # do not branch here -- so it is the token under it that counts.
    'try': frozenset({'PrefixOp'}), '?': frozenset({'try_expression'}),
}

# Arm kinds that may be the language's `default` arm, which never counts as a
# decision. Marker = the arm's first child: Kotlin `else`, Swift
# `default_keyword`, C# `_` (`discard`). Dart's `_` is a constant_pattern
# wrapping a lone `identifier`, indistinguishable from a constant name without
# source text (the walkers have none), so a lone-identifier pattern is treated
# as the catch-all -- a deliberate +/-1 approximation on Dart switch
# expressions that match a named constant (BACK-1301).
_DEFAULT_CAPABLE_ARMS = frozenset({
    'SwitchProng', 'case_statement', 'case_clause', 'match_arm', 'pattern_section', 'when_entry', 'switch_entry', 'switch_expression_arm', 'switch_expression_case'})
_DEFAULT_ARM_MARKERS = frozenset({'else', 'default_keyword', 'discard', 'default', '_', 'wildcard'})


# Wrapper nodes whose first child is the arm's real pattern: Zig `SwitchCase`, Python
# `case_pattern`, Rust `match_pattern`. Look through them for the catch-all marker.
_ARM_PATTERN_WRAPPERS = frozenset({'SwitchCase', 'case_pattern', 'match_pattern'})


def _is_default_arm(arm) -> bool:
    """True when `arm` is the catch-all arm (`default`, `else`, or a `_` wildcard).

    Policy (BACK-1318): a catch-all arm never counts, in any language -- Python
    `case _`, Rust `_ =>`, Scala `case _` as well as C `default:` / Kotlin `else`.
    """
    for first in _children(arm):
        kind = _zero_arg(first, 'kind')
        if kind == 'case':  # keyword token ahead of the pattern (Python, Scala, C)
            continue
        if kind in _ARM_PATTERN_WRAPPERS:
            return _is_default_arm(first)
        if kind in _DEFAULT_ARM_MARKERS:
            return True
        if kind == 'constant_pattern':
            inner = _children(first)
            return len(inner) == 1 and _zero_arg(inner[0], 'kind') == 'identifier'
        # GDScript `_:` is a lone `identifier`, indistinguishable from a named
        # binding (also irrefutable) without source text: same +/-1 approximation
        # as Dart's constant_pattern above.
        return kind == 'identifier' and _zero_arg(arm, 'kind') == 'pattern_section'
    return False


_NESTING_TYPES = frozenset({
    'if_statement', 'if_expression', 'if', 'IfStatement',
    'unless',  # Ruby block `unless … end` nests; the modifiers (MODIFIER_NODES) do not
    'for_statement', 'for_expression', 'for',
    'foreach_statement', 'for_in_statement', 'enhanced_for_statement',
    'while_statement', 'while_expression', 'while',
    'loop_expression',
    'try_statement', 'try', 'with_statement', 'with',
    'match_statement', 'match_expression', 'case_statement',
    'do_statement', 'switch_statement',
})

# Keyword-container pairs not to double-count (a construct node plus the bare
# keyword token it contains, when both appear in _DECISION_TYPES).
_KEYWORD_PAIRS = frozenset({
    ('if_statement', 'if'),
    ('if_expression', 'if'),
    # Python `a if c else b`: the wrapper contains a bare `if` token, a decision
    # kind -- without the pair every ternary counted twice.
    ('conditional_expression', 'if'),
    ('elif_clause', 'elif'),
    ('for_statement', 'for'),
    ('for_expression', 'for'),
    ('for_in_statement', 'for'),
    ('enhanced_for_statement', 'for'),
    ('while_statement', 'while'),
    ('while_expression', 'while'),
    ('case_statement', 'case'),
    # Ruby: each conditional wrapper contains a bare keyword token of a kind that
    # is itself a decision type — dedup so the pair counts once (BACK-500).
    ('if_modifier', 'if'),
    ('unless_modifier', 'unless'),
    ('unless', 'unless'),
    # tree-sitter-ruby names a statement node and its bare keyword token
    # identically ('while' > 'while'), so the container/keyword pair above has
    # to be spelled same-kind for each Ruby construct (BACK-1284). Without
    # these every Ruby decision point counted twice.
    ('if', 'if'),
    ('elsif', 'elsif'),
    ('while', 'while'),
    ('until', 'until'),
    ('for', 'for'),
    ('when', 'when'),
    ('rescue', 'rescue'),
    ('boolean_operator', 'or'),
    ('boolean_operator', 'and'),
    # Kotlin: `when_expression` wraps a bare `when` keyword token (BACK-1301).
    ('when_expression', 'when'),
    # C `do { } while (c)`: the statement wraps a bare `while` keyword token.
    ('do_statement', 'while'),
    # Zig: `IfStatement`/`IfExpr` wrap an `IfPrefix` that holds the bare `if` token.
    ('IfPrefix', 'if'),
})


_SCALA_LOGICAL_OPERATORS = frozenset({'&&', '||'})


def _has_child_kind(node, kind) -> bool:
    return any(_zero_arg(c, 'kind') == kind for c in _children(node))


def is_decision(kind: str, parent_kind, node=None, node_text=None) -> bool:
    """True if `node` (of `kind`, under `parent_kind`) adds one decision point.

    `node` is only needed to recognise a catch-all arm; omit it and default-
    capable arm kinds count unconditionally. `node_text(node) -> str` is only
    needed for Scala infix `&&`/`||` (an `operator_identifier` shared with `+`);
    omit it and those undercount rather than guess.

    The single decision rule shared by `calculate_complexity_and_depth` and
    treesitter's merged `_complexity_depth_and_calls` walk (BACK-1303) --
    edit the rule here, never in a walker.
    """
    if kind == 'operator_identifier':  # Scala infix operator
        return (parent_kind == 'infix_expression' and node_text is not None
                and node_text(node) in _SCALA_LOGICAL_OPERATORS)
    if kind == 'catch_clause' and node is not None and _has_child_kind(node, 'case_block'):
        return False  # Scala: `catch { case ... }` -- the case arms carry the count
    if kind in _DECISION_TYPES:
        if parent_kind is not None and (parent_kind, kind) in _KEYWORD_PAIRS:
            return False
        return not (node is not None and kind in _DEFAULT_CAPABLE_ARMS and _is_default_arm(node))
    parents = _OPERATOR_TOKEN_PARENTS.get(kind)
    if parents is not None:
        return parent_kind in parents
    return kind == 'case' and parent_kind in _CASE_TOKEN_PARENTS


def calculate_complexity_and_depth(node, is_opaque=None, node_text=None) -> tuple:
    """Compute cyclomatic complexity and max nesting depth in one iterative pass.

    Replaces separate recursive traversals with a single iterative stack walk,
    halving the node visits.

    `is_opaque(child)` marks a descendant that has its own entry elsewhere (a nested
    function): it is not entered, so its decisions do not also inflate the enclosing
    function. treesitter's walker does this via FUNCTION_NODE_TYPES (BACK-490);
    analyzers with a bespoke function builder (Zig) pass their own predicate.
    `node_text` is forwarded to `is_decision`.

    Returns:
        (complexity, depth) where complexity = decision_count + 1
    """
    nesting_types = _NESTING_TYPES

    decision_count = 0
    max_depth = 0

    # Stack entries: (node, n_type, current_depth)
    stack = [(node, None, 0)]
    while stack:
        n, n_type, depth = stack.pop()
        if depth > max_depth:
            max_depth = depth
        for child in _children(n):
            if is_opaque is not None and is_opaque(child):
                continue
            child_type = _zero_arg(child, 'kind')
            if is_decision(child_type, n_type, child, node_text):
                decision_count += 1
            child_depth = depth + 1 if child_type in nesting_types else depth
            stack.append((child, child_type, child_depth))

    return decision_count + 1, max_depth


def calculate_complexity(node, is_opaque=None, node_text=None) -> int:
    """Return cyclomatic complexity for a function node."""
    if not node:
        return 1
    complexity, _ = calculate_complexity_and_depth(node, is_opaque, node_text)
    return int(complexity)


def get_nesting_depth(node) -> int:
    """Return maximum nesting depth within a function node."""
    if not node:
        return 0
    _, depth = calculate_complexity_and_depth(node)
    return int(depth)
