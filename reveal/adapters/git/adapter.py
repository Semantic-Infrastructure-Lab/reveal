"""Git repository inspection adapter.

Progressive disclosure for Git repositories with token-efficient output.
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, Any, Optional, List, cast, Union
from ..base import ResourceAdapter, register_adapter, register_renderer
from ...utils.query import (
    parse_query_filters,
    parse_result_control,
    compare_values,
    ResultControl
)


# Check if pygit2 is available
try:
    import pygit2
    PYGIT2_AVAILABLE = True
except ImportError:
    PYGIT2_AVAILABLE = False
    pygit2 = None  # type: ignore[assignment]


class GitRenderer:
    """Renderer for git repository inspection results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render git repository structure.

        Args:
            result: Git structure from adapter
            format: Output format (text, json)
        """
        if format == 'json':
            print(json.dumps(result, indent=2))
            return

        # Text rendering based on result type
        result_type = result.get('type', 'unknown')

        if result_type in ('repository', 'git_repository'):
            GitRenderer._render_repository_overview(result)
        elif result_type in ('ref', 'git_ref'):
            GitRenderer._render_ref_structure(result)
        elif result_type in ('file', 'git_file'):
            GitRenderer._render_file(result)
        elif result_type in ('file_history', 'git_file_history'):
            GitRenderer._render_file_history(result)
        elif result_type in ('file_blame', 'git_file_blame'):
            GitRenderer._render_file_blame(result)
        else:
            print(json.dumps(result, indent=2))

    @staticmethod
    def _render_repository_overview(result: dict) -> None:
        """Render repository overview."""
        print(f"Repository: {result['path']}")
        print()

        head = result['head']
        if head['branch']:
            print(f"HEAD: {head['branch']} @ {head['commit']}")
        elif head['detached']:
            print(f"HEAD: (detached) @ {head['commit']}")
        print()

        print(f"Branches: {result['branches']['count']}")
        for branch in result['branches']['recent']:
            print(f"  • {branch['name']:<20} {branch['commit']} {branch['date']} {branch['message']}")
        print()

        print(f"Tags: {result['tags']['count']}")
        for tag in result['tags']['recent']:
            print(f"  • {tag['name']:<20} {tag['commit']} {tag['date']} {tag['message']}")
        print()

        print("Recent Commits:")
        for commit in result['commits']['recent']:
            print(f"  {commit['hash']} {commit['date']} {commit['author']}")
            print(f"    {commit['message']}")

    @staticmethod
    def _render_ref_structure(result: dict) -> None:
        """Render ref/commit history."""
        print(f"Ref: {result['ref']}")
        print()

        commit = result['commit']
        print(f"Commit: {commit['full_hash']}")
        print(f"Author: {commit['author']} <{commit['email']}>")
        print(f"Date:   {commit['date']}")
        print()
        print(commit['full_message'])
        print()

        print("History:")
        for c in result['history']:
            print(f"  {c['hash']} {c['date']} {c['author']}")
            print(f"    {c['message']}")

    @staticmethod
    def _render_file(result: dict) -> None:
        """Render file contents."""
        print(f"File: {result['path']} @ {result['ref']}")
        print(f"Commit: {result['commit']}")
        print(f"Size: {result['size']} bytes, {result['lines']} lines")
        print()
        print(result['content'])

    @staticmethod
    def _render_file_history(result: dict) -> None:
        """Render file history."""
        print(f"File History: {result['path']} @ {result['ref']}")
        print(f"Commits: {result['count']}")
        print()

        for commit in result['commits']:
            print(f"  {commit['hash']} {commit['date']} {commit['author']}")
            print(f"    {commit['message']}")

    @staticmethod
    def _render_file_blame(result: dict) -> None:
        """Render file blame with progressive disclosure."""
        # Check if detail mode is requested
        detail_mode = result.get('detail', False)

        if detail_mode:
            # Detailed view: show all hunks (original behavior)
            print(f"File Blame (Detailed): {result['path']} @ {result['ref']}")
            print(f"Lines: {result['lines']}")
            print()

            for hunk in result['hunks']:
                lines_info = hunk['lines']
                commit_info = hunk['commit']
                print(f"Lines {lines_info['start']}-{lines_info['start'] + lines_info['count'] - 1}:")
                print(f"  {commit_info['hash']} {commit_info['date']} {commit_info['author']}")
                print(f"  {commit_info['message']}")
                print()
        else:
            # Summary view: show contributors and key hunks
            GitRenderer._render_file_blame_summary(result)

    @staticmethod
    def _render_file_blame_summary(result: dict) -> None:
        """Render blame summary (default view)."""
        # Check if this is semantic blame (element-specific)
        element = result.get('element')
        if element:
            print(f"Element Blame: {result['path']} → {element['name']}")
            print(f"Lines {element['line_start']}-{element['line_end']} ({len(result['hunks'])} hunks)")
        else:
            print(f"File Blame Summary: {result['path']} ({result['lines']} lines, {len(result['hunks'])} hunks)")
        print()

        # Calculate contributor stats
        contributors = {}
        for hunk in result['hunks']:
            author = hunk['commit']['author']
            lines = hunk['lines']['count']
            if author not in contributors:
                contributors[author] = {'lines': 0, 'hunks': 0, 'latest_date': hunk['commit']['date']}
            contributors[author]['lines'] += lines
            contributors[author]['hunks'] += 1
            # Track latest commit date
            if hunk['commit']['date'] > contributors[author]['latest_date']:
                contributors[author]['latest_date'] = hunk['commit']['date']

        # Sort by lines contributed (descending)
        sorted_contributors = sorted(contributors.items(), key=lambda x: x[1]['lines'], reverse=True)

        print("Contributors (by lines owned):")
        total_lines = result['lines']
        for author, stats in sorted_contributors[:5]:  # Top 5 contributors
            pct = (stats['lines'] / total_lines * 100) if total_lines > 0 else 0
            print(f"  {author:30} {stats['lines']:4} lines ({pct:5.1f}%)  Last: {stats['latest_date']}")

        if len(sorted_contributors) > 5:
            print(f"  ... and {len(sorted_contributors) - 5} more contributors")
        print()

        # Find key hunks (largest continuous blocks)
        key_hunks = sorted(result['hunks'], key=lambda h: h['lines']['count'], reverse=True)[:5]

        print("Key hunks (largest continuous blocks):")
        for hunk in key_hunks:
            lines_info = hunk['lines']
            commit_info = hunk['commit']
            start = lines_info['start']
            end = start + lines_info['count'] - 1
            print(f"  Lines {start:3}-{end:3} ({lines_info['count']:3} lines)  {commit_info['hash']} {commit_info['date']} {commit_info['author'][:20]}")
            print(f"    {commit_info['message'][:70]}")
        print()

        print(f"Use: reveal git://{result['path']}?type=blame&detail=full for line-by-line view")

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render error message."""
        print(f"Error: {error}", file=sys.stderr)
        if isinstance(error, ImportError):
            # pygit2 not installed
            print(file=sys.stderr)
            print("The git:// adapter requires pygit2.", file=sys.stderr)
            print("Install with: pip install reveal-cli[git]", file=sys.stderr)
            print("Alternative: pip install pygit2>=1.14.0", file=sys.stderr)
            print(file=sys.stderr)
            print("For more info: reveal help://git", file=sys.stderr)


