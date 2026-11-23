"""``api.query('help://TOPIC')`` answers the topic, as ``reveal help://TOPIC`` does (BACK-2764, pathread P1 B5).

The CLI router reads help's resource as the topic (an element-namespace adapter); the API called the structure, which
ignored its resource, so every topic (``help://quick``, ``help://ast``) and a topic that does not exist answered the
help index. A topic that does not exist is the invalid request the CLI exits 2 on (``RequestValidationError``).
Controls: the bare ``help://`` stays the index; the element-argument form ``api.query('help://', 'quick')`` keeps
answering the topic.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from conftest import _run_reveal_direct  # noqa: E402

from reveal import api  # noqa: E402
from reveal.errors import RequestValidationError  # noqa: E402

TOPICS = ['quick', 'ast', 'ast/workflows', 'schemas/ast', 'examples', 'search?search=nav&top=3']


def _cli(uri):
    run = _run_reveal_direct(uri, '--format', 'json')
    return run.returncode, json.loads(run.stdout)


def _without_meta(document):
    return {key: value for key, value in document.items() if key != 'meta'}


@pytest.mark.parametrize('topic', TOPICS)
def test_api_answers_the_topic_the_uri_names(topic):
    code, cli = _cli(f'help://{topic}')
    assert code == 0
    answer = api.query(f'help://{topic}')
    assert answer['type'] == cli['type'] != 'help', (answer['type'], cli['type'])
    assert _without_meta(answer) == _without_meta(cli)


def test_a_topic_that_does_not_exist_is_an_invalid_request():
    code, cli = _cli('help://no-such-topic')
    assert code == 2
    with pytest.raises(RequestValidationError, match="no-such-topic"):
        api.query('help://no-such-topic')


def test_the_bare_uri_is_still_the_index():
    assert api.query('help://')['type'] == 'help'


def test_the_element_argument_form_still_answers_the_topic():
    assert api.query('help://', 'quick')['type'] == 'help_quick'
