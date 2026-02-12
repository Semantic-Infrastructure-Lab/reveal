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
        schemes = list(sorted(list_supported_schemes()))

        for scheme in schemes:
            adapter_class = get_adapter_class(scheme)
            renderer_class = get_renderer_class(scheme)

            if not adapter_class or not renderer_class:
                continue

            # Find adapter file for error reporting
            adapter_file = self._find_adapter_file(reveal_root, scheme)
            if not adapter_file:
                continue

            # Check if renderer supports elements
            supports_elements = hasattr(renderer_class, 'render_element')

            # Check if adapter implements required methods
            has_get_element = hasattr(adapter_class, 'get_element')
            has_get_structure = hasattr(adapter_class, 'get_structure')

            # Validation 1: If renderer has render_element, adapter must have get_element
            if supports_elements and not has_get_element:
                detections.append(Detection(
                    file_path=str(adapter_file),
                    line=self._find_class_line(adapter_file, adapter_class.__name__),
                    rule_code=self.code,
                    message=f"Adapter '{scheme}' missing get_element() but renderer has render_element()",
                    suggestion=(
                        f"Add get_element() method to adapter:\n"
                        f"  def get_element(self, element_name: str) -> Optional[Dict[str, Any]]:\n"
                        f"      \"\"\"Get specific element by name.\"\"\"\n"
                        f"      # Return element data or None if not found\n"
                        f"      return None\n"
                        f"\n"
                        f"Renderer has render_element, so generic handler expects get_element."
                    ),
                    context="Renderer supports elements but adapter doesn't implement get_element",
                    severity=Severity.HIGH,
                    category=self.category
                ))

            # Validation 2: All adapters should have get_structure
            if not has_get_structure:
                detections.append(Detection(
                    file_path=str(adapter_file),
                    line=self._find_class_line(adapter_file, adapter_class.__name__),
                    rule_code=self.code,
                    message=f"Adapter '{scheme}' missing get_structure() method",
                    suggestion=(
                        f"Add get_structure() method to adapter:\n"
                        f"  def get_structure(self) -> Dict[str, Any]:\n"
                        f"      \"\"\"Get complete structure.\"\"\"\n"
                        f"      return {{}}\n"
                        f"\n"
                        f"All adapters should implement get_structure()."
                    ),
                    context="Adapter missing required get_structure() method",
                    severity=Severity.HIGH,
                    category=self.category
                ))

            # Validation 3: Test get_element error handling (if it exists)
            if supports_elements and has_get_element:
                detection = self._test_get_element_error_handling(
                    scheme, adapter_class, adapter_file
                )
                if detection:
                    detections.append(detection)

        return detections

    def _test_get_element_error_handling(self, scheme: str, adapter_class: type,
                                        adapter_file: Path) -> Optional[Detection]:
        """Test that get_element returns None for missing elements (doesn't crash).

        Args:
            scheme: URI scheme
            adapter_class: Adapter class to test
            adapter_file: Path to adapter file

        Returns:
            Detection if violation found, None otherwise
        """
        # Try to instantiate adapter with minimal args
        try:
            # Try no-arg first
            try:
                adapter = adapter_class()
            except TypeError:
                # Try with safe resource arg
                try:
                    adapter = adapter_class('.')
                except (TypeError, ValueError, ImportError):
                    # Can't instantiate - skip this test
                    return None
            except (ValueError, ImportError):
                # Can't instantiate - skip this test
                return None

            # Test get_element with non-existent element
            test_element = "_nonexistent_test_element_xyz_"
            try:
                result = adapter.get_element(test_element)

                # get_element should return None for missing elements
                if result is not None:
                    # This might be OK if adapter has this element
                    # Can't reliably test without knowing adapter's elements
                    return None

                return None  # Correct behavior

            except Exception as e:
                # VIOLATION: get_element should return None, not crash
                exception_type = type(e).__name__

                return Detection(
                    file_path=str(adapter_file),
                    line=self._find_method_line(adapter_file, 'get_element'),
                    rule_code=self.code,
                    message=f"Adapter '{scheme}' get_element() crashes with {exception_type} for missing element",
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

        except Exception:
            # Can't test this adapter - skip
            return None

    def _find_class_line(self, adapter_file: Path, class_name: str) -> int:
        """Find line number of class definition.

        Args:
            adapter_file: Path to adapter file
            class_name: Name of class to find

        Returns:
            Line number of class, or 1 if not found
        """
        try:
            with open(adapter_file, 'r') as f:
                for i, line in enumerate(f, start=1):
                    if f'class {class_name}' in line:
                        return i
        except Exception:
            pass
        return 1

    def _find_method_line(self, adapter_file: Path, method_name: str) -> int:
        """Find line number of method definition.

        Args:
            adapter_file: Path to adapter file
            method_name: Name of method to find

        Returns:
            Line number of method, or 1 if not found
        """
        try:
            with open(adapter_file, 'r') as f:
                for i, line in enumerate(f, start=1):
                    if f'def {method_name}' in line:
                        return i
        except Exception:
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