@register_adapter('git')
@register_renderer(GitRenderer)
class GitAdapter(ResourceAdapter):
    """
    Git repository inspection adapter.

    Provides progressive disclosure of Git repository structure:
    - Repository → Branches/Tags → Commits → Files → History/Blame

    Examples:
        git://.                    # Repository overview
        git://.@main               # Branch/commit history
        git://path/file.py@tag     # File at specific tag
        git://path/file.py?type=history  # File history
        git://path/file.py?type=blame    # File blame

    Requires: pip install reveal-cli[git]
    """

    def _normalize_resource_parameter(self, resource: Optional[str],
                                       path: Optional[str]) -> str:
        """Normalize resource parameter handling backward compatibility.

        Args:
            resource: Resource string
            path: Backward compatibility path parameter

        Returns:
            Normalized resource string

        Raises:
            TypeError: If no resource provided
        """
        # Handle backward compatibility: path= parameter takes precedence
        if path is not None:
            resource = path

        # No-arg initialization should raise TypeError, not ValueError
        # This lets the generic handler try the next pattern
        if resource is None:
            raise TypeError("GitAdapter requires a resource path")

        return resource

    def _handle_routing_query_workaround(self, ref: Optional[str],
                                          query: Optional[Dict[str, str]]) -> tuple:
        """Handle routing.py passing query string as ref parameter.

        routing.py Try 2 does: adapter_class(path, query)

        Args:
            ref: Git reference (or query string)
            query: Query parameters dict

        Returns:
            Tuple of (ref, query) with query string extracted if needed
        """
        if ref is not None and '=' in ref and query is None:
            # ref looks like a query string, move it to query
            query_string = ref
            ref = None
            query = {}
            for param in query_string.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    query[key] = value

        return ref, query

    def _parse_and_initialize_attributes(self, resource: str, ref: Optional[str],
                                          subpath: Optional[str],
                                          query: Optional[Dict[str, str]]) -> None:
        """Parse resource string or use explicit args to initialize attributes.

        Args:
            resource: Resource string or path
            ref: Git reference
            subpath: Path within repository
            query: Query parameters
        """
        # Parse resource string if it looks like a URI (has @ or is a file path)
        # This handles both "README.md@ref" and "README.md" (treated as subpath)
        # Also handles empty string from bare URIs like "git://"
        if subpath is None and resource is not None:
            # Parse resource string to extract path/subpath/ref
            parsed = self._parse_resource_string(resource)
            self.path = parsed['path']
            # Only override ref/query if not already set from routing workaround
            if ref is None:
                self.ref = parsed['ref']
            else:
                self.ref = ref
            self.subpath = parsed['subpath']
            # Merge parsed query with explicitly provided query
            if query:
                self.query = {**parsed['query'], **query}
            else:
                self.query = parsed['query']
        else:
            # Old style: explicit arguments (all provided)
            self.path = resource
            self.ref = ref or 'HEAD'
            self.subpath = subpath
            self.query = query or {}

    def _separate_query_parameters(self) -> tuple:
        """Separate result control params from filter params.

        Returns:
            Tuple of (result_control_parts, filter_parts)
        """
        result_control_parts = []
        filter_parts = []

        for k, v in self.query.items():
            # Result control parameters
            if k in ['sort', 'limit', 'offset']:
                result_control_parts.append(f"{k}={v}")
            # Operational parameters (exclude from both)
            elif k in ['type', 'detail', 'element']:
                continue
            # Filter parameters
            else:
                # Check if key already ends with an operator character (~, !, >, <, .)
                if k and k[-1] in ['~', '!', '>', '<', '.']:
                    # Key has operator, just add = between key and value
                    filter_parts.append(f"{k}={v}")
                else:
                    # Regular key, use = operator
                    filter_parts.append(f"{k}={v}")

        return result_control_parts, filter_parts

    def _initialize_result_control(self, result_control_parts: list) -> None:
        """Initialize result control from parts.

        Args:
            result_control_parts: List of result control parameter strings
        """
        result_control_query = '&'.join(result_control_parts)
        if result_control_query:
            _, self.result_control = parse_result_control(result_control_query)
        else:
            self.result_control = ResultControl()

    def _initialize_query_filters(self, filter_parts: list) -> None:
        """Initialize query filters from parts.

        Args:
            filter_parts: List of filter parameter strings
        """
        filter_query = '&'.join(filter_parts)
        self.query_filters = []
        if filter_query:
            try:
                self.query_filters = parse_query_filters(filter_query)
            except Exception:
                # If parsing fails, fall back to empty filters
                self.query_filters = []

    def __init__(self, resource: Optional[str] = None, ref: Optional[str] = None,
                 subpath: Optional[str] = None, query: Optional[Dict[str, str]] = None,
                 path: Optional[str] = None):
        """
        Initialize Git adapter.

        Supports two initialization styles:
        1. Single resource string (new style, for generic handler):
           GitAdapter("path/file.py@ref?type=history")
        2. Multiple arguments (old style, backward compatibility):
           GitAdapter(path=".", ref="main", subpath="file.py", query={...})

        Args:
            resource: Either resource URI string or repository path (optional if path provided)
            ref: Git reference (commit, branch, tag, HEAD~N)
            subpath: Path within repository (file or directory)
            query: Query parameters (type=history|blame, since, author, etc.)
            path: Alias for resource (backward compatibility with tests)
        """
        # Normalize resource parameter
        resource = self._normalize_resource_parameter(resource, path)

        # Handle routing workaround
        ref, query = self._handle_routing_query_workaround(ref, query)

        # Parse and initialize attributes
        self._parse_and_initialize_attributes(resource, ref, subpath, query)

        self.repo: Optional['pygit2.Repository'] = None

        # Parse query parameters
        result_control_parts, filter_parts = self._separate_query_parameters()

        # Initialize result control and filters
        self._initialize_result_control(result_control_parts)
        self._initialize_query_filters(filter_parts)

    @staticmethod
    def _parse_resource_string(resource: str) -> Dict[str, Any]:
        """Parse git resource string.

        Handles various git:// URI formats:
        - "." - current directory, default ref
        - ".@main" - current dir, main branch
        - "path/file.py@v1.0" - file at tag
        - "path/file.py?type=history" - file history
        - ".@HEAD~1/src/app.py?type=blame" - complex

        Args:
            resource: Resource string from URI

        Returns:
            Dict with path, ref, subpath, query
        """
        path = '.'
        ref = 'HEAD'
        subpath = None
        query: Dict[str, Any] = {}

        # Handle empty resource
        if not resource or resource == '':
            return {'path': path, 'ref': ref, 'subpath': subpath, 'query': query}

        # Extract query parameters first (?key=value)
        if '?' in resource:
            resource, query_string = resource.rsplit('?', 1)
            # Simple query parsing (key=value&key2=value2)
            for param in query_string.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    query[key] = value

        # Extract ref (@branch or @tag or @commit)
        if '@' in resource:
            resource, ref = resource.rsplit('@', 1)

        # What's left is path or subpath
        # Logic: If resource starts with "." or "/", treat as repo path
        # Otherwise, treat as subpath within current directory
        if resource:
            if resource == '.' or resource.startswith('/') or resource.startswith('./'):
                path = resource
                subpath = None
            else:
                # Resource looks like a file path, not a repo path
                path = '.'
                subpath = resource

        return {'path': path, 'ref': ref, 'subpath': subpath, 'query': query}

    def _check_pygit2(self):
        """Check if pygit2 is available and provide helpful error."""
        if not PYGIT2_AVAILABLE:
            raise ImportError(
                "git:// adapter requires pygit2\n\n"
                "Install with: pip install reveal-cli[git]\n"
                "Alternative: pip install pygit2>=1.14.0\n\n"
                "For more info: reveal help://git"
            )

    def _open_repository(self) -> 'pygit2.Repository':
        """Open pygit2 repository. Lazy initialization."""
        self._check_pygit2()

        if self.repo is None:
            try:
                # Discover repository from path
                repo_path = pygit2.discover_repository(self.path)
                if not repo_path:
                    raise ValueError(f"Not a git repository: {self.path}")
                self.repo = pygit2.Repository(repo_path)
            except (pygit2.GitError, KeyError) as e:
                raise ValueError(f"Failed to open repository: {self.path}") from e
        return self.repo

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """
        Get repository structure using progressive disclosure.

        Returns different views based on what's specified:
        - No ref/subpath: Repository overview (branches, tags, recent commits)
        - With ref: Commit details or ref history
        - With subpath: File contents, history, or blame
        """
        repo = self._open_repository()

        # Check query type for special operations
        query_type = self.query.get('type', None)

        if self.subpath:
            if query_type == 'history':
                return self._get_file_history(repo)
            elif query_type == 'blame':
                return self._get_file_blame(repo)
            else:
                return self._get_file_at_ref(repo)
        elif self.ref != 'HEAD' or query_type:
            return self._get_ref_structure(repo)
        else:
            return self._get_repository_overview(repo)

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Extract specific element (commit, file, branch).

        Args:
            element_name: Name of element (commit hash, branch name, file path)
        """
        repo = self._open_repository()

        # Try as commit hash
        try:
            commit = repo.revparse_single(element_name)
            if isinstance(commit, pygit2.Commit):
                return self._format_commit(commit, detailed=True)
        except (KeyError, pygit2.GitError):
            pass

        # Try as file path at current ref
        if '/' in element_name or '.' in element_name:
            old_subpath = self.subpath
            self.subpath = element_name
            try:
                result = self._get_file_at_ref(repo)
                return result
            except Exception:
                pass
            finally:
                self.subpath = old_subpath

        return None

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for git:// adapter.

        Returns JSON schema for AI agent integration.
        """
        return {
            'adapter': 'git',
            'description': 'Git repository inspection with history, blame, and file tracking',
            'uri_syntax': 'git://<path>[/<subpath>][@<ref>][?<query>]',
            'query_params': {
                'type': {
                    'type': 'string',
                    'description': 'Query type for file operations',
                    'values': ['history', 'blame'],
                    'examples': ['?type=history', '?type=blame']
                },
                'detail': {
                    'type': 'string',
                    'description': 'Detail level for blame',
                    'values': ['full', 'summary'],
                    'examples': ['?type=blame&detail=full']
                },
                'element': {
                    'type': 'string',
                    'description': 'Semantic element for blame (function/class name)',
                    'examples': ['?type=blame&element=load_config']
                },
                'author': {
                    'type': 'string',
                    'description': 'Filter commits by author name (case-insensitive)',
                    'examples': ['?author=John', '?author~=john']
                },
                'email': {
                    'type': 'string',
                    'description': 'Filter commits by author email (case-insensitive)',
                    'examples': ['?email=john@example.com', '?email~=@example.com']
                },
                'message': {
                    'type': 'string',
                    'description': 'Filter commits by message (supports regex with ~=)',
                    'examples': ['?message~=bug', '?message=Initial commit']
                },
                'hash': {
                    'type': 'string',
                    'description': 'Filter commits by hash prefix',
                    'examples': ['?hash=a1b2c3d']
                }
            },
            'elements': {},  # File paths and refs are dynamic
            'cli_flags': [],
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': [
                {
                    'type': 'git_repository',
                    'description': 'Repository overview with branches, tags, and recent commits',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'git_repository'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string', 'const': 'repository'},
                            'path': {'type': 'string'},
                            'head': {'type': 'object'},
                            'branches': {'type': 'object'},
                            'tags': {'type': 'object'},
                            'commits': {'type': 'object'}
                        }
                    }
                },
                {
                    'type': 'git_ref',
                    'description': 'Branch/tag/commit history',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'git_ref'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string'},
                            'ref': {'type': 'string'},
                            'commit': {'type': 'object'},
                            'history': {'type': 'array'}
                        }
                    }
                },
                {
                    'type': 'git_file',
                    'description': 'File contents at specific ref',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'git_file'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string', 'const': 'file'},
                            'path': {'type': 'string'},
                            'ref': {'type': 'string'},
                            'commit': {'type': 'string'},
                            'size': {'type': 'integer'},
                            'lines': {'type': 'integer'},
                            'content': {'type': 'string'}
                        }
                    }
                },
                {
                    'type': 'git_file_history',
                    'description': 'File commit history',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'git_file_history'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string'},
                            'path': {'type': 'string'},
                            'ref': {'type': 'string'},
                            'count': {'type': 'integer'},
                            'commits': {'type': 'array'}
                        }
                    }
                },
                {
                    'type': 'git_file_blame',
                    'description': 'File blame with author attribution',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'git_file_blame'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string'},
                            'path': {'type': 'string'},
                            'ref': {'type': 'string'},
                            'lines': {'type': 'integer'},
                            'element': {'type': ['string', 'null']},
                            'contributors': {'type': 'array'},
                            'hunks': {'type': 'array'}
                        }
                    }
                }
            ],
            'example_queries': [
                {
                    'uri': 'git://.',
                    'description': 'Repository overview (branches, tags, commits)',
                    'output_type': 'git_repository'
                },
                {
                    'uri': 'git://.@main',
                    'description': 'Branch/commit history',
                    'ref': 'main',
                    'output_type': 'git_ref'
                },
                {
                    'uri': 'git://.@abc1234',
                    'description': 'Specific commit details',
                    'ref': 'abc1234',
                    'output_type': 'git_ref'
                },
                {
                    'uri': 'git://src/app.py@v1.0',
                    'description': 'File contents at tag',
                    'ref': 'v1.0',
                    'output_type': 'git_file'
                },
                {
                    'uri': 'git://src/app.py?type=history',
                    'description': 'File commit history (50 commits)',
                    'query_param': '?type=history',
                    'output_type': 'git_file_history'
                },
                {
                    'uri': 'git://src/app.py?type=blame',
                    'description': 'File blame summary (contributors + key hunks)',
                    'query_param': '?type=blame',
                    'output_type': 'git_file_blame'
                },
                {
                    'uri': 'git://src/app.py?type=blame&detail=full',
                    'description': 'File blame detailed (line-by-line)',
                    'query_param': '?type=blame&detail=full',
                    'output_type': 'git_file_blame'
                },
                {
                    'uri': 'git://src/app.py?type=blame&element=load_config',
                    'description': 'Semantic blame (who wrote this function)',
                    'query_param': '?type=blame&element=load_config',
                    'output_type': 'git_file_blame'
                }
            ],
            'notes': [
                'Requires pygit2 library (pip install pygit2)',
                'Supports @ syntax for refs (branches, tags, commits)',
                'Query params for file-level operations (history, blame)',
                'Semantic blame works with Python functions/classes'
            ]
        }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for git:// adapter."""
        return {
            'name': 'git',
            'description': 'Explore Git repositories with progressive disclosure',
            'syntax': 'git://<path>[/<subpath>][@<ref>][?<query>]',
            'examples': [
                {'uri': 'git://.', 'description': 'Repository overview (branches, tags, commits)'},
                {'uri': 'git://.@main', 'description': 'Branch/commit history'},
                {'uri': 'git://.@abc1234', 'description': 'Specific commit details'},
                {'uri': 'git://src/app.py@v1.0', 'description': 'File contents at tag'},
                {'uri': 'git://src/app.py?type=history', 'description': 'File commit history (50 commits)'},
                {'uri': 'git://src/app.py?type=blame', 'description': 'File blame summary (contributors + key hunks)'},
                {'uri': 'git://src/app.py?type=blame&detail=full', 'description': 'File blame detailed (line-by-line)'},
                {'uri': 'git://src/app.py?type=blame&element=load_config', 'description': 'Semantic blame (who wrote this function)'},
                {'uri': 'git://.?author=John', 'description': 'Filter commits by author name'},
                {'uri': 'git://.?message~=bug', 'description': 'Filter commits with "bug" in message (regex)'},
                {'uri': 'git://.?author=John&message~=fix', 'description': 'Filter by author AND message'},
            ],
            'query_parameters': {
                'type': 'Operation type: history (file history) or blame (line annotations)',
                'detail': 'For blame: "full" shows line-by-line (default is summary)',
                'element': 'For blame: function/class name for semantic blame',
                'limit': 'Limit number of results (default: 50 for history, 20 for refs)',
                'author': 'Filter commits by author name (case-insensitive, use ~= for regex)',
                'email': 'Filter commits by author email (case-insensitive, use ~= for regex)',
                'message': 'Filter commits by message (use ~= for regex matching)',
                'hash': 'Filter commits by hash prefix',
            },
            'notes': [
                'Requires pygit2: pip install reveal-cli[git]',
                'Read-only inspection (no write operations)',
                'Supports all Git references: commit hash, branch, tag, HEAD~N, etc.',
                'Use @ for ref specification: git://path@ref',
                'Use ? for query parameters: git://path?type=history',
                'Overview (git://.) shows 10 most recent items per category',
                'Use ?limit=N on history/element queries for more results',
                'Commit filtering: Use =, ~=, >, <, >=, <=, != operators',
                'Multiple filters use AND logic: ?author=John&message~=bug',
            ],
            'see_also': [
                'reveal help://diff - Compare two files or directories',
                'reveal help://ast - Query code structure by complexity/size',
                'reveal help://stats - Analyze codebase metrics and hotspots',
            ]
        }

    # Private implementation methods

    def _get_repository_overview(self, repo: 'pygit2.Repository') -> Dict[str, Any]:
        """Generate repository overview structure."""
        head_info = self._get_head_info(repo)
        branches = self._list_branches(repo)
        tags = self._list_tags(repo)
        recent_commits = self._get_recent_commits(repo, limit=10)

        return {
            'contract_version': '1.0',
            'type': 'git_repository',
            'source': repo.workdir or repo.path,
            'source_type': 'directory',
            'path': repo.workdir or repo.path,
            'head': head_info,
            'branches': {
                'count': len(list(repo.branches.local)),
                'recent': branches[:10],
            },
            'tags': {
                'count': len([ref for ref in repo.references if ref.startswith('refs/tags/')]),
                'recent': tags[:10],
            },
            'commits': {
                'recent': recent_commits,
            },
            'stats': {
                'is_bare': repo.is_bare,
                'is_empty': repo.is_empty,
                'head_detached': repo.head_is_detached if not repo.is_empty else False,
            }
        }

    def _get_ref_structure(self, repo: 'pygit2.Repository') -> Dict[str, Any]:
        """Get structure for specific ref (commit/branch/tag)."""
        try:
            obj = repo.revparse_single(self.ref)

            # If it's a tag, peel to the commit
            while hasattr(obj, 'peel') and not isinstance(obj, pygit2.Commit):
                obj = obj.peel(pygit2.Commit)  # type: ignore[assignment]

            if isinstance(obj, pygit2.Commit):
                commit_obj = cast('pygit2.Commit', obj)
                # Get commit history from this point
                limit = int(self.query.get('limit', 20))
                commits = self._get_commit_history(repo, commit_obj, limit=limit)

                return {
                    'contract_version': '1.0',
                    'type': 'git_ref',
                    'source': f"{repo.workdir or repo.path}@{self.ref}",
                    'source_type': 'directory',
                    'ref': self.ref,
                    'commit': self._format_commit(commit_obj, detailed=True),
                    'history': commits,
                }
            else:
                raise ValueError(f"Cannot resolve ref to commit: {self.ref}")

        except (KeyError, pygit2.GitError) as e:
            raise ValueError(f"Invalid ref: {self.ref}") from e

    def _get_file_at_ref(self, repo: 'pygit2.Repository') -> Dict[str, Any]:
        """Get file contents at specific ref."""
        try:
            # Resolve the ref to a commit
            obj = repo.revparse_single(self.ref)
            while hasattr(obj, 'peel') and not isinstance(obj, pygit2.Commit):
                obj = obj.peel(pygit2.Commit)  # type: ignore[assignment]

            if not isinstance(obj, pygit2.Commit):
                raise ValueError(f"Cannot resolve ref to commit: {self.ref}")

            commit = cast('pygit2.Commit', obj)

            # Navigate to the file in the tree
            tree = commit.tree
            entry = tree[self.subpath]

            if entry.type_str == 'blob':
                blob = cast('pygit2.Blob', repo[entry.id])
                content = blob.data.decode('utf-8', errors='replace')

                return {
                    'contract_version': '1.0',
                    'type': 'git_file',
                    'source': f"{self.subpath}@{self.ref}",
                    'source_type': 'file',
                    'path': self.subpath,
                    'ref': self.ref,
                    'commit': str(commit.id)[:7],
                    'size': blob.size,
                    'content': content,
                    'lines': len(content.splitlines()),
                }
            else:
                raise ValueError(f"Path is not a file: {self.subpath}")

        except (KeyError, pygit2.GitError) as e:
            raise ValueError(f"File not found at {self.ref}: {self.subpath}") from e

    def _get_file_history(self, repo: 'pygit2.Repository') -> Dict[str, Any]:
        """Get commit history for a specific file."""
        try:
            limit = int(self.query.get('limit', 50))
            commits = []

            # Start from HEAD or specified ref
            obj = repo.revparse_single(self.ref)
            while hasattr(obj, 'peel') and not isinstance(obj, pygit2.Commit):
                obj = obj.peel(pygit2.Commit)  # type: ignore[assignment]

            commit = cast('pygit2.Commit', obj)

            # Walk commit history
            walker = repo.walk(commit.id, pygit2.GIT_SORT_TIME)  # type: ignore[arg-type]

            for commit in walker:
                # Check if this commit touched the file
                if self._commit_touches_file(repo, commit, self.subpath):
                    commit_dict = self._format_commit(commit)
                    # Apply query filters
                    if self._matches_all_filters(commit_dict):
                        commits.append(commit_dict)

                        # Legacy limit parameter support (for backward compatibility)
                        # Note: Prefer using ?limit=N in query string for result control
                        if len(commits) >= limit:
                            break

            # Apply result control (sort, limit, offset) from query params
            from ...utils.query import apply_result_control
            total_matches = len(commits)
            controlled_commits = apply_result_control(commits, self.result_control)

            return {
                'contract_version': '1.0',
                'type': 'git_file_history',
                'source': f"{self.subpath}@{self.ref}",
                'source_type': 'file',
                'path': self.subpath,
                'ref': self.ref,
                'commits': controlled_commits,
                'count': len(controlled_commits),
                'total_matches': total_matches if total_matches != len(controlled_commits) else None,
            }

        except (KeyError, pygit2.GitError) as e:
            raise ValueError(f"Failed to get file history: {self.subpath}") from e

    def _get_file_blame(self, repo: 'pygit2.Repository') -> Dict[str, Any]:
        """Get blame information for a file or specific element."""
        try:
            # Resolve ref to commit
            obj = repo.revparse_single(self.ref)
            while hasattr(obj, 'peel') and not isinstance(obj, pygit2.Commit):
                obj = obj.peel(pygit2.Commit)  # type: ignore[assignment]

            commit = cast('pygit2.Commit', obj)

            # Get blame for the file
            blame = repo.blame(self.subpath, newest_commit=commit.id)

            # Get file contents to include with blame
            tree = commit.tree
            entry = tree[self.subpath]
            blob = cast('pygit2.Blob', repo[entry.id])
            lines = blob.data.decode('utf-8', errors='replace').splitlines()

            # Format blame hunks
            hunks: List[Dict[str, Any]] = []
            for hunk in blame:
                commit_obj = cast('pygit2.Commit', repo[hunk.final_commit_id])
                committer = hunk.final_committer
                if not committer:
                    continue
                hunks.append({
                    'lines': {
                        'start': hunk.final_start_line_number,
                        'count': hunk.lines_in_hunk,
                    },
                    'commit': {
                        'hash': str(hunk.final_commit_id)[:7],
                        'author': committer.name,
                        'email': committer.email,
                        'date': datetime.fromtimestamp(committer.time).strftime('%Y-%m-%d %H:%M:%S'),
                        'message': commit_obj.message.split('\n')[0],
                    },
                })

            # Check if semantic blame (element-specific) is requested
            element_name = self.query.get('element')
            element_info = None
            if element_name:
                # Get line range for the element
                element_range = self._get_element_line_range(element_name)
                if element_range:
                    element_info = {
                        'name': element_name,
                        'line_start': element_range['line'],
                        'line_end': element_range['line_end'],
                    }
                    # Filter hunks to only those within the element's range
                    filtered_hunks: List[Dict[str, Any]] = []
                    for hunk_dict in hunks:
                        hunk_start = hunk_dict['lines']['start']
                        hunk_end = hunk_start + hunk_dict['lines']['count'] - 1
                        # Check if hunk overlaps with element range
                        if (hunk_start <= element_range['line_end'] and
                            hunk_end >= element_range['line']):
                            filtered_hunks.append(hunk_dict)
                    hunks = filtered_hunks
                else:
                    # Element was requested but not found - inform user
                    print(f"Note: Element '{element_name}' not found in {self.subpath}, showing full file blame", file=sys.stderr)

            # Check if detail mode is requested
            detail_mode = self.query.get('detail') == 'full'

            result = {
                'contract_version': '1.0',
                'type': 'git_file_blame',
                'source': f"{self.subpath}@{self.ref}",
                'source_type': 'file',
                'path': self.subpath,
                'ref': self.ref,
                'commit': str(commit.id)[:7],
                'lines': len(lines),
                'hunks': hunks,
                'file_content': lines,
                'detail': detail_mode,
            }

            if element_info:
                result['element'] = element_info

            return result

        except (KeyError, pygit2.GitError) as e:
            raise ValueError(f"Failed to get file blame: {self.subpath}") from e

    def _get_element_line_range(self, element_name: str) -> Optional[Dict[str, int]]:
        """Get line range for a specific element (function/class) in the file."""
        try:
            # Use reveal's registry to analyze the file
            from reveal.registry import get_analyzer

            # Build absolute path if needed
            if self.path and self.path != '.':
                file_path = os.path.join(self.path, self.subpath)
            else:
                file_path = self.subpath

            # Make path absolute for analyzer
            if not os.path.isabs(file_path):
                file_path = os.path.abspath(file_path)

            analyzer_class = get_analyzer(file_path)
            if not analyzer_class:
                return None

            analyzer = analyzer_class(file_path)
            structure = analyzer.get_structure()

            # Search for the element in functions and classes
            for func in structure.get('functions', []):
                if func.get('name') == element_name:
                    return {'line': func['line'], 'line_end': func.get('line_end', func['line'])}

            for cls in structure.get('classes', []):
                if cls.get('name') == element_name:
                    return {'line': cls['line'], 'line_end': cls.get('line_end', cls['line'])}

            return None

        except Exception as e:
            # Log error for debugging but don't fail the whole blame operation
            print(f"Warning: Failed to get element range: {e}", file=sys.stderr)
            return None

    def _commit_touches_file(self, repo: 'pygit2.Repository',
                            commit: 'pygit2.Commit', filepath: str) -> bool:
        """Check if a commit modified a specific file."""
        try:
            # Get file at this commit
            tree = commit.tree
            try:
                entry = tree[filepath]
                current_oid = entry.id
            except KeyError:
                # File doesn't exist in this commit
                return False

            # Check parents
            if not commit.parents:
                # Initial commit - file exists, so it was added
                return True

            # Check if file changed from any parent
            for parent in commit.parents:
                try:
                    parent_tree = parent.tree
                    parent_entry = parent_tree[filepath]
                    parent_oid = parent_entry.id

                    # If OID changed, file was modified
                    if current_oid != parent_oid:
                        return True
                except KeyError:
                    # File didn't exist in parent - it was added
                    return True

            return False

        except Exception:
            return False

    def _get_head_info(self, repo: 'pygit2.Repository') -> Dict[str, Any]:
        """Get HEAD information."""
        if repo.is_empty or repo.head_is_unborn:
            return {'branch': None, 'commit': None, 'detached': False}

        try:
            return {
                'branch': repo.head.shorthand if not repo.head_is_detached else None,
                'commit': str(repo.head.target)[:7],
                'detached': repo.head_is_detached,
            }
        except Exception:
            return {'branch': None, 'commit': None, 'detached': False}

    def _list_branches(self, repo: 'pygit2.Repository', limit: int = 20) -> List[Dict[str, Any]]:
        """List repository branches."""
        branches = []

        try:
            for branch_name in repo.branches.local:
                try:
                    branch = repo.branches.get(branch_name)
                    if not branch or not branch.target:
                        continue

                    commit = cast('pygit2.Commit', repo[branch.target])
                    branches.append({
                        'name': branch_name,
                        'commit': str(commit.id)[:7],
                        'message': commit.message.split('\n')[0][:80],
                        'author': commit.author.name,
                        'date': datetime.fromtimestamp(commit.commit_time).strftime('%Y-%m-%d'),
                        'timestamp': commit.commit_time,
                    })
                except (KeyError, pygit2.GitError):
                    continue
        except Exception:
            pass

        return sorted(branches, key=lambda b: cast(int, b.get('timestamp', 0)), reverse=True)[:limit]

    def _list_tags(self, repo: 'pygit2.Repository', limit: int = 20) -> List[Dict[str, Any]]:
        """List repository tags."""
        tags = []

        try:
            for ref_name in repo.references:
                if not ref_name.startswith('refs/tags/'):
                    continue

                try:
                    ref = repo.references.get(ref_name)
                    if not ref:
                        continue

                    tag_name = ref_name.replace('refs/tags/', '')
                    target = repo[ref.target]

                    # Peel to commit
                    while hasattr(target, 'peel') and not isinstance(target, pygit2.Commit):
                        target = target.peel(pygit2.Commit)  # type: ignore[assignment]

                    if isinstance(target, pygit2.Commit):
                        commit_target = cast('pygit2.Commit', target)
                        tags.append({
                            'name': tag_name,
                            'commit': str(commit_target.id)[:7],
                            'message': commit_target.message.split('\n')[0][:80],
                            'date': datetime.fromtimestamp(commit_target.commit_time).strftime('%Y-%m-%d'),
                            'timestamp': commit_target.commit_time,
                        })
                except (KeyError, pygit2.GitError, AttributeError):
                    continue
        except Exception:
            pass

        return sorted(tags, key=lambda t: cast(int, t.get('timestamp', 0)), reverse=True)[:limit]

    def _get_recent_commits(self, repo: 'pygit2.Repository', limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent commits from HEAD."""
        commits: List[Dict[str, Any]] = []

        try:
            if repo.is_empty:
                return commits

            walker = repo.walk(repo.head.target, pygit2.GIT_SORT_TIME)  # type: ignore[arg-type]

            for commit in walker:
                commit_dict = self._format_commit(commit)
                # Apply query filters
                if self._matches_all_filters(commit_dict):
                    commits.append(commit_dict)
                    # Legacy limit for backward compatibility
                    if len(commits) >= limit:
                        break
        except Exception:
            pass

        # Apply result control if specified in query
        if self.result_control.limit or self.result_control.sort_field or self.result_control.offset:
            from ...utils.query import apply_result_control
            commits = apply_result_control(commits, self.result_control)

        return commits

    def _get_commit_history(self, repo: 'pygit2.Repository',
                           start_commit: 'pygit2.Commit', limit: int = 20) -> List[Dict[str, Any]]:
        """Get commit history from a starting commit."""
        commits = []

        try:
            walker = repo.walk(start_commit.id, pygit2.GIT_SORT_TIME)  # type: ignore[arg-type]

            for commit in walker:
                commit_dict = self._format_commit(commit)
                # Apply query filters
                if self._matches_all_filters(commit_dict):
                    commits.append(commit_dict)
                    # Legacy limit for backward compatibility
                    if len(commits) >= limit:
                        break
        except Exception:
            pass

        # Apply result control if specified in query
        if self.result_control.limit or self.result_control.sort_field or self.result_control.offset:
            from ...utils.query import apply_result_control
            commits = apply_result_control(commits, self.result_control)

        return commits

    def _compare(self, field_value: Any, operator: str, target_value: Union[bool, int, float, str]) -> bool:
        """Compare field value against target using operator.

        Uses unified compare_values() from query.py to eliminate duplication.

        Args:
            field_value: Value from commit dict
            operator: Comparison operator (=, >, <, >=, <=, !=, ~=, ..)
            target_value: Target value to compare against

        Returns:
            True if comparison passes, False otherwise
        """
        return compare_values(
            field_value,
            operator,
            target_value,
            options={
                'allow_list_any': False,  # Git commits don't have list fields
                'case_sensitive': False,  # Author/email/message searches case-insensitive
                'coerce_numeric': True,   # For timestamp comparisons
                'none_matches_not_equal': True
            }
        )

    def _matches_all_filters(self, commit_dict: Dict[str, Any]) -> bool:
        """Check if commit matches all query filters.

        Args:
            commit_dict: Formatted commit dict from _format_commit()

        Returns:
            True if matches all filters, False otherwise
        """
        if not self.query_filters:
            return True

        for qf in self.query_filters:
            # Get field value from commit dict
            field_value = commit_dict.get(qf.field)
            if not self._compare(field_value, qf.op, qf.value):
                return False

        return True

    def _format_commit(self, commit: 'pygit2.Commit', detailed: bool = False) -> Dict[str, Any]:
        """Format commit information."""
        basic_info = {
            'hash': str(commit.id)[:7],
            'author': commit.author.name,
            'email': commit.author.email,
            'date': datetime.fromtimestamp(commit.commit_time).strftime('%Y-%m-%d %H:%M:%S'),
            'timestamp': commit.commit_time,
            'message': commit.message.split('\n')[0][:100],
        }

        if detailed:
            basic_info.update({
                'full_hash': str(commit.id),
                'full_message': commit.message,
                'parents': [str(p.id)[:7] for p in commit.parents],
                'committer': commit.committer.name,
                'committer_email': commit.committer.email,
            })

        return basic_info

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about the resource."""
        try:
            repo = self._open_repository()
            return {
                'type': 'git_repository',
                'path': repo.workdir or repo.path,
                'adapter': 'git',
            }
        except Exception:
            return {
                'type': 'git_repository',
                'adapter': 'git',
            }
