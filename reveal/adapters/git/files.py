"""Git file operations: history, blame, and content retrieval."""

import os
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional, cast, TYPE_CHECKING

if TYPE_CHECKING:
    import pygit2


def get_file_at_ref(
    repo: 'pygit2.Repository',
    ref: str,
    subpath: str
) -> Dict[str, Any]:
    """Get file contents at specific ref."""
    import pygit2

    try:
        # Resolve the ref to a commit
        obj = repo.revparse_single(ref)
        while hasattr(obj, 'peel') and not isinstance(obj, pygit2.Commit):
            obj = obj.peel(pygit2.Commit)  # type: ignore[assignment]

        if not isinstance(obj, pygit2.Commit):
            raise ValueError(f"Cannot resolve ref to commit: {ref}")

        commit = cast('pygit2.Commit', obj)

        # Navigate to the file in the tree
        tree = commit.tree
        entry = tree[subpath]

        if entry.type_str == 'blob':
            blob = cast('pygit2.Blob', repo[entry.id])
            content = blob.data.decode('utf-8', errors='replace')

            return {
                'contract_version': '1.0',
                'type': 'git_file',
                'source': f"{subpath}@{ref}",
                'source_type': 'file',
                'path': subpath,
                'ref': ref,
                'commit': str(commit.id)[:7],
                'size': blob.size,
                'content': content,
                'lines': len(content.splitlines()),
            }
        else:
            raise ValueError(
                f"Path is not a file: {subpath}\n"
                f"  git:// requires a file path or no path.\n"
                f"  For repo overview use: reveal git://"
            )

    except (KeyError, pygit2.GitError) as e:
        raise ValueError(f"File not found at {ref}: {subpath}") from e


def get_file_history(
    repo: 'pygit2.Repository',
    ref: str,
    subpath: str,
    query: Dict[str, str],
    result_control,
    query_filters: list,
    format_commit_func,
    matches_all_filters_func,
    commit_touches_file_func
) -> Dict[str, Any]:
    """Get commit history for a specific file."""
    import pygit2

    try:
        limit = int(query.get('limit', 50))
        commits = []

        # Start from HEAD or specified ref
        obj = repo.revparse_single(ref)
        while hasattr(obj, 'peel') and not isinstance(obj, pygit2.Commit):
            obj = obj.peel(pygit2.Commit)  # type: ignore[assignment]

        commit = cast('pygit2.Commit', obj)

        # Walk commit history
        walker = repo.walk(commit.id, pygit2.GIT_SORT_TIME)  # type: ignore[arg-type]

        for commit in walker:
            # Check if this commit touched the file
            if commit_touches_file_func(repo, commit, subpath):
                commit_dict = format_commit_func(commit)
                # Apply query filters
                if matches_all_filters_func(commit_dict):
                    commits.append(commit_dict)

                    # Legacy limit parameter support (for backward compatibility)
                    # Note: Prefer using ?limit=N in query string for result control
                    if len(commits) >= limit:
                        break

        # Apply result control (sort, limit, offset) from query params
        from ...utils.query import apply_result_control
        total_matches = len(commits)
        controlled_commits = apply_result_control(commits, result_control)

        return {
            'contract_version': '1.0',
            'type': 'git_file_history',
            'source': f"{subpath}@{ref}",
            'source_type': 'file',
            'path': subpath,
            'ref': ref,
            'commits': controlled_commits,
            'count': len(controlled_commits),
            'total_matches': total_matches if total_matches != len(controlled_commits) else None,
        }

    except (KeyError, pygit2.GitError) as e:
        raise ValueError(f"Failed to get file history: {subpath}") from e


def get_file_blame(
    repo: 'pygit2.Repository',
    ref: str,
    subpath: str,
    query: Dict[str, str],
    path: str,
    get_element_line_range_func
) -> Dict[str, Any]:
    """Get blame information for a file or specific element."""
    import pygit2

    try:
        # Resolve ref to commit
        obj = repo.revparse_single(ref)
        while hasattr(obj, 'peel') and not isinstance(obj, pygit2.Commit):
            obj = obj.peel(pygit2.Commit)  # type: ignore[assignment]

        commit = cast('pygit2.Commit', obj)

        # Get blame for the file
        blame = repo.blame(subpath, newest_commit=commit.id)

        # Get file contents to include with blame
        tree = commit.tree
        entry = tree[subpath]
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
        element_name = query.get('element')
        element_info = None
        if element_name:
            # Get line range for the element
            element_range = get_element_line_range_func(element_name, path, subpath)
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
                print(f"Note: Element '{element_name}' not found in {subpath}, showing full file blame", file=sys.stderr)

        # Check if detail mode is requested
        detail_mode = query.get('detail') == 'full'

        result = {
            'contract_version': '1.0',
            'type': 'git_file_blame',
            'source': f"{subpath}@{ref}",
            'source_type': 'file',
            'path': subpath,
            'ref': ref,
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
        raise ValueError(f"Failed to get file blame: {subpath}") from e


def get_element_line_range(element_name: str, path: str, subpath: str) -> Optional[Dict[str, int]]:
    """Get line range for a specific element (function/class) in the file."""
    try:
        # Use reveal's registry to analyze the file
        from reveal.registry import get_analyzer

        # Build absolute path if needed
        if path and path != '.':
            file_path = os.path.join(path, subpath)
        else:
            file_path = subpath

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


def commit_touches_file(
    repo: 'pygit2.Repository',
    commit: 'pygit2.Commit',
    filepath: str
) -> bool:
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
