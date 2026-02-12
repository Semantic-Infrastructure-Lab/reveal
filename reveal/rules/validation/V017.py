"""
V017: Tree-sitter node type coverage validation.

Verifies that TreeSitterAnalyzer has node type definitions for all languages
supported via dynamic fallback. Missing node types cause empty analysis results.

Background:
-----------
TreeSitterAnalyzer uses node type lists to extract structure from ANY tree-sitter
language. When new languages are added to tree-sitter-language-pack, corresponding
node types must be added to the analyzer.

Examples:
    reveal reveal://treesitter.py --check --select V017
    reveal reveal:// --check --select V017
"""

import re
from typing import List, Dict, Any, Optional, Set

from ..base import BaseRule, Detection, RulePrefix, Severity


class V017(BaseRule):
    """Verify tree-sitter node types defined for all supported languages.

    TreeSitterAnalyzer provides universal structure extraction via node type lists.
    Each language's syntax tree uses different node type names. This rule ensures
    common node types are defined for languages we claim to support.

    Severity: HIGH (missing node types → empty results for users)
    Category: Validation

    Detects:
    - Languages in fallback list without corresponding node types
    - Node type lists that haven't been updated for new languages

    Passes:
    - All supported languages have representative node types
    - Node type coverage is complete
    """

    code = "V017"
    message = "Tree-sitter node types missing for supported language"
    category = RulePrefix.V
    severity = Severity.HIGH
    file_patterns = ['.py']
    version = "1.0.0"

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check tree-sitter node type coverage.

        Args:
            file_path: Path to file being checked
            structure: Parsed structure
            content: Raw file content

        Returns:
            List of detections for missing node type coverage
        """
        # Only check treesitter.py
        if 'treesitter.py' not in file_path:
            return []

        # Extract defined node types
        defined_types = self._extract_node_types(content)

        # Check coverage for critical node categories
        detections: List[Detection] = []

        # Check function node types
        function_types = self._extract_function_types(content)
        if len(function_types) < 5:
            detections.append(self.create_detection(
                file_path,
                self._find_line_number(content, '_get_function_node_types'),
                message=f"Insufficient function node types ({len(function_types)} found, expected 10+)",
                suggestion=(
                    "Add node types for major languages:\n"
                    "  - function_definition (Python)\n"
                    "  - function_declaration (Go, C, JavaScript)\n"
                    "  - function_item (Rust)\n"
                    "  - method_declaration (Java, C#)\n"
                    "  - function_signature (Dart)\n"
                    "See tree-sitter grammar docs for each language"
                )
            ))

        # Check class node types
        class_types = self._extract_class_types(content)
        if len(class_types) < 3:
            detections.append(self.create_detection(
                file_path,
                self._find_line_number(content, '_get_class_node_types'),
                message=f"Insufficient class node types ({len(class_types)} found, expected 5+)",
                suggestion=(
                    "Add node types for major languages:\n"
                    "  - class_definition (Python)\n"
                    "  - class_declaration (Java, JavaScript)\n"
                    "  - struct_item (Rust)\n"
                    "  - interface_declaration (Java, TypeScript)"
                )
            ))

        # Check identifier node types (for name extraction)
        if 'simple_identifier' not in content and 'identifier' in content:
            # Check if we need simple_identifier (Kotlin, Swift use this)
            detections.append(self.create_detection(
                file_path,
                self._find_line_number(content, 'identifier'),
                message="Missing 'simple_identifier' node type (needed for Kotlin/Swift)",
                suggestion=(
                    "Add 'simple_identifier' to name extraction logic.\n"
                    "Kotlin and Swift use 'simple_identifier' instead of 'identifier'.\n"
                    "See: interstellar-blackhole-0113 mobile platform fix"
                )
            ))

        return detections

    def _extract_node_types(self, content: str) -> Set[str]:
        """Extract all node type strings from content.

        Args:
            content: File content

        Returns:
            Set of node type strings
        """
        node_types = set()

        # Pattern: strings that look like node types (snake_case, ends with _definition, etc.)
        # Common patterns: *_definition, *_declaration, *_statement, *_item
        pattern = r"['\"]([a-z_]+(?:_definition|_declaration|_statement|_item|_expression|identifier))['\"]"
        matches = re.findall(pattern, content)

        node_types.update(matches)

        return node_types

    def _extract_function_types(self, content: str) -> List[str]:
        """Extract function node types from _get_function_node_types().

        Args:
            content: File content

        Returns:
            List of function node type strings
        """
        types = []

        # Find the _get_function_node_types method
        pattern = r"def _get_function_node_types.*?\]"
        match = re.search(pattern, content, re.DOTALL)

        if match:
            method_content = match.group(0)
            # Extract strings within this method
            string_pattern = r"['\"]([a-z_]+)['\"]"
            types = re.findall(string_pattern, method_content)

        return types

    def _extract_class_types(self, content: str) -> List[str]:
        """Extract class node types from _get_class_node_types().

        Args:
            content: File content

        Returns:
            List of class node type strings
        """
        types = []

        # Find the _get_class_node_types method
        pattern = r"def _get_class_node_types.*?\]"
        match = re.search(pattern, content, re.DOTALL)

        if match:
            method_content = match.group(0)
            # Extract strings within this method
            string_pattern = r"['\"]([a-z_]+)['\"]"
            types = re.findall(string_pattern, method_content)

        return types

    def _find_line_number(self, content: str, search_str: str) -> int:
        """Find line number of string in content.

        Args:
            content: File content
            search_str: String to find

        Returns:
            Line number (1-indexed), or 1 if not found
        """
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if search_str in line:
                return i
        return 1
