"""The binder omits a control given a typed ``None``: no key, not given, as if the request never named it (BACK-2779).

``apply_declared_overrides`` (the one place typed keywords meet a bound URI request, ``api.query``'s URI form) wrote a
typed ``None`` as a present key holding the declaration's default (``{'limit': None}``, patches ``{'limit': 20}``).
A reader that walks the bound keys then met a value no request gave: Metrics rendered ``limit=None`` into its control
query and raised ``limit must be a non-negative integer: 'None'``, Markdown echoed ``query: 'limit=None'``. An omitted
control leaves no key (``bind_declared_params``: "Omitted controls remain omitted"), so ``None`` does the same.

The original URI is still judged before the overrides, so ``None`` cannot hide an invalid ``?limit=-1``
(COMMAND_MODEL "Applicability", BACK-2692).
"""
import pytest

from reveal.adapters.base import get_adapter_class
from reveal.utils.query_binding import bind_declared_params, given_controls

NOUNS = ('metrics', 'ast', 'patches')


def _bind(noun, source, overrides):
    return bind_declared_params(get_adapter_class(noun).PARAM_SPECS, source, transport='uri', overrides=overrides)


def _has(params, key):
    return dict.__contains__(params, key)  # a routing check: QueryParams.__contains__ would record a read


@pytest.mark.parametrize('noun', NOUNS)
@pytest.mark.parametrize('source', ['', 'limit=1'])
def test_a_typed_none_omits_the_control(noun, source):
    params = _bind(noun, source, {'limit': None})
    assert not _has(params, 'limit')
    assert 'limit' not in given_controls(params) and params.declaration('limit') is None


@pytest.mark.parametrize('noun', NOUNS)
def test_none_binds_as_the_request_that_never_named_it(noun):
    assert dict(_bind(noun, '', {'limit': None})) == dict(_bind(noun, '', None))


@pytest.mark.parametrize('noun', NOUNS)
def test_a_typed_value_is_still_a_given_control(noun):
    params = _bind(noun, 'limit=1', {'limit': 3})
    assert dict.__getitem__(params, 'limit') == 3 and 'limit' in given_controls(params)


def test_a_none_beside_another_override_leaves_that_one():
    params = _bind('metrics', '', {'limit': None, 'offset': 2})
    assert not _has(params, 'limit') and dict.__getitem__(params, 'offset') == 2


def test_an_invalid_original_still_raises_under_none():
    with pytest.raises(ValueError, match='limit'):
        _bind('ast', 'limit=-1', {'limit': None})
