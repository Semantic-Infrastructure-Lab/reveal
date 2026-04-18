"""Cyclomatic complexity and nesting depth metrics for AST nodes.

Standalone functions — no TreeSitterAnalyzer dependency — so the check/review
flow can import this without pulling the full analyzer base class into scope.
"""


def calculate_complexity_and_depth(node) -> tuple:
    """Compute cyclomatic complexity and max nesting depth in one iterative pass.

    Replaces separate recursive traversals with a single iterative stack walk,
    halving the node visits.

    Returns:
        (complexity, depth) where complexity = decision_count + 1
    """
    decision_types = {
        # Conditionals
        'if_statement', 'if_expression', 'if',
        'elif_clause', 'elsif',
        'else_if_clause',
        'case_statement', 'case',
        'when',
        'switch_case',
        'unless',
        # Loops
        'for_statement', 'for_expression', 'for',
        'while_statement', 'while',
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
        # Pattern matching
        'match_statement', 'case_clause',
    }

    nesting_types = {
        'if_statement', 'if_expression', 'if',
        'for_statement', 'for_expression', 'for', 'while_statement', 'while',
        'try_statement', 'try', 'with_statement', 'with',
        'match_statement', 'match_expression', 'case_statement',
        'do_statement', 'switch_statement',
    }

    # Keyword-container pairs not to double-count
    keyword_pairs = {
        ('if_statement', 'if'),
        ('if_expression', 'if'),
        ('elif_clause', 'elif'),
        ('for_statement', 'for'),
        ('for_expression', 'for'),
        ('while_statement', 'while'),
        ('case_statement', 'case'),
        ('boolean_operator', 'or'),
        ('boolean_operator', 'and'),
    }

    decision_count = 0
    max_depth = 0

    # Stack entries: (node, n_type, current_depth)
    stack = [(node, None, 0)]
    while stack:
        n, n_type, depth = stack.pop()
        if depth > max_depth:
            max_depth = depth
        for child in n.children:
            child_type = child.type
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
