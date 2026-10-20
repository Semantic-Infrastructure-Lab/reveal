"""Bounded lexical facts for shared-write navigation (no import resolution)."""
from __future__ import annotations

from typing import Any, Callable, Optional

from ...core import node_children
from ...core.node_taxonomy import CLASS_NODES, DEF_NODES, FUNCTION_EXPRESSION_NODES, LAMBDA_NODES
from ...core.treesitter_compat import _zero_arg
from ...rules.base_mixins import kind_nodes
from .nav_varflow import _declared_name_node, _MEMBER_ACCESS_KINDS, var_flow


# Anonymous/value-function shapes verified by the Python/JS/PHP fixtures.
_FUNCTIONS = DEF_NODES | LAMBDA_NODES | FUNCTION_EXPRESSION_NODES | frozenset({'anonymous_function'})
_CLASSES = CLASS_NODES
_ROOTS = frozenset({'module', 'program'})


def _span(node: Any) -> tuple:
    return _zero_arg(node, 'start_byte'), _zero_arg(node, 'end_byte')


def _ancestors(node: Any):
    while node is not None:
        yield node
        node = _zero_arg(node, 'parent')


def _owner(node: Any, language: str, *, block: bool = False):
    kinds = _FUNCTIONS | _CLASSES | _ROOTS
    if block and language in ('javascript', 'typescript', 'tsx'):
        kinds = kinds | {'statement_block', 'for_statement', 'for_in_statement', 'catch_clause'}
    return next((part for part in _ancestors(node) if _zero_arg(part, 'kind') in kinds), None)


def _pattern_names(node: Any, text: Callable) -> set[str]:
    """Names in a parameter/pattern, excluding named keys, defaults and types."""
    if node is None:
        return set()
    kind = _zero_arg(node, 'kind')
    if kind in ('identifier', 'variable_name', 'shorthand_property_identifier_pattern'):
        return {text(node)}
    name = node.child_by_field_name('name')
    if name is not None:
        return _pattern_names(name, text)
    left = node.child_by_field_name('left')
    if left is not None:
        return _pattern_names(left, text)
    pattern = node.child_by_field_name('pattern')
    if pattern is not None:
        return _pattern_names(pattern, text)
    # Object destructuring pairs bind the value, not the property key.
    value = node.child_by_field_name('value')
    if kind == 'pair_pattern' and value is not None:
        return _pattern_names(value, text)
    excluded = {
        _span(part) for field in ('value', 'type', 'return_type')
        if (part := node.child_by_field_name(field)) is not None
    }
    return set().union(*(_pattern_names(child, text) for child in node_children(node)
                         if _zero_arg(child, 'is_named') and _span(child) not in excluded))


