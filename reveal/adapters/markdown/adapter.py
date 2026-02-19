"""Markdown query adapter (markdown://)."""

from pathlib import Path
from typing import Dict, Any, Optional

from ..base import ResourceAdapter, register_adapter, register_renderer
from ...utils.query import parse_query_filters, parse_result_control, ResultControl
from ...utils.validation import require_directory

from .renderer import MarkdownRenderer
from .help import get_schema, get_help
from . import query as query_module
from . import operations


@register_adapter('markdown')
@register_renderer(MarkdownRenderer)
class MarkdownQueryAdapter(ResourceAdapter):
    """Adapter for querying markdown files by frontmatter via markdown:// URIs.

    Enables finding markdown files based on frontmatter field values,
    missing fields, or wildcards. Works on local directory trees.
    """

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for markdown:// adapter.

        Returns JSON schema for AI agent integration.
        """
        return get_schema()

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for markdown:// adapter."""
        return get_help()

    def __init__(self, base_path: str, query: Optional[str] = None):
        """Initialize the markdown query adapter.

        Args:
            base_path: Directory to search for markdown files
            query: Query string (e.g., 'topics=reveal', '!status', 'lines>100')
        """
        # Strip scheme prefix if the full URI was passed (e.g. "markdown://path/to/file")
        clean_path = base_path
        if '://' in base_path:
            clean_path = base_path.split('://', 1)[1]
        resolved = Path(clean_path).resolve()
        if resolved.is_file():
            raise ValueError(
                f"markdown:// queries a directory of markdown files, not a single file.\n"
                f"To read a single markdown file, use: reveal {clean_path}"
            )
        self.base_path = require_directory(resolved)
        self.query = query

        # Parse result control (sort, limit, offset) and get cleaned query
        if query:
            filter_query, self.result_control = parse_result_control(query)
        else:
            filter_query = ''
            self.result_control = ResultControl()

        # Parse query filters conditionally (only if new operators present)
        # This prevents legacy parameters from being misinterpreted
        self.query_filters = []
        has_new_operators = filter_query and any(op in filter_query for op in ['>', '<', '!=', '~=', '..', '=='])

        if has_new_operators:
            try:
                self.query_filters = parse_query_filters(filter_query)
            except Exception:
                # If parsing fails, fall back to empty filters
                self.query_filters = []

        # Keep legacy filter parsing for backward compatibility
        # Only use legacy parsing if there are no new operators
        self.filters = []
        if filter_query and not has_new_operators:
            self.filters = query_module.parse_query(filter_query)

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Query markdown files and return matching results.

        Returns:
            Dict containing matched files with frontmatter summary
        """
        result = operations.get_structure(
            self.base_path,
            self.query or '',
            self.filters,
            self.query_filters,
            self.result_control
        )
        return {
            'contract_version': '1.0',
            'type': 'markdown_query',
            'source': str(self.base_path),
            'source_type': 'directory',
            **result,
        }

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get frontmatter from a specific file.

        Args:
            element_name: Filename or path to check

        Returns:
            Dict with file frontmatter details
        """
        return operations.get_element(self.base_path, element_name)

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about the query scope.

        Returns:
            Dict with query metadata
        """
        return operations.get_metadata(self.base_path)

    # Backward compatibility methods for tests
    def _parse_query(self, query: str):
        """Parse query string (backward compatibility)."""
        return query_module.parse_query(query)

    def _compare(self, field_value, operator, target_value):
        """Compare values (backward compatibility)."""
        return query_module.compare(field_value, operator, target_value)

    def _find_markdown_files(self):
        """Find markdown files (backward compatibility)."""
        from . import files
        return files.find_markdown_files(self.base_path)

    def _extract_frontmatter(self, path):
        """Extract frontmatter (backward compatibility)."""
        from . import files
        return files.extract_frontmatter(path)

    def _matches_filter(self, frontmatter, field, operator, value):
        """Match filter (backward compatibility)."""
        from . import filtering
        return filtering.matches_filter(frontmatter, field, operator, value)

    def _matches_all_filters(self, frontmatter):
        """Match all filters (backward compatibility)."""
        from . import filtering
        return filtering.matches_all_filters(frontmatter, self.filters, self.query_filters)
