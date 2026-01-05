"""Tree-sitter based analyzer for multi-language support."""

import warnings
from typing import Dict, List, Any, Optional
from .base import FileAnalyzer

# Suppress tree-sitter deprecation warnings globally
warnings.filterwarnings('ignore', category=FutureWarning, module='tree_sitter')

from tree_sitter_languages import get_parser


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
        """Parse file with tree-sitter."""
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', category=FutureWarning, module='tree_sitter')
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

        # Common import node types across languages
        import_types = [
            'import_statement',      # Python, JavaScript
            'import_declaration',    # Go, Java
            'use_declaration',       # Rust
            'using_directive',       # C#
            'import_from_statement', # Python
            'preproc_include',       # C/C++
        ]

        for import_type in import_types:
            nodes = self._find_nodes_by_type(import_type)
            for node in nodes:
                imports.append({
                    'line': node.start_point[0] + 1,
                    'content': self._get_node_text(node),
                })

        return imports

    def _extract_functions(self) -> List[Dict[str, Any]]:
        """Extract function definitions with complexity metrics and decorators."""
        functions = []
        # Track by (line, name) to avoid duplicates (tree-sitter may return different objects)
        processed_funcs = set()

        # Common function node types
        function_types = [
            'function_definition',   # Python
            'function_declaration',  # Go, C, JavaScript
            'function_item',         # Rust
            'method_declaration',    # Java, C#, Kotlin
            'function',              # Generic
            'method',                # Ruby
            'function_definition_statement',  # Lua (global functions)
            'local_function_definition_statement',  # Lua (local functions)
        ]

        # Step 1: Find decorated functions (Python)
        # decorated_definition contains decorator(s) + function/class
        decorated_nodes = self._find_nodes_by_type('decorated_definition')
        for decorated_node in decorated_nodes:
            func_node = None
            decorators = []

            # Find function_definition child and decorator siblings
            for child in decorated_node.children:
                if child.type in function_types:
                    func_node = child
                elif child.type == 'decorator':
                    decorators.append(self._get_node_text(child))

            if func_node:
                name = self._get_node_name(func_node)
                if name:
                    # Use decorated_definition bounds (includes decorators)
                    line_start = decorated_node.start_point[0] + 1
                    line_end = decorated_node.end_point[0] + 1
                    line_count = line_end - line_start + 1
                    # Track by func_node line (not decorated_node) to match step 2
                    func_line = func_node.start_point[0] + 1

                    functions.append({
                        'line': line_start,
                        'line_end': line_end,
                        'name': name,
                        'signature': self._get_signature(func_node),
                        'line_count': line_count,
                        'depth': self._get_nesting_depth(func_node),
                        'complexity': self._calculate_complexity(func_node),
                        'decorators': decorators,
                    })
                    processed_funcs.add((func_line, name))

        # Step 2: Find undecorated functions
        for func_type in function_types:
            nodes = self._find_nodes_by_type(func_type)
            for node in nodes:
                name = self._get_node_name(node)
                if not name:
                    continue

                line_start = node.start_point[0] + 1
                if (line_start, name) in processed_funcs:
                    continue  # Already processed as decorated

                line_end = node.end_point[0] + 1
                line_count = line_end - line_start + 1

                functions.append({
                    'line': line_start,
                    'line_end': line_end,
                    'name': name,
                    'signature': self._get_signature(node),
                    'line_count': line_count,
                    'depth': self._get_nesting_depth(node),
                    'complexity': self._calculate_complexity(node),
                    'decorators': [],
                })

        return functions

    def _extract_classes(self) -> List[Dict[str, Any]]:
        """Extract class definitions with decorators."""
        classes = []
        # Track by (line, name) to avoid duplicates (tree-sitter may return different objects)
        processed_classes = set()

        class_types = [
            'class_definition',      # Python
            'class_declaration',     # Java, C#, JavaScript, Kotlin
            'class_specifier',       # C++
            'struct_item',           # Rust (treated as class)
            'class',                 # Ruby
            'object_declaration',    # Kotlin
        ]

        # Step 1: Find decorated classes (Python)
        decorated_nodes = self._find_nodes_by_type('decorated_definition')
        for decorated_node in decorated_nodes:
            class_node = None
            decorators = []

            # Find class_definition child and decorator siblings
            for child in decorated_node.children:
                if child.type in class_types:
                    class_node = child
                elif child.type == 'decorator':
                    decorators.append(self._get_node_text(child))

            if class_node:
                name = self._get_node_name(class_node)
                if name:
                    # Use decorated_definition bounds (includes decorators)
                    line_start = decorated_node.start_point[0] + 1
                    line_end = decorated_node.end_point[0] + 1
                    # Track by class_node line (not decorated_node) to match step 2
                    class_line = class_node.start_point[0] + 1
                    classes.append({
                        'line': line_start,
                        'line_end': line_end,
                        'name': name,
                        'decorators': decorators,
                    })
                    processed_classes.add((class_line, name))

        # Step 2: Find undecorated classes
        for class_type in class_types:
            nodes = self._find_nodes_by_type(class_type)
            for node in nodes:
                name = self._get_node_name(node)
                if not name:
                    continue

                line_start = node.start_point[0] + 1
                if (line_start, name) in processed_classes:
                    continue  # Already processed as decorated

                line_end = node.end_point[0] + 1
                classes.append({
                    'line': line_start,
                    'line_end': line_end,
                    'name': name,
                    'decorators': [],
                })

        return classes

    def _extract_structs(self) -> List[Dict[str, Any]]:
        """Extract struct definitions (for languages that have them)."""
        structs = []

        struct_types = [
            'struct_item',           # Rust
            'struct_specifier',      # C/C++
            'struct_declaration',    # Go
        ]

        for struct_type in struct_types:
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

        # Map element type to node types
        type_map = {
            'function': ['function_definition', 'function_declaration', 'function_item', 'method_declaration'],
            'class': ['class_definition', 'class_declaration'],
            'struct': ['struct_item', 'struct_specifier', 'struct_declaration'],
        }

        node_types = type_map.get(element_type, [element_type])

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
        """Find all nodes of a given type in the tree."""
        if not self.tree:
            return []

        nodes = []

        def walk(node):
            if node.type == node_type:
                nodes.append(node)
            for child in node.children:
                walk(child)

        walk(self.tree.root_node)
        return nodes

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
            if child.type in ('identifier', 'name', 'constant'):
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
        if node.type in ('identifier', 'name'):
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
        Inspired by TIA's complexity scanner.

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
        decision_types = {
            # Conditionals (each branch is a decision point)
            'if_statement', 'if_expression', 'if',
            'elif_clause', 'else_if_clause',
            'case_statement', 'switch_case',

            # Loops (each loop is a decision point)
            'for_statement', 'for_expression', 'for',
            'while_statement', 'while',
            'do_statement',

            # Boolean operators (each adds a branch)
            'boolean_operator', 'binary_operator',  # Generic
            'and', 'or',  # Python
            'logical_and', 'logical_or',  # C-family

            # Ternary/conditional expressions
            'conditional_expression', 'ternary_expression',

            # Exception handling (each except/catch is a branch)
            'except_clause', 'catch_clause',

            # Pattern matching
            'match_statement', 'case_clause',
        }

        def count_decisions(n):
            """Recursively count decision points."""
            count = 0

            for child in n.children:
                # Count this node if it's a decision point
                if child.type in decision_types:
                    count += 1

                # Special handling for boolean operators in expressions
                # Check if operator is 'and' or 'or' by examining node text
                if child.type in ('binary_operator', 'boolean_operator'):
                    text = self._get_node_text(child)
                    if text and any(op in text for op in [' and ', ' or ', '&&', '||']):
                        count += 1

                # Recursively count in children
                count += count_decisions(child)

            return count

        # McCabe complexity = decision points + 1
        return count_decisions(node) + 1
