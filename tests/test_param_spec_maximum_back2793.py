"""ParamSpec's upper bound and the one walk-depth declaration (Scott 2026-11-24, BACK-2793).

``ParamSpec.maximum`` is refused like ``minimum``, never clamped; with both bounds either side reads
``NAME must be LOW..HIGH, got N`` (the converted value, so the text is the same on every transport). A minimum alone
keeps ``NAME must be >= LOW``. ``depth_param()`` declares a walk depth once, graph hops ``WALK_DEPTH`` (1..5).
"""
import pytest

from reveal.utils.query_binding import bind_declared_params
from reveal.utils.query_parser import WALK_DEPTH, ParamSpec, depth_param, whole_number

pytestmark = pytest.mark.component


def _bounded(**bounds):
    return ParamSpec('n', 'integer', '', None, whole_number, **bounds)


@pytest.mark.parametrize('raw,message', [('0', 'n must be 1..5, got 0'), ('6', 'n must be 1..5, got 6'),
                                         ('-1', 'n must be 1..5, got -1'), (' 9 ', 'n must be 1..5, got 9')])
def test_both_bounds_refuse_either_side_with_the_range(raw, message):
    with pytest.raises(ValueError, match=f'^{message}$'):
        _bounded(minimum=1, maximum=5).validate(raw)


@pytest.mark.parametrize('raw,value', [('1', 1), ('5', 5), ('+3', 3), (4, 4), (None, None)])
def test_both_bounds_accept_the_range_and_an_absent_value(raw, value):
    assert _bounded(minimum=1, maximum=5).validate(raw) == value


def test_a_minimum_alone_keeps_its_message_and_a_maximum_alone_names_its_bound():
    with pytest.raises(ValueError, match='^n must be >= 0$'):
        _bounded(minimum=0).validate('-1')
    assert _bounded(minimum=0).validate('99') == 99
    with pytest.raises(ValueError, match='^n must be <= 3, got 4$'):
        _bounded(maximum=3).validate('4')
    assert _bounded(maximum=3).validate('-7') == -7


def test_the_schema_states_both_bounds():
    schema = _bounded(minimum=1, maximum=5).schema()
    assert (schema['minimum'], schema['maximum']) == (1, 5)
    assert 'maximum' not in _bounded(minimum=0).schema()


def test_depth_param_declares_graph_hops_once():
    spec = depth_param('levels to walk', default=2, answers=('callers',), requires=('x=1',), examples=('--depth 2',))
    assert WALK_DEPTH == (1, 5)
    assert (spec.name, spec.type, spec.default, spec.minimum, spec.maximum) == ('depth', 'integer', 2, 1, 5)
    assert spec.description == '1..5 levels to walk' and spec.cli.flags == ('--depth',)
    assert (spec.answers, spec.requires, spec.examples) == (('callers',), ('x=1',), ('--depth 2',))
    for raw in ('1.5', '2.0', 'x', True):
        with pytest.raises(ValueError, match='whole number'):
            spec.validate(raw)


@pytest.mark.parametrize('transport,source,overrides', [('uri', 'depth=6', None), ('typed', {'depth': 6}, None),
                                                        ('uri', '', {'depth': 0})])
def test_the_binder_refuses_an_out_of_range_depth_on_every_source(transport, source, overrides):
    with pytest.raises(ValueError, match=r'^depth must be 1\.\.5, got (6|0)$'):
        bind_declared_params([depth_param('Hops')], source, transport=transport, overrides=overrides)


def test_the_binder_binds_an_in_range_depth():
    spec = depth_param('Hops')
    assert spec.read(bind_declared_params([spec], 'depth=5', transport='uri')) == 5
