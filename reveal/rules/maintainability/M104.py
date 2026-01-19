"""
M104: Hardcoded configuration detection.

Detects large lists/dicts hardcoded in Python that should be externalized
to configuration files (YAML, JSON, TOML). Improves maintainability and
allows non-developers to modify configuration.

Examples:
    reveal app.py --check --select M104
    reveal src/ --check --select M104  # Check entire directory
"""

import ast
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity


class M104(BaseRule):
    """Detect hardcoded configuration that should be externalized.

    Large lists and dictionaries of configuration data should be stored in
    external files (YAML, JSON, TOML) rather than hardcoded in Python.
    This improves maintainability and allows configuration changes without
    code modifications.

    Severity: LOW (quality improvement, not a bug)
    Category: Maintainability

    Detects:
    - Lists with >10 string literals (likely config)
    - Dictionaries with >5 key-value pairs (likely config)
    - Hardcoded mappings that could be data files

    Passes:
    - Small lists/dicts (<10 items)
    - Configuration already in external files
    - Computed/dynamic data structures

    Thresholds (configurable via .reveal.toml):
    - list_size_threshold: 10 (default)
    - dict_size_threshold: 5 (default)
    """

    code = "M104"
    message = "Large hardcoded configuration should be externalized to config file"
    category = RulePrefix.M
    severity = Severity.LOW
    file_patterns = ['.py']
    version = "1.0.0"

    # Default thresholds
    DEFAULT_LIST_THRESHOLD = 10
    DEFAULT_DICT_THRESHOLD = 5

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check for hardcoded configuration.

        Args:
            file_path: Path to file being checked
            structure: Parsed structure
            content: Raw file content

        Returns:
            List of detections for hardcoded config
        """
        # Only check Python files
        if not file_path.endswith('.py'):
            return []

        # Skip test files (they often have large test data)
        # Check for test directories (/tests/, /test/) or test file patterns
        path_lower = file_path.lower()
        filename = Path(file_path).name.lower()
        is_test_file = (
            '/tests/' in path_lower or
            '/test/' in path_lower or
            path_lower.endswith('_test.py') or
            path_lower.endswith('/test.py') or
            filename.startswith('test_')
        )
        if is_test_file:
            return []

        # Get thresholds from config
        list_threshold = self.get_threshold('list_size_threshold', self.DEFAULT_LIST_THRESHOLD)
        dict_threshold = self.get_threshold('dict_size_threshold', self.DEFAULT_DICT_THRESHOLD)

        detections = []

        try:
            tree = ast.parse(content)
            detector = _HardcodedConfigDetector(
                file_path,
                list_threshold,
                dict_threshold
            )
            detector.visit(tree)
            detections.extend(detector.detections)
        except SyntaxError:
            # Can't parse - skip
            pass

        # Convert to Detection objects
        result = []
        for detection_info in detections:
            result.append(self.create_detection(
                file_path,
                detection_info['line'],
                message=detection_info['message'],
                suggestion=detection_info['suggestion']
            ))

        return result


class _HardcodedConfigDetector(ast.NodeVisitor):
    """AST visitor to detect hardcoded configuration.

    Walks the AST and identifies large literals that likely represent
    configuration data.
    """

    def __init__(self,
                 file_path: str,
                 list_threshold: int,
                 dict_threshold: int):
        """Initialize detector.

        Args:
            file_path: Path to file being analyzed
            list_threshold: Minimum list size to flag
            dict_threshold: Minimum dict size to flag
        """
        self.file_path = file_path
        self.list_threshold = list_threshold
        self.dict_threshold = dict_threshold
        self.detections = []

    def visit_List(self, node: ast.List):
        """Visit list literal."""
        self.generic_visit(node)

        # Count items
        size = len(node.elts)

        if size >= self.list_threshold:
            # Check if mostly strings (likely config)
            string_count = sum(1 for elt in node.elts
                             if isinstance(elt, ast.Constant) and isinstance(elt.value, str))

            if string_count > size * 0.7:  # >70% strings
                self.detections.append({
                    'line': node.lineno,
                    'message': f"Large list with {size} items should be externalized to config file",
                    'suggestion': (
                        f"Move this {size}-item list to YAML/JSON config file:\n"
                        "  1. Create config/data.yaml with list data\n"
                        "  2. Load with: yaml.safe_load(open('config/data.yaml'))\n"
                        "  3. Benefits: easier to maintain, non-developers can update"
                    )
                })

    def visit_Dict(self, node: ast.Dict):
        """Visit dict literal."""
        self.generic_visit(node)

        # Count key-value pairs
        size = len(node.keys)

        if size >= self.dict_threshold:
            # Large dict - likely configuration
            self.detections.append({
                'line': node.lineno,
                'message': f"Large dictionary with {size} key-value pairs should be externalized",
                'suggestion': (
                    f"Move this {size}-item dict to config file:\n"
                    "  1. Create config/mappings.yaml with dict data\n"
                    "  2. Load with: yaml.safe_load(open('config/mappings.yaml'))\n"
                    "  3. Benefits: easier to maintain, version separately from code"
                )
            })

    def visit_Assign(self, node: ast.Assign):
        """Visit assignment statement.

        Check for large constant assignments that look like config.
        """
        self.generic_visit(node)

        # Check if assigning to a constant-style name (UPPERCASE)
        for target in node.targets:
            if isinstance(target, ast.Name):
                name = target.id
                # Check if name suggests configuration
                if name.isupper() and any(keyword in name for keyword in
                                        ['PATTERNS', 'TYPES', 'MAPPINGS', 'CONFIG', 'DEFAULTS']):
                    # This looks like configuration - check the value
                    if isinstance(node.value, (ast.List, ast.Dict)):
                        # Already handled by visit_List/visit_Dict
                        pass
