"""Git file operations: history, blame, and content retrieval."""

import os
import re
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional, cast, TYPE_CHECKING

_LINE_RANGE_RE = re.compile(r'^[Ll](\d+)-[Ll]?(\d+)$')

_BLAME_NOISE_RE = re.compile(
    r'normalize|line.end|gitattributes|format|whitespace|prettier|eslint'
    r'|black|isort|autopep8|clang.?format',
    re.IGNORECASE,
)

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

        no_merges = query.get('no_merges') in ('1', 'true', 'yes')
        content_pattern: Optional[str] = query.get('content~') or query.get('content') or None

        # Walk commit history
        walker = repo.walk(commit.id, pygit2.GIT_SORT_TIME)  # type: ignore[arg-type]

        for commit in walker:
            if no_merges and len(commit.parents) > 1:
                continue
            if not commit_touches_file_func(repo, commit, subpath):
                continue
            commit_dict = format_commit_func(commit)
            if not matches_all_filters_func(commit_dict):
                continue
            if content_pattern and not _commit_diff_contains(repo, commit, subpath, content_pattern):
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


def _commit_diff_contains(
    repo: 'pygit2.Repository',
    commit: 'pygit2.Commit',
    subpath: str,
    pattern: str,
) -> bool:
    """Return True if pattern appears in the diff introduced by commit.

    Searches the raw unified diff text, so it matches both added and removed
    lines (classic pickaxe behaviour). Pass subpath='' to search all files.
    """
    import subprocess
    repo_root = repo.workdir.rstrip('/\\') if repo.workdir else '.'
    if commit.parents:
        cmd = ['git', '-C', repo_root, 'diff',
               str(commit.parents[0].id), str(commit.id)]
    else:
        empty_tree = '4b825dc642cb6eb9a060e54bf8d69288fbee4904'
        cmd = ['git', '-C', repo_root, 'diff', empty_tree, str(commit.id)]
    if subpath:
        cmd += ['--', subpath]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if (line and line[0] in ('+', '-')
                    and not line.startswith('+++')
                    and not line.startswith('---')
                    and pattern in line):
                return True
        return False
    except Exception:
        return False


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


def _file_has_no_named_elements(path: str, subpath: str) -> bool:
    """Return True if the file has no analyzable functions or classes (procedural file)."""
    try:
        from reveal.registry import get_analyzer
        file_path = os.path.join(path, subpath) if path and path != '.' else subpath
        if not os.path.isabs(file_path):
            file_path = os.path.abspath(file_path)
        analyzer_class = get_analyzer(file_path)
        if not analyzer_class:
            return True
        structure = analyzer_class(file_path).get_structure()
        return not structure.get('functions') and not structure.get('classes')
    except Exception:
        return False


def _apply_element_blame_filter(element_name, hunks, path, subpath, get_range_func):
    """Filter blame hunks to the line range of a named element or explicit L<s>-L<e> range.

    Returns (element_info, filtered_hunks). If element not found, returns (None, original_hunks).
    """
    # Handle explicit line-range syntax: L128-L162 or L128-162
    lr_match = _LINE_RANGE_RE.match(element_name)
    if lr_match:
        el_start = int(lr_match.group(1))
        el_end = int(lr_match.group(2))
        if el_start > el_end:
            el_start, el_end = el_end, el_start
        element_info = {'name': element_name, 'line_start': el_start, 'line_end': el_end}
        filtered = []
        for h in hunks:
            h_start = h['lines']['start']
            h_end = h_start + h['lines']['count'] - 1
            if h_start <= el_end and h_end >= el_start:
                clipped = min(h_end, el_end) - max(h_start, el_start) + 1
                filtered.append({**h, 'clipped_lines': clipped})
        return element_info, filtered

    # Named element lookup
    element_range = get_range_func(element_name, path, subpath)
    if not element_range:
        if _file_has_no_named_elements(path, subpath):
            print(
                f"Warning: Element '{element_name}' not found in {subpath} — "
                f"file has no named elements (procedural). "
                f"Use ?element=L<start>-L<end> to blame a specific line range.",
                file=sys.stderr,
            )
        else:
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


def _resolve_blame_commit(repo: 'pygit2.Repository', ref: str) -> 'pygit2.Commit':
    """Peel a ref string to a Commit object."""
    import pygit2
    obj = repo.revparse_single(ref)
    while hasattr(obj, 'peel') and not isinstance(obj, pygit2.Commit):
        obj = obj.peel(pygit2.Commit)  # type: ignore[assignment]
    return cast('pygit2.Commit', obj)


