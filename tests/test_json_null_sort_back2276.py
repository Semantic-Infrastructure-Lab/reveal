"""BACK-2276: json:// ``?sort=-field`` with a null (or missing) value sorts.

The sort key gave a null ``(0, '')`` in descending order, which was then compared with
``(0, 30)``: ``'<' not supported between 'int' and 'str'``, so the array stayed in source
order with a ``sort_failed`` warning. Ascending order worked. Null and missing values now
sort last in both directions, in their source order, as ``utils/query_control`` already
orders them for ast:// and metrics://.
"""

import json

import pytest

from reveal.adapters.json.adapter import JsonAdapter

ROWS = [
    {'n': 'a', 'age': 30},
    {'n': 'b', 'age': 25},
    {'n': 'nul1', 'age': None},
    {'n': 'c', 'age': 40},
    {'n': 'miss'},
    {'n': 'nul2', 'age': None},
]


@pytest.fixture
def people(tmp_path):
    path = tmp_path / 'people.json'
    path.write_text(json.dumps(ROWS), encoding='utf-8')
    return path


def _sorted(path, query):
    result = JsonAdapter(str(path), query).get_structure()
    return [row['n'] for row in result['value']], result


def test_descending_sort_puts_nulls_last(people):
    names, result = _sorted(people, 'sort=-age')
    assert names == ['c', 'a', 'b', 'nul1', 'miss', 'nul2']
    assert 'warnings' not in result


def test_descending_sort_pages_past_the_nulls(people):
    names, _ = _sorted(people, 'sort=-age&offset=1&limit=3')
    assert names == ['a', 'b', 'nul1']


# Negative controls: what must not change.

def test_ascending_sort_still_puts_nulls_last(people):
    names, result = _sorted(people, 'sort=age')
    assert names == ['b', 'a', 'c', 'nul1', 'miss', 'nul2']
    assert 'warnings' not in result


def test_values_that_do_not_compare_still_disclose(tmp_path):
    path = tmp_path / 'mixed.json'
    path.write_text(json.dumps([{'a': 1}, {'a': None}, {'a': 'x'}, {'a': 3}]), encoding='utf-8')
    for query in ('sort=a', 'sort=-a'):
        result = JsonAdapter(str(path), query).get_structure()
        assert [v['a'] for v in result['value']] == [1, None, 'x', 3]  # source order
        [warning] = result['warnings']
        assert warning['type'] == 'sort_failed'
