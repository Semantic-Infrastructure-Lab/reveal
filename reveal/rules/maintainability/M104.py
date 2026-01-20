"""M104: Hardcoded list detector.

Detects hardcoded lists that may become stale or are duplicated.
Focuses on high-staleness-risk patterns: tree-sitter node types,
file extensions, entity types, etc.

Example violation:
    # This list will become stale when new languages are added
    EXTENSIONS = ['.py', '.js', '.ts', '.go', '.rs']

    # Better: derive from registered analyzers or use a constant
    EXTENSIONS = list(ANALYZER_REGISTRY.keys())

This rule helps identify:
- Lists that should be centralized constants
- Duplicated lists across files
- Lists likely to become outdated
"""

import ast
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

from ..base import BaseRule, Detection, RulePrefix, Severity
from ..base_mixins import ASTParsingMixin


class M104(BaseRule, ASTParsingMixin):
    """Detect hardcoded lists that may become stale."""

    code = "M104"
    message = "Hardcoded list detected"
    category = RulePrefix.M
    severity = Severity.LOW
    file_patterns = ['.py']

    # Minimum list size to flag (smaller lists are often intentional)
    MIN_LIST_SIZE = 5
    # Lower threshold for dict values (these are often lookup tables)
    MIN_DICT_VALUE_SIZE = 3

    # Known stable lists that should be suppressed (lowercase patterns)
    STABLE_PATTERNS = {
        # Output formats are contract-bound
        'output_format', 'format',
        # HTML tags are HTML5 spec
        'semantic_tag', 'html_tag',
        # Test data
        'test_', 'mock_', 'fixture',
        # __all__ exports
        '__all__',
    }

    # High-staleness-risk patterns (lowercase)
    HIGH_RISK_PATTERNS = {
        'extension': 'File extensions change as new formats emerge',
        'node_type': 'Tree-sitter node types change with grammar updates',
        'type_map': 'Type mappings need updates for new languages',
        'pattern': 'Patterns may need updates for new cases',
    }

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check for hardcoded lists in Python files."""
        tree, detections = self._parse_python_or_skip(content, file_path)
        if tree is None:
            return detections

        # Find all list assignments
        for node in ast.walk(tree):
            # Module-level or class-level list assignments
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and isinstance(node.value, ast.List):
                        detection = self._check_list_assignment(
                            file_path, target.id, node.value, node.lineno
                        )
                        if detection:
                            detections.append(detection)

            # Dict with list values (common pattern for mappings)
            # Flag dicts that have many list values - these are often lookup tables
            # that should be derived from a single source of truth
            if isinstance(node, ast.Dict):
                list_value_count = 0
                for key, val in zip(node.keys, node.values):
                    if isinstance(val, ast.List) and len(val.elts) >= self.MIN_DICT_VALUE_SIZE:
                        list_value_count += 1

                # Flag if dict has 5+ list values (significant lookup table)
                if list_value_count >= 5:
                    sample_keys = []
                    for key, val in zip(node.keys, node.values):
                        if isinstance(val, ast.List) and len(val.elts) >= self.MIN_DICT_VALUE_SIZE:
                            key_name = key.value if isinstance(key, ast.Constant) else '?'
                            sample_keys.append(str(key_name))
                            if len(sample_keys) >= 3:
                                break

                    detections.append(self.create_detection(
                        file_path=file_path,
                        line=node.lineno,
                        message=f"Large lookup table with {list_value_count} hardcoded list values",
                        suggestion="Consider deriving these mappings from registered components or a central config",
                        context=f"Keys include: {', '.join(sample_keys)}...",
                        severity=Severity.MEDIUM
                    ))

        return detections

    def _check_list_assignment(self, file_path: str, name: str,
                               list_node: ast.List, line: int) -> Optional[Detection]:
        """Check a named list assignment."""
        if len(list_node.elts) < self.MIN_LIST_SIZE:
            return None

        name_lower = name.lower()

        # Skip known stable patterns
        if any(pattern in name_lower for pattern in self.STABLE_PATTERNS):
            return None

        # Extract values for classification
        values = self._extract_list_values(list_node)
        classification = self._classify_list(name, values)

        # Only flag high-risk lists
        if classification == 'STABLE':
            return None

        # Check for high-staleness-risk patterns
        risk_reason = None
        for pattern, reason in self.HIGH_RISK_PATTERNS.items():
            if pattern in name_lower:
                risk_reason = reason
                break

        # Also flag lists with file extensions
        if any(str(v).startswith('.') and len(str(v)) <= 6 for v in values[:5]):
            risk_reason = 'File extension lists may become stale'
            classification = 'FILE_EXTENSIONS'

        # Flag tree-sitter node types
        if any('_definition' in str(v) or '_declaration' in str(v) for v in values):
            risk_reason = 'Tree-sitter node types change with grammar updates'
            classification = 'TREESITTER_NODES'

        if not risk_reason and classification == 'OTHER':
            return None

        sample = ', '.join(str(v) for v in values[:3])
        if len(values) > 3:
            sample += f', ... ({len(values)} items)'

        return self.create_detection(
            file_path=file_path,
            line=line,
            message=f"Hardcoded list '{name}' ({classification})",
            suggestion=f"Consider extracting to a constant or deriving dynamically. {risk_reason or ''}",
            context=f"[{sample}]"
        )

    def _check_dict_list_value(self, file_path: str, key_name: str,
                                list_node: ast.List, line: int) -> Optional[Detection]:
        """Check a list value in a dictionary."""
        values = self._extract_list_values(list_node)
        classification = self._classify_list(key_name, values)

        if classification in ('STABLE', 'OTHER'):
            return None

        sample = ', '.join(str(v) for v in values[:3])

        return self.create_detection(
            file_path=file_path,
            line=line,
            message=f"Hardcoded list in dict['{key_name}'] ({classification})",
            suggestion="Consider extracting repeated patterns to constants",
            context=f"[{sample}, ...]",
            severity=Severity.LOW
        )

    def _extract_list_values(self, list_node: ast.List) -> List[Any]:
        """Extract constant values from a list AST node."""
        values = []
        for elt in list_node.elts:
            if isinstance(elt, ast.Constant):
                values.append(elt.value)
        return values

    def _classify_list(self, name: str, values: List[Any]) -> str:
        """Classify what kind of hardcoded list this is."""
        if not values:
            return 'OTHER'

        name_lower = (name or '').lower()

        # File extensions
        if any(str(v).startswith('.') and len(str(v)) <= 6 for v in values[:5]):
            return 'FILE_EXTENSIONS'

        # Tree-sitter node types
        if any('_definition' in str(v) or '_declaration' in str(v) for v in values):
            return 'TREESITTER_NODES'

        # Entity types
        entity_keywords = {'function', 'class', 'method', 'struct', 'interface', 'module'}
        if len(set(str(v) for v in values) & entity_keywords) >= 2:
            return 'ENTITY_TYPES'

        # Output formats (stable)
        if set(str(v) for v in values) & {'text', 'json', 'grep'}:
            return 'STABLE'

        # HTML tags (stable)
        html_tags = {'nav', 'header', 'main', 'article', 'section', 'aside', 'footer'}
        if len(set(str(v) for v in values) & html_tags) >= 2:
            return 'STABLE'

        return 'OTHER'
