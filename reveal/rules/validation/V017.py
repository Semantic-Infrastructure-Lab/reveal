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

from ..base import BaseRule, Detection, RulePrefix, Severity, RuleScope
from .utils import find_reveal_root


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
    scope = RuleScope.CROSS_FILE
    message = "Tree-sitter node types missing for supported language"
    category = RulePrefix.V
    severity = Severity.HIGH
    file_patterns = []  # No file-extension form; reveal:// self-check only
    uri_patterns = ['^reveal://.*']
    version = "1.0.0"
    internal = True  # only ever validates reveal's own treesitter.py

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check tree-sitter node type coverage of reveal's own source.

        The evidence is two files read together: core/node_taxonomy.py holds the function and
        class node types (BACK-814, BACK-911), treesitter.py the identifier kinds. Either alone
        answers wrongly, so the registry matches this rule to a ``reveal://`` target only
        (BACK-2253) and ``reveal://`` carries no content of its own: both files are read here.

        Args:
            file_path: ``reveal://...`` for a self-check; anything else is not applicable
            structure: Unused
            content: Unused

        Returns:
            List of detections for missing node type coverage
        """
        if not file_path.startswith('reveal://'):
            return []
        reveal_root = find_reveal_root()
        if not reveal_root:
            return self.unavailable("reveal source root unavailable")
        # BACK-911 left a back-compat shim (no frozenset literals) at the old adapters/ast/
        # path: read core/ first.
        taxonomy_path = reveal_root / 'core' / 'node_taxonomy.py'
        if not taxonomy_path.exists():
            taxonomy_path = reveal_root / 'adapters' / 'ast' / 'node_taxonomy.py'
        treesitter_path = reveal_root / 'treesitter.py'
        if not taxonomy_path.exists():
            return self.unavailable("required source or documentation missing", taxonomy_path.as_posix())
        try:
            taxonomy = taxonomy_path.read_text(encoding='utf-8')
            identifiers = (
                treesitter_path.read_text(encoding='utf-8')
                if treesitter_path.exists() else taxonomy
            )
        except OSError:
            return self.unavailable("required input could not be inspected")
        return self.check_sources(str(taxonomy_path), taxonomy, identifiers)

    def check_sources(self,
                      file_path: str,
                      content: str,
                      identifier_content: Optional[str] = None) -> List[Detection]:
        """Judge node type coverage in *content* (the taxonomy) and *identifier_content*.

        *identifier_content* is the source of the name-extraction kinds (treesitter.py);
        it defaults to *content*.
        """
        if identifier_content is None:
            identifier_content = content

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
        if 'simple_identifier' not in identifier_content and 'identifier' in identifier_content:
            # Check if we need simple_identifier (Kotlin, Swift use this)
            detections.append(self.create_detection(
                file_path,
                self._find_line_number(identifier_content, 'identifier'),
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

    # Python type annotation keywords that may appear in method signatures
    _TYPE_ANNOTATION_WORDS: Set[str] = {
        'str', 'int', 'bool', 'float', 'list', 'dict', 'tuple',
        'set', 'any', 'optional', 'none', 'true', 'false',
    }

    def _extract_strings_filtered(self, text: str) -> List[str]:
        """Extract quoted lowercase strings, removing type-annotation keywords."""
        raw = re.findall(r"['\"]([a-z_]+)['\"]", text)
        return [t for t in raw if t not in self._TYPE_ANNOTATION_WORDS]

    def _extract_function_types(self, content: str) -> List[str]:
        """Extract function node types from node_taxonomy.py's DEF_NODES frozenset
        (BACK-814 source of truth), falling back to the pre-BACK-814
        _get_function_node_types()/FUNCTION_NODE_TYPES shapes for direct
        invocation against an older/unrefactored treesitter.py.

        Args:
            content: File content

        Returns:
            List of function node type strings
        """
        # Match from the frozenset opener up to (and including) its closing '}'.
        # re.DOTALL allows matching across lines for the multi-line literal.
        match = re.search(r"DEF_NODES:\s*frozenset\s*=\s*frozenset\(\{.*?\}\)", content, re.DOTALL)
        if match:
            types = self._extract_strings_filtered(match.group(0))
            if types:
                return types

        # Fallback: pre-BACK-814 treesitter.py shapes
        match = re.search(r"def _get_function_node_types.*?\]", content, re.DOTALL)
        if match:
            types = self._extract_strings_filtered(match.group(0))
            if types:
                return types
        const_match = re.search(r"FUNCTION_NODE_TYPES\s*=\s*\(.*?\)", content, re.DOTALL)
        if const_match:
            return self._extract_strings_filtered(const_match.group(0))

        return []

    def _extract_class_types(self, content: str) -> List[str]:
        """Extract class node types from node_taxonomy.py's CLASS_NODES frozenset
        (BACK-814 source of truth), falling back to the pre-BACK-814
        _get_class_node_types()/CLASS_NODE_TYPES shapes for direct invocation
        against an older/unrefactored treesitter.py.

        Args:
            content: File content

        Returns:
            List of class node type strings
        """
        match = re.search(r"CLASS_NODES:\s*frozenset\s*=\s*frozenset\(\{.*?\}\)", content, re.DOTALL)
        if match:
            types = self._extract_strings_filtered(match.group(0))
            if types:
                return types

        # Fallback: pre-BACK-814 treesitter.py shapes
        match = re.search(r"def _get_class_node_types.*?\]", content, re.DOTALL)
        if match:
            types = self._extract_strings_filtered(match.group(0))
            if types:
                return types
        const_match = re.search(r"CLASS_NODE_TYPES\s*=\s*\(.*?\)", content, re.DOTALL)
        if const_match:
            return self._extract_strings_filtered(const_match.group(0))

        return []

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
