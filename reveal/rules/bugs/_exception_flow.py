"""Does a handler hand the caught exception to the caller or to a reporting sink? (B006)

A handler that passes the exception on is not silent: ``listener.onFailure(e)``,
``res.status(500).json({error: e.message})``, ``assert.strictEqual(e.message, 'x')``.  A handler
that only computes something from it is: ``return isinstance(e, KeyError)``, ``return len(e.args)``.
The two are told apart by two questions, neither of which looks at corpus-specific names:

1. What is the callee's role?  (``callee_role``) A callee is *silent* when it keeps, logs at debug
   level, discards, or computes a scalar from its argument (language builtins, pure namespaces such as
   ``Objects`` and ``Object``, predicate-shaped names such as ``isRetryable``).  A *converter*
   (``str``, ``String``, ``JSON.stringify``) returns the exception's text: a handler that only returns
   it hides the failure, but a reporting call that receives it still discloses it.  An *assertion*
   consumes the exception to check it, so any mention counts.  Everything else is an *effect*.
2. Does the exception's content flow into the call?  (``py_carries`` / ``ts_carries``) It does through
   payload-preserving wrappers (attribute access, f-strings, ``new X(e)``, ``{error: e}``, the branches
   of a conditional) and does not through a computation (``len(e.args)``, ``e instanceof T``,
   ``e.code === 404``).

The role tables are categories of the language, not names seen in a corpus (BACK-1835).
"""

import ast
import re
from typing import Any, Callable, Iterable, List, Optional, Sequence, Tuple

from ...core import node_children, _zero_arg

# Debug-level or verbose logging is invisible in a normal run (BACK-983).
_LOG_LEVEL = frozenset({
    'debug', 'trace', 'info', 'notice', 'verbose', 'log', 'fine', 'finer', 'finest', 'd', 'v', 'i',
})
# Sinks that keep the exception without reading it: collecting is not disclosing.
_STORAGE = frozenset({
    'add', 'addAll', 'addFirst', 'addLast', 'append', 'push', 'put', 'offer', 'insert', 'extend',
    'set', 'compareAndSet', 'update', 'remove', 'removeAll', 'delete', 'pop', 'put_nowait',
    'increment', 'decrement', 'setattr', 'delattr', 'requireNonNull', 'checkNotNull', 'identity',
})
# Callees that reduce their argument to a value that no longer says what failed.  Per language,
# because a name means different things: Python's ``next(it)`` is a builtin, Express's ``next(err)``
# forwards the error.  Builtins count only as bare calls; methods that look a value up by key count
# on any receiver.
_PY_BUILTINS = frozenset({
    'abs', 'all', 'any', 'bin', 'bool', 'callable', 'chr', 'dir', 'divmod', 'enumerate', 'filter',
    'float', 'getattr', 'hasattr', 'hash', 'hex', 'id', 'int', 'isinstance', 'issubclass', 'iter',
    'len', 'map', 'max', 'min', 'next', 'oct', 'ord', 'pow', 'range', 'reversed', 'round', 'sorted',
    'sum', 'type', 'vars', 'zip',
})
_JS_BUILTINS = frozenset({'Boolean', 'Number', 'isNaN', 'isFinite', 'parseInt', 'parseFloat'})
_LOOKUPS = {
    'py': frozenset({'get', 'count', 'index'}),
    'js': frozenset({'resolve', 'isArray', 'indexOf', 'includes', 'has', 'get'}),
    'java': frozenset({'ofNullable', 'hashCode', 'equals', 'compare', 'compareTo', 'indexOf', 'get',
                       'getOrDefault', 'containsKey', 'nonNull'}),
}
_BUILTINS = {'py': _PY_BUILTINS, 'js': _JS_BUILTINS, 'java': frozenset()}
# Namespaces whose members compute a value from their argument.
_PURE_NAMESPACES = frozenset({
    'Object', 'Array', 'Number', 'Math', 'Boolean', 'Symbol', 'Reflect',
    'Objects', 'Integer', 'Long', 'Double', 'Optional', 'Arrays', 'Collections',
})
# Callees that turn the exception into its text.
_CONVERTERS = frozenset({
    'str', 'repr', 'ascii', 'format', 'String', 'valueOf', 'toString', 'stringify', 'dumps',
    'format_exception', 'format_exc',
})
_DISCARD_PREFIXES = ('ignore', 'swallow', 'suppress', 'discard')
# isFoo / is_foo / hasFoo / canFoo ...: a predicate, whatever it is called after the prefix.
_PREDICATE_NAME = re.compile(r'^(is|has|can|should|contains|equals|matches|starts|ends)(?=[A-Z_0-9]|$)')
# debugMessage / debug_log / verboseLog: level-gated logging, invisible in a normal run.  Not `trace`:
# traceError(e) is an error-logging helper, not a trace-level call.
_LOG_LEVEL_NAME = re.compile(r'^(?i:debug|verbose)(?=[A-Z_0-9]|$)')
_ASSERTION_NAME = re.compile(r'^(assert|expect|verify)', re.IGNORECASE)
_ASSERTION_RECEIVERS = frozenset({'assert', 'expect', 'should', 'chai', 'assertions'})


