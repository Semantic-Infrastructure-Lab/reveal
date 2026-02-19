"""Tree-sitter based analyzer for multi-language support."""

import os
from typing import Dict, List, Any, Optional, Tuple
from .base import FileAnalyzer
from .core import suppress_treesitter_warnings

# Suppress tree-sitter deprecation warnings (centralized in core module)
suppress_treesitter_warnings()

from tree_sitter_language_pack import get_parser  # noqa: E402


# Module-level cache: (path_str, mtime_ns) -> {'tree': ..., 'node_cache': ...}
# Eliminates redundant parses when multiple rules/callers analyze the same
# unchanged file (e.g. extract_imports + extract_symbols + extract_exports
# for the same .py file during `reveal --check`).
_parse_cache: Dict[Tuple[str, int], Dict[str, Any]] = {}


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
)

# Node types for class extraction
CLASS_NODE_TYPES = (
    'class_definition',      # Python
    'class_declaration',     # Java, C#, JavaScript
    'class_specifier',       # C++
    'struct_item',           # Rust (treated as class)
    'class',                 # Ruby
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
    'function': FUNCTION_NODE_TYPES[:4],  # Most common function types
    'class': CLASS_NODE_TYPES[:2],        # Most common class types
    'struct': STRUCT_NODE_TYPES,
}

# Parent node types for hierarchical extraction (Class.method)
PARENT_NODE_TYPES = (
    'class_definition', 'class_declaration',
    'struct_item', 'struct_specifier', 'struct_declaration',
    'impl_item',              # Rust impl blocks
    'interface_declaration',
    'module',                 # Ruby module
)

# Child node types for hierarchical extraction (methods within classes)
CHILD_NODE_TYPES = (
    'function_definition', 'function_declaration',
    'method_declaration', 'method_definition',
    'function_item',         # Rust
)

