"""Bound parameter names from qualified syntax shapes; unknown is never an empty list."""
from typing import Any, Callable, List, Optional

from . import _zero_arg, node_children

# These languages have explicit binding fields qualified by native grammar fixtures.
PARAMETER_LANGUAGES = frozenset({'python', 'javascript', 'typescript', 'tsx', 'go', 'rust',
                               'java', 'c_sharp', 'csharp', 'php', 'ruby', 'c', 'cpp'})
_LISTS = frozenset({'parameters', 'lambda_parameters', 'parameter_list', 'formal_parameters', 'method_parameters'})
_LEAVES = frozenset({'identifier', 'name', 'variable_name', 'shorthand_property_identifier_pattern'})
_BINDING_FIELD = {'assignment_pattern': 'left', 'object_assignment_pattern': 'left', 'pair_pattern': 'value',
                  'required_parameter': 'pattern',
                  'parameter': 'pattern', 'default_parameter': 'name', 'typed_default_parameter': 'name',
                  'formal_parameter': 'name', 'simple_parameter': 'name', 'variadic_parameter': 'name',
                  'optional_parameter_declaration': 'declarator', 'keyword_parameter': 'name',
                  'optional_parameter': 'name'}
_PATTERN_LISTS = frozenset({'object_pattern', 'array_pattern', 'tuple_pattern', 'list_pattern'})
_WRAPPERS = frozenset({'list_splat_pattern', 'dictionary_splat_pattern', 'rest_pattern',
                       'splat_parameter', 'hash_splat_parameter', 'mut_pattern', 'parenthesized_declarator'})


def parameter_list(node: Any) -> Any:
    """The function's own list, excluding Go receivers/returns and C nested declarators."""
    params = node.child_by_field_name('parameters')
    if params is not None:
        return params
    declarator = node.child_by_field_name('declarator')
    if declarator is not None:
        return parameter_list(declarator)
    return next((c for c in node_children(node) if _zero_arg(c, 'kind') in _LISTS), None)


def _bindings(node: Any, text: Callable) -> Optional[List[str]]:
    kind = _zero_arg(node, 'kind')
    if kind in _LEAVES:
        return [text(node)]
    if kind in ('self_parameter', 'positional_separator', 'keyword_separator'):
        return []
    # Go groups bind several names; C uses declarator chains; C# has a name field.
    names = node.children_by_field_name('name')
    if kind == 'parameter_declaration' and names:
        return [text(n) for n in names]
    field = _BINDING_FIELD.get(kind)
    target = node.child_by_field_name(field) if field else None
    if target is None:
        target = (node.child_by_field_name('name') or node.child_by_field_name('pattern')
                  or node.child_by_field_name('declarator'))
    if target is not None:
        return _bindings(target, text)
    children = [c for c in node_children(node) if _zero_arg(c, 'is_named')]
    if kind == 'spread_parameter':
        binding = next((c for c in children if _zero_arg(c, 'kind') == 'variable_declarator'), None)
        return _bindings(binding, text) if binding is not None else None
    if kind in _WRAPPERS or kind == 'typed_parameter':
        return _bindings(children[0], text) if children else None
    if kind in _PATTERN_LISTS:
        return _binding_sequence(children, text)
    if kind == 'parameter_declaration' and text(node).strip() == 'void':
        return []
    return None


def _binding_sequence(nodes: List[Any], text: Callable) -> Optional[List[str]]:
    names = []
    for node in nodes:
        found = _bindings(node, text)
        if found is None:
            return None
        names.extend(found)
    return names


def parameter_names(node: Any, language: str, text: Callable) -> Optional[List[str]]:
    """None means unqualified grammar/binding shape; [] proves a known empty list."""
    if language not in PARAMETER_LANGUAGES:
        return None
    params = parameter_list(node)
    if params is None:
        single = node.child_by_field_name('parameter')  # JS single-argument arrow
        if single is not None:
            return _bindings(single, text)
        return [] if language == 'ruby' else None
    names = _binding_sequence([c for c in node_children(params) if _zero_arg(c, 'is_named')], text)
    return [n for n in names if n not in ('self', 'cls')] if names is not None and language == 'python' else names
