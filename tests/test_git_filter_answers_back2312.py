"""Git filters preserve every requested condition (BACK-2312)."""
import json

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.git.adapter import GitAdapter

pygit2 = pytest.importorskip('pygit2')


@pytest.fixture
def history_repo(tmp_path):
    repo = pygit2.init_repository(str(tmp_path))
    parent = []
    for index, message in enumerate(('feat: one', 'feat: fix two', 'chore: fix three')):
        (tmp_path / 'sample.py').write_text(f'value = {index}\n', encoding='utf-8')
        repo.index.add('sample.py')
        repo.index.write()
        signature = pygit2.Signature('Reviewer', 'reviewer@example.com', 1700000000 + index, 0)
        oid = repo.create_commit('HEAD', signature, signature, message, repo.index.write_tree(), parent)
        parent = [oid]
    return tmp_path


@pytest.mark.parametrize('conditions', ['message~=feat&message~=fix', 'message~=fix&message~=feat'])
@pytest.mark.parametrize('entry', ['inline', 'query', 'cli'])
def test_repeated_message_filters_and_in_both_orders(history_repo, conditions, entry):
    query = f'type=history&{conditions}'
    if entry == 'cli':
        result = run(f'git://{history_repo}?{query}', '--format', 'json')
        assert result.returncode == 0, result.stderr
        answer = json.loads(result.stdout)
    elif entry == 'query':
        answer = GitAdapter(str(history_repo), query).get_structure()
    else:
        answer = GitAdapter(f'{history_repo}?{query}').get_structure()
    assert [row['message'] for row in answer['history']] == ['feat: fix two']


def test_single_filter_and_unrelated_operational_controls(history_repo):
    answer = GitAdapter(str(history_repo), 'type=history&message~=feat&limit=1').get_structure()
    assert [row['message'] for row in answer['history']] == ['feat: fix two']
    assert len(GitAdapter(str(history_repo), 'type=history').get_structure()['history']) == 3


@pytest.mark.parametrize('query', ['type=history&message~=feat&message~=fix',
                                  {'type': 'history', 'message~': 'feat: fix'}])
def test_explicit_query_replaces_inline_occurrences_of_same_raw_key(history_repo, query):
    answer = GitAdapter(f'{history_repo}?message~=chore&message~=missing', query).get_structure()
    assert [row['message'] for row in answer['history']] == ['feat: fix two']


def test_overlay_retains_other_inline_filters_and_operational_last_value(history_repo):
    answer = GitAdapter(f'{history_repo}?type=history&author~=Reviewer&limit=2',
                        'message~=feat&message~=fix&limit=7&limit=1').get_structure()
    assert [row['message'] for row in answer['history']] == ['feat: fix two']
    assert GitAdapter(str(history_repo), 'type=history&limit=2&limit=1').result_control.limit == 1


def test_repeated_since_aliases_and_date_conditions(history_repo):
    adapter = GitAdapter(str(history_repo), 'type=history&since=2020&since=2021&date<2025')
    assert [(q.field, q.op, q.value) for q in adapter.query_filters] == [
        ('date', '>=', 2020), ('date', '>=', 2021), ('date', '<', 2025)]
    assert len(adapter.get_structure()['history']) == 3


def test_repeated_unknown_filter_is_reported_once(history_repo):
    result = run(f'git://{history_repo}?type=history&authr~=a&authr~=b', '--format', 'json')
    body = json.loads(result.stdout)
    warnings = [w for w in body['meta']['warnings'] if w['type'] == 'unknown_filter_field']
    assert len(warnings) == 1
    assert warnings[0]['message'].count("'authr'") == 1
    assert 'has no effect' not in result.stderr
