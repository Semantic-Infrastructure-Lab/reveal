"""Git declaration foundation: API controls must reach the existing query owners."""
import pytest

from reveal.api import query

pygit2 = pytest.importorskip('pygit2')


@pytest.fixture
def repo_path(tmp_path):
    repo = pygit2.init_repository(str(tmp_path))
    parent = []
    for i in range(3):
        (tmp_path / 'code.py').write_text(f'def answer():\n    return {i}\n', encoding='utf-8')
        repo.index.add('code.py')
        repo.index.write()
        sig = pygit2.Signature('Scott', 'scott@example.com', 1700000000 + i, 0)
        parent = [repo.create_commit('HEAD', sig, sig, f'change {i}', repo.index.write_tree(), parent)]
    return tmp_path


def test_typed_view_and_zero_limit_override_uri(repo_path):
    uri = f'git://{repo_path}?type=history&limit=1'
    assert len(query(uri)['history']) == 1
    result = query(uri, view='history', limit=0)
    assert result['history'] == []
    assert len(query(uri)['history']) == 1


def test_typed_repeated_where_uses_existing_commit_predicates(repo_path):
    uri = f'git://{repo_path}?type=history'
    result = query(uri, where=['message~=change', 'timestamp>1700000000', 'timestamp<1700000002'])
    assert [c['message'] for c in result['history']] == ['change 1']


def test_canonical_uri_and_typed_controls_match(repo_path):
    a = query(f'git://{repo_path}?view=history&where=message%3Dchange%202')
    b = query(f'git://{repo_path}', view='history', where=['message=change 2'])
    assert a == b and len(a['history']) == 1


def test_typed_raw_detail_reaches_historical_file_owner(repo_path):
    result = query(f'git://{repo_path}/code.py@HEAD~1', detail='raw')
    assert result['type'] == 'git_file' and 'return 1' in result['content']


def test_typed_false_and_original_uri_validation(repo_path):
    with pytest.raises(ValueError):
        query(f'git://{repo_path}?limit=-1', limit=1)
    with pytest.raises(ValueError):
        query(f'git://{repo_path}?view=history&type=blame')
    with pytest.raises(TypeError):
        query(f'git://{repo_path}', misspelled_control=True)


def test_positive_merge_policy_and_legacy_ownership_scope(repo_path):
    repo = pygit2.Repository(str(repo_path))
    head = repo.head.target
    sig = pygit2.Signature('Scott', 'scott@example.com', 1700000010, 0)
    side = repo.create_commit(None, sig, sig, 'side', repo.head.peel().tree.id, [head])
    repo.create_commit('HEAD', sig, sig, 'merge', repo.head.peel().tree.id, [head, side])
    uri = f'git://{repo_path}?view=history'
    whole = query(uri)
    without = query(uri, merges=False)
    assert len(without['history']) == len(whole['history']) - 1
    assert query(uri + '&merges=off') == without
    assert query(uri, merges=True) == whole
    assert query(uri + '&merges=1') == whole  # existing ownership-only legacy spelling


def test_repeated_time_aliases_and_original_regex_validation(repo_path):
    uri = f'git://{repo_path}?view=history'
    result = query(uri + '&since=2023&since=2023-11-15')
    assert result['history'] == []
    with pytest.raises(ValueError, match='regular expression'):
        query(uri + '&message~=[', where=['message=change 1'])


def test_diff_content_predicate_stays_on_existing_pickaxe_owner(repo_path):
    uri = f'git://{repo_path}/code.py?type=history'
    legacy = query(uri + '&content~=return 1')
    canonical = query(uri, where=['content~=return 1'])
    assert canonical == legacy
    assert [c['message'] for c in canonical['commits']] == ['change 2', 'change 1']


def test_none_overrides_restore_omitted_defaults(repo_path):
    uri = f'git://{repo_path}?view=history&limit=1&since=2024'
    result = query(uri, limit=None, since=None)
    assert len(result['history']) == 3
    assert query(f'git://{repo_path}?view=history', view=None)['type'] == 'git_repository'
