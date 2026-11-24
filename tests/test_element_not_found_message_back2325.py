"""ElementNotFoundError says the miss as its raiser words it, and keeps saying it when copied (BACK-2325).

The path read's miss is ``Element 'nosuch' not found in ok.py`` (or ``No element #3 found in ok.py``): the Python API
raises the CLI's message, so the error takes it. An Answer keeps a copy of the request's error (``uri._detached``,
``copy.copy``), which rebuilt the error from its message as if the message were the element name: the copy of
``ElementNotFoundError('nope')`` said ``Element 'Element 'nope' not found' not found``.
"""
import copy
import pickle

import pytest

from reveal.errors import ElementNotFoundError, MissingResourceError

pytestmark = [pytest.mark.unit]


@pytest.mark.parametrize('given, text', [
    (('nope',), "Element 'nope' not found"),
    (('@3', 'No element #3 found in ok.py'), 'No element #3 found in ok.py'),
], ids=['default', 'message'])
def test_a_copy_and_a_pickle_say_what_the_error_says(given, text):
    error = ElementNotFoundError(*given)
    for kept in (copy.copy(error), pickle.loads(pickle.dumps(error))):
        assert type(kept) is ElementNotFoundError and isinstance(kept, MissingResourceError)
        assert str(kept) == str(error) == text
        assert kept.element == error.element


def test_sibling_the_default_message_names_the_element():
    error = ElementNotFoundError('nope')
    assert str(error) == "Element 'nope' not found" and error.element == 'nope'
