"""Opt-in URI value decoding happens after query structure, before value grammar."""
import pytest

from reveal.utils.query_parser import parse_query_filters


def decoded(query):
    return [(q.field, q.op, q.value) for q in parse_query_filters(query, percent_decode_values=True)]


@pytest.mark.parametrize('query,expected', [
    ('message=hello%20world', [('message', '=', 'hello world')]),
    ('message=a%26b%3Dc&author=Jane%20Doe', [('message', '=', 'a&b=c'), ('author', '=', 'Jane Doe')]),
    ('message=a+b%2Bc', [('message', '=', 'a+b+c')]),
    ('message=%2520%25', [('message', '=', '%20%')]),
    ('message=%E2%9C%93', [('message', '=', '✓')]),
    ('message=%20padded%20', [('message', '=', ' padded ')]),
    ('name=%2Aworker%2A', [('name', '*', '*worker*')]),
    ('lines=2%2E%2E5', [('lines', '..', '2..5')]),
    ('lines>%31', [('lines', '>', True)]),
    ('message~=%5Ea%5C%2Bb%24', [('message', '~=', r'^a\+b$')]),
    ('message~=a%26b&message~=c%3Dd', [('message', '~=', 'a&b'), ('message', '~=', 'c=d')]),
])
def test_decoding_preserves_query_structure_and_existing_value_semantics(query, expected):
    assert decoded(query) == expected


def test_default_raw_policy_is_unchanged():
    query = 'message=a%26b%20c&name=%2Aworker%2A'
    expected = [('message', '=', 'a%26b%20c'), ('name', '=', '%2Aworker%2A')]
    assert [(q.field, q.op, q.value) for q in parse_query_filters(query)] == expected


def test_explicit_false_keeps_raw_values():
    assert [(q.field, q.op, q.value) for q in parse_query_filters(
        'message=a%26b%20c', percent_decode_values=False)] == [('message', '=', 'a%26b%20c')]


def test_only_values_are_decoded_once():
    assert decoded('mes%73age=%2526') == [('mes%73age', '=', '%26')]
    assert decoded('message=%ZZ') == [('message', '=', '%ZZ')]


def test_decoded_regex_is_validated():
    with pytest.raises(ValueError):
        decoded('message~=%5B')


def test_invalid_utf8_is_rejected_instead_of_replaced():
    with pytest.raises(UnicodeDecodeError):
        decoded('message=%FF')
