"""Tests for depth=, has_annotations=, and callers= ast:// filters.

BACK-242: depth>N nesting depth filter
BACK-239: has_annotations=false annotation coverage filter
BACK-243: callers>N inbound coupling filter
"""

import os
import tempfile
import unittest

from reveal.adapters.ast.adapter import AstAdapter
from reveal.adapters.ast.filtering import _has_annotations


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_temp(code: str, suffix: str = '.py') -> str:
    f = tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False, encoding='utf-8')
    f.write(code)
    f.flush()
    f.close()
    return f.name


def _results_by_name(path: str, query_string: str):
    adapter = AstAdapter(path, query_string)
    s = adapter.get_structure()
    return {r['name']: r for r in s.get('results', [])}


# ---------------------------------------------------------------------------
# _has_annotations unit tests
# ---------------------------------------------------------------------------

class TestHasAnnotations(unittest.TestCase):

    def test_no_sig_returns_false(self):
        self.assertFalse(_has_annotations(''))

    def test_no_annotations(self):
        self.assertFalse(_has_annotations('foo(a, b, c)'))

    def test_return_annotation_only(self):
        self.assertTrue(_has_annotations('foo(a, b) -> bool'))

    def test_param_annotation_only(self):
        self.assertTrue(_has_annotations('foo(a: int, b)'))

    def test_both_annotations(self):
        self.assertTrue(_has_annotations('foo(a: int, b: str) -> bool'))

    def test_self_only_no_annotations(self):
        self.assertFalse(_has_annotations('method(self)'))

    def test_generic_return(self):
        self.assertTrue(_has_annotations('get_data(self) -> Dict[str, Any]'))

    def test_none_return(self):
        self.assertTrue(_has_annotations('cleanup(self) -> None'))


# ---------------------------------------------------------------------------
# BACK-242: depth filter
# ---------------------------------------------------------------------------

DEEP_CODE = '''\
def shallow(x):
    return x + 1


def medium(items):
    result = []
    for item in items:
        if item > 0:
            result.append(item)
    return result


def deep_nested(data):
    result = []
    for item in data:
        if item:
            for sub in item:
                if sub > 0:
                    if sub < 100:
                        result.append(sub)
    return result
'''


class TestDepthFilter(unittest.TestCase):

    def setUp(self):
        self.path = _write_temp(DEEP_CODE)

    def tearDown(self):
        os.unlink(self.path)

    def test_depth_field_present(self):
        fns = _results_by_name(self.path, 'type=function')
        self.assertIn('depth', fns['shallow'])

    def test_shallow_has_low_depth(self):
        fns = _results_by_name(self.path, 'type=function')
        self.assertLessEqual(fns['shallow']['depth'], 1)

    def test_deep_nested_has_high_depth(self):
        fns = _results_by_name(self.path, 'type=function')
        self.assertGreaterEqual(fns['deep_nested']['depth'], 4)

    def test_depth_filter_excludes_shallow(self):
        fns = _results_by_name(self.path, 'depth>3')
        self.assertNotIn('shallow', fns)

    def test_depth_filter_includes_deep(self):
        fns = _results_by_name(self.path, 'depth>3')
        self.assertIn('deep_nested', fns)

    def test_depth_lte_filter(self):
        fns = _results_by_name(self.path, 'depth<=1')
        self.assertIn('shallow', fns)
        self.assertNotIn('deep_nested', fns)


# ---------------------------------------------------------------------------
# BACK-239: has_annotations filter
# ---------------------------------------------------------------------------

ANNOTATION_CODE = '''\
def unannotated(a, b):
    return a + b


def partly_annotated(a: int, b):
    return a + b


def fully_annotated(a: int, b: str) -> bool:
    return bool(a)


def return_only() -> None:
    pass
'''


class TestHasAnnotationsFilter(unittest.TestCase):

    def setUp(self):
        self.path = _write_temp(ANNOTATION_CODE)

    def tearDown(self):
        os.unlink(self.path)

    def test_false_finds_unannotated(self):
        fns = _results_by_name(self.path, 'has_annotations=false&type=function')
        self.assertIn('unannotated', fns)

    def test_false_excludes_partly_annotated(self):
        fns = _results_by_name(self.path, 'has_annotations=false&type=function')
        self.assertNotIn('partly_annotated', fns)

    def test_false_excludes_fully_annotated(self):
        fns = _results_by_name(self.path, 'has_annotations=false&type=function')
        self.assertNotIn('fully_annotated', fns)

    def test_false_excludes_return_only(self):
        fns = _results_by_name(self.path, 'has_annotations=false&type=function')
        self.assertNotIn('return_only', fns)

    def test_true_finds_annotated(self):
        fns = _results_by_name(self.path, 'has_annotations=true&type=function')
        self.assertIn('fully_annotated', fns)
        self.assertIn('partly_annotated', fns)
        self.assertIn('return_only', fns)

    def test_true_excludes_unannotated(self):
        fns = _results_by_name(self.path, 'has_annotations=true&type=function')
        self.assertNotIn('unannotated', fns)


# ---------------------------------------------------------------------------
# BACK-243: callers filter
# ---------------------------------------------------------------------------

CALLER_CODE = '''\
def helper_a():
    pass


def helper_b():
    pass


def caller_one():
    helper_a()


def caller_two():
    helper_a()
    helper_b()


def caller_three():
    helper_a()
    helper_b()
    helper_a()


def standalone():
    pass
'''


class TestCallersFilter(unittest.TestCase):

    def setUp(self):
        self.path = _write_temp(CALLER_CODE)

    def tearDown(self):
        os.unlink(self.path)

    def test_callers_field_present(self):
        fns = _results_by_name(self.path, 'type=function')
        self.assertIn('called_by', fns['helper_a'])

    def test_callers_gt_1_finds_popular(self):
        fns = _results_by_name(self.path, 'callers>1')
        self.assertIn('helper_a', fns)

    def test_callers_gt_0_excludes_standalone(self):
        fns = _results_by_name(self.path, 'callers>0')
        self.assertNotIn('standalone', fns)

    def test_callers_eq_0_finds_standalone(self):
        # Query parser maps 0 → False; compare_value(0, ==False) is True in Python
        fns = _results_by_name(self.path, 'callers=0')
        self.assertIn('standalone', fns)

    def test_callers_lt_2_finds_single_caller(self):
        fns = _results_by_name(self.path, 'callers<2&callers>0')
        self.assertIn('helper_b', fns)

    def test_callers_combined_with_complexity(self):
        # Ensure callers filter can be combined with other filters
        fns = _results_by_name(self.path, 'callers>0&complexity>1')
        # No functions match both (all are complexity 1)
        self.assertIsInstance(fns, dict)


if __name__ == '__main__':
    unittest.main()
