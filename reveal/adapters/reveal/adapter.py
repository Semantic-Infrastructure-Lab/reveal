"""Reveal meta-adapter (reveal://) - Self-inspection and validation."""

from pathlib import Path
from typing import Dict, List, Any, Optional

from ..base import ResourceAdapter, register_adapter, register_renderer
from ...rules.validation.utils import find_reveal_root

from .renderer import RevealRenderer
from .help import get_schema, get_help
from . import structure, operations, formatting


@register_adapter('reveal')
@register_renderer(RevealRenderer)
class RevealAdapter(ResourceAdapter):
    """Adapter for inspecting reveal's own codebase and configuration.

    Examples:
        reveal reveal://                     # Show reveal's structure
        reveal reveal://analyzers            # List all analyzers
        reveal reveal://rules                # List all rules
        reveal reveal:// --check             # Run validation rules
        reveal reveal:// --check --select V  # Only validation rules
        reveal help://reveal                 # Learn about reveal://
    """

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for reveal:// adapter.

        Returns JSON schema for AI agent integration.
        """
        return get_schema()

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for reveal:// adapter."""
        return get_help()

    def __init__(self, component: Optional[str] = None):
        """Initialize reveal adapter.

        Args:
            component: Optional component to inspect (analyzers, rules, etc.)
        """
        self.component = component
        self.reveal_root = self._find_reveal_root()

    def _find_reveal_root(self) -> Path:
        """Find reveal's root directory using shared utility.

        Delegates to reveal.rules.validation.utils.find_reveal_root for consistent
        path resolution across all reveal components.

        Returns:
            Path to reveal's root directory (never None - falls back to package location)
        """
        # Use shared utility (dev_only=False to include installed package fallback)
        root = find_reveal_root(dev_only=False)

        # Fallback for edge case where utility returns None
        # (should never happen with dev_only=False, but ensures backwards compatibility)
        if root is None:
            root = Path(__file__).parent.parent.parent

        return root

    def get_structure(self, **kwargs: Any) -> Dict[str, Any]:
        """Get reveal's internal structure.

        Returns:
            Dict containing analyzers, adapters, rules, etc.
            Filtered by self.component if specified.
        """
        result = structure.get_structure(self.reveal_root, self.component, **kwargs)
        return {
            'contract_version': '1.0',
            'type': 'reveal_structure',
            'source': f'reveal://{self.component or "."}',
            'source_type': 'runtime',
            **result,
        }

    def check(self, select: Optional[List[str]] = None, ignore: Optional[List[str]] = None) -> Dict[str, Any]:
        """Run validation rules on reveal itself.

        Args:
            select: Optional list of rule codes to run
            ignore: Optional list of rule codes to ignore

        Returns:
            Dict with detections and metadata
        """
        return operations.check(select=select, ignore=ignore)

    def get_element(self, element_name: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        """Extract a specific element from a reveal source file.

        Args:
            element_name: Element to extract (e.g., function name) or resource path
            **kwargs: Optional keyword arguments:
                - resource: File path within reveal (e.g., "rules/links/L001.py")
                - args: Command-line arguments

        Returns:
            Dict with success status if successful, None if failed
        """
        return operations.get_element(self.reveal_root, element_name, **kwargs)

    def format_output(self, structure: Dict[str, Any], format_type: str = 'text') -> str:
        """Format reveal structure for display.

        Args:
            structure: Structure dict from get_structure()
            format_type: Output format (text or json)

        Returns:
            Formatted string
        """
        return formatting.format_output(structure, format_type)

    # Backward compatibility methods for tests
    def _get_analyzers(self) -> List[Dict[str, Any]]:
        """Get all registered analyzers (backward compatibility)."""
        return structure.get_analyzers(self.reveal_root)

    def _get_adapters(self) -> List[Dict[str, Any]]:
        """Get all registered adapters (backward compatibility)."""
        return structure.get_adapters()

    def _get_rules(self) -> List[Dict[str, Any]]:
        """Get all available rules (backward compatibility)."""
        return structure.get_rules(self.reveal_root)

    def _get_supported_types(self) -> List[str]:
        """Get list of supported file extensions (backward compatibility)."""
        return structure.get_supported_types(self.reveal_root)

    def _get_config(self) -> Dict[str, Any]:
        """Get current configuration (backward compatibility)."""
        from .config import get_config
        return get_config(self.reveal_root)

    def _format_metadata_section(self, meta: Dict[str, Any]) -> List[str]:
        """Format metadata/overview section (backward compatibility)."""
        return formatting.format_metadata_section(meta)

    def _format_sources_section(self, sources: Dict[str, Any]) -> List[str]:
        """Format configuration sources section (backward compatibility)."""
        return formatting.format_sources_section(sources)

    def _format_active_config_section(self, active: Dict[str, Any]) -> List[str]:
        """Format active configuration section (backward compatibility)."""
        return formatting.format_active_config_section(active)

    def _format_config_output(self, structure: Dict[str, Any]) -> str:
        """Format configuration structure for text display (backward compatibility)."""
        return formatting.format_config_output(structure)
