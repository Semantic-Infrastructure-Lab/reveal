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
    subpath: str,
    raw: bool = False,
) -> Dict[str, Any]:
    """Get file structure (or raw contents when raw=True) at a specific ref."""
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
            short_hash = str(commit.id)[:7]
            line_count = len(content.splitlines())
            commit_info = {
                'hash': short_hash,
                'author': commit.author.name,
                'date': datetime.fromtimestamp(commit.commit_time).strftime('%Y-%m-%d'),
                'message': commit.message.split('\n')[0].strip(),
            }

            if raw:
                return {
                    'contract_version': '1.0',
                    'type': 'git_file',
                    'source': f"{subpath}@{ref}",
                    'source_type': 'file',
                    'path': subpath,
                    'ref': ref,
                    'commit': short_hash,
                    'commit_info': commit_info,
                    'size': blob.size,
                    'content': content,
                    'lines': line_count,
                }

            structure = _analyze_blob_content(content, subpath)
            return {
                'contract_version': '1.0',
                'type': 'git_file_structure',
                'source': f"{subpath}@{ref}",
                'source_type': 'file',
                'path': subpath,
                'ref': ref,
                'commit': short_hash,
                'commit_info': commit_info,
                'size': blob.size,
                'lines': line_count,
                'structure': structure,
            }
        else:
            raise ValueError(
                f"Path is not a file: {subpath}\n"
                f"  git:// expects a file path, not a directory.\n"
                f"  For repo overview: reveal git://\n"
                f"  For a specific repo: reveal 'git:///path/to/repo'"
            )

    except (KeyError, pygit2.GitError) as e:
        raise ValueError(f"File not found at {ref}: {subpath}") from e


def _analyze_blob_content(content: str, subpath: str) -> Dict[str, Any]:
    """Write blob content to a temp file and run the reveal analyzer on it."""
    import tempfile
    from pathlib import Path
    from reveal.registry import get_analyzer

    suffix = Path(subpath).suffix
    with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        analyzer_class = get_analyzer(temp_path, allow_fallback=False)
        if not analyzer_class:
            return {}
        structure = analyzer_class(temp_path).get_structure()
        return cast(Dict[str, Any], structure.get('structure', structure))
    finally:
        os.unlink(temp_path)


def get_file_diff(
    repo: 'pygit2.Repository',
    ref: str,
    subpath: str,
    query: Dict[str, Any],
) -> Dict[str, Any]:
    """Get a unified diff of a file at a commit vs its parent.

    Returns commit metadata + the raw diff text. Supports:
    - ?context=N  — context lines (default 3)
    - ?element=func_name  — pre-filter to hunks touching that element
    """
    import subprocess
    import pygit2

    try:
        obj = repo.revparse_single(ref)
        while hasattr(obj, 'peel') and not isinstance(obj, pygit2.Commit):
            obj = obj.peel(pygit2.Commit)  # type: ignore[assignment]
        if not isinstance(obj, pygit2.Commit):
            raise ValueError(f"Cannot resolve ref to commit: {ref}")
        commit = cast('pygit2.Commit', obj)
    except (KeyError, pygit2.GitError) as e:
        raise ValueError(f"Cannot resolve ref: {ref}") from e

    short_hash = str(commit.id)[:7]
    context = int(query.get('context', 3))
    element = query.get('element')
    repo_root = repo.workdir.rstrip('/\\') if repo.workdir else '.'

    if commit.parents:
        cmd = ['git', '-C', repo_root, 'diff', f'-U{context}',
               str(commit.parents[0].id), str(commit.id), '--', subpath]
    else:
        # First commit — diff against the empty tree
        empty_tree = '4b825dc642cb6eb9a060e54bf8d69288fbee4904'
        cmd = ['git', '-C', repo_root, 'diff', f'-U{context}',
               empty_tree, str(commit.id), '--', subpath]

    result = subprocess.run(cmd, capture_output=True, text=True)
    diff_text = result.stdout

    if not diff_text:
        diff_text = f"(no changes to {subpath} in this commit)"

    if element:
        diff_text = _filter_diff_to_element(diff_text, element)

    commit_info = {
        'hash': short_hash,
        'author': commit.author.name,
        'date': datetime.fromtimestamp(commit.commit_time).strftime('%Y-%m-%d %H:%M:%S'),
        'message': commit.message.split('\n')[0].strip(),
    }

    return {
        'contract_version': '1.0',
        'type': 'git_file_diff',
        'source': f"{subpath}@{ref}",
        'source_type': 'file',
        'path': subpath,
        'ref': ref,
        'commit': short_hash,
        'commit_info': commit_info,
        'diff_text': diff_text,
        'element_filter': element,
    }


def _filter_diff_to_element(diff_text: str, element: str) -> str:
    """Return only the hunks from diff_text whose context or body mention element."""
    lines = diff_text.splitlines(keepends=True)
    header_lines: List[str] = []
    hunks: List[List[str]] = []
    current: List[str] = []
    in_header = True

    for line in lines:
        if line.startswith('@@'):
            in_header = False
            if current:
                hunks.append(current)
            current = [line]
        elif in_header:
            header_lines.append(line)
        else:
            current.append(line)

    if current:
        hunks.append(current)

    matching = [h for h in hunks if any(element in l for l in h)]
    if not matching:
        return f"(no hunks in this diff mention '{element}')\n\n" + diff_text

    return ''.join(header_lines) + ''.join(''.join(h) for h in matching)


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
            if not commit_touches_file_func(repo, commit, subpath):
                continue
            commit_dict = format_commit_func(commit)
            if not matches_all_filters_func(commit_dict):
                continue
            commits.append(commit_dict)
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


