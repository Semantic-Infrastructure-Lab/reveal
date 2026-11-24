"""``api.query`` typed keywords bind through every declared noun's declarations (BACK-2656, Step 2c finding).

A noun whose own ``PARAM_SPECS`` declares its controls answers ``api.query(URI, control=value)`` exactly as the URI
spelling ``URI?control=value``: the keyword binds through the same binder and meets the same checks (unsupported
control, applicability) before the adapter is built. Deps, Hotspots, Pack, Patches and Testability declared their
controls but not ``BOUND_QUERY_CALL``, so their keywords went to ``get_structure(**kwargs)``: Deps and Patches dropped
them in silence, Hotspots, Pack and Testability raised ``TypeError`` (unexpected keyword argument).
"""
import json

import pytest

from reveal import api
from reveal.errors import RequestValidationError


@pytest.fixture
def proj(tmp_path, monkeypatch):
    (tmp_path / 'app.py').write_text('import os\nimport helper\n\n\ndef serve(x):\n    if x:\n        if x > 1:\n'
                                     '            return os.getcwd()\n    return helper.VALUE\n', encoding='utf-8')
    (tmp_path / 'helper.py').write_text('import app\n\nVALUE = 1\n', encoding='utf-8')
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'test_app.py').write_text(
        'from unittest import mock\n\nimport app\n\n\n' + ''.join(
            f"def test_{index}():\n    with mock.patch('app.os.getcwd'):\n        assert app.serve(2)\n\n\n"
            for index in range(3)), encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _answer(uri, **keywords):
    result = json.loads(json.dumps(api.query(uri, **keywords), default=str))
    result.pop('execution', None)
    (result.get('meta') or {}).pop('timing', None)
    return result


@pytest.mark.parametrize('uri,keywords,query', [
    ('deps://.', {'no_circular': True}, 'no_circular=true'),            # dropped in silence before
    ('patches://tests', {'group': 'file'}, 'group=file'),               # dropped in silence before
    ('hotspots://.', {'files_only': True}, 'files_only=true'),          # TypeError before
    ('pack://.', {'budget': 100}, 'budget=100'),                        # TypeError before
    ('testability://.', {'test_paths': ['tests']}, 'test-paths=tests'),  # TypeError before (a typed array)
])
def test_a_typed_keyword_answers_as_its_uri_spelling(proj, uri, keywords, query):
    keyword = _answer(uri, **keywords)
    assert keyword == _answer(f'{uri}?{query}')
    assert keyword != _answer(uri), 'the control must change this answer, or the comparison proves nothing'


@pytest.mark.parametrize('uri,keywords,control', [
    ('patches://tests', {'min_patches': 2}, 'where'),  # the legacy word is where's term (BACK-2625)
])
def test_a_typed_keyword_meets_the_applicability_check(proj, uri, keywords, control):
    with pytest.raises(RequestValidationError, match=f"control '{control}' is not read by this answer"):
        api.query(uri, **keywords)


def test_a_second_view_is_a_conflict_not_an_unread_control(proj):
    with pytest.raises(ValueError, match='view: conflicting spellings'):
        api.query('patches://.', view='pressure', group='file')


@pytest.mark.parametrize('uri', ['deps://.', 'patches://tests', 'hotspots://.', 'pack://.', 'testability://.'])
def test_an_undeclared_keyword_is_still_the_unsupported_control_error(proj, uri):
    with pytest.raises((TypeError, ValueError), match="unsupported control 'bogus'"):
        api.query(uri, bogus=1)
