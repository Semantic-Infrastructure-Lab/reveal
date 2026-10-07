"""Git repository inspection adapter.

Progressive disclosure for Git repositories with token-efficient output.
"""

import os
import sys
from pathlib import Path

from typing import Dict, Any, Optional, Tuple

from ..base import ResourceAdapter, register_adapter, register_renderer
from ...errors import NotApplicableError
from ...utils.query import (
    parse_query_filters,
    parse_query_params,
    parse_result_control,
    ResultControl
)
from ...utils.query_parser import QueryParams, mark_query_keys, peek_query_items, query_key

# Import modular components
from ...utils.path_utils import to_posix
from .renderer import GitRenderer
from . import refs, commits, files, queries

_SCHEMA_QUERY_PARAMS = {
    'type': {'type': 'string', 'description': 'Query type for file operations', 'values': ['history', 'blame', 'diff', 'ownership'], 'examples': ['?type=history', '?type=blame', '?type=ownership']},
    'merges': {'type': 'string', 'description': 'For ownership: "1" includes merge commits (excluded by default)', 'examples': ['?type=ownership&merges=1']},
    'detail': {'type': 'string', 'description': 'Detail level for blame', 'values': ['full', 'summary'], 'examples': ['?type=blame&detail=full']},
    'element': {'type': 'string', 'description': 'Semantic element (function/class name) for blame, history/log and diff', 'examples': ['?type=blame&element=load_config', '?type=history&element=load_config']},
    'context': {'type': 'integer', 'description': 'For diff: number of context lines around each hunk (default: 3)', 'examples': ['?type=diff&context=10']},
    'author': {'type': 'string', 'description': 'Filter commits by author name (case-insensitive)', 'examples': ['?author=John', '?author~=john']},
    'email': {'type': 'string', 'description': 'Filter commits by author email (case-insensitive)', 'examples': ['?email=john@example.com', '?email~=@example.com']},
    'message': {'type': 'string', 'description': 'Filter commits by message (supports regex with ~=)', 'examples': ['?message~=bug', '?message=Initial commit']},
    'hash': {'type': 'string', 'description': 'Filter commits by hash prefix', 'examples': ['?hash=a1b2c3d']},
    'date': {'type': 'string', 'description': 'Filter commits by date — supports >, <, >=, <= with ISO date string. ?since=YYYY-MM-DD is an ergonomic alias for date>=YYYY-MM-DD', 'examples': ['?date>2026-01-01']},
    'ref': {'type': 'string', 'description': 'Override starting ref — alias for @ref in the URI (branch, tag, or commit)', 'examples': ['?type=history&ref=v0.63.0', '?ref=main']},
    'bucket': {'type': 'string', 'description': 'Modifier on type=history: bucket commits into periods (commit_count + distinct author_count per period) instead of a flat list. Works on a file, directory, or the whole repo.', 'values': ['week', 'month'], 'examples': ['?type=history&bucket=month', '?type=history&bucket=week']},
    'no_merges': {'type': 'string', 'description': 'Set to "1" to exclude merge commits (commits with more than one parent)', 'examples': ['?type=history&no_merges=1']},
    'since': {'type': 'string', 'description': 'Ergonomic alias for date>=YYYY-MM-DD (rewritten into a date filter)', 'examples': ['?since=2026-01-01']},
    'until': {'type': 'string', 'description': 'Ergonomic alias for date<=YYYY-MM-DD (rewritten into a date filter)', 'examples': ['?until=2026-01-01']},
    'ignore': {'type': 'string', 'description': 'For blame: comma-separated commit hash prefixes to suppress', 'examples': ['?type=blame&ignore=69b0093,f5fcac0']},
    'raw': {'type': 'string', 'description': 'For file-at-ref: "1" returns raw file contents instead of structural view', 'examples': ['?raw=1']},
    'content~': {'type': 'string', 'description': 'Pickaxe search: only commits where the diff added or removed the given string (regex)', 'examples': ['?content~=TODO']},
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
    _git_output_type('git_file_structure', 'File structure (functions, classes, imports) at specific ref', {
        'source_type': {'type': 'string', 'const': 'file'},
        'path': {'type': 'string'}, 'ref': {'type': 'string'}, 'commit': {'type': 'string'},
        'size': {'type': 'integer'}, 'lines': {'type': 'integer'}, 'structure': {'type': 'object'}
    }),
    _git_output_type('git_file', 'File contents at specific ref (?raw=1)', {
        'source_type': {'type': 'string', 'const': 'file'},
        'path': {'type': 'string'}, 'ref': {'type': 'string'}, 'commit': {'type': 'string'},
        'size': {'type': 'integer'}, 'lines': {'type': 'integer'}, 'content': {'type': 'string'}
    }),
    _git_output_type('git_file_history', 'File commit history', {
        'path': {'type': 'string'}, 'ref': {'type': 'string'},
        'count': {'type': 'integer'}, 'commits': {'type': 'array'}
    }),
    _git_output_type('git_timeline', 'Bucketed commit/author counts over time for a file, directory, or repo', {
        'source_type': {'type': 'string', 'enum': ['file', 'directory', 'repository']},
        'path': {'type': ['string', 'null']}, 'ref': {'type': 'string'},
        'bucket': {'type': 'string', 'enum': ['week', 'month']},
        'buckets': {'type': 'array'},
        'commit_count': {'type': 'integer'}, 'distinct_author_count': {'type': 'integer'}
    }),
    _git_output_type('git_file_blame', 'File blame with author attribution', {
        'path': {'type': 'string'}, 'ref': {'type': 'string'},
        'lines': {'type': 'integer'}, 'element': {'type': ['string', 'null']},
        'contributors': {'type': 'array'}, 'hunks': {'type': 'array'}
    }),
    _git_output_type('git_ownership', 'Commit-share ownership for a file, directory, or repository', {
        'source_type': {'type': 'string', 'enum': ['file', 'directory', 'repository']},
        'path': {'type': 'string'}, 'ref': {'type': 'string'},
        'total_commits': {'type': 'integer'}, 'contributor_count': {'type': 'integer'},
        'primary_author': {'type': ['object', 'null']}, 'last_touch': {'type': ['string', 'null']},
        'authors': {'type': 'array'}
    }),
]

