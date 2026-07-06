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

IF_NODES: frozenset = frozenset({'if_statement', 'if_expression', 'if', 'IfStatement'})
ELIF_NODES: frozenset = frozenset({'elif_clause', 'elseif_clause'})
ELSE_NODES: frozenset = frozenset({'else_clause', 'else'})
# Zig's IfStatement (BACK-431 Issue G smoke-tier audit) has no AST fields at
# all — unlike every other IF_NODES member, `_walk_if_while`'s
# 'condition'/'body' field lookup silently no-ops for it, so it's kept out
# of nav_varflow's IF_WHILE_NODES; it still counts for --outline/--ifmap
# (SCOPE_NODES/KEYWORD_LABEL), which only match on node kind.
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
# C++ `for (T x : items)` — 'declarator'/'right' fields (its own shape,
# distinct from Java's enhanced_for_statement above). Found via the BACK-439b/c
# conformance-matrix cross-language pass: the existing Tier 1 C++ fixture had
# no range-based for loop, so this was never exercised — --outline/--ifmap/
# --loopmap were silently blind to it. --varflow dispatch (declarator=WRITE,
# right=READ) is a follow-on, not fixed by this taxonomy addition alone; see
# BACK-450.
FOR_RANGE_LOOP_NODES: frozenset = frozenset({'for_range_loop'})
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
# Zig's `switch (x) { .a => ..., .b => ... }` (BACK-431 Issue G tier B
# dogfood audit: found via real Ghostty source, terminal/formatter.zig uses
# switch pervasively) — `SwitchExpr`/`SwitchProng`, distinct kinds from
# every other language's switch/case shape. Kotlin's `when (x) { ... }`
# (BACK-431 tier A real-corpus dogfood audit: found via real tivi source,
# SeasonsEpisodesRepository.kt's markSeasonWatched) is the same
# fully-fieldless shape as Zig's switch — `when_expression`/`when_entry`.
# Swift's `switch x { case ... }` node itself (`switch_statement`) was
# already covered, but its case-arm node (`switch_entry`, wrapping both
# `case`-pattern and `default` arms) was not — every switch case in real
# Swift source (Kickstarter's AppDelegateViewModel.navigation(fromPushEnvelope:))
# was invisible to --ifmap/--outline (BACK-431 tier A real-corpus dogfood audit).
# PHP's switch (`switch_statement`, already covered) uses `case_statement`/
# `default_statement` for its arms — distinct names from every other
# language's shape, and from the (apparently never-verified) 'switch_case'/
# 'switch_default' placeholders already in these sets. Found via real
# WordPress source (wp-includes/post.php's wp_attachment_is) where the
# entire switch body — all 4 cases — was invisible to --ifmap despite
# --exits correctly finding the returns inside them (structural walking
# doesn't need the CASE label; --ifmap does).
CASE_NODES: frozenset = frozenset({
    'case_clause', 'match_arm', 'switch_case', 'SwitchProng', 'when_entry',
    'switch_entry', 'case_statement',
})
SWITCH_NODES: frozenset = frozenset({
    'switch_statement', 'switch', 'SwitchExpr', 'when_expression',
})
SWITCH_DEFAULT_NODES: frozenset = frozenset({
    'switch_default', 'default', 'default_statement',
})

