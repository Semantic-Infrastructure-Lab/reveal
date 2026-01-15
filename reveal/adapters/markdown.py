"""Markdown query adapter (markdown://)."""

import os
import re
import sys
import yaml
import fnmatch
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from .base import ResourceAdapter, register_adapter, register_renderer


class MarkdownRenderer:
    """Renderer for markdown query results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render markdown query results.

        Args:
            result: Structure dict from MarkdownQueryAdapter.get_structure()
            format: Output format ('text', 'json', 'grep')
        """
        from ..rendering.adapters.markdown_query import render_markdown_query
        render_markdown_query(result, format)

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        """Render specific markdown file frontmatter.

        Args:
            result: Element dict from MarkdownQueryAdapter.get_element()
            format: Output format ('text', 'json', 'grep')
        """
        from ..rendering.adapters.markdown_query import render_markdown_query
        render_markdown_query(result, format, single_file=True)

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render user-friendly errors."""
        print(f"Error querying markdown: {error}", file=sys.stderr)


@register_adapter('markdown')
@register_renderer(MarkdownRenderer)
class MarkdownQueryAdapter(ResourceAdapter):
    """Adapter for querying markdown files by frontmatter via markdown:// URIs.

    Enables finding markdown files based on frontmatter field values,
    missing fields, or wildcards. Works on local directory trees.
    """

    def __init__(self, base_path: str = '.', query: Optional[str] = None):
        """Initialize the markdown query adapter.

        Args:
            base_path: Directory to search for markdown files
            query: Query string (e.g., 'topics=reveal', '!status')
        """
        self.base_path = Path(base_path).resolve()
        self.query = query
        self.filters = self._parse_query(query) if query else []

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for markdown:// adapter."""
        return {
            'name': 'markdown',
            'description': 'Query markdown files by front matter fields',
            'syntax': 'markdown://[path/]?[field=value][&field2=value2]',
            'examples': [
                {
                    'uri': 'markdown://',
                    'description': 'List all markdown files in current directory'
                },
                {
                    'uri': 'markdown://docs/',
                    'description': 'List all markdown files in docs/ directory'
                },
                {
                    'uri': 'markdown://sessions/?topics=reveal',
                    'description': 'Find files where topics contains "reveal"'
                },
                {
                    'uri': 'markdown://docs/?tags=python&status=active',
                    'description': 'Multiple filters (AND logic)'
                },
                {
                    'uri': 'markdown://?!topics',
                    'description': 'Find files missing topics field'
                },
                {
                    'uri': 'markdown://?type=*guide*',
                    'description': 'Wildcard matching (glob-style)'
                },
                {
                    'uri': 'markdown://docs/?status=active --format=json',
                    'description': 'JSON output for scripting'
                },
            ],
            'features': [
                'Recursive directory traversal',
                'Exact match: field=value',
                'Wildcard match: field=*pattern* (glob-style)',
                'Missing field: !field',
                'List fields: matches if value in list',
                'Multiple filters: field1=val1&field2=val2 (AND)',
                'JSON output for tooling integration',
            ],
            'filters': {
                'field=value': 'Exact match (or substring for lists)',
                'field=*pattern*': 'Glob-style wildcard matching',
                '!field': 'File is missing this field',
            },
            'notes': [
                'Searches recursively in specified directory',
                'Only processes files with valid YAML frontmatter',
                'Field values in lists are matched if any item matches',
                'Combine with reveal --related for graph exploration',
            ],
            'try_now': [
                'reveal markdown://',
                'reveal markdown://?!title',
            ],
            'workflows': [
                {
                    'name': 'Find Undocumented Files',
                    'scenario': 'Identify files missing required metadata',
                    'steps': [
                        "reveal markdown://?!topics      # Missing topics",
                        "reveal markdown://?!status           # Missing status",
                    ],
                },
                {
                    'name': 'Explore Knowledge Graph',
                    'scenario': 'Find and traverse related documents',
                    'steps': [
                        "reveal markdown://sessions/?topics=reveal",
                        "reveal <found-file> --related-all    # Follow links",
                    ],
                },
            ],
            'output_formats': ['text', 'json', 'grep'],
            'see_also': [
                'reveal file.md --related - Follow related documents',
                'reveal file.md --frontmatter - Show frontmatter',
                'reveal help://knowledge-graph - Knowledge graph guide',
            ]
        }

    def _parse_query(self, query: str) -> List[Tuple[str, str, str]]:
        """Parse query string into filter tuples.

        Args:
            query: Query string (e.g., 'field=value&!other')

        Returns:
            List of (field, operator, value) tuples
            Operators: '=' (match), '!' (missing), '*' (wildcard)
        """
        filters = []
        if not query:
            return filters

        # Split on & for multiple filters
        parts = query.split('&')
        for part in parts:
            part = part.strip()
            if not part:
                continue

            if part.startswith('!'):
                # Missing field filter: !field
                field = part[1:]
                filters.append((field, '!', ''))
            elif '=' in part:
                # Value filter: field=value or field=*pattern*
                field, value = part.split('=', 1)
                if '*' in value:
                    filters.append((field, '*', value))
                else:
                    filters.append((field, '=', value))
            else:
                # Treat as existence check: field (exists)
                filters.append((part, '?', ''))

        return filters

    def _find_markdown_files(self) -> List[Path]:
        """Find all markdown files in base_path recursively.

        Returns:
            List of Path objects to markdown files
        """
        files = []
        if not self.base_path.exists():
            return files

        if self.base_path.is_file():
            if self.base_path.suffix.lower() in ('.md', '.markdown'):
                return [self.base_path]
            return []

        for root, _, filenames in os.walk(self.base_path):
            for filename in filenames:
                if filename.lower().endswith(('.md', '.markdown')):
                    files.append(Path(root) / filename)

        return sorted(files)

    def _extract_frontmatter(self, path: Path) -> Optional[Dict[str, Any]]:
        """Extract YAML frontmatter from a markdown file.

        Args:
            path: Path to markdown file

        Returns:
            Frontmatter dict or None if no valid frontmatter
        """
        try:
            content = path.read_text(encoding='utf-8')
        except Exception:
            return None

        # Check for frontmatter
        if not content.startswith('---'):
            return None

        # Find closing ---
        end_match = re.search(r'\n---\s*\n', content[3:])
        if not end_match:
            return None

        yaml_content = content[3:end_match.start() + 3]

        try:
            return yaml.safe_load(yaml_content)
        except yaml.YAMLError:
            return None

    def _matches_filter(self, frontmatter: Optional[Dict[str, Any]],
                        field: str, operator: str, value: str) -> bool:
        """Check if frontmatter matches a single filter.

        Args:
            frontmatter: Parsed frontmatter dict (or None)
            field: Field name to check
            operator: '=' (match), '!' (missing), '*' (wildcard), '?' (exists)
            value: Value to match against

        Returns:
            True if matches
        """
        if operator == '!':
            # Missing field filter
            return frontmatter is None or field not in frontmatter

        if frontmatter is None:
            return False

        if operator == '?':
            # Exists filter
            return field in frontmatter

        if field not in frontmatter:
            return False

        fm_value = frontmatter[field]

        # Handle list values (match if any item matches)
        if isinstance(fm_value, list):
            if operator == '*':
                return any(fnmatch.fnmatch(str(item), value) for item in fm_value)
            else:
                return any(str(item) == value for item in fm_value)

        # Handle scalar values
        fm_str = str(fm_value)
        if operator == '*':
            return fnmatch.fnmatch(fm_str, value)
        else:
            return fm_str == value

    def _matches_all_filters(self, frontmatter: Optional[Dict[str, Any]]) -> bool:
        """Check if frontmatter matches all filters (AND logic).

        Args:
            frontmatter: Parsed frontmatter dict (or None)

        Returns:
            True if matches all filters
        """
        if not self.filters:
            return True  # No filters = match all

        return all(
            self._matches_filter(frontmatter, field, op, value)
            for field, op, value in self.filters
        )

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Query markdown files and return matching results.

        Returns:
            Dict containing matched files with frontmatter summary
        """
        files = self._find_markdown_files()
        results = []

        for path in files:
            frontmatter = self._extract_frontmatter(path)

            if self._matches_all_filters(frontmatter):
                result = {
                    'path': str(path),
                    'relative_path': str(path.relative_to(Path.cwd())
                                         if path.is_relative_to(Path.cwd())
                                         else path),
                    'has_frontmatter': frontmatter is not None,
                }

                # Include key frontmatter fields
                if frontmatter:
                    for key in ['title', 'type', 'status', 'tags', 'topics']:
                        if key in frontmatter:
                            result[key] = frontmatter[key]

                results.append(result)

        return {
            'type': 'markdown_query',
            'base_path': str(self.base_path),
            'query': self.query,
            'filters': [
                {'field': f, 'operator': o, 'value': v}
                for f, o, v in self.filters
            ],
            'total_files': len(files),
            'matched_files': len(results),
            'results': results,
        }

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get frontmatter from a specific file.

        Args:
            element_name: Filename or path to check

        Returns:
            Dict with file frontmatter details
        """
        # Try to find the file
        target = self.base_path / element_name
        if not target.exists():
            target = Path(element_name)

        if not target.exists():
            return None

        frontmatter = self._extract_frontmatter(target)

        return {
            'path': str(target),
            'has_frontmatter': frontmatter is not None,
            'frontmatter': frontmatter,
        }

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about the query scope.

        Returns:
            Dict with query metadata
        """
        files = self._find_markdown_files()
        with_fm = sum(1 for f in files if self._extract_frontmatter(f) is not None)

        return {
            'type': 'markdown_query',
            'base_path': str(self.base_path),
            'total_files': len(files),
            'with_frontmatter': with_fm,
            'without_frontmatter': len(files) - with_fm,
        }
