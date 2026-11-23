"""``ElementNotFoundError`` (BACK-2214): an adapter whose structure call answers an element its resource names
(``diff://a.py:b.py/nope``) raises it for a name that is not there, and the router answers it as every element miss:
exit 2, code ``element_not_found``, the adapter's names in ``available_elements`` and, in text, on stderr
(``uri._fail_element_not_found``). It answered "Element 'nope' not found" with no names.

Shared owners: ``errors.py`` (the class, a ``MissingResourceError``, so ``api.query`` raises it as an invalid request)
and ``cli/routing/uri._call_adapter``. Effect on every noun: only an adapter that raises the new class (diff) changes;
a plain ``MissingResourceError`` is the invalid request it was, with no names.
"""
import pytest

from reveal.cli.routing.uri import _Answered, _call_adapter
from reveal.errors import ElementNotFoundError, MissingResourceError, RequestValidationError
from reveal.utils.results import FailureCause

pytestmark = [pytest.mark.unit]


class _Adapter:
    def __init__(self, error):
        self.error = error

    def get_structure(self):
        raise self.error

    def list_elements(self):
        return ['ok', 'only_left']


def _answered(error, *, adapter=True):
    instance = _Adapter(error)
    with pytest.raises(_Answered) as answered:
        _call_adapter(instance.get_structure, 'fake', 'a:b/nope', _Adapter, classify_validation=True,
                      adapter=instance if adapter else None)
    return answered.value


def test_an_element_miss_lists_the_adapters_names():
    answered = _answered(ElementNotFoundError('nope'))
    assert answered.result['error'] == "Element 'nope' not found"
    assert answered.result['available_elements'] == ['ok', 'only_left']
    assert [e['code'] for e in answered.result['meta']['errors']] == ['element_not_found']
    assert answered.execution_facts.failures == frozenset({FailureCause.INVALID_REQUEST})


def test_without_the_adapter_it_is_still_the_invalid_request():
    answered = _answered(ElementNotFoundError('nope'), adapter=False)
    assert 'available_elements' not in answered.result
    assert answered.execution_facts.failures == frozenset({FailureCause.INVALID_REQUEST})


def test_a_plain_missing_resource_is_unchanged():
    answered = _answered(MissingResourceError('File not found: a.py'))
    assert 'available_elements' not in answered.result
    assert [e['code'] for e in answered.result['meta']['errors']] == ['invalid_request']


def test_it_is_an_invalid_request_to_the_api():
    error = ElementNotFoundError('nope')
    assert isinstance(error, MissingResourceError) and isinstance(error, RequestValidationError)
    assert error.element == 'nope' and str(error) == "Element 'nope' not found"
