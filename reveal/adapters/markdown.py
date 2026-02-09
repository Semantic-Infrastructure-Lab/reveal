"""Markdown query adapter (markdown://)."""

import os
import re
import sys
import yaml
import fnmatch
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from .base import ResourceAdapter, register_adapter, register_renderer
from ..utils.query import (
    parse_query_filters,
    parse_result_control,
    compare_values,
    ResultControl
)


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

    def __init__(self, base_path: str, query: Optional[str] = None):
        """Initialize the markdown query adapter.

        Args:
            base_path: Directory to search for markdown files
            query: Query string (e.g., 'topics=reveal', '!status', 'lines>100')
        """
        self.base_path = Path(base_path).resolve()
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
            self.filters = self._parse_query(filter_query)

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for markdown:// adapter.

        Returns JSON schema for AI agent integration.
        """
        return {
            'adapter': 'markdown',
            'description': 'Query markdown files by YAML frontmatter fields with filtering support',
            'uri_syntax': 'markdown://[path/]?[field=value][&field2=value2]',
            'query_params': {
                'field=value': {
                    'type': 'filter',
                    'description': 'Exact match (or substring for list fields)',
                    'operators': ['='],
                    'examples': ['topics=reveal', 'status=active', 'tags=python']
                },
                'field=*pattern*': {
                    'type': 'filter',
                    'description': 'Glob-style wildcard matching',
                    'operators': ['=', '*'],
                    'examples': ['type=*guide*', 'title=*API*']
                },
                '!field': {
                    'type': 'filter',
                    'description': 'File is missing this field',
                    'operators': ['!'],
                    'examples': ['!topics', '!status', '!title']
                }
            },
            'elements': {},  # Dynamic based on filenames
            'cli_flags': [],
            'supports_batch': False,
            'supports_advanced': False,
            'filter_logic': 'Multiple filters use AND logic (field1=val1&field2=val2)',
            'output_types': [
                {
                    'type': 'markdown_query',
                    'description': 'Markdown files matching frontmatter filters',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'markdown_query'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string', 'enum': ['directory', 'file']},
                            'base_path': {'type': 'string'},
                            'query': {'type': 'string'},
                            'filters': {'type': 'array'},
                            'total_files': {'type': 'integer'},
                            'matched_files': {'type': 'integer'},
                            'results': {
                                'type': 'array',
                                'items': {
                                    'type': 'object',
                                    'properties': {
                                        'path': {'type': 'string'},
                                        'relative_path': {'type': 'string'},
                                        'has_frontmatter': {'type': 'boolean'},
                                        'title': {'type': 'string'},
                                        'type': {'type': 'string'},
                                        'status': {'type': 'string'},
                                        'tags': {'type': 'array'},
                                        'topics': {'type': 'array'}
                                    }
                                }
                            }
                        }
                    },
                    'example': {
                        'contract_version': '1.0',
                        'type': 'markdown_query',
                        'source': 'docs/',
                        'source_type': 'directory',
                        'base_path': '/home/user/docs',
                        'query': 'topics=reveal&status=active',
                        'total_files': 42,
                        'matched_files': 5,
                        'results': [
                            {
                                'path': '/home/user/docs/reveal_guide.md',
                                'relative_path': 'docs/reveal_guide.md',
                                'has_frontmatter': True,
                                'title': 'Reveal Guide',
                                'topics': ['reveal', 'documentation'],
                                'status': 'active'
                            }
                        ]
                    }
                }
            ],
            'example_queries': [
                {
                    'uri': 'markdown://',
                    'description': 'List all markdown files in current directory',
                    'output_type': 'markdown_query'
                },
                {
                    'uri': 'markdown://docs/',
                    'description': 'List all markdown files in docs/ directory',
                    'output_type': 'markdown_query'
                },
                {
                    'uri': 'markdown://sessions/?topics=reveal',
                    'description': 'Find files where topics contains "reveal"',
                    'cli_flag': '?topics=reveal',
                    'output_type': 'markdown_query'
                },
                {
                    'uri': 'markdown://docs/?tags=python&status=active',
                    'description': 'Multiple filters (AND logic)',
                    'cli_flag': '?tags=python&status=active',
                    'output_type': 'markdown_query'
                },
                {
                    'uri': 'markdown://?!topics',
                    'description': 'Find files missing topics field',
                    'cli_flag': '?!topics',
                    'output_type': 'markdown_query'
                },
                {
                    'uri': 'markdown://?type=*guide*',
                    'description': 'Wildcard matching (glob-style)',
                    'cli_flag': '?type=*guide*',
                    'output_type': 'markdown_query'
                }
            ]
        }

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
                    'uri': 'markdown://?priority>10',
                    'description': 'Numeric comparison (greater than)'
                },
                {
                    'uri': 'markdown://?priority=5..15',
                    'description': 'Numeric range (5 to 15 inclusive)'
                },
                {
                    'uri': 'markdown://?title~=^API',
                    'description': 'Regex matching (titles starting with "API")'
                },
                {
                    'uri': 'markdown://?sort=-priority',
                    'description': 'Sort by priority descending'
                },
                {
                    'uri': 'markdown://?priority>5&sort=-priority&limit=10',
                    'description': 'Filter, sort, and limit results'
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
                'Numeric comparisons: field>value, field<value, field>=value, field<=value',
                'Range queries: field=min..max',
                'Regex matching: field~=pattern',
                'List fields: matches if value in list',
                'Multiple filters: field1=val1&field2=val2 (AND)',
                'Result control: sort=field, sort=-field (descending)',
                'Pagination: limit=N, offset=M',
                'JSON output for tooling integration',
            ],
            'operators': {
                'field=value': 'Exact match (or substring for lists)',
                'field>value': 'Greater than (numeric)',
                'field<value': 'Less than (numeric)',
                'field>=value': 'Greater than or equal (numeric)',
                'field<=value': 'Less than or equal (numeric)',
                'field!=value': 'Not equal',
                'field~=pattern': 'Regex match',
                'field=min..max': 'Range (inclusive)',
                'field=*pattern*': 'Glob-style wildcard',
                '!field': 'Field is missing',
            },
            'result_control': {
                'sort=field': 'Sort results by field (ascending)',
                'sort=-field': 'Sort results by field (descending)',
                'limit=N': 'Limit to N results',
                'offset=M': 'Skip first M results',
            },
            'notes': [
                'Searches recursively in specified directory',
                'Only processes files with valid YAML frontmatter',
                'Field values in lists are matched if any item matches',
                'Numeric comparisons work on numeric frontmatter fields',
                'Use sort/limit/offset for pagination and result control',
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

    def _compare(self, field_value: Any, operator: str, target_value: str) -> bool:
        """Compare field value against target using operator.

        Uses unified compare_values() from query.py to eliminate duplication.

        Args:
            field_value: Value from frontmatter field
            operator: Comparison operator (>, <, >=, <=, ==, !=, ~=, .., !~)
            target_value: Target value to compare against

        Returns:
            True if comparison matches
        """
        return compare_values(
            field_value,
            operator,
            target_value,
            options={
                'allow_list_any': True,
                'case_sensitive': False,
                'coerce_numeric': True,
                'none_matches_not_equal': True
            }
        )

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
        # Check legacy filters first (backward compatibility)
        if self.filters:
            if not all(
                self._matches_filter(frontmatter, field, op, value)
                for field, op, value in self.filters
            ):
                return False

        # Check new query filters (unified syntax)
        if self.query_filters:
            for qf in self.query_filters:
                if frontmatter is None:
                    return False

                # Get field value from frontmatter
                field_value = frontmatter.get(qf.field)

                # Compare using operator
                if not self._compare(field_value, qf.op, qf.value):
                    return False

        return True

    def _build_result_item(self, path: Path, frontmatter: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Build result item dict with path and frontmatter fields."""
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

        return result

    def _create_sort_key(self, item: Dict[str, Any]) -> tuple:
        """Create sort key for an item based on result_control.sort_field."""
        # Check if field exists in the result dict (including frontmatter fields)
        if self.result_control.sort_field in item:
            value = item[self.result_control.sort_field]
            # Handle None values (sort to end)
            if value is None:
                return (1, 0) if self.result_control.sort_descending else (0, 0)
            # Handle list values (use first element)
            if isinstance(value, list):
                return (0, str(value[0]) if value else '')
            return (0, value)
        return (1, 0) if self.result_control.sort_descending else (0, 0)

    def _apply_sorting(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply sorting to results based on result_control."""
        if not self.result_control.sort_field:
            return results

        try:
            return sorted(
                results,
                key=self._create_sort_key,
                reverse=self.result_control.sort_descending
            )
        except Exception:
            # If sorting fails, continue without sorting
            return results

    def _apply_pagination(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply offset and limit to results based on result_control."""
        if self.result_control.offset:
            results = results[self.result_control.offset:]
        if self.result_control.limit is not None:
            results = results[:self.result_control.limit]
        return results

    def _build_response_dict(
        self,
        files: List[Path],
        total_matches: int,
        controlled_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build response dict with metadata."""
        return {
            'contract_version': '1.0',
            'type': 'markdown_query',
            'source': str(self.base_path),
            'source_type': 'directory' if self.base_path.is_dir() else 'file',
            'base_path': str(self.base_path),
            'query': self.query,
            'filters': [
                {'field': f, 'operator': o, 'value': v}
                for f, o, v in self.filters
            ],
            'total_files': len(files),
            'matched_files': total_matches,
            'results': controlled_results,
        }

    def _add_truncation_warning(
        self,
        response: Dict[str, Any],
        displayed: int,
        total_matches: int
    ) -> None:
        """Add truncation warning to response if results were limited."""
        if displayed < total_matches:
            response['warnings'] = [{
                'type': 'truncated',
                'message': f'Results truncated: showing {displayed} of {total_matches} total matches'
            }]
            response['displayed_results'] = displayed
            response['total_matches'] = total_matches

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Query markdown files and return matching results.

        Returns:
            Dict containing matched files with frontmatter summary
        """
        files = self._find_markdown_files()
        results = []

        # Build results for matching files
        for path in files:
            frontmatter = self._extract_frontmatter(path)
            if self._matches_all_filters(frontmatter):
                result = self._build_result_item(path, frontmatter)
                results.append(result)

        # Apply result control (sort, limit, offset)
        total_matches = len(results)
        controlled_results = self._apply_sorting(results)
        controlled_results = self._apply_pagination(controlled_results)

        # Build response with metadata
        response = self._build_response_dict(files, total_matches, controlled_results)

        # Add truncation warning if needed
        displayed = len(controlled_results)
        self._add_truncation_warning(response, displayed, total_matches)

        return response

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
