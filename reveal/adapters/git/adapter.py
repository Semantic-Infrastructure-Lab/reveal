"""Git repository inspection adapter.

Progressive disclosure for Git repositories with token-efficient output.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from urllib.parse import parse_qs, urlparse
from ..base import ResourceAdapter, register_adapter, register_renderer


# Check if pygit2 is available
try:
    import pygit2
    PYGIT2_AVAILABLE = True
except ImportError:
    PYGIT2_AVAILABLE = False
    pygit2 = None


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

        if result_type == 'repository':
            GitRenderer._render_repository_overview(result)
        elif result_type == 'ref':
            GitRenderer._render_ref_structure(result)
        elif result_type == 'file':
            GitRenderer._render_file(result)
        elif result_type == 'file_history':
            GitRenderer._render_file_history(result)
        elif result_type == 'file_blame':
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
        # Handle backward compatibility: path= parameter takes precedence
        if path is not None:
            resource = path

        if resource is None:
            raise ValueError("Either 'resource' or 'path' parameter must be provided")

        # Handle routing.py passing query string as ref parameter
        # (routing.py Try 2 does: adapter_class(path, query))
        if ref is not None and '=' in ref and query is None:
            # ref looks like a query string, move it to query
            query_string = ref
            ref = None
            query = {}
            for param in query_string.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    query[key] = value

        # Parse resource string if it looks like a URI (has @ or is a file path)
        # This handles both "README.md@ref" and "README.md" (treated as subpath)
        if subpath is None and resource:
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

        self.repo = None

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
        query = {}

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
            ],
            'query_parameters': {
                'type': 'Operation type: history (file history) or blame (line annotations)',
                'detail': 'For blame: "full" shows line-by-line (default is summary)',
                'element': 'For blame: function/class name for semantic blame',
                'limit': 'Limit number of results (default: 50 for history, 20 for refs)',
            },
            'notes': [
                'Requires pygit2: pip install reveal-cli[git]',
                'Read-only inspection (no write operations)',
                'Supports all Git references: commit hash, branch, tag, HEAD~N, etc.',
                'Use @ for ref specification: git://path@ref',
                'Use ? for query parameters: git://path?type=history',
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
            'type': 'repository',
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
                obj = obj.peel(pygit2.Commit)

            if isinstance(obj, pygit2.Commit):
                # Get commit history from this point
                limit = int(self.query.get('limit', 20))
                commits = self._get_commit_history(repo, obj, limit=limit)

                return {
                    'type': 'ref',
                    'ref': self.ref,
                    'commit': self._format_commit(obj, detailed=True),
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
                obj = obj.peel(pygit2.Commit)

            if not isinstance(obj, pygit2.Commit):
                raise ValueError(f"Cannot resolve ref to commit: {self.ref}")

            commit = obj

            # Navigate to the file in the tree
            tree = commit.tree
            entry = tree[self.subpath]

            if entry.type_str == 'blob':
                blob = repo[entry.id]
                content = blob.data.decode('utf-8', errors='replace')

                return {
                    'type': 'file',
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
                obj = obj.peel(pygit2.Commit)

            # Walk commit history
            walker = repo.walk(obj.id, pygit2.GIT_SORT_TIME)

            for commit in walker:
                # Check if this commit touched the file
                if self._commit_touches_file(repo, commit, self.subpath):
                    commits.append(self._format_commit(commit))

                    if len(commits) >= limit:
                        break

            return {
                'type': 'file_history',
                'path': self.subpath,
                'ref': self.ref,
                'commits': commits,
                'count': len(commits),
            }

        except (KeyError, pygit2.GitError) as e:
            raise ValueError(f"Failed to get file history: {self.subpath}") from e

    def _get_file_blame(self, repo: 'pygit2.Repository') -> Dict[str, Any]:
        """Get blame information for a file or specific element."""
        try:
            # Resolve ref to commit
            obj = repo.revparse_single(self.ref)
            while hasattr(obj, 'peel') and not isinstance(obj, pygit2.Commit):
                obj = obj.peel(pygit2.Commit)

            commit = obj

            # Get blame for the file
            blame = repo.blame(self.subpath, newest_commit=commit.id)

            # Get file contents to include with blame
            tree = commit.tree
            entry = tree[self.subpath]
            blob = repo[entry.id]
            lines = blob.data.decode('utf-8', errors='replace').splitlines()

            # Format blame hunks
            hunks = []
            for hunk in blame:
                commit_obj = repo[hunk.final_commit_id]
                hunks.append({
                    'lines': {
                        'start': hunk.final_start_line_number,
                        'count': hunk.lines_in_hunk,
                    },
                    'commit': {
                        'hash': str(hunk.final_commit_id)[:7],
                        'author': hunk.final_committer.name,
                        'email': hunk.final_committer.email,
                        'date': datetime.fromtimestamp(hunk.final_committer.time).strftime('%Y-%m-%d %H:%M:%S'),
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
                    filtered_hunks = []
                    for hunk in hunks:
                        hunk_start = hunk['lines']['start']
                        hunk_end = hunk_start + hunk['lines']['count'] - 1
                        # Check if hunk overlaps with element range
                        if (hunk_start <= element_range['line_end'] and
                            hunk_end >= element_range['line']):
                            filtered_hunks.append(hunk)
                    hunks = filtered_hunks
                else:
                    # Element was requested but not found - inform user
                    print(f"Note: Element '{element_name}' not found in {self.subpath}, showing full file blame", file=sys.stderr)

            # Check if detail mode is requested
            detail_mode = self.query.get('detail') == 'full'

            result = {
                'type': 'file_blame',
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

                    commit = repo[branch.target]
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

        return sorted(branches, key=lambda b: b.get('timestamp', 0), reverse=True)[:limit]

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
                        target = target.peel(pygit2.Commit)

                    if isinstance(target, pygit2.Commit):
                        tags.append({
                            'name': tag_name,
                            'commit': str(target.id)[:7],
                            'message': target.message.split('\n')[0][:80],
                            'date': datetime.fromtimestamp(target.commit_time).strftime('%Y-%m-%d'),
                            'timestamp': target.commit_time,
                        })
                except (KeyError, pygit2.GitError, AttributeError):
                    continue
        except Exception:
            pass

        return sorted(tags, key=lambda t: t.get('timestamp', 0), reverse=True)[:limit]

    def _get_recent_commits(self, repo: 'pygit2.Repository', limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent commits from HEAD."""
        commits = []

        try:
            if repo.is_empty:
                return commits

            walker = repo.walk(repo.head.target, pygit2.GIT_SORT_TIME)

            for commit in walker:
                commits.append(self._format_commit(commit))
                if len(commits) >= limit:
                    break
        except Exception:
            pass

        return commits

    def _get_commit_history(self, repo: 'pygit2.Repository',
                           start_commit: 'pygit2.Commit', limit: int = 20) -> List[Dict[str, Any]]:
        """Get commit history from a starting commit."""
        commits = []

        try:
            walker = repo.walk(start_commit.id, pygit2.GIT_SORT_TIME)

            for commit in walker:
                commits.append(self._format_commit(commit))
                if len(commits) >= limit:
                    break
        except Exception:
            pass

        return commits

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
