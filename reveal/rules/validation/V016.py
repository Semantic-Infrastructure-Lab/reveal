"""
V016: Adapter help completeness validation.

Ensures all adapter classes implement the get_help() method for discoverability.
Missing help documentation prevents users from understanding adapter capabilities
through `reveal help://` command.

Examples:
    reveal reveal://. --check --select V016  # Check reveal's own adapters
    reveal path/to/adapters/ --check --select V016  # Check custom adapters
"""

from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root, is_dev_checkout


class V016(BaseRule):
    """Verify all adapters implement get_help() for discoverability.

    Adapters should provide help documentation via the static get_help() method.
    This enables users to discover adapter capabilities through reveal help://.

    Severity: MEDIUM
    Category: Validation

    Detects:
    - Adapter classes without get_help() implementation
    - get_help() that returns None (no documentation)

    Passes:
    - Adapters with complete get_help() implementation
    - Non-adapter files
    """

    code = "V016"
    message = "Adapter missing get_help() documentation for discoverability"
    category = RulePrefix.V
    severity = Severity.MEDIUM
    file_patterns = ['.py']
    version = "1.0.0"

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check if adapters have get_help() documentation.

        Args:
            file_path: Path to file being checked
            structure: Parsed structure (functions, classes)
            content: Raw file content

        Returns:
            List of detections for adapters missing help
        """
        # When called via reveal reveal:// --check, do self-scan of all adapter files
        if file_path.startswith('reveal://'):
            return self._check_reveal_adapters()

        # Only check Python files in adapters/ directory
        if not file_path.endswith('.py'):
            return []

        if '/adapters/' not in file_path:
            return []

        # Skip __init__.py and base.py
        path = Path(file_path)
        if path.name in ['__init__.py', 'base.py']:
            return []

        # Check if file defines adapter class
        if not self._is_adapter_file(structure, content):
            return []

        # Check if get_help() is implemented
        if self._has_get_help_implementation(structure, content):
            return []

        # Adapter missing help documentation
        return [self.create_detection(
            file_path, 1,
            message="Adapter missing get_help() implementation",
            suggestion=(
                "Add @staticmethod get_help() method returning Dict with:\n"
                "  - name: str (adapter scheme)\n"
                "  - description: str (one-line summary)\n"
                "  - examples: List[Dict] (usage examples)\n"
                "  - syntax: str (URI pattern)\n"
                "See reveal/adapters/python/adapter.py for reference"
            )
        )]

    def _is_adapter_file(self, structure: Optional[Dict], content: str) -> bool:
        """Check if file defines an adapter class.

        Args:
            structure: Parsed structure
            content: Raw content

        Returns:
            True if file contains adapter class definition
        """
        if not structure:
            return False

        # Check for classes inheriting from ResourceAdapter
        classes = structure.get('classes', [])
        for cls in classes:
            cls_name = cls.get('name', '')

            # Check if class name suggests it's an adapter
            if 'Adapter' in cls_name:
                return True

            # Check if class inherits from ResourceAdapter (simple heuristic)
            # More robust: could parse inheritance, but this is sufficient
            if 'ResourceAdapter' in content:
                return True

        return False

    def _has_get_help_implementation(self,
                                    structure: Optional[Dict],
                                    content: str) -> bool:
        """Check if file implements get_help() method.

        Args:
            structure: Parsed structure
            content: Raw content

        Returns:
            True if get_help() is defined and not just returning None
        """
        if not structure:
            return False

        # Check functions at module level
        functions = structure.get('functions', [])
        for func in functions:
            if func.get('name') == 'get_help':
                # Found get_help() - check if it's not trivially returning None
                # Simple heuristic: if it has 'return None' only, it's not implemented
                if 'return None' in content and content.count('return') == 1:
                    return False
                return True

        # Also check as class method
        classes = structure.get('classes', [])
        for cls in classes:
            # Check methods of this class
            # Note: structure might not include full method details
            # Fall back to content search
            if 'def get_help(' in content and '@staticmethod' in content:
                return True

        return False

    def _check_reveal_adapters(self) -> List[Detection]:
        """Scan all reveal adapter files when called via reveal:// --check.

        V016 is normally a per-file rule but `reveal reveal:// --check` calls
        check_file() once with path="reveal://" and no content. This method
        handles that case by discovering and checking all adapter Python files
        directly, so V016 fires correctly from self-check.
        """
        reveal_root = find_reveal_root()
        if not reveal_root or not is_dev_checkout(reveal_root):
            return []

        from ...registry import get_analyzer

        adapters_dir = reveal_root / 'adapters'
        if not adapters_dir.exists():
            return []

        detections: List[Detection] = []

        for py_file in sorted(adapters_dir.rglob('*.py')):
            # Skip __init__.py and base.py (same logic as check())
            if py_file.name in ('__init__.py', 'base.py'):
                continue

            file_path_str = str(py_file)

            try:
                content = py_file.read_text(encoding='utf-8', errors='replace')
                analyzer_class = get_analyzer(file_path_str, allow_fallback=False)
                if not analyzer_class:
                    continue
                analyzer = analyzer_class(file_path_str)
                structure = analyzer.get_structure()
            except Exception:
                continue

            if not self._is_adapter_file(structure, content):
                continue
            if self._has_get_help_implementation(structure, content):
                continue

            # Use path relative to project root for readable output
            try:
                display_path = str(py_file.relative_to(reveal_root.parent))
            except ValueError:
                display_path = file_path_str

            detections.append(self.create_detection(
                display_path, 1,
                message="Adapter missing get_help() implementation",
                suggestion=(
                    "Add @staticmethod get_help() method returning Dict with:\n"
                    "  - name: str (adapter scheme)\n"
                    "  - description: str (one-line summary)\n"
                    "  - examples: List[Dict] (usage examples)\n"
                    "  - syntax: str (URI pattern)\n"
                    "See reveal/adapters/python/adapter.py for reference"
                )
            ))

        return detections
