"""BACK-1062: D002 precision -- structural shape alone is not duplication.

D002's vector mixes identifier frequencies with shape features (line count,
control-flow density, assignment density).  The shape features dominate the
cosine, so two functions with the same skeleton but unrelated content scored
95%+ similar (reveal's own get_file_blame vs get_file_at_ref).  A candidate must
also share most of its identifiers (Jaccard >= D002.MIN_SEQUENCE_MATCH), and a
no-op hook padded with a docstring is not a candidate (BACK-1049's predicate,
shared via duplicates/_bodies.py).
"""

import pytest

from reveal.analyzers.python import PythonAnalyzer
from reveal.rules.duplicates.D002 import D002

pytestmark = pytest.mark.component

HOOKS = '''class Base:
    def _hook_one(self, node):
        """Hook: override to report the first kind of thing.

        Languages override this where their grammar needs it.
        No-op by default; see the analyzer subclasses.
        Padding line so the raw body passes the size gate.
        Padding line so the raw body passes the size gate.
        """
        return []

    def _hook_two(self, node):
        """Hook: override to report the second kind of thing.

        Languages override this where their grammar needs it.
        No-op by default; see the analyzer subclasses.
        Padding line so the raw body passes the size gate.
        Padding line so the raw body passes the size gate.
        """
        return []
'''

SAME_SHAPE_UNRELATED = '''class Svc:
    def read_manifest(self, path):
        entries = []
        for line in open(path):
            if line.startswith('#'):
                continue
            parts = line.split(',')
            if len(parts) > 2:
                entries.append(parts[0])
        total = len(entries)
        return total

    def render_invoice(self, order):
        rows = {}
        for item in order.items:
            key = item.sku
            rows[key] = rows.get(key, 0) + item.count
            if item.cancelled:
                del rows[key]
        lines = sorted(rows)
        header = self.title.upper()
        footer = len(lines)
        return header, lines, footer
'''

NEAR_DUPLICATE = '''class Svc:
    def read_users(self, path):
        entries = []
        for line in open(path):
            if line.startswith('#'):
                continue
            parts = line.split(',')
            if len(parts) > 2:
                entries.append(parts[0])
        total = len(entries)
        return total

    def read_groups(self, path):
        entries = []
        for line in open(path):
            if line.startswith('#'):
                continue
            parts = line.split(',')
            if len(parts) > 3:
                entries.append(parts[0])
        total = len(entries)
        return total
'''


def _candidates(tmp_path, source):
    path = tmp_path / "m.py"
    path.write_text(source, encoding='utf-8')
    structure = PythonAnalyzer(str(path)).get_structure()
    return D002().check(str(path), structure, source)


def test_padded_noop_hooks_are_not_candidates(tmp_path):
    assert _candidates(tmp_path, HOOKS) == []


def test_same_skeleton_unrelated_content_is_not_a_candidate(tmp_path):
    assert _candidates(tmp_path, SAME_SHAPE_UNRELATED) == []


def test_near_duplicate_is_still_a_candidate(tmp_path):
    (det,) = _candidates(tmp_path, NEAR_DUPLICATE)
    assert "'read_groups'" in det.message and "'read_users'" in det.message


def test_unrelated_function_is_never_named(tmp_path):
    """read_manifest copies read_users, render_invoice is unrelated to both."""
    source = SAME_SHAPE_UNRELATED + "\n" + NEAR_DUPLICATE.replace("class Svc", "class Other")
    messages = " ".join(d.message for d in _candidates(tmp_path, source))
    assert "read_users" in messages and "read_groups" in messages
    assert "render_invoice" not in messages
