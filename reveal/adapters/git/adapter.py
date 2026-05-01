"""Git repository inspection adapter.

Progressive disclosure for Git repositories with token-efficient output.
"""

import os

from typing import Dict, Any, Optional

from ..base import ResourceAdapter, register_adapter, register_renderer
from ...utils.query import (
    parse_query_filters,
    parse_query_params,
    parse_result_control,
    ResultControl
)

# Import modular components
from .renderer import GitRenderer
from . import refs, commits, files, queries

_SCHEMA_QUERY_PARAMS = {
    'type': {'type': 'string', 'description': 'Query type for file operations', 'values': ['history', 'blame'], 'examples': ['?type=history', '?type=blame']},
    'detail': {'type': 'string', 'description': 'Detail level for blame', 'values': ['full', 'summary'], 'examples': ['?type=blame&detail=full']},
    'element': {'type': 'string', 'description': 'Semantic element for blame (function/class name)', 'examples': ['?type=blame&element=load_config']},
    'author': {'type': 'string', 'description': 'Filter commits by author name (case-insensitive)', 'examples': ['?author=John', '?author~=john']},
    'email': {'type': 'string', 'description': 'Filter commits by author email (case-insensitive)', 'examples': ['?email=john@example.com', '?email~=@example.com']},
    'message': {'type': 'string', 'description': 'Filter commits by message (supports regex with ~=)', 'examples': ['?message~=bug', '?message=Initial commit']},
    'hash': {'type': 'string', 'description': 'Filter commits by hash prefix', 'examples': ['?hash=a1b2c3d']},
    'ref': {'type': 'string', 'description': 'Override starting ref — alias for @ref in the URI (branch, tag, or commit)', 'examples': ['?type=history&ref=v0.63.0', '?ref=main']},
}

def _git_output_type(type_name: str, description: str, extra_props: dict) -> dict:
    base = {
        'contract_version': {'type': 'string'},
        'type': {'type': 'string', 'const': type_name},
        'source': {'type': 'string'},
        'source_type': {'type': 'string'},
    }
    base.update(extra_props)
    return {'type': type_name, 'description': description, 'schema': {'type': 'object', 'properties': base}}

_SCHEMA_OUTPUT_TYPES = [
    _git_output_type('git_repository', 'Repository overview with branches, tags, and recent commits', {
        'source_type': {'type': 'string', 'const': 'repository'},
        'path': {'type': 'string'}, 'head': {'type': 'object'},
        'branches': {'type': 'object'}, 'tags': {'type': 'object'}, 'commits': {'type': 'object'}
    }),
    _git_output_type('git_ref', 'Branch/tag/commit history', {
        'ref': {'type': 'string'}, 'commit': {'type': 'object'}, 'history': {'type': 'array'}
    }),
    _git_output_type('git_file', 'File contents at specific ref', {
        'source_type': {'type': 'string', 'const': 'file'},
        'path': {'type': 'string'}, 'ref': {'type': 'string'}, 'commit': {'type': 'string'},
        'size': {'type': 'integer'}, 'lines': {'type': 'integer'}, 'content': {'type': 'string'}
    }),
    _git_output_type('git_file_history', 'File commit history', {
        'path': {'type': 'string'}, 'ref': {'type': 'string'},
        'count': {'type': 'integer'}, 'commits': {'type': 'array'}
    }),
    _git_output_type('git_file_blame', 'File blame with author attribution', {
        'path': {'type': 'string'}, 'ref': {'type': 'string'},
        'lines': {'type': 'integer'}, 'element': {'type': ['string', 'null']},
        'contributors': {'type': 'array'}, 'hunks': {'type': 'array'}
    }),
]

