"""dotted_holder: the shared dotted-path lookup the router's budget and count restatement read (BACK-2667)."""
import pytest

from reveal.utils.results import dotted_holder, restate_shown_counts

pytestmark = pytest.mark.unit


def test_top_level_name_is_held_by_the_result():
    result = {'value': [1, 2]}
    assert dotted_holder(result, 'value') == (result, 'value')


def test_nested_name_is_held_by_its_parent_dict():
    result = {'commits': {'recent': [1, 2, 3]}}
    holder, key = dotted_holder(result, 'commits.recent')
    assert holder is result['commits'] and key == 'recent'


def test_missing_or_non_dict_steps_have_no_holder():
    assert dotted_holder({'commits': [1]}, 'commits.recent') == (None, 'recent')
    assert dotted_holder({}, 'map.fan_in.rows') == (None, 'rows')
    assert dotted_holder('not a dict', 'value') == (None, 'value')


def test_absent_last_key_still_has_its_holder():
    result = {'commits': {}}
    assert dotted_holder(result, 'commits.recent') == (result['commits'], 'recent')


def test_restate_shown_counts_reads_through_it():
    result = {'summary': {'patch_groups_reported': 6}, 'top': 4}
    restate_shown_counts(result, ('summary.patch_groups_reported', 'top', 'summary.absent.deeper'), 1)
    assert result == {'summary': {'patch_groups_reported': 1}, 'top': 1}