# All element types for line-based extraction
ALL_ELEMENT_NODE_TYPES = (
    'function_definition', 'function_declaration', 'function_item',
    'method_declaration', 'method_definition',
    'class_definition', 'class_declaration',
    'struct_item', 'struct_specifier', 'struct_declaration',
)


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
            self.tree = cached['tree']
            if 'node_cache' in cached:
                self._node_cache = cached['node_cache']
            return

        try:
            parser = get_parser(self.language)  # type: ignore[arg-type]  # language is validated at runtime
            content_bytes = self.content.encode('utf-8')
            self._content_bytes = content_bytes  # cache for _get_node_text reuse
            self.tree = parser.parse(content_bytes)
        except Exception:
            # Parsing failed - fall back to text analysis
            self.tree = None

        if self.tree is not None:
            _parse_cache[self._cache_key] = {'tree': self.tree}

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
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
        structure['functions'] = self._extract_functions()
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

    def _extract_imports(self) -> List[Dict[str, Any]]:
        """Extract import statements."""
        imports = []

        for import_type in IMPORT_NODE_TYPES:
            nodes = self._find_nodes_by_type(import_type)
            for node in nodes:
                imports.append({
                    'line': node.start_point[0] + 1,
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

        return functions

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
            for child in decorated_node.children:
                if child.type in function_types:
                    func_node = child
                elif child.type == 'decorator':
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
                    func_line = func_node.start_point[0] + 1
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

                line_start = node.start_point[0] + 1
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
        line_start = bounds_node.start_point[0] + 1
        line_end = bounds_node.end_point[0] + 1

        complexity, depth = self._calculate_complexity_and_depth(node)
        return {
            'line': line_start,
            'line_end': line_end,
            'name': name,
            'signature': self._get_signature(node),
            'line_count': line_end - line_start + 1,
            'depth': depth,
            'complexity': complexity,
            'decorators': decorators,
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
            for child in decorated_node.children:
                if child.type in class_types:
                    class_node = child
                elif child.type == 'decorator':
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
                    class_line = class_node.start_point[0] + 1
                    tracking_lines.add((class_line, name))

        return classes, tracking_lines

    def _extract_undecorated_classes(self, class_types: List[str],
                                    processed_classes: set) -> List[Dict[str, Any]]:
        """Extract undecorated classes across all supported languages."""
        classes = []

        for class_type in class_types:
            nodes = self._find_nodes_by_type(class_type)
            for node in nodes:
                name = self._get_node_name(node)
                if not name:
                    continue

                line_start = node.start_point[0] + 1
                if (line_start, name) in processed_classes:
                    continue  # Already processed as decorated

                classes.append(self._build_class_dict(
                    node=node,
                    name=name,
                    decorators=[]
                ))

        return classes

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
        line_start = bounds_node.start_point[0] + 1
        line_end = bounds_node.end_point[0] + 1

        return {
            'line': line_start,
            'line_end': line_end,
            'name': name,
            'decorators': decorators,
        }

    def _extract_structs(self) -> List[Dict[str, Any]]:
        """Extract struct definitions (for languages that have them)."""
        structs = []

        for struct_type in STRUCT_NODE_TYPES:
            nodes = self._find_nodes_by_type(struct_type)
            for node in nodes:
                name = self._get_node_name(node)
                if name:
                    line_start = node.start_point[0] + 1
                    line_end = node.end_point[0] + 1
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
                    return {
                        'name': name,
                        'line_start': node.start_point[0] + 1,
                        'line_end': node.end_point[0] + 1,
                        'source': self._get_node_text(node),
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

        # Build cache on first access (lazy initialization)
        if not hasattr(self, '_node_cache'):
            self._node_cache: Dict[str, List[Any]] = {}
            stack = [self.tree.root_node]
            while stack:
                node = stack.pop()
                self._node_cache.setdefault(node.type, []).append(node)
                # Reverse children to maintain document order (stack is LIFO)
                children = node.children
                if children:
                    stack.extend(reversed(children))

            # Write completed node_cache back to module-level cache
            if hasattr(self, '_cache_key') and self._cache_key in _parse_cache:
                _parse_cache[self._cache_key]['node_cache'] = self._node_cache

        return self._node_cache.get(node_type, [])

    def _get_node_text(self, node) -> str:
        """Get the source text for a node.

        IMPORTANT: Tree-sitter uses byte offsets, not character offsets!
        Must slice the UTF-8 bytes, not the string, to handle multi-byte characters.

        Caches content.encode('utf-8') per instance to avoid re-encoding the
        entire file on every call (hot path: called once per symbol/function/class).
        """
        try:
            content_bytes = self._content_bytes  # type: ignore[attr-defined]
        except AttributeError:
            content_bytes = self.content.encode('utf-8')
            self._content_bytes = content_bytes  # type: ignore[attr-defined]
        return content_bytes[node.start_byte:node.end_byte].decode('utf-8')

    def _get_node_name(self, node) -> Optional[str]:
        """Get the name of a node (function/class/struct name).

        CRITICAL: For functions with return types (C/C++), the tree structure is:
            function_definition:
                type_identifier (return type) - NOT the function name!
                function_declarator (contains actual name)
                    identifier (actual function name!)

        We must search declarators BEFORE looking at type_identifier to avoid
        extracting the return type instead of the function name.
        """
        # PRIORITY 1: For C/C++ functions, look inside declarators FIRST
        # These contain the actual function/variable name, not the type
        for child in node.children:
            if child.type in ('function_declarator', 'pointer_declarator', 'declarator'):
                # Recursively search for identifier (may be nested deep)
                name = self._find_identifier_in_tree(child)
                if name:
                    return name

        # PRIORITY 2: Direct identifier/name children (most languages)
        for child in node.children:
            if child.type in ('identifier', 'name', 'constant', 'simple_identifier'):
                return self._get_node_text(child)

        # PRIORITY 3: type_identifier (fallback for structs, classes)
        # Only use this if we haven't found a name in declarators
        for child in node.children:
            if child.type == 'type_identifier':
                return self._get_node_text(child)

        # PRIORITY 4: field_identifier (for struct fields)
        for child in node.children:
            if child.type == 'field_identifier':
                return self._get_node_text(child)

        return None

    def _find_identifier_in_tree(self, node) -> Optional[str]:
        """Recursively search for an identifier in a node tree.

        Used to extract names from deeply nested declarators.
        Example: pointer_declarator → function_declarator → identifier
        """
        # Check current node
        if node.type in ('identifier', 'name', 'simple_identifier'):
            return self._get_node_text(node)

        # Search children recursively
        for child in node.children:
            # Skip pointer/reference symbols and parameter lists
            if child.type in ('*', '&', 'parameter_list', 'parameters'):
                continue

            name = self._find_identifier_in_tree(child)
            if name:
                return name

        return None

    def _get_signature(self, node) -> str:
        """Get function signature (parameters and return type only)."""
        # Look for parameters node to extract just signature part
        params_text = ''
        return_type = ''

        for child in node.children:
            if child.type in ('parameters', 'parameter_list', 'formal_parameters'):
                params_text = self._get_node_text(child)
            elif child.type in ('return_type', 'type'):
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

        return first_line

    def _get_nesting_depth(self, node) -> int:
        """Calculate maximum nesting depth within a function node.

        Delegates to _calculate_complexity_and_depth for a single-pass traversal.
        """
        if not node:
            return 0
        _, depth = self._calculate_complexity_and_depth(node)
        return depth

    def _calculate_complexity(self, node) -> int:
        """Calculate cyclomatic complexity for a function node.

        Delegates to _calculate_complexity_and_depth for a single-pass traversal.
        """
        if not node:
            return 1
        complexity, _ = self._calculate_complexity_and_depth(node)
        return complexity

    def _calculate_complexity_and_depth(self, node) -> tuple:
        """Compute cyclomatic complexity and max nesting depth in one iterative pass.

        Replaces separate recursive _calculate_complexity and _get_nesting_depth
        traversals with a single iterative stack walk, halving the node visits.

        Returns:
            (complexity, depth) where complexity = decision_count + 1
        """
        # Decision point node types across languages
        decision_types = {
            # Conditionals
            'if_statement', 'if_expression', 'if',
            'elif_clause', 'elsif',
            'else_if_clause',
            'case_statement', 'case',
            'when',
            'switch_case',
            'unless',
            # Loops
            'for_statement', 'for_expression', 'for',
            'while_statement', 'while',
            'until',
            'do_statement',
            # Boolean operators
            'boolean_operator',
            'and', 'or',
            'logical_and', 'logical_or',
            # Ternary
            'conditional_expression', 'ternary_expression',
            # Exception handling
            'except_clause', 'catch_clause',
            'rescue',
            # Pattern matching
            'match_statement', 'case_clause',
        }

        # Nesting types for depth calculation
        nesting_types = {
            'if_statement', 'if_expression', 'if',
            'for_statement', 'for_expression', 'for', 'while_statement', 'while',
            'try_statement', 'try', 'with_statement', 'with',
            'match_statement', 'match_expression', 'case_statement',
            'do_statement', 'switch_statement',
        }

        # Keyword-container pairs not to double-count
        keyword_pairs = {
            ('if_statement', 'if'),
            ('if_expression', 'if'),
            ('elif_clause', 'elif'),
            ('for_statement', 'for'),
            ('for_expression', 'for'),
            ('while_statement', 'while'),
            ('case_statement', 'case'),
            ('boolean_operator', 'or'),
            ('boolean_operator', 'and'),
        }

        decision_count = 0
        max_depth = 0

        # Stack entries: (node, n_type, current_depth)
        # n_type = type of this node (used as parent context for its children)
        stack = [(node, None, 0)]
        while stack:
            n, n_type, depth = stack.pop()
            if depth > max_depth:
                max_depth = depth
            for child in n.children:
                child_type = child.type
                # Count decision points (skip keyword children of their containers)
                if child_type in decision_types and (n_type, child_type) not in keyword_pairs:
                    decision_count += 1
                # Increase depth when entering a nesting construct
                child_depth = depth + 1 if child_type in nesting_types else depth
                stack.append((child, child_type, child_depth))

        return decision_count + 1, max_depth
