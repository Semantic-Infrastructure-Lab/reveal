"""Cyclomatic complexity and nesting depth metrics for AST nodes.

Standalone functions — no TreeSitterAnalyzer dependency — so the check/review
flow can import this without pulling the full analyzer base class into scope.
"""

from typing import Any, Mapping, Optional

from .core import node_children as _children
from .core.node_taxonomy import is_do_block, is_prefix_try
from .core.treesitter_compat import _zero_arg
from .utils.lines import split_lines


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
# Iterator-method loops (Ruby `.each`, JS/Kotlin `forEach`, Rust `.for_each`) are
# deliberately NOT decisions: they are block-taking calls, and counting those would
# also count map/tap/File.open (BACK-1285; documented in AST_ADAPTER_GUIDE.md).
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
    'for_statement', 'for_expression', 'for', 'ForStatement',
    'foreach_statement', 'for_in_statement', 'enhanced_for_statement',
    'while_statement', 'while_expression', 'while',
    'until',
    'c_style_for_statement',  # bash `for ((...))`
    'while_modifier', 'until_modifier',  # ruby `x += 1 while c` (do not nest)
    'do_statement',
    # Body-first loops (BACK-1528): kotlin, swift, scala, lua `repeat ... until`
    'do_while_statement', 'repeat_while_statement', 'do_while_expression',
    'repeat_statement',
    # Boolean operators
    'boolean_operator',
    'and', 'or',
    # Ternary
    'conditional_expression', 'ternary_expression',
    'conditional',  # ruby `a ? b : c`
    'IfExpr',  # zig `const x = if (c) a else b` (statements: IfStatement)
    # zig `.a => for (xs) |x| {...}`, `if (c) for (...)`: a for loop used as an expression
    # (legacy grammar LoopExpr > ForExpr; its `for` token is excluded by the ForPrefix pair).
    # Uncounted until BACK-2540 found it against pack 1.25's for_expression, which counts.
    'ForExpr',
    # Exception handling
    'except_clause', 'catch_clause', 'catch_block',  # kotlin
    'rescue',
    'rescue_modifier',  # ruby `x rescue y` (BACK-1530); does not nest
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
    # Ruby 3 `case/in` arms and PHP `match` arms (BACK-1529). PHP's default arm
    # is its own kind (match_default_expression), uncounted. A Ruby `in _` arm
    # is a lone identifier, indistinguishable from a binding `in x` without
    # source text, so it counts (+1); Ruby's usual catch-all is `else`.
    'in_clause', 'match_conditional_expression',
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
    # Zig `a orelse b` / `a catch b`: `BitwiseOp` tokens in the legacy grammar (pack <= 1.24);
    # 1.25's are under `binary_expression` / `catch_expression` (BACK-2540).
    'orelse': frozenset({'BitwiseOp', 'binary_expression'}), 'catch': frozenset({'BitwiseOp', 'catch_expression'}),
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
    'SwitchProng', 'switch_case', 'case_statement', 'case_clause', 'match_arm', 'pattern_section', 'when_entry', 'switch_entry', 'switch_expression_arm', 'switch_expression_case'})
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
        return bool(kind == 'identifier' and _zero_arg(arm, 'kind') == 'pattern_section')
    return False


_NESTING_TYPES = frozenset({
    'if_statement', 'if_expression', 'if', 'IfStatement', 'IfExpr',
    'unless',  # Ruby block `unless … end` nests; the modifiers (MODIFIER_NODES) do not
    'for_statement', 'for_expression', 'for', 'ForStatement',
    'foreach_statement', 'for_in_statement', 'enhanced_for_statement',
    'c_style_for_statement',
    'while_statement', 'while_expression', 'while', 'until',
    'loop_expression',
    'try_statement', 'try', 'with_statement', 'with',
    'try_with_resources_statement',  # java (BACK-1530)
    # Not Kotlin's try_expression: Rust's `x?` shares the kind, and nesting it
    # would deepen every function that uses `?`.
    'match_statement', 'match_expression', 'case_statement',
    'do_statement', 'switch_statement',
    # Go's switch statements nest like every other switch_statement (BACK-1529).
    'expression_switch_statement', 'type_switch_statement', 'select_statement',
    'do_while_statement', 'repeat_while_statement', 'do_while_expression',
    'repeat_statement',
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
    ('rescue_modifier', 'rescue'),
    ('boolean_operator', 'or'),
    ('boolean_operator', 'and'),
    # Kotlin: `when_expression` wraps a bare `when` keyword token (BACK-1301).
    ('when_expression', 'when'),
    # C `do { } while (c)`: the statement wraps a bare `while` keyword token.
    ('do_statement', 'while'),
    # PowerShell `do { } until (c)` (BACK-1541: counted twice without it).
    ('do_statement', 'until'),
    # BACK-1528: the same shape in the other body-first loops, the ruby loop
    # modifiers and bash's C-style for. Before these kinds were decisions, the
    # bare token alone carried the count; now the construct does.
    ('do_while_statement', 'while'),
    ('repeat_while_statement', 'while'),
    ('do_while_expression', 'while'),
    ('repeat_statement', 'until'),
    ('while_modifier', 'while'),
    ('until_modifier', 'until'),
    ('c_style_for_statement', 'for'),
    # Zig: `IfStatement`/`IfExpr` wrap an `IfPrefix` that holds the bare `if` token.
    ('IfPrefix', 'if'),
    ('ForPrefix', 'for'),
    # Zig on pack 1.25: a conditional type (`var s: if (libc) c_int else u32`) is chosen at
    # compile time, not a runtime branch; the legacy grammar's IfTypeExpr never counted either
    # (BACK-2540). The wrapper is no decision kind, so this pair keeps the whole form at zero.
    ('if_type_expression', 'if'),
})


