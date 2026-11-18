"""Applicability (COMMAND_MODEL "Applicability", BACK-2656): a control the selected answer does not read is an invalid
request, refused before analysis on every transport.

An answer is named by its predicted result type and by the selection that picks it (an operation's name,
``name=value``, or ``default``); a control declares the answers that read it in ``ParamSpec.answers`` (empty: every
answer). The shared check is ``query_binding.reject_unread_controls``; only the data can tell for a few controls, and
those answer with the one shared ``control_unread_by_data`` warning (Scott 2026-11-18, Q2).
"""
import pytest

from reveal.errors import RequestValidationError
from reveal.utils.query_binding import (answer_facets, apply_declared_overrides, bind_prepared_params,
                                        prepare_declared_params, reject_unread_controls, unread_by_data_warning)
from reveal.utils.query_parser import ParamSpec, collect_query_keys

VIEW = ParamSpec('view', 'string', 'answer', None, str, choices=('a', 'b'), role='operation')
MODE = ParamSpec('mode', 'boolean', 'a legacy answer', False, lambda v: str(v).lower() in ('1', 'true', ''),
                 role='operation')
ALPHA = ParamSpec('alpha', 'integer', 'read by view=a only', None, int, answers=('view=a',))
GAMMA = ParamSpec('gamma', 'integer', 'read by the fixture_b answer only', None, int, answers=('fixture_b',))
DELTA = ParamSpec('delta', 'integer', 'read by the default answer and mode', None, int, answers=('default', 'mode'))
BETA = ParamSpec('beta', 'integer', 'read by every answer', None, int)
SPECS = (VIEW, MODE, ALPHA, GAMMA, DELTA, BETA)


def _uri(query):
    params = prepare_declared_params(SPECS, query, 'uri')
    return bind_prepared_params(SPECS, params, transport='uri')


def _type(params):
    return 'fixture_b' if params.get('view') == 'b' else 'fixture_a'


def _check(params):
    reject_unread_controls(SPECS, params, lambda: _type(params))


def test_an_answer_is_named_by_its_type_and_its_selection():
    assert answer_facets(SPECS, _uri(''), 'fixture_a') == ('fixture_a', 'default')
    assert answer_facets(SPECS, _uri('view=b'), 'fixture_b') == ('fixture_b', 'view', 'view=b')
    assert answer_facets(SPECS, _uri('mode=true'), 'fixture_a') == ('fixture_a', 'mode')
    assert answer_facets(SPECS, _uri('mode=false'), 'fixture_a') == ('fixture_a', 'default')  # a switch that is off


@pytest.mark.parametrize('query', ['view=a&alpha=1', 'view=b&gamma=1', 'delta=1', 'mode&delta=1', 'view=a&beta=1',
                                   'view=b&beta=1', 'beta=1', ''])
def test_a_control_on_an_answer_that_reads_it_answers(query):
    _check(_uri(query))


@pytest.mark.parametrize('query,control,read_by,reads', [
    ('view=b&alpha=1', 'alpha', 'view=a', 'gamma, beta'),       # named by selection
    ('alpha=1', 'alpha', 'view=a', 'delta, beta'),              # the default answer
    ('view=a&gamma=1', 'gamma', 'fixture_b', 'alpha, beta'),    # named by type
    ('view=a&delta=1', 'delta', 'default, mode', 'alpha, beta'),
])
def test_a_control_the_answer_does_not_read_is_an_invalid_request(query, control, read_by, reads):
    with pytest.raises(RequestValidationError) as raised:
        _check(_uri(query))
    message = str(raised.value)
    assert message.startswith(f"control '{control}' is not read by this answer ("), message
    assert f'; {control} is read by: {read_by}; controls this answer reads: {reads}' in message, message


def test_several_unread_controls_are_named_together():
    with pytest.raises(RequestValidationError, match="controls 'alpha', 'gamma' are not read by this answer "
                                                     r"\(fixture_a, default\); alpha is read by: view=a; gamma"):
        _check(_uri('alpha=1&gamma=2'))


def test_the_answer_is_predicted_only_when_a_given_control_declares_answers():
    def unreachable():
        raise AssertionError('predicted although no given control declares its answers')
    for query in ('', 'beta=1', 'view=b&beta=1'):
        reject_unread_controls(SPECS, _uri(query), unreachable)


def test_an_omitted_typed_control_and_a_none_override_are_not_given():
    typed = prepare_declared_params(SPECS, {'view': 'b', 'alpha': None}, 'typed')  # an omitted flag arrives as None
    _check(bind_prepared_params(SPECS, typed, transport='typed'))
    with pytest.raises(RequestValidationError, match="'alpha' is not read"):
        _check(bind_prepared_params(SPECS, prepare_declared_params(SPECS, {'view': 'b', 'alpha': 3}, 'typed'),
                                    transport='typed'))
    uri = _uri('view=b&alpha=1')
    _check(apply_declared_overrides(SPECS, uri, {'alpha': None}))  # None selects the declared default
    with pytest.raises(RequestValidationError, match="'alpha' is not read"):
        _check(apply_declared_overrides(SPECS, _uri('view=b'), {'alpha': 2}))


def test_the_declaration_is_published_in_the_schema():
    assert ALPHA.schema()['answers'] == ['view=a']
    assert 'answers' not in BETA.schema()


def test_a_control_only_the_data_shows_unread_is_one_shared_warning_that_counts_as_its_read():
    with collect_query_keys() as log:
        params = _uri('beta=1')
        warning = unread_by_data_warning(params, ['beta', 'beta'], 'the value at this path is not a list')
    assert warning == {'type': 'control_unread_by_data', 'code': 'control_unread_by_data', 'fields': ['beta'],
                       'message': "'beta' has no effect on this data: the value at this path is not a list"}
    assert 'beta' in log.used
    assert unread_by_data_warning(params, [], 'x') is None
