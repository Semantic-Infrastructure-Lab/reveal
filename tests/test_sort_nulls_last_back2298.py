"""BACK-2298: ``utils.query_control.sort_nulls_last``, the one ``?sort=`` null rule."""
import pytest

from reveal.utils.query_control import sort_nulls_last

ROWS = [('a', 2), ('n1', None), ('b', 1), ('c', 2), ('n2', None), ('d', 0)]


def _names(rows):
    return [name for name, _ in rows]


def test_ascending_puts_nulls_last_in_source_order():
    assert _names(sort_nulls_last(ROWS, lambda row: row[1])) == ['d', 'b', 'a', 'c', 'n1', 'n2']


def test_descending_puts_nulls_last_in_source_order():
    # Equal values keep their source order too ('a' before 'c'), as sorted(reverse=True) does.
    assert _names(sort_nulls_last(ROWS, lambda row: row[1], descending=True)) == ['a', 'c', 'b', 'd', 'n1', 'n2']


def test_zero_and_empty_text_are_values_not_nulls():
    rows = [('empty', ''), ('none', None), ('x', 'x')]
    assert _names(sort_nulls_last(rows, lambda row: row[1])) == ['empty', 'x', 'none']
    assert _names(sort_nulls_last(ROWS, lambda row: row[1]))[0] == 'd'  # 0 sorts as a value


def test_input_is_not_mutated_and_the_value_is_read_once_per_item():
    rows = list(ROWS)
    reads = []
    sort_nulls_last(rows, lambda row: reads.append(row) or row[1], descending=True)
    assert rows == ROWS
    assert reads == ROWS


def test_values_that_do_not_compare_raise():
    with pytest.raises(TypeError):
        sort_nulls_last([1, 'a', None], lambda v: v)


def test_empty_and_all_null():
    assert sort_nulls_last([], lambda v: v) == []
    assert sort_nulls_last([None, None], lambda v: v, descending=True) == [None, None]
