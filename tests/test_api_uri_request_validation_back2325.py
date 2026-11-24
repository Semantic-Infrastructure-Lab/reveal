"""``api.query(URI)`` refuses what the noun's request validation refuses, as the CLI does (D21, BACK-2325).

The CLI's declared route runs each noun's ``validate_request`` on the bound request before the adapter answers; the
Python API's URI form did not. So ``api.query('patches://proj?view=pressure&tests=nope')`` (and testability's) raised
``NotApplicableError`` ("none of the tests= paths exist") where ``reveal`` exits 2 with ``Test path not found: nope``,
and calls' ``callers=FILE:NAME`` raised a plain ``ValueError``. The URI form now runs the same validation (the
declared route's ``_validate_bound_request``) and raises ``RequestValidationError`` with the CLI's message.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.errors import NotApplicableError, RequestValidationError

TEST_PY = 'from unittest import mock\n\n\ndef test_f():\n    with mock.patch("m.f"):\n        pass\n'
REFUSED = [
    ('patches://proj?view=pressure&tests=nope', 'Test path not found: nope'),
    ('testability://proj?tests=nope', 'Test path not found: nope'),
]


@pytest.fixture
def fx(tmp_path, monkeypatch):
    (tmp_path / 'proj' / 'tests').mkdir(parents=True)
    (tmp_path / 'proj' / 'm.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'proj' / 'tests' / 'test_m.py').write_text(TEST_PY, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize('uri, message', REFUSED)
def test_the_uri_form_raises_the_clis_invalid_request(fx, uri, message):
    with pytest.raises(RequestValidationError, match=message) as raised:
        api.query(uri)
    assert not isinstance(raised.value, NotApplicableError)


@pytest.mark.parametrize('uri, message', REFUSED)
def test_sibling_the_cli_exits_2_with_that_message(fx, uri, message):
    run = _run_reveal_direct(uri, '--format', 'json')
    assert run.returncode == 2
    assert json.loads(run.stdout)['error'] == message


def test_sibling_the_noun_form_already_raised_it(fx):
    with pytest.raises(RequestValidationError, match='Test path not found: nope'):
        api.query('patches', 'proj', view='pressure', tests='nope')


def test_control_an_existing_test_root_answers(fx):
    assert api.query('patches://proj?view=pressure&tests=proj/tests')['type'] == 'testability_report'


def test_a_plain_value_error_of_validation_is_the_request_error(fx):
    """calls' validation raises a plain ValueError; the CLI answers it as an invalid request, so does the API."""
    with pytest.raises(RequestValidationError, match='callers takes a bare NAME'):
        api.query('calls://proj?callers=m.py:f')