DEF_NODES: frozenset = frozenset({
    'function_definition', 'function_declaration', 'function_item',
    'method_definition', 'method_declaration', 'function', 'arrow_function',
    # BACK-462: treesitter.py's FUNCTION_NODE_TYPES (element-extraction taxonomy)
    # and this set (control-flow/scope taxonomy) independently diverged after
    # Issue A's control-flow consolidation. 'method' (Ruby), 'function_signature'
    # (Dart), 'Decl' (Zig) were present there but missing here, so --scope
    # silently dropped the enclosing function from a line's ancestor chain in
    # those three languages (verified: Ruby/Dart/Zig --scope on a nested `if`
    # showed only the IF, never the enclosing DEF — Python's equivalent
    # correctly shows both). Lua's two statement kinds are also in
    # FUNCTION_NODE_TYPES but were already covered here via 'function_declaration'
    # (real Lua node kind; the treesitter.py comment naming them appears stale).
    'method', 'function_signature', 'Decl',
})
CLASS_NODES: frozenset = frozenset({
    'class_definition', 'class_declaration', 'class',
    # BACK-431 remaining scope (rose-tone-0704 finding #1): treesitter.py's
    # CLASS_NODE_TYPES (element-extraction taxonomy) already covered these —
    # C++ `class_specifier`, PHP `new class {...}` (`anonymous_class`), and
    # TypeScript `abstract class` (`abstract_class_declaration`) — but this
    # set (used for --scope's ancestor chain via FUNCTION_TYPES) didn't, so a
    # method's enclosing class was silently dropped from --scope in those
    # three languages (confirmed live: Python correctly showed CLASS as an
    # ancestor, C++/PHP/TS did not).
    'class_specifier', 'anonymous_class', 'abstract_class_declaration',
})
# C/C++ struct-with-methods (`struct Foo { void bar() {...} }`) has the same
# --scope gap as CLASS_NODES above, confirmed live — kept as its own family
# (not folded into CLASS_NODES) so the STRUCT label stays honest rather than
# claiming "class" for a construct that isn't one.
#
# BACK-478: the other three members were found via a cross-taxonomy audit
# against treesitter.py's separate extraction-side STRUCT_NODE_TYPES, which
# had drifted in two different ways: (1) `struct_declaration` was labeled
# "Go" in a comment but is actually C#'s real struct node kind (verified via
# direct tree-sitter inspection) — Go has no `struct_declaration` node at
# all; (2) Go's *real* struct kind, `struct_type`, was missing from every
# taxonomy, so Go structs were entirely invisible to --structs/--outline/
# --scope. `struct_type` has no name of its own — it nests inside
# `type_declaration -> type_spec -> [type_identifier, struct_type]`, so the
# name lives on a sibling, not a descendant; see
# TreeSitterAnalyzer._get_node_name's struct_type branch. `struct_item`
# (Rust) was already extracted correctly via this family but was *also*
# double-listed under CLASS_NODE_TYPES in treesitter.py — removed there so a
# Rust struct is labeled STRUCT everywhere, not STRUCT-and-CLASS.
STRUCT_NODES: frozenset = frozenset({
    'struct_specifier',    # C/C++
    'struct_item',         # Rust
    'struct_declaration',  # C#
    'struct_type',         # Go
})
# Rust methods live in `impl Foo { }` blocks, not in `struct Foo { }` itself
# (Rust structs have no nested methods) — the --scope gap there is impl_item
# missing, not struct_item, confirmed live (a Rust method's enclosing impl
# block was silently dropped from --scope's ancestor chain).
IMPL_NODES: frozenset = frozenset({'impl_item'})
LAMBDA_NODES: frozenset = frozenset({'lambda'})

RETURN_NODES: frozenset = frozenset({'return_statement', 'return'})
RAISE_NODES: frozenset = frozenset({'raise_statement', 'raise'})
# Scala's grammar is expression-oriented like Rust's — 'throw_expression',
# not 'throw_statement' (BACK-431 Issue G smoke-tier audit: Scala's `throw`
# was invisible to --exits/--returns without this, the same failure shape
# BACK-430 found for Rust).
THROW_NODES: frozenset = frozenset({'throw_statement', 'throw_expression'})
YIELD_NODES: frozenset = frozenset({'yield_statement', 'yield'})
# BACK-431: bare 'break'/'continue' were already recognized by nav_exits.py's
# hand-written _EXIT_KIND but missing from nav_outline.py's EXIT_NODES — a
# real drift instance found while consolidating (a grammar that emits bare
# `break`/`continue` keyword nodes was invisible to --outline while already
# working in --exits/--returns).
BREAK_NODES: frozenset = frozenset({'break_statement', 'break'})
CONTINUE_NODES: frozenset = frozenset({'continue_statement', 'continue'})


