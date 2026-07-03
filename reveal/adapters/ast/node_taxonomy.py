"""Single source of truth for cross-language control-flow node-kind taxonomy.

BACK-427/430/431 root cause: this knowledge — "which tree-sitter node kinds
represent an if/while/for/match/return/etc. across every supported grammar"
— was independently hand-declared in nav_outline.py, nav_varflow.py, and
nav_exits.py, despite treesitter.py already claiming to be the "single
source of truth." Each copy drifted on its own: a language's grammar naming
choice (Python's `if_statement` vs Rust's expression-oriented
`if_expression` vs PHP's bare `if`) got added to whichever module the bug
report happened to be about, never all three. BACK-427 fixed `if_expression`
in nav_outline.py and nav_varflow.py but never nav_exits.py; BACK-430 found
that gap three sessions later.

The fix: group node kinds into per-construct families below. A language's
missing node-kind variant is added to exactly one family, and every consumer
(SCOPE_NODES / GATE_NODES / EXIT_NODES / IF_WHILE_NODES) picks it up
automatically because they're built by union, not re-declared.
"""

from __future__ import annotations

from typing import Dict


# ---------------------------------------------------------------------------
# Per-construct families
# ---------------------------------------------------------------------------

IF_NODES: frozenset = frozenset({'if_statement', 'if_expression', 'if'})
ELIF_NODES: frozenset = frozenset({'elif_clause', 'elseif_clause'})
ELSE_NODES: frozenset = frozenset({'else_clause', 'else'})
WHILE_NODES: frozenset = frozenset({'while_statement', 'while_expression', 'while'})
# Loop constructs that share the C-style 'left'/'right' field shape in
# nav_varflow (loop var = 'left', iterable = 'right'): plain for, C#/PHP
# `foreach`, and JS/TS `for…of` / `for…in` (`for_in_statement`). BACK-431:
# `for_in_statement` was absent from the family entirely, making JS/TS
# for-each loops invisible to --outline/--ifmap/--varflow (confirmed live).
FOR_NODES: frozenset = frozenset({
    'for_statement', 'foreach_statement', 'for_in_statement', 'for',
})
# Rust `for x in y { }` — 'pattern'/'value' fields, not 'left'/'right' (BACK-430).
FOR_EXPRESSION_NODES: frozenset = frozenset({'for_expression'})
# Java `for (T x : items)` — 'name'/'value' fields (its own shape); was also
# absent from the taxonomy (BACK-431), so Java enhanced-for loops were
# invisible to --outline/--varflow the same way JS/TS for-each were.
FOR_EACH_NAME_VALUE_NODES: frozenset = frozenset({'enhanced_for_statement'})
# Rust `loop { }` — no condition field at all.
LOOP_NODES: frozenset = frozenset({'loop_expression'})
DO_NODES: frozenset = frozenset({'do_statement'})
TRY_NODES: frozenset = frozenset({'try_statement', 'try'})
EXCEPT_NODES: frozenset = frozenset({'except_clause'})
FINALLY_NODES: frozenset = frozenset({'finally_clause', 'finally'})
CATCH_NODES: frozenset = frozenset({'catch_clause', 'catch'})
WITH_NODES: frozenset = frozenset({'with_statement', 'with'})
# Rust `match x { }` — 'value'/'body' fields. Python's `match_statement` uses
# a *different* field name ('subject', not 'value') for its scrutinee, so it
# is kept out of this family — nav_varflow.py's dispatch only knows the Rust
# field shape; MATCH_NODES (below) is the membership-only union used where
# field names don't matter (nav_outline.py/nav_exits.py structural walking).
MATCH_EXPRESSION_NODES: frozenset = frozenset({'match_expression'})
MATCH_NODES: frozenset = MATCH_EXPRESSION_NODES | frozenset({'match_statement'})
CASE_NODES: frozenset = frozenset({'case_clause', 'match_arm', 'switch_case'})
SWITCH_NODES: frozenset = frozenset({'switch_statement', 'switch'})
SWITCH_DEFAULT_NODES: frozenset = frozenset({'switch_default', 'default'})

DEF_NODES: frozenset = frozenset({
    'function_definition', 'function_declaration', 'function_item',
    'method_definition', 'method_declaration', 'function', 'arrow_function',
})
CLASS_NODES: frozenset = frozenset({'class_definition', 'class_declaration', 'class'})
LAMBDA_NODES: frozenset = frozenset({'lambda'})

RETURN_NODES: frozenset = frozenset({'return_statement', 'return'})
RAISE_NODES: frozenset = frozenset({'raise_statement', 'raise'})
THROW_NODES: frozenset = frozenset({'throw_statement'})
YIELD_NODES: frozenset = frozenset({'yield_statement', 'yield'})
# BACK-431: bare 'break'/'continue' were already recognized by nav_exits.py's
# hand-written _EXIT_KIND but missing from nav_outline.py's EXIT_NODES — a
# real drift instance found while consolidating (a grammar that emits bare
# `break`/`continue` keyword nodes was invisible to --outline while already
# working in --exits/--returns).
BREAK_NODES: frozenset = frozenset({'break_statement', 'break'})
CONTINUE_NODES: frozenset = frozenset({'continue_statement', 'continue'})


