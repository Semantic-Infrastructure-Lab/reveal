"""Git reference, branch, and tag handling."""

import logging
from datetime import datetime
from typing import Dict, Any, List, cast, TYPE_CHECKING
from reveal.reveal_types import CONTRACT_VERSION

from ...utils.results import ResultBuilder
from .commits import disclose_timeline_cut, timeline_fields

if TYPE_CHECKING:
    import pygit2

logger = logging.getLogger(__name__)


def get_ref_structure(
    repo: 'pygit2.Repository',
    ref: str,
    query: Dict[str, str],
    query_filters: list,
    result_control,
    format_commit_func,
    matches_all_filters_func,
    get_commit_history_func
) -> Dict[str, Any]:
    """Get structure for specific ref (commit/branch/tag)."""
    try:
        import pygit2

        obj = repo.revparse_single(ref)

        # If it's a tag, peel to the commit
        while hasattr(obj, 'peel') and not isinstance(obj, pygit2.Commit):
            obj = obj.peel(pygit2.Commit)  # type: ignore[assignment]

        if isinstance(obj, pygit2.Commit):
            commit_obj = cast('pygit2.Commit', obj)
            # Get commit history from this point
            limit = int(query.get('limit', 20))
            walk = get_commit_history_func(repo, commit_obj, limit=limit)

            result = ResultBuilder.create(
                result_type='git_ref',
                source=f"{repo.workdir or repo.path}@{ref}",
                source_type='directory',
                contract_version=CONTRACT_VERSION,
                ref=ref,
                commit=format_commit_func(commit_obj, detailed=True),
                history=walk.commits,
                filter_applied=bool(query_filters),
            )
            walk.disclose(result, 'history')
            # BACK-1166: surface a content-pattern search degradation, if the
            # caller requested one (get_commit_history_func resets this
            # before running).
            from .files import get_content_search_disclosure
            disclosure = get_content_search_disclosure()
            if disclosure:
                result.setdefault('warnings', []).append({
                    'type': 'content_search_unavailable',
                    'message': disclosure,
                })
            if getattr(repo, 'is_shallow', False):
                result['shallow_clone'] = True
            return result
        else:
            raise ValueError(f"Cannot resolve ref to commit: {ref}")

    except (KeyError, pygit2.GitError) as e:
        raise ValueError(f"Invalid ref: {ref}") from e


def get_ref_timeline(
    repo: 'pygit2.Repository',
    ref: str,
    bucket: str,
    get_commit_timeline_func,
) -> Dict[str, Any]:
    """Bucket repo-wide commit history (no subpath) by week/month."""
    try:
        import pygit2

        obj = repo.revparse_single(ref)
        while hasattr(obj, 'peel') and not isinstance(obj, pygit2.Commit):
            obj = obj.peel(pygit2.Commit)  # type: ignore[assignment]

        if not isinstance(obj, pygit2.Commit):
            raise ValueError(f"Cannot resolve ref to commit: {ref}")

        commit_obj = cast('pygit2.Commit', obj)
        walk = get_commit_timeline_func(repo, commit_obj)

        result = ResultBuilder.create(
            result_type='git_timeline',
            source=f"{repo.workdir or repo.path}@{ref}",
            source_type='repository',
            contract_version=CONTRACT_VERSION,
            path=None,
            ref=ref,
            **timeline_fields(walk.commits, bucket),
        )
        disclose_timeline_cut(result, walk)
        if getattr(repo, 'is_shallow', False):
            result['shallow_clone'] = True
        return result

    except (KeyError, pygit2.GitError) as e:
        raise ValueError(f"Invalid ref: {ref}") from e


def get_head_info(repo: 'pygit2.Repository') -> Dict[str, Any]:
    """Get HEAD information."""
    if repo.is_empty or repo.head_is_unborn:
        return {'branch': None, 'commit': None, 'detached': False}

    try:
        return {
            'branch': repo.head.shorthand if not repo.head_is_detached else None,
            'commit': str(repo.head.target)[:7],
            'detached': repo.head_is_detached,
        }
    except Exception as e:
        # Same shape as a genuinely empty/unborn repo (line 92) — log so a
        # corrupted-HEAD failure isn't indistinguishable from a fresh repo.
        logger.warning(f"Failed to read HEAD info: {e}")
        return {'branch': None, 'commit': None, 'detached': False}


def _get_branch_info(repo, branch_name) -> 'Dict[str, Any] | None':
    """Return branch info dict for branch_name, or None on error."""
    import pygit2
    try:
        branch = repo.branches.get(branch_name)
        if not branch or not branch.target:
            return None
        commit = cast('pygit2.Commit', repo[branch.target])
        return {
            'name': branch_name,
            'commit': str(commit.id)[:7],
            'message': commit.message.split('\n')[0][:80],
            'author': commit.author.name,
            'date': datetime.fromtimestamp(commit.commit_time).strftime('%Y-%m-%d'),
            'timestamp': commit.commit_time,
        }
    except (KeyError, pygit2.GitError):
        return None


def list_branches(repo: 'pygit2.Repository') -> List[Dict[str, Any]]:
    """List repository branches, newest first. The caller cuts (BACK-1551).

    A branch that can't be read is skipped by _get_branch_info; failing to list the
    branches at all propagates, rather than returning a partial list as if whole
    (BACK-1614).
    """
    branches = []
    for branch_name in repo.branches.local:
        info = _get_branch_info(repo, branch_name)
        if info:
            branches.append(info)
    return sorted(branches, key=lambda b: cast(int, b.get('timestamp', 0)), reverse=True)


def _get_tag_info(repo, ref_name) -> 'Dict[str, Any] | None':
    """Return tag info dict for ref_name, or None on error."""
    import pygit2
    try:
        ref = repo.references.get(ref_name)
        if not ref:
            return None
        tag_name = ref_name.replace('refs/tags/', '')
        target = repo[ref.target]
        while hasattr(target, 'peel') and not isinstance(target, pygit2.Commit):
            target = target.peel(pygit2.Commit)  # type: ignore[assignment]
        if not isinstance(target, pygit2.Commit):
            return None
        commit_target = cast('pygit2.Commit', target)
        return {
            'name': tag_name,
            'commit': str(commit_target.id)[:7],
            'message': commit_target.message.split('\n')[0][:80],
            'date': datetime.fromtimestamp(commit_target.commit_time).strftime('%Y-%m-%d'),
            'timestamp': commit_target.commit_time,
        }
    except (KeyError, pygit2.GitError, AttributeError):
        return None


def list_tags(repo: 'pygit2.Repository') -> List[Dict[str, Any]]:
    """List repository tags, newest first. The caller cuts (BACK-1551).

    Same contract as list_branches: one unreadable tag is skipped, a failure to
    list them propagates (BACK-1614).
    """
    tags = []
    for ref_name in repo.references:
        if not ref_name.startswith('refs/tags/'):
            continue
        info = _get_tag_info(repo, ref_name)
        if info:
            tags.append(info)
    return sorted(tags, key=lambda t: cast(int, t.get('timestamp', 0)), reverse=True)
