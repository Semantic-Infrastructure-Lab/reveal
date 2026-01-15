"""Git repository inspection adapter.

Progressive disclosure for Git repositories with token-efficient output.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from ..base import ResourceAdapter, register_adapter


# Check if pygit2 is available
try:
    import pygit2
    PYGIT2_AVAILABLE = True
except ImportError:
    PYGIT2_AVAILABLE = False
    pygit2 = None


@register_adapter('git')
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

    def __init__(self, path: str = '.', ref: Optional[str] = None,
                 subpath: Optional[str] = None, query: Optional[Dict[str, str]] = None):
        """
        Initialize Git adapter.

        Args:
            path: Repository path (default: current directory)
            ref: Git reference (commit, branch, tag, HEAD~N)
            subpath: Path within repository (file or directory)
            query: Query parameters (type=history|blame, since, author, etc.)
        """
        self.path = path
        self.ref = ref or 'HEAD'
        self.subpath = subpath
        self.query = query or {}
        self.repo = None

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
                {'uri': 'git://src/app.py?type=history', 'description': 'File commit history'},
                {'uri': 'git://src/app.py?type=blame', 'description': 'File blame (who/when/why)'},
                {'uri': 'git://.?since=1w', 'description': 'Commits from last week'},
            ],
            'query_parameters': {
                'type': 'Operation type: history (file history) or blame (line annotations)',
                'since': 'Show commits since date/time (e.g., 1w, 2026-01-01)',
                'until': 'Show commits until date',
                'author': 'Filter by author name/email',
                'limit': 'Limit number of results (default: 10 for commits, 100 for blame)',
            },
            'notes': [
                'Requires pygit2: pip install reveal-cli[git]',
                'Read-only inspection (no write operations)',
                'Supports all Git references: commit hash, branch, tag, HEAD~N, etc.',
                'Use @ for ref specification: git://path@ref',
                'Use ? for query parameters: git://path?type=history',
            ],
            'see_also': [
                'reveal help://git-guide - Comprehensive guide with examples',
                'reveal help://diff - Compare Git references',
                'reveal diff://git:file@v1 vs git:file@v2 - File comparison',
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
        """Get blame information for a file."""
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

            return {
                'type': 'file_blame',
                'path': self.subpath,
                'ref': self.ref,
                'commit': str(commit.id)[:7],
                'lines': len(lines),
                'hunks': hunks,
                'file_content': lines,
            }

        except (KeyError, pygit2.GitError) as e:
            raise ValueError(f"Failed to get file blame: {self.subpath}") from e

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