# ---------------------------------------------------------------------------
# Composite sets — what each consumer actually queries against
# ---------------------------------------------------------------------------

FUNCTION_TYPES: frozenset = DEF_NODES | CLASS_NODES | LAMBDA_NODES

EXIT_NODES: frozenset = (
    RETURN_NODES | RAISE_NODES | THROW_NODES | YIELD_NODES
    | BREAK_NODES | CONTINUE_NODES
)

ALTERNATIVE_NODES: frozenset = (
    ELIF_NODES | ELSE_NODES | EXCEPT_NODES | FINALLY_NODES | CATCH_NODES
    | SWITCH_DEFAULT_NODES
)

# nav_outline.py: every construct that opens a nested scope worth descending into.
SCOPE_NODES: frozenset = (
    IF_NODES | ELIF_NODES | ELSE_NODES | WHILE_NODES | FOR_NODES
    | FOR_EXPRESSION_NODES | FOR_EACH_NAME_VALUE_NODES | LOOP_NODES | DO_NODES
    | TRY_NODES | EXCEPT_NODES | FINALLY_NODES | CATCH_NODES | WITH_NODES
    | MATCH_NODES | CASE_NODES | SWITCH_NODES
)

# nav_exits.py: constructs whose body is entered conditionally — used to
# build return/exit gate chains (collect_gate_chains). for_expression/
# loop_expression/match_expression have no 'condition' field (confirmed via
# direct tree-sitter inspection, BACK-430), so _get_condition() returns None
# for them and they don't push a gate onto the chain — included anyway so a
# return nested inside one is still walked, not skipped outright.
GATE_NODES: frozenset = (
    IF_NODES | ELIF_NODES | WHILE_NODES | FOR_NODES | FOR_EXPRESSION_NODES
    | FOR_EACH_NAME_VALUE_NODES | LOOP_NODES | DO_NODES | MATCH_NODES | WITH_NODES
)

# nav_varflow.py: if/elif/while share the same 'condition'/'body' field
# shape (_walk_if_while) — for/for_expression/match have their own shapes
# (different field names) and are handled by dedicated dispatch branches.
IF_WHILE_NODES: frozenset = IF_NODES | ELIF_NODES | WHILE_NODES


KEYWORD_LABEL: Dict[str, str] = {
    'if_statement': 'IF', 'if': 'IF', 'if_expression': 'IF',
    'elif_clause': 'ELIF', 'elseif_clause': 'ELIF',
    'else_clause': 'ELSE', 'else': 'ELSE',
    'for_statement': 'FOR', 'for': 'FOR', 'for_expression': 'FOR',
    'foreach_statement': 'FOR', 'for_in_statement': 'FOR',
    'enhanced_for_statement': 'FOR',
    'while_statement': 'WHILE', 'while': 'WHILE', 'while_expression': 'WHILE',
    'loop_expression': 'LOOP',
    'try_statement': 'TRY', 'try': 'TRY',
    'except_clause': 'EXCEPT',
    'finally_clause': 'FINALLY', 'finally': 'FINALLY',
    'with_statement': 'WITH', 'with': 'WITH',
    'match_statement': 'MATCH', 'match_expression': 'MATCH',
    'case_clause': 'CASE', 'match_arm': 'CASE',
    'do_statement': 'DO',
    'switch_statement': 'SWITCH', 'switch': 'SWITCH',
    'catch_clause': 'CATCH', 'catch': 'CATCH',
    'switch_case': 'CASE',
    'switch_default': 'DEFAULT', 'default': 'DEFAULT',
    'function_definition': 'DEF', 'function_declaration': 'DEF',
    'function_item': 'DEF', 'function': 'DEF',
    'method_definition': 'DEF', 'method_declaration': 'DEF',
    'arrow_function': 'DEF',
    'lambda': 'LAMBDA',
    'class_definition': 'CLASS', 'class_declaration': 'CLASS', 'class': 'CLASS',
    'return_statement': 'RETURN', 'return': 'RETURN',
    'raise_statement': 'RAISE', 'raise': 'RAISE',
    'throw_statement': 'THROW',
    'yield_statement': 'YIELD', 'yield': 'YIELD',
    'break_statement': 'BREAK', 'break': 'BREAK',
    'continue_statement': 'CONTINUE', 'continue': 'CONTINUE',
}


# ---------------------------------------------------------------------------
# Guard rail: catch a family/composite drifting out of sync with KEYWORD_LABEL
# or with each other at import time, not at whatever call site happens to hit
# the gap first — see tests/test_node_taxonomy.py for the full cross-check.
# ---------------------------------------------------------------------------

_ALL_LABELED_KINDS: frozenset = frozenset(KEYWORD_LABEL)
assert (SCOPE_NODES | EXIT_NODES | FUNCTION_TYPES) <= _ALL_LABELED_KINDS, (
    'node_taxonomy: a composite set contains a node kind with no KEYWORD_LABEL entry'
)
