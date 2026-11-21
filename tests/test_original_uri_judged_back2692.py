"""BACK-2692: an api.query override cannot hide an invalid request: the URI is judged as a request of its own before\nthe typed overrides, on every declared noun that declares applicability (one check, in the factory)."""
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


def test_an_override_that_selects_an_answer_reading_the_control_does_not_make_the_original_valid(src):
    with pytest.raises(RequestValidationError):
        api.query(f'metrics://{src}?top=3', view='hotspots')  # the URI alone is invalid; give both as overrides


def test_a_valid_uri_an_override_changes_is_an_ordinary_override(src):
    assert api.query(f'metrics://{src}?view=hotspots&top=3', top=None)['type']
