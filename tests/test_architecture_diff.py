"""Unit tests for reveal.diff.architecture_diff (BACK-441).

Covers the pure delta logic (diff_snapshots and its helpers) directly,
independent of git/materialization, plus the OID-memoization cache. The
git-backed end-to-end scenario (materialize a real ref, diff against the
working tree, assert on the CLI's --against output) lives in
tests/test_cli_architecture.py alongside the rest of the `architecture`
command's tests.
"""

import unittest
from pathlib import Path
from unittest.mock import patch

from reveal.diff.architecture_diff import (
    StructureCache,
    diff_snapshots,
    _diff_counts,
    _diff_circular_groups,
    _diff_components,
    _diff_entry_points,
)


def _snapshot(
    fan_in=None, fan_out=None, circular_groups=None,
    component_cohesion=None, entry_points=None, complexity_centroid=0.0,
):
    return {
        'fan_in': fan_in or {},
        'fan_out': fan_out or {},
        'circular_groups': circular_groups or [],
        'component_cohesion': component_cohesion or {},
        'entry_points': set(entry_points or []),
        'complexity_centroid': complexity_centroid,
    }


# ── null-vs-zero edge case ───────────────────────────────────────────────────

class TestNullVsZero(unittest.TestCase):
    """Edge case #1: an added/removed file's absent side must be `null`, not
    `0` — collapsing to 0 would falsely imply "existed with count 0"."""

    def test_added_file_base_is_null_not_zero(self):
        base = {}
        head = {'src/new.py': 5}
        result = _diff_counts(base, head, 'fan_in')
        self.assertEqual(result, [
            {'file': 'src/new.py', 'base': None, 'head': 5, 'change': None},
        ])

    def test_removed_file_head_is_null_not_zero(self):
        base = {'src/old.py': 3}
        head = {}
        result = _diff_counts(base, head, 'fan_out')
        self.assertEqual(result, [
            {'file': 'src/old.py', 'base': 3, 'head': None, 'change': None},
        ])

    def test_file_with_genuine_zero_on_both_sides_is_not_a_delta(self):
        # A file present on both sides with an unchanged value (including a
        # real 0) is not a delta at all — must not be confused with "added".
        base = {'src/leaf.py': 0}
        head = {'src/leaf.py': 0}
        self.assertEqual(_diff_counts(base, head, 'fan_in'), [])

    def test_unchanged_nonzero_count_is_not_a_delta(self):
        base = {'src/a.py': 4}
        head = {'src/a.py': 4}
        self.assertEqual(_diff_counts(base, head, 'fan_in'), [])

    def test_changed_count_reports_signed_change(self):
        base = {'src/auth.py': 3}
        head = {'src/auth.py': 9}
        result = _diff_counts(base, head, 'fan_in')
        self.assertEqual(result, [
            {'file': 'src/auth.py', 'base': 3, 'head': 9, 'change': 6},
        ])

    def test_full_diff_snapshots_preserves_null_for_added_file(self):
        base = _snapshot(fan_in={}, fan_out={})
        head = _snapshot(fan_in={'src/c.py': 2}, fan_out={'src/c.py': 0})
        deltas = diff_snapshots(base, head, top_n=20)
        fan_in_entry = next(e for e in deltas['fan_in'] if e['file'] == 'src/c.py')
        self.assertIsNone(fan_in_entry['base'])
        self.assertEqual(fan_in_entry['head'], 2)
        self.assertIsNone(fan_in_entry['change'])


# ── circular groups: introduced / resolved ──────────────────────────────────

class TestCircularGroups(unittest.TestCase):

    def test_introduced_group(self):
        base = []
        head = [frozenset({'a.py', 'b.py'})]
        result = _diff_circular_groups(base, head)
        self.assertEqual(result['introduced'], [['a.py', 'b.py']])
        self.assertEqual(result['resolved'], [])

    def test_resolved_group(self):
        base = [frozenset({'x.py', 'y.py'})]
        head = []
        result = _diff_circular_groups(base, head)
        self.assertEqual(result['introduced'], [])
        self.assertEqual(result['resolved'], [['x.py', 'y.py']])

    def test_unchanged_group_is_neither(self):
        group = frozenset({'a.py', 'b.py'})
        result = _diff_circular_groups([group], [group])
        self.assertEqual(result['introduced'], [])
        self.assertEqual(result['resolved'], [])

    def test_group_membership_change_counts_as_both(self):
        # a.py+b.py -> a.py+b.py+c.py is a different SCC (exact-set diff, per
        # design doc's "Tarjan SCC set difference"), not a "modified" group.
        base = [frozenset({'a.py', 'b.py'})]
        head = [frozenset({'a.py', 'b.py', 'c.py'})]
        result = _diff_circular_groups(base, head)
        self.assertEqual(result['introduced'], [['a.py', 'b.py', 'c.py']])
        self.assertEqual(result['resolved'], [['a.py', 'b.py']])