_SCALA_LOGICAL_OPERATORS = frozenset({'&&', '||'})


def _has_child_kind(node, kind) -> bool:
    return any(_zero_arg(c, 'kind') == kind for c in _children(node))


# Type wrappers whose operand is a type (Zig `*T`, `?T`, `[]T`, `[N]T`, `E!T`).
_TYPE_WRAPPER_KINDS = frozenset({'pointer_type', 'nullable_type', 'slice_type', 'array_type', 'error_union_type'})


def _selects_a_type(node) -> bool:
    """True for an expression in a type position, a compile-time type operation (Zig on
    pack 1.25, BACK-2540): `status: *if (libc) c_int else u32` (an `if_expression` there,
    as the `if_type_expression` it uses elsewhere) and `fn f() (A || B)!void` (`||`
    merges error sets; Zig's runtime boolean operators are `and`/`or`). Nested `||`
    operands and parentheses are climbed. JS, C and TS have no `||` in a type position.
    In a value position (`const T = if (c) A else B;`) an if stays a decision, as the
    legacy grammar's IfExpr is."""
    parent = _zero_arg(node, 'parent')
    # range_expression: 1.25 wraps `*if (c) A else B` in one inside a pointer type.
    while parent is not None and _zero_arg(parent, 'kind') in (
            'binary_expression', 'parenthesized_expression', 'range_expression'):
        node, parent = parent, _zero_arg(parent, 'parent')
    if parent is None:
        return False
    if _zero_arg(parent, 'kind') in _TYPE_WRAPPER_KINDS:
        return True
    type_field = parent.child_by_field_name('type')
    return type_field is not None and (_zero_arg(type_field, 'start_byte'), _zero_arg(type_field, 'end_byte')) == (
        _zero_arg(node, 'start_byte'), _zero_arg(node, 'end_byte'))


# Operand kinds only Zig has (pack 1.25): an error set literal `error{A, B}` and a builtin
# call such as `@TypeOf(err)`. Either one in a `||` chain makes it an error-set merge.
_ZIG_ERROR_SET_OPERANDS = frozenset({'error_set_declaration', 'builtin_function'})


def _merges_error_sets(binary) -> bool:
    """True for a Zig error-set merge written in a value position inside a function,
    `const ErrSet = @TypeOf(err) || error{Unknown};`, recognized by a Zig-only operand
    anywhere in the `||` chain (BACK-2540). Zig's runtime boolean operators are `and`/`or`."""
    top = binary
    parent = _zero_arg(top, 'parent')
    while parent is not None and _zero_arg(parent, 'kind') in ('binary_expression', 'parenthesized_expression'):
        top, parent = parent, _zero_arg(parent, 'parent')
    stack = [top]
    while stack:
        current = stack.pop()
        for child in _children(current):
            kind = _zero_arg(child, 'kind')
            if kind in _ZIG_ERROR_SET_OPERANDS:
                return True
            if kind in ('binary_expression', 'parenthesized_expression'):
                stack.append(child)
    return False


def _scala_infix_verdict(parent_kind, node, node_text) -> Optional[bool]:
    """Scala infix `&&`/`||` is an `operator_identifier` shared with `+`."""
    return (parent_kind == 'infix_expression' and node_text is not None
            and node_text(node) in _SCALA_LOGICAL_OPERATORS)


def _scala_catch_verdict(parent_kind, node, node_text) -> Optional[bool]:
    """Scala `catch { case ... }`: the case arms carry the count."""
    return False if _has_child_kind(node, 'case_block') else None


def _do_block_verdict(parent_kind, node, node_text) -> Optional[bool]:
    """Swift `do { } catch`, Lua `do ... end`: a block, not a loop (BACK-1541)."""
    return False if is_do_block(node) else None


def _type_choice_verdict(parent_kind, node, node_text) -> Optional[bool]:
    """Zig 1.25 `status: *if (libc) c_int else u32` selects a type (_selects_a_type)."""
    return False if _selects_a_type(node) else None


