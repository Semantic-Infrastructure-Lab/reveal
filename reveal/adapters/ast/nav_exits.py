"""Exit analysis: collect_exits, collect_deps, collect_mutations, gate chains, renderers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Collection, Dict, List, Optional, Tuple, TypedDict, Literal

from .nav_calls import _extract_callee
from .nav_bindings import BindingScope
from ...conventions import FAMILY_BY_LANGUAGE, conventions_for
from .nav_varflow import all_var_flow
from .node_taxonomy import (
    CATCH_NODES, ELIF_NODES, ELSE_NODES, EXCEPT_NODES, GATE_NODES, IF_NODES,
    exit_label, is_rust_try_operator, zig_catch_parts, MEMBER_CONTAINER_NODES,
)
from ...core import node_children as _children, node_prev_sibling as _prev_sibling
from ...core.treesitter_compat import _zero_arg
from reveal.utils.lines import split_lines
from reveal.reveal_types import WarningEntry


# Language-construct names treated as hard exits even when represented as calls.
# Ruby raises exceptions with `raise`/`fail` — plain method calls, not keyword
# nodes (no raise_statement in tree-sitter-ruby), so they must be caught here the
# way PHP/Perl `die`/`exit` are. Found via discourse deep-conformance dogfooding
# (Ruby `raise ArgumentError` was invisible to --exits/--returns/--flowto).
_EXIT_CALL_NAMES: frozenset = frozenset({'die', 'exit', 'raise', 'fail', 'abort'})

# BACK-1406: an exit written as a bare name, with no call node. PHP's `die;`
# is a `name` in an expression_statement (`exit;` is an exit_statement, in
# EXIT_NODES); Ruby's bare `raise` / `exit` / `abort` is an `identifier`
# directly in a body. Only in statement position: in Python or JS a bare
# `exit` statement is a no-op expression, so the PHP form is keyed to PHP's
# `name` kind and the Ruby form to Ruby's statement containers.
_RUBY_STATEMENT_PARENTS: frozenset = frozenset({
    'body_statement', 'then', 'else', 'if_modifier', 'unless_modifier',
    'block_body', 'begin', 'ensure', 'program',
})


def bare_exit_name(node: Any, get_text: Callable) -> Optional[str]:
    """`die` / `exit` / `raise` / ... when node is one written as a bare
    statement (PHP `die;`, Ruby `raise`), else None."""
    kind = _zero_arg(node, 'kind')
    if kind not in ('name', 'identifier'):
        return None
    parent = _zero_arg(node, 'parent')
    if parent is None:
        return None
    parent_kind = _zero_arg(parent, 'kind')
    in_statement = (parent_kind == 'expression_statement' if kind == 'name'
                    else parent_kind in _RUBY_STATEMENT_PARENTS)
    if not in_statement:
        return None
    name = get_text(node)
    return name if name in _EXIT_CALL_NAMES else None

# BACK-421 part 3: C++ error-handling macros expand to an early return, but
# tree-sitter parses the raw (pre-preprocessor) source, so they appear as a
# plain call_expression -- e.g. `CHECK_OR_RETURN(cond, val)` expands to
# `if (!(cond)) return (val)`. Godot's ERR_FAIL_* family (ERR_FAIL_COND,
# ERR_FAIL_COND_V_MSG, ERR_FAIL_NULL, ...) is the same idiom under a
# different name -- matched by prefix rather than enumerating every
# variant, since upstream adds new _MSG/_V/_EDMSG suffixes regularly.
_CPP_MACRO_EXIT_PREFIXES: tuple = ('ERR_FAIL',)
_CPP_MACRO_EXIT_NAMES: frozenset = frozenset({'CHECK_OR_RETURN'})


def _is_exit_call(callee: Optional[str]) -> bool:
    """True if a call_expression callee name is a known exit idiom (die/exit/raise/fail, C++ error macros)."""
    if callee is None:
        return False
    if callee in _EXIT_CALL_NAMES or callee in _CPP_MACRO_EXIT_NAMES:
        return True
    return callee.startswith(_CPP_MACRO_EXIT_PREFIXES)


# Statement-shaped kinds that can appear as a direct child of a Rust `block`.
# Anything else appearing as the LAST such child (before the closing '}') is
# a bare tail expression -- Rust's implicit-return idiom: no distinguishing
# node kind exists (it's the same expression kinds used everywhere else),
# only its position (last, unwrapped by expression_statement/no semicolon).
_RUST_BLOCK_STATEMENT_KINDS: frozenset = frozenset({
    'expression_statement', 'let_declaration', 'empty_statement',
    'const_item', 'static_item', 'function_item', 'struct_item',
    'enum_item', 'impl_item', 'trait_item', 'mod_item', 'use_declaration',
    'type_item', 'union_item', 'macro_definition', 'macro_invocation',
    'attribute_item', 'inner_attribute_item',
    'line_comment', 'block_comment', '{', '}',
})


def _find_rust_tail_expression(scope_node: Any) -> Optional[Any]:
    """Return the function's implicit-return tail expression node, if any.

    Only called when scope_node's kind is 'function_item' -- Rust's own
    function-node kind, so this never fires for another language's block.
    """
    body = None
    for child in _children(scope_node):
        if _zero_arg(child, 'kind') == 'block':
            body = child
    if body is None:
        return None
    last = None
    for child in _children(body):
        if _zero_arg(child, 'kind') in ('{', '}'):
            continue
        last = child
    if last is not None and _zero_arg(last, 'kind') not in _RUST_BLOCK_STATEMENT_KINDS:
        return last
    return None


# BACK-1482: Ruby returns its last expression, so `def f; if c; 5; else; 6; end; end`
# returns 5 or 6 with no `return` keyword. Branch containers whose value is the
# value of their last statement (the `then`/`else` bodies of if/unless/elsif,
# case `when`, case/in `in_clause`); anything else at the tail is a leaf value.
_RUBY_METHOD_KINDS: frozenset = frozenset({'method', 'singleton_method'})
_RUBY_BRANCH_KINDS: frozenset = frozenset({
    'if', 'unless', 'elsif', 'case', 'case_match', 'when', 'in_clause',
    'then', 'else',
})
# `x if c` / `x unless c`: the value is x (or nil), so x is the tail.
_RUBY_MODIFIER_KINDS: frozenset = frozenset({'if_modifier', 'unless_modifier'})
# Tails that yield no useful value (loops, definitions) or whose
# rescue/ensure flow this does not model: reported as no tail, not guessed at.
_RUBY_NO_TAIL_KINDS: frozenset = frozenset({
    'while', 'until', 'for', 'begin', 'method', 'singleton_method', 'class',
    'module', 'singleton_class', 'comment', 'while_modifier', 'until_modifier',
    'rescue_modifier',
})


def _named_statements(node: Any) -> List[Any]:
    return [c for c in _children(node)
            if _zero_arg(c, 'is_named') and _zero_arg(c, 'kind') != 'comment']


def _ruby_tail_values(node: Any, get_text: Callable,
                      call_node_types: Collection[str]) -> List[Any]:
    """Leaf nodes whose value a Ruby statement evaluates to, branch by branch."""
    kind = _zero_arg(node, 'kind')
    if kind in _RUBY_NO_TAIL_KINDS:
        return []
    if kind in _RUBY_MODIFIER_KINDS:
        body = _named_statements(node)[:1]
        return _ruby_tail_values(body[0], get_text, call_node_types) if body else []
    if kind in _RUBY_BRANCH_KINDS:
        parts = _named_statements(node)
        if kind in ('then', 'else'):
            parts = parts[-1:]
        else:
            parts = [c for c in parts if _zero_arg(c, 'kind') in _RUBY_BRANCH_KINDS]
        values: List[Any] = []
        for part in parts:
            values.extend(_ruby_tail_values(part, get_text, call_node_types))
        return values
    if _exit_at(node, get_text, call_node_types) is not None:
        return []  # an explicit return/raise: already reported, never doubled
    return [node]


def find_tail_expressions(scope_node: Any, get_text: Callable,
                          call_node_types: Collection[str]) -> List[Any]:
    """Implicit-return value nodes of a function whose language returns its
    last expression: Rust's `function_item` tail, Ruby's `method` /
    `singleton_method` last statement (one per if/case branch)."""
    kind = _zero_arg(scope_node, 'kind')
    if kind == 'function_item':
        tail = _find_rust_tail_expression(scope_node)
        return [tail] if tail is not None else []
    if kind in _RUBY_METHOD_KINDS:
        for child in _children(scope_node):
            if _zero_arg(child, 'kind') == 'body_statement':
                stmts = _named_statements(child)
                if stmts and _zero_arg(stmts[-1], 'kind') not in ('rescue', 'ensure'):
                    return _ruby_tail_values(stmts[-1], get_text, call_node_types)
    return []


def _tail_returns(scope_node: Any, from_line: int, to_line: int, get_text: Callable,
                  call_node_types: Collection[str]) -> List[Dict[str, Any]]:
    """RETURN items for the implicit returns of scope_node within a line range."""
    items = []
    for tail in find_tail_expressions(scope_node, get_text, call_node_types):
        tail_line = _zero_arg(tail, 'start_position').row + 1
        if from_line <= tail_line <= to_line:
            text = split_lines(get_text(tail))[0].strip()
            if len(text) > 80:
                text = text[:77] + '...'
            items.append({'kind': 'RETURN', 'line': tail_line, 'text': text})
    return items

_HARD_EXIT_KINDS: frozenset = frozenset({'RETURN', 'RAISE', 'THROW', 'EXIT'})

# YIELD suspends a generator — not a hard exit but transfers control.
_SOFT_EXIT_KINDS: frozenset = frozenset({'BREAK', 'CONTINUE', 'YIELD'})


def _first_line(text: str) -> str:
    text = split_lines(text)[0].strip() if text else ''
    return text[:77] + '...' if len(text) > 80 else text


def _exit_at(node: Any, get_text: Callable,
             call_node_types: Collection[str]) -> Optional[tuple]:
    """(kind, text, descend) when node is an exit, else None -- the one
    definition of "exit" that --exits and --returns (collect_gate_chains) both
    use: an exit node (return/raise/throw/PHP exit_statement...), Rust's `?`,
    an exit call (`die(...)`, `raise X`, `ERR_FAIL_*`), or a bare exit name
    (PHP `die;`, Ruby `raise`). descend: whether the walk continues into it
    (a call's arguments can hold further calls)."""
    ntype = _zero_arg(node, 'kind')
    label = exit_label(node, ntype)
    if label is not None:
        return label, _first_line(get_text(node)), False
    if is_rust_try_operator(node):  # Rust `x?`: an early Err return (BACK-428)
        return 'RETURN', _first_line(get_text(node)), False
    if ntype in call_node_types:
        if _is_exit_call(_extract_callee(node, get_text)):
            return 'EXIT', _first_line(get_text(node)), True
        return None
    name = bare_exit_name(node, get_text)
    return ('EXIT', name, False) if name else None


# Exit execution ownership is deliberately separate from definition/import scope.
# These kinds identify callable syntax, not class/struct aggregate inventories.
_EXIT_CALLABLE_KINDS = {
    'python': frozenset({'function_definition', 'lambda'}),
    'js': frozenset({'function_declaration', 'function_expression', 'arrow_function',
                     'method_definition', 'generator_function', 'generator_function_declaration'}),
    'c': frozenset({'function_definition'}),
    'cpp': frozenset({'function_definition', 'lambda_expression'}),
    'go': frozenset({'function_declaration', 'method_declaration', 'func_literal'}),
    'java': frozenset({'method_declaration', 'constructor_declaration', 'lambda_expression'}),
    'csharp': frozenset({'method_declaration', 'constructor_declaration', 'local_function_statement',
                        'lambda_expression', 'anonymous_method_expression'}),
    'rust': frozenset({'function_item', 'closure_expression'}),
    'ruby': frozenset({'method', 'singleton_method', 'lambda'}),
    'lua': frozenset({'function_declaration', 'function_definition'}),
    'php': frozenset({'function_definition', 'method_declaration', 'anonymous_function', 'arrow_function'}),
    'kotlin': frozenset({'function_declaration', 'anonymous_function', 'secondary_constructor'}),
    'swift': frozenset({'function_declaration', 'lambda_literal', 'init_declaration', 'deinit_declaration'}),
    'dart': frozenset({'function_body', 'function_signature', 'function_expression', 'lambda_expression'}),
    'scala': frozenset({'function_definition'}),
    'gdscript': frozenset({'function_definition', 'constructor_definition', 'lambda'}),
}
_JS_EXIT_LANGUAGES = frozenset(language for language, family in FAMILY_BY_LANGUAGE.items() if family == 'js')
_EXIT_BODY_CHILDREN = frozenset({'function_body', 'function_expression_body', 'statements', 'Block'})
_EXIT_PARAMETER_CHILDREN = frozenset({'parameters', 'formal_parameters', 'parameter_list',
                                    'formal_parameter_list', 'function_value_parameters',
                                    'parameter', 'default_value', 'lambda_function_type'})
_EXIT_DECLARATOR_CHILDREN = frozenset({'function_declarator', 'lambda_declarator',
                                     'constructor_initializer', 'field_initializer_list', 'FnProto'})
_EXIT_CLASS_EVALUATION_KNOWN = frozenset({'python', 'ruby'}) | _JS_EXIT_LANGUAGES
_EXIT_ENTRY_EVALUATION_KNOWN = frozenset({'python', 'ruby', 'kotlin', 'scala'}) | _JS_EXIT_LANGUAGES
_EXIT_CLASS_KINDS = frozenset({'class_declaration', 'class_definition', 'class_specifier',
                              'struct_specifier', 'struct_declaration', 'object_declaration'})


def _exit_callable(node: Any, language: str) -> bool:
    kind = _zero_arg(node, 'kind')
    if language == 'zig':
        parts = {_zero_arg(c, 'kind') for c in _children(node)} if kind == 'Decl' else set()
        return {'FnProto', 'Block'} <= parts
    key = 'js' if language in _JS_EXIT_LANGUAGES else language
    return _zero_arg(node, 'is_named') and kind in _EXIT_CALLABLE_KINDS.get(key, ())


def _field_is(node: Any, child: Any, name: str) -> bool:
    value = node.child_by_field_name(name)
    return value is not None and _same_span(value, child)


def _body_edge(node: Any, child: Any) -> bool:
    return (_field_is(node, child, 'body') or _zero_arg(child, 'kind') in _EXIT_BODY_CHILDREN
            or (_zero_arg(node, 'kind') == 'function_body' and _zero_arg(child, 'kind') == 'block'))


def _parameter_edge(node: Any, child: Any) -> bool:
    return (_field_is(node, child, 'parameters') or _field_is(node, child, 'parameter')
            or _zero_arg(child, 'kind') in _EXIT_PARAMETER_CHILDREN)


def _js_deferred_field(node: Any, child: Any) -> bool:
    if _zero_arg(node, 'kind') not in {'field_definition', 'public_field_definition', 'property_definition'}:
        return False
    return _field_is(node, child, 'value') and not any(
        _zero_arg(c, 'kind') == 'static' for c in _children(node))


def _first_generator_clause(node: Any) -> bool:
    previous = _prev_sibling(node)
    while previous is not None:
        if _zero_arg(previous, 'kind') == 'for_in_clause':
            return False
        previous = _prev_sibling(previous)
    return True


def _generator_deferred_edge(node: Any, child: Any) -> bool:
    """Only a generator's leftmost iterable operand is evaluated at formation."""
    kind = _zero_arg(node, 'kind')
    if kind == 'generator_expression':
        return _zero_arg(child, 'kind') != 'for_in_clause' or not _first_generator_clause(child)
    if kind == 'for_in_clause':
        parent = _zero_arg(node, 'parent')
        if parent is not None and _zero_arg(parent, 'kind') == 'generator_expression':
            return not (_first_generator_clause(node) and _field_is(node, child, 'right'))
    return False


def _language_exit_uncertainty(language: str, node: Any, child: Any) -> Optional[str]:
    kind = _zero_arg(child, 'kind')
    if language == 'python' and _generator_deferred_edge(node, child):
        return 'Python generator region execution is deferred until iteration'
    if language == 'rust' and kind == 'async_block':
        return 'Rust async block execution is deferred until the future is polled'
    if language == 'ruby' and kind in {'block', 'do_block'}:
        return 'Ruby block return ownership depends on callable binding'
    if language == 'kotlin' and kind == 'lambda_literal':
        return 'Kotlin lambda return ownership depends on inline and label semantics'
    if language == 'scala' and kind == 'lambda_expression':
        return 'Scala nonlocal-return language-version support is not qualified'
    return None


class ExitOwnershipSite(TypedDict):
    line: int
    kind: str
    text: str
    start_byte: int
    end_byte: int
    region_start: int
    region_end: int
    cause: str


class _ExitScopeRequired(TypedDict):
    mode: Literal['selected_callable', 'source_scope']
    language: str
    rule: str


class ExitScope(_ExitScopeRequired, total=False):
    unresolved_sites: List[ExitOwnershipSite]
    reason: str
    site_byte_basis: str
    implicit_tail_rule: str


class ExitOwnershipWarning(WarningEntry, total=False):
    sites: List[ExitOwnershipSite]


@dataclass
class ExitOwnership:
    """Request-local callable execution scope, with unresolved recorded-site evidence.

    An absent record leaves the library collectors' source-scope inventory unchanged.
    """
    language: str
    scope_node: Any
    unresolved_sites: List[ExitOwnershipSite] = field(default_factory=list)
    mode: Literal['selected_callable', 'source_scope'] = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        qualified = _exit_callable(self.scope_node, self.language)
        if self.language == 'dart' and _zero_arg(self.scope_node, 'kind') == 'function_signature':
            qualified = False  # A resolved signature alone has no invocation body.
        self.mode = 'selected_callable' if qualified else 'source_scope'
        if self.mode == 'selected_callable':
            self.reason = 'verified_callable_syntax'
        elif _zero_arg(self.scope_node, 'parent') is None:
            self.reason = 'source_root_inventory'
        elif _zero_arg(self.scope_node, 'kind') in MEMBER_CONTAINER_NODES:
            self.reason = 'aggregate_scope_inventory'
        else:
            self.reason = 'unqualified_resolved_scope'

    def reset(self) -> None:
        """Start one collection; previously returned metadata remains a snapshot."""
        self.unresolved_sites.clear()

    def selected(self, node: Any) -> bool:
        return (_zero_arg(node, 'kind') == _zero_arg(self.scope_node, 'kind')
                and _same_span(node, self.scope_node))

    def allows(self, node: Any, child: Any) -> bool:
        if self.mode == 'source_scope':
            return True
        if self.selected(node):
            return self._selected_edge(node, child)
        if self.language in _JS_EXIT_LANGUAGES and _js_deferred_field(node, child):
            return False
        if not _exit_callable(node, self.language):
            return True
        if self.language == 'python':
            return not _body_edge(node, child)
        if self.language == 'dart' and _zero_arg(node, 'kind') == 'function_body':
            return False
        return not (_body_edge(node, child) or _parameter_edge(node, child)
                    or _zero_arg(child, 'kind') in _EXIT_DECLARATOR_CHILDREN)

    def _selected_edge(self, node: Any, child: Any) -> bool:
        if self.language == 'python':
            return _body_edge(node, child)
        if self.language in _JS_EXIT_LANGUAGES or self.language == 'ruby':
            return _body_edge(node, child) or _parameter_edge(node, child)
        return _zero_arg(child, 'kind') not in {'lambda_capture_specifier', 'capture_list'}

    def context(self, node: Any, child: Any, inherited: Optional[Tuple[str, int, int]]) -> Optional[Tuple[str, int, int]]:
        if self.mode == 'source_scope':
            return None
        kind = _zero_arg(child, 'kind')
        cause = _language_exit_uncertainty(self.language, node, child)
        if cause is None and kind in _EXIT_CLASS_KINDS and self.language not in _EXIT_CLASS_EVALUATION_KNOWN:
            cause = 'Local aggregate initializer execution ownership is not qualified'
        elif (cause is None and self.selected(node) and not _body_edge(node, child)
              and self.language not in _EXIT_ENTRY_EVALUATION_KNOWN):
            cause = 'Invocation-associated header execution ownership is not qualified'
        if cause is None:
            return inherited
        return cause, _zero_arg(child, 'start_position').row + 1, _zero_arg(child, 'end_position').row + 1

    def record(self, node: Any, kind: str, text: str, context: Optional[Tuple[str, int, int]]) -> None:
        if context is None:
            return
        cause, start, end = context
        site: ExitOwnershipSite = {'line': _zero_arg(node, 'start_position').row + 1,
                                   'kind': kind, 'text': text,
                                   'start_byte': _zero_arg(node, 'start_byte'),
                                   'end_byte': _zero_arg(node, 'end_byte'),
                                   'region_start': start, 'region_end': end, 'cause': cause}
        if site not in self.unresolved_sites:
            self.unresolved_sites.append(site)

    def scope_metadata(self) -> ExitScope:
        data: ExitScope = {'mode': self.mode, 'language': self.language, 'reason': self.reason,
                'rule': ('Candidate execution-region sites; verified nested bodies excluded; unresolved sites retained with diagnostics'
                         if self.mode == 'selected_callable' else
                         'Source-scope inventory may include sites from multiple callable owners'),
                'implicit_tail_rule': 'Implicit tail returns are inferred only for the resolved scope, '
                                      'not for nested callable scopes.'}
        if self.unresolved_sites:
            data['unresolved_sites'] = [site.copy() for site in self.unresolved_sites]
            data['site_byte_basis'] = 'parser_source'
        return data

    def warnings(self) -> List[ExitOwnershipWarning]:
        warnings: List[ExitOwnershipWarning] = []
        if self.unresolved_sites:
            sites = ', '.join(f"L{s['line']} {s['kind']} {s['text']}" for s in self.unresolved_sites)
            warnings.append({'type': 'ownership_unresolved',
                             'message': f'Execution ownership is unresolved for recorded sites at {sites}; '
                                        'review their source regions before attributing them to this callable.',
                             'sites': [site.copy() for site in self.unresolved_sites]})
        if self.reason == 'unqualified_resolved_scope':
            warnings.append({'type': 'ownership_scope_limited',
                             'message': 'Callable ownership is not qualified for this resolved scope; '
                                        'the result is a source-scope inventory and can cross callable owners.'})
        if (self.mode == 'selected_callable' and self.language == 'dart'
                and _zero_arg(self.scope_node, 'kind') == 'function_body'):
            warnings.append({'type': 'ownership_scope_limited',
                             'message': 'Dart navigation resolved a function body; signature and constructor '
                                        'initializer context is not available here. Use a source-region '
                                        'inventory to inspect that syntax.'})
        return warnings


def _exit_children(node: Any, ownership: Optional[ExitOwnership], context=None):
    """The existing traversal's next direct children and their ownership context."""
    for child in _children(node):
        if ownership is None or ownership.allows(node, child):
            yield child, ownership.context(node, child, context) if ownership else None


def collect_exits(
    scope_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
    call_node_types: Optional[Collection[str]] = None,
    *,
    ownership: Optional[ExitOwnership] = None,
) -> List[Dict[str, Any]]:
    """Collect exit nodes within a line range.

    Without ownership this is a source-scope inventory. ExitOwnership narrows
    verified callable execution edges without changing the list record shape.

    Each item is a dict:
        kind -- 'RETURN', 'RAISE', 'THROW', 'YIELD', 'BREAK', 'CONTINUE', or 'EXIT'
        line -- 1-indexed line number
        text -- first line of the node's source text (truncated to 80 chars)
    """
    if ownership is not None:
        ownership.reset()
    if call_node_types is None:
        from ...treesitter import CALL_NODE_TYPES  # noqa: PLC0415
        call_node_types = CALL_NODE_TYPES

    results: List[Dict[str, Any]] = []
    stack = list(reversed(list(_exit_children(scope_node, ownership))))
    while stack:
        node, context = stack.pop()
        line = _zero_arg(node, 'start_position').row + 1
        if _zero_arg(node, 'end_position').row + 1 < from_line or line > to_line:
            continue

        if from_line <= line <= to_line:
            found = _exit_at(node, get_text, call_node_types)
            if found is not None:
                kind, text, descend = found
                results.append({'kind': kind, 'line': line, 'text': text})
                if ownership is not None:
                    ownership.record(node, kind, text, context)
                if not descend:
                    continue

        stack.extend(reversed(list(_exit_children(node, ownership, context))))

    results.extend(_tail_returns(scope_node, from_line, to_line, get_text, call_node_types))

    results.sort(key=lambda r: r['line'])
    return results


def render_exits(
    exits: List[Dict[str, Any]],
    from_line: int,
    to_line: int,
    verdict: bool = False,
) -> str:
    """Render collect_exits results."""
    lines: List[str] = []
    if not exits:
        lines.append(f'No exits in L{from_line}→L{to_line}')
    else:
        for e in exits:
            lines.append(f'{e["kind"]:<10}L{e["line"]}:  {e["text"]}')

    if verdict:
        has_hard = any(e['kind'] in _HARD_EXIT_KINDS for e in exits)
        has_soft = any(e['kind'] in _SOFT_EXIT_KINDS for e in exits)
        if has_hard:
            v = '⚠ BLOCKED'
        elif has_soft:
            v = '~ CONDITIONAL'
        else:
            v = '✓ CLEAR'
        lines.append(f'\nflowto L{to_line}: {v}')

    return '\n'.join(lines)


def _unbound_range_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Exclude inner-owned bindings without hiding same-spelled outer reads.

    Whole closures own their parameters; an extracted body still needs a
    parameter declared outside the selected range.
    """
    owned = {e.get('binding_scope') for e in events
             if e['kind'] == 'WRITE' and e.get('binding_scope') is not None}
    return [e for e in events if e.get('binding_scope') not in owned]


def collect_deps(
    scope_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
    language: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Identify variables that flow INTO a line range (potential function parameters).

    A variable is a dep if its first event in the range is a READ.
    """
    all_events = all_var_flow(scope_node, from_line, to_line, get_text)
    deps: List[Dict[str, Any]] = []
    builtins = conventions_for(FAMILY_BY_LANGUAGE.get(language or '', language or '')).builtins
    bindings = BindingScope(scope_node, get_text, language)
    for var_name, events in all_events.items():
        in_range = [e for e in events if from_line <= e['line'] <= to_line]
        if not in_range:
            continue
        visible = _unbound_range_events(in_range)
        if not visible:
            continue
        first_in_range = visible[0]
        if first_in_range['kind'].startswith('READ'):
            first_write = next((e for e in visible if e['kind'] == 'WRITE'), None)
            dep = {
                'var': var_name,
                'first_read_line': first_in_range['line'],
                'first_write_line': first_write['line'] if first_write else None,
            }
            if var_name in builtins and not bindings.has_explicit_binding(
                    var_name, first_in_range['node']):
                dep['classification'] = 'builtin'
            deps.append(dep)
    deps.sort(key=lambda d: d['first_read_line'])
    return deps


def collect_mutations(
    scope_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
) -> List[Dict[str, Any]]:
    """Identify variables written in a range that are read after it (potential returns)."""
    full_to = _zero_arg(scope_node, 'end_position').row + 1
    all_events = all_var_flow(
        scope_node, from_line, to_line, get_text, full_to=full_to
    )
    mutations: List[Dict[str, Any]] = []
    for var_name, events in all_events.items():
        in_range = [e for e in events if from_line <= e['line'] <= to_line]
        after_range = [e for e in events if e['line'] > to_line]
        writes_in = [e for e in in_range if e['kind'] == 'WRITE'
                     and any(later.get('binding_scope') == e.get('binding_scope')
                             for later in after_range)]
        if writes_in:
            owners = {e.get('binding_scope') for e in writes_in}
            after_range = [e for e in after_range if e.get('binding_scope') in owners]
            last_write = max(writes_in, key=lambda e: e['line'])
            next_read = min(after_range, key=lambda e: e['line'])
            mutations.append({
                'var': var_name,
                'last_write_line': last_write['line'],
                'next_read_line': next_read['line'],
            })
    mutations.sort(key=lambda m: m['last_write_line'])
    return mutations


def render_deps(
    deps: List[Dict[str, Any]],
    from_line: int,
    to_line: int,
) -> str:
    """Render collect_deps results."""
    if not deps:
        return f'No dependencies flowing into L{from_line}→L{to_line}'
    lines: List[str] = []
    for d in deps:
        write_info = (
            f'  (first write L{d["first_write_line"]})'
            if d['first_write_line'] is not None
            else '  (never written in range)'
        )
        label = 'BUILTIN' if d.get('classification') == 'builtin' else 'PARAM'
        lines.append(
            f'{label}  {d["var"]:<30}  first read L{d["first_read_line"]}{write_info}'
        )
    return '\n'.join(lines)


def render_mutations(
    mutations: List[Dict[str, Any]],
    from_line: int,
    to_line: int,
) -> str:
    """Render collect_mutations results."""
    if not mutations:
        return (
            f'No read-after-write hazards in L{from_line}→L{to_line}.\n'
            f'  (--outputs: variables written here and read after — potential return values)\n'
            f'  To see all writes to a specific variable: reveal <file> <func> --varflow <var>'
        )
    lines: List[str] = []
    for m in mutations:
        lines.append(
            f'RETURN {m["var"]:<30}  written L{m["last_write_line"]},'
            f' next read L{m["next_read_line"]}'
        )
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# BACK-200: --returns gate-chain walker
# ---------------------------------------------------------------------------

# See node_taxonomy.GATE_NODES for the definition and per-kind field-shape notes.
_GATE_NODE_TYPES: frozenset = GATE_NODES


def _positional_if_parts(node: Any):
    """Dart's ordinary if header span and bodies, without guessing patterns."""
    if (_zero_arg(node, 'kind') != 'if_statement' or
            node.child_by_field_name('condition') is not None):
        return None
    children = [c for c in _children(node)
                if _zero_arg(c, 'kind') not in ('comment', 'line_comment', 'block_comment')]
    if [_zero_arg(c, 'kind') for c in children[:2]] != ['if', '(']:
        return None
    close = next((i for i, c in enumerate(children) if _zero_arg(c, 'kind') == ')'), None)
    if close is None:
        return None
    condition, bodies = children[2:close], children[close + 1:]
    if not condition or not all(_zero_arg(c, 'is_named') for c in condition):
        return None
    selected = _positional_if_bodies(node, bodies)
    if selected is None:
        return None
    return condition[0], condition[-1], *selected


def _positional_if_bodies(node: Any, bodies: List[Any]):
    """Verify the positional tail agrees with the existing branch fields."""
    if len(bodies) not in (1, 3) or not _zero_arg(bodies[0], 'is_named'):
        return None
    alternative = None
    if len(bodies) == 3:
        if _zero_arg(bodies[1], 'kind') != 'else' or not _zero_arg(bodies[2], 'is_named'):
            return None
        alternative = bodies[2]
    expected = [node.child_by_field_name(field) for field in ('consequence', 'alternative')]
    expected_spans = [(_zero_arg(c, 'start_byte'), _zero_arg(c, 'end_byte'))
                      for c in expected if c is not None]
    body_spans = [(_zero_arg(c, 'start_byte'), _zero_arg(c, 'end_byte'))
                  for c in (bodies[0], alternative) if c is not None]
    if body_spans != expected_spans:
        return None
    return bodies[0], alternative


def _branch_parts(node: Any):
    """Condition and selected bodies, including Zig's fieldless prefix shape."""
    condition = node.child_by_field_name('condition')
    consequence = node.child_by_field_name('consequence')
    if consequence is None:
        consequence = node.child_by_field_name('body')
    alternative = node.child_by_field_name('alternative')
    if _zero_arg(node, 'kind') in ('IfStatement', 'IfExpr'):
        children = _children(node)
        prefix = next((c for c in children if _zero_arg(c, 'kind') == 'IfPrefix'), None)
        if prefix is not None:
            condition = next((c for c in _children(prefix) if _zero_arg(c, 'is_named')), None)
            bodies = [c for c in children if _zero_arg(c, 'is_named') and not _same_span(c, prefix)]
            consequence = bodies[0] if bodies else None
            alternative = bodies[1] if len(bodies) > 1 else None
    return condition, consequence, alternative


def _get_condition(node: Any, get_text: Callable) -> Optional[Dict[str, Any]]:
    """Extract condition text + line from a control-flow node."""
    cond, _, _ = _branch_parts(node)
    positional = _positional_if_parts(node)
    if positional is not None:
        first, last, _, _ = positional
        start = _zero_arg(first, 'start_byte') - _zero_arg(node, 'start_byte')
        end = _zero_arg(last, 'end_byte') - _zero_arg(node, 'start_byte')
        text = get_text(node).encode('utf-8')[start:end].decode('utf-8').strip()
        line = _zero_arg(first, 'start_position').row + 1
        return {'line': line, 'text': text[:57] + '...' if len(text) > 60 else text}
    if cond is None:
        # An unrecognized Dart token header (for example if-case) must not
        # inherit the PHP parenthesized-expression fallback below.
        if (_zero_arg(node, 'kind') == 'if_statement' and
                any(_zero_arg(c, 'kind') == '(' for c in _children(node))):
            return None
        # PHP: condition is a parenthesized_expression positional child
        for child in _children(node):
            if _zero_arg(child, 'kind') == 'parenthesized_expression':
                cond = child
                break
    if cond is None:
        return None
    text = get_text(cond).strip()
    if text.startswith('(') and text.endswith(')'):
        text = text[1:-1].strip()
    # Ruby `unless`/`until` (and their modifiers) invert the sense — the body
    # runs when the condition is FALSE, so a bare condition text reads
    # backwards. Prefix the keyword so the gate line is honest (BACK-500).
    kind = _zero_arg(node, 'kind')
    if kind in ('unless', 'unless_modifier', 'until', 'until_modifier'):
        text = f'{kind.split("_")[0]} {text}'
    if len(text) > 60:
        text = text[:57] + '...'
    return {'line': _zero_arg(cond, 'start_position').row + 1, 'text': text}


def _same_span(left: Any, right: Any) -> bool:
    """Bindings at the language-pack floor compare nodes by identity."""
    return right is not None and all(
        _zero_arg(left, field) == _zero_arg(right, field)
        for field in ('start_byte', 'end_byte')
    )


def _branch_gates(node: Any, gates: List[Dict[str, Any]], get_text: Callable):
    """Route gates to branch bodies, retaining failed sibling tests in order.

    Python/PHP keep elif arms as siblings; Ruby nests them, while other
    grammars put another if inside the alternative. Use fields and the shared
    taxonomy for all three shapes rather than interpreting source keywords.
    """
    condition = _get_condition(node, get_text)
    _, consequence, alternative = _branch_parts(node)
    remaining = gates + [dict(condition, text=f'not ({condition["text"]})')] if condition else gates
    for child in _children(node):
        kind = _zero_arg(child, 'kind')
        if _zero_arg(child, 'is_named') and (
                kind in ELIF_NODES | ELSE_NODES or _same_span(child, alternative)):
            yield child, remaining
            # Flat sibling elif chains must carry every earlier failed test.
            if kind in ELIF_NODES:
                test = _get_condition(child, get_text)
                if test:
                    remaining = remaining + [dict(test, text=f'not ({test["text"]})')]
        elif _same_span(child, consequence):
            yield child, gates + [condition] if condition else gates
        else:
            # Conditions and initializers run before the branch is selected.
            yield child, gates



def _try_children(node: Any, gates: List[Dict[str, Any]]):
    """Dart's sibling handler headers own only their next block, not finally.

    Other try_statement grammars nest their handler body inside the clause;
    those children pass through to the normal handler dispatch unchanged.
    """
    header = None
    for child in _children(node):
        kind = _zero_arg(child, 'kind')
        if kind == 'on' or (kind == 'catch_clause' and
                            child.child_by_field_name('body') is None):
            if header is None:
                header = child
        context = gates
        if kind == 'block' and header is not None:
            context = gates + [{'line': _zero_arg(header, 'start_position').row + 1,
                                'text': 'on exception'}]
            header = None
        yield child, context


def _gated_children(node: Any, gates: List[Dict[str, Any]], get_text: Callable):
    """Child contexts for branch selection, loops and exception handlers."""
    kind = _zero_arg(node, 'kind')
    if (kind in IF_NODES | ELIF_NODES and _zero_arg(node, 'is_named') and
            _branch_parts(node)[1] is not None):
        yield from _branch_gates(node, gates, get_text)
        return

    catch = zig_catch_parts(node)
    if catch is not None:
        header, handler = catch
        context = gates + [{'line': _zero_arg(header, 'start_position').row + 1,
                            'text': 'on exception'}]
        for child in _children(node):
            yield child, context if _same_span(child, handler) else gates
        return

    if kind == 'try_statement':
        yield from _try_children(node, gates)
        return

    context = gates
    handler = None
    if kind in EXCEPT_NODES | CATCH_NODES and _zero_arg(node, 'is_named'):
        context = gates + [{'line': _zero_arg(node, 'start_position').row + 1,
                            'text': 'on exception'}]
        # Ruby's rescue modifier has a normal body and a handler expression.
        handler = node.child_by_field_name('handler')
    elif kind in _GATE_NODE_TYPES:
        cond = _get_condition(node, get_text)
        context = gates + [cond] if cond else gates
    for child in _children(node):
        yield child, context if handler is None or _same_span(child, handler) else gates


def collect_gate_chains(
    scope_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
    call_node_types: Optional[Collection[str]] = None,
    *,
    ownership: Optional[ExitOwnership] = None,
) -> List[Dict[str, Any]]:
    """Collect exit nodes in a line range, each annotated with their gate chain.

    Optional ownership uses the same execution-edge policy as collect_exits.

    Each result dict:
        kind  -- exit kind ('RETURN', 'EXIT', 'RAISE', etc.)
        line  -- 1-indexed line
        text  -- source text of the exit statement
        gates -- list of {line, text} dicts, innermost-last
    """
    if ownership is not None:
        ownership.reset()
    if call_node_types is None:
        from ...treesitter import CALL_NODE_TYPES  # noqa: PLC0415
        call_node_types = CALL_NODE_TYPES

    results: List[Dict[str, Any]] = []

    def walk(node: Any, gates: List[Dict[str, Any]], context=None) -> None:
        line = _zero_arg(node, 'start_position').row + 1
        if _zero_arg(node, 'end_position').row + 1 < from_line or line > to_line:
            return

        if from_line <= line <= to_line:
            found = _exit_at(node, get_text, call_node_types)
            if found is not None:
                kind, text, descend = found
                results.append({'kind': kind, 'line': line, 'text': text, 'gates': gates[:]})
                if ownership is not None:
                    ownership.record(node, kind, text, context)
                if not descend:
                    return

        for child, child_gates in _gated_children(node, gates, get_text):
            if ownership is None or ownership.allows(node, child):
                walk(child, child_gates, ownership.context(node, child, context) if ownership else None)

    walk(scope_node, [])

    results.extend({**item, 'gates': []} for item in _tail_returns(
        scope_node, from_line, to_line, get_text, call_node_types))

    results.sort(key=lambda r: r['line'])
    return results


def render_gate_chains(
    chains: List[Dict[str, Any]],
    from_line: int,
    to_line: int,
) -> str:
    """Render collect_gate_chains output."""
    if not chains:
        return 'Exit sites (static)\nNo exits recorded in this selection.'
    counts: Dict[str, int] = {}
    for item in chains:
        counts[item['kind']] = counts.get(item['kind'], 0) + 1
    lines: List[str] = ['Exit sites (static)', ', '.join(f'{kind}: {count}' for kind, count in counts.items())]
    for item in chains:
        gates = item['gates']
        lines.append(f'{item["kind"]:<10}L{item["line"]}:  {item["text"]}')
        for g in gates:
            lines.append(f'          gate: {g["text"]} (L{g["line"]})')
        lines.append('')
    return '\n'.join(lines).rstrip()