class BindingScope:
    """Transient lexical facts shared by statewrites and builtin classification.

    Assignment bindings come from the existing var-flow owner. These facts do
    not infer aliases, imported objects, PHP capture references or dynamic names.
    """

    def __init__(self, func_node: Any, get_text: Callable, language: Optional[str]):
        self.scope = func_node
        self.text = get_text
        self.root = next(reversed(list(_ancestors(func_node))))
        self.language = language or ('python' if _zero_arg(self.root, 'kind') == 'module' else '')
        self._writes: dict[str, list[Any]] = {}

    def _events(self, name: str) -> list[Any]:
        if name not in self._writes:
            end = _zero_arg(self.root, 'end_position').row + 1
            self._writes[name] = [event for event in
                                  var_flow(self.root, name, 1, end, self.text)
                                  if event['kind'] == 'WRITE']
        return self._writes[name]

    def _declared(self, scope: Any, name: str) -> bool:
        parameters = (scope.child_by_field_name(field) for field in ('parameters', 'parameter'))
        if any(name in _pattern_names(parameter, self.text) for parameter in parameters):
            return True
        if any(self._write_binding(event, scope, name) for event in self._events(name)):
            return True
        return self._named_declaration(scope, name) or self._import_binding(scope, name)

    def _write_binding(self, event: Any, scope: Any, name: str) -> bool:
        if event.get('binding_scope') is not None:
            return False
        node = event['node']
        path = list(_ancestors(node))
        boundary = next((i for i, part in enumerate(path)
                         if _zero_arg(part, 'kind') in _FUNCTIONS | _CLASSES | _ROOTS), len(path))
        path = path[:boundary]
        # `var` hoists to the function; let/const remain in the nearest block.
        hoisted = self.language != 'python' and any(
            _zero_arg(part, 'kind') == 'variable_declaration' for part in path)
        owner = _owner(node, self.language, block=self.language != 'python' and not hoisted)
        if owner is None or _span(owner) != _span(scope):
            return False
        if self.language == 'python':
            # Container/member WRITE events mutate storage, but do not bind a name.
            assignment = next((i for i, part in enumerate(path)
                               if _zero_arg(part, 'kind') in ('assignment', 'augmented_assignment')), len(path))
            mutation = any(_zero_arg(part, 'kind') in _MEMBER_ACCESS_KINDS | {'subscript'}
                           for part in path[:assignment])
            return not mutation and not self._explicit(scope, name)
        # JS bare assignment resolves an existing binding; declarations introduce it.
        return any(_zero_arg(part, 'kind') == 'variable_declarator' for part in path)

    def _named_declaration(self, scope: Any, name: str) -> bool:
        for declaration in kind_nodes(self.root, *_FUNCTIONS, *_CLASSES):
            name_node = _declared_name_node(declaration)
            if name_node is None or self.text(name_node) != name:
                continue
            owner = _owner(_zero_arg(declaration, 'parent'), self.language, block=True)
            if owner is not None and _span(owner) == _span(scope):
                return True
        return False

    def _import_binding(self, scope: Any, name: str) -> bool:
        if self.language != 'python':
            return False
        for declaration in kind_nodes(self.root, 'import_statement', 'import_from_statement'):
            owner = _owner(declaration, self.language)
            if owner is not None and _span(owner) == _span(scope):
                if name in self._import_names(declaration):
                    return True
        return False

    def _import_names(self, node: Any) -> set[str]:
        names = set()
        for child in node_children(node):
            kind = _zero_arg(child, 'kind')
            if kind == 'aliased_import':
                alias = child.child_by_field_name('alias')
                if alias is not None:
                    names.add(self.text(alias))
            elif kind == 'dotted_name':
                module = node.child_by_field_name('module_name')
                if module is None or _span(child) != _span(module):
                    names.add(self.text(child).split('.')[0])
        return names

    def _explicit(self, scope: Any, name: str) -> Optional[str]:
        kinds = ('global_statement', 'nonlocal_statement', 'global_declaration')
        for declaration in kind_nodes(self.root, *kinds):
            owner = _owner(declaration, self.language)
            if owner is None or _span(owner) != _span(scope):
                continue
            if name in _pattern_names(declaration, self.text):
                return 'nonlocal' if _zero_arg(declaration, 'kind') == 'nonlocal_statement' else 'global'
        return None

    def _owned_binding(self, name: str, node: Any) -> bool:
        """A scoped WRITE binds only targets inside that lexical owner's span."""
        start, end = _span(node)
        for event in self._events(name):
            binding = event.get('binding_scope')
            if binding is not None and binding[0] <= start and end <= binding[1]:
                return True
        return False

    def has_explicit_binding(self, name: str, at_node: Any = None) -> bool:
        """Whether a lexical declaration shadows e.g. a Python builtin."""
        node = self.scope if at_node is None else at_node
        if self._owned_binding(name, node):
            return True
        scopes = _FUNCTIONS | _ROOTS
        if _zero_arg(self.scope, 'kind') in _CLASSES:
            scopes = scopes | _CLASSES
        for scope in _ancestors(node):
            if _zero_arg(scope, 'kind') not in scopes:
                continue
            if self._explicit(scope, name) or self._declared(scope, name):
                return True
        return False

    def shared_write_kind(self, target: Any) -> Optional[str]:
        """Classify external storage roots; ordinary container locals stay local."""
        if self.language not in ('python', 'javascript', 'typescript', 'tsx', 'php'):
            return None
        base = target
        while _zero_arg(base, 'kind') not in ('identifier', 'variable_name'):
            children = [child for child in node_children(base) if _zero_arg(child, 'is_named')]
            if not children:
                return None
            base = children[0]
        name = self.text(base)
        scope = _owner(target, self.language)
        if scope is None:
            return None
        if self.language == 'php':
            if name == '$GLOBALS':
                return 'global'
            return self._explicit(scope, name)
        explicit = self._explicit(scope, name)
        if explicit:
            return explicit
        # Python's plain name assignment introduces a local, even if a module
        # binding has the same spelling. Container/attribute stores read a root.
        if self.language == 'python' and _span(base) == _span(target):
            return 'global' if _zero_arg(scope, 'kind') in _ROOTS else None
        return self._shared_root(target, name)

    def _shared_root(self, target: Any, name: str) -> Optional[str]:
        if self._owned_binding(name, target):
            return None
        owner = _owner(target, self.language)
        if owner is not None and _zero_arg(owner, 'kind') in _CLASSES:
            if self._declared(owner, name):
                return None
        scopes = _FUNCTIONS | _ROOTS
        if self.language != 'python':
            scopes = scopes | {'statement_block', 'for_statement', 'for_in_statement', 'catch_clause'}
        for enclosing in _ancestors(target):
            kind = _zero_arg(enclosing, 'kind')
            if kind not in scopes:
                continue
            explicit = self._explicit(enclosing, name)
            if explicit:
                return explicit
            if self._declared(enclosing, name):
                return 'global' if kind in _ROOTS else None
        return None
