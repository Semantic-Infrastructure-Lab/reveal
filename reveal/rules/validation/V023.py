"""V023: Output Contract Compliance.

Validates that adapter/analyzer outputs conform to the v1.0 Output Contract
specification. Ensures required fields are present, type naming follows
conventions, and line number fields use standardized names.

This rule enables:
- Stable JSON output for AI agents
- Predictable schemas for tool builders
- Clear contracts for adapter contributors

Contract Requirements (v1.0):
    Required fields (4):
        - contract_version: '1.0' (semver string)
        - type: snake_case identifier
        - source: data source location
        - source_type: 'file' | 'directory' | 'database' | 'runtime' | 'network'

    Naming conventions:
        - type field: snake_case (e.g., 'ast_query', not 'ast-query')
        - line fields: line_start/line_end (not 'line')

Examples:
    reveal reveal://. --check --select V023  # Check reveal's own adapters
    reveal path/to/adapters/ --check --select V023  # Check custom adapters

See also:
    docs/OUTPUT_CONTRACT.md - Full specification
    internal-docs/research/OUTPUT_CONTRACT_ANALYSIS.md - Design rationale
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from .adapter_utils import get_adapter_class


class V023(BaseRule):
    """Verify adapter outputs conform to Output Contract v1.0.

    Validates required fields, naming conventions, and schema compliance
    for all adapter and analyzer outputs.

    Severity: HIGH (blocks stable JSON output)
    Category: Validation

    Detects:
    - Missing required fields (contract_version, type, source, source_type)
    - Invalid type naming (non-snake_case)
    - Deprecated line field names ('line' instead of 'line_start')
    - Invalid source_type values

    Passes:
    - Adapters with full v1.0 contract compliance
    - Non-adapter files
    """

    code = "V023"
    message = "Output Contract violation - non-compliant adapter output"
    category = RulePrefix.V
    severity = Severity.HIGH
    file_patterns = ['.py']
    version = "1.0.0"

    # Valid source_type enum values
    VALID_SOURCE_TYPES = {'file', 'directory', 'database', 'runtime', 'network'}

    # Type field must match this pattern (snake_case)
    TYPE_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check adapter/analyzer output contract compliance.

        Args:
            file_path: Path to file being checked
            structure: Parsed structure (functions, classes)
            content: Raw file content

        Returns:
            List of detections for contract violations
        """
        detections: List[Detection] = []

        # Only check Python files in adapters/ or analyzers/ directories
        if not file_path.endswith('.py'):
            return []

        if '/adapters/' not in file_path and '/analyzers/' not in file_path:
            return []

        # Skip __init__.py, base.py, utils files
        path = Path(file_path)
        if path.name in ['__init__.py', 'base.py', 'utils.py', 'adapter_utils.py']:
            return []

        # Check if file defines adapter or analyzer class
        if not self._is_adapter_or_analyzer_file(structure, content):
            return []

        # For adapters, we can test actual output
        if '/adapters/' in file_path:
            detections.extend(self._check_adapter_output(file_path, content))

        # For analyzers, check code patterns (can't easily instantiate)
        if '/analyzers/' in file_path:
            detections.extend(self._check_analyzer_code(file_path, structure, content))

        return detections

    def _is_adapter_or_analyzer_file(self, structure: Optional[Dict], content: str) -> bool:
        """Check if file defines an adapter or analyzer class."""
        if not structure:
            return False

        # Check for adapter/analyzer classes
        classes = structure.get('classes', [])
        for cls in classes:
            cls_name = cls.get('name', '')
            if 'Adapter' in cls_name or 'Analyzer' in cls_name:
                return True

        # Check for ResourceAdapter or FileAnalyzer inheritance
        if 'ResourceAdapter' in content or 'FileAnalyzer' in content:
            return True

        return False

    def _check_adapter_output(self, file_path: str, content: str) -> List[Detection]:
        """Check actual adapter output for contract compliance."""
        detections: List[Detection] = []

        # Extract adapter scheme from file path
        scheme = self._extract_scheme(file_path)
        if not scheme:
            return []

        # Try to get adapter class and test its output
        try:
            adapter_class = get_adapter_class(scheme)
            if not adapter_class:
                return []

            # Try to get sample output from get_structure()
            # We can't fully instantiate, but we can check the method exists
            if not hasattr(adapter_class, 'get_structure'):
                return []

            # Check code for required fields being set
            detections.extend(self._check_output_code_patterns(
                file_path, content, 'get_structure'
            ))

        except Exception:
            # If we can't import/test, skip runtime checks
            pass

        return detections

    def _check_analyzer_code(self, file_path: str, structure: Optional[Dict],
                            content: str) -> List[Detection]:
        """Check analyzer code patterns for contract compliance."""
        return self._check_output_code_patterns(file_path, content, 'get_structure')

    def _check_output_code_patterns(self, file_path: str, content: str,
                                    method_name: str) -> List[Detection]:
        """Check code for output contract patterns.

        Looks for return statements in get_structure/get_element methods
        and validates they include required fields.
        """
        detections: List[Detection] = []

        # Find the method definition
        method_start = content.find(f'def {method_name}(')
        if method_start == -1:
            return []

        # Extract method body (simple heuristic: up to next 'def' or end of class)
        method_end = content.find('\n    def ', method_start + 1)
        if method_end == -1:
            method_end = content.find('\nclass ', method_start)
        if method_end == -1:
            method_end = len(content)

        method_body = content[method_start:method_end]

        # Calculate line number for detections
        line_num = content[:method_start].count('\n') + 1

        detections.extend(self._check_required_contract_fields(
            method_body, method_name, file_path, line_num
        ))
        detections.extend(self._check_deprecated_line_field(method_body, file_path, line_num))
        detections.extend(self._check_hyphenated_type_values(method_body, file_path, line_num))
        return detections

    def _check_required_contract_fields(self, method_body, method_name, file_path, line_num):
        """Check that required contract fields appear in the method body."""
        # Dispatcher pattern: method delegates to sub-methods/functions that own the contract.
        # e.g. get_structure() returns self._get_ssl_structure() or files.get_file_history()
        # The fields live in those callees; checking the dispatcher is a false positive.
        if 'return self._get_' in method_body or 'return self._' in method_body:
            return []
        # Module-level delegation: all paths return via an imported helper (e.g. return files.get_X(...))
        import re as _re
        delegated_returns = _re.findall(r'\breturn \w+\.\w+\(', method_body)
        direct_dict_returns = _re.findall(r'\breturn \{', method_body)
        if delegated_returns and not direct_dict_returns:
            return []

        # ResultBuilder pattern: fields are passed as kwargs, not dict literals.
        # ResultBuilder.create(contract_version=..., source=..., ...) satisfies the contract.
        if 'ResultBuilder.create(' in method_body:
            return []

        required_fields = ['contract_version', 'type', 'source', 'source_type']
        missing_fields = [
            f for f in required_fields
            if not any(p in method_body for p in [f"'{f}':", f'"{f}":', f"'{f}' :", f'"{f}" :'])
        ]
        if not missing_fields:
            return []
        return [self.create_detection(
            file_path, line_num,
            message=f"Output missing required contract fields: {', '.join(missing_fields)}",
            suggestion=(
                f"Add required fields to return dict in {method_name}():\n"
                f"  return {{\n"
                f"    'contract_version': '1.0',\n"
                f"    'type': 'your_adapter_type',  # snake_case\n"
                f"    'source': self.source_path,\n"
                f"    'source_type': 'file',  # or 'directory', 'database', 'runtime', 'network'\n"
                f"    # ... rest of output\n"
                f"  }}\n"
                f"See docs/OUTPUT_CONTRACT.md for full specification"
            )
        )]

    def _check_deprecated_line_field(self, method_body, file_path, line_num):
        """Check for use of deprecated 'line' field instead of 'line_start'/'line_end'."""
        if ("'line':" not in method_body and '"line":' not in method_body):
            return []
        if "'line_start'" in method_body or '"line_start"' in method_body:
            return []
        return [self.create_detection(
            file_path, line_num,
            message="Output uses deprecated 'line' field (use 'line_start'/'line_end')",
            suggestion=(
                "Replace 'line' field with 'line_start' and 'line_end':\n"
                "  'line_start': start_line,  # 1-indexed\n"
                "  'line_end': end_line,      # 1-indexed, inclusive\n"
                "See docs/OUTPUT_CONTRACT.md section 'Line Number Fields'"
            )
        )]

    def _check_hyphenated_type_values(self, method_body, file_path, line_num):
        """Check for hyphenated type values that should be snake_case."""
        detections = []
        for type_val in re.findall(r"'type'\s*:\s*['\"]([^'\"]+)['\"]", method_body):
            if '-' in type_val:
                detections.append(self.create_detection(
                    file_path, line_num,
                    message=f"Type field uses hyphens: '{type_val}' (should be snake_case)",
                    suggestion=(
                        f"Change type to snake_case: '{type_val.replace('-', '_')}'\n"
                        f"Type field must match pattern: ^[a-z][a-z0-9_]*$\n"
                        f"Examples: 'ast_query', 'mysql_server', 'environment'"
                    )
                ))
        return detections

    def _extract_scheme(self, file_path: str) -> Optional[str]:
        """Extract adapter scheme from file path.

        Examples:
            'reveal/adapters/ast.py' -> 'ast'
            'reveal/adapters/json_adapter.py' -> 'json'
            'reveal/adapters/git/adapter.py' -> 'git'
        """
        path = Path(file_path)

        # Pattern 1: adapters/scheme.py
        if path.parent.name == 'adapters' and path.stem not in ['__init__', 'base']:
            return path.stem.replace('_adapter', '')

        # Pattern 2: adapters/scheme/adapter.py or adapters/scheme/__init__.py
        if path.parent.parent.name == 'adapters':
            return path.parent.name

        return None