def _reduces(name: str, receiver: Optional[str], lang: Optional[str]) -> bool:
    langs = (lang,) if lang else tuple(_LOOKUPS)
    return any(name in _LOOKUPS[l] or (receiver is None and name in _BUILTINS[l]) for l in langs)


def callee_role(name: Optional[str], receiver: Optional[str], lang: Optional[str] = None) -> str:
    """'silent', 'converter', 'assertion' or 'effect' for a call to ``receiver.name``.

    ``receiver`` is None for a bare call and '' for a call on something that is not a plain name.
    ``lang`` ('py', 'js', 'java') selects the language's reducer tables; None accepts any."""
    if not name:
        return 'effect'
    if name.lower().startswith(_DISCARD_PREFIXES):
        return 'silent'
    if _ASSERTION_NAME.match(name) or (receiver or '').lower() in _ASSERTION_RECEIVERS:
        return 'assertion'
    if name in _CONVERTERS:
        return 'converter'
    if name in _LOG_LEVEL or name in _STORAGE or _reduces(name, receiver, lang) or _PREDICATE_NAME.match(name) \
            or _LOG_LEVEL_NAME.match(name):
        return 'silent'
    if receiver in _PURE_NAMESPACES:
        return 'silent'
    return 'effect'


def _forwards(role: str, operands: Sequence[Any], carries: Callable[[Any], bool],
              mentions: Callable[[Any], bool]) -> bool:
    if role in ('silent', 'converter'):
        return False
    check = mentions if role == 'assertion' else carries
    return any(check(op) for op in operands)


# --- Python ---------------------------------------------------------------------------------

_PY_DEFERRED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def _py_executed(root: ast.AST) -> Iterable[ast.AST]:
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, _PY_DEFERRED):
            continue
        yield node
        stack.extend(ast.iter_child_nodes(node))


def _py_call_parts(call: ast.Call) -> Tuple[Optional[str], Optional[str], List[ast.AST]]:
    func = call.func
    if isinstance(func, ast.Attribute):
        name = func.attr
        receiver = func.value.id if isinstance(func.value, ast.Name) else ''
    elif isinstance(func, ast.Name):
        name, receiver = func.id, None
    else:
        name, receiver = None, None
    return name, receiver, [*call.args, *(kw.value for kw in call.keywords)]


def _py_mentions(node: ast.AST, caught: str) -> bool:
    return any(isinstance(n, ast.Name) and n.id == caught for n in _py_executed(node))


def py_carries(node: Optional[ast.AST], caught: str) -> bool:
    """True if the value of ``node`` can carry what the caught exception says."""
    if isinstance(node, ast.Name):
        return node.id == caught
    if isinstance(node, (ast.Attribute, ast.Subscript, ast.Starred, ast.Await, ast.FormattedValue)):
        return py_carries(node.value, caught)
    if isinstance(node, ast.Call):
        name, receiver, operands = _py_call_parts(node)
        if callee_role(name, receiver, 'py') == 'silent':
            return False
        return (any(py_carries(op, caught) for op in operands)
                or (isinstance(node.func, ast.Attribute) and py_carries(node.func.value, caught)))
    if isinstance(node, ast.JoinedStr):
        return any(py_carries(v, caught) for v in node.values)
    if isinstance(node, ast.BinOp):
        return py_carries(node.left, caught) or py_carries(node.right, caught)
    if isinstance(node, ast.BoolOp):
        return any(py_carries(v, caught) for v in node.values)
    if isinstance(node, ast.IfExp):
        return py_carries(node.body, caught) or py_carries(node.orelse, caught)
    if isinstance(node, ast.Dict):
        return any(py_carries(v, caught) for v in node.values)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return any(py_carries(v, caught) for v in node.elts)
    return False


