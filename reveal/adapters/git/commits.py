"""Git commit operations and formatting."""

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, Any, List, Optional, TYPE_CHECKING
from reveal.reveal_types import CONTRACT_VERSION

from ...utils.query import ResultControl, apply_result_control
from ...utils.results import ResultBuilder, note_truncation

if TYPE_CHECKING:
    import pygit2


def history_sort() -> int:
    """pygit2 walk order for every user-visible history listing (BACK-1426).

    GIT_SORT_TIME alone leaves commits with the same timestamp in arbitrary order
    (three commits made in one second listed c3, c1, c2); adding TOPOLOGICAL keeps a
    child before its parent, so ties come out the way `git log` prints them.
    """
    import pygit2
    return pygit2.GIT_SORT_TOPOLOGICAL | pygit2.GIT_SORT_TIME

@dataclass
class HistoryWalk:
    """One page of a history walk, and what the walk knows about the rest (BACK-1547).

    ``total`` counts the matching commits the walk saw. It is exact when the walk ran to
    the end of history, and a lower bound (``exact=False``) when it stopped one commit
    past the page: more exist, but not how many.
    """
    commits: List[Dict[str, Any]]
    total: int
    exact: bool

    def disclose(self, result: Any, field: str, hint: Optional[str] = None) -> None:
        """Record the page as a cut of ``result[field]`` if it is one."""
        note_truncation(result, field, len(self.commits), self.total, 'limit',
                        hint=hint, exact=self.exact)


def walk_history(
    repo: 'pygit2.Repository',
    start_id,
    keep: Callable[['pygit2.Commit'], Optional[Dict[str, Any]]],
    limit: Optional[int],
    result_control: Optional[ResultControl] = None,
) -> HistoryWalk:
    """Walk history from ``start_id`` newest first, and page the commits ``keep`` accepts.

    The one commit walk behind every git:// view (BACK-1547). There were five copies, and
    each stopped at ``offset + limit``, so none could say whether more commits existed,
    ``?sort=`` ordered only the commits already walked (``?sort=date&limit=3`` listed the
    3 newest, re-sorted, not the 3 oldest), and two returned whatever they held when the
    walk raised.

    - ``keep(commit)`` returns the commit's dict, or None to skip it.
    - A limit cuts the answer; it doesn't bound what is read. With ``?sort=`` the walk
      reads all of history, since the sort must see every match, and the total is exact.
      Without it, history order is the answer's order, so the walk stops one commit past
      ``offset + limit``: that commit proves more exist.
    - A walk that fails partway fails the query, rather than passing off what it had
      collected as the whole answer.
    """
    import pygit2

    control = result_control or ResultControl()
    offset = control.offset or 0
    stop_at = None if limit is None or control.sort_field else offset + limit + 1
    matched: List[Dict[str, Any]] = []
    try:
        for commit in repo.walk(start_id, history_sort()):  # type: ignore[arg-type]
            commit_dict = keep(commit)
            if commit_dict is None:
                continue
            matched.append(commit_dict)
            if stop_at is not None and len(matched) >= stop_at:
                break
    except pygit2.GitError as exc:
        raise ValueError(
            f"git history walk failed after {len(matched)} commits: {exc}") from exc
    page = apply_result_control(matched, control)
    if limit is not None:
        page = page[:limit]
    return HistoryWalk(page, len(matched), stop_at is None or len(matched) < stop_at)


def commit_filter(
    repo: 'pygit2.Repository',
    format_commit_func,
    matches_all_filters_func,
    *,
    no_merges: bool = False,
    touches: Optional[Callable[..., bool]] = None,
    subpath: str = '',
    content_pattern: Optional[str] = None,
) -> Callable[['pygit2.Commit'], Optional[Dict[str, Any]]]:
    """The ``keep`` for ``walk_history``: which commits a git:// view lists.

    Cheapest test first: merges, then the path touch check, then the formatted commit's
    filters, then the diff search (``?content~=``), which reads blobs.
    """
    if content_pattern:
        from .files import _commit_diff_contains, _reset_content_search_error
        _reset_content_search_error()

    def keep(commit: 'pygit2.Commit') -> Optional[Dict[str, Any]]:
        if no_merges and len(commit.parents) > 1:
            return None
        if touches is not None and not touches(repo, commit, subpath):
            return None
        commit_dict: Dict[str, Any] = format_commit_func(commit)
        if not matches_all_filters_func(commit_dict):
            return None
        if content_pattern and not _commit_diff_contains(repo, commit, subpath, content_pattern):
            return None
        return commit_dict

    return keep


