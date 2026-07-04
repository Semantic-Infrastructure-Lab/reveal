"""Cyclomatic complexity and nesting depth metrics for AST nodes.

Standalone functions — no TreeSitterAnalyzer dependency — so the check/review
flow can import this without pulling the full analyzer base class into scope.
"""

from .core import node_children as _children


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
    'elif_clause', 'elsif', 'elseif_clause', 'else_if_clause',
    'case_statement', 'case',
    'when',
    'switch_case',
    'unless',
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
    # Exception handling
    'except_clause', 'catch_clause',
    'rescue',
    # Pattern matching — Python match_statement/case_clause and Rust
    # match_expression/match_arm (BACK-431).
    'match_statement', 'match_expression', 'case_clause', 'match_arm',
    # Zig `switch (x) { .a => ..., .b => ... }` (BACK-431 Issue G tier B).
    'SwitchProng',
    # Kotlin `when (x) { ... }`, Swift `switch x { case ... }`, and PHP
    # `switch ($x) { case ... }` — each arm/entry is its own decision, same
    # role as SwitchProng/match_arm (BACK-431 tier A real-corpus dogfood
    # audit).
    'when_entry', 'switch_entry', 'case_statement',
})

_NESTING_TYPES = frozenset({
    'if_statement', 'if_expression', 'if', 'IfStatement',
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
    ('elif_clause', 'elif'),
    ('for_statement', 'for'),
    ('for_expression', 'for'),
    ('for_in_statement', 'for'),
    ('enhanced_for_statement', 'for'),
    ('while_statement', 'while'),
    ('while_expression', 'while'),
    ('case_statement', 'case'),
    ('boolean_operator', 'or'),
    ('boolean_operator', 'and'),
})


def calculate_complexity_and_depth(node) -> tuple:
    """Compute cyclomatic complexity and max nesting depth in one iterative pass.

    Replaces separate recursive traversals with a single iterative stack walk,
    halving the node visits.

    Returns:
        (complexity, depth) where complexity = decision_count + 1
    """
    decision_types = _DECISION_TYPES
    nesting_types = _NESTING_TYPES
    keyword_pairs = _KEYWORD_PAIRS

    decision_count = 0
    max_depth = 0

    # Stack entries: (node, n_type, current_depth)
    stack = [(node, None, 0)]
    while stack:
        n, n_type, depth = stack.pop()
        if depth > max_depth:
            max_depth = depth
        for child in _children(n):
            child_type = child.kind()
            if child_type in decision_types and (n_type is None or (n_type, child_type) not in keyword_pairs):
                decision_count += 1
            child_depth = depth + 1 if child_type in nesting_types else depth
            stack.append((child, child_type, child_depth))

    return decision_count + 1, max_depth


def calculate_complexity(node) -> int:
    """Return cyclomatic complexity for a function node."""
    if not node:
        return 1
    complexity, _ = calculate_complexity_and_depth(node)
    return int(complexity)


def get_nesting_depth(node) -> int:
    """Return maximum nesting depth within a function node."""
    if not node:
        return 0
    _, depth = calculate_complexity_and_depth(node)
    return int(depth)