_SCHEMA_EXAMPLE_QUERIES = [
    {'uri': 'git://.', 'description': 'Repository overview (branches, tags, commits)', 'output_type': 'git_repository'},
    {'uri': 'git://.@main', 'description': 'Branch/commit history', 'ref': 'main', 'output_type': 'git_ref'},
    {'uri': 'git://.@abc1234', 'description': 'Specific commit details', 'ref': 'abc1234', 'output_type': 'git_ref'},
    {'uri': 'git://src/app.py@v1.0', 'description': 'File contents at tag', 'ref': 'v1.0', 'output_type': 'git_file'},
    {'uri': 'git://src/app.py?type=history', 'description': 'File commit history (50 commits)', 'query_param': '?type=history', 'output_type': 'git_file_history'},
    {'uri': 'git://src/app.py?type=blame', 'description': 'File blame summary (contributors + key hunks)', 'query_param': '?type=blame', 'output_type': 'git_file_blame'},
    {'uri': 'git://src/app.py?type=blame&detail=full', 'description': 'File blame detailed (line-by-line)', 'query_param': '?type=blame&detail=full', 'output_type': 'git_file_blame'},
    {'uri': 'git://src/app.py?type=blame&element=load_config', 'description': 'Semantic blame (who wrote this function)', 'query_param': '?type=blame&element=load_config', 'output_type': 'git_file_blame'},
]

