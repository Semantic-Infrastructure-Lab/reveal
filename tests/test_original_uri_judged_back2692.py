"""BACK-2692: an api.query override cannot hide an inapplicable control of the ORIGINAL URI, on every declared noun
that declares applicability (the check runs once, in the factory, before the overrides bind)."""
import pytest

from reveal import api
from reveal.errors import RequestValidationError


@pytest.fixture
def src(tmp_path):
    (tmp_path / 'app.py').write_text('def go():\n    return 1\n', encoding='utf-8')
    return tmp_path


def test_override_none_does_not_hide_an_unread_uri_control(src):
    uri = f'metrics://{src / "app.py"}?top=3'
    with pytest.raises(RequestValidationError):
        api.query(uri)  # the effective request already refuses it
    with pytest.raises(RequestValidationError):
        api.query(uri, top=None)  # the override must not launder it


def test_an_applicable_original_with_an_override_still_answers(src):
    assert api.query(f'metrics://{src}', limit=1)['type']


def test_an_override_that_makes_the_control_applicable_still_refuses_the_original(src):
    with pytest.raises(RequestValidationError):
        api.query(f'metrics://{src / "app.py"}?top=3', view='hotspots')
