"""restate_shown_counts and BUDGET_COUNT_FIELDS: the shared API the router uses after a cut (BACK-2653)."""
import pytest

from reveal.adapters.base import ResourceAdapter
from reveal.utils.results import restate_shown_counts

pytestmark = pytest.mark.unit


def test_sets_top_level_and_nested_integer_counts():
    result = {'top': 6, 'population': {'displayed_files': 11, 'analyzed_files': 11}}
    restate_shown_counts(result, ('top', 'population.displayed_files'), 2)
    assert result == {'top': 2, 'population': {'displayed_files': 2, 'analyzed_files': 11}}


def test_absent_paths_and_non_integers_are_left_alone():
    result = {'summary': {'reported': True}, 'other': 'x'}
    restate_shown_counts(result, ('missing', 'summary.reported', 'other.deeper', 'summary.none'), 0)
    assert result == {'summary': {'reported': True}, 'other': 'x'}


def test_zero_is_a_count():
    result = {'displayed_groups': 6}
    restate_shown_counts(result, ('displayed_groups',), 0)
    assert result == {'displayed_groups': 0}


def test_adapters_declare_nothing_by_default():
    assert ResourceAdapter.BUDGET_COUNT_FIELDS == {}
