"""``api.query`` of a help page that names nothing raises with the CLI's teaching sentence (BACK-2787, D21).

``reveal help://ast/bogus`` exits 2 and says why: "Unknown section 'bogus'. Sections of ast: ...". The API returned the
error page as a dict until BACK-2788 made it raise ``RequestValidationError``; its message was still the bare label
``Invalid section``, because the help adapter declared no public diagnostic, so the API fell back to the result's
``error`` label (and MCP masked the page as an internal error, BACK-2798). D21: the API raises the CLI's own failure
meaning with the CLI's own message, on the URI form and the noun form alike.

Siblings: a page that exists still answers, and a topic that is no page at all (``help://nosuchtopic``, the element
miss) keeps its own message.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.errors import RequestValidationError

# (URI, noun-form topic, the start of the sentence the CLI teaches)
PAGES = [
    ('help://ast/bogus', 'ast/bogus', "Unknown section 'bogus'. Sections of ast:"),
    ('help://schemas/bogus', 'schemas/bogus', "No adapter named 'bogus'"),
]


def _cli_message(uri):
    """The CLI's exit and the sentence its JSON answer teaches (``message``)."""
    run = _run_reveal_direct(uri, '--format', 'json')
    return run.returncode, json.loads(run.stdout)['message']


@pytest.mark.parametrize('uri, topic, says', PAGES)
def test_the_uri_form_raises_with_the_clis_sentence(uri, topic, says):
    code, message = _cli_message(uri)
    assert code == 2 and message.startswith(says)
    with pytest.raises(RequestValidationError) as raised:
        api.query(uri)
    assert str(raised.value) == message


@pytest.mark.parametrize('uri, topic, says', PAGES)
def test_the_noun_form_raises_with_the_clis_sentence(uri, topic, says):
    _code, message = _cli_message(uri)
    with pytest.raises(RequestValidationError) as raised:
        api.query('help', topic)
    assert str(raised.value) == message


@pytest.mark.parametrize('argv', [('help://ast/bogus',), ('help', 'ast/bogus'), ('help://ast/bogus', '--format', 'json')])
def test_the_cli_says_the_sentence_once_as_its_error(argv):
    """The sentence is the answer's ``error`` (the CLI's error line), said once: the label ``Invalid section`` is gone
    from every transport, and the text page does not repeat the sentence under the error line."""
    run = _run_reveal_direct(*argv)
    assert run.returncode == 2
    lines = [line for line in run.stderr.splitlines() if line.strip()]
    assert lines[0].startswith("Error (help://): Unknown section 'bogus'. Sections of ast:")
    assert sum("Unknown section 'bogus'" in line for line in lines) == 1 and 'Invalid section' not in run.stderr
    if '--format' in argv:
        document = json.loads(run.stdout)
        assert document['error'] == document['message']


@pytest.mark.parametrize('call', [lambda: api.query('help://ast'), lambda: api.query('help', 'ast')])
def test_a_page_that_exists_still_answers(call):
    assert call()['type'] == 'static_guide'


def test_a_topic_that_is_no_page_keeps_its_own_message():
    with pytest.raises(RequestValidationError, match="Element 'nosuchtopic' not found"):
        api.query('help://nosuchtopic')
