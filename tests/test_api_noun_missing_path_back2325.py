"""The noun form of ``api.query`` raises a missing path as ``PathNotFoundError`` (ruling S7, D21, BACK-2325).

``api.query('ast', 'nope')`` raised the base ``RequestValidationError``: the declared route built the CLI's invalid
answer (exit 2, ``Path not found: nope``) without the error a library caller catches, while ``api.analyze`` and the
URI form raise ``PathNotFoundError`` (a ``RequestValidationError``, still a ``FileNotFoundError``) for the same path.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.errors import PathNotFoundError, RequestValidationError

NOUNS = [('ast', {}), ('calls', {'callers': 'f'}), ('imports', {}), ('markdown', {}), ('metrics', {})]


@pytest.fixture
def fx(tmp_path, monkeypatch):
    (tmp_path / 'd').mkdir()
    (tmp_path / 'd' / 'ok.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize('noun, controls', NOUNS)
def test_the_noun_form_raises_a_missing_path_as_path_not_found(fx, noun, controls):
    with pytest.raises(PathNotFoundError) as raised:
        api.query(noun, 'nope', **controls)
    assert str(raised.value) == 'Path not found: nope'
    assert isinstance(raised.value, FileNotFoundError)


@pytest.mark.parametrize('noun, controls', NOUNS)
def test_sibling_it_was_and_stays_the_request_error(fx, noun, controls):
    with pytest.raises(RequestValidationError, match='^Path not found: nope$'):
        api.query(noun, 'nope', **controls)


@pytest.mark.parametrize('noun, controls', NOUNS)
def test_sibling_the_cli_exits_2_with_that_message(fx, noun, controls):
    flags = [word for key, value in controls.items() for word in (f'--{key}', value)]
    run = _run_reveal_direct(noun, 'nope', *flags, '--format', 'json')
    assert run.returncode == 2
    assert json.loads(run.stdout)['error'] == 'Path not found: nope'


@pytest.mark.parametrize('noun, controls', NOUNS)
def test_control_an_existing_path_answers(fx, noun, controls):
    assert isinstance(api.query(noun, 'd', **controls), dict)


def test_control_an_unsupported_control_is_no_missing_path(fx):
    with pytest.raises(RequestValidationError) as raised:
        api.query('calls', 'd', callers='m.py:f')
    assert not isinstance(raised.value, FileNotFoundError)
