"""Git repository inspection adapter.

Progressive disclosure for Git repositories with token-efficient output.
"""

from typing import Dict, Any, Optional, cast

from ..base import ResourceAdapter, register_adapter, register_renderer
from ...utils.query import (
    parse_query_filters,
    parse_result_control,
    ResultControl
)

# Import modular components
from .renderer import GitRenderer
from . import refs, commits, files, queries


# Check if pygit2 is available
try:
    import pygit2
    PYGIT2_AVAILABLE = True
except ImportError:
    PYGIT2_AVAILABLE = False
    pygit2 = None  # type: ignore[assignment]


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
                return files.get_file_history(
                    repo, self.ref, self.subpath, self.query,
                    self.result_control, self.query_filters,
                    commits.format_commit,
                    lambda cd: queries.matches_all_filters(cd, self.query_filters),
                    files.commit_touches_file
                )
            elif query_type == 'blame':
                return files.get_file_blame(
                    repo, self.ref, self.subpath, self.query, self.path,
                    lambda en: files.get_element_line_range(en, self.path, self.subpath)
                )
            else:
                return files.get_file_at_ref(repo, self.ref, self.subpath)
        elif self.ref != 'HEAD' or query_type:
            return refs.get_ref_structure(
                repo, self.ref, self.query, self.query_filters,
                self.result_control,
                commits.format_commit,
                lambda cd: queries.matches_all_filters(cd, self.query_filters),
                lambda repo, start_commit, limit: commits.get_commit_history(
                    repo, start_commit, limit,
                    commits.format_commit,
                    lambda cd: queries.matches_all_filters(cd, self.query_filters),
                    self.result_control,
                    self.query_filters
                )
            )
        else:
            return commits.get_repository_overview(
                repo,
                refs.get_head_info,
                refs.list_branches,
                refs.list_tags,
                lambda repo, limit: commits.get_recent_commits(
                    repo, limit,
                    commits.format_commit,
                    lambda cd: queries.matches_all_filters(cd, self.query_filters),
                    self.result_control,
                    self.query_filters
                )
            )

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
                return commits.format_commit(commit, detailed=True)
        except (KeyError, pygit2.GitError):
            pass

        # Try as file path at current ref
        if '/' in element_name or '.' in element_name:
            old_subpath = self.subpath
            self.subpath = element_name
            try:
                result = files.get_file_at_ref(repo, self.ref, self.subpath)
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
