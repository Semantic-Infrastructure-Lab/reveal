"""A control that must not be given with another (BACK-2623, on the BACK-2656 ``requires`` seam).

``ParamSpec.requires`` already says "this control needs that one's value" (``churn=on``) or "needs one of those given"
(``pick|find``). A ``!name`` entry says "needs that one NOT given": two controls that set one thing in two ways that
never agree (surface's text-only legacy ``top`` and its answer cap ``limit``, which ``--all`` binds) are then one
generated refusal, exit 2 naming both, rather than a hand-written conflict check in the noun.
"""
import pytest

from reveal.errors import RequestValidationError
from reveal.utils.query_binding import bind_prepared_params, prepare_declared_params, reject_unread_controls
from reveal.utils.query_parser import ParamSpec

CAP = ParamSpec('cap', 'integer', 'the answer cap', None, int, minimum=0)
SHOWN = ParamSpec('shown', 'integer', 'a display-only cap', None, int, minimum=0, requires=('!cap',))
FREE = ParamSpec('free', 'string', 'needs nothing', None, str)
SPECS = (CAP, SHOWN, FREE)


def _check(query=None, **typed):
    if query is not None:
        params = bind_prepared_params(SPECS, prepare_declared_params(SPECS, query, 'uri'), transport='uri')
    else:
        params = bind_prepared_params(SPECS, prepare_declared_params(SPECS, typed, 'typed'), transport='typed')
    reject_unread_controls(SPECS, params, lambda: 'fixture')


@pytest.mark.parametrize('query', ['shown=1', 'cap=2', 'cap=0', 'shown=1&free=x', ''])
def test_either_control_alone_answers(query):
    _check(query)


@pytest.mark.parametrize('request_', [{'query': 'shown=1&cap=2'}, {'query': 'shown=2&cap=2'}, {'query': 'shown=1&cap=0'},
                                      {'shown': 1, 'cap': 0}])
def test_both_given_is_an_invalid_request_naming_both(request_):
    with pytest.raises(RequestValidationError, match=r"control 'shown' cannot be combined with 'cap'"):
        _check(**request_)


def test_a_typed_none_is_not_given():
    _check(shown=1, cap=None)


def test_the_entry_is_published_in_the_schema():
    assert SHOWN.schema()['requires'] == ['!cap']