def get_repository_overview(
    repo: 'pygit2.Repository',
    get_head_info_func,
    list_branches_func,
    list_tags_func,
    get_recent_commits_func,
    recent_limit: int = 10,
) -> Dict[str, Any]:
    """Generate repository overview structure.

    ``recent_limit`` is ``?limit`` (default 10), so ``--all`` reaches the recent-commit list
    too; it was a fixed 10 that neither lifted (BACK-1547). It cuts the newest branches and
    tags the same way, disclosed: they were a silent 20 inside ``list_branches``/``list_tags``
    and then ``[:10]`` here, with only the ``count`` sibling to say so (BACK-1551).
    """
    head_info = get_head_info_func(repo)
    branches = list_branches_func(repo)
    tags = list_tags_func(repo)
    recent = get_recent_commits_func(repo, limit=recent_limit)

    result = ResultBuilder.create(
        result_type='git_repository',
        source=repo.workdir or repo.path,
        source_type='directory',
        contract_version=CONTRACT_VERSION,
        path=repo.workdir or repo.path,
        head=head_info,
        branches={
            'count': len(list(repo.branches.local)),
            'recent': branches[:recent_limit],
        },
        tags={
            'count': len([ref for ref in repo.references if ref.startswith('refs/tags/')]),
            'recent': tags[:recent_limit],
        },
        commits={
            'recent': recent.commits,
        },
        stats={
            'is_bare': repo.is_bare,
            'is_empty': repo.is_empty,
            'head_detached': repo.head_is_detached if not repo.is_empty else False,
        }
    )
    recent.disclose(result, 'commits.recent')
    for field, listed in (('branches.recent', branches), ('tags.recent', tags)):
        note_truncation(result, field, min(recent_limit, len(listed)), len(listed), 'limit',
                        hint='raise ?limit=N, or --all')
    # BACK-1166: surface a content-pattern search degradation, if the caller
    # requested one (get_recent_commits_func resets this before running).
    from .files import get_content_search_disclosure
    disclosure = get_content_search_disclosure()
    if disclosure:
        result.setdefault('warnings', []).append({
            'type': 'content_search_unavailable',
            'message': disclosure,
        })
    return result


def get_recent_commits(
    repo: 'pygit2.Repository',
    limit: int,
    format_commit_func,
    matches_all_filters_func,
    result_control,
    query_filters: list,
    no_merges: bool = False,
    content_pattern: Optional[str] = None,
) -> HistoryWalk:
    """Get recent commits from HEAD."""
    if repo.is_empty:
        return HistoryWalk([], 0, True)
    keep = commit_filter(repo, format_commit_func, matches_all_filters_func,
                         no_merges=no_merges, content_pattern=content_pattern)
    return walk_history(repo, repo.head.target, keep, limit, result_control)


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
) -> HistoryWalk:
    """Get commit history from a starting commit."""
    keep = commit_filter(repo, format_commit_func, matches_all_filters_func,
                         no_merges=no_merges, content_pattern=content_pattern)
    return walk_history(repo, start_commit.id, keep, limit, result_control)


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
    limit: int,
    format_commit_func,
    matches_all_filters_func,
    no_merges: bool = False,
) -> HistoryWalk:
    """Walk history from start_commit for a week/month timeline (``timeline_fields``).

    Unlike get_commit_history, this collects up to `limit` matching commits
    (a much higher default than the flat-list view, since a meaningful
    timeline needs the full range); the caller aggregates them into period
    counts rather than listing them.
    """
    keep = commit_filter(repo, format_commit_func, matches_all_filters_func,
                         no_merges=no_merges)
    return walk_history(repo, start_commit.id, keep, limit)


def timeline_fields(matched: List[Dict[str, Any]], bucket: str) -> Dict[str, Any]:
    """The bucketed counts a git_timeline result reports for ``matched``."""
    return {
        'bucket': bucket,
        'buckets': bucket_commits(matched, bucket),
        'commit_count': len(matched),
        'distinct_author_count': len({c.get('email') or c.get('author') for c in matched}),
    }


def disclose_timeline_cut(result: Any, walk: HistoryWalk) -> None:
    """A timeline counts only the commits its walk reached. When ``?limit`` stopped the
    walk, older history is missing from every count, so the result says so (BACK-1547)."""
    walk.disclose(result, 'commits',
                  hint='raise ?limit=N; the timeline counts only the newest N commits')


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
