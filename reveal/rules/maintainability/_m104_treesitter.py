"""Tree-sitter based collection-literal extraction for M104.

M104's classification heuristics (_classify_list, _detect_list_risk_factors,
_format_list_sample, _should_skip_collection) already operate on
(name: str, values: list) — language-agnostic by construction. Only the
*extraction* of "a named collection literal" was Python-ast-specific. This
module supplies that extraction for JS/TS, Go, Rust, and Java, each of which
represents a hardcoded list/array/vec differently in its grammar:

- JS/TS:  `const NAME = [...]`               -> `array` node
- Go:     `var/const NAME = []T{...}`        -> `composite_literal` (slice/array type, not map)
- Rust:   `let/const NAME = [...]` or `vec![...]` -> `array_expression` / `vec!` macro
- Java:   `T[] NAME = {...}` or `List.of(...)`/`Arrays.asList(...)`

Each extractor yields (name, line, kind, values) tuples, mirroring what
M104's own `_extract_list_values` + `ast.Assign` walk produces for Python.
"""

from typing import Any, Iterator, List, Optional, Tuple

from ...core.treesitter_compat import iter_tree, node_children, _zero_arg

_QUOTE_CHARS = '"\'`'


def _node_text(node: Any, content_bytes: bytes) -> str:
    start = _zero_arg(node, 'start_byte')
    end = _zero_arg(node, 'end_byte')
    return content_bytes[start:end].decode('utf-8', 'replace')


def _strip_quotes(text: str) -> str:
    if len(text) >= 2 and text[0] in _QUOTE_CHARS and text[-1] == text[0]:
        return text[1:-1]
    return text


def _node_line(node: Any) -> int:
    return node.start_position().row + 1


def _kind(node: Any) -> str:
    return _zero_arg(node, 'kind')


def _find_child(node: Any, kind: str) -> Optional[Any]:
    for child in node_children(node):
        if _kind(child) == kind:
            return child
    return None


def _find_descendant(node: Any, kinds: frozenset) -> Optional[Any]:
    """Depth-first search (including `node` itself) for the first node whose
    kind is in `kinds`. Used to reach a literal buried under type-annotation
    scaffolding (Go's `expression_list`, Rust's typed `let`, ...)."""
    if _kind(node) in kinds:
        return node
    for child in node_children(node):
        found = _find_descendant(child, kinds)
        if found is not None:
            return found
    return None


_JS_STRING_KINDS = frozenset({'string', 'number'})


def _extract_js(root: Any, content_bytes: bytes) -> Iterator[Tuple[str, int, str, List[str]]]:
    for node in iter_tree(root):
        if _kind(node) != 'variable_declarator':
            continue
        name_node = _find_child(node, 'identifier')
        array_node = _find_child(node, 'array')
        if name_node is None or array_node is None:
            continue
        values = [
            _strip_quotes(_node_text(child, content_bytes)) if _kind(child) == 'string'
            else _node_text(child, content_bytes)
            for child in node_children(array_node)
            if _kind(child) in _JS_STRING_KINDS
        ]
        if values:
            yield _node_text(name_node, content_bytes), _node_line(node), 'array', values


_GO_DECL_KINDS = frozenset({'var_spec', 'const_spec', 'short_var_declaration'})
_GO_COLLECTION_TYPE_KINDS = frozenset({'slice_type', 'array_type'})


def _extract_go(root: Any, content_bytes: bytes) -> Iterator[Tuple[str, int, str, List[str]]]:
    for node in iter_tree(root):
        if _kind(node) not in _GO_DECL_KINDS:
            continue
        name_node = _find_child(node, 'identifier')
        if name_node is None:
            # short_var_declaration's left side is an expression_list wrapping
            # the identifier(s), not a direct identifier child.
            left = _find_child(node, 'expression_list')
            name_node = _find_child(left, 'identifier') if left is not None else None
        if name_node is None:
            continue

        composite = _find_descendant(node, frozenset({'composite_literal'}))
        if composite is None:
            continue
        type_children = node_children(composite)
        if not type_children or _kind(type_children[0]) not in _GO_COLLECTION_TYPE_KINDS:
            continue  # skip map_type and struct literals — not a stale-list risk
        literal_value = _find_child(composite, 'literal_value')
        if literal_value is None:
            continue
        values = [
            _strip_quotes(_node_text(child, content_bytes))
            for child in node_children(literal_value)
            if _kind(child) == 'literal_element'
        ]
        if values:
            yield _node_text(name_node, content_bytes), _node_line(node), 'slice', values


