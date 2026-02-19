"""V019: Adapter initialization pattern compliance.

Validates that adapters follow the generic_adapter_handler initialization contract.
The generic handler tries 5 initialization patterns in sequence - adapters must
raise TypeError (not ValueError or other exceptions) when a pattern doesn't match.

Example violations:
    - DiffAdapter() raises ValueError instead of TypeError
    - Adapter crashes with AttributeError during initialization
    - Adapter requires specific args but doesn't communicate via TypeError

The contract:
    1. No-arg init: adapter_class()
    2. Query parsing: adapter_class(path, query)
    3. Keyword args: adapter_class(base_path=path, query=query)
    4. Resource arg: adapter_class(resource)
    5. Full URI: adapter_class(f"{scheme}://{resource}")

Adapters should raise TypeError when their signature doesn't match a pattern.
This allows generic_adapter_handler to try the next pattern gracefully.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root
from .adapter_utils import find_adapter_file, find_init_definition_line


class V019(BaseRule):
    """Validate that adapters follow initialization patterns correctly."""

    code = "V019"
    message = "Adapter initialization pattern violation"
    category = RulePrefix.V
    severity = Severity.HIGH
    file_patterns = ['*']  # Runs on reveal:// URIs

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check that all adapters handle initialization patterns correctly."""
        # Only run this check for reveal:// URIs
        if not file_path.startswith('reveal://'):
            return []

        # Find reveal root
        reveal_root = find_reveal_root()
        if not reveal_root:
            return []

        # Get all registered adapters
        try:
            from ...adapters.base import list_supported_schemes, get_adapter_class
        except Exception:
            return []

        detections: List[Detection] = []
        schemes = list(sorted(list_supported_schemes()))

        for scheme in schemes:
            adapter_class = get_adapter_class(scheme)
            if not adapter_class:
                continue

            # Find adapter file for error reporting
            adapter_file = find_adapter_file(reveal_root, scheme)
            if not adapter_file:
                continue

            # Test no-arg initialization
            detection = self._test_no_arg_init(scheme, adapter_class, adapter_file)
            if detection:
                detections.append(detection)

            # Test resource string initialization
            detection = self._test_resource_init(scheme, adapter_class, adapter_file)
            if detection:
                detections.append(detection)

        return detections

    def _test_no_arg_init(self, scheme: str, adapter_class: type,
                         adapter_file: Path) -> Optional[Detection]:
        """Test that no-arg init raises TypeError (not ValueError or crashes).

        Args:
            scheme: URI scheme
            adapter_class: Adapter class to test
            adapter_file: Path to adapter file for error reporting

        Returns:
            Detection if violation found, None otherwise
        """
        try:
            # Try no-arg initialization
            adapter_class()
            # Success is fine - adapter supports no-arg init
            return None
        except TypeError:
            # Expected - adapter doesn't support no-arg init
            return None
        except ValueError as e:
            # VIOLATION: Should raise TypeError, not ValueError
            return self.create_detection(
                file_path=str(adapter_file),
                line=find_init_definition_line(adapter_file),
                message=f"Adapter '{scheme}' raises ValueError instead of TypeError on no-arg init",
                suggestion=(
                    f"Change __init__ to raise TypeError for invalid initialization:\n"
                    f"  - If adapter requires arguments, let Python raise TypeError naturally\n"
                    f"  - Don't validate arguments and raise ValueError in __init__\n"
                    f"  - ValueError says 'wrong value', TypeError says 'wrong call pattern'\n"
                    f"  - Generic handler catches TypeError to try next pattern\n"
                    f"\n"
                    f"Current error: {str(e)}"
                ),
                context="No-arg initialization raises ValueError instead of TypeError"
            )
        except Exception as e:
            # VIOLATION: Crashed with unexpected exception
            exception_type = type(e).__name__
            return self.create_detection(
                file_path=str(adapter_file),
                line=find_init_definition_line(adapter_file),
                message=f"Adapter '{scheme}' crashes with {exception_type} on no-arg init",
                suggestion=(
                    f"Fix __init__ to handle initialization gracefully:\n"
                    f"  - Don't crash with {exception_type}\n"
                    f"  - Raise TypeError if signature doesn't match\n"
                    f"  - Don't access attributes that might not exist\n"
                    f"\n"
                    f"Error: {str(e)}"
                ),
                context=f"No-arg initialization crashes with {exception_type}"
            )

    def _test_resource_init(self, scheme: str, adapter_class: type,
                           adapter_file: Path) -> Optional[Detection]:
        """Test that resource string init works or raises TypeError.

        Args:
            scheme: URI scheme
            adapter_class: Adapter class to test
            adapter_file: Path to adapter file for error reporting

        Returns:
            Detection if violation found, None otherwise
        """
        # Use a safe test resource string
        test_resource = "test_resource"

        try:
            adapter_class(test_resource)
            # Success is fine - adapter supports resource arg
            return None
        except TypeError:
            # Expected - adapter doesn't support single resource arg
            return None
        except ImportError:
            # Expected - adapter might require optional dependencies
            return None
        except ValueError as e:
            # Check if this is argument validation or parsing error
            error_msg = str(e).lower()

            # These are acceptable ValueErrors (argument validation)
            if 'requires' in error_msg or 'format' in error_msg or 'invalid' in error_msg:
                # This is fine - adapter is validating the resource format
                return None

            # Unexpected ValueError
            # Note: severity overridden to MEDIUM (less critical than no-arg issues)
            detection = self.create_detection(
                file_path=str(adapter_file),
                line=find_init_definition_line(adapter_file),
                message=f"Adapter '{scheme}' raises unexpected ValueError on resource init",
                suggestion=(
                    f"Review ValueError usage in __init__:\n"
                    f"  - ValueError is OK for validating resource format\n"
                    f"  - But should be caught by generic_adapter_handler\n"
                    f"  - Make error messages user-friendly with examples\n"
                    f"\n"
                    f"Current error: {str(e)}"
                ),
                context="Resource initialization raises ValueError"
            )
            # Override severity for this specific case
            detection.severity = Severity.MEDIUM
            return detection
        except Exception as e:
            # AttributeError suggests adapter is accessing attributes that don't exist
            if isinstance(e, AttributeError):
                return self.create_detection(
                    file_path=str(adapter_file),
                    line=find_init_definition_line(adapter_file),
                    message=f"Adapter '{scheme}' has AttributeError on resource init",
                    suggestion=(
                        f"Fix attribute access in __init__:\n"
                        f"  - Don't access attributes before setting them\n"
                        f"  - Check if dependencies are available before using\n"
                        f"  - Use hasattr() or getattr() for optional attributes\n"
                        f"\n"
                        f"Error: {str(e)}"
                    ),
                    context="Resource initialization crashes with AttributeError"
                )

            # Other exceptions might be OK (e.g., file not found, database connection)
            return None

    def get_description(self) -> str:
        """Get detailed rule description."""
        return (
            "Ensures adapters follow the generic_adapter_handler initialization contract. "
            "Adapters must raise TypeError (not ValueError) when their signature doesn't "
            "match an initialization pattern. This allows the generic handler to gracefully "
            "try alternative patterns. Adapters should not crash with AttributeError or "
            "other unexpected exceptions during initialization."
        )
