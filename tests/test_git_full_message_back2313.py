"""Git message matching uses source messages, not display previews (BACK-2313)."""
import json

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.git.adapter import GitAdapter

pygit2 = pytest.importorskip('pygit2')


@pytest.fixture
def message_repo(tmp_path):
    repo = pygit2.init_repository(str(tmp_path))
    parent = []
    messages = ['long ' + 'x' * 110 + ' LATE_SUBJECT', 'short subject\n\nBODY_TOKEN details\n',
                'unrelated subject']
    for index, message in enumerate(messages):
        (tmp_path / 'sample.py').write_text(f'value = {index}\n', encoding='utf-8')
        repo.index.add('sample.py')
        repo.index.write()
        signature = pygit2.Signature('Reviewer', 'reviewer@example.com', 1700000000 + index, 0)
        oid = repo.create_commit('HEAD', signature, signature, message, repo.index.write_tree(), parent)
        parent = [oid]
    return tmp_path


@pytest.mark.parametrize('target,view', [('repo', ''), ('repo', 'type=history&'),
                                       ('file', 'type=history&'), ('repo', 'type=history&bucket=month&'),
                                       ('file', 'type=history&bucket=month&')])
@pytest.mark.parametrize('needle', ['LATE_SUBJECT', 'BODY_TOKEN'])
@pytest.mark.parametrize('entry', ['api', 'cli'])
def test_message_matches_beyond_display_subject(message_repo, target, view, needle, entry):
    path = message_repo / 'sample.py' if target == 'file' else message_repo
    query = view + f'message~={needle}'
    if entry == 'cli':
        result = run(f'git://{path}?{query}', '--format', 'json')
        assert result.returncode == 0, result.stderr
        answer = json.loads(result.stdout)
    else:
        answer = GitAdapter(str(path), query).get_structure()
    if 'bucket=' in view:
        assert answer['commit_count'] == 1
    else:
        rows = answer['history'] if 'history' in answer else answer['commits']
        rows = rows['recent'] if isinstance(rows, dict) else rows
        assert len(rows) == 1
        expected = ('long ' + 'x' * 110)[:100] if needle == 'LATE_SUBJECT' else 'short subject'
        assert rows[0]['message'] == expected
        assert set(rows[0]) == {'hash', 'author', 'email', 'date', 'timestamp', 'message'}


def test_unfiltered_display_and_negative_filter_are_unchanged(message_repo):
    answer = GitAdapter(str(message_repo), 'type=history').get_structure()
    assert [row['message'] for row in answer['history']] == [
        'unrelated subject', 'short subject', ('long ' + 'x' * 110)[:100]]
    assert not GitAdapter(str(message_repo), 'type=history&message~=NO_SUCH_TEXT').get_structure()['history']
