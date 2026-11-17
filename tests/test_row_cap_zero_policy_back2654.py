"""The shared zero-policy seam for row caps (BACK-2654 item 2b, Caps row): a cap declares whether its zero means every
row; `row_cap` and `declared_result_control` read that declaration, never a noun-local rule."""
from reveal.utils.query_binding import bind_declared_params
from reveal.utils.query_control import declared_result_control
from reveal.utils.query_parser import ParamSpec, UNCAPPING_ZEROS

UNCAPPED = ParamSpec('limit', 'integer', 'Rows; 0 = no cap', None, int, minimum=0, zero_policy='no cap')
LITERAL = ParamSpec('limit', 'integer', 'Rows; 0 = an empty page', None, int, minimum=0, zero_policy='empty page')
OFFSET = ParamSpec('offset', 'integer', 'Skipped rows', 0, int, minimum=0)


def test_zero_uncaps_follows_the_declared_policy():
    assert {'no cap', 'all', 'uncapped'} == set(UNCAPPING_ZEROS)
    assert UNCAPPED.zero_uncaps and not LITERAL.zero_uncaps


def test_row_cap_turns_an_uncapping_zero_into_every_row():
    assert UNCAPPED.row_cap(0) is None and UNCAPPED.row_cap('0') is None and UNCAPPED.row_cap(None) is None
    assert UNCAPPED.row_cap(5) == 5 and UNCAPPED.row_cap('5') == 5
    # negative control: a literal zero stays a zero cap
    assert LITERAL.row_cap(0) == 0 and LITERAL.row_cap(3) == 3


def test_declared_result_control_lifts_an_uncapping_zero_only():
    control = declared_result_control(bind_declared_params((UNCAPPED, OFFSET), 'limit=0&offset=2', transport='uri'))
    assert vars(control)['limit'] is None and vars(control)['uncapped'] is True and vars(control)['offset'] == 2
    literal = declared_result_control(bind_declared_params((LITERAL, OFFSET), 'limit=0', transport='uri'))
    assert vars(literal)['limit'] == 0 and vars(literal)['uncapped'] is False
    omitted = declared_result_control(bind_declared_params((UNCAPPED, OFFSET), '', transport='uri'))
    assert vars(omitted)['limit'] is None and vars(omitted)['uncapped'] is False


def test_the_declaration_a_value_was_bound_through_is_named():
    params = bind_declared_params((UNCAPPED, OFFSET), 'limit=3', transport='uri')
    assert params.declaration('limit') is UNCAPPED and params.declaration('nosuch') is None
