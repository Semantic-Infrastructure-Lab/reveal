"""calls://?uncalled reports why it left definitions out (BACK-1533).

The exclusions were an inline chain of `continue`; they are now one ordered list of named
predicates, and the result counts each so an over-eager exclusion is visible.
"""
import pytest

from reveal.adapters.calls.index import find_uncalled

pytestmark = pytest.mark.component

SOURCE = '''\
class Box:
    def __init__(self):
        pass

    @property
    def size(self):
        return 1

    def dead_method(self):
        pass


def helper():
    return 1


def used():
    return helper()


def orphan():  # reported
    pass


def kept():  # noqa: uncalled
    pass


def test_something():
    used()
'''


def test_result_counts_every_exclusion_by_reason(tmp_path):
    (tmp_path / 'm.py').write_text(SOURCE, encoding='utf-8')
    result = find_uncalled(str(tmp_path))
    names = {e['name'] for e in result['entries']}
    assert names == {'dead_method', 'orphan'}
    reasons = result['excluded_by_reason']
    assert reasons['implicit'] >= 2          # __init__ and the property
    assert reasons['called'] == 2            # helper, used
    assert reasons['noqa'] == 1              # kept
    assert reasons['test_entry_point'] == 1  # test_something
    assert result['test_entrypoints_excluded'] == reasons['test_entry_point']
    assert result['total_defined'] == len(names) + sum(reasons.values())


def test_including_test_framework_does_not_count_them_as_excluded(tmp_path):
    (tmp_path / 'm.py').write_text(SOURCE, encoding='utf-8')
    result = find_uncalled(str(tmp_path), include_test_framework=True)
    assert 'test_something' in {e['name'] for e in result['entries']}
    assert 'test_entry_point' not in result['excluded_by_reason']