def py_forwards(value: Optional[ast.AST], caught: Optional[str]) -> bool:
    """A statement or returned call (awaited or not) that hands the exception on."""
    if isinstance(value, ast.Await):
        value = value.value
    if not caught or not isinstance(value, ast.Call):
        return False
    name, receiver, operands = _py_call_parts(value)
    if _forwards(callee_role(name, receiver, 'py'), operands,
                 lambda op: py_carries(op, caught), lambda op: _py_mentions(op, caught)):
        return True
    return _py_chain_asserts(value, caught)


def _py_chain_asserts(call: ast.Call, caught: str) -> bool:
    """``assertThat(e).is_equal_to(x)``: an assertion earlier in the receiver chain consumes e."""
    node = call.func
    while isinstance(node, ast.Attribute):
        node = node.value
        if isinstance(node, ast.Call):
            name, receiver, operands = _py_call_parts(node)
            if callee_role(name, receiver, 'py') == 'assertion' and any(_py_mentions(op, caught) for op in operands):
                return True
            node = node.func
    return False


# --- tree-sitter (JavaScript, TypeScript, Java) ---------------------------------------------

_TS_DEFERRED = frozenset({
    'lambda_expression', 'arrow_function', 'function_declaration', 'function_expression',
    'generator_function', 'generator_function_declaration', 'method_declaration',
    'method_definition', 'class_declaration', 'class_body', 'function',
})
# Containers whose children are the value (types and tokens never match an identifier).
_TS_CARRY_ALL = frozenset({
    'parenthesized_expression', 'await_expression', 'as_expression', 'non_null_expression',
    'type_assertion', 'satisfies_expression', 'spread_element', 'array', 'object',
    'template_string', 'template_substitution', 'sequence_expression', 'array_initializer',
    'cast_expression', 'argument_list', 'arguments',
})
_TS_CALL_KINDS = frozenset({'call_expression', 'method_invocation'})
_TS_NEW_KINDS = frozenset({'new_expression', 'object_creation_expression'})
_TS_CARRY_OPERATORS = frozenset({'+', '||', '??', '&&'})
_JAVA_CALL_KINDS = frozenset({'method_invocation', 'object_creation_expression'})


def _ts_role(node, name: Optional[str], receiver: Optional[str]) -> str:
    return callee_role(name, receiver, 'java' if _kind(node) in _JAVA_CALL_KINDS else 'js')


def _kind(node) -> str:
    kind: str = _zero_arg(node, 'kind')
    return kind


def ts_executed(root) -> Iterable[Any]:
    stack = [root]
    while stack:
        node = stack.pop()
        if _kind(node) in _TS_DEFERRED:
            continue
        yield node
        stack.extend(node_children(node))


def ts_mentions(node, caught: str, text: Callable[[Any], str]) -> bool:
    return any(_kind(n) in ('identifier', 'shorthand_property_identifier') and text(n) == caught
               for n in ts_executed(node))


def _ts_operands(node) -> List[Any]:
    args = next((c for c in node_children(node) if _kind(c) in ('arguments', 'argument_list')), None)
    return [c for c in node_children(args) if _kind(c) not in ('(', ')', ',')] if args else []


def _ts_object_name(obj, text: Callable[[Any], str]) -> str:
    """Receiver identifier of a member call; '' when the object is not a plain name."""
    return text(obj) if obj is not None and _kind(obj) == 'identifier' else ''


def _ts_new_parts(node, text):
    target = next((c for c in node_children(node)
                   if _kind(c) in ('identifier', 'type_identifier', 'member_expression', 'scoped_type_identifier')), None)
    return (text(target) if target is not None else None), None


