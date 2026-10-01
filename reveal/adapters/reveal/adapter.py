"""Reveal meta-adapter (reveal://) - Self-inspection and validation."""

from pathlib import Path
from typing import Dict, List, Any, Optional, cast
from reveal.reveal_types import CONTRACT_VERSION, RevealResult

from ..base import ResourceAdapter, Stability, register_adapter, register_renderer
from ...rules.validation.utils import find_reveal_root
from ...utils.path_utils import to_posix
from ...utils.results import ResultBuilder

from .renderer import RevealRenderer
from .help import get_schema, get_help
from . import structure, operations, formatting


# The views reveal:// answers without an element (structure.get_structure).
SECTIONS = ('config', 'analyzers', 'rules', 'adapters')


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
    HELP_CLUSTER = 'Self-Describing'

    internal = True
    STABILITY = Stability.STABLE
    LEGACY_INIT = False
    HONORS_RESULT_CONTROL = False  # ignores its query entirely (BACK-1385)
    BUDGET_LIST_FIELD = ('analyzers', 'adapters', 'rules')  # --head/--tail slice each (BACK-1497)
    CANONICAL_EMPTY_RESOURCE = ''

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

    def __init__(self, resource: str = '', query: Optional[str] = None, **kwargs: Any):
        """Initialize reveal adapter.

        Args:
            resource: Optional component to inspect (analyzers, rules, etc.)
            query: Unused, accepted for canonical signature conformance.
        """
        self.component = resource or None
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

    def get_structure(self, **kwargs: Any) -> RevealResult:
        """Get reveal's internal structure.

        Returns:
            Dict containing analyzers, adapters, rules, etc.
            Filtered by self.component if specified.
        """
        if self.component and self.component.lower() not in SECTIONS:
            return self._unknown_section()
        result = structure.get_structure(self.reveal_root, self.component, **kwargs)
        return ResultBuilder.create(
            result_type='reveal_structure',
            source=f'reveal://{self.component or "."}',
            source_type='runtime',
            contract_version=CONTRACT_VERSION,
            data=result,
        )

    def _unknown_section(self) -> RevealResult:
        """An unknown section fails, naming the real ones (BACK-1521).

        It fell through to the full view with exit 0, so a typo (``reveal://analyzer``)
        answered a different question as if it were the one asked.
        """
        message = (f"Unknown reveal:// section '{self.component}'. "
                   f"Sections: {', '.join(SECTIONS)}.")
        source_file = self.reveal_root / str(self.component)
        if source_file.is_file():
            message += f" To read that source file: reveal {to_posix(source_file)}"
        return ResultBuilder.create_error(
            result_type='reveal_structure', source=f'reveal://{self.component}',
            error=message, contract_version=CONTRACT_VERSION, source_type='runtime')

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
        """One element of a reveal source file: ``reveal reveal://<file> <element>``.

        The file is named relative to reveal's own package, so a pip install's
        source is readable without knowing its site-packages path. Extraction is
        the file view's own (display.element), returned as a result the router
        emits; it used to print through handle_file with no renderer to reach it,
        so every form answered the structure view instead (BACK-1565).
        """
        from ...display.element import _extract_by_syntax, _parse_element_syntax
        from ...registry import get_analyzer

        source_file = self._source_file()
        analyzer_class = get_analyzer(str(source_file), allow_fallback=True) if source_file else None
        if source_file is None or analyzer_class is None:
            return None
        found = _extract_by_syntax(analyzer_class(str(source_file)), element_name,
                                   _parse_element_syntax(element_name))
        if not found:
            return None
        return cast(Dict[str, Any], ResultBuilder.create(
            result_type='code_element',  # the schema's declared output type
            source=f'reveal://{self.component}',
            source_type='runtime',
            contract_version=CONTRACT_VERSION,
            # The schema's field names: 'source' is the envelope's target (reveal://<file>).
            data={'element': element_name, 'file': to_posix(str(self.component)),
                  'line_start': found['line_start'], 'line_end': found['line_end'],
                  'content': found['source']},
        ))

    def _source_file(self) -> Optional[Path]:
        """The reveal source file the resource names, or None."""
        if not self.component:
            return None
        candidate = self.reveal_root / str(self.component)
        if not candidate.is_file() and str(self.component) == 'adapters/reveal.py':
            candidate = self.reveal_root / 'adapters' / 'reveal' / 'adapter.py'  # pre-split path
        return candidate if candidate.is_file() else None

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
