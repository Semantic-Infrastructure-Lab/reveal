"""Git commit operations and formatting."""

from datetime import datetime
from typing import Dict, Any, List, Optional, TYPE_CHECKING

from ...utils.query import apply_result_control

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
    query_filters: list,
    no_merges: bool = False,
    content_pattern: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get recent commits from HEAD."""
    import pygit2

    if content_pattern:
        from .files import _commit_diff_contains

    commits: List[Dict[str, Any]] = []

    try:
        if repo.is_empty:
            return commits

        walker = repo.walk(repo.head.target, pygit2.GIT_SORT_TIME)  # type: ignore[arg-type]

        for commit in walker:
            if no_merges and len(commit.parents) > 1:
                continue
            commit_dict = format_commit_func(commit)
            if not matches_all_filters_func(commit_dict):
                continue
            if content_pattern and not _commit_diff_contains(repo, commit, '', content_pattern):
                continue
            commits.append(commit_dict)
            if len(commits) >= limit:
                break
    except Exception:
        pass  # return whatever commits were collected before the error

    # Apply result control if specified in query
    if result_control.limit or result_control.sort_field or result_control.offset:
        commits = apply_result_control(commits, result_control)

    return commits


def get_commit_history(
    repo: 'pygit2.Repository',
    start_commit: 'pygit2.Commit',
    limit: int,
    format_commit_func,
    matches_all_filters_func,
    result_control,
    query_filters: list,
    no_merges: bool = False,
    content_pattern: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get commit history from a starting commit."""
    import pygit2

    if content_pattern:
        from .files import _commit_diff_contains

    commits = []

    try:
        walker = repo.walk(start_commit.id, pygit2.GIT_SORT_TIME)  # type: ignore[arg-type]

        for commit in walker:
            if no_merges and len(commit.parents) > 1:
                continue
            commit_dict = format_commit_func(commit)
            if not matches_all_filters_func(commit_dict):
                continue
            if content_pattern and not _commit_diff_contains(repo, commit, '', content_pattern):
                continue
            commits.append(commit_dict)
            if len(commits) >= limit:
                break
    except Exception:
        pass  # return whatever commits were collected before the error

    # Apply result control if specified in query
    if result_control.limit or result_control.sort_field or result_control.offset:
        commits = apply_result_control(commits, result_control)

    return commits


def bucket_commits(commit_dicts: List[Dict[str, Any]], bucket: str) -> List[Dict[str, Any]]:
    """Group formatted commits into week/month buckets.

    Each bucket reports commit_count and the count of distinct authors
    (by email, falling back to name) touching that period. Buckets are
    returned sorted chronologically ascending.
    """
    groups: Dict[str, Dict[str, Any]] = {}

    for commit_dict in commit_dicts:
        dt = datetime.fromtimestamp(commit_dict['timestamp'])
        if bucket == 'week':
            iso_year, iso_week, _ = dt.isocalendar()
            period = f"{iso_year}-W{iso_week:02d}"
        else:  # month
            period = f"{dt.year}-{dt.month:02d}"

        author_key = commit_dict.get('email') or commit_dict.get('author')
        group = groups.setdefault(period, {'period': period, 'commit_count': 0, '_authors': set()})
        group['commit_count'] += 1
        group['_authors'].add(author_key)

    buckets = []
    for period in sorted(groups.keys()):
        group = groups[period]
        buckets.append({
            'period': group['period'],
            'commit_count': group['commit_count'],
            'author_count': len(group['_authors']),
        })
    return buckets


def get_commit_timeline(
    repo: 'pygit2.Repository',
    start_commit: 'pygit2.Commit',
    bucket: str,
    limit: int,
    format_commit_func,
    matches_all_filters_func,
    no_merges: bool = False,
) -> Dict[str, Any]:
    """Walk history from start_commit and bucket it by week/month.

    Unlike get_commit_history, this collects up to `limit` matching commits
    (a much higher default than the flat-list view, since a meaningful
    timeline needs the full range) and returns aggregated period counts
    rather than a commit list.
    """
    import pygit2

    matched: List[Dict[str, Any]] = []

    try:
        walker = repo.walk(start_commit.id, pygit2.GIT_SORT_TIME)  # type: ignore[arg-type]

        for commit in walker:
            if no_merges and len(commit.parents) > 1:
                continue
            commit_dict = format_commit_func(commit)
            if not matches_all_filters_func(commit_dict):
                continue
            matched.append(commit_dict)
            if len(matched) >= limit:
                break
    except Exception:
        pass  # return whatever commits were collected before the error

    buckets = bucket_commits(matched, bucket)

    return {
        'bucket': bucket,
        'buckets': buckets,
        'commit_count': len(matched),
        'distinct_author_count': len({c.get('email') or c.get('author') for c in matched}),
    }


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
