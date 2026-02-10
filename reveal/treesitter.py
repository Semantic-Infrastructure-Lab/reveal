"""Tree-sitter based analyzer for multi-language support."""

from typing import Dict, List, Any, Optional
from .base import FileAnalyzer
from .core import suppress_treesitter_warnings

# Suppress tree-sitter deprecation warnings (centralized in core module)
suppress_treesitter_warnings()

from tree_sitter_language_pack import get_parser


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
    'local_function_definition_statement', # Lua (local functions)
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
    'import_from_statement', # Python
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

    language: str = None  # Set in subclass

    def __init__(self, path: str):
        super().__init__(path)
        self.tree = None

        if self.language:
            self._parse_tree()

    def _parse_tree(self):
        """Parse file with tree-sitter.

        Note: Tree-sitter warnings are suppressed at module level via
        suppress_treesitter_warnings() call at top of file.
        """
        try:
            parser = get_parser(self.language)
            self.tree = parser.parse(self.content.encode('utf-8'))
        except Exception:
            # Parsing failed - fall back to text analysis
            self.tree = None

    def get_structure(self, head: int = None, tail: int = None,
                      range: tuple = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
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

    def _extract_decorated_functions(self, function_types: List[str]):
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

        return {
            'line': line_start,
            'line_end': line_end,
            'name': name,
            'signature': self._get_signature(node),
            'line_count': line_end - line_start + 1,
            'depth': self._get_nesting_depth(node),
            'complexity': self._calculate_complexity(node),
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

    def _extract_decorated_classes(self, class_types: List[str]):
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

    def _find_nodes_by_type(self, node_type: str) -> List:
        """Find all nodes of a given type in the tree.

        Uses single-pass caching: first call walks entire tree once and caches
        ALL node types. Subsequent calls return from cache. This is 5-6x faster
        than walking the tree separately for each node type query.
        """
        if not self.tree:
            return []

        # Build cache on first access (lazy initialization)
        if not hasattr(self, '_node_cache'):
            self._node_cache = {}
            stack = [self.tree.root_node]
            while stack:
                node = stack.pop()
                node_t = node.type
                if node_t not in self._node_cache:
                    self._node_cache[node_t] = []
                self._node_cache[node_t].append(node)
                # Reverse children to maintain document order (stack is LIFO)
                stack.extend(reversed(node.children))

        return self._node_cache.get(node_type, [])

    def _get_node_text(self, node) -> str:
        """Get the source text for a node.

        IMPORTANT: Tree-sitter uses byte offsets, not character offsets!
        Must slice the UTF-8 bytes, not the string, to handle multi-byte characters.
        """
        start_byte = node.start_byte
        end_byte = node.end_byte
        # Convert to bytes, slice, then decode back to string
        content_bytes = self.content.encode('utf-8')
        return content_bytes[start_byte:end_byte].decode('utf-8')

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

        Counts control flow structures: if, for, while, with, try, match, etc.

        Args:
            node: Tree-sitter node (function/method)

        Returns:
            Maximum nesting depth (0 = no nesting)
        """
        if not node:
            return 0

        # Control flow node types across languages
        nesting_types = {
            # Conditionals
            'if_statement', 'if_expression', 'if',
            # Loops
            'for_statement', 'for_expression', 'for', 'while_statement', 'while',
            # Exception handling
            'try_statement', 'try', 'with_statement', 'with',
            # Pattern matching
            'match_statement', 'match_expression', 'case_statement',
            # Other control flow
            'do_statement', 'switch_statement',
        }

        def get_depth(n, current_depth=0):
            """Recursively calculate depth."""
            max_depth = current_depth

            for child in n.children:
                child_depth = current_depth
                # If this child is a nesting construct, increase depth
                if child.type in nesting_types:
                    child_depth = current_depth + 1

                # Recursively check children
                nested_depth = get_depth(child, child_depth)
                max_depth = max(max_depth, nested_depth)

            return max_depth

        return get_depth(node)

    def _calculate_complexity(self, node) -> int:
        """Calculate cyclomatic complexity for a function node.

        McCabe complexity: count of decision points + 1
        Decision points: if, elif, for, while, and, or, try/except, case, etc.

        Args:
            node: Tree-sitter node (function/method)

        Returns:
            Cyclomatic complexity score (1 = simple, higher = more complex)
        """
        if not node:
            return 1

        # Decision point node types across languages
        # These represent branches in the control flow
        #
        # IMPORTANT: Include both long forms (Python's if_statement) and
        # short forms (Ruby's if, case, when) as they serve as containers
        # in different languages.
        #
        # Note: In Python, 'if' nodes are just keywords with no decision-relevant
        # children, so they don't cause double-counting. In Ruby, 'if' is the
        # actual container node type.
        decision_types = {
            # Conditionals (each branch is a decision point)
            'if_statement', 'if_expression', 'if',  # Python uses if_statement, Ruby uses if
            'elif_clause', 'elsif',  # Python uses elif_clause, Ruby uses elsif
            'else_if_clause',
            'case_statement', 'case',  # Python uses case_statement, Ruby uses case
            'when',  # Ruby case branches
            'switch_case',
            'unless',  # Ruby negative conditional

            # Loops (each loop is a decision point)
            'for_statement', 'for_expression', 'for',  # Ruby uses 'for'
            'while_statement', 'while',  # Ruby uses 'while'
            'until',  # Ruby negative loop
            'do_statement',

            # Boolean operators (each adds a branch)
            'boolean_operator',  # Python, generic
            'and', 'or',  # Ruby uses and/or as node types
            'logical_and', 'logical_or',  # C-family (JavaScript, C++, etc.)

            # Ternary/conditional expressions
            'conditional_expression', 'ternary_expression',

            # Exception handling (each except/catch is a branch)
            'except_clause', 'catch_clause',
            'rescue',  # Ruby exception handling

            # Pattern matching
            'match_statement', 'case_clause',
        }

        # Keyword-container pairs that should not be double-counted
        # Format: (parent_type, child_type) - if child is just a keyword for parent, skip it
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

        def count_decisions(n, parent_type=None):
            """Recursively count decision points.

            Args:
                n: Current node
                parent_type: Type of parent node (to detect keyword children)
            """
            count = 0

            for child in n.children:
                child_is_decision = child.type in decision_types

                # Skip if this is a keyword child of its container
                # (e.g., 'if' keyword inside 'if_statement' in Python)
                is_keyword_child = (parent_type, child.type) in keyword_pairs

                # Count if this is a decision type and not a keyword child
                if child_is_decision and not is_keyword_child:
                    count += 1

                # Recursively count in children, passing current node type as parent
                count += count_decisions(child, parent_type=child.type)

            return count

        # McCabe complexity = decision points + 1
        return count_decisions(node) + 1
