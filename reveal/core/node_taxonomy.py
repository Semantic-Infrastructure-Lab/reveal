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

from typing import Any, Dict, Optional

from .treesitter_compat import _zero_arg, node_children


# ---------------------------------------------------------------------------
# Per-construct families
# ---------------------------------------------------------------------------

# Ruby statement modifiers (`raise … if cond`, `return 0 unless x`) and block
# `unless` are real conditional gates. Without them the guarded exit reads as
# unconditional in --returns/--exits gate chains (a correctness bug, BACK-500),
# and the branch is invisible to --ifmap. They flow into GATE_NODES (derived
# from IF_NODES below), so _get_condition's `condition` field lookup captures the
# gate. `unless`/`unless_modifier` carry an inverted sense conveyed by the UNLESS
# label. Found via discourse deep-conformance dogfooding.
# Statement modifiers (`x if cond` / `x unless cond`, and the loop forms
# `x += 1 while cond` / `x -= 1 until cond`) are decisions and gates, but —
# unlike block conditionals and loops — they wrap a single statement and do NOT
# introduce a nesting level. Kept as their own set so complexity's nesting metric
# can exclude them while still counting them as decisions.
IF_MODIFIER_NODES: frozenset = frozenset({'if_modifier', 'unless_modifier'})
LOOP_MODIFIER_NODES: frozenset = frozenset({'while_modifier', 'until_modifier'})  # BACK-1528
MODIFIER_NODES: frozenset = IF_MODIFIER_NODES | LOOP_MODIFIER_NODES
IF_NODES: frozenset = frozenset({
    'if_statement', 'if_expression', 'if', 'IfStatement', 'unless',
}) | IF_MODIFIER_NODES
# Lua's `elseif`/`else` arms are elseif_statement/else_statement: in no
# family, so --outline put their bodies under the IF (BACK-1530).
ELIF_NODES: frozenset = frozenset({'elif_clause', 'elseif_clause', 'elseif_statement'})
ELSE_NODES: frozenset = frozenset({'else_clause', 'else', 'else_statement'})
# Zig's IfStatement (BACK-431 Issue G smoke-tier audit) has no AST fields at
# all — unlike every other IF_NODES member, `_walk_if_while`'s
# 'condition'/'body' field lookup silently no-ops for it, so it's kept out
# of nav_varflow's IF_WHILE_NODES; it still counts for --outline/--ifmap
# (SCOPE_NODES/KEYWORD_LABEL), which only match on node kind.
# Ruby block `until cond ... end` is a named `until` (its keyword token is an
# anonymous `until`, skipped by the outline walkers); labeled WHILE so --loopmap
# keeps it, and the label text still reads "until ..." (BACK-1528).
WHILE_NODES: frozenset = frozenset({
    'while_statement', 'while_expression', 'while', 'until',
}) | LOOP_MODIFIER_NODES
# Loop constructs that share the C-style 'left'/'right' field shape in
# nav_varflow (loop var = 'left', iterable = 'right'): plain for, C#/PHP
# `foreach`, and JS/TS `for…of` / `for…in` (`for_in_statement`). BACK-431:
# `for_in_statement` was absent from the family entirely, making JS/TS
# for-each loops invisible to --outline/--ifmap/--varflow (confirmed live).
# Bash `for ((i=0; i<n; i++))` (`c_style_for_statement`) has C's
# initializer/condition/update/body fields, like C's for_statement here: neither
# has 'left'/'right', so _walk_for walks it as plain children (BACK-1528).
FOR_NODES: frozenset = frozenset({
    'for_statement', 'foreach_statement', 'for_in_statement', 'for',
    'c_style_for_statement',
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
# Body-first loops. C/Java/JS/C#/PHP/Dart `do_statement` (Swift's
# `do { } catch { }` and Lua's `do ... end` blocks share that kind: test
# is_do_block(), BACK-1541); Kotlin
# `do_while_statement`, Swift `repeat_while_statement`, Scala `do_while_expression`
# and Lua `repeat ... until` (`repeat_statement`) were in no family, so the loop
# was missing from --outline/--loopmap and its body read as unnested (BACK-1528).
DO_NODES: frozenset = frozenset({
    'do_statement', 'do_while_statement', 'repeat_while_statement',
    'do_while_expression', 'repeat_statement',
})

# BACK-477: Ruby's per-element iteration idiom (`items.each do |x| ... end`,
# `list.map { |x| ... }`, `3.times do ... end`) has NO dedicated loop AST
# node at all — it parses to a generic `call` node with a `do_block`/`block`
# child, structurally indistinguishable by kind from any other block-taking
# call that is *not* a loop (`File.open(p) do |f|`, `mutex.synchronize do`,
# `ActiveRecord::Base.transaction do`). The called method name is the only
# signal that a block runs once per element, so --loopmap/--fanout recognize
# these names specifically (see nav_outline._block_loop_keyword) rather than
# treating every block-call as a loop — a semantic pattern, deliberately not
# a node-kind add to LOOP_NODES/SCOPE_NODES (which would swallow every Ruby
# block). The block requirement gates out the no-block callsites of the same
# names (`Model.find(id)`, `arr.map` returning an Enumerator) — nothing
# executes per-element inline there, so they are correctly not loops.
RUBY_BLOCK_NODES: frozenset = frozenset({'do_block', 'block'})
RUBY_ITERATOR_METHODS: frozenset = frozenset({
    'each', 'each_with_index', 'each_with_object', 'each_pair', 'each_key',
    'each_value', 'each_entry', 'each_index', 'each_slice', 'each_cons',
    'each_line', 'each_char', 'each_byte',
    'map', 'map!', 'flat_map', 'collect', 'collect!', 'collect_concat',
    'select', 'select!', 'filter', 'filter!', 'filter_map',
    'reject', 'reject!', 'find_all', 'detect', 'find',
    'inject', 'reduce', 'group_by', 'partition', 'sort_by', 'min_by', 'max_by',
    'times', 'upto', 'downto', 'step',
    'find_each', 'find_in_batches', 'in_batches',  # ActiveRecord batching
})
# Ruby Kernel#loop — a genuine unconditional loop (labeled LOOP, not FOR).
RUBY_LOOP_METHODS: frozenset = frozenset({'loop'})

# BACK-477: Ruby's 'begin' is the literal tree-sitter kind of its
# begin/rescue/ensure/end block. Java's `try (var r = ...) { }` is its own
# kind, try_with_resources_statement (BACK-1530).
# Kotlin's and Scala's try/catch/finally block is a `try_expression`, and so
# are Swift's `try f()` and Rust's `?` operator (`validate(order)?` wraps the
# call). A scope test must use opens_scope() below, not this family alone, or
# every Swift `try` and Rust `?` would read as a TRY and break Rust's
# documented no-try/catch `--catchmap` contract.
# Before BACK-1530 the kind was left out altogether, so a Kotlin catch_block
# printed with no TRY above it.
TRY_NODES: frozenset = frozenset({
    'try_statement', 'try', 'begin', 'try_with_resources_statement', 'try_expression',
})
EXCEPT_NODES: frozenset = frozenset({'except_clause'})
# BACK-477: Kotlin's finally_block; Ruby's 'ensure' block (literal kind name).
FINALLY_NODES: frozenset = frozenset({'finally_clause', 'finally', 'finally_block', 'ensure'})
# BACK-477: catch_block is Kotlin AND Swift's shared kind name for the catch
# arm (verified via direct tree-sitter inspection, no collision found with
# any other supported grammar). Ruby's 'rescue' clause, and its statement
# modifier `x rescue y` (rescue_modifier, BACK-1530).
CATCH_NODES: frozenset = frozenset({
    'catch_clause', 'catch', 'catch_block', 'rescue', 'rescue_modifier',
})
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
# Ruby's case/when use bare `case` (the case expression) and `when` (the arm)
# node kinds — distinct from every wrapper-suffixed shape above. Safe to add as
# bare kinds: the outline/branchmap collectors skip anonymous nodes
# (`if not child.is_named(): continue`), and Ruby's case-expression / when-arm
# are named while the `case`/`when` keyword *tokens* (and C/Java's `case` label
# tokens) are anonymous — so no keyword-token collision. Found via discourse
# deep-conformance dogfooding (Ruby `case/when` was invisible to --ifmap).
CASE_NODES: frozenset = frozenset({
    'case_clause', 'match_arm', 'switch_case', 'SwitchProng', 'when_entry',
    'switch_entry', 'case_statement', 'when',
    # Go: each `case` arm of expression/type switches and select (`default`
    # arms are `default_case` -- deliberately not a branch) (BACK-1298).
    'expression_case', 'type_case', 'communication_case',
    # BACK-1529: C# / Dart switch-expression arms, Ruby 3 `case/in` arms, PHP
    # `match` arms (the default arm is match_default_expression, below).
    'switch_expression_arm', 'switch_expression_case', 'in_clause',
    'match_conditional_expression',
})
# BACK-1529: Go's switch/type-switch/select, the Java/C#/Dart switch
# expression and Ruby 3's `case/in` (`case_match`) were in no family, so
# --outline showed their arms flat under the function with no SWITCH scope
# (and nothing at all for the switch expressions and case_match).
SWITCH_NODES: frozenset = frozenset({
    'switch_statement', 'switch', 'SwitchExpr', 'when_expression', 'case',
    'expression_switch_statement', 'type_switch_statement', 'select_statement',
    'switch_expression', 'case_match',
})
SWITCH_DEFAULT_NODES: frozenset = frozenset({
    'switch_default', 'default', 'default_statement',
    'default_case',               # Go (BACK-1529)
    'match_default_expression',   # PHP `default => ...` (BACK-1529)
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
    # BACK-638: Java/C# constructors parse to a DISTINCT node kind from
    # method_declaration, not a same-name variant of it. Without this, a
    # constructor's name lookup (--boundary/--effects/--scope/element
    # extraction) fell through to the enclosing class_declaration instead
    # (same string name), silently returning the WHOLE CLASS BODY as the
    # constructor's range — sibling methods' effects leaked into constructor
    # --sideeffects results. Found via the Java sideeffects-recall-oracle
    # loop (BACK-547 third language): RecoveryMetricsCollector.java's
    # --boundary showed effects from an unrelated method ~70 lines later.
    'constructor_declaration',  # Java, C#
    # BACK-547 C# sideeffects-recall-oracle pre-flight check: C# operator
    # overloads (`public static bool operator ==(...)`) parse to their own
    # distinct node kind, not a variant of method_declaration. Without this,
    # they were entirely absent from --outline/--boundary/--sideeffects/
    # --scope and any name lookup failed outright ("could not find function
    # or method") — the node has no identifier child at all, so the paired
    # name-extraction fix (_operator_declaration_name) is also required.
    'operator_declaration',  # C#
    # BACK-647: Ruby's `def self.foo`/`def Class.foo` parses to a DISTINCT
    # node kind, 'singleton_method', not a same-name variant of 'method'
    # (`def foo`) — the dominant Ruby/Rails idiom for module-level utility,
    # job, and service-object entry points. Without this, every such method
    # was entirely invisible to --outline/get_structure()/--scope, and a
    # bare name lookup failed outright even when the name was unique in the
    # file. Verified live: Discourse's lib/discourse.rb (107 `def self.`
    # methods) showed only 6 functions in --outline.
    'singleton_method',  # Ruby class method
    # BACK-643: JS/TS/TSX `async function* name() {}` parses to a DISTINCT
    # node kind, 'generator_function_declaration', not a variant of
    # 'function_declaration'. Without this, a generator declared inside
    # another function's body was entirely absent from get_structure()/
    # --outline/--scope, and bare-name lookup errored "could not find
    # function or method" even though the enclosing function's
    # --sideeffects correctly included its effects.
    'generator_function_declaration',  # JS/TS/TSX generator function statement
    # BACK-718/BACK-724 (GDScript sideeffects-recall-oracle, seventeenth
    # language): GDScript's `func _init(...)` constructor parses to its OWN
    # distinct node kind, 'constructor_definition' — not even folded into
    # the enclosing class (GDScript has no wrapping class_declaration for a
    # top-level script file at all). Without this, `_init` was ENTIRELY
    # absent from --outline/get_structure()/--scope and direct name lookup
    # errored outright. Verified live: samples/gdscript_pixelorama's
    # SteamManager.gd `_init` (a real corpus `env` oracle positive) was
    # invisible to both --outline and direct lookup.
    'constructor_definition',  # GDScript `func _init(...)`
    # Swift `init(...)`/`deinit` (BACK-730 tenth language pre-flight, found
    # before the Swift calls-recall-oracle measurement) parse to their OWN
    # distinct node kinds, not a variant of `function_declaration` — arguably
    # THE most common lifecycle method in any Swift OOP codebase. Without
    # these, every initializer/deinitializer was entirely invisible to
    # --outline/get_structure()/--scope, and every call made from inside one
    # had no caller/ancestor scope to attribute to at all (a total edge
    # loss, not just a misattribution). Neither node has an identifier
    # child — the node KIND itself carries the fixed lifecycle name (see
    # TreeSitterAnalyzer._get_node_name's special-case branch).
    'init_declaration',    # Swift `init(...) { ... }`
    'deinit_declaration',  # Swift `deinit { ... }`
    # Dart constructors/getters/setters (BACK-730 eighteenth and final
    # language: `Dog(...)`, `Dog.named(...)`, `factory Dog.fromJson(...)`,
    # `int get x { ... }`, `set x(int value) { ... }`, `const Foo({...})`)
    # each parse to their OWN distinct node kinds, not variants of
    # `function_signature` (plain methods). Constructors are the PRIMARY
    # entry point for object construction in idiomatic Dart, and a `const`
    # constructor is Flutter's single most common StatelessWidget/
    # StatefulWidget constructor pattern — without these, none had a
    # caller/ancestor scope of their own, so every call made inside one
    # (a super-init-list helper, a named-constructor delegate, a call inside
    # a parameter default value) was silently dropped entirely, not just
    # misattributed. Getters/setters are a common idiom for computed
    # properties on both classes AND extensions (real corpus example:
    # AppFlowy's `String.fileSize` extension getter showed zero functions
    # in the whole file without this). See `_function_end_node` (disjoint
    # function_signature/function_body sibling shape) and
    # `_dart_constructor_name`/`_dart_merge_signature_extra_calls` for the
    # paired name-extraction and parameter-default-value call handling.
    'constructor_signature',           # Dart `Dog(...)` / `Dog.named(...)`
    'factory_constructor_signature',   # Dart `factory Dog.fromJson(...)`
    'getter_signature',                # Dart `int get x { ... }`
    'setter_signature',                # Dart `set x(int value) { ... }`
    'constant_constructor_signature',  # Dart `const Foo({this.x = 1, ...})`
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
    # BACK-798 (C# recall oracle) added 'record_declaration' to treesitter.py's
    # CLASS_NODE_TYPES (a C# 9+/Java 16+ record is a distinct node kind from
    # class/struct) but never here — the exact drift BACK-814's guard-rail
    # test exists to catch, caught live by that test the same session. Without
    # this, a record member was silently dropped from --scope's ancestor chain
    # even after BACK-798 fixed get_structure()/contracts for it.
    'record_declaration',
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
# BACK-1400: type declarations that own members but are neither a class, a
# struct nor an impl. Element extraction needs them twice: as the `Parent` in
# `Parent.member` (`Metadata.isMetadata` on a Java nested enum was "not
# found") and as a bare-name target (`Metadata` resolved to the enum's
# constructor, a function, because no type tier knew the enum). Kinds and
# names verified per grammar with tree-sitter-language-pack. Kotlin's `object`
# is absent on purpose: a top-level `object Obj {}` parses as
# infix_expression, not object_declaration. Not part of FUNCTION_TYPES, so
# --scope's ancestor chain is unchanged.
TYPE_DECL_NODES: frozenset = frozenset({
    'interface_declaration',  # Java, C#, PHP, TypeScript
    'enum_declaration',       # Java, C#, PHP, TypeScript, Dart
    'enum_item',              # Rust
    'trait_item',             # Rust (default method bodies)
    'trait_declaration',      # PHP
    'trait_definition',       # Scala
    'object_definition',      # Scala
    'enum_definition',        # Scala 3
    'protocol_declaration',   # Swift
    'mixin_declaration',      # Dart
    'extension_declaration',  # Dart
    'internal_module',        # TypeScript `namespace NS {}`
})
# Every node kind that can be the `Parent` of `Parent.member` extraction.
# 'module' is Ruby's module (Python's root is also 'module', but it has no
# name, so it never matches a parent name).
MEMBER_CONTAINER_NODES: frozenset = (
    CLASS_NODES | STRUCT_NODES | IMPL_NODES | TYPE_DECL_NODES | frozenset({'module'})
)

# BACK-1527: expression-oriented grammars wrap each exit in an *_expression
# (Rust return/break/continue/yield, Scala return; JS/TS/PHP yield), C++20
# coroutines have co_return/co_yield statements, Dart `yield*` is
# yield_each_statement. Without the wrapper, --exits matched only the bare
# keyword token inside it and printed `return` without its value, and
# --outline (which skips anonymous tokens) dropped every Rust return.
RETURN_NODES: frozenset = frozenset({
    'return_statement', 'return', 'return_expression', 'co_return_statement',
})
RAISE_NODES: frozenset = frozenset({'raise_statement', 'raise'})
# Scala's grammar is expression-oriented like Rust's — 'throw_expression',
# not 'throw_statement' (BACK-431 Issue G smoke-tier audit: Scala's `throw`
# was invisible to --exits/--returns without this, the same failure shape
# BACK-430 found for Rust).
# Kotlin and Swift wrap return/throw/break/continue in one control-transfer
# wrapper (JUMP_WRAPPER_NODES, below) whose exit kind is its keyword child:
# Kotlin's `jump_expression` holds a bare `throw`/`return`/..., Swift's
# `control_transfer_statement` holds `throw_keyword` or a bare `return`/....
# Those keyword kinds are here, as RETURN_NODES carries bare 'return', so
# exit_label() can name the wrapper by its first child. NB: Swift's `throws`
# (function effect specifier on the signature) is deliberately NOT included —
# only `throw_keyword` (the statement). Found via tivi (Kotlin) + ios-oss
# (Swift) deep-conformance dogfooding.
THROW_NODES: frozenset = frozenset(
    {'throw_statement', 'throw_expression', 'throw', 'throw_keyword'}
)
YIELD_NODES: frozenset = frozenset({
    'yield_statement', 'yield', 'yield_expression', 'co_yield_statement',
    'yield_each_statement',  # Dart `yield*`
})
# BACK-1406: PHP parses `exit;` / `exit(1)` as a statement, not a call -- unlike
# `die("x")`, which is a function_call_expression caught by nav_exits'
# _EXIT_CALL_NAMES. Without this, --returns/--exits/--sideeffects missed every
# `exit` in PHP.
HARD_EXIT_NODES: frozenset = frozenset({'exit_statement'})
# BACK-431: bare 'break'/'continue' were already recognized by nav_exits.py's
# hand-written _EXIT_KIND but missing from nav_outline.py's EXIT_NODES — a
# real drift instance found while consolidating (a grammar that emits bare
# `break`/`continue` keyword nodes was invisible to --outline while already
# working in --exits/--returns).
BREAK_NODES: frozenset = frozenset({'break_statement', 'break', 'break_expression'})
CONTINUE_NODES: frozenset = frozenset({'continue_statement', 'continue', 'continue_expression'})
# BACK-1527: wrappers whose exit kind is their first child, a keyword in one of
# the families above (Kotlin `return x`, `throw e`, `break`, `continue`; Swift
# the same with `throw_keyword`). The kind carries no control-flow word, so the
# grammar-coverage test cannot see it. Kotlin's labeled `return@forEach` has
# its own `return@` token: it leaves the lambda, not the function, and is not
# an exit. Not part of EXIT_NODES (no fixed label); use exit_label().
JUMP_WRAPPER_NODES: frozenset = frozenset({'jump_expression', 'control_transfer_statement'})


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

# Data-flow family: Finding 2's second example. Member/scoped-access node
# kinds where only the leftmost (base object) child is a real variable
# reference — the rightmost child is an attribute/field/member name, not an
# independent identifier. This was the *literal* re-declared-three-times
# case Finding 2 named: nav_varflow.py had the fullest version (this one,
# unchanged); nav_statewrites.py's independent copy was missing
# 'scoped_identifier'/'dot_index_expression'/'method_index_expression';
# nav_calls.py's independent copy was missing 'field_access' (Java),
# 'navigation_expression' (Kotlin/Swift), and both Lua kinds — a real,
# live bug (BACK-478 move 1 step 2): nav_calls.py's fluent-chain callee
# collapse (BACK-415, `a().b().c()` -> callee ".c" not the whole chain
# text) silently didn't fire for Kotlin/Swift/Lua chains, which rendered
# each outer call's "callee" as the entire chain's source text instead.
MEMBER_ACCESS_NODES: frozenset = frozenset({
    'attribute',                  # Python: obj.attr
    'member_access_expression',   # C#: obj.Member
    'field_expression',           # C, Rust: obj.field
    'field_access',               # Java: obj.field
    'member_expression',          # JS/TS: obj.prop
    'selector_expression',        # Go: obj.Field
    'scoped_identifier',          # Rust: path::segment
    'navigation_expression',      # Kotlin/Swift: obj.member / obj.method()
    'dot_index_expression',       # Lua: obj.field
    'method_index_expression',    # Lua: obj:method() (colon call syntax)
})


# ---------------------------------------------------------------------------
# Composite sets — what each consumer actually queries against
# ---------------------------------------------------------------------------

FUNCTION_TYPES: frozenset = DEF_NODES | CLASS_NODES | STRUCT_NODES | IMPL_NODES | LAMBDA_NODES

EXIT_NODES: frozenset = (
    RETURN_NODES | RAISE_NODES | THROW_NODES | YIELD_NODES
    | BREAK_NODES | CONTINUE_NODES | HARD_EXIT_NODES
)

# nav_outline.py: clauses printed at their construct's own depth (an else is a
# sibling of its if). A default arm is not one: it is an arm like CASE, so it
# is a scope below. Where it sits under a body node (JS switch_body, PHP
# match_block) the depth came out the same either way; Go's default_case is a
# direct child of the switch and printed beside it (BACK-1529).
ALTERNATIVE_NODES: frozenset = (
    ELIF_NODES | ELSE_NODES | EXCEPT_NODES | FINALLY_NODES | CATCH_NODES
)

# nav_outline.py: every construct that opens a nested scope worth descending into.
SCOPE_NODES: frozenset = (
    IF_NODES | ELIF_NODES | ELSE_NODES | WHILE_NODES | FOR_NODES
    | FOR_EXPRESSION_NODES | FOR_EACH_NAME_VALUE_NODES | FOR_RANGE_LOOP_NODES
    | LOOP_NODES | DO_NODES
    | TRY_NODES | EXCEPT_NODES | FINALLY_NODES | CATCH_NODES | WITH_NODES
    | MATCH_NODES | CASE_NODES | SWITCH_NODES | SWITCH_DEFAULT_NODES
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
    'if_modifier': 'IF', 'unless': 'UNLESS', 'unless_modifier': 'UNLESS',
    'elif_clause': 'ELIF', 'elseif_clause': 'ELIF', 'elseif_statement': 'ELIF',
    'else_clause': 'ELSE', 'else': 'ELSE', 'else_statement': 'ELSE',
    'for_statement': 'FOR', 'for': 'FOR', 'for_expression': 'FOR',
    'foreach_statement': 'FOR', 'for_in_statement': 'FOR',
    'enhanced_for_statement': 'FOR', 'for_range_loop': 'FOR',
    'c_style_for_statement': 'FOR',
    'while_statement': 'WHILE', 'while': 'WHILE', 'while_expression': 'WHILE',
    'until': 'WHILE', 'while_modifier': 'WHILE', 'until_modifier': 'WHILE',
    'loop_expression': 'LOOP',
    'try_statement': 'TRY', 'try': 'TRY',
    'begin': 'TRY', 'try_with_resources_statement': 'TRY', 'try_expression': 'TRY',
    'except_clause': 'EXCEPT',
    'finally_clause': 'FINALLY', 'finally': 'FINALLY',
    'finally_block': 'FINALLY', 'ensure': 'FINALLY',
    'with_statement': 'WITH', 'with': 'WITH',
    'match_statement': 'MATCH', 'match_expression': 'MATCH',
    'case_clause': 'CASE', 'match_arm': 'CASE', 'SwitchProng': 'CASE',
    'when_entry': 'CASE',
    'do_statement': 'DO', 'do_while_statement': 'DO', 'repeat_while_statement': 'DO',
    'do_while_expression': 'DO', 'repeat_statement': 'DO',
    'switch_statement': 'SWITCH', 'switch': 'SWITCH', 'SwitchExpr': 'SWITCH',
    'when_expression': 'SWITCH',
    'expression_switch_statement': 'SWITCH', 'type_switch_statement': 'SWITCH',  # Go
    'select_statement': 'SWITCH',  # Go `select` (its arms are communication_case)
    'switch_expression': 'SWITCH', 'case_match': 'SWITCH',
    'catch_clause': 'CATCH', 'catch': 'CATCH',
    'catch_block': 'CATCH', 'rescue': 'CATCH', 'rescue_modifier': 'CATCH',
    'switch_case': 'CASE', 'switch_entry': 'CASE', 'case_statement': 'CASE',
    'expression_case': 'CASE', 'type_case': 'CASE', 'communication_case': 'CASE',  # Go
    'case': 'SWITCH', 'when': 'CASE',  # Ruby case/when (bare kinds; named nodes)
    'switch_expression_arm': 'CASE', 'switch_expression_case': 'CASE',  # C#, Dart
    'in_clause': 'CASE', 'match_conditional_expression': 'CASE',  # Ruby case/in, PHP match
    'switch_default': 'DEFAULT', 'default': 'DEFAULT', 'default_statement': 'DEFAULT',
    'default_case': 'DEFAULT', 'match_default_expression': 'DEFAULT',  # Go, PHP match
    'function_definition': 'DEF', 'function_declaration': 'DEF',
    'function_item': 'DEF', 'function': 'DEF',
    'method_definition': 'DEF', 'method_declaration': 'DEF',
    'arrow_function': 'DEF',
    'method': 'DEF', 'function_signature': 'DEF', 'Decl': 'DEF',
    'constructor_declaration': 'DEF',  # BACK-638: Java/C#
    'operator_declaration': 'DEF',  # BACK-547 C# recall-oracle pre-flight
    'singleton_method': 'DEF',  # BACK-647: Ruby `def self.foo`/`def Class.foo`
    'generator_function_declaration': 'DEF',  # BACK-643: JS/TS `async function* name() {}`
    'constructor_definition': 'DEF',  # BACK-718/BACK-724: GDScript `func _init(...)`
    'init_declaration': 'DEF', 'deinit_declaration': 'DEF',  # Swift `init(...)`/`deinit`
    'constructor_signature': 'DEF', 'factory_constructor_signature': 'DEF',  # Dart constructors
    'getter_signature': 'DEF', 'setter_signature': 'DEF',  # Dart `get`/`set`
    'constant_constructor_signature': 'DEF',  # Dart `const` constructor
    'lambda': 'LAMBDA',
    'class_definition': 'CLASS', 'class_declaration': 'CLASS', 'class': 'CLASS',
    'class_specifier': 'CLASS', 'anonymous_class': 'CLASS',
    'abstract_class_declaration': 'CLASS',
    'record_declaration': 'CLASS',  # BACK-798: C# 9+/Java 16+ record
    'struct_specifier': 'STRUCT',
    'struct_item': 'STRUCT',
    'struct_declaration': 'STRUCT',
    'struct_type': 'STRUCT',
    'impl_item': 'IMPL',
    'return_statement': 'RETURN', 'return': 'RETURN',
    'return_expression': 'RETURN', 'co_return_statement': 'RETURN',  # BACK-1527
    'raise_statement': 'RAISE', 'raise': 'RAISE',
    'throw_statement': 'THROW', 'throw_expression': 'THROW', 'throw': 'THROW',
    'throw_keyword': 'THROW',
    'yield_statement': 'YIELD', 'yield': 'YIELD',
    'yield_expression': 'YIELD', 'co_yield_statement': 'YIELD',  # BACK-1527
    'yield_each_statement': 'YIELD',
    'exit_statement': 'EXIT',  # BACK-1406: PHP `exit;`
    'break_statement': 'BREAK', 'break': 'BREAK', 'break_expression': 'BREAK',
    'continue_statement': 'CONTINUE', 'continue': 'CONTINUE',
    'continue_expression': 'CONTINUE',
}


def is_rust_try_operator(node: Any) -> bool:
    """True for Rust's `x?` -- the one `try_expression` that is not a try block.

    Kotlin's try block and Rust's `?` share the kind string; only the shape
    tells them apart: Rust's always holds a literal `?` token, Kotlin's opens
    with `try` (BACK-428, BACK-1530). --exits reads it as an early RETURN; a
    scope test must skip it."""
    return (_zero_arg(node, 'kind') == 'try_expression'
            and any(_zero_arg(c, 'kind') == '?' for c in node_children(node)))


def exit_label(node: Any, kind: str) -> Optional[str]:
    """RETURN / THROW / BREAK / ... when a node of ``kind`` is an exit, else None.

    The one definition --outline and --exits/--returns share. EXIT_NODES name
    themselves; a JUMP_WRAPPER_NODES wrapper is named by its keyword child, so
    the exit is reported at the whole statement (`return x`, not `return`)."""
    if kind in JUMP_WRAPPER_NODES:
        first = node_children(node)[:1]
        kind = _zero_arg(first[0], 'kind') if first else ''
    return KEYWORD_LABEL[kind] if kind in EXIT_NODES else None


_DO_LOOP_CONDITION_TOKENS: frozenset = frozenset({'while', 'until'})


def is_do_block(node: Any) -> bool:
    """True for a `do_statement` that is a block, not a body-first loop.

    C/C++/CUDA/GLSL/Java/JS/TS/C#/PHP/Dart/ObjC/PowerShell use the kind for
    `do { } while (c)` (PowerShell also `do { } until (c)`): the loop always
    holds its `while`/`until` token. Swift's `do { } catch { }` (its do-while
    is `repeat_while_statement`) and Lua's `do ... end` never do. DO_NODES
    alone made --loopmap list those blocks as loops and complexity count them
    as decisions (BACK-1541)."""
    return (_zero_arg(node, 'kind') == 'do_statement'
            and not any(_zero_arg(c, 'kind') in _DO_LOOP_CONDITION_TOKENS
                        for c in node_children(node)))


def scope_label(node: Any, kind: str) -> str:
    """The keyword --outline/--scope/--loopmap/--catchmap print for a scope node.

    KEYWORD_LABEL, except where one kind names two constructs: a `do` block
    that opens a scope is Swift's do/catch, a TRY (its catch_block children
    are the CATCHes), not a DO loop."""
    if kind == 'do_statement' and is_do_block(node):
        return 'TRY'
    return KEYWORD_LABEL.get(kind, kind.upper())


def opens_scope(node: Any, kind: str) -> bool:
    """Whether a node of ``kind`` opens an --outline/--scope scope.

    SCOPE_NODES, except where the kind alone does not say it is a scope:
    - a `try_expression` that is not a try block. Four grammars use that kind:
      Kotlin and Scala for a try block, which opens with the bare `try` token,
      and Swift (`try f()`) and Rust (`f()?`) for an operator on a throwing
      call (BACK-1530);
    - a `do` block with no catch (Swift `do { }`, Lua `do ... end`), which is a
      plain block like a bare `{ }` (BACK-1541)."""
    if kind not in SCOPE_NODES:
        return False
    if kind == 'do_statement' and is_do_block(node):
        return any(_zero_arg(c, 'kind') == 'catch_block' for c in node_children(node))
    if kind != 'try_expression':
        return True
    first = node_children(node)[:1]
    return bool(first) and _zero_arg(first[0], 'kind') == 'try'


# ---------------------------------------------------------------------------
# Guard rail: catch a family/composite drifting out of sync with KEYWORD_LABEL
# or with each other at import time, not at whatever call site happens to hit
# the gap first — see tests/test_node_taxonomy.py for the full cross-check.
# ---------------------------------------------------------------------------

_ALL_LABELED_KINDS: frozenset = frozenset(KEYWORD_LABEL)
assert (SCOPE_NODES | EXIT_NODES | FUNCTION_TYPES) <= _ALL_LABELED_KINDS, (
    'node_taxonomy: a composite set contains a node kind with no KEYWORD_LABEL entry'
)