def _error_set_merge_verdict(parent_kind, node, node_text) -> Optional[bool]:
    """Zig 1.25 `(A || B)!T`, `@TypeOf(e) || error{X}`: `||` merges error sets."""
    parent = _zero_arg(node, 'parent')
    if parent_kind == 'binary_expression' and parent is not None and (
            _selects_a_type(parent) or _merges_error_sets(parent)):
        return False
    return None


def _prefix_try_verdict(parent_kind, node, node_text) -> Optional[bool]:
    """Zig 1.25 `try x` exits early on error, as the legacy grammar's `try` under `PrefixOp`
    does; a Kotlin/Scala block `try`'s keyword is not a decision (BACK-2540)."""
    if parent_kind != 'try_expression':
        return None
    parent = _zero_arg(node, 'parent')
    return parent is not None and is_prefix_try(parent)


# Kinds whose verdict needs more than kind and parent: each returns True/False, or None to
# fall through to the general rule. Skipped without a node (callers that pass only kinds).
_SPECIAL_VERDICTS = {
    'operator_identifier': _scala_infix_verdict,
    'catch_clause': _scala_catch_verdict,
    'do_statement': _do_block_verdict,
    'if_expression': _type_choice_verdict,
    '||': _error_set_merge_verdict,
    'try': _prefix_try_verdict,
}


def is_decision(kind: str, parent_kind, node=None, node_text=None) -> bool:
    """True if `node` (of `kind`, under `parent_kind`) adds one decision point.

    `node` is only needed to recognise a catch-all arm and the _SPECIAL_VERDICTS shapes;
    omit it and default-capable arm kinds count unconditionally. `node_text(node) -> str` is
    only needed for Scala infix `&&`/`||` (an `operator_identifier` shared with `+`);
    omit it and those undercount rather than guess.

    The single decision rule shared by `calculate_complexity_and_depth` and
    treesitter's merged `_complexity_depth_and_calls` walk (BACK-1303) --
    edit the rule here, never in a walker.
    """
    special = _SPECIAL_VERDICTS.get(kind)
    if special is not None and node is not None:
        verdict = special(parent_kind, node, node_text)
        if verdict is not None:
            return verdict
    elif kind == 'operator_identifier':
        return False  # no node: a Scala infix operator cannot be read (see above)
    if kind in _DECISION_TYPES:
        if parent_kind is not None and (parent_kind, kind) in _KEYWORD_PAIRS:
            return False
        return not (node is not None and kind in _DEFAULT_CAPABLE_ARMS and _is_default_arm(node))
    parents = _OPERATOR_TOKEN_PARENTS.get(kind)
    if parents is not None:
        return parent_kind in parents
    return kind == 'case' and parent_kind in _CASE_TOKEN_PARENTS


def is_nesting(kind: str, node) -> bool:
    """True if `node` (of `kind`) opens one nesting level.

    Only a named node nests. Most grammars put the construct's bare keyword token under it
    (`if_statement > 'if'`, Ruby `if > 'if'`, Zig legacy `IfPrefix > 'if'`); the token shares a
    nesting kind but is anonymous, and counting it read a lone `if` as depth 2 (BACK-2543).
    """
    return kind in _NESTING_TYPES and bool(_zero_arg(node, 'is_named'))


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
            child_depth = depth + 1 if is_nesting(child_type, child) else depth
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


# Control-flow tokens the keyword fallback counts. Language-agnostic and text-based, so it
# is an estimate: it also counts a token inside a string or comment.
_FALLBACK_PATTERNS = (
    ' if ', ' if(',       # conditionals
    ' else if ', 'elif ',  # else-if chains
    ' for ', ' for(',     # loops
    ' while ', ' while(',
    ' && ', ' and ',      # boolean operators
    ' || ', ' or ',
    ' case ',             # switch/match cases
    ' catch ', ' catch(',  # exception handling
    ' except ',
    ' ? ',                # ternary operator
)


def fallback_complexity(func: Mapping[str, Any], content: Optional[str]) -> int:
    """Estimate complexity for a function whose analyzer supplies no tree-sitter score.

    The one fallback for ast://, stats:// and C901 (BACK-1519): count control-flow
    tokens in the function's lines, starting at 1. A record with no line range gets
    ``line_count // 10`` (at least 1); a range outside *content* gets 1. Callers use a
    supplied ``func['complexity']`` first and call this only when there is none.
    """
    start_line = func.get('line', 0)
    end_line = func.get('line_end') or start_line

    if start_line == 0 or end_line == 0:
        return max(1, int(func.get('line_count', 0)) // 10)

    lines = split_lines(content or '')
    if start_line > len(lines) or end_line > len(lines):
        return 1

    func_content = '\n'.join(lines[start_line - 1:end_line])
    return 1 + sum(func_content.count(pattern) for pattern in _FALLBACK_PATTERNS)