_RUST_DECL_KINDS = frozenset({'let_declaration', 'const_item'})
_RUST_LITERAL_KINDS = frozenset({
    'string_literal', 'raw_string_literal', 'integer_literal', 'float_literal',
})


def _extract_rust(root: Any, content_bytes: bytes) -> Iterator[Tuple[str, int, str, List[str]]]:
    for node in iter_tree(root):
        if _kind(node) not in _RUST_DECL_KINDS:
            continue
        name_node = _find_child(node, 'identifier')
        if name_node is None:
            continue

        kind = 'array'
        collection = _find_descendant(node, frozenset({'array_expression'}))
        if collection is None:
            macro = _find_child(node, 'macro_invocation')
            macro_name = _find_child(macro, 'identifier') if macro is not None else None
            if macro_name is not None and _node_text(macro_name, content_bytes) == 'vec':
                collection = _find_child(macro, 'token_tree')
                kind = 'vec!'
        if collection is None:
            continue

        values = [
            _strip_quotes(_node_text(child, content_bytes))
            if _kind(child).endswith('string_literal')
            else _node_text(child, content_bytes)
            for child in node_children(collection)
            if _kind(child) in _RUST_LITERAL_KINDS
        ]
        if values:
            yield _node_text(name_node, content_bytes), _node_line(node), kind, values


_JAVA_LITERAL_KINDS = frozenset({'string_literal', 'decimal_integer_literal'})
_JAVA_COLLECTION_METHODS = frozenset({
    ('List', 'of'), ('List', 'copyOf'), ('Set', 'of'), ('Arrays', 'asList'),
})


def _extract_java(root: Any, content_bytes: bytes) -> Iterator[Tuple[str, int, str, List[str]]]:
    for node in iter_tree(root):
        if _kind(node) != 'variable_declarator':
            continue
        name_node = _find_child(node, 'identifier')
        if name_node is None:
            continue

        kind = 'array'
        values: List[str] = []
        array_init = _find_child(node, 'array_initializer')
        if array_init is not None:
            values = [
                _strip_quotes(_node_text(child, content_bytes))
                for child in node_children(array_init)
                if _kind(child) in _JAVA_LITERAL_KINDS
            ]
        else:
            call = _find_child(node, 'method_invocation')
            idents = (
                [c for c in node_children(call) if _kind(c) == 'identifier']
                if call is not None else []
            )
            if len(idents) >= 2:
                receiver = _node_text(idents[0], content_bytes)
                method = _node_text(idents[1], content_bytes)
                if (receiver, method) in _JAVA_COLLECTION_METHODS:
                    kind = f'{receiver}.{method}'
                    args = _find_child(call, 'argument_list')
                    if args is not None:
                        values = [
                            _strip_quotes(_node_text(child, content_bytes))
                            for child in node_children(args)
                            if _kind(child) in _JAVA_LITERAL_KINDS
                        ]
        if values:
            yield _node_text(name_node, content_bytes), _node_line(node), kind, values


_EXTRACTORS = {
    'javascript': _extract_js,
    'typescript': _extract_js,
    'tsx': _extract_js,
    'go': _extract_go,
    'rust': _extract_rust,
    'java': _extract_java,
}


def extract_collections(
    language: str, root: Any, content_bytes: bytes,
) -> Iterator[Tuple[str, int, str, List[str]]]:
    """Yield (name, line, kind, values) for every named collection literal
    `check()` should classify, for the given tree-sitter `language` name."""
    extractor = _EXTRACTORS.get(language)
    if extractor is None or root is None:
        return
    yield from extractor(root, content_bytes)