# ---------------------------------------------------------------------------
# Extraction-taxonomy families (BACK-478)
# ---------------------------------------------------------------------------
# Not control-flow constructs, so not part of FUNCTION_TYPES/SCOPE_NODES/
# EXIT_NODES/KEYWORD_LABEL below — this is the second, independently-drifting
# taxonomy Finding 1 (MULTI_LANGUAGE_FORWARD_DIRECTION_2026-07-05.md) named:
# treesitter.py's element-extraction node-kind lists. IMPORT_NODES is the
# first one pulled in here; tests/adapters/test_node_taxonomy.py pins that
# treesitter.py's IMPORT_NODE_TYPES/CLASS_NODE_TYPES/STRUCT_NODE_TYPES stay
# equal to this module's families (not re-declared at module level to avoid
# the treesitter.py <-> adapters.ast circular-import risk that already made
# nav_exits.py/nav_calls.py use deferred imports for CALL_NODE_TYPES).
IMPORT_NODES: frozenset = frozenset({
    'import_statement',           # Python, JavaScript
    'import_declaration',         # Go, Java
    'use_declaration',            # Rust
    'using_directive',            # C#
    'import_from_statement',      # Python
    'preproc_include',            # C/C++
    'namespace_use_declaration',  # PHP
    'import_header',              # Kotlin
})


# ---------------------------------------------------------------------------
# Composite sets — what each consumer actually queries against
# ---------------------------------------------------------------------------

FUNCTION_TYPES: frozenset = DEF_NODES | CLASS_NODES | STRUCT_NODES | IMPL_NODES | LAMBDA_NODES

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
    | FOR_EXPRESSION_NODES | FOR_EACH_NAME_VALUE_NODES | FOR_RANGE_LOOP_NODES
    | LOOP_NODES | DO_NODES
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
    | FOR_EACH_NAME_VALUE_NODES | FOR_RANGE_LOOP_NODES
    | LOOP_NODES | DO_NODES | MATCH_NODES | WITH_NODES
)

# nav_varflow.py: if/elif/while share the same 'condition'/'body' field
# shape (_walk_if_while) — for/for_expression/match have their own shapes
# (different field names) and are handled by dedicated dispatch branches.
IF_WHILE_NODES: frozenset = IF_NODES | ELIF_NODES | WHILE_NODES


KEYWORD_LABEL: Dict[str, str] = {
    'if_statement': 'IF', 'if': 'IF', 'if_expression': 'IF', 'IfStatement': 'IF',
    'elif_clause': 'ELIF', 'elseif_clause': 'ELIF',
    'else_clause': 'ELSE', 'else': 'ELSE',
    'for_statement': 'FOR', 'for': 'FOR', 'for_expression': 'FOR',
    'foreach_statement': 'FOR', 'for_in_statement': 'FOR',
    'enhanced_for_statement': 'FOR', 'for_range_loop': 'FOR',
    'while_statement': 'WHILE', 'while': 'WHILE', 'while_expression': 'WHILE',
    'loop_expression': 'LOOP',
    'try_statement': 'TRY', 'try': 'TRY',
    'except_clause': 'EXCEPT',
    'finally_clause': 'FINALLY', 'finally': 'FINALLY',
    'with_statement': 'WITH', 'with': 'WITH',
    'match_statement': 'MATCH', 'match_expression': 'MATCH',
    'case_clause': 'CASE', 'match_arm': 'CASE', 'SwitchProng': 'CASE',
    'when_entry': 'CASE',
    'do_statement': 'DO',
    'switch_statement': 'SWITCH', 'switch': 'SWITCH', 'SwitchExpr': 'SWITCH',
    'when_expression': 'SWITCH',
    'catch_clause': 'CATCH', 'catch': 'CATCH',
    'switch_case': 'CASE', 'switch_entry': 'CASE', 'case_statement': 'CASE',
    'switch_default': 'DEFAULT', 'default': 'DEFAULT', 'default_statement': 'DEFAULT',
    'function_definition': 'DEF', 'function_declaration': 'DEF',
    'function_item': 'DEF', 'function': 'DEF',
    'method_definition': 'DEF', 'method_declaration': 'DEF',
    'arrow_function': 'DEF',
    'method': 'DEF', 'function_signature': 'DEF', 'Decl': 'DEF',
    'lambda': 'LAMBDA',
    'class_definition': 'CLASS', 'class_declaration': 'CLASS', 'class': 'CLASS',
    'class_specifier': 'CLASS', 'anonymous_class': 'CLASS',
    'abstract_class_declaration': 'CLASS',
    'struct_specifier': 'STRUCT',
    'struct_item': 'STRUCT',
    'struct_declaration': 'STRUCT',
    'struct_type': 'STRUCT',
    'impl_item': 'IMPL',
    'return_statement': 'RETURN', 'return': 'RETURN',
    'raise_statement': 'RAISE', 'raise': 'RAISE',
    'throw_statement': 'THROW', 'throw_expression': 'THROW',
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
