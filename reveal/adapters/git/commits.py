"""Git commit operations and formatting."""

from datetime import datetime
from typing import Dict, Any, List, TYPE_CHECKING

if TYPE_CHECKING:
    import pygit2


def get_repository_overview(
    repo: 'pygit2.Repository',
    get_head_info_func,
    list_branches_func,
    list_tags_func,
    get_recent_commits_func
) -> Dict[str, Any]:
    """Generate repository overview structure."""
    head_info = get_head_info_func(repo)
    branches = list_branches_func(repo)
    tags = list_tags_func(repo)
    recent_commits = get_recent_commits_func(repo, limit=10)

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


def get_recent_commits(
    repo: 'pygit2.Repository',
    limit: int,
    format_commit_func,
    matches_all_filters_func,
    result_control,
    query_filters: list
) -> List[Dict[str, Any]]:
    """Get recent commits from HEAD."""
    import pygit2

    commits: List[Dict[str, Any]] = []

    try:
        if repo.is_empty:
            return commits

        walker = repo.walk(repo.head.target, pygit2.GIT_SORT_TIME)  # type: ignore[arg-type]

        for commit in walker:
            commit_dict = format_commit_func(commit)
            # Apply query filters
            if matches_all_filters_func(commit_dict):
                commits.append(commit_dict)
                # Legacy limit for backward compatibility
                if len(commits) >= limit:
                    break
    except Exception:
        pass  # return whatever commits were collected before the error

    # Apply result control if specified in query
    if result_control.limit or result_control.sort_field or result_control.offset:
        from ...utils.query import apply_result_control
        commits = apply_result_control(commits, result_control)

    return commits


def get_commit_history(
    repo: 'pygit2.Repository',
    start_commit: 'pygit2.Commit',
    limit: int,
    format_commit_func,
    matches_all_filters_func,
    result_control,
    query_filters: list
) -> List[Dict[str, Any]]:
    """Get commit history from a starting commit."""
    import pygit2

    commits = []

    try:
        walker = repo.walk(start_commit.id, pygit2.GIT_SORT_TIME)  # type: ignore[arg-type]

        for commit in walker:
            commit_dict = format_commit_func(commit)
            # Apply query filters
            if matches_all_filters_func(commit_dict):
                commits.append(commit_dict)
                # Legacy limit for backward compatibility
                if len(commits) >= limit:
                    break
    except Exception:
        pass  # return whatever commits were collected before the error

    # Apply result control if specified in query
    if result_control.limit or result_control.sort_field or result_control.offset:
        from ...utils.query import apply_result_control
        commits = apply_result_control(commits, result_control)

    return commits


def format_commit(commit: 'pygit2.Commit', detailed: bool = False) -> Dict[str, Any]:
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
