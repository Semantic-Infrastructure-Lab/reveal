"""``PathNotFoundError`` (BACK-2325, D21): the one class for a path a request names that does not exist. It is a
``MissingResourceError`` (an invalid resource, exit 2, D6) and still the ``FileNotFoundError`` a library caller
catches, as ``UnsupportedOverrideError`` is still a ``TypeError``.

Shared owner: ``errors.py``. Effect on every noun and transport: none until an owner raises it. The URI router already
answers a ``MissingResourceError`` as an invalid request on a legacy operation too (``uri._call_adapter``), and MCP
reads an ``OSError``'s message as public, so the class is classified the same way on both. diff's private
``DiffTargetNotFoundError`` derives from it with the bases it had.
"""
import pytest

from reveal.adapters.diff.resolution import DiffTargetNotFoundError
from reveal.cli.routing.uri import _Answered, _call_adapter
from reveal.errors import MissingResourceError, PathNotFoundError, RequestValidationError
from reveal.utils.results import FailureCause

pytestmark = [pytest.mark.unit]


def test_a_missing_path_is_an_invalid_request_and_a_file_not_found_error():
    error = PathNotFoundError('Path not found: missing.py')
    for cls in (MissingResourceError, RequestValidationError, ValueError, FileNotFoundError, OSError):
        assert isinstance(error, cls), cls
    assert str(error) == 'Path not found: missing.py'
    with pytest.raises(FileNotFoundError):  # what a library caller catches today
        raise error


@pytest.mark.parametrize('classify_validation', [False, True])
def test_the_router_answers_it_as_an_invalid_request_on_every_operation(classify_validation):
    def call():
        raise PathNotFoundError('Path not found: missing.py')

    with pytest.raises(_Answered) as answered:
        _call_adapter(call, 'fake', 'missing.py', None, classify_validation=classify_validation)
    assert answered.value.result['error'] == 'Path not found: missing.py'
    assert answered.value.result['meta']['errors'][0]['code'] == 'invalid_request'
    assert isinstance(answered.value.request_error, PathNotFoundError)
    assert answered.value.execution_facts.failures == frozenset({FailureCause.INVALID_REQUEST})


def test_diff_target_not_found_keeps_its_bases():
    # Negative control: the private copy adopts the shared class without losing either base it had.
    error = DiffTargetNotFoundError('File not found: nope.py')
    assert isinstance(error, PathNotFoundError)
    assert isinstance(error, MissingResourceError) and isinstance(error, FileNotFoundError)