def _ts_java_invocation_parts(node, text):
    children = node_children(node)
    dots = [i for i, c in enumerate(children) if _kind(c) == '.']
    if dots and dots[-1] + 1 < len(children):
        return text(children[dots[-1] + 1]), _ts_object_name(children[dots[-1] - 1], text)
    ident = next((c for c in children if _kind(c) == 'identifier'), None)
    return (text(ident) if ident is not None else None), None


def _ts_js_call_parts(node, text):
    children = node_children(node)
    callee = children[0] if children else None
    if callee is None:
        return None, None
    if _kind(callee) == 'identifier':
        return text(callee), None
    if _kind(callee) != 'member_expression':
        return None, None
    parts = node_children(callee)
    prop = next((c for c in parts if _kind(c) == 'property_identifier'), None)
    return (text(prop) if prop is not None else None), _ts_object_name(parts[0] if parts else None, text)


def ts_call_parts(node, text: Callable[[Any], str]) -> Tuple[Optional[str], Optional[str], List[Any]]:
    """(callee name, receiver, argument nodes) of a call or ``new`` node.  The receiver is None for a
    bare call and '' when the object is not a plain name."""
    kind = _kind(node)
    if kind in _TS_NEW_KINDS:
        name, receiver = _ts_new_parts(node, text)
    elif kind == 'method_invocation':
        name, receiver = _ts_java_invocation_parts(node, text)
    else:
        name, receiver = _ts_js_call_parts(node, text)
    return name, receiver, _ts_operands(node)


def _ts_any_carries(nodes, caught: str, text) -> bool:
    return any(ts_carries(c, caught, text) for c in nodes)


def _ts_call_carries(node, caught: str, text) -> bool:
    name, receiver, operands = ts_call_parts(node, text)
    if _ts_role(node, name, receiver) == 'silent':
        return False
    if _ts_any_carries(operands, caught, text):
        return True
    # a method call on a carrier: ``e.toString()``, ``String(e).toUpperCase()``
    children = node_children(node)
    return (_kind(node) in _TS_CALL_KINDS and bool(children)
            and _kind(children[0]) in ('member_expression', 'method_invocation', 'identifier')
            and ts_carries(children[0], caught, text))


def ts_carries(node, caught: str, text: Callable[[Any], str]) -> bool:
    """True if the value of ``node`` can carry what the caught exception says."""
    kind = _kind(node)
    children = node_children(node)
    if kind in ('identifier', 'shorthand_property_identifier'):
        return text(node) == caught
    if kind in _TS_CARRY_ALL:
        return _ts_any_carries(children, caught, text)
    if kind in ('member_expression', 'subscript_expression', 'field_access'):
        return _ts_any_carries(children[:1], caught, text)
    if kind == 'pair':
        return _ts_any_carries(children[-1:], caught, text)
    if kind == 'ternary_expression':
        return _ts_any_carries(children[2:], caught, text)
    if kind == 'binary_expression':
        return any(_kind(c) in _TS_CARRY_OPERATORS for c in children) and _ts_any_carries(children, caught, text)
    if kind in _TS_CALL_KINDS or kind in _TS_NEW_KINDS:
        return _ts_call_carries(node, caught, text)
    return False


def ts_forwards(call, caught: Optional[str], text: Callable[[Any], str]) -> bool:
    """A statement or returned call (awaited or not) that hands the exception on."""
    if not caught:
        return False
    name, receiver, operands = ts_call_parts(call, text)
    if _forwards(_ts_role(call, name, receiver), operands,
                          lambda op: ts_carries(op, caught, text),
                          lambda op: ts_mentions(op, caught, text)):
        return True
    return _ts_chain_asserts(call, caught, text)


def _ts_chain_asserts(call, caught: str, text: Callable[[Any], str]) -> bool:
    """``expect(e.message).toBe(x)``, ``assertThat(e).hasMessage(x)``: an assertion earlier in the
    receiver chain consumes the exception."""
    node = call
    while node is not None and _kind(node) in _TS_CALL_KINDS | {'member_expression'}:
        children = node_children(node)
        node = children[0] if children else None
        if node is not None and _kind(node) in _TS_CALL_KINDS:
            name, receiver, operands = ts_call_parts(node, text)
            if _ts_role(node, name, receiver) == 'assertion' and any(ts_mentions(op, caught, text) for op in operands):
                return True
    return False
