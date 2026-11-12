"""A result variant is allowed only for the declared primary operation type."""
import pytest

from reveal.cli.routing.declared import qualify_declared_answer
from reveal.utils.results import ResultBuilder


class Owner:
    RESULT_TYPE = 'detail'
    RESULT_TYPE_VARIANTS = {'detail': ('ambiguity',)}


@pytest.mark.parametrize('actual,expected,valid', [
    ('detail', 'detail', True), ('ambiguity', 'detail', True),
    ('other', 'detail', False), ('ambiguity', 'other', False),
])
def test_variants_are_scoped_to_primary_type(actual, expected, valid):
    answer = ResultBuilder.create(actual, 'resource', source_type='runtime')
    result = qualify_declared_answer(answer, Owner, 'resource', expected)
    assert (result is answer) is valid


def test_undeclared_variants_still_reject():
    class StrictOwner:
        RESULT_TYPE = 'detail'
    answer = ResultBuilder.create('ambiguity', 'resource', source_type='runtime')
    result = qualify_declared_answer(answer, StrictOwner, 'resource')
    assert result['type'] == 'detail'
    assert result['meta']['errors'][0]['code'] == 'invalid_adapter_answer'