def _read_blob_lines(repo: 'pygit2.Repository', commit: 'pygit2.Commit', subpath: str) -> List[str]:
    """Read file lines from a blob in the given commit's tree."""
    import pygit2
    tree = commit.tree
    entry = tree[subpath]
    blob = cast('pygit2.Blob', repo[entry.id])
    return blob.data.decode('utf-8', errors='replace').splitlines()


def _format_blame_hunks(repo: 'pygit2.Repository', blame: Any) -> List[Dict[str, Any]]:
    """Convert pygit2 blame hunks to serializable dicts."""
    import pygit2
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
    return hunks


def _read_blame_ignore_revs(workdir: Optional[str]) -> List[str]:
    """Read short SHAs from .git-blame-ignore-revs if present in workdir."""
    if not workdir:
        return []
    revs_path = os.path.join(workdir, '.git-blame-ignore-revs')
    if not os.path.exists(revs_path):
        return []
    shas: List[str] = []
    with open(revs_path) as f:
        for line in f:
            sha = line.split('#')[0].strip()
            if sha and len(sha) >= 7:
                shas.append(sha[:7])
    return shas


def _detect_noise_commits(hunks: List[Dict[str, Any]]) -> List[str]:
    """Return hunk SHAs that match the noise pattern AND own >50% of hunks."""
    total = len(hunks)
    if total == 0:
        return []
    hunk_counts: Dict[str, int] = {}
    hunk_msg: Dict[str, str] = {}
    for h in hunks:
        sha7 = h['commit']['hash']
        hunk_counts[sha7] = hunk_counts.get(sha7, 0) + 1
        hunk_msg[sha7] = h['commit']['message']
    return [
        sha7 for sha7, count in hunk_counts.items()
        if count / total > 0.5 and _BLAME_NOISE_RE.search(hunk_msg[sha7])
    ]


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
        commit = _resolve_blame_commit(repo, ref)
        blame = repo.blame(subpath, newest_commit=commit.id)
        lines = _read_blob_lines(repo, commit, subpath)
        hunks = _format_blame_hunks(repo, blame)

        element_name = query.get('element')
        element_info = None
        if element_name:
            element_info, hunks = _apply_element_blame_filter(
                element_name, hunks, path, subpath, get_element_line_range_func
            )

        # ?ignore=off disables all auto-ignore and shows raw blame.
        ignore_off = query.get('ignore', '').strip().lower() == 'off'
        explicit_shas: List[str] = []
        ignore_revs_shas: List[str] = []
        auto_shas: List[str] = []
        if not ignore_off:
            ignore_raw = query.get('ignore', '')
            explicit_shas = [s.strip() for s in ignore_raw.split(',') if s.strip()] if ignore_raw else []
            ignore_revs_shas = _read_blame_ignore_revs(getattr(repo, 'workdir', None))
            auto_shas = _detect_noise_commits(hunks)

        all_ignore_shas = list(dict.fromkeys(explicit_shas + ignore_revs_shas + auto_shas))
        ignored_summary: List[Dict[str, Any]] = []
        if all_ignore_shas:
            hunks, ignored_summary = _filter_ignored_hunks(hunks, all_ignore_shas)
            explicit_set = {s[:7] for s in explicit_shas}
            revs_set = {s[:7] for s in ignore_revs_shas}
            for entry in ignored_summary:
                h7 = entry['hash'][:7]
                if h7 in explicit_set:
                    entry['source'] = 'explicit'
                elif h7 in revs_set:
                    entry['source'] = 'ignore-revs'
                else:
                    entry['source'] = 'auto-detect'

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

        if getattr(repo, 'is_shallow', False):
            result['shallow_clone'] = True

        if element_info:
            result['element'] = element_info
        if ignored_summary:
            result['ignored'] = ignored_summary

        return result

    except (KeyError, pygit2.GitError) as e:
        raise ValueError(f"Failed to get file blame: {subpath}") from e


