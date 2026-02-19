"""Git reference, branch, and tag handling."""

from datetime import datetime
from typing import Dict, Any, List, cast, TYPE_CHECKING

if TYPE_CHECKING:
    import pygit2


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
            commits = get_commit_history_func(repo, commit_obj, limit=limit)

            return {
                'contract_version': '1.0',
                'type': 'git_ref',
                'source': f"{repo.workdir or repo.path}@{ref}",
                'source_type': 'directory',
                'ref': ref,
                'commit': format_commit_func(commit_obj, detailed=True),
                'history': commits,
            }
        else:
            raise ValueError(f"Cannot resolve ref to commit: {ref}")

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
    except Exception:
        return {'branch': None, 'commit': None, 'detached': False}


def list_branches(repo: 'pygit2.Repository', limit: int = 20) -> List[Dict[str, Any]]:
    """List repository branches."""
    import pygit2

    branches = []

    try:
        for branch_name in repo.branches.local:
            try:
                branch = repo.branches.get(branch_name)
                if not branch or not branch.target:
                    continue

                commit = cast('pygit2.Commit', repo[branch.target])
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
        pass  # return whatever branches were collected before the error

    return sorted(branches, key=lambda b: cast(int, b.get('timestamp', 0)), reverse=True)[:limit]


def list_tags(repo: 'pygit2.Repository', limit: int = 20) -> List[Dict[str, Any]]:
    """List repository tags."""
    import pygit2

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
                    target = target.peel(pygit2.Commit)  # type: ignore[assignment]

                if isinstance(target, pygit2.Commit):
                    commit_target = cast('pygit2.Commit', target)
                    tags.append({
                        'name': tag_name,
                        'commit': str(commit_target.id)[:7],
                        'message': commit_target.message.split('\n')[0][:80],
                        'date': datetime.fromtimestamp(commit_target.commit_time).strftime('%Y-%m-%d'),
                        'timestamp': commit_target.commit_time,
                    })
            except (KeyError, pygit2.GitError, AttributeError):
                continue
    except Exception:
        pass  # return whatever tags were collected before the error

    return sorted(tags, key=lambda t: cast(int, t.get('timestamp', 0)), reverse=True)[:limit]
