"""~= and !~ honor the adapter's case_sensitive option like = and * do (BACK-2279)."""
import pytest

from reveal.utils.query_eval import compare_values

INSENSITIVE = {'case_sensitive': False}
SENSITIVE = {'case_sensitive': True}


@pytest.mark.parametrize('op,expected', [('~=', True), ('!~', False)])
def test_insensitive_regex_ignores_case(op, expected):
    assert compare_values('Nora', op, 'nora', INSENSITIVE) is expected


@pytest.mark.parametrize('op,expected', [('~=', False), ('!~', True)])
def test_sensitive_regex_respects_case(op, expected):
    assert compare_values('Nora', op, 'nora', SENSITIVE) is expected


def test_default_is_insensitive_like_equality():
    assert compare_values('Nora', '=', 'nora') is True
    assert compare_values('Nora', '~=', 'nora') is True