def _aggregate_commit_authors(
    repo: 'pygit2.Repository',
    start_commit: 'pygit2.Commit',
    git_subpath: Optional[str],
    include_merges: bool,
    limit: Optional[int],
) -> tuple:
    """Walk history from start_commit, attributing touching commits to authors.

    Returns (author_list, total) where author_list is sorted by commit count
    descending and each entry carries name, email, commits, share, last_touch.
    """
    import pygit2

    authors: Dict[tuple, Dict[str, Any]] = {}
    total = 0
    walked = 0

    walker = repo.walk(start_commit.id, pygit2.GIT_SORT_TIME)  # type: ignore[arg-type]
    for c in walker:
        if not include_merges and len(c.parents) > 1:
            continue
        walked += 1
        if limit and walked > limit:
            break
        if not commit_touches_path(repo, c, git_subpath):
            continue
        total += 1
        key = (c.author.name, c.author.email)
        rec = authors.get(key)
        if rec is None:
            authors[key] = {
                'name': c.author.name,
                'email': c.author.email,
                'commits': 1,
                '_ts': c.commit_time,
            }
        else:
            rec['commits'] += 1
            if c.commit_time > rec['_ts']:
                rec['_ts'] = c.commit_time

    author_list = sorted(authors.values(), key=lambda a: a['commits'], reverse=True)
    for a in author_list:
        a['share'] = round(a['commits'] / total, 4) if total else 0.0
        a['last_touch'] = datetime.fromtimestamp(a.pop('_ts')).strftime('%Y-%m-%d')

    return author_list, total


def get_ownership(
    repo: 'pygit2.Repository',
    ref: str,
    git_subpath: Optional[str],
    query: Dict[str, str],
    result_control,
) -> Dict[str, Any]:
    """Aggregate git-log authorship over a file, directory, or whole repo.

    Returns commit-share ownership: primary author, per-author commit share,
    contributor count, and last-touch date. This is straight commit-log
    aggregation (commit-share, NOT line-ownership — use ?type=blame for
    surviving-line attribution). The consumer applies the bus-factor /
    key-person judgment over this data.

    git_subpath is repo-root-relative; None means the whole repository.
    """
    import pygit2

    try:
        commit = _resolve_blame_commit(repo, ref)
    except (KeyError, pygit2.GitError) as e:
        raise ValueError(f"Failed to resolve ref for ownership: {ref}") from e

    # Classify the target (file / directory / repository) from the tree entry.
    if git_subpath is None:
        source_type = 'repository'
    else:
        try:
            entry = commit.tree[git_subpath]
        except KeyError as e:
            raise ValueError(
                f"Path not found at {ref}: {git_subpath}"
            ) from e
        source_type = 'directory' if isinstance(repo[entry.id], pygit2.Tree) else 'file'

    include_merges = query.get('merges') in ('1', 'true', 'yes')
    limit = getattr(result_control, 'limit', None) if result_control else None

    author_list, total = _aggregate_commit_authors(
        repo, commit, git_subpath, include_merges, limit
    )

    result: Dict[str, Any] = {
        'contract_version': '1.0',
        'type': 'git_ownership',
        'source': f"{git_subpath or '.'}@{ref}",
        'source_type': source_type,
        'path': git_subpath or '.',
        'ref': ref,
        'total_commits': total,
        'contributor_count': len(author_list),
        'primary_author': author_list[0] if author_list else None,
        'last_touch': max((a['last_touch'] for a in author_list), default=None),
        'authors': author_list,
        '_meta': {
            'analysis_kind': 'commit-ownership',
            'confidence': 'high',
            'known_limits': [
                'commit-share, not line-ownership — use ?type=blame for surviving-line attribution',
                'merge commits excluded by default (use ?merges=1 to include)',
                'author identity is name+email — aliases / multiple emails count as distinct contributors',
            ],
        },
    }

    if getattr(repo, 'is_shallow', False):
        result['shallow_clone'] = True

    return result


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


def commit_touches_path(
    repo: 'pygit2.Repository',
    commit: 'pygit2.Commit',
    path: Optional[str]
) -> bool:
    """Check if a commit changed the tree entry at `path` (file OR directory).

    A directory path resolves to a tree entry whose id is the subtree oid, so
    comparing it against the parent's subtree oid detects any change beneath it.
    `path` of None/'' means the whole repository (any change vs parent).
    """
    try:
        if not path:
            if not commit.parents:
                return True
            return any(commit.tree.id != p.tree.id for p in commit.parents)
        return commit_touches_file(repo, commit, path)
    except Exception:
        return False


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
