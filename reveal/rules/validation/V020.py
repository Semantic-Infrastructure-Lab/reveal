"""V020: Adapter element/structure contract compliance.

Validates that adapters correctly implement get_element() and get_structure()
based on their renderer's capabilities. The generic_adapter_handler has complex
logic for deciding when to call get_element vs get_structure.

Example violations:
    - Renderer has render_element but adapter doesn't implement get_element
    - get_element crashes instead of returning None for missing elements
    - Adapter confuses resource string with element name

The contract:
    - If renderer has render_element: adapter is "element-based"
      - Must implement get_element(name) → result or None
      - Handler may call get_element with resource string if no element specified
      - This is by design - allows "reveal python://PATH" to show PATH details

    - If renderer lacks render_element: adapter is "structure-only"
      - Only get_structure() is called
      - get_element() not needed

Current handler logic (routing.py line 193):
    supports_elements = hasattr(renderer_class, 'render_element')
    if supports_elements and (element or resource):
        element_name = element if element else resource
        result = adapter.get_element(element_name)

This means resource strings become element names if no explicit element provided.
Adapters must handle this gracefully.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root


class V020(BaseRule):
    """Validate that adapters implement element/structure contract correctly."""

    code = "V020"
    message = "Adapter element/structure contract violation"
    category = RulePrefix.V
    severity = Severity.MEDIUM
    file_patterns = ['*']  # Runs on reveal:// URIs

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check that adapters implement element/structure methods correctly."""
        # Only run this check for reveal:// URIs
        if not file_path.startswith('reveal://'):
            return []

        # Find reveal root
        reveal_root = find_reveal_root()
        if not reveal_root:
            return []

        # Get all registered adapters and renderers
        try:
            from ...adapters.base import (
                list_supported_schemes,
                get_adapter_class,
                get_renderer_class
            )
        except Exception:
            return []

        detections: List[Detection] = []
        for scheme in sorted(list_supported_schemes()):
            adapter_class = get_adapter_class(scheme)
            renderer_class = get_renderer_class(scheme)
            if not adapter_class or not renderer_class:
                continue
            adapter_file = self._find_adapter_file(reveal_root, scheme)
            if not adapter_file:
                continue
            detections.extend(
                self._check_scheme(scheme, adapter_class, renderer_class, adapter_file)
            )
        return detections

    def _check_scheme(
        self,
        scheme: str,
        adapter_class: type,
        renderer_class: type,
        adapter_file: Path,
    ) -> List[Detection]:
        """Check a single adapter/renderer pair for contract compliance."""
        detections: List[Detection] = []
        supports_elements = hasattr(renderer_class, 'render_element')
        has_get_element = hasattr(adapter_class, 'get_element')
        has_get_structure = hasattr(adapter_class, 'get_structure')
        class_line = self._find_line_matching(adapter_file, f'class {adapter_class.__name__}')

        # Validation 1: If renderer has render_element, adapter must have get_element
        if supports_elements and not has_get_element:
            detections.append(Detection(
                file_path=str(adapter_file),
                line=class_line,
                rule_code=self.code,
                message=f"Adapter '{scheme}' missing get_element() but renderer has render_element()",
                suggestion=(
                    "Add get_element() method to adapter:\n"
                    "  def get_element(self, element_name: str) -> Optional[Dict[str, Any]]:\n"
                    "      \"\"\"Get specific element by name.\"\"\"\n"
                    "      # Return element data or None if not found\n"
                    "      return None\n"
                    "\n"
                    "Renderer has render_element, so generic handler expects get_element."
                ),
                context="Renderer supports elements but adapter doesn't implement get_element",
                severity=Severity.HIGH,
                category=self.category
            ))

        # Validation 2: All adapters should have get_structure
        if not has_get_structure:
            detections.append(Detection(
                file_path=str(adapter_file),
                line=class_line,
                rule_code=self.code,
                message=f"Adapter '{scheme}' missing get_structure() method",
                suggestion=(
                    "Add get_structure() method to adapter:\n"
                    "  def get_structure(self) -> Dict[str, Any]:\n"
                    "      \"\"\"Get complete structure.\"\"\"\n"
                    "      return {}\n"
                    "\n"
                    "All adapters should implement get_structure()."
                ),
                context="Adapter missing required get_structure() method",
                severity=Severity.HIGH,
                category=self.category
            ))

        # Validation 3: Test get_element error handling (if it exists)
        if supports_elements and has_get_element:
            detection = self._test_get_element_error_handling(scheme, adapter_class, adapter_file)
            if detection:
                detections.append(detection)

        return detections

    def _test_get_element_error_handling(self, scheme: str, adapter_class: type,
                                        adapter_file: Path) -> Optional[Detection]:
        """Test that get_element returns None for missing elements (doesn't crash)."""
        adapter = self._try_instantiate(adapter_class)
        if adapter is None:
            return None

        test_element = "_nonexistent_test_element_xyz_"
        try:
            result = adapter.get_element(test_element)
            # Correct behavior: return None for missing element.
            # If result is not None the adapter found something — can't judge without
            # knowing its elements, so skip.
            _ = result
            return None
        except Exception as e:
            exception_type = type(e).__name__
            return Detection(
                file_path=str(adapter_file),
                line=self._find_line_matching(adapter_file, 'def get_element'),
                rule_code=self.code,
                message=(
                    f"Adapter '{scheme}' get_element() crashes with "
                    f"{exception_type} for missing element"
                ),
                suggestion=(
                    f"Fix get_element() to return None for missing elements:\n"
                    f"  def get_element(self, element_name: str) -> Optional[Dict[str, Any]]:\n"
                    f"      try:\n"
                    f"          # ... find element ...\n"
                    f"          return element_data\n"
                    f"      except (KeyError, ValueError):\n"
                    f"          return None  # Element not found\n"
                    f"\n"
                    f"Don't let exceptions propagate - return None instead.\n"
                    f"Error: {str(e)}"
                ),
                context=f"get_element crashes with {exception_type} instead of returning None",
                severity=Severity.MEDIUM,
                category=self.category
            )

    @staticmethod
    def _try_instantiate(adapter_class: type) -> Optional[object]:
        """Attempt to instantiate adapter with minimal arguments; return None if impossible."""
        try:
            return adapter_class()
        except TypeError:
            pass
        except (ValueError, ImportError, Exception):  # noqa: BLE001
            return None
        try:
            return adapter_class('.')
        except Exception:  # noqa: BLE001
            return None

    def _find_line_matching(self, file_path: Path, pattern: str) -> int:
        """Find the first line number (1-indexed) containing *pattern*, or 1."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f, start=1):
                    if pattern in line:
                        return i
        except OSError:
            pass
        return 1

    def _find_adapter_file(self, reveal_root: Path, scheme: str) -> Optional[Path]:
        """Find the adapter file for a given scheme.

        Args:
            reveal_root: Path to reveal package root
            scheme: URI scheme (e.g., 'env', 'ast', 'git')

        Returns:
            Path to adapter file, or None if not found
        """
        adapters_dir = reveal_root / 'adapters'
        if not adapters_dir.exists():
            return None

        # Try common patterns
        for pattern in [
            f"{scheme}.py",
            f"{scheme}_adapter.py",
            f"{scheme}/adapter.py",
            f"{scheme}/__init__.py"
        ]:
            adapter_file = adapters_dir / pattern
            if adapter_file.exists():
                return adapter_file

        return None

    def get_description(self) -> str:
        """Get detailed rule description."""
        return (
            "Ensures adapters implement get_element() and get_structure() correctly "
            "based on their renderer's capabilities. If renderer has render_element(), "
            "adapter must implement get_element() that returns None for missing elements "
            "(not crash). All adapters must implement get_structure(). This contract "
            "enables generic_adapter_handler to work reliably with all adapters."
        )
