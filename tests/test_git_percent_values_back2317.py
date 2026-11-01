"""Git percent-escaped filter values preserve delimiters and decode once."""
import json
from urllib.parse import quote

import pytest

from conftest import _run_reveal_direct as run
from reveal import api
from reveal.adapters.git.adapter import GitAdapter

pygit2 = pytest.importorskip('pygit2')
MESSAGES = ['hello world', 'a&b=c', 'a+b', 'a b', 'literal %20', '100%', '✓ value', 'regex [x].', ' padded ']


@pytest.fixture
def encoded_repo(tmp_path):
    repo = pygit2.init_repository(str(tmp_path))
    parents = []
    for index, message in enumerate(MESSAGES):
        (tmp_path / 'sample.py').write_text(f'value = {index}\n', encoding='utf-8')
        repo.index.add('sample.py')
        signature = pygit2.Signature('Jane Doe', 'jane@example.com', 1700000000 + index, 0)
        parents = [repo.create_commit('HEAD', signature, signature, message, repo.index.write_tree(), parents)]
    return tmp_path


def answer_for(root, query, entry):
    if entry == 'cli':
        result = run(f'git://{root}?type=history&{query}', '--format', 'json')
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    if entry == 'api':
        return api.query(f'git://{root}?type=history&{query}')
    return GitAdapter(str(root), f'type=history&{query}').get_structure()


@pytest.mark.parametrize('message', [message for message in MESSAGES if message != 'regex [x].'])
@pytest.mark.parametrize('entry', ['adapter', 'api', 'cli'])
def test_encoded_exact_values_match_source_messages(encoded_repo, message, entry):
    answer = answer_for(encoded_repo, 'message=' + quote(message, safe=''), entry)
    assert [row['message'] for row in answer['history']] == [message]


def test_regex_decodes_after_operators_and_validates_pattern(encoded_repo):
    answer = answer_for(encoded_repo, 'message~=%5Eregex%20%5C%5Bx%5C%5D%5C%2E%24', 'adapter')
    assert [row['message'] for row in answer['history']] == ['regex [x].']
    with pytest.raises(ValueError):
        GitAdapter(str(encoded_repo), 'type=history&message~=%5B')


def test_encoded_glob_and_repeated_filters_use_decoded_values(encoded_repo):
    answer = answer_for(encoded_repo, 'message=%2A%26%2A&message~=%3Dc', 'cli')
    assert [row['message'] for row in answer['history']] == ['a&b=c']


def test_encoded_bare_operator_and_author(encoded_repo):
    answer = answer_for(encoded_repo, 'timestamp>170000000%35&timestamp<170000000%37&author=Jane%20Doe', 'adapter')
    assert [row['message'] for row in answer['history']] == ['✓ value']


def test_encoded_inline_overlay(encoded_repo):
    answer = GitAdapter(f'{encoded_repo}?type=history&message=nope', {'message': 'a%26b%3Dc'}).get_structure()
    assert [row['message'] for row in answer['history']] == ['a&b=c']


def test_literal_plus_is_not_form_decoded_and_unencoded_sibling_keeps_meaning(encoded_repo):
    answer = answer_for(encoded_repo, 'message=a+b', 'cli')
    assert [row['message'] for row in answer['history']] == ['a+b']
    answer = answer_for(encoded_repo, 'message=hello world&limit=1', 'adapter')
    assert [row['message'] for row in answer['history']] == ['hello world']


def test_decoded_numeric_range_keeps_range_semantics(encoded_repo):
    answer = answer_for(encoded_repo, 'timestamp=1700000000%2E%2E1700000001', 'cli')
    assert [row['message'] for row in answer['history']] == ['a&b=c', 'hello world']


def test_invalid_utf8_fails_instead_of_silently_missing(encoded_repo):
    with pytest.raises(UnicodeDecodeError):
        GitAdapter(str(encoded_repo), 'type=history&message=%FF')
