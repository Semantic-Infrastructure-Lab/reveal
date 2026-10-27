"""A declined component cohesion is not a drift from or to 0.0 in architecture diff (BACK-1428)."""
from reveal.diff.architecture_diff import _diff_components, _normalize_snapshot
from pathlib import Path


def _raw(root, components):
    return {'root': root, 'fan_in_out': [], 'circular_groups': [], 'components': components,
            'entry_points': [], 'complex_fns': [], 'unsupported_extensions': {}}


def test_declined_component_is_not_read_as_cohesion_zero(tmp_path):
    comp = {'component': str(tmp_path / 'util'), 'files': 2, 'internal': 0, 'outgoing': 0, 'incoming': 0,
            'cohesion': None, 'cohesion_reason': 'same-package visibility', 'top_bridge': None}
    snapshot = _normalize_snapshot(_raw(tmp_path, [comp]), 5)
    assert snapshot['component_cohesion'].get('util') is None
    assert 'util' in snapshot['component_declined']


def test_two_declined_sides_produce_no_delta():
    assert _diff_components({}, {}, base_declined={'util'}, head_declined={'util'}) == []


def test_measured_to_declined_is_flagged_not_a_drop_to_zero():
    out = _diff_components({'util': 0.8}, {}, base_declined=set(), head_declined={'util'})
    assert out == [{'component': 'util', 'base_cohesion': 0.8, 'head_cohesion': None, 'change': None,
                    'declined_on': 'head'}]


def test_negative_control_measured_components_diff_as_before():
    assert _diff_components({'a': 0.5, 'b': 0.2}, {'a': 0.75, 'c': 1.0}) == [
        {'component': 'a', 'base_cohesion': 0.5, 'head_cohesion': 0.75, 'change': 0.25},
        {'component': 'b', 'base_cohesion': 0.2, 'head_cohesion': None, 'change': None},
        {'component': 'c', 'base_cohesion': None, 'head_cohesion': 1.0, 'change': None},
    ]