_SCHEMA_NOTES = [
    'Requires pygit2 library (pip install pygit2)',
    'Supports @ syntax for refs (branches, tags, commits)',
    'Query params for file-level operations (history, blame)',
    'Semantic blame works with Python functions/classes'
]


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

    BUDGET_LIST_FIELD = 'commits'

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
            query = parse_query_params(query_string)

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
            elif k in ['type', 'detail', 'element', 'ignore', 'raw', 'context']:
                continue
            # ?ref= overrides the starting ref (alias for @ref in the URI)
            elif k == 'ref':
                self.ref = v
            # ?since=YYYY-MM-DD — ergonomic alias for date>=YYYY-MM-DD
            elif k == 'since':
                filter_parts.append(f"date>={v}")
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
            query = parse_query_params(query_string)

        # Extract ref (@branch or @tag or @commit)
        if '@' in resource:
            resource, ref = resource.rsplit('@', 1)

        # What's left is path or subpath
        # Logic:
        #   "."             → repo root at CWD (bare overview)
        #   "/abs/repo"     → repo root at absolute path
        #   "../other-repo" → repo root at relative path (no file extension heuristic)
        #   "./file.py"     → file path relative to CWD (strip leading ./)
        #   "path/file.py"  → file path relative to CWD
        if resource:
            if resource in ('.', './'):
                path = resource
                subpath = None
            elif resource.startswith('./'):
                # "./path/to/file.py" — a file path written with explicit ./ prefix
                path = '.'
                subpath = resource[2:]
            elif resource.startswith('/') or os.path.isabs(resource):
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
            # Normalize subpath to be relative to the repo root, not CWD.
            # pygit2 tree/blame APIs require repo-root-relative paths.
            # self.path and self.subpath remain CWD-relative for filesystem ops
            # (e.g. get_element_line_range reads the actual file on disk).
            git_subpath = self.subpath
            if repo.workdir:
                abs_file = os.path.abspath(os.path.join(self.path, self.subpath))
                repo_root = os.path.abspath(repo.workdir.rstrip('/\\'))
                git_subpath = os.path.relpath(abs_file, repo_root).replace(os.sep, '/')

            if query_type == 'history':
                element_name = self.query.get('element')
                if element_name:
                    touch_func = lambda repo, commit, subpath, _en=element_name: \
                        files.commit_touches_element(repo, commit, subpath, _en)
                else:
                    touch_func = files.commit_touches_file
                result = files.get_file_history(
                    repo, self.ref, git_subpath, self.query,
                    self.result_control, self.query_filters,
                    commits.format_commit,
                    lambda cd: queries.matches_all_filters(cd, self.query_filters),
                    touch_func
                )
                if element_name:
                    result['element'] = element_name
                return result
            elif query_type == 'blame':
                return files.get_file_blame(
                    repo, self.ref, git_subpath, self.query, self.path,
                    lambda en, _path, _sub: files.get_element_line_range(en, self.path, self.subpath)
                )
            elif query_type == 'diff':
                return files.get_file_diff(repo, self.ref, git_subpath, self.query)
            else:
                raw = self.query.get('raw') in ('1', 'true', 'yes')
                return files.get_file_at_ref(repo, self.ref, git_subpath, raw=raw)
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
                pass  # not a valid file path at this ref; fall through to return None
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
            'query_params': _SCHEMA_QUERY_PARAMS,
            'elements': {},
            'cli_flags': [],
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': _SCHEMA_OUTPUT_TYPES,
            'example_queries': _SCHEMA_EXAMPLE_QUERIES,
            'notes': _SCHEMA_NOTES,
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
                {'uri': 'git://src/app.py@v1.0', 'description': 'File structure at tag (functions, classes, imports)'},
                {'uri': 'git://src/app.py@v1.0?raw=1', 'description': 'File raw contents at tag'},
                {'uri': 'git://src/app.py@abc1234?type=diff', 'description': 'What this commit changed in the file (vs parent)'},
                {'uri': 'git://src/app.py@abc1234?type=diff&element=load_config', 'description': 'Diff scoped to hunks touching a named element'},
                {'uri': 'git://src/app.py@abc1234?type=diff&context=10', 'description': 'Diff with more context lines'},
                {'uri': 'git://src/app.py?type=history', 'description': 'File commit history (50 commits)'},
                {'uri': 'git://src/app.py?type=history&element=load_config', 'description': 'Element-scoped history (only commits that changed this function)'},
                {'uri': 'git://src/app.py?type=blame', 'description': 'File blame summary (contributors + key hunks)'},
                {'uri': 'git://src/app.py?type=blame&detail=full', 'description': 'File blame detailed (line-by-line)'},
                {'uri': 'git://src/app.py?type=blame&element=load_config', 'description': 'Semantic blame (who wrote this function)'},
                {'uri': 'git://src/app.py?type=blame&ignore=69b0093,f5fcac0', 'description': 'Blame suppressing noise commits (e.g. mass-formatting)'},
                {'uri': 'git://.?author=John', 'description': 'Filter commits by author name'},
                {'uri': 'git://.?message~=bug', 'description': 'Filter commits with "bug" in message (regex)'},
                {'uri': 'git://.?author=John&message~=fix', 'description': 'Filter by author AND message'},
                {'uri': 'git://src/app.py?type=history&date>2026-01-01', 'description': 'File history since a date (ISO format, operator form)'},
                {'uri': 'git://src/app.py?type=history&since=2026-01-01', 'description': 'File history since a date (since= alias, equivalent)'},
                {'uri': 'git://src/app.py?type=history&since=2026-01-01&author=John', 'description': 'History since date AND by author'},
            ],
            'query_parameters': {
                'type': 'Operation type: history, blame, or diff. Default (no type): structural view of file at ref.',
                'raw': 'For file-at-ref: "1" returns raw file contents instead of structural view',
                'detail': 'For blame: "full" shows line-by-line (default is summary)',
                'element': 'For blame/diff/history: function/class name to scope output to that element',
                'ignore': 'For blame: comma-separated commit hash prefixes to suppress (e.g. ignore=69b0093,f5fcac0)',
                'context': 'For diff: number of context lines (default 3)',
                'limit': 'Limit number of results (default: 50 for history, 20 for refs)',
                'author': 'Filter commits by author name (case-insensitive, use ~= for regex)',
                'email': 'Filter commits by author email (case-insensitive, use ~= for regex)',
                'message': 'Filter commits by message (use ~= for regex matching)',
                'hash': 'Filter commits by hash prefix',
                'date': 'Filter commits by date — supports >, <, >=, <= with ISO date string (e.g. date>2026-01-01). Use since=YYYY-MM-DD as an ergonomic alias for date>=YYYY-MM-DD.',
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
                '~= uses substring regex match (e.g. ?message~=fix matches "fixes", "prefix-fix"). Use ?message~=\\bfix\\b for word-boundary match.',
                'For file-scoped history, use: reveal \'git://path/to/file.py?type=history\' (not --log flag)',
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