# ── component coupling ───────────────────────────────────────────────────────

class TestComponentCoupling(unittest.TestCase):

    def test_changed_cohesion_reported(self):
        result = _diff_components({'src/auth': 0.82}, {'src/auth': 0.55})
        self.assertEqual(result, [
            {'component': 'src/auth', 'base_cohesion': 0.82, 'head_cohesion': 0.55, 'change': -0.27},
        ])

    def test_unchanged_cohesion_omitted(self):
        result = _diff_components({'src/auth': 0.82}, {'src/auth': 0.82})
        self.assertEqual(result, [])

    def test_added_component_base_is_null(self):
        result = _diff_components({}, {'src/new': 0.9})
        self.assertEqual(result, [
            {'component': 'src/new', 'base_cohesion': None, 'head_cohesion': 0.9, 'change': None},
        ])

    def test_removed_component_head_is_null(self):
        result = _diff_components({'src/old': 0.4}, {})
        self.assertEqual(result, [
            {'component': 'src/old', 'base_cohesion': 0.4, 'head_cohesion': None, 'change': None},
        ])


# ── entry points ─────────────────────────────────────────────────────────────

class TestEntryPoints(unittest.TestCase):

    def test_added_and_removed(self):
        base = {'src/old_main.py'}
        head = {'src/cli2.py'}
        result = _diff_entry_points(base, head)
        self.assertEqual(result, {'added': ['src/cli2.py'], 'removed': ['src/old_main.py']})

    def test_unchanged_entry_point_not_reported(self):
        base = {'src/main.py'}
        head = {'src/main.py'}
        result = _diff_entry_points(base, head)
        self.assertEqual(result, {'added': [], 'removed': []})


# ── complexity centroid ──────────────────────────────────────────────────────

class TestComplexityCentroid(unittest.TestCase):

    def test_centroid_delta(self):
        base = _snapshot(complexity_centroid=12.4)
        head = _snapshot(complexity_centroid=15.1)
        deltas = diff_snapshots(base, head, top_n=20)
        centroid = deltas['complexity_centroid']
        self.assertEqual(centroid['base'], 12.4)
        self.assertEqual(centroid['head'], 15.1)
        self.assertEqual(centroid['change'], 2.7)
        self.assertEqual(centroid['top_n'], 20)


# ── OID memoization ──────────────────────────────────────────────────────────

class TestStructureCache(unittest.TestCase):
    """Per-file structure extraction memoized by blob OID: parsing is a pure
    function of content, so the same OID must only be parsed once — but this
    cache is never a substitute for recomputing derived graph metrics
    (fan-in/out, SCC, cohesion), which always come from a fresh diff_snapshots
    call over each ref's own full graph."""

    @patch('reveal.diff.architecture_diff._extract_structure')
    def test_same_oid_different_paths_extracted_once(self, mock_extract):
        mock_extract.return_value = {'functions': []}
        cache = StructureCache()

        cache.get_structure(Path('/tmp/base/a.py'), 'oid-123')
        cache.get_structure(Path('/tmp/head/a.py'), 'oid-123')  # same content, different snapshot

        self.assertEqual(mock_extract.call_count, 1)
        self.assertEqual(cache.hits, 1)
        self.assertEqual(cache.misses, 1)

    @patch('reveal.diff.architecture_diff._extract_structure')
    def test_different_oids_both_extracted(self, mock_extract):
        mock_extract.side_effect = [{'functions': ['f1']}, {'functions': ['f2']}]
        cache = StructureCache()

        cache.get_structure(Path('/tmp/base/a.py'), 'oid-aaa')
        cache.get_structure(Path('/tmp/head/a.py'), 'oid-bbb')

        self.assertEqual(mock_extract.call_count, 2)
        self.assertEqual(cache.hits, 0)
        self.assertEqual(cache.misses, 2)

    @patch('reveal.diff.architecture_diff._extract_structure')
    def test_cached_result_is_returned_verbatim(self, mock_extract):
        mock_extract.return_value = {'functions': ['only_call']}
        cache = StructureCache()

        first = cache.get_structure(Path('/tmp/a.py'), 'oid-x')
        second = cache.get_structure(Path('/tmp/b.py'), 'oid-x')

        self.assertEqual(first, second)
        self.assertEqual(mock_extract.call_count, 1)


if __name__ == '__main__':
    unittest.main()
