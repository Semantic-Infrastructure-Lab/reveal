"""Tree-sitter based analyzer for multi-language support."""

import logging
import os
from collections import OrderedDict
from typing import Dict, List, Any, Optional, Tuple
from .base import FileAnalyzer
from .complexity import calculate_complexity_and_depth
from .core import suppress_treesitter_warnings
from .core import node_children as _children
from .core import node_next_sibling as _next_sibling

# Suppress tree-sitter deprecation warnings (centralized in core module)
suppress_treesitter_warnings()

from tree_sitter_language_pack import get_parser  # noqa: E402

logger = logging.getLogger(__name__)

# Module-level cache: (path_str, mtime_ns) -> {'tree': ..., 'node_cache': ...}
# Eliminates redundant parses when multiple rules/callers analyze the same
# unchanged file (e.g. extract_imports + extract_symbols + extract_exports
# for the same .py file during `reveal --check`).
#
# Bounded LRU: directory scans (stats://, overview) visit each file once so
# the cache provides no hit benefit while growing to hold every file's parse
# tree and node cache in memory indefinitely.  128 entries covers all
# realistic single-file multi-adapter patterns without unbounded growth.
_MAX_PARSE_CACHE = 128
_parse_cache: OrderedDict[Tuple[str, int], Dict[str, Any]] = OrderedDict()


# =============================================================================
# TREE-SITTER NODE TYPE CONSTANTS
# =============================================================================
# Single source of truth for tree-sitter node types across languages.
# Used by treesitter.py and display/element.py for consistent extraction.
#
# MAINTENANCE: When adding new language support, update these lists.
# Run `reveal file.ext --show-ast` to discover node types for new languages.
# =============================================================================

# Node types for function extraction
FUNCTION_NODE_TYPES = (
    'function_definition',   # Python
    'function_declaration',  # Go, C, JavaScript, Kotlin, Swift
    'function_item',         # Rust
    'function_signature',    # Dart
    'method_declaration',    # Java, C#
    'method_definition',     # Ruby
    'function',              # Generic
    'method',                # Ruby
    'function_definition_statement',       # Lua (global functions)
    'local_function_definition_statement',  # Lua (local functions)
    'Decl',                   # Zig (wraps FnProto + body; see ZigAnalyzer._get_node_name)
)

# Node types for class extraction
CLASS_NODE_TYPES = (
    'class_definition',           # Python
    'class_declaration',          # Java, C#, JavaScript, PHP
    'abstract_class_declaration', # TypeScript: abstract class Foo { ... }
    'class_specifier',            # C++
    'struct_item',                # Rust (treated as class)
    'class',                      # Ruby
    'anonymous_class',            # PHP: new class(...) extends Foo { ... }
)

# Node types for struct extraction
STRUCT_NODE_TYPES = (
    'struct_item',           # Rust
    'struct_specifier',      # C/C++
    'struct_declaration',    # Go
)

# Node types for import extraction
IMPORT_NODE_TYPES = (
    'import_statement',      # Python, JavaScript
    'import_declaration',    # Go, Java
    'use_declaration',       # Rust
    'using_directive',       # C#
    'import_from_statement',  # Python
    'preproc_include',       # C/C++
)

# Mapping from element type to node types (for element extraction)
ELEMENT_TYPE_MAP = {
    'function': FUNCTION_NODE_TYPES,
    'class': CLASS_NODE_TYPES,
    'struct': STRUCT_NODE_TYPES,
}

# Node types for call expression extraction (call graph)
CALL_NODE_TYPES = {
    'call',                    # Python
    'call_expression',         # JS, TS, Go, Rust, C, C++, Kotlin
    'function_call_expression', # PHP
    'member_call_expression',  # PHP $obj->method()
    'object_creation_expression', # PHP new ClassName()
    'method_call',             # Ruby, Rust (method syntax)
    'method_call_expression',  # Rust
    'invocation_expression',   # C#
    'function_call',           # Lua, Bash
    'method_invocation',       # Java
}

# Callee node types for attribute/member access (self.foo, obj.method, pkg.Func)
CALLEE_ATTRIBUTE_TYPES = {
    'attribute',             # Python: self.bar
    'member_expression',     # JS/TS: obj.method
    'field_expression',      # C/C++: obj.field
    'selector_expression',   # Go: pkg.Func
}

# Parent node types for hierarchical extraction (Class.method)
PARENT_NODE_TYPES = (
    'class_definition', 'class_declaration',
    'class_specifier',        # C++ class (BACK-451)
    'struct_item', 'struct_specifier', 'struct_declaration',
    'impl_item',              # Rust impl blocks
    'interface_declaration',
    'module',                 # Ruby module
    'anonymous_class',        # PHP anonymous class
)

# Child node types for hierarchical extraction (methods within classes)
CHILD_NODE_TYPES = (
    'function_definition', 'function_declaration',
    'method_declaration', 'method_definition',
    'function_item',         # Rust
    'function_signature',    # Dart methods (wrapped in method_signature)
)

