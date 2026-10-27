"""BACK-2308: ``sort_failed_warning`` is the one builder of the ``sort_failed`` entry.

json:// built it inline (BACK-1614); metrics:// needs the same entry, so the builder moved to
``utils.query_control`` beside ``unknown_sort_field_warning``.
"""
from reveal.utils.query_control import sort_failed_warning, sort_nulls_last
from reveal.utils.results import RESULT_CONTROL_WARNINGS


def _type_error():
    try:
        sort_nulls_last([{'a': 1}, {'a': 'x'}], lambda item: item['a'])
    except TypeError as error:
        return error
    raise AssertionError('mixed int and str compared')


def test_the_entry_names_the_field_and_the_error():
    error = _type_error()
    assert sort_failed_warning('a', error) == {
        'type': 'sort_failed', 'message': f"Not sorted by 'a': {error}"}


def test_the_entry_is_a_result_control_warning():
    # The output seam prints it once; renderers skip it (warning_render).
    assert sort_failed_warning('a', _type_error())['type'] in RESULT_CONTROL_WARNINGS
