"""
Tree-sitter base analyzer for multi-language code analysis.

This module provides a unified interface for analyzing code using tree-sitter,
making it trivial to add support for new languages (Rust, C#, Go, Java, etc.).

Key Features:
- Automatic line number extraction (tree-sitter preserves exact positions)
- Common patterns: functions, classes, structs, methods, imports
- Graceful degradation when tree-sitter not available
- Simple language-specific extension via node type mapping

Plugin developers can add a new language in ~30 lines of code.
"""

from typing import Dict, Any, List, Optional, Tuple
from .base import BaseAnalyzer

# Optional dependency - gracefully handle if not installed
try:
    import warnings
    # Suppress tree-sitter deprecation warnings (fixed in future tree-sitter-languages)
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', category=FutureWarning, module='tree_sitter')
        from tree_sitter_languages import get_language, get_parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False


class TreeSitterAnalyzer(BaseAnalyzer):
    """
    Base class for tree-sitter-powered analyzers.

    Subclasses just need to:
    1. Set self.language_name (e.g., 'rust', 'c_sharp', 'go')
    2. Define node_type_map for language-specific syntax
    3. Optionally override extract_* methods for custom behavior

    Example:
        @register(['.rs'], name='Rust', icon='🦀')
        class RustAnalyzer(TreeSitterAnalyzer):
            def __init__(self, lines, **kwargs):
                super().__init__(lines, language_name='rust', **kwargs)

            node_type_map = {
                'function': 'function_item',
                'struct': 'struct_item',
                'impl': 'impl_item',
            }
    """

    def __init__(self, lines: List[str], **kwargs):
        """
        Initialize tree-sitter analyzer.

        Args:
            lines: Source code lines
            **kwargs: Passed to BaseAnalyzer (must include language_name)
        """
        super().__init__(lines, **kwargs)
        # Language name must be set by subclass before calling super().__init__()
        # or passed in kwargs
        if not hasattr(self, 'language_name'):
            self.language_name = kwargs.get('language_name', 'unknown')
        self.content = '\n'.join(lines).encode('utf-8')
        self.tree = None
        self.parse_error = None

        # Node type mapping (only initialize if subclass didn't set it)
        if not hasattr(self, 'node_type_map'):
            self.node_type_map = {}

        # Parse if tree-sitter available
        if TREE_SITTER_AVAILABLE:
            try:
                import warnings
                # Suppress tree-sitter internal deprecation warnings
                with warnings.catch_warnings():
                    warnings.filterwarnings('ignore', category=FutureWarning, module='tree_sitter')
                    parser = get_parser(self.language_name)
                    self.tree = parser.parse(self.content)
            except Exception as e:
                self.parse_error = str(e)

    def analyze_structure(self) -> Dict[str, Any]:
        """
        Analyze code structure using tree-sitter.

        Returns dict with:
        - functions: List of {'name': str, 'line': int}
        - classes/structs: List of {'name': str, 'line': int}
        - imports: List of {'name': str, 'line': int}
        - other language-specific items
        """
        if not TREE_SITTER_AVAILABLE:
            return {
                'error': 'tree-sitter not installed',
                'install': 'pip install tree-sitter tree-sitter-languages'
            }

        if self.parse_error:
            return {'error': f'Parse error: {self.parse_error}'}

        if not self.tree:
            return {'error': 'No parse tree available'}

        # Extract structure
        structure = {
            'functions': self.extract_functions(),
            'classes': self.extract_classes(),
            'structs': self.extract_structs(),
            'imports': self.extract_imports(),
        }

        # Add custom extractions from subclass
        custom = self.extract_custom()
        if custom:
            structure.update(custom)

        return structure

    def extract_functions(self) -> List[Dict[str, Any]]:
        """Extract function definitions with line numbers."""
        node_type = self.node_type_map.get('function')
        if not node_type:
            return []
        return self._extract_nodes(node_type, name_field='name')

    def extract_classes(self) -> List[Dict[str, Any]]:
        """Extract class definitions with line numbers."""
        node_type = self.node_type_map.get('class')
        if not node_type:
            return []
        return self._extract_nodes(node_type, name_field='name')

    def extract_structs(self) -> List[Dict[str, Any]]:
        """Extract struct definitions (for languages like Rust, C, Go)."""
        node_type = self.node_type_map.get('struct')
        if not node_type:
            return []
        return self._extract_nodes(node_type, name_field='name')

    def extract_imports(self) -> List[Dict[str, Any]]:
        """Extract import/use statements."""
        node_type = self.node_type_map.get('import')
        if not node_type:
            return []
        # Imports often don't have a simple 'name' field, so get full text
        return self._extract_nodes(node_type, name_field=None, use_text=True)

    def extract_custom(self) -> Optional[Dict[str, List]]:
        """
        Override in subclass to extract language-specific items.

        Example for Rust:
            return {
                'traits': self._extract_nodes('trait_item'),
                'enums': self._extract_nodes('enum_item'),
            }
        """
        return None

    def _extract_nodes(self, node_type: str, name_field: Optional[str] = 'name',
                      use_text: bool = False) -> List[Dict[str, Any]]:
        """
        Extract all nodes of a given type from the tree.

        Args:
            node_type: Tree-sitter node type to find
            name_field: Name of the field containing the identifier (default: 'name')
            use_text: If True, use full node text instead of name field

        Returns:
            List of {'name': str, 'line': int} dicts
        """
        if not self.tree:
            return []

        results = []
        cursor = self.tree.walk()

        def visit(cursor):
            """Recursive tree walker."""
            node = cursor.node

            if node.type == node_type:
                # Extract name
                if use_text:
                    name = node.text.decode('utf-8').strip()
                elif name_field:
                    name_node = node.child_by_field_name(name_field)
                    if name_node:
                        name = name_node.text.decode('utf-8')
                    else:
                        name = f"<{node_type}>"
                else:
                    name = f"<{node_type}>"

                # Line numbers are 0-indexed in tree-sitter, convert to 1-indexed
                line = node.start_point[0] + 1

                # Only include if in focus range
                if self.in_focus_range(line):
                    results.append({
                        'name': name,
                        'line': line
                    })

            # Recurse to children
            if cursor.goto_first_child():
                visit(cursor)
                while cursor.goto_next_sibling():
                    visit(cursor)
                cursor.goto_parent()

        visit(cursor)
        return results

    def generate_preview(self) -> List[Tuple[int, str]]:
        """
        Generate preview showing first few functions/classes.

        Subclasses can override for custom preview behavior.
        """
        preview = []

        # Show first comment block if exists
        for i, line in enumerate(self.lines[:20], 1):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                preview.append((i, line))
            elif stripped and not preview:
                # First non-comment line
                preview.append((i, line))
                break
            elif stripped:
                break

        # Show first few functions/classes
        structure = self.analyze_structure()
        functions = structure.get('functions', [])[:5]
        classes = structure.get('classes', [])[:5]
        structs = structure.get('structs', [])[:5]

        items = functions + classes + structs
        items.sort(key=lambda x: x['line'])

        for item in items[:10]:
            line_num = item['line']
            if line_num <= len(self.lines):
                preview.append((line_num, self.lines[line_num - 1]))

        return preview[:30]

    def get_supported_languages(self) -> List[str]:
        """Return list of languages supported by tree-sitter installation."""
        if not TREE_SITTER_AVAILABLE:
            return []

        # Common languages available in tree-sitter-languages
        common = [
            'rust', 'c_sharp', 'go', 'java', 'javascript', 'typescript',
            'python', 'c', 'cpp', 'ruby', 'php', 'swift', 'kotlin',
            'scala', 'haskell', 'ocaml', 'bash', 'lua', 'r',
        ]

        available = []
        for lang in common:
            try:
                get_language(lang)
                available.append(lang)
            except Exception:
                pass

        return available