# All element types for line-based extraction
ALL_ELEMENT_NODE_TYPES = (
    'function_definition', 'function_declaration', 'function_item',
    'method_declaration', 'method_definition',
    'class_definition', 'class_declaration',
    'struct_item', 'struct_specifier', 'struct_declaration',
    'anonymous_class',        # PHP anonymous class
)


def build_callers_index(functions: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Invert the callees map to produce a within-file callers index.

    Args:
        functions: List of function dicts with 'name' and 'calls' fields.

    Returns:
        Dict mapping function name → sorted list of names that call it (within this file).

    Example:
        [{'name': 'main', 'calls': ['parse', 'run']},
         {'name': 'run',  'calls': ['parse']}]
        → {'parse': ['main', 'run'], 'run': ['main']}
    """
    callers: Dict[str, List[str]] = {}
    for func in functions:
        for callee in func.get('calls', []):
            # Strip attribute prefix for local matching: "self.bar" → "bar"
            local_name = callee.split('.')[-1]
            callers.setdefault(local_name, [])
            if func['name'] not in callers[local_name]:
                callers[local_name].append(func['name'])
    return callers


# Node kinds used to pair a function/method's real name with its argument
# list (BACK-413) — shared between _get_node_name and _get_signature so both
# agree on which parameter_list is the actual signature vs. a receiver
# (Go) or which identifier is the name vs. a bare return type (C#).
_NAME_KINDS = ('identifier', 'name', 'constant', 'simple_identifier', 'property_identifier', 'field_identifier')
_PARAM_LIST_KINDS = ('parameters', 'parameter_list', 'formal_parameters')


class TreeSitterAnalyzer(FileAnalyzer):
    """Base class for tree-sitter based analyzers.

    Provides automatic extraction for ANY tree-sitter language!

    Subclass just needs to set:
        language (str): tree-sitter language name (e.g., 'python', 'rust', 'go')

    Everything else is automatic:
    - Structure extraction (imports, functions, classes, structs)
    - Element extraction (get specific function/class)
    - Line number tracking

    Usage:
        @register('.go', name='Go', icon='🔷')
        class GoAnalyzer(TreeSitterAnalyzer):
            language = 'go'
            # Done! Full support in 3 lines.
    """

    language: Optional[str] = None  # Set in subclass

    def __init__(self, path: str):
        super().__init__(path)
        self.tree: Optional[Any] = None
        self._node_cache: Optional[Dict[str, List[Any]]] = None  # None = unbuilt; {} = built but empty
        self._content_bytes: Optional[bytes] = None

        if self.language:
            self._parse_tree()

    def _parse_tree(self) -> None:
        """Parse file with tree-sitter.

        Uses a module-level cache keyed by (path, mtime_ns) to avoid
        re-parsing the same unchanged file across multiple analyzer
        instances (e.g. extract_imports, extract_symbols, extract_exports
        all called on the same .py file during --check).

        Note: Tree-sitter warnings are suppressed at module level via
        suppress_treesitter_warnings() call at top of file.
        """
        path_str = os.path.abspath(str(self.path))
        try:
            mtime_ns = os.stat(path_str).st_mtime_ns
        except OSError:
            mtime_ns = 0
        self._cache_key: Tuple[str, int] = (path_str, mtime_ns)

        cached = _parse_cache.get(self._cache_key)
        if cached is not None:
            # Move to end (most-recently-used) on hit
            _parse_cache.move_to_end(self._cache_key)
            self.tree = cached['tree']
            if 'node_cache' in cached:
                self._node_cache = cached['node_cache']
            return

        try:
            parser = get_parser(self.language)  # type: ignore[arg-type]  # language is validated at runtime
            self.tree = parser.parse(self.content)
        except Exception as e:
            logger.debug("tree-sitter parse failed for %s: %s", self.path, e)
            self.tree = None

        if self.tree is not None:
            _parse_cache[self._cache_key] = {'tree': self.tree}
            if len(_parse_cache) > _MAX_PARSE_CACHE:
                _parse_cache.popitem(last=False)  # evict least-recently-used

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, Any]:
        """Extract structure using tree-sitter.

        Args:
            head: Show first N semantic units (per category)
            tail: Show last N semantic units (per category)
            range: Show semantic units in range (start, end) - 1-indexed (per category)
            **kwargs: Additional parameters (unused)

        Returns imports, functions, classes, structs, etc.
        Works for ANY tree-sitter language!

        Note: Slicing applies to each category independently
        (e.g., --head 5 shows first 5 functions AND first 5 classes)
        """
        if not self.tree:
            return {}

        structure = {}

        # Extract common elements
        structure['imports'] = self._extract_imports()
        functions = self._extract_functions()
        callers_index = build_callers_index(functions)
        for func in functions:
            func['called_by'] = callers_index.get(func['name'], [])
        structure['functions'] = functions
        structure['classes'] = self._extract_classes()
        structure['structs'] = self._extract_structs()

        # Apply semantic slicing to each category
        if head or tail or range:
            for category in structure:
                structure[category] = self._apply_semantic_slice(
                    structure[category], head, tail, range
                )

        # Remove empty categories
        return {k: v for k, v in structure.items() if v}

    def _extract_relationships(self, structure: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """Extract intra-file call graph edges from structure.

        Flattens the per-function ``calls`` lists into a flat edge list suitable
        for graph consumers.  Only edges where both endpoints are named are emitted;
        callee names are included as-is (may include attribute access like
        ``self.validate`` or cross-module calls like ``json.dumps``).

        Returns:
            ``{'calls': [{'from': caller_name, 'from_line': line, 'to': callee}, ...]}``
            or ``{}`` if no call data is present.
        """
        edges = []
        for category in ('functions', 'methods'):
            for func in structure.get(category, []):
                caller_name = func.get('name', '')
                caller_line = func.get('line', 0)
                if not caller_name:
                    continue
                for callee in func.get('calls', []):
                    if callee:
                        edges.append({
                            'from': caller_name,
                            'from_line': caller_line,
                            'to': callee,
                        })
        return {'calls': edges} if edges else {}

    def _extract_imports(self) -> List[Dict[str, Any]]:
        """Extract import statements."""
        imports = []

        for import_type in IMPORT_NODE_TYPES:
            nodes = self._find_nodes_by_type(import_type)
            for node in nodes:
                imports.append({
                    'line': node.start_position().row + 1,
                    'content': self._get_node_text(node),
                })

        return imports

    def _extract_functions(self) -> List[Dict[str, Any]]:
        """Extract function definitions with complexity metrics and decorators.

        Handles both decorated and undecorated functions across multiple languages.
        """
        functions = []
        processed_funcs = set()  # Track (func_node_line, name) to avoid duplicates

        function_types = self._get_function_node_types()

        # Extract decorated functions first (Python-specific)
        decorated_funcs, decorated_lines = self._extract_decorated_functions(function_types)
        functions.extend(decorated_funcs)
        processed_funcs.update(decorated_lines)

        # Extract undecorated functions
        undecorated_funcs = self._extract_undecorated_functions(function_types, processed_funcs)
        functions.extend(undecorated_funcs)

        functions.extend(self._extract_arrow_functions())

        return functions

    # ── JS-family arrow-function-as-const (`const f = (...) => {}`) ─────────
    # BACK-431 Issue G tier B dogfood audit (mysterious-probe-0703, real
    # excalidraw source): this pattern was TypeScript/TSX-only special-case
    # logic that get_structure()/--outline used, but plain JavaScript had no
    # equivalent at all (`const f = () => {}` was invisible even to
    # --outline) — and neither language's nav-flag lookup
    # (file_handler._find_element_node) called it, so `reveal file.ts f
    # --varflow x` failed with "could not find function" for a function
    # --outline listed a moment earlier. Promoted here so every JS-family
    # grammar (lexical_declaration is JS/TS/TSX/JSX-specific — a no-op for
    # every other language) gets both get_structure() coverage and nav-flag
    # resolution from one shared implementation.

    def _is_module_scope_decl(self, lexical_decl_node) -> bool:
        parent = lexical_decl_node.parent()
        if parent is None:
            return False
        if parent.kind() == 'program':
            return True
        if parent.kind() == 'export_statement':
            gp = parent.parent()
            return gp is not None and gp.kind() == 'program'
        return False

    def _arrow_or_fn_value(self, variable_declarator_node) -> Tuple[Optional[Any], Optional[Any]]:
        """Return (name_node, value_node) for a variable_declarator, or (None, None)."""
        name_node = value_node = None
        for ch in _children(variable_declarator_node):
            if ch.kind() == 'identifier' and name_node is None:
                name_node = ch
            elif ch.kind() in ('arrow_function', 'function_expression'):
                value_node = ch
        return name_node, value_node

    def _extract_arrow_functions(self) -> List[Dict[str, Any]]:
        """Extract module-scope arrow/function-expression declarations (const X = () => {})."""
        funcs = []
        for decl_node in self._find_nodes_by_type('lexical_declaration'):
            if not self._is_module_scope_decl(decl_node):
                continue
            for child in _children(decl_node):
                if child.kind() != 'variable_declarator':
                    continue
                name_node, value_node = self._arrow_or_fn_value(child)
                if name_node and value_node:
                    funcs.append(self._build_function_dict(
                        value_node, self._get_node_text(name_node), []
                    ))
        return funcs

    def _find_named_arrow_function(self, name: str):
        """Resolve a module-scope `const name = (...) => {}` declaration to
        its function node, for nav-flag lookup by bare name
        (file_handler._find_element_node)."""
        for decl_node in self._find_nodes_by_type('lexical_declaration'):
            if not self._is_module_scope_decl(decl_node):
                continue
            for child in _children(decl_node):
                if child.kind() != 'variable_declarator':
                    continue
                name_node, value_node = self._arrow_or_fn_value(child)
                if name_node and value_node and self._get_node_text(name_node) == name:
                    return value_node
        return None

    def _get_function_node_types(self) -> List[str]:
        """Get common function node types across languages."""
        return list(FUNCTION_NODE_TYPES)

    def _extract_decorated_functions(self, function_types: List[str]) -> tuple[List[Dict[str, Any]], set]:
        """Extract decorated functions (Python-specific).

        decorated_definition contains decorator(s) + function/class.
        Returns tuple: (functions_list, tracking_set)
        tracking_set contains (func_node_line, name) for deduplication.
        """
        functions = []
        tracking_lines = set()
        decorated_nodes = self._find_nodes_by_type('decorated_definition')

        for decorated_node in decorated_nodes:
            func_node, decorators = None, []

            # Find function child and collect decorators
            for child in _children(decorated_node):
                if child.kind() in function_types:
                    func_node = child
                elif child.kind() == 'decorator':
                    decorators.append(self._get_node_text(child))

            if func_node:
                name = self._get_node_name(func_node)
                if name:
                    func_dict = self._build_function_dict(
                        node=func_node,
                        decorated_node=decorated_node,
                        name=name,
                        decorators=decorators
                    )
                    functions.append(func_dict)
                    # Track by func_node line (not decorated_node line) for matching
                    func_line = func_node.start_position().row + 1
                    tracking_lines.add((func_line, name))

        return functions, tracking_lines

    def _extract_undecorated_functions(self, function_types: List[str],
                                      processed_funcs: set) -> List[Dict[str, Any]]:
        """Extract undecorated functions across all supported languages."""
        functions = []

        for func_type in function_types:
            nodes = self._find_nodes_by_type(func_type)
            for node in nodes:
                name = self._get_node_name(node)
                if not name:
                    continue

                line_start = node.start_position().row + 1
                if (line_start, name) in processed_funcs:
                    continue  # Already processed as decorated

                functions.append(self._build_function_dict(
                    node=node,
                    name=name,
                    decorators=[]
                ))

        return functions

    def _build_function_dict(self, node, name: str, decorators: List[str],
                            decorated_node=None) -> Dict[str, Any]:
        """Build function dictionary with metrics.

        Args:
            node: Function node
            name: Function name
            decorators: List of decorator strings
            decorated_node: Optional parent decorated_definition node
        """
        # Use decorated_node bounds if available (includes decorators)
        bounds_node = decorated_node if decorated_node else node
        line_start = bounds_node.start_position().row + 1
        end_node = self._function_end_node(bounds_node)
        line_end = end_node.end_position().row + 1
        # For Dart, end_node is the sibling function_body — walk that for
        # complexity/calls too, or both metrics silently see an empty body
        # (same blindness _function_end_node's docstring describes).
        body_node = end_node if end_node is not bounds_node else node

        complexity, depth = calculate_complexity_and_depth(body_node)
        return {
            'line': line_start,
            'line_end': line_end,
            'name': name,
            'signature': self._get_signature(node),
            'line_count': line_end - line_start + 1,
            'depth': depth,
            'complexity': complexity,
            'decorators': decorators,
            'calls': self._extract_calls_in_function(body_node),
        }

    def _extract_classes(self) -> List[Dict[str, Any]]:
        """Extract class definitions with decorators.

        Handles both decorated and undecorated classes across multiple languages.
        """
        classes = []
        processed_classes = set()  # Track (class_node_line, name) to avoid duplicates

        class_types = self._get_class_node_types()

        # Extract decorated classes first (Python-specific)
        decorated_classes, decorated_lines = self._extract_decorated_classes(class_types)
        classes.extend(decorated_classes)
        processed_classes.update(decorated_lines)

        # Extract undecorated classes
        undecorated_classes = self._extract_undecorated_classes(class_types, processed_classes)
        classes.extend(undecorated_classes)

        return classes

    def _get_class_node_types(self) -> List[str]:
        """Get common class node types across languages."""
        return list(CLASS_NODE_TYPES)

    def _extract_decorated_classes(self, class_types: List[str]) -> tuple[List[Dict[str, Any]], set]:
        """Extract decorated classes (Python-specific).

        decorated_definition contains decorator(s) + class.
        Returns tuple: (classes_list, tracking_set)
        tracking_set contains (class_node_line, name) for deduplication.
        """
        classes = []
        tracking_lines = set()
        decorated_nodes = self._find_nodes_by_type('decorated_definition')

        for decorated_node in decorated_nodes:
            class_node, decorators = None, []

            # Find class child and collect decorators
            for child in _children(decorated_node):
                if child.kind() in class_types:
                    class_node = child
                elif child.kind() == 'decorator':
                    decorators.append(self._get_node_text(child))

            if class_node:
                name = self._get_node_name(class_node)
                if name:
                    class_dict = self._build_class_dict(
                        node=class_node,
                        decorated_node=decorated_node,
                        name=name,
                        decorators=decorators
                    )
                    classes.append(class_dict)
                    # Track by class_node line (not decorated_node line) for matching
                    class_line = class_node.start_position().row + 1
                    tracking_lines.add((class_line, name))

        return classes, tracking_lines

    def _get_anonymous_class_name(self, node) -> str:
        """Generate a synthetic name for a PHP anonymous class node.

        Reads the extends/implements clause to produce a descriptive label:
            new class extends NodeVisitorAbstract { ... }
            → 'anonymous(NodeVisitorAbstract)@L144'

        Falls back to 'anonymous@L{line}' when no base class is present.
        """
        line = node.start_position().row + 1
        for child in _children(node):
            if child.kind() == 'base_clause':
                for base_child in _children(child):
                    if base_child.kind() == 'name':
                        base_name = self._get_node_text(base_child)
                        return f'anonymous({base_name})@L{line}'
        return f'anonymous@L{line}'

    def _extract_undecorated_classes(self, class_types: List[str],
                                    processed_classes: set) -> List[Dict[str, Any]]:
        """Extract undecorated classes across all supported languages."""
        classes = []

        for class_type in class_types:
            nodes = self._find_nodes_by_type(class_type)
            for node in nodes:
                name = self._get_node_name(node)
                if not name:
                    # PHP anonymous classes have no identifier child — generate a
                    # synthetic name from the extends clause and line number.
                    if node.kind() == 'anonymous_class':
                        name = self._get_anonymous_class_name(node)
                    else:
                        continue

                line_start = node.start_position().row + 1
                if (line_start, name) in processed_classes:
                    continue  # Already processed as decorated

                classes.append(self._build_class_dict(
                    node=node,
                    name=name,
                    decorators=[]
                ))

        return classes

    def _extract_class_bases(self, node) -> List[str]:
        """Extract base class names from a class node.

        Handles:
        - Python: argument_list with identifiers/attributes (ABC, abc.ABC)
        - TypeScript class/abstract_class: class_heritage → extends_clause + implements_clause
        - TypeScript interface: extends_type_clause with type_identifier(s)

        Skips punctuation and keyword arguments (metaclass=...).
        Returns an empty list for classes with no bases.
        """
        node_type = node.kind()

        # TypeScript class_declaration / abstract_class_declaration:
        # class Foo extends Bar implements IBaz, IQux { ... }
        if node_type in ('class_declaration', 'abstract_class_declaration'):
            for child in _children(node):
                if child.kind() == 'class_heritage':
                    bases = []
                    for heritage_child in _children(child):
                        if heritage_child.kind() == 'extends_clause':
                            # extends_clause: "extends <identifier>"
                            for item in _children(heritage_child):
                                if item.kind() in ('identifier', 'type_identifier'):
                                    text = self._get_node_text(item).strip()
                                    if text:
                                        bases.append(text)
                        elif heritage_child.kind() == 'implements_clause':
                            # implements_clause: "implements TypeA, TypeB, ..."
                            for item in _children(heritage_child):
                                if item.kind() in ('type_identifier', 'identifier',
                                                   'generic_type'):
                                    if item.kind() == 'generic_type':
                                        # e.g. implements IFoo<T> — extract base name
                                        for gchild in _children(item):
                                            if gchild.kind() == 'type_identifier':
                                                text = self._get_node_text(gchild).strip()
                                                if text:
                                                    bases.append(text)
                                                break
                                    else:
                                        text = self._get_node_text(item).strip()
                                        if text:
                                            bases.append(text)
                    return bases

        # TypeScript interface_declaration:
        # interface IFoo extends IBar, IBaz { ... }
        if node_type == 'interface_declaration':
            for child in _children(node):
                if child.kind() == 'extends_type_clause':
                    bases = []
                    for item in _children(child):
                        if item.kind() in ('type_identifier', 'identifier'):
                            text = self._get_node_text(item).strip()
                            if text:
                                bases.append(text)
                    return bases
            return []

        # Python: class Foo(ABC, abc.Meta, metaclass=ABCMeta): ...
        for child in _children(node):
            if child.kind() != 'argument_list':
                continue
            bases = []
            for item in _children(child):
                if item.kind() in ('identifier', 'attribute'):
                    text = self._get_node_text(item).strip()
                    if text:
                        bases.append(text)
            return bases
        return []

    def _build_class_dict(self, node, name: str, decorators: List[str],
                         decorated_node=None) -> Dict[str, Any]:
        """Build class dictionary.

        Args:
            node: Class node
            name: Class name
            decorators: List of decorator strings
            decorated_node: Optional parent decorated_definition node
        """
        # Use decorated_node bounds if available (includes decorators)
        bounds_node = decorated_node if decorated_node else node
        line_start = bounds_node.start_position().row + 1
        line_end = bounds_node.end_position().row + 1

        result: Dict[str, Any] = {
            'line': line_start,
            'line_end': line_end,
            'name': name,
            'decorators': decorators,
            'bases': self._extract_class_bases(node),
        }
        # TypeScript abstract classes use a distinct node type — flag them so
        # consumers (e.g. contracts command) can distinguish from concrete classes.
        if node.kind() == 'abstract_class_declaration':
            result['is_abstract'] = True
        return result

    def _extract_structs(self) -> List[Dict[str, Any]]:
        """Extract struct definitions (for languages that have them)."""
        structs = []

        for struct_type in STRUCT_NODE_TYPES:
            nodes = self._find_nodes_by_type(struct_type)
            for node in nodes:
                name = self._get_node_name(node)
                if name:
                    line_start = node.start_position().row + 1
                    line_end = node.end_position().row + 1
                    structs.append({
                        'line': line_start,
                        'line_end': line_end,
                        'name': name,
                    })

        return structs

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a specific element using tree-sitter.

        Args:
            element_type: 'function', 'class', 'struct', etc.
            name: Name of the element

        Returns:
            Dict with source, line numbers, etc.
        """
        if not self.tree:
            return super().extract_element(element_type, name)

        node_types = ELEMENT_TYPE_MAP.get(element_type, [element_type])

        # Find matching node
        for node_type in node_types:
            nodes = self._find_nodes_by_type(node_type)
            for node in nodes:
                node_name = self._get_node_name(node)
                if node_name == name:
                    end_node = self._function_end_node(node)
                    source = (
                        self._get_node_text(node) if end_node is node
                        else self._get_text_span(node.start_byte(), end_node.end_byte())
                    )
                    return {
                        'name': name,
                        'line_start': node.start_position().row + 1,
                        'line_end': end_node.end_position().row + 1,
                        'source': source,
                    }

        # Fall back to grep
        return super().extract_element(element_type, name)

    def _find_nodes_by_type(self, node_type: str) -> List[Any]:
        """Find all nodes of a given type in the tree.

        Uses single-pass caching: first call walks entire tree once and caches
        ALL node types. Subsequent calls return from cache. This is 5-6x faster
        than walking the tree separately for each node type query.

        Also writes the completed node_cache back into the module-level
        _parse_cache so subsequent analyzer instances for the same unchanged
        file can skip the tree traversal entirely.
        """
        if not self.tree:
            return []

        # Build cache on first access (lazy initialization); None sentinel means unbuilt
        if self._node_cache is None:
            self._node_cache = {}
            stack = [self.tree.root_node()]
            while stack:
                node = stack.pop()
                self._node_cache.setdefault(node.kind(), []).append(node)
                # Reverse children to maintain document order (stack is LIFO)
                children = _children(node)
                if children:
                    stack.extend(reversed(children))

            # Write completed node_cache back to module-level cache
            if hasattr(self, '_cache_key') and self._cache_key in _parse_cache:
                _parse_cache[self._cache_key]['node_cache'] = self._node_cache
                _parse_cache.move_to_end(self._cache_key)  # refresh LRU position

        return (self._node_cache or {}).get(node_type, [])

    def _get_node_text(self, node) -> str:
        """Get the source text for a node.

        IMPORTANT: Tree-sitter uses byte offsets, not character offsets!
        Must slice the UTF-8 bytes, not the string, to handle multi-byte characters.

        Caches content.encode('utf-8') per instance to avoid re-encoding the
        entire file on every call (hot path: called once per symbol/function/class).
        """
        try:
            if self._content_bytes is None:
                raise AttributeError
            content_bytes = self._content_bytes
        except AttributeError:
            content_bytes = self.content.encode('utf-8')
            self._content_bytes = content_bytes
        return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

    def _get_text_span(self, start_byte: int, end_byte: int) -> str:
        """Get source text for an arbitrary byte range spanning two nodes
        (e.g. Dart's disjoint function_signature + function_body pair) —
        same byte-not-character slicing rationale as _get_node_text."""
        try:
            if self._content_bytes is None:
                raise AttributeError
            content_bytes = self._content_bytes
        except AttributeError:
            content_bytes = self.content.encode('utf-8')
            self._content_bytes = content_bytes
        return content_bytes[start_byte:end_byte].decode('utf-8')

    def _function_end_node(self, node):
        """Return the node whose end position bounds a function's body.

        Every other FUNCTION_NODE_TYPES member nests its body inside the
        function node itself. Dart's grammar is the odd one out:
        `function_signature` (name + params) and `function_body` are
        SEPARATE sibling nodes, not parent/child. Using the signature node's
        own end position (old behavior) silently truncated every Dart
        function's range to its one-line signature — every nav flag
        (--varflow/--exits/--returns/--ifmap/etc.), plus --outline's
        line_end/line_count, saw an empty range for the entire function body
        (BACK-431 Issue G smoke-tier audit: `--varflow` reported "no
        references found" for a variable declared and read three lines into
        the body).
        """
        if node.kind() == 'function_signature':
            sibling = _next_sibling(node)
            if sibling is None:
                # Methods wrap function_signature in a method_signature node
                # (`class_body: method_signature(function_signature), function_body`)
                # — function_signature is method_signature's only child, so its
                # own next-sibling is None; the real function_body sibling is
                # one level up, next to method_signature (dogfood audit against
                # AppFlowy: every class method showed "[1 lines]" in --outline
                # even after the top-level-function fix above).
                parent = node.parent()
                if parent is not None and parent.kind() == 'method_signature':
                    sibling = _next_sibling(parent)
            if sibling is not None and sibling.kind() == 'function_body':
                return sibling
        return node

    def _get_node_name(self, node) -> Optional[str]:
        """Get the name of a node (function/class/struct name).

        CRITICAL: For functions with return types (C/C++), the tree structure is:
            function_definition:
                type_identifier (return type) - NOT the function name!
                function_declarator (contains actual name)
                    identifier (actual function name!)

        We must search declarators BEFORE looking at type_identifier to avoid
        extracting the return type instead of the function name.

        CRITICAL (BACK-413): some grammars put more than one name-shaped node
        among a method's direct children — a bare non-generic return type
        (C# `Task Close()`) or a receiver (Go `func (s *T) Name()`) parses as
        an `identifier`/`field_identifier` sibling of the real name. Picking
        the first match (old behavior) grabs the return type/receiver instead
        of the name. The real name is always the one immediately preceding
        the parameter list, so that pairing is checked first.
        """
        kids = _children(node)

        # PRIORITY 1: For C/C++ functions, look inside declarators FIRST
        # These contain the actual function/variable name, not the type
        for child in kids:
            if child.kind() in ('function_declarator', 'pointer_declarator', 'declarator'):
                # Recursively search for identifier (may be nested deep)
                name = self._find_identifier_in_tree(child)
                if name:
                    return name

        # PRIORITY 2: name-kind child immediately preceding a parameter list —
        # the node actually attached to the argument list, not an unrelated
        # identifier-shaped sibling (return type, receiver, etc.)
        for i, child in enumerate(kids):
            if child.kind() in _PARAM_LIST_KINDS and i > 0 and kids[i - 1].kind() in _NAME_KINDS:
                return self._get_node_text(kids[i - 1])

        # PRIORITY 2b: no adjacent parameter list — first identifier/name child
        # (classes, fields, variables; excludes field_identifier, see PRIORITY 4)
        for child in kids:
            if child.kind() in ('identifier', 'name', 'constant', 'simple_identifier', 'property_identifier'):
                return self._get_node_text(child)

        # PRIORITY 2c: Lua `function table.name(...)` / `function tbl.a.b(...)`
        # — an extremely common module-method idiom (BACK-431 Issue G tier B
        # dogfood audit: found via real Kong source, `kong/concurrency.lua`'s
        # entire public API is declared this way). The name is a
        # `dot_index_expression` ("concurrency.with_worker_mutex"), a kind
        # absent from every check above; return just the final segment,
        # matching how every other bare-name function lookup in reveal works.
        for child in kids:
            if child.kind() == 'dot_index_expression':
                return self._get_node_text(child).rsplit('.', 1)[-1]

        # PRIORITY 3: type_identifier (fallback for structs, classes)
        # Only use this if we haven't found a name in declarators
        for child in kids:
            if child.kind() == 'type_identifier':
                return self._get_node_text(child)

        # PRIORITY 4: field_identifier (for struct fields)
        for child in kids:
            if child.kind() == 'field_identifier':
                return self._get_node_text(child)

        return None

    def _find_identifier_in_tree(self, node) -> Optional[str]:
        """Recursively search for an identifier in a node tree.

        Used to extract names from deeply nested declarators.
        Example: pointer_declarator → function_declarator → identifier

        BACK-451: C++ in-line member functions parse their name as a
        ``field_identifier`` inside the ``function_declarator`` (a free
        function uses a plain ``identifier``). Without it here, every C++
        class method returned no name and was silently dropped from the
        structure entirely — invisible to ``--outline`` and ``Class.method``
        extraction alike.
        """
        # Check current node
        if node.kind() in ('identifier', 'name', 'simple_identifier', 'field_identifier'):
            return self._get_node_text(node)

        # Search children recursively
        for child in _children(node):
            # Skip pointer/reference symbols and parameter lists
            if child.kind() in ('*', '&', 'parameter_list', 'parameters'):
                continue

            name = self._find_identifier_in_tree(child)
            if name:
                return name

        return None

    def _get_signature(self, node) -> str:
        """Get function signature (parameters and return type only).

        CRITICAL (BACK-413): some grammars attach more than one parameter_list
        to a single method node — Go methods carry a receiver parameter_list
        before the name AND, for multi-value returns, a tuple-shaped
        parameter_list after the real params (`func (s *T) F() (int, error)`).
        Blindly taking the last parameter_list child (old behavior) grabs the
        tuple-return list instead of the actual arguments. The real params are
        always the parameter_list immediately after the name (see
        _get_node_name), so that pairing is used here too.
        """
        kids = _children(node)
        params_text = ''
        return_type = ''

        for i, child in enumerate(kids):
            if child.kind() in _PARAM_LIST_KINDS and i > 0 and kids[i - 1].kind() in _NAME_KINDS:
                params_text = self._get_node_text(child)
                break

        if not params_text:
            # No name-adjacent parameter list found (e.g. anonymous
            # functions/lambdas) — fall back to the first one present.
            for child in kids:
                if child.kind() in _PARAM_LIST_KINDS:
                    params_text = self._get_node_text(child)
                    break

        for child in kids:
            if child.kind() in ('return_type', 'type'):
                return_type = ' -> ' + self._get_node_text(child).strip(': ')

        if params_text:
            return params_text + return_type

        # Fallback: try to extract from first line
        text = self._get_node_text(node)
        first_line = text.split('\n')[0].strip()

        # Remove common prefixes (def, func, fn, function, etc.)
        for prefix in ['def ', 'func ', 'fn ', 'function ', 'async def ', 'pub fn ', 'fn ', 'async fn ']:
            if first_line.startswith(prefix):
                first_line = first_line[len(prefix):]
                break

        # Extract just the signature part (name + params + return)
        # Remove the name to leave just params + return type
        if '(' in first_line:
            name_end = first_line.index('(')
            signature = first_line[name_end:].rstrip(':').strip()
            return signature

        # No parens at all — e.g. Ruby's paren-less method defs (`def human?`
        # ... `end`) — there is no parameter signature to show; the
        # remaining text is just the name again, which callers (e.g.
        # display/outline.py's _build_item_display, which concatenates
        # name+signature) would otherwise render as a duplicated name like
        # `human?human?` (BACK-431 tier A real-corpus dogfood audit: found
        # via real Discourse source, app/models/user.rb).
        return ''

    def _get_nesting_depth(self, node) -> int:
        """Return maximum nesting depth within a function node."""
        if not node:
            return 0
        _, depth = calculate_complexity_and_depth(node)
        return int(depth)

    def _calculate_complexity(self, node) -> int:
        """Return cyclomatic complexity for a function node."""
        if not node:
            return 1
        complexity, _ = calculate_complexity_and_depth(node)
        return int(complexity)

    def _calculate_complexity_and_depth(self, node) -> tuple:
        """Compute cyclomatic complexity and max nesting depth."""
        return calculate_complexity_and_depth(node)

    def _get_callee_name(self, call_node) -> Optional[str]:
        """Extract the callee name from a call expression node.

        Handles five forms:
          - Simple:         foo()             → "foo"
          - Attribute:      self.bar()        → "self.bar"
          - Chained:        a.b.c()           → "a.b.c"
          - Starred:        *foo(bar)         → "foo"
          - PHP method:     $obj->method()    → "$obj->method"
          - PHP new:        new ClassName()   → "new ClassName"
        """
        if not call_node.child_count():
            return None

        # PHP: $obj->method() — member_call_expression children are:
        #   receiver (->|?->) name arguments
        if call_node.kind() == 'member_call_expression':
            receiver_text = None
            method_name = None
            seen_arrow = False
            for child in _children(call_node):
                if child.kind() in ('->', '?->'):
                    seen_arrow = True
                    continue
                if child.kind() == 'arguments':
                    break
                if not seen_arrow:
                    receiver_text = self._get_node_text(child)
                else:
                    method_name = self._get_node_text(child)
            if method_name:
                return f"{receiver_text}->{method_name}" if receiver_text else method_name
            return None

        # PHP: new ClassName() — object_creation_expression
        if call_node.kind() == 'object_creation_expression':
            for child in _children(call_node):
                if child.kind() not in ('new', 'arguments'):
                    return f"new {self._get_node_text(child)}"
            return None

        callee_node = call_node.child(0)
        if callee_node.kind() == 'identifier':
            return self._get_node_text(callee_node)
        if callee_node.kind() in CALLEE_ATTRIBUTE_TYPES:
            return self._get_node_text(callee_node).lstrip('*')
        # tree-sitter parses `*foo(args)` as call(list_splat(*foo), args).
        if callee_node.kind() == 'list_splat':
            for child in _children(callee_node):
                if child.kind() == 'identifier':
                    return self._get_node_text(child)
                if child.kind() in CALLEE_ATTRIBUTE_TYPES:
                    return self._get_node_text(child).lstrip('*')
        text = self._get_node_text(callee_node).strip().lstrip('*')
        return text if text else None

    def _extract_calls_in_function(self, func_node) -> List[str]:
        """Walk function body subtree and return unique callee name strings.

        Returns best-effort callee names from call expression nodes within the
        function body. Names are not resolved across files (that's Phase 3).

        Examples:
            foo()           → ["foo"]
            self.bar()      → ["self.bar"]
            foo(bar())      → ["foo", "bar"]  (nested calls both captured)
        """
        calls: List[str] = []
        seen: set = set()
        stack = _children(func_node)
        while stack:
            node = stack.pop()
            if node.kind() in CALL_NODE_TYPES:
                name = self._get_callee_name(node)
                if name and name not in seen:
                    calls.append(name)
                    seen.add(name)
            stack.extend(reversed(_children(node)))
        return calls