_SCHEMA_EXAMPLE_QUERIES = [
    {'uri': 'git://.', 'description': 'Repository overview (branches, tags, commits)', 'output_type': 'git_repository'},
    {'uri': 'git://.@main', 'description': 'Branch/commit history', 'ref': 'main', 'output_type': 'git_ref'},
    {'uri': 'git://.@abc1234', 'description': 'Specific commit details', 'ref': 'abc1234', 'output_type': 'git_ref'},
    {'uri': 'git://src/app.py@v1.0', 'description': 'File structure at tag', 'ref': 'v1.0', 'output_type': 'git_file_structure'},
    {'uri': 'git://src/app.py@v1.0?raw=1', 'description': 'File contents at tag', 'ref': 'v1.0', 'query_param': '?raw=1', 'output_type': 'git_file'},
    {'uri': 'git://src/app.py?type=history', 'description': 'File commit history (50 commits)', 'query_param': '?type=history', 'output_type': 'git_file_history'},
    {'uri': 'git://src/app.py?type=blame', 'description': 'File blame summary (contributors + key hunks)', 'query_param': '?type=blame', 'output_type': 'git_file_blame'},
    {'uri': 'git://src/app.py?type=blame&detail=full', 'description': 'File blame detailed (line-by-line)', 'query_param': '?type=blame&detail=full', 'output_type': 'git_file_blame'},
    {'uri': 'git://src/app.py?type=blame&element=load_config', 'description': 'Semantic blame (who wrote this function)', 'query_param': '?type=blame&element=load_config', 'output_type': 'git_file_blame'},
    {'uri': 'git://src/app.py?type=ownership', 'description': 'Commit-share ownership of a file (primary author, contributors, last touch)', 'query_param': '?type=ownership', 'output_type': 'git_ownership'},
    {'uri': 'git://src/?type=ownership', 'description': 'Commit-share ownership of a directory', 'query_param': '?type=ownership', 'output_type': 'git_ownership'},
    {'uri': 'git://src/app.py?type=history&bucket=month', 'description': 'Monthly commit/author counts for a file', 'query_param': '?type=history&bucket=month', 'output_type': 'git_timeline'},
    {'uri': 'git://src/?type=history&bucket=week', 'description': 'Weekly commit/author counts for a directory', 'query_param': '?type=history&bucket=week', 'output_type': 'git_timeline'},
    {'uri': 'git://.?type=history&bucket=month', 'description': 'Monthly commit/author counts for the whole repo', 'query_param': '?type=history&bucket=month', 'output_type': 'git_timeline'},
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


def _absolute_directory_scope(directory: str) -> Tuple[str, Optional[str]]:
    """``(path, subpath)`` for an absolute directory: the repository, or a directory in its work tree.

    A directory below the work-tree root becomes the work tree plus the root-relative
    subpath, so every path view (ownership, history, blame, diff, the file view) answers
    for it exactly as its relative spelling does (BACK-1654), instead of for the whole
    repository (BACK-1690). The root itself, anything inside the git dir, and a bare
    repository stay the repository. Discovery is the call ``_open_repository`` makes;
    when it finds nothing or libgit2 refuses the repository, the directory stays the
    repository path and ``_open_repository`` reports that failure.
    """
    if not PYGIT2_AVAILABLE:
        return directory, None
    try:
        git_dir = pygit2.discover_repository(directory)
        workdir = pygit2.Repository(git_dir).workdir if git_dir else None
    except (pygit2.GitError, KeyError):  # reported by _open_repository on the same discovery
        return directory, None
    if not git_dir or not workdir:
        return directory, None
    target, root = Path(directory).resolve(), Path(workdir).resolve()
    if target == root or not target.is_relative_to(root) or target.is_relative_to(Path(git_dir).resolve()):
        return directory, None
    return workdir.rstrip('/\\'), target.relative_to(root).as_posix()


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
    HELP_CLUSTER = ('Code Analysis', 'Sessions & Docs')
    QUICK_RANK = 4

    BUDGET_LIST_FIELD = ('commits', 'history')  # path views / repo and ref views (BACK-1645)
    LEGACY_INIT = False
    CLI_QUERY_FLAGS = {
        'since': 'since={value}', 'until': 'until={value}',  # BACK-1192
        'all': 'limit=1000000',  # lifts the 50-commit log default (BACK-1379)
        # BACK-1379: 'detail' is view-scoped to type=blame (_VIEW_SCOPED_PARAMS
        # below) -- --verbose is a no-op on any other type=, same as detail= itself.
        'verbose': 'detail=full',
    }

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
            # Merge parsed query with explicitly provided query; merging is not reading
            # (BACK-1537), so the merged dict keeps recording which keys a view reads.
            self.query: Dict[str, Any] = parsed['query']
            for key, value in peek_query_items(query or {}):
                self.query[key] = value
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
        self._filter_keys = []  # the user's keys behind filter_parts, for warnings

        # Routing a key is not reading it (BACK-1537): each key counts as used where it is
        # applied -- result control when a view reads the ResultControl, operational keys
        # when a view reads them, filters when parsed.
        for k, v in peek_query_items(self.query):
            # Result control parameters
            if k in ['sort', 'limit', 'offset']:
                result_control_parts.append(f"{k}={v}")
            # Operational parameters (exclude from both)
            elif k in ['type', 'detail', 'element', 'ignore', 'raw', 'context',
                       'no_merges', 'content', 'content~', 'bucket']:
                continue
            # ?ref= overrides the starting ref (alias for @ref in the URI)
            elif k == 'ref':
                self.ref = v
                mark_query_keys(self.query, k)
            # ?since=YYYY-MM-DD — ergonomic alias for date>=YYYY-MM-DD
            # ?until=YYYY-MM-DD — ergonomic alias for date<=YYYY-MM-DD (BACK-1192,
            # symmetric with ?since= above — the CLI --until flag needs a target
            # to alias into; only date>= existed before this)
            elif k in ('since', 'until'):
                filter_parts.append(f"date{'>' if k == 'since' else '<'}={v}")
                self._filter_keys.append(k)
                mark_query_keys(self.query, k)  # the filter parser records 'date'
            # Filter parameters (a key may already end with its operator: author~, date>)
            else:
                filter_parts.append(f"{k}={v}")
                self._filter_keys.append(query_key(k))

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

        # BACK-909: warn on unrecognized params (e.g. ?verbose=1, which isn't a
        # git:// param). Mixed adapter: skip filter-expression keys (author~=john,
        # date>=2026-01-01 — these carry an operator char in the raw key) and the
        # cross-cutting result-control params handled separately.
        self._warn_unknown_query_params(
            self.query,
            skip_filter_keys=True,
            extra_known_keys={'sort', 'limit', 'offset'},
        )
        self._warn_view_scoped_query_params()

    # Params only meaningful when `type=` resolves to this exact value —
    # accepted (they're in the schema) but silently inert on any other view.
    # Each names every view that reads it: ?element= is the blame target, narrows
    # history/log to the commits touching that element and diff to its hunks, so naming
    # blame alone warned "no effect" over a correct element history (BACK-1604).
    _VIEW_SCOPED_PARAMS = {
        'merges': ('ownership',),
        'detail': ('blame',),
        'element': ('blame', 'history', 'log', 'diff'),
        'context': ('diff',),
        'ignore': ('blame',),
        'bucket': ('history', 'log'),
    }

    def _warn_view_scoped_query_params(self) -> None:
        """BACK-1127: warn when a recognized param has no effect on the
        resolved view — same silent-failure shape as BACK-909's
        unknown-param warning, but for a param name that IS in the schema,
        just not for this ``type=``. Without this, a typo shouts
        (_warn_unknown_query_params) while a semantically-wrong-but-valid
        param says nothing — the signal is inverted relative to risk.
        """
        query_type = self.query.get('type')
        resolved = query_type or ('file content' if self.subpath else 'default (log)')

        # BACK-1504: on a file or directory, commit filters are applied only by
        # ?type=history; the default view shows the file at the ref and never
        # reads them, so `git://f.py?message~=fix` answered with no filter at all.
        if self.subpath and query_type not in ('history', 'log', 'ownership') and self.query_filters:
            fields = ', '.join(f"'{key}'" for key in sorted(set(self._filter_keys)))
            view = f"type={query_type}" if query_type else 'file content'
            print(
                f"⚠ Filter param(s) {fields} have no effect on git:// view '{view}' -- "
                f"add ?type=history to filter this path's commits. "
                f"Result does not reflect them.",
                file=sys.stderr,
            )

        for key, valid_types in self._VIEW_SCOPED_PARAMS.items():
            if key in self.query and query_type not in valid_types:
                applies = ', '.join(f'?type={t}' for t in valid_types)
                print(
                    f"⚠ Query param '{key}' has no effect on git:// view "
                    f"'{resolved}' — only applies to {applies}. "
                    f"Result does not reflect it.",
                    file=sys.stderr,
                )

        if query_type == 'ownership':
            if 'no_merges' in self.query:
                print(
                    "⚠ Query param 'no_merges' has no effect on git:// view "
                    "'ownership' — ownership already excludes merge commits "
                    "by default; use ?merges=1 to include them. Result does "
                    "not reflect it.",
                    file=sys.stderr,
                )
            # 'merges' is legitimately read from self.query directly by
            # get_ownership() even though _separate_query_parameters()
            # *also* routes it into query_filters (it isn't in that
            # method's operational-key exclusion list) — exclude it here
            # so a real ownership param doesn't get flagged as inert.
            inert_keys = set(self._filter_keys) - {'merges'}
            if inert_keys:
                fields = ', '.join(f"'{key}'" for key in sorted(inert_keys))
                print(
                    f"⚠ Filter param(s) {fields} have no effect on git:// "
                    f"view 'ownership' — ownership aggregates commit-share "
                    f"unfiltered. Result does not reflect them.",
                    file=sys.stderr,
                )

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
        query: Dict[str, Any] = QueryParams()

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
        #   "/abs/repo/sub" → that directory of the repo, as "sub" from inside it (BACK-1690)
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
                # An absolute *directory* is the repo when it is the work-tree root,
                # else that directory of the repo (BACK-1690). An
                # absolute *file* path must be split into repo-dir + subpath, or
                # it silently falls through to a repo overview with the file and
                # @ref ignored — which then cascades into a bogus diff:// showing
                # every function removed (BACK-417). _repo_relative_subpath
                # converts the absolute subpath back to repo-root-relative.
                if os.path.isdir(resource):
                    path, subpath = _absolute_directory_scope(resource)
                else:
                    path = os.path.dirname(resource) or os.sep
                    subpath = resource
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
            repo_path = None
            try:
                # Discover the repository from the target, not the cwd (BACK-1654)
                start = self._discovery_start()
                repo_path = pygit2.discover_repository(start)
                if not repo_path:
                    target = to_posix(os.path.normpath(os.path.join(self.path, self.subpath or '')))
                    raise NotApplicableError(f"Not a git repository: {target}")
                self.repo = pygit2.Repository(repo_path)
            except (pygit2.GitError, KeyError) as e:
                raise ValueError(self._open_failure_message(e, repo_path)) from e
        return self.repo

    def _open_failure_message(self, cause: Exception, repo_path: Optional[str]) -> str:
        """Why the repository would not open, with the fix when libgit2 refused ownership.

        libgit2 won't open a repo owned by another UID (CVE-2022-24765): a bind-mounted
        host checkout read by a container user. Its own message names the refusal but not
        the remedy, so the router's one-line error was "Failed to open repository" with
        the cause only in a traceback nobody sees (BACK-1118).
        """
        detail = str(cause) or type(cause).__name__
        message = f"Failed to open repository: {self.path}: {detail}"
        if 'not owned by current user' in detail or 'safe.directory' in detail:
            repo_dir = (repo_path or self.path).rstrip('/\\')
            if repo_dir.endswith('.git'):  # libgit2 names the .git dir; trust its worktree
                repo_dir = os.path.dirname(repo_dir)
            message += (f"\nThe repository belongs to another user. Mark it trusted with: "
                        f"git config --global --add safe.directory {to_posix(repo_dir)}")
        return message

    def _discovery_start(self) -> str:
        """Where repository discovery begins: the target's nearest existing directory.

        A relative target parses as ``path='.'`` plus a cwd-relative ``subpath``
        (``repo/src`` from the repo's parent), so discovering from ``self.path`` alone
        looked at the cwd and missed the repo the target is in (BACK-1654). A subpath
        that no longer exists on disk (a deleted file read at a ref) climbs to the
        nearest directory that does.
        """
        candidate = os.path.abspath(os.path.join(self.path, self.subpath or ''))
        while not os.path.isdir(candidate):
            parent = os.path.dirname(candidate)
            if parent == candidate:
                break
            candidate = parent
        return candidate

    def _repo_relative_subpath(self, repo: 'pygit2.Repository') -> str:
        """Convert self.subpath (CWD-relative) to a repo-root-relative path.

        pygit2 tree/blame APIs require repo-root-relative paths. Returns the
        subpath unchanged for bare repos (no workdir).
        """
        git_subpath = self.subpath
        if repo.workdir:
            abs_file = os.path.abspath(os.path.join(self.path, self.subpath))
            repo_root = os.path.abspath(repo.workdir.rstrip('/\\'))
            git_subpath = os.path.relpath(abs_file, repo_root).replace(os.sep, '/')
        return git_subpath

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
        no_merges = self.query.get('no_merges') in ('1', 'true', 'yes')
        content_pattern = self.query.get('content~') or self.query.get('content') or None

        # Ownership works on a file, a directory, or the whole repo, so it is
        # routed before the subpath/ref branching below.
        if query_type == 'ownership':
            git_subpath = self._repo_relative_subpath(repo) if self.subpath else None
            return files.get_ownership(
                repo, self.ref, git_subpath, self.query, self.result_control
            )

        if self.subpath:
            # Normalize subpath to be relative to the repo root, not CWD.
            # pygit2 tree/blame APIs require repo-root-relative paths.
            # self.path and self.subpath remain CWD-relative for filesystem ops
            # (e.g. get_element_line_range reads the actual file on disk).
            git_subpath = self._repo_relative_subpath(repo)

            # BACK-1225: 'log' (what overview:// sends for its "Recent changes"
            # section) is the same request as 'history' here -- it was never
            # recognized by this string check, so a directory subpath fell
            # through to the file-content branch below and failed with a
            # misdirected "git:// expects a file path" error blaming the
            # caller's syntax instead of this adapter's own missing alias.
            if query_type in ('history', 'log'):
                element_name = self.query.get('element')
                # subpath docstring promises "file or directory" -- only used
                # to label the result honestly (result_type/source_type); the
                # touch check itself (commit_touches_path) already handles
                # both transparently (a directory's tree entry has a content-
                # addressed oid too, same as a file's blob id -- already
                # proven by get_ownership()'s directory-scoped queries).
                subpath_is_dir = not element_name and os.path.isdir(
                    os.path.join(self.path, self.subpath))
                if element_name:
                    touch_func = lambda repo, commit, subpath, _en=element_name: \
                        files.commit_touches_element(repo, commit, subpath, _en)
                else:
                    touch_func = files.commit_touches_path

                if 'bucket' in self.query:
                    return files.get_file_timeline(
                        repo, self.ref, git_subpath, self.query,
                        commits.format_commit,
                        lambda cd: queries.matches_all_filters(cd, self.query_filters),
                        touch_func,
                    )

                result = files.get_file_history(
                    repo, self.ref, git_subpath, self.query,
                    self.result_control, self.query_filters,
                    commits.format_commit,
                    lambda cd: queries.matches_all_filters(cd, self.query_filters),
                    touch_func,
                    is_dir=subpath_is_dir,
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
        elif query_type == 'history' and 'bucket' in self.query:
            bucket = self.query.get('bucket', 'month')
            if bucket not in ('week', 'month'):
                raise ValueError(f"Invalid bucket: {bucket!r} (expected 'week' or 'month')")
            limit = int(self.query.get('limit', 20000))
            return refs.get_ref_timeline(
                repo, self.ref, bucket,
                lambda repo, start_commit, _lim=limit, _nm=no_merges: \
                    commits.get_commit_timeline(
                        repo, start_commit, _lim,
                        commits.format_commit,
                        lambda cd: queries.matches_all_filters(cd, self.query_filters),
                        no_merges=_nm,
                    )
            )
        elif self.ref != 'HEAD' or query_type:
            return refs.get_ref_structure(
                repo, self.ref, self.query, self.query_filters,
                self.result_control,
                commits.format_commit,
                lambda cd: queries.matches_all_filters(cd, self.query_filters),
                lambda repo, start_commit, limit, _nm=no_merges, _cp=content_pattern: \
                    commits.get_commit_history(
                        repo, start_commit, limit,
                        commits.format_commit,
                        lambda cd: queries.matches_all_filters(cd, self.query_filters),
                        self.result_control,
                        self.query_filters,
                        no_merges=_nm,
                        content_pattern=_cp,
                    )
            )
        else:
            return commits.get_repository_overview(
                repo,
                refs.get_head_info,
                refs.list_branches,
                refs.list_tags,
                lambda repo, limit, _nm=no_merges, _cp=content_pattern: \
                    commits.get_recent_commits(
                        repo, limit,
                        commits.format_commit,
                        lambda cd: queries.matches_all_filters(cd, self.query_filters),
                        self.result_control,
                        self.query_filters,
                        no_merges=_nm,
                        content_pattern=_cp,
                    ),
                recent_limit=int(self.query.get('limit', 10)),
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
            except ValueError:
                pass  # get_file_at_ref's "no such file at this ref"; fall through to return None
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
                {'uri': 'git://src/app.py?type=blame&element=process_payment&ignore=69b0093', 'description': 'Who really wrote this function, excluding a mass-format commit'},
                {'uri': 'git://src/app.py?type=ownership', 'description': 'Commit-share ownership of a file (primary author, contributor count, last touch)'},
                {'uri': 'git://src/?type=ownership', 'description': 'Commit-share ownership of a directory (aggregate over all files beneath it)'},
                {'uri': 'git://.?type=ownership', 'description': 'Commit-share ownership of the whole repository'},
                {'uri': 'git://src/app.py?type=ownership&merges=1', 'description': 'Ownership including merge commits (excluded by default)'},
                {'uri': 'git://.?author=John', 'description': 'Filter commits by author name'},
                {'uri': 'git://.?message~=bug', 'description': 'Filter commits with "bug" in message (regex)'},
                {'uri': 'git://.?author=John&message~=fix', 'description': 'Filter by author AND message'},
                {'uri': 'git://src/app.py?type=history&date>2026-01-01', 'description': 'File history since a date (ISO format, operator form)'},
                {'uri': 'git://src/app.py?type=history&since=2026-01-01', 'description': 'File history since a date (since= alias, equivalent)'},
                {'uri': 'git://src/app.py?type=history&since=2026-01-01&author=John', 'description': 'History since date AND by author'},
                {'uri': 'git://src/app.py?type=history&content~=MyClass', 'description': 'Commits where the diff added or removed "MyClass" (pickaxe search)'},
                {'uri': 'git://.?content~=SmLogs', 'description': 'Repo-wide: find any commit whose diff contains "SmLogs"'},
                {'uri': 'git://src/app.py?type=history&no_merges=1', 'description': 'File history excluding merge commits'},
                {'uri': 'git://.@main?no_merges=1', 'description': 'Branch history without merge noise'},
                {'uri': 'git://src/app.py?type=history&bucket=month', 'description': 'Monthly commit/author counts for a file (is activity trending up or down?)'},
                {'uri': 'git://src/?type=history&bucket=week', 'description': 'Weekly commit/author counts for a directory'},
                {'uri': 'git://.?type=history&bucket=month', 'description': 'Monthly commit/author counts for the whole repo'},
                {'uri': 'git://.?type=history&bucket=month&author=John', 'description': 'Monthly timeline filtered to one author'},
            ],
            'query_parameters': {
                'type': 'Operation type: history, blame, diff, or ownership. Default (no type): structural view of file at ref.',
                'bucket': 'Modifier on type=history: "week" or "month" — buckets commits into periods (commit_count + distinct author_count per period) instead of returning a flat list. Works on a file, directory, or the whole repo. Rendering (bars, charts) is consumer-side.',
                'merges': 'For ownership: "1" includes merge commits (excluded by default, since merges rarely represent authorship).',
                'raw': 'For file-at-ref: "1" returns raw file contents instead of structural view',
                'detail': 'For blame: "full" shows line-by-line (default is summary)',
                'element': 'For blame/diff/history: function/class name to scope output to that element. For ?type=history, runs the analyzer at each commit — use ?limit=N on files with deep history.',
                'ignore': 'For blame: comma-separated commit hash prefixes to suppress (e.g. ignore=69b0093,f5fcac0). Any prefix length works — 4–7 chars is typical.',
                'context': 'For diff: number of context lines (default 3)',
                'limit': 'Limit number of results (default: 10 recent commits, branches and tags for the repository view, 50 for history, 20 for refs, 20000 for bucket= timelines — timelines need the full matching range, not a short page). A cut history says so: "showing 50 of 51+" (at least 51).',
                'sort': 'Order commits by a field: date, author, message (-field for descending). History is newest first without it; a sort reads all matching history before ?limit cuts it.',
                'author': 'Filter commits by author name (case-insensitive, use ~= for regex)',
                'email': 'Filter commits by author email (case-insensitive, use ~= for regex)',
                'message': 'Filter commits by message (use ~= for regex matching)',
                'hash': 'Filter commits by hash prefix',
                'date': 'Filter commits by date — supports >, <, >=, <= with ISO date string (e.g. date>2026-01-01). Use since=YYYY-MM-DD as an ergonomic alias for date>=YYYY-MM-DD.',
                'content~': 'Pickaxe search: only commits where the diff added or removed the given string. Works on file-scoped history (?type=history) and repo-wide (git://.?content~=X). Independent of commit message wording.',
                'no_merges': 'Set to 1 to exclude merge commits (commits with more than one parent). Useful for repos with noisy merge-commit messages.',
            },
            'notes': [
                'Requires pygit2: pip install reveal-cli[git]',
                'Read-only inspection (no write operations)',
                'Supports all Git references: commit hash, branch, tag, HEAD~N, etc.',
                'Use @ for ref specification: git://path@ref',
                'Use ? for query parameters: git://path?type=history',
                'Overview (git://.) shows 10 most recent items per category',
                'Use ?limit=N on history/element queries for more results (element history default: 50; consider ?limit=20 for deep histories)',
                'Commit filtering: Use =, ~=, >, <, >=, <=, != operators',
                'Multiple filters use AND logic: ?author=John&message~=bug',
                '~= uses substring regex match (e.g. ?message~=fix matches "fixes", "prefix-fix"). Use ?message~=\\bfix\\b for word-boundary match.',
                'For file-scoped history, use: reveal \'git://path/to/file.py?type=history\' (not --log flag)',
            ],
            'see_also': [
                'reveal help://ast - Query code structure by complexity/size',
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
        except (OSError, ValueError, pygit2.GitError):
            return {
                'type': 'git_repository',
                'adapter': 'git',
            }
