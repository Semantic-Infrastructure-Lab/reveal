"""V018: Adapter renderer registration completeness.

Validates that every registered adapter has a corresponding renderer.
This prevents the git:// situation where an adapter was registered but
had no handler, causing reveal to fail silently.

Example violation:
    - Adapter: git (registered with @register_adapter)
    - No renderer: GitRenderer (missing @register_renderer)
    - Result: URI scheme listed but unusable

This rule ensures the renderer registry stays in sync with the adapter registry.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root


class V018(BaseRule):
    """Validate that all adapters have registered renderers."""

    code = "V018"
    message = "Adapter missing renderer registration"
    category = RulePrefix.V
    severity = Severity.HIGH
    file_patterns = ['*']  # Runs on any target (checks reveal internals)

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check that all adapters have renderers."""
        # Only run this check for reveal:// URIs
        if not file_path.startswith('reveal://'):
            return []

        # Find reveal root
        reveal_root = find_reveal_root()
        if not reveal_root:
            return []

        # Get registered adapters and renderers
        try:
            from ...adapters.base import list_supported_schemes, list_renderer_schemes
            adapters = set(list_supported_schemes())
            renderers = set(list_renderer_schemes())
        except Exception:
            # If we can't import, skip check
            return []

        # Check for adapters without renderers
        detections: List[Detection] = []
        missing_renderers = adapters - renderers

        for scheme in sorted(missing_renderers):
            # Find adapter file
            adapter_file = self._find_adapter_file(reveal_root, scheme)
            if adapter_file:
                detections.append(self.create_detection(
                    file_path=str(adapter_file),
                    line=1,
                    message=f"Adapter '{scheme}' registered but no renderer found",
                    suggestion=(
                        f"Add renderer class and @register_renderer decorator:\n"
                        f"  1. Create {scheme.title()}Renderer class with:\n"
                        f"     - render_structure(result, format)\n"
                        f"     - render_error(error)\n"
                        f"     - render_element(result, format) [if adapter supports elements]\n"
                        f"  2. Add @register_renderer({scheme.title()}Renderer) above @register_adapter('{scheme}')"
                    ),
                    context=f"Adapter registered but unusable without renderer"
                ))

        # Also check for renderers without adapters (less critical)
        orphaned_renderers = renderers - adapters
        for scheme in sorted(orphaned_renderers):
            # This is unusual but not necessarily wrong (renderer might be for future adapter)
            adapter_file = self._find_adapter_file(reveal_root, scheme)
            if adapter_file:
                detections.append(self.create_detection(
                    file_path=str(adapter_file),
                    line=1,
                    message=f"Renderer registered for '{scheme}' but no adapter found",
                    suggestion=f"Either add @register_adapter('{scheme}') or remove renderer registration",
                    context="Renderer exists without corresponding adapter",
                    severity=Severity.LOW
                ))

        return detections

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

        # Try common patterns:
        # 1. adapters/<scheme>.py (e.g., adapters/env.py)
        scheme_file = adapters_dir / f"{scheme}.py"
        if scheme_file.exists():
            return scheme_file

        # 2. adapters/<scheme>_adapter.py (e.g., adapters/json_adapter.py)
        adapter_file = adapters_dir / f"{scheme}_adapter.py"
        if adapter_file.exists():
            return adapter_file

        # 3. adapters/<scheme>/adapter.py (e.g., adapters/git/adapter.py)
        dir_adapter = adapters_dir / scheme / "adapter.py"
        if dir_adapter.exists():
            return dir_adapter

        # 4. adapters/<scheme>/__init__.py (e.g., adapters/mysql/__init__.py)
        dir_init = adapters_dir / scheme / "__init__.py"
        if dir_init.exists():
            return dir_init

        return None

    def get_description(self) -> str:
        """Get detailed rule description."""
        return (
            "Ensures all registered adapters have corresponding renderers. "
            "The renderer-based architecture requires every adapter to have "
            "a renderer class with render_structure() and render_error() methods. "
            "Without a renderer, the adapter is registered but unusable."
        )