def _filter_ignored_hunks(hunks: List[Dict[str, Any]], ignore_shas: List[str]):
    """Remove hunks whose commit hash starts with any of the given sha prefixes.

    Returns (kept_hunks, ignored_summary) where ignored_summary is a list of
    {hash, message, lines} dicts for suppressed commits.
    """
    if not ignore_shas:
        return hunks, []

    ignored_by_sha: Dict[str, Dict[str, Any]] = {}
    kept = []
    for h in hunks:
        h_hash = h['commit']['hash']
        matched = next((s for s in ignore_shas if h_hash.startswith(s) or s.startswith(h_hash)), None)
        if matched:
            if h_hash not in ignored_by_sha:
                ignored_by_sha[h_hash] = {
                    'hash': h_hash,
                    'message': h['commit']['message'],
                    'lines': 0,
                }
            ignored_by_sha[h_hash]['lines'] += h.get('clipped_lines', h['lines']['count'])
        else:
            kept.append(h)

    return kept, list(ignored_by_sha.values())


def _apply_element_blame_filter(element_name, hunks, path, subpath, get_range_func):
    """Filter blame hunks to the line range of a named element.

    Returns (element_info, filtered_hunks). If element not found, returns (None, original_hunks).
    """
    element_range = get_range_func(element_name, path, subpath)
    if not element_range:
        print(f"Note: Element '{element_name}' not found in {subpath}, showing full file blame",
              file=sys.stderr)
        return None, hunks

    element_info = {
        'name': element_name,
        'line_start': element_range['line'],
        'line_end': element_range['line_end'],
    }
    el_start = element_range['line']
    el_end = element_range['line_end']
    filtered = []
    for h in hunks:
        h_start = h['lines']['start']
        h_end = h_start + h['lines']['count'] - 1
        if h_start <= el_end and h_end >= el_start:
            clipped = min(h_end, el_end) - max(h_start, el_start) + 1
            filtered.append({**h, 'clipped_lines': clipped})
    return element_info, filtered


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
            element_info, hunks = _apply_element_blame_filter(
                element_name, hunks, path, subpath, get_element_line_range_func
            )

        # Apply ignore filter (?ignore=sha1,sha2) after element filtering so
        # clipped_lines are already set before we count suppressed lines.
        ignore_raw = query.get('ignore', '')
        ignore_shas = [s.strip() for s in ignore_raw.split(',') if s.strip()] if ignore_raw else []
        ignored_summary: List[Dict[str, Any]] = []
        if ignore_shas:
            hunks, ignored_summary = _filter_ignored_hunks(hunks, ignore_shas)

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
        if ignored_summary:
            result['ignored'] = ignored_summary

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

        for parent in commit.parents:
            if _parent_has_different_file(parent, filepath, current_oid):
                return True
        return False

    except Exception:
        return False


def _parent_has_different_file(parent, filepath: str, current_oid) -> bool:
    """Return True if parent commit has a different (or missing) version of filepath."""
    try:
        parent_entry = parent.tree[filepath]
        return current_oid != parent_entry.id
    except KeyError:
        return True


def _get_element_content_at_commit(
    repo: 'pygit2.Repository',
    commit: 'pygit2.Commit',
    filepath: str,
    element_name: str,
) -> Optional[str]:
    """Extract the text of a named element from a file at a specific commit.

    Returns None if the file or element doesn't exist at that commit.
    """
    import tempfile
    from pathlib import Path

    try:
        tree = commit.tree
        entry = tree[filepath]
        blob = cast('pygit2.Blob', repo[entry.id])
        content = blob.data.decode('utf-8', errors='replace')
        file_lines = content.splitlines()

        suffix = Path(filepath).suffix or '.txt'
        with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            from reveal.registry import get_analyzer
            analyzer_class = get_analyzer(tmp_path)
            if not analyzer_class:
                return None
            structure = analyzer_class(tmp_path).get_structure()

            element_range = None
            for item in structure.get('functions', []) + structure.get('classes', []):
                if item.get('name') == element_name:
                    element_range = (item['line'], item.get('line_end', item['line']))
                    break

            if element_range is None:
                return None

            start, end = element_range
            return '\n'.join(file_lines[start - 1:end])
        finally:
            os.unlink(tmp_path)

    except (KeyError, Exception):
        return None


def commit_touches_element(
    repo: 'pygit2.Repository',
    commit: 'pygit2.Commit',
    filepath: str,
    element_name: str,
) -> bool:
    """Check if a commit changed a specific named element within a file.

    Uses commit_touches_file as a fast gate, then compares the element's text
    at this commit vs each parent to detect actual content changes.
    """
    if not commit_touches_file(repo, commit, filepath):
        return False

    current = _get_element_content_at_commit(repo, commit, filepath, element_name)
    if current is None:
        return False

    if not commit.parents:
        return True

    for parent in commit.parents:
        parent_content = _get_element_content_at_commit(repo, parent, filepath, element_name)
        if parent_content != current:
            return True

    return False
