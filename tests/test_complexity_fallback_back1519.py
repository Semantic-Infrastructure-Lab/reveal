"""BACK-1519: one fallback complexity number for a function with no tree-sitter score.

ast:// (line-count buckets), stats:// (``estimate_complexity``, its own keyword list)
and C901 (its own keyword list) each had a private fallback, so one function with no
analyzer-supplied ``complexity`` read as three different numbers.
"""

import re
import unittest
from types import SimpleNamespace

from reveal.adapters.ast.analysis import create_element_dict
from reveal.adapters.stats.metrics import estimate_complexity
from reveal.rules.complexity.C901 import C901

ROUNDS = 12
# Each round: ' if ', ' and ', ' or ' on one line and 'elif ' on the next. C901's list counts
# 4 per round (the 'else:' line counts 0); stats' list counts 6 ('if ' also matches inside
# 'elif ', plus 'else:'); the ast line-count bucket (37 lines) says 5.
ROUND = '    if x and y or z:\n    elif x:\n    else:\n'
CONTENT = 'def f(x, y, z):\n' + ROUND * ROUNDS
LINE_END = 1 + 3 * ROUNDS
CANONICAL = 1 + 4 * ROUNDS


def _record(**extra) -> dict:
    """A function record as a non-tree-sitter analyzer reports it (no ``complexity``)."""
    rec = {'name': 'f', 'line': 1, 'line_end': LINE_END, 'line_count': LINE_END}
    rec.update(extra)
    return rec


def _ast_number(rec: dict) -> int:
    analyzer = SimpleNamespace(content=CONTENT)
    return create_element_dict('f.py', 'functions', dict(rec), analyzer)['complexity']


def _stats_number(rec: dict) -> int:
    return estimate_complexity(dict(rec), CONTENT)


def _c901_number(rec: dict) -> int:
    detections = C901().check('f.py', {'functions': [dict(rec)]}, CONTENT)
    assert len(detections) == 1, detections
    return int(re.search(r'complexity: (\d+)', detections[0].message).group(1))


class TestOneFallbackNumber(unittest.TestCase):

    def test_three_paths_agree_without_tree_sitter_complexity(self):
        numbers = {'ast': _ast_number(_record()), 'stats': _stats_number(_record()),
                   'c901': _c901_number(_record())}
        self.assertEqual(len(set(numbers.values())), 1, numbers)

    def test_the_agreed_number_is_c901s_keyword_count(self):
        # C901's list is the canonical one (BACK-1519): 1 + 12 rounds * (if, and, or, elif)
        self.assertEqual(_c901_number(_record()), CANONICAL)
        self.assertEqual(_ast_number(_record()), CANONICAL)
        self.assertEqual(_stats_number(_record()), CANONICAL)

    # Negative controls: a supplied tree-sitter score is never replaced by the fallback.
    def test_supplied_score_wins_in_all_three(self):
        rec = _record(complexity=7)
        self.assertEqual(_ast_number(rec), 7)
        self.assertEqual(_stats_number(rec), 7)
        self.assertEqual(C901().check('f.py', {'functions': [rec]}, CONTENT), [])

    def test_straight_line_function_is_one_everywhere(self):
        content = 'def g():\n    return 1\n'
        rec = {'name': 'g', 'line': 1, 'line_end': 2, 'line_count': 2}
        analyzer = SimpleNamespace(content=content)
        self.assertEqual(create_element_dict('g.py', 'functions', dict(rec), analyzer)['complexity'], 1)
        self.assertEqual(estimate_complexity(dict(rec), content), 1)


if __name__ == '__main__':
    unittest.main()
