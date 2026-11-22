"""The shared time-window codec, as a unit (utils/time_window.py; COMMAND_MODEL "Time window", BACK-2728).

The behaviour on every noun and transport is conformance column 25 and tests/test_time_window_back2728.py.
"""
import re
from datetime import date, datetime

import pytest

from reveal.utils.query_binding import bind_declared_params
from reveal.utils.query_parser import ParamSpec, ParamValueError
from reveal.utils.time_window import (FORMS, PERIOD, ZONED, bound_start, is_time_bound, resolve_today, time_bound,
                                      time_window_param)

VALID = ('2020-01-01', '2030-01-01', 'today', '2026-01-01', '2023-11-15', '2021', '2020', '2026-01',
         '2026-01-15T14:00:00.50+02:00', '2026-01-15T00:00:00.1234-1200', '2026-01-15T12:00:00Z', '2099-01-01',
         '1900-01-01', '2024-05-23', '2026-02-01 12:00:00', '2026-02-01T12:00', '2026-02-01 11:59:59',
         '2026-02-01T12:00:00z', '2026-02-01 12:00 +0200', '2024-02-29', '2026-02-01T23:59:59.999999-12:00')
MALFORMED = ('bogus', '2026-13-45', 'notadate', 'x', '', '2026-02-30', '2026-13', '20260201', '2026-W05', 'Today',
             '2026-1-1', 'HEAD~1', '2026-02-01T25:00', '2026-02-01T12', '2026-02-01T12:60', '2026-02-01T12:00:60',
             '2026-02-01T12:00+24:00', '2026-02-01T12:00+02:60', ' 2026-01-01', '2026-01-01 ', '0000', '2025-02-29',
             '2026-032', '2026-02-01T1200')


@pytest.mark.parametrize('value', VALID)
def test_a_form_of_the_grammar_converts_to_itself(value):
    assert is_time_bound(value) and time_bound('since')(value) == value


@pytest.mark.parametrize('value', MALFORMED + (None, True, 20260201))
def test_anything_else_is_an_invalid_request_naming_the_control_and_the_forms(value):
    assert not is_time_bound(value)
    with pytest.raises(ParamValueError) as raised:
        time_bound('until')(value)
    assert str(raised.value) == f'until must be {FORMS}, got {value!r}'


def test_a_typed_list_is_one_setting():
    convert = time_bound('since')
    assert convert(['2026-01-01', '2026-01-01']) == '2026-01-01'
    with pytest.raises(ParamValueError, match="'2026-01-01' and '2026-02-01'; give it once"):
        convert(['2026-01-01', '2026-02-01'])
    with pytest.raises(ParamValueError, match='since must be today'):
        convert(['bogus'])


def test_every_zoned_form_is_one_git_converts_to_local_time():
    """The codec's grammar is Git's: each zoned time it accepts is one Git's date comparison converts."""
    timed = [value for value in VALID if 'T' in value or ' ' in value]
    zoned = [value for value in timed if value[-1] in 'zZ' or re.search(r'[+-]\d{2}:?\d{2}$', value)]
    assert len(zoned) == 6 and all(ZONED.fullmatch(value) for value in zoned), zoned
    assert all(PERIOD.fullmatch(value) for value in VALID if value not in timed and value != 'today')


def test_today_is_the_local_date_and_nothing_else_changes():
    assert resolve_today('today') == date.today().isoformat()
    assert resolve_today('2026-01-15') == '2026-01-15' and resolve_today('') == '' and resolve_today(None) is None


@pytest.mark.parametrize('value,start', [('2026', '2026-01-01'), ('2026-02', '2026-02-01'), ('2026-02-03', '2026-02-03'),
                                         ('2026-02-01T12:00:00z', '2026-02-01T12:00:00Z'),
                                         ('2026-02-01 12:00 +0200', '2026-02-01 12:00 +0200'),
                                         ('2026-01-15T00:00:00.1234-1200', '2026-01-15T00:00:00.1234-1200')])
def test_a_bounds_start_is_an_instant_fromisoformat_reads(value, start):
    assert bound_start(value) == start
    datetime.fromisoformat(start)


def test_todays_start_is_todays_date():
    assert bound_start('today') == date.today().isoformat()


def test_every_valid_form_has_a_start_fromisoformat_reads():
    for value in VALID:
        datetime.fromisoformat(bound_start(value))


def test_the_declaration_is_a_scalar_setting_with_its_flag_and_the_forms_in_its_help():
    spec = time_window_param('until', 'Upper bound on the session date', answers=('a',), requires=('where',),
                             metavar='DATE')
    assert (spec.name, spec.type, spec.default, spec.repeatable, spec.answers, spec.requires) == \
        ('until', 'string', None, False, ('a',), ('where',))
    assert spec.cli.flags == ('--until',) and spec.cli.metavar == 'DATE'
    assert spec.description == f'Upper bound on the session date. Takes {FORMS}'
    assert spec.validate('today') == 'today' and spec.validate(None) is None
    with pytest.raises(ParamValueError, match='^until must be today'):
        spec.validate('2026-02-30')


def test_the_binder_has_no_rule_keyed_on_the_word():
    """A control named since that is no time bound (Pack's git ref; the back2696 test spec) binds any text: the rule is
    the declaration's codec, not the name."""
    ref = ParamSpec('since', 'string', 'A git ref', None, str)
    assert dict(bind_declared_params((ref,), 'since=HEAD~1', transport='uri').peek_items()) == {'since': 'HEAD~1'}
    bound = time_window_param('since', 'Lower bound')
    with pytest.raises(ValueError, match='since must be today'):
        bind_declared_params((bound,), 'since=HEAD~1', transport='uri')
