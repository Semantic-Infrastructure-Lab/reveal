"""Tree-sitter based analyzer for multi-language support."""

import warnings
from typing import Dict, List, Any, Optional
from .base import FileAnalyzer

# Optional tree-sitter import
try:
    from tree_sitter_languages import get_parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    get_parser = None


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

        if TREE_SITTER_AVAILABLE and self.language:
            self._parse_tree()

    def _parse_tree(self):
        """Parse file with tree-sitter."""
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', category=FutureWarning, module='tree_sitter')
                parser = get_parser(self.language)
                self.tree = parser.parse(self.content.encode('utf-8'))
        except Exception as e:
            # Parsing failed - fall back to text analysis
            self.tree = None

    def get_structure(self) -> Dict[str, List[Dict[str, Any]]]:
        """Extract structure using tree-sitter.

        Returns imports, functions, classes, structs, etc.
        Works for ANY tree-sitter language!
        """
        if not self.tree:
            return {}

        structure = {}

        # Extract common elements
        structure['imports'] = self._extract_imports()
        structure['functions'] = self._extract_functions()
        structure['classes'] = self._extract_classes()
        structure['structs'] = self._extract_structs()

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
        """Extract function definitions."""
        functions = []

        # Common function node types
        function_types = [
            'function_definition',   # Python
            'function_declaration',  # Go, C, JavaScript
            'function_item',         # Rust
            'method_declaration',    # Java, C#
            'function',              # Generic
        ]

        for func_type in function_types:
            nodes = self._find_nodes_by_type(func_type)
            for node in nodes:
                name = self._get_function_name(node)
                if name:
                    functions.append({
                        'line': node.start_point[0] + 1,
                        'name': name,
                        'signature': self._get_signature(node),
                    })

        return functions

    def _extract_classes(self) -> List[Dict[str, Any]]:
        """Extract class definitions."""
        classes = []

        class_types = [
            'class_definition',      # Python
            'class_declaration',     # Java, C#, JavaScript
            'struct_item',           # Rust (treated as class)
        ]

        for class_type in class_types:
            nodes = self._find_nodes_by_type(class_type)
            for node in nodes:
                name = self._get_class_name(node)
                if name:
                    classes.append({
                        'line': node.start_point[0] + 1,
                        'name': name,
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
                name = self._get_struct_name(node)
                if name:
                    structs.append({
                        'line': node.start_point[0] + 1,
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
        """Get the source text for a node."""
        start_byte = node.start_byte
        end_byte = node.end_byte
        return self.content[start_byte:end_byte]

    def _get_node_name(self, node) -> Optional[str]:
        """Get the name of a node (function/class/struct name)."""
        # Look for 'name' or 'identifier' child
        for child in node.children:
            if child.type in ('identifier', 'name'):
                return self._get_node_text(child)

        return None

    def _get_function_name(self, node) -> Optional[str]:
        """Extract function name from function node."""
        return self._get_node_name(node)

    def _get_class_name(self, node) -> Optional[str]:
        """Extract class name from class node."""
        return self._get_node_name(node)

    def _get_struct_name(self, node) -> Optional[str]:
        """Extract struct name from struct node."""
        return self._get_node_name(node)

    def _get_signature(self, node) -> str:
        """Get function signature (simplified)."""
        # Just return first line for now
        text = self._get_node_text(node)
        first_line = text.split('\n')[0]
        return first_line.strip()
